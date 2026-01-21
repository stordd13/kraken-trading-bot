"""Test all components to verify everything works.

This script tests:
1. Database connection
2. Data seeding
3. Backtest execution
4. Dashboard setup

Usage:
    python -m scripts.test_all
"""

import asyncio
from pathlib import Path
import sys

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from krakenbot.config.settings import get_settings
from krakenbot.core.database import DatabaseManager


async def test_database_connection():
    """Test 1: Database connection."""
    print("=" * 80)
    print("TEST 1: Database Connection")
    print("=" * 80)

    try:
        settings = get_settings()
        db_manager = DatabaseManager()
        await db_manager.init_db(settings)
        print("✅ Database connection successful")
        await db_manager.close_db()
        return True
    except Exception as e:
        print(f"❌ Database connection failed: {e}")
        return False


async def test_data_exists():
    """Test 2: Check if OHLC data exists."""
    print("\n" + "=" * 80)
    print("TEST 2: OHLC Data Check")
    print("=" * 80)

    try:
        from sqlalchemy import func, select

        from krakenbot.models.market_data import OHLCData

        settings = get_settings()
        db_manager = DatabaseManager()
        await db_manager.init_db(settings)

        async with db_manager.session() as session:
            stmt = select(func.count()).select_from(OHLCData)
            result = await session.execute(stmt)
            count = result.scalar()

            print(f"OHLC candles in database: {count}")

            if count > 0:
                print("✅ OHLC data exists")
                await db_manager.close_db()
                return True
            else:
                print("⚠️  No OHLC data found. Run: python -m scripts.seed_test_data --days 30")
                await db_manager.close_db()
                return False
    except Exception as e:
        print(f"❌ Data check failed: {e}")
        return False


async def test_backtest_runs_table():
    """Test 3: Check if backtest_runs table exists."""
    print("\n" + "=" * 80)
    print("TEST 3: Backtest Runs Table")
    print("=" * 80)

    try:
        from sqlalchemy import func, select

        from krakenbot.models.trades import BacktestRun

        settings = get_settings()
        db_manager = DatabaseManager()
        await db_manager.init_db(settings)

        async with db_manager.session() as session:
            stmt = select(func.count()).select_from(BacktestRun)
            result = await session.execute(stmt)
            count = result.scalar()

            print(f"Backtest runs in database: {count}")

            if count > 0:
                print("✅ Backtest runs table exists and has data")
            else:
                print("⚠️  No backtest runs found. Run: python -m scripts.backtest --pair XBT/USDC --days 7 --save")

            await db_manager.close_db()
            return True
    except Exception as e:
        print(f"❌ Backtest runs table check failed: {e}")
        print("   Run migration: alembic upgrade head")
        return False


async def test_bot_state_table():
    """Test 4: Check if bot_state table exists."""
    print("\n" + "=" * 80)
    print("TEST 4: Bot State Table")
    print("=" * 80)

    try:
        from sqlalchemy import func, select

        from krakenbot.models.trades import BotState

        settings = get_settings()
        db_manager = DatabaseManager()
        await db_manager.init_db(settings)

        async with db_manager.session() as session:
            stmt = select(func.count()).select_from(BotState)
            result = await session.execute(stmt)
            count = result.scalar()

            print(f"Bot states in database: {count}")

            if count > 0:
                print("✅ Bot state table exists and has data")
            else:
                print("⚠️  No bot state found (normal if bot hasn't run yet)")

            await db_manager.close_db()
            return True
    except Exception as e:
        print(f"❌ Bot state table check failed: {e}")
        return False


def test_dash_installed():
    """Test 5: Check if Dash is installed (for dashboard)."""
    print("\n" + "=" * 80)
    print("TEST 5: Dash Installation")
    print("=" * 80)

    try:
        import dash
        import plotly
        print(f"✅ Dash {dash.__version__} installed")
        print(f"✅ Plotly {plotly.__version__} installed")
        return True
    except ImportError as e:
        print(f"❌ Missing package: {e}")
        print("   Run: poetry add dash dash-bootstrap-components plotly")
        return False


def test_docker_running():
    """Test 6: Check if Docker database is running."""
    print("\n" + "=" * 80)
    print("TEST 6: Docker Database")
    print("=" * 80)

    try:
        import subprocess
        result = subprocess.run(
            ["docker", "compose", "ps", "--filter", "name=krakenbot-db", "--format", "json"],
            capture_output=True,
            text=True,
            timeout=5
        )

        if result.returncode == 0 and result.stdout.strip():
            print("✅ Docker database is running")
            return True
        else:
            print("⚠️  Docker database not running")
            print("   Run: docker compose up -d db")
            return False
    except Exception as e:
        print(f"⚠️  Could not check Docker: {e}")
        return False


async def main():
    """Run all tests."""
    print("\n" + "🔍 TESTING ALL KRAKENBOT COMPONENTS" + "\n")

    results = {
        "Docker Database": test_docker_running(),
        "Database Connection": await test_database_connection(),
        "OHLC Data": await test_data_exists(),
        "Backtest Runs Table": await test_backtest_runs_table(),
        "Bot State Table": await test_bot_state_table(),
        "Dash Installation": test_dash_installed(),
    }

    # Summary
    print("\n" + "=" * 80)
    print("SUMMARY")
    print("=" * 80)

    passed = sum(1 for v in results.values() if v)
    total = len(results)

    for name, result in results.items():
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"{status:12} {name}")

    print("\n" + f"Results: {passed}/{total} tests passed")

    if passed == total:
        print("\n🎉 All tests passed! You can now:")
        print("   1. Run backtest: python -m scripts.backtest --pair XBT/USDC --days 7 --save")
        print("   2. Start dashboard: python scripts/dashboard.py")
    else:
        print("\n⚠️  Some tests failed. Follow the suggestions above to fix them.")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
