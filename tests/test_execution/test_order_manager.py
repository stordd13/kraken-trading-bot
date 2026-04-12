"""Tests for the OrderManager module.

This module tests all order lifecycle management functionality including:
- Order placement and tracking
- Pending order fill detection (paper mode candle simulation)
- Order expiry detection and cancellation
- Profit target placement and cancellation
- OHLC candle storage for paper fill simulation
- Statistics and pending count properties
- Cancel all pending orders (shutdown)
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock
import uuid

import pytest

from krakenbot.config.settings import ExchangeFees, TradingMode
from krakenbot.core.event_bus import EventBus
from krakenbot.execution.order_manager import OrderManager
from krakenbot.models.base import OrderStatus, OrderType, TradeSide
from krakenbot.strategies.base import BaseStrategy, TradingSignal

# =============================================================================
# Helpers
# =============================================================================


class FakeOrder:
    """Lightweight Order stand-in that avoids SQLAlchemy instrumentation.

    Reproduces the attributes and properties of the real Order model
    so that OrderManager can interact with it identically.
    """

    def __init__(
        self,
        *,
        order_id: str = "paper-001",
        pair: str = "XBT/USDC",
        side: TradeSide = TradeSide.BUY,
        amount: Decimal = Decimal("0.001"),
        price: Decimal = Decimal("42000"),
        status: OrderStatus = OrderStatus.PENDING,
        strategy: str = "threshold",
        bot_id: str = "bot-test-001",
        signal_metadata: dict | None = None,
        expires_at: datetime | None = None,
    ) -> None:
        self.id = uuid.uuid4()
        self.order_id = order_id
        self.bot_id = bot_id
        self.pair = pair
        self.side = side
        self.order_type = OrderType.LIMIT
        self.amount = amount
        self.price = price
        self.filled_amount = Decimal("0")
        self.filled_price: Decimal | None = None
        self.fee = Decimal("0")
        self.status = status
        self.strategy = strategy
        self.signal_metadata = signal_metadata
        self.expires_at = expires_at
        self.created_at = datetime.now(UTC)
        self.updated_at = datetime.now(UTC)

    @property
    def is_pending(self) -> bool:
        return self.status == OrderStatus.PENDING

    @property
    def is_filled(self) -> bool:
        return self.status == OrderStatus.FILLED


def _make_order(
    *,
    order_id: str = "paper-001",
    pair: str = "XBT/USDC",
    side: TradeSide = TradeSide.BUY,
    amount: Decimal = Decimal("0.001"),
    price: Decimal = Decimal("42000"),
    status: OrderStatus = OrderStatus.PENDING,
    strategy: str = "threshold",
    bot_id: str = "bot-test-001",
    signal_metadata: dict | None = None,
    expires_at: datetime | None = None,
) -> FakeOrder:
    """Create a fake Order object for testing.

    Uses FakeOrder to avoid SQLAlchemy instrumented attribute issues
    when constructing Order objects outside of a database session.

    Returns:
        A FakeOrder instance configured for testing.
    """
    return FakeOrder(
        order_id=order_id,
        pair=pair,
        side=side,
        amount=amount,
        price=price,
        status=status,
        strategy=strategy,
        bot_id=bot_id,
        signal_metadata=signal_metadata,
        expires_at=expires_at,
    )


def _make_db_session_context(mock_session: AsyncMock):
    """Create an async context manager that yields mock_session.

    Used to mock db_manager.session() which is an async context manager.

    Args:
        mock_session: The mock session to yield.

    Returns:
        An async context manager factory.
    """

    @asynccontextmanager
    async def _ctx():
        yield mock_session

    return _ctx


class PositionAssigningStrategy(BaseStrategy):
    """Minimal strategy used to assign a position_id during fill events."""

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
# OrderManager Tests
# =============================================================================


class TestOrderManager:
    """Tests for the OrderManager class."""

    @pytest.fixture
    def mock_rest_client(self) -> AsyncMock:
        """Create a mock Kraken REST client."""
        client = AsyncMock()
        client.place_limit_order = AsyncMock()
        client.get_order_status = AsyncMock()
        client.cancel_order = AsyncMock()
        client.is_paper_mode = True
        client.exchange_name = "kraken"
        client._paper_balance = {
            "USDC": Decimal("10000"),
            "XBT": Decimal("0.1"),
        }
        client.paper_balance = client._paper_balance
        client.remove_paper_order = MagicMock()
        return client

    @pytest.fixture
    def mock_db_session(self) -> AsyncMock:
        """Create a mock async database session."""
        session = AsyncMock()
        session.get = AsyncMock(return_value=None)
        session.add = MagicMock()
        session.execute = AsyncMock()
        return session

    @pytest.fixture
    def mock_db_manager(self, mock_db_session: AsyncMock) -> MagicMock:
        """Create a mock database manager with session context."""
        db_manager = MagicMock()
        db_manager.session = _make_db_session_context(mock_db_session)
        db_manager.read_session = _make_db_session_context(mock_db_session)
        return db_manager

    @pytest.fixture
    def mock_event_bus(self) -> AsyncMock:
        """Create a mock event bus."""
        bus = AsyncMock()
        bus.publish = AsyncMock()
        return bus

    @pytest.fixture
    def mock_order_settings(self) -> MagicMock:
        """Create mock settings with order configuration."""
        settings = MagicMock()
        settings.order.limit_order_expiry_minutes = 15
        settings.trading.mode = TradingMode.PAPER
        settings.trading.candle_interval_min = 5
        settings.multi_strategy.enabled = False
        settings.exchange_fees = ExchangeFees()
        return settings

    @pytest.fixture
    def order_manager(
        self,
        mock_rest_client: AsyncMock,
        mock_db_manager: MagicMock,
        mock_event_bus: AsyncMock,
        mock_order_settings: MagicMock,
    ) -> OrderManager:
        """Create an OrderManager instance for testing."""
        return OrderManager(
            rest_client=mock_rest_client,
            db_manager=mock_db_manager,
            event_bus=mock_event_bus,
            settings=mock_order_settings,
        )

    # -------------------------------------------------------------------------
    # Properties Tests
    # -------------------------------------------------------------------------

    def test_pending_count_empty(self, order_manager: OrderManager) -> None:
        """Test pending_count is zero when no orders are tracked."""
        assert order_manager.pending_count == 0

    def test_pending_count_with_orders(self, order_manager: OrderManager) -> None:
        """Test pending_count reflects tracked pending orders."""
        order_manager._pending_orders["order-1"] = _make_order(order_id="order-1")
        order_manager._pending_orders["order-2"] = _make_order(order_id="order-2")

        assert order_manager.pending_count == 2

    def test_stats_initial_values(self, order_manager: OrderManager) -> None:
        """Test stats are initialized to zero."""
        stats = order_manager.stats

        assert stats["orders_placed"] == 0
        assert stats["orders_filled"] == 0
        assert stats["orders_expired"] == 0
        assert stats["orders_cancelled"] == 0
        assert stats["check_cycles"] == 0

    def test_stats_returns_copy(self, order_manager: OrderManager) -> None:
        """Test stats returns a copy, not the internal dict."""
        stats = order_manager.stats
        stats["orders_placed"] = 999

        assert order_manager.stats["orders_placed"] == 0

    # -------------------------------------------------------------------------
    # place_and_track Tests
    # -------------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_place_and_track_pending_order(
        self,
        order_manager: OrderManager,
        mock_rest_client: AsyncMock,
    ) -> None:
        """Test placing a limit order that remains pending."""
        pending_order = _make_order(
            order_id="paper-100",
            status=OrderStatus.PENDING,
        )
        mock_rest_client.place_limit_order.return_value = pending_order

        result = await order_manager.place_and_track(
            pair="XBT/USDC",
            side=TradeSide.BUY,
            amount=Decimal("0.001"),
            price=Decimal("42000"),
            strategy="threshold",
            signal_metadata={"reference_price": "42100"},
        )

        assert result.order_id == "paper-100"
        assert result.status == OrderStatus.PENDING

        # Order should be tracked in pending
        assert "paper-100" in order_manager._pending_orders
        assert order_manager.pending_count == 1
        assert order_manager.stats["orders_placed"] == 1

        # REST client should have been called
        mock_rest_client.place_limit_order.assert_awaited_once_with(
            pair="XBT/USDC",
            side=TradeSide.BUY,
            amount=Decimal("0.001"),
            price=Decimal("42000"),
            strategy="threshold",
            expires_in_seconds=15 * 60,
        )

    @pytest.mark.asyncio
    async def test_place_and_track_immediate_fill(
        self,
        order_manager: OrderManager,
        mock_rest_client: AsyncMock,
        mock_event_bus: AsyncMock,
    ) -> None:
        """Test placing an order that fills immediately."""
        filled_order = _make_order(
            order_id="paper-101",
            status=OrderStatus.FILLED,
        )
        filled_order.filled_amount = Decimal("0.001")
        filled_order.filled_price = Decimal("42000")
        filled_order.fee = Decimal("0.0672")
        mock_rest_client.place_limit_order.return_value = filled_order

        result = await order_manager.place_and_track(
            pair="XBT/USDC",
            side=TradeSide.BUY,
            amount=Decimal("0.001"),
            price=Decimal("42000"),
            strategy="threshold",
        )

        assert result.status == OrderStatus.FILLED

        # Should NOT be in pending tracking
        assert "paper-101" not in order_manager._pending_orders
        assert order_manager.pending_count == 0

        # Stats should reflect placement and fill
        assert order_manager.stats["orders_placed"] == 1
        assert order_manager.stats["orders_filled"] == 1

        # Fill event should be published
        mock_event_bus.publish.assert_awaited()

    @pytest.mark.asyncio
    async def test_publish_fill_event_runs_fill_handler_after_strategy_assigns_position_id(
        self,
        mock_rest_client: AsyncMock,
        mock_db_manager: MagicMock,
        mock_order_settings: MagicMock,
    ) -> None:
        """The fill handler must see the position_id assigned during TRADE_ORDER_FILLED."""
        event_bus = EventBus()
        order_manager = OrderManager(
            rest_client=mock_rest_client,
            db_manager=mock_db_manager,
            event_bus=event_bus,
            settings=mock_order_settings,
        )
        strategy = PositionAssigningStrategy(
            mock_order_settings,
            event_bus,
            mock_db_manager,
            bot_id="threshold",
            assigned_position_id=7,
        )
        await strategy.start()

        captured: dict[str, int] = {}

        async def fill_handler(order: FakeOrder) -> None:
            captured["position_id"] = order.signal_metadata["position_id"]

        order_manager.set_fill_handler(fill_handler)
        order = _make_order(
            order_id="paper-102",
            status=OrderStatus.FILLED,
            strategy="threshold",
            signal_metadata={"reference_price": "42000"},
        )
        order.filled_amount = Decimal("0.001")
        order.filled_price = Decimal("42000")
        order.fee = Decimal("0.0672")

        await order_manager._publish_fill_event(order)

        assert captured["position_id"] == 7

    @pytest.mark.asyncio
    async def test_place_and_track_uses_default_expiry(
        self,
        order_manager: OrderManager,
        mock_rest_client: AsyncMock,
        mock_order_settings: MagicMock,
    ) -> None:
        """Test that default expiry is computed from settings."""
        mock_order_settings.order.limit_order_expiry_minutes = 30
        pending_order = _make_order(status=OrderStatus.PENDING)
        mock_rest_client.place_limit_order.return_value = pending_order

        await order_manager.place_and_track(
            pair="XBT/USDC",
            side=TradeSide.BUY,
            amount=Decimal("0.001"),
            price=Decimal("42000"),
            strategy="threshold",
        )

        # Should use 30 * 60 = 1800 seconds
        call_kwargs = mock_rest_client.place_limit_order.call_args.kwargs
        assert call_kwargs["expires_in_seconds"] == 1800

    @pytest.mark.asyncio
    async def test_place_and_track_custom_expiry(
        self,
        order_manager: OrderManager,
        mock_rest_client: AsyncMock,
    ) -> None:
        """Test placing an order with custom expiry override."""
        pending_order = _make_order(status=OrderStatus.PENDING)
        mock_rest_client.place_limit_order.return_value = pending_order

        await order_manager.place_and_track(
            pair="XBT/USDC",
            side=TradeSide.BUY,
            amount=Decimal("0.001"),
            price=Decimal("42000"),
            strategy="threshold",
            expires_in_seconds=3600,
        )

        call_kwargs = mock_rest_client.place_limit_order.call_args.kwargs
        assert call_kwargs["expires_in_seconds"] == 3600

    @pytest.mark.asyncio
    async def test_place_and_track_attaches_signal_metadata(
        self,
        order_manager: OrderManager,
        mock_rest_client: AsyncMock,
    ) -> None:
        """Test that signal_metadata is attached to the order."""
        pending_order = _make_order(status=OrderStatus.PENDING)
        mock_rest_client.place_limit_order.return_value = pending_order

        metadata = {"reference_price": "42100", "position_id": 5}
        await order_manager.place_and_track(
            pair="XBT/USDC",
            side=TradeSide.BUY,
            amount=Decimal("0.001"),
            price=Decimal("42000"),
            strategy="threshold",
            signal_metadata=metadata,
        )

        assert pending_order.signal_metadata is not None
        assert pending_order.signal_metadata["reference_price"] == "42100"
        assert pending_order.signal_metadata["position_id"] == 5
        assert pending_order.signal_metadata["execution_interval"] == 5

    # -------------------------------------------------------------------------
    # on_ohlc Tests
    # -------------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_on_ohlc_stores_last_candle(self, order_manager: OrderManager) -> None:
        """Test that on_ohlc stores candle data for paper fill simulation."""
        candle = {
            "pair": "XBT/USDC",
            "interval": 5,
            "low": Decimal("41000"),
            "high": Decimal("43000"),
            "close": Decimal("42500"),
        }

        await order_manager.on_ohlc(candle)

        assert order_manager._last_candle is not None
        assert order_manager._last_candle["low"] == Decimal("41000")
        assert order_manager._last_candle["high"] == Decimal("43000")
        assert order_manager._last_candles[("XBT/USDC", 5)]["close"] == Decimal("42500")

    @pytest.mark.asyncio
    async def test_on_ohlc_replaces_previous_candle(self, order_manager: OrderManager) -> None:
        """Test that on_ohlc replaces the previously stored candle."""
        candle_1 = {
            "pair": "XBT/USDC",
            "interval": 5,
            "low": Decimal("40000"),
            "high": Decimal("41000"),
        }
        candle_2 = {
            "pair": "XBT/USDC",
            "interval": 5,
            "low": Decimal("42000"),
            "high": Decimal("44000"),
        }

        await order_manager.on_ohlc(candle_1)
        await order_manager.on_ohlc(candle_2)

        assert order_manager._last_candle["low"] == Decimal("42000")
        assert order_manager._last_candles[("XBT/USDC", 5)]["low"] == Decimal("42000")

    # -------------------------------------------------------------------------
    # check_pending_orders: Paper Mode Fill Simulation
    # -------------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_check_pending_buy_filled_when_low_hits_price(
        self,
        order_manager: OrderManager,
        mock_rest_client: AsyncMock,
        mock_event_bus: AsyncMock,
    ) -> None:
        """Test BUY limit fills when candle low <= limit price."""
        buy_order = _make_order(
            order_id="paper-200",
            side=TradeSide.BUY,
            price=Decimal("41500"),
            amount=Decimal("0.001"),
            pair="XBT/USDC",
            expires_at=datetime.now(UTC) + timedelta(hours=1),
        )
        order_manager._pending_orders["paper-200"] = buy_order

        # Candle low touches the limit price
        order_manager._last_candle = {
            "low": Decimal("41400"),
            "high": Decimal("42500"),
        }

        await order_manager.check_pending_orders()

        assert buy_order.status == OrderStatus.FILLED
        assert buy_order.filled_amount == Decimal("0.001")
        assert buy_order.filled_price == Decimal("41500")
        assert "paper-200" not in order_manager._pending_orders
        assert order_manager.stats["orders_filled"] == 1
        mock_event_bus.publish.assert_awaited()

    @pytest.mark.asyncio
    async def test_check_pending_buy_not_filled_when_low_above_price(
        self,
        order_manager: OrderManager,
    ) -> None:
        """Test BUY limit does NOT fill when candle low > limit price."""
        buy_order = _make_order(
            order_id="paper-201",
            side=TradeSide.BUY,
            price=Decimal("41000"),
            expires_at=datetime.now(UTC) + timedelta(hours=1),
        )
        order_manager._pending_orders["paper-201"] = buy_order

        # Candle low is above limit price
        order_manager._last_candle = {
            "low": Decimal("41500"),
            "high": Decimal("42500"),
        }

        await order_manager.check_pending_orders()

        assert buy_order.status == OrderStatus.PENDING
        assert "paper-201" in order_manager._pending_orders

    @pytest.mark.asyncio
    async def test_check_pending_sell_filled_when_high_hits_price(
        self,
        order_manager: OrderManager,
        mock_rest_client: AsyncMock,
        mock_event_bus: AsyncMock,
    ) -> None:
        """Test SELL limit fills when candle high >= limit price."""
        sell_order = _make_order(
            order_id="paper-202",
            side=TradeSide.SELL,
            price=Decimal("43000"),
            amount=Decimal("0.001"),
            pair="XBT/USDC",
            expires_at=datetime.now(UTC) + timedelta(hours=1),
        )
        order_manager._pending_orders["paper-202"] = sell_order

        # Candle high reaches the limit price
        order_manager._last_candle = {
            "low": Decimal("41500"),
            "high": Decimal("43500"),
        }

        await order_manager.check_pending_orders()

        assert sell_order.status == OrderStatus.FILLED
        assert sell_order.filled_amount == Decimal("0.001")
        assert sell_order.filled_price == Decimal("43000")
        assert "paper-202" not in order_manager._pending_orders
        assert order_manager.stats["orders_filled"] == 1

    @pytest.mark.asyncio
    async def test_check_pending_sell_not_filled_when_high_below_price(
        self,
        order_manager: OrderManager,
    ) -> None:
        """Test SELL limit does NOT fill when candle high < limit price."""
        sell_order = _make_order(
            order_id="paper-203",
            side=TradeSide.SELL,
            price=Decimal("44000"),
            expires_at=datetime.now(UTC) + timedelta(hours=1),
        )
        order_manager._pending_orders["paper-203"] = sell_order

        # Candle high is below limit price
        order_manager._last_candle = {
            "low": Decimal("41500"),
            "high": Decimal("43500"),
        }

        await order_manager.check_pending_orders()

        assert sell_order.status == OrderStatus.PENDING
        assert "paper-203" in order_manager._pending_orders

    @pytest.mark.asyncio
    async def test_check_pending_no_candle_data_skips_fill(
        self,
        order_manager: OrderManager,
    ) -> None:
        """Test that paper fill check is skipped when no candle data exists."""
        buy_order = _make_order(
            order_id="paper-204",
            side=TradeSide.BUY,
            price=Decimal("41000"),
            expires_at=datetime.now(UTC) + timedelta(hours=1),
        )
        order_manager._pending_orders["paper-204"] = buy_order

        # No candle data set
        assert order_manager._last_candle is None

        await order_manager.check_pending_orders()

        assert buy_order.status == OrderStatus.PENDING
        assert "paper-204" in order_manager._pending_orders

    @pytest.mark.asyncio
    async def test_check_pending_no_pending_orders_returns_early(
        self,
        order_manager: OrderManager,
    ) -> None:
        """Test that check_pending_orders returns early with no pending orders."""
        await order_manager.check_pending_orders()

        # check_cycles should NOT be incremented when no pending orders
        assert order_manager.stats["check_cycles"] == 0

    @pytest.mark.asyncio
    async def test_check_pending_increments_check_cycles(
        self,
        order_manager: OrderManager,
    ) -> None:
        """Test that check_cycles stat is incremented on each check."""
        order_manager._pending_orders["paper-205"] = _make_order(
            order_id="paper-205",
            expires_at=datetime.now(UTC) + timedelta(hours=1),
        )

        await order_manager.check_pending_orders()

        assert order_manager.stats["check_cycles"] == 1

    # -------------------------------------------------------------------------
    # check_pending_orders: Expiry Detection
    # -------------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_check_pending_expired_order(
        self,
        order_manager: OrderManager,
        mock_rest_client: AsyncMock,
    ) -> None:
        """Test that expired orders are detected and cancelled."""
        expired_order = _make_order(
            order_id="paper-300",
            expires_at=datetime.now(UTC) - timedelta(minutes=5),
        )
        order_manager._pending_orders["paper-300"] = expired_order

        await order_manager.check_pending_orders()

        assert expired_order.status == OrderStatus.EXPIRED
        assert "paper-300" not in order_manager._pending_orders
        assert order_manager.stats["orders_expired"] == 1
        mock_rest_client.cancel_order.assert_awaited_once_with("paper-300", "XBT/USDC")

    @pytest.mark.asyncio
    async def test_check_pending_not_yet_expired(
        self,
        order_manager: OrderManager,
    ) -> None:
        """Test that orders with future expiry are not cancelled."""
        order = _make_order(
            order_id="paper-301",
            expires_at=datetime.now(UTC) + timedelta(hours=1),
        )
        order_manager._pending_orders["paper-301"] = order

        # No candle data, so fill check won't trigger
        await order_manager.check_pending_orders()

        assert order.status == OrderStatus.PENDING
        assert "paper-301" in order_manager._pending_orders

    @pytest.mark.asyncio
    async def test_check_pending_expiry_before_fill_check(
        self,
        order_manager: OrderManager,
        mock_rest_client: AsyncMock,
    ) -> None:
        """Test that expiry is checked before fill, even if candle would fill."""
        expired_order = _make_order(
            order_id="paper-302",
            side=TradeSide.BUY,
            price=Decimal("41000"),
            expires_at=datetime.now(UTC) - timedelta(minutes=1),
        )
        order_manager._pending_orders["paper-302"] = expired_order

        # Candle would trigger fill, but expiry takes precedence
        order_manager._last_candle = {
            "low": Decimal("40000"),
            "high": Decimal("42000"),
        }

        await order_manager.check_pending_orders()

        assert expired_order.status == OrderStatus.EXPIRED
        assert "paper-302" not in order_manager._pending_orders

    # -------------------------------------------------------------------------
    # place_profit_target Tests
    # -------------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_place_profit_target(
        self,
        order_manager: OrderManager,
        mock_rest_client: AsyncMock,
    ) -> None:
        """Test placing a profit target limit sell for a position."""
        sell_order = _make_order(
            order_id="paper-400",
            side=TradeSide.SELL,
            price=Decimal("45000"),
            status=OrderStatus.PENDING,
        )
        mock_rest_client.place_limit_order.return_value = sell_order

        result = await order_manager.place_profit_target(
            position_id=42,
            pair="XBT/USDC",
            amount=Decimal("0.001"),
            target_price=Decimal("45000"),
            strategy="threshold",
        )

        assert result.order_id == "paper-400"
        assert order_manager._position_profit_targets[42] == "paper-400"
        assert "paper-400" in order_manager._pending_orders

        # Verify place_limit_order was called with SELL side
        call_kwargs = mock_rest_client.place_limit_order.call_args.kwargs
        assert call_kwargs["side"] == TradeSide.SELL
        assert call_kwargs["price"] == Decimal("45000")
        assert call_kwargs["expires_in_seconds"] == 86400

    @pytest.mark.asyncio
    async def test_place_profit_target_cancels_existing(
        self,
        order_manager: OrderManager,
        mock_rest_client: AsyncMock,
    ) -> None:
        """Test that placing a new profit target cancels the existing one."""
        # Set up existing profit target
        existing_order = _make_order(
            order_id="paper-401",
            side=TradeSide.SELL,
            status=OrderStatus.PENDING,
        )
        order_manager._pending_orders["paper-401"] = existing_order
        order_manager._position_profit_targets[42] = "paper-401"

        # Place new profit target
        new_order = _make_order(
            order_id="paper-402",
            side=TradeSide.SELL,
            price=Decimal("46000"),
            status=OrderStatus.PENDING,
        )
        mock_rest_client.place_limit_order.return_value = new_order

        await order_manager.place_profit_target(
            position_id=42,
            pair="XBT/USDC",
            amount=Decimal("0.001"),
            target_price=Decimal("46000"),
            strategy="threshold",
        )

        # Old order should be cancelled
        assert "paper-401" not in order_manager._pending_orders
        assert existing_order.status == OrderStatus.CANCELLED

        # New order should be tracked
        assert order_manager._position_profit_targets[42] == "paper-402"
        assert "paper-402" in order_manager._pending_orders

    @pytest.mark.asyncio
    async def test_place_profit_target_metadata(
        self,
        order_manager: OrderManager,
        mock_rest_client: AsyncMock,
    ) -> None:
        """Test that profit target includes correct signal_metadata."""
        sell_order = _make_order(
            order_id="paper-403",
            side=TradeSide.SELL,
            status=OrderStatus.PENDING,
        )
        mock_rest_client.place_limit_order.return_value = sell_order

        await order_manager.place_profit_target(
            position_id=99,
            pair="XBT/USDC",
            amount=Decimal("0.001"),
            target_price=Decimal("50000"),
            strategy="threshold",
        )

        # Verify signal_metadata was set on the order
        assert sell_order.signal_metadata is not None
        assert sell_order.signal_metadata["position_id"] == 99
        assert sell_order.signal_metadata["order_type"] == "profit_target"

    # -------------------------------------------------------------------------
    # cancel_profit_target Tests
    # -------------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_cancel_profit_target_existing(
        self,
        order_manager: OrderManager,
        mock_rest_client: AsyncMock,
    ) -> None:
        """Test cancelling an existing profit target before market sell."""
        order = _make_order(
            order_id="paper-500",
            side=TradeSide.SELL,
            status=OrderStatus.PENDING,
        )
        order_manager._pending_orders["paper-500"] = order
        order_manager._position_profit_targets[42] = "paper-500"

        result = await order_manager.cancel_profit_target(42)

        assert result is True
        assert order.status == OrderStatus.CANCELLED
        assert "paper-500" not in order_manager._pending_orders
        assert 42 not in order_manager._position_profit_targets
        assert order_manager.stats["orders_cancelled"] == 1
        mock_rest_client.cancel_order.assert_awaited_once_with("paper-500")

    @pytest.mark.asyncio
    async def test_cancel_profit_target_nonexistent(
        self,
        order_manager: OrderManager,
        mock_rest_client: AsyncMock,
    ) -> None:
        """Test cancelling a profit target that does not exist returns False."""
        result = await order_manager.cancel_profit_target(999)

        assert result is False
        mock_rest_client.cancel_order.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_cancel_profit_target_exchange_error_still_cleans_up(
        self,
        order_manager: OrderManager,
        mock_rest_client: AsyncMock,
    ) -> None:
        """Test that cancel_profit_target cleans up even if exchange cancel fails."""
        order = _make_order(
            order_id="paper-501",
            side=TradeSide.SELL,
            status=OrderStatus.PENDING,
        )
        order_manager._pending_orders["paper-501"] = order
        order_manager._position_profit_targets[42] = "paper-501"

        mock_rest_client.cancel_order.side_effect = Exception("Network error")

        result = await order_manager.cancel_profit_target(42)

        # Should still return True and clean up internal state
        assert result is True
        assert "paper-501" not in order_manager._pending_orders
        assert 42 not in order_manager._position_profit_targets
        assert order_manager.stats["orders_cancelled"] == 1

    # -------------------------------------------------------------------------
    # cancel_all_pending Tests
    # -------------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_cancel_all_pending_multiple_orders(
        self,
        order_manager: OrderManager,
        mock_rest_client: AsyncMock,
    ) -> None:
        """Test cancelling all pending orders during shutdown."""
        order_1 = _make_order(order_id="paper-600", pair="XBT/USDC")
        order_2 = _make_order(order_id="paper-601", pair="XBT/USDC")
        order_3 = _make_order(order_id="paper-602", pair="XBT/USDC")

        order_manager._pending_orders["paper-600"] = order_1
        order_manager._pending_orders["paper-601"] = order_2
        order_manager._pending_orders["paper-602"] = order_3
        order_manager._position_profit_targets[10] = "paper-600"

        count = await order_manager.cancel_all_pending()

        assert count == 3
        assert order_manager.pending_count == 0
        assert len(order_manager._position_profit_targets) == 0
        assert order_1.status == OrderStatus.CANCELLED
        assert order_2.status == OrderStatus.CANCELLED
        assert order_3.status == OrderStatus.CANCELLED
        assert mock_rest_client.cancel_order.await_count == 3

    @pytest.mark.asyncio
    async def test_cancel_all_pending_empty(self, order_manager: OrderManager) -> None:
        """Test cancel_all_pending with no pending orders returns zero."""
        count = await order_manager.cancel_all_pending()

        assert count == 0

    @pytest.mark.asyncio
    async def test_cancel_all_pending_partial_failure(
        self,
        order_manager: OrderManager,
        mock_rest_client: AsyncMock,
    ) -> None:
        """Test cancel_all_pending continues when some cancellations fail."""
        order_1 = _make_order(order_id="paper-610", pair="XBT/USDC")
        order_2 = _make_order(order_id="paper-611", pair="XBT/USDC")

        order_manager._pending_orders["paper-610"] = order_1
        order_manager._pending_orders["paper-611"] = order_2

        # First cancel fails, second succeeds
        mock_rest_client.cancel_order.side_effect = [
            Exception("Timeout"),
            None,
        ]

        count = await order_manager.cancel_all_pending()

        # Only the successful cancellation counted
        assert count == 1
        assert order_manager.pending_count == 0

    # -------------------------------------------------------------------------
    # Paper Fill Simulation Edge Cases
    # -------------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_paper_fill_buy_exact_low_equals_price(
        self,
        order_manager: OrderManager,
        mock_rest_client: AsyncMock,
    ) -> None:
        """Test BUY fills when candle low exactly equals limit price."""
        buy_order = _make_order(
            order_id="paper-700",
            side=TradeSide.BUY,
            price=Decimal("41500"),
            amount=Decimal("0.001"),
            pair="XBT/USDC",
            expires_at=datetime.now(UTC) + timedelta(hours=1),
        )
        order_manager._pending_orders["paper-700"] = buy_order

        order_manager._last_candle = {
            "low": Decimal("41500"),  # Exactly at limit price
            "high": Decimal("42500"),
        }

        await order_manager.check_pending_orders()

        assert buy_order.status == OrderStatus.FILLED

    @pytest.mark.asyncio
    async def test_paper_fill_sell_exact_high_equals_price(
        self,
        order_manager: OrderManager,
        mock_rest_client: AsyncMock,
    ) -> None:
        """Test SELL fills when candle high exactly equals limit price."""
        sell_order = _make_order(
            order_id="paper-701",
            side=TradeSide.SELL,
            price=Decimal("43000"),
            amount=Decimal("0.001"),
            pair="XBT/USDC",
            expires_at=datetime.now(UTC) + timedelta(hours=1),
        )
        order_manager._pending_orders["paper-701"] = sell_order

        order_manager._last_candle = {
            "low": Decimal("41500"),
            "high": Decimal("43000"),  # Exactly at limit price
        }

        await order_manager.check_pending_orders()

        assert sell_order.status == OrderStatus.FILLED

    @pytest.mark.asyncio
    async def test_paper_fill_zero_candle_data_skips(
        self,
        order_manager: OrderManager,
    ) -> None:
        """Test that candle data with zero low/high is ignored."""
        buy_order = _make_order(
            order_id="paper-702",
            side=TradeSide.BUY,
            price=Decimal("41000"),
            expires_at=datetime.now(UTC) + timedelta(hours=1),
        )
        order_manager._pending_orders["paper-702"] = buy_order

        order_manager._last_candle = {
            "low": Decimal("0"),
            "high": Decimal("0"),
        }

        await order_manager.check_pending_orders()

        assert buy_order.status == OrderStatus.PENDING

    @pytest.mark.asyncio
    async def test_paper_fill_updates_paper_balance_buy(
        self,
        order_manager: OrderManager,
        mock_rest_client: AsyncMock,
    ) -> None:
        """Test that paper BUY fill deducts USDC and adds BTC."""
        initial_usdc = Decimal("10000")
        initial_btc = Decimal("0.1")
        mock_rest_client._paper_balance = {
            "USDC": initial_usdc,
            "BTC": initial_btc,
        }
        mock_rest_client.paper_balance = mock_rest_client._paper_balance

        buy_order = _make_order(
            order_id="paper-703",
            side=TradeSide.BUY,
            price=Decimal("42000"),
            amount=Decimal("0.001"),
            pair="XBT/USDC",
            expires_at=datetime.now(UTC) + timedelta(hours=1),
        )
        order_manager._pending_orders["paper-703"] = buy_order

        order_manager._last_candle = {
            "low": Decimal("41000"),
            "high": Decimal("43000"),
        }

        await order_manager.check_pending_orders()

        assert buy_order.status == OrderStatus.FILLED

        # Balance should be updated
        value = Decimal("0.001") * Decimal("42000")  # 42 USDC
        fee = value * Decimal("0.0016")  # ~0.0672 USDC
        assert mock_rest_client._paper_balance["USDC"] == initial_usdc - value - fee
        assert mock_rest_client._paper_balance["BTC"] == initial_btc + Decimal("0.001")
        assert "XBT" not in mock_rest_client._paper_balance

    @pytest.mark.asyncio
    async def test_paper_fill_updates_paper_balance_sell_with_btc(
        self,
        order_manager: OrderManager,
        mock_rest_client: AsyncMock,
    ) -> None:
        """Test that paper SELL fill reads and updates the canonical BTC balance."""
        initial_usdc = Decimal("0")
        initial_btc = Decimal("0.1")
        mock_rest_client._paper_balance = {
            "USDC": initial_usdc,
            "BTC": initial_btc,
        }
        mock_rest_client.paper_balance = mock_rest_client._paper_balance

        sell_order = _make_order(
            order_id="paper-703-sell",
            side=TradeSide.SELL,
            price=Decimal("42000"),
            amount=Decimal("0.001"),
            pair="XBT/USDC",
            expires_at=datetime.now(UTC) + timedelta(hours=1),
        )
        order_manager._pending_orders["paper-703-sell"] = sell_order

        order_manager._last_candle = {
            "low": Decimal("41000"),
            "high": Decimal("43000"),
        }

        await order_manager.check_pending_orders()

        assert sell_order.status == OrderStatus.FILLED

        value = Decimal("0.001") * Decimal("42000")
        fee = value * Decimal("0.0016")
        assert mock_rest_client._paper_balance["BTC"] == initial_btc - Decimal("0.001")
        assert mock_rest_client._paper_balance["USDC"] == initial_usdc + value - fee
        assert "XBT" not in mock_rest_client._paper_balance

    @pytest.mark.asyncio
    async def test_paper_fill_insufficient_balance_expires_order(
        self,
        order_manager: OrderManager,
        mock_rest_client: AsyncMock,
    ) -> None:
        """Test that paper fill with insufficient balance expires the order."""
        mock_rest_client._paper_balance = {
            "USDC": Decimal("1"),  # Not enough
            "XBT": Decimal("0"),
        }
        mock_rest_client.paper_balance = mock_rest_client._paper_balance

        buy_order = _make_order(
            order_id="paper-704",
            side=TradeSide.BUY,
            price=Decimal("42000"),
            amount=Decimal("0.001"),
            pair="XBT/USDC",
            expires_at=datetime.now(UTC) + timedelta(hours=1),
        )
        order_manager._pending_orders["paper-704"] = buy_order

        order_manager._last_candle = {
            "low": Decimal("41000"),
            "high": Decimal("43000"),
        }

        await order_manager.check_pending_orders()

        # Order should be expired (insufficient balance handling)
        assert buy_order.status == OrderStatus.EXPIRED
        assert "paper-704" not in order_manager._pending_orders

    # -------------------------------------------------------------------------
    # Profit Target Cleanup Tests
    # -------------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_profit_target_cleaned_on_fill(
        self,
        order_manager: OrderManager,
        mock_rest_client: AsyncMock,
    ) -> None:
        """Test that profit target mapping is cleaned when order fills."""
        sell_order = _make_order(
            order_id="paper-800",
            side=TradeSide.SELL,
            price=Decimal("45000"),
            amount=Decimal("0.001"),
            pair="XBT/USDC",
            signal_metadata={"position_id": 42, "order_type": "profit_target"},
            expires_at=datetime.now(UTC) + timedelta(hours=24),
        )
        order_manager._pending_orders["paper-800"] = sell_order
        order_manager._position_profit_targets[42] = "paper-800"

        # Candle triggers fill
        order_manager._last_candle = {
            "low": Decimal("44000"),
            "high": Decimal("46000"),
        }

        await order_manager.check_pending_orders()

        assert sell_order.status == OrderStatus.FILLED
        assert 42 not in order_manager._position_profit_targets

    @pytest.mark.asyncio
    async def test_profit_target_cleaned_on_expiry(
        self,
        order_manager: OrderManager,
        mock_rest_client: AsyncMock,
    ) -> None:
        """Test that profit target mapping is cleaned when order expires."""
        sell_order = _make_order(
            order_id="paper-801",
            side=TradeSide.SELL,
            price=Decimal("45000"),
            signal_metadata={"position_id": 42, "order_type": "profit_target"},
            expires_at=datetime.now(UTC) - timedelta(minutes=5),
        )
        order_manager._pending_orders["paper-801"] = sell_order
        order_manager._position_profit_targets[42] = "paper-801"

        await order_manager.check_pending_orders()

        assert sell_order.status == OrderStatus.EXPIRED
        assert 42 not in order_manager._position_profit_targets
