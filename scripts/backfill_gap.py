"""Backfill OHLC gaps for the current exchange (``EXCHANGE_NAME``) via REST.

Thin CLI around :mod:`krakenbot.data.backfill`: detects internal gaps (LAG
query) and the tail gap (``MAX(timestamp)`` → last closed candle) per
(pair, interval) for ``exchange = settings.exchange_name`` and fills them with
``fetch_ohlcv`` + ``ON CONFLICT DO NOTHING`` (rows written by the WebSocket
collector always win).  The same code runs nightly inside the collector
(``TaskScheduler``); this script is the manual / demo entry point.

Guarantee: correct for ``EXCHANGE_NAME=bybit`` only (see the module docstring
of ``krakenbot.data.backfill`` — other REST clients return open-stamped candles).

Usage::

    poetry run python scripts/backfill_gap.py --dry-run          # gap table only, no fetch
    poetry run python scripts/backfill_gap.py                    # fill everything
    poetry run python scripts/backfill_gap.py --pairs BTC/USDC --intervals 1 5 --lookback-days 3

Run it on the server (DB local), never through the SSH tunnel for real writes.
"""

# ruff: noqa: E402

from __future__ import annotations

import argparse
import asyncio
from datetime import timedelta
from pathlib import Path
import sys

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / ".env")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from krakenbot.config.settings import get_settings
from krakenbot.connectors.exchange import build_exchange_rest_client
from krakenbot.core.database import DatabaseManager
from krakenbot.core.event_bus import get_event_bus
from krakenbot.core.logger import get_logger
from krakenbot.data.backfill import BackfillSummary, backfill_gaps

logger = get_logger(__name__).bind(component="backfill_gap")

INTERVAL_LABEL = {1: "1m", 5: "5m", 15: "15m", 60: "1h", 240: "4h", 1440: "1d", 10080: "1w"}


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "--pairs", nargs="+", default=None, help="Pairs (default: SCHEDULER_PAIRS from settings)."
    )
    parser.add_argument(
        "--intervals",
        nargs="+",
        type=int,
        default=None,
        help="Intervals in minutes (default: SCHEDULER_INTERVALS from settings).",
    )
    parser.add_argument(
        "--lookback-days",
        type=int,
        default=None,
        help="Only scan internal gaps in the last N days (default: full history). "
        "The tail gap is always checked.",
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="Print the gap table without fetching or writing."
    )
    return parser.parse_args(argv)


def format_summary(summary: BackfillSummary) -> str:
    """Human-readable table of the run (one line per gap)."""
    lines = [
        "=" * 100,
        f"  Gap backfill — exchange='{summary.exchange}' "
        f"now={summary.now.isoformat()} dry_run={summary.dry_run}",
        "=" * 100,
        f"  {'Pair':<9} {'TF':<4} {'Start (DB ts)':<26} {'End (DB ts)':<26} "
        f"{'Missing':>7} {'Fetched':>7} {'Inserted':>8}  Status",
        f"  {'-' * 9} {'-' * 4} {'-' * 26} {'-' * 26} {'-' * 7} {'-' * 7} {'-' * 8}  {'-' * 12}",
    ]
    for r in summary.results:
        g = r.gap
        status = f"ERROR: {r.error}" if r.error else r.stop_reason
        lines.append(
            f"  {g.pair:<9} {INTERVAL_LABEL.get(g.interval, f'{g.interval}m'):<4} "
            f"{g.start.isoformat():<26} {g.end.isoformat():<26} "
            f"{g.missing:>7} {r.fetched:>7} {r.inserted:>8}  {status}"
        )
    if not summary.results:
        lines.append("  (no gap)")
    lines.append(f"  {'-' * 98}")
    lines.append(
        f"  gaps_found={summary.gaps_found} gaps_filled={summary.gaps_filled} "
        f"candles_inserted={summary.candles_inserted} failures={len(summary.failures)}"
    )
    return "\n".join(lines)


async def _async_main(args: argparse.Namespace) -> int:
    settings = get_settings()
    exchange = settings.exchange_name
    pairs = args.pairs or list(settings.scheduler.pairs)
    intervals = args.intervals or list(settings.scheduler.intervals)
    lookback = timedelta(days=args.lookback_days) if args.lookback_days else None

    if exchange.lower() != "bybit":
        logger.warning(
            "backfill_unverified_exchange",
            exchange=exchange,
            reason="fetch_ohlcv is end-stamped for bybit only; other clients return open time",
        )

    db_manager = DatabaseManager()
    await db_manager.init_db(settings)
    rest_client = build_exchange_rest_client(settings, get_event_bus(), db_manager, read_only=True)
    try:
        summary = await backfill_gaps(
            rest_client,
            db_manager,
            exchange,
            pairs,
            intervals,
            lookback=lookback,
            dry_run=args.dry_run,
            batch_size=settings.scheduler.batch_size,
        )
    finally:
        await rest_client.close()
        await db_manager.close_db()

    print()
    print(format_summary(summary))
    print()
    return 1 if summary.failures else 0


def main(argv: list[str] | None = None) -> int:
    return asyncio.run(_async_main(parse_args(argv)))


if __name__ == "__main__":
    raise SystemExit(main())
