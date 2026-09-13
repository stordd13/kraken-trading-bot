"""Binance WebSocket client for real-time market data.

Connects to Binance's public WebSocket API using dynamic SUBSCRIBE
on the ``/ws`` endpoint.  Supports kline (OHLC) and ticker streams.

Features:
    - Dynamic stream subscription / unsubscription
    - Preventive reconnection at 23 h (Binance disconnects at 24 h)
    - Anti-zombie data-flow watchdog with Telegram alerts
    - Exponential-backoff reconnection (max 300 s, 10 attempts)
    - Event format compatible with KrakenWebSocketClient

Example:
    >>> from krakenbot.connectors.binance.ws import BinanceWebSocketClient
    >>> client = BinanceWebSocketClient(settings, event_bus)
    >>> await client.connect()
    >>> await client.subscribe_ohlc("BTC/USDC", 5)
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

from krakenbot.connectors.base_ws import BaseWebSocketClient
from krakenbot.core.event_bus import EventType
from krakenbot.core.exceptions import DataValidationError, WebSocketConnectionError
from krakenbot.core.logger import get_logger
from krakenbot.models.market_data import OHLCData

if TYPE_CHECKING:
    from aiohttp import ClientWebSocketResponse

    from krakenbot.config.settings import Settings
    from krakenbot.core.database import DatabaseManager
    from krakenbot.core.event_bus import EventBus
    from krakenbot.notifications.telegram import TelegramNotifier

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# Interval mapping: minutes ↔ Binance kline interval string
# ---------------------------------------------------------------------------
INTERVAL_MAP: dict[int, str] = {
    1: "1m",
    5: "5m",
    15: "15m",
    30: "30m",
    60: "1h",
    240: "4h",
    1440: "1d",
    10080: "1w",
}

BINANCE_INTERVAL_MAP: dict[str, int] = {v: k for k, v in INTERVAL_MAP.items()}

# Known quote currencies for symbol → pair conversion
_QUOTE_CURRENCIES = ("USDC", "USDT", "BUSD", "EUR", "USD")

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _pair_to_symbol(pair: str) -> str:
    """Convert ``'BTC/USDC'`` → ``'btcusdc'`` for WS stream names."""
    return pair.replace("/", "").lower()


def _symbol_to_pair(symbol: str) -> str:
    """Convert ``'BTCUSDC'`` → ``'BTC/USDC'`` for EventBus events."""
    upper = symbol.upper()
    for quote in _QUOTE_CURRENCIES:
        if upper.endswith(quote):
            base = upper[: -len(quote)]
            return f"{base}/{quote}"
    return upper


# ---------------------------------------------------------------------------
# BinanceWebSocketClient
# ---------------------------------------------------------------------------


class BinanceWebSocketClient(BaseWebSocketClient):
    """Binance WebSocket client using dynamic stream subscription.

    Connects to ``wss://stream.binance.com:9443/ws``, then sends
    ``SUBSCRIBE`` messages for each desired stream.  Handles automatic
    reconnection, preventive 23 h reconnect (Binance disconnects at
    24 h), and zombie detection with optional Telegram alerts.
    """

    _PREVENTIVE_RECONNECT_SECONDS: int = 23 * 3600  # 23 hours

    def __init__(
        self,
        settings: Settings,
        event_bus: EventBus,
        db_manager: DatabaseManager | None = None,
        telegram_notifier: TelegramNotifier | None = None,
    ) -> None:
        super().__init__(settings, event_bus, db_manager=db_manager)
        self._telegram_notifier = telegram_notifier

        # WebSocket state
        self._ws: ClientWebSocketResponse | None = None
        self._session: aiohttp.ClientSession | None = None

        # Subscription tracking  (key → metadata dict)
        self._subscriptions: dict[str, dict[str, Any]] = {}

        # Preventive reconnect task
        self._preventive_reconnect_task: asyncio.Task[None] | None = None
        self._connection_start_time: datetime | None = None

        # Anti-zombie flag (one alert per episode)
        self._zombie_alert_sent: bool = False

        # Auto-incrementing request id for SUBSCRIBE / UNSUBSCRIBE
        self._request_id: int = 0

        logger.info(
            "binance_ws_initialized",
            base_url=self._settings.binance.ws_url,
        )

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def is_connected(self) -> bool:
        return self._connected and self._ws is not None and not self._ws.closed

    # ------------------------------------------------------------------
    # Connection lifecycle
    # ------------------------------------------------------------------

    async def connect(self) -> None:  # noqa: C901
        """Establish WebSocket connection and start background tasks."""
        if self._running:
            logger.warning("binance_ws_already_running")
            return

        ws_url = f"{self._settings.binance.ws_url}/ws"
        logger.info("binance_ws_connecting", url=ws_url)

        try:
            self._session = aiohttp.ClientSession()
            self._ws = await self._session.ws_connect(
                ws_url,
                heartbeat=20.0,
                receive_timeout=90.0,
            )

            self._connected = True
            self._running = True
            self._last_message_time = datetime.now(UTC)
            self._connection_start_time = datetime.now(UTC)
            self._reconnect_count = 0

            logger.info("binance_ws_connected")

            # Start background tasks
            self._message_task = asyncio.create_task(self._message_loop())
            self._heartbeat_task = asyncio.create_task(self._heartbeat_monitor())
            self._data_flow_task = asyncio.create_task(self._data_flow_watchdog())
            self._preventive_reconnect_task = asyncio.create_task(
                self._preventive_reconnect_timer()
            )

            await self._event_bus.publish(
                EventType.BOT_STARTED,
                {"component": "binance_ws", "url": ws_url},
            )

        except Exception as e:
            await self._cleanup()
            logger.error("binance_ws_connection_failed", error=str(e), url=ws_url)
            raise WebSocketConnectionError(
                message=f"Failed to connect to Binance WebSocket: {e}",
                url=ws_url,
            ) from e

    async def close(self) -> None:
        """Gracefully close the WebSocket connection."""
        logger.info("binance_ws_closing")
        self._running = False

        for task in (
            self._heartbeat_task,
            self._data_flow_task,
            self._preventive_reconnect_task,
            self._message_task,
        ):
            if task and not task.done():
                task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await task

        await self._cleanup()
        logger.info("binance_ws_closed")

    # ------------------------------------------------------------------
    # Subscription
    # ------------------------------------------------------------------

    async def subscribe_ohlc(self, pair: str, interval: int) -> None:
        """Subscribe to OHLC kline stream for *pair* at *interval* minutes."""
        if interval not in INTERVAL_MAP:
            raise DataValidationError(
                message=f"Invalid OHLC interval for Binance: {interval}",
                details={
                    "field": "interval",
                    "expected": str(sorted(INTERVAL_MAP.keys())),
                    "received": str(interval),
                },
            )

        symbol = _pair_to_symbol(pair)
        tf = INTERVAL_MAP[interval]
        stream_name = f"{symbol}@kline_{tf}"

        sub_key = f"ohlc-{pair}-{interval}"
        self._subscriptions[sub_key] = {
            "type": "ohlc",
            "pair": pair,
            "interval": interval,
            "stream": stream_name,
        }

        if self.is_connected:
            await self._send_subscribe([stream_name])

        logger.info(
            "binance_ws_subscribe_ohlc",
            pair=pair,
            interval=interval,
            stream=stream_name,
        )

    async def subscribe_ticker(self, pair: str) -> None:
        """Subscribe to 24 h ticker stream for *pair*."""
        symbol = _pair_to_symbol(pair)
        stream_name = f"{symbol}@ticker"

        sub_key = f"ticker-{pair}"
        self._subscriptions[sub_key] = {
            "type": "ticker",
            "pair": pair,
            "stream": stream_name,
        }

        if self.is_connected:
            await self._send_subscribe([stream_name])

        logger.info(
            "binance_ws_subscribe_ticker",
            pair=pair,
            stream=stream_name,
        )

    async def unsubscribe_ohlc(self, pair: str, interval: int) -> None:
        """Unsubscribe from OHLC kline stream."""
        tf = INTERVAL_MAP.get(interval)
        if tf is None:
            return

        symbol = _pair_to_symbol(pair)
        stream_name = f"{symbol}@kline_{tf}"
        sub_key = f"ohlc-{pair}-{interval}"
        self._subscriptions.pop(sub_key, None)

        if self.is_connected:
            await self._send_unsubscribe([stream_name])

        logger.info(
            "binance_ws_unsubscribe_ohlc",
            pair=pair,
            interval=interval,
        )

    # ------------------------------------------------------------------
    # Message loop
    # ------------------------------------------------------------------

    async def _message_loop(self) -> None:
        """Receive messages and dispatch to handlers."""
        while self._running and self._ws and not self._ws.closed:
            try:
                msg = await self._ws.receive()
                self._last_message_time = datetime.now(UTC)

                if msg.type == aiohttp.WSMsgType.TEXT:
                    self._stats["messages_received"] += 1
                    await self._handle_message(msg.data)

                elif msg.type == aiohttp.WSMsgType.CLOSED:
                    logger.warning(
                        "binance_ws_connection_closed",
                        close_code=self._ws.close_code if self._ws else None,
                    )
                    self._connected = False
                    if self._running:
                        asyncio.create_task(self._reconnect())
                    break

                elif msg.type == aiohttp.WSMsgType.ERROR:
                    logger.error(
                        "binance_ws_error",
                        error=str(self._ws.exception() if self._ws else "unknown"),
                    )
                    self._connected = False
                    if self._running:
                        asyncio.create_task(self._reconnect())
                    break

            except asyncio.CancelledError:
                break
            except TimeoutError:
                logger.warning("binance_ws_receive_timeout")
                if self._running:
                    asyncio.create_task(self._reconnect())
                break
            except Exception as e:
                logger.error(
                    "binance_ws_message_loop_error",
                    error=str(e),
                    error_type=type(e).__name__,
                )
                self._stats["errors"] += 1
                if self._running:
                    asyncio.create_task(self._reconnect())
                break

    # ------------------------------------------------------------------
    # Message handling
    # ------------------------------------------------------------------

    async def _handle_message(self, raw_data: str) -> None:
        """Parse and route an incoming WebSocket message."""
        try:
            data = json.loads(raw_data)

            # Subscribe / unsubscribe response
            if isinstance(data, dict) and "id" in data:
                result = data.get("result")
                if result is not None:
                    logger.warning(
                        "binance_ws_request_error",
                        id=data["id"],
                        result=result,
                    )
                else:
                    logger.debug("binance_ws_request_ok", id=data["id"])
                return

            # Combined-stream wrapper: {"stream": "...", "data": {...}}
            if isinstance(data, dict) and "stream" in data:
                event_data = data["data"]
            else:
                event_data = data

            if not isinstance(event_data, dict):
                return

            event_type = event_data.get("e")
            if event_type == "kline":
                await self._handle_kline(event_data)
            elif event_type == "24hrTicker":
                await self._handle_ticker(event_data)
            else:
                logger.debug("binance_ws_unknown_event", event_type=event_type)

        except json.JSONDecodeError as e:
            logger.error(
                "binance_ws_json_decode_error",
                error=str(e),
                data=raw_data[:200],
            )
            self._stats["errors"] += 1
        except Exception as e:
            logger.error(
                "binance_ws_handle_message_error",
                error=str(e),
                error_type=type(e).__name__,
            )
            self._stats["errors"] += 1

    async def _handle_kline(self, data: dict[str, Any]) -> None:
        """Handle a kline (OHLC candle) event.

        Publishes to ``MARKET_OHLC`` with the same dict format as
        ``KrakenWebSocketClient`` so that downstream strategies work
        without changes.
        """
        try:
            k = data["k"]
            pair = _symbol_to_pair(k["s"])

            interval_str: str = k["i"]
            interval = BINANCE_INTERVAL_MAP.get(interval_str)
            if interval is None:
                logger.warning(
                    "binance_ws_unknown_interval",
                    interval=interval_str,
                )
                return

            is_closed: bool = k["x"]

            # Use candle close time + 1 ms as the period-end timestamp
            # (Binance "T" is the last ms of the candle window)
            candle_end_ms: int = k["T"] + 1
            timestamp = datetime.fromtimestamp(candle_end_ms / 1000, tz=UTC)

            ohlc_event: dict[str, Any] = {
                "pair": pair,
                "interval": interval,
                "timestamp": timestamp.isoformat(),
                "is_complete": is_closed,
                "open": k["o"],
                "high": k["h"],
                "low": k["l"],
                "close": k["c"],
                "volume": k["v"],
                "vwap": None,  # Binance klines do not include VWAP
                "trades_count": k.get("n"),
            }

            await self._event_bus.publish(EventType.MARKET_OHLC, ohlc_event)

            if is_closed:
                self._stats["ohlc_received"] += 1

                # Persist completed candle to DB (no-op if db_manager is None)
                ohlc = OHLCData(
                    timestamp=timestamp,
                    pair=pair,
                    interval=interval,
                    exchange="binance",
                    open=Decimal(k["o"]),
                    high=Decimal(k["h"]),
                    low=Decimal(k["l"]),
                    close=Decimal(k["c"]),
                    volume=Decimal(k["v"]),
                    vwap=None,
                    trades_count=k.get("n"),
                )
                await self._save_ohlc(ohlc)

                logger.info(
                    "binance_ws_ohlc_complete",
                    pair=pair,
                    interval=interval,
                    close=k["c"],
                    candle_timestamp=timestamp.isoformat(),
                )
            else:
                logger.debug(
                    "binance_ws_ohlc_update",
                    pair=pair,
                    interval=interval,
                    close=k["c"],
                )

        except (KeyError, ValueError, TypeError) as e:
            logger.error(
                "binance_ws_kline_parse_error",
                error=str(e),
                data=str(data)[:200],
            )
            self._stats["errors"] += 1

    async def _handle_ticker(self, data: dict[str, Any]) -> None:
        """Handle a 24 h ticker event."""
        try:
            pair = _symbol_to_pair(data["s"])
            self._stats["ticks_received"] += 1

            await self._event_bus.publish(
                EventType.MARKET_TICK,
                {
                    "pair": pair,
                    "last": data.get("c"),  # last price
                    "bid": data.get("b"),
                    "ask": data.get("a"),
                    "volume": data.get("v"),
                },
            )
        except (KeyError, ValueError) as e:
            logger.error("binance_ws_ticker_parse_error", error=str(e))
            self._stats["errors"] += 1

    # ------------------------------------------------------------------
    # OHLC persistence
    # ------------------------------------------------------------------

    async def _save_ohlc(self, ohlc: OHLCData) -> None:
        """Save OHLC data to database if db_manager is available.

        When the collector creates this client it passes *db_manager* so
        completed candles are persisted.  The trader passes ``None`` to
        avoid double-writes (the collector already handles persistence).
        """
        if self._db_manager is None:
            return
        try:
            async with self._db_manager.session() as session:
                await session.merge(ohlc)
        except Exception as e:
            logger.error(
                "binance_ws_ohlc_save_error",
                error=str(e),
                pair=ohlc.pair,
            )

    # ------------------------------------------------------------------
    # Heartbeat monitor
    # ------------------------------------------------------------------

    async def _heartbeat_monitor(self) -> None:
        """Check that messages are being received regularly."""
        while self._running:
            try:
                await asyncio.sleep(self._heartbeat_interval)

                if self._last_message_time is None:
                    continue

                elapsed = (datetime.now(UTC) - self._last_message_time).total_seconds()
                timeout = self._heartbeat_timeout * 3  # 30 s default

                if elapsed > timeout and self._connected:
                    logger.warning(
                        "binance_ws_heartbeat_timeout",
                        seconds_since_last=elapsed,
                        threshold=timeout,
                    )
                    if self._running:
                        asyncio.create_task(self._reconnect())
                    break

            except asyncio.CancelledError:
                break

    # ------------------------------------------------------------------
    # Anti-zombie watchdog
    # ------------------------------------------------------------------

    async def _data_flow_watchdog(self) -> None:
        """Detect zombie WebSocket and trigger reconnect + Telegram alert.

        Waits 60 s for initial data, then checks every 5 min that the
        message counter is still incrementing.
        """
        await asyncio.sleep(60)  # initial grace period

        last_count = self._stats["messages_received"]

        while self._running:
            try:
                await asyncio.sleep(300)  # check every 5 min

                current_count = self._stats["messages_received"]

                if current_count == last_count and self._connected:
                    logger.error(
                        "binance_ws_data_flow_stale",
                        last_count=last_count,
                        current_count=current_count,
                        message="No new messages in 5 minutes, forcing reconnection",
                    )

                    if not self._zombie_alert_sent:
                        await self._send_zombie_alert()
                        self._zombie_alert_sent = True

                    if self._running:
                        asyncio.create_task(self._reconnect())
                    break
                else:
                    logger.debug(
                        "binance_ws_data_flow_ok",
                        messages_delta=current_count - last_count,
                    )

                last_count = current_count

            except asyncio.CancelledError:
                break

    # ------------------------------------------------------------------
    # Preventive reconnect (Binance 24 h limit)
    # ------------------------------------------------------------------

    async def _preventive_reconnect_timer(self) -> None:
        """Force a clean reconnect at 23 h to avoid Binance's 24 h cutoff."""
        try:
            await asyncio.sleep(self._PREVENTIVE_RECONNECT_SECONDS)

            if self._running and self._connected:
                logger.info(
                    "binance_ws_preventive_reconnect",
                    connection_age_hours=23,
                    reason="avoid_24h_disconnect",
                )
                self._stats["reconnections"] += 1
                await self._force_disconnect_and_reconnect()

        except asyncio.CancelledError:
            pass

    # ------------------------------------------------------------------
    # Reconnection
    # ------------------------------------------------------------------

    async def _reconnect(self) -> None:
        """Reconnect with exponential backoff."""
        self._reconnect_count += 1
        self._stats["reconnections"] += 1

        if self._reconnect_count > self._max_reconnect_attempts:
            logger.error(
                "binance_ws_max_reconnect_attempts",
                attempts=self._reconnect_count,
            )
            await self._send_critical_alert()
            await self._event_bus.publish(
                EventType.SYSTEM_ERROR,
                {
                    "component": "binance_ws",
                    "error": "Max reconnection attempts exceeded",
                },
            )
            return

        delay = self._reconnect_delay * (2 ** (self._reconnect_count - 1))
        delay = min(delay, 300)

        logger.info(
            "binance_ws_reconnecting",
            attempt=self._reconnect_count,
            delay_seconds=delay,
        )

        await asyncio.sleep(delay)

        # Preserve subscriptions across reconnect
        saved_subscriptions = dict(self._subscriptions)
        was_zombie = self._zombie_alert_sent

        await self._cleanup()
        self._subscriptions = saved_subscriptions

        try:
            await self.connect()

            # Re-subscribe to all previous subscriptions
            for _sub_key, sub_info in saved_subscriptions.items():
                if sub_info["type"] == "ohlc":
                    await self.subscribe_ohlc(sub_info["pair"], sub_info["interval"])
                elif sub_info["type"] == "ticker":
                    await self.subscribe_ticker(sub_info["pair"])

            # Reset zombie flag and send recovery alert
            self._zombie_alert_sent = False
            if was_zombie:
                await self._send_recovery_alert()

        except Exception as e:
            logger.error(
                "binance_ws_reconnect_failed",
                error=str(e),
                attempt=self._reconnect_count,
            )
            asyncio.create_task(self._reconnect())

    async def _force_disconnect_and_reconnect(self) -> None:
        """Cleanly disconnect and trigger reconnect (used by preventive timer)."""
        saved_subscriptions = dict(self._subscriptions)
        await self._cleanup()
        self._subscriptions = saved_subscriptions

        try:
            await self.connect()

            for _sub_key, sub_info in saved_subscriptions.items():
                if sub_info["type"] == "ohlc":
                    await self.subscribe_ohlc(sub_info["pair"], sub_info["interval"])
                elif sub_info["type"] == "ticker":
                    await self.subscribe_ticker(sub_info["pair"])

        except Exception as e:
            logger.error(
                "binance_ws_preventive_reconnect_failed",
                error=str(e),
            )
            asyncio.create_task(self._reconnect())

    # ------------------------------------------------------------------
    # Telegram alerts
    # ------------------------------------------------------------------

    async def _send_zombie_alert(self) -> None:
        """Send Telegram alert when WebSocket becomes zombie."""
        notifier = self._get_telegram_notifier()
        if notifier is None:
            return
        try:
            elapsed = ""
            if self._last_message_time:
                secs = (datetime.now(UTC) - self._last_message_time).total_seconds()
                elapsed = f"No messages for <b>{int(secs)}s</b>\n"

            message = (
                "\U0001f6a8 <b>WebSocket Zombie Detected</b>\n\n"
                f"{elapsed}"
                f"Exchange: <code>{self._settings.exchange_name}</code>\n"
                "Reconnecting now\u2026\n\n"
                f"Messages received: {self._stats['messages_received']}\n"
                f"OHLC received: {self._stats['ohlc_received']}\n"
                f"Reconnections: {self._stats['reconnections']}"
            )
            await notifier.send(message)
            logger.info("binance_ws_zombie_telegram_sent")
        except Exception as e:
            logger.warning("binance_ws_telegram_alert_failed", error=str(e))

    async def _send_recovery_alert(self) -> None:
        """Send Telegram alert when WebSocket recovers from zombie state."""
        notifier = self._get_telegram_notifier()
        if notifier is None:
            return
        try:
            message = (
                "\u2705 <b>WebSocket Recovered</b>\n\n"
                f"Exchange: <code>{self._settings.exchange_name}</code>\n"
                f"Reconnection #{self._stats['reconnections']} successful"
            )
            await notifier.send(message, silent=True)
            logger.info("binance_ws_recovery_telegram_sent")
        except Exception as e:
            logger.warning("binance_ws_telegram_alert_failed", error=str(e))

    async def _send_critical_alert(self) -> None:
        """Send Telegram alert when max reconnect attempts exhausted."""
        notifier = self._get_telegram_notifier()
        if notifier is None:
            return
        try:
            message = (
                "\U0001f534 <b>CRITICAL: WebSocket Reconnect Failed</b>\n\n"
                f"Exchange: <code>{self._settings.exchange_name}</code>\n"
                f"Max attempts ({self._max_reconnect_attempts}) exceeded\n"
                "Bot may be offline!"
            )
            await notifier.send(message)
            logger.info("binance_ws_critical_telegram_sent")
        except Exception as e:
            logger.warning("binance_ws_telegram_alert_failed", error=str(e))

    def _get_telegram_notifier(self) -> TelegramNotifier | None:
        """Return the telegram notifier (explicit or singleton fallback)."""
        if self._telegram_notifier is not None:
            return self._telegram_notifier
        # Lazy fallback to global singleton
        from krakenbot.notifications.telegram import get_notifier

        return get_notifier()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _next_request_id(self) -> int:
        """Return an auto-incrementing request id."""
        self._request_id += 1
        return self._request_id

    async def _send_subscribe(self, streams: list[str]) -> None:
        """Send a SUBSCRIBE frame over the WebSocket."""
        if self._ws is None or self._ws.closed:
            return
        msg = {
            "method": "SUBSCRIBE",
            "params": streams,
            "id": self._next_request_id(),
        }
        await self._ws.send_json(msg)
        logger.debug("binance_ws_subscribe_sent", streams=streams)

    async def _send_unsubscribe(self, streams: list[str]) -> None:
        """Send an UNSUBSCRIBE frame over the WebSocket."""
        if self._ws is None or self._ws.closed:
            return
        msg = {
            "method": "UNSUBSCRIBE",
            "params": streams,
            "id": self._next_request_id(),
        }
        await self._ws.send_json(msg)
        logger.debug("binance_ws_unsubscribe_sent", streams=streams)

    async def _cleanup(self) -> None:
        """Close WebSocket and aiohttp session."""
        self._connected = False
        self._running = False

        if self._ws and not self._ws.closed:
            with contextlib.suppress(Exception):
                await self._ws.close()
        self._ws = None

        if self._session and not self._session.closed:
            with contextlib.suppress(Exception):
                await self._session.close()
        self._session = None

        # Cancel background tasks
        for task in (
            self._message_task,
            self._heartbeat_task,
            self._data_flow_task,
            self._preventive_reconnect_task,
        ):
            if task and not task.done():
                task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await task

        self._message_task = None
        self._heartbeat_task = None
        self._data_flow_task = None
        self._preventive_reconnect_task = None
