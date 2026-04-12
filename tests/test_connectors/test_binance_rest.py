"""Tests for the Binance REST client.

This module tests the REST client functionality including:
- Balance queries
- Order placement (paper and live modes)
- Order management
- MIN_NOTIONAL validation
- BNB fee asset handling
- Error handling

IMPORTANT: These tests use mocked API calls and never make real
API requests to Binance.
"""

from __future__ import annotations

from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from krakenbot.config.settings import (
    BinanceSettings,
    DatabaseSettings,
    ExchangeFees,
    KrakenSettings,
    Settings,
    TradingMode,
    TradingSettings,
)
from krakenbot.connectors.binance.rest import (
    BinanceRestClient,
)
from krakenbot.core.event_bus import EventBus, reset_event_bus
from krakenbot.core.exceptions import (
    InsufficientBalanceError,
    OrderExecutionError,
)
from krakenbot.models.base import OrderStatus, TradeSide, TradeStatus


@pytest.fixture
def mock_binance_paper_settings() -> Settings:
    """Create mock settings for paper trading on Binance."""
    return Settings(
        app_name="KrakenBot-Test",
        environment="testing",
        exchange_name="binance",
        kraken=KrakenSettings(
            api_key="test_api_key",
            api_secret="test_api_secret",
        ),
        binance=BinanceSettings(
            api_key="test_binance_key",
            api_secret="test_binance_secret",
        ),
        database=DatabaseSettings(
            url="postgresql+asyncpg://test:test@localhost:5432/krakenbot_test",
        ),
        trading=TradingSettings(
            mode=TradingMode.PAPER,
            pair="BTC/USDC",
        ),
        exchange_fees=ExchangeFees.binance_defaults(use_bnb=True),
    )


@pytest.fixture
def mock_binance_live_settings() -> Settings:
    """Create mock settings for live trading on Binance."""
    trading_settings = TradingSettings.model_construct(
        mode=TradingMode.LIVE,
        pair="BTC/USDC",
        confirm_live="yes",
        default_order_amount_eur=100.0,
        candle_interval_min=15,
    )

    return Settings(
        app_name="KrakenBot-Test",
        environment="testing",
        exchange_name="binance",
        kraken=KrakenSettings(
            api_key="test_api_key",
            api_secret="test_api_secret",
        ),
        binance=BinanceSettings(
            api_key="test_binance_key",
            api_secret="test_binance_secret",
        ),
        database=DatabaseSettings(
            url="postgresql+asyncpg://test:test@localhost:5432/krakenbot_test",
        ),
        trading=trading_settings,
        exchange_fees=ExchangeFees.binance_defaults(use_bnb=True),
    )


@pytest.fixture
def binance_event_bus() -> EventBus:
    """Create a fresh EventBus for testing."""
    reset_event_bus()
    return EventBus()


@pytest.fixture
def binance_mock_db_manager() -> MagicMock:
    """Create a mock database manager."""
    manager = MagicMock()

    session_mock = MagicMock()
    session_mock.add = MagicMock()

    session_cm = MagicMock()
    session_cm.__aenter__ = AsyncMock(return_value=session_mock)
    session_cm.__aexit__ = AsyncMock(return_value=None)
    manager.session.return_value = session_cm

    return manager


@pytest.fixture
def paper_binance_client(
    mock_binance_paper_settings: Settings,
    binance_event_bus: EventBus,
    binance_mock_db_manager: MagicMock,
) -> BinanceRestClient:
    """Create a Binance REST client in paper mode."""
    with patch("ccxt.async_support.binance"):
        return BinanceRestClient(
            mock_binance_paper_settings,
            binance_event_bus,
            binance_mock_db_manager,
        )


@pytest.fixture
def live_binance_client(
    mock_binance_live_settings: Settings,
    binance_event_bus: EventBus,
    binance_mock_db_manager: MagicMock,
) -> BinanceRestClient:
    """Create a Binance REST client in live mode."""
    with patch("ccxt.async_support.binance"):
        return BinanceRestClient(
            mock_binance_live_settings,
            binance_event_bus,
            binance_mock_db_manager,
        )


# =========================================================================
# Initialization tests
# =========================================================================


class TestBinanceRestClientInit:
    """Tests for REST client initialization."""

    def test_init_paper_mode(
        self, mock_binance_paper_settings: Settings, binance_event_bus: EventBus
    ) -> None:
        """Test initialization in paper mode."""
        with patch("ccxt.async_support.binance"):
            client = BinanceRestClient(mock_binance_paper_settings, binance_event_bus)

        assert client.exchange_name == "binance"
        assert client.is_paper_mode is True
        assert client.stats == {
            "orders_placed": 0,
            "orders_filled": 0,
            "orders_failed": 0,
            "api_calls": 0,
        }

    def test_init_live_mode(
        self, mock_binance_live_settings: Settings, binance_event_bus: EventBus
    ) -> None:
        """Test initialization in live mode."""
        with patch("ccxt.async_support.binance"):
            client = BinanceRestClient(mock_binance_live_settings, binance_event_bus)

        assert client.exchange_name == "binance"
        assert client.is_paper_mode is False

    def test_initial_paper_balance_structure(self, paper_binance_client: BinanceRestClient) -> None:
        """Paper balance should have quote and base currencies initialized to 0."""
        balance = paper_binance_client.paper_balance
        assert "USDC" in balance
        assert "BTC" in balance


# =========================================================================
# Paper balance tests
# =========================================================================


class TestBinancePaperBalance:
    """Tests for paper balance management."""

    @pytest.mark.asyncio
    async def test_get_balance_paper(self, paper_binance_client: BinanceRestClient) -> None:
        """Paper mode get_balance returns in-memory balance."""
        paper_binance_client._paper_balance = {
            "USDC": Decimal("5000"),
            "BTC": Decimal("0.1"),
        }
        balance = await paper_binance_client.get_balance()
        assert balance["USDC"] == Decimal("5000")
        assert balance["BTC"] == Decimal("0.1")

    @pytest.mark.asyncio
    async def test_set_paper_balance(self, paper_binance_client: BinanceRestClient) -> None:
        """set_paper_balance updates local state."""
        await paper_binance_client.set_paper_balance("USDC", Decimal("2000"))
        assert paper_binance_client._paper_balance["USDC"] == Decimal("2000")

    def test_get_paper_balance_returns_copy(self, paper_binance_client: BinanceRestClient) -> None:
        """get_paper_balance returns a copy, not a reference."""
        paper_binance_client._paper_balance = {"USDC": Decimal("1000")}
        bal = paper_binance_client.get_paper_balance()
        bal["USDC"] = Decimal("0")
        assert paper_binance_client._paper_balance["USDC"] == Decimal("1000")

    def test_update_last_price(self, paper_binance_client: BinanceRestClient) -> None:
        """update_last_price stores the price."""
        paper_binance_client.update_last_price("BTC/USDC", Decimal("65000"))
        assert paper_binance_client._last_prices["BTC/USDC"] == Decimal("65000")

    def test_remove_paper_order(self, paper_binance_client: BinanceRestClient) -> None:
        """remove_paper_order deletes from in-memory orders."""
        paper_binance_client._paper_orders["test-123"] = {"order_id": "test-123"}
        paper_binance_client.remove_paper_order("test-123")
        assert "test-123" not in paper_binance_client._paper_orders

    def test_remove_paper_order_missing(self, paper_binance_client: BinanceRestClient) -> None:
        """remove_paper_order does not raise for missing order."""
        paper_binance_client.remove_paper_order("nonexistent")


# =========================================================================
# Market order tests (paper mode)
# =========================================================================


class TestBinancePaperMarketOrders:
    """Tests for market orders in paper mode."""

    @pytest.mark.asyncio
    async def test_place_market_buy_paper(self, paper_binance_client: BinanceRestClient) -> None:
        """Paper market BUY deducts USDC + fee, adds BTC."""
        paper_binance_client._paper_balance = {
            "USDC": Decimal("10000"),
            "BTC": Decimal("0"),
        }
        paper_binance_client._last_prices["BTC/USDC"] = Decimal("60000")

        trade = await paper_binance_client.place_market_order(
            "BTC/USDC", TradeSide.BUY, Decimal("0.01"), "test_strategy"
        )

        assert trade.side == TradeSide.BUY
        assert trade.amount == Decimal("0.01")
        assert trade.price == Decimal("60000")
        assert trade.status == TradeStatus.FILLED
        assert trade.fee > Decimal("0")

        # Balance check: spent 600 USDC + fee
        assert paper_binance_client._paper_balance["BTC"] == Decimal("0.01")
        expected_usdc = Decimal("10000") - Decimal("600") - trade.fee
        assert paper_binance_client._paper_balance["USDC"] == expected_usdc

    @pytest.mark.asyncio
    async def test_place_market_sell_paper(self, paper_binance_client: BinanceRestClient) -> None:
        """Paper market SELL deducts BTC, adds USDC minus fee."""
        paper_binance_client._paper_balance = {
            "USDC": Decimal("0"),
            "BTC": Decimal("0.01"),
        }
        paper_binance_client._last_prices["BTC/USDC"] = Decimal("60000")

        trade = await paper_binance_client.place_market_order(
            "BTC/USDC", TradeSide.SELL, Decimal("0.01"), "test_strategy"
        )

        assert trade.side == TradeSide.SELL
        assert trade.status == TradeStatus.FILLED

        # Balance check: received 600 USDC minus fee
        assert paper_binance_client._paper_balance["BTC"] == Decimal("0")
        expected_usdc = Decimal("600") - trade.fee
        assert paper_binance_client._paper_balance["USDC"] == expected_usdc

    @pytest.mark.asyncio
    async def test_place_market_order_insufficient_balance(
        self, paper_binance_client: BinanceRestClient
    ) -> None:
        """Paper market BUY with insufficient USDC raises error."""
        paper_binance_client._paper_balance = {
            "USDC": Decimal("100"),
            "BTC": Decimal("0"),
        }
        paper_binance_client._last_prices["BTC/USDC"] = Decimal("60000")

        with pytest.raises(InsufficientBalanceError):
            await paper_binance_client.place_market_order(
                "BTC/USDC", TradeSide.BUY, Decimal("0.01"), "test_strategy"
            )

    @pytest.mark.asyncio
    async def test_min_order_size_validation(self, paper_binance_client: BinanceRestClient) -> None:
        """Order below minimum lot size is rejected."""
        paper_binance_client._last_prices["BTC/USDC"] = Decimal("60000")

        with pytest.raises(OrderExecutionError, match="below minimum"):
            await paper_binance_client.place_market_order(
                "BTC/USDC", TradeSide.BUY, Decimal("0.000001"), "test"
            )


# =========================================================================
# MIN_NOTIONAL validation
# =========================================================================


class TestBinanceMinNotional:
    """Tests for MIN_NOTIONAL validation (5 USDC)."""

    @pytest.mark.asyncio
    async def test_min_notional_market_order_rejected(
        self, paper_binance_client: BinanceRestClient
    ) -> None:
        """Market order below 5 USDC notional is rejected."""
        paper_binance_client._paper_balance = {"USDC": Decimal("10000"), "BTC": Decimal("0")}
        paper_binance_client._last_prices["BTC/USDC"] = Decimal("60000")

        # 0.00005 BTC * 60000 = 3 USDC < 5 USDC min
        with pytest.raises(OrderExecutionError, match="below Binance minimum"):
            await paper_binance_client.place_market_order(
                "BTC/USDC", TradeSide.BUY, Decimal("0.00005"), "test"
            )

    @pytest.mark.asyncio
    async def test_min_notional_limit_order_rejected(
        self, paper_binance_client: BinanceRestClient
    ) -> None:
        """Limit order below 5 USDC notional is rejected."""
        paper_binance_client._paper_balance = {"USDC": Decimal("10000"), "BTC": Decimal("0")}

        # 0.00005 * 60000 = 3 USDC < 5 USDC min
        with pytest.raises(OrderExecutionError, match="below Binance minimum"):
            await paper_binance_client.place_limit_order(
                "BTC/USDC",
                TradeSide.BUY,
                Decimal("0.00005"),
                Decimal("60000"),
                "test",
            )

    @pytest.mark.asyncio
    async def test_min_notional_passes_at_threshold(
        self, paper_binance_client: BinanceRestClient
    ) -> None:
        """Order at exactly 5 USDC notional is accepted."""
        paper_binance_client._paper_balance = {"USDC": Decimal("10000"), "BTC": Decimal("0")}
        paper_binance_client._last_prices["BTC/USDC"] = Decimal("100000")

        # 0.00005 BTC * 100000 = 5 USDC = exactly MIN_NOTIONAL
        trade = await paper_binance_client.place_market_order(
            "BTC/USDC", TradeSide.BUY, Decimal("0.00005"), "test"
        )
        assert trade.status == TradeStatus.FILLED


# =========================================================================
# Limit order tests (paper mode)
# =========================================================================


class TestBinancePaperLimitOrders:
    """Tests for limit orders in paper mode."""

    @pytest.mark.asyncio
    async def test_limit_order_immediate_fill_buy(
        self, paper_binance_client: BinanceRestClient
    ) -> None:
        """Limit BUY at or above current price fills immediately."""
        paper_binance_client._paper_balance = {"USDC": Decimal("10000"), "BTC": Decimal("0")}
        paper_binance_client._last_prices["BTC/USDC"] = Decimal("60000")

        order = await paper_binance_client.place_limit_order(
            "BTC/USDC", TradeSide.BUY, Decimal("0.01"), Decimal("61000"), "test"
        )

        assert order.status == OrderStatus.FILLED
        assert order.filled_amount == Decimal("0.01")
        assert paper_binance_client._paper_balance["BTC"] == Decimal("0.01")

    @pytest.mark.asyncio
    async def test_limit_order_pending_buy(self, paper_binance_client: BinanceRestClient) -> None:
        """Limit BUY below current price creates PENDING order."""
        paper_binance_client._paper_balance = {"USDC": Decimal("10000"), "BTC": Decimal("0")}
        paper_binance_client._last_prices["BTC/USDC"] = Decimal("60000")

        order = await paper_binance_client.place_limit_order(
            "BTC/USDC", TradeSide.BUY, Decimal("0.01"), Decimal("59000"), "test"
        )

        assert order.status == OrderStatus.PENDING
        assert order.filled_amount == Decimal("0")
        # Balance should not change for pending order
        assert paper_binance_client._paper_balance["BTC"] == Decimal("0")
        # Order tracked in paper_orders
        assert any(o.get("pair") == "BTC/USDC" for o in paper_binance_client._paper_orders.values())

    @pytest.mark.asyncio
    async def test_limit_order_immediate_fill_sell(
        self, paper_binance_client: BinanceRestClient
    ) -> None:
        """Limit SELL at or below current price fills immediately."""
        paper_binance_client._paper_balance = {"USDC": Decimal("0"), "BTC": Decimal("0.01")}
        paper_binance_client._last_prices["BTC/USDC"] = Decimal("60000")

        order = await paper_binance_client.place_limit_order(
            "BTC/USDC", TradeSide.SELL, Decimal("0.01"), Decimal("59000"), "test"
        )

        assert order.status == OrderStatus.FILLED
        assert paper_binance_client._paper_balance["BTC"] == Decimal("0")


# =========================================================================
# Cancel order tests
# =========================================================================


class TestBinancePaperCancelOrder:
    """Tests for order cancellation."""

    @pytest.mark.asyncio
    async def test_cancel_existing_paper_order(
        self, paper_binance_client: BinanceRestClient
    ) -> None:
        """Cancelling an existing paper order returns True."""
        paper_binance_client._paper_orders["test-order-1"] = {
            "order_id": "test-order-1",
            "pair": "BTC/USDC",
            "side": "buy",
            "amount": "0.01",
            "price": "59000",
            "status": "pending",
        }

        result = await paper_binance_client.cancel_order("test-order-1")
        assert result is True
        assert "test-order-1" not in paper_binance_client._paper_orders

    @pytest.mark.asyncio
    async def test_cancel_nonexistent_paper_order(
        self, paper_binance_client: BinanceRestClient
    ) -> None:
        """Cancelling a nonexistent paper order returns False."""
        result = await paper_binance_client.cancel_order("nonexistent")
        assert result is False


# =========================================================================
# Order status tests
# =========================================================================


class TestBinancePaperOrderStatus:
    """Tests for order status queries."""

    @pytest.mark.asyncio
    async def test_get_order_status_existing(self, paper_binance_client: BinanceRestClient) -> None:
        """Status of existing paper order."""
        paper_binance_client._paper_orders["test-order-1"] = {
            "order_id": "test-order-1",
            "pair": "BTC/USDC",
            "side": "buy",
            "amount": "0.01",
            "price": "59000",
            "status": "pending",
        }

        status = await paper_binance_client.get_order_status("test-order-1")
        assert status["order_id"] == "test-order-1"
        assert status["status"] == "pending"
        assert status["amount"] == Decimal("0.01")

    @pytest.mark.asyncio
    async def test_get_order_status_not_found(
        self, paper_binance_client: BinanceRestClient
    ) -> None:
        """Status of nonexistent order returns not_found."""
        status = await paper_binance_client.get_order_status("nonexistent")
        assert status["status"] == "not_found"


# =========================================================================
# Live mode tests (mocked ccxt)
# =========================================================================


class TestBinanceLiveMode:
    """Mock-based tests for live mode (no real API calls)."""

    @pytest.mark.asyncio
    async def test_get_ticker_live(self, live_binance_client: BinanceRestClient) -> None:
        """Live get_ticker calls ccxt and returns Decimal values."""
        live_binance_client._exchange.fetch_ticker = AsyncMock(
            return_value={
                "symbol": "BTC/USDC",
                "bid": 59900.0,
                "ask": 60100.0,
                "last": 60000.0,
                "baseVolume": 1234.5,
                "high": 61000.0,
                "low": 59000.0,
                "timestamp": 1700000000000,
            }
        )

        ticker = await live_binance_client.get_ticker("BTC/USDC")

        assert ticker["pair"] == "BTC/USDC"
        assert ticker["last"] == Decimal("60000.0")
        assert ticker["bid"] == Decimal("59900.0")
        assert ticker["ask"] == Decimal("60100.0")
        assert isinstance(ticker["last"], Decimal)

    @pytest.mark.asyncio
    async def test_get_balance_live(self, live_binance_client: BinanceRestClient) -> None:
        """Live get_balance calls ccxt fetch_balance."""
        live_binance_client._exchange.fetch_balance = AsyncMock(
            return_value={
                "free": {"BTC": 0.5, "USDC": 5000.0, "BNB": 1.2},
            }
        )

        balance = await live_binance_client.get_balance()

        assert balance["BTC"] == Decimal("0.5")
        assert balance["USDC"] == Decimal("5000.0")
        assert balance["BNB"] == Decimal("1.2")

    @pytest.mark.asyncio
    async def test_fetch_ohlcv_interval_mapping(
        self, live_binance_client: BinanceRestClient
    ) -> None:
        """fetch_ohlcv correctly maps interval minutes to ccxt timeframes."""
        live_binance_client._exchange.fetch_ohlcv = AsyncMock(
            return_value=[
                [1700000000000, 60000.0, 61000.0, 59000.0, 60500.0, 100.0],
            ]
        )

        candles = await live_binance_client.fetch_ohlcv("BTC/USDC", interval=240, limit=10)

        # Verify the ccxt call used "4h" timeframe
        call_kwargs = live_binance_client._exchange.fetch_ohlcv.call_args
        assert call_kwargs.kwargs["timeframe"] == "4h"

        assert len(candles) == 1
        assert candles[0]["close"] == Decimal("60500.0")
        assert candles[0]["pair"] == "BTC/USDC"
        assert candles[0]["interval"] == 240

    @pytest.mark.asyncio
    async def test_bnb_fee_asset_handling(self, live_binance_client: BinanceRestClient) -> None:
        """Live market order with BNB fee currency logs and tracks correctly."""
        live_binance_client._last_prices["BTC/USDC"] = Decimal("60000")

        live_binance_client._exchange.create_market_order = AsyncMock(
            return_value={
                "id": "binance-order-123",
                "filled": 0.01,
                "average": 60000.0,
                "fee": {"cost": 0.0001, "currency": "BNB"},
                "status": "closed",
            }
        )

        trade = await live_binance_client.place_market_order(
            "BTC/USDC", TradeSide.BUY, Decimal("0.01"), "test"
        )

        assert trade.fee_currency == "BNB"
        assert trade.fee == Decimal("0.0001")
        assert trade.status == TradeStatus.FILLED

    @pytest.mark.asyncio
    async def test_live_limit_order_gtc(self, live_binance_client: BinanceRestClient) -> None:
        """Live limit order passes timeInForce=GTC parameter."""
        live_binance_client._exchange.create_limit_order = AsyncMock(
            return_value={
                "id": "binance-limit-123",
                "status": "open",
                "filled": 0,
            }
        )

        await live_binance_client.place_limit_order(
            "BTC/USDC", TradeSide.BUY, Decimal("0.01"), Decimal("59000"), "test"
        )

        call_kwargs = live_binance_client._exchange.create_limit_order.call_args
        assert call_kwargs.kwargs["params"] == {"timeInForce": "GTC"}


# =========================================================================
# Margin not supported
# =========================================================================


class TestBinanceMarginNotSupported:
    """Margin trading is not supported in P2."""

    @pytest.mark.asyncio
    async def test_margin_order_raises(self, paper_binance_client: BinanceRestClient) -> None:
        """place_margin_order raises NotImplementedError."""
        with pytest.raises(NotImplementedError, match="not supported in P2"):
            await paper_binance_client.place_margin_order(
                "BTC/USDC", TradeSide.BUY, Decimal("0.01")
            )

    @pytest.mark.asyncio
    async def test_margin_balance_empty(self, paper_binance_client: BinanceRestClient) -> None:
        """get_margin_balance returns zeros."""
        balance = await paper_binance_client.get_margin_balance()
        assert balance["total_margin"] == Decimal("0")

    @pytest.mark.asyncio
    async def test_margin_positions_empty(self, paper_binance_client: BinanceRestClient) -> None:
        """get_open_margin_positions returns empty list."""
        positions = await paper_binance_client.get_open_margin_positions()
        assert positions == []


# =========================================================================
# ExchangeFees presets
# =========================================================================


class TestExchangeFeesPresets:
    """Tests for ExchangeFees class methods."""

    def test_kraken_defaults(self) -> None:
        """Kraken defaults should match historical values."""
        fees = ExchangeFees.kraken_defaults()
        assert fees.maker == Decimal("0.0016")
        assert fees.taker == Decimal("0.0026")

    def test_binance_defaults_with_bnb(self) -> None:
        """Binance with BNB discount should be 0.075%."""
        fees = ExchangeFees.binance_defaults(use_bnb=True)
        assert fees.maker == Decimal("0.00075")
        assert fees.taker == Decimal("0.00075")

    def test_binance_defaults_without_bnb(self) -> None:
        """Binance without BNB discount should be 0.10%."""
        fees = ExchangeFees.binance_defaults(use_bnb=False)
        assert fees.maker == Decimal("0.0010")
        assert fees.taker == Decimal("0.0010")


# =========================================================================
# Factory integration
# =========================================================================


class TestBinanceFactory:
    """Tests for build_exchange_rest_client with Binance."""

    def test_factory_returns_binance_client(self, mock_binance_paper_settings: Settings) -> None:
        """Factory returns BinanceRestClient when exchange_name='binance'."""
        from krakenbot.connectors.exchange import build_exchange_rest_client

        event_bus = MagicMock()
        db_manager = MagicMock()

        with patch("krakenbot.connectors.binance.rest.BinanceRestClient") as mock_cls:
            mock_cls.return_value = MagicMock(exchange_name="binance")
            client = build_exchange_rest_client(mock_binance_paper_settings, event_bus, db_manager)

        assert client.exchange_name == "binance"

    def test_factory_returns_kraken_by_default(self, mock_settings: Settings) -> None:
        """Factory returns KrakenRestClient by default (exchange_name='kraken')."""
        from krakenbot.connectors.exchange import build_exchange_rest_client

        event_bus = MagicMock()
        db_manager = MagicMock()

        with patch("krakenbot.connectors.kraken.rest.KrakenRestClient") as mock_cls:
            mock_cls.return_value = MagicMock(exchange_name="kraken")
            client = build_exchange_rest_client(mock_settings, event_bus, db_manager)

        assert client.exchange_name == "kraken"
