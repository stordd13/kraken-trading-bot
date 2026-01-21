#!/usr/bin/env python3
"""Check KrakenBot status and database state.

This script provides a quick way to check:
- Database connectivity
- OHLC data statistics
- Recent trades
- Bot state

Usage:
    python scripts/status.py

Via SSH tunnel (from local machine):
    ssh -L 5432:localhost:5432 user@server -N &
    python scripts/status.py
"""

from __future__ import annotations

import asyncio
import os
import sys
from datetime import datetime, timedelta, timezone
from decimal import Decimal

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from krakenbot.models.market_data import OHLCData
from krakenbot.models.trades import BotState, Trade


async def get_status() -> None:
    """Check database and display bot status."""
    # Get database URL from environment or use default
    database_url = os.environ.get(
        "DATABASE_URL",
        "postgresql+asyncpg://krakenbot:bruno@localhost:5432/krakenbot",
    )

    print("=" * 60)
    print("🤖 KRAKENBOT STATUS CHECK")
    print("=" * 60)
    print(f"📅 Time: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')} UTC")
    print(f"🔗 Database: {database_url.split('@')[1] if '@' in database_url else database_url}")
    print()

    try:
        # Create engine
        engine = create_async_engine(database_url, echo=False)
        async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

        async with async_session() as session:
            # 1. Check database connectivity
            print("📊 DATABASE CONNECTION")
            print("-" * 40)
            result = await session.execute(text("SELECT version()"))
            version = result.scalar()
            print(f"✅ Connected: {version[:50]}...")
            print()

            # 2. OHLC Data Statistics
            print("📈 OHLC DATA STATISTICS")
            print("-" * 40)

            # Count total candles
            result = await session.execute(
                select(func.count()).select_from(OHLCData)
            )
            total_candles = result.scalar() or 0
            print(f"Total candles: {total_candles:,}")

            # Count by interval
            result = await session.execute(
                select(OHLCData.interval, func.count())
                .group_by(OHLCData.interval)
                .order_by(OHLCData.interval)
            )
            intervals = result.all()
            for interval, count in intervals:
                print(f"  • {interval}min: {count:,} candles")

            # Get latest candle
            result = await session.execute(
                select(OHLCData)
                .order_by(OHLCData.timestamp.desc())
                .limit(1)
            )
            latest_candle = result.scalar()
            if latest_candle:
                age_minutes = (
                    datetime.now(timezone.utc) - latest_candle.timestamp.replace(tzinfo=timezone.utc)
                ).total_seconds() / 60
                print(f"\nLatest candle:")
                print(f"  • Pair: {latest_candle.pair}")
                print(f"  • Time: {latest_candle.timestamp}")
                print(f"  • Close: {latest_candle.close}")
                print(f"  • Age: {age_minutes:.1f} minutes")
            print()

            # 3. Bot State
            print("🤖 BOT STATE")
            print("-" * 40)

            result = await session.execute(select(BotState))
            bot_states = result.scalars().all()

            if not bot_states:
                print("No bot state found (bot may not have run yet)")
            else:
                for state in bot_states:
                    status_emoji = {
                        "running": "🟢",
                        "stopped": "🔴",
                        "error": "❌",
                        "paused": "⏸️",
                        "initializing": "🔄",
                    }.get(state.status.value if hasattr(state.status, "value") else str(state.status), "❓")

                    print(f"{status_emoji} Bot: {state.bot_id}")
                    print(f"  • Strategy: {state.strategy}")
                    print(f"  • Status: {state.status.value if hasattr(state.status, 'value') else state.status}")
                    print(f"  • Position: {state.position_size}")
                    print(f"  • Entry price: {state.entry_price or 'N/A'}")
                    print(f"  • Daily P&L: {state.daily_pnl}")
                    print(f"  • Total P&L: {state.total_pnl}")
                    print(f"  • Last trade: {state.last_trade_at or 'Never'}")
                    if state.error_message:
                        print(f"  • Error: {state.error_message}")
            print()

            # 4. Recent Trades
            print("💰 RECENT TRADES (Last 10)")
            print("-" * 40)

            result = await session.execute(
                select(Trade)
                .order_by(Trade.timestamp.desc())
                .limit(10)
            )
            trades = result.scalars().all()

            if not trades:
                print("No trades found")
            else:
                for trade in trades:
                    side_emoji = "🟢" if trade.side.value == "buy" else "🔴"
                    pnl_str = f" (P&L: {trade.pnl})" if trade.pnl else ""
                    print(
                        f"{side_emoji} {trade.timestamp.strftime('%Y-%m-%d %H:%M')} "
                        f"{trade.side.value.upper()} {trade.amount} @ {trade.price}{pnl_str}"
                    )
            print()

            # 5. Last 24h summary
            print("📊 LAST 24H SUMMARY")
            print("-" * 40)

            yesterday = datetime.now(timezone.utc) - timedelta(days=1)
            result = await session.execute(
                select(func.count(), func.sum(Trade.pnl))
                .where(Trade.timestamp >= yesterday)
            )
            row = result.one()
            trade_count = row[0] or 0
            total_pnl = row[1] or Decimal("0")

            print(f"Trades executed: {trade_count}")
            print(f"Total P&L: {total_pnl}")

            # Count candles in last 24h
            result = await session.execute(
                select(func.count())
                .where(OHLCData.timestamp >= yesterday)
            )
            candles_24h = result.scalar() or 0
            print(f"Candles received: {candles_24h}")

        await engine.dispose()

        print()
        print("=" * 60)
        print("✅ Status check complete")
        print("=" * 60)

    except Exception as e:
        print(f"❌ Error: {e}")
        print()
        print("Possible issues:")
        print("  1. Database not running (docker compose up -d)")
        print("  2. SSH tunnel not active (ssh -L 5432:localhost:5432 user@server -N)")
        print("  3. Wrong DATABASE_URL environment variable")
        sys.exit(1)


def main() -> None:
    """Entry point."""
    asyncio.run(get_status())


if __name__ == "__main__":
    main()
