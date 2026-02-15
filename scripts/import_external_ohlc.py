"""Import historical OHLC data from external exchanges via CCXT.

Fetches BTC/USDT data from Binance (deep history, years of data) and imports
it into our database as XBT/USDC candles. Uses ON CONFLICT DO NOTHING to
preserve existing Kraken collector data.

Why Binance BTC/USDT?
- Binance has the deepest free historical data (years)
- BTC/USDT ≈ BTC/USDC (< 0.1% price difference, negligible for backtesting)
- CCXT handles pagination correctly for Binance (unlike Kraken REST API)

Usage:
    poetry run python scripts/import_external_ohlc.py --intervals 15 60 --days 365
    poetry run python scripts/import_external_ohlc.py --intervals 60 --days 730 --dry-run
    poetry run python scripts/import_external_ohlc.py --intervals 15 60 --days 365 -y
"""

import argparse
import asyncio
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
import sys

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

import ccxt.async_support as ccxt
import structlog
from sqlalchemy.dialects.postgresql import insert as pg_insert

from krakenbot.config.settings import get_settings
from krakenbot.core.database import DatabaseManager
from krakenbot.models.market_data import OHLCData

logger = structlog.get_logger()

# Mapping: CCXT timeframe string -> interval in minutes
TIMEFRAME_MAP = {
    1: "1m",
    5: "5m",
    15: "15m",
    60: "1h",
    240: "4h",
    1440: "1d",
}

# Target pair name in our database
TARGET_PAIR = "XBT/USDC"

# Source exchange and symbol
SOURCE_EXCHANGE = "binance"
SOURCE_SYMBOL = "BTC/USDT"

# Binance returns max 1000 candles per request
BINANCE_LIMIT = 1000

# Batch size for DB inserts
DB_BATCH_SIZE = 500


async def fetch_candles_from_binance(
    exchange: ccxt.Exchange,
    interval: int,
    start_time: datetime,
    end_time: datetime,
) -> list[dict]:
    """Fetch OHLCV candles from Binance with automatic pagination.

    Args:
        exchange: CCXT Binance exchange instance.
        interval: Candle interval in minutes.
        start_time: Start of period (UTC).
        end_time: End of period (UTC).

    Returns:
        List of candle dicts ready for DB insertion.
    """
    timeframe = TIMEFRAME_MAP.get(interval)
    if not timeframe:
        raise ValueError(
            f"Unsupported interval: {interval}. "
            f"Supported: {list(TIMEFRAME_MAP.keys())}"
        )

    since_ms = int(start_time.timestamp() * 1000)
    end_ms = int(end_time.timestamp() * 1000)
    interval_ms = interval * 60 * 1000

    all_candles: list[dict] = []
    current_since = since_ms

    while current_since < end_ms:
        try:
            ohlcv = await exchange.fetch_ohlcv(
                SOURCE_SYMBOL,
                timeframe=timeframe,
                since=current_since,
                limit=BINANCE_LIMIT,
            )
        except ccxt.RateLimitExceeded:
            logger.warning("rate_limit_hit, waiting 10s")
            await asyncio.sleep(10)
            continue
        except ccxt.BaseError as e:
            logger.error("ccxt_error", error=str(e))
            break

        if not ohlcv:
            break

        for candle in ohlcv:
            ts_ms, o, h, l, c, v = candle  # noqa: E741
            if ts_ms >= end_ms:
                break

            all_candles.append({
                "timestamp": datetime.fromtimestamp(ts_ms / 1000, tz=UTC),
                "pair": TARGET_PAIR,
                "interval": interval,
                "open": Decimal(str(o)),
                "high": Decimal(str(h)),
                "low": Decimal(str(l)),
                "close": Decimal(str(c)),
                "volume": Decimal(str(v)),
            })

        # Move to after the last candle
        last_ts = ohlcv[-1][0]
        if last_ts <= current_since:
            # No progress, avoid infinite loop
            break
        current_since = last_ts + interval_ms

        # Log progress
        fetched_end = datetime.fromtimestamp(last_ts / 1000, tz=UTC)
        logger.info(
            "fetch_progress",
            interval=interval,
            candles_fetched=len(all_candles),
            current_date=fetched_end.strftime("%Y-%m-%d %H:%M"),
        )

        # Respect rate limits (Binance: 1200 req/min)
        await asyncio.sleep(0.1)

    return all_candles


async def save_candles_preserve_existing(
    db_manager: DatabaseManager,
    candles: list[dict],
) -> tuple[int, int]:
    """Save candles to DB, preserving existing data.

    Uses ON CONFLICT DO NOTHING so existing Kraken collector data
    is never overwritten by external source data.

    Args:
        db_manager: Database manager instance.
        candles: List of candle dicts.

    Returns:
        Tuple of (total_attempted, rows_inserted).
    """
    if not candles:
        return 0, 0

    total_inserted = 0

    for i in range(0, len(candles), DB_BATCH_SIZE):
        batch = candles[i : i + DB_BATCH_SIZE]

        async with db_manager.session() as session:
            for candle_data in batch:
                stmt = (
                    pg_insert(OHLCData)
                    .values(
                        timestamp=candle_data["timestamp"],
                        pair=candle_data["pair"],
                        interval=candle_data["interval"],
                        open=candle_data["open"],
                        high=candle_data["high"],
                        low=candle_data["low"],
                        close=candle_data["close"],
                        volume=candle_data["volume"],
                    )
                    .on_conflict_do_nothing(
                        index_elements=["timestamp", "pair", "interval"],
                    )
                )
                result = await session.execute(stmt)
                if result.rowcount > 0:
                    total_inserted += 1

            await session.commit()

        logger.info(
            "batch_saved",
            batch_num=i // DB_BATCH_SIZE + 1,
            batch_size=len(batch),
            total_inserted=total_inserted,
        )

    return len(candles), total_inserted


async def get_existing_data_range(
    db_manager: DatabaseManager,
    pair: str,
    interval: int,
) -> tuple[datetime | None, datetime | None, int]:
    """Get the existing data range for a pair/interval.

    Returns:
        Tuple of (earliest_timestamp, latest_timestamp, count).
    """
    from sqlalchemy import func, select

    async with db_manager.session() as session:
        stmt = (
            select(
                func.min(OHLCData.timestamp),
                func.max(OHLCData.timestamp),
                func.count(),
            )
            .where(OHLCData.pair == pair)
            .where(OHLCData.interval == interval)
        )
        result = await session.execute(stmt)
        row = result.one()
        return row[0], row[1], row[2]


async def import_interval(
    exchange: ccxt.Exchange,
    db_manager: DatabaseManager,
    interval: int,
    days: int,
    dry_run: bool = False,
) -> dict:
    """Import data for a single interval.

    Args:
        exchange: CCXT exchange instance.
        db_manager: Database manager.
        interval: Candle interval in minutes.
        days: Number of days to go back.
        dry_run: If True, only estimate without inserting.

    Returns:
        Dict with import statistics.
    """
    end_time = datetime.now(UTC)
    start_time = end_time - timedelta(days=days)

    # Check existing data
    earliest, latest, count = await get_existing_data_range(
        db_manager, TARGET_PAIR, interval
    )

    expected_candles = int(days * 24 * 60 / interval)

    logger.info(
        "import_start",
        interval=interval,
        timeframe=TIMEFRAME_MAP[interval],
        source=f"{SOURCE_EXCHANGE}:{SOURCE_SYMBOL}",
        target=TARGET_PAIR,
        start=start_time.strftime("%Y-%m-%d"),
        end=end_time.strftime("%Y-%m-%d"),
        days=days,
        expected_candles=expected_candles,
        existing_candles=count,
        existing_range=f"{earliest} → {latest}" if earliest else "none",
    )

    if dry_run:
        gap = expected_candles - count
        logger.info(
            "dry_run_estimate",
            interval=interval,
            expected=expected_candles,
            existing=count,
            estimated_new=max(0, gap),
        )
        return {
            "interval": interval,
            "expected": expected_candles,
            "existing": count,
            "estimated_new": max(0, gap),
            "fetched": 0,
            "inserted": 0,
        }

    # Fetch from Binance
    candles = await fetch_candles_from_binance(
        exchange, interval, start_time, end_time
    )

    logger.info(
        "fetch_complete",
        interval=interval,
        candles_fetched=len(candles),
    )

    if not candles:
        logger.warning("no_candles_fetched", interval=interval)
        return {
            "interval": interval,
            "expected": expected_candles,
            "existing": count,
            "fetched": 0,
            "inserted": 0,
        }

    # Save to DB (preserve existing)
    total_attempted, total_inserted = await save_candles_preserve_existing(
        db_manager, candles
    )

    # Check new data range
    new_earliest, new_latest, new_count = await get_existing_data_range(
        db_manager, TARGET_PAIR, interval
    )

    logger.info(
        "import_complete",
        interval=interval,
        fetched=total_attempted,
        inserted=total_inserted,
        skipped=total_attempted - total_inserted,
        new_total=new_count,
        new_range=f"{new_earliest} → {new_latest}",
    )

    return {
        "interval": interval,
        "expected": expected_candles,
        "existing_before": count,
        "fetched": total_attempted,
        "inserted": total_inserted,
        "skipped": total_attempted - total_inserted,
        "total_after": new_count,
    }


async def main() -> None:
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Import historical OHLC data from Binance (BTC/USDT → XBT/USDC)"
    )
    parser.add_argument(
        "--intervals",
        nargs="+",
        type=int,
        default=[15, 60],
        help="Candle intervals in minutes (default: 15 60)",
    )
    parser.add_argument(
        "--days",
        type=int,
        default=365,
        help="Days of history to fetch (default: 365)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Estimate without inserting data",
    )
    parser.add_argument(
        "-y", "--yes",
        action="store_true",
        help="Skip confirmation prompt",
    )
    args = parser.parse_args()

    # Validate intervals
    for interval in args.intervals:
        if interval not in TIMEFRAME_MAP:
            print(f"Error: unsupported interval {interval}. "
                  f"Supported: {list(TIMEFRAME_MAP.keys())}")
            sys.exit(1)

    # Summary
    print("\n" + "=" * 60)
    print("  External OHLC Data Import")
    print("=" * 60)
    print(f"  Source:     Binance {SOURCE_SYMBOL}")
    print(f"  Target:     {TARGET_PAIR} (in our DB)")
    print(f"  Intervals:  {args.intervals} minutes")
    print(f"  Days:       {args.days}")
    print(f"  Dry run:    {args.dry_run}")
    print()
    print("  NOTE: Uses ON CONFLICT DO NOTHING — existing Kraken")
    print("        collector data will NOT be overwritten.")
    print("=" * 60 + "\n")

    if not args.yes and not args.dry_run:
        confirm = input("Proceed? [y/N] ").strip().lower()
        if confirm != "y":
            print("Aborted.")
            sys.exit(0)

    # Initialize database
    settings = get_settings()
    db_manager = DatabaseManager()
    await db_manager.init_db(settings)

    # Initialize Binance via CCXT (no API key needed for public data)
    exchange = ccxt.binance({
        "enableRateLimit": True,
    })

    try:
        results = []
        for interval in args.intervals:
            result = await import_interval(
                exchange, db_manager, interval, args.days, args.dry_run
            )
            results.append(result)

        # Print summary
        print("\n" + "=" * 60)
        print("  Import Summary")
        print("=" * 60)
        for r in results:
            tf = TIMEFRAME_MAP.get(r["interval"], f"{r['interval']}m")
            print(f"\n  {tf} ({r['interval']}min):")
            if args.dry_run:
                print(f"    Expected candles:  {r['expected']:,}")
                print(f"    Existing candles:  {r['existing']:,}")
                print(f"    Estimated new:     {r['estimated_new']:,}")
            else:
                print(f"    Fetched from Binance:  {r['fetched']:,}")
                print(f"    Inserted (new):        {r['inserted']:,}")
                print(f"    Skipped (existing):    {r['skipped']:,}")
                print(f"    Total in DB:           {r['total_after']:,}")

        print("\n" + "=" * 60 + "\n")

    finally:
        await exchange.close()
        await db_manager.close_db()


if __name__ == "__main__":
    asyncio.run(main())
