"""Backtesting framework for KrakenBot strategies.

This module provides tools to test trading strategies on historical data
and calculate performance metrics.

Usage:
    python -m scripts.backtest --strategy threshold --days 7 --pair XBT/USDC
"""

import argparse
import asyncio
from dataclasses import dataclass, field
from datetime import datetime, timedelta, UTC
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from krakenbot.config.settings import Settings, get_settings
from krakenbot.core.database import DatabaseManager
from krakenbot.core.event_bus import EventBus
from krakenbot.core.logger import get_logger
from krakenbot.models.base import TradeSide
from krakenbot.models.market_data import OHLCData
from krakenbot.strategies.base import SignalType, TradingSignal
from krakenbot.strategies.threshold import ThresholdStrategy


@dataclass
class BacktestTrade:
    """Record of a simulated trade during backtesting."""

    timestamp: datetime
    side: TradeSide
    price: Decimal
    amount_usdc: Decimal
    amount_crypto: Decimal
    fee: Decimal
    pnl: Decimal | None = None  # Profit/loss (set when closing position)


@dataclass
class BacktestMetrics:
    """Performance metrics from a backtest run."""

    # Basic stats
    total_trades: int = 0
    winning_trades: int = 0
    losing_trades: int = 0

    # P&L metrics
    total_pnl: Decimal = Decimal("0")
    total_fees: Decimal = Decimal("0")
    net_pnl: Decimal = Decimal("0")  # total_pnl - total_fees

    # Performance ratios
    win_rate: float = 0.0  # winning_trades / total_trades
    average_win: Decimal = Decimal("0")
    average_loss: Decimal = Decimal("0")
    profit_factor: float = 0.0  # total_wins / total_losses

    # Risk metrics
    max_drawdown: Decimal = Decimal("0")  # Largest peak-to-trough decline
    max_drawdown_pct: float = 0.0
    sharpe_ratio: float = 0.0  # Risk-adjusted return

    # Position tracking
    starting_balance: Decimal = Decimal("1000")
    ending_balance: Decimal = Decimal("1000")
    total_return_pct: float = 0.0

    # Time metrics
    start_time: datetime | None = None
    end_time: datetime | None = None
    duration_days: float = 0.0

    # Trade history
    trades: list[BacktestTrade] = field(default_factory=list)


class BacktestEngine:
    """Engine for running strategy backtests on historical data.

    The engine replays historical OHLC data from the database and simulates
    strategy execution without modifying the live bot state.
    """

    def __init__(
        self,
        settings: Settings,
        db_manager: DatabaseManager,
        strategy_name: str = "threshold",
    ):
        """Initialize backtest engine.

        Args:
            settings: Application settings
            db_manager: Database manager for historical data
            strategy_name: Name of strategy to backtest
        """
        self.settings = settings
        self.db_manager = db_manager
        self.strategy_name = strategy_name
        self.logger = get_logger().bind(component="backtest")

        # Simulation state
        self.usdc_balance = Decimal("1000")  # Starting balance
        self.crypto_balance = Decimal("0")
        self.entry_price: Decimal | None = None
        self.in_position = False

        # Metrics tracking
        self.metrics = BacktestMetrics(starting_balance=self.usdc_balance)
        self.equity_curve: list[tuple[datetime, Decimal]] = []

        # Strategy instance (will be created during run)
        self.event_bus = EventBus()
        self.strategy: ThresholdStrategy | None = None

    async def load_historical_data(
        self,
        pair: str,
        start_time: datetime,
        end_time: datetime,
    ) -> list[OHLCData]:
        """Load OHLC data from database for backtesting period.

        Args:
            pair: Trading pair (e.g., "XBT/USDC")
            start_time: Start of backtest period
            end_time: End of backtest period

        Returns:
            List of OHLC candles sorted by timestamp
        """
        self.logger.info(
            "loading_historical_data",
            pair=pair,
            start=start_time.isoformat(),
            end=end_time.isoformat(),
        )

        async with self.db_manager.session() as session:
            stmt = (
                select(OHLCData)
                .where(OHLCData.pair == pair)
                .where(OHLCData.timestamp >= start_time)
                .where(OHLCData.timestamp <= end_time)
                .order_by(OHLCData.timestamp.asc())
            )
            result = await session.execute(stmt)
            candles = list(result.scalars().all())

        self.logger.info("historical_data_loaded", candle_count=len(candles))
        return candles

    async def execute_signal(self, signal: TradingSignal, current_price: Decimal) -> None:
        """Execute a trading signal in the simulation.

        Args:
            signal: Trading signal from strategy
            current_price: Current market price
        """
        if signal.signal_type == SignalType.HOLD:
            return

        fee_pct = Decimal("0.004")  # 0.4% taker fee on Kraken

        if signal.signal_type == SignalType.BUY and not self.in_position:
            # Buy with available USDC
            order_amount = min(
                self.usdc_balance,
                self.settings.trading.default_order_amount_eur,  # Reuse EUR setting
            )

            if order_amount < 1:  # Minimum order
                return

            fee = order_amount * fee_pct
            amount_after_fee = order_amount - fee
            crypto_bought = amount_after_fee / current_price

            # Update balances
            self.usdc_balance -= order_amount
            self.crypto_balance += crypto_bought
            self.entry_price = current_price
            self.in_position = True

            # Record trade
            trade = BacktestTrade(
                timestamp=signal.timestamp,
                side=TradeSide.BUY,
                price=current_price,
                amount_usdc=order_amount,
                amount_crypto=crypto_bought,
                fee=fee,
            )
            self.metrics.trades.append(trade)
            self.metrics.total_fees += fee

            self.logger.debug(
                "backtest_buy",
                price=float(current_price),
                amount_usdc=float(order_amount),
                crypto=float(crypto_bought),
            )

        elif signal.signal_type == SignalType.SELL and self.in_position:
            # Sell all crypto holdings
            proceeds = self.crypto_balance * current_price
            fee = proceeds * fee_pct
            amount_after_fee = proceeds - fee

            # Calculate P&L
            cost_basis = self.entry_price * self.crypto_balance if self.entry_price else Decimal("0")
            pnl = amount_after_fee - cost_basis

            # Update balances
            self.usdc_balance += amount_after_fee
            crypto_sold = self.crypto_balance
            self.crypto_balance = Decimal("0")
            self.in_position = False

            # Record trade
            trade = BacktestTrade(
                timestamp=signal.timestamp,
                side=TradeSide.SELL,
                price=current_price,
                amount_usdc=amount_after_fee,
                amount_crypto=crypto_sold,
                fee=fee,
                pnl=pnl,
            )
            self.metrics.trades.append(trade)
            self.metrics.total_fees += fee
            self.metrics.total_pnl += pnl

            # Track win/loss
            if pnl > 0:
                self.metrics.winning_trades += 1
            else:
                self.metrics.losing_trades += 1

            self.logger.debug(
                "backtest_sell",
                price=float(current_price),
                crypto=float(crypto_sold),
                pnl=float(pnl),
            )

            self.entry_price = None

    def calculate_final_metrics(self) -> None:
        """Calculate final performance metrics after backtest completes."""
        self.metrics.total_trades = len([t for t in self.metrics.trades if t.side == TradeSide.SELL])

        if self.metrics.total_trades > 0:
            self.metrics.win_rate = self.metrics.winning_trades / self.metrics.total_trades

        # Calculate average win/loss
        winning_pnls = [t.pnl for t in self.metrics.trades if t.pnl and t.pnl > 0]
        losing_pnls = [t.pnl for t in self.metrics.trades if t.pnl and t.pnl < 0]

        if winning_pnls:
            self.metrics.average_win = sum(winning_pnls, Decimal("0")) / len(winning_pnls)
        if losing_pnls:
            self.metrics.average_loss = sum(losing_pnls, Decimal("0")) / len(losing_pnls)

        # Profit factor
        total_wins = sum(winning_pnls, Decimal("0"))
        total_losses = abs(sum(losing_pnls, Decimal("0")))
        if total_losses > 0:
            self.metrics.profit_factor = float(total_wins / total_losses)

        # Net P&L
        self.metrics.net_pnl = self.metrics.total_pnl - self.metrics.total_fees

        # Final balance
        self.metrics.ending_balance = self.usdc_balance
        if self.in_position and self.entry_price:
            # Add unrealized position value
            self.metrics.ending_balance += self.crypto_balance * self.metrics.trades[-1].price

        # Total return
        if self.metrics.starting_balance > 0:
            self.metrics.total_return_pct = float(
                ((self.metrics.ending_balance - self.metrics.starting_balance)
                 / self.metrics.starting_balance) * 100
            )

        # Max drawdown calculation
        peak = self.metrics.starting_balance
        max_dd = Decimal("0")

        for timestamp, equity in self.equity_curve:
            if equity > peak:
                peak = equity
            drawdown = peak - equity
            if drawdown > max_dd:
                max_dd = drawdown

        self.metrics.max_drawdown = max_dd
        if peak > 0:
            self.metrics.max_drawdown_pct = float((max_dd / peak) * 100)

        # Sharpe ratio (simplified: assumes daily returns)
        if len(self.equity_curve) > 1:
            returns = []
            for i in range(1, len(self.equity_curve)):
                prev_equity = self.equity_curve[i - 1][1]
                curr_equity = self.equity_curve[i][1]
                if prev_equity > 0:
                    ret = float((curr_equity - prev_equity) / prev_equity)
                    returns.append(ret)

            if returns:
                avg_return = sum(returns) / len(returns)
                variance = sum((r - avg_return) ** 2 for r in returns) / len(returns)
                std_dev = variance ** 0.5

                if std_dev > 0:
                    # Annualized Sharpe (assuming 365 days)
                    self.metrics.sharpe_ratio = (avg_return / std_dev) * (365 ** 0.5)

    async def run(
        self,
        pair: str,
        start_time: datetime,
        end_time: datetime,
    ) -> BacktestMetrics:
        """Run backtest for specified period.

        Args:
            pair: Trading pair to backtest
            start_time: Start of backtest period
            end_time: End of backtest period

        Returns:
            Performance metrics from the backtest
        """
        self.logger.info(
            "backtest_starting",
            pair=pair,
            strategy=self.strategy_name,
            start=start_time.isoformat(),
            end=end_time.isoformat(),
        )

        self.metrics.start_time = start_time
        self.metrics.end_time = end_time
        self.metrics.duration_days = (end_time - start_time).total_seconds() / 86400

        # Load historical data
        candles = await self.load_historical_data(pair, start_time, end_time)

        if len(candles) < 10:
            self.logger.error(
                "insufficient_data",
                candle_count=len(candles),
                minimum_required=10,
            )
            raise ValueError(f"Insufficient data: only {len(candles)} candles available")

        # Initialize strategy
        if self.strategy_name == "threshold":
            self.strategy = ThresholdStrategy(
                event_bus=self.event_bus,
                db_manager=self.db_manager,
                settings=self.settings,
            )
        else:
            raise ValueError(f"Unknown strategy: {self.strategy_name}")

        # Replay historical data
        for i, candle in enumerate(candles):
            # Feed OHLC to strategy
            ohlc_data = {
                "pair": candle.pair,
                "timestamp": candle.timestamp,
                "open": candle.open,
                "high": candle.high,
                "low": candle.low,
                "close": candle.close,
                "volume": candle.volume,
            }

            await self.strategy.on_ohlc(ohlc_data)

            # Generate signal
            signal = await self.strategy.generate_signal()

            # Execute signal
            if signal:
                await self.execute_signal(signal, candle.close)

            # Track equity curve
            current_equity = self.usdc_balance
            if self.in_position and self.entry_price:
                current_equity += self.crypto_balance * candle.close
            self.equity_curve.append((candle.timestamp, current_equity))

            # Log progress every 100 candles
            if (i + 1) % 100 == 0:
                self.logger.info(
                    "backtest_progress",
                    processed=i + 1,
                    total=len(candles),
                    pct=round((i + 1) / len(candles) * 100, 1),
                )

        # Calculate final metrics
        self.calculate_final_metrics()

        self.logger.info(
            "backtest_completed",
            total_trades=self.metrics.total_trades,
            net_pnl=float(self.metrics.net_pnl),
            win_rate=round(self.metrics.win_rate * 100, 2),
            total_return_pct=round(self.metrics.total_return_pct, 2),
        )

        return self.metrics

    def print_report(self) -> None:
        """Print a formatted backtest report to console."""
        print("\n" + "=" * 80)
        print("BACKTEST REPORT".center(80))
        print("=" * 80)

        print(f"\n{'Strategy:':<30} {self.strategy_name}")
        print(f"{'Period:':<30} {self.metrics.start_time.date()} to {self.metrics.end_time.date()}")
        print(f"{'Duration:':<30} {self.metrics.duration_days:.1f} days")

        print("\n" + "-" * 80)
        print("PERFORMANCE SUMMARY")
        print("-" * 80)

        print(f"{'Starting Balance:':<30} {float(self.metrics.starting_balance):.2f} USDC")
        print(f"{'Ending Balance:':<30} {float(self.metrics.ending_balance):.2f} USDC")
        print(f"{'Total Return:':<30} {self.metrics.total_return_pct:+.2f}%")
        print(f"{'Net P&L:':<30} {float(self.metrics.net_pnl):+.2f} USDC")
        print(f"{'Total Fees Paid:':<30} {float(self.metrics.total_fees):.2f} USDC")

        print("\n" + "-" * 80)
        print("TRADE STATISTICS")
        print("-" * 80)

        print(f"{'Total Trades:':<30} {self.metrics.total_trades}")
        print(f"{'Winning Trades:':<30} {self.metrics.winning_trades}")
        print(f"{'Losing Trades:':<30} {self.metrics.losing_trades}")
        print(f"{'Win Rate:':<30} {self.metrics.win_rate * 100:.2f}%")
        print(f"{'Average Win:':<30} {float(self.metrics.average_win):+.2f} USDC")
        print(f"{'Average Loss:':<30} {float(self.metrics.average_loss):+.2f} USDC")
        print(f"{'Profit Factor:':<30} {self.metrics.profit_factor:.2f}")

        print("\n" + "-" * 80)
        print("RISK METRICS")
        print("-" * 80)

        print(f"{'Max Drawdown:':<30} {float(self.metrics.max_drawdown):.2f} USDC")
        print(f"{'Max Drawdown %:':<30} {self.metrics.max_drawdown_pct:.2f}%")
        print(f"{'Sharpe Ratio:':<30} {self.metrics.sharpe_ratio:.2f}")

        print("\n" + "=" * 80 + "\n")


async def main() -> None:
    """CLI entry point for backtesting."""
    parser = argparse.ArgumentParser(description="Backtest KrakenBot trading strategies")
    parser.add_argument(
        "--strategy",
        type=str,
        default="threshold",
        help="Strategy name to backtest (default: threshold)",
    )
    parser.add_argument(
        "--pair",
        type=str,
        default="XBT/USDC",
        help="Trading pair (default: XBT/USDC)",
    )
    parser.add_argument(
        "--days",
        type=int,
        default=7,
        help="Number of days to backtest (default: 7)",
    )
    parser.add_argument(
        "--end-date",
        type=str,
        default=None,
        help="End date (YYYY-MM-DD, default: now)",
    )

    args = parser.parse_args()

    # Parse dates
    if args.end_date:
        end_time = datetime.fromisoformat(args.end_date).replace(tzinfo=UTC)
    else:
        end_time = datetime.now(UTC)

    start_time = end_time - timedelta(days=args.days)

    # Initialize components
    settings = get_settings()
    db_manager = DatabaseManager(settings.database.url)
    await db_manager.connect()

    try:
        # Run backtest
        engine = BacktestEngine(settings, db_manager, strategy_name=args.strategy)
        metrics = await engine.run(args.pair, start_time, end_time)

        # Print report
        engine.print_report()

    finally:
        await db_manager.disconnect()


if __name__ == "__main__":
    asyncio.run(main())
