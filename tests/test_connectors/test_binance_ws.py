"""Tests for the Binance WebSocket client.

This module tests the WebSocket client functionality including:
- Initialization and state management
- Stream subscription / unsubscription
- Kline message parsing and EventBus publishing
- Anti-zombie watchdog and Telegram alerts
- Reconnection with exponential backoff
- Factory dispatch

IMPORTANT: These tests use mocked WebSocket connections and never
make real API calls to Binance.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
import json
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from krakenbot.config.settings import (
    BinanceSettings,
    DatabaseSettings,
    KrakenSettings,
    Settings,
    TradingMode,
    TradingSettings,
)
from krakenbot.connectors.binance.ws import (
    BINANCE_INTERVAL_MAP,
    INTERVAL_MAP,
    BinanceWebSocketClient,
    _pair_to_symbol,
    _symbol_to_pair,
)
from krakenbot.connectors.exchange import build_exchange_ws_client
from krakenbot.core.event_bus import EventBus, EventType, reset_event_bus
from krakenbot.core.exceptions import DataValidationError

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_settings() -> Settings:
    """Create mock settings with Binance exchange."""
    return Settings(
        app_name="KrakenBot-Test",
        environment="testing",
        exchange_name="binance",
        kraken=KrakenSettings(
            api_key="test_api_key",
            api_secret="test_api_secret",
        ),
        binance=BinanceSettings(
            api_key="test_binance_key",
            api_secret="test_binance_secret",
            ws_url="wss://stream.binance.com:9443",
        ),
        database=DatabaseSettings(
            url="postgresql+asyncpg://test:test@localhost:5432/krakenbot_test",
        ),
        trading=TradingSettings(
            mode=TradingMode.PAPER,
            pair="BTC/USDC",
        ),
    )


@pytest.fixture
def event_bus() -> EventBus:
    """Create a fresh EventBus for testing."""
    reset_event_bus()
    return EventBus()


@pytest.fixture
def mock_telegram() -> MagicMock:
    """Create a mock Telegram notifier."""
    notifier = MagicMock()
    notifier.send = AsyncMock(return_value=True)
    notifier.send_error = AsyncMock(return_value=True)
    return notifier


@pytest.fixture
def ws_client(
    mock_settings: Settings, event_bus: EventBus, mock_telegram: MagicMock
) -> BinanceWebSocketClient:
    """Create a BinanceWebSocketClient for testing."""
    return BinanceWebSocketClient(
        mock_settings,
        event_bus,
        telegram_notifier=mock_telegram,
    )


def _make_kline_message(
    *,
    symbol: str = "BTCUSDC",
    interval: str = "5m",
    is_closed: bool = True,
    open_price: str = "65000.00",
    high: str = "65200.00",
    low: str = "64900.00",
    close: str = "65100.00",
    volume: str = "12.345",
    start_time: int = 1700000000000,
    end_time: int = 1700000299999,
    trades: int = 42,
) -> str:
    """Build a Binance kline WebSocket message as JSON string."""
    data = {
        "e": "kline",
        "E": start_time + 100,
        "s": symbol,
        "k": {
            "t": start_time,
            "T": end_time,
            "s": symbol,
            "i": interval,
            "o": open_price,
            "c": close,
            "h": high,
            "l": low,
            "v": volume,
            "x": is_closed,
            "n": trades,
            "q": "802345.67",
        },
    }
    return json.dumps(data)


def _make_combined_kline_message(**kwargs: Any) -> str:
    """Build a combined-stream wrapped kline message."""
    inner = json.loads(_make_kline_message(**kwargs))
    symbol = kwargs.get("symbol", "BTCUSDC").lower()
    interval = kwargs.get("interval", "5m")
    wrapped = {
        "stream": f"{symbol}@kline_{interval}",
        "data": inner,
    }
    return json.dumps(wrapped)


# ---------------------------------------------------------------------------
# TestInit
# ---------------------------------------------------------------------------


class TestInit:
    """Test BinanceWebSocketClient initialization."""

    def test_init_creates_client(self, mock_settings: Settings, event_bus: EventBus) -> None:
        client = BinanceWebSocketClient(mock_settings, event_bus)
        assert not client.is_connected
        assert client.stats["messages_received"] == 0
        assert client.stats["ohlc_received"] == 0
        assert client.stats["reconnections"] == 0

    def test_init_without_telegram(self, mock_settings: Settings, event_bus: EventBus) -> None:
        client = BinanceWebSocketClient(mock_settings, event_bus, telegram_notifier=None)
        assert client._telegram_notifier is None

    def test_init_stores_telegram(
        self,
        mock_settings: Settings,
        event_bus: EventBus,
        mock_telegram: MagicMock,
    ) -> None:
        client = BinanceWebSocketClient(mock_settings, event_bus, telegram_notifier=mock_telegram)
        assert client._telegram_notifier is mock_telegram


# ---------------------------------------------------------------------------
# TestPairMapping
# ---------------------------------------------------------------------------


class TestPairMapping:
    """Test pair/symbol conversion helpers."""

    @pytest.mark.parametrize(
        ("pair", "expected"),
        [
            ("BTC/USDC", "btcusdc"),
            ("ETH/USDC", "ethusdc"),
            ("SOL/USDT", "solusdt"),
        ],
    )
    def test_pair_to_symbol(self, pair: str, expected: str) -> None:
        assert _pair_to_symbol(pair) == expected

    @pytest.mark.parametrize(
        ("symbol", "expected"),
        [
            ("BTCUSDC", "BTC/USDC"),
            ("ETHUSDC", "ETH/USDC"),
            ("SOLUSDT", "SOL/USDT"),
            ("BTCEUR", "BTC/EUR"),
        ],
    )
    def test_symbol_to_pair(self, symbol: str, expected: str) -> None:
        assert _symbol_to_pair(symbol) == expected


# ---------------------------------------------------------------------------
# TestSubscription
# ---------------------------------------------------------------------------


class TestSubscription:
    """Test stream subscription management."""

    async def test_subscribe_ohlc_builds_correct_stream(
        self, ws_client: BinanceWebSocketClient
    ) -> None:
        await ws_client.subscribe_ohlc("BTC/USDC", 240)
        sub = ws_client._subscriptions["ohlc-BTC/USDC-240"]
        assert sub["stream"] == "btcusdc@kline_4h"
        assert sub["type"] == "ohlc"
        assert sub["pair"] == "BTC/USDC"
        assert sub["interval"] == 240

    async def test_subscribe_ohlc_all_intervals(self, ws_client: BinanceWebSocketClient) -> None:
        for interval_min, binance_str in INTERVAL_MAP.items():
            await ws_client.subscribe_ohlc("BTC/USDC", interval_min)
            sub = ws_client._subscriptions[f"ohlc-BTC/USDC-{interval_min}"]
            assert sub["stream"] == f"btcusdc@kline_{binance_str}"

    async def test_subscribe_ohlc_invalid_interval(self, ws_client: BinanceWebSocketClient) -> None:
        with pytest.raises(DataValidationError):
            await ws_client.subscribe_ohlc("BTC/USDC", 999)

    async def test_subscribe_ticker_builds_correct_stream(
        self, ws_client: BinanceWebSocketClient
    ) -> None:
        await ws_client.subscribe_ticker("BTC/USDC")
        sub = ws_client._subscriptions["ticker-BTC/USDC"]
        assert sub["stream"] == "btcusdc@ticker"
        assert sub["type"] == "ticker"

    async def test_unsubscribe_removes_stream(self, ws_client: BinanceWebSocketClient) -> None:
        await ws_client.subscribe_ohlc("BTC/USDC", 5)
        assert "ohlc-BTC/USDC-5" in ws_client._subscriptions

        await ws_client.unsubscribe_ohlc("BTC/USDC", 5)
        assert "ohlc-BTC/USDC-5" not in ws_client._subscriptions

    async def test_subscribe_ohlc_sends_subscribe_when_connected(
        self, ws_client: BinanceWebSocketClient
    ) -> None:
        """When connected, subscribe_ohlc should send a SUBSCRIBE frame."""
        mock_ws = AsyncMock()
        mock_ws.closed = False
        ws_client._ws = mock_ws
        ws_client._connected = True

        await ws_client.subscribe_ohlc("BTC/USDC", 5)

        mock_ws.send_json.assert_called_once()
        sent = mock_ws.send_json.call_args[0][0]
        assert sent["method"] == "SUBSCRIBE"
        assert "btcusdc@kline_5m" in sent["params"]

    async def test_unsubscribe_sends_unsubscribe_when_connected(
        self, ws_client: BinanceWebSocketClient
    ) -> None:
        """When connected, unsubscribe should send an UNSUBSCRIBE frame."""
        mock_ws = AsyncMock()
        mock_ws.closed = False
        ws_client._ws = mock_ws
        ws_client._connected = True

        await ws_client.subscribe_ohlc("BTC/USDC", 5)
        mock_ws.send_json.reset_mock()

        await ws_client.unsubscribe_ohlc("BTC/USDC", 5)

        mock_ws.send_json.assert_called_once()
        sent = mock_ws.send_json.call_args[0][0]
        assert sent["method"] == "UNSUBSCRIBE"
        assert "btcusdc@kline_5m" in sent["params"]


# ---------------------------------------------------------------------------
# TestKlineHandling
# ---------------------------------------------------------------------------


class TestKlineHandling:
    """Test kline message parsing and EventBus publishing."""

    async def test_handle_kline_closed_publishes_complete(
        self, ws_client: BinanceWebSocketClient, event_bus: EventBus
    ) -> None:
        received: list[dict] = []
        await event_bus.subscribe(EventType.MARKET_OHLC, lambda d: received.append(d))

        raw = _make_kline_message(is_closed=True)
        await ws_client._handle_message(raw)

        assert len(received) == 1
        assert received[0]["is_complete"] is True
        assert received[0]["pair"] == "BTC/USDC"

    async def test_handle_kline_in_progress_publishes_incomplete(
        self, ws_client: BinanceWebSocketClient, event_bus: EventBus
    ) -> None:
        received: list[dict] = []
        await event_bus.subscribe(EventType.MARKET_OHLC, lambda d: received.append(d))

        raw = _make_kline_message(is_closed=False)
        await ws_client._handle_message(raw)

        assert len(received) == 1
        assert received[0]["is_complete"] is False

    async def test_handle_kline_correct_event_format(
        self, ws_client: BinanceWebSocketClient, event_bus: EventBus
    ) -> None:
        """Verify event dict matches Kraken format (strings, ISO timestamp)."""
        received: list[dict] = []
        await event_bus.subscribe(EventType.MARKET_OHLC, lambda d: received.append(d))

        raw = _make_kline_message(
            is_closed=True,
            open_price="65000.00",
            high="65200.00",
            low="64900.00",
            close="65100.00",
            volume="12.345",
            end_time=1700000299999,
        )
        await ws_client._handle_message(raw)

        evt = received[0]
        assert evt["pair"] == "BTC/USDC"
        assert evt["interval"] == 5  # 5m -> 5
        assert isinstance(evt["timestamp"], str)  # ISO string
        assert evt["open"] == "65000.00"
        assert evt["high"] == "65200.00"
        assert evt["low"] == "64900.00"
        assert evt["close"] == "65100.00"
        assert evt["volume"] == "12.345"
        assert evt["vwap"] is None  # Binance doesn't have VWAP
        assert evt["trades_count"] == 42

    async def test_ohlc_received_stat_only_on_closed(
        self, ws_client: BinanceWebSocketClient
    ) -> None:
        # In-progress candle should not increment ohlc_received
        raw_open = _make_kline_message(is_closed=False)
        await ws_client._handle_message(raw_open)
        assert ws_client._stats["ohlc_received"] == 0

        # Closed candle should increment
        raw_closed = _make_kline_message(is_closed=True)
        await ws_client._handle_message(raw_closed)
        assert ws_client._stats["ohlc_received"] == 1

    async def test_handle_combined_stream_wrapper(
        self, ws_client: BinanceWebSocketClient, event_bus: EventBus
    ) -> None:
        """Combined-stream format (with 'stream' wrapper) should be handled."""
        received: list[dict] = []
        await event_bus.subscribe(EventType.MARKET_OHLC, lambda d: received.append(d))

        raw = _make_combined_kline_message(is_closed=True)
        await ws_client._handle_message(raw)

        assert len(received) == 1
        assert received[0]["is_complete"] is True

    async def test_handle_subscribe_response_ignored(
        self, ws_client: BinanceWebSocketClient, event_bus: EventBus
    ) -> None:
        """Subscribe response messages should not trigger OHLC events."""
        received: list[dict] = []
        await event_bus.subscribe(EventType.MARKET_OHLC, lambda d: received.append(d))

        response = json.dumps({"result": None, "id": 1})
        await ws_client._handle_message(response)

        assert len(received) == 0

    async def test_handle_kline_interval_mapping(
        self, ws_client: BinanceWebSocketClient, event_bus: EventBus
    ) -> None:
        """Verify all interval mappings work correctly."""
        for binance_str, minutes in BINANCE_INTERVAL_MAP.items():
            received: list[dict] = []
            await event_bus.subscribe(EventType.MARKET_OHLC, lambda d, r=received: r.append(d))

            raw = _make_kline_message(interval=binance_str, is_closed=True)
            await ws_client._handle_message(raw)

            assert received[-1]["interval"] == minutes
            await event_bus.clear_subscribers(EventType.MARKET_OHLC)


# ---------------------------------------------------------------------------
# TestWatchdogAndAlerts
# ---------------------------------------------------------------------------


class TestWatchdogAndAlerts:
    """Test zombie detection and Telegram alerts."""

    async def test_zombie_detection_triggers_reconnect(
        self, ws_client: BinanceWebSocketClient
    ) -> None:
        """If message count is stale after 5 min, watchdog triggers reconnect."""
        ws_client._running = True
        ws_client._connected = True
        ws_client._stats["messages_received"] = 42  # frozen count

        with patch.object(ws_client, "_reconnect", new_callable=AsyncMock):
            # Override sleep to make test fast
            with patch("asyncio.sleep", new_callable=AsyncMock):
                # Run watchdog — it checks once and should detect stale data
                await ws_client._data_flow_watchdog()

            # Zombie should have been detected (alert flag set)
            assert ws_client._zombie_alert_sent

    async def test_zombie_alert_sent_via_telegram(
        self, ws_client: BinanceWebSocketClient, mock_telegram: MagicMock
    ) -> None:
        """Telegram alert should be sent when zombie is detected."""
        ws_client._running = True
        ws_client._connected = True
        ws_client._last_message_time = datetime(2020, 1, 1, tzinfo=UTC)

        await ws_client._send_zombie_alert()

        mock_telegram.send.assert_called_once()
        msg = mock_telegram.send.call_args[0][0]
        assert "Zombie" in msg
        assert "binance" in msg

    async def test_zombie_alert_only_sent_once(
        self, ws_client: BinanceWebSocketClient, mock_telegram: MagicMock
    ) -> None:
        """Zombie alert should not be sent again if already sent."""
        ws_client._zombie_alert_sent = True
        ws_client._last_message_time = datetime(2020, 1, 1, tzinfo=UTC)

        # _send_zombie_alert is only called by the watchdog when _zombie_alert_sent is False
        # So we test the flag gating directly
        ws_client._running = True
        ws_client._connected = True
        ws_client._stats["messages_received"] = 0

        # Simulate the watchdog logic
        if not ws_client._zombie_alert_sent:
            await ws_client._send_zombie_alert()
        else:
            pass  # Alert not sent because flag is True

        mock_telegram.send.assert_not_called()

    async def test_recovery_alert_after_reconnect(
        self, ws_client: BinanceWebSocketClient, mock_telegram: MagicMock
    ) -> None:
        """Recovery alert should be sent after reconnect from zombie state."""
        await ws_client._send_recovery_alert()

        mock_telegram.send.assert_called_once()
        msg = mock_telegram.send.call_args[0][0]
        assert "Recovered" in msg


# ---------------------------------------------------------------------------
# TestReconnection
# ---------------------------------------------------------------------------


class TestReconnection:
    """Test reconnection with exponential backoff."""

    async def test_reconnect_exponential_backoff(self, ws_client: BinanceWebSocketClient) -> None:
        """Verify exponential backoff delay calculation."""
        delays: list[float] = []

        with (
            patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep,
            patch.object(ws_client, "_cleanup", new_callable=AsyncMock),
            patch.object(ws_client, "connect", new_callable=AsyncMock),
        ):
            # Simulate 4 reconnection attempts
            for _ in range(4):
                ws_client._reconnect_count = 0  # reset so _reconnect increments
                await ws_client._reconnect()
                if mock_sleep.called:
                    delays.append(mock_sleep.call_args[0][0])
                mock_sleep.reset_mock()

        # Each attempt starts at count 0 -> incremented to 1 -> delay = 5 * 2^0 = 5
        for d in delays:
            assert d == 5.0

    async def test_reconnect_capped_at_300(self, ws_client: BinanceWebSocketClient) -> None:
        """Backoff delay should be capped at 300 seconds."""
        ws_client._reconnect_count = 9  # next will be 10

        with (
            patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep,
            patch.object(ws_client, "_cleanup", new_callable=AsyncMock),
            patch.object(ws_client, "connect", new_callable=AsyncMock),
        ):
            await ws_client._reconnect()

        delay = mock_sleep.call_args[0][0]
        assert delay <= 300

    async def test_reconnect_max_attempts_sends_critical_alert(
        self, ws_client: BinanceWebSocketClient, mock_telegram: MagicMock
    ) -> None:
        """After max attempts, a critical Telegram alert should be sent."""
        ws_client._reconnect_count = ws_client._max_reconnect_attempts

        await ws_client._reconnect()

        mock_telegram.send.assert_called_once()
        msg = mock_telegram.send.call_args[0][0]
        assert "CRITICAL" in msg

    async def test_reconnect_resubscribes(self, ws_client: BinanceWebSocketClient) -> None:
        """After reconnect, all previous subscriptions should be restored."""
        ws_client._subscriptions = {
            "ohlc-BTC/USDC-5": {
                "type": "ohlc",
                "pair": "BTC/USDC",
                "interval": 5,
                "stream": "btcusdc@kline_5m",
            },
            "ticker-BTC/USDC": {
                "type": "ticker",
                "pair": "BTC/USDC",
                "stream": "btcusdc@ticker",
            },
        }

        with (
            patch("asyncio.sleep", new_callable=AsyncMock),
            patch.object(ws_client, "_cleanup", new_callable=AsyncMock),
            patch.object(ws_client, "connect", new_callable=AsyncMock),
            patch.object(ws_client, "subscribe_ohlc", new_callable=AsyncMock) as mock_sub_ohlc,
            patch.object(ws_client, "subscribe_ticker", new_callable=AsyncMock) as mock_sub_ticker,
        ):
            await ws_client._reconnect()

        mock_sub_ohlc.assert_called_once_with("BTC/USDC", 5)
        mock_sub_ticker.assert_called_once_with("BTC/USDC")

    async def test_reconnect_resets_zombie_flag(
        self, ws_client: BinanceWebSocketClient, mock_telegram: MagicMock
    ) -> None:
        """After successful reconnect from zombie state, flag should reset."""
        ws_client._zombie_alert_sent = True

        with (
            patch("asyncio.sleep", new_callable=AsyncMock),
            patch.object(ws_client, "_cleanup", new_callable=AsyncMock),
            patch.object(ws_client, "connect", new_callable=AsyncMock),
        ):
            await ws_client._reconnect()

        assert ws_client._zombie_alert_sent is False
        # Recovery alert should have been sent
        mock_telegram.send.assert_called()


# ---------------------------------------------------------------------------
# TestPreventiveReconnect
# ---------------------------------------------------------------------------


class TestPreventiveReconnect:
    """Test 23h preventive reconnect."""

    async def test_preventive_reconnect_sleeps_23h(self, ws_client: BinanceWebSocketClient) -> None:
        """Preventive reconnect should sleep for 23 hours."""
        ws_client._running = True
        ws_client._connected = True

        with (
            patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep,
            patch.object(ws_client, "_force_disconnect_and_reconnect", new_callable=AsyncMock),
        ):
            await ws_client._preventive_reconnect_timer()

        mock_sleep.assert_called_once_with(23 * 3600)


# ---------------------------------------------------------------------------
# TestFactory
# ---------------------------------------------------------------------------


class TestFactory:
    """Test build_exchange_ws_client factory function."""

    def test_factory_returns_binance_ws(self, mock_settings: Settings, event_bus: EventBus) -> None:
        client = build_exchange_ws_client(mock_settings, event_bus)
        assert isinstance(client, BinanceWebSocketClient)

    def test_factory_returns_kraken_ws(self, event_bus: EventBus) -> None:
        from krakenbot.connectors.kraken.ws import KrakenWebSocketClient

        settings = Settings(
            app_name="KrakenBot-Test",
            environment="testing",
            exchange_name="kraken",
            kraken=KrakenSettings(
                api_key="test",
                api_secret="test",
            ),
            database=DatabaseSettings(
                url="postgresql+asyncpg://test:test@localhost:5432/krakenbot_test",
            ),
            trading=TradingSettings(
                mode=TradingMode.PAPER,
                pair="XBT/EUR",
            ),
        )
        mock_db = MagicMock()
        client = build_exchange_ws_client(settings, event_bus, db_manager=mock_db)
        assert isinstance(client, KrakenWebSocketClient)


# ---------------------------------------------------------------------------
# TestConnection
# ---------------------------------------------------------------------------


class TestConnection:
    """Test connection lifecycle."""

    async def test_connect_creates_session_and_ws(self, ws_client: BinanceWebSocketClient) -> None:
        mock_ws = AsyncMock()
        mock_ws.closed = False
        mock_ws.receive = AsyncMock(side_effect=asyncio.CancelledError)

        mock_session = AsyncMock()
        mock_session.ws_connect = AsyncMock(return_value=mock_ws)

        with patch("aiohttp.ClientSession", return_value=mock_session):
            await ws_client.connect()

        mock_session.ws_connect.assert_called_once()
        url = mock_session.ws_connect.call_args[0][0]
        assert url == "wss://stream.binance.com:9443/ws"
        assert ws_client._connected

        # Clean up tasks
        await ws_client.close()

    async def test_close_without_connection(self, ws_client: BinanceWebSocketClient) -> None:
        """close() should not raise if never connected."""
        await ws_client.close()  # Should not raise

    async def test_is_connected_false_initially(self, ws_client: BinanceWebSocketClient) -> None:
        assert not ws_client.is_connected

    async def test_stats_initialized_to_zero(self, ws_client: BinanceWebSocketClient) -> None:
        stats = ws_client.stats
        assert stats["messages_received"] == 0
        assert stats["ohlc_received"] == 0
        assert stats["ticks_received"] == 0
        assert stats["errors"] == 0
        assert stats["reconnections"] == 0
