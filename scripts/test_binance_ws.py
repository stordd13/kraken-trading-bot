"""Test script to validate BinanceWebSocketClient with a real connection.

Connects to the public Binance WebSocket (no API keys required),
subscribes to BTC/USDC kline streams, and logs received events.

Usage:
    poetry run python scripts/test_binance_ws.py
    poetry run python scripts/test_binance_ws.py --duration 60
    poetry run python scripts/test_binance_ws.py --pair ETH/USDC --duration 120
"""

from __future__ import annotations

import argparse
import asyncio
import sys

from dotenv import load_dotenv
import structlog

load_dotenv()

from krakenbot.config.settings import Settings  # noqa: E402
from krakenbot.connectors.binance.ws import BinanceWebSocketClient  # noqa: E402
from krakenbot.core.event_bus import EventBus, EventType  # noqa: E402

log = structlog.get_logger()


async def main(pair: str, duration: int) -> None:
    """Run a live WebSocket test against Binance public streams."""
    settings = Settings()
    event_bus = EventBus()

    client = BinanceWebSocketClient(settings, event_bus, telegram_notifier=None)

    received_events: list[dict] = []
    complete_count = 0

    async def on_ohlc(data: dict) -> None:
        nonlocal complete_count
        received_events.append(data)
        is_complete = data.get("is_complete", False)
        if is_complete:
            complete_count += 1
        log.info(
            "ohlc_event",
            pair=data["pair"],
            interval=data["interval"],
            close=data["close"],
            is_complete=is_complete,
            total_events=len(received_events),
            complete_candles=complete_count,
        )

    await event_bus.subscribe(EventType.MARKET_OHLC, on_ohlc)

    try:
        log.info("connecting", pair=pair, duration_seconds=duration)
        await client.connect()

        # Subscribe to 1m (frequent updates for quick testing) and 5m
        await client.subscribe_ohlc(pair, 1)
        await client.subscribe_ohlc(pair, 5)
        log.info("subscribed", pair=pair, intervals="1m, 5m")

        log.info("listening", duration_seconds=duration)
        await asyncio.sleep(duration)

    except KeyboardInterrupt:
        log.info("interrupted_by_user")
    finally:
        await client.close()

    # Summary
    in_progress = len(received_events) - complete_count
    stats = client.stats

    log.info(
        "test_summary",
        total_ohlc_events=len(received_events),
        complete_candles=complete_count,
        in_progress_updates=in_progress,
        ws_messages_received=stats["messages_received"],
        ws_ohlc_received=stats["ohlc_received"],
        ws_errors=stats["errors"],
        ws_reconnections=stats["reconnections"],
        status="PASS" if len(received_events) > 0 else "FAIL",
    )

    if len(received_events) == 0:
        log.error("no_events_received", message="WebSocket test FAILED")
        sys.exit(1)
    else:
        log.info("test_passed", message="WebSocket connection working correctly")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Test Binance WebSocket connection")
    parser.add_argument("--pair", default="BTC/USDC", help="Trading pair (default: BTC/USDC)")
    parser.add_argument(
        "--duration", type=int, default=300, help="Listen duration in seconds (default: 300)"
    )
    args = parser.parse_args()

    asyncio.run(main(args.pair, args.duration))
