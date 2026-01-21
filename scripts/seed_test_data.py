"""Seed test OHLC data for testing backtest and dashboard.

This script creates fake OHLC data to test the backtest and dashboard features
without waiting for the bot to accumulate real data.

Usage:
    python -m scripts.seed_test_data --days 30
"""

import argparse
import asyncio
from datetime import UTC, datetime, timedelta
from decimal import Decimal
import random

from krakenbot.config.settings import get_settings
from krakenbot.core.database import DatabaseManager
from krakenbot.models.market_data import OHLCData


async def seed_ohlc_data(
    db_manager: DatabaseManager,
    pair: str,
    days: int,
    interval_minutes: int = 15,
) -> int:
    """Seed fake OHLC data for testing.

    Args:
        db_manager: Database manager instance.
        pair: Trading pair (e.g., "XBT/USDC").
        days: Number of days of data to generate.
        interval_minutes: Candle interval in minutes.

    Returns:
        Number of candles created.
    """
    print(f"Seeding {days} days of OHLC data for {pair}...")

    # Starting price around $100,000 for BTC
    base_price = 100000.0
    current_price = base_price

    # Calculate timestamps
    end_time = datetime.now(UTC)
    start_time = end_time - timedelta(days=days)
    interval_delta = timedelta(minutes=interval_minutes)

    candles = []
    current_time = start_time

    while current_time < end_time:
        # Simulate price movement (random walk with slight upward bias)
        price_change_pct = random.uniform(-0.02, 0.025)  # -2% to +2.5%
        current_price *= (1 + price_change_pct)

        # Generate OHLC
        open_price = current_price
        high_price = current_price * (1 + abs(random.uniform(0, 0.01)))
        low_price = current_price * (1 - abs(random.uniform(0, 0.01)))
        close_price = current_price * (1 + random.uniform(-0.005, 0.005))

        # Update current price for next candle
        current_price = close_price

        # Random volume
        volume = Decimal(str(random.uniform(0.1, 5.0)))

        # Create candle
        candle = OHLCData(
            timestamp=current_time,
            pair=pair,
            interval=interval_minutes,
            open=Decimal(str(round(open_price, 2))),
            high=Decimal(str(round(high_price, 2))),
            low=Decimal(str(round(low_price, 2))),
            close=Decimal(str(round(close_price, 2))),
            volume=volume,
            vwap=Decimal(str(round((open_price + high_price + low_price + close_price) / 4, 2))),
        )
        candles.append(candle)

        current_time += interval_delta

    # Bulk insert
    async with db_manager.session() as session:
        session.add_all(candles)
        await session.commit()

    print(f"✅ Created {len(candles)} OHLC candles")
    print(f"   Period: {start_time.strftime('%Y-%m-%d %H:%M')} to {end_time.strftime('%Y-%m-%d %H:%M')}")
    print(f"   Price range: ${min(c.low for c in candles):.2f} - ${max(c.high for c in candles):.2f}")

    return len(candles)


async def main() -> None:
    """CLI entry point."""
    parser = argparse.ArgumentParser(description="Seed test OHLC data")
    parser.add_argument(
        "--pair",
        type=str,
        default="XBT/USDC",
        help="Trading pair (default: XBT/USDC)",
    )
    parser.add_argument(
        "--days",
        type=int,
        default=30,
        help="Number of days of data (default: 30)",
    )
    parser.add_argument(
        "--interval",
        type=int,
        default=15,
        help="Candle interval in minutes (default: 15)",
    )

    args = parser.parse_args()

    # Initialize database
    settings = get_settings()
    db_manager = DatabaseManager()
    await db_manager.init_db(settings)

    try:
        await seed_ohlc_data(
            db_manager,
            pair=args.pair,
            days=args.days,
            interval_minutes=args.interval,
        )
    finally:
        await db_manager.close_db()


if __name__ == "__main__":
    asyncio.run(main())
