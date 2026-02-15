"""Backtesting framework for KrakenBot strategies.

This module provides tools to test trading strategies on historical data
and calculate performance metrics.

Usage:
    python -m scripts.backtest --strategy threshold --days 7 --pair XBT/USDC
"""

import argparse
import asyncio
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from sqlalchemy import select

# Load .env from project root
load_dotenv(Path(__file__).parent.parent / ".env")

from krakenbot.config.settings import Settings, get_settings
from krakenbot.core.database import DatabaseManager
from krakenbot.core.event_bus import EventBus
from krakenbot.core.logger import get_logger
from krakenbot.models.base import TradeSide
from krakenbot.models.market_data import OHLCData
from krakenbot.models.trades import BacktestRun, Trade, TradeStatus
from krakenbot.strategies.base import SignalType, TradingSignal


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
    regime: str | None = None  # Market regime at trade time


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
    sortino_ratio: float = 0.0  # Risk-adjusted return (downside volatility only)

    # Position tracking
    starting_balance: Decimal = Decimal("1000")
    ending_balance: Decimal = Decimal("1000")
    total_return_pct: float = 0.0

    # Time metrics
    start_time: datetime | None = None
    end_time: datetime | None = None
    duration_days: float = 0.0
    average_holding_time_minutes: float = 0.0  # Average time positions are held

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
        candle_interval: int = 1,
    ):
        """Initialize backtest engine.

        Args:
            settings: Application settings
            db_manager: Database manager for historical data
            strategy_name: Name of strategy to backtest
            candle_interval: Candle interval in minutes (default: 1)
        """
        self.settings = settings
        self.db_manager = db_manager
        self.strategy_name = strategy_name
        self.candle_interval = candle_interval
        self.logger = get_logger().bind(component="backtest")

        # Simulation state
        self.usdc_balance = Decimal("1000")  # Starting balance
        self.crypto_balance = Decimal("0")
        self.entry_price: Decimal | None = None
        self.in_position = False

        # Metrics tracking
        self.metrics = BacktestMetrics(starting_balance=self.usdc_balance)
        self.equity_curve: list[tuple[datetime, Decimal]] = []
        self._current_regime: str | None = None
        self._regime_stats: dict[str, dict] = {}

        # Strategy instance (will be created during run)
        self.event_bus = EventBus()
        self.strategy = None  # Will be created during run

    def _load_strategy_params(self, strategy_name: str) -> dict[str, Any] | None:
        """Load strategy params from strategies.yaml via settings."""
        if not self.settings.multi_strategy.enabled:
            return None
        for s in self.settings.multi_strategy.strategies:
            if s.name == strategy_name:
                return s.params
        return None

    async def _load_candles_for_interval(
        self,
        pair: str,
        interval: int,
        start_time: datetime,
        end_time: datetime,
    ) -> list[OHLCData]:
        """Load OHLC candles for a specific interval.

        Args:
            pair: Trading pair.
            interval: Candle interval in minutes (5, 15, 60).
            start_time: Start of period.
            end_time: End of period.

        Returns:
            List of OHLC candles sorted by timestamp.
        """
        async with self.db_manager.session() as session:
            stmt = (
                select(OHLCData)
                .where(OHLCData.pair == pair)
                .where(OHLCData.interval == interval)
                .where(OHLCData.timestamp >= start_time)
                .where(OHLCData.timestamp <= end_time)
                .order_by(OHLCData.timestamp.asc())
            )
            result = await session.execute(stmt)
            return list(result.scalars().all())

    async def _build_replay_sequence(
        self,
        pair: str,
        start_time: datetime,
        end_time: datetime,
        candles_trading: list[OHLCData],
    ) -> list[tuple[OHLCData, int, bool]]:
        """Build interleaved replay sequence with multi-timeframe warmup.

        Loads 15m and 1h candles (with warmup period before start_time),
        merges them with the trading candles, and sorts chronologically.
        Higher timeframes are processed first on timestamp ties so the
        analyzer is updated before the trigger timeframe generates signals.

        Args:
            pair: Trading pair.
            start_time: Start of backtest trading period.
            end_time: End of backtest period.
            candles_trading: Already-loaded trading candles for the period.

        Returns:
            List of (candle, interval, is_tradeable) tuples.
        """
        ci = self.candle_interval  # Trading interval (e.g., 5, 1, 15)

        # Warmup periods before start_time
        warmup_1h = start_time - timedelta(days=3)  # ~72 candles (> 50 warmup)
        warmup_15m = start_time - timedelta(hours=10)  # ~40 candles (> 20 warmup)
        warmup_trading = start_time - timedelta(hours=3)  # ~36 candles (> 20 warmup)

        # Load higher timeframe data (full range: warmup + backtest period)
        candles_1h = await self._load_candles_for_interval(pair, 60, warmup_1h, end_time)
        candles_15m = await self._load_candles_for_interval(pair, 15, warmup_15m, end_time)
        candles_warmup = await self._load_candles_for_interval(pair, ci, warmup_trading, start_time)

        self.logger.info(
            "mtf_data_loaded",
            trading_interval=ci,
            candles_1h=len(candles_1h),
            candles_15m=len(candles_15m),
            candles_warmup=len(candles_warmup),
            candles_trading=len(candles_trading),
        )

        # Build sequence
        sequence: list[tuple[OHLCData, int, bool]] = []

        # Trading interval warmup (before start_time) - not tradeable
        for c in candles_warmup:
            sequence.append((c, ci, False))

        # 1h candles - never tradeable (feed analyzer + capitulation hourly tracking)
        for c in candles_1h:
            sequence.append((c, 60, False))

        # 15m candles - never tradeable (feed analyzer)
        for c in candles_15m:
            sequence.append((c, 15, False))

        # Trading candles
        for c in candles_trading:
            sequence.append((c, ci, True))

        # Sort: timestamp ASC, then higher timeframes first (60 > 15 > trading)
        interval_order = {60: 0, 15: 1, ci: 2}
        sequence.sort(key=lambda x: (x[0].timestamp, interval_order.get(x[1], 3)))

        return sequence

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
            interval=self.candle_interval,
            start=start_time.isoformat(),
            end=end_time.isoformat(),
        )

        async with self.db_manager.session() as session:
            stmt = (
                select(OHLCData)
                .where(OHLCData.pair == pair)
                .where(OHLCData.interval == self.candle_interval)
                .where(OHLCData.timestamp >= start_time)
                .where(OHLCData.timestamp <= end_time)
                .order_by(OHLCData.timestamp.asc())
            )
            result = await session.execute(stmt)
            candles = list(result.scalars().all())

        self.logger.info(
            "historical_data_loaded", candle_count=len(candles), interval=self.candle_interval
        )
        return candles

    async def execute_signal(self, signal: TradingSignal, current_price: Decimal) -> None:
        """Execute a trading signal in the simulation.

        Args:
            signal: Trading signal from strategy
            current_price: Current market price
        """
        if signal.signal_type == SignalType.HOLD:
            return

        # Route margin (short) signals to separate handler
        if signal.metadata and signal.metadata.get("mode") == "margin":
            await self._execute_short_signal(signal, current_price)
            return

        # Realistic trading costs
        fee_pct = Decimal("0.0026")  # 0.26% maker fee on Kraken (tier 1)
        spread_pct = Decimal("0.0002")  # 0.02% typical BTC/USDC spread
        slippage_pct = Decimal("0.0001")  # 0.01% slippage (small orders)

        # Handle multi-position strategies differently
        is_multi = self.strategy_name in [
            "threshold_multi",
            "threshold_rolling",
            "adaptive",
            "capitulation",
            "bear_short",
        ]

        if signal.signal_type == SignalType.BUY and (is_multi or not self.in_position):
            # Buy with available USDC
            order_amount = min(
                self.usdc_balance,
                Decimal(str(self.settings.trading.default_order_amount_eur)),  # Convert to Decimal
            )

            self.logger.debug(
                "backtest_buy_attempt",
                usdc_balance=float(self.usdc_balance),
                order_amount=float(order_amount),
                min_order=1.0,
            )

            if order_amount < Decimal("1"):  # Minimum order
                self.logger.warning(
                    "backtest_buy_skipped_min_order", order_amount=float(order_amount)
                )
                return

            # Apply spread + slippage to get realistic execution price
            # When buying, we pay the ASK price (higher than mid)
            execution_price = current_price * (Decimal("1") + spread_pct + slippage_pct)

            fee = order_amount * fee_pct
            amount_after_fee = order_amount - fee
            crypto_bought = amount_after_fee / execution_price

            # Update balances
            self.usdc_balance -= order_amount
            self.crypto_balance += crypto_bought
            self.entry_price = execution_price  # Store actual execution price
            self.in_position = True

            # Update strategy position state for next signal generation
            if is_multi:
                # For multi-position, notify strategy of new position
                if self.strategy_name in ["threshold_rolling", "adaptive"]:
                    # These strategies need reference_price
                    reference_price = Decimal(
                        str(signal.metadata.get("reference_price", current_price))
                    )
                    position_id = self.strategy.add_position(
                        entry_price=current_price,  # Use mid-price for strategy
                        amount_usdc=order_amount,
                        reference_price=reference_price,
                        entry_time=signal.timestamp,
                    )
                else:
                    # threshold_multi, capitulation don't need reference_price
                    position_id = self.strategy.add_position(
                        entry_price=current_price,  # Use mid-price for strategy
                        amount_usdc=order_amount,
                        entry_time=signal.timestamp,
                    )
                self.logger.debug("multi_position_opened", position_id=position_id)
            else:
                # Single position mode
                # Use current_price (not execution_price) so strategy sees mid-market price
                self.strategy.set_position_state(has_position=True, entry_price=current_price)

            # Record trade
            trade = BacktestTrade(
                timestamp=signal.timestamp,
                side=TradeSide.BUY,
                price=execution_price,  # Actual execution price with spread+slippage
                amount_usdc=order_amount,
                amount_crypto=crypto_bought,
                fee=fee,
                regime=signal.metadata.get("regime") if signal.metadata else self._current_regime,
            )
            self.metrics.trades.append(trade)
            self.metrics.total_fees += fee

            self.logger.debug(
                "backtest_buy",
                price=float(current_price),
                amount_usdc=float(order_amount),
                crypto=float(crypto_bought),
            )

        elif signal.signal_type == SignalType.SELL and (is_multi or self.in_position):
            # Apply spread + slippage to get realistic execution price
            # When selling, we receive the BID price (lower than mid)
            execution_price = current_price * (Decimal("1") - spread_pct - slippage_pct)

            # For multi-position strategies, get position details first
            if is_multi:
                position_id = signal.metadata.get("position_id") if signal.metadata else None
                if position_id:
                    # Close position and get its details
                    closed_pos = self.strategy.close_position(position_id)
                    if closed_pos:
                        # Calculate crypto amount from position's USDC amount and entry price
                        crypto_amount = closed_pos.amount_usdc / closed_pos.entry_price
                    else:
                        # Position not found, skip this sell
                        self.logger.warning("position_not_found_for_sell", position_id=position_id)
                        return
                else:
                    # No position_id in metadata
                    self.logger.warning("no_position_id_in_sell_signal")
                    return

                # Calculate proceeds from this specific position
                proceeds = crypto_amount * execution_price
                fee = proceeds * fee_pct
                amount_after_fee = proceeds - fee

                # Calculate P&L for this position
                cost_basis = closed_pos.amount_usdc  # Original USDC spent
                pnl = amount_after_fee - cost_basis

                # Update balances
                self.usdc_balance += amount_after_fee
                self.crypto_balance -= crypto_amount  # Decrement crypto balance
                crypto_sold = crypto_amount

                # Check if all positions are closed
                if not self.strategy.open_positions:
                    self.in_position = False

                self.logger.debug("multi_position_closed", position_id=position_id)
            else:
                # Single position mode - use global tracking
                proceeds = self.crypto_balance * execution_price
                fee = proceeds * fee_pct
                amount_after_fee = proceeds - fee

                # Calculate P&L
                cost_basis = (
                    self.entry_price * self.crypto_balance if self.entry_price else Decimal("0")
                )
                pnl = amount_after_fee - cost_basis

                # Update balances
                self.usdc_balance += amount_after_fee
                crypto_sold = self.crypto_balance
                self.crypto_balance = Decimal("0")
                self.in_position = False

                # Single position mode
                self.strategy.set_position_state(has_position=False, entry_price=None)

            # Record trade
            trade = BacktestTrade(
                timestamp=signal.timestamp,
                side=TradeSide.SELL,
                price=execution_price,  # Actual execution price with spread+slippage
                amount_usdc=amount_after_fee,
                amount_crypto=crypto_sold,
                fee=fee,
                pnl=pnl,
                regime=self._current_regime,
            )
            self.metrics.trades.append(trade)
            self.metrics.total_fees += fee
            self.metrics.total_pnl += pnl

            # Track win/loss
            if pnl > 0:
                self.metrics.winning_trades += 1
            else:
                self.metrics.losing_trades += 1

            # Extract holding time from signal metadata if available
            holding_time_minutes = (
                signal.metadata.get("holding_time_minutes") if signal.metadata else None
            )

            log_data = {
                "price": float(current_price),
                "crypto": float(crypto_sold),
                "pnl": float(pnl),
            }

            if holding_time_minutes is not None:
                log_data["holding_time_minutes"] = holding_time_minutes

            self.logger.debug("backtest_sell", **log_data)

            self.entry_price = None

    async def _execute_short_signal(self, signal: TradingSignal, current_price: Decimal) -> None:
        """Execute a margin short signal in the simulation.

        SELL with is_short_open: open a short (lock margin collateral).
        BUY with is_short_close: close a short (release margin, calculate PnL).

        Rollover fee: 0.01% per 4h of position value.
        """
        fee_pct = Decimal("0.0026")  # 0.26% taker fee
        spread_pct = Decimal("0.0002")
        slippage_pct = Decimal("0.0001")

        if signal.metadata.get("is_short_open") and signal.signal_type == SignalType.SELL:
            # Open short: lock margin collateral
            leverage = signal.metadata.get("leverage", 2)
            order_amount = min(
                self.usdc_balance,
                Decimal(str(self.settings.trading.default_order_amount_eur)),
            )

            if order_amount < Decimal("1"):
                return

            # Execution: selling at bid (lower)
            execution_price = current_price * (Decimal("1") - spread_pct - slippage_pct)
            fee = order_amount * fee_pct

            # Lock margin collateral (order_amount / leverage)
            collateral = order_amount / Decimal(str(leverage))
            self.usdc_balance -= collateral

            # Notify strategy
            position_id = self.strategy.add_position(
                entry_price=current_price,
                amount_usdc=order_amount,
                entry_time=signal.timestamp,
            )

            self.in_position = True

            trade = BacktestTrade(
                timestamp=signal.timestamp,
                side=TradeSide.SELL,
                price=execution_price,
                amount_usdc=order_amount,
                amount_crypto=order_amount / execution_price,
                fee=fee,
                regime=signal.metadata.get("regime") if signal.metadata else self._current_regime,
            )
            self.metrics.trades.append(trade)
            self.metrics.total_fees += fee

            self.logger.debug(
                "backtest_short_open",
                price=float(current_price),
                amount_usdc=float(order_amount),
                collateral=float(collateral),
                position_id=position_id,
            )

        elif signal.metadata.get("is_short_close") and signal.signal_type == SignalType.BUY:
            # Close short: release collateral, calculate PnL
            position_id = signal.metadata.get("position_id")
            if not position_id:
                return

            closed_pos = self.strategy.close_position(position_id)
            if not closed_pos:
                self.logger.warning("short_position_not_found", position_id=position_id)
                return

            # Execution: buying at ask (higher)
            execution_price = current_price * (Decimal("1") + spread_pct + slippage_pct)
            crypto_amount = closed_pos.amount_usdc / closed_pos.entry_price
            close_value = crypto_amount * execution_price
            fee = close_value * fee_pct

            # Short PnL: (entry - exit) * amount
            gross_pnl = (closed_pos.entry_price - execution_price) * crypto_amount

            # Rollover fee: 0.01% per 4h of position value
            holding_hours = (signal.timestamp - closed_pos.entry_time).total_seconds() / 3600
            rollover_periods = holding_hours / 4
            position_value = closed_pos.amount_usdc
            rollover_fee = position_value * Decimal("0.0001") * Decimal(str(rollover_periods))

            pnl = gross_pnl - fee - rollover_fee

            # Release collateral and apply PnL
            leverage = signal.metadata.get("leverage", 2)
            collateral = closed_pos.amount_usdc / Decimal(str(leverage))
            self.usdc_balance += collateral + pnl

            if not self.strategy.open_positions:
                self.in_position = False

            trade = BacktestTrade(
                timestamp=signal.timestamp,
                side=TradeSide.BUY,
                price=execution_price,
                amount_usdc=close_value,
                amount_crypto=crypto_amount,
                fee=fee + rollover_fee,
                pnl=pnl,
                regime=self._current_regime,
            )
            self.metrics.trades.append(trade)
            self.metrics.total_fees += fee + rollover_fee
            self.metrics.total_pnl += pnl

            if pnl > 0:
                self.metrics.winning_trades += 1
            else:
                self.metrics.losing_trades += 1

            self.logger.debug(
                "backtest_short_close",
                price=float(current_price),
                pnl=float(pnl),
                rollover_fee=float(rollover_fee),
                holding_hours=round(holding_hours, 1),
            )

    def calculate_final_metrics(self) -> None:
        """Calculate final performance metrics after backtest completes."""
        self.metrics.total_trades = len(
            [t for t in self.metrics.trades if t.side == TradeSide.SELL]
        )

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
        if self.crypto_balance > 0 and self.metrics.trades:
            # Add unrealized position value at last known price
            self.metrics.ending_balance += self.crypto_balance * self.metrics.trades[-1].price

        # Total return
        if self.metrics.starting_balance > 0:
            self.metrics.total_return_pct = float(
                (
                    (self.metrics.ending_balance - self.metrics.starting_balance)
                    / self.metrics.starting_balance
                )
                * 100
            )

        # Max drawdown calculation
        peak = self.metrics.starting_balance
        max_dd = Decimal("0")

        for _timestamp, equity in self.equity_curve:
            if equity > peak:
                peak = equity
            drawdown = peak - equity
            if drawdown > max_dd:
                max_dd = drawdown

        self.metrics.max_drawdown = max_dd
        if peak > 0:
            self.metrics.max_drawdown_pct = float((max_dd / peak) * 100)

        # Calculate average holding time (for completed trades with timestamps)
        buy_trades = {t.timestamp: t for t in self.metrics.trades if t.side == TradeSide.BUY}
        sell_trades = [t for t in self.metrics.trades if t.side == TradeSide.SELL]

        holding_times = []
        for sell_trade in sell_trades:
            # Find the corresponding buy trade (match by closest timestamp before sell)
            matching_buys = [t for t in buy_trades.values() if t.timestamp < sell_trade.timestamp]
            if matching_buys:
                buy_trade = max(matching_buys, key=lambda x: x.timestamp)
                holding_time = (sell_trade.timestamp - buy_trade.timestamp).total_seconds() / 60
                holding_times.append(holding_time)

        if holding_times:
            self.metrics.average_holding_time_minutes = sum(holding_times) / len(holding_times)

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
                std_dev = variance**0.5

                if std_dev > 0:
                    # Annualized Sharpe (assuming 365 days)
                    self.metrics.sharpe_ratio = (avg_return / std_dev) * (365**0.5)

                # Sortino ratio: uses only downside volatility
                negative_returns = [r for r in returns if r < 0]
                if negative_returns:
                    downside_variance = sum(r**2 for r in negative_returns) / len(returns)
                    downside_std = downside_variance**0.5
                    if downside_std > 0:
                        # Annualized Sortino (assuming 365 days)
                        self.metrics.sortino_ratio = (avg_return / downside_std) * (365**0.5)

        # Regime breakdown: aggregate P&L per market regime
        regime_stats: dict[str, dict] = {}
        for trade in self.metrics.trades:
            r = trade.regime or "unknown"
            if r not in regime_stats:
                regime_stats[r] = {
                    "trades": 0,
                    "pnl": Decimal("0"),
                    "wins": 0,
                    "losses": 0,
                }
            if trade.pnl is not None:
                regime_stats[r]["trades"] += 1
                regime_stats[r]["pnl"] += trade.pnl
                if trade.pnl > 0:
                    regime_stats[r]["wins"] += 1
                else:
                    regime_stats[r]["losses"] += 1
        self._regime_stats = regime_stats

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
        # Override settings pair with backtest pair
        self.settings.trading.pair = pair

        if self.strategy_name == "threshold":
            from krakenbot.strategies.threshold import ThresholdStrategy

            self.strategy = ThresholdStrategy(
                event_bus=self.event_bus,
                db_manager=self.db_manager,
                settings=self.settings,
            )
        elif self.strategy_name == "threshold_multi":
            from krakenbot.strategies.threshold_multi import ThresholdMultiStrategy

            self.strategy = ThresholdMultiStrategy(
                event_bus=self.event_bus,
                db_manager=self.db_manager,
                settings=self.settings,
            )
        elif self.strategy_name == "threshold_rolling":
            from krakenbot.strategies.threshold_rolling import ThresholdRollingStrategy

            self.strategy = ThresholdRollingStrategy(
                event_bus=self.event_bus,
                db_manager=self.db_manager,
                settings=self.settings,
            )
        elif self.strategy_name == "technical_indicator":
            from krakenbot.strategies.technical_indicator import TechnicalIndicatorStrategy

            self.strategy = TechnicalIndicatorStrategy(
                event_bus=self.event_bus,
                db_manager=self.db_manager,
                settings=self.settings,
            )
        elif self.strategy_name == "adaptive":
            from krakenbot.indicators.multi_timeframe import MultiTimeframeAnalyzer
            from krakenbot.strategies.adaptive import AdaptiveStrategy

            analyzer = MultiTimeframeAnalyzer()
            strategy_params = self._load_strategy_params("adaptive")
            self.strategy = AdaptiveStrategy(
                settings=self.settings,
                event_bus=self.event_bus,
                db_manager=self.db_manager,
                analyzer=analyzer,
                strategy_params=strategy_params,
            )
        elif self.strategy_name == "capitulation":
            from krakenbot.indicators.multi_timeframe import MultiTimeframeAnalyzer
            from krakenbot.strategies.capitulation import CapitulationStrategy

            analyzer = MultiTimeframeAnalyzer()
            strategy_params = self._load_strategy_params("capitulation")
            self.strategy = CapitulationStrategy(
                settings=self.settings,
                event_bus=self.event_bus,
                db_manager=self.db_manager,
                analyzer=analyzer,
                strategy_params=strategy_params,
            )
        elif self.strategy_name == "bear_short":
            from krakenbot.indicators.multi_timeframe import MultiTimeframeAnalyzer
            from krakenbot.strategies.bear_short import BearShortStrategy

            analyzer = MultiTimeframeAnalyzer()
            strategy_params = self._load_strategy_params("bear_short")
            self.strategy = BearShortStrategy(
                settings=self.settings,
                event_bus=self.event_bus,
                db_manager=self.db_manager,
                analyzer=analyzer,
                strategy_params=strategy_params,
            )
        else:
            raise ValueError(
                f"Unknown strategy: {self.strategy_name}. "
                f"Available: threshold, threshold_multi, threshold_rolling, "
                f"technical_indicator, adaptive, capitulation, bear_short"
            )

        # CRITICAL: Skip DB sync in backtest mode for all strategies
        self.strategy._skip_db_sync = True

        # Build replay sequence (with MTF warmup for adaptive/capitulation)
        needs_mtf = self.strategy_name in ["adaptive", "capitulation", "bear_short"]
        if needs_mtf:
            replay_sequence = await self._build_replay_sequence(pair, start_time, end_time, candles)
        else:
            replay_sequence = [(c, self.candle_interval, True) for c in candles]

        tradeable_total = sum(1 for _, _, t in replay_sequence if t)

        # Replay historical data
        tradeable_idx = 0
        for candle, interval, is_tradeable in replay_sequence:
            # Feed OHLC to strategy (all timeframes)
            ohlc_data = {
                "pair": candle.pair,
                "timestamp": candle.timestamp,
                "open": candle.open,
                "high": candle.high,
                "low": candle.low,
                "close": candle.close,
                "volume": candle.volume,
                "interval": interval,
                "is_complete": True,
            }

            await self.strategy.on_ohlc(ohlc_data)

            # Only trade on tradeable 5m candles (skip warmup + higher TFs)
            if not is_tradeable:
                continue

            tradeable_idx += 1

            # Simulate tick with closing price for strategy
            tick_data = {
                "pair": candle.pair,
                "timestamp": candle.timestamp,
                "price": candle.close,
                "volume": candle.volume,
                "side": "buy",  # Dummy side for backtest
            }
            await self.strategy.on_tick(tick_data)

            # Generate signal
            signal = await self.strategy.generate_signal()

            # Track current regime from analyzer
            analyzer = getattr(self.strategy, "analyzer", None)
            if analyzer:
                last_analysis = getattr(analyzer, "_last_analysis", None)
                if last_analysis:
                    self._current_regime = last_analysis.regime.value

            # DEBUG: Log all BUY/SELL signals
            if signal and signal.signal_type.value in ["buy", "sell"]:
                self.logger.info(
                    "backtest_signal",
                    timestamp=candle.timestamp,
                    signal=signal.signal_type.value,
                    reason=signal.reason,
                    price=float(candle.close),
                )

            # Execute signal
            if signal:
                await self.execute_signal(signal, candle.close)

            # Track equity curve
            current_equity = self.usdc_balance
            if self.crypto_balance > 0:
                current_equity += self.crypto_balance * candle.close
            self.equity_curve.append((candle.timestamp, current_equity))

            # Log progress every 100 tradeable candles
            if tradeable_idx % 100 == 0:
                self.logger.info(
                    "backtest_progress",
                    processed=tradeable_idx,
                    total=tradeable_total,
                    pct=round(tradeable_idx / tradeable_total * 100, 1),
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

        # Display average holding time if available
        if self.metrics.average_holding_time_minutes > 0:
            hours = int(self.metrics.average_holding_time_minutes // 60)
            minutes = int(self.metrics.average_holding_time_minutes % 60)
            if hours > 0:
                time_str = f"{hours}h {minutes}min"
            else:
                time_str = f"{minutes}min"
            print(
                f"{'Avg Holding Time:':<30} {time_str} ({self.metrics.average_holding_time_minutes:.1f} min)"
            )

        print("\n" + "-" * 80)
        print("RISK METRICS")
        print("-" * 80)

        print(f"{'Max Drawdown:':<30} {float(self.metrics.max_drawdown):.2f} USDC")
        print(f"{'Max Drawdown %:':<30} {self.metrics.max_drawdown_pct:.2f}%")
        print(f"{'Sharpe Ratio:':<30} {self.metrics.sharpe_ratio:.2f}")
        print(f"{'Sortino Ratio:':<30} {self.metrics.sortino_ratio:.2f}")

        # Regime breakdown
        if self._regime_stats:
            print("\n" + "-" * 80)
            print("REGIME BREAKDOWN")
            print("-" * 80)
            print(f"  {'Regime':<16} {'Trades':>7} {'Win Rate':>10} {'Net P&L':>14}")
            print(f"  {'-' * 16} {'-' * 7} {'-' * 10} {'-' * 14}")

            # Display in canonical order
            regime_order = ["strong_bull", "bull", "neutral", "bear", "strong_bear", "unknown"]
            for regime in regime_order:
                if regime not in self._regime_stats:
                    continue
                stats = self._regime_stats[regime]
                trades = stats["trades"]
                if trades > 0:
                    win_rate = stats["wins"] / trades * 100
                    pnl = float(stats["pnl"])
                    print(
                        f"  {regime.upper():<16} {trades:>7} {win_rate:>9.1f}% {pnl:>+13.2f} USDC"
                    )
                else:
                    print(f"  {regime.upper():<16} {trades:>7} {'N/A':>10} {'0.00':>13} USDC")

        print("\n" + "=" * 80 + "\n")

    async def save_to_database(
        self,
        pair: str,
        run_name: str | None = None,
    ) -> BacktestRun:
        """Save backtest results to database for dashboard visualization.

        Args:
            pair: Trading pair that was backtested.
            run_name: Optional human-readable name. If not provided, generates one.

        Returns:
            The saved BacktestRun instance.
        """
        # Generate run name if not provided
        if run_name is None:
            date_str = self.metrics.start_time.strftime("%Y-%m-%d")
            run_name = f"{self.strategy_name}_{pair}_{date_str}_{self.metrics.duration_days:.0f}d"

        # Create BacktestRun instance
        backtest_run = BacktestRun(
            run_name=run_name,
            strategy=self.strategy_name,
            pair=pair,
            start_time=self.metrics.start_time,
            end_time=self.metrics.end_time,
            starting_balance=self.metrics.starting_balance,
            ending_balance=self.metrics.ending_balance,
            total_trades=self.metrics.total_trades,
            winning_trades=self.metrics.winning_trades,
            losing_trades=self.metrics.losing_trades,
            win_rate=Decimal(str(self.metrics.win_rate)),
            total_pnl=self.metrics.total_pnl,
            total_fees=self.metrics.total_fees,
            net_pnl=self.metrics.net_pnl,
            total_return_pct=Decimal(str(self.metrics.total_return_pct)),
            max_drawdown=self.metrics.max_drawdown,
            max_drawdown_pct=Decimal(str(self.metrics.max_drawdown_pct)),
            sharpe_ratio=Decimal(str(self.metrics.sharpe_ratio)),
            sortino_ratio=Decimal(str(self.metrics.sortino_ratio)),
            profit_factor=Decimal(str(self.metrics.profit_factor)),
            average_win=self.metrics.average_win,
            average_loss=self.metrics.average_loss,
        )

        # Save to database
        async with self.db_manager.session() as session:
            session.add(backtest_run)
            await session.commit()
            await session.refresh(backtest_run)

            self.logger.info(
                "backtest_saved_to_db",
                backtest_id=str(backtest_run.id),
                run_name=run_name,
            )

        return backtest_run

    async def save_trades_to_database(
        self,
        backtest_run_id: str,
        pair: str,
    ) -> None:
        """Save backtest trades to database (optional, for detailed analysis).

        Args:
            backtest_run_id: ID of the backtest run (for filtering).
            pair: Trading pair.
        """
        async with self.db_manager.session() as session:
            for trade in self.metrics.trades:
                db_trade = Trade(
                    timestamp=trade.timestamp,
                    pair=pair,
                    side=trade.side,
                    amount=trade.amount_crypto,
                    price=trade.price,
                    fee=trade.fee,
                    fee_currency="USDC",
                    strategy=f"backtest_{backtest_run_id}",  # Tag as backtest trade
                    pnl=trade.pnl,
                    status=TradeStatus.FILLED,
                    notes=f"Backtest trade from run {backtest_run_id}",
                )
                session.add(db_trade)

            await session.commit()

            self.logger.info(
                "backtest_trades_saved",
                backtest_id=backtest_run_id,
                trade_count=len(self.metrics.trades),
            )


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
    parser.add_argument(
        "--save",
        action="store_true",
        help="Save backtest results to database (for dashboard visualization)",
    )
    parser.add_argument(
        "--name",
        type=str,
        default=None,
        help="Custom name for this backtest run",
    )
    parser.add_argument(
        "--interval",
        type=int,
        default=1,
        help="Candle interval in minutes (default: 1). Use 5 for more realistic trading.",
    )
    parser.add_argument(
        "--cross-validate",
        action="store_true",
        help="Run temporal cross-validation (train 70%% / test 30%%)",
    )
    parser.add_argument(
        "--train-ratio",
        type=float,
        default=0.7,
        help="Train set ratio for cross-validation (default: 0.7 = 70%%)",
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
    db_manager = DatabaseManager()
    await db_manager.init_db(settings)

    try:
        if args.cross_validate:
            # Temporal cross-validation: train on first X%, test on remaining
            total_duration = end_time - start_time
            train_duration = total_duration * args.train_ratio
            split_time = start_time + train_duration

            print("\n" + "=" * 80)
            print("TEMPORAL CROSS-VALIDATION".center(80))
            print("=" * 80)
            print(f"\nTotal period: {start_time.date()} to {end_time.date()} ({args.days} days)")
            print(f"Train ratio: {args.train_ratio:.0%}")
            print(f"Split point: {split_time.date()}")
            print(
                f"Train: {start_time.date()} to {split_time.date()} ({int(train_duration.days)} days)"
            )
            print(
                f"Test:  {split_time.date()} to {end_time.date()} ({args.days - int(train_duration.days)} days)"
            )

            # Run TRAIN backtest
            print("\n" + "-" * 80)
            print("TRAIN SET".center(80))
            print("-" * 80)

            train_engine = BacktestEngine(
                settings,
                db_manager,
                strategy_name=args.strategy,
                candle_interval=args.interval,
            )
            train_metrics = await train_engine.run(args.pair, start_time, split_time)
            train_engine.print_report()

            # Run TEST backtest
            print("\n" + "-" * 80)
            print("TEST SET".center(80))
            print("-" * 80)

            test_engine = BacktestEngine(
                settings,
                db_manager,
                strategy_name=args.strategy,
                candle_interval=args.interval,
            )
            test_metrics = await test_engine.run(args.pair, split_time, end_time)
            test_engine.print_report()

            # Print comparison
            print("\n" + "=" * 80)
            print("TRAIN vs TEST COMPARISON".center(80))
            print("=" * 80)
            print(f"\n{'Metric':<25} {'Train':<15} {'Test':<15} {'Delta':<15}")
            print("-" * 70)

            # Total return
            train_ret = train_metrics.total_return_pct
            test_ret = test_metrics.total_return_pct
            print(
                f"{'Total Return %':<25} {train_ret:>+.2f}%{'':<8} {test_ret:>+.2f}%{'':<8} {test_ret - train_ret:>+.2f}%"
            )

            # Win rate
            train_wr = train_metrics.win_rate * 100
            test_wr = test_metrics.win_rate * 100
            print(
                f"{'Win Rate %':<25} {train_wr:>.2f}%{'':<9} {test_wr:>.2f}%{'':<9} {test_wr - train_wr:>+.2f}%"
            )

            # Profit factor
            print(
                f"{'Profit Factor':<25} {train_metrics.profit_factor:>.2f}{'':<12} {test_metrics.profit_factor:>.2f}{'':<12} {test_metrics.profit_factor - train_metrics.profit_factor:>+.2f}"
            )

            # Sharpe ratio
            print(
                f"{'Sharpe Ratio':<25} {train_metrics.sharpe_ratio:>.2f}{'':<12} {test_metrics.sharpe_ratio:>.2f}{'':<12} {test_metrics.sharpe_ratio - train_metrics.sharpe_ratio:>+.2f}"
            )

            # Sortino ratio
            print(
                f"{'Sortino Ratio':<25} {train_metrics.sortino_ratio:>.2f}{'':<12} {test_metrics.sortino_ratio:>.2f}{'':<12} {test_metrics.sortino_ratio - train_metrics.sortino_ratio:>+.2f}"
            )

            # Max drawdown
            train_dd = train_metrics.max_drawdown_pct
            test_dd = test_metrics.max_drawdown_pct
            print(
                f"{'Max Drawdown %':<25} {train_dd:>.2f}%{'':<9} {test_dd:>.2f}%{'':<9} {test_dd - train_dd:>+.2f}%"
            )

            # Trade count
            print(
                f"{'Total Trades':<25} {train_metrics.total_trades:<15} {test_metrics.total_trades:<15} {test_metrics.total_trades - train_metrics.total_trades:>+d}"
            )

            print("\n" + "=" * 80)

            # Overfitting warning
            if train_ret > 0 and test_ret < 0:
                print("\n⚠️  WARNING: Possible OVERFITTING detected!")
                print("    Strategy is profitable on train but loses on test data.")
                print("    Consider adjusting parameters or using a different strategy.\n")
            elif train_ret > test_ret * 2 and train_ret > 5:
                print("\n⚠️  CAUTION: Train performance is significantly better than test.")
                print("    This may indicate overfitting to historical patterns.\n")
            elif test_ret > train_ret:
                print("\n✅ Good sign: Test performance matches or exceeds train performance.\n")

        else:
            # Standard single backtest
            engine = BacktestEngine(
                settings,
                db_manager,
                strategy_name=args.strategy,
                candle_interval=args.interval,
            )
            await engine.run(args.pair, start_time, end_time)

            # Print report
            engine.print_report()

            # Save to database if requested
            if args.save:
                backtest_run = await engine.save_to_database(args.pair, run_name=args.name)
                print(f"\n✅ Backtest results saved to database with ID: {backtest_run.id}")
                print(f"   Run name: {backtest_run.run_name}")

                # Save individual trades for dashboard visualization
                await engine.save_trades_to_database(str(backtest_run.id), args.pair)
                print(f"   Trades saved: {len(engine.metrics.trades)}")
                print("   View in dashboard: python scripts/dashboard.py\n")

    finally:
        await db_manager.close_db()


if __name__ == "__main__":
    asyncio.run(main())
