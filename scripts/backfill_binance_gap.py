"""Backfill the Binance OHLC gap created by stopping the collector.

When the collector is stopped (e.g. to free CPU/RAM during P7 grid search),
the Binance WebSocket stream falls silent and no candles land in the DB.
There is **no automatic backfill** for Binance — the existing TaskScheduler
only services Kraken (``src/krakenbot/scheduler/task_scheduler.py``).

This wrapper queries ``MAX(timestamp)`` per (pair, interval) for
``exchange='binance'`` and replays the gap up to ``now`` via
:meth:`BinanceRestClient.fetch_ohlcv`, then writes the candles back through
the same idempotent ``ON CONFLICT DO UPDATE`` path used by
``scripts/fetch_ohlc.py``.

Coverage: BTC/USDC, ETH/USDC, SOL/USDC × {5m, 15m, 1h, 4h, 1d, 1w} = 18
combinations. Add ``--include-1m`` if a 1m gap also needs filling.

Usage::

    poetry run python scripts/backfill_binance_gap.py
    poetry run python scripts/backfill_binance_gap.py --pairs BTC/USDC --intervals 5 15
    poetry run python scripts/backfill_binance_gap.py --dry-run  # just print gaps
"""

# ruff: noqa: E402

from __future__ import annotations

import argparse
import asyncio
from datetime import UTC, datetime, timedelta
from pathlib import Path
import sys

from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / ".env")

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

# Reuse helpers from fetch_ohlc.py (same project layout, no duplication).
from fetch_ohlc import get_last_timestamp, save_ohlc_batch  # type: ignore

from krakenbot.config.settings import get_settings
from krakenbot.connectors.binance.rest import BinanceRestClient
from krakenbot.core.database import DatabaseManager
from krakenbot.core.event_bus import get_event_bus
from krakenbot.core.logger import get_logger

logger = get_logger(__name__).bind(component="backfill_binance_gap")

EXCHANGE = "binance"
DEFAULT_PAIRS: tuple[str, ...] = ("BTC/USDC", "ETH/USDC", "SOL/USDC")
DEFAULT_INTERVALS: tuple[int, ...] = (5, 15, 60, 240, 1440, 10080)  # 5m, 15m, 1h, 4h, 1d, 1w
INTERVAL_LABEL = {
    1: "1m",
    5: "5m",
    15: "15m",
    60: "1h",
    240: "4h",
    1440: "1d",
    10080: "1w",
}


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "--pairs",
        nargs="+",
        default=list(DEFAULT_PAIRS),
        help="Pairs to backfill (default: BTC/USDC ETH/USDC SOL/USDC).",
    )
    parser.add_argument(
        "--intervals",
        nargs="+",
        type=int,
        default=list(DEFAULT_INTERVALS),
        help="Intervals in minutes (default: 5 15 60 240 1440 10080).",
    )
    parser.add_argument(
        "--include-1m",
        action="store_true",
        help="Also backfill 1-minute candles (heavy on the 1m TF; skip by default).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the detected gap per (pair, interval) without fetching.",
    )
    parser.add_argument(
        "--max-fetch",
        type=int,
        default=1000,
        help="Max candles per Binance REST call (default 1000 — Binance's hard limit).",
    )
    return parser.parse_args(argv)


async def _backfill_one(
    rest_client: BinanceRestClient,
    db_manager: DatabaseManager,
    pair: str,
    interval: int,
    *,
    dry_run: bool,
    max_fetch: int,
) -> dict:
    """Backfill one (pair, interval). Returns a summary dict."""
    last_ts = await get_last_timestamp(db_manager, pair, interval, exchange=EXCHANGE)
    now = datetime.now(UTC)

    if last_ts is None:
        return {
            "pair": pair,
            "interval": interval,
            "label": INTERVAL_LABEL.get(interval, f"{interval}m"),
            "status": "no_baseline",
            "gap_minutes": None,
            "candles_fetched": 0,
        }

    gap_minutes = (now - last_ts).total_seconds() / 60.0
    if gap_minutes < interval:
        # Already up-to-date (gap smaller than one candle of this TF)
        return {
            "pair": pair,
            "interval": interval,
            "label": INTERVAL_LABEL.get(interval, f"{interval}m"),
            "status": "already_current",
            "last_ts": last_ts.isoformat(),
            "gap_minutes": gap_minutes,
            "candles_fetched": 0,
        }

    if dry_run:
        return {
            "pair": pair,
            "interval": interval,
            "label": INTERVAL_LABEL.get(interval, f"{interval}m"),
            "status": "would_fetch",
            "last_ts": last_ts.isoformat(),
            "gap_minutes": gap_minutes,
            "candles_fetched": 0,
        }

    # Fetch from one candle after last_ts so we don't re-grab the boundary
    # (ON CONFLICT DO UPDATE would handle it anyway, but skipping saves a call).
    since = last_ts + timedelta(minutes=interval)
    total_inserted = 0

    while since < now:
        batch = await rest_client.fetch_ohlcv(
            pair=pair,
            interval=interval,
            since=since,
            limit=max_fetch,
        )
        if not batch:
            break

        # Stop bumping `since` if the last batch reaches now (avoid infinite loop)
        last_in_batch = batch[-1]["timestamp"]
        n_saved = await save_ohlc_batch(db_manager, batch, exchange=EXCHANGE)
        total_inserted += n_saved
        logger.info(
            "binance_gap_backfilled",
            pair=pair,
            interval=interval,
            since=since.isoformat(),
            last_in_batch=last_in_batch.isoformat(),
            candles=n_saved,
        )

        next_since = last_in_batch + timedelta(minutes=interval)
        if next_since <= since:
            # Paranoid guard against a stuck cursor
            break
        since = next_since

        if len(batch) < max_fetch:
            # Reached the live edge — Binance returned fewer than the cap.
            break

    return {
        "pair": pair,
        "interval": interval,
        "label": INTERVAL_LABEL.get(interval, f"{interval}m"),
        "status": "ok",
        "last_ts_before": last_ts.isoformat(),
        "gap_minutes": gap_minutes,
        "candles_fetched": total_inserted,
    }


async def _async_main(args: argparse.Namespace) -> int:
    intervals = list(args.intervals)
    if args.include_1m and 1 not in intervals:
        intervals.insert(0, 1)

    settings = get_settings()
    db_manager = DatabaseManager()
    await db_manager.init_db(settings)

    event_bus = get_event_bus()
    rest_client = BinanceRestClient(settings, event_bus, db_manager)

    summaries: list[dict] = []
    try:
        for pair in args.pairs:
            for interval in intervals:
                logger.info("processing", pair=pair, interval=interval, dry_run=args.dry_run)
                summary = await _backfill_one(
                    rest_client,
                    db_manager,
                    pair,
                    interval,
                    dry_run=args.dry_run,
                    max_fetch=args.max_fetch,
                )
                summaries.append(summary)
    finally:
        await db_manager.close_db()

    # Print a human-readable summary table
    print()
    print(f"{'=' * 72}")
    print(f"  Binance gap backfill — exchange='{EXCHANGE}'")
    print(f"{'=' * 72}")
    print(f"  {'Pair':<10} {'TF':<5} {'Status':<18} {'Gap (min)':<12} {'Inserted':<8}")
    print(f"  {'-' * 10} {'-' * 5} {'-' * 18} {'-' * 12} {'-' * 8}")
    total = 0
    for s in summaries:
        gap = f"{s['gap_minutes']:.1f}" if s["gap_minutes"] is not None else "n/a"
        print(
            f"  {s['pair']:<10} {s['label']:<5} {s['status']:<18} {gap:<12} "
            f"{s['candles_fetched']:<8}"
        )
        total += s["candles_fetched"]
    print(f"  {'-' * 10} {'-' * 5} {'-' * 18} {'-' * 12} {'-' * 8}")
    print(f"  Total candles inserted: {total}")
    print()

    return 0


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    return asyncio.run(_async_main(args))


if __name__ == "__main__":
    raise SystemExit(main())
