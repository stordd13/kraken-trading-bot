"""B1 round-trip demonstration for BybitRestClient on api.bybit.eu.

Read-only by default (markets, balance, ticker, OHLCV, paper round-trip).
With ``--trade`` it additionally places real LIMIT orders (never MARKET) that are
rejected or cancelled immediately, to settle the two open B0 questions:

  1. PostOnly far below the market (~notional USDC) -> status -> cancel   (criterion 4)
  2. LIMIT BUY at -2 %  -> expected rejection by priceLimitRatioX (capture retCode)
  3. PostOnly BUY above the ask -> expected PostOnly rejection (never fills)

Requires BYBIT_API_KEY / BYBIT_API_SECRET in .env. ``--trade`` needs a key with
readOnly=0 + Spot Trade and >= notional USDC available.

Usage:
    poetry run python scripts/audit/bybit_b1_roundtrip.py [--pair BTC/USDC] [--notional 6] [--trade]
"""

from __future__ import annotations

import argparse
import asyncio
from decimal import Decimal
import os
import sys

from dotenv import load_dotenv

from krakenbot.config.settings import (
    BybitSettings,
    DatabaseSettings,
    Settings,
    TradingMode,
    TradingSettings,
)
from krakenbot.connectors.bybit.rest import BybitRestClient
from krakenbot.core.event_bus import EventBus
from krakenbot.core.exceptions import KrakenBotError
from krakenbot.models.base import OrderStatus, TradeSide


def _section(title: str) -> None:
    print("\n" + "=" * 78 + f"\n{title}\n" + "=" * 78)


def _settings(mode: TradingMode, pair: str) -> Settings:
    key, secret = os.getenv("BYBIT_API_KEY", ""), os.getenv("BYBIT_API_SECRET", "")
    if not key or not secret:
        sys.exit("BYBIT_API_KEY / BYBIT_API_SECRET missing from .env")
    if mode == TradingMode.LIVE:
        trading = TradingSettings.model_construct(
            mode=TradingMode.LIVE,
            pair=pair,
            confirm_live="yes",
            default_order_amount_eur=100.0,
            candle_interval_min=15,
        )
    else:
        trading = TradingSettings(mode=TradingMode.PAPER, pair=pair)
    return Settings(
        environment="testing",
        exchange_name="bybit",
        bybit=BybitSettings(api_key=key, api_secret=secret),
        database=DatabaseSettings(url="postgresql+asyncpg://x:x@localhost:5432/unused"),
        trading=trading,
        _env_file=None,
    )


async def read_only_checks(pair: str) -> Decimal:
    _section("1. Read-only: load_markets / balance / ticker / OHLCV (LIVE client)")
    client = BybitRestClient(_settings(TradingMode.LIVE, pair), EventBus(), None)
    try:
        await client.load_markets()
        market = client._exchange.markets[pair]
        print(
            f"markets loaded on {client._settings.bybit.hostname}: {len(client._exchange.markets)}"
        )
        print(f"{pair} precision={market['precision']} limits={market.get('limits')}")

        balance = await client.get_balance()
        print(f"balance (free): {balance or '{} (wallet empty)'}")

        ticker = await client.get_ticker(pair)
        print(f"ticker: bid={ticker['bid']} ask={ticker['ask']} last={ticker['last']}")

        candles = await client.fetch_ohlcv(pair, 240, limit=3)
        for c in candles:
            print(f"  4h {c['timestamp'].isoformat()} O={c['open']} C={c['close']} V={c['volume']}")

        print(f"open orders: {await client.get_open_orders(pair)}")
        print(f"stats: {client.stats}")
        last: Decimal = ticker["last"]
        return last
    finally:
        await client.close()


async def paper_round_trip(pair: str, last: Decimal, notional: Decimal) -> None:
    _section("2. Paper round-trip (simulated fills, real ticker)")
    client = BybitRestClient(_settings(TradingMode.PAPER, pair), EventBus(), None)
    try:
        client.update_last_price(pair, last)
        await client.set_paper_balance("USDC", Decimal("1000"))
        await client.set_paper_balance("BTC", Decimal("0"))
        amount = client._round_amount(pair, notional / last)

        buy = await client.place_market_order(pair, TradeSide.BUY, amount, strategy="b1_demo")
        print(f"market BUY  {buy.amount} @ {buy.price} fee={buy.fee} {buy.fee_currency}")
        print(f"  balance: {client.get_paper_balance()}")

        limit = await client.place_limit_order(
            pair, TradeSide.SELL, amount, last * Decimal("1.05"), strategy="b1_demo"
        )
        print(f"limit SELL PostOnly(paper) -> {limit.status.value} id={limit.order_id}")
        print(f"  status: {await client.get_order_status(limit.order_id)}")
        print(f"  cancel: {await client.cancel_order(limit.order_id)}")

        sell = await client.place_market_order(pair, TradeSide.SELL, amount, strategy="b1_demo")
        print(f"market SELL {sell.amount} @ {sell.price} fee={sell.fee} {sell.fee_currency}")
        final = client.get_paper_balance()
        print(f"  balance: {final}")
        expected = Decimal("1000") - buy.fee - sell.fee
        print(f"  check: USDC == 1000 - fees -> {final['USDC'] == expected} (expected {expected})")
    finally:
        await client.close()


async def live_limit_checks(pair: str, last: Decimal, notional: Decimal) -> None:
    _section("3. LIVE limit orders (real, cancelled/rejected — NEVER market)")
    client = BybitRestClient(_settings(TradingMode.LIVE, pair), EventBus(), None)
    try:
        await client.load_markets()

        # 3a. PostOnly far below the market -> pending -> status -> cancel
        price = client._round_price(pair, last * Decimal("0.95"), TradeSide.BUY)
        amount = client._round_amount(pair, notional / price)
        print(f"3a. PostOnly BUY {amount} @ {price} (-5 %)")
        try:
            order = await client.place_limit_order(pair, TradeSide.BUY, amount, price, "b1_demo")
            print(
                f"    -> status={order.status.value} id={order.order_id} meta={order.signal_metadata}"
            )
            if order.status != OrderStatus.CANCELLED:
                print(
                    f"    get_order_status: {await client.get_order_status(order.order_id, pair)}"
                )
                print(f"    cancel_order: {await client.cancel_order(order.order_id, pair)}")
        except KrakenBotError as e:
            print(f"    -> {type(e).__name__}: {e}")

        # 3b. LIMIT BUY at -2 % -> priceLimitRatioX (0.5 %) expected rejection
        price = client._round_price(pair, last * Decimal("0.98"), TradeSide.BUY)
        amount = client._round_amount(pair, notional / price)
        print(f"3b. GTC BUY {amount} @ {price} (-2 %, priceLimitRatioX probe)")
        try:
            order = await client.place_limit_order(
                pair, TradeSide.BUY, amount, price, "b1_demo", post_only=False
            )
            print(
                f"    -> ACCEPTED status={order.status.value} id={order.order_id} (no rejection!)"
            )
            if order.status != OrderStatus.CANCELLED:
                print(f"    cancel_order: {await client.cancel_order(order.order_id, pair)}")
        except KrakenBotError as e:
            print(f"    -> {type(e).__name__}: {e}")

        # 3c. PostOnly BUY above the ask -> PostOnly rejection expected (never fills)
        ticker = await client.get_ticker(pair)
        ask = ticker["ask"] or last
        price = client._round_price(pair, ask * Decimal("1.001"), TradeSide.SELL)
        amount = client._round_amount(pair, notional / price)
        print(f"3c. PostOnly BUY {amount} @ {price} (above ask {ask})")
        try:
            order = await client.place_limit_order(pair, TradeSide.BUY, amount, price, "b1_demo")
            print(
                f"    -> status={order.status.value} id={order.order_id} meta={order.signal_metadata}"
            )
            if order.status not in {OrderStatus.CANCELLED, OrderStatus.FILLED}:
                print(f"    cancel_order: {await client.cancel_order(order.order_id, pair)}")
        except KrakenBotError as e:
            print(f"    -> {type(e).__name__}: {e}")

        print(f"open orders after run: {await client.get_open_orders(pair)}")
        print(f"stats: {client.stats}")
    finally:
        await client.close()


async def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pair", default="BTC/USDC")
    parser.add_argument("--notional", type=Decimal, default=Decimal("6"))
    parser.add_argument("--trade", action="store_true", help="place real LIMIT orders")
    args = parser.parse_args()

    load_dotenv()
    last = await read_only_checks(args.pair)
    await paper_round_trip(args.pair, last, args.notional)
    if args.trade:
        await live_limit_checks(args.pair, last, args.notional)
    else:
        _section("3. LIVE limit orders: skipped (pass --trade)")


if __name__ == "__main__":
    asyncio.run(main())
