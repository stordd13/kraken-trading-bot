"""B3 §3.3 — cross-checks after the Bybit EU historical import (read-only).

(a) 1d/1w timestamp convention Bybit (period end) vs Binance (Vision, open time):
    for the same candle the Bybit DB timestamp is expected to be exactly one
    interval later; weekly candles on Monday 00:00 UTC on both sides.
(b) 1h close prices Bybit vs Binance on the overlap, Binance shifted by +1h to
    align on the same candle: Pearson correlation, median / p99 / max |diff| in bps.
(c) WS vs REST: a few candles written by the WebSocket collector since 2026-09-09
    compared with what the REST kline endpoint returns for the same timestamps.

Raw output goes to stdout (paste into results/B3_bybit_data_report.md).

Usage (server, DB local; local via the SSH tunnel is fine — reads only):
    poetry run python scripts/audit/bybit_b3_crosscheck.py [--pairs BTC/USDC ...]
"""

from __future__ import annotations

import argparse
import asyncio
from datetime import UTC, datetime, timedelta
from decimal import Decimal
import os
from pathlib import Path
import statistics
import sys

import asyncpg
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent.parent
load_dotenv(ROOT / ".env")
sys.path.insert(0, str(ROOT / "src"))

from krakenbot.config.settings import get_settings  # noqa: E402
from krakenbot.connectors.exchange import build_exchange_rest_client  # noqa: E402
from krakenbot.core.event_bus import get_event_bus  # noqa: E402

PAIRS = ["BTC/USDC", "ETH/USDC", "SOL/USDC"]
WS_SINCE = datetime(2026, 9, 9, 18, 13, tzinfo=UTC)  # server collector start (+1 candle)


def _section(title: str) -> None:
    print("\n" + "=" * 100 + f"\n{title}\n" + "=" * 100)


async def check_daily_weekly(conn: asyncpg.Connection, pair: str) -> None:
    for interval, label in ((1440, "1d"), (10080, "1w")):
        step = timedelta(minutes=interval)
        rows = await conn.fetch(
            """
            WITH by AS (SELECT timestamp, open, close FROM market_data_ohlc
                        WHERE exchange='bybit' AND pair=$1 AND interval=$2),
                 bi AS (SELECT timestamp, open, close FROM market_data_ohlc
                        WHERE exchange='binance' AND pair=$1 AND interval=$2)
            SELECT COUNT(*) FILTER (WHERE bi_same.timestamp IS NOT NULL) AS same_ts,
                   COUNT(*) FILTER (WHERE bi_shift.timestamp IS NOT NULL) AS shifted_ts,
                   COUNT(*) AS bybit_rows,
                   MIN(by.timestamp) AS bybit_min, MAX(by.timestamp) AS bybit_max,
                   COUNT(*) FILTER (WHERE bi_shift.timestamp IS NOT NULL
                       AND ABS(by.open - bi_shift.open) / bi_shift.open < 0.01) AS shifted_open_close_to_binance,
                   COUNT(*) FILTER (WHERE bi_same.timestamp IS NOT NULL
                       AND ABS(by.open - bi_same.open) / bi_same.open < 0.01) AS same_open_close_to_binance
            FROM by
            LEFT JOIN bi bi_same  ON bi_same.timestamp  = by.timestamp
            LEFT JOIN bi bi_shift ON bi_shift.timestamp = by.timestamp - $3::interval
            """,
            pair,
            interval,
            step,
        )
        r = rows[0]
        dow = await conn.fetch(
            "SELECT exchange, EXTRACT(DOW FROM timestamp)::int AS dow, COUNT(*) FROM market_data_ohlc "
            "WHERE pair=$1 AND interval=$2 AND exchange IN ('bybit','binance') GROUP BY 1,2 ORDER BY 1,2",
            pair,
            interval,
        )
        print(
            f"{pair} {label}: bybit_rows={r['bybit_rows']} [{r['bybit_min']} → {r['bybit_max']}] | "
            f"binance rows at SAME ts={r['same_ts']} (open within 1 %: {r['same_open_close_to_binance']}) | "
            f"binance rows at ts-{label}={r['shifted_ts']} (open within 1 %: {r['shifted_open_close_to_binance']})"
        )
        print(f"    DOW (0=Sun,1=Mon): {[(d['exchange'], d['dow'], d['count']) for d in dow]}")
        verdict = (
            "OK: offset = exactly one interval (bybit end-stamped, binance open-stamped)"
            if r["shifted_open_close_to_binance"] >= r["same_open_close_to_binance"]
            else "STOP: bybit rows match binance at the SAME timestamp — convention differs from expectation"
        )
        print(f"    → {verdict}")


async def check_hourly_prices(conn: asyncpg.Connection, pair: str) -> None:
    rows = await conn.fetch(
        """
        SELECT by.timestamp, by.close AS by_close, bi.close AS bi_close
        FROM market_data_ohlc by
        JOIN market_data_ohlc bi
          ON bi.exchange='binance' AND bi.pair=by.pair AND bi.interval=60
         AND bi.timestamp = by.timestamp - interval '1 hour'
        WHERE by.exchange='bybit' AND by.pair=$1 AND by.interval=60 AND by.volume > 0
        ORDER BY by.timestamp
        """,
        pair,
    )
    if len(rows) < 10:
        print(f"{pair} 1h: only {len(rows)} overlapping candles — nothing to compare")
        return
    a = [float(r["by_close"]) for r in rows]
    b = [float(r["bi_close"]) for r in rows]
    corr = statistics.correlation(a, b)
    diffs_bps = [abs(x - y) / y * 1e4 for x, y in zip(a, b, strict=True)]
    diffs_sorted = sorted(diffs_bps)
    p99 = diffs_sorted[int(len(diffs_sorted) * 0.99) - 1]
    worst = max(range(len(diffs_bps)), key=diffs_bps.__getitem__)
    signed_mean = statistics.mean((x - y) / y * 1e4 for x, y in zip(a, b, strict=True))
    print(
        f"{pair} 1h: n={len(rows)} [{rows[0]['timestamp']} → {rows[-1]['timestamp']}] "
        f"corr={corr:.6f} |diff| median={statistics.median(diffs_bps):.2f} bps p99={p99:.1f} bps "
        f"max={diffs_bps[worst]:.1f} bps at {rows[worst]['timestamp']} "
        f"(bybit {a[worst]:.2f} vs binance {b[worst]:.2f}) signed mean={signed_mean:+.2f} bps"
    )
    print(f"    → {'OK' if corr > 0.999 else 'STOP: correlation below 0.999'}")


async def check_ws_vs_rest(conn: asyncpg.Connection, rest, pair: str) -> None:
    for interval in (1, 60, 1440):
        row = await conn.fetchrow(
            "SELECT timestamp, open, high, low, close, volume, vwap FROM market_data_ohlc "
            "WHERE exchange='bybit' AND pair=$1 AND interval=$2 AND timestamp >= $3 AND volume > 0 "
            "ORDER BY timestamp LIMIT 1",
            pair,
            interval,
            WS_SINCE,
        )
        if row is None:
            print(f"{pair} {interval}m: no WS row since {WS_SINCE}")
            continue
        since = row["timestamp"] - timedelta(minutes=interval)
        candles = await rest.fetch_ohlcv(pair, interval, since=since, limit=1)
        rest_c = next((c for c in candles if c["timestamp"] == row["timestamp"]), None)
        if rest_c is None:
            print(
                f"{pair} {interval}m {row['timestamp']}: REST returned no candle at this timestamp → STOP"
            )
            continue
        same = all(
            Decimal(str(row[k])) == rest_c[k] for k in ("open", "high", "low", "close", "volume")
        )
        vwap_same = (row["vwap"] is None and rest_c["vwap"] is None) or (
            row["vwap"] is not None
            and rest_c["vwap"] is not None
            and abs(Decimal(str(row["vwap"])) - rest_c["vwap"]) <= Decimal("0.00000001")
        )
        print(
            f"{pair} {interval}m {row['timestamp']}: DB o/h/l/c/v={row['open']}/{row['high']}/"
            f"{row['low']}/{row['close']}/{row['volume']} vwap={row['vwap']} | REST "
            f"{rest_c['open']}/{rest_c['high']}/{rest_c['low']}/{rest_c['close']}/{rest_c['volume']} "
            f"vwap={rest_c['vwap']} → OHLCV {'IDENTICAL' if same else 'DIFFER'}, vwap {'same' if vwap_same else 'DIFFER'}"
        )


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--pairs", nargs="+", default=PAIRS)
    args = ap.parse_args()
    url = os.environ["DATABASE_URL"].replace("postgresql+asyncpg://", "postgresql://")
    conn = await asyncpg.connect(url, timeout=30)
    settings = get_settings()
    rest = build_exchange_rest_client(settings, get_event_bus(), None, read_only=True)
    try:
        _section("(a) 1d / 1w timestamp convention — Bybit (end) vs Binance (Vision, open)")
        for pair in args.pairs:
            await check_daily_weekly(conn, pair)
        _section("(b) 1h closes — Bybit vs Binance (Binance shifted +1h), overlap period")
        for pair in args.pairs:
            await check_hourly_prices(conn, pair)
        _section("(c) WS rows vs REST kline — same timestamp, OHLCV + vwap")
        for pair in args.pairs:
            await check_ws_vs_rest(conn, rest, pair)
    finally:
        await rest.close()
        await conn.close()


if __name__ == "__main__":
    asyncio.run(main())
