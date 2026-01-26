#!/usr/bin/env python3
"""Grid search for optimal trading strategy parameters.

This script tests multiple combinations of strategy parameters
and reports the best performing configurations using the existing
BacktestEngine.

Usage:
    python scripts/backtest_grid.py --pair XBT/USDC --days 5
"""

import argparse
import asyncio
import sys
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path

from dotenv import load_dotenv

# Load .env from project root
load_dotenv(Path(__file__).parent.parent / ".env")

# Add scripts dir to path for importing backtest
sys.path.insert(0, str(Path(__file__).parent))

from backtest import BacktestEngine, BacktestMetrics

from krakenbot.config.settings import Settings, get_settings, reload_settings
from krakenbot.core.database import DatabaseManager
from krakenbot.core.logger import get_logger

logger = get_logger(__name__)


@dataclass
class GridSearchResult:
    """Result from a single parameter combination."""

    buy_threshold: float
    sell_threshold: float
    lookback: int
    total_trades: int
    win_rate: float
    net_pnl: float
    total_return_pct: float
    max_drawdown_pct: float
    sharpe_ratio: float


async def run_backtest_with_params(
    db_manager: DatabaseManager,
    pair: str,
    start_time: datetime,
    end_time: datetime,
    buy_threshold: float,
    sell_threshold: float,
    lookback: int,
) -> GridSearchResult:
    """Run a single backtest with specific parameters."""

    # Get fresh settings and override parameters
    settings = reload_settings()

    # Override strategy parameters
    settings.strategy.buy_threshold_pct = buy_threshold
    settings.strategy.sell_threshold_pct = sell_threshold
    settings.strategy.lookback_periods = lookback

    # Create and run backtest
    engine = BacktestEngine(settings, db_manager, strategy_name="threshold_rolling")

    try:
        metrics = await engine.run(pair, start_time, end_time)
    except Exception as e:
        # Return empty result on error
        return GridSearchResult(
            buy_threshold=buy_threshold,
            sell_threshold=sell_threshold,
            lookback=lookback,
            total_trades=0,
            win_rate=0.0,
            net_pnl=0.0,
            total_return_pct=0.0,
            max_drawdown_pct=0.0,
            sharpe_ratio=0.0,
        )

    return GridSearchResult(
        buy_threshold=buy_threshold,
        sell_threshold=sell_threshold,
        lookback=lookback,
        total_trades=metrics.total_trades,
        win_rate=metrics.win_rate,
        net_pnl=float(metrics.net_pnl),
        total_return_pct=float(metrics.total_return_pct),
        max_drawdown_pct=float(metrics.max_drawdown_pct),
        sharpe_ratio=metrics.sharpe_ratio,
    )


async def main() -> None:
    """Run grid search for optimal parameters."""
    parser = argparse.ArgumentParser(description="Grid search for strategy parameters")
    parser.add_argument("--pair", type=str, default="XBT/USDC", help="Trading pair")
    parser.add_argument("--days", type=int, default=5, help="Number of days to backtest")
    parser.add_argument("--end-date", type=str, default=None, help="End date (YYYY-MM-DD)")
    parser.add_argument("--quick", action="store_true", help="Quick mode (fewer combinations)")
    args = parser.parse_args()

    # Parse dates
    if args.end_date:
        end_time = datetime.fromisoformat(args.end_date).replace(tzinfo=UTC)
    else:
        end_time = datetime.now(UTC)
    start_time = end_time - timedelta(days=args.days)

    # Initialize database
    settings = get_settings()
    db_manager = DatabaseManager()
    await db_manager.init_db(settings)

    # Define parameter grid
    if args.quick:
        buy_thresholds = [-0.5, -1.0, -2.0]
        sell_thresholds = [1.0, 2.0, 3.0]
        lookbacks = [20, 50]
    else:
        # Extended grid with long lookbacks (in 1-min candles)
        # 60=1h, 360=6h, 1440=1day, 4320=3days, 10080=7days
        buy_thresholds = [-0.5, -1.0, -1.5, -2.0, -2.5, -3.0]
        sell_thresholds = [1.0, 2.0, 3.0, 4.0, 5.0]
        lookbacks = [60, 360, 1440, 4320, 10080]

    total_combinations = len(buy_thresholds) * len(sell_thresholds) * len(lookbacks)

    print(f"\n{'='*80}")
    print(f"GRID SEARCH - {args.pair}")
    print(f"{'='*80}")
    print(f"Period: {start_time.date()} to {end_time.date()} ({args.days} days)")
    print(f"Testing {total_combinations} parameter combinations...")
    print(f"{'='*80}\n")

    results: list[GridSearchResult] = []
    completed = 0

    try:
        for buy_thresh in buy_thresholds:
            for sell_thresh in sell_thresholds:
                for lookback in lookbacks:
                    result = await run_backtest_with_params(
                        db_manager=db_manager,
                        pair=args.pair,
                        start_time=start_time,
                        end_time=end_time,
                        buy_threshold=buy_thresh,
                        sell_threshold=sell_thresh,
                        lookback=lookback,
                    )
                    results.append(result)
                    completed += 1

                    # Progress indicator
                    if completed % 5 == 0 or completed == total_combinations:
                        pct = completed / total_combinations * 100
                        print(f"Progress: {completed}/{total_combinations} ({pct:.0f}%)")

        # Sort by net P&L
        results.sort(key=lambda r: r.net_pnl, reverse=True)

        # Print top 10 results
        print(f"\n{'='*80}")
        print("TOP 10 PARAMETER COMBINATIONS (by Net P&L)")
        print(f"{'='*80}")
        print(f"{'Buy%':>6} {'Sell%':>6} {'Look':>5} {'Trades':>7} {'WinRate':>8} {'P&L':>10} {'Return%':>8} {'MaxDD%':>7} {'Sharpe':>7}")
        print("-" * 80)

        for r in results[:10]:
            print(f"{r.buy_threshold:>6.2f} {r.sell_threshold:>6.2f} {r.lookback:>5} {r.total_trades:>7} {r.win_rate:>7.1f}% {r.net_pnl:>+10.2f} {r.total_return_pct:>+7.2f}% {r.max_drawdown_pct:>6.2f}% {r.sharpe_ratio:>7.2f}")

        # Print worst 5 for reference
        print(f"\n{'='*80}")
        print("BOTTOM 5 PARAMETER COMBINATIONS")
        print(f"{'='*80}")
        print(f"{'Buy%':>6} {'Sell%':>6} {'Look':>5} {'Trades':>7} {'WinRate':>8} {'P&L':>10} {'Return%':>8} {'MaxDD%':>7} {'Sharpe':>7}")
        print("-" * 80)

        for r in results[-5:]:
            print(f"{r.buy_threshold:>6.2f} {r.sell_threshold:>6.2f} {r.lookback:>5} {r.total_trades:>7} {r.win_rate:>7.1f}% {r.net_pnl:>+10.2f} {r.total_return_pct:>+7.2f}% {r.max_drawdown_pct:>6.2f}% {r.sharpe_ratio:>7.2f}")

        # Summary statistics
        profitable = [r for r in results if r.net_pnl > 0]
        with_trades = [r for r in results if r.total_trades > 0]

        print(f"\n{'='*80}")
        print("SUMMARY")
        print(f"{'='*80}")
        print(f"Combinations with trades: {len(with_trades)}/{len(results)} ({len(with_trades)/len(results)*100:.1f}%)")
        print(f"Profitable combinations: {len(profitable)}/{len(results)} ({len(profitable)/len(results)*100:.1f}%)")

        if results[0].net_pnl != 0:
            best = results[0]
            print(f"\nBest configuration:")
            print(f"  Buy threshold: {best.buy_threshold}%")
            print(f"  Sell threshold: {best.sell_threshold}%")
            print(f"  Lookback: {best.lookback} periods")
            print(f"  Trades: {best.total_trades}")
            print(f"  Win rate: {best.win_rate:.1f}%")
            print(f"  Net P&L: {best.net_pnl:+.2f} USDC")
            print(f"  Return: {best.total_return_pct:+.2f}%")
            print(f"  Sharpe: {best.sharpe_ratio:.2f}")

        if profitable:
            avg_pnl = sum(r.net_pnl for r in profitable) / len(profitable)
            print(f"\nAvg P&L (profitable only): {avg_pnl:+.2f} USDC")

        print(f"{'='*80}\n")

    finally:
        await db_manager.close_db()


if __name__ == "__main__":
    asyncio.run(main())
