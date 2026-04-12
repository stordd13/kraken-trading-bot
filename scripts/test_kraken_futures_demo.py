"""Manual test script for Kraken Futures in demo environment.

Usage:
    1. Create API keys at https://demo-futures.kraken.com/settings/api
    2. Set env vars:
       KRAKEN_FUTURES_API_KEY=xxx
       KRAKEN_FUTURES_API_SECRET=yyy
       KRAKEN_FUTURES_DEMO=true
       KRAKEN_FUTURES_ENABLED=true
    3. Run: poetry run python scripts/test_kraken_futures_demo.py
"""

from __future__ import annotations

import asyncio
import time

import structlog

from krakenbot.config.settings import KrakenFuturesSettings, Settings
from krakenbot.connectors.kraken.futures import KrakenFuturesClient

log = structlog.get_logger()


async def main() -> None:
    """Run a series of read-only tests against the Kraken Futures demo env."""
    settings = Settings(
        environment="development",
        kraken_futures=KrakenFuturesSettings(
            enabled=True,
            demo=True,
        ),
    )

    if not settings.kraken_futures.api_key.get_secret_value():
        log.error(
            "missing_api_key",
            message="Set KRAKEN_FUTURES_API_KEY and KRAKEN_FUTURES_API_SECRET env vars",
        )
        return

    client = KrakenFuturesClient(settings)

    try:
        # 1. Balance
        log.info("test_1_balance", status="fetching...")
        balance = await client.get_balance()
        log.info("test_1_balance", result=str(balance))

        # 2. Funding rate
        log.info("test_2_funding_rate", status="fetching XBT/USD...")
        rate = await client.get_funding_rate("XBT/USD")
        log.info("test_2_funding_rate", rate=str(rate))

        # 3. Funding history (last 24h)
        log.info("test_3_funding_history", status="fetching 24h...")
        since = int(time.time() * 1000) - 86400000
        history = await client.get_funding_history("XBT/USD", since, limit=24)
        log.info("test_3_funding_history", count=len(history))
        for h in history[:5]:
            log.info("funding_sample", timestamp=h["timestamp"], rate=str(h["rate"]))

        # 4. Current position (should be None on a fresh demo account)
        log.info("test_4_position", status="fetching XBT/USD...")
        position = await client.get_perp_position("XBT/USD")
        log.info("test_4_position", result=str(position))

        # 5. All positions
        log.info("test_5_all_positions", status="fetching...")
        positions = await client.get_all_positions()
        log.info("test_5_all_positions", count=len(positions))

        # 6. DEMO ORDER — uncomment to actually place an order
        # WARNING: This will place a real order on the demo exchange
        # log.warning("PLACING DEMO ORDER — 0.001 BTC market buy")
        # order = await client.place_perp_order(
        #     pair="XBT/USD",
        #     side="buy",
        #     amount=Decimal("0.001"),
        #     price=None,  # market order
        #     leverage=1,
        # )
        # log.info("demo_order_placed", order=str(order))

        log.info("all_tests_passed")

    finally:
        await client.close()


if __name__ == "__main__":
    asyncio.run(main())
