"""Bybit EU WebSocket client for real-time market data (public spot, v5).

Connects to ``wss://stream.bybit.eu/v5/public/spot`` and subscribes to
``kline.{interval}.{SYMBOL}`` / ``tickers.{SYMBOL}`` topics (max 10 args per
subscribe request, see ``skills/bybit.md``).  Structural clone of
``connectors/binance/ws.py`` with three Bybit-specific differences:

1. **Application-level ping** ``{"op": "ping"}`` every 20 s.  The pong comes
   back as ``{"op": "ping", "ret_msg": "pong"}``.  A missing pong within 10 s is
   the ONE signal of a zombie connection (forced reconnect + Telegram alert).
   Both values are ``BybitSettings.ws_ping_interval_seconds`` /
   ``ws_pong_timeout_seconds`` (env ``BYBIT_WS_*``).
2. **Sparse data flow.** Bybit only pushes a kline message when a trade happens
   (~31 klines + 22 tickers / 5 min on ONE pair on the EU instance, less at
   night).  The data-flow watchdog therefore looks at the AGGREGATE topic flow
   (all klines + tickers, pongs excluded) with two configurable thresholds
   (``BybitSettings.ws_watchdog_*``):

   - ``warn`` (default 10 min): quiet market OR lost subscriptions — the client
     logs a warning and re-sends its subscriptions (idempotent on Bybit: a
     duplicate subscribe yields no ack and no duplicate stream).  No reconnect,
     no Telegram — unless it happens ``resubscribe_alert_count`` times in 24 h.
   - ``zombie`` (default 30 min): connection alive (pongs OK) but no data at
     all — Telegram alert + forced reconnect.
3. **Kline format**: ``data[0]`` with ``start``/``end`` in ms, ``end``
   inclusive → DB timestamp = ``end + 1 ms`` (= ``start + interval``, same
   convention as Binance ``T + 1``).  ``confirm: true`` = closed candle.
   ``volume`` in base, ``turnover`` in quote → ``vwap = turnover / volume``.
   No trade count.  Flat candles (``volume = 0``) are valid and persisted.

The preventive 23 h reconnect of the Binance client is kept (no documented
24 h cutoff on Bybit, but harmless).

Example:
    >>> from krakenbot.connectors.bybit.ws import BybitWebSocketClient
    >>> client = BybitWebSocketClient(settings, event_bus)
    >>> await client.connect()
    >>> await client.subscribe_ohlc("BTC/USDC", 5)
    >>> await client.close()
"""

from __future__ import annotations

import asyncio
from collections import deque
import contextlib
from datetime import UTC, datetime, timedelta
from decimal import Decimal, InvalidOperation
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
# Interval mapping: minutes ↔ Bybit kline interval string
# ---------------------------------------------------------------------------
INTERVAL_MAP: dict[int, str] = {
    1: "1",
    5: "5",
    15: "15",
    60: "60",
    240: "240",
    1440: "D",
    10080: "W",
}

BYBIT_INTERVAL_MAP: dict[str, int] = {v: k for k, v in INTERVAL_MAP.items()}

#: Bybit v5 spot: max ``args`` per subscribe / unsubscribe request.
MAX_ARGS_PER_REQUEST: int = 10

#: Quote currencies listed on bybit.eu (for symbol → pair conversion).
_QUOTE_CURRENCIES = ("USDC", "USDT", "EUR", "PLN", "USD")

_VWAP_QUANT = Decimal("0.00000001")  # DECIMAL(18, 8) column


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _pair_to_symbol(pair: str) -> str:
    """Convert ``'BTC/USDC'`` → ``'BTCUSDC'`` (Bybit topic symbol)."""
    return pair.replace("/", "").upper()


def _symbol_to_pair(symbol: str) -> str:
    """Convert ``'BTCUSDC'`` → ``'BTC/USDC'`` for EventBus events."""
    upper = symbol.upper()
    for quote in _QUOTE_CURRENCIES:
        if upper.endswith(quote) and len(upper) > len(quote):
            return f"{upper[: -len(quote)]}/{quote}"
    return upper


def _chunk(items: list[str], size: int) -> list[list[str]]:
    """Split *items* into consecutive lists of at most *size* elements."""
    return [items[i : i + size] for i in range(0, len(items), size)]


def _ms_to_datetime(ms: int) -> datetime:
    """Exact ms → aware UTC datetime (no float rounding)."""
    return datetime.fromtimestamp(ms // 1000, tz=UTC) + timedelta(milliseconds=ms % 1000)


# ---------------------------------------------------------------------------
# BybitWebSocketClient
# ---------------------------------------------------------------------------


class BybitWebSocketClient(BaseWebSocketClient):
    """Bybit EU public spot WebSocket client (kline + ticker topics).

    Single connection, dynamic subscribe in chunks of 10 args, application
    ping every 20 s, two-stage aggregate data-flow watchdog, preventive 23 h
    reconnect and exponential-backoff reconnection with Telegram alerts.
    """

    _PREVENTIVE_RECONNECT_SECONDS: int = 23 * 3600
    _RECEIVE_TIMEOUT_SECONDS: float = 60.0
    _WATCHDOG_GRACE_SECONDS: int = 60
    _WATCHDOG_CHECK_SECONDS: int = 60
    _WATCHDOG_STATS_EVERY_CHECKS: int = 5  # INFO flow stats every 5 min
    _RESUBSCRIBE_WINDOW: timedelta = timedelta(hours=24)

    def __init__(
        self,
        settings: Settings,
        event_bus: EventBus,
        db_manager: DatabaseManager | None = None,
        telegram_notifier: TelegramNotifier | None = None,
    ) -> None:
        super().__init__(settings, event_bus, db_manager=db_manager)
        self._telegram_notifier = telegram_notifier

        # Liveness parameters (BYBIT_WS_PING_INTERVAL_SECONDS / BYBIT_WS_PONG_TIMEOUT_SECONDS)
        self._PING_INTERVAL_SECONDS: float = float(settings.bybit.ws_ping_interval_seconds)
        self._PONG_TIMEOUT_SECONDS: float = float(settings.bybit.ws_pong_timeout_seconds)

        # WebSocket state
        self._ws: ClientWebSocketResponse | None = None
        self._session: aiohttp.ClientSession | None = None

        # Subscription tracking  (key → metadata dict)
        self._subscriptions: dict[str, dict[str, Any]] = {}

        # Preventive reconnect task
        self._preventive_reconnect_task: asyncio.Task[None] | None = None
        self._connection_start_time: datetime | None = None

        # Liveness: application ping/pong + aggregate topic flow
        self._last_pong_time: datetime | None = None
        self._last_topic_message_time: datetime | None = None

        # Watchdog state
        self._stale_resubscribed: bool = False
        self._resubscribe_events: deque[datetime] = deque()
        self._resubscribe_storm_alert_sent: bool = False

        # Anti-zombie flag (one alert per episode)
        self._zombie_alert_sent: bool = False

        # Set by close(): a pending backoff reconnect must not resurrect the client
        self._closing: bool = False

        # Auto-incrementing request id (req_id) for subscribe / ping
        self._request_id: int = 0

        self._stats.update({"topic_messages": 0, "pongs_received": 0, "resubscribes": 0})

        bybit = self._settings.bybit
        logger.info(
            "bybit_ws_initialized",
            ws_url=bybit.ws_url,
            ping_interval_seconds=bybit.ws_ping_interval_seconds,
            pong_timeout_seconds=bybit.ws_pong_timeout_seconds,
            watchdog_warn_seconds=bybit.ws_watchdog_warn_seconds,
            watchdog_zombie_seconds=bybit.ws_watchdog_zombie_seconds,
            resubscribe_alert_count=bybit.ws_watchdog_resubscribe_alert_count,
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

    async def connect(self) -> None:
        """Establish WebSocket connection and start background tasks."""
        if self._running:
            logger.warning("bybit_ws_already_running")
            return

        self._closing = False
        ws_url = self._settings.bybit.ws_url
        logger.info("bybit_ws_connecting", url=ws_url)

        try:
            self._session = aiohttp.ClientSession()
            # heartbeat=None: the application-level {"op":"ping"} is the single
            # liveness mechanism (no competing protocol-level ping).
            self._ws = await self._session.ws_connect(
                ws_url,
                heartbeat=None,
                receive_timeout=self._RECEIVE_TIMEOUT_SECONDS,
            )

            now = datetime.now(UTC)
            self._connected = True
            self._running = True
            self._last_message_time = now
            self._connection_start_time = now
            self._last_pong_time = None
            self._last_topic_message_time = None
            self._stale_resubscribed = False
            self._reconnect_count = 0

            logger.info("bybit_ws_connected")

            self._message_task = asyncio.create_task(self._message_loop())
            self._heartbeat_task = asyncio.create_task(self._ping_loop())
            self._data_flow_task = asyncio.create_task(self._data_flow_watchdog())
            self._preventive_reconnect_task = asyncio.create_task(
                self._preventive_reconnect_timer()
            )

            await self._event_bus.publish(
                EventType.BOT_STARTED,
                {"component": "bybit_ws", "url": ws_url},
            )

        except Exception as e:
            await self._cleanup()
            logger.error("bybit_ws_connection_failed", error=str(e), url=ws_url)
            raise WebSocketConnectionError(
                message=f"Failed to connect to Bybit WebSocket: {e}",
                url=ws_url,
            ) from e

    async def close(self) -> None:
        """Gracefully close the WebSocket connection."""
        logger.info("bybit_ws_closing")
        self._closing = True
        self._running = False
        await self._cleanup()
        logger.info("bybit_ws_closed")

    # ------------------------------------------------------------------
    # Subscription
    # ------------------------------------------------------------------

    async def subscribe_ohlc(self, pair: str, interval: int) -> None:
        """Subscribe to the kline topic for *pair* at *interval* minutes."""
        if interval not in INTERVAL_MAP:
            raise DataValidationError(
                message=f"Invalid OHLC interval for Bybit: {interval}",
                details={
                    "field": "interval",
                    "expected": str(sorted(INTERVAL_MAP.keys())),
                    "received": str(interval),
                },
            )

        topic = f"kline.{INTERVAL_MAP[interval]}.{_pair_to_symbol(pair)}"
        sub_key = f"ohlc-{pair}-{interval}"
        self._subscriptions[sub_key] = {
            "type": "ohlc",
            "pair": pair,
            "interval": interval,
            "topic": topic,
        }

        if self.is_connected:
            await self._send_subscribe([topic])

        logger.info("bybit_ws_subscribe_ohlc", pair=pair, interval=interval, topic=topic)

    async def subscribe_ticker(self, pair: str) -> None:
        """Subscribe to the spot ticker topic for *pair*."""
        topic = f"tickers.{_pair_to_symbol(pair)}"
        sub_key = f"ticker-{pair}"
        self._subscriptions[sub_key] = {"type": "ticker", "pair": pair, "topic": topic}

        if self.is_connected:
            await self._send_subscribe([topic])

        logger.info("bybit_ws_subscribe_ticker", pair=pair, topic=topic)

    async def unsubscribe_ohlc(self, pair: str, interval: int) -> None:
        """Unsubscribe from the kline topic."""
        tf = INTERVAL_MAP.get(interval)
        if tf is None:
            return

        topic = f"kline.{tf}.{_pair_to_symbol(pair)}"
        self._subscriptions.pop(f"ohlc-{pair}-{interval}", None)

        if self.is_connected:
            await self._send_unsubscribe([topic])

        logger.info("bybit_ws_unsubscribe_ohlc", pair=pair, interval=interval)

    def _subscribed_topics(self) -> list[str]:
        """All currently tracked topics (klines first, then tickers), deduplicated."""
        return list(dict.fromkeys(sub["topic"] for sub in self._subscriptions.values()))

    async def _resubscribe_all(self) -> None:
        """Re-send every tracked subscription in chunks of 10 args.

        Idempotent on Bybit: a duplicate subscribe returns no ack and does not
        duplicate the stream (verified in the B0 audit).
        """
        topics = self._subscribed_topics()
        if not topics:
            return
        await self._send_subscribe(topics)
        logger.info(
            "bybit_ws_resubscribed",
            topics=len(topics),
            requests=len(_chunk(topics, MAX_ARGS_PER_REQUEST)),
        )

    # ------------------------------------------------------------------
    # Message loop
    # ------------------------------------------------------------------

    async def _message_loop(self) -> None:
        """Receive frames and dispatch to handlers."""
        while self._running and self._ws and not self._ws.closed:
            try:
                msg = await self._ws.receive()
                self._last_message_time = datetime.now(UTC)

                if msg.type == aiohttp.WSMsgType.TEXT:
                    self._stats["messages_received"] += 1
                    await self._handle_message(msg.data)

                elif msg.type == aiohttp.WSMsgType.CLOSED:
                    logger.warning(
                        "bybit_ws_connection_closed",
                        close_code=self._ws.close_code if self._ws else None,
                    )
                    self._connected = False
                    if self._running:
                        asyncio.create_task(self._reconnect())
                    break

                elif msg.type == aiohttp.WSMsgType.ERROR:
                    logger.error(
                        "bybit_ws_error",
                        error=str(self._ws.exception() if self._ws else "unknown"),
                    )
                    self._connected = False
                    if self._running:
                        asyncio.create_task(self._reconnect())
                    break

            except asyncio.CancelledError:
                break
            except TimeoutError:
                logger.warning(
                    "bybit_ws_receive_timeout",
                    timeout_seconds=self._RECEIVE_TIMEOUT_SECONDS,
                )
                if self._running:
                    asyncio.create_task(self._reconnect())
                break
            except Exception as e:
                logger.error(
                    "bybit_ws_message_loop_error",
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
        """Parse and route an incoming frame.

        Routing order: pong → subscribe/unsubscribe ack → ``kline.*`` →
        ``tickers.*``.  Only topic messages count as market data flow.
        """
        try:
            data = json.loads(raw_data)
            if not isinstance(data, dict):
                return

            topic = data.get("topic")
            if topic is None:
                self._handle_control_message(data)
                return

            self._last_topic_message_time = datetime.now(UTC)
            self._stats["topic_messages"] += 1
            self._stale_resubscribed = False

            if topic.startswith("kline."):
                payload = data.get("data") or []
                for candle in payload:
                    await self._handle_kline(topic, candle)
            elif topic.startswith("tickers."):
                await self._handle_ticker(topic, data.get("data") or {}, data.get("ts"))
            else:
                logger.debug("bybit_ws_unknown_topic", topic=topic)

        except json.JSONDecodeError as e:
            logger.error("bybit_ws_json_decode_error", error=str(e), data=raw_data[:200])
            self._stats["errors"] += 1
        except Exception as e:
            logger.error(
                "bybit_ws_handle_message_error",
                error=str(e),
                error_type=type(e).__name__,
            )
            self._stats["errors"] += 1

    def _handle_control_message(self, data: dict[str, Any]) -> None:
        """Handle frames without ``topic``: pong and subscribe/unsubscribe acks."""
        op = data.get("op")
        ret_msg = data.get("ret_msg")

        if ret_msg == "pong" or op == "pong":
            self._last_pong_time = datetime.now(UTC)
            self._stats["pongs_received"] += 1
            logger.debug("bybit_ws_pong", req_id=data.get("req_id"))
            return

        if op in ("subscribe", "unsubscribe"):
            if data.get("success", True):
                logger.debug("bybit_ws_request_ok", op=op, req_id=data.get("req_id"))
            else:
                logger.warning(
                    "bybit_ws_request_error",
                    op=op,
                    req_id=data.get("req_id"),
                    ret_msg=ret_msg,
                )
            return

        logger.debug("bybit_ws_unknown_control_message", op=op, ret_msg=ret_msg)

    async def _handle_kline(self, topic: str, k: dict[str, Any]) -> None:
        """Handle one kline entry of a ``kline.{tf}.{SYMBOL}`` message.

        Publishes ``MARKET_OHLC`` with the same dict format as the Binance and
        Kraken clients; persists the candle when ``confirm`` is true.
        """
        try:
            _, topic_tf, symbol = topic.split(".", 2)
            pair = _symbol_to_pair(symbol)

            interval_str = str(k.get("interval", topic_tf))
            interval = BYBIT_INTERVAL_MAP.get(interval_str)
            if interval is None:
                logger.warning("bybit_ws_unknown_interval", interval=interval_str, topic=topic)
                return

            is_closed = bool(k["confirm"])

            # `end` is the last inclusive ms of the candle → period-end = end + 1 ms
            timestamp = _ms_to_datetime(int(k["end"]) + 1)

            volume = Decimal(str(k["volume"]))
            turnover = Decimal(str(k.get("turnover", "0")))
            vwap: Decimal | None = None
            if volume > 0:
                vwap = (turnover / volume).quantize(_VWAP_QUANT)

            ohlc_event: dict[str, Any] = {
                "pair": pair,
                "interval": interval,
                "timestamp": timestamp.isoformat(),
                "is_complete": is_closed,
                "open": str(k["open"]),
                "high": str(k["high"]),
                "low": str(k["low"]),
                "close": str(k["close"]),
                "volume": str(k["volume"]),
                "vwap": str(vwap) if vwap is not None else None,
                "trades_count": None,  # not provided by Bybit klines
            }

            await self._event_bus.publish(EventType.MARKET_OHLC, ohlc_event)

            if is_closed:
                self._stats["ohlc_received"] += 1

                ohlc = OHLCData(
                    timestamp=timestamp,
                    pair=pair,
                    interval=interval,
                    exchange="bybit",
                    open=Decimal(str(k["open"])),
                    high=Decimal(str(k["high"])),
                    low=Decimal(str(k["low"])),
                    close=Decimal(str(k["close"])),
                    volume=volume,  # 0 = flat candle, still persisted
                    vwap=vwap,
                    trades_count=None,
                )
                await self._save_ohlc(ohlc)

                logger.info(
                    "bybit_ws_ohlc_complete",
                    pair=pair,
                    interval=interval,
                    close=str(k["close"]),
                    volume=str(volume),
                    candle_timestamp=timestamp.isoformat(),
                )
            else:
                logger.debug(
                    "bybit_ws_ohlc_update",
                    pair=pair,
                    interval=interval,
                    close=str(k["close"]),
                )

        except (KeyError, ValueError, TypeError, InvalidOperation) as e:
            logger.error(
                "bybit_ws_kline_parse_error",
                error=str(e),
                topic=topic,
                data=str(k)[:200],
            )
            self._stats["errors"] += 1

    async def _handle_ticker(self, topic: str, data: dict[str, Any], ts: int | None) -> None:
        """Handle a ``tickers.{SYMBOL}`` snapshot.

        The Bybit v5 *spot* ticker has no best bid/ask (``bid``/``ask`` are
        published as ``None``).  Nothing downstream reads them from this event
        (strategies read ``price``; REST ``get_ticker`` carries bid/ask).
        ``price`` is the Kraken-compatible key consumed by strategies; ``last``
        mirrors the Binance client.
        """
        try:
            symbol = data.get("symbol") or topic.split(".", 1)[1]
            pair = _symbol_to_pair(symbol)
            last_price = data.get("lastPrice")
            self._stats["ticks_received"] += 1

            await self._event_bus.publish(
                EventType.MARKET_TICK,
                {
                    "pair": pair,
                    "timestamp": _ms_to_datetime(int(ts)).isoformat() if ts else None,
                    "price": last_price,
                    "last": last_price,
                    "bid": None,
                    "ask": None,
                    "volume": data.get("volume24h"),
                },
            )
        except (KeyError, ValueError, TypeError) as e:
            logger.error("bybit_ws_ticker_parse_error", error=str(e), topic=topic)
            self._stats["errors"] += 1

    # ------------------------------------------------------------------
    # OHLC persistence
    # ------------------------------------------------------------------

    async def _save_ohlc(self, ohlc: OHLCData) -> None:
        """Persist a completed candle (no-op when *db_manager* is ``None``).

        The collector passes *db_manager*; the trader passes ``None`` to avoid
        double writes.  ``merge`` upserts on the composite PK
        (timestamp, pair, interval, exchange).
        """
        if self._db_manager is None:
            return
        try:
            async with self._db_manager.session() as session:
                await session.merge(ohlc)
        except Exception as e:
            logger.error(
                "bybit_ws_ohlc_save_error",
                error=str(e),
                pair=ohlc.pair,
                interval=ohlc.interval,
            )

    # ------------------------------------------------------------------
    # Application ping / pong (connection liveness)
    # ------------------------------------------------------------------

    async def _ping_loop(self) -> None:
        """Send ``{"op":"ping"}`` every 20 s; reconnect if no pong within 10 s.

        This is the connection-level zombie detector.  Pongs are control
        messages and do NOT count as market data flow.
        """
        while self._running:
            try:
                if not self.is_connected:
                    await asyncio.sleep(1)
                    continue

                sent_at = datetime.now(UTC)
                await self._send_ping()
                await asyncio.sleep(self._PONG_TIMEOUT_SECONDS)

                if not self._running:
                    break

                pong_missing = self._last_pong_time is None or self._last_pong_time < sent_at
                if pong_missing and self._connected:
                    logger.error(
                        "bybit_ws_pong_timeout",
                        timeout_seconds=self._PONG_TIMEOUT_SECONDS,
                        last_pong=self._last_pong_time.isoformat()
                        if self._last_pong_time
                        else None,
                        message="No pong within timeout, forcing reconnection",
                    )
                    self._stats["errors"] += 1
                    if not self._zombie_alert_sent:
                        await self._send_zombie_alert(reason="pong_timeout")
                        self._zombie_alert_sent = True
                    if self._running:
                        asyncio.create_task(self._reconnect())
                    break

                await asyncio.sleep(self._PING_INTERVAL_SECONDS - self._PONG_TIMEOUT_SECONDS)

            except asyncio.CancelledError:
                break
            except Exception as e:
                # Send failure on a closed socket: the message loop handles reconnect.
                logger.warning("bybit_ws_ping_error", error=str(e), error_type=type(e).__name__)
                break

    # ------------------------------------------------------------------
    # Aggregate data-flow watchdog (two-stage, configurable)
    # ------------------------------------------------------------------

    def _seconds_since_last_topic_message(self) -> float | None:
        """Seconds since the last kline/ticker message (or since connect)."""
        reference = self._last_topic_message_time or self._connection_start_time
        if reference is None:
            return None
        return (datetime.now(UTC) - reference).total_seconds()

    async def _data_flow_watchdog(self) -> None:
        """Detect lost subscriptions / zombie flow on the AGGREGATE topic stream.

        Bybit pushes klines only on trades, so silence is first treated as a
        quiet market (warn threshold: re-subscribe, no reconnect) and only as
        a zombie after the larger zombie threshold (Telegram + reconnect).
        Thresholds come from ``BybitSettings`` (``BYBIT_WS_WATCHDOG_*``).
        """
        await asyncio.sleep(self._WATCHDOG_GRACE_SECONDS)

        checks = 0
        last_topic_count = self._stats["topic_messages"]
        last_pong_count = self._stats["pongs_received"]

        while self._running:
            try:
                await asyncio.sleep(self._WATCHDOG_CHECK_SECONDS)
                checks += 1

                if checks % self._WATCHDOG_STATS_EVERY_CHECKS == 0:
                    logger.info(
                        "bybit_ws_data_flow_ok",
                        window_seconds=self._WATCHDOG_CHECK_SECONDS
                        * self._WATCHDOG_STATS_EVERY_CHECKS,
                        topic_messages_delta=self._stats["topic_messages"] - last_topic_count,
                        pongs_delta=self._stats["pongs_received"] - last_pong_count,
                        ohlc_received=self._stats["ohlc_received"],
                        resubscribes_24h=len(self._resubscribe_events),
                    )
                    last_topic_count = self._stats["topic_messages"]
                    last_pong_count = self._stats["pongs_received"]

                if not self._connected:
                    continue

                stale = self._seconds_since_last_topic_message()
                if stale is None:
                    continue

                bybit = self._settings.bybit
                if stale >= bybit.ws_watchdog_zombie_seconds:
                    logger.error(
                        "bybit_ws_data_flow_zombie",
                        stale_seconds=int(stale),
                        threshold=bybit.ws_watchdog_zombie_seconds,
                        pong_alive=self._pong_alive(),
                        resubscribes_24h=len(self._resubscribe_events),
                        message="Connection alive but no topic message, forcing reconnection",
                    )
                    if not self._zombie_alert_sent:
                        await self._send_zombie_alert(reason="data_flow_zombie")
                        self._zombie_alert_sent = True
                    if self._running:
                        asyncio.create_task(self._reconnect())
                    break

                if stale >= bybit.ws_watchdog_warn_seconds and not self._stale_resubscribed:
                    await self._handle_stale_flow(stale)

            except asyncio.CancelledError:
                break

    def _pong_alive(self) -> bool:
        """Whether a pong arrived within the last ping interval + timeout."""
        if self._last_pong_time is None:
            return False
        age = (datetime.now(UTC) - self._last_pong_time).total_seconds()
        return age <= self._PING_INTERVAL_SECONDS + self._PONG_TIMEOUT_SECONDS

    async def _handle_stale_flow(self, stale_seconds: float) -> None:
        """Warn-stage action: re-subscribe silently, escalate if recurring."""
        now = datetime.now(UTC)
        logger.warning(
            "bybit_ws_data_flow_stale",
            stale_seconds=int(stale_seconds),
            threshold=self._settings.bybit.ws_watchdog_warn_seconds,
            pong_alive=self._pong_alive(),
            reason="quiet_market_or_lost_subscriptions",
            action="resubscribe",
        )
        self._stale_resubscribed = True
        self._stats["resubscribes"] += 1
        self._resubscribe_events.append(now)
        self._prune_resubscribe_events(now)

        await self._resubscribe_all()

        threshold = self._settings.bybit.ws_watchdog_resubscribe_alert_count
        if len(self._resubscribe_events) >= threshold:
            if not self._resubscribe_storm_alert_sent:
                await self._send_resubscribe_storm_alert()
                self._resubscribe_storm_alert_sent = True
        else:
            self._resubscribe_storm_alert_sent = False

    def _prune_resubscribe_events(self, now: datetime) -> None:
        cutoff = now - self._RESUBSCRIBE_WINDOW
        while self._resubscribe_events and self._resubscribe_events[0] < cutoff:
            self._resubscribe_events.popleft()

    # ------------------------------------------------------------------
    # Preventive reconnect (kept from Binance, 23 h)
    # ------------------------------------------------------------------

    async def _preventive_reconnect_timer(self) -> None:
        """Force a clean reconnect at 23 h."""
        try:
            await asyncio.sleep(self._PREVENTIVE_RECONNECT_SECONDS)

            if self._running and self._connected:
                logger.info(
                    "bybit_ws_preventive_reconnect",
                    connection_age_hours=23,
                    reason="periodic_clean_reconnect",
                )
                self._stats["reconnections"] += 1
                await self._force_disconnect_and_reconnect()

        except asyncio.CancelledError:
            pass

    # ------------------------------------------------------------------
    # Reconnection
    # ------------------------------------------------------------------

    async def _reconnect(self) -> None:
        """Reconnect with exponential backoff and restore subscriptions."""
        self._reconnect_count += 1
        self._stats["reconnections"] += 1

        if self._reconnect_count > self._max_reconnect_attempts:
            logger.error("bybit_ws_max_reconnect_attempts", attempts=self._reconnect_count)
            await self._send_critical_alert()
            await self._event_bus.publish(
                EventType.SYSTEM_ERROR,
                {"component": "bybit_ws", "error": "Max reconnection attempts exceeded"},
            )
            return

        delay = min(self._reconnect_delay * (2 ** (self._reconnect_count - 1)), 300)
        logger.info(
            "bybit_ws_reconnecting",
            attempt=self._reconnect_count,
            delay_seconds=delay,
        )
        await asyncio.sleep(delay)

        if self._closing:
            logger.info("bybit_ws_reconnect_aborted", reason="client_closed")
            return

        saved_subscriptions = dict(self._subscriptions)
        was_zombie = self._zombie_alert_sent
        reconnect_count = self._reconnect_count

        await self._cleanup()
        self._subscriptions = saved_subscriptions

        try:
            await self.connect()
            await self._resubscribe_all()

            self._zombie_alert_sent = False
            if was_zombie:
                await self._send_recovery_alert()

        except Exception as e:
            logger.error("bybit_ws_reconnect_failed", error=str(e), attempt=reconnect_count)
            # connect() resets the counter only on success; restore the backoff position
            self._reconnect_count = reconnect_count
            asyncio.create_task(self._reconnect())

    async def _force_disconnect_and_reconnect(self) -> None:
        """Cleanly disconnect and reconnect immediately (preventive timer)."""
        saved_subscriptions = dict(self._subscriptions)
        await self._cleanup()
        self._subscriptions = saved_subscriptions

        try:
            await self.connect()
            await self._resubscribe_all()
        except Exception as e:
            logger.error("bybit_ws_preventive_reconnect_failed", error=str(e))
            asyncio.create_task(self._reconnect())

    # ------------------------------------------------------------------
    # Telegram alerts
    # ------------------------------------------------------------------

    async def _send_zombie_alert(self, reason: str) -> None:
        """Telegram alert for a zombie connection (pong timeout or dead flow)."""
        notifier = self._get_telegram_notifier()
        if notifier is None:
            return
        try:
            stale = self._seconds_since_last_topic_message()
            detail = (
                f"No pong from Bybit within {int(self._PONG_TIMEOUT_SECONDS)} s (connection dead)\n"
                if reason == "pong_timeout"
                else f"Connection alive (pongs OK) but no market data for <b>{int(stale or 0)}s</b>\n"
            )
            message = (
                "\U0001f6a8 <b>WebSocket Zombie Detected</b>\n\n"
                f"{detail}"
                f"Exchange: <code>{self._settings.exchange_name}</code>\n"
                f"Reason: <code>{reason}</code>\n"
                "Reconnecting now…\n\n"
                f"Topic messages: {self._stats['topic_messages']}\n"
                f"OHLC received: {self._stats['ohlc_received']}\n"
                f"Reconnections: {self._stats['reconnections']}"
            )
            await notifier.send(message)
            logger.info("bybit_ws_zombie_telegram_sent", reason=reason)
        except Exception as e:
            logger.warning("bybit_ws_telegram_alert_failed", error=str(e))

    async def _send_resubscribe_storm_alert(self) -> None:
        """Telegram alert when the warn-stage re-subscribe recurs within 24 h."""
        notifier = self._get_telegram_notifier()
        if notifier is None:
            return
        try:
            message = (
                "⚠️ <b>WebSocket: recurring re-subscribes</b>\n\n"
                f"Exchange: <code>{self._settings.exchange_name}</code>\n"
                f"{len(self._resubscribe_events)} watchdog re-subscribes in the last 24 h "
                f"(threshold {self._settings.bybit.ws_watchdog_resubscribe_alert_count})\n"
                "Connection is alive; topic flow keeps stalling "
                f"(> {self._settings.bybit.ws_watchdog_warn_seconds}s). "
                "Check network / Bybit status / logs."
            )
            await notifier.send(message)
            logger.info("bybit_ws_resubscribe_storm_telegram_sent")
        except Exception as e:
            logger.warning("bybit_ws_telegram_alert_failed", error=str(e))

    async def _send_recovery_alert(self) -> None:
        """Telegram alert when the connection recovers from a zombie episode."""
        notifier = self._get_telegram_notifier()
        if notifier is None:
            return
        try:
            message = (
                "✅ <b>WebSocket Recovered</b>\n\n"
                f"Exchange: <code>{self._settings.exchange_name}</code>\n"
                f"Reconnection #{self._stats['reconnections']} successful"
            )
            await notifier.send(message, silent=True)
            logger.info("bybit_ws_recovery_telegram_sent")
        except Exception as e:
            logger.warning("bybit_ws_telegram_alert_failed", error=str(e))

    async def _send_critical_alert(self) -> None:
        """Telegram alert when max reconnect attempts are exhausted."""
        notifier = self._get_telegram_notifier()
        if notifier is None:
            return
        try:
            message = (
                "\U0001f534 <b>CRITICAL: WebSocket Reconnect Failed</b>\n\n"
                f"Exchange: <code>{self._settings.exchange_name}</code>\n"
                f"Max attempts ({self._max_reconnect_attempts}) exceeded\n"
                "Collector / bot may be offline!"
            )
            await notifier.send(message)
            logger.info("bybit_ws_critical_telegram_sent")
        except Exception as e:
            logger.warning("bybit_ws_telegram_alert_failed", error=str(e))

    def _get_telegram_notifier(self) -> TelegramNotifier | None:
        """Return the telegram notifier (explicit or singleton fallback)."""
        if self._telegram_notifier is not None:
            return self._telegram_notifier
        from krakenbot.notifications.telegram import get_notifier

        return get_notifier()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _next_request_id(self) -> str:
        """Return an auto-incrementing ``req_id``."""
        self._request_id += 1
        return str(self._request_id)

    async def _send_op(self, op: str, topics: list[str]) -> None:
        """Send ``op`` for *topics* in chunks of ``MAX_ARGS_PER_REQUEST``."""
        if self._ws is None or self._ws.closed:
            return
        for chunk in _chunk(topics, MAX_ARGS_PER_REQUEST):
            msg = {"req_id": self._next_request_id(), "op": op, "args": chunk}
            await self._ws.send_json(msg)
            logger.debug(f"bybit_ws_{op}_sent", req_id=msg["req_id"], args=chunk)

    async def _send_subscribe(self, topics: list[str]) -> None:
        await self._send_op("subscribe", topics)

    async def _send_unsubscribe(self, topics: list[str]) -> None:
        await self._send_op("unsubscribe", topics)

    async def _send_ping(self) -> None:
        """Send the application-level ping frame."""
        if self._ws is None or self._ws.closed:
            return
        await self._ws.send_json({"req_id": self._next_request_id(), "op": "ping"})

    async def _cleanup(self) -> None:
        """Close the socket/session and cancel background tasks.

        Safe to call from inside one of the background tasks (the current
        task is never awaited on itself).
        """
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

        current = asyncio.current_task()
        for task in (
            self._message_task,
            self._heartbeat_task,
            self._data_flow_task,
            self._preventive_reconnect_task,
        ):
            if task and task is not current and not task.done():
                task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await task

        self._message_task = None
        self._heartbeat_task = None
        self._data_flow_task = None
        self._preventive_reconnect_task = None
