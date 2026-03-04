"""Fetch external data for ML feature store.

Usage:
    # Backfill full Fear & Greed history (since 2018):
    poetry run python scripts/fetch_external_data.py --source fear_greed --backfill

    # Fetch latest Fear & Greed only:
    poetry run python scripts/fetch_external_data.py --source fear_greed

    # Fetch last 30 days:
    poetry run python scripts/fetch_external_data.py --source fear_greed --days 30
"""

from __future__ import annotations

import argparse
import asyncio
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


async def main() -> None:
    parser = argparse.ArgumentParser(description="Fetch external data for ML features")
    parser.add_argument(
        "--source",
        choices=["fear_greed", "all"],
        default="fear_greed",
        help="Data source to fetch",
    )
    parser.add_argument(
        "--backfill",
        action="store_true",
        help="Backfill full history (all available data)",
    )
    parser.add_argument(
        "--days",
        type=int,
        default=1,
        help="Number of days to fetch (default: 1 = latest only)",
    )
    args = parser.parse_args()

    # Init DB
    settings = get_settings()
    db_manager = DatabaseManager()
    await db_manager.init_db(settings)

    fetcher = ExternalDataFetcher(db_manager)

    try:
        if args.source in ("fear_greed", "all"):
            if args.backfill:
                print("Backfilling full Fear & Greed history...")
                count = await fetcher.backfill_fear_greed()
                print(f"Fear & Greed: {count} rows upserted (full history)")
            else:
                print(f"Fetching Fear & Greed (last {args.days} days)...")
                count = await fetcher.fetch_and_store_fear_greed(limit=args.days)
                print(f"Fear & Greed: {count} rows upserted")
    finally:
        await db_manager.close_db()


if __name__ == "__main__":
    asyncio.run(main())
