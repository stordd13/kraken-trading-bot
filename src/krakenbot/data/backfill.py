"""Exchange-agnostic OHLC gap detection and REST backfill (B3).

Detects missing candles in ``market_data_ohlc`` for the *current* exchange
(always passed by the caller from ``settings.exchange_name`` — this module
contains no exchange literal) and fills them through
:meth:`ExchangeRestClient.fetch_ohlcv`.

Timestamp convention
--------------------
DB rows written by the WebSocket collectors are stamped at the **period end**:
``timestamp = open_time + interval``.  A candle with DB timestamp ``T`` covers
``(T - interval, T]`` and is closed iff ``now >= T``.  Weekly candles open on
Monday 00:00 UTC, so the 10080-minute grid is anchored on Monday (the epoch,
1970-01-01, is a Thursday).

Correctness guarantee — READ BEFORE RUNNING ON ANOTHER EXCHANGE
----------------------------------------------------------------
The backfill is only correct when the REST client returns candles stamped the
way that exchange's rows are stored.  Today this holds for **Bybit only**
(``BybitRestClient.fetch_ohlcv`` returns ``start + interval`` from the raw v5
kline endpoint).  Binance and Kraken clients still return the ccxt *open* time,
and the Binance rows in DB are a mix of Vision (open-stamped) and WS
(end-stamped) data, so the invariant cannot even be defined there.  Running
this backfill with ``EXCHANGE_NAME=binance`` or ``kraken`` would insert candles
shifted by one interval **without any error**.  See
:class:`krakenbot.connectors.exchange.ExchangeRestClient` and
``results/B3_bybit_data_report.md``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
import math
from typing import TYPE_CHECKING, Any

from sqlalchemy import bindparam, text
from sqlalchemy.dialects.postgresql import insert as pg_insert

from krakenbot.core.logger import get_logger
from krakenbot.models.market_data import OHLCData

if TYPE_CHECKING:
    from collections.abc import Iterable, Sequence

    from sqlalchemy.ext.asyncio import AsyncSession

    from krakenbot.connectors.exchange import ExchangeRestClient
    from krakenbot.core.database import DatabaseManager

logger = get_logger(__name__)

#: Max candles per REST call (Bybit v5 / Binance hard limit; clients cap internally too).
FETCH_LIMIT = 1000
#: Extra pages tolerated beyond ``ceil(missing / FETCH_LIMIT)`` before giving up on a gap.
MAX_EXTRA_PAGES = 2
#: Rows per ``INSERT`` statement (PostgreSQL ~65k bound-parameter limit, see skills/database.md).
DEFAULT_BATCH_SIZE = 1000
#: A candle is only considered backfillable this long after its close (REST propagation).
CANDLE_SETTLE = timedelta(seconds=15)
#: Weekly candles open Monday 00:00 UTC; epoch 0 is Thursday 00:00 UTC → +4 days.
_WEEK_ANCHOR_S = 4 * 86_400
_WEEK_MINUTES = 10_080
_PK_COLUMNS = ["timestamp", "pair", "interval", "exchange"]

_INTERNAL_GAPS_SQL = """
WITH ordered AS (
    SELECT pair, interval, timestamp,
           LAG(timestamp) OVER (PARTITION BY pair, interval ORDER BY timestamp) AS prev
    FROM market_data_ohlc
    WHERE exchange = :exchange
      AND pair IN :pairs
      AND interval IN :intervals
      {since_clause}
)
SELECT pair, interval, prev, timestamp AS next
FROM ordered
WHERE prev IS NOT NULL
  AND EXTRACT(EPOCH FROM (timestamp - prev)) > interval * 60
ORDER BY pair, interval, prev
"""

_BOUNDS_SQL = """
SELECT pair, interval, MIN(timestamp) AS min_ts, MAX(timestamp) AS max_ts
FROM market_data_ohlc
WHERE exchange = :exchange
  AND pair IN :pairs
  AND interval IN :intervals
GROUP BY pair, interval
"""


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Gap:
    """A run of missing candles, bounded by the DB timestamps of the first and last one."""

    pair: str
    interval: int
    start: datetime
    end: datetime

    @property
    def step(self) -> timedelta:
        return timedelta(minutes=self.interval)

    @property
    def missing(self) -> int:
        """Number of missing candles (``start`` and ``end`` inclusive)."""
        return int((self.end - self.start) / self.step) + 1


@dataclass(slots=True)
class GapResult:
    """Outcome of one :func:`fill_gap` call (or a dry-run placeholder)."""

    gap: Gap
    fetched: int = 0
    inserted: int = 0
    pages: int = 0
    stop_reason: str = "dry_run"
    error: str | None = None


@dataclass(slots=True)
class BackfillSummary:
    """Result of one :func:`backfill_gaps` run, shared by the CLI and the scheduler."""

    exchange: str
    now: datetime
    dry_run: bool
    results: list[GapResult] = field(default_factory=list)

    @property
    def gaps_found(self) -> int:
        return len(self.results)

    @property
    def gaps_filled(self) -> int:
        if self.dry_run:
            return 0
        return sum(1 for r in self.results if r.error is None)

    @property
    def candles_inserted(self) -> int:
        return sum(r.inserted for r in self.results)

    @property
    def failures(self) -> list[GapResult]:
        return [r for r in self.results if r.error is not None]


# ---------------------------------------------------------------------------
# Pure helpers (no I/O)
# ---------------------------------------------------------------------------


def _as_utc(ts: datetime) -> datetime:
    """Return *ts* as an aware UTC datetime (naive input is assumed UTC)."""
    if ts.tzinfo is None:
        return ts.replace(tzinfo=UTC)
    return ts.astimezone(UTC)


def _anchor_seconds(interval: int) -> int:
    return _WEEK_ANCHOR_S if interval == _WEEK_MINUTES else 0


def floor_to_grid(ts: datetime, interval: int) -> datetime:
    """Floor *ts* to the candle grid of *interval* minutes (Monday-anchored for 1w)."""
    if interval <= 0:
        raise ValueError(f"interval must be positive, got {interval}")
    step = interval * 60
    anchor = _anchor_seconds(interval)
    epoch = int(_as_utc(ts).timestamp())
    floored = (epoch - anchor) // step * step + anchor
    return datetime.fromtimestamp(floored, tz=UTC)


def is_grid_aligned(ts: datetime, interval: int) -> bool:
    """True when *ts* sits exactly on the candle grid (no sub-second part either)."""
    ts_utc = _as_utc(ts)
    return ts_utc.microsecond == 0 and floor_to_grid(ts_utc, interval) == ts_utc


def last_closed_timestamp(now: datetime, interval: int) -> datetime:
    """DB timestamp of the most recent *closed* candle at *now* (end convention)."""
    return floor_to_grid(now, interval)


def internal_gaps_from_rows(rows: Iterable[tuple[str, int, datetime, datetime]]) -> list[Gap]:
    """Turn ``(pair, interval, prev, next)`` LAG rows into :class:`Gap` objects."""
    gaps: list[Gap] = []
    for pair, interval, prev, nxt in rows:
        step = timedelta(minutes=interval)
        prev_utc, next_utc = _as_utc(prev), _as_utc(nxt)
        if next_utc - prev_utc <= step:
            continue
        gaps.append(Gap(pair, interval, prev_utc + step, next_utc - step))
    return gaps


def tail_gap(pair: str, interval: int, max_ts: datetime | None, now: datetime) -> Gap | None:
    """Gap between the last stored candle and the last closed one, if any.

    Returns ``None`` when there is no baseline (nothing stored: that is the
    historical import's job, not a backfill), or when the series is current.
    """
    if max_ts is None:
        logger.info("backfill_no_baseline", pair=pair, interval=interval)
        return None
    step = timedelta(minutes=interval)
    max_utc = _as_utc(max_ts)
    last_closed = last_closed_timestamp(now, interval)
    if max_utc >= last_closed:
        if max_utc > last_closed:
            logger.warning(
                "backfill_future_candle",
                pair=pair,
                interval=interval,
                max_ts=max_utc.isoformat(),
                last_closed=last_closed.isoformat(),
            )
        return None
    return Gap(pair, interval, max_utc + step, last_closed)


def candle_to_row(candle: dict[str, Any], exchange: str) -> dict[str, Any]:
    """Map a ``fetch_ohlcv`` candle dict to an ``OHLCData`` insert row."""
    return {
        "timestamp": _as_utc(candle["timestamp"]),
        "pair": candle["pair"],
        "interval": candle["interval"],
        "exchange": exchange,
        "open": candle["open"],
        "high": candle["high"],
        "low": candle["low"],
        "close": candle["close"],
        "volume": candle["volume"],
        "vwap": candle.get("vwap"),
        "trades_count": candle.get("trades_count"),
    }


# ---------------------------------------------------------------------------
# Database I/O
# ---------------------------------------------------------------------------


async def fetch_timestamp_bounds(
    db_manager: DatabaseManager,
    exchange: str,
    pairs: Sequence[str],
    intervals: Sequence[int],
) -> dict[tuple[str, int], tuple[datetime, datetime] | None]:
    """``(MIN, MAX)(timestamp)`` per (pair, interval) for *exchange*; ``None`` when no row."""
    stmt = text(_BOUNDS_SQL).bindparams(
        bindparam("pairs", expanding=True), bindparam("intervals", expanding=True)
    )
    async with db_manager.read_session() as session:
        result = await session.execute(
            stmt, {"exchange": exchange, "pairs": list(pairs), "intervals": list(intervals)}
        )
        rows = result.all()
    found = {
        (str(pair), int(interval)): (_as_utc(min_ts), _as_utc(max_ts))
        for pair, interval, min_ts, max_ts in rows
    }
    return {(p, i): found.get((p, i)) for p in pairs for i in intervals}


async def fetch_max_timestamps(
    db_manager: DatabaseManager,
    exchange: str,
    pairs: Sequence[str],
    intervals: Sequence[int],
) -> dict[tuple[str, int], datetime | None]:
    """``MAX(timestamp)`` per (pair, interval) for *exchange*; ``None`` when no row."""
    bounds = await fetch_timestamp_bounds(db_manager, exchange, pairs, intervals)
    return {key: (b[1] if b is not None else None) for key, b in bounds.items()}


async def detect_gaps(
    db_manager: DatabaseManager,
    exchange: str,
    pairs: Sequence[str],
    intervals: Sequence[int],
    *,
    now: datetime | None = None,
    lookback: timedelta | None = None,
) -> list[Gap]:
    """Internal gaps (LAG query, optionally limited to the last *lookback*) + tail gaps."""
    now_utc = _as_utc(now) if now is not None else datetime.now(UTC)
    settled_now = now_utc - CANDLE_SETTLE

    params: dict[str, Any] = {
        "exchange": exchange,
        "pairs": list(pairs),
        "intervals": list(intervals),
    }
    since_clause = ""
    if lookback is not None:
        since_clause = "AND timestamp >= :since"
        params["since"] = now_utc - lookback
    stmt = text(_INTERNAL_GAPS_SQL.format(since_clause=since_clause)).bindparams(
        bindparam("pairs", expanding=True), bindparam("intervals", expanding=True)
    )
    async with db_manager.read_session() as session:
        result = await session.execute(stmt, params)
        rows = [(str(p), int(i), prev, nxt) for p, i, prev, nxt in result.all()]

    gaps = internal_gaps_from_rows(rows)
    max_timestamps = await fetch_max_timestamps(db_manager, exchange, pairs, intervals)
    for (pair, interval), max_ts in max_timestamps.items():
        gap = tail_gap(pair, interval, max_ts, settled_now)
        if gap is not None:
            gaps.append(gap)

    gaps.sort(key=lambda g: (g.pair, g.interval, g.start))
    logger.info(
        "backfill_gaps_detected",
        exchange=exchange,
        gaps=len(gaps),
        missing_candles=sum(g.missing for g in gaps),
        lookback_days=lookback.days if lookback else None,
    )
    return gaps


async def insert_candles(
    session: AsyncSession,
    rows: list[dict[str, Any]],
    *,
    batch_size: int = DEFAULT_BATCH_SIZE,
) -> int:
    """Insert *rows* with ``ON CONFLICT DO NOTHING`` in batches; returns rows inserted.

    Existing rows (e.g. written by the WebSocket collector) always win.
    """
    if batch_size <= 0:
        raise ValueError("batch_size must be positive")
    inserted = 0
    for i in range(0, len(rows), batch_size):
        batch = rows[i : i + batch_size]
        stmt = pg_insert(OHLCData).values(batch).on_conflict_do_nothing(index_elements=_PK_COLUMNS)
        result = await session.execute(stmt)
        rowcount = getattr(result, "rowcount", -1)
        inserted += len(batch) if not isinstance(rowcount, int) or rowcount < 0 else rowcount
    return inserted


# ---------------------------------------------------------------------------
# Backfill
# ---------------------------------------------------------------------------


async def fill_gap(
    rest_client: ExchangeRestClient,
    db_manager: DatabaseManager,
    gap: Gap,
    exchange: str,
    *,
    batch_size: int = DEFAULT_BATCH_SIZE,
    fetch_limit: int = FETCH_LIMIT,
) -> GapResult:
    """Fetch and insert the candles of one *gap* (pages of *fetch_limit*).

    ``since`` is the open time of the first missing candle (``gap.start -
    interval``); each page advances to the DB timestamp of its newest candle,
    which is the open time of the next one.  Rows outside ``[gap.start,
    gap.end]`` are dropped; a misaligned timestamp raises ``ValueError``.
    """
    result = GapResult(gap=gap, stop_reason="completed")
    step = gap.step
    since = gap.start - step
    max_iter = math.ceil(gap.missing / fetch_limit) + MAX_EXTRA_PAGES

    for _ in range(max_iter):
        batch = await rest_client.fetch_ohlcv(
            gap.pair, gap.interval, since=since, limit=fetch_limit
        )
        result.pages += 1
        if not batch:
            result.stop_reason = "empty_batch"
            break
        result.fetched += len(batch)
        last_ts = max(_as_utc(c["timestamp"]) for c in batch)

        rows: list[dict[str, Any]] = []
        for candle in batch:
            ts = _as_utc(candle["timestamp"])
            if ts < gap.start or ts > gap.end:
                continue
            if not is_grid_aligned(ts, gap.interval):
                raise ValueError(
                    f"misaligned candle from {exchange}: {gap.pair} {gap.interval}m {ts.isoformat()}"
                )
            rows.append(candle_to_row(candle, exchange))
        if rows:
            async with db_manager.session() as session:
                result.inserted += await insert_candles(session, rows, batch_size=batch_size)

        if last_ts >= gap.end:
            break
        if last_ts <= since:
            result.stop_reason = "not_advancing"
            logger.warning(
                "backfill_cursor_not_advancing",
                pair=gap.pair,
                interval=gap.interval,
                since=since.isoformat(),
                last_ts=last_ts.isoformat(),
            )
            break
        since = last_ts
    else:
        result.stop_reason = "max_iterations"
        logger.warning(
            "backfill_max_iterations",
            pair=gap.pair,
            interval=gap.interval,
            pages=result.pages,
            missing=gap.missing,
        )

    logger.info(
        "backfill_gap_filled",
        exchange=exchange,
        pair=gap.pair,
        interval=gap.interval,
        start=gap.start.isoformat(),
        end=gap.end.isoformat(),
        missing=gap.missing,
        fetched=result.fetched,
        inserted=result.inserted,
        pages=result.pages,
        stop_reason=result.stop_reason,
    )
    return result


async def backfill_gaps(
    rest_client: ExchangeRestClient,
    db_manager: DatabaseManager,
    exchange: str,
    pairs: Sequence[str],
    intervals: Sequence[int],
    *,
    now: datetime | None = None,
    lookback: timedelta | None = None,
    dry_run: bool = False,
    batch_size: int = DEFAULT_BATCH_SIZE,
    fetch_limit: int = FETCH_LIMIT,
) -> BackfillSummary:
    """Detect every gap for *exchange* and fill them sequentially.

    One gap failing (network, misaligned data) is recorded in its
    :class:`GapResult` and does not stop the others.  With *dry_run* nothing
    is fetched or written.
    """
    now_utc = _as_utc(now) if now is not None else datetime.now(UTC)
    summary = BackfillSummary(exchange=exchange, now=now_utc, dry_run=dry_run)
    gaps = await detect_gaps(db_manager, exchange, pairs, intervals, now=now_utc, lookback=lookback)

    for gap in gaps:
        if dry_run:
            summary.results.append(GapResult(gap=gap))
            continue
        try:
            summary.results.append(
                await fill_gap(
                    rest_client,
                    db_manager,
                    gap,
                    exchange,
                    batch_size=batch_size,
                    fetch_limit=fetch_limit,
                )
            )
        except Exception as e:  # noqa: BLE001 — one gap must not stop the run
            logger.error(
                "backfill_gap_failed",
                exchange=exchange,
                pair=gap.pair,
                interval=gap.interval,
                start=gap.start.isoformat(),
                end=gap.end.isoformat(),
                error=str(e),
                error_type=type(e).__name__,
            )
            summary.results.append(GapResult(gap=gap, stop_reason="error", error=str(e)))

    logger.info(
        "backfill_completed",
        exchange=exchange,
        dry_run=dry_run,
        gaps_found=summary.gaps_found,
        gaps_filled=summary.gaps_filled,
        candles_inserted=summary.candles_inserted,
        failures=len(summary.failures),
    )
    return summary
