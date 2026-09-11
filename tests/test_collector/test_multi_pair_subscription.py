"""Tests for collector multi-pair subscription logic.

Validates that:
- All configured timeframes (settings.scheduler.intervals) are subscribed per pair
- Each pair also gets a ticker subscription
- Total subscription count is correct for N pairs
- TaskScheduler is built for every exchange with the read-only factory client (B3)
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from krakenbot.collector import DataCollector

ALL_INTERVALS = [1, 5, 15, 60, 240, 1440, 10080]


@pytest.fixture
def mock_collector_settings() -> MagicMock:
    """Create mock settings for the collector."""
    settings = MagicMock()
    settings.scheduler.pairs = ["BTC/USDC", "ETH/USDC", "SOL/USDC"]
    settings.scheduler.intervals = list(ALL_INTERVALS)
    settings.scheduler.enabled = False
    settings.exchange_name = "bybit"
    settings.log_level = "DEBUG"
    settings.log_json = False
    settings.app_name = "KrakenBot-Test"
    settings.environment = "testing"
    return settings


class TestMultiPairSubscription:
    """Collector subscribes to all pairs × all timeframes."""

    @pytest.mark.asyncio
    async def test_subscription_count_3_pairs(self, mock_collector_settings: MagicMock) -> None:
        """3 pairs × 7 intervals + 3 tickers = 24 subscriptions (3 Bybit requests)."""
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

        # 3 pairs × 7 intervals = 21 ohlc subscriptions
        assert ws.subscribe_ohlc.await_count == 21

        # 3 ticker subscriptions
        assert ws.subscribe_ticker.await_count == 3

    @pytest.mark.asyncio
    async def test_all_intervals_subscribed(self, mock_collector_settings: MagicMock) -> None:
        """Each pair gets every configured timeframe (7 by default, incl. 1m)."""
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

        expected_intervals = ALL_INTERVALS
        for pair in ["BTC/USDC", "ETH/USDC", "SOL/USDC"]:
            assert sorted(intervals_per_pair[pair]) == expected_intervals

    @pytest.mark.asyncio
    async def test_single_pair_still_works(self) -> None:
        """1 pair, 2 configured intervals → 2 ohlc + 1 ticker."""
        settings = MagicMock()
        settings.scheduler.pairs = ["BTC/USDC"]
        settings.scheduler.intervals = [60, 240]
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

        assert ws.subscribe_ohlc.await_count == 2
        assert ws.subscribe_ohlc.await_args_list[0].args == ("BTC/USDC", 60)
        assert ws.subscribe_ticker.await_count == 1


class TestTaskSchedulerViaFactory:
    """TaskScheduler is built for any exchange with the collector's read-only REST client (B3)."""

    @staticmethod
    def _collector(settings: MagicMock) -> DataCollector:
        collector = DataCollector.__new__(DataCollector)
        collector.settings = settings
        collector.logger = MagicMock()
        collector._setup_completed = False
        collector._running = False
        collector._shutdown_requested = False
        collector.task_scheduler = None
        return collector

    @staticmethod
    def _settings(exchange_name: str, enabled: bool = True) -> MagicMock:
        settings = MagicMock()
        settings.scheduler.pairs = ["BTC/USDC"]
        settings.scheduler.intervals = [60]
        settings.scheduler.enabled = enabled
        settings.exchange_name = exchange_name
        return settings

    @pytest.mark.parametrize("exchange_name", ["kraken", "binance", "bybit"])
    async def test_scheduler_built_with_factory_client(self, exchange_name: str) -> None:
        collector = self._collector(self._settings(exchange_name))
        db = MagicMock()
        db.init_db = AsyncMock()
        bus = MagicMock()
        rest_client = MagicMock()
        with (
            patch("krakenbot.collector.get_event_bus", return_value=bus),
            patch("krakenbot.collector.DatabaseManager", return_value=db),
            patch(
                "krakenbot.collector.build_exchange_rest_client", return_value=rest_client
            ) as factory,
            patch("krakenbot.collector.build_exchange_ws_client", return_value=MagicMock()),
            patch("krakenbot.collector.TaskScheduler") as scheduler_cls,
        ):
            await collector.setup()

        factory.assert_called_once_with(collector.settings, bus, db, read_only=True)
        scheduler_cls.assert_called_once_with(collector.settings, bus, db, rest_client)
        assert collector.task_scheduler is scheduler_cls.return_value
        assert not any(
            call.args and call.args[0] == "task_scheduler_skipped"
            for call in collector.logger.warning.call_args_list
        )

    async def test_scheduler_disabled_by_settings(self) -> None:
        collector = self._collector(self._settings("bybit", enabled=False))
        db = MagicMock()
        db.init_db = AsyncMock()
        with (
            patch("krakenbot.collector.get_event_bus", return_value=MagicMock()),
            patch("krakenbot.collector.DatabaseManager", return_value=db),
            patch("krakenbot.collector.build_exchange_rest_client", return_value=MagicMock()),
            patch("krakenbot.collector.build_exchange_ws_client", return_value=MagicMock()),
            patch("krakenbot.collector.TaskScheduler") as scheduler_cls,
        ):
            await collector.setup()

        scheduler_cls.assert_not_called()
        assert collector.task_scheduler is None
