"""Backfill historical OHLC data for all configured pairs and intervals.

This script performs initial backfilling of historical data from Kraken API
for all configured trading pairs and intervals. It's designed to be run once
to populate the database before starting the scheduled collection jobs.

Usage:
    python -m scripts.backfill_historical_data
    python -m scripts.backfill_historical_data --dry-run
    python -m scripts.backfill_historical_data --pairs XBT/USDC
    python -m scripts.backfill_historical_data --intervals 15 60

Examples:
    # Backfill all configured pairs and intervals
    python -m scripts.backfill_historical_data

    # Dry run to estimate volume
    python -m scripts.backfill_historical_data --dry-run

    # Backfill only specific pairs
    python -m scripts.backfill_historical_data --pairs XBT/USDC XBT/EUR

    # Backfill only specific intervals
    python -m scripts.backfill_historical_data --intervals 15 60
"""

import argparse
import asyncio
from pathlib import Path
import sys

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from datetime import UTC, datetime, timedelta

import structlog

from krakenbot.config.settings import get_settings
from krakenbot.connectors.kraken.rest import KrakenRestClient
from krakenbot.core.database import DatabaseManager
from krakenbot.core.event_bus import get_event_bus
from krakenbot.utils.time_utils import (
    calculate_total_candles,
    get_max_days_for_interval,
)

logger = structlog.get_logger()


async def estimate_backfill_volume(
    pairs: list[str],
    intervals: list[int],
) -> dict:
    """Estimate total volume of data to backfill.

    Args:
        pairs: List of trading pairs.
        intervals: List of intervals in minutes.

    Returns:
        Dictionary with estimation details.
    """
    total_candles = 0
    total_api_calls = 0
    details = []

    for interval in intervals:
        max_days = get_max_days_for_interval(interval)
        start_time = datetime.now(UTC) - timedelta(days=max_days)
        end_time = datetime.now(UTC)

        candles_per_pair = calculate_total_candles(start_time, end_time, interval)
        candles_for_interval = candles_per_pair * len(pairs)

        # Each API call can fetch max 720 candles
        api_calls_per_pair = (candles_per_pair + 719) // 720
        api_calls_for_interval = api_calls_per_pair * len(pairs)

        total_candles += candles_for_interval
        total_api_calls += api_calls_for_interval

        details.append(
            {
                "interval": interval,
                "max_days": max_days,
                "candles_per_pair": candles_per_pair,
                "candles_total": candles_for_interval,
                "api_calls": api_calls_for_interval,
            }
        )

    # Estimate time (1 second per API call)
    estimated_seconds = total_api_calls
    estimated_minutes = estimated_seconds / 60

    return {
        "total_candles": total_candles,
        "total_api_calls": total_api_calls,
        "estimated_time_seconds": estimated_seconds,
        "estimated_time_minutes": estimated_minutes,
        "details": details,
    }


async def backfill_pair_interval(
    rest_client: KrakenRestClient,
    db_manager: DatabaseManager,
    pair: str,
    interval: int,
    batch_size: int = 1000,
    bidirectional: bool = True,
) -> dict:
    """Backfill data for a single pair and interval.

    Args:
        rest_client: Kraken REST client.
        db_manager: Database manager.
        pair: Trading pair (e.g., "XBT/USDC").
        interval: Candle interval in minutes.
        batch_size: Batch size for database inserts.
        bidirectional: If True, fetch both historical and new data.
                       If False, only fetch new data (forward).

    Returns:
        Dictionary with fetch results (or int for backwards compatibility).
    """
    from scripts.fetch_ohlc import fetch_ohlc_bidirectional, fetch_ohlc_with_resume

    max_days = get_max_days_for_interval(interval)

    logger.info(
        "backfilling_pair_interval",
        pair=pair,
        interval=interval,
        max_days=max_days,
        bidirectional=bidirectional,
    )

    try:
        if bidirectional:
            # Fetch both historical (backwards) and new (forwards) data
            result = await fetch_ohlc_bidirectional(
                rest_client=rest_client,
                db_manager=db_manager,
                pair=pair,
                interval=interval,
                max_days=max_days,
                batch_size=batch_size,
            )

            logger.info(
                "backfill_completed",
                pair=pair,
                interval=interval,
                backwards_candles=result["backwards_candles"],
                forwards_candles=result["forwards_candles"],
                total_candles=result["total_candles"],
            )

            return result
        else:
            # Only fetch new data (forward from last timestamp)
            total_candles = await fetch_ohlc_with_resume(
                rest_client=rest_client,
                db_manager=db_manager,
                pair=pair,
                interval=interval,
                days=max_days,
                resume=True,
                batch_size=batch_size,
            )

            logger.info(
                "backfill_completed",
                pair=pair,
                interval=interval,
                candles_fetched=total_candles,
            )

            return {
                "total_candles": total_candles,
                "backwards_candles": 0,
                "forwards_candles": total_candles,
            }

    except Exception as e:
        logger.error(
            "backfill_failed",
            pair=pair,
            interval=interval,
            error=str(e),
        )
        raise


async def backfill_all(
    pairs: list[str],
    intervals: list[int],
    parallel: bool = False,
    batch_size: int = 1000,
    bidirectional: bool = True,
) -> dict:
    """Backfill all pairs and intervals.

    Args:
        pairs: List of trading pairs.
        intervals: List of intervals in minutes.
        parallel: If True, run all backfills in parallel (NOT RECOMMENDED due to rate limits).
        batch_size: Batch size for database inserts.
        bidirectional: If True, fetch both historical and new data.

    Returns:
        Dictionary with backfill results.
    """
    settings = get_settings()
    event_bus = get_event_bus()
    db_manager = DatabaseManager()
    await db_manager.init_db(settings)

    rest_client = KrakenRestClient(settings, event_bus, db_manager)

    results = {
        "pairs": {},
        "total_candles": 0,
        "backwards_candles": 0,
        "forwards_candles": 0,
        "total_tasks": 0,
        "failed_tasks": 0,
    }

    try:
        tasks = []

        for pair in pairs:
            results["pairs"][pair] = {}
            for interval in intervals:
                results["total_tasks"] += 1

                if parallel:
                    # NOT RECOMMENDED: May hit rate limits
                    task = backfill_pair_interval(
                        rest_client, db_manager, pair, interval, batch_size, bidirectional
                    )
                    tasks.append(task)
                else:
                    # Sequential execution (respects rate limits)
                    try:
                        result = await backfill_pair_interval(
                            rest_client, db_manager, pair, interval, batch_size, bidirectional
                        )
                        results["pairs"][pair][interval] = result
                        results["total_candles"] += result["total_candles"]
                        results["backwards_candles"] += result.get("backwards_candles", 0)
                        results["forwards_candles"] += result.get("forwards_candles", 0)
                    except Exception as e:
                        results["failed_tasks"] += 1
                        results["pairs"][pair][interval] = f"FAILED: {e}"

        # If parallel, wait for all tasks
        if parallel:
            task_results = await asyncio.gather(*tasks, return_exceptions=True)

            pair_idx = 0
            interval_idx = 0
            for result in task_results:
                pair = pairs[pair_idx]
                interval = intervals[interval_idx]

                if isinstance(result, Exception):
                    results["failed_tasks"] += 1
                    results["pairs"][pair][interval] = f"FAILED: {result}"
                else:
                    results["pairs"][pair][interval] = result
                    results["total_candles"] += result["total_candles"]
                    results["backwards_candles"] += result.get("backwards_candles", 0)
                    results["forwards_candles"] += result.get("forwards_candles", 0)

                interval_idx += 1
                if interval_idx >= len(intervals):
                    interval_idx = 0
                    pair_idx += 1

    finally:
        await rest_client.close()
        await db_manager.close_db()

    return results


def print_estimation(estimation: dict):
    """Print backfill estimation in human-readable format.

    Args:
        estimation: Estimation dictionary from estimate_backfill_volume().
    """
    print("\n" + "=" * 80)
    print("BACKFILL ESTIMATION")
    print("=" * 80)

    for detail in estimation["details"]:
        print(f"\nInterval {detail['interval']}min: {detail['max_days']} days")
        print(f"  Candles per pair: {detail['candles_per_pair']:,}")
        print(f"  Total candles: {detail['candles_total']:,}")
        print(f"  API calls: {detail['api_calls']:,}")

    print("\n" + "-" * 80)
    print(f"TOTAL CANDLES: {estimation['total_candles']:,}")
    print(f"TOTAL API CALLS: {estimation['total_api_calls']:,}")
    print(
        f"ESTIMATED TIME: {estimation['estimated_time_minutes']:.1f} minutes (~{int(estimation['estimated_time_seconds'])} seconds)"
    )
    print("=" * 80 + "\n")


def print_results(results: dict):
    """Print backfill results in human-readable format.

    Args:
        results: Results dictionary from backfill_all().
    """
    print("\n" + "=" * 80)
    print("BACKFILL RESULTS")
    print("=" * 80)

    for pair, intervals_data in results["pairs"].items():
        print(f"\nPair: {pair}")
        for interval, data in intervals_data.items():
            if isinstance(data, str):
                print(f"  {interval}min: {data}")
            elif isinstance(data, dict):
                backwards = data.get("backwards_candles", 0)
                forwards = data.get("forwards_candles", 0)
                total = data.get("total_candles", 0)
                print(
                    f"  {interval}min: {total:,} candles (historical: {backwards:,}, new: {forwards:,})"
                )
            else:
                print(f"  {interval}min: {data:,} candles")

    print("\n" + "-" * 80)
    print(f"TOTAL CANDLES FETCHED: {results['total_candles']:,}")
    if "backwards_candles" in results:
        print(f"  - Historical (backwards): {results['backwards_candles']:,}")
        print(f"  - New (forwards): {results['forwards_candles']:,}")
    print(f"TOTAL TASKS: {results['total_tasks']}")
    print(f"FAILED TASKS: {results['failed_tasks']}")

    if results["failed_tasks"] == 0:
        print("\n✅ All backfill tasks completed successfully!")
    else:
        print(f"\n⚠️  {results['failed_tasks']} tasks failed. Check logs for details.")

    print("=" * 80 + "\n")


async def main():
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Backfill historical OHLC data from Kraken",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )

    parser.add_argument(
        "--pairs",
        type=str,
        nargs="+",
        help="Trading pairs to backfill (default: from settings)",
    )

    parser.add_argument(
        "--intervals",
        type=int,
        nargs="+",
        choices=[1, 5, 15, 30, 60, 240, 1440],
        help="Intervals to backfill (default: from settings)",
    )

    parser.add_argument(
        "--batch-size",
        type=int,
        default=1000,
        help="Number of candles per database batch insert (default: 1000)",
    )

    parser.add_argument(
        "--parallel",
        action="store_true",
        help="Run backfills in parallel (NOT RECOMMENDED: may hit rate limits)",
    )

    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Estimate volume without fetching data",
    )

    parser.add_argument(
        "--forward-only",
        action="store_true",
        help="Only fetch new data (after last timestamp). Skip historical backfill.",
    )

    parser.add_argument(
        "-y",
        "--yes",
        action="store_true",
        help="Skip confirmation prompts (for non-interactive use)",
    )

    args = parser.parse_args()

    # Load settings
    settings = get_settings()

    # Determine pairs and intervals
    pairs = args.pairs if args.pairs else settings.scheduler.pairs
    intervals = args.intervals if args.intervals else settings.scheduler.intervals

    bidirectional = not args.forward_only

    logger.info(
        "backfill_starting",
        pairs=pairs,
        intervals=intervals,
        parallel=args.parallel,
        dry_run=args.dry_run,
        bidirectional=bidirectional,
    )

    if args.dry_run:
        # Dry run - estimate only
        estimation = await estimate_backfill_volume(pairs, intervals)
        print_estimation(estimation)
        return

    # Warn if parallel mode
    if args.parallel and not args.yes:
        print("⚠️  WARNING: Parallel mode may hit Kraken API rate limits (15 req/min)")
        print("This is NOT RECOMMENDED. Sequential mode is safer.")
        print("\nContinue anyway? [y/N]: ", end="")
        response = input().lower()
        if response != "y":
            print("Aborted.")
            return

    # Show estimation before starting
    estimation = await estimate_backfill_volume(pairs, intervals)
    print_estimation(estimation)

    if not args.yes:
        print("Start backfill? [y/N]: ", end="")
        response = input().lower()
        if response != "y":
            print("Aborted.")
            return

    # Execute backfill
    try:
        results = await backfill_all(
            pairs=pairs,
            intervals=intervals,
            parallel=args.parallel,
            batch_size=args.batch_size,
            bidirectional=bidirectional,
        )

        # Print results
        print_results(results)

        # Exit with error code if any tasks failed
        if results["failed_tasks"] > 0:
            sys.exit(1)

    except Exception as e:
        logger.error("backfill_error", error=str(e))
        print(f"\n❌ Backfill failed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
