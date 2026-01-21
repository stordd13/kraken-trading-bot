"""Analyze paper trading performance.

This script fetches trades from the database and calculates key metrics
to evaluate the paper trading strategy performance.

Usage:
    # Via SSH tunnel (from local machine)
    ssh -L 5432:localhost:5432 bruno@<IP> -N &
    poetry run python scripts/analyze_paper_trading.py

    # With specific date range
    poetry run python scripts/analyze_paper_trading.py --days 7
    poetry run python scripts/analyze_paper_trading.py --start 2026-01-15 --end 2026-01-21
"""

import argparse
import asyncio
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from sqlalchemy import select

from krakenbot.config.settings import get_settings
from krakenbot.core.database import DatabaseManager
from krakenbot.models.base import TradeSide
from krakenbot.models.trades import Trade


@dataclass
class PaperTradingMetrics:
    """Metrics from paper trading analysis."""

    # Period
    start_date: datetime | None = None
    end_date: datetime | None = None
    duration_days: float = 0.0

    # Trade counts
    total_trades: int = 0
    buy_trades: int = 0
    sell_trades: int = 0
    completed_round_trips: int = 0  # buy + sell pairs

    # P&L
    total_pnl: Decimal = Decimal("0")
    total_fees: Decimal = Decimal("0")
    net_pnl: Decimal = Decimal("0")
    winning_trades: int = 0
    losing_trades: int = 0
    win_rate: float = 0.0

    # Detailed P&L
    gross_profit: Decimal = Decimal("0")  # Sum of winning trades
    gross_loss: Decimal = Decimal("0")  # Sum of losing trades (absolute)
    average_win: Decimal = Decimal("0")
    average_loss: Decimal = Decimal("0")
    profit_factor: float = 0.0
    largest_win: Decimal = Decimal("0")
    largest_loss: Decimal = Decimal("0")

    # Per-trade stats
    average_trade_size_usdc: Decimal = Decimal("0")
    average_holding_time_minutes: float = 0.0

    # Individual trades for detailed analysis
    trades: list[dict] = field(default_factory=list)


async def analyze_paper_trading(
    db_manager: DatabaseManager,
    start_time: datetime | None = None,
    end_time: datetime | None = None,
    strategy_filter: str | None = None,
) -> PaperTradingMetrics:
    """Analyze paper trading performance from database.

    Args:
        db_manager: Database manager instance.
        start_time: Start of analysis period (optional).
        end_time: End of analysis period (optional).
        strategy_filter: Filter by strategy name (optional).

    Returns:
        PaperTradingMetrics with calculated statistics.
    """
    metrics = PaperTradingMetrics()

    async with db_manager.session() as session:
        # Build query
        stmt = select(Trade).order_by(Trade.timestamp.asc())

        # Apply filters
        if start_time:
            stmt = stmt.where(Trade.timestamp >= start_time)
        if end_time:
            stmt = stmt.where(Trade.timestamp <= end_time)
        if strategy_filter:
            stmt = stmt.where(Trade.strategy.ilike(f"%{strategy_filter}%"))
        else:
            # Exclude backtest trades by default
            stmt = stmt.where(~Trade.strategy.ilike("backtest_%"))

        result = await session.execute(stmt)
        trades = list(result.scalars().all())

    if not trades:
        print("No trades found for the specified period.")
        return metrics

    # Basic counts
    metrics.total_trades = len(trades)
    metrics.buy_trades = sum(1 for t in trades if t.side == TradeSide.BUY)
    metrics.sell_trades = sum(1 for t in trades if t.side == TradeSide.SELL)

    # Period
    metrics.start_date = trades[0].timestamp
    metrics.end_date = trades[-1].timestamp
    metrics.duration_days = (metrics.end_date - metrics.start_date).total_seconds() / 86400

    # Calculate P&L from sell trades (which have pnl field set)
    sell_trades_with_pnl = [t for t in trades if t.side == TradeSide.SELL and t.pnl is not None]
    metrics.completed_round_trips = len(sell_trades_with_pnl)

    winning_pnls = []
    losing_pnls = []

    for trade in sell_trades_with_pnl:
        if trade.pnl > 0:
            metrics.winning_trades += 1
            winning_pnls.append(trade.pnl)
        elif trade.pnl < 0:
            metrics.losing_trades += 1
            losing_pnls.append(trade.pnl)

    # P&L calculations
    metrics.total_pnl = sum((t.pnl for t in sell_trades_with_pnl), Decimal("0"))
    metrics.total_fees = sum((t.fee for t in trades), Decimal("0"))
    metrics.net_pnl = metrics.total_pnl  # Fees already included in pnl calculation

    # Win rate
    if metrics.completed_round_trips > 0:
        metrics.win_rate = metrics.winning_trades / metrics.completed_round_trips

    # Gross profit/loss
    metrics.gross_profit = sum(winning_pnls, Decimal("0"))
    metrics.gross_loss = abs(sum(losing_pnls, Decimal("0")))

    # Average win/loss
    if winning_pnls:
        metrics.average_win = metrics.gross_profit / len(winning_pnls)
        metrics.largest_win = max(winning_pnls)
    if losing_pnls:
        metrics.average_loss = abs(sum(losing_pnls, Decimal("0"))) / len(losing_pnls)
        metrics.largest_loss = min(losing_pnls)  # Most negative

    # Profit factor
    if metrics.gross_loss > 0:
        metrics.profit_factor = float(metrics.gross_profit / metrics.gross_loss)

    # Average trade size
    buy_trades_list = [t for t in trades if t.side == TradeSide.BUY]
    if buy_trades_list:
        total_value = sum((t.amount * t.price for t in buy_trades_list), Decimal("0"))
        metrics.average_trade_size_usdc = total_value / len(buy_trades_list)

    # Calculate holding times by matching buy/sell pairs
    holding_times = []
    buy_queue: list[Trade] = []

    for trade in trades:
        if trade.side == TradeSide.BUY:
            buy_queue.append(trade)
        elif trade.side == TradeSide.SELL and buy_queue:
            buy_trade = buy_queue.pop(0)  # FIFO matching
            holding_time = (trade.timestamp - buy_trade.timestamp).total_seconds() / 60
            holding_times.append(holding_time)

    if holding_times:
        metrics.average_holding_time_minutes = sum(holding_times) / len(holding_times)

    # Store individual trades for detailed view
    for trade in trades:
        metrics.trades.append(
            {
                "timestamp": trade.timestamp,
                "side": trade.side.value,
                "price": float(trade.price),
                "amount": float(trade.amount),
                "value": float(trade.amount * trade.price),
                "fee": float(trade.fee),
                "pnl": float(trade.pnl) if trade.pnl else None,
                "strategy": trade.strategy,
            }
        )

    return metrics


def print_report(metrics: PaperTradingMetrics) -> None:
    """Print formatted paper trading report."""
    print("\n" + "=" * 80)
    print("PAPER TRADING ANALYSIS REPORT".center(80))
    print("=" * 80)

    if metrics.start_date:
        print(f"\n{'Period:':<30} {metrics.start_date.date()} to {metrics.end_date.date()}")
        print(f"{'Duration:':<30} {metrics.duration_days:.1f} days")

    print("\n" + "-" * 80)
    print("TRADE SUMMARY")
    print("-" * 80)

    print(f"{'Total Trades:':<30} {metrics.total_trades}")
    print(f"{'  - Buy Orders:':<30} {metrics.buy_trades}")
    print(f"{'  - Sell Orders:':<30} {metrics.sell_trades}")
    print(f"{'Completed Round-Trips:':<30} {metrics.completed_round_trips}")

    print("\n" + "-" * 80)
    print("PERFORMANCE")
    print("-" * 80)

    print(f"{'Net P&L:':<30} {float(metrics.net_pnl):+.2f} USDC")
    print(f"{'Total Fees:':<30} {float(metrics.total_fees):.2f} USDC")
    print(f"{'Winning Trades:':<30} {metrics.winning_trades}")
    print(f"{'Losing Trades:':<30} {metrics.losing_trades}")
    print(f"{'Win Rate:':<30} {metrics.win_rate * 100:.1f}%")

    if metrics.profit_factor > 0:
        print(f"{'Profit Factor:':<30} {metrics.profit_factor:.2f}")

    print("\n" + "-" * 80)
    print("TRADE DETAILS")
    print("-" * 80)

    print(f"{'Average Win:':<30} {float(metrics.average_win):+.2f} USDC")
    print(f"{'Average Loss:':<30} {float(metrics.average_loss):-.2f} USDC")
    print(f"{'Largest Win:':<30} {float(metrics.largest_win):+.2f} USDC")
    print(f"{'Largest Loss:':<30} {float(metrics.largest_loss):-.2f} USDC")
    print(f"{'Avg Trade Size:':<30} {float(metrics.average_trade_size_usdc):.2f} USDC")

    # Holding time
    if metrics.average_holding_time_minutes > 0:
        hours = int(metrics.average_holding_time_minutes // 60)
        minutes = int(metrics.average_holding_time_minutes % 60)
        if hours > 0:
            time_str = f"{hours}h {minutes}min"
        else:
            time_str = f"{minutes}min"
        print(f"{'Avg Holding Time:':<30} {time_str}")

    # Recent trades
    if metrics.trades:
        print("\n" + "-" * 80)
        print("RECENT TRADES (last 10)")
        print("-" * 80)
        print(f"{'Timestamp':<22} {'Side':<6} {'Price':>12} {'Value':>10} {'P&L':>10}")
        print("-" * 80)

        for trade in metrics.trades[-10:]:
            pnl_str = f"{trade['pnl']:+.2f}" if trade["pnl"] else "-"
            print(
                f"{trade['timestamp'].strftime('%Y-%m-%d %H:%M'):<22} "
                f"{trade['side']:<6} "
                f"{trade['price']:>12.2f} "
                f"{trade['value']:>10.2f} "
                f"{pnl_str:>10}"
            )

    print("\n" + "=" * 80 + "\n")


async def main() -> None:
    """CLI entry point for paper trading analysis."""
    parser = argparse.ArgumentParser(description="Analyze paper trading performance")
    parser.add_argument(
        "--days",
        type=int,
        default=None,
        help="Number of days to analyze (default: all)",
    )
    parser.add_argument(
        "--start",
        type=str,
        default=None,
        help="Start date (YYYY-MM-DD)",
    )
    parser.add_argument(
        "--end",
        type=str,
        default=None,
        help="End date (YYYY-MM-DD)",
    )
    parser.add_argument(
        "--strategy",
        type=str,
        default=None,
        help="Filter by strategy name",
    )

    args = parser.parse_args()

    # Parse dates
    end_time = None
    start_time = None

    if args.end:
        end_time = datetime.fromisoformat(args.end).replace(tzinfo=UTC)
    if args.start:
        start_time = datetime.fromisoformat(args.start).replace(tzinfo=UTC)
    elif args.days:
        end_time = end_time or datetime.now(UTC)
        start_time = end_time - timedelta(days=args.days)

    # Initialize database
    settings = get_settings()
    db_manager = DatabaseManager()
    await db_manager.init_db(settings)

    try:
        # Run analysis
        metrics = await analyze_paper_trading(
            db_manager,
            start_time=start_time,
            end_time=end_time,
            strategy_filter=args.strategy,
        )

        # Print report
        print_report(metrics)

    finally:
        await db_manager.close_db()


if __name__ == "__main__":
    asyncio.run(main())
