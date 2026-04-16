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
from sqlalchemy import select, text

# Load .env from project root
load_dotenv(Path(__file__).parent.parent / ".env")

from krakenbot.config.settings import ExchangeFees, Settings, get_settings
from krakenbot.core.database import DatabaseManager
from krakenbot.core.event_bus import EventBus
from krakenbot.core.logger import get_logger
from krakenbot.models.base import TradeSide
from krakenbot.models.market_data import OHLCData
from krakenbot.models.trades import BacktestRun, Trade, TradeStatus
from krakenbot.strategies.base import SignalType, TradingSignal


def _backtest_chunk_days(interval: int) -> int:
    """Choose a conservative chunk size for hypertable reads."""
    if interval >= 10080:
        return 90
    if interval >= 1440:
        return 30
    if interval >= 240:
        return 14
    if interval >= 60:
        return 7
    return 3


async def _load_candles_chunked(
    db_manager: DatabaseManager,
    pair: str,
    interval: int,
    start_time: datetime,
    end_time: datetime,
    exchange: str = "kraken",
) -> list[OHLCData]:
    """Load OHLC candles in bounded windows to avoid Timescale lock exhaustion."""
    candles: list[OHLCData] = []
    chunk_days = _backtest_chunk_days(interval)
    window_start = start_time

    while window_start <= end_time:
        window_end = min(window_start + timedelta(days=chunk_days), end_time)

        async with db_manager.read_session() as session:
            # Timescale can choose a generic prepared plan that touches too many
            # chunks; forcing a custom plan keeps backtest reads bounded.
            await session.execute(text("SET LOCAL plan_cache_mode = force_custom_plan"))
            stmt = (
                select(OHLCData)
                .where(OHLCData.pair == pair)
                .where(OHLCData.interval == interval)
                .where(OHLCData.exchange == exchange)
                .where(OHLCData.timestamp >= window_start)
                .where(
                    OHLCData.timestamp <= window_end
                    if window_end == end_time
                    else OHLCData.timestamp < window_end
                )
                .order_by(OHLCData.timestamp.asc())
            )
            result = await session.execute(stmt)
            candles.extend(result.scalars().all())

        if window_end >= end_time:
            break
        window_start = window_end

    return candles


def _override_pair_in_params(
    params: dict[str, Any] | None,
    pair: str,
) -> dict[str, Any]:
    """Return a shallow-copied params dict with 'pair' forced to `pair`.

    Why: strategies.yaml may hardcode `pair: BTC/USDC` in router inner params.
    `BaseStrategy.effective_pair` reads strategy_params["pair"] before
    settings.trading.pair, so the YAML value shadows the backtest pair unless
    we override here. Always inject the pair (even when params is None or empty)
    so the strategy sees a single, consistent source of truth.
    """
    merged = dict(params or {})
    merged["pair"] = pair
    return merged


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
    calmar_ratio: float = 0.0  # Annualized return / max drawdown

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

    def to_dict(self) -> dict[str, float | int]:
        """Return metrics as a JSON-serializable dict for programmatic use."""
        return {
            "total_trades": self.total_trades,
            "winning_trades": self.winning_trades,
            "losing_trades": self.losing_trades,
            "win_rate": self.win_rate,
            "total_return_pct": self.total_return_pct,
            "sharpe_ratio": self.sharpe_ratio,
            "sortino_ratio": self.sortino_ratio,
            "max_drawdown_pct": self.max_drawdown_pct,
            "profit_factor": self.profit_factor,
            "calmar_ratio": self.calmar_ratio,
            "net_pnl": float(self.net_pnl),
            "total_fees": float(self.total_fees),
            "total_pnl": float(self.total_pnl),
            "starting_balance": float(self.starting_balance),
            "ending_balance": float(self.ending_balance),
            "duration_days": self.duration_days,
            "average_holding_time_minutes": self.average_holding_time_minutes,
        }


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
        exchange: str = "kraken",
        starting_capital: float = 1000.0,
    ):
        """Initialize backtest engine.

        Args:
            settings: Application settings
            db_manager: Database manager for historical data
            strategy_name: Name of strategy to backtest
            candle_interval: Candle interval in minutes (default: 1)
            exchange: Exchange data source to filter on
            starting_capital: Starting balance in USDC
        """
        self.settings = settings
        self.db_manager = db_manager
        self.strategy_name = strategy_name
        self.candle_interval = candle_interval
        self.exchange = exchange
        self.logger = get_logger().bind(component="backtest")

        # Exchange-aware fees
        if exchange == "binance":
            self.fees = ExchangeFees.binance_defaults(use_bnb=True)
        else:
            self.fees = ExchangeFees()

        # Simulation state
        self.usdc_balance = Decimal(str(starting_capital))
        self.crypto_balance = Decimal("0")
        self.entry_price: Decimal | None = None
        self.in_position = False

        # Metrics tracking
        self.metrics = BacktestMetrics(starting_balance=self.usdc_balance)
        self.equity_curve: list[tuple[datetime, Decimal]] = []
        self._current_regime: str | None = None
        self._regime_stats: dict[str, dict] = {}
        self._entry_regimes: dict[int, str] = {}  # position_id → entry regime
        self._entry_regime: str | None = None  # single-position mode

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

    def _load_inner_strategy_params(self, inner_name: str) -> dict[str, Any] | None:
        """Load params for an inner strategy nested under multi_strategy_router."""
        router_params = self._load_strategy_params("multi_strategy_router")
        if router_params is None:
            return None
        strategies = router_params.get("strategies", {})
        inner = strategies.get(inner_name, {})
        return inner.get("params")

    # Strategies that need specific higher timeframes loaded
    _NEEDS_4H = {
        "gemini_suivi_tendance_momentum",
        "grok_supertrend_4h",
        "grok_supertrend_short_4h",
        "grok_ema_adx_atr",
        "grok_ichimoku_cloud_4h",
        "grok_donchian_breakout_4h",
        "grok_vwap_trend_4h",
    }
    _NEEDS_1D = {
        "gemini_suivi_tendance_momentum",
        "grok_supertrend_4h",
        "grok_supertrend_short_4h",
        "grok_ema_adx_atr",
        "grok_adaptive_dca_weekly",
        "grok_ichimoku_cloud_4h",
        "grok_donchian_breakout_4h",
        "grok_vwap_trend_4h",
    }
    _NEEDS_1W = {
        "gemini_suivi_tendance_momentum",
        "grok_ema_adx_atr",
        "grok_adaptive_dca_weekly",
    }
    _NEEDS_1H = {
        "adaptive",
        "capitulation",
        "bear_short",
        "trend_following",
        "gemini_scalping_volatilite",
        "gemini_retour_moyenne",
    }
    _NEEDS_15M = {
        "adaptive",
        "capitulation",
        "bear_short",
        "gemini_retour_moyenne",
    }
    # Strategies that check _is_4h / _is_daily in generate_signal()
    _HAS_IS_4H = {
        "grok_supertrend_4h",
        "grok_supertrend_short_4h",
        "grok_ema_adx_atr",
        "grok_ichimoku_cloud_4h",
        "grok_donchian_breakout_4h",
        "grok_vwap_trend_4h",
    }
    _HAS_IS_DAILY = {"grok_adaptive_dca_weekly"}

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
        return await _load_candles_chunked(
            self.db_manager,
            pair,
            interval,
            start_time,
            end_time,
            exchange=self.exchange,
        )

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
        warmup_4h = start_time - timedelta(days=15)  # ~90 candles (> 52 for Ichimoku)
        warmup_1d = start_time - timedelta(days=250)  # ~250 candles for EMA(200, "1d") warmup
        warmup_1w = start_time - timedelta(days=400)  # ~57 candles

        # Load higher timeframe data (full range: warmup + backtest period)
        candles_1h: list[OHLCData] = []
        candles_15m: list[OHLCData] = []
        if self.strategy_name in self._NEEDS_1H:
            candles_1h = await self._load_candles_for_interval(pair, 60, warmup_1h, end_time)
        if self.strategy_name in self._NEEDS_15M:
            candles_15m = await self._load_candles_for_interval(pair, 15, warmup_15m, end_time)
        candles_warmup = await self._load_candles_for_interval(pair, ci, warmup_trading, start_time)

        # Load 4h, 1d, 1w if the strategy needs them
        candles_4h: list[OHLCData] = []
        candles_1d: list[OHLCData] = []
        candles_1w: list[OHLCData] = []
        if self.strategy_name in self._NEEDS_4H:
            candles_4h = await self._load_candles_for_interval(pair, 240, warmup_4h, end_time)
        if self.strategy_name in self._NEEDS_1D:
            candles_1d = await self._load_candles_for_interval(pair, 1440, warmup_1d, end_time)
        if self.strategy_name in self._NEEDS_1W:
            candles_1w = await self._load_candles_for_interval(pair, 10080, warmup_1w, end_time)

        self.logger.info(
            "mtf_data_loaded",
            trading_interval=ci,
            candles_1h=len(candles_1h),
            candles_15m=len(candles_15m),
            candles_4h=len(candles_4h),
            candles_1d=len(candles_1d),
            candles_1w=len(candles_1w),
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

        # 4h candles — tradeable only for 4h strategies
        is_4h_trigger = self.strategy_name in self._HAS_IS_4H
        for c in candles_4h:
            is_tradeable = is_4h_trigger and c.timestamp >= start_time
            sequence.append((c, 240, is_tradeable))

        # 1d candles — tradeable only for daily strategies
        is_daily_trigger = self.strategy_name in self._HAS_IS_DAILY
        for c in candles_1d:
            is_tradeable = is_daily_trigger and c.timestamp >= start_time
            sequence.append((c, 1440, is_tradeable))

        # 1w candles — never tradeable (feed analyzer only)
        for c in candles_1w:
            sequence.append((c, 10080, False))

        # Trading candles (skip if 4h is the trigger — already added above)
        if not is_4h_trigger and not is_daily_trigger:
            for c in candles_trading:
                sequence.append((c, ci, True))

        # Sort: timestamp ASC, then higher timeframes first
        interval_order = {10080: 0, 1440: 1, 240: 2, 60: 3, 15: 4, ci: 5}
        sequence.sort(key=lambda x: (x[0].timestamp, interval_order.get(x[1], 6)))

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
                .where(OHLCData.exchange == self.exchange)
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

    def _resolve_fill(self, signal: TradingSignal, candle: OHLCData) -> tuple[Decimal | None, bool]:
        """Resolve fill price using the NEXT candle's OHLC (no look-ahead bias).

        Args:
            signal: Pending signal from previous candle.
            candle: The NEXT candle (N+1) used for fill simulation.

        Returns:
            Tuple of (fill_price, is_limit_fill).
            fill_price is None if a limit order wasn't reached.
        """
        order_type = (signal.metadata or {}).get("order_type", "market")

        if order_type == "limit":
            limit_price = Decimal(
                str(signal.metadata.get("limit_price") or signal.price or candle.open)
            )
            if signal.signal_type == SignalType.BUY:
                if candle.low <= limit_price:
                    return limit_price, True
                return None, True
            else:  # SELL limit
                if candle.high >= limit_price:
                    return limit_price, True
                return None, True
        else:
            # Market order: fill at open of N+1 (spread+slippage added by execute_signal)
            return candle.open, False

    @staticmethod
    def _is_short_signal(signal: TradingSignal) -> bool:
        """Check if a signal is a margin/short signal."""
        if not signal.metadata:
            return False
        return bool(signal.metadata.get("is_short_open") or signal.metadata.get("is_short_close"))

    async def execute_signal(
        self, signal: TradingSignal, current_price: Decimal, *, is_limit_fill: bool = False
    ) -> None:
        """Execute a trading signal in the simulation.

        Args:
            signal: Trading signal from strategy
            current_price: Current market price (open of next candle for market, limit price for limit)
            is_limit_fill: If True, skip spread/slippage and use maker fee
        """
        if signal.signal_type == SignalType.HOLD:
            return

        # Route margin (short) signals to separate handler
        if signal.metadata and signal.metadata.get("mode") == "margin":
            await self._execute_short_signal(signal, current_price, is_limit_fill=is_limit_fill)
            return

        # Realistic trading costs (exchange-aware)
        if is_limit_fill:
            fee_pct = self.fees.maker
            spread_pct = Decimal("0")  # Limit order: no spread
            slippage_pct = Decimal("0")  # Limit order: no slippage
        else:
            fee_pct = self.fees.taker
            spread_pct = self.fees.spread
            slippage_pct = self.fees.slippage

        # Handle multi-position strategies differently
        is_multi = self.strategy_name in [
            "threshold_rolling",
            "adaptive",
            "capitulation",
            "bear_short",
            "grok_supertrend_short_4h",
            "trend_following",
        ]

        # Accumulation strategies buy repeatedly without selling (e.g. DCA)
        is_accumulation = self.strategy_name in [
            "grok_adaptive_dca_weekly",
        ]

        # Grok strategies use on_trade_filled() instead of set_position_state()
        uses_otf = hasattr(self.strategy, "on_trade_filled") and self.strategy_name in [
            "gemini_scalping_volatilite",
            "gemini_retour_moyenne",
            "gemini_suivi_tendance_momentum",
            "grok_supertrend_4h",
            "grok_ema_adx_atr",
            "grok_adaptive_dca_weekly",
            "grok_ichimoku_cloud_4h",
            "grok_donchian_breakout_4h",
            "grok_vwap_trend_4h",
        ]

        # Override order size from strategy metadata
        if uses_otf and signal.metadata:
            strategy_order_size = signal.metadata.get("order_size_usdc")
            if strategy_order_size is not None:
                order_amount_override = min(self.usdc_balance, Decimal(str(strategy_order_size)))
            else:
                order_amount_override = None
        else:
            order_amount_override = None

        if signal.signal_type == SignalType.BUY and (
            is_multi or is_accumulation or not self.in_position
        ):
            # Buy with available USDC
            if order_amount_override is not None:
                order_amount = order_amount_override
            else:
                base_amount = Decimal(str(self.settings.trading.default_order_amount_eur))
                # Apply position_size_multiplier to match runtime sizing
                # (ExecutionEngine._resolve_open_order_notional)
                if signal.metadata:
                    mult = signal.metadata.get("position_size_multiplier")
                    if mult is not None:
                        base_amount *= Decimal(str(mult))
                order_amount = min(self.usdc_balance, base_amount)

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
            elif uses_otf:
                # Grok strategies: notify via on_trade_filled
                await self.strategy.on_trade_filled(
                    trade_id=f"bt-{len(self.metrics.trades) + 1}",
                    pair=signal.pair,
                    side="buy",
                    amount=crypto_bought,
                    price=execution_price,
                    fee=fee,
                    reference_price=current_price,
                    position_id=None,
                )
            else:
                # Single position mode (legacy)
                # Use current_price (not execution_price) so strategy sees mid-market price
                self.strategy.set_position_state(has_position=True, entry_price=current_price)

            # Record trade with entry regime
            entry_regime = (
                signal.metadata.get("regime") if signal.metadata else None
            ) or self._current_regime
            trade = BacktestTrade(
                timestamp=signal.timestamp,
                side=TradeSide.BUY,
                price=execution_price,  # Actual execution price with spread+slippage
                amount_usdc=order_amount,
                amount_crypto=crypto_bought,
                fee=fee,
                regime=entry_regime,
            )
            self.metrics.trades.append(trade)
            self.metrics.total_fees += fee

            # Store entry regime for future SELL trade
            if is_multi:
                self._entry_regimes[position_id] = entry_regime or "unknown"
            else:
                self._entry_regime = entry_regime

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
            elif uses_otf:
                # Grok strategies: sell via on_trade_filled
                proceeds = self.crypto_balance * execution_price
                fee = proceeds * fee_pct
                amount_after_fee = proceeds - fee

                cost_basis = (
                    self.entry_price * self.crypto_balance if self.entry_price else Decimal("0")
                )
                pnl = amount_after_fee - cost_basis

                crypto_sold = self.crypto_balance

                await self.strategy.on_trade_filled(
                    trade_id=f"bt-sell-{len(self.metrics.trades) + 1}",
                    pair=signal.pair,
                    side="sell",
                    amount=crypto_sold,
                    price=execution_price,
                    fee=fee,
                    reference_price=current_price,
                    position_id=signal.metadata.get("position_id") if signal.metadata else None,
                )

                self.usdc_balance += amount_after_fee
                self.crypto_balance = Decimal("0")
                self.in_position = False
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

            # Record trade with ENTRY regime (not exit regime)
            if is_multi and position_id:
                sell_regime = self._entry_regimes.pop(position_id, self._current_regime)
            else:
                sell_regime = self._entry_regime or self._current_regime
                self._entry_regime = None
            trade = BacktestTrade(
                timestamp=signal.timestamp,
                side=TradeSide.SELL,
                price=execution_price,  # Actual execution price with spread+slippage
                amount_usdc=amount_after_fee,
                amount_crypto=crypto_sold,
                fee=fee,
                pnl=pnl,
                regime=sell_regime,
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

    async def _execute_short_signal(
        self, signal: TradingSignal, current_price: Decimal, *, is_limit_fill: bool = False
    ) -> None:
        """Execute a margin short signal in the simulation.

        SELL with is_short_open: open a short (lock margin collateral).
        BUY with is_short_close: close a short (release margin, calculate PnL).

        Rollover fee: 0.01% per 4h of position value.
        """
        if is_limit_fill:
            fee_pct = self.fees.maker
            spread_pct = Decimal("0")
            slippage_pct = Decimal("0")
        else:
            fee_pct = self.fees.taker
            spread_pct = self.fees.spread
            slippage_pct = self.fees.slippage

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

            entry_regime = (
                signal.metadata.get("regime") if signal.metadata else None
            ) or self._current_regime
            trade = BacktestTrade(
                timestamp=signal.timestamp,
                side=TradeSide.SELL,
                price=execution_price,
                amount_usdc=order_amount,
                amount_crypto=order_amount / execution_price,
                fee=fee,
                regime=entry_regime,
            )
            self.metrics.trades.append(trade)
            self.metrics.total_fees += fee
            # Store entry regime for future short close
            self._entry_regimes[position_id] = entry_regime or "unknown"

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

            # Use ENTRY regime for short close (not exit regime)
            close_regime = self._entry_regimes.pop(position_id, self._current_regime)
            trade = BacktestTrade(
                timestamp=signal.timestamp,
                side=TradeSide.BUY,
                price=execution_price,
                amount_usdc=close_value,
                amount_crypto=crypto_amount,
                fee=fee + rollover_fee,
                pnl=pnl,
                regime=close_regime,
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
        sell_trades = [t for t in self.metrics.trades if t.side == TradeSide.SELL]
        self.metrics.total_trades = len(sell_trades)

        # Accumulation strategies (e.g. DCA) have no sells — count buys instead
        if self.metrics.total_trades == 0 and self.strategy_name in [
            "grok_adaptive_dca_weekly",
        ]:
            self.metrics.total_trades = len(
                [t for t in self.metrics.trades if t.side == TradeSide.BUY]
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

        # Final balance — prefer equity curve (values crypto at last candle close)
        if self.equity_curve:
            self.metrics.ending_balance = self.equity_curve[-1][1]
        else:
            self.metrics.ending_balance = self.usdc_balance
            if self.crypto_balance > 0 and self.metrics.trades:
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

        # Calmar ratio: annualized return / max drawdown %
        if self.metrics.max_drawdown_pct > 0 and self.metrics.duration_days > 0:
            annualized_return = self.metrics.total_return_pct * (365 / self.metrics.duration_days)
            self.metrics.calmar_ratio = annualized_return / self.metrics.max_drawdown_pct

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

        if self.strategy_name == "threshold_rolling":
            from krakenbot.strategies.threshold_rolling import ThresholdRollingStrategy

            self.strategy = ThresholdRollingStrategy(
                event_bus=self.event_bus,
                db_manager=self.db_manager,
                settings=self.settings,
            )
        elif self.strategy_name == "adaptive":
            from krakenbot.indicators.multi_timeframe import MultiTimeframeAnalyzer
            from krakenbot.strategies.adaptive import AdaptiveStrategy

            analyzer = MultiTimeframeAnalyzer()
            strategy_params = _override_pair_in_params(
                self._load_strategy_params("adaptive"), pair
            )
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
            strategy_params = _override_pair_in_params(
                self._load_strategy_params("capitulation"), pair
            )
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
            strategy_params = _override_pair_in_params(
                self._load_strategy_params("bear_short"), pair
            )
            self.strategy = BearShortStrategy(
                settings=self.settings,
                event_bus=self.event_bus,
                db_manager=self.db_manager,
                analyzer=analyzer,
                strategy_params=strategy_params,
            )
        elif self.strategy_name == "trend_following":
            from krakenbot.strategies.trend_following import TrendFollowingStrategy

            strategy_params = _override_pair_in_params(
                self._load_strategy_params("trend_following"), pair
            )
            self.strategy = TrendFollowingStrategy(
                settings=self.settings,
                event_bus=self.event_bus,
                db_manager=self.db_manager,
                strategy_params=strategy_params,
            )
        # ---------------------------------------------------------------
        # Gemini strategies (Phase-1A)
        # ---------------------------------------------------------------
        elif self.strategy_name == "gemini_scalping_volatilite":
            from krakenbot.indicators.multi_timeframe import MultiTimeframeAnalyzer
            from krakenbot.strategies.gemini_scalping_volatilite import (
                GeminiScalpingVolatilite,
            )

            analyzer = MultiTimeframeAnalyzer()
            strategy_params = _override_pair_in_params(
                self._load_inner_strategy_params("gemini_scalping_volatilite"), pair
            )
            self.strategy = GeminiScalpingVolatilite(
                settings=self.settings,
                event_bus=self.event_bus,
                db_manager=self.db_manager,
                bot_id="scalping_vol",
                strategy_params=strategy_params,
                analyzer=analyzer,
            )
        elif self.strategy_name == "gemini_retour_moyenne":
            from krakenbot.indicators.multi_timeframe import MultiTimeframeAnalyzer
            from krakenbot.strategies.gemini_retour_moyenne import GeminiRetourMoyenne

            analyzer = MultiTimeframeAnalyzer()
            strategy_params = _override_pair_in_params(
                self._load_inner_strategy_params("gemini_retour_moyenne"), pair
            )
            self.strategy = GeminiRetourMoyenne(
                settings=self.settings,
                event_bus=self.event_bus,
                db_manager=self.db_manager,
                bot_id="retour_moy",
                strategy_params=strategy_params,
                analyzer=analyzer,
            )
        elif self.strategy_name == "gemini_suivi_tendance_momentum":
            from krakenbot.indicators.multi_timeframe import MultiTimeframeAnalyzer
            from krakenbot.strategies.gemini_suivi_tendance_momentum import (
                GeminiSuiviTendanceMomentum,
            )

            analyzer = MultiTimeframeAnalyzer()
            strategy_params = _override_pair_in_params(
                self._load_inner_strategy_params("gemini_suivi_tendance_momentum"), pair
            )
            self.strategy = GeminiSuiviTendanceMomentum(
                settings=self.settings,
                event_bus=self.event_bus,
                db_manager=self.db_manager,
                bot_id="tendance_mom",
                strategy_params=strategy_params,
                analyzer=analyzer,
            )
        # ---------------------------------------------------------------
        # Grok strategies (Phase-1A)
        # ---------------------------------------------------------------
        elif self.strategy_name == "grok_supertrend_4h":
            from krakenbot.indicators.multi_timeframe import MultiTimeframeAnalyzer
            from krakenbot.strategies.grok_supertrend_4h import (
                GrokSuperTrend4hRegime,
            )

            analyzer = MultiTimeframeAnalyzer()
            strategy_params = _override_pair_in_params(
                self._load_inner_strategy_params("grok_supertrend_4h"), pair
            )
            self.strategy = GrokSuperTrend4hRegime(
                settings=self.settings,
                event_bus=self.event_bus,
                db_manager=self.db_manager,
                bot_id="supertrend_4h",
                strategy_params=strategy_params,
                analyzer=analyzer,
            )
        elif self.strategy_name == "grok_ema_adx_atr":
            from krakenbot.indicators.multi_timeframe import MultiTimeframeAnalyzer
            from krakenbot.strategies.grok_ema_adx_atr import GrokEMA27_125_ADX_ATR

            analyzer = MultiTimeframeAnalyzer()
            strategy_params = _override_pair_in_params(
                self._load_inner_strategy_params("grok_ema_adx_atr"), pair
            )
            self.strategy = GrokEMA27_125_ADX_ATR(
                settings=self.settings,
                event_bus=self.event_bus,
                db_manager=self.db_manager,
                bot_id="ema_cross_4h",
                strategy_params=strategy_params,
                analyzer=analyzer,
            )
        elif self.strategy_name == "grok_supertrend_short_4h":
            from krakenbot.indicators.multi_timeframe import MultiTimeframeAnalyzer
            from krakenbot.strategies.grok_supertrend_short_4h import (
                GrokSuperTrendShort4hRegime,
            )

            analyzer = MultiTimeframeAnalyzer()
            strategy_params = _override_pair_in_params(
                self._load_inner_strategy_params("grok_supertrend_short_4h"), pair
            )
            self.strategy = GrokSuperTrendShort4hRegime(
                settings=self.settings,
                event_bus=self.event_bus,
                db_manager=self.db_manager,
                bot_id="supertrend_short_4h",
                strategy_params=strategy_params,
                analyzer=analyzer,
            )
        elif self.strategy_name == "grok_adaptive_dca_weekly":
            from krakenbot.indicators.multi_timeframe import MultiTimeframeAnalyzer
            from krakenbot.strategies.grok_adaptive_dca_weekly import (
                GrokAdaptiveDCAWeekly,
            )

            analyzer = MultiTimeframeAnalyzer()
            strategy_params = _override_pair_in_params(
                self._load_inner_strategy_params("grok_adaptive_dca_weekly"), pair
            )
            self.strategy = GrokAdaptiveDCAWeekly(
                settings=self.settings,
                event_bus=self.event_bus,
                db_manager=self.db_manager,
                bot_id="dca_weekly",
                strategy_params=strategy_params,
                analyzer=analyzer,
            )
        # ---------------------------------------------------------------
        # New trend-following strategies (Phase-1B)
        # ---------------------------------------------------------------
        elif self.strategy_name == "grok_ichimoku_cloud_4h":
            from krakenbot.indicators.multi_timeframe import MultiTimeframeAnalyzer
            from krakenbot.strategies.grok_ichimoku_cloud_4h import (
                GrokIchimokuCloudBreakoutV1,
            )

            analyzer = MultiTimeframeAnalyzer()
            strategy_params = _override_pair_in_params(
                self._load_inner_strategy_params("grok_ichimoku_cloud_4h"), pair
            )
            self.strategy = GrokIchimokuCloudBreakoutV1(
                settings=self.settings,
                event_bus=self.event_bus,
                db_manager=self.db_manager,
                bot_id="ichimoku_cloud_4h",
                strategy_params=strategy_params,
                analyzer=analyzer,
            )
        elif self.strategy_name == "grok_donchian_breakout_4h":
            from krakenbot.indicators.multi_timeframe import MultiTimeframeAnalyzer
            from krakenbot.strategies.grok_donchian_breakout_4h import (
                GrokDonchianChannelBreakoutV1,
            )

            analyzer = MultiTimeframeAnalyzer()
            strategy_params = _override_pair_in_params(
                self._load_inner_strategy_params("grok_donchian_breakout_4h"), pair
            )
            self.strategy = GrokDonchianChannelBreakoutV1(
                settings=self.settings,
                event_bus=self.event_bus,
                db_manager=self.db_manager,
                bot_id="donchian_breakout_4h",
                strategy_params=strategy_params,
                analyzer=analyzer,
            )
        elif self.strategy_name == "grok_vwap_trend_4h":
            from krakenbot.indicators.multi_timeframe import MultiTimeframeAnalyzer
            from krakenbot.strategies.grok_vwap_trend_4h import GrokVWAPTrendV1

            analyzer = MultiTimeframeAnalyzer()
            strategy_params = _override_pair_in_params(
                self._load_inner_strategy_params("grok_vwap_trend_4h"), pair
            )
            self.strategy = GrokVWAPTrendV1(
                settings=self.settings,
                event_bus=self.event_bus,
                db_manager=self.db_manager,
                bot_id="vwap_trend_4h",
                strategy_params=strategy_params,
                analyzer=analyzer,
            )
        else:
            raise ValueError(
                f"Unknown strategy: {self.strategy_name}. "
                f"Available: threshold_rolling, adaptive, capitulation, "
                f"bear_short, trend_following, "
                f"gemini_scalping_volatilite, gemini_retour_moyenne, "
                f"gemini_suivi_tendance_momentum, "
                f"grok_supertrend_4h, grok_supertrend_short_4h, grok_ema_adx_atr, "
                f"grok_adaptive_dca_weekly, "
                f"grok_ichimoku_cloud_4h, grok_donchian_breakout_4h, "
                f"grok_vwap_trend_4h"
            )

        # CRITICAL: Skip DB sync in backtest mode for all strategies
        self.strategy._skip_db_sync = True

        # Pre-register lazy indicators so they exist before warmup data flows.
        # Without this, the first get_*() call returns None because the indicator
        # was just created and has no data yet.
        bt_analyzer = getattr(self.strategy, "analyzer", None)
        if bt_analyzer is not None:
            # EMAs used by regime calculation and strategies
            _LAZY_EMAS = {
                "grok_supertrend_4h": [(20, "4h"), (50, "4h")],
                "grok_supertrend_short_4h": [(20, "4h"), (50, "4h")],
                "grok_ema_adx_atr": [(27, "4h"), (125, "4h")],
                "gemini_suivi_tendance_momentum": [(20, "4h"), (50, "4h")],
                "grok_ichimoku_cloud_4h": [(20, "4h"), (50, "4h")],
                "grok_donchian_breakout_4h": [(20, "4h"), (50, "4h")],
                "grok_vwap_trend_4h": [(20, "4h"), (50, "4h")],
            }
            for period, tf in _LAZY_EMAS.get(self.strategy_name, []):
                bt_analyzer.get_ema(period, tf)

            # SuperTrend
            if self.strategy_name in ("grok_supertrend_4h", "grok_supertrend_short_4h"):
                bt_analyzer.get_supertrend("4h", atr_period=10, multiplier=3.0)

            # Ichimoku
            if self.strategy_name == "grok_ichimoku_cloud_4h":
                bt_analyzer.get_ichimoku("4h")

            # Donchian
            if self.strategy_name == "grok_donchian_breakout_4h":
                bt_analyzer.get_donchian("4h", period_upper=20, period_lower=10)

            # VWAP
            if self.strategy_name == "grok_vwap_trend_4h":
                bt_analyzer.get_vwap(20, "4h")

        # Build replay sequence (with MTF warmup for strategies using MultiTimeframeAnalyzer)
        needs_mtf = self.strategy_name in [
            "adaptive",
            "capitulation",
            "bear_short",
            "trend_following",
            "gemini_scalping_volatilite",
            "gemini_retour_moyenne",
            "gemini_suivi_tendance_momentum",
            "grok_supertrend_4h",
            "grok_supertrend_short_4h",
            "grok_ema_adx_atr",
            "grok_adaptive_dca_weekly",
            "grok_ichimoku_cloud_4h",
            "grok_donchian_breakout_4h",
            "grok_vwap_trend_4h",
        ]
        if needs_mtf:
            replay_sequence = await self._build_replay_sequence(pair, start_time, end_time, candles)
        else:
            replay_sequence = [(c, self.candle_interval, True) for c in candles]

        tradeable_total = sum(1 for _, _, t in replay_sequence if t)

        # Replay historical data — NEXT-BAR EXECUTION MODEL
        # Signal on candle N → fill at open of candle N+1 (market) or limit price (limit)
        # This eliminates look-ahead bias: we never fill at a price we just analyzed.
        tradeable_idx = 0
        pending: tuple[TradingSignal, str | None] | None = None  # (signal, entry_regime)

        for candle, interval, is_tradeable in replay_sequence:
            # PHASE 1: Execute pending signal from PREVIOUS candle using THIS candle's OHLC
            if is_tradeable and pending:
                pending_signal, entry_regime = pending
                fill_price, is_limit = self._resolve_fill(pending_signal, candle)
                if fill_price is not None:
                    saved_regime = self._current_regime
                    self._current_regime = entry_regime
                    if self._is_short_signal(pending_signal):
                        await self._execute_short_signal(
                            pending_signal, fill_price, is_limit_fill=is_limit
                        )
                    else:
                        await self.execute_signal(
                            pending_signal, fill_price, is_limit_fill=is_limit
                        )
                    self._current_regime = saved_regime
                else:
                    self.logger.debug(
                        "limit_order_not_filled",
                        timestamp=candle.timestamp,
                        signal=pending_signal.signal_type.value,
                    )
                pending = None

            # PHASE 2: Feed OHLC to strategy (all timeframes)
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

            # Feed the analyzer BEFORE on_ohlc so indicators are up-to-date.
            # Strategies like grok_* don't call analyzer.update() internally.
            bt_analyzer = getattr(self.strategy, "analyzer", None)
            if bt_analyzer is not None:
                bt_analyzer.update(ohlc_data, interval)

            await self.strategy.on_ohlc(ohlc_data)

            # Only trade on tradeable candles (skip warmup + higher TFs)
            if not is_tradeable:
                continue

            tradeable_idx += 1

            # Set timeframe flags for strategies that check them in generate_signal()
            if hasattr(self.strategy, "_is_4h"):
                self.strategy._is_4h = interval == 240
            if hasattr(self.strategy, "_is_daily"):
                self.strategy._is_daily = interval == 1440

            # Simulate tick with closing price for strategy analysis
            tick_data = {
                "pair": candle.pair,
                "timestamp": candle.timestamp,
                "price": candle.close,
                "volume": candle.volume,
                "side": "buy",  # Dummy side for backtest
            }
            await self.strategy.on_tick(tick_data)

            # PHASE 3: Generate signal → defer to NEXT candle
            signal = await self.strategy.generate_signal()

            # Track current regime from analyzer
            bt_analyzer = getattr(self.strategy, "analyzer", None)
            if bt_analyzer:
                last_analysis = getattr(bt_analyzer, "_last_analysis", None)
                if last_analysis:
                    self._current_regime = last_analysis.regime.value

            # Log signals for debugging
            if signal and signal.signal_type.value in ["buy", "sell"]:
                self.logger.info(
                    "backtest_signal",
                    timestamp=candle.timestamp,
                    signal=signal.signal_type.value,
                    reason=signal.reason,
                    price=float(candle.close),
                )

            # Queue signal for next-bar execution (no look-ahead bias)
            if signal:
                pending = (signal, self._current_regime)

            # Track equity curve (mark-to-market at close is fine)
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


class GridBacktester:
    """Backtest engine specialized for grid strategies.

    Grid strategies manage multiple simultaneous limit orders.
    Fills are detected by checking candle low/high against all active levels.
    """

    GRID_STRATEGIES = {"grid_spot", "grid_adaptive", "grok_grid_atr_adaptive_v4"}

    def __init__(
        self,
        settings: Settings,
        db_manager: DatabaseManager,
        strategy_name: str = "grid_spot",
        candle_interval: int = 5,
        exchange: str = "kraken",
        starting_capital: float = 1000.0,
    ):
        """Initialize grid backtester."""
        self.settings = settings
        self.db_manager = db_manager
        self.strategy_name = strategy_name
        self.candle_interval = candle_interval
        self.exchange = exchange
        self.logger = get_logger().bind(component="grid_backtest")

        # Exchange-aware fees
        if exchange == "binance":
            self.fees = ExchangeFees.binance_defaults(use_bnb=True)
        else:
            self.fees = ExchangeFees()

        # Simulation state
        self.usdc_balance = Decimal(str(starting_capital))
        self.btc_held = Decimal("0")

        # Grid state
        self.active_buy_orders: list[dict[str, Decimal]] = []  # {price, amount_usdc}
        self.active_sell_orders: list[dict[str, Any]] = []  # {price, amount_btc, entry_price}

        # Grid metrics
        self.pairs_completed: int = 0
        self.grid_profit: Decimal = Decimal("0")
        self.total_fees: Decimal = Decimal("0")
        self.total_orders_placed: int = 0
        self.rebalance_count: int = 0

        # Standard metrics
        self.metrics = BacktestMetrics(starting_balance=self.usdc_balance)
        self.equity_curve: list[tuple[datetime, Decimal]] = []

        # EventBus for strategy init
        self.event_bus = EventBus()

        # Strategy params
        self._strategy_bot_id = strategy_name
        self._strategy_params = self._load_grid_strategy_params(strategy_name)

        # Grid config from strategy params
        self.grid_levels = int(self._strategy_params.get("grid_levels", 10))
        self.grid_spacing_pct = Decimal(str(self._strategy_params.get("grid_spacing_pct", 2.0)))
        self.range_size_pct = Decimal(str(self._strategy_params.get("range_size_pct", 20.0)))
        self.rebalance_threshold_pct = Decimal(
            str(self._strategy_params.get("rebalance_threshold_pct", 5.0))
        )
        self.order_amount_usdc = Decimal(str(self._strategy_params.get("order_amount_usdc", 30)))

        # Grid center tracking
        self._grid_center: Decimal | None = None
        self._grid_initialized = False

        # For adaptive grid: ATR-based params
        self.atr_multiplier = Decimal(str(self._strategy_params.get("atr_multiplier", 3.0)))
        self.min_spacing_pct = Decimal(str(self._strategy_params.get("min_spacing_pct", 1.5)))
        self.max_spacing_pct = Decimal(str(self._strategy_params.get("max_spacing_pct", 4.0)))
        self.directional_pause_pct = Decimal(
            str(self._strategy_params.get("directional_pause_pct", 25.0))
        )

        # Directional pause tracking
        self._hourly_prices: list[Decimal] = []
        self._grid_paused: bool = False

    def _load_strategy_params(self, strategy_name: str) -> dict[str, Any] | None:
        """Load top-level strategy params from settings."""
        if not self.settings.multi_strategy.enabled:
            return None
        for strategy in self.settings.multi_strategy.strategies:
            if strategy.name == strategy_name:
                self._strategy_bot_id = getattr(strategy, "bot_id", strategy_name)
                return strategy.params or {}
        return None

    def _load_inner_strategy_entry(self, inner_name: str) -> dict[str, Any] | None:
        """Load an inner router strategy entry from settings."""
        if not self.settings.multi_strategy.enabled:
            return None
        for strategy in self.settings.multi_strategy.strategies:
            if strategy.name != "multi_strategy_router":
                continue
            strategies = (strategy.params or {}).get("strategies", {})
            entry = strategies.get(inner_name)
            if entry is not None:
                return entry
        return None

    def _load_grid_strategy_params(self, strategy_name: str) -> dict[str, Any]:
        """Resolve params for grid strategies, including router inner strategies."""
        if strategy_name == "grok_grid_atr_adaptive_v4":
            entry = self._load_inner_strategy_entry(strategy_name) or {}
            self._strategy_bot_id = entry.get("bot_id", "grid_atr_v4")
            return entry.get("params") or {}
        return self._load_strategy_params(strategy_name) or {}

    def _make_ohlc_payload(self, candle: OHLCData, interval: int) -> dict[str, Any]:
        """Build strategy-compatible OHLC payload."""
        return {
            "pair": candle.pair,
            "timestamp": candle.timestamp,
            "open": candle.open,
            "high": candle.high,
            "low": candle.low,
            "close": candle.close,
            "volume": candle.volume,
            "interval": interval,
            "timeframe": interval,
            "is_complete": True,
        }

    async def _build_grok_grid_replay_sequence(
        self,
        pair: str,
        start_time: datetime,
        end_time: datetime,
        candles_trading: list[OHLCData],
    ) -> list[tuple[OHLCData, int, bool]]:
        """Build replay for ATR grid using 4h trigger + 1d/1w context feeds."""
        warmup_4h = start_time - timedelta(days=15)
        warmup_1d = start_time - timedelta(days=250)
        warmup_1w = start_time - timedelta(days=400)

        candles_4h_warmup = await self._load_candles_for_interval(pair, 240, warmup_4h, start_time)
        candles_1d = await self._load_candles_for_interval(pair, 1440, warmup_1d, end_time)
        candles_1w = await self._load_candles_for_interval(pair, 10080, warmup_1w, end_time)

        replay_sequence: list[tuple[OHLCData, int, bool]] = []
        for candle in candles_4h_warmup:
            replay_sequence.append((candle, 240, False))
        for candle in candles_1w:
            replay_sequence.append((candle, 10080, False))
        for candle in candles_1d:
            replay_sequence.append((candle, 1440, False))
        for candle in candles_trading:
            replay_sequence.append((candle, 240, True))

        replay_sequence.sort(key=lambda item: (item[0].timestamp, -item[1]))
        return replay_sequence

    async def _create_grok_grid_strategy(self):
        """Instantiate the real ATR-adaptive grid strategy for faithful replay."""
        from krakenbot.indicators.multi_timeframe import MultiTimeframeAnalyzer
        from krakenbot.strategies.grok_grid_atr_adaptive_v4 import GrokGridATRAdaptiveV4

        analyzer = MultiTimeframeAnalyzer()
        strategy = GrokGridATRAdaptiveV4(
            settings=self.settings,
            event_bus=self.event_bus,
            db_manager=self.db_manager,
            bot_id=self._strategy_bot_id,
            strategy_params=self._strategy_params,
            analyzer=analyzer,
        )
        strategy._skip_db_sync = True
        strategy._running = True
        return strategy, analyzer

    def _get_grok_grid_pending_orders(self, strategy: Any) -> list[dict[str, Any]]:
        """Return pending buy levels plus paired sell targets for open positions."""
        pending_orders: list[dict[str, Any]] = []

        for key, level in strategy._grid_levels.items():
            if level.status != "pending" or level.side != "buy":
                continue
            pending_orders.append(
                {
                    "order_id": key,
                    "side": "buy",
                    "price": level.price,
                    "amount_usdc": level.amount_usdc,
                    "level": level,
                }
            )

        for position in strategy.open_positions:
            pending_orders.append(
                {
                    "order_id": f"sell_pos_{position.position_id}",
                    "side": "sell",
                    "price": position.sell_level,
                    "amount_btc": position.amount_btc,
                    "position_id": position.position_id,
                }
            )

        return pending_orders

    def _get_grok_grid_pending_order_ids(self, strategy: Any) -> set[str]:
        """Return current pending order ids for order-placement accounting."""
        return {order["order_id"] for order in self._get_grok_grid_pending_orders(strategy)}

    def _mark_grok_grid_level_filled(self, strategy: Any, side: str, price: Decimal) -> None:
        """Mark a matching grid level as filled when a simulated fill occurs."""
        if side == "buy":
            level = strategy._grid_levels.get(f"buy_{price}")
            if level is not None:
                level.status = "filled"
            return

        for level in strategy._grid_levels.values():
            if (
                level.side == side
                and level.status == "pending"
                and abs(level.price - price) < Decimal("1")
            ):
                level.status = "filled"
                break

    async def _process_grok_grid_buy_fill(
        self, strategy: Any, order: dict[str, Any], candle: OHLCData
    ) -> None:
        """Process a grok ATR-grid BUY fill through the real strategy lifecycle."""
        fill_price = order["price"]
        amount_usdc = order["amount_usdc"]
        if self.usdc_balance < amount_usdc:
            return

        fee = amount_usdc * self.fees.maker
        net_usdc = amount_usdc - fee
        btc_bought = net_usdc / fill_price

        self.usdc_balance -= amount_usdc
        self.btc_held += btc_bought
        self.total_fees += fee
        self._mark_grok_grid_level_filled(strategy, "buy", fill_price)

        self.metrics.trades.append(
            BacktestTrade(
                timestamp=candle.timestamp,
                side=TradeSide.BUY,
                price=fill_price,
                amount_usdc=amount_usdc,
                amount_crypto=btc_bought,
                fee=fee,
            )
        )

        strategy._current_timestamp = candle.timestamp
        await strategy.on_trade_filled(
            trade_id=f"grid-buy-{candle.timestamp.isoformat()}-{fill_price}",
            pair=candle.pair,
            side="buy",
            amount=btc_bought,
            price=fill_price,
            fee=fee,
            reference_price=None,
            position_id=None,
        )
        self.total_orders_placed += 1

    async def _process_grok_grid_sell_fill(
        self, strategy: Any, order: dict[str, Any], candle: OHLCData
    ) -> None:
        """Process a grok ATR-grid SELL fill through the real strategy lifecycle."""
        fill_price = order["price"]
        amount_btc = order["amount_btc"]
        if self.btc_held < amount_btc:
            return

        gross_usdc = amount_btc * fill_price
        fee = gross_usdc * self.fees.maker
        net_usdc = gross_usdc - fee
        self.btc_held -= amount_btc
        self.usdc_balance += net_usdc
        self.total_fees += fee
        self._mark_grok_grid_level_filled(strategy, "sell", fill_price)

        matched_position = None
        for position in strategy.open_positions:
            if position.position_id == order["position_id"]:
                matched_position = position
                break
        if matched_position is None:
            return

        cost_basis = matched_position.amount_btc * matched_position.entry_price
        pnl = net_usdc - cost_basis
        self.grid_profit += pnl
        self.metrics.total_pnl += pnl
        self.pairs_completed += 1
        if pnl > 0:
            self.metrics.winning_trades += 1
        else:
            self.metrics.losing_trades += 1

        self.metrics.trades.append(
            BacktestTrade(
                timestamp=candle.timestamp,
                side=TradeSide.SELL,
                price=fill_price,
                amount_usdc=gross_usdc,
                amount_crypto=amount_btc,
                fee=fee,
                pnl=pnl,
            )
        )

        strategy._current_timestamp = candle.timestamp
        await strategy.on_trade_filled(
            trade_id=f"grid-sell-{candle.timestamp.isoformat()}-{fill_price}",
            pair=candle.pair,
            side="sell",
            amount=amount_btc,
            price=fill_price,
            fee=fee,
            reference_price=None,
            position_id=order["position_id"],
        )
        self.total_orders_placed += 1

    def _initialize_grid(self, current_price: Decimal) -> None:
        """Initialize the grid around the current price."""
        half_range = current_price * self.range_size_pct / Decimal("200")
        grid_low = current_price - half_range
        grid_high = current_price + half_range
        self._grid_center = current_price

        self.active_buy_orders.clear()
        self.active_sell_orders.clear()

        for i in range(self.grid_levels):
            ratio = Decimal(str(i)) / Decimal(str(self.grid_levels - 1))
            level_price = grid_low * (grid_high / grid_low) ** ratio
            level_price = level_price.quantize(Decimal("0.1"))

            if level_price < current_price:
                self.active_buy_orders.append(
                    {"price": level_price, "amount_usdc": self.order_amount_usdc}
                )
                self.total_orders_placed += 1
            elif level_price > current_price:
                # Sell orders need BTC — initially empty, they get created from fills
                pass

        self._grid_initialized = True
        self.logger.info(
            "grid_backtest_initialized",
            center=float(current_price),
            buy_levels=len(self.active_buy_orders),
            low=float(grid_low),
            high=float(grid_high),
        )

    def _process_buy_fill(self, order: dict[str, Decimal], candle: OHLCData) -> None:
        """Process a buy order fill."""
        fill_price = order["price"]
        amount_usdc = order["amount_usdc"]

        if self.usdc_balance < amount_usdc:
            return  # Insufficient balance

        fee = amount_usdc * self.fees.maker
        net_usdc = amount_usdc - fee
        btc_bought = net_usdc / fill_price

        self.usdc_balance -= amount_usdc
        self.btc_held += btc_bought
        self.total_fees += fee

        # Record trade
        self.metrics.trades.append(
            BacktestTrade(
                timestamp=candle.timestamp,
                side=TradeSide.BUY,
                price=fill_price,
                amount_usdc=amount_usdc,
                amount_crypto=btc_bought,
                fee=fee,
            )
        )

        # Place paired sell at upper level
        sell_price = fill_price * (Decimal("1") + self.grid_spacing_pct / Decimal("100"))
        sell_price = sell_price.quantize(Decimal("0.1"))

        # Ensure sell price is profitable (covers 2x round-trip fees = 0.64%)
        min_profitable_sell = fill_price * Decimal("1.0064")
        if sell_price < min_profitable_sell:
            sell_price = min_profitable_sell.quantize(Decimal("0.1"))

        self.active_sell_orders.append(
            {
                "price": sell_price,
                "amount_btc": btc_bought,
                "entry_price": fill_price,
            }
        )
        self.total_orders_placed += 2  # buy filled + sell placed

    def _process_sell_fill(self, order: dict[str, Any], candle: OHLCData) -> None:
        """Process a sell order fill."""
        fill_price = order["price"]
        amount_btc = order["amount_btc"]
        entry_price = order["entry_price"]

        if self.btc_held < amount_btc:
            return  # Insufficient BTC

        gross_usdc = amount_btc * fill_price
        fee = gross_usdc * self.fees.maker
        net_usdc = gross_usdc - fee

        self.btc_held -= amount_btc
        self.usdc_balance += net_usdc
        self.total_fees += fee

        # Calculate profit
        cost_basis = amount_btc * entry_price
        pnl = net_usdc - cost_basis
        self.grid_profit += pnl
        self.metrics.total_pnl += pnl
        self.pairs_completed += 1

        if pnl > 0:
            self.metrics.winning_trades += 1
        else:
            self.metrics.losing_trades += 1

        # Record trade
        self.metrics.trades.append(
            BacktestTrade(
                timestamp=candle.timestamp,
                side=TradeSide.SELL,
                price=fill_price,
                amount_usdc=gross_usdc,
                amount_crypto=amount_btc,
                fee=fee,
                pnl=pnl,
            )
        )

        # Place paired buy at lower level
        buy_price = fill_price * (Decimal("1") - self.grid_spacing_pct / Decimal("100"))
        buy_price = buy_price.quantize(Decimal("0.1"))
        self.active_buy_orders.append({"price": buy_price, "amount_usdc": self.order_amount_usdc})
        self.total_orders_placed += 1

    def _check_rebalance(self, current_price: Decimal) -> bool:
        """Check and execute rebalance if needed."""
        if self._grid_center is None:
            return False
        deviation_pct = abs(current_price - self._grid_center) / self._grid_center * Decimal("100")
        if deviation_pct > self.rebalance_threshold_pct:
            self._initialize_grid(current_price)
            self.rebalance_count += 1
            return True
        return False

    def _update_range_from_atr(self, current_price: Decimal, atr_value: Decimal) -> None:
        """Update grid range based on ATR (for grid_adaptive)."""
        half_range = atr_value * self.atr_multiplier
        total_range_pct = (half_range * Decimal("2")) / current_price * Decimal("100")
        spacing_pct = total_range_pct / Decimal(str(self.grid_levels))

        # Enforce profitability floor and min_spacing
        min_profitable = Decimal("0.64")
        effective_min = max(self.min_spacing_pct, min_profitable)
        if spacing_pct < effective_min:
            spacing_pct = effective_min
            total_range_pct = spacing_pct * Decimal(str(self.grid_levels))

        # Enforce max spacing
        if spacing_pct > self.max_spacing_pct:
            spacing_pct = self.max_spacing_pct
            total_range_pct = spacing_pct * Decimal(str(self.grid_levels))

        self.range_size_pct = total_range_pct
        self.grid_spacing_pct = spacing_pct

    def _check_directional_pause(self, current_price: Decimal) -> None:
        """Check and update directional pause state."""
        if self.directional_pause_pct <= 0:
            self._grid_paused = False
            return

        if len(self._hourly_prices) < 50:
            return

        sma50 = sum(self._hourly_prices[-50:]) / Decimal("50")
        if sma50 <= 0:
            return

        deviation_pct = abs(current_price - sma50) / sma50 * Decimal("100")
        self._grid_paused = deviation_pct > self.directional_pause_pct

    async def run(self, pair: str, start_time: datetime, end_time: datetime) -> BacktestMetrics:
        """Run grid backtest."""
        self.metrics.start_time = start_time
        self.metrics.end_time = end_time
        self.metrics.duration_days = (end_time - start_time).total_seconds() / 86400

        self.settings.trading.pair = pair

        # Override hardcoded pair in YAML strategy_params so the inner strategy
        # (e.g. grok_grid_atr_adaptive_v4) binds to the backtest pair, not the
        # default BTC/USDC shipped in strategies.yaml.
        self._strategy_params = _override_pair_in_params(self._strategy_params, pair)

        # Load candles
        candles = await self._load_candles(pair, start_time, end_time)
        if len(candles) < 10:
            raise ValueError(f"Insufficient data: only {len(candles)} candles")

        self.logger.info(
            "grid_backtest_started",
            strategy=self.strategy_name,
            pair=pair,
            candles=len(candles),
            period=f"{start_time.date()} to {end_time.date()}",
        )

        # For MTF grid variants, load higher timeframe context candles
        analyzer = None
        strategy = None
        replay_sequence: list[tuple[OHLCData, int, bool]] = []

        if self.strategy_name == "grid_adaptive":
            from krakenbot.indicators.multi_timeframe import MultiTimeframeAnalyzer

            analyzer = MultiTimeframeAnalyzer()

            # Load 1h warmup candles (for ATR)
            warmup_start = start_time - timedelta(hours=72)
            candles_1h = await self._load_candles_for_interval(pair, 60, warmup_start, end_time)

            # Build replay: 1h warmup + trading candles
            for c in candles_1h:
                is_tradeable = c.timestamp >= start_time
                replay_sequence.append((c, 60, is_tradeable))
            for c in candles:
                replay_sequence.append((c, self.candle_interval, True))

            # Sort by timestamp, higher intervals first on ties
            replay_sequence.sort(key=lambda x: (x[0].timestamp, -x[1]))
        elif self.strategy_name == "grok_grid_atr_adaptive_v4":
            strategy, analyzer = await self._create_grok_grid_strategy()
            replay_sequence = await self._build_grok_grid_replay_sequence(
                pair, start_time, end_time, candles
            )
        else:
            replay_sequence = [(c, self.candle_interval, True) for c in candles]

        # Replay
        for candle, interval, is_tradeable in replay_sequence:
            current_price = candle.close

            if self.strategy_name == "grok_grid_atr_adaptive_v4":
                assert analyzer is not None
                assert strategy is not None

                if is_tradeable:
                    pending_orders = self._get_grok_grid_pending_orders(strategy)
                    filled_buys = [
                        order
                        for order in pending_orders
                        if order["side"] == "buy" and candle.low <= order["price"]
                    ]
                    filled_sells = [
                        order
                        for order in pending_orders
                        if order["side"] == "sell" and candle.high >= order["price"]
                    ]
                    for order in filled_buys:
                        await self._process_grok_grid_buy_fill(strategy, order, candle)
                    for order in filled_sells:
                        await self._process_grok_grid_sell_fill(strategy, order, candle)

                analyzer.update(self._make_ohlc_payload(candle, interval), interval)

                if not is_tradeable:
                    continue

                old_center = strategy._grid_center
                old_spacing = strategy._grid_spacing
                before_ids = self._get_grok_grid_pending_order_ids(strategy)

                await strategy._handle_ohlc(self._make_ohlc_payload(candle, interval))

                after_ids = self._get_grok_grid_pending_order_ids(strategy)
                self.total_orders_placed += len(after_ids - before_ids)
                if old_center is not None and (
                    strategy._grid_center != old_center or strategy._grid_spacing != old_spacing
                ):
                    self.rebalance_count += 1

                equity = self.usdc_balance + self.btc_held * current_price
                self.equity_curve.append((candle.timestamp, equity))
                continue

            # Feed analyzer (for grid_adaptive ATR)
            if analyzer is not None:
                ohlc_data = {
                    "timestamp": candle.timestamp,
                    "open": float(candle.open),
                    "high": float(candle.high),
                    "low": float(candle.low),
                    "close": float(candle.close),
                    "volume": float(candle.volume),
                    "interval": interval,
                }
                analyzer.update(ohlc_data, interval)

                # Track 1h prices for SMA50 (directional pause)
                if interval == 60:
                    self._hourly_prices.append(current_price)

                # Update ATR range for adaptive grid
                if is_tradeable and interval == 60:
                    analysis = analyzer.analyze()
                    if analysis is not None and analysis.volatility_atr:
                        self._update_range_from_atr(current_price, analysis.volatility_atr)

                # Check directional pause
                self._check_directional_pause(current_price)

            if not is_tradeable:
                continue

            # Initialize grid on first tradeable candle
            if not self._grid_initialized:
                if self._grid_paused:
                    continue
                self._initialize_grid(current_price)
                continue

            # Check buy fills: candle.low <= buy_price
            filled_buys = []
            remaining_buys = []
            for order in self.active_buy_orders:
                if candle.low <= order["price"]:
                    filled_buys.append(order)
                else:
                    remaining_buys.append(order)
            self.active_buy_orders = remaining_buys

            for order in filled_buys:
                self._process_buy_fill(order, candle)

            # Check sell fills: candle.high >= sell_price
            filled_sells = []
            remaining_sells = []
            for order in self.active_sell_orders:
                if candle.high >= order["price"]:
                    filled_sells.append(order)
                else:
                    remaining_sells.append(order)
            self.active_sell_orders = remaining_sells

            for order in filled_sells:
                self._process_sell_fill(order, candle)

            # Check rebalance (skip if directional pause active)
            if not self._grid_paused:
                self._check_rebalance(current_price)

            # Track equity
            equity = self.usdc_balance + self.btc_held * current_price
            self.equity_curve.append((candle.timestamp, equity))

        # Calculate final metrics
        self._calculate_final_metrics()

        return self.metrics

    async def _load_candles(
        self, pair: str, start_time: datetime, end_time: datetime
    ) -> list[OHLCData]:
        """Load OHLC candles from database."""
        return await _load_candles_chunked(
            self.db_manager,
            pair,
            self.candle_interval,
            start_time,
            end_time,
            exchange=self.exchange,
        )

    async def _load_candles_for_interval(
        self, pair: str, interval: int, start_time: datetime, end_time: datetime
    ) -> list[OHLCData]:
        """Load OHLC candles for a specific interval."""
        return await _load_candles_chunked(
            self.db_manager,
            pair,
            interval,
            start_time,
            end_time,
            exchange=self.exchange,
        )

    def _calculate_final_metrics(self) -> None:
        """Calculate final performance metrics."""
        self.metrics.total_trades = self.pairs_completed
        self.metrics.total_fees = self.total_fees
        self.metrics.net_pnl = self.metrics.total_pnl - self.total_fees

        if self.metrics.total_trades > 0:
            self.metrics.win_rate = self.metrics.winning_trades / self.metrics.total_trades

        # Average win/loss
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

        # Ending balance (include unrealized BTC value)
        if self.equity_curve:
            self.metrics.ending_balance = self.equity_curve[-1][1]
        else:
            self.metrics.ending_balance = self.usdc_balance

        # Total return
        if self.metrics.starting_balance > 0:
            self.metrics.total_return_pct = float(
                (self.metrics.ending_balance - self.metrics.starting_balance)
                / self.metrics.starting_balance
                * 100
            )

        # Max drawdown
        peak = self.metrics.starting_balance
        max_dd = Decimal("0")
        for _ts, equity in self.equity_curve:
            if equity > peak:
                peak = equity
            drawdown = peak - equity
            if drawdown > max_dd:
                max_dd = drawdown
        self.metrics.max_drawdown = max_dd
        if peak > 0:
            self.metrics.max_drawdown_pct = float((max_dd / peak) * 100)

        # Sharpe ratio
        if len(self.equity_curve) > 1:
            returns = []
            for i in range(1, len(self.equity_curve)):
                prev_eq = self.equity_curve[i - 1][1]
                curr_eq = self.equity_curve[i][1]
                if prev_eq > 0:
                    returns.append(float((curr_eq - prev_eq) / prev_eq))
            if returns:
                avg_ret = sum(returns) / len(returns)
                variance = sum((r - avg_ret) ** 2 for r in returns) / len(returns)
                std_dev = variance**0.5
                if std_dev > 0:
                    self.metrics.sharpe_ratio = (avg_ret / std_dev) * (365**0.5)

                # Sortino
                neg_returns = [r for r in returns if r < 0]
                if neg_returns:
                    ds_var = sum(r**2 for r in neg_returns) / len(returns)
                    ds_std = ds_var**0.5
                    if ds_std > 0:
                        self.metrics.sortino_ratio = (avg_ret / ds_std) * (365**0.5)

        # Calmar ratio: annualized return / max drawdown %
        if self.metrics.max_drawdown_pct > 0 and self.metrics.duration_days > 0:
            annualized_return = self.metrics.total_return_pct * (365 / self.metrics.duration_days)
            self.metrics.calmar_ratio = annualized_return / self.metrics.max_drawdown_pct

    def print_report(self) -> None:
        """Print grid-specific backtest report."""
        print("\n" + "=" * 80)
        print("GRID BACKTEST REPORT".center(80))
        print("=" * 80)

        print(f"\n{'Strategy:':<30} {self.strategy_name}")
        if self.metrics.start_time and self.metrics.end_time:
            print(
                f"{'Period:':<30} {self.metrics.start_time.date()} to {self.metrics.end_time.date()}"
            )
        print(f"{'Duration:':<30} {self.metrics.duration_days:.1f} days")

        print("\n" + "-" * 80)
        print("GRID METRICS")
        print("-" * 80)

        print(f"{'Grid Pairs Completed:':<30} {self.pairs_completed}")
        print(f"{'Grid Profit:':<30} {float(self.grid_profit):+.2f} USDC")
        print(f"{'Total Fees:':<30} {float(self.total_fees):.2f} USDC")
        print(f"{'Net Grid Profit:':<30} {float(self.grid_profit - self.total_fees):+.2f} USDC")

        print(f"{'BTC Held (unrealized):':<30} {float(self.btc_held):.6f} BTC")

        efficiency = (
            (self.pairs_completed * 2) / self.total_orders_placed * 100
            if self.total_orders_placed > 0
            else 0
        )
        print(f"{'Grid Efficiency:':<30} {efficiency:.1f}%")
        print(f"{'Total Orders Placed:':<30} {self.total_orders_placed}")
        print(f"{'Rebalances:':<30} {self.rebalance_count}")

        print("\n" + "-" * 80)
        print("PERFORMANCE SUMMARY")
        print("-" * 80)

        print(f"{'Starting Balance:':<30} {float(self.metrics.starting_balance):.2f} USDC")
        print(f"{'Ending Balance:':<30} {float(self.metrics.ending_balance):.2f} USDC")
        print(f"{'Total Return:':<30} {self.metrics.total_return_pct:+.2f}%")
        print(f"{'Net P&L:':<30} {float(self.metrics.net_pnl):+.2f} USDC")

        print("\n" + "-" * 80)
        print("RISK METRICS")
        print("-" * 80)

        print(f"{'Max Drawdown:':<30} {float(self.metrics.max_drawdown):.2f} USDC")
        print(f"{'Max Drawdown %:':<30} {self.metrics.max_drawdown_pct:.2f}%")
        print(f"{'Sharpe Ratio:':<30} {self.metrics.sharpe_ratio:.2f}")
        print(f"{'Sortino Ratio:':<30} {self.metrics.sortino_ratio:.2f}")

        print("\n" + "=" * 80 + "\n")

    async def save_to_database(self, pair: str, run_name: str | None = None) -> BacktestRun:
        """Save grid backtest results to database."""
        if run_name is None:
            run_name = f"{self.strategy_name}_{self.metrics.start_time.date()}_to_{self.metrics.end_time.date()}"

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
            win_rate=Decimal(str(round(self.metrics.win_rate, 4))),
            total_return_pct=Decimal(str(round(self.metrics.total_return_pct, 4))),
            max_drawdown=self.metrics.max_drawdown or Decimal("0"),
            max_drawdown_pct=Decimal(str(round(self.metrics.max_drawdown_pct, 4))),
            total_pnl=self.metrics.total_pnl,
            net_pnl=self.metrics.net_pnl,
            sharpe_ratio=Decimal(str(round(self.metrics.sharpe_ratio, 4))),
            sortino_ratio=Decimal(str(round(self.metrics.sortino_ratio, 4))),
            profit_factor=Decimal(str(round(self.metrics.profit_factor, 4))),
            average_win=self.metrics.average_win,
            average_loss=self.metrics.average_loss,
            total_fees=self.total_fees,
        )

        async with self.db_manager.session() as session:
            session.add(backtest_run)
            await session.commit()
            await session.refresh(backtest_run)

        return backtest_run


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
    parser.add_argument(
        "--exchange",
        type=str,
        default="kraken",
        help="Exchange data source: kraken or binance (default: kraken)",
    )
    parser.add_argument(
        "--start-date",
        type=str,
        default=None,
        help="Start date (YYYY-MM-DD). Overrides --days when set.",
    )
    parser.add_argument(
        "--capital",
        type=float,
        default=1000.0,
        help="Starting capital in USDC (default: 1000)",
    )

    args = parser.parse_args()

    # Parse dates
    if args.end_date:
        end_time = datetime.fromisoformat(args.end_date).replace(tzinfo=UTC)
    else:
        end_time = datetime.now(UTC)

    if args.start_date:
        start_time = datetime.fromisoformat(args.start_date).replace(tzinfo=UTC)
    else:
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
            total_days = int(total_duration.total_seconds() / 86400)
            print(f"\nTotal period: {start_time.date()} to {end_time.date()} ({total_days} days)")
            print(f"Train ratio: {args.train_ratio:.0%}")
            print(f"Split point: {split_time.date()}")
            print(
                f"Train: {start_time.date()} to {split_time.date()} ({int(train_duration.days)} days)"
            )
            print(
                f"Test:  {split_time.date()} to {end_time.date()} ({total_days - int(train_duration.days)} days)"
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
                exchange=args.exchange,
                starting_capital=args.capital,
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
                exchange=args.exchange,
                starting_capital=args.capital,
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
            # Standard single backtest — route grid strategies to GridBacktester
            if args.strategy in GridBacktester.GRID_STRATEGIES:
                engine = GridBacktester(
                    settings,
                    db_manager,
                    strategy_name=args.strategy,
                    candle_interval=args.interval,
                    exchange=args.exchange,
                    starting_capital=args.capital,
                )
            else:
                engine = BacktestEngine(
                    settings,
                    db_manager,
                    strategy_name=args.strategy,
                    candle_interval=args.interval,
                    exchange=args.exchange,
                    starting_capital=args.capital,
                )

            await engine.run(args.pair, start_time, end_time)

            # Print report
            engine.print_report()

            # Save to database if requested
            if args.save:
                backtest_run = await engine.save_to_database(args.pair, run_name=args.name)
                print(f"\n✅ Backtest results saved to database with ID: {backtest_run.id}")
                print(f"   Run name: {backtest_run.run_name}")

                # Save individual trades for dashboard visualization (signal-based only)
                if hasattr(engine, "save_trades_to_database"):
                    await engine.save_trades_to_database(str(backtest_run.id), args.pair)
                    print(f"   Trades saved: {len(engine.metrics.trades)}")
                print("   View in dashboard: python scripts/dashboard.py\n")

    finally:
        await db_manager.close_db()


if __name__ == "__main__":
    asyncio.run(main())
