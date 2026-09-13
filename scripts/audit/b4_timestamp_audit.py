"""B4.1 — Binance timestamp convention audit (READ-ONLY, no write ever).

Classifies every ``exchange='binance'`` series (pair × interval) as open- or
end-stamped by content, using the reference exchange (Bybit, end-stamped by
construction) on the overlap period, and writes the **boundary manifest**
(``results/b4_binance_stamp_boundaries.json``) that drives the re-stamp
migration.  Sections follow the brief (``agent/AGENT_B4_1_...md`` § 4):

  a) map of the series: bounds, counts, internal gaps (LAG), grid alignment
  b) classification per weekly window (open vs end), duplicate signature
  c) migration quantification: rows to re-stamp, PK collisions (content compared)
  d) exact boundaries → JSON manifest (source of truth of the perimeter)
  e) upstream edge around the boundary + spot checks

``--post-migration`` replays the same checks after the re-stamp and expects the
*end* hypothesis to win **every** window (strict, GATE 1 decision a — the rows
that were ambiguous before the migration must vote end at ``T + interval``),
counts equal to the manifest, gaps shifted by one interval, the spot checks
moved by one interval, and the last 1w candle of each pair to be a complete
week cross-checked against the 1d closes (brief § 6 invariants 1-5 + decision c).

Usage (via the SSH tunnel is fine — reads only)::

    poetry run python scripts/audit/b4_timestamp_audit.py \
        --out-json results/b4_binance_stamp_boundaries.json --out-md /tmp/b4_audit.md
    poetry run python scripts/audit/b4_timestamp_audit.py --post-migration \
        --boundaries results/b4_binance_stamp_boundaries.json

Exit code 0 when every series is consistent with the expected convention and
no divergent collision exists; 1 otherwise (decision at the gate).
"""

# ruff: noqa: E402

from __future__ import annotations

import argparse
import asyncio
from datetime import UTC, datetime, timedelta
from decimal import Decimal
import os
from pathlib import Path
import sys
from typing import Any

import asyncpg
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent.parent
load_dotenv(ROOT / ".env")
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts" / "audit"))

from b4_stamp_lib import (
    INTERVALS,
    PAIRS,
    TARGET_EXCHANGE,
    BoundaryManifest,
    SeriesBoundary,
    WindowVote,
    assess_votes,
    find_switch,
    grid_anchor_seconds,
    label,
    refine_boundary,
    shifted_gaps,
    summarize_votes,
)

from krakenbot.data.backfill import internal_gaps_from_rows, is_grid_aligned

METHOD = (
    "per-row vote on the reference-exchange overlap: the Binance candle at T is compared with the "
    "reference candle at T (end hypothesis) and at T+interval (open hypothesis); the closer close "
    "wins, and when the two candidate closes are within 0.1 % of each other (ambiguous, e.g. two "
    "near-equal weekly closes) the full OHLC distance (|open|+|high|+|low|+|close|) decides; votes "
    "aggregated per ISO week; boundary = last open-stamped row"
)


def _dist(alias: str) -> str:
    """OHLC distance between the Binance row ``bi`` and a reference row alias."""
    return (
        f"(ABS(bi.open - {alias}.open) + ABS(bi.high - {alias}.high) + "
        f"ABS(bi.low - {alias}.low) + ABS(bi.close - {alias}.close))"
    )


D_SAME, D_NEXT = _dist("e"), _dist("o")
#: The two candidate reference closes are too close for the close alone to decide.
AMBIGUOUS = "ABS(e.close - o.close) <= 0.001 * bi.close"
OPEN_WINS = (
    f"(CASE WHEN {AMBIGUOUS} THEN {D_NEXT} < {D_SAME} "
    "ELSE ABS(bi.close - o.close) < ABS(bi.close - e.close) END)"
)
END_WINS = (
    f"(CASE WHEN {AMBIGUOUS} THEN {D_SAME} < {D_NEXT} "
    "ELSE ABS(bi.close - e.close) < ABS(bi.close - o.close) END)"
)

#: (pair, interval, open-stamped timestamp of the candle, expected open, expected close)
SPOT_CHECKS: list[tuple[str, int, datetime, Decimal, Decimal]] = [
    (
        "BTC/USDC",
        1440,
        datetime(2024, 1, 1, tzinfo=UTC),
        Decimal("42274.27"),
        Decimal("44185.08"),
    ),
]


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--pairs", nargs="+", default=PAIRS)
    ap.add_argument("--intervals", nargs="+", type=int, default=INTERVALS)
    ap.add_argument("--reference-exchange", default="bybit")
    ap.add_argument(
        "--overlap-since",
        default="2025-06-01",
        help="Start of the reference overlap used for the content classification (UTC date).",
    )
    ap.add_argument("--out-json", type=Path, default=None, help="Write the boundary manifest.")
    ap.add_argument("--out-md", type=Path, default=None, help="Also write the report text.")
    ap.add_argument(
        "--post-migration",
        action="store_true",
        help="Replay the checks after the re-stamp against --boundaries (expects end-stamped).",
    )
    ap.add_argument(
        "--boundaries",
        type=Path,
        default=ROOT / "results" / "b4_binance_stamp_boundaries.json",
        help="Manifest to compare against in --post-migration mode.",
    )
    return ap.parse_args(argv)


class Report:
    def __init__(self) -> None:
        self.lines: list[str] = []
        self.problems: list[str] = []

    def section(self, title: str) -> None:
        self.add("\n" + "=" * 100 + f"\n{title}\n" + "=" * 100)

    def add(self, line: str = "") -> None:
        print(line)
        self.lines.append(line)

    def problem(self, msg: str) -> None:
        self.problems.append(msg)
        self.add(f"    → STOP: {msg}")

    def text(self) -> str:
        return "\n".join(self.lines) + "\n"


# ---------------------------------------------------------------------------
# Queries (all read-only)
# ---------------------------------------------------------------------------


async def q_totals(conn: asyncpg.Connection) -> dict[str, int]:
    rows = await conn.fetch("SELECT exchange, COUNT(*) AS n FROM market_data_ohlc GROUP BY 1")
    return {r["exchange"]: int(r["n"]) for r in rows}


async def q_bounds(conn: asyncpg.Connection, exchange: str, pair: str, interval: int) -> Any:
    return await conn.fetchrow(
        "SELECT COUNT(*) AS n, MIN(timestamp) AS min_ts, MAX(timestamp) AS max_ts "
        "FROM market_data_ohlc WHERE exchange=$1 AND pair=$2 AND interval=$3",
        exchange,
        pair,
        interval,
    )


async def q_gaps(
    conn: asyncpg.Connection, exchange: str, pair: str, interval: int
) -> list[tuple[datetime, datetime]]:
    rows = await conn.fetch(
        """
        SELECT prev, timestamp AS next FROM (
            SELECT timestamp, LAG(timestamp) OVER (ORDER BY timestamp) AS prev
            FROM market_data_ohlc WHERE exchange=$1 AND pair=$2 AND interval=$3) s
        WHERE prev IS NOT NULL AND EXTRACT(EPOCH FROM (timestamp - prev)) > $3 * 60
        ORDER BY prev
        """,
        exchange,
        pair,
        interval,
    )
    gaps = internal_gaps_from_rows((pair, interval, r["prev"], r["next"]) for r in rows)
    return [(g.start - g.step, g.end + g.step) for g in gaps]


async def q_misaligned(conn: asyncpg.Connection, exchange: str, pair: str, interval: int) -> int:
    row = await conn.fetchrow(
        "SELECT COUNT(*) AS n FROM market_data_ohlc WHERE exchange=$1 AND pair=$2 AND interval=$3 "
        "AND (EXTRACT(EPOCH FROM timestamp)::bigint - $4) % ($3 * 60) <> 0",
        exchange,
        pair,
        interval,
        grid_anchor_seconds(interval),
    )
    return int(row["n"])


async def q_window_votes(
    conn: asyncpg.Connection,
    exchange: str,
    reference: str,
    pair: str,
    interval: int,
    since: datetime,
) -> list[WindowVote]:
    rows = await conn.fetch(
        f"""
        WITH bi AS (SELECT timestamp, open, high, low, close FROM market_data_ohlc
                    WHERE exchange=$1 AND pair=$3 AND interval=$4 AND timestamp >= $5),
             rf AS (SELECT timestamp, open, high, low, close FROM market_data_ohlc
                    WHERE exchange=$2 AND pair=$3 AND interval=$4 AND volume > 0)
        SELECT date_trunc('week', bi.timestamp) AS wk,
               COUNT(*) FILTER (WHERE {OPEN_WINS}) AS n_open,
               COUNT(*) FILTER (WHERE {END_WINS}) AS n_end,
               COUNT(*) FILTER (WHERE NOT {OPEN_WINS} AND NOT {END_WINS}) AS n_tie
        FROM bi
        JOIN rf e ON e.timestamp = bi.timestamp
        JOIN rf o ON o.timestamp = bi.timestamp + make_interval(mins => $4)
        GROUP BY 1 ORDER BY 1
        """,
        exchange,
        reference,
        pair,
        interval,
        since,
    )
    return [WindowVote(r["wk"], int(r["n_open"]), int(r["n_end"]), int(r["n_tie"])) for r in rows]


async def q_row_votes(
    conn: asyncpg.Connection,
    exchange: str,
    reference: str,
    pair: str,
    interval: int,
    start: datetime,
    end: datetime,
) -> list[tuple[datetime, str]]:
    rows = await conn.fetch(
        f"""
        SELECT bi.timestamp,
               CASE WHEN {OPEN_WINS} THEN 'open'
                    WHEN {END_WINS} THEN 'end'
                    ELSE 'tie' END AS vote
        FROM market_data_ohlc bi
        JOIN market_data_ohlc e ON e.exchange=$2 AND e.pair=$3 AND e.interval=$4
             AND e.timestamp = bi.timestamp AND e.volume > 0
        JOIN market_data_ohlc o ON o.exchange=$2 AND o.pair=$3 AND o.interval=$4
             AND o.timestamp = bi.timestamp + make_interval(mins => $4) AND o.volume > 0
        WHERE bi.exchange=$1 AND bi.pair=$3 AND bi.interval=$4
          AND bi.timestamp >= $5 AND bi.timestamp < $6
        ORDER BY bi.timestamp
        """,
        exchange,
        reference,
        pair,
        interval,
        start,
        end,
    )
    return [(r["timestamp"], r["vote"]) for r in rows]


async def q_window_detail(
    conn: asyncpg.Connection,
    exchange: str,
    reference: str,
    pair: str,
    interval: int,
    window_start: datetime,
    expect: str,
) -> list[Any]:
    """Rows of one window that voted against ``expect`` (closes side by side, for the report)."""
    not_expected = f"NOT {OPEN_WINS}" if expect == "open" else f"NOT {END_WINS}"
    return await conn.fetch(
        f"""
        SELECT bi.timestamp, bi.close AS bi_close, e.close AS ref_same, o.close AS ref_next,
               {D_SAME} AS d_same, {D_NEXT} AS d_next
        FROM market_data_ohlc bi
        JOIN market_data_ohlc e ON e.exchange=$2 AND e.pair=$3 AND e.interval=$4
             AND e.timestamp = bi.timestamp AND e.volume > 0
        JOIN market_data_ohlc o ON o.exchange=$2 AND o.pair=$3 AND o.interval=$4
             AND o.timestamp = bi.timestamp + make_interval(mins => $4) AND o.volume > 0
        WHERE bi.exchange=$1 AND bi.pair=$3 AND bi.interval=$4
          AND bi.timestamp >= $5 AND bi.timestamp < $5 + interval '7 days'
          AND {not_expected}
        ORDER BY bi.timestamp LIMIT 20
        """,
        exchange,
        reference,
        pair,
        interval,
        window_start,
    )


async def q_row_detail(
    conn: asyncpg.Connection, exchange: str, reference: str, pair: str, interval: int, ts: datetime
) -> Any:
    return await conn.fetchrow(
        f"""
        SELECT bi.timestamp, bi.close AS bi_close, e.close AS ref_same, o.close AS ref_next,
               {D_SAME} AS d_same, {D_NEXT} AS d_next
        FROM market_data_ohlc bi
        LEFT JOIN market_data_ohlc e ON e.exchange=$2 AND e.pair=$3 AND e.interval=$4
             AND e.timestamp = bi.timestamp
        LEFT JOIN market_data_ohlc o ON o.exchange=$2 AND o.pair=$3 AND o.interval=$4
             AND o.timestamp = bi.timestamp + make_interval(mins => $4)
        WHERE bi.exchange=$1 AND bi.pair=$3 AND bi.interval=$4 AND bi.timestamp = $5
        """,
        exchange,
        reference,
        pair,
        interval,
        ts,
    )


async def q_daily_between(
    conn: asyncpg.Connection, exchange: str, pair: str, lo: datetime, hi: datetime
) -> list[Any]:
    """1d rows with ``lo <= timestamp <= hi`` ordered by timestamp."""
    return await conn.fetch(
        "SELECT timestamp, open, high, low, close FROM market_data_ohlc "
        "WHERE exchange=$1 AND pair=$2 AND interval=1440 AND timestamp >= $3 AND timestamp <= $4 "
        "ORDER BY timestamp",
        exchange,
        pair,
        lo,
        hi,
    )


def _bps(a: Decimal, b: Decimal) -> Decimal:
    return abs(a - b) / b * 10_000


async def check_last_week(
    conn: asyncpg.Connection, rep: Report, exchange: str, reference: str, pair: str, expect: str
) -> None:
    """GATE 1 decision c: the last 1w candle of *pair* must be a complete week.

    Cross-checked against the 1d candles: same-source (Binance) 1d rows give exact
    open/close equality, the reference exchange (end-stamped 1d) covers the days
    past the Binance 1d range with a spread tolerance.  A candle truncated at the
    end of the Vision range would close exactly on the last Binance 1d close and
    span fewer than 7 days.
    """
    week = timedelta(days=7)
    day = timedelta(days=1)
    tol_bps = Decimal(50)
    row = await conn.fetchrow(
        "SELECT timestamp, open, high, low, close FROM market_data_ohlc "
        "WHERE exchange=$1 AND pair=$2 AND interval=10080 ORDER BY timestamp DESC LIMIT 1",
        exchange,
        pair,
    )
    if row is None:
        rep.problem(f"{pair} 1w: no row")
        return
    w_open = row["timestamp"] if expect == "open" else row["timestamp"] - week
    w_end = w_open + week
    # same-source 1d rows: open-stamped [w_open, w_end) before, end-stamped (w_open, w_end] after
    if expect == "open":
        bi_days = await q_daily_between(conn, exchange, pair, w_open, w_end - day)
    else:
        bi_days = await q_daily_between(conn, exchange, pair, w_open + day, w_end)
    ref_days = await q_daily_between(conn, reference, pair, w_open + day, w_end)
    rep.add(
        f"{pair} 1w last candle {row['timestamp'].isoformat()} covers "
        f"[{w_open.date()}, {w_end.date()}) o={row['open']} h={row['high']} l={row['low']} "
        f"c={row['close']} | {exchange} 1d days={len(bi_days)} {reference} 1d days={len(ref_days)}"
    )
    problems: list[str] = []
    if not bi_days or bi_days[0]["open"] != row["open"]:
        problems.append("1w open != first 1d open (same source)")
    if len(bi_days) == 7:
        if bi_days[-1]["close"] != row["close"]:
            problems.append("1w close != 7th 1d close (same source)")
        hi = max(d["high"] for d in bi_days)
        lo = min(d["low"] for d in bi_days)
        if row["high"] != hi or row["low"] != lo:
            problems.append("1w high/low != 1d range (same source)")
        verdict = "COMPLETE (7 same-source days)" if not problems else "INCONSISTENT"
    else:
        if bi_days and bi_days[-1]["close"] == row["close"]:
            problems.append(
                f"1w close equals the last {exchange} 1d close ({bi_days[-1]['timestamp'].date()}): "
                f"candle truncated after {len(bi_days)} day(s)"
            )
        if len(ref_days) < 7:
            problems.append(f"only {len(ref_days)} {reference} 1d days to cross-check")
        else:
            d_close = _bps(row["close"], ref_days[-1]["close"])
            d_high = _bps(row["high"], max(d["high"] for d in ref_days))
            d_low = _bps(row["low"], min(d["low"] for d in ref_days))
            rep.add(
                f"    vs {reference} 1d [{ref_days[0]['timestamp'].date()} → "
                f"{ref_days[-1]['timestamp'].date()}]: close diff={d_close:.1f} bps "
                f"high diff={d_high:.1f} bps low diff={d_low:.1f} bps (tolerance {tol_bps} bps)"
            )
            if max(d_close, d_high, d_low) > tol_bps:
                problems.append("1w close/high/low do not match the 7 reference days")
        verdict = "COMPLETE (7 reference days)" if not problems else "TRUNCATED/INCONSISTENT"
    rep.add(f"    → {verdict}")
    for prob in problems:
        rep.problem(f"{pair} 1w last candle: {prob}")


async def q_ambiguous_rows(
    conn: asyncpg.Connection,
    exchange: str,
    reference: str,
    pair: str,
    interval: int,
    since: datetime,
    limit: int = 50,
) -> list[Any]:
    """Rows where the two candidate reference closes are within 0.1 % (close alone undecided)."""
    return await conn.fetch(
        f"""
        SELECT bi.timestamp, bi.close AS bi_close, e.close AS ref_same, o.close AS ref_next,
               {D_SAME} AS d_same, {D_NEXT} AS d_next
        FROM market_data_ohlc bi
        JOIN market_data_ohlc e ON e.exchange=$2 AND e.pair=$3 AND e.interval=$4
             AND e.timestamp = bi.timestamp AND e.volume > 0
        JOIN market_data_ohlc o ON o.exchange=$2 AND o.pair=$3 AND o.interval=$4
             AND o.timestamp = bi.timestamp + make_interval(mins => $4) AND o.volume > 0
        WHERE bi.exchange=$1 AND bi.pair=$3 AND bi.interval=$4 AND bi.timestamp >= $5
          AND {AMBIGUOUS}
        ORDER BY bi.timestamp LIMIT $6
        """,
        exchange,
        reference,
        pair,
        interval,
        since,
        limit,
    )


async def q_dup_signature(
    conn: asyncpg.Connection, exchange: str, pair: str, interval: int
) -> tuple[int, int, datetime | None, datetime | None]:
    row = await conn.fetchrow(
        """
        SELECT COUNT(*) FILTER (WHERE volume > 0) AS dup_vol,
               COUNT(*) FILTER (WHERE volume = 0) AS dup_flat,
               MIN(timestamp) FILTER (WHERE volume > 0) AS first_vol,
               MAX(timestamp) FILTER (WHERE volume > 0) AS last_vol
        FROM (
          SELECT timestamp, open, high, low, close, volume,
                 LEAD(timestamp) OVER w AS nt, LEAD(open) OVER w AS no, LEAD(high) OVER w AS nh,
                 LEAD(low) OVER w AS nl, LEAD(close) OVER w AS nc, LEAD(volume) OVER w AS nv
          FROM market_data_ohlc WHERE exchange=$1 AND pair=$2 AND interval=$3
          WINDOW w AS (ORDER BY timestamp)
        ) s
        WHERE nt = timestamp + make_interval(mins => $3)
          AND no = open AND nh = high AND nl = low AND nc = close AND nv = volume
        """,
        exchange,
        pair,
        interval,
    )
    return int(row["dup_vol"]), int(row["dup_flat"]), row["first_vol"], row["last_vol"]


async def q_count_upto(
    conn: asyncpg.Connection, exchange: str, pair: str, interval: int, boundary: datetime
) -> int:
    row = await conn.fetchrow(
        "SELECT COUNT(*) AS n FROM market_data_ohlc "
        "WHERE exchange=$1 AND pair=$2 AND interval=$3 AND timestamp <= $4",
        exchange,
        pair,
        interval,
        boundary,
    )
    return int(row["n"])


async def q_collisions(
    conn: asyncpg.Connection, exchange: str, pair: str, interval: int, boundary: datetime
) -> list[Any]:
    """Perimeter rows whose target ``T + interval`` is already taken by a row outside the perimeter.

    Such a target row is necessarily ``> boundary`` hence ``T > boundary - interval``:
    only the top of the series can collide.
    """
    return await conn.fetch(
        """
        SELECT a.timestamp AS src_ts, b.timestamp AS dst_ts,
               a.open AS a_open, a.high AS a_high, a.low AS a_low, a.close AS a_close, a.volume AS a_volume,
               b.open AS b_open, b.high AS b_high, b.low AS b_low, b.close AS b_close, b.volume AS b_volume
        FROM market_data_ohlc a
        JOIN market_data_ohlc b ON b.exchange=a.exchange AND b.pair=a.pair AND b.interval=a.interval
             AND b.timestamp = a.timestamp + make_interval(mins => $3)
        WHERE a.exchange=$1 AND a.pair=$2 AND a.interval=$3
          AND a.timestamp <= $4 AND a.timestamp > $4 - make_interval(mins => $3)
          AND b.timestamp > $4
        ORDER BY a.timestamp
        """,
        exchange,
        pair,
        interval,
        boundary,
    )


async def q_rows_around(
    conn: asyncpg.Connection,
    exchange: str,
    pair: str,
    interval: int,
    ts: datetime,
    before: int,
    after: int,
) -> list[Any]:
    step = timedelta(minutes=interval)
    return await conn.fetch(
        "SELECT timestamp, open, high, low, close, volume FROM market_data_ohlc "
        "WHERE exchange=$1 AND pair=$2 AND interval=$3 AND timestamp >= $4 AND timestamp <= $5 "
        "ORDER BY timestamp",
        exchange,
        pair,
        interval,
        ts - step * before,
        ts + step * after,
    )


async def q_first_after(
    conn: asyncpg.Connection, exchange: str, pair: str, interval: int, ts: datetime
) -> Any:
    return await conn.fetchrow(
        "SELECT timestamp FROM market_data_ohlc WHERE exchange=$1 AND pair=$2 AND interval=$3 "
        "AND timestamp > $4 ORDER BY timestamp LIMIT 1",
        exchange,
        pair,
        interval,
        ts,
    )


async def q_max_ts_by_exchange(conn: asyncpg.Connection, pair: str, interval: int) -> list[Any]:
    return await conn.fetch(
        "SELECT exchange, MIN(timestamp) AS min_ts, MAX(timestamp) AS max_ts, COUNT(*) AS n "
        "FROM market_data_ohlc WHERE pair=$1 AND interval=$2 GROUP BY 1 ORDER BY 1",
        pair,
        interval,
    )


# ---------------------------------------------------------------------------
# Audit (pre-migration) and post-migration replay
# ---------------------------------------------------------------------------


def _fmt_row(r: Any) -> str:
    return (
        f"{r['timestamp'].isoformat()} o={r['open']} h={r['high']} l={r['low']} "
        f"c={r['close']} v={r['volume']}"
    )


async def audit_series(
    conn: asyncpg.Connection,
    rep: Report,
    exchange: str,
    reference: str,
    pair: str,
    interval: int,
    since: datetime,
    expect: str,
    manifest_entry: SeriesBoundary | None,
) -> SeriesBoundary | None:
    """Run sections a–e for one series; returns the boundary (None if the series is empty)."""
    lab = label(interval)
    name = f"{pair} {lab}"
    step = timedelta(minutes=interval)
    b = await q_bounds(conn, exchange, pair, interval)
    rows_n = int(b["n"])
    if rows_n == 0:
        rep.add(f"{name}: no rows")
        return None
    min_ts, max_ts = b["min_ts"], b["max_ts"]

    # (a) map
    gaps = await q_gaps(conn, exchange, pair, interval)
    missing = sum(int((n - p) / step) - 1 for p, n in gaps)
    misaligned = await q_misaligned(conn, exchange, pair, interval)
    rep.add(
        f"{name}: rows={rows_n} [{min_ts.isoformat()} → {max_ts.isoformat()}] "
        f"gaps={len(gaps)} missing_candles={missing} misaligned={misaligned}"
    )
    for p, n in gaps:
        rep.add(
            f"    gap: after {p.isoformat()} until {n.isoformat()} ({int((n - p) / step) - 1} candles)"
        )
    if misaligned:
        rep.problem(f"{name}: {misaligned} rows off the candle grid")
    if not (is_grid_aligned(min_ts, interval) and is_grid_aligned(max_ts, interval)):
        rep.problem(f"{name}: MIN/MAX not grid aligned (Monday anchoring for 1w)")

    # (b) classification by content
    votes = await q_window_votes(conn, exchange, reference, pair, interval, since)
    summary = summarize_votes(votes)
    n_rows_voted = sum(v.total for v in votes)
    rep.add(
        f"    windows: open={summary['open']} end={summary['end']} tie={summary['tie']} "
        f"(rows voted={n_rows_voted}, weeks={len(votes)})"
    )
    recheck_rows: list[datetime] = []
    if expect == "open" and interval >= 1440:
        # GATE 1 (a): rows the close alone cannot classify (small windows) are re-checked one by
        # one after the migration; on ≥ 42-row windows the strict window verdict is enough.
        for d in await q_ambiguous_rows(conn, exchange, reference, pair, interval, since):
            recheck_rows.append(d["timestamp"])
            rep.add(
                f"      close-ambiguous row {d['timestamp'].isoformat()}: {exchange} close="
                f"{d['bi_close']} | {reference} close at T={d['ref_same']} at T+{lab}="
                f"{d['ref_next']} | OHLC dist same={d['d_same']} next={d['d_next']} → re-check post"
            )
    for v in votes:
        if v.verdict != expect:
            note = ""
            if expect == "end":
                note = " — RESIDUAL (strict post-migration check)"
            elif v.total < 3:
                note = " — not decisive (< 3 rows)"
            rep.add(
                f"      window {v.window_start.date()} → {v.verdict} "
                f"(open={v.n_open} end={v.n_end} tie={v.n_tie}){note}"
            )
            for d in await q_window_detail(
                conn, exchange, reference, pair, interval, v.window_start, expect
            ):
                if d["timestamp"] not in recheck_rows:
                    recheck_rows.append(d["timestamp"])
                rep.add(
                    f"        {d['timestamp'].isoformat()} {exchange} close={d['bi_close']} | "
                    f"{reference} close at T={d['ref_same']} at T+{lab}={d['ref_next']} | "
                    f"OHLC dist same={d['d_same']} next={d['d_next']}"
                )
    if not votes:
        rep.problem(f"{name}: no overlap with {reference} — cannot classify by content")
        return None
    for prob in assess_votes(votes, expect, strict=(expect == "end")):  # type: ignore[arg-type]
        rep.problem(f"{name}: {prob}")
    if expect == "end" and manifest_entry is not None and manifest_entry.recheck_rows:
        rep.add(f"    rows ambiguous before the migration, now expected at T+{lab} voting end:")
        for t in manifest_entry.recheck_rows:
            shifted = t + step
            rv = await q_row_votes(
                conn, exchange, reference, pair, interval, shifted, shifted + timedelta(seconds=1)
            )
            vote = rv[0][1] if rv else "missing"
            detail = await q_row_detail(conn, exchange, reference, pair, interval, shifted)
            extra = (
                f" ({exchange} close={detail['bi_close']} | {reference} close at T="
                f"{detail['ref_same']} at T+{lab}={detail['ref_next']} | OHLC dist same="
                f"{detail['d_same']} next={detail['d_next']})"
                if detail
                else ""
            )
            rep.add(f"      {t.isoformat()} → {shifted.isoformat()}: vote={vote}{extra}")
            if vote != "end":
                rep.problem(f"{name}: formerly ambiguous row {shifted.isoformat()} votes '{vote}'")

    dup_vol, dup_flat, dup_first, dup_last = await q_dup_signature(conn, exchange, pair, interval)
    rep.add(
        f"    dup signature (T,T+{lab}) identical OHLCV: volume>0={dup_vol} "
        f"[{dup_first} → {dup_last}] flat(volume=0)={dup_flat}"
    )

    # boundary
    last_open, first_end = find_switch(votes)
    boundary: datetime | None
    first_end_ts: datetime | None = None
    if expect == "open":
        if first_end is None:
            boundary = max_ts  # everything open-stamped
        else:
            start = last_open.window_start if last_open else since
            end = first_end.window_start + timedelta(days=7)
            row_votes = await q_row_votes(conn, exchange, reference, pair, interval, start, end)
            boundary = refine_boundary(row_votes)
            if boundary is None:
                # no run of >= 3 consecutive 'end' rows: the trailing 'end' window is noise
                boundary = max_ts
                rep.add(
                    f"    trailing end window {first_end.window_start.date()} has no run of "
                    f"end-stamped rows → treated as noise, boundary = MAX(timestamp)"
                )
            else:
                first_end_ts = boundary + step
                rep.add(
                    f"    switch found: last open window {start.date()} / first end window "
                    f"{first_end.window_start.date()} → row-level boundary {boundary}"
                )
    else:
        boundary = manifest_entry.last_open_stamped_ts if manifest_entry else None

    if boundary is None:
        rep.problem(f"{name}: boundary undetermined")
        return None

    # (c) quantification (pre) / accounting (post)
    if expect == "open":
        restamps = await q_count_upto(conn, exchange, pair, interval, boundary)
        collisions = await q_collisions(conn, exchange, pair, interval, boundary)
        rep.add(
            f"    perimeter: timestamp <= {boundary.isoformat()} → rows_to_restamp={restamps} "
            f"collisions={len(collisions)}"
        )
        for c in collisions:
            same = all(
                c[f"a_{k}"] == c[f"b_{k}"] for k in ("open", "high", "low", "close", "volume")
            )
            rep.add(
                f"      collision {c['src_ts'].isoformat()} → {c['dst_ts'].isoformat()}: "
                f"{'IDENTICAL' if same else 'DIVERGENT'} "
                f"(vision o/c={c['a_open']}/{c['a_close']} vs existing {c['b_open']}/{c['b_close']})"
            )
            if not same:
                rep.problem(f"{name}: divergent collision at {c['src_ts'].isoformat()}")
    else:
        assert manifest_entry is not None
        restamps = manifest_entry.expected_restamps
        collisions = []
        exp_rows = manifest_entry.expected_rows_after
        exp_max = manifest_entry.last_open_stamped_ts + step  # type: ignore[operator]
        exp_min = manifest_entry.min_ts + step
        rep.add(
            f"    accounting: rows={rows_n} expected={exp_rows} | max={max_ts.isoformat()} "
            f"expected={exp_max.isoformat()} | min={min_ts.isoformat()} expected={exp_min.isoformat()}"
        )
        if rows_n != exp_rows:
            rep.problem(f"{name}: rows {rows_n} != expected {exp_rows}")
        if max_ts != exp_max:
            rep.problem(f"{name}: MAX {max_ts} != expected {exp_max}")
        if min_ts != exp_min:
            rep.problem(f"{name}: MIN {min_ts} != expected {exp_min}")
        exp_gaps = shifted_gaps(manifest_entry.gaps, interval)
        if gaps != exp_gaps:
            rep.problem(f"{name}: gaps differ from audit gaps shifted by +{lab}")
        else:
            rep.add(f"    gaps: identical to audit shifted by +{lab} ({len(gaps)})")
        if dup_vol != manifest_entry.dup_signature_volume_gt0:
            rep.problem(
                f"{name}: dup signature {dup_vol} != audit {manifest_entry.dup_signature_volume_gt0}"
            )

    # (e) upstream edge
    edge = await q_rows_around(conn, exchange, pair, interval, boundary, 1, 2)
    rep.add(f"    edge rows around boundary {boundary.isoformat()}:")
    for r in edge:
        rep.add(f"      {_fmt_row(r)}")
    if expect == "open":
        at_target = [r for r in edge if r["timestamp"] == boundary + step]
        nxt = await q_first_after(conn, exchange, pair, interval, boundary)
        rep.add(
            f"    row at boundary+{lab}: {'PRESENT' if at_target else 'absent'} | "
            f"first {exchange} row after boundary: {nxt['timestamp'].isoformat() if nxt else 'none'}"
        )
    others = await q_max_ts_by_exchange(conn, pair, interval)
    rep.add(
        "    other exchanges: "
        + " | ".join(
            f"{o['exchange']} n={o['n']} [{o['min_ts'].isoformat()} → {o['max_ts'].isoformat()}]"
            for o in others
            if o["exchange"] != exchange
        )
    )

    return SeriesBoundary(
        pair=pair,
        interval=interval,
        rows=rows_n,
        min_ts=min_ts,
        max_ts=max_ts,
        last_open_stamped_ts=boundary,
        first_end_stamped_ts=first_end_ts,
        expected_restamps=restamps,
        expected_collisions=len(collisions),
        gaps=gaps,
        dup_signature_volume_gt0=dup_vol,
        window_verdicts=summary,
        recheck_rows=recheck_rows,
    )


async def spot_checks(conn: asyncpg.Connection, rep: Report, exchange: str, expect: str) -> None:
    for pair, interval, open_ts, exp_open, exp_close in SPOT_CHECKS:
        step = timedelta(minutes=interval)
        want_ts = open_ts if expect == "open" else open_ts + step
        rows = await q_rows_around(conn, exchange, pair, interval, open_ts, 0, 1)
        for r in rows:
            rep.add(f"  {pair} {label(interval)} {_fmt_row(r)}")
        hit = next((r for r in rows if r["timestamp"] == want_ts), None)
        ok = hit is not None and hit["open"] == exp_open and hit["close"] == exp_close
        rep.add(
            f"  → candle open={exp_open} close={exp_close} expected at {want_ts.isoformat()}: "
            f"{'OK' if ok else 'MISMATCH'}"
        )
        if not ok:
            rep.problem(f"spot check {pair} {label(interval)} {want_ts.isoformat()} failed")


async def _async_main(args: argparse.Namespace) -> int:
    expect = "end" if args.post_migration else "open"
    exchange = TARGET_EXCHANGE
    since = datetime.fromisoformat(args.overlap_since).replace(tzinfo=UTC)
    manifest_in = BoundaryManifest.load(args.boundaries) if args.post_migration else None

    url = os.environ["DATABASE_URL"].replace("postgresql+asyncpg://", "postgresql://")
    conn = await asyncpg.connect(url, timeout=30)
    rep = Report()
    try:
        await conn.execute("SET default_transaction_read_only = on")
        await conn.execute("SET statement_timeout = '1800s'")
        mode = (
            "POST-MIGRATION replay (expects end-stamped)"
            if args.post_migration
            else "AUDIT (expects open-stamped)"
        )
        rep.section(
            f"B4.1 timestamp audit — exchange='{exchange}' reference='{args.reference_exchange}' — {mode}"
        )
        rep.add(f"generated_at={datetime.now(UTC).isoformat()} overlap_since={since.date()}")
        totals = await q_totals(conn)
        rep.add("db totals: " + ", ".join(f"{k}={v}" for k, v in sorted(totals.items())))
        if manifest_in is not None:
            rep.add(
                "manifest totals: "
                + ", ".join(f"{k}={v}" for k, v in sorted(manifest_in.db_totals.items()))
                + f" (generated {manifest_in.generated_at.isoformat()})"
            )
            for ex in ("kraken",):
                if totals.get(ex) != manifest_in.db_totals.get(ex):
                    rep.problem(
                        f"{ex} row count changed: {manifest_in.db_totals.get(ex)} → {totals.get(ex)}"
                    )

        series: list[SeriesBoundary] = []
        for pair in args.pairs:
            for interval in args.intervals:
                rep.section(f"{pair} {label(interval)}")
                entry = manifest_in.get(pair, interval) if manifest_in else None
                if args.post_migration and entry is None:
                    rep.problem(f"{pair} {label(interval)}: missing from manifest")
                    continue
                sb = await audit_series(
                    conn,
                    rep,
                    exchange,
                    args.reference_exchange,
                    pair,
                    interval,
                    since,
                    expect,
                    entry,
                )
                if sb is not None:
                    series.append(sb)

        rep.section("Spot checks")
        await spot_checks(conn, rep, exchange, expect)

        if 10080 in args.intervals:
            rep.section("Last 1w candle completeness (GATE 1 decision c)")
            for pair in args.pairs:
                await check_last_week(conn, rep, exchange, args.reference_exchange, pair, expect)

        rep.section("Summary")
        rep.add(
            f"  {'Series':<14} {'rows':>9} {'min':<26} {'boundary (last open ts)':<26} "
            f"{'restamps':>9} {'collisions':>10} {'win open/end/tie':>17}"
        )
        for s in series:
            wv = s.window_verdicts
            rep.add(
                f"  {s.pair + ' ' + label(s.interval):<14} {s.rows:>9} {s.min_ts.isoformat():<26} "
                f"{(s.last_open_stamped_ts.isoformat() if s.last_open_stamped_ts else '-'):<26} "
                f"{s.expected_restamps:>9} {s.expected_collisions:>10} "
                f"{wv.get('open', 0):>5}/{wv.get('end', 0)}/{wv.get('tie', 0)}"
            )
        rep.add(
            f"  total rows={sum(s.rows for s in series)} restamps={sum(s.expected_restamps for s in series)} "
            f"collisions={sum(s.expected_collisions for s in series)} series={len(series)}"
        )
        if rep.problems:
            rep.add(f"\n  {len(rep.problems)} PROBLEM(S):")
            for p in rep.problems:
                rep.add(f"    - {p}")
        else:
            rep.add(f"\n  all series consistent with '{expect}' convention — no problem")

        if args.out_json and not args.post_migration:
            manifest = BoundaryManifest(
                generated_at=datetime.now(UTC),
                method=METHOD,
                exchange=exchange,
                reference_exchange=args.reference_exchange,
                db_totals=totals,
                series=series,
            )
            manifest.dump(args.out_json)
            rep.add(f"\n  manifest written: {args.out_json}")
    finally:
        await conn.close()

    if args.out_md:
        args.out_md.write_text(rep.text(), encoding="utf-8")
    return 1 if rep.problems else 0


def main(argv: list[str] | None = None) -> int:
    return asyncio.run(_async_main(parse_args(argv)))


if __name__ == "__main__":
    raise SystemExit(main())
