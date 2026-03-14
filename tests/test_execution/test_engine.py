"""Tests for the ExecutionEngine module.

This module tests the execution engine functionality including:
- Signal handling
- Order execution flow
- BotState updates
- Error handling
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch
import uuid

import pytest

from krakenbot.core.event_bus import EventBus, EventType
from krakenbot.execution.engine import ExecutionEngine
from krakenbot.execution.risk import RiskCheckResult
from krakenbot.models.base import BotStatus, SignalType, TradeSide, TradeStatus
from krakenbot.models.trades import BotState, Trade
from krakenbot.strategies.base import BaseStrategy, TradingSignal

# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def mock_event_bus() -> EventBus:
    """Create a mock event bus."""
    event_bus = EventBus()
    return event_bus


@pytest.fixture
def mock_rest_client() -> MagicMock:
    """Create a mock REST client."""
    client = MagicMock()
    client.get_balance = AsyncMock(return_value={"EUR": Decimal("1000.00"), "XBT": Decimal("0.01")})
    client.get_ticker = AsyncMock(
        return_value={"last": Decimal("42000.00"), "bid": Decimal("41990.00")}
    )
    client.place_market_order = AsyncMock()
    return client


@pytest.fixture
def mock_db_manager() -> MagicMock:
    """Create a mock database manager."""
    manager = MagicMock()

    # Create proper async context managers for sessions
    async def mock_read_session():
        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar.return_value = None
        mock_session.execute = AsyncMock(return_value=mock_result)
        return mock_session

    async def mock_session():
        mock_sess = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_sess.execute = AsyncMock(return_value=mock_result)
        mock_sess.add = MagicMock()
        mock_sess.get = AsyncMock(return_value=None)
        return mock_sess

    # Setup context managers
    read_cm = MagicMock()
    read_cm.__aenter__ = AsyncMock(side_effect=mock_read_session)
    read_cm.__aexit__ = AsyncMock(return_value=None)
    manager.read_session = MagicMock(return_value=read_cm)

    session_cm = MagicMock()
    session_cm.__aenter__ = AsyncMock(side_effect=mock_session)
    session_cm.__aexit__ = AsyncMock(return_value=None)
    manager.session = MagicMock(return_value=session_cm)

    return manager


@pytest.fixture
def execution_engine(
    mock_settings: MagicMock,
    mock_event_bus: EventBus,
    mock_db_manager: MagicMock,
    mock_rest_client: MagicMock,
) -> ExecutionEngine:
    """Create an ExecutionEngine instance for testing."""
    return ExecutionEngine(
        settings=mock_settings,
        event_bus=mock_event_bus,
        db_manager=mock_db_manager,
        rest_client=mock_rest_client,
    )


@pytest.fixture
def sample_buy_signal() -> TradingSignal:
    """Create a sample BUY signal."""
    return TradingSignal(
        signal_type=SignalType.BUY,
        pair="XBT/EUR",
        price=Decimal("42000.00"),
        confidence=0.85,
        reason="Price dropped 1%",
        strategy="threshold_v1",
        timestamp=datetime.now(UTC),
    )


@pytest.fixture
def sample_sell_signal() -> TradingSignal:
    """Create a sample SELL signal."""
    return TradingSignal(
        signal_type=SignalType.SELL,
        pair="XBT/EUR",
        price=Decimal("43000.00"),
        confidence=0.90,
        reason="Price rose 2%",
        strategy="threshold_v1",
        timestamp=datetime.now(UTC),
    )


@pytest.fixture
def sample_hold_signal() -> TradingSignal:
    """Create a sample HOLD signal."""
    return TradingSignal(
        signal_type=SignalType.HOLD,
        pair="XBT/EUR",
        price=Decimal("42000.00"),
        confidence=0.50,
        reason="No action needed",
        strategy="threshold_v1",
        timestamp=datetime.now(UTC),
    )


@pytest.fixture
def sample_trade() -> Trade:
    """Create a sample trade object."""
    return Trade(
        id=uuid.uuid4(),
        timestamp=datetime.now(UTC),
        pair="XBT/EUR",
        side=TradeSide.BUY,
        amount=Decimal("0.00035714"),
        price=Decimal("42000.00"),
        fee=Decimal("0.04"),
        fee_currency="EUR",
        strategy="threshold_v1",
        status=TradeStatus.FILLED,
        order_id="test-order-123",
    )


class PositionAssigningStrategy(BaseStrategy):
    """Minimal strategy used to assign position IDs during fill events."""

    def __init__(
        self,
        settings: Any,
        event_bus: EventBus,
        db_manager: Any,
        *,
        bot_id: str,
        assigned_position_id: int = 7,
    ) -> None:
        super().__init__(settings, event_bus, db_manager, bot_id=bot_id)
        self.assigned_position_id = assigned_position_id
        self._position: SimpleNamespace | None = None

    async def on_tick(self, tick_data: dict[str, Any]) -> None:
        return None

    async def on_ohlc(self, ohlc_data: dict[str, Any]) -> None:
        return None

    async def generate_signal(self) -> TradingSignal | None:
        return None

    def get_name(self) -> str:
        return "position_assigning_strategy"

    def get_config(self) -> dict[str, Any]:
        return {"name": self.get_name()}

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
        if side == "buy":
            self._position = SimpleNamespace(position_id=self.assigned_position_id)


# =============================================================================
# Start/Stop Tests
# =============================================================================


class TestExecutionEngineLifecycle:
    """Tests for ExecutionEngine start/stop functionality."""

    @pytest.mark.asyncio
    async def test_start(self, execution_engine: ExecutionEngine) -> None:
        """Test starting the execution engine."""
        assert not execution_engine.is_running

        await execution_engine.start()

        assert execution_engine.is_running

    @pytest.mark.asyncio
    async def test_stop(self, execution_engine: ExecutionEngine) -> None:
        """Test stopping the execution engine."""
        await execution_engine.start()
        assert execution_engine.is_running

        await execution_engine.stop()

        assert not execution_engine.is_running

    @pytest.mark.asyncio
    async def test_start_already_running(self, execution_engine: ExecutionEngine) -> None:
        """Test starting an already running engine."""
        await execution_engine.start()
        await execution_engine.start()  # Should log warning but not error

        assert execution_engine.is_running

    @pytest.mark.asyncio
    async def test_stop_not_running(self, execution_engine: ExecutionEngine) -> None:
        """Test stopping an engine that is not running."""
        await execution_engine.stop()  # Should log warning but not error

        assert not execution_engine.is_running

    @pytest.mark.asyncio
    async def test_stats_after_stop(self, execution_engine: ExecutionEngine) -> None:
        """Test that stats are available after stopping."""
        await execution_engine.start()
        await execution_engine.stop()

        stats = execution_engine.stats
        assert "signals_received" in stats
        assert "signals_executed" in stats


# =============================================================================
# Signal Handling Tests
# =============================================================================


class TestSignalHandling:
    """Tests for signal handling functionality."""

    @pytest.mark.asyncio
    async def test_handle_signal_ignores_hold(
        self,
        execution_engine: ExecutionEngine,
        sample_hold_signal: TradingSignal,
    ) -> None:
        """Test that HOLD signals are ignored."""
        await execution_engine.start()

        await execution_engine._handle_signal({"signal": sample_hold_signal})

        assert execution_engine.stats["signals_ignored"] == 1
        assert execution_engine.stats["signals_executed"] == 0

    @pytest.mark.asyncio
    async def test_handle_signal_when_not_running(
        self,
        execution_engine: ExecutionEngine,
        sample_buy_signal: TradingSignal,
    ) -> None:
        """Test that signals are ignored when engine is not running."""
        # Don't start the engine
        await execution_engine._handle_signal({"signal": sample_buy_signal})

        assert execution_engine.stats["signals_received"] == 0

    @pytest.mark.asyncio
    async def test_handle_signal_missing_signal(self, execution_engine: ExecutionEngine) -> None:
        """Test handling event data without signal."""
        await execution_engine.start()

        await execution_engine._handle_signal({})  # No signal key

        # Should increment received but not execute
        assert execution_engine.stats["signals_received"] == 1
        assert execution_engine.stats["signals_executed"] == 0

    @pytest.mark.asyncio
    async def test_handle_buy_signal_full_flow(
        self,
        execution_engine: ExecutionEngine,
        sample_buy_signal: TradingSignal,
        sample_trade: Trade,
        mock_rest_client: MagicMock,
    ) -> None:
        """Test complete buy signal execution flow."""
        # Setup mocks
        mock_rest_client.place_market_order.return_value = sample_trade

        # Mock risk manager to approve
        with patch.object(
            execution_engine.risk_manager,
            "check_order",
            return_value=RiskCheckResult(approved=True),
        ):
            await execution_engine.start()
            await execution_engine._handle_signal({"signal": sample_buy_signal})

        assert execution_engine.stats["signals_received"] == 1
        assert execution_engine.stats["signals_executed"] == 1
        mock_rest_client.place_market_order.assert_called_once()

    @pytest.mark.asyncio
    async def test_handle_signal_risk_rejected(
        self,
        execution_engine: ExecutionEngine,
        sample_buy_signal: TradingSignal,
        mock_rest_client: MagicMock,
    ) -> None:
        """Test signal rejected by risk manager."""
        # Mock risk manager to reject
        with patch.object(
            execution_engine.risk_manager,
            "check_order",
            return_value=RiskCheckResult(approved=False, reasons=["Daily loss limit exceeded"]),
        ):
            await execution_engine.start()
            await execution_engine._handle_signal({"signal": sample_buy_signal})

        assert execution_engine.stats["signals_rejected"] == 1
        assert execution_engine.stats["signals_executed"] == 0
        mock_rest_client.place_market_order.assert_not_called()

    @pytest.mark.asyncio
    async def test_handle_signal_execution_error(
        self,
        execution_engine: ExecutionEngine,
        sample_buy_signal: TradingSignal,
        mock_rest_client: MagicMock,
    ) -> None:
        """Test error handling during signal execution."""
        # Mock risk manager to approve
        with patch.object(
            execution_engine.risk_manager,
            "check_order",
            return_value=RiskCheckResult(approved=True),
        ):
            # Mock order to fail
            mock_rest_client.place_market_order.side_effect = Exception("API Error")

            await execution_engine.start()
            await execution_engine._handle_signal({"signal": sample_buy_signal})

        assert execution_engine.stats["execution_errors"] == 1
        assert execution_engine.stats["signals_executed"] == 0


# =============================================================================
# Order Amount Calculation Tests
# =============================================================================


class TestOrderAmountCalculation:
    """Tests for order amount calculation."""

    @pytest.mark.asyncio
    async def test_calculate_order_amount_buy(self, execution_engine: ExecutionEngine) -> None:
        """Test order amount calculation for buy orders."""
        # Default order amount is 15 EUR
        amount = await execution_engine._calculate_order_amount(
            pair="XBT/EUR",
            side=TradeSide.BUY,
            price=Decimal("42000"),
        )

        # 15 EUR / 42000 = 0.00035714 BTC
        expected = Decimal("15") / Decimal("42000")
        assert amount == expected.quantize(Decimal("0.00000001"))

    @pytest.mark.asyncio
    async def test_calculate_order_amount_sell_no_position(
        self,
        execution_engine: ExecutionEngine,
    ) -> None:
        """Test order amount calculation for sell with no position returns 0."""
        # The default mock returns None for scalar(), so position should be 0
        amount = await execution_engine._calculate_order_amount(
            pair="XBT/EUR",
            side=TradeSide.SELL,
            price=Decimal("42000"),
        )

        assert amount == Decimal("0")


# =============================================================================
# BotState Update Tests
# =============================================================================


class TestBotStateUpdates:
    """Tests for BotState update functionality."""

    @pytest.mark.asyncio
    async def test_update_bot_state_buy_creates_new(
        self,
        execution_engine: ExecutionEngine,
        sample_trade: Trade,
        sample_buy_signal: TradingSignal,
    ) -> None:
        """Test that buy trade creates new BotState if none exists.

        The default mock_db_manager fixture returns None from
        scalar_one_or_none(), so a new BotState should be created.
        """
        # Call the update method - should not raise
        await execution_engine._update_bot_state(sample_trade, sample_buy_signal)

        # Test passes if no exception is raised

    @pytest.mark.asyncio
    async def test_handle_buy_trade_helper(
        self,
        execution_engine: ExecutionEngine,
        sample_trade: Trade,
        sample_buy_signal: TradingSignal,
    ) -> None:
        """Test the _handle_buy_trade helper method updates state correctly."""
        # Create a fresh BotState
        bot_state = BotState(
            bot_id="threshold_v1",
            strategy="threshold_v1",
            status=BotStatus.RUNNING,
            position_size=Decimal("0"),
            daily_pnl=Decimal("0"),
            total_pnl=Decimal("0"),
            daily_trades_count=0,
        )

        mock_session = MagicMock()
        mock_session.add = MagicMock()  # Mock session.add() for OpenPosition creation

        await execution_engine._handle_buy_trade(
            mock_session, bot_state, sample_trade, sample_buy_signal
        )

        # Verify state was updated (cumulative now instead of overwrite)
        assert bot_state.position_size == sample_trade.amount
        assert bot_state.entry_price == sample_trade.price
        assert bot_state.daily_trades_count == 1
        # Verify OpenPosition was added to session
        mock_session.add.assert_called_once()

    @pytest.mark.asyncio
    async def test_handle_sell_trade_helper_with_pnl(
        self,
        execution_engine: ExecutionEngine,
    ) -> None:
        """Test the _handle_sell_trade helper calculates P&L correctly."""
        # Create sell trade
        sell_trade = Trade(
            id=uuid.uuid4(),
            timestamp=datetime.now(UTC),
            pair="XBT/EUR",
            side=TradeSide.SELL,
            amount=Decimal("0.001"),
            price=Decimal("43000.00"),  # Exit at 43000
            fee=Decimal("0.05"),
            fee_currency="EUR",
            strategy="threshold_v1",
            status=TradeStatus.FILLED,
            order_id="test-order-456",
        )

        sell_signal = TradingSignal(
            signal_type=SignalType.SELL,
            pair="XBT/EUR",
            price=Decimal("43000.00"),
            confidence=0.90,
            reason="Price rose",
            strategy="threshold_v1",
            timestamp=datetime.now(UTC),
        )

        # Existing state with position
        existing_state = BotState(
            bot_id="threshold_v1",
            strategy="threshold_v1",
            status=BotStatus.RUNNING,
            position_size=Decimal("0.001"),
            entry_price=Decimal("42000.00"),  # Entry at 42000
            daily_pnl=Decimal("0"),
            total_pnl=Decimal("0"),
            daily_trades_count=0,
        )

        mock_session = AsyncMock()
        mock_session.get = AsyncMock(return_value=sell_trade)

        await execution_engine._handle_sell_trade(
            mock_session, existing_state, sell_trade, sell_signal
        )

        # P&L = (43000 - 42000) * 0.001 - 0.05 = 1.0 - 0.05 = 0.95
        expected_pnl = Decimal("0.95")
        assert existing_state.daily_pnl == expected_pnl
        assert existing_state.total_pnl == expected_pnl
        assert existing_state.position_size == Decimal("0")
        assert existing_state.entry_price is None

    @pytest.mark.asyncio
    async def test_market_open_fill_assigns_position_id_before_bot_state_update(
        self,
        mock_settings: MagicMock,
        mock_db_manager: MagicMock,
        mock_rest_client: MagicMock,
        sample_trade: Trade,
    ) -> None:
        """Opening market fills should persist the strategy-assigned position_id."""
        event_bus = EventBus()
        strategy = PositionAssigningStrategy(
            mock_settings,
            event_bus,
            mock_db_manager,
            bot_id="threshold_v1",
            assigned_position_id=7,
        )
        await strategy.start()

        signal = TradingSignal(
            signal_type=SignalType.BUY,
            pair="XBT/EUR",
            price=Decimal("42000.00"),
            confidence=0.85,
            reason="Market open",
            strategy="threshold_v1",
            timestamp=datetime.now(UTC),
            metadata={"reference_price": "42000"},
        )
        mock_rest_client.place_market_order.return_value = sample_trade
        engine = ExecutionEngine(mock_settings, event_bus, mock_db_manager, mock_rest_client)

        with (
            patch.object(
                engine.risk_manager,
                "check_order",
                return_value=RiskCheckResult(approved=True),
            ),
            patch.object(engine, "_update_bot_state", new=AsyncMock()) as update_bot_state,
        ):
            await engine._execute_signal(signal)

        assert signal.metadata["position_id"] == 7
        assert update_bot_state.await_args.args[1].metadata["position_id"] == 7

    @pytest.mark.asyncio
    async def test_handle_limit_order_fill_uses_order_position_metadata(
        self,
        mock_settings: MagicMock,
        sample_trade: Trade,
    ) -> None:
        """Limit fill sync should rebuild bot-state updates from stored order metadata."""
        sample_trade.strategy = "threshold_v1"
        sample_trade.side = TradeSide.BUY

        read_session = AsyncMock()
        read_session.get = AsyncMock(return_value=sample_trade)
        read_cm = MagicMock()
        read_cm.__aenter__ = AsyncMock(return_value=read_session)
        read_cm.__aexit__ = AsyncMock(return_value=None)

        db_manager = MagicMock()
        db_manager.read_session = MagicMock(return_value=read_cm)

        engine = ExecutionEngine(mock_settings, EventBus(), db_manager, MagicMock())
        order = SimpleNamespace(
            id=sample_trade.id,
            order_id="paper-123",
            strategy="threshold_v1",
            signal_metadata={"position_id": 7, "reference_price": "42000"},
        )

        with patch.object(engine, "_update_bot_state", new=AsyncMock()) as update_bot_state:
            await engine._handle_limit_order_fill(order)

        assert update_bot_state.await_args.args[0] == sample_trade
        assert update_bot_state.await_args.args[1].metadata["position_id"] == 7


# =============================================================================
# Manual Order Tests
# =============================================================================


class TestManualOrders:
    """Tests for manual order execution."""

    @pytest.mark.asyncio
    async def test_execute_manual_order_success(
        self,
        execution_engine: ExecutionEngine,
        sample_trade: Trade,
        mock_rest_client: MagicMock,
    ) -> None:
        """Test successful manual order execution."""
        mock_rest_client.place_market_order.return_value = sample_trade

        with patch.object(
            execution_engine.risk_manager,
            "check_order",
            return_value=RiskCheckResult(approved=True),
        ):
            result = await execution_engine.execute_manual_order(
                pair="XBT/EUR",
                side=TradeSide.BUY,
                amount=Decimal("0.001"),
            )

        assert result is not None
        assert result.id == sample_trade.id
        mock_rest_client.place_market_order.assert_called_once()

    @pytest.mark.asyncio
    async def test_execute_manual_order_risk_rejected(
        self,
        execution_engine: ExecutionEngine,
        mock_rest_client: MagicMock,
    ) -> None:
        """Test manual order rejected by risk manager."""
        with patch.object(
            execution_engine.risk_manager,
            "check_order",
            return_value=RiskCheckResult(approved=False, reasons=["Position too large"]),
        ):
            result = await execution_engine.execute_manual_order(
                pair="XBT/EUR",
                side=TradeSide.BUY,
                amount=Decimal("1.0"),  # Large amount
            )

        assert result is None
        mock_rest_client.place_market_order.assert_not_called()

    @pytest.mark.asyncio
    async def test_execute_manual_order_no_price(
        self,
        execution_engine: ExecutionEngine,
        mock_rest_client: MagicMock,
    ) -> None:
        """Test manual order fails when no price available."""
        mock_rest_client.get_ticker.return_value = {"last": Decimal("0")}

        result = await execution_engine.execute_manual_order(
            pair="XBT/EUR",
            side=TradeSide.BUY,
            amount=Decimal("0.001"),
        )

        assert result is None


# =============================================================================
# Statistics Tests
# =============================================================================


class TestExecutionStatistics:
    """Tests for execution statistics."""

    def test_stats_initial_values(self, execution_engine: ExecutionEngine) -> None:
        """Test initial statistics values."""
        stats = execution_engine.stats

        assert stats["signals_received"] == 0
        assert stats["signals_executed"] == 0
        assert stats["signals_rejected"] == 0
        assert stats["signals_ignored"] == 0
        assert stats["execution_errors"] == 0

    def test_stats_returns_copy(self, execution_engine: ExecutionEngine) -> None:
        """Test that stats returns a copy, not the original."""
        stats = execution_engine.stats
        stats["signals_received"] = 999

        assert execution_engine.stats["signals_received"] == 0

    def test_reset_stats(self, execution_engine: ExecutionEngine) -> None:
        """Test statistics reset."""
        execution_engine._stats["signals_received"] = 10
        execution_engine._stats["signals_executed"] = 5

        execution_engine.reset_stats()

        assert execution_engine.stats["signals_received"] == 0
        assert execution_engine.stats["signals_executed"] == 0


# =============================================================================
# Event Bus Integration Tests
# =============================================================================


class TestEventBusIntegration:
    """Tests for EventBus integration."""

    @pytest.mark.asyncio
    async def test_subscribes_to_trade_signal(
        self,
        execution_engine: ExecutionEngine,
        mock_event_bus: EventBus,
    ) -> None:
        """Test that engine subscribes to TRADE_SIGNAL events."""
        await execution_engine.start()

        subscriber_count = mock_event_bus.get_subscriber_count(EventType.TRADE_SIGNAL)
        assert subscriber_count >= 1

    @pytest.mark.asyncio
    async def test_unsubscribes_on_stop(
        self,
        execution_engine: ExecutionEngine,
        mock_event_bus: EventBus,
    ) -> None:
        """Test that engine unsubscribes on stop."""
        await execution_engine.start()
        initial_count = mock_event_bus.get_subscriber_count(EventType.TRADE_SIGNAL)

        await execution_engine.stop()

        final_count = mock_event_bus.get_subscriber_count(EventType.TRADE_SIGNAL)
        assert final_count < initial_count

    @pytest.mark.asyncio
    async def test_signal_received_via_event_bus(
        self,
        execution_engine: ExecutionEngine,
        mock_event_bus: EventBus,
        sample_buy_signal: TradingSignal,
        sample_trade: Trade,
        mock_rest_client: MagicMock,
    ) -> None:
        """Test that signals published to event bus are processed."""
        mock_rest_client.place_market_order.return_value = sample_trade

        with patch.object(
            execution_engine.risk_manager,
            "check_order",
            return_value=RiskCheckResult(approved=True),
        ):
            await execution_engine.start()

            # Publish signal via event bus
            await mock_event_bus.publish(
                EventType.TRADE_SIGNAL,
                {"signal": sample_buy_signal, "strategy": "threshold_v1"},
            )

        # Give time for async processing
        assert execution_engine.stats["signals_received"] >= 1
