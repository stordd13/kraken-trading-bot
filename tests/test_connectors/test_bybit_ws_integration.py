"""Opt-in integration test against the real Bybit EU public WebSocket.

Skipped unless ``BYBIT_INTEGRATION`` is set (any value, e.g. ``1``):
connects to ``wss://stream.bybit.eu/v5/public/spot``, subscribes to the 1-min
klines + tickers of BTC/ETH/SOL-USDC, and expects at least one pong and at
least one market message (kline or ticker) within 90 s.  No DB, no API key.

    BYBIT_INTEGRATION=1 poetry run pytest tests/test_connectors/test_bybit_ws_integration.py -q
"""

from __future__ import annotations

import asyncio
from datetime import datetime
import os
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from krakenbot.config.settings import (
    BybitSettings,
    DatabaseSettings,
    Settings,
    TradingMode,
    TradingSettings,
)
from krakenbot.connectors.bybit.ws import BybitWebSocketClient
from krakenbot.core.event_bus import EventBus, EventType, reset_event_bus

_MODE = os.getenv("BYBIT_INTEGRATION", "")

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(not _MODE, reason="Set BYBIT_INTEGRATION=1 to hit stream.bybit.eu"),
]

PAIRS = ["BTC/USDC", "ETH/USDC", "SOL/USDC"]
TIMEOUT_SECONDS = 90


def _settings() -> Settings:
    return Settings(
        environment="testing",
        exchange_name="bybit",
        bybit=BybitSettings(_env_file=None),
        database=DatabaseSettings(url="postgresql+asyncpg://x:x@localhost:5432/unused"),
        trading=TradingSettings(mode=TradingMode.PAPER, pair="BTC/USDC"),
        _env_file=None,
    )


async def test_real_stream_pong_and_market_data() -> None:
    reset_event_bus()
    bus = EventBus()
    ohlc: list[dict[str, Any]] = []
    ticks: list[dict[str, Any]] = []
    await bus.subscribe(EventType.MARKET_OHLC, lambda d: ohlc.append(d))
    await bus.subscribe(EventType.MARKET_TICK, lambda d: ticks.append(d))

    telegram = MagicMock()
    telegram.send = AsyncMock(return_value=True)
    client = BybitWebSocketClient(_settings(), bus, db_manager=None, telegram_notifier=telegram)

    await client.connect()
    try:
        assert client.is_connected
        for pair in PAIRS:
            await client.subscribe_ohlc(pair, 1)
            await client.subscribe_ticker(pair)

        loop = asyncio.get_running_loop()
        deadline = loop.time() + TIMEOUT_SECONDS
        while loop.time() < deadline:
            if client.stats["pongs_received"] >= 1 and (ohlc or ticks):
                break
            await asyncio.sleep(1)
    finally:
        stats = client.stats
        await client.close()

    print(f"bybit ws integration stats: {stats}, klines={len(ohlc)}, ticks={len(ticks)}")
    assert stats["pongs_received"] >= 1, "no application pong received"
    assert ohlc or ticks, "no kline/ticker message received within timeout"
    assert stats["errors"] == 0
    assert stats["reconnections"] == 0
    telegram.send.assert_not_awaited()

    if not ohlc:
        print("NOTE: no 1-min kline within timeout (no trade on BTC/ETH/SOL-USDC) — tickers only")
    for event in ohlc:
        ts = datetime.fromisoformat(event["timestamp"])
        assert int(ts.timestamp()) % 60 == 0, f"timestamp not aligned on the grid: {ts}"
        assert event["pair"] in PAIRS
        assert event["interval"] == 1
        assert event["trades_count"] is None
    for tick in ticks:
        assert tick["pair"] in PAIRS
        assert tick["price"] is not None
