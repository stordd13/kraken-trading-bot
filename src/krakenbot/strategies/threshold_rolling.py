"""Rolling reference threshold-based mean reversion strategy.

This strategy maintains multiple reference prices (rolling window):
- Each candle's close price becomes a reference
- Opens a NEW position when price drops by threshold% vs ANY reference
- Each reference can only trigger ONE position (no duplicates)
- Closes positions individually when profit target OR stop-loss is reached
- Tracks position holding time for analytics

Example:
    >>> from krakenbot.strategies.threshold_rolling import ThresholdRollingStrategy
    >>> strategy = ThresholdRollingStrategy(settings, event_bus, db_manager)
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
class RollingPosition:
    """Represents a single open position with reference tracking."""

    entry_price: Decimal
    entry_time: datetime
    amount_usdc: Decimal  # Size of this position
    position_id: int  # Unique ID for tracking
    reference_price: Decimal  # The reference price that triggered this position


class ThresholdRollingStrategy(BaseStrategy):
    """Rolling reference threshold mean reversion strategy.

    This strategy maintains a rolling window of reference prices:
    - Each candle's close becomes a reference (up to lookback_periods)
    - Opens position when price drops threshold% vs ANY reference
    - Each reference can only trigger ONE position (avoids duplicates)
    - Tracks holding time for each position

    Attributes:
        buy_threshold_pct: Percentage drop to trigger buy (negative value).
        sell_threshold_pct: Percentage gain to trigger sell (positive value).
        stop_loss_pct: Stop-loss percentage (from settings).
        lookback_periods: Number of reference prices to maintain.
        max_open_positions: Maximum number of simultaneous positions.
    """

    def __init__(
        self,
        settings: Settings,
        event_bus: EventBus,
        db_manager: DatabaseManager,
    ) -> None:
        """Initialize the rolling reference threshold strategy.

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
        self._reference_prices: list[Decimal] = []  # Rolling window of reference prices
        self._current_price: Decimal | None = None
        self._current_timestamp: datetime | None = (
            None  # Track current candle time for holding calculations
        )
        self._open_positions: list[RollingPosition] = []
        self._next_position_id: int = 1
        self._skip_db_sync: bool = False
        self._used_references: set[Decimal] = set()  # Track which refs already have positions

        self.logger.debug(
            "threshold_rolling_strategy_initialized",
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
        """Process OHLC candle and update reference prices."""
        if ohlc_data.get("pair") != self.pair:
            return

        close_price = Decimal(str(ohlc_data["close"]))

        # Store timestamp for holding time calculations
        if "timestamp" in ohlc_data:
            timestamp_value = ohlc_data["timestamp"]
            # Convert to datetime if it's a string or float (Unix timestamp)
            if isinstance(timestamp_value, str):
                # Parse ISO format or Unix timestamp string
                try:
                    self._current_timestamp = datetime.fromisoformat(
                        timestamp_value.replace("Z", "+00:00")
                    )
                except ValueError:
                    # Try as Unix timestamp
                    self._current_timestamp = datetime.fromtimestamp(float(timestamp_value), tz=UTC)
            elif isinstance(timestamp_value, (int, float)):
                # Unix timestamp
                self._current_timestamp = datetime.fromtimestamp(timestamp_value, tz=UTC)
            elif isinstance(timestamp_value, datetime):
                self._current_timestamp = timestamp_value
            else:
                self._current_timestamp = datetime.now(UTC)
        else:
            self._current_timestamp = datetime.now(UTC)

        # Add this candle's close as a new reference price
        self._reference_prices.append(close_price)

        # Maintain rolling window (FIFO)
        if len(self._reference_prices) > self.lookback_periods:
            removed_ref = self._reference_prices.pop(0)
            # Clean up used_references if the old reference is removed
            self._used_references.discard(removed_ref)

        self.logger.debug(
            "ohlc_processed",
            pair=self.pair,
            close=float(close_price),
            num_references=len(self._reference_prices),
            open_positions=len(self._open_positions),
        )

    async def generate_signal(self) -> TradingSignal | None:
        """Generate trading signal based on rolling reference logic.

        Can generate multiple types of signals:
        - BUY: Open new position if price drops vs any unused reference
        - SELL: Close a specific position (profit target or stop-loss)
        - HOLD: No action needed

        Returns:
            TradingSignal with BUY, SELL, or HOLD, or None if not ready.
        """
        # Need current price and at least one reference to generate signals
        if not self._current_price or not self._reference_prices:
            return None

        # Update position state from database (for live trading)
        await self._update_position_state()

        # Use current candle timestamp for calculations (or fallback to now)
        current_time = self._current_timestamp or datetime.now(UTC)

        # SELL LOGIC: Check each open position for profit target or stop-loss
        for position in self._open_positions:
            profit_pct = (
                (self._current_price - position.entry_price) / position.entry_price
            ) * Decimal("100")

            # Calculate holding time using candle timestamp
            holding_time = current_time - position.entry_time
            holding_minutes = holding_time.total_seconds() / 60

            # Check profit target
            if profit_pct >= Decimal(str(self.sell_threshold_pct)):
                return TradingSignal(
                    signal_type=SignalType.SELL,
                    pair=self.pair,
                    price=self._current_price,
                    confidence=0.9,
                    reason=f"Position #{position.position_id} profit target: {float(profit_pct):.2f}% >= {self.sell_threshold_pct}% (held {holding_minutes:.1f} min)",
                    strategy=self.get_name(),
                    timestamp=current_time,
                    metadata={
                        "position_id": position.position_id,
                        "entry_price": float(position.entry_price),
                        "reference_price": float(position.reference_price),
                        "profit_pct": float(profit_pct),
                        "holding_time_minutes": holding_minutes,
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
                    reason=f"Position #{position.position_id} STOP-LOSS: {float(profit_pct):.2f}% <= -{self.stop_loss_pct}% (held {holding_minutes:.1f} min)",
                    strategy=self.get_name(),
                    timestamp=current_time,
                    metadata={
                        "position_id": position.position_id,
                        "entry_price": float(position.entry_price),
                        "reference_price": float(position.reference_price),
                        "profit_pct": float(profit_pct),
                        "holding_time_minutes": holding_minutes,
                        "reason": "stop_loss",
                    },
                )

        # BUY LOGIC: Check if we can open a new position
        if len(self._open_positions) < self.max_open_positions:
            # Check ALL reference prices in the rolling window
            for ref_price in self._reference_prices:
                # Skip if this reference already has an open position
                if ref_price in self._used_references:
                    continue

                # Calculate drop percentage vs this reference
                drop_pct = ((self._current_price - ref_price) / ref_price) * Decimal("100")

                # Check if threshold is met
                if drop_pct <= Decimal(str(self.buy_threshold_pct)):
                    # Mark this reference as used
                    self._used_references.add(ref_price)

                    return TradingSignal(
                        signal_type=SignalType.BUY,
                        pair=self.pair,
                        price=self._current_price,
                        confidence=0.8,
                        reason=f"Price drop vs reference: {float(drop_pct):.2f}% <= {self.buy_threshold_pct}% (position {len(self._open_positions) + 1}/{self.max_open_positions})",
                        strategy=self.get_name(),
                        timestamp=current_time,
                        metadata={
                            "reference_price": float(ref_price),
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
            reason=f"No trading conditions met ({len(self._open_positions)}/{self.max_open_positions} positions, {len(self._reference_prices)} refs)",
            strategy=self.get_name(),
            timestamp=current_time,
            metadata={
                "open_positions": len(self._open_positions),
                "num_references": len(self._reference_prices),
                "used_references": len(self._used_references),
            },
        )

    def add_position(
        self,
        entry_price: Decimal,
        amount_usdc: Decimal,
        reference_price: Decimal,
        entry_time: datetime | None = None,
    ) -> int:
        """Add a new position to tracking.

        Args:
            entry_price: Entry price of the position.
            amount_usdc: Size of the position in USDC.
            reference_price: The reference price that triggered this position.
            entry_time: Entry timestamp (default: now).

        Returns:
            Position ID.
        """
        position_id = self._next_position_id
        self._next_position_id += 1

        position = RollingPosition(
            entry_price=entry_price,
            entry_time=entry_time or datetime.now(UTC),
            amount_usdc=amount_usdc,
            position_id=position_id,
            reference_price=reference_price,
        )

        self._open_positions.append(position)
        self._used_references.add(reference_price)

        self.logger.info(
            "position_opened",
            position_id=position_id,
            entry_price=float(entry_price),
            reference_price=float(reference_price),
            amount_usdc=float(amount_usdc),
            total_positions=len(self._open_positions),
        )

        return position_id

    def close_position(self, position_id: int) -> RollingPosition | None:
        """Close a position by ID.

        Args:
            position_id: ID of the position to close.

        Returns:
            The closed RollingPosition object, or None if not found.
        """
        for i, position in enumerate(self._open_positions):
            if position.position_id == position_id:
                closed_position = self._open_positions.pop(i)

                # Calculate holding time
                now = datetime.now(UTC)

                holding_time = now - closed_position.entry_time
                holding_minutes = holding_time.total_seconds() / 60

                self.logger.info(
                    "position_closed",
                    position_id=position_id,
                    entry_price=float(closed_position.entry_price),
                    reference_price=float(closed_position.reference_price),
                    holding_time_minutes=holding_minutes,
                    total_positions=len(self._open_positions),
                )

                # Note: We keep the reference in _used_references
                # It will be cleaned up when it leaves the rolling window
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
        return "threshold_rolling"

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
        self._reference_prices.clear()
        self._current_price = None
        self._open_positions.clear()
        self._used_references.clear()
        self._next_position_id = 1
        self.logger.debug("threshold_rolling_strategy_state_reset", strategy=self.get_name())

    @property
    def open_positions_count(self) -> int:
        """Get the number of open positions."""
        return len(self._open_positions)

    @property
    def open_positions(self) -> list[RollingPosition]:
        """Get list of open positions."""
        return self._open_positions.copy()

    @property
    def current_price(self) -> Decimal | None:
        """Get the current market price."""
        return self._current_price

    @property
    def reference_prices(self) -> list[Decimal]:
        """Get all reference prices in the rolling window."""
        return self._reference_prices.copy()

    @property
    def reference_price(self) -> Decimal | None:
        """Get the most recent reference price (for backward compatibility with main.py)."""
        return self._reference_prices[-1] if self._reference_prices else None

    @property
    def has_position(self) -> bool:
        """Check if strategy has any open positions."""
        return len(self._open_positions) > 0

    @property
    def entry_price(self) -> Decimal | None:
        """Get entry price of the first open position (for backward compatibility with main.py)."""
        return self._open_positions[0].entry_price if self._open_positions else None

    @property
    def price_history_len(self) -> int:
        """Get the length of price history (number of reference prices)."""
        return len(self._reference_prices)
