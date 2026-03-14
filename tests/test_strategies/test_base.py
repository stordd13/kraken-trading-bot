"""Tests for base strategy module.

This module tests:
- TradingSignal dataclass
- TradingSignal properties (should_trade, is_buy, is_sell)
- BaseStrategy abstract class with mocks
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from krakenbot.core.event_bus import EventBus, EventType
from krakenbot.models.base import SignalType
from krakenbot.strategies.base import BaseStrategy, TradingSignal


class TestTradingSignal:
    """Tests for TradingSignal dataclass."""

    def test_create_buy_signal(self) -> None:
        """Test creating a BUY signal."""
        signal = TradingSignal(
            signal_type=SignalType.BUY,
            pair="XBT/EUR",
            price=Decimal("42000.00"),
            confidence=0.8,
            reason="Price drop detected: -1.5%",
            strategy="threshold",
            timestamp=datetime.now(UTC),
        )

        assert signal.signal_type == SignalType.BUY
        assert signal.pair == "XBT/EUR"
        assert signal.price == Decimal("42000.00")
        assert signal.confidence == 0.8
        assert signal.reason == "Price drop detected: -1.5%"
        assert signal.strategy == "threshold"
        assert signal.metadata == {}

    def test_create_sell_signal_with_metadata(self) -> None:
        """Test creating a SELL signal with metadata."""
        metadata = {"entry_price": 41000.0, "profit_pct": 2.5}
        signal = TradingSignal(
            signal_type=SignalType.SELL,
            pair="XBT/EUR",
            price=Decimal("42025.00"),
            confidence=0.9,
            reason="Profit target reached",
            strategy="threshold",
            timestamp=datetime.now(UTC),
            metadata=metadata,
        )

        assert signal.signal_type == SignalType.SELL
        assert signal.metadata == metadata

    def test_create_hold_signal(self) -> None:
        """Test creating a HOLD signal."""
        signal = TradingSignal(
            signal_type=SignalType.HOLD,
            pair="XBT/EUR",
            price=Decimal("42000.00"),
            confidence=1.0,
            reason="No conditions met",
            strategy="threshold",
            timestamp=datetime.now(UTC),
        )

        assert signal.signal_type == SignalType.HOLD

    def test_should_trade_buy(self) -> None:
        """Test should_trade returns True for BUY."""
        signal = TradingSignal(
            signal_type=SignalType.BUY,
            pair="XBT/EUR",
            price=Decimal("42000.00"),
            confidence=0.8,
            reason="Test",
            strategy="threshold",
            timestamp=datetime.now(UTC),
        )

        assert signal.should_trade is True

    def test_should_trade_sell(self) -> None:
        """Test should_trade returns True for SELL."""
        signal = TradingSignal(
            signal_type=SignalType.SELL,
            pair="XBT/EUR",
            price=Decimal("42000.00"),
            confidence=0.8,
            reason="Test",
            strategy="threshold",
            timestamp=datetime.now(UTC),
        )

        assert signal.should_trade is True

    def test_should_trade_hold(self) -> None:
        """Test should_trade returns False for HOLD."""
        signal = TradingSignal(
            signal_type=SignalType.HOLD,
            pair="XBT/EUR",
            price=Decimal("42000.00"),
            confidence=1.0,
            reason="Test",
            strategy="threshold",
            timestamp=datetime.now(UTC),
        )

        assert signal.should_trade is False

    def test_is_buy(self) -> None:
        """Test is_buy property."""
        buy_signal = TradingSignal(
            signal_type=SignalType.BUY,
            pair="XBT/EUR",
            price=Decimal("42000.00"),
            confidence=0.8,
            reason="Test",
            strategy="threshold",
            timestamp=datetime.now(UTC),
        )

        sell_signal = TradingSignal(
            signal_type=SignalType.SELL,
            pair="XBT/EUR",
            price=Decimal("42000.00"),
            confidence=0.8,
            reason="Test",
            strategy="threshold",
            timestamp=datetime.now(UTC),
        )

        hold_signal = TradingSignal(
            signal_type=SignalType.HOLD,
            pair="XBT/EUR",
            price=Decimal("42000.00"),
            confidence=1.0,
            reason="Test",
            strategy="threshold",
            timestamp=datetime.now(UTC),
        )

        assert buy_signal.is_buy is True
        assert buy_signal.is_sell is False
        assert sell_signal.is_buy is False
        assert sell_signal.is_sell is True
        assert hold_signal.is_buy is False
        assert hold_signal.is_sell is False

    def test_is_sell(self) -> None:
        """Test is_sell property."""
        signal = TradingSignal(
            signal_type=SignalType.SELL,
            pair="XBT/EUR",
            price=Decimal("42000.00"),
            confidence=0.8,
            reason="Test",
            strategy="threshold",
            timestamp=datetime.now(UTC),
        )

        assert signal.is_sell is True
        assert signal.is_buy is False

    def test_to_dict(self) -> None:
        """Test converting signal to dictionary."""
        now = datetime.now(UTC)
        signal = TradingSignal(
            signal_type=SignalType.BUY,
            pair="XBT/EUR",
            price=Decimal("42000.00"),
            confidence=0.8,
            reason="Test reason",
            strategy="threshold",
            timestamp=now,
            metadata={"key": "value"},
        )

        result = signal.to_dict()

        assert result["signal_type"] == "buy"
        assert result["pair"] == "XBT/EUR"
        assert result["price"] == "42000.00"
        assert result["confidence"] == 0.8
        assert result["reason"] == "Test reason"
        assert result["strategy"] == "threshold"
        assert result["timestamp"] == now.isoformat()
        assert result["metadata"] == {"key": "value"}

    def test_validation_confidence_too_low(self) -> None:
        """Test validation fails for confidence < 0."""
        with pytest.raises(ValueError, match="Confidence must be between"):
            TradingSignal(
                signal_type=SignalType.BUY,
                pair="XBT/EUR",
                price=Decimal("42000.00"),
                confidence=-0.1,
                reason="Test",
                strategy="threshold",
                timestamp=datetime.now(UTC),
            )

    def test_validation_confidence_too_high(self) -> None:
        """Test validation fails for confidence > 1."""
        with pytest.raises(ValueError, match="Confidence must be between"):
            TradingSignal(
                signal_type=SignalType.BUY,
                pair="XBT/EUR",
                price=Decimal("42000.00"),
                confidence=1.5,
                reason="Test",
                strategy="threshold",
                timestamp=datetime.now(UTC),
            )

    def test_validation_empty_pair(self) -> None:
        """Test validation fails for empty pair."""
        with pytest.raises(ValueError, match="Pair cannot be empty"):
            TradingSignal(
                signal_type=SignalType.BUY,
                pair="",
                price=Decimal("42000.00"),
                confidence=0.8,
                reason="Test",
                strategy="threshold",
                timestamp=datetime.now(UTC),
            )

    def test_validation_empty_strategy(self) -> None:
        """Test validation fails for empty strategy."""
        with pytest.raises(ValueError, match="Strategy name cannot be empty"):
            TradingSignal(
                signal_type=SignalType.BUY,
                pair="XBT/EUR",
                price=Decimal("42000.00"),
                confidence=0.8,
                reason="Test",
                strategy="",
                timestamp=datetime.now(UTC),
            )

    def test_validation_naive_timestamp(self) -> None:
        """Test validation fails for naive timestamp (no timezone)."""
        with pytest.raises(ValueError, match="Timestamp must be timezone-aware"):
            TradingSignal(
                signal_type=SignalType.BUY,
                pair="XBT/EUR",
                price=Decimal("42000.00"),
                confidence=0.8,
                reason="Test",
                strategy="threshold",
                timestamp=datetime.now(),  # No timezone
            )


class ConcreteStrategy(BaseStrategy):
    """Concrete implementation of BaseStrategy for testing."""

    def __init__(
        self,
        settings: Any,
        event_bus: EventBus,
        db_manager: Any,
    ) -> None:
        """Initialize test strategy."""
        super().__init__(settings, event_bus, db_manager)
        self.tick_count = 0
        self.ohlc_count = 0
        self._signal_to_return: TradingSignal | None = None

    async def on_tick(self, tick_data: dict[str, Any]) -> None:
        """Handle tick data."""
        self.tick_count += 1

    async def on_ohlc(self, ohlc_data: dict[str, Any]) -> None:
        """Handle OHLC data."""
        self.ohlc_count += 1

    async def generate_signal(self) -> TradingSignal | None:
        """Generate signal."""
        return self._signal_to_return

    def get_name(self) -> str:
        """Return strategy name."""
        return "test_strategy"

    def get_config(self) -> dict[str, Any]:
        """Return config."""
        return {"name": "test_strategy"}

    def set_signal(self, signal: TradingSignal | None) -> None:
        """Set signal to return."""
        self._signal_to_return = signal


class PositionAssigningStrategy(ConcreteStrategy):
    """Test strategy that assigns a position_id on fills."""

    def __init__(
        self,
        settings: Any,
        event_bus: EventBus,
        db_manager: Any,
        *,
        assigned_position_id: int = 7,
        open_side: str = "buy",
    ) -> None:
        super().__init__(settings, event_bus, db_manager)
        self.assigned_position_id = assigned_position_id
        self.open_side = open_side
        self._position: SimpleNamespace | None = None

    async def on_trade_filled(
        self,
        trade_id: str,
        pair: str,
        side: str,
        amount: Decimal,
        price: Decimal,
        fee: Decimal,
        reference_price: Decimal | None,
        position_id: int | None,
    ) -> None:
        if side == self.open_side:
            self._position = SimpleNamespace(position_id=self.assigned_position_id)


class TestBaseStrategy:
    """Tests for BaseStrategy abstract class."""

    @pytest.fixture
    def mock_event_bus(self) -> AsyncMock:
        """Create mock event bus."""
        bus = AsyncMock(spec=EventBus)
        bus.subscribe = AsyncMock()
        bus.unsubscribe = AsyncMock()
        bus.publish = AsyncMock()
        return bus

    @pytest.fixture
    def mock_db_manager(self) -> MagicMock:
        """Create mock database manager."""
        manager = MagicMock()
        manager.read_session = MagicMock()
        return manager

    @pytest.fixture
    def strategy(
        self,
        mock_settings: Any,
        mock_event_bus: AsyncMock,
        mock_db_manager: MagicMock,
    ) -> ConcreteStrategy:
        """Create test strategy."""
        return ConcreteStrategy(mock_settings, mock_event_bus, mock_db_manager)

    def test_initialization(self, strategy: ConcreteStrategy) -> None:
        """Test strategy initialization."""
        assert strategy.is_running is False
        assert strategy.last_signal_at is None
        assert strategy.get_name() == "test_strategy"

    @pytest.mark.asyncio
    async def test_start(
        self,
        strategy: ConcreteStrategy,
        mock_event_bus: AsyncMock,
    ) -> None:
        """Test starting the strategy."""
        await strategy.start()

        assert strategy.is_running is True
        assert mock_event_bus.subscribe.call_count == 3

        # Verify subscriptions to correct event types
        calls = mock_event_bus.subscribe.call_args_list
        event_types = [call[0][0] for call in calls]
        assert EventType.MARKET_TICK in event_types
        assert EventType.MARKET_OHLC in event_types
        assert EventType.TRADE_ORDER_FILLED in event_types

    @pytest.mark.asyncio
    async def test_stop(
        self,
        strategy: ConcreteStrategy,
        mock_event_bus: AsyncMock,
    ) -> None:
        """Test stopping the strategy."""
        await strategy.start()
        await strategy.stop()

        assert strategy.is_running is False
        assert mock_event_bus.unsubscribe.call_count == 3

    @pytest.mark.asyncio
    async def test_handle_tick_when_running(
        self,
        strategy: ConcreteStrategy,
    ) -> None:
        """Test tick handling when strategy is running."""
        strategy._running = True
        tick_data = {"pair": "XBT/EUR", "price": "42000.00"}

        await strategy._handle_tick(tick_data)

        assert strategy.tick_count == 1

    @pytest.mark.asyncio
    async def test_handle_tick_when_stopped(
        self,
        strategy: ConcreteStrategy,
    ) -> None:
        """Test tick handling is skipped when strategy is stopped."""
        strategy._running = False
        tick_data = {"pair": "XBT/EUR", "price": "42000.00"}

        await strategy._handle_tick(tick_data)

        assert strategy.tick_count == 0

    @pytest.mark.asyncio
    async def test_handle_ohlc_when_running(
        self,
        strategy: ConcreteStrategy,
    ) -> None:
        """Test OHLC handling when strategy is running."""
        strategy._running = True
        ohlc_data = {
            "pair": "XBT/EUR",
            "open": "42000.00",
            "high": "42500.00",
            "low": "41800.00",
            "close": "42300.00",
        }

        await strategy._handle_ohlc(ohlc_data)

        assert strategy.ohlc_count == 1

    @pytest.mark.asyncio
    async def test_handle_ohlc_when_stopped(
        self,
        strategy: ConcreteStrategy,
    ) -> None:
        """Test OHLC handling is skipped when strategy is stopped."""
        strategy._running = False
        ohlc_data = {"pair": "XBT/EUR", "close": "42300.00"}

        await strategy._handle_ohlc(ohlc_data)

        assert strategy.ohlc_count == 0

    @pytest.mark.asyncio
    async def test_handle_ohlc_publishes_signal(
        self,
        strategy: ConcreteStrategy,
        mock_event_bus: AsyncMock,
    ) -> None:
        """Test OHLC handler publishes signal when actionable."""
        strategy._running = True

        # Set up a BUY signal to be returned
        buy_signal = TradingSignal(
            signal_type=SignalType.BUY,
            pair="XBT/EUR",
            price=Decimal("42000.00"),
            confidence=0.8,
            reason="Test",
            strategy="test_strategy",
            timestamp=datetime.now(UTC),
        )
        strategy.set_signal(buy_signal)

        ohlc_data = {"pair": "XBT/EUR", "close": "42000.00"}
        await strategy._handle_ohlc(ohlc_data)

        # Verify signal was published
        mock_event_bus.publish.assert_called_once()
        call_args = mock_event_bus.publish.call_args
        assert call_args[0][0] == EventType.TRADE_SIGNAL
        assert call_args[0][1]["signal"] == buy_signal

    @pytest.mark.asyncio
    async def test_handle_ohlc_does_not_publish_hold_signal(
        self,
        strategy: ConcreteStrategy,
        mock_event_bus: AsyncMock,
    ) -> None:
        """Test OHLC handler does not publish HOLD signal."""
        strategy._running = True

        # Set up a HOLD signal
        hold_signal = TradingSignal(
            signal_type=SignalType.HOLD,
            pair="XBT/EUR",
            price=Decimal("42000.00"),
            confidence=1.0,
            reason="No conditions met",
            strategy="test_strategy",
            timestamp=datetime.now(UTC),
        )
        strategy.set_signal(hold_signal)

        ohlc_data = {"pair": "XBT/EUR", "close": "42000.00"}
        await strategy._handle_ohlc(ohlc_data)

        # Verify no signal was published
        mock_event_bus.publish.assert_not_called()

    @pytest.mark.asyncio
    async def test_handle_tick_error_handling(
        self,
        strategy: ConcreteStrategy,
    ) -> None:
        """Test tick handler catches and logs errors."""
        strategy._running = True

        # Make on_tick raise an exception
        async def failing_on_tick(data: dict[str, Any]) -> None:
            raise ValueError("Test error")

        strategy.on_tick = failing_on_tick

        # Should not raise
        await strategy._handle_tick({"pair": "XBT/EUR", "price": "42000.00"})

    @pytest.mark.asyncio
    async def test_handle_ohlc_error_handling(
        self,
        strategy: ConcreteStrategy,
    ) -> None:
        """Test OHLC handler catches and logs errors."""
        strategy._running = True

        # Make on_ohlc raise an exception
        async def failing_on_ohlc(data: dict[str, Any]) -> None:
            raise ValueError("Test error")

        strategy.on_ohlc = failing_on_ohlc

        # Should not raise
        await strategy._handle_ohlc({"pair": "XBT/EUR", "close": "42000.00"})

    @pytest.mark.asyncio
    async def test_handle_trade_filled_infers_position_id_from_strategy_state(
        self,
        mock_settings: Any,
        mock_event_bus: AsyncMock,
        mock_db_manager: MagicMock,
    ) -> None:
        """BUY fills should propagate the strategy-assigned position_id to runtime metadata."""
        strategy = PositionAssigningStrategy(
            mock_settings,
            mock_event_bus,
            mock_db_manager,
            assigned_position_id=7,
        )
        strategy._running = True

        signal_metadata = {"reference_price": "42000"}
        fill_event = {
            "trade_id": "trade-123",
            "pair": "XBT/EUR",
            "side": "buy",
            "amount": "0.001",
            "price": "42000",
            "fee": "0.04",
            "strategy": strategy.bot_id,
            "reference_price": "42000",
            "signal_metadata": signal_metadata,
        }

        await strategy._handle_trade_filled(fill_event)

        assert fill_event["position_id"] == 7
        assert signal_metadata["position_id"] == 7

    def test_reset_state(self, strategy: ConcreteStrategy) -> None:
        """Test resetting strategy state."""
        strategy._last_signal_at = datetime.now(UTC)

        strategy.reset_state()

        assert strategy.last_signal_at is None

    def test_get_config(self, strategy: ConcreteStrategy) -> None:
        """Test getting strategy config."""
        config = strategy.get_config()

        assert config == {"name": "test_strategy"}
