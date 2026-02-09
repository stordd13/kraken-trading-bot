"""Fetch historical OHLC data from Kraken and store in database.

This script fetches historical OHLC candles from Kraken REST API with automatic
pagination to handle API limits (720 candles per request).

Usage:
    python -m scripts.fetch_ohlc --pair XBT/USDC --interval 15 --days 7
    python -m scripts.fetch_ohlc --pair XBT/EUR --interval 60 --days 30 --batch-size 1000
    python -m scripts.fetch_ohlc --pair XBT/USDC --interval 1 --days 7 --resume

Examples:
    # Fetch 7 days of 15min candles for XBT/USDC
    python -m scripts.fetch_ohlc --pair XBT/USDC --interval 15 --days 7

    # Fetch 90 days of 15min candles (will paginate automatically)
    python -m scripts.fetch_ohlc --pair XBT/USDC --interval 15 --days 90

    # Resume from last stored timestamp
    python -m scripts.fetch_ohlc --pair XBT/USDC --interval 15 --days 90 --resume
"""

import argparse
import asyncio
from datetime import UTC, datetime, timedelta
from pathlib import Path
import sys

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from sqlalchemy import func, select
import structlog
from tqdm import tqdm

from krakenbot.config.settings import get_settings
from krakenbot.connectors.kraken_rest import KrakenRestClient
from krakenbot.core.database import DatabaseManager
from krakenbot.core.event_bus import get_event_bus
from krakenbot.models.market_data import OHLCData
from krakenbot.utils.time_utils import (
    calculate_pagination_steps,
    calculate_total_candles,
    get_max_days_for_interval,
)

logger = structlog.get_logger()


async def get_last_timestamp(
    db_manager: DatabaseManager,
    pair: str,
    interval: int,
) -> datetime | None:
    """Get last stored timestamp for pair/interval.

    Args:
        db_manager: Database manager instance.
        pair: Trading pair (e.g., "XBT/USDC").
        interval: Candle interval in minutes.

    Returns:
        Last stored timestamp or None if no data exists.
    """
    async with db_manager.session() as session:
        stmt = (
            select(func.max(OHLCData.timestamp))
            .where(OHLCData.pair == pair)
            .where(OHLCData.interval == interval)
        )
        result = await session.execute(stmt)
        return result.scalar()


async def get_first_timestamp(
    db_manager: DatabaseManager,
    pair: str,
    interval: int,
) -> datetime | None:
    """Get first (oldest) stored timestamp for pair/interval.

    Args:
        db_manager: Database manager instance.
        pair: Trading pair (e.g., "XBT/USDC").
        interval: Candle interval in minutes.

    Returns:
        First stored timestamp or None if no data exists.
    """
    async with db_manager.session() as session:
        stmt = (
            select(func.min(OHLCData.timestamp))
            .where(OHLCData.pair == pair)
            .where(OHLCData.interval == interval)
        )
        result = await session.execute(stmt)
        return result.scalar()


async def save_ohlc_batch(
    db_manager: DatabaseManager,
    candles: list[dict],
) -> int:
    """Save a batch of OHLC candles to database.

    Uses session.merge() for deduplication (idempotent inserts).

    Args:
        db_manager: Database manager instance.
        candles: List of OHLC dictionaries from fetch_ohlcv().

    Returns:
        Number of candles saved.
    """
    if not candles:
        return 0

    from sqlalchemy.dialects.postgresql import insert as pg_insert

    async with db_manager.session() as session:
        # Use PostgreSQL's ON CONFLICT DO UPDATE for deduplication
        for candle_data in candles:
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
                .on_conflict_do_update(
                    index_elements=["timestamp", "pair", "interval"],
                    set_=dict(
                        open=candle_data["open"],
                        high=candle_data["high"],
                        low=candle_data["low"],
                        close=candle_data["close"],
                        volume=candle_data["volume"],
                    ),
                )
            )
            await session.execute(stmt)

        await session.commit()

    return len(candles)


async def fetch_ohlc_range(
    rest_client: KrakenRestClient,
    db_manager: DatabaseManager,
    pair: str,
    interval: int,
    start_time: datetime,
    end_time: datetime,
    batch_size: int = 1000,
) -> int:
    """Fetch OHLC data for a time range with automatic pagination.

    Args:
        rest_client: Kraken REST client.
        db_manager: Database manager.
        pair: Trading pair (e.g., "XBT/USDC").
        interval: Candle interval in minutes.
        start_time: Start of time range (UTC).
        end_time: End of time range (UTC).
        batch_size: Number of candles per database insert batch.

    Returns:
        Total number of candles fetched.

    Raises:
        Exception: On API errors after retries exhausted.
    """
    # Calculate pagination steps
    chunks = calculate_pagination_steps(start_time, end_time, interval, limit=720)

    total_candles = 0
    batch_buffer = []

    # Progress bar
    total_expected = calculate_total_candles(start_time, end_time, interval)
    pbar = tqdm(
        total=total_expected,
        desc=f"Fetching {pair} {interval}min",
        unit="candles",
    )

    for chunk_start, chunk_end in chunks:
        retry_count = 0
        max_retries = 3

        while retry_count < max_retries:
            try:
                # Fetch OHLC data from Kraken
                candles = await rest_client.fetch_ohlcv(
                    pair=pair,
                    interval=interval,
                    since=chunk_start,
                    limit=720,
                )

                if not candles:
                    logger.warning(
                        "no_candles_returned",
                        pair=pair,
                        interval=interval,
                        chunk_start=chunk_start,
                        chunk_end=chunk_end,
                    )
                    break

                # Add to batch buffer
                batch_buffer.extend(candles)

                # Flush batch if buffer is full
                if len(batch_buffer) >= batch_size:
                    saved_count = await save_ohlc_batch(db_manager, batch_buffer)
                    total_candles += saved_count
                    pbar.update(saved_count)
                    batch_buffer = []

                # Rate limiting: 1 request per second
                await asyncio.sleep(1)

                # Success - break retry loop
                break

            except Exception as e:
                retry_count += 1
                logger.warning(
                    "fetch_failed_retrying",
                    pair=pair,
                    interval=interval,
                    chunk_start=chunk_start,
                    retry=retry_count,
                    max_retries=max_retries,
                    error=str(e),
                )

                if retry_count >= max_retries:
                    logger.error(
                        "fetch_failed_max_retries",
                        pair=pair,
                        interval=interval,
                        chunk_start=chunk_start,
                        error=str(e),
                    )
                    pbar.close()
                    raise

                # Wait before retry (exponential backoff)
                await asyncio.sleep(2**retry_count)

    # Flush remaining candles in buffer
    if batch_buffer:
        saved_count = await save_ohlc_batch(db_manager, batch_buffer)
        total_candles += saved_count
        pbar.update(saved_count)

    pbar.close()

    logger.info(
        "fetch_completed",
        pair=pair,
        interval=interval,
        start_time=start_time,
        end_time=end_time,
        total_candles=total_candles,
    )

    return total_candles


async def fetch_ohlc_with_resume(
    rest_client: KrakenRestClient,
    db_manager: DatabaseManager,
    pair: str,
    interval: int,
    days: int,
    resume: bool = False,
    batch_size: int = 1000,
) -> int:
    """Fetch OHLC data, optionally resuming from last stored timestamp.

    Args:
        rest_client: Kraken REST client.
        db_manager: Database manager.
        pair: Trading pair (e.g., "XBT/USDC").
        interval: Candle interval in minutes.
        days: Number of days to fetch.
        resume: If True, resume from last stored timestamp.
        batch_size: Number of candles per database insert batch.

    Returns:
        Total number of candles fetched.
    """
    end_time = datetime.now(UTC)

    if resume:
        # Check for existing data
        last_ts = await get_last_timestamp(db_manager, pair, interval)

        if last_ts:
            # Resume from last timestamp + 1 interval
            start_time = last_ts + timedelta(minutes=interval)
            logger.info(
                "resuming_fetch",
                pair=pair,
                interval=interval,
                last_timestamp=last_ts,
                resume_from=start_time,
            )
        else:
            # No existing data, fetch full range
            start_time = end_time - timedelta(days=days)
            logger.info(
                "no_existing_data",
                pair=pair,
                interval=interval,
                fetching_full_range=True,
            )
    else:
        # Fetch full range
        start_time = end_time - timedelta(days=days)

    # Validate time range
    if start_time >= end_time:
        logger.warning(
            "invalid_time_range",
            pair=pair,
            interval=interval,
            start_time=start_time,
            end_time=end_time,
        )
        return 0

    # Fetch data
    return await fetch_ohlc_range(
        rest_client=rest_client,
        db_manager=db_manager,
        pair=pair,
        interval=interval,
        start_time=start_time,
        end_time=end_time,
        batch_size=batch_size,
    )


async def fetch_ohlc_bidirectional(
    rest_client: KrakenRestClient,
    db_manager: DatabaseManager,
    pair: str,
    interval: int,
    max_days: int,
    batch_size: int = 1000,
) -> dict:
    """Fetch OHLC data in both directions: fill gaps before and after existing data.

    This function:
    1. Finds the first (oldest) and last (newest) timestamps in DB
    2. Fetches historical data BEFORE the first timestamp (up to max_days limit)
    3. Fetches new data AFTER the last timestamp (up to now)

    Args:
        rest_client: Kraken REST client.
        db_manager: Database manager.
        pair: Trading pair (e.g., "XBT/USDC").
        interval: Candle interval in minutes.
        max_days: Maximum days of history to fetch (based on Kraken API limits).
        batch_size: Number of candles per database insert batch.

    Returns:
        Dictionary with fetch results:
        {
            "backwards_candles": int,  # Candles fetched before existing data
            "forwards_candles": int,   # Candles fetched after existing data
            "total_candles": int,      # Total candles fetched
            "first_ts_before": datetime | None,  # First timestamp before backfill
            "first_ts_after": datetime | None,   # First timestamp after backfill
        }
    """
    now = datetime.now(UTC)
    earliest_possible = now - timedelta(days=max_days)

    # Get current data boundaries
    first_ts = await get_first_timestamp(db_manager, pair, interval)
    last_ts = await get_last_timestamp(db_manager, pair, interval)

    result = {
        "backwards_candles": 0,
        "forwards_candles": 0,
        "total_candles": 0,
        "first_ts_before": first_ts,
        "first_ts_after": None,
    }

    if first_ts is None:
        # No existing data - fetch full range
        logger.info(
            "no_existing_data_fetching_full_range",
            pair=pair,
            interval=interval,
            max_days=max_days,
        )
        candles = await fetch_ohlc_range(
            rest_client=rest_client,
            db_manager=db_manager,
            pair=pair,
            interval=interval,
            start_time=earliest_possible,
            end_time=now,
            batch_size=batch_size,
        )
        result["backwards_candles"] = candles
        result["total_candles"] = candles
        result["first_ts_after"] = await get_first_timestamp(db_manager, pair, interval)
        return result

    # Step 1: Fetch BACKWARDS (historical data before first_ts)
    if first_ts > earliest_possible:
        # There's room to fetch older data
        backwards_end = first_ts - timedelta(minutes=interval)
        backwards_start = earliest_possible

        logger.info(
            "fetching_backwards",
            pair=pair,
            interval=interval,
            from_ts=backwards_start,
            to_ts=backwards_end,
            days_to_fetch=(backwards_end - backwards_start).days,
        )

        if backwards_start < backwards_end:
            result["backwards_candles"] = await fetch_ohlc_range(
                rest_client=rest_client,
                db_manager=db_manager,
                pair=pair,
                interval=interval,
                start_time=backwards_start,
                end_time=backwards_end,
                batch_size=batch_size,
            )
    else:
        logger.info(
            "no_backwards_fetch_needed",
            pair=pair,
            interval=interval,
            first_ts=first_ts,
            earliest_possible=earliest_possible,
        )

    # Step 2: Fetch FORWARDS (new data after last_ts)
    if last_ts and last_ts < now:
        forwards_start = last_ts + timedelta(minutes=interval)
        forwards_end = now

        logger.info(
            "fetching_forwards",
            pair=pair,
            interval=interval,
            from_ts=forwards_start,
            to_ts=forwards_end,
        )

        if forwards_start < forwards_end:
            result["forwards_candles"] = await fetch_ohlc_range(
                rest_client=rest_client,
                db_manager=db_manager,
                pair=pair,
                interval=interval,
                start_time=forwards_start,
                end_time=forwards_end,
                batch_size=batch_size,
            )

    result["total_candles"] = result["backwards_candles"] + result["forwards_candles"]
    result["first_ts_after"] = await get_first_timestamp(db_manager, pair, interval)

    logger.info(
        "bidirectional_fetch_complete",
        pair=pair,
        interval=interval,
        backwards_candles=result["backwards_candles"],
        forwards_candles=result["forwards_candles"],
        total_candles=result["total_candles"],
        first_ts_before=result["first_ts_before"],
        first_ts_after=result["first_ts_after"],
    )

    return result


async def main():
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Fetch historical OHLC data from Kraken",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )

    parser.add_argument(
        "--pair",
        type=str,
        required=True,
        help="Trading pair (e.g., XBT/USDC, XBT/EUR)",
    )

    parser.add_argument(
        "--interval",
        type=int,
        required=True,
        choices=[1, 5, 15, 30, 60, 240, 1440],
        help="Candle interval in minutes",
    )

    parser.add_argument(
        "--days",
        type=int,
        help="Number of days to fetch (if not specified, uses safe max for interval)",
    )

    parser.add_argument(
        "--limit",
        type=int,
        default=720,
        help="Max candles per API request (default: 720, Kraken max)",
    )

    parser.add_argument(
        "--batch-size",
        type=int,
        default=1000,
        help="Number of candles per database batch insert (default: 1000)",
    )

    parser.add_argument(
        "--resume",
        action="store_true",
        help="Resume from last stored timestamp instead of fetching full range",
    )

    args = parser.parse_args()

    # Determine days to fetch
    if args.days is None:
        args.days = get_max_days_for_interval(args.interval)
        logger.info(
            "using_safe_max_days",
            interval=args.interval,
            days=args.days,
        )

    # Validate days against safe limits
    max_safe_days = get_max_days_for_interval(args.interval)
    if args.days > max_safe_days:
        logger.warning(
            "days_exceeds_safe_limit",
            interval=args.interval,
            requested_days=args.days,
            max_safe_days=max_safe_days,
        )
        print(
            f"⚠️  Warning: Requesting {args.days} days exceeds Kraken retention limit "
            f"({max_safe_days} days for {args.interval}min interval)"
        )
        print("Some data may be unavailable. Continue anyway? [y/N]: ", end="")
        response = input().lower()
        if response != "y":
            print("Aborted.")
            return

    # Initialize components
    settings = get_settings()
    event_bus = get_event_bus()
    db_manager = DatabaseManager()
    await db_manager.init_db(settings)

    rest_client = KrakenRestClient(settings, event_bus, db_manager)

    try:
        logger.info(
            "starting_fetch",
            pair=args.pair,
            interval=args.interval,
            days=args.days,
            resume=args.resume,
        )

        # Fetch OHLC data
        total_candles = await fetch_ohlc_with_resume(
            rest_client=rest_client,
            db_manager=db_manager,
            pair=args.pair,
            interval=args.interval,
            days=args.days,
            resume=args.resume,
            batch_size=args.batch_size,
        )

        print(f"\n✅ Fetched {total_candles} candles for {args.pair} ({args.interval}min)")
        logger.info(
            "fetch_success",
            pair=args.pair,
            interval=args.interval,
            total_candles=total_candles,
        )

    except Exception as e:
        logger.error(
            "fetch_failed",
            pair=args.pair,
            interval=args.interval,
            error=str(e),
        )
        print(f"\n❌ Fetch failed: {e}")
        sys.exit(1)

    finally:
        await rest_client.close()
        await db_manager.close_db()


if __name__ == "__main__":
    asyncio.run(main())
