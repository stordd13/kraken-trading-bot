"""Tests for the Kraken WebSocket client.

This module tests the WebSocket client functionality including:
- Connection management
- Subscription handling
- Message parsing
- Data persistence
- Event publishing

IMPORTANT: These tests use mocked WebSocket connections and never
make real API calls to Kraken.
"""

from __future__ import annotations

import asyncio
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from krakenbot.config.settings import (
    DatabaseSettings,
    KrakenSettings,
    Settings,
    TradingMode,
    TradingSettings,
)
from krakenbot.connectors.kraken_ws import (
    VALID_OHLC_INTERVALS,
    KrakenWebSocketClient,
)
from krakenbot.core.event_bus import EventBus, EventType, reset_event_bus
from krakenbot.core.exceptions import (
    DataValidationError,
    WebSocketDisconnectedError,
)


@pytest.fixture
def mock_settings() -> Settings:
    """Create mock settings for testing.

    Returns:
        A Settings instance configured for testing.
    """
    return Settings(
        app_name="KrakenBot-Test",
        environment="testing",
        kraken=KrakenSettings(
            api_key="test_api_key",
            api_secret="test_api_secret",
            ws_url="wss://ws.kraken.com",
            ws_reconnect_delay_sec=1,
        ),
        database=DatabaseSettings(
            url="postgresql+asyncpg://test:test@localhost:5432/krakenbot_test",
        ),
        trading=TradingSettings(
            mode=TradingMode.PAPER,
            pair="XBT/EUR",
        ),
    )


@pytest.fixture
def event_bus() -> EventBus:
    """Create a fresh EventBus for testing.

    Returns:
        A new EventBus instance.
    """
    reset_event_bus()
    return EventBus()


@pytest.fixture
def mock_db_manager() -> MagicMock:
    """Create a mock database manager.

    Returns:
        A mock DatabaseManager.
    """
    manager = MagicMock()
    manager.session = MagicMock()

    # Create async context manager mock
    session_cm = MagicMock()
    session_cm.__aenter__ = AsyncMock(return_value=MagicMock())
    session_cm.__aexit__ = AsyncMock(return_value=None)
    manager.session.return_value = session_cm

    return manager


@pytest.fixture
def ws_client(
    mock_settings: Settings,
    event_bus: EventBus,
    mock_db_manager: MagicMock,
) -> KrakenWebSocketClient:
    """Create a WebSocket client for testing.

    Args:
        mock_settings: Test settings.
        event_bus: Test event bus.
        mock_db_manager: Mock database manager.

    Returns:
        A KrakenWebSocketClient instance.
    """
    return KrakenWebSocketClient(mock_settings, event_bus, mock_db_manager)


class TestKrakenWebSocketClientInit:
    """Tests for WebSocket client initialization."""

    def test_init_creates_client(
        self, mock_settings: Settings, event_bus: EventBus, mock_db_manager: MagicMock
    ) -> None:
        """Test that client initializes properly."""
        client = KrakenWebSocketClient(mock_settings, event_bus, mock_db_manager)

        assert client is not None
        assert client.is_connected is False
        assert client._running is False

    def test_init_with_settings(
        self, mock_settings: Settings, event_bus: EventBus, mock_db_manager: MagicMock
    ) -> None:
        """Test that client stores settings correctly."""
        client = KrakenWebSocketClient(mock_settings, event_bus, mock_db_manager)

        assert client._settings == mock_settings


class TestKrakenWebSocketClientConnection:
    """Tests for WebSocket connection management."""

    @patch("aiohttp.ClientSession")
    async def test_connect_creates_session(
        self,
        mock_session_class: MagicMock,
        ws_client: KrakenWebSocketClient,
    ) -> None:
        """Test that connect creates a client session."""
        mock_session = AsyncMock()
        mock_ws = AsyncMock()
        mock_ws.closed = False
        mock_ws.receive = AsyncMock(side_effect=asyncio.CancelledError)
        mock_session.ws_connect = AsyncMock(return_value=mock_ws)
        mock_session_class.return_value = mock_session

        try:
            await ws_client.connect()
        except asyncio.CancelledError:
            pass

        mock_session.ws_connect.assert_called_once()

    async def test_is_connected_false_initially(
        self, ws_client: KrakenWebSocketClient
    ) -> None:
        """Test that is_connected is False before connecting."""
        assert ws_client.is_connected is False

    async def test_close_without_connection(
        self, ws_client: KrakenWebSocketClient
    ) -> None:
        """Test that close works even without connection."""
        # Should not raise
        await ws_client.close()
        assert ws_client.is_connected is False


class TestKrakenWebSocketClientSubscription:
    """Tests for subscription functionality."""

    def test_valid_ohlc_intervals(self) -> None:
        """Test that valid OHLC intervals are defined."""
        assert 1 in VALID_OHLC_INTERVALS
        assert 5 in VALID_OHLC_INTERVALS
        assert 15 in VALID_OHLC_INTERVALS
        assert 60 in VALID_OHLC_INTERVALS
        assert 1440 in VALID_OHLC_INTERVALS

    async def test_subscribe_ohlc_invalid_interval(
        self, ws_client: KrakenWebSocketClient
    ) -> None:
        """Test that invalid OHLC interval raises error."""
        # Mock connection
        ws_client._connected = True
        ws_client._ws = AsyncMock()

        with pytest.raises(DataValidationError) as exc_info:
            await ws_client.subscribe_ohlc("XBT/EUR", interval=7)

        assert "Invalid OHLC interval" in str(exc_info.value)

    async def test_subscribe_without_connection_raises(
        self, ws_client: KrakenWebSocketClient
    ) -> None:
        """Test that subscribing without connection raises error."""
        with pytest.raises(WebSocketDisconnectedError):
            await ws_client.subscribe_ohlc("XBT/EUR")

    async def test_subscribe_ticker_without_connection_raises(
        self, ws_client: KrakenWebSocketClient
    ) -> None:
        """Test that ticker subscription without connection raises error."""
        with pytest.raises(WebSocketDisconnectedError):
            await ws_client.subscribe_ticker("XBT/EUR")

    async def test_subscribe_trades_without_connection_raises(
        self, ws_client: KrakenWebSocketClient
    ) -> None:
        """Test that trades subscription without connection raises error."""
        with pytest.raises(WebSocketDisconnectedError):
            await ws_client.subscribe_trades("XBT/EUR")


class TestKrakenWebSocketClientMessageHandling:
    """Tests for message handling."""

    async def test_handle_ohlc_data(
        self,
        ws_client: KrakenWebSocketClient,
        event_bus: EventBus,
    ) -> None:
        """Test handling OHLC data message."""
        received_events: list[dict[str, Any]] = []

        async def capture_event(data: dict[str, Any]) -> None:
            received_events.append(data)

        await event_bus.subscribe(EventType.MARKET_OHLC, capture_event)

        # Simulate OHLC message
        # Format: [channelID, [time, etime, open, high, low, close, vwap, volume, count], "ohlc-15", "XBT/EUR"]
        ohlc_data = [
            "1548111060.000000",
            "1548111120.000000",
            "3586.70000",
            "3586.70000",
            "3586.60000",
            "3586.60000",
            "3586.68894",
            "0.03373000",
            "2",
        ]

        await ws_client._handle_ohlc_data("XBT/EUR", ohlc_data, "ohlc-15")

        assert len(received_events) == 1
        assert received_events[0]["pair"] == "XBT/EUR"
        assert received_events[0]["interval"] == 15
        assert received_events[0]["close"] == "3586.60000"

    async def test_handle_ticker_data(
        self,
        ws_client: KrakenWebSocketClient,
        event_bus: EventBus,
    ) -> None:
        """Test handling ticker data message."""
        received_events: list[dict[str, Any]] = []

        async def capture_event(data: dict[str, Any]) -> None:
            received_events.append(data)

        await event_bus.subscribe(EventType.MARKET_TICK, capture_event)

        # Simulate ticker message
        ticker_data = {
            "a": ["5525.40000", "1", "1.000"],
            "b": ["5525.10000", "1", "1.000"],
            "c": ["5525.10000", "0.00398963"],
            "v": ["2634.11501494", "3591.17907851"],
            "p": ["5631.44067", "5653.78720"],
            "t": [11493, 16267],
        }

        await ws_client._handle_ticker_data("XBT/EUR", ticker_data)

        assert len(received_events) == 1
        assert received_events[0]["pair"] == "XBT/EUR"
        assert received_events[0]["price"] == "5525.10000"

    async def test_handle_trade_data(
        self,
        ws_client: KrakenWebSocketClient,
        event_bus: EventBus,
    ) -> None:
        """Test handling trade data message."""
        received_events: list[dict[str, Any]] = []

        async def capture_event(data: dict[str, Any]) -> None:
            received_events.append(data)

        await event_bus.subscribe(EventType.MARKET_TICK, capture_event)

        # Simulate trade message
        trade_data = [
            ["5541.20000", "0.15850568", "1534614057.321597", "s", "l", ""],
            ["5541.20000", "0.12345678", "1534614057.321598", "b", "m", ""],
        ]

        await ws_client._handle_trade_data("XBT/EUR", trade_data)

        assert len(received_events) == 2
        assert received_events[0]["side"] == "sell"
        assert received_events[1]["side"] == "buy"

    async def test_handle_system_status(
        self, ws_client: KrakenWebSocketClient
    ) -> None:
        """Test handling system status message."""
        # Should not raise
        await ws_client._handle_system_message(
            {"event": "systemStatus", "status": "online", "version": "1.0.0"}
        )

    async def test_handle_subscription_status(
        self, ws_client: KrakenWebSocketClient
    ) -> None:
        """Test handling subscription status message."""
        # Should store channel mapping
        await ws_client._handle_subscription_status(
            {
                "channelID": 42,
                "pair": "XBT/EUR",
                "status": "subscribed",
                "subscription": {"name": "ohlc", "interval": 15},
            }
        )

        assert 42 in ws_client._channel_ids
        assert ws_client._channel_ids[42]["pair"] == "XBT/EUR"

    async def test_handle_heartbeat(self, ws_client: KrakenWebSocketClient) -> None:
        """Test handling heartbeat message."""
        # Should not raise
        await ws_client._handle_system_message({"event": "heartbeat"})

    async def test_handle_error_message(
        self, ws_client: KrakenWebSocketClient
    ) -> None:
        """Test handling error message."""
        # Should increment error counter
        initial_errors = ws_client._stats["errors"]

        await ws_client._handle_system_message(
            {"event": "error", "errorMessage": "Test error"}
        )

        assert ws_client._stats["errors"] == initial_errors + 1


class TestKrakenWebSocketClientStats:
    """Tests for statistics tracking."""

    def test_stats_initialized(self, ws_client: KrakenWebSocketClient) -> None:
        """Test that stats are initialized to zero."""
        stats = ws_client.stats

        assert stats["messages_received"] == 0
        assert stats["ohlc_received"] == 0
        assert stats["ticks_received"] == 0
        assert stats["errors"] == 0

    async def test_stats_increment_ohlc(
        self, ws_client: KrakenWebSocketClient
    ) -> None:
        """Test that OHLC stats are incremented when candle completes.

        Kraken WS doesn't notify candle completion - we detect it when a NEW
        candle starts (candle_start changes). So we need 2 OHLC updates:
        - First update: starts tracking first candle
        - Second update with new candle_start: marks first as complete
        """
        # First candle (15:51:00 - 15:52:00)
        ohlc_data_1 = [
            "1548111060.000000",  # 2019-01-21 22:51:00
            "1548111120.000000",  # 2019-01-21 22:52:00
            "3586.70000",
            "3586.70000",
            "3586.60000",
            "3586.60000",
            "3586.68894",
            "0.03373000",
            "2",
        ]

        # Second candle (15:52:00 - 15:53:00) - this triggers completion of first
        ohlc_data_2 = [
            "1548111120.000000",  # 2019-01-21 22:52:00 (start of new candle)
            "1548111180.000000",  # 2019-01-21 22:53:00
            "3587.00000",
            "3587.50000",
            "3586.80000",
            "3587.20000",
            "3587.00000",
            "0.05000000",
            "3",
        ]

        await ws_client._handle_ohlc_data("XBT/EUR", ohlc_data_1, "ohlc-15")
        assert ws_client._stats["ohlc_received"] == 0  # First candle not complete yet

        await ws_client._handle_ohlc_data("XBT/EUR", ohlc_data_2, "ohlc-15")
        assert ws_client._stats["ohlc_received"] == 1  # First candle now complete

    async def test_stats_increment_ticks(
        self, ws_client: KrakenWebSocketClient
    ) -> None:
        """Test that tick stats are incremented."""
        ticker_data = {
            "a": ["5525.40000", "1", "1.000"],
            "b": ["5525.10000", "1", "1.000"],
            "c": ["5525.10000", "0.00398963"],
        }

        await ws_client._handle_ticker_data("XBT/EUR", ticker_data)

        assert ws_client._stats["ticks_received"] == 1


class TestKrakenWebSocketClientDataParsing:
    """Tests for data parsing edge cases."""

    async def test_parse_ohlc_with_missing_fields(
        self, ws_client: KrakenWebSocketClient
    ) -> None:
        """Test parsing OHLC with minimum fields (no vwap, no trades_count)."""
        # First candle with minimum required fields
        ohlc_data_1 = [
            "1548111060.000000",
            "1548111120.000000",
            "3586.70000",
            "3586.70000",
            "3586.60000",
            "3586.60000",
            "",  # Empty vwap
            "0.03373000",
        ]

        # Second candle triggers completion of first
        ohlc_data_2 = [
            "1548111120.000000",  # New candle start
            "1548111180.000000",
            "3587.00000",
            "3587.00000",
            "3587.00000",
            "3587.00000",
            "",
            "0.01000000",
        ]

        # Should handle gracefully
        initial_ohlc = ws_client._stats["ohlc_received"]
        await ws_client._handle_ohlc_data("XBT/EUR", ohlc_data_1, "ohlc-15")
        await ws_client._handle_ohlc_data("XBT/EUR", ohlc_data_2, "ohlc-15")
        assert ws_client._stats["ohlc_received"] == initial_ohlc + 1

    async def test_parse_invalid_ohlc_data(
        self, ws_client: KrakenWebSocketClient
    ) -> None:
        """Test parsing invalid OHLC data."""
        # Invalid data format
        ohlc_data = ["not", "enough", "fields"]

        initial_errors = ws_client._stats["errors"]
        await ws_client._handle_ohlc_data("XBT/EUR", ohlc_data, "ohlc-15")
        assert ws_client._stats["errors"] > initial_errors

    async def test_parse_ticker_with_missing_optional_fields(
        self, ws_client: KrakenWebSocketClient
    ) -> None:
        """Test parsing ticker with minimum required fields."""
        ticker_data = {
            "c": ["5525.10000", "0.00398963"],
        }

        initial_ticks = ws_client._stats["ticks_received"]
        await ws_client._handle_ticker_data("XBT/EUR", ticker_data)
        assert ws_client._stats["ticks_received"] == initial_ticks + 1


class TestKrakenWebSocketClientPairMapping:
    """Tests for pair name mapping."""

    async def test_btc_eur_maps_to_xbt_eur(
        self, ws_client: KrakenWebSocketClient
    ) -> None:
        """Test that BTC/EUR maps to XBT/EUR."""
        # Mock connection
        ws_client._connected = True
        ws_client._ws = AsyncMock()
        ws_client._ws.closed = False  # Required for is_connected property
        ws_client._ws.send_json = AsyncMock()

        await ws_client.subscribe_ohlc("BTC/EUR", interval=15)

        # Check the sent message uses XBT/EUR
        call_args = ws_client._ws.send_json.call_args[0][0]
        assert call_args["pair"] == ["XBT/EUR"]

    async def test_unknown_pair_passes_through(
        self, ws_client: KrakenWebSocketClient
    ) -> None:
        """Test that unknown pairs pass through unchanged."""
        ws_client._connected = True
        ws_client._ws = AsyncMock()
        ws_client._ws.closed = False  # Required for is_connected property
        ws_client._ws.send_json = AsyncMock()

        await ws_client.subscribe_ohlc("UNKNOWN/PAIR", interval=15)

        call_args = ws_client._ws.send_json.call_args[0][0]
        assert call_args["pair"] == ["UNKNOWN/PAIR"]
