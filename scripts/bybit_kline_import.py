"""One-shot historical kline import for Bybit EU (B3).

Pages ``GET /v5/market/kline?category=spot`` (through
``BybitRestClient.fetch_ohlcv``, raw endpoint: ``vwap = turnover/volume``,
``timestamp = start + interval`` like the WebSocket rows) from the first EU
candle (2025-06-11) to now for every configured pair × interval and inserts
with ``ON CONFLICT DO NOTHING`` in batches of 1000 — candles already written
by the running collector always win.

Resumable: without ``--force-full`` each (pair, interval) restarts from its
``MAX(timestamp)`` (the DB timestamp is the period end = open time of the next
candle) — **unless** the series has a leading hole (``MIN(timestamp)`` later
than ``--since``: the collector wrote recent rows but the history was never
imported), in which case it scans from ``--since`` and lets ``ON CONFLICT``
skip the rows already there.  Flat candles (``volume=0``) are real candles
and are written.

Stop condition (proved in the logs, ``last_responses``): a page shorter than
1000 rows is followed by a call from its last candle that returns no closed
candle (``empty``), or the page reaches the last closed candle (``reached_now``).

Usage (server, tmux, collector running — never through the SSH tunnel)::

    tmux new -s b3-import
    poetry run python scripts/bybit_kline_import.py                 # resume all 3 pairs x 7 TF
    poetry run python scripts/bybit_kline_import.py --dry-run       # cursors + estimated calls
    poetry run python scripts/bybit_kline_import.py --pairs BTC/USDC --intervals 60 --force-full
"""

# ruff: noqa: E402

from __future__ import annotations

import argparse
import asyncio
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
import math
from pathlib import Path
import sys
import time
from typing import Any

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / ".env")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from krakenbot.config.settings import get_settings
from krakenbot.connectors.exchange import ExchangeRestClient, build_exchange_rest_client
from krakenbot.core.database import DatabaseManager
from krakenbot.core.event_bus import get_event_bus
from krakenbot.core.logger import get_logger
from krakenbot.data.backfill import (
    candle_to_row,
    fetch_timestamp_bounds,
    floor_to_grid,
    insert_candles,
    is_grid_aligned,
    last_closed_timestamp,
)

logger = get_logger(__name__).bind(component="bybit_kline_import")

TARGET_EXCHANGE = "bybit"  # this script is Bybit-specific by design (raw v5 kline history)
DEFAULT_SINCE = datetime(2025, 6, 1, tzinfo=UTC)  # before the first EU candle (2025-06-11)
EU_HISTORY_START = datetime(2025, 6, 11, tzinfo=UTC)  # first Bybit EU spot candles (B0 audit)
PAGE_LIMIT = 1000
PROGRESS_EVERY_PAGES = 10
INTERVAL_LABEL = {1: "1m", 5: "5m", 15: "15m", 60: "1h", 240: "4h", 1440: "1d", 10080: "1w"}


@dataclass(slots=True)
class ImportStats:
    """Per (pair, interval) outcome."""

    pair: str
    interval: int
    since: datetime
    resumed: bool
    pages: int = 0
    fetched: int = 0
    inserted: int = 0
    first_ts: datetime | None = None
    last_ts: datetime | None = None
    stop_reason: str = "dry_run"
    duration_s: float = 0.0
    estimated_calls: int = 0
    last_responses: list[dict[str, Any]] = field(default_factory=list)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--pairs", nargs="+", default=None, help="Default: SCHEDULER_PAIRS.")
    parser.add_argument(
        "--intervals", nargs="+", type=int, default=None, help="Default: SCHEDULER_INTERVALS."
    )
    parser.add_argument(
        "--since",
        type=lambda s: datetime.fromisoformat(s).replace(tzinfo=UTC),
        default=DEFAULT_SINCE,
        help="Start (UTC, ISO) when there is no data yet or with --force-full "
        "(default 2025-06-01).",
    )
    parser.add_argument(
        "--force-full",
        action="store_true",
        help="Ignore MAX(timestamp) and rescan from --since (ON CONFLICT DO NOTHING keeps DB rows).",
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="Only print the resume cursor and estimated calls."
    )
    return parser.parse_args(argv)


def resolve_since(
    bounds: tuple[datetime, datetime] | None,
    default_since: datetime,
    interval: int,
    *,
    force_full: bool,
    history_start: datetime = EU_HISTORY_START,
) -> tuple[datetime, bool]:
    """(open time of the first candle to fetch, resumed?).

    *bounds* is ``(MIN, MAX)(timestamp)`` of the stored series or ``None``.
    Resume from ``MAX`` only when the stored series starts close to the
    exchange's first candle (``history_start``, tolerance ``max(1 day, 2 ×
    interval)`` — the first 1w candle closes 5 days after the EU opening).  A
    series that begins later has a leading hole (rows written by the live
    collector, history never imported) and is scanned from the requested start;
    ``ON CONFLICT DO NOTHING`` keeps the existing rows.
    """
    start = floor_to_grid(default_since, interval)
    if force_full or bounds is None:
        return start, False
    min_ts, max_ts = bounds
    step = timedelta(minutes=interval)
    expected_first = max(start, history_start) + max(timedelta(days=1), 2 * step)
    if min_ts > expected_first:
        logger.info(
            "bybit_import_leading_hole",
            interval=interval,
            min_ts=min_ts.isoformat(),
            expected_first_before=expected_first.isoformat(),
            action="full scan from requested start (ON CONFLICT keeps existing rows)",
        )
        return start, False
    return max_ts, True  # DB ts = period end = open time of the next candle


def _response_digest(since: datetime, batch: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "since": since.isoformat(),
        "candles": len(batch),
        "first": batch[0]["timestamp"].isoformat() if batch else None,
        "last": batch[-1]["timestamp"].isoformat() if batch else None,
    }


async def import_pair_interval(
    rest_client: ExchangeRestClient,
    db_manager: DatabaseManager | None,
    exchange: str,
    pair: str,
    interval: int,
    *,
    since: datetime,
    resumed: bool,
    now: datetime,
    batch_size: int = 1000,
    dry_run: bool = False,
) -> ImportStats:
    """Page one (pair, interval) from *since* up to the last closed candle."""
    stats = ImportStats(pair=pair, interval=interval, since=since, resumed=resumed)
    step = timedelta(minutes=interval)
    last_closed = last_closed_timestamp(now, interval)
    stats.estimated_calls = max(0, math.ceil(((last_closed - since) / step) / PAGE_LIMIT))
    if dry_run or since >= last_closed:
        stats.stop_reason = "dry_run" if dry_run else "already_current"
        return stats

    t0 = time.monotonic()
    cursor = since
    while True:
        batch = await rest_client.fetch_ohlcv(pair, interval, since=cursor, limit=PAGE_LIMIT)
        stats.pages += 1
        stats.last_responses = (stats.last_responses + [_response_digest(cursor, batch)])[-2:]
        if not batch:
            stats.stop_reason = "empty"
            break

        stats.fetched += len(batch)
        rows: list[dict[str, Any]] = []
        for candle in batch:
            ts = candle["timestamp"]
            if not is_grid_aligned(ts, interval):
                raise ValueError(f"misaligned candle {pair} {interval}m {ts.isoformat()}")
            rows.append(candle_to_row(candle, exchange))
        if stats.first_ts is None:
            stats.first_ts = rows[0]["timestamp"]
        batch_last = rows[-1]["timestamp"]
        stats.last_ts = batch_last

        if db_manager is not None:
            async with db_manager.session() as session:
                stats.inserted += await insert_candles(session, rows, batch_size=batch_size)

        if stats.pages % PROGRESS_EVERY_PAGES == 0:
            logger.info(
                "bybit_import_progress",
                pair=pair,
                interval=interval,
                pages=stats.pages,
                estimated_calls=stats.estimated_calls,
                fetched=stats.fetched,
                inserted=stats.inserted,
                cursor=batch_last.isoformat(),
                elapsed_s=round(time.monotonic() - t0, 1),
            )

        if batch_last <= cursor:
            stats.stop_reason = "not_advancing"
            logger.warning(
                "bybit_import_not_advancing",
                pair=pair,
                interval=interval,
                cursor=cursor.isoformat(),
                last=batch_last.isoformat(),
            )
            break
        cursor = batch_last
        if batch_last >= last_closed:
            stats.stop_reason = "reached_now"
            break

    stats.duration_s = round(time.monotonic() - t0, 1)
    logger.info(
        "bybit_import_done",
        pair=pair,
        interval=interval,
        resumed=resumed,
        since=since.isoformat(),
        pages=stats.pages,
        fetched=stats.fetched,
        inserted=stats.inserted,
        first_ts=stats.first_ts.isoformat() if stats.first_ts else None,
        last_ts=stats.last_ts.isoformat() if stats.last_ts else None,
        stop_reason=stats.stop_reason,
        duration_s=stats.duration_s,
        last_responses=stats.last_responses,
    )
    return stats


def format_table(results: list[ImportStats], total_duration_s: float) -> str:
    lines = [
        "=" * 118,
        "  Bybit EU kline import",
        "=" * 118,
        f"  {'Pair':<9} {'TF':<4} {'Since (open)':<26} {'Res':<3} {'Est.':>5} {'Pages':>5} "
        f"{'Fetched':>8} {'Inserted':>8} {'Last ts':<26} {'Dur s':>7}  Stop",
    ]
    for s in results:
        lines.append(
            f"  {s.pair:<9} {INTERVAL_LABEL.get(s.interval, f'{s.interval}m'):<4} "
            f"{s.since.isoformat():<26} {'yes' if s.resumed else 'no':<3} {s.estimated_calls:>5} "
            f"{s.pages:>5} {s.fetched:>8} {s.inserted:>8} "
            f"{(s.last_ts.isoformat() if s.last_ts else '-'):<26} {s.duration_s:>7}  {s.stop_reason}"
        )
    lines.append("  " + "-" * 116)
    lines.append(
        f"  total: pages={sum(s.pages for s in results)} fetched={sum(s.fetched for s in results)} "
        f"inserted={sum(s.inserted for s in results)} duration={total_duration_s:.0f}s"
    )
    return "\n".join(lines)


async def _async_main(args: argparse.Namespace) -> int:
    settings = get_settings()
    if settings.exchange_name.lower() != TARGET_EXCHANGE:
        logger.error(
            "bybit_import_wrong_exchange",
            exchange=settings.exchange_name,
            expected=TARGET_EXCHANGE,
        )
        return 2
    exchange = settings.exchange_name
    pairs = args.pairs or list(settings.scheduler.pairs)
    intervals = args.intervals or list(settings.scheduler.intervals)

    db_manager = DatabaseManager()
    await db_manager.init_db(settings)
    rest_client = build_exchange_rest_client(settings, get_event_bus(), db_manager, read_only=True)
    results: list[ImportStats] = []
    t0 = time.monotonic()
    try:
        bounds = await fetch_timestamp_bounds(db_manager, exchange, pairs, intervals)
        for pair in pairs:
            for interval in intervals:
                since, resumed = resolve_since(
                    bounds.get((pair, interval)),
                    args.since,
                    interval,
                    force_full=args.force_full,
                )
                logger.info(
                    "bybit_import_start",
                    pair=pair,
                    interval=interval,
                    since=since.isoformat(),
                    resumed=resumed,
                    dry_run=args.dry_run,
                )
                results.append(
                    await import_pair_interval(
                        rest_client,
                        None if args.dry_run else db_manager,
                        exchange,
                        pair,
                        interval,
                        since=since,
                        resumed=resumed,
                        now=datetime.now(UTC),
                        batch_size=settings.scheduler.batch_size,
                        dry_run=args.dry_run,
                    )
                )
    finally:
        await rest_client.close()
        await db_manager.close_db()

    print()
    print(format_table(results, time.monotonic() - t0))
    print()
    return 0


def main(argv: list[str] | None = None) -> int:
    return asyncio.run(_async_main(parse_args(argv)))


if __name__ == "__main__":
    raise SystemExit(main())
