"""Opt-in integration tests against the real Bybit EU API (api.bybit.eu).

Skipped unless ``BYBIT_INTEGRATION`` is set:
    BYBIT_INTEGRATION=1      read-only calls + paper round-trip (needs BYBIT_API_KEY/SECRET in .env)
    BYBIT_INTEGRATION=trade  additionally places ONE real PostOnly limit order far from the
                             market (~6 USDC notional) and cancels it — requires a key with
                             readOnly=0 + Spot Trade and >= 6 USDC available.

Never places a real MARKET order.
"""

from __future__ import annotations

from decimal import Decimal
import os

from dotenv import load_dotenv
import pytest

from krakenbot.config.settings import (
    BybitSettings,
    DatabaseSettings,
    Settings,
    TradingMode,
    TradingSettings,
)
from krakenbot.connectors.bybit.rest import (
    MIN_ORDER_SIZE,
    TICK_SIZE,
    BybitRestClient,
)
from krakenbot.core.event_bus import EventBus, reset_event_bus
from krakenbot.models.base import OrderStatus, TradeSide

_MODE = os.getenv("BYBIT_INTEGRATION", "")

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        not _MODE,
        reason="Set BYBIT_INTEGRATION=1 (read-only) or =trade (real limit order) to run",
    ),
]

PAIR = "BTC/USDC"


def _settings(mode: TradingMode) -> Settings:
    load_dotenv()
    key, secret = os.getenv("BYBIT_API_KEY", ""), os.getenv("BYBIT_API_SECRET", "")
    if mode == TradingMode.LIVE:
        trading = TradingSettings.model_construct(
            mode=TradingMode.LIVE,
            pair=PAIR,
            confirm_live="yes",
            default_order_amount_eur=100.0,
            candle_interval_min=15,
        )
    else:
        trading = TradingSettings(mode=TradingMode.PAPER, pair=PAIR)
    return Settings(
        environment="testing",
        exchange_name="bybit",
        bybit=BybitSettings(api_key=key, api_secret=secret),
        database=DatabaseSettings(url="postgresql+asyncpg://x:x@localhost:5432/unused"),
        trading=trading,
        _env_file=None,
    )


@pytest.fixture
async def live_client() -> BybitRestClient:
    reset_event_bus()
    client = BybitRestClient(_settings(TradingMode.LIVE), EventBus(), None)
    yield client
    await client.close()


@pytest.fixture
async def paper_client() -> BybitRestClient:
    reset_event_bus()
    client = BybitRestClient(_settings(TradingMode.PAPER), EventBus(), None)
    yield client
    await client.close()


async def test_load_markets_eu_filters_match_skill(live_client: BybitRestClient) -> None:
    await live_client.load_markets()
    assert live_client.markets_loaded
    for pair, step in MIN_ORDER_SIZE.items():
        market = live_client._exchange.markets[pair]
        assert Decimal(str(market["precision"]["amount"])) == step, pair
        assert Decimal(str(market["precision"]["price"])) == TICK_SIZE[pair], pair


async def test_get_balance_real(live_client: BybitRestClient) -> None:
    balance = await live_client.get_balance()
    assert isinstance(balance, dict)
    assert all(isinstance(v, Decimal) for v in balance.values())


async def test_fetch_ohlcv_4h(live_client: BybitRestClient) -> None:
    candles = await live_client.fetch_ohlcv(PAIR, 240, limit=10)
    assert 1 <= len(candles) <= 10
    assert candles[-1]["close"] > 0
    assert candles[0]["timestamp"] < candles[-1]["timestamp"]


async def test_paper_round_trip_with_real_ticker(paper_client: BybitRestClient) -> None:
    ticker = await paper_client.get_ticker(PAIR)
    last = ticker["last"]
    assert last and last > 0

    await paper_client.set_paper_balance("USDC", Decimal("1000"))
    await paper_client.set_paper_balance("BTC", Decimal("0"))
    amount = Decimal("0.0002")

    buy = await paper_client.place_market_order(PAIR, TradeSide.BUY, amount, strategy="b1")
    sell = await paper_client.place_market_order(PAIR, TradeSide.SELL, amount, strategy="b1")

    fee_total = buy.fee + sell.fee
    expected_usdc = Decimal("1000") - fee_total
    assert paper_client.paper_balance["BTC"] == Decimal("0")
    assert paper_client.paper_balance["USDC"] == expected_usdc
    assert fee_total == amount * last * Decimal("0.0025") * 2


@pytest.mark.skipif(_MODE != "trade", reason="BYBIT_INTEGRATION=trade required (real order)")
async def test_live_post_only_limit_round_trip(live_client: BybitRestClient) -> None:
    ticker = await live_client.get_ticker(PAIR)
    price = (ticker["last"] * Decimal("0.95")).quantize(Decimal("0.1"))
    amount = (Decimal("6") / price).quantize(Decimal("0.000001"))
    order = await live_client.place_limit_order(PAIR, TradeSide.BUY, amount, price, "b1")
    try:
        assert order.status == OrderStatus.PENDING, order.signal_metadata
        status = await live_client.get_order_status(order.order_id, PAIR)
        assert status["status"] == "open"
    finally:
        assert await live_client.cancel_order(order.order_id, PAIR) is True
    assert await live_client.get_open_orders(PAIR) == []
