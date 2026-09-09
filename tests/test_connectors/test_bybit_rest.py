"""Tests for the Bybit EU REST client.

Covers: init/options, fees source, paper mode (market/limit/cancel/status),
lot/tick rounding, MIN_NOTIONAL, live-mode request shapes (market BUY without
price, quote-cost buy, PostOnly, orderLinkId), PostOnly rejection normalisation,
retCode → exception mapping, lazy load_markets, factory dispatch.

IMPORTANT: ccxt is mocked — no real API request is ever made.
"""

from __future__ import annotations

from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import ccxt.async_support as ccxt
import pytest

from krakenbot.config.settings import (
    BybitSettings,
    DatabaseSettings,
    ExchangeFees,
    Settings,
    TradingMode,
    TradingSettings,
)
from krakenbot.connectors.bybit.rest import (
    MAX_CLIENT_ORDER_ID_LEN,
    MIN_NOTIONAL,
    POST_ONLY_REJECT_REASON,
    BybitRestClient,
)
from krakenbot.connectors.exchange import build_exchange_rest_client, build_exchange_ws_client
from krakenbot.core.event_bus import EventBus, reset_event_bus
from krakenbot.core.exceptions import (
    InsufficientBalanceError,
    KrakenAPIError,
    OrderCancelError,
    OrderExecutionError,
    RateLimitError,
)
from krakenbot.models.base import OrderStatus, TradeSide, TradeStatus

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _settings(mode: TradingMode, **overrides: object) -> Settings:
    if mode == TradingMode.LIVE:
        trading = TradingSettings.model_construct(
            mode=TradingMode.LIVE,
            pair="BTC/USDC",
            confirm_live="yes",
            default_order_amount_eur=100.0,
            candle_interval_min=15,
        )
    else:
        trading = TradingSettings(mode=TradingMode.PAPER, pair="BTC/USDC")
    return Settings(
        app_name="KrakenBot-Test",
        environment="testing",
        exchange_name="bybit",
        bybit=BybitSettings(
            api_key="test_bybit_key",
            api_secret="test_bybit_secret",
            trade_api_key="test_bybit_trade_key",
            trade_api_secret="test_bybit_trade_secret",
        ),
        database=DatabaseSettings(
            url="postgresql+asyncpg://test:test@localhost:5432/krakenbot_test",
        ),
        trading=trading,
        _env_file=None,
        **overrides,
    )


@pytest.fixture
def bybit_paper_settings() -> Settings:
    return _settings(TradingMode.PAPER)


@pytest.fixture
def bybit_live_settings() -> Settings:
    return _settings(TradingMode.LIVE)


@pytest.fixture
def bybit_event_bus() -> EventBus:
    reset_event_bus()
    return EventBus()


@pytest.fixture
def bybit_mock_db_manager() -> MagicMock:
    manager = MagicMock()
    session_mock = MagicMock()
    session_mock.add = MagicMock()
    session_cm = MagicMock()
    session_cm.__aenter__ = AsyncMock(return_value=session_mock)
    session_cm.__aexit__ = AsyncMock(return_value=None)
    manager.session.return_value = session_cm
    return manager


def _make_client(settings: Settings, event_bus: EventBus, db: MagicMock) -> BybitRestClient:
    with patch("ccxt.async_support.bybit"):
        client = BybitRestClient(settings, event_bus, db)
    # ccxt is a MagicMock: make the async surface awaitable and markets a real dict
    client._exchange.load_markets = AsyncMock(return_value={})
    client._exchange.markets = {}
    client._exchange.close = AsyncMock()
    return client


@pytest.fixture
def paper_client(
    bybit_paper_settings: Settings, bybit_event_bus: EventBus, bybit_mock_db_manager: MagicMock
) -> BybitRestClient:
    return _make_client(bybit_paper_settings, bybit_event_bus, bybit_mock_db_manager)


@pytest.fixture
def live_client(
    bybit_live_settings: Settings, bybit_event_bus: EventBus, bybit_mock_db_manager: MagicMock
) -> BybitRestClient:
    return _make_client(bybit_live_settings, bybit_event_bus, bybit_mock_db_manager)


def _ccxt_error(cls: type[Exception], ret_code: int, msg: str = "error") -> Exception:
    """Build a ccxt exception with a Bybit-shaped message (retCode embedded)."""
    return cls(f'bybit {{"retCode":{ret_code},"retMsg":"{msg}","result":{{}}}}')


# ---------------------------------------------------------------------------
# Init
# ---------------------------------------------------------------------------


class TestInit:
    def test_ccxt_options(self, bybit_paper_settings: Settings, bybit_event_bus: EventBus) -> None:
        with patch("ccxt.async_support.bybit") as mock_cls:
            client = BybitRestClient(bybit_paper_settings, bybit_event_bus, None)
        config = mock_cls.call_args.args[0]
        assert config["hostname"] == "bybit.eu"
        assert config["apiKey"] == "test_bybit_key"  # paper -> read-only key
        assert client.key_role == "readonly"
        assert config["enableRateLimit"] is True
        assert config["options"]["defaultType"] == "spot"
        assert config["options"]["adjustForTimeDifference"] is True
        assert config["options"]["enableUnifiedAccount"] is True
        assert config["options"]["recvWindow"] == 5000

    def test_properties(self, paper_client: BybitRestClient) -> None:
        assert paper_client.exchange_name == "bybit"
        assert paper_client.is_paper_mode is True
        assert paper_client.markets_loaded is False
        assert paper_client.stats == {
            "orders_placed": 0,
            "orders_filled": 0,
            "orders_failed": 0,
            "api_calls": 0,
        }
        assert set(paper_client.paper_balance) == {"BTC", "USDC"}

    def test_live_flag(self, live_client: BybitRestClient) -> None:
        assert live_client.is_paper_mode is False

    def test_live_uses_trade_key(
        self, bybit_live_settings: Settings, bybit_event_bus: EventBus
    ) -> None:
        with patch("ccxt.async_support.bybit") as mock_cls:
            client = BybitRestClient(bybit_live_settings, bybit_event_bus, None)
        config = mock_cls.call_args.args[0]
        assert config["apiKey"] == "test_bybit_trade_key"
        assert config["secret"] == "test_bybit_trade_secret"
        assert client.key_role == "trade"

    def test_live_readonly_override(
        self, bybit_live_settings: Settings, bybit_event_bus: EventBus
    ) -> None:
        with patch("ccxt.async_support.bybit") as mock_cls:
            client = BybitRestClient(
                bybit_live_settings, bybit_event_bus, None, key_role="readonly"
            )
        assert mock_cls.call_args.args[0]["apiKey"] == "test_bybit_key"
        assert client.key_role == "readonly"

    def test_live_without_trade_key_raises(self, bybit_event_bus: EventBus) -> None:
        settings = _settings(TradingMode.LIVE)
        settings.bybit = BybitSettings(api_key="ro", api_secret="ro", _env_file=None)
        with (
            patch("ccxt.async_support.bybit"),
            pytest.raises(ValueError, match="BYBIT_TRADE_API_KEY"),
        ):
            BybitRestClient(settings, bybit_event_bus, None)

    def test_paper_without_any_key_is_allowed(self, bybit_event_bus: EventBus) -> None:
        settings = _settings(TradingMode.PAPER)
        settings.bybit = BybitSettings(_env_file=None)
        with patch("ccxt.async_support.bybit"):
            client = BybitRestClient(settings, bybit_event_bus, None)
        assert client.key_role == "readonly"

    def test_fees_default_to_bybit_when_not_set(self, paper_client: BybitRestClient) -> None:
        assert paper_client.fees.maker == Decimal("0.0010")
        assert paper_client.fees.taker == Decimal("0.0025")

    def test_fees_explicit_settings_win(
        self, bybit_event_bus: EventBus, bybit_mock_db_manager: MagicMock
    ) -> None:
        settings = _settings(
            TradingMode.PAPER,
            exchange_fees=ExchangeFees(maker=Decimal("0.0005"), taker=Decimal("0.0009")),
        )
        client = _make_client(settings, bybit_event_bus, bybit_mock_db_manager)
        assert client.fees.maker == Decimal("0.0005")
        assert client.fees.taker == Decimal("0.0009")

    def test_non_unified_account_disables_uta_option(self, bybit_event_bus: EventBus) -> None:
        settings = _settings(TradingMode.PAPER)
        settings.bybit = BybitSettings(
            api_key="k", api_secret="s", account_type="CLASSIC", _env_file=None
        )
        with patch("ccxt.async_support.bybit") as mock_cls:
            BybitRestClient(settings, bybit_event_bus, None)
        assert mock_cls.call_args.args[0]["options"]["enableUnifiedAccount"] is False

    async def test_close(self, paper_client: BybitRestClient) -> None:
        await paper_client.close()
        paper_client._exchange.close.assert_awaited_once()


# ---------------------------------------------------------------------------
# Rounding / validation
# ---------------------------------------------------------------------------


class TestRounding:
    def test_round_amount_static_table(self, paper_client: BybitRestClient) -> None:
        assert paper_client._round_amount("BTC/USDC", Decimal("0.00012345")) == Decimal("0.000123")
        assert paper_client._round_amount("ETH/USDC", Decimal("0.12349")) == Decimal("0.1234")
        assert paper_client._round_amount("SOL/USDC", Decimal("1.2349")) == Decimal("1.234")

    def test_round_price_directional(self, paper_client: BybitRestClient) -> None:
        assert paper_client._round_price("BTC/USDC", Decimal("60000.07"), TradeSide.BUY) == Decimal(
            "60000.0"
        )
        assert paper_client._round_price(
            "BTC/USDC", Decimal("60000.07"), TradeSide.SELL
        ) == Decimal("60000.1")
        assert paper_client._round_price("SOL/USDC", Decimal("150.123"), TradeSide.BUY) == Decimal(
            "150.12"
        )

    def test_rounding_uses_loaded_markets(self, paper_client: BybitRestClient) -> None:
        paper_client._markets_loaded = True
        paper_client._exchange.markets = {
            "BTC/USDC": {"precision": {"amount": 0.0001, "price": 0.5}},
        }
        assert paper_client._round_amount("BTC/USDC", Decimal("0.00019")) == Decimal("0.0001")
        assert paper_client._round_price("BTC/USDC", Decimal("60000.7"), TradeSide.BUY) == Decimal(
            "60000.5"
        )

    def test_amount_below_step_rejected(self, paper_client: BybitRestClient) -> None:
        with pytest.raises(OrderExecutionError, match="below minimum"):
            paper_client._prepare_amount("BTC/USDC", TradeSide.BUY, Decimal("0.0000005"))

    def test_client_order_id_length(self) -> None:
        cid = BybitRestClient._new_client_order_id()
        assert cid.startswith("kb-")
        assert len(cid) <= MAX_CLIENT_ORDER_ID_LEN


class TestMinNotional:
    async def test_market_below_min_notional(self, paper_client: BybitRestClient) -> None:
        paper_client.update_last_price("BTC/USDC", Decimal("50000"))
        with pytest.raises(OrderExecutionError, match="below Bybit minimum"):
            await paper_client.place_market_order("BTC/USDC", TradeSide.BUY, Decimal("0.00009"))

    async def test_limit_below_min_notional(self, paper_client: BybitRestClient) -> None:
        with pytest.raises(OrderExecutionError, match="below Bybit minimum"):
            await paper_client.place_limit_order(
                "BTC/USDC", TradeSide.BUY, Decimal("0.00009"), Decimal("50000")
            )

    async def test_exactly_min_notional_passes(self, paper_client: BybitRestClient) -> None:
        paper_client._paper_balance["USDC"] = Decimal("1000")
        paper_client.update_last_price("BTC/USDC", Decimal("50000"))
        trade = await paper_client.place_market_order(
            "BTC/USDC", TradeSide.BUY, Decimal("0.0001")
        )  # 5 USDC
        assert trade.amount * trade.price == MIN_NOTIONAL

    async def test_quote_amount_below_min_notional(self, live_client: BybitRestClient) -> None:
        with pytest.raises(OrderExecutionError, match="below Bybit minimum"):
            await live_client.place_market_order(
                "BTC/USDC", TradeSide.BUY, Decimal("0"), quote_amount=Decimal("4.99")
            )

    async def test_quote_amount_sell_rejected(self, live_client: BybitRestClient) -> None:
        with pytest.raises(OrderExecutionError, match="only supported for market BUY"):
            await live_client.place_market_order(
                "BTC/USDC", TradeSide.SELL, Decimal("0.001"), quote_amount=Decimal("10")
            )


# ---------------------------------------------------------------------------
# Paper mode
# ---------------------------------------------------------------------------


class TestPaperMarketOrders:
    async def test_buy_debits_quote_with_taker_fee(self, paper_client: BybitRestClient) -> None:
        paper_client._paper_balance = {"USDC": Decimal("1000"), "BTC": Decimal("0")}
        paper_client.update_last_price("BTC/USDC", Decimal("50000"))

        trade = await paper_client.place_market_order(
            "BTC/USDC", TradeSide.BUY, Decimal("0.001"), strategy="t"
        )

        # value 50, fee 0.25 % = 0.125
        assert trade.status == TradeStatus.FILLED
        assert trade.fee == Decimal("0.125")
        assert paper_client.paper_balance["USDC"] == Decimal("949.875")
        assert paper_client.paper_balance["BTC"] == Decimal("0.001")
        assert paper_client.stats["orders_filled"] == 1

    async def test_sell_credits_quote_minus_fee(self, paper_client: BybitRestClient) -> None:
        paper_client._paper_balance = {"USDC": Decimal("0"), "BTC": Decimal("0.01")}
        paper_client.update_last_price("BTC/USDC", Decimal("50000"))

        trade = await paper_client.place_market_order("BTC/USDC", TradeSide.SELL, Decimal("0.001"))

        assert trade.fee == Decimal("0.125")
        assert paper_client.paper_balance["BTC"] == Decimal("0.009")
        assert paper_client.paper_balance["USDC"] == Decimal("49.875")

    async def test_amount_is_rounded_down_to_step(self, paper_client: BybitRestClient) -> None:
        paper_client._paper_balance = {"USDC": Decimal("1000"), "BTC": Decimal("0")}
        paper_client.update_last_price("BTC/USDC", Decimal("50000"))
        trade = await paper_client.place_market_order(
            "BTC/USDC", TradeSide.BUY, Decimal("0.0012345678")
        )
        assert trade.amount == Decimal("0.001234")

    async def test_insufficient_balance(self, paper_client: BybitRestClient) -> None:
        paper_client._paper_balance = {"USDC": Decimal("10"), "BTC": Decimal("0")}
        paper_client.update_last_price("BTC/USDC", Decimal("50000"))
        with pytest.raises(InsufficientBalanceError):
            await paper_client.place_market_order("BTC/USDC", TradeSide.BUY, Decimal("0.001"))

    async def test_uses_ticker_when_no_last_price(self, paper_client: BybitRestClient) -> None:
        paper_client._paper_balance = {"USDC": Decimal("1000"), "BTC": Decimal("0")}
        paper_client._exchange.fetch_ticker = AsyncMock(return_value={"last": 40000.0})
        trade = await paper_client.place_market_order("BTC/USDC", TradeSide.BUY, Decimal("0.001"))
        assert trade.price == Decimal("40000.0")
        assert paper_client.markets_loaded is True  # get_ticker loaded markets lazily


class TestPaperLimitOrders:
    async def test_buy_fills_immediately_with_maker_fee(
        self, paper_client: BybitRestClient
    ) -> None:
        paper_client._paper_balance = {"USDC": Decimal("1000"), "BTC": Decimal("0")}
        paper_client.update_last_price("BTC/USDC", Decimal("50000"))
        order = await paper_client.place_limit_order(
            "BTC/USDC", TradeSide.BUY, Decimal("0.001"), Decimal("50100")
        )
        # value 50.1, maker 0.10 % = 0.0501
        assert order.status == OrderStatus.FILLED
        assert order.fee == Decimal("0.0501")
        assert paper_client.paper_balance["USDC"] == Decimal("1000") - Decimal("50.1501")

    async def test_pending_when_price_not_reached(self, paper_client: BybitRestClient) -> None:
        paper_client.update_last_price("BTC/USDC", Decimal("50000"))
        order = await paper_client.place_limit_order(
            "BTC/USDC", TradeSide.BUY, Decimal("0.001"), Decimal("49000.07")
        )
        assert order.status == OrderStatus.PENDING
        assert order.price == Decimal("49000.0")  # rounded to tick
        assert order.order_id in paper_client._paper_orders
        assert (await paper_client.get_open_orders("BTC/USDC"))[0]["order_id"] == order.order_id

    async def test_cancel_and_status(self, paper_client: BybitRestClient) -> None:
        paper_client.update_last_price("BTC/USDC", Decimal("50000"))
        order = await paper_client.place_limit_order(
            "BTC/USDC", TradeSide.SELL, Decimal("0.001"), Decimal("55000")
        )
        status = await paper_client.get_order_status(order.order_id)
        assert status["status"] == "pending"
        assert await paper_client.cancel_order(order.order_id) is True
        assert await paper_client.cancel_order(order.order_id) is False
        assert (await paper_client.get_order_status(order.order_id))["status"] == "not_found"

    async def test_paper_balance_helpers(self, paper_client: BybitRestClient) -> None:
        await paper_client.set_paper_balance("USDC", Decimal("42"))
        assert paper_client.get_paper_balance()["USDC"] == Decimal("42")
        balance = await paper_client.get_balance()
        assert balance["USDC"] == Decimal("42")
        assert await paper_client.get_trade_history() == []
        paper_client.remove_paper_order("missing")  # no error


# ---------------------------------------------------------------------------
# Live mode (ccxt mocked)
# ---------------------------------------------------------------------------


class TestLiveMarketOrders:
    async def test_market_buy_never_passes_price(self, live_client: BybitRestClient) -> None:
        live_client._exchange.create_order = AsyncMock(
            return_value={
                "id": "123",
                "filled": 0.001,
                "average": 50000.0,
                "fee": {"cost": 0.0000025, "currency": "BTC"},
            }
        )
        trade = await live_client.place_market_order(
            "BTC/USDC", TradeSide.BUY, Decimal("0.001"), strategy="t", signal_price=Decimal("50000")
        )
        args = live_client._exchange.create_order.call_args.args
        assert args[:3] == ("BTC/USDC", "market", "buy")
        assert args[3] == 0.001
        assert args[4] is None  # price
        params = args[5]
        assert "cost" not in params
        assert params["clientOrderId"].startswith("kb-")
        assert len(params["clientOrderId"]) <= MAX_CLIENT_ORDER_ID_LEN
        assert trade.order_id == "123"
        assert trade.fee_currency == "BTC"
        assert trade.price == Decimal("50000.0")
        live_client._exchange.load_markets.assert_awaited_once()

    async def test_market_buy_with_quote_amount_uses_cost(
        self, live_client: BybitRestClient
    ) -> None:
        live_client._exchange.create_order = AsyncMock(
            return_value={"id": "124", "filled": 0.0002, "average": 50000.0}
        )
        live_client.update_last_price("BTC/USDC", Decimal("50000"))
        trade = await live_client.place_market_order(
            "BTC/USDC", TradeSide.BUY, Decimal("0"), quote_amount=Decimal("10")
        )
        args = live_client._exchange.create_order.call_args.args
        assert args[3] is None  # amount
        assert args[4] is None  # price
        assert args[5]["cost"] == "10"
        assert trade.amount == Decimal("0.0002")

    async def test_fee_currency_defaults_to_received_currency(
        self, live_client: BybitRestClient
    ) -> None:
        live_client._exchange.create_order = AsyncMock(return_value={"id": "1", "filled": 0.001})
        trade = await live_client.place_market_order(
            "BTC/USDC", TradeSide.SELL, Decimal("0.001"), signal_price=Decimal("50000")
        )
        assert trade.fee_currency == "USDC"
        assert trade.price == Decimal("50000")

    async def test_insufficient_funds_maps_and_publishes(
        self, live_client: BybitRestClient
    ) -> None:
        live_client._exchange.create_order = AsyncMock(
            side_effect=_ccxt_error(ccxt.InsufficientFunds, 170131, "Insufficient balance")
        )
        with pytest.raises(InsufficientBalanceError):
            await live_client.place_market_order(
                "BTC/USDC", TradeSide.BUY, Decimal("0.001"), signal_price=Decimal("50000")
            )
        assert live_client.stats["orders_failed"] == 1


class TestLiveLimitOrders:
    async def test_post_only_default_and_orderlinkid(self, live_client: BybitRestClient) -> None:
        live_client._exchange.create_order = AsyncMock(return_value={"id": "555", "status": "open"})
        order = await live_client.place_limit_order(
            "BTC/USDC", TradeSide.BUY, Decimal("0.001"), Decimal("45000.07")
        )
        args = live_client._exchange.create_order.call_args.args
        assert args[:3] == ("BTC/USDC", "limit", "buy")
        assert args[3] == 0.001
        assert args[4] == 45000.0  # tick rounded
        assert args[5]["timeInForce"] == "PostOnly"
        assert args[5]["clientOrderId"].startswith("kb-")
        assert order.status == OrderStatus.PENDING
        assert order.order_id == "555"
        assert order.signal_metadata["post_only"] is True

    async def test_gtc_when_post_only_disabled(self, live_client: BybitRestClient) -> None:
        live_client._exchange.create_order = AsyncMock(return_value={"id": "556", "status": "open"})
        await live_client.place_limit_order(
            "BTC/USDC", TradeSide.SELL, Decimal("0.001"), Decimal("60000"), post_only=False
        )
        assert live_client._exchange.create_order.call_args.args[5]["timeInForce"] == "GTC"

    async def test_status_fetched_when_create_has_no_status(
        self, live_client: BybitRestClient
    ) -> None:
        live_client._exchange.create_order = AsyncMock(return_value={"id": "557"})
        live_client._exchange.fetch_order = AsyncMock(
            return_value={"id": "557", "status": "closed", "filled": 0.001, "average": 45000.0}
        )
        order = await live_client.place_limit_order(
            "BTC/USDC", TradeSide.BUY, Decimal("0.001"), Decimal("45000")
        )
        live_client._exchange.fetch_order.assert_awaited_once_with(
            "557", "BTC/USDC", params={"acknowledged": True}
        )
        assert order.status == OrderStatus.FILLED
        assert order.filled_price == Decimal("45000.0")

    async def test_post_only_rejection_via_exception(self, live_client: BybitRestClient) -> None:
        live_client._exchange.create_order = AsyncMock(
            side_effect=ccxt.OrderImmediatelyFillable("bybit PostOnly would take liquidity")
        )
        order = await live_client.place_limit_order(
            "BTC/USDC", TradeSide.BUY, Decimal("0.001"), Decimal("70000")
        )
        assert order.status == OrderStatus.CANCELLED
        assert order.filled_amount == Decimal("0")
        assert order.signal_metadata["reject_reason"] == POST_ONLY_REJECT_REASON
        assert live_client.stats["orders_failed"] == 0

    async def test_post_only_rejection_via_status(self, live_client: BybitRestClient) -> None:
        live_client._exchange.create_order = AsyncMock(return_value={"id": "558"})
        live_client._exchange.fetch_order = AsyncMock(
            return_value={
                "id": "558",
                "status": "rejected",
                "filled": 0,
                "info": {"rejectReason": "EC_PostOnlyWillTakeLiquidity"},
            }
        )
        order = await live_client.place_limit_order(
            "BTC/USDC", TradeSide.BUY, Decimal("0.001"), Decimal("70000")
        )
        assert order.status == OrderStatus.CANCELLED
        assert order.signal_metadata["reject_reason"] == POST_ONLY_REJECT_REASON
        assert order.signal_metadata["exchange_order_id"] == "558"
        assert order.signal_metadata["raw_reason"] == "EC_PostOnlyWillTakeLiquidity"

    async def test_price_limit_ratio_rejection_raises(self, live_client: BybitRestClient) -> None:
        live_client._exchange.create_order = AsyncMock(
            side_effect=_ccxt_error(
                ccxt.InvalidOrder, 170193, "Buy order price cannot be higher than 50250"
            )
        )
        with pytest.raises(OrderExecutionError, match="priceLimitRatio") as exc_info:
            await live_client.place_limit_order(
                "BTC/USDC", TradeSide.BUY, Decimal("0.001"), Decimal("40000")
            )
        assert exc_info.value.details["reason"] == "price_limit_ratio"
        assert exc_info.value.details["ret_code"] == 170193


class TestLiveReadMethods:
    async def test_get_balance(self, live_client: BybitRestClient) -> None:
        live_client._exchange.fetch_balance = AsyncMock(
            return_value={"free": {"USDC": 123.45, "BTC": 0.0, "ETH": None}}
        )
        assert await live_client.get_balance() == {"USDC": Decimal("123.45")}

    async def test_get_ticker(self, live_client: BybitRestClient) -> None:
        live_client._exchange.fetch_ticker = AsyncMock(
            return_value={"bid": 49999.9, "ask": 50000.1, "last": 50000.0, "baseVolume": 12.5}
        )
        ticker = await live_client.get_ticker("BTC/USDC")
        assert ticker["last"] == Decimal("50000.0")
        assert ticker["high"] is None
        assert live_client._last_prices["BTC/USDC"] == Decimal("50000.0")

    async def test_fetch_ohlcv(self, live_client: BybitRestClient) -> None:
        live_client._exchange.fetch_ohlcv = AsyncMock(
            return_value=[[1700000000000, 1.0, 2.0, 0.5, 1.5, 10.0, 15.0]]
        )
        candles = await live_client.fetch_ohlcv("BTC/USDC", 240, limit=5000)
        kwargs = live_client._exchange.fetch_ohlcv.call_args.kwargs
        assert kwargs["timeframe"] == "4h"
        assert kwargs["limit"] == 1000
        assert candles[0]["close"] == Decimal("1.5")
        assert candles[0]["timestamp"].tzinfo is not None

    async def test_get_open_orders_and_history(self, live_client: BybitRestClient) -> None:
        live_client._exchange.fetch_open_orders = AsyncMock(
            return_value=[
                {"id": "1", "symbol": "BTC/USDC", "side": "buy", "amount": 0.001, "price": 45000}
            ]
        )
        live_client._exchange.fetch_my_trades = AsyncMock(
            return_value=[
                {
                    "id": "t1",
                    "order": "1",
                    "symbol": "BTC/USDC",
                    "side": "buy",
                    "amount": 0.001,
                    "price": 45000,
                    "fee": {"cost": 0.000001, "currency": "BTC"},
                }
            ]
        )
        orders = await live_client.get_open_orders("BTC/USDC")
        assert orders[0]["price"] == Decimal("45000")
        trades = await live_client.get_trade_history("BTC/USDC")
        assert trades[0]["fee_currency"] == "BTC"

    async def test_get_order_status_acknowledges_lookback(
        self, live_client: BybitRestClient
    ) -> None:
        # Observed 2026-09-09: ccxt bybit fetchOrder() raises unless acknowledged=True
        live_client._exchange.fetch_order = AsyncMock(
            return_value={"id": "9", "status": "open", "filled": 0, "amount": 0.001, "price": 1}
        )
        status = await live_client.get_order_status("9", "BTC/USDC")
        assert status["status"] == "open"
        live_client._exchange.fetch_order.assert_awaited_once_with(
            "9", "BTC/USDC", params={"acknowledged": True}
        )

    async def test_get_order_status_not_found(self, live_client: BybitRestClient) -> None:
        live_client._exchange.fetch_order = AsyncMock(
            side_effect=_ccxt_error(ccxt.ExchangeError, 170213, "Order does not exist")
        )
        status = await live_client.get_order_status("x", "BTC/USDC")
        assert status["status"] == "not_found"

    async def test_cancel_order_paths(self, live_client: BybitRestClient) -> None:
        live_client._exchange.cancel_order = AsyncMock(return_value={})
        assert await live_client.cancel_order("1", "BTC/USDC") is True

        live_client._exchange.cancel_order = AsyncMock(side_effect=ccxt.OrderNotFound("gone"))
        assert await live_client.cancel_order("1", "BTC/USDC") is False

        live_client._exchange.cancel_order = AsyncMock(
            side_effect=_ccxt_error(ccxt.ExchangeError, 170999, "boom")
        )
        with pytest.raises(OrderCancelError):
            await live_client.cancel_order("1", "BTC/USDC")


class TestLoadMarkets:
    async def test_loaded_once(self, live_client: BybitRestClient) -> None:
        await live_client.load_markets()
        await live_client.load_markets()
        await live_client._ensure_markets()
        live_client._exchange.load_markets.assert_awaited_once()
        assert live_client.markets_loaded is True

    async def test_reload(self, live_client: BybitRestClient) -> None:
        await live_client.load_markets()
        await live_client.load_markets(reload=True)
        assert live_client._exchange.load_markets.await_count == 2

    async def test_failure_raises_api_error(self, live_client: BybitRestClient) -> None:
        live_client._exchange.load_markets = AsyncMock(
            side_effect=ccxt.ExchangeNotAvailable("down")
        )
        with pytest.raises(KrakenAPIError, match="bybit.eu"):
            await live_client.load_markets()
        assert live_client.markets_loaded is False


# ---------------------------------------------------------------------------
# retCode mapping
# ---------------------------------------------------------------------------


class TestRetCodeMapping:
    @pytest.mark.parametrize(
        ("exc_cls", "ret_code", "expected"),
        [
            (ccxt.InsufficientFunds, 170131, InsufficientBalanceError),
            (ccxt.ExchangeError, 170131, InsufficientBalanceError),  # raw retCode path
            (ccxt.RateLimitExceeded, 10006, RateLimitError),
            (ccxt.ExchangeError, 10006, RateLimitError),
            (ccxt.DDoSProtection, 0, RateLimitError),
            (ccxt.InvalidNonce, 10002, KrakenAPIError),
            (ccxt.ExchangeError, 10002, KrakenAPIError),
            (ccxt.BadRequest, 10001, OrderExecutionError),
            (ccxt.InvalidOrder, 170193, OrderExecutionError),
            (ccxt.InvalidOrder, 170194, OrderExecutionError),
            (ccxt.AuthenticationError, 10003, KrakenAPIError),
            (ccxt.AuthenticationError, 10005, KrakenAPIError),
            (ccxt.ExchangeError, 10005, KrakenAPIError),
            (ccxt.ExchangeError, 170999, OrderExecutionError),
        ],
    )
    def test_mapping(
        self,
        live_client: BybitRestClient,
        exc_cls: type[Exception],
        ret_code: int,
        expected: type[Exception],
    ) -> None:
        error = live_client._translate_error(_ccxt_error(exc_cls, ret_code), pair="BTC/USDC")
        assert isinstance(error, expected)
        if ret_code:
            assert error.details["ret_code"] == ret_code

    def test_clock_drift_message_is_actionable(self, live_client: BybitRestClient) -> None:
        error = live_client._translate_error(_ccxt_error(ccxt.InvalidNonce, 10002, "timestamp"))
        assert "NTP" in error.message
        assert "recv_window=5000" in error.message

    def test_permission_denied_message_is_actionable(self, live_client: BybitRestClient) -> None:
        # Observed 2026-09-08 with a readOnly=1 key on api.bybit.eu (order/create)
        error = live_client._translate_error(
            _ccxt_error(
                ccxt.AuthenticationError, 10005, "Invalid API-key, IP, or permissions for action."
            ),
            pair="BTC/USDC",
        )
        assert isinstance(error, KrakenAPIError)
        assert error.details["reason"] == "permission_denied"
        assert "read-only" in error.message
        assert "Spot Trade" in error.message

    def test_http_403_is_rate_limit(self, live_client: BybitRestClient) -> None:
        error = live_client._translate_error(ccxt.ExchangeError("bybit 403 Forbidden"))
        assert isinstance(error, RateLimitError)

    def test_context_selects_fallback(self, live_client: BybitRestClient) -> None:
        exc = ccxt.ExchangeError("bybit unknown")
        assert isinstance(live_client._translate_error(exc, context="cancel"), OrderCancelError)
        assert isinstance(live_client._translate_error(exc, context="balance"), KrakenAPIError)
        assert isinstance(live_client._translate_error(exc, context="order"), OrderExecutionError)

    def test_extract_ret_code(self) -> None:
        assert BybitRestClient._extract_ret_code(Exception('{"retCode":170131,"x":1}')) == 170131
        assert BybitRestClient._extract_ret_code(Exception('{"retCode": "10002"}')) == 10002
        assert BybitRestClient._extract_ret_code(Exception("no code")) is None


# ---------------------------------------------------------------------------
# Margin (spot only) + factory
# ---------------------------------------------------------------------------


class TestMarginAndFactory:
    async def test_margin_not_supported(self, paper_client: BybitRestClient) -> None:
        with pytest.raises(NotImplementedError):
            await paper_client.place_margin_order("BTC/USDC", TradeSide.BUY, Decimal("0.001"))
        assert (await paper_client.get_margin_balance())["total_margin"] == Decimal("0")
        assert await paper_client.get_open_margin_positions() == []

    def test_factory_builds_bybit_client(
        self, bybit_paper_settings: Settings, bybit_event_bus: EventBus
    ) -> None:
        with patch("ccxt.async_support.bybit"):
            client = build_exchange_rest_client(bybit_paper_settings, bybit_event_bus, None)
        assert isinstance(client, BybitRestClient)
        assert client.exchange_name == "bybit"

    def test_ws_factory_builds_bybit_ws_client(
        self, bybit_paper_settings: Settings, bybit_event_bus: EventBus
    ) -> None:
        from krakenbot.connectors.bybit.ws import BybitWebSocketClient

        client = build_exchange_ws_client(bybit_paper_settings, bybit_event_bus)
        assert isinstance(client, BybitWebSocketClient)
