"""MACD crossover trading strategy.

This module implements a trend-following MACD (Moving Average Convergence Divergence) strategy:
- Buy when MACD line crosses above signal line (bullish crossover)
- Sell when MACD line crosses below signal line (bearish crossover) OR profit target reached

MACD is a trend-following momentum indicator that shows the relationship between
two moving averages of a security's price.

Example:
    >>> from krakenbot.strategies.macd import MACDStrategy
    >>> strategy = MACDStrategy(settings, event_bus, db_manager)
    >>> await strategy.start()
"""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from typing import TYPE_CHECKING, Any

from sqlalchemy import select

from krakenbot.models.base import SignalType
from krakenbot.models.trades import BotState
from krakenbot.strategies.base import BaseStrategy, TradingSignal

if TYPE_CHECKING:
    from krakenbot.config.settings import Settings
    from krakenbot.core.database import DatabaseManager
    from krakenbot.core.event_bus import EventBus


class MACDStrategy(BaseStrategy):
    """MACD crossover trend-following strategy.

    Uses MACD (Moving Average Convergence Divergence) to identify trend changes:
    - MACD = EMA(12) - EMA(26)
    - Signal = EMA(9) of MACD
    - Buy when MACD crosses above Signal
    - Sell when MACD crosses below Signal

    Attributes:
        fast_period: Fast EMA period (default: 12)
        slow_period: Slow EMA period (default: 26)
        signal_period: Signal line EMA period (default: 9)
        profit_target_pct: Profit target to close position (default: 2.5%)
    """

    def __init__(
        self,
        settings: Settings,
        event_bus: EventBus,
        db_manager: DatabaseManager,
        fast_period: int = 12,
        slow_period: int = 26,
        signal_period: int = 9,
        profit_target_pct: float = 2.5,
    ) -> None:
        """Initialize the MACD strategy.

        Args:
            settings: Application settings.
            event_bus: Event bus for pub/sub communication.
            db_manager: Database manager for position state.
            fast_period: Fast EMA period.
            slow_period: Slow EMA period.
            signal_period: Signal line EMA period.
            profit_target_pct: Profit target percentage.
        """
        super().__init__(settings, event_bus, db_manager)

        # Configuration
        self.fast_period = fast_period
        self.slow_period = slow_period
        self.signal_period = signal_period
        self.profit_target_pct = Decimal(str(profit_target_pct))
        self.pair = settings.trading.pair

        # Internal state
        self._price_history: list[Decimal] = []
        self._current_price: Decimal | None = None
        self._fast_ema: Decimal | None = None
        self._slow_ema: Decimal | None = None
        self._macd: Decimal | None = None
        self._signal: Decimal | None = None
        self._prev_macd: Decimal | None = None
        self._prev_signal: Decimal | None = None
        self._entry_price: Decimal | None = None
        self._has_position: bool = False
        self._skip_db_sync: bool = False

        self.logger.debug(
            "macd_strategy_initialized",
            strategy=self.get_name(),
            fast_period=fast_period,
            slow_period=slow_period,
            signal_period=signal_period,
            profit_target_pct=float(profit_target_pct),
            pair=self.pair,
        )

    async def on_tick(self, tick_data: dict[str, Any]) -> None:
        """Update current price from tick data."""
        if tick_data.get("pair") != self.pair:
            return

        self._current_price = Decimal(str(tick_data["price"]))

    async def on_ohlc(self, ohlc_data: dict[str, Any]) -> None:
        """Process OHLC candle and update MACD."""
        if ohlc_data.get("pair") != self.pair:
            return

        close_price = Decimal(str(ohlc_data["close"]))

        # Add to price history
        self._price_history.append(close_price)

        # Calculate EMAs and MACD
        if len(self._price_history) >= self.slow_period:
            # Calculate fast and slow EMAs
            self._fast_ema = self._calculate_ema(self._price_history, self.fast_period)
            self._slow_ema = self._calculate_ema(self._price_history, self.slow_period)

            # Calculate MACD
            if self._fast_ema and self._slow_ema:
                new_macd = self._fast_ema - self._slow_ema

                # Update signal line (EMA of MACD)
                if self._signal is None:
                    self._signal = new_macd  # Initialize
                else:
                    multiplier = Decimal("2") / (self.signal_period + 1)
                    self._signal = (new_macd - self._signal) * multiplier + self._signal

                # Store previous values for crossover detection
                self._prev_macd = self._macd
                self._prev_signal = self._signal
                self._macd = new_macd

        self.logger.debug(
            "ohlc_processed",
            pair=self.pair,
            close=float(close_price),
            macd=float(self._macd) if self._macd else None,
            signal=float(self._signal) if self._signal else None,
            history_len=len(self._price_history),
        )

    def _calculate_ema(self, prices: list[Decimal], period: int) -> Decimal | None:
        """Calculate Exponential Moving Average.

        Args:
            prices: List of prices.
            period: EMA period.

        Returns:
            EMA value or None if not enough data.
        """
        if len(prices) < period:
            return None

        # Use SMA as initial EMA
        ema = sum(prices[:period]) / period

        # Calculate EMA for remaining prices
        multiplier = Decimal("2") / (period + 1)
        for price in prices[period:]:
            ema = (price - ema) * multiplier + ema

        return ema

    async def generate_signal(self) -> TradingSignal | None:
        """Generate trading signal based on MACD crossover."""
        # Need current price and MACD values
        if (
            not self._current_price
            or self._macd is None
            or self._signal is None
            or self._prev_macd is None
            or self._prev_signal is None
        ):
            return None

        # Update position state from database
        await self._update_position_state()

        now = datetime.now(timezone.utc)

        # SELL LOGIC 1: Profit target reached
        if self._has_position and self._entry_price:
            profit_pct = (
                (self._current_price - self._entry_price) / self._entry_price
            ) * Decimal("100")

            if profit_pct >= self.profit_target_pct:
                return TradingSignal(
                    signal_type=SignalType.SELL,
                    pair=self.pair,
                    price=self._current_price,
                    confidence=0.9,
                    reason=f"Profit target reached: {float(profit_pct):.2f}% >= {float(self.profit_target_pct)}%",
                    strategy=self.get_name(),
                    timestamp=now,
                    metadata={
                        "entry_price": float(self._entry_price),
                        "profit_pct": float(profit_pct),
                        "macd": float(self._macd),
                        "signal": float(self._signal),
                    },
                )

        # SELL LOGIC 2: Bearish crossover (MACD crosses below Signal)
        if self._has_position:
            if self._prev_macd >= self._prev_signal and self._macd < self._signal:
                return TradingSignal(
                    signal_type=SignalType.SELL,
                    pair=self.pair,
                    price=self._current_price,
                    confidence=0.7,
                    reason=f"MACD bearish crossover: {float(self._macd):.2f} < {float(self._signal):.2f}",
                    strategy=self.get_name(),
                    timestamp=now,
                    metadata={
                        "macd": float(self._macd),
                        "signal": float(self._signal),
                    },
                )

        # BUY LOGIC: Bullish crossover (MACD crosses above Signal)
        if not self._has_position:
            if self._prev_macd <= self._prev_signal and self._macd > self._signal:
                return TradingSignal(
                    signal_type=SignalType.BUY,
                    pair=self.pair,
                    price=self._current_price,
                    confidence=0.7,
                    reason=f"MACD bullish crossover: {float(self._macd):.2f} > {float(self._signal):.2f}",
                    strategy=self.get_name(),
                    timestamp=now,
                    metadata={
                        "macd": float(self._macd),
                        "signal": float(self._signal),
                    },
                )

        # Default: HOLD
        return TradingSignal(
            signal_type=SignalType.HOLD,
            pair=self.pair,
            price=self._current_price,
            confidence=1.0,
            reason="No trading conditions met",
            strategy=self.get_name(),
            timestamp=now,
            metadata={
                "macd": float(self._macd) if self._macd else None,
                "signal": float(self._signal) if self._signal else None,
            },
        )

    async def _update_position_state(self) -> None:
        """Update position state from database."""
        if self._skip_db_sync:
            return

        try:
            async with self.db_manager.read_session() as session:
                result = await session.execute(
                    select(BotState).where(BotState.bot_id == self.get_name())
                )
                bot_state = result.scalar_one_or_none()

                if bot_state:
                    self._has_position = bot_state.has_position
                    self._entry_price = bot_state.entry_price
                else:
                    self._has_position = False
                    self._entry_price = None
        except Exception as e:
            self.logger.warning(
                "position_state_update_failed",
                error=str(e),
                error_type=type(e).__name__,
                strategy=self.get_name(),
            )

    def get_name(self) -> str:
        """Return the strategy name."""
        return "macd"

    def get_config(self) -> dict[str, Any]:
        """Return the strategy configuration."""
        return {
            "name": self.get_name(),
            "fast_period": self.fast_period,
            "slow_period": self.slow_period,
            "signal_period": self.signal_period,
            "profit_target_pct": float(self.profit_target_pct),
            "pair": self.pair,
        }

    def reset_state(self) -> None:
        """Reset the strategy's internal state."""
        super().reset_state()
        self._price_history.clear()
        self._current_price = None
        self._fast_ema = None
        self._slow_ema = None
        self._macd = None
        self._signal = None
        self._prev_macd = None
        self._prev_signal = None
        self._entry_price = None
        self._has_position = False
        self.logger.debug("macd_strategy_state_reset", strategy=self.get_name())

    def set_position_state(
        self,
        has_position: bool,
        entry_price: Decimal | None = None,
    ) -> None:
        """Set position state (for testing/backtest)."""
        self._has_position = has_position
        self._entry_price = entry_price
