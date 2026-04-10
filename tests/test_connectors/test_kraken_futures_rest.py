"""Tests for KrakenFuturesClient (perpetual futures)."""

from __future__ import annotations

from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from krakenbot.config.settings import (
    DatabaseSettings,
    KrakenFuturesSettings,
    KrakenSettings,
    LogLevel,
    Settings,
    TradingMode,
    TradingSettings,
)
from krakenbot.connectors.base_perps import BaseExchangePerps
from krakenbot.connectors.kraken_futures_rest import KrakenFuturesClient


def _make_settings(
    *,
    max_leverage: int = 3,
    demo: bool = True,
) -> Settings:
    """Build test Settings with Kraken Futures enabled."""
    return Settings(
        app_name="KrakenBot-Test",
        environment="testing",
        log_level=LogLevel.DEBUG,
        log_json=False,
        kraken=KrakenSettings(api_key="spot_key", api_secret="spot_secret"),
        database=DatabaseSettings(
            url="postgresql+asyncpg://test:test@localhost:5432/test",
        ),
        trading=TradingSettings(mode=TradingMode.PAPER, pair="XBT/USDC"),
        kraken_futures=KrakenFuturesSettings(
            enabled=True,
            api_key="futures_test_key",
            api_secret="futures_test_secret",
            demo=demo,
            max_leverage=max_leverage,
        ),
    )


@pytest.fixture
def mock_futures_settings() -> Settings:
    return _make_settings()


@pytest.fixture
def futures_client(mock_futures_settings: Settings) -> KrakenFuturesClient:
    with patch("ccxt.async_support.krakenfutures"):
        return KrakenFuturesClient(mock_futures_settings)


class TestInit:
    """Initialization and properties."""

    def test_name(self, futures_client: KrakenFuturesClient) -> None:
        assert futures_client.name == "kraken_futures"

    def test_maker_fee(self, futures_client: KrakenFuturesClient) -> None:
        assert futures_client.maker_fee == Decimal("0.0002")

    def test_taker_fee(self, futures_client: KrakenFuturesClient) -> None:
        assert futures_client.taker_fee == Decimal("0.0005")

    def test_max_leverage_from_settings(self) -> None:
        settings = _make_settings(max_leverage=5)
        with patch("ccxt.async_support.krakenfutures"):
            client = KrakenFuturesClient(settings)
        assert client.max_leverage == 5

    def test_is_subclass_of_base_perps(self, futures_client: KrakenFuturesClient) -> None:
        assert isinstance(futures_client, BaseExchangePerps)

    def test_demo_mode_sets_sandbox(self) -> None:
        settings = _make_settings(demo=True)
        with patch("ccxt.async_support.krakenfutures") as mock_cls:
            mock_exchange = MagicMock()
            mock_cls.return_value = mock_exchange
            KrakenFuturesClient(settings)
            mock_exchange.set_sandbox_mode.assert_called_once_with(True)

    def test_production_mode_no_sandbox(self) -> None:
        settings = _make_settings(demo=False)
        with patch("ccxt.async_support.krakenfutures") as mock_cls:
            mock_exchange = MagicMock()
            mock_cls.return_value = mock_exchange
            KrakenFuturesClient(settings)
            mock_exchange.set_sandbox_mode.assert_not_called()


class TestPairNormalization:
    """Pair format conversion."""

    def test_xbt_usd(self, futures_client: KrakenFuturesClient) -> None:
        assert futures_client.normalize_pair_to_exchange("XBT/USD") == "PF_XBTUSD"

    def test_eth_usd(self, futures_client: KrakenFuturesClient) -> None:
        assert futures_client.normalize_pair_to_exchange("ETH/USD") == "PF_ETHUSD"

    def test_sol_usd(self, futures_client: KrakenFuturesClient) -> None:
        assert futures_client.normalize_pair_to_exchange("SOL/USD") == "PF_SOLUSD"

    def test_btc_alias(self, futures_client: KrakenFuturesClient) -> None:
        assert futures_client.normalize_pair_to_exchange("BTC/USD") == "PF_XBTUSD"

    def test_unsupported_pair_raises(self, futures_client: KrakenFuturesClient) -> None:
        with pytest.raises(ValueError, match="Unsupported pair"):
            futures_client.normalize_pair_to_exchange("DOGE/EUR")

    def test_denormalize_xbt(self, futures_client: KrakenFuturesClient) -> None:
        assert futures_client.denormalize_pair_from_exchange("PF_XBTUSD") == "XBT/USD"

    def test_denormalize_eth(self, futures_client: KrakenFuturesClient) -> None:
        assert futures_client.denormalize_pair_from_exchange("PF_ETHUSD") == "ETH/USD"

    def test_denormalize_unknown_returns_as_is(self, futures_client: KrakenFuturesClient) -> None:
        assert futures_client.denormalize_pair_from_exchange("UNKNOWN") == "UNKNOWN"


class TestLeverageCap:
    """Leverage safety limits."""

    @pytest.mark.asyncio
    async def test_place_order_leverage_exceeds_max(
        self, futures_client: KrakenFuturesClient
    ) -> None:
        with pytest.raises(ValueError, match="exceeds max"):
            await futures_client.place_perp_order("XBT/USD", "buy", Decimal("0.01"), leverage=10)

    @pytest.mark.asyncio
    async def test_set_leverage_exceeds_max(self, futures_client: KrakenFuturesClient) -> None:
        with pytest.raises(ValueError, match="exceeds max"):
            await futures_client.set_leverage("XBT/USD", 10)

    @pytest.mark.asyncio
    async def test_set_leverage_below_one(self, futures_client: KrakenFuturesClient) -> None:
        with pytest.raises(ValueError, match=">= 1"):
            await futures_client.set_leverage("XBT/USD", 0)


class TestBalance:
    """Balance retrieval."""

    @pytest.mark.asyncio
    async def test_get_balance_returns_decimal(self, futures_client: KrakenFuturesClient) -> None:
        futures_client._exchange.fetch_balance = AsyncMock(
            return_value={"total": {"USD": 5000.0, "BTC": 0.5, "ETH": 0.0}}
        )
        balance = await futures_client.get_balance()
        assert balance == {
            "USD": Decimal("5000.0"),
            "BTC": Decimal("0.5"),
        }
        # ETH=0.0 filtered out
        assert "ETH" not in balance
        # All values are Decimal
        for v in balance.values():
            assert isinstance(v, Decimal)


class TestPositions:
    """Position retrieval and management."""

    @pytest.mark.asyncio
    async def test_get_position_none_when_empty(self, futures_client: KrakenFuturesClient) -> None:
        futures_client._exchange.fetch_positions = AsyncMock(return_value=[])
        result = await futures_client.get_perp_position("XBT/USD")
        assert result is None

    @pytest.mark.asyncio
    async def test_get_position_returns_correct_format(
        self, futures_client: KrakenFuturesClient
    ) -> None:
        futures_client._exchange.fetch_positions = AsyncMock(
            return_value=[
                {
                    "contracts": 0.5,
                    "side": "long",
                    "notional": 25000.0,
                    "entryPrice": 50000.0,
                    "markPrice": 51000.0,
                    "unrealizedPnl": 500.0,
                    "leverage": 3,
                    "liquidationPrice": 40000.0,
                }
            ]
        )
        pos = await futures_client.get_perp_position("XBT/USD")
        assert pos is not None
        assert pos["pair"] == "XBT/USD"
        assert pos["side"] == "long"
        assert pos["size"] == Decimal("0.5")
        assert pos["size_usd"] == Decimal("25000.0")
        assert pos["entry_price"] == Decimal("50000.0")
        assert pos["mark_price"] == Decimal("51000.0")
        assert pos["unrealized_pnl"] == Decimal("500.0")
        assert pos["leverage"] == 3
        assert pos["liquidation_price"] == Decimal("40000.0")
        # All monetary values are Decimal
        for key in ("size", "size_usd", "entry_price", "mark_price", "unrealized_pnl"):
            assert isinstance(pos[key], Decimal)

    @pytest.mark.asyncio
    async def test_get_position_no_liquidation_price(
        self, futures_client: KrakenFuturesClient
    ) -> None:
        futures_client._exchange.fetch_positions = AsyncMock(
            return_value=[
                {
                    "contracts": 0.1,
                    "side": "short",
                    "notional": 5000.0,
                    "entryPrice": 50000.0,
                    "markPrice": 49000.0,
                    "unrealizedPnl": 100.0,
                    "leverage": 1,
                    "liquidationPrice": None,
                }
            ]
        )
        pos = await futures_client.get_perp_position("XBT/USD")
        assert pos is not None
        assert pos["side"] == "short"
        assert pos["liquidation_price"] is None

    @pytest.mark.asyncio
    async def test_close_position_when_none(self, futures_client: KrakenFuturesClient) -> None:
        futures_client._exchange.fetch_positions = AsyncMock(return_value=[])
        result = await futures_client.close_perp_position("XBT/USD")
        assert result == {"status": "NO_POSITION"}

    @pytest.mark.asyncio
    async def test_get_all_positions_filters_zero(
        self, futures_client: KrakenFuturesClient
    ) -> None:
        futures_client._exchange.fetch_positions = AsyncMock(
            return_value=[
                {
                    "symbol": "PF_XBTUSD",
                    "contracts": 0.5,
                    "side": "long",
                    "notional": 25000.0,
                    "entryPrice": 50000.0,
                    "markPrice": 51000.0,
                    "unrealizedPnl": 500.0,
                    "leverage": 2,
                },
                {
                    "symbol": "PF_ETHUSD",
                    "contracts": 0,  # should be filtered out
                    "side": "long",
                    "notional": 0,
                    "entryPrice": 0,
                    "markPrice": 0,
                    "unrealizedPnl": 0,
                    "leverage": 1,
                },
            ]
        )
        positions = await futures_client.get_all_positions()
        assert len(positions) == 1
        assert positions[0]["pair"] == "XBT/USD"


class TestFundingRate:
    """Funding rate queries."""

    @pytest.mark.asyncio
    async def test_get_funding_rate_returns_decimal(
        self, futures_client: KrakenFuturesClient
    ) -> None:
        futures_client._exchange.fetch_funding_rate = AsyncMock(
            return_value={"fundingRate": 0.0001}
        )
        rate = await futures_client.get_funding_rate("XBT/USD")
        assert rate == Decimal("0.0001")
        assert isinstance(rate, Decimal)

    @pytest.mark.asyncio
    async def test_get_funding_history_format(self, futures_client: KrakenFuturesClient) -> None:
        futures_client._exchange.fetch_funding_rate_history = AsyncMock(
            return_value=[
                {"timestamp": 1700000000000, "fundingRate": 0.0001},
                {"timestamp": 1700003600000, "fundingRate": -0.0002},
            ]
        )
        history = await futures_client.get_funding_history(
            "XBT/USD", since_ms=1700000000000, limit=10
        )
        assert len(history) == 2
        assert history[0]["timestamp"] == 1700000000000
        assert history[0]["rate"] == Decimal("0.0001")
        assert history[1]["rate"] == Decimal("-0.0002")
        for h in history:
            assert isinstance(h["rate"], Decimal)


class TestOrderPlacement:
    """Order placement via ccxt."""

    @pytest.mark.asyncio
    async def test_place_market_order(self, futures_client: KrakenFuturesClient) -> None:
        futures_client._exchange.set_leverage = AsyncMock()
        futures_client._exchange.create_market_order = AsyncMock(
            return_value={
                "id": "order-123",
                "status": "closed",
                "amount": 0.01,
                "price": 50000.0,
            }
        )
        result = await futures_client.place_perp_order(
            pair="XBT/USD",
            side="buy",
            amount=Decimal("0.01"),
            price=None,
            leverage=2,
        )
        assert result["order_id"] == "order-123"
        assert result["status"] == "FILLED"
        assert result["amount"] == Decimal("0.01")
        assert result["price"] == Decimal("50000.0")
        assert isinstance(result["amount"], Decimal)
        assert isinstance(result["price"], Decimal)
        futures_client._exchange.create_market_order.assert_called_once()

    @pytest.mark.asyncio
    async def test_place_limit_order(self, futures_client: KrakenFuturesClient) -> None:
        futures_client._exchange.set_leverage = AsyncMock()
        futures_client._exchange.create_limit_order = AsyncMock(
            return_value={
                "id": "order-456",
                "status": "open",
                "amount": 0.05,
                "price": 48000.0,
            }
        )
        result = await futures_client.place_perp_order(
            pair="XBT/USD",
            side="buy",
            amount=Decimal("0.05"),
            price=Decimal("48000"),
            leverage=1,
        )
        assert result["order_id"] == "order-456"
        assert result["status"] == "PENDING"
        assert result["price"] == Decimal("48000.0")
        futures_client._exchange.create_limit_order.assert_called_once()

    @pytest.mark.asyncio
    async def test_reduce_only_param(self, futures_client: KrakenFuturesClient) -> None:
        futures_client._exchange.set_leverage = AsyncMock()
        futures_client._exchange.create_market_order = AsyncMock(
            return_value={
                "id": "order-789",
                "status": "closed",
                "amount": 0.01,
                "price": 50000.0,
            }
        )
        await futures_client.place_perp_order(
            pair="XBT/USD",
            side="sell",
            amount=Decimal("0.01"),
            reduce_only=True,
        )
        call_kwargs = futures_client._exchange.create_market_order.call_args
        assert call_kwargs.kwargs["params"]["reduceOnly"] is True


class TestStatusNormalization:
    """Order status mapping."""

    def test_open_to_pending(self) -> None:
        assert KrakenFuturesClient._normalize_status("open") == "PENDING"

    def test_closed_to_filled(self) -> None:
        assert KrakenFuturesClient._normalize_status("closed") == "FILLED"

    def test_canceled_to_cancelled(self) -> None:
        assert KrakenFuturesClient._normalize_status("canceled") == "CANCELLED"

    def test_expired(self) -> None:
        assert KrakenFuturesClient._normalize_status("expired") == "EXPIRED"

    def test_unknown_uppercased(self) -> None:
        assert KrakenFuturesClient._normalize_status("partial") == "PARTIAL"
