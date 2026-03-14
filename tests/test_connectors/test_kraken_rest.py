"""Tests for the Kraken REST client.

This module tests the REST client functionality including:
- Balance queries
- Order placement (paper and live modes)
- Order management
- Error handling

IMPORTANT: These tests use mocked API calls and never make real
API requests to Kraken.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from krakenbot.config.settings import (
    DatabaseSettings,
    KrakenSettings,
    Settings,
    TradingMode,
    TradingSettings,
)
from krakenbot.connectors.kraken_rest import (
    MIN_ORDER_SIZE,
    KrakenRestClient,
)
from krakenbot.core.event_bus import EventBus, EventType, reset_event_bus
from krakenbot.core.exceptions import (
    InsufficientBalanceError,
    KrakenAPIError,
    OrderExecutionError,
)
from krakenbot.models.base import OrderStatus, TradeSide, TradeStatus


@pytest.fixture
def mock_paper_settings() -> Settings:
    """Create mock settings for paper trading.

    Returns:
        A Settings instance configured for paper trading.
    """
    return Settings(
        app_name="KrakenBot-Test",
        environment="testing",
        kraken=KrakenSettings(
            api_key="test_api_key",
            api_secret="test_api_secret",
        ),
        database=DatabaseSettings(
            url="postgresql+asyncpg://test:test@localhost:5432/krakenbot_test",
        ),
        trading=TradingSettings(
            mode=TradingMode.PAPER,
            pair="XBT/EUR",
        ),
    )


@pytest.fixture
def mock_live_settings() -> Settings:
    """Create mock settings for live trading.

    Returns:
        A Settings instance configured for live trading.
    """
    # Use model_construct to bypass validation for testing purposes.
    # This is necessary because the TradingSettings validator checks
    # confirm_live before it's available in the validation context.
    trading_settings = TradingSettings.model_construct(
        mode=TradingMode.LIVE,
        pair="XBT/EUR",
        confirm_live="yes",
        default_order_amount_eur=15.0,
        candle_interval_min=15,
    )

    return Settings(
        app_name="KrakenBot-Test",
        environment="testing",
        kraken=KrakenSettings(
            api_key="test_api_key",
            api_secret="test_api_secret",
        ),
        database=DatabaseSettings(
            url="postgresql+asyncpg://test:test@localhost:5432/krakenbot_test",
        ),
        trading=trading_settings,
    )


@pytest.fixture
def event_bus() -> EventBus:
    """Create a fresh EventBus for testing.

    Returns:
        A new EventBus instance.
    """
    reset_event_bus()
    return EventBus()


@pytest.fixture
def mock_db_manager() -> MagicMock:
    """Create a mock database manager.

    Returns:
        A mock DatabaseManager.
    """
    manager = MagicMock()

    # Create async context manager mock for session
    session_mock = MagicMock()
    session_mock.add = MagicMock()

    session_cm = MagicMock()
    session_cm.__aenter__ = AsyncMock(return_value=session_mock)
    session_cm.__aexit__ = AsyncMock(return_value=None)
    manager.session.return_value = session_cm

    return manager


@pytest.fixture
def paper_client(
    mock_paper_settings: Settings,
    event_bus: EventBus,
    mock_db_manager: MagicMock,
) -> KrakenRestClient:
    """Create a REST client in paper mode.

    Args:
        mock_paper_settings: Test settings for paper mode.
        event_bus: Test event bus.
        mock_db_manager: Mock database manager.

    Returns:
        A KrakenRestClient in paper mode.
    """
    with patch("ccxt.async_support.kraken"):
        return KrakenRestClient(mock_paper_settings, event_bus, mock_db_manager)


@pytest.fixture
def live_client(
    mock_live_settings: Settings,
    event_bus: EventBus,
    mock_db_manager: MagicMock,
) -> KrakenRestClient:
    """Create a REST client in live mode.

    Args:
        mock_live_settings: Test settings for live mode.
        event_bus: Test event bus.
        mock_db_manager: Mock database manager.

    Returns:
        A KrakenRestClient in live mode.
    """
    with patch("ccxt.async_support.kraken"):
        return KrakenRestClient(mock_live_settings, event_bus, mock_db_manager)


class TestKrakenRestClientInit:
    """Tests for REST client initialization."""

    def test_init_paper_mode(self, mock_paper_settings: Settings, event_bus: EventBus) -> None:
        """Test initialization in paper mode."""
        with patch("ccxt.async_support.kraken"):
            client = KrakenRestClient(mock_paper_settings, event_bus)

        assert client.is_paper_mode is True

    def test_init_live_mode(self, mock_live_settings: Settings, event_bus: EventBus) -> None:
        """Test initialization in live mode."""
        with patch("ccxt.async_support.kraken"):
            client = KrakenRestClient(mock_live_settings, event_bus)

        assert client.is_paper_mode is False

    def test_paper_balance_initialized(self, paper_client: KrakenRestClient) -> None:
        """Test that paper balance is initialized with zeros (populated by initialize_paper_balance)."""
        balance = paper_client.get_paper_balance()

        # Balance starts at zero — real balance is loaded at startup via initialize_paper_balance()
        assert "EUR" in balance
        assert balance["EUR"] == Decimal("0")
        assert "BTC" in balance
        assert balance["BTC"] == Decimal("0")


class TestKrakenRestClientBalance:
    """Tests for balance queries."""

    async def test_get_balance_paper_mode(self, paper_client: KrakenRestClient) -> None:
        """Test getting balance in paper mode."""
        await paper_client.set_paper_balance("EUR", Decimal("1000"))
        balance = await paper_client.get_balance()

        assert "EUR" in balance
        assert balance["EUR"] == Decimal("1000")

    async def test_get_balance_live_mode(self, live_client: KrakenRestClient) -> None:
        """Test getting balance in live mode."""
        # Mock the ccxt fetch_balance
        live_client._exchange.fetch_balance = AsyncMock(
            return_value={
                "free": {
                    "EUR": 500.0,
                    "XBT": 0.1,
                },
                "used": {},
                "total": {},
            }
        )

        balance = await live_client.get_balance()

        assert balance["EUR"] == Decimal("500.0")
        assert balance["XBT"] == Decimal("0.1")

    async def test_get_balance_api_error(self, live_client: KrakenRestClient) -> None:
        """Test balance query with API error."""
        import ccxt

        live_client._exchange.fetch_balance = AsyncMock(side_effect=ccxt.ExchangeError("API error"))

        with pytest.raises(KrakenAPIError):
            await live_client.get_balance()


class TestKrakenRestClientPaperTrading:
    """Tests for paper trading functionality."""

    async def test_place_market_order_buy(
        self, paper_client: KrakenRestClient, event_bus: EventBus
    ) -> None:
        """Test placing a buy order in paper mode."""
        received_events: list[dict[str, Any]] = []

        async def capture_event(data: dict[str, Any]) -> None:
            received_events.append(data)

        await event_bus.subscribe(EventType.TRADE_ORDER_FILLED, capture_event)

        # Set initial balance and price for paper trading
        await paper_client.set_paper_balance("EUR", Decimal("1000"))
        paper_client.update_last_price("XBT/EUR", Decimal("42000"))

        trade = await paper_client.place_market_order(
            "XBT/EUR",
            TradeSide.BUY,
            Decimal("0.001"),
            strategy="test",
        )

        assert trade.side == TradeSide.BUY
        assert trade.amount == Decimal("0.001")
        assert trade.price == Decimal("42000")
        assert trade.status == TradeStatus.FILLED
        assert "paper" in trade.order_id.lower()

        # Check event was published
        assert len(received_events) == 1
        assert received_events[0]["mode"] == "paper"

    async def test_place_market_order_sell(self, paper_client: KrakenRestClient) -> None:
        """Test placing a sell order in paper mode."""
        await paper_client.set_paper_balance("BTC", Decimal("0.1"))
        paper_client.update_last_price("XBT/EUR", Decimal("42000"))

        trade = await paper_client.place_market_order(
            "XBT/EUR",
            TradeSide.SELL,
            Decimal("0.001"),
            strategy="test",
        )

        assert trade.side == TradeSide.SELL
        assert trade.status == TradeStatus.FILLED

    async def test_paper_balance_updates_on_buy(self, paper_client: KrakenRestClient) -> None:
        """Test that paper balance updates correctly on buy."""
        await paper_client.set_paper_balance("EUR", Decimal("1000"))
        initial_eur = paper_client.get_paper_balance()["EUR"]
        paper_client.update_last_price("XBT/EUR", Decimal("42000"))

        await paper_client.place_market_order(
            "XBT/EUR",
            TradeSide.BUY,
            Decimal("0.001"),
            strategy="test",
        )

        final_balance = paper_client.get_paper_balance()

        # Should have less EUR
        assert final_balance["EUR"] < initial_eur
        # Paper balances should keep a single canonical BTC key
        assert final_balance["BTC"] == Decimal("0.001")
        assert "XBT" not in final_balance

    async def test_paper_balance_updates_on_sell(self, paper_client: KrakenRestClient) -> None:
        """Test that paper balance updates correctly on sell."""
        await paper_client.set_paper_balance("BTC", Decimal("0.1"))
        await paper_client.set_paper_balance("EUR", Decimal("0"))
        paper_client.update_last_price("XBT/EUR", Decimal("42000"))

        await paper_client.place_market_order(
            "XBT/EUR",
            TradeSide.SELL,
            Decimal("0.001"),
            strategy="test",
        )

        final_balance = paper_client.get_paper_balance()

        # Paper balances should keep a single canonical BTC key
        assert final_balance["BTC"] == Decimal("0.099")
        assert "XBT" not in final_balance
        # Should have gained EUR
        assert final_balance["EUR"] > 0

    async def test_paper_insufficient_balance_buy(self, paper_client: KrakenRestClient) -> None:
        """Test buy order fails with insufficient balance."""
        await paper_client.set_paper_balance("EUR", Decimal("1"))  # Very little EUR
        paper_client.update_last_price("XBT/EUR", Decimal("42000"))

        with pytest.raises(InsufficientBalanceError):
            await paper_client.place_market_order(
                "XBT/EUR",
                TradeSide.BUY,
                Decimal("1"),  # Try to buy 1 BTC
                strategy="test",
            )

    async def test_paper_insufficient_balance_sell(self, paper_client: KrakenRestClient) -> None:
        """Test sell order fails with insufficient balance."""
        await paper_client.set_paper_balance("BTC", Decimal("0"))
        paper_client.update_last_price("XBT/EUR", Decimal("42000"))

        with pytest.raises(InsufficientBalanceError):
            await paper_client.place_market_order(
                "XBT/EUR",
                TradeSide.SELL,
                Decimal("0.001"),
                strategy="test",
            )

    async def test_place_limit_order_immediate_fill_buy_normalizes_btc(
        self,
        paper_client: KrakenRestClient,
    ) -> None:
        """Immediate paper BUY limit fills should credit BTC, not create XBT."""
        await paper_client.set_paper_balance("EUR", Decimal("1000"))
        paper_client.update_last_price("XBT/EUR", Decimal("42000"))

        order = await paper_client.place_limit_order(
            "XBT/EUR",
            TradeSide.BUY,
            Decimal("0.001"),
            Decimal("43000"),
            strategy="test",
        )

        final_balance = paper_client.get_paper_balance()

        assert order.status == OrderStatus.FILLED
        assert final_balance["BTC"] == Decimal("0.001")
        assert "XBT" not in final_balance

    async def test_place_limit_order_immediate_fill_sell_uses_btc_balance(
        self,
        paper_client: KrakenRestClient,
    ) -> None:
        """Immediate paper SELL limit fills should read the canonical BTC balance."""
        await paper_client.set_paper_balance("BTC", Decimal("0.1"))
        paper_client.update_last_price("XBT/EUR", Decimal("42000"))

        order = await paper_client.place_limit_order(
            "XBT/EUR",
            TradeSide.SELL,
            Decimal("0.001"),
            Decimal("41000"),
            strategy="test",
        )

        final_balance = paper_client.get_paper_balance()

        assert order.status == OrderStatus.FILLED
        assert final_balance["BTC"] == Decimal("0.099")
        assert "XBT" not in final_balance


class TestKrakenRestClientLiveTrading:
    """Tests for live trading functionality."""

    async def test_place_market_order_live(
        self, live_client: KrakenRestClient, event_bus: EventBus
    ) -> None:
        """Test placing a live market order."""
        received_events: list[dict[str, Any]] = []

        async def capture_event(data: dict[str, Any]) -> None:
            received_events.append(data)

        await event_bus.subscribe(EventType.TRADE_ORDER_FILLED, capture_event)

        # Mock ccxt create_market_order
        live_client._exchange.create_market_order = AsyncMock(
            return_value={
                "id": "OXXXXX-XXXXX",
                "filled": 0.001,
                "average": 42000,
                "fee": {"cost": 0.11, "currency": "EUR"},
            }
        )

        trade = await live_client.place_market_order(
            "XBT/EUR",
            TradeSide.BUY,
            Decimal("0.001"),
            strategy="test",
        )

        assert trade.status == TradeStatus.FILLED
        assert trade.order_id == "OXXXXX-XXXXX"
        assert trade.price == Decimal("42000")

        # Check event was published
        assert len(received_events) == 1
        assert received_events[0]["mode"] == "live"

    async def test_live_order_insufficient_funds(
        self, live_client: KrakenRestClient, event_bus: EventBus
    ) -> None:
        """Test live order with insufficient funds."""
        import ccxt

        received_events: list[dict[str, Any]] = []

        async def capture_event(data: dict[str, Any]) -> None:
            received_events.append(data)

        await event_bus.subscribe(EventType.TRADE_ORDER_FAILED, capture_event)

        live_client._exchange.create_market_order = AsyncMock(
            side_effect=ccxt.InsufficientFunds("Not enough EUR")
        )

        with pytest.raises(InsufficientBalanceError):
            await live_client.place_market_order(
                "XBT/EUR",
                TradeSide.BUY,
                Decimal("0.001"),
                strategy="test",
            )

        # Check failure event was published
        assert len(received_events) == 1

    async def test_live_order_api_error(self, live_client: KrakenRestClient) -> None:
        """Test live order with API error."""
        import ccxt

        live_client._exchange.create_market_order = AsyncMock(
            side_effect=ccxt.ExchangeError("API error")
        )

        with pytest.raises(OrderExecutionError):
            await live_client.place_market_order(
                "XBT/EUR",
                TradeSide.BUY,
                Decimal("0.001"),
                strategy="test",
            )


class TestKrakenRestClientOrderValidation:
    """Tests for order validation."""

    async def test_minimum_order_size_validation(self, paper_client: KrakenRestClient) -> None:
        """Test that orders below minimum size are rejected."""
        paper_client.update_last_price("XBT/EUR", Decimal("42000"))

        with pytest.raises(OrderExecutionError) as exc_info:
            await paper_client.place_market_order(
                "XBT/EUR",
                TradeSide.BUY,
                Decimal("0.00001"),  # Below minimum
                strategy="test",
            )

        assert "minimum" in str(exc_info.value).lower()

    def test_min_order_sizes_defined(self) -> None:
        """Test that minimum order sizes are defined."""
        assert "XBT/EUR" in MIN_ORDER_SIZE
        assert "XBT/USD" in MIN_ORDER_SIZE
        assert MIN_ORDER_SIZE["XBT/EUR"] == Decimal("0.0001")


class TestKrakenRestClientOrderManagement:
    """Tests for order management functionality."""

    async def test_get_open_orders_paper(self, paper_client: KrakenRestClient) -> None:
        """Test getting open orders in paper mode."""
        orders = await paper_client.get_open_orders()

        assert isinstance(orders, list)

    async def test_get_open_orders_live(self, live_client: KrakenRestClient) -> None:
        """Test getting open orders in live mode."""
        live_client._exchange.fetch_open_orders = AsyncMock(
            return_value=[
                {
                    "id": "OXXXXX-1",
                    "symbol": "XBT/EUR",
                    "side": "buy",
                    "amount": 0.001,
                    "filled": 0,
                    "price": 42000,
                    "status": "open",
                    "timestamp": 1234567890,
                }
            ]
        )

        orders = await live_client.get_open_orders()

        assert len(orders) == 1
        assert orders[0]["order_id"] == "OXXXXX-1"

    async def test_cancel_order_paper(
        self, paper_client: KrakenRestClient, event_bus: EventBus
    ) -> None:
        """Test cancelling order in paper mode."""
        # Add a paper order
        paper_client._paper_orders["test-order-1"] = {"pair": "XBT/EUR"}

        received_events: list[dict[str, Any]] = []

        async def capture_event(data: dict[str, Any]) -> None:
            received_events.append(data)

        await event_bus.subscribe(EventType.TRADE_ORDER_CANCELLED, capture_event)

        result = await paper_client.cancel_order("test-order-1")

        assert result is True
        assert len(received_events) == 1

    async def test_cancel_nonexistent_order_paper(self, paper_client: KrakenRestClient) -> None:
        """Test cancelling non-existent paper order."""
        result = await paper_client.cancel_order("nonexistent")

        assert result is False

    async def test_cancel_order_live(
        self, live_client: KrakenRestClient, event_bus: EventBus
    ) -> None:
        """Test cancelling order in live mode."""
        live_client._exchange.cancel_order = AsyncMock(return_value=True)

        received_events: list[dict[str, Any]] = []

        async def capture_event(data: dict[str, Any]) -> None:
            received_events.append(data)

        await event_bus.subscribe(EventType.TRADE_ORDER_CANCELLED, capture_event)

        result = await live_client.cancel_order("OXXXXX-1", "XBT/EUR")

        assert result is True
        assert len(received_events) == 1


class TestKrakenRestClientTicker:
    """Tests for ticker functionality."""

    async def test_get_ticker(self, paper_client: KrakenRestClient) -> None:
        """Test getting ticker data."""
        paper_client._exchange.fetch_ticker = AsyncMock(
            return_value={
                "bid": 41900,
                "ask": 42100,
                "last": 42000,
                "baseVolume": 1000,
                "high": 43000,
                "low": 41000,
                "timestamp": 1234567890,
            }
        )

        ticker = await paper_client.get_ticker("XBT/EUR")

        assert ticker["pair"] == "XBT/EUR"
        assert ticker["last"] == Decimal("42000")
        assert ticker["bid"] == Decimal("41900")
        assert ticker["ask"] == Decimal("42100")

    async def test_get_ticker_updates_last_price(self, paper_client: KrakenRestClient) -> None:
        """Test that get_ticker updates last price for paper trading."""
        paper_client._exchange.fetch_ticker = AsyncMock(
            return_value={
                "last": 45000,
            }
        )

        await paper_client.get_ticker("XBT/EUR")

        assert paper_client._last_prices["XBT/EUR"] == Decimal("45000")


class TestKrakenRestClientStatistics:
    """Tests for statistics tracking."""

    def test_stats_initialized(self, paper_client: KrakenRestClient) -> None:
        """Test that stats are initialized."""
        stats = paper_client.stats

        assert stats["orders_placed"] == 0
        assert stats["orders_filled"] == 0
        assert stats["orders_failed"] == 0
        assert stats["api_calls"] == 0

    async def test_stats_track_paper_orders(self, paper_client: KrakenRestClient) -> None:
        """Test that paper orders are tracked in stats."""
        await paper_client.set_paper_balance("EUR", Decimal("1000"))
        paper_client.update_last_price("XBT/EUR", Decimal("42000"))

        await paper_client.place_market_order(
            "XBT/EUR",
            TradeSide.BUY,
            Decimal("0.001"),
            strategy="test",
        )

        stats = paper_client.stats
        assert stats["orders_placed"] == 1
        assert stats["orders_filled"] == 1

    async def test_stats_track_live_orders(self, live_client: KrakenRestClient) -> None:
        """Test that live orders are tracked in stats."""
        live_client._exchange.create_market_order = AsyncMock(
            return_value={
                "id": "OXXXXX-1",
                "filled": 0.001,
                "average": 42000,
                "fee": {"cost": 0.11, "currency": "EUR"},
            }
        )

        await live_client.place_market_order(
            "XBT/EUR",
            TradeSide.BUY,
            Decimal("0.001"),
            strategy="test",
        )

        stats = live_client.stats
        assert stats["api_calls"] >= 1
        assert stats["orders_placed"] == 1
        assert stats["orders_filled"] == 1


class TestKrakenRestClientPaperBalance:
    """Tests for paper balance management."""

    async def test_set_paper_balance(self, paper_client: KrakenRestClient) -> None:
        """Test setting paper balance."""
        await paper_client.set_paper_balance("EUR", Decimal("5000"))

        balance = paper_client.get_paper_balance()
        assert balance["EUR"] == Decimal("5000")

    async def test_set_paper_balance_live_mode_ignored(self, live_client: KrakenRestClient) -> None:
        """Test that set_paper_balance is ignored in live mode."""
        # This should not raise but log a warning
        await live_client.set_paper_balance("EUR", Decimal("5000"))
        # Live mode doesn't use paper balance


class TestKrakenRestClientClose:
    """Tests for client cleanup."""

    async def test_close_calls_exchange_close(self, paper_client: KrakenRestClient) -> None:
        """Test that close properly cleans up."""
        paper_client._exchange.close = AsyncMock()

        await paper_client.close()

        paper_client._exchange.close.assert_called_once()
