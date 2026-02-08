"""Kraken WebSocket client for real-time market data.

This module provides an async WebSocket client that connects to Kraken's
public WebSocket API for receiving real-time market data.

Supported Subscriptions:
    - OHLC candles (various intervals)
    - Ticker updates (bid/ask, last price, volume)
    - Trade feed (public trades)

Features:
    - Automatic reconnection on disconnect
    - Heartbeat monitoring
    - Rate limiting
    - Database persistence of received data
    - Event bus integration

WebSocket URLs:
    - Public: wss://ws.kraken.com
    - Private: wss://ws-auth.kraken.com (not used here)

Documentation:
    https://docs.kraken.com/websockets/

Example:
    >>> from krakenbot.connectors.kraken_ws import KrakenWebSocketClient
    >>> client = KrakenWebSocketClient(settings, event_bus, db_manager)
    >>> await client.connect()
    >>> await client.subscribe_ohlc("XBT/EUR", interval=15)
    >>> # ... client runs and receives data
    >>> await client.close()
"""

from __future__ import annotations

import asyncio
import contextlib
from datetime import UTC, datetime
from decimal import Decimal
import json
from typing import TYPE_CHECKING, Any

import aiohttp

from krakenbot.core.event_bus import EventBus, EventType
from krakenbot.core.exceptions import (
    DataValidationError,
    WebSocketConnectionError,
    WebSocketDisconnectedError,
)
from krakenbot.core.logger import get_logger
from krakenbot.models.base import TradeSide
from krakenbot.models.market_data import OHLCData, TickData

if TYPE_CHECKING:
    from aiohttp import ClientWebSocketResponse

    from krakenbot.config.settings import Settings
    from krakenbot.core.database import DatabaseManager

logger = get_logger(__name__)


# Kraken WebSocket API valid OHLC intervals (in minutes)
VALID_OHLC_INTERVALS = {1, 5, 15, 30, 60, 240, 1440, 10080, 21600}

# Kraken pair name mapping (some pairs use different names in WebSocket)
PAIR_MAPPING = {
    "XBT/EUR": "XBT/EUR",
    "BTC/EUR": "XBT/EUR",
    "XBT/USD": "XBT/USD",
    "BTC/USD": "XBT/USD",
    "XBT/USDC": "XBT/USDC",
    "BTC/USDC": "XBT/USDC",
    "ETH/EUR": "ETH/EUR",
    "ETH/USD": "ETH/USD",
}


class KrakenWebSocketClient:
    """Async WebSocket client for Kraken public market data.

    This client connects to Kraken's public WebSocket API and provides
    real-time market data streaming. It handles connection management,
    automatic reconnection, and data persistence.

    Attributes:
        settings: Application settings.
        event_bus: Event bus for publishing events.
        db_manager: Database manager for data persistence.

    Example:
        >>> client = KrakenWebSocketClient(settings, event_bus, db_manager)
        >>> await client.connect()
        >>> await client.subscribe_ohlc("XBT/EUR", interval=15)
        >>> await client.subscribe_ticker("XBT/EUR")
        >>> # Client runs in background
        >>> await client.close()
    """

    def __init__(
        self,
        settings: Settings,
        event_bus: EventBus,
        db_manager: DatabaseManager,
    ) -> None:
        """Initialize the WebSocket client.

        Args:
            settings: Application settings.
            event_bus: Event bus for publishing events.
            db_manager: Database manager for data persistence.
        """
        self._settings = settings
        self._event_bus = event_bus
        self._db_manager = db_manager

        # WebSocket state
        self._ws: ClientWebSocketResponse | None = None
        self._session: aiohttp.ClientSession | None = None
        self._running = False
        self._connected = False

        # Subscription tracking
        self._subscriptions: dict[str, dict[str, Any]] = {}
        self._channel_ids: dict[int, dict[str, Any]] = {}

        # OHLC candle tracking for completion detection
        # Kraken WS doesn't notify when a candle completes - it just sends updates
        # We detect completion by tracking when candle_start changes (new candle started)
        self._last_candle_start: dict[str, datetime] = {}  # key = "pair-interval"
        self._last_candle_data: dict[str, dict[str, Any]] = {}  # Store last candle for completion

        # Reconnection settings
        self._reconnect_delay = settings.kraken.ws_reconnect_delay_sec
        self._max_reconnect_attempts = 10
        self._reconnect_count = 0

        # Heartbeat settings
        self._heartbeat_interval = 30.0  # seconds
        self._heartbeat_timeout = 10.0  # seconds
        self._last_message_time: datetime | None = None

        # Background tasks
        self._message_task: asyncio.Task[None] | None = None
        self._heartbeat_task: asyncio.Task[None] | None = None
        self._data_flow_task: asyncio.Task[None] | None = None

        # Statistics
        self._stats = {
            "messages_received": 0,
            "ohlc_received": 0,
            "ticks_received": 0,
            "errors": 0,
            "reconnections": 0,
        }

    @property
    def is_connected(self) -> bool:
        """Check if WebSocket is connected.

        Returns:
            True if connected.
        """
        return self._connected and self._ws is not None and not self._ws.closed

    @property
    def stats(self) -> dict[str, int]:
        """Get client statistics.

        Returns:
            Dictionary of statistics.
        """
        return self._stats.copy()

    async def connect(self) -> None:
        """Connect to Kraken WebSocket.

        Establishes a WebSocket connection and starts the message
        handling loop.

        Raises:
            WebSocketConnectionError: If connection fails.
        """
        if self._running:
            logger.warning("kraken_ws_already_running")
            return

        logger.info(
            "kraken_ws_connecting",
            url=self._settings.kraken.ws_url,
        )

        try:
            # Create aiohttp session
            self._session = aiohttp.ClientSession()

            # Connect to WebSocket
            self._ws = await self._session.ws_connect(
                self._settings.kraken.ws_url,
                heartbeat=self._heartbeat_interval,
                receive_timeout=self._heartbeat_timeout * 3,
            )

            self._connected = True
            self._running = True
            self._last_message_time = datetime.now(UTC)
            self._reconnect_count = 0

            logger.info("kraken_ws_connected")

            # Start message handling loop
            self._message_task = asyncio.create_task(self._message_loop())

            # Start heartbeat monitoring
            self._heartbeat_task = asyncio.create_task(self._heartbeat_monitor())

            # Start data flow watchdog (detects zombie connections)
            self._data_flow_task = asyncio.create_task(self._data_flow_watchdog())

            # Publish connection event
            await self._event_bus.publish(
                EventType.BOT_STARTED,
                {"component": "kraken_ws", "url": self._settings.kraken.ws_url},
            )

        except Exception as e:
            await self._cleanup()
            logger.error(
                "kraken_ws_connection_failed",
                error=str(e),
                url=self._settings.kraken.ws_url,
            )
            raise WebSocketConnectionError(
                message=f"Failed to connect to Kraken WebSocket: {e}",
                url=self._settings.kraken.ws_url,
            ) from e

    async def close(self) -> None:
        """Close WebSocket connection gracefully.

        Sends unsubscribe messages and closes the connection cleanly.
        """
        logger.info("kraken_ws_closing")
        self._running = False

        # Cancel background tasks
        if self._heartbeat_task and not self._heartbeat_task.done():
            self._heartbeat_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._heartbeat_task

        if self._data_flow_task and not self._data_flow_task.done():
            self._data_flow_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._data_flow_task

        if self._message_task and not self._message_task.done():
            self._message_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._message_task

        await self._cleanup()

        # Publish disconnection event
        await self._event_bus.publish(
            EventType.BOT_STOPPED,
            {"component": "kraken_ws"},
        )

        logger.info("kraken_ws_closed")

    async def _cleanup(self) -> None:
        """Clean up resources."""
        self._connected = False

        if self._ws and not self._ws.closed:
            await self._ws.close()
        self._ws = None

        if self._session and not self._session.closed:
            await self._session.close()
        self._session = None

        self._subscriptions.clear()
        self._channel_ids.clear()
        self._last_candle_start.clear()
        self._last_candle_data.clear()

    async def _reconnect(self) -> None:
        """Attempt to reconnect to WebSocket.

        Implements exponential backoff for reconnection attempts.
        """
        self._reconnect_count += 1
        self._stats["reconnections"] += 1

        if self._reconnect_count > self._max_reconnect_attempts:
            logger.error(
                "kraken_ws_max_reconnect_attempts",
                attempts=self._reconnect_count,
            )
            await self._event_bus.publish(
                EventType.SYSTEM_ERROR,
                {
                    "component": "kraken_ws",
                    "error": "Max reconnection attempts exceeded",
                },
            )
            return

        # Exponential backoff
        delay = self._reconnect_delay * (2 ** (self._reconnect_count - 1))
        delay = min(delay, 300)  # Max 5 minutes

        logger.info(
            "kraken_ws_reconnecting",
            attempt=self._reconnect_count,
            delay_seconds=delay,
        )

        await asyncio.sleep(delay)

        # Clean up and reconnect
        await self._cleanup()

        try:
            await self.connect()

            # Re-subscribe to all previous subscriptions
            for _sub_key, sub_info in list(self._subscriptions.items()):
                if sub_info["type"] == "ohlc":
                    await self.subscribe_ohlc(
                        sub_info["pair"],
                        sub_info["interval"],
                    )
                elif sub_info["type"] == "ticker":
                    await self.subscribe_ticker(sub_info["pair"])
                elif sub_info["type"] == "trade":
                    await self.subscribe_trades(sub_info["pair"])

        except Exception as e:
            logger.error(
                "kraken_ws_reconnect_failed",
                error=str(e),
                attempt=self._reconnect_count,
            )
            # Schedule another reconnection attempt
            asyncio.create_task(self._reconnect())

    async def _message_loop(self) -> None:
        """Main message handling loop.

        Receives messages from WebSocket and dispatches them to handlers.
        """
        while self._running and self._ws and not self._ws.closed:
            try:
                msg = await self._ws.receive()
                self._last_message_time = datetime.now(UTC)

                if msg.type == aiohttp.WSMsgType.TEXT:
                    self._stats["messages_received"] += 1
                    await self._handle_message(msg.data)

                elif msg.type == aiohttp.WSMsgType.CLOSED:
                    logger.warning(
                        "kraken_ws_connection_closed",
                        close_code=self._ws.close_code,
                    )
                    self._connected = False
                    if self._running:
                        asyncio.create_task(self._reconnect())
                    break

                elif msg.type == aiohttp.WSMsgType.ERROR:
                    logger.error(
                        "kraken_ws_error",
                        error=str(self._ws.exception()),
                    )
                    self._connected = False
                    if self._running:
                        asyncio.create_task(self._reconnect())
                    break

            except asyncio.CancelledError:
                break
            except TimeoutError:
                logger.warning("kraken_ws_receive_timeout")
                if self._running:
                    asyncio.create_task(self._reconnect())
                break
            except Exception as e:
                logger.error(
                    "kraken_ws_message_loop_error",
                    error=str(e),
                    error_type=type(e).__name__,
                )
                self._stats["errors"] += 1
                if self._running:
                    asyncio.create_task(self._reconnect())
                break

    async def _heartbeat_monitor(self) -> None:
        """Monitor connection health via heartbeat.

        Checks that messages are being received regularly.
        """
        while self._running:
            try:
                await asyncio.sleep(self._heartbeat_interval)

                if not self._last_message_time:
                    continue

                elapsed = (datetime.now(UTC) - self._last_message_time).total_seconds()

                if elapsed > self._heartbeat_timeout * 3:
                    logger.warning(
                        "kraken_ws_heartbeat_timeout",
                        elapsed_seconds=elapsed,
                    )
                    if self._running:
                        asyncio.create_task(self._reconnect())
                    break

            except asyncio.CancelledError:
                break

    async def _data_flow_watchdog(self) -> None:
        """Monitor that data is actually flowing (detect zombie connections).

        This watchdog checks every 5 minutes that the message counter is
        increasing. If no new messages are received, it forces a reconnection.
        This catches "zombie" connections where the WebSocket appears connected
        but is not receiving any data.
        """
        # Wait for initial connection to stabilize
        await asyncio.sleep(60)

        last_count = self._stats["messages_received"]

        while self._running:
            try:
                # Check every 5 minutes
                await asyncio.sleep(300)

                current_count = self._stats["messages_received"]

                if current_count == last_count and self._connected:
                    logger.warning(
                        "kraken_ws_data_flow_stale",
                        last_count=last_count,
                        current_count=current_count,
                        message="No new messages in 5 minutes, forcing reconnection",
                    )
                    if self._running:
                        asyncio.create_task(self._reconnect())
                    break
                else:
                    logger.debug(
                        "kraken_ws_data_flow_ok",
                        messages_delta=current_count - last_count,
                    )

                last_count = current_count

            except asyncio.CancelledError:
                break

    async def _handle_message(self, raw_data: str) -> None:
        """Process incoming WebSocket message.

        Args:
            raw_data: Raw JSON message string.
        """
        try:
            data = json.loads(raw_data)

            # Handle different message types
            if isinstance(data, dict):
                await self._handle_system_message(data)
            elif isinstance(data, list):
                await self._handle_data_message(data)

        except json.JSONDecodeError as e:
            logger.error(
                "kraken_ws_json_decode_error",
                error=str(e),
                data=raw_data[:200],
            )
            self._stats["errors"] += 1
        except Exception as e:
            logger.error(
                "kraken_ws_handle_message_error",
                error=str(e),
                error_type=type(e).__name__,
            )
            self._stats["errors"] += 1

    async def _handle_system_message(self, data: dict[str, Any]) -> None:
        """Handle system/control messages.

        Args:
            data: Parsed message dictionary.
        """
        event = data.get("event")

        if event == "systemStatus":
            logger.info(
                "kraken_ws_system_status",
                status=data.get("status"),
                version=data.get("version"),
            )

        elif event == "subscriptionStatus":
            await self._handle_subscription_status(data)

        elif event == "heartbeat":
            logger.debug("kraken_ws_heartbeat")

        elif event == "pong":
            logger.debug("kraken_ws_pong")

        elif event == "error":
            logger.error(
                "kraken_ws_api_error",
                error_message=data.get("errorMessage"),
                error_type=data.get("errorMessage"),
            )
            self._stats["errors"] += 1

    async def _handle_subscription_status(self, data: dict[str, Any]) -> None:
        """Handle subscription status messages.

        Args:
            data: Subscription status data.
        """
        status = data.get("status")
        channel_id = data.get("channelID")
        pair = data.get("pair")
        subscription = data.get("subscription", {})
        sub_name = subscription.get("name")

        if status == "subscribed":
            logger.info(
                "kraken_ws_subscribed",
                channel_id=channel_id,
                pair=pair,
                subscription=sub_name,
            )
            # Store channel mapping
            if channel_id is not None:
                self._channel_ids[channel_id] = {
                    "pair": pair,
                    "type": sub_name,
                    "subscription": subscription,
                }

        elif status == "unsubscribed":
            logger.info(
                "kraken_ws_unsubscribed",
                channel_id=channel_id,
                pair=pair,
            )
            if channel_id in self._channel_ids:
                del self._channel_ids[channel_id]

        elif status == "error":
            logger.error(
                "kraken_ws_subscription_error",
                error=data.get("errorMessage"),
                pair=pair,
            )

    async def _handle_data_message(self, data: list[Any]) -> None:
        """Handle data messages (OHLC, ticker, trades).

        Args:
            data: Array message from WebSocket.
        """
        # Format: [channelID, data, channelName, pair]
        if len(data) < 4:
            logger.warning(
                "kraken_ws_invalid_data_message",
                data=str(data)[:200],
            )
            return

        data[0]
        payload = data[1]
        channel_name = data[2]
        pair = data[3]

        # Route to appropriate handler
        if channel_name.startswith("ohlc"):
            await self._handle_ohlc_data(pair, payload, channel_name)
        elif channel_name == "ticker":
            await self._handle_ticker_data(pair, payload)
        elif channel_name == "trade":
            await self._handle_trade_data(pair, payload)
        else:
            logger.debug(
                "kraken_ws_unknown_channel",
                channel_name=channel_name,
            )

    async def _handle_ohlc_data(
        self,
        pair: str,
        data: list[str],
        channel_name: str,
    ) -> None:
        """Handle OHLC candle data.

        Kraken WebSocket sends OHLC updates on every trade during the candle.
        It does NOT send a notification when a candle completes.

        We detect candle completion by tracking when candle_start changes,
        which means a new candle has started and the previous one is complete.

        Args:
            pair: Trading pair.
            data: OHLC data array.
            channel_name: Channel name (e.g., "ohlc-15").
        """
        try:
            # Parse interval from channel name (e.g., "ohlc-15" -> 15)
            interval = int(channel_name.split("-")[1])

            # Parse OHLC data
            # Format: [time, etime, open, high, low, close, vwap, volume, count]
            # time = candle start time, etime = candle end time
            candle_start = datetime.fromtimestamp(float(data[0]), tz=UTC)
            candle_end = datetime.fromtimestamp(float(data[1]), tz=UTC)

            # Tracking key for this pair/interval combination
            key = f"{pair}-{interval}"

            # Create OHLC object for event
            ohlc = OHLCData(
                timestamp=candle_start,
                pair=pair,
                interval=interval,
                open=Decimal(data[2]),
                high=Decimal(data[3]),
                low=Decimal(data[4]),
                close=Decimal(data[5]),
                vwap=Decimal(data[6]) if data[6] else None,
                volume=Decimal(data[7]),
                trades_count=int(data[8]) if len(data) > 8 else None,
            )

            # Detect candle transition: if candle_start changed, previous candle is complete
            if key in self._last_candle_start:
                if candle_start > self._last_candle_start[key]:
                    # New candle started! The PREVIOUS candle is now complete.
                    if key in self._last_candle_data:
                        prev_data = self._last_candle_data[key]

                        # Save completed candle to database
                        prev_ohlc = OHLCData(
                            timestamp=prev_data["timestamp"],
                            pair=prev_data["pair"],
                            interval=prev_data["interval"],
                            open=Decimal(prev_data["open"]),
                            high=Decimal(prev_data["high"]),
                            low=Decimal(prev_data["low"]),
                            close=Decimal(prev_data["close"]),
                            vwap=Decimal(prev_data["vwap"]) if prev_data["vwap"] else None,
                            volume=Decimal(prev_data["volume"]),
                            trades_count=prev_data["trades_count"],
                        )
                        await self._save_ohlc(prev_ohlc)
                        self._stats["ohlc_received"] += 1

                        logger.info(
                            "kraken_ws_ohlc_complete",
                            pair=pair,
                            interval=interval,
                            close=prev_data["close"],
                            candle_start=prev_data["timestamp"].isoformat(),
                        )

                        # Publish COMPLETED candle event
                        await self._event_bus.publish(
                            EventType.MARKET_OHLC,
                            {
                                "pair": prev_data["pair"],
                                "interval": prev_data["interval"],
                                "timestamp": prev_data["timestamp"].isoformat(),
                                "candle_end": prev_data["candle_end"].isoformat(),
                                "is_complete": True,
                                "open": prev_data["open"],
                                "high": prev_data["high"],
                                "low": prev_data["low"],
                                "close": prev_data["close"],
                                "volume": prev_data["volume"],
                                "vwap": prev_data["vwap"],
                                "trades_count": prev_data["trades_count"],
                            },
                        )

            # Update tracking with current candle data
            self._last_candle_start[key] = candle_start
            self._last_candle_data[key] = {
                "timestamp": candle_start,
                "candle_end": candle_end,
                "pair": pair,
                "interval": interval,
                "open": str(ohlc.open),
                "high": str(ohlc.high),
                "low": str(ohlc.low),
                "close": str(ohlc.close),
                "volume": str(ohlc.volume),
                "vwap": str(ohlc.vwap) if ohlc.vwap else None,
                "trades_count": ohlc.trades_count,
            }

            # Always publish IN-PROGRESS candle for live price tracking
            logger.debug(
                "kraken_ws_ohlc_update",
                pair=pair,
                interval=interval,
                close=str(ohlc.close),
                candle_end=candle_end.isoformat(),
            )

            await self._event_bus.publish(
                EventType.MARKET_OHLC,
                {
                    "pair": pair,
                    "interval": interval,
                    "timestamp": candle_start.isoformat(),
                    "candle_end": candle_end.isoformat(),
                    "is_complete": False,  # Current candle is always in-progress
                    "open": str(ohlc.open),
                    "high": str(ohlc.high),
                    "low": str(ohlc.low),
                    "close": str(ohlc.close),
                    "volume": str(ohlc.volume),
                    "vwap": str(ohlc.vwap) if ohlc.vwap else None,
                    "trades_count": ohlc.trades_count,
                },
            )

        except (IndexError, ValueError) as e:
            logger.error(
                "kraken_ws_ohlc_parse_error",
                error=str(e),
                pair=pair,
                data=str(data)[:200],
            )
            self._stats["errors"] += 1

    async def _handle_ticker_data(
        self,
        pair: str,
        data: dict[str, Any],
    ) -> None:
        """Handle ticker (price) updates.

        Args:
            pair: Trading pair.
            data: Ticker data dictionary.
        """
        try:
            # Parse ticker data
            # c: last trade closed [price, lot volume]
            last_price = Decimal(data["c"][0])
            last_volume = Decimal(data["c"][1])

            # Create tick data
            tick = TickData(
                timestamp=datetime.now(UTC),
                pair=pair,
                sequence=0,  # Will be updated in save
                price=last_price,
                volume=last_volume,
                side=TradeSide.BUY,  # Unknown from ticker, default to buy
            )

            # Save to database
            await self._save_tick(tick)
            self._stats["ticks_received"] += 1

            # Publish event
            await self._event_bus.publish(
                EventType.MARKET_TICK,
                {
                    "pair": pair,
                    "timestamp": tick.timestamp.isoformat(),
                    "price": str(last_price),
                    "volume": str(last_volume),
                    "bid": str(Decimal(data["b"][0])) if "b" in data else None,
                    "ask": str(Decimal(data["a"][0])) if "a" in data else None,
                    "vwap_today": str(Decimal(data["p"][1])) if "p" in data else None,
                    "volume_today": str(Decimal(data["v"][1])) if "v" in data else None,
                },
            )

            logger.debug(
                "kraken_ws_ticker_received",
                pair=pair,
                price=str(last_price),
            )

        except (KeyError, IndexError, ValueError) as e:
            logger.error(
                "kraken_ws_ticker_parse_error",
                error=str(e),
                pair=pair,
            )
            self._stats["errors"] += 1

    async def _handle_trade_data(
        self,
        pair: str,
        data: list[list[str]],
    ) -> None:
        """Handle public trade data.

        Args:
            pair: Trading pair.
            data: Array of trades.
        """
        try:
            for i, trade in enumerate(data):
                # Format: [price, volume, time, side, orderType, misc]
                price = Decimal(trade[0])
                volume = Decimal(trade[1])
                timestamp = datetime.fromtimestamp(float(trade[2]), tz=UTC)
                side = TradeSide.BUY if trade[3] == "b" else TradeSide.SELL

                tick = TickData(
                    timestamp=timestamp,
                    pair=pair,
                    sequence=i,
                    price=price,
                    volume=volume,
                    side=side,
                )

                # Save to database
                await self._save_tick(tick)
                self._stats["ticks_received"] += 1

                # Publish event
                await self._event_bus.publish(
                    EventType.MARKET_TICK,
                    {
                        "pair": pair,
                        "timestamp": timestamp.isoformat(),
                        "price": str(price),
                        "volume": str(volume),
                        "side": side.value,
                    },
                )

            logger.debug(
                "kraken_ws_trades_received",
                pair=pair,
                count=len(data),
            )

        except (IndexError, ValueError) as e:
            logger.error(
                "kraken_ws_trade_parse_error",
                error=str(e),
                pair=pair,
            )
            self._stats["errors"] += 1

    async def _save_ohlc(self, ohlc: OHLCData) -> None:
        """Save OHLC data to database.

        Args:
            ohlc: OHLC data to save.
        """
        try:
            async with self._db_manager.session() as session:
                # Use merge to handle duplicates (same timestamp, pair, interval)
                await session.merge(ohlc)
        except Exception as e:
            logger.error(
                "kraken_ws_ohlc_save_error",
                error=str(e),
                pair=ohlc.pair,
            )

    async def _save_tick(self, tick: TickData) -> None:
        """Save tick data to database.

        Args:
            tick: Tick data to save.
        """
        try:
            async with self._db_manager.session() as session:
                # Handle sequence for duplicate timestamps
                # Use merge to handle duplicates
                await session.merge(tick)
        except Exception as e:
            logger.error(
                "kraken_ws_tick_save_error",
                error=str(e),
                pair=tick.pair,
            )

    async def _send_message(self, message: dict[str, Any]) -> None:
        """Send a message to the WebSocket.

        Args:
            message: Message to send.

        Raises:
            WebSocketDisconnectedError: If not connected.
        """
        if not self.is_connected:
            raise WebSocketDisconnectedError("WebSocket is not connected")

        await self._ws.send_json(message)  # type: ignore[union-attr]

    async def subscribe_ohlc(self, pair: str, interval: int = 15) -> None:
        """Subscribe to OHLC candle data.

        Args:
            pair: Trading pair (e.g., "XBT/EUR").
            interval: Candle interval in minutes.
                      Valid values: 1, 5, 15, 30, 60, 240, 1440, 10080, 21600

        Raises:
            DataValidationError: If interval is invalid.
            WebSocketDisconnectedError: If not connected.
        """
        if interval not in VALID_OHLC_INTERVALS:
            raise DataValidationError(
                message=f"Invalid OHLC interval: {interval}",
                field="interval",
                expected=str(VALID_OHLC_INTERVALS),
                received=str(interval),
            )

        # Map pair name if needed
        ws_pair = PAIR_MAPPING.get(pair, pair)

        message = {
            "event": "subscribe",
            "pair": [ws_pair],
            "subscription": {
                "name": "ohlc",
                "interval": interval,
            },
        }

        await self._send_message(message)

        # Track subscription
        sub_key = f"ohlc-{ws_pair}-{interval}"
        self._subscriptions[sub_key] = {
            "type": "ohlc",
            "pair": ws_pair,
            "interval": interval,
        }

        logger.info(
            "kraken_ws_subscribe_ohlc",
            pair=ws_pair,
            interval=interval,
        )

    async def subscribe_ticker(self, pair: str) -> None:
        """Subscribe to ticker (price) updates.

        Args:
            pair: Trading pair (e.g., "XBT/EUR").

        Raises:
            WebSocketDisconnectedError: If not connected.
        """
        ws_pair = PAIR_MAPPING.get(pair, pair)

        message = {
            "event": "subscribe",
            "pair": [ws_pair],
            "subscription": {
                "name": "ticker",
            },
        }

        await self._send_message(message)

        sub_key = f"ticker-{ws_pair}"
        self._subscriptions[sub_key] = {
            "type": "ticker",
            "pair": ws_pair,
        }

        logger.info(
            "kraken_ws_subscribe_ticker",
            pair=ws_pair,
        )

    async def subscribe_trades(self, pair: str) -> None:
        """Subscribe to public trade feed.

        Args:
            pair: Trading pair (e.g., "XBT/EUR").

        Raises:
            WebSocketDisconnectedError: If not connected.
        """
        ws_pair = PAIR_MAPPING.get(pair, pair)

        message = {
            "event": "subscribe",
            "pair": [ws_pair],
            "subscription": {
                "name": "trade",
            },
        }

        await self._send_message(message)

        sub_key = f"trade-{ws_pair}"
        self._subscriptions[sub_key] = {
            "type": "trade",
            "pair": ws_pair,
        }

        logger.info(
            "kraken_ws_subscribe_trades",
            pair=ws_pair,
        )

    async def unsubscribe_ohlc(self, pair: str, interval: int = 15) -> None:
        """Unsubscribe from OHLC candle data.

        Args:
            pair: Trading pair.
            interval: Candle interval in minutes.
        """
        ws_pair = PAIR_MAPPING.get(pair, pair)

        message = {
            "event": "unsubscribe",
            "pair": [ws_pair],
            "subscription": {
                "name": "ohlc",
                "interval": interval,
            },
        }

        await self._send_message(message)

        sub_key = f"ohlc-{ws_pair}-{interval}"
        self._subscriptions.pop(sub_key, None)

        logger.info(
            "kraken_ws_unsubscribe_ohlc",
            pair=ws_pair,
            interval=interval,
        )

    async def unsubscribe_ticker(self, pair: str) -> None:
        """Unsubscribe from ticker updates.

        Args:
            pair: Trading pair.
        """
        ws_pair = PAIR_MAPPING.get(pair, pair)

        message = {
            "event": "unsubscribe",
            "pair": [ws_pair],
            "subscription": {
                "name": "ticker",
            },
        }

        await self._send_message(message)

        sub_key = f"ticker-{ws_pair}"
        self._subscriptions.pop(sub_key, None)

        logger.info(
            "kraken_ws_unsubscribe_ticker",
            pair=ws_pair,
        )

    async def unsubscribe_trades(self, pair: str) -> None:
        """Unsubscribe from trade feed.

        Args:
            pair: Trading pair.
        """
        ws_pair = PAIR_MAPPING.get(pair, pair)

        message = {
            "event": "unsubscribe",
            "pair": [ws_pair],
            "subscription": {
                "name": "trade",
            },
        }

        await self._send_message(message)

        sub_key = f"trade-{ws_pair}"
        self._subscriptions.pop(sub_key, None)

        logger.info(
            "kraken_ws_unsubscribe_trades",
            pair=ws_pair,
        )

    async def ping(self) -> None:
        """Send ping message to check connection.

        Raises:
            WebSocketDisconnectedError: If not connected.
        """
        await self._send_message({"event": "ping"})
        logger.debug("kraken_ws_ping_sent")
