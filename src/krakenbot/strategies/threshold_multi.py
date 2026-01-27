"""Multi-position threshold-based mean reversion strategy.

DEPRECATED/EXPERIMENTAL: This strategy is not exported and not used in
production. Use ThresholdRollingStrategy (threshold_rolling.py) instead.
Kept for reference and potential future use.

This strategy can open multiple independent positions simultaneously:
- Opens a NEW position each time price drops by threshold% vs moving average
- Each position has its own entry price and profit target
- Closes positions individually when profit target OR stop-loss is reached
- Respects max_open_positions limit from risk management

Example:
    >>> from krakenbot.strategies.threshold_multi import ThresholdMultiStrategy
    >>> strategy = ThresholdMultiStrategy(settings, event_bus, db_manager)
    >>> await strategy.start()
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from typing import TYPE_CHECKING, Any

from krakenbot.models.base import SignalType
from krakenbot.strategies.base import BaseStrategy, TradingSignal

if TYPE_CHECKING:
    from krakenbot.config.settings import Settings
    from krakenbot.core.database import DatabaseManager
    from krakenbot.core.event_bus import EventBus


@dataclass
class Position:
    """Represents a single open position."""

    entry_price: Decimal
    entry_time: datetime
    amount_usdc: Decimal  # Size of this position
    position_id: int  # Unique ID for tracking


class ThresholdMultiStrategy(BaseStrategy):
    """Multi-position threshold mean reversion strategy.

    Unlike the single-position threshold strategy, this one can open
    multiple positions simultaneously, each triggered independently
    when the price drops below the threshold.

    Attributes:
        buy_threshold_pct: Percentage drop to trigger buy (negative value).
        sell_threshold_pct: Percentage gain to trigger sell (positive value).
        stop_loss_pct: Stop-loss percentage (from settings).
        lookback_periods: Number of periods for moving average calculation.
        max_open_positions: Maximum number of simultaneous positions.
    """

    def __init__(
        self,
        settings: Settings,
        event_bus: EventBus,
        db_manager: DatabaseManager,
    ) -> None:
        """Initialize the multi-position threshold strategy.

        Args:
            settings: Application settings with strategy configuration.
            event_bus: Event bus for pub/sub communication.
            db_manager: Database manager for position state.
        """
        super().__init__(settings, event_bus, db_manager)

        # Configuration from settings
        self.buy_threshold_pct = settings.strategy.buy_threshold_pct
        self.sell_threshold_pct = settings.strategy.sell_threshold_pct
        self.stop_loss_pct = settings.risk.emergency_stop_loss_pct
        self.lookback_periods = settings.strategy.lookback_periods
        self.max_open_positions = settings.risk.max_open_positions
        self.pair = settings.trading.pair

        # Internal state
        self._price_history: list[Decimal] = []
        self._current_price: Decimal | None = None
        self._reference_price: Decimal | None = None
        self._open_positions: list[Position] = []
        self._next_position_id: int = 1
        self._skip_db_sync: bool = False
        self._last_buy_price: Decimal | None = None  # Track last buy to avoid duplicates

        self.logger.debug(
            "threshold_multi_strategy_initialized",
            strategy=self.get_name(),
            buy_threshold_pct=self.buy_threshold_pct,
            sell_threshold_pct=self.sell_threshold_pct,
            stop_loss_pct=self.stop_loss_pct,
            lookback_periods=self.lookback_periods,
            max_open_positions=self.max_open_positions,
            pair=self.pair,
        )

    async def on_tick(self, tick_data: dict[str, Any]) -> None:
        """Update current price from tick data."""
        if tick_data.get("pair") != self.pair:
            return

        self._current_price = Decimal(str(tick_data["price"]))

    async def on_ohlc(self, ohlc_data: dict[str, Any]) -> None:
        """Process OHLC candle and update price history."""
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
            open_positions=len(self._open_positions),
        )

    async def generate_signal(self) -> TradingSignal | None:
        """Generate trading signal based on threshold logic.

        Can generate multiple types of signals:
        - BUY: Open new position if conditions met
        - SELL: Close a specific position (profit target or stop-loss)
        - HOLD: No action needed

        Returns:
            TradingSignal with BUY, SELL, or HOLD, or None if not ready.
        """
        # Need current price and reference price to generate signals
        if not self._current_price or not self._reference_price:
            return None

        # Update position state from database (for live trading)
        await self._update_position_state()

        now = datetime.now(UTC)

        # SELL LOGIC: Check each open position for profit target or stop-loss
        for position in self._open_positions:
            profit_pct = (
                (self._current_price - position.entry_price) / position.entry_price
            ) * Decimal("100")

            # Check profit target
            if profit_pct >= Decimal(str(self.sell_threshold_pct)):
                return TradingSignal(
                    signal_type=SignalType.SELL,
                    pair=self.pair,
                    price=self._current_price,
                    confidence=0.9,
                    reason=f"Position #{position.position_id} profit target: {float(profit_pct):.2f}% >= {self.sell_threshold_pct}%",
                    strategy=self.get_name(),
                    timestamp=now,
                    metadata={
                        "position_id": position.position_id,
                        "entry_price": float(position.entry_price),
                        "profit_pct": float(profit_pct),
                        "reason": "profit_target",
                    },
                )

            # Check stop-loss
            if profit_pct <= -Decimal(str(self.stop_loss_pct)):
                return TradingSignal(
                    signal_type=SignalType.SELL,
                    pair=self.pair,
                    price=self._current_price,
                    confidence=1.0,
                    reason=f"Position #{position.position_id} STOP-LOSS: {float(profit_pct):.2f}% <= -{self.stop_loss_pct}%",
                    strategy=self.get_name(),
                    timestamp=now,
                    metadata={
                        "position_id": position.position_id,
                        "entry_price": float(position.entry_price),
                        "profit_pct": float(profit_pct),
                        "reason": "stop_loss",
                    },
                )

        # BUY LOGIC: Check if we can open a new position
        if len(self._open_positions) < self.max_open_positions:
            drop_pct = (
                (self._current_price - self._reference_price) / self._reference_price
            ) * Decimal("100")

            # Avoid buying at nearly the same price twice
            # (prevent duplicate buys on same candle)
            price_changed_enough = True
            if self._last_buy_price is not None:
                price_change = (
                    abs(self._current_price - self._last_buy_price) / self._last_buy_price
                )
                if price_change < Decimal("0.001"):  # Less than 0.1% change
                    price_changed_enough = False

            if drop_pct <= Decimal(str(self.buy_threshold_pct)) and price_changed_enough:
                self._last_buy_price = self._current_price
                return TradingSignal(
                    signal_type=SignalType.BUY,
                    pair=self.pair,
                    price=self._current_price,
                    confidence=0.8,
                    reason=f"Price drop detected: {float(drop_pct):.2f}% <= {self.buy_threshold_pct}% (position {len(self._open_positions) + 1}/{self.max_open_positions})",
                    strategy=self.get_name(),
                    timestamp=now,
                    metadata={
                        "reference_price": float(self._reference_price),
                        "drop_pct": float(drop_pct),
                        "threshold_pct": self.buy_threshold_pct,
                        "current_positions": len(self._open_positions),
                        "max_positions": self.max_open_positions,
                    },
                )

        # Default: HOLD
        return TradingSignal(
            signal_type=SignalType.HOLD,
            pair=self.pair,
            price=self._current_price,
            confidence=1.0,
            reason=f"No trading conditions met ({len(self._open_positions)}/{self.max_open_positions} positions)",
            strategy=self.get_name(),
            timestamp=now,
            metadata={"open_positions": len(self._open_positions)},
        )

    def add_position(
        self,
        entry_price: Decimal,
        amount_usdc: Decimal,
        entry_time: datetime | None = None,
    ) -> int:
        """Add a new position to tracking.

        Args:
            entry_price: Entry price of the position.
            amount_usdc: Size of the position in USDC.
            entry_time: Entry timestamp (default: now).

        Returns:
            Position ID.
        """
        position_id = self._next_position_id
        self._next_position_id += 1

        position = Position(
            entry_price=entry_price,
            entry_time=entry_time or datetime.now(UTC),
            amount_usdc=amount_usdc,
            position_id=position_id,
        )

        self._open_positions.append(position)

        self.logger.info(
            "position_opened",
            position_id=position_id,
            entry_price=float(entry_price),
            amount_usdc=float(amount_usdc),
            total_positions=len(self._open_positions),
        )

        return position_id

    def close_position(self, position_id: int) -> Position | None:
        """Close a position by ID.

        Args:
            position_id: ID of the position to close.

        Returns:
            The closed Position object, or None if not found.
        """
        for i, position in enumerate(self._open_positions):
            if position.position_id == position_id:
                closed_position = self._open_positions.pop(i)
                self.logger.info(
                    "position_closed",
                    position_id=position_id,
                    entry_price=float(closed_position.entry_price),
                    total_positions=len(self._open_positions),
                )
                return closed_position

        self.logger.warning(
            "position_not_found",
            position_id=position_id,
            open_positions=[p.position_id for p in self._open_positions],
        )
        return None

    async def _update_position_state(self) -> None:
        """Update position state from database.

        In multi-position mode, this would load all open positions
        from the database. For now, in backtest mode, we skip DB sync.
        """
        if self._skip_db_sync:
            return

        # TODO: Implement DB loading of multiple positions
        # For now, rely on in-memory state
        pass

    def get_name(self) -> str:
        """Return the strategy name."""
        return "threshold_multi"

    def get_config(self) -> dict[str, Any]:
        """Return the strategy configuration."""
        return {
            "name": self.get_name(),
            "buy_threshold_pct": self.buy_threshold_pct,
            "sell_threshold_pct": self.sell_threshold_pct,
            "stop_loss_pct": self.stop_loss_pct,
            "lookback_periods": self.lookback_periods,
            "max_open_positions": self.max_open_positions,
            "pair": self.pair,
        }

    def reset_state(self) -> None:
        """Reset the strategy's internal state."""
        super().reset_state()
        self._price_history.clear()
        self._current_price = None
        self._reference_price = None
        self._open_positions.clear()
        self._next_position_id = 1
        self._last_buy_price = None
        self.logger.debug("threshold_multi_strategy_state_reset", strategy=self.get_name())

    @property
    def open_positions_count(self) -> int:
        """Get the number of open positions."""
        return len(self._open_positions)

    @property
    def open_positions(self) -> list[Position]:
        """Get list of open positions."""
        return self._open_positions.copy()

    @property
    def current_price(self) -> Decimal | None:
        """Get the current market price."""
        return self._current_price

    @property
    def reference_price(self) -> Decimal | None:
        """Get the reference price (moving average)."""
        return self._reference_price

    @property
    def has_position(self) -> bool:
        """Check if strategy has any open positions."""
        return len(self._open_positions) > 0
