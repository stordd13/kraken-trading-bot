"""Test script to validate BinanceRestClient with real read-only credentials.

Requires BINANCE_API_KEY and BINANCE_API_SECRET in .env or environment.
Will only call read-only endpoints (no orders placed).

Usage:
    poetry run python scripts/test_binance_connection.py
"""

from __future__ import annotations

import asyncio
import sys

import structlog

from dotenv import load_dotenv
load_dotenv()

from krakenbot.config.settings import Settings
from krakenbot.connectors.binance.rest import BinanceRestClient
from krakenbot.core.event_bus import EventBus

log = structlog.get_logger()


async def main() -> None:
    """Run read-only Binance API tests."""
    settings = Settings()
    event_bus = EventBus()

    if not settings.binance.api_key.get_secret_value():
        log.error(
            "missing_binance_credentials",
            message="Set BINANCE_API_KEY and BINANCE_API_SECRET in .env",
        )
        sys.exit(1)

    client = BinanceRestClient(settings, event_bus, db_manager=None)
    passed = 0
    failed = 0

    try:
        # Test 1: get_ticker
        log.info("test_1_get_ticker")
        try:
            ticker = await client.get_ticker("BTC/USDC")
            log.info("ticker_result", pair=ticker["pair"], last=str(ticker["last"]))
            passed += 1
        except Exception as e:
            log.error("test_1_failed", error=str(e))
            failed += 1

        # Test 2: fetch_ohlcv (1h candles, last 10)
        log.info("test_2_fetch_ohlcv")
        try:
            candles = await client.fetch_ohlcv("BTC/USDC", interval=60, limit=10)
            log.info(
                "ohlcv_result",
                count=len(candles),
                first=str(candles[0]["timestamp"]) if candles else None,
                last=str(candles[-1]["timestamp"]) if candles else None,
            )
            passed += 1
        except Exception as e:
            log.error("test_2_failed", error=str(e))
            failed += 1

        # Test 3: get_balance
        log.info("test_3_get_balance")
        try:
            balance = await client.get_balance()
            log.info("balance_result", currencies=list(balance.keys()))
            passed += 1
        except Exception as e:
            log.error("test_3_failed", error=str(e))
            failed += 1

        # Test 4: get_open_orders
        log.info("test_4_get_open_orders")
        try:
            orders = await client.get_open_orders("BTC/USDC")
            log.info("open_orders", count=len(orders))
            passed += 1
        except Exception as e:
            log.error("test_4_failed", error=str(e))
            failed += 1

        # Summary
        log.info(
            "test_summary",
            passed=passed,
            failed=failed,
            total=passed + failed,
        )

        if failed > 0:
            sys.exit(1)

    finally:
        await client.close()


if __name__ == "__main__":
    asyncio.run(main())
