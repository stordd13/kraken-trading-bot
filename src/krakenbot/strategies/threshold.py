"""Threshold-based mean reversion trading strategy.

This module implements a simple mean reversion strategy that:
- Buys when price drops below a threshold relative to a moving average
- Sells when profit target is reached

Example:
    >>> from krakenbot.strategies.threshold import ThresholdStrategy
    >>> strategy = ThresholdStrategy(settings, event_bus, db_manager)
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


class ThresholdStrategy(BaseStrategy):
    """Strategie simple de mean reversion basee sur des seuils.

    This strategy implements a basic mean reversion approach:
    - Maintains a moving average of recent closing prices
    - Generates BUY signal when price drops below threshold vs reference
    - Generates SELL signal when profit target is reached

    Attributes:
        buy_threshold_pct: Percentage drop to trigger buy (negative value).
        sell_threshold_pct: Percentage gain to trigger sell (positive value).
        lookback_periods: Number of periods for moving average calculation.
        pair: Trading pair being monitored.
    """

    def __init__(
        self,
        settings: Settings,
        event_bus: EventBus,
        db_manager: DatabaseManager,
    ) -> None:
        """Initialize the threshold strategy.

        Args:
            settings: Application settings with strategy configuration.
            event_bus: Event bus for pub/sub communication.
            db_manager: Database manager for position state.
        """
        super().__init__(settings, event_bus, db_manager)

        # Configuration from settings
        self.buy_threshold_pct = settings.strategy.buy_threshold_pct
        self.sell_threshold_pct = settings.strategy.sell_threshold_pct
        self.lookback_periods = settings.strategy.lookback_periods
        self.pair = settings.trading.pair

        # Internal state
        self._price_history: list[Decimal] = []
        self._current_price: Decimal | None = None
        self._reference_price: Decimal | None = None
        self._entry_price: Decimal | None = None
        self._has_position: bool = False
        self._skip_db_sync: bool = False  # Set to True in backtest mode

        self.logger.debug(
            "strategy_initialized",
            strategy=self.get_name(),
            buy_threshold_pct=self.buy_threshold_pct,
            sell_threshold_pct=self.sell_threshold_pct,
            lookback_periods=self.lookback_periods,
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

        self.logger.debug(
            "tick_processed",
            pair=self.pair,
            price=float(self._current_price),
        )

    async def on_ohlc(self, ohlc_data: dict[str, Any]) -> None:
        """Process OHLC candle and update price history.

        Args:
            ohlc_data: OHLC data with keys: timestamp, pair, open, high, low, close, volume.
        """
        if ohlc_data.get("pair") != self.pair:
            return

        close_price = Decimal(str(ohlc_data["close"]))

        # Add to price history (FIFO queue)
        self._price_history.append(close_price)
        if len(self._price_history) > self.lookback_periods:
            self._price_history.pop(0)

        # Calculate reference price (simple moving average)
        if len(self._price_history) >= self.lookback_periods:
            self._reference_price = sum(self._price_history) / len(self._price_history)

        self.logger.debug(
            "ohlc_processed",
            pair=self.pair,
            close=float(close_price),
            reference=float(self._reference_price) if self._reference_price else None,
            history_len=len(self._price_history),
        )

    async def generate_signal(self) -> TradingSignal | None:
        """Generate trading signal based on threshold logic.

        Returns:
            TradingSignal with BUY, SELL, or HOLD, or None if not ready.
        """
        # Need current price and reference price to generate signals
        if not self._current_price or not self._reference_price:
            return None

        # Update position state from database
        await self._update_position_state()

        now = datetime.now(timezone.utc)

        # DEBUG: Log strategy internal state
        self.logger.debug(
            "strategy_state_check",
            has_position=self._has_position,
            entry_price=float(self._entry_price) if self._entry_price else None,
            current_price=float(self._current_price) if self._current_price else None,
            reference_price=float(self._reference_price) if self._reference_price else None,
        )

        # SELL LOGIC: Check if profit target is reached
        if self._has_position and self._entry_price:
            profit_pct = (
                (self._current_price - self._entry_price) / self._entry_price
            ) * Decimal("100")

            self.logger.debug(
                "strategy_sell_check",
                profit_pct=float(profit_pct),
                sell_threshold_pct=self.sell_threshold_pct,
                meets_threshold=profit_pct >= Decimal(str(self.sell_threshold_pct)),
            )

            if profit_pct >= Decimal(str(self.sell_threshold_pct)):
                self.logger.info(
                    "strategy_sell_signal",
                    profit_pct=float(profit_pct),
                    entry_price=float(self._entry_price),
                    current_price=float(self._current_price),
                )
                return TradingSignal(
                    signal_type=SignalType.SELL,
                    pair=self.pair,
                    price=self._current_price,
                    confidence=0.8,
                    reason=f"Profit target reached: {float(profit_pct):.2f}% >= {self.sell_threshold_pct}%",
                    strategy=self.get_name(),
                    timestamp=now,
                    metadata={
                        "entry_price": float(self._entry_price),
                        "profit_pct": float(profit_pct),
                        "target_pct": self.sell_threshold_pct,
                    },
                )

        # BUY LOGIC: Check if price dropped enough below reference
        if not self._has_position:
            drop_pct = (
                (self._current_price - self._reference_price) / self._reference_price
            ) * Decimal("100")

            if drop_pct <= Decimal(str(self.buy_threshold_pct)):
                return TradingSignal(
                    signal_type=SignalType.BUY,
                    pair=self.pair,
                    price=self._current_price,
                    confidence=0.8,
                    reason=f"Price drop detected: {float(drop_pct):.2f}% <= {self.buy_threshold_pct}%",
                    strategy=self.get_name(),
                    timestamp=now,
                    metadata={
                        "reference_price": float(self._reference_price),
                        "drop_pct": float(drop_pct),
                        "threshold_pct": self.buy_threshold_pct,
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
        )

    async def _update_position_state(self) -> None:
        """Update position state from database.

        Reads the current bot state from the database to determine
        if we have an open position and at what entry price.

        If _skip_db_sync is True (backtest mode), skips DB read and uses internal state.
        """
        # In backtest mode, use internal state instead of DB
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
            # Keep existing state on error

    def get_name(self) -> str:
        """Return the strategy name.

        Returns:
            Strategy identifier.
        """
        return "threshold"

    def get_config(self) -> dict[str, Any]:
        """Return the strategy configuration.

        Returns:
            Dictionary with all configuration parameters.
        """
        return {
            "name": self.get_name(),
            "buy_threshold_pct": self.buy_threshold_pct,
            "sell_threshold_pct": self.sell_threshold_pct,
            "lookback_periods": self.lookback_periods,
            "pair": self.pair,
        }

    def reset_state(self) -> None:
        """Reset the strategy's internal state.

        Clears price history and position state.
        """
        super().reset_state()
        self._price_history.clear()
        self._current_price = None
        self._reference_price = None
        self._entry_price = None
        self._has_position = False
        self.logger.debug("threshold_strategy_state_reset", strategy=self.get_name())

    @property
    def current_price(self) -> Decimal | None:
        """Get the current price.

        Returns:
            Current market price or None if not set.
        """
        return self._current_price

    @property
    def reference_price(self) -> Decimal | None:
        """Get the reference price (moving average).

        Returns:
            Reference price or None if not enough data.
        """
        return self._reference_price

    @property
    def price_history_len(self) -> int:
        """Get the length of price history.

        Returns:
            Number of prices in history.
        """
        return len(self._price_history)

    @property
    def has_position(self) -> bool:
        """Check if strategy has an open position.

        Returns:
            True if position is open.
        """
        return self._has_position

    @property
    def entry_price(self) -> Decimal | None:
        """Get the entry price of current position.

        Returns:
            Entry price or None if no position.
        """
        return self._entry_price

    def set_position_state(
        self,
        has_position: bool,
        entry_price: Decimal | None = None,
    ) -> None:
        """Set position state (for testing).

        Args:
            has_position: Whether a position is open.
            entry_price: Entry price of the position.
        """
        self._has_position = has_position
        self._entry_price = entry_price
