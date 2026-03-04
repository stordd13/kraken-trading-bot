"""Build ML feature store from historical OHLC data.

Replays candles through the MultiTimeframeAnalyzer to compute
all ML features and store them in the ml_features table.

Usage:
    # Build features for BTC, last 3 years:
    poetry run python scripts/build_ml_features.py --pairs XBT/USDC --days 1095

    # Build for all 3 pairs, custom date range:
    poetry run python scripts/build_ml_features.py \\
        --pairs XBT/USDC ETH/USDC SOL/USDC \\
        --start 2017-01-01 --end 2026-03-01

    # Backfill external data first, then build features:
    poetry run python scripts/build_ml_features.py \\
        --pairs XBT/USDC --days 1095 --fetch-external

    # External data only (no feature build):
    poetry run python scripts/build_ml_features.py --external-only
"""

from __future__ import annotations

import argparse
import asyncio
from datetime import UTC, datetime, timedelta
import os
from pathlib import Path
import sys

from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / ".env")

# Override for local dev
os.environ.setdefault(
    "DATABASE_URL",
    "postgresql+asyncpg://krakenbot:krakenbot@localhost:5432/krakenbot",
)

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from krakenbot.config.settings import get_settings
from krakenbot.core.database import DatabaseManager
from krakenbot.ml.features.external_data import ExternalDataFetcher
from krakenbot.ml.features.feature_store import FeatureStore


async def main() -> None:
    parser = argparse.ArgumentParser(description="Build ML feature store")
    parser.add_argument(
        "--pairs",
        nargs="+",
        default=["XBT/USDC"],
        help="Trading pairs to build features for",
    )
    parser.add_argument(
        "--days",
        type=int,
        default=1095,
        help="Number of days to build features for (from now)",
    )
    parser.add_argument("--start", type=str, default=None, help="Start date (YYYY-MM-DD)")
    parser.add_argument("--end", type=str, default=None, help="End date (YYYY-MM-DD)")
    parser.add_argument(
        "--no-targets",
        action="store_true",
        help="Skip target computation",
    )
    parser.add_argument(
        "--fetch-external",
        action="store_true",
        help="Fetch external data before building features",
    )
    parser.add_argument(
        "--external-only",
        action="store_true",
        help="Only fetch external data, skip feature build",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=500,
        help="DB insert batch size",
    )
    args = parser.parse_args()

    # Compute date range
    if args.end:
        end_date = datetime.strptime(args.end, "%Y-%m-%d").replace(tzinfo=UTC)
    else:
        end_date = datetime.now(UTC)

    if args.start:
        start_date = datetime.strptime(args.start, "%Y-%m-%d").replace(tzinfo=UTC)
    else:
        start_date = end_date - timedelta(days=args.days)

    # Init DB
    settings = get_settings()
    db_manager = DatabaseManager()
    await db_manager.init_db(settings)

    try:
        # Fetch external data if requested
        if args.fetch_external or args.external_only:
            print("Fetching external data (Fear & Greed full backfill)...")
            fetcher = ExternalDataFetcher(db_manager)
            count = await fetcher.backfill_fear_greed()
            print(f"  Fear & Greed: {count} rows upserted")

            if args.external_only:
                print("External data only mode — done.")
                return

        # Build features
        feature_store = FeatureStore(db_manager)

        for pair in args.pairs:
            print(f"\n{'=' * 60}")
            print(f"Building features for {pair}")
            print(f"  Period: {start_date.date()} to {end_date.date()}")
            print(f"{'=' * 60}")

            rows = await feature_store.build_batch(
                pair=pair,
                start_date=start_date,
                end_date=end_date,
                compute_targets=not args.no_targets,
                batch_size=args.batch_size,
            )
            print(f"  Result: {rows} feature rows written")

            # Print summary stats
            await _print_summary(db_manager, pair, start_date, end_date)

    finally:
        await db_manager.close_db()


async def _print_summary(
    db_manager: DatabaseManager,
    pair: str,
    start_date: datetime,
    end_date: datetime,
) -> None:
    """Print feature coverage summary."""
    from sqlalchemy import text

    async with db_manager.read_session() as session:
        # Total rows
        result = await session.execute(
            text(
                "SELECT COUNT(*), MIN(timestamp), MAX(timestamp) "
                "FROM ml_features WHERE pair = :pair AND interval = 240"
            ),
            {"pair": pair},
        )
        row = result.one()
        total, min_ts, max_ts = row

        print(f"\n  Summary for {pair}:")
        print(f"    Total rows: {total}")
        if min_ts and max_ts:
            print(f"    Time range: {min_ts} to {max_ts}")

        # NULL percentage for key features
        feature_cols = [
            "ema_spread_4h", "rsi_14_4h", "supertrend_dist_4h", "adx_4h",
            "realized_vol_4h", "fear_greed_index",
            "target_return_4h", "target_return_24h",
        ]
        if total > 0:
            print("    NULL % per feature:")
            for col in feature_cols:
                result = await session.execute(
                    text(
                        f"SELECT COUNT(*) FILTER (WHERE {col} IS NULL) * 100.0 / COUNT(*) "
                        f"FROM ml_features WHERE pair = :pair AND interval = 240 "
                        f"AND timestamp >= :start AND timestamp <= :end"
                    ),
                    {"pair": pair, "start": start_date, "end": end_date},
                )
                null_pct = result.scalar_one()
                status = "OK" if null_pct < 5 else "WARN" if null_pct < 20 else "HIGH"
                print(f"      {col:30s} {null_pct:6.1f}% NULL  [{status}]")


if __name__ == "__main__":
    asyncio.run(main())
