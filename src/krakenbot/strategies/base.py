"""Base strategy module with abstract class and trading signal.

This module provides the foundation for all trading strategies including:
- TradingSignal: Dataclass for trading signal with metadata
- BaseStrategy: Abstract base class that all strategies must inherit from

Example:
    >>> from krakenbot.strategies.base import BaseStrategy, TradingSignal, SignalType
    >>> class MyStrategy(BaseStrategy):
    ...     async def on_tick(self, tick_data: dict[str, Any]) -> None:
    ...         self._current_price = Decimal(str(tick_data["price"]))
    ...     async def on_ohlc(self, ohlc_data: dict[str, Any]) -> None:
    ...         # Process OHLC data
    ...         pass
    ...     async def generate_signal(self) -> TradingSignal | None:
    ...         return TradingSignal(...)
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from typing import TYPE_CHECKING, Any

from krakenbot.core.event_bus import EventType
from krakenbot.core.logger import get_logger
from krakenbot.models.base import SignalType

if TYPE_CHECKING:
    from krakenbot.config.settings import Settings
    from krakenbot.core.database import DatabaseManager
    from krakenbot.core.event_bus import EventBus


@dataclass
class TradingSignal:
    """Signal de trading avec metadonnees.

    A trading signal represents a decision to buy, sell, or hold based on
    market analysis performed by a strategy.

    Attributes:
        signal_type: Type of signal (BUY/SELL/HOLD).
        pair: Trading pair (e.g., "XBT/EUR").
        price: Current price at signal generation time.
        confidence: Confidence level from 0.0 to 1.0.
        reason: Human-readable explanation of the signal.
        strategy: Name of the strategy that generated the signal.
        timestamp: When the signal was generated (UTC).
        metadata: Additional data for analysis (optional).
    """

    signal_type: SignalType
    pair: str
    price: Decimal
    confidence: float
    reason: str
    strategy: str
    timestamp: datetime
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        """Validate signal data after initialization."""
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError(f"Confidence must be between 0.0 and 1.0, got {self.confidence}")
        if not self.pair:
            raise ValueError("Pair cannot be empty")
        if not self.strategy:
            raise ValueError("Strategy name cannot be empty")
        if self.timestamp.tzinfo is None:
            raise ValueError("Timestamp must be timezone-aware (UTC)")

    @property
    def should_trade(self) -> bool:
        """Check if the signal is actionable (not HOLD).

        Returns:
            True if the signal is BUY or SELL, False if HOLD.
        """
        return self.signal_type != SignalType.HOLD

    @property
    def is_buy(self) -> bool:
        """Check if this is a buy signal.

        Returns:
            True if signal type is BUY.
        """
        return self.signal_type == SignalType.BUY

    @property
    def is_sell(self) -> bool:
        """Check if this is a sell signal.

        Returns:
            True if signal type is SELL.
        """
        return self.signal_type == SignalType.SELL

    def to_dict(self) -> dict[str, Any]:
        """Convert signal to dictionary for serialization.

        Returns:
            Dictionary representation of the signal.
        """
        return {
            "signal_type": self.signal_type.value,
            "pair": self.pair,
            "price": str(self.price),
            "confidence": self.confidence,
            "reason": self.reason,
            "strategy": self.strategy,
            "timestamp": self.timestamp.isoformat(),
            "metadata": self.metadata,
        }


class BaseStrategy(ABC):
    """Classe de base abstraite pour toutes les strategies de trading.

    All trading strategies must inherit from this class and implement
    the abstract methods. The base class provides common functionality
    for event handling, logging, and lifecycle management.

    Attributes:
        settings: Application settings.
        event_bus: Event bus for pub/sub communication.
        db_manager: Database manager for persistence.
        logger: Structured logger instance.
    """

    def __init__(
        self,
        settings: Settings,
        event_bus: EventBus,
        db_manager: DatabaseManager,
    ) -> None:
        """Initialize strategy.

        Args:
            settings: Application settings.
            event_bus: Event bus for pub/sub.
            db_manager: Database manager.
        """
        self.settings = settings
        self.event_bus = event_bus
        self.db_manager = db_manager
        self.logger = get_logger(self.__class__.__name__)

        # State tracking
        self._running: bool = False
        self._last_signal_at: datetime | None = None

    @abstractmethod
    async def on_tick(self, tick_data: dict[str, Any]) -> None:
        """Handle incoming tick data.

        This method is called for each new tick received from the market.
        Implementations should update internal state based on the tick.

        Args:
            tick_data: Tick data with keys: timestamp, pair, price, volume, side.
        """
        pass

    @abstractmethod
    async def on_ohlc(self, ohlc_data: dict[str, Any]) -> None:
        """Handle incoming OHLC candle data.

        This method is called when a new OHLC candle is received.
        Implementations should update indicators and analysis state.

        Args:
            ohlc_data: OHLC data with keys: timestamp, pair, open, high, low, close, volume.
        """
        pass

    @abstractmethod
    async def generate_signal(self) -> TradingSignal | None:
        """Generate a trading signal based on current market state.

        This method is called after processing OHLC data to determine
        if a trade should be executed.

        Returns:
            TradingSignal if a signal is generated, None otherwise.
        """
        pass

    @abstractmethod
    def get_name(self) -> str:
        """Return the strategy name.

        Returns:
            Unique identifier for the strategy.
        """
        pass

    @abstractmethod
    def get_config(self) -> dict[str, Any]:
        """Return the strategy configuration.

        Returns:
            Dictionary with all configuration parameters.
        """
        pass

    async def start(self) -> None:
        """Start the strategy.

        Subscribes to market events and sets the running state.
        """
        self._running = True
        self.logger.info("strategy_started", strategy=self.get_name())

        # Subscribe to market events
        await self.event_bus.subscribe(EventType.MARKET_TICK, self._handle_tick)
        await self.event_bus.subscribe(EventType.MARKET_OHLC, self._handle_ohlc)

    async def stop(self) -> None:
        """Stop the strategy.

        Unsubscribes from market events and clears the running state.
        """
        self._running = False
        self.logger.info("strategy_stopped", strategy=self.get_name())

        # Unsubscribe from events
        await self.event_bus.unsubscribe(EventType.MARKET_TICK, self._handle_tick)
        await self.event_bus.unsubscribe(EventType.MARKET_OHLC, self._handle_ohlc)

    async def _handle_tick(self, data: dict[str, Any]) -> None:
        """Internal handler for tick events.

        Args:
            data: Tick event data.
        """
        if not self._running:
            return

        try:
            await self.on_tick(data)
        except Exception as e:
            self.logger.error(
                "tick_handler_error",
                error=str(e),
                error_type=type(e).__name__,
                strategy=self.get_name(),
                exc_info=e,
            )

    async def _handle_ohlc(self, data: dict[str, Any]) -> None:
        """Internal handler for OHLC events.

        Processes OHLC data and generates signals if conditions are met.

        Args:
            data: OHLC event data.
        """
        if not self._running:
            return

        try:
            await self.on_ohlc(data)

            # Generate signal after processing OHLC
            signal = await self.generate_signal()
            if signal and signal.should_trade:
                self._last_signal_at = signal.timestamp

                # Publish signal to event bus
                await self.event_bus.publish(
                    EventType.TRADE_SIGNAL,
                    {
                        "signal": signal,
                        "strategy": self.get_name(),
                    },
                )

                self.logger.info(
                    "signal_generated",
                    signal_type=signal.signal_type.value,
                    pair=signal.pair,
                    price=float(signal.price),
                    confidence=signal.confidence,
                    reason=signal.reason,
                    strategy=self.get_name(),
                )
        except Exception as e:
            self.logger.error(
                "ohlc_handler_error",
                error=str(e),
                error_type=type(e).__name__,
                strategy=self.get_name(),
                exc_info=e,
            )

    @property
    def is_running(self) -> bool:
        """Check if the strategy is currently running.

        Returns:
            True if the strategy is active and processing events.
        """
        return self._running

    @property
    def last_signal_at(self) -> datetime | None:
        """Get the timestamp of the last generated signal.

        Returns:
            Datetime of last signal, or None if no signal generated yet.
        """
        return self._last_signal_at

    def reset_state(self) -> None:
        """Reset the strategy's internal state.

        Subclasses should override this to reset strategy-specific state.
        """
        self._last_signal_at = None
        self.logger.debug("strategy_state_reset", strategy=self.get_name())
