"""Tests for collector multi-pair subscription logic.

Validates that:
- All 6 timeframes are subscribed per pair
- Each pair also gets a ticker subscription
- Total subscription count is correct for N pairs
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from krakenbot.collector import DataCollector


@pytest.fixture
def mock_collector_settings() -> MagicMock:
    """Create mock settings for the collector."""
    settings = MagicMock()
    settings.scheduler.pairs = ["BTC/USDC", "ETH/USDC", "SOL/USDC"]
    settings.scheduler.intervals = [5, 60, 240, 1440]
    settings.scheduler.enabled = False
    settings.log_level = "DEBUG"
    settings.log_json = False
    settings.app_name = "KrakenBot-Test"
    settings.environment = "testing"
    return settings


class TestMultiPairSubscription:
    """Collector subscribes to all pairs × all timeframes."""

    @pytest.mark.asyncio
    async def test_subscription_count_3_pairs(self, mock_collector_settings: MagicMock) -> None:
        """3 pairs × 6 intervals + 3 tickers = 21 subscriptions."""
        collector = DataCollector.__new__(DataCollector)
        collector.settings = mock_collector_settings
        collector.logger = MagicMock()
        collector._setup_completed = True
        collector._running = False
        collector._shutdown_requested = False

        # Mock WS client
        ws = MagicMock()
        ws.connect = AsyncMock()
        ws.subscribe_ohlc = AsyncMock()
        ws.subscribe_ticker = AsyncMock()
        collector.ws_client = ws

        # No task scheduler
        collector.task_scheduler = None

        await collector.start()

        # 3 pairs × 6 intervals = 18 ohlc subscriptions
        assert ws.subscribe_ohlc.await_count == 18

        # 3 ticker subscriptions
        assert ws.subscribe_ticker.await_count == 3

    @pytest.mark.asyncio
    async def test_all_intervals_subscribed(self, mock_collector_settings: MagicMock) -> None:
        """Each pair gets all 6 analysis timeframes: 5, 15, 60, 240, 1440, 10080."""
        collector = DataCollector.__new__(DataCollector)
        collector.settings = mock_collector_settings
        collector.logger = MagicMock()
        collector._setup_completed = True
        collector._running = False
        collector._shutdown_requested = False

        ws = MagicMock()
        ws.connect = AsyncMock()
        ws.subscribe_ohlc = AsyncMock()
        ws.subscribe_ticker = AsyncMock()
        collector.ws_client = ws
        collector.task_scheduler = None

        await collector.start()

        # Collect all interval args
        intervals_per_pair: dict[str, list[int]] = {}
        for call in ws.subscribe_ohlc.await_args_list:
            pair, interval = call.args
            intervals_per_pair.setdefault(pair, []).append(interval)

        expected_intervals = [5, 15, 60, 240, 1440, 10080]
        for pair in ["BTC/USDC", "ETH/USDC", "SOL/USDC"]:
            assert sorted(intervals_per_pair[pair]) == expected_intervals

    @pytest.mark.asyncio
    async def test_single_pair_still_works(self) -> None:
        """1 pair → 6 ohlc + 1 ticker = 7 subscriptions."""
        settings = MagicMock()
        settings.scheduler.pairs = ["BTC/USDC"]
        settings.scheduler.intervals = [60]
        settings.scheduler.enabled = False

        collector = DataCollector.__new__(DataCollector)
        collector.settings = settings
        collector.logger = MagicMock()
        collector._setup_completed = True
        collector._running = False
        collector._shutdown_requested = False

        ws = MagicMock()
        ws.connect = AsyncMock()
        ws.subscribe_ohlc = AsyncMock()
        ws.subscribe_ticker = AsyncMock()
        collector.ws_client = ws
        collector.task_scheduler = None

        await collector.start()

        assert ws.subscribe_ohlc.await_count == 6
        assert ws.subscribe_ticker.await_count == 1
