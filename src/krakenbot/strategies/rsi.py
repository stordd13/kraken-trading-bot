"""RSI-based mean reversion trading strategy.

This module implements a classic RSI (Relative Strength Index) strategy:
- Buy when RSI < 30 (oversold)
- Sell when RSI > 70 (overbought) OR profit target reached

The RSI is a momentum oscillator that measures the speed and magnitude
of recent price changes to evaluate overbought or oversold conditions.

Example:
    >>> from krakenbot.strategies.rsi import RSIStrategy
    >>> strategy = RSIStrategy(settings, event_bus, db_manager)
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


class RSIStrategy(BaseStrategy):
    """RSI-based mean reversion strategy.

    Uses the Relative Strength Index to identify oversold (buy)
    and overbought (sell) conditions.

    Attributes:
        rsi_period: Number of periods for RSI calculation (default: 14)
        rsi_oversold: RSI threshold for buy signals (default: 30)
        rsi_overbought: RSI threshold for sell signals (default: 70)
        profit_target_pct: Profit target to close position (default: 2.0%)
    """

    def __init__(
        self,
        settings: Settings,
        event_bus: EventBus,
        db_manager: DatabaseManager,
        rsi_period: int = 14,
        rsi_oversold: float = 30.0,
        rsi_overbought: float = 70.0,
        profit_target_pct: float = 2.0,
    ) -> None:
        """Initialize the RSI strategy.

        Args:
            settings: Application settings.
            event_bus: Event bus for pub/sub communication.
            db_manager: Database manager for position state.
            rsi_period: Number of periods for RSI calculation.
            rsi_oversold: RSI threshold for buy signals.
            rsi_overbought: RSI threshold for sell signals.
            profit_target_pct: Profit target percentage.
        """
        super().__init__(settings, event_bus, db_manager)

        # Configuration
        self.rsi_period = rsi_period
        self.rsi_oversold = Decimal(str(rsi_oversold))
        self.rsi_overbought = Decimal(str(rsi_overbought))
        self.profit_target_pct = Decimal(str(profit_target_pct))
        self.pair = settings.trading.pair

        # Internal state
        self._price_history: list[Decimal] = []
        self._current_price: Decimal | None = None
        self._rsi: Decimal | None = None
        self._entry_price: Decimal | None = None
        self._has_position: bool = False
        self._skip_db_sync: bool = False  # Set to True in backtest mode

        self.logger.debug(
            "rsi_strategy_initialized",
            strategy=self.get_name(),
            rsi_period=rsi_period,
            rsi_oversold=float(rsi_oversold),
            rsi_overbought=float(rsi_overbought),
            profit_target_pct=float(profit_target_pct),
            pair=self.pair,
        )

    async def on_tick(self, tick_data: dict[str, Any]) -> None:
        """Update current price from tick data.

        Args:
            tick_data: Tick data with keys: timestamp, pair, price, volume, side.
        """
        if tick_data.get("pair") != self.pair:
            return

        self._current_price = Decimal(str(tick_data["price"]))

    async def on_ohlc(self, ohlc_data: dict[str, Any]) -> None:
        """Process OHLC candle and update RSI.

        Args:
            ohlc_data: OHLC data with keys: timestamp, pair, open, high, low, close, volume.
        """
        if ohlc_data.get("pair") != self.pair:
            return

        close_price = Decimal(str(ohlc_data["close"]))

        # Add to price history
        self._price_history.append(close_price)

        # Keep only necessary history (RSI period + 1)
        if len(self._price_history) > self.rsi_period + 1:
            self._price_history.pop(0)

        # Calculate RSI if we have enough data
        if len(self._price_history) >= self.rsi_period + 1:
            self._rsi = self._calculate_rsi()

        self.logger.debug(
            "ohlc_processed",
            pair=self.pair,
            close=float(close_price),
            rsi=float(self._rsi) if self._rsi else None,
            history_len=len(self._price_history),
        )

    def _calculate_rsi(self) -> Decimal:
        """Calculate RSI from price history.

        Returns:
            RSI value (0-100)
        """
        if len(self._price_history) < self.rsi_period + 1:
            return Decimal("50")  # Neutral RSI if not enough data

        # Calculate price changes
        gains = []
        losses = []

        for i in range(1, len(self._price_history)):
            change = self._price_history[i] - self._price_history[i - 1]
            if change > 0:
                gains.append(change)
                losses.append(Decimal("0"))
            else:
                gains.append(Decimal("0"))
                losses.append(abs(change))

        # Use only the last rsi_period changes
        gains = gains[-self.rsi_period :]
        losses = losses[-self.rsi_period :]

        # Calculate average gain and loss
        avg_gain = sum(gains) / self.rsi_period
        avg_loss = sum(losses) / self.rsi_period

        # Avoid division by zero
        if avg_loss == 0:
            return Decimal("100")

        # Calculate RS and RSI
        rs = avg_gain / avg_loss
        rsi = Decimal("100") - (Decimal("100") / (Decimal("1") + rs))

        return rsi

    async def generate_signal(self) -> TradingSignal | None:
        """Generate trading signal based on RSI.

        Returns:
            TradingSignal with BUY, SELL, or HOLD, or None if not ready.
        """
        # Need current price and RSI to generate signals
        if not self._current_price or self._rsi is None:
            return None

        # Update position state from database
        await self._update_position_state()

        now = datetime.now(timezone.utc)

        # SELL LOGIC 1: Check if profit target is reached
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
                        "rsi": float(self._rsi),
                    },
                )

        # SELL LOGIC 2: RSI overbought
        if self._has_position and self._rsi >= self.rsi_overbought:
            return TradingSignal(
                signal_type=SignalType.SELL,
                pair=self.pair,
                price=self._current_price,
                confidence=0.7,
                reason=f"RSI overbought: {float(self._rsi):.1f} >= {float(self.rsi_overbought)}",
                strategy=self.get_name(),
                timestamp=now,
                metadata={
                    "rsi": float(self._rsi),
                    "rsi_threshold": float(self.rsi_overbought),
                },
            )

        # BUY LOGIC: RSI oversold
        if not self._has_position and self._rsi <= self.rsi_oversold:
            return TradingSignal(
                signal_type=SignalType.BUY,
                pair=self.pair,
                price=self._current_price,
                confidence=0.7,
                reason=f"RSI oversold: {float(self._rsi):.1f} <= {float(self.rsi_oversold)}",
                strategy=self.get_name(),
                timestamp=now,
                metadata={
                    "rsi": float(self._rsi),
                    "rsi_threshold": float(self.rsi_oversold),
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
            metadata={"rsi": float(self._rsi) if self._rsi else None},
        )

    async def _update_position_state(self) -> None:
        """Update position state from database.

        If _skip_db_sync is True (backtest mode), skips DB read.
        """
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
        return "rsi"

    def get_config(self) -> dict[str, Any]:
        """Return the strategy configuration."""
        return {
            "name": self.get_name(),
            "rsi_period": self.rsi_period,
            "rsi_oversold": float(self.rsi_oversold),
            "rsi_overbought": float(self.rsi_overbought),
            "profit_target_pct": float(self.profit_target_pct),
            "pair": self.pair,
        }

    def reset_state(self) -> None:
        """Reset the strategy's internal state."""
        super().reset_state()
        self._price_history.clear()
        self._current_price = None
        self._rsi = None
        self._entry_price = None
        self._has_position = False
        self.logger.debug("rsi_strategy_state_reset", strategy=self.get_name())

    def set_position_state(
        self,
        has_position: bool,
        entry_price: Decimal | None = None,
    ) -> None:
        """Set position state (for testing/backtest).

        Args:
            has_position: Whether a position is open.
            entry_price: Entry price of the position.
        """
        self._has_position = has_position
        self._entry_price = entry_price

    @property
    def current_rsi(self) -> Decimal | None:
        """Get the current RSI value."""
        return self._rsi
