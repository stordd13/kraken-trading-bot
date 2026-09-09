"""Tests for the Bybit EU WebSocket client (public spot v5).

Covers: interval mapping, symbol conversion, subscribe chunking (max 10 args),
kline parsing (confirmed / unconfirmed / volume 0, ``end + 1 ms`` rule, Decimal
VWAP, ``exchange="bybit"`` persistence), ticker parsing, pong / ack handling,
application ping loop (pong timeout → reconnect), two-stage aggregate data-flow
watchdog (warn → re-subscribe, zombie → reconnect, re-subscribe storm escalation),
reconnection, preventive reconnect, factory dispatch and connection lifecycle.

IMPORTANT: the WebSocket is always mocked — no real connection to Bybit.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable, Coroutine
from datetime import UTC, datetime, timedelta
from decimal import Decimal
import json
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from krakenbot.config.settings import (
    BybitSettings,
    DatabaseSettings,
    Settings,
    TradingMode,
    TradingSettings,
)
from krakenbot.connectors.bybit.ws import (
    BYBIT_INTERVAL_MAP,
    INTERVAL_MAP,
    MAX_ARGS_PER_REQUEST,
    BybitWebSocketClient,
    _chunk,
    _pair_to_symbol,
    _symbol_to_pair,
)
from krakenbot.connectors.exchange import build_exchange_ws_client
from krakenbot.core.event_bus import EventBus, EventType, reset_event_bus
from krakenbot.core.exceptions import DataValidationError
from krakenbot.models.market_data import OHLCData

PAIRS = ["BTC/USDC", "ETH/USDC", "SOL/USDC"]
WARN_SECONDS = 600
ZOMBIE_SECONDS = 1800
STORM_COUNT = 3

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_settings() -> Settings:
    return Settings(
        app_name="KrakenBot-Test",
        environment="testing",
        exchange_name="bybit",
        bybit=BybitSettings(
            ws_watchdog_warn_seconds=WARN_SECONDS,
            ws_watchdog_zombie_seconds=ZOMBIE_SECONDS,
            ws_watchdog_resubscribe_alert_count=STORM_COUNT,
            _env_file=None,
        ),
        database=DatabaseSettings(
            url="postgresql+asyncpg://test:test@localhost:5432/krakenbot_test",
        ),
        trading=TradingSettings(mode=TradingMode.PAPER, pair="BTC/USDC"),
        _env_file=None,
    )


@pytest.fixture
def event_bus() -> EventBus:
    reset_event_bus()
    return EventBus()


@pytest.fixture
def mock_telegram() -> MagicMock:
    notifier = MagicMock()
    notifier.send = AsyncMock(return_value=True)
    notifier.send_error = AsyncMock(return_value=True)
    return notifier


@pytest.fixture
def mock_db_manager() -> MagicMock:
    manager = MagicMock()
    session = MagicMock()
    session.merge = AsyncMock()
    session_cm = MagicMock()
    session_cm.__aenter__ = AsyncMock(return_value=session)
    session_cm.__aexit__ = AsyncMock(return_value=None)
    manager.session.return_value = session_cm
    manager.merge_mock = session.merge
    return manager


@pytest.fixture
def ws_client(
    mock_settings: Settings, event_bus: EventBus, mock_telegram: MagicMock
) -> BybitWebSocketClient:
    return BybitWebSocketClient(mock_settings, event_bus, telegram_notifier=mock_telegram)


@pytest.fixture
def ws_client_db(
    mock_settings: Settings,
    event_bus: EventBus,
    mock_telegram: MagicMock,
    mock_db_manager: MagicMock,
) -> BybitWebSocketClient:
    return BybitWebSocketClient(
        mock_settings, event_bus, db_manager=mock_db_manager, telegram_notifier=mock_telegram
    )


def _attach_mock_ws(client: BybitWebSocketClient) -> AsyncMock:
    """Pretend the client is connected with a mocked socket."""
    ws = AsyncMock()
    ws.closed = False
    client._ws = ws
    client._connected = True
    client._running = True
    client._connection_start_time = datetime.now(UTC)
    return ws


def _kline_msg(
    *,
    symbol: str = "BTCUSDC",
    tf: str = "5",
    interval_min: int = 5,
    confirm: bool = True,
    start: int = 1788791400000,  # 2026-09-07 14:30:00 UTC, aligned on 5 min
    open_: str = "79050",
    high: str = "79061.3",
    low: str = "79036.9",
    close: str = "79036.9",
    volume: str = "0.773761",
    turnover: str = "61165.4975707",
) -> str:
    end = start + interval_min * 60_000 - 1  # inclusive last ms
    return json.dumps(
        {
            "type": "snapshot",
            "topic": f"kline.{tf}.{symbol}",
            "data": [
                {
                    "start": start,
                    "end": end,
                    "interval": tf,
                    "open": open_,
                    "close": close,
                    "high": high,
                    "low": low,
                    "volume": volume,
                    "turnover": turnover,
                    "confirm": confirm,
                    "timestamp": end + 155,
                }
            ],
            "ts": end + 155,
        }
    )


def _ticker_msg(symbol: str = "BTCUSDC", last: str = "79050.1", ts: int = 1788791461070) -> str:
    return json.dumps(
        {
            "topic": f"tickers.{symbol}",
            "ts": ts,
            "type": "snapshot",
            "cs": 18248946678,
            "data": {
                "symbol": symbol,
                "lastPrice": last,
                "highPrice24h": "80535",
                "lowPrice24h": "79023.3",
                "prevPrice24h": "79626.9",
                "volume24h": "38.764377",
                "turnover24h": "3087626.5845112",
                "price24hPcnt": "-0.0072",
                "usdIndexPrice": "",
            },
        }
    )


def _pong_msg(req_id: str = "7") -> str:
    return json.dumps(
        {"success": True, "ret_msg": "pong", "conn_id": "abc", "req_id": req_id, "op": "ping"}
    )


def _ack_msg(*, success: bool = True, op: str = "subscribe", ret_msg: str | None = None) -> str:
    return json.dumps(
        {
            "success": success,
            "ret_msg": ret_msg if ret_msg is not None else op,
            "conn_id": "abc",
            "req_id": "1",
            "op": op,
        }
    )


def _stop_after(
    client: BybitWebSocketClient, n: int
) -> Callable[[float], Coroutine[Any, Any, None]]:
    """Fake ``asyncio.sleep`` that stops the client loop after *n* calls."""
    calls = {"n": 0}

    async def _sleep(_seconds: float) -> None:
        calls["n"] += 1
        if calls["n"] >= n:
            client._running = False

    return _sleep


async def _subscribe_all(client: BybitWebSocketClient) -> None:
    for pair in PAIRS:
        for interval in INTERVAL_MAP:
            await client.subscribe_ohlc(pair, interval)
        await client.subscribe_ticker(pair)


# ---------------------------------------------------------------------------
# Helpers / mapping
# ---------------------------------------------------------------------------


class TestHelpers:
    def test_interval_map_matches_bybit_v5(self) -> None:
        assert INTERVAL_MAP == {
            1: "1",
            5: "5",
            15: "15",
            60: "60",
            240: "240",
            1440: "D",
            10080: "W",
        }
        assert len(BYBIT_INTERVAL_MAP) == 7
        for minutes, tf in INTERVAL_MAP.items():
            assert BYBIT_INTERVAL_MAP[tf] == minutes

    def test_pair_symbol_roundtrip(self) -> None:
        assert _pair_to_symbol("BTC/USDC") == "BTCUSDC"
        assert _pair_to_symbol("eth/usdc") == "ETHUSDC"
        assert _symbol_to_pair("BTCUSDC") == "BTC/USDC"
        assert _symbol_to_pair("SOLUSDC") == "SOL/USDC"
        assert _symbol_to_pair("BTCEUR") == "BTC/EUR"
        assert _symbol_to_pair("BTCPLN") == "BTC/PLN"
        assert _symbol_to_pair("WEIRD") == "WEIRD"

    def test_chunk_24_topics_into_3_requests(self) -> None:
        topics = [f"t{i}" for i in range(24)]
        chunks = _chunk(topics, MAX_ARGS_PER_REQUEST)
        assert [len(c) for c in chunks] == [10, 10, 4]
        assert [t for c in chunks for t in c] == topics
        assert _chunk([], 10) == []


# ---------------------------------------------------------------------------
# Init
# ---------------------------------------------------------------------------


class TestInit:
    def test_init_state(self, ws_client: BybitWebSocketClient, mock_settings: Settings) -> None:
        assert ws_client.is_connected is False
        assert ws_client._subscriptions == {}
        stats = ws_client.stats
        for key in ("messages_received", "topic_messages", "pongs_received", "resubscribes"):
            assert stats[key] == 0
        assert ws_client._settings.bybit.ws_url == "wss://stream.bybit.eu/v5/public/spot"
        assert mock_settings.bybit.ws_watchdog_warn_seconds == WARN_SECONDS


# ---------------------------------------------------------------------------
# Subscription
# ---------------------------------------------------------------------------


class TestSubscription:
    async def test_subscribe_ohlc_sends_topic(self, ws_client: BybitWebSocketClient) -> None:
        ws = _attach_mock_ws(ws_client)
        await ws_client.subscribe_ohlc("BTC/USDC", 60)
        ws.send_json.assert_awaited_once_with(
            {"req_id": "1", "op": "subscribe", "args": ["kline.60.BTCUSDC"]}
        )
        assert ws_client._subscriptions["ohlc-BTC/USDC-60"]["topic"] == "kline.60.BTCUSDC"

    async def test_subscribe_daily_and_weekly_use_letters(
        self, ws_client: BybitWebSocketClient
    ) -> None:
        ws = _attach_mock_ws(ws_client)
        await ws_client.subscribe_ohlc("ETH/USDC", 1440)
        await ws_client.subscribe_ohlc("ETH/USDC", 10080)
        sent = [c.args[0]["args"] for c in ws.send_json.await_args_list]
        assert sent == [["kline.D.ETHUSDC"], ["kline.W.ETHUSDC"]]

    async def test_subscribe_ticker_sends_topic(self, ws_client: BybitWebSocketClient) -> None:
        ws = _attach_mock_ws(ws_client)
        await ws_client.subscribe_ticker("ETH/USDC")
        ws.send_json.assert_awaited_once_with(
            {"req_id": "1", "op": "subscribe", "args": ["tickers.ETHUSDC"]}
        )

    async def test_subscribe_invalid_interval(self, ws_client: BybitWebSocketClient) -> None:
        with pytest.raises(DataValidationError):
            await ws_client.subscribe_ohlc("BTC/USDC", 7)

    async def test_subscribe_when_disconnected_is_deferred(
        self, ws_client: BybitWebSocketClient
    ) -> None:
        await ws_client.subscribe_ohlc("BTC/USDC", 5)
        assert "ohlc-BTC/USDC-5" in ws_client._subscriptions
        assert ws_client._ws is None

    async def test_resubscribe_all_chunks_by_10(self, ws_client: BybitWebSocketClient) -> None:
        await _subscribe_all(ws_client)  # disconnected: only tracked
        assert len(ws_client._subscribed_topics()) == 24

        ws = _attach_mock_ws(ws_client)
        await ws_client._resubscribe_all()

        payloads = [c.args[0] for c in ws.send_json.await_args_list]
        assert len(payloads) == 3
        assert [len(p["args"]) for p in payloads] == [10, 10, 4]
        assert all(p["op"] == "subscribe" for p in payloads)
        assert len({p["req_id"] for p in payloads}) == 3
        all_topics = [t for p in payloads for t in p["args"]]
        assert len(all_topics) == len(set(all_topics)) == 24
        assert "kline.1.SOLUSDC" in all_topics
        assert "tickers.BTCUSDC" in all_topics

    async def test_unsubscribe_ohlc(self, ws_client: BybitWebSocketClient) -> None:
        ws = _attach_mock_ws(ws_client)
        await ws_client.subscribe_ohlc("BTC/USDC", 5)
        await ws_client.unsubscribe_ohlc("BTC/USDC", 5)
        assert "ohlc-BTC/USDC-5" not in ws_client._subscriptions
        assert ws.send_json.await_args_list[-1].args[0] == {
            "req_id": "2",
            "op": "unsubscribe",
            "args": ["kline.5.BTCUSDC"],
        }


# ---------------------------------------------------------------------------
# Kline handling
# ---------------------------------------------------------------------------


class TestKlineHandling:
    async def test_confirmed_kline_publishes_and_persists(
        self, ws_client_db: BybitWebSocketClient, event_bus: EventBus, mock_db_manager: MagicMock
    ) -> None:
        received: list[dict[str, Any]] = []
        await event_bus.subscribe(EventType.MARKET_OHLC, lambda d: received.append(d))

        await ws_client_db._handle_message(_kline_msg(confirm=True))

        assert len(received) == 1
        ev = received[0]
        assert ev["pair"] == "BTC/USDC"
        assert ev["interval"] == 5
        assert ev["is_complete"] is True
        # end + 1 ms == start + interval, aligned on the 5-min grid
        ts = datetime.fromisoformat(ev["timestamp"])
        assert ts == datetime(2026, 9, 7, 14, 35, tzinfo=UTC)
        assert int(ts.timestamp()) % (5 * 60) == 0
        assert ev["close"] == "79036.9"
        assert ev["volume"] == "0.773761"
        assert ev["trades_count"] is None
        expected_vwap = (Decimal("61165.4975707") / Decimal("0.773761")).quantize(
            Decimal("0.00000001")
        )
        assert ev["vwap"] == str(expected_vwap)

        mock_db_manager.merge_mock.assert_awaited_once()
        ohlc = mock_db_manager.merge_mock.await_args.args[0]
        assert isinstance(ohlc, OHLCData)
        assert ohlc.exchange == "bybit"
        assert ohlc.pair == "BTC/USDC"
        assert ohlc.interval == 5
        assert ohlc.timestamp == ts
        assert ohlc.close == Decimal("79036.9")
        assert ohlc.volume == Decimal("0.773761")
        assert ohlc.vwap == expected_vwap
        assert ohlc.trades_count is None

        stats = ws_client_db.stats
        assert stats["ohlc_received"] == 1
        assert stats["topic_messages"] == 1
        assert ws_client_db._last_topic_message_time is not None

    async def test_unconfirmed_kline_publishes_without_persisting(
        self, ws_client_db: BybitWebSocketClient, event_bus: EventBus, mock_db_manager: MagicMock
    ) -> None:
        received: list[dict[str, Any]] = []
        await event_bus.subscribe(EventType.MARKET_OHLC, lambda d: received.append(d))

        await ws_client_db._handle_message(_kline_msg(confirm=False))

        assert len(received) == 1
        assert received[0]["is_complete"] is False
        mock_db_manager.merge_mock.assert_not_awaited()
        assert ws_client_db.stats["ohlc_received"] == 0
        assert ws_client_db.stats["topic_messages"] == 1

    async def test_flat_candle_volume_zero_is_persisted_with_null_vwap(
        self, ws_client_db: BybitWebSocketClient, event_bus: EventBus, mock_db_manager: MagicMock
    ) -> None:
        received: list[dict[str, Any]] = []
        await event_bus.subscribe(EventType.MARKET_OHLC, lambda d: received.append(d))

        await ws_client_db._handle_message(
            _kline_msg(confirm=True, volume="0", turnover="0", high="79050", low="79050")
        )

        assert received[0]["vwap"] is None
        mock_db_manager.merge_mock.assert_awaited_once()
        ohlc = mock_db_manager.merge_mock.await_args.args[0]
        assert ohlc.volume == Decimal("0")
        assert ohlc.vwap is None
        assert ws_client_db.stats["errors"] == 0

    async def test_daily_kline_maps_to_1440(
        self, ws_client: BybitWebSocketClient, event_bus: EventBus
    ) -> None:
        received: list[dict[str, Any]] = []
        await event_bus.subscribe(EventType.MARKET_OHLC, lambda d: received.append(d))
        day_start = 1788739200000  # 2026-09-07 00:00:00 UTC
        await ws_client._handle_message(
            _kline_msg(symbol="SOLUSDC", tf="D", interval_min=1440, start=day_start)
        )
        ev = received[0]
        assert ev["pair"] == "SOL/USDC"
        assert ev["interval"] == 1440
        assert datetime.fromisoformat(ev["timestamp"]) == datetime(2026, 9, 8, tzinfo=UTC)

    async def test_no_db_manager_is_noop(
        self, ws_client: BybitWebSocketClient, event_bus: EventBus
    ) -> None:
        await ws_client._handle_message(_kline_msg(confirm=True))
        assert ws_client.stats["ohlc_received"] == 1
        assert ws_client.stats["errors"] == 0

    async def test_unknown_interval_is_ignored(
        self, ws_client: BybitWebSocketClient, event_bus: EventBus
    ) -> None:
        received: list[dict[str, Any]] = []
        await event_bus.subscribe(EventType.MARKET_OHLC, lambda d: received.append(d))
        await ws_client._handle_message(_kline_msg(tf="7", interval_min=7))
        assert received == []
        assert ws_client.stats["errors"] == 0

    async def test_malformed_kline_counts_error(self, ws_client: BybitWebSocketClient) -> None:
        msg = json.loads(_kline_msg())
        del msg["data"][0]["close"]
        await ws_client._handle_message(json.dumps(msg))
        assert ws_client.stats["errors"] == 1

    async def test_db_save_error_is_logged_not_raised(
        self, ws_client_db: BybitWebSocketClient, mock_db_manager: MagicMock
    ) -> None:
        mock_db_manager.merge_mock.side_effect = RuntimeError("db down")
        await ws_client_db._handle_message(_kline_msg(confirm=True))
        assert ws_client_db.stats["ohlc_received"] == 1


# ---------------------------------------------------------------------------
# Ticker handling
# ---------------------------------------------------------------------------


class TestTickerHandling:
    async def test_ticker_publishes_market_tick(
        self, ws_client: BybitWebSocketClient, event_bus: EventBus
    ) -> None:
        received: list[dict[str, Any]] = []
        await event_bus.subscribe(EventType.MARKET_TICK, lambda d: received.append(d))

        await ws_client._handle_message(_ticker_msg(symbol="ETHUSDC", last="4321.5"))

        assert len(received) == 1
        tick = received[0]
        assert tick["pair"] == "ETH/USDC"
        assert tick["price"] == "4321.5"  # key read by strategies (Kraken contract)
        assert tick["last"] == "4321.5"
        assert tick["bid"] is None and tick["ask"] is None  # not in Bybit spot ticker
        assert tick["volume"] == "38.764377"
        assert tick["timestamp"] == "2026-09-07T14:31:01.070000+00:00"
        assert ws_client.stats["ticks_received"] == 1
        assert ws_client.stats["topic_messages"] == 1


# ---------------------------------------------------------------------------
# Control messages: pong, acks, garbage
# ---------------------------------------------------------------------------


class TestControlMessages:
    async def test_pong_is_liveness_not_market_data(
        self, ws_client: BybitWebSocketClient, event_bus: EventBus
    ) -> None:
        received: list[dict[str, Any]] = []
        await event_bus.subscribe(EventType.MARKET_OHLC, lambda d: received.append(d))
        await event_bus.subscribe(EventType.MARKET_TICK, lambda d: received.append(d))

        before = datetime.now(UTC)
        await ws_client._handle_message(_pong_msg())

        assert ws_client._last_pong_time is not None
        assert ws_client._last_pong_time >= before
        assert ws_client.stats["pongs_received"] == 1
        assert ws_client.stats["topic_messages"] == 0
        assert ws_client._last_topic_message_time is None
        assert received == []

    async def test_subscribe_ack_is_ignored(self, ws_client: BybitWebSocketClient) -> None:
        await ws_client._handle_message(_ack_msg(success=True))
        await ws_client._handle_message(_ack_msg(op="unsubscribe"))
        assert ws_client.stats["topic_messages"] == 0
        assert ws_client.stats["errors"] == 0
        assert ws_client._last_pong_time is None

    async def test_failed_ack_logs_warning_without_error_count(
        self, ws_client: BybitWebSocketClient
    ) -> None:
        with patch("krakenbot.connectors.bybit.ws.logger") as log:
            await ws_client._handle_message(_ack_msg(success=False, ret_msg="args size >10"))
        log.warning.assert_called_once()
        assert log.warning.call_args.args[0] == "bybit_ws_request_error"
        assert log.warning.call_args.kwargs["ret_msg"] == "args size >10"
        assert ws_client.stats["errors"] == 0

    async def test_invalid_json_counts_error(self, ws_client: BybitWebSocketClient) -> None:
        await ws_client._handle_message("{not json")
        assert ws_client.stats["errors"] == 1

    async def test_topic_message_resets_stale_flag(self, ws_client: BybitWebSocketClient) -> None:
        ws_client._stale_resubscribed = True
        await ws_client._handle_message(_ticker_msg())
        assert ws_client._stale_resubscribed is False


# ---------------------------------------------------------------------------
# Ping loop (connection liveness)
# ---------------------------------------------------------------------------


class TestPingLoop:
    async def test_ping_sent_and_pong_keeps_connection(
        self, ws_client: BybitWebSocketClient, mock_telegram: MagicMock
    ) -> None:
        ws = _attach_mock_ws(ws_client)
        calls = {"n": 0}

        async def fake_sleep(_seconds: float) -> None:
            calls["n"] += 1
            if calls["n"] == 1:  # pong arrives during the 10 s wait
                ws_client._last_pong_time = datetime.now(UTC)
            else:
                ws_client._running = False

        with (
            patch("asyncio.sleep", side_effect=fake_sleep),
            patch.object(ws_client, "_reconnect", new_callable=AsyncMock) as reconnect,
        ):
            await ws_client._ping_loop()
        await asyncio.sleep(0)

        ws.send_json.assert_awaited_once_with({"req_id": "1", "op": "ping"})
        reconnect.assert_not_awaited()
        mock_telegram.send.assert_not_awaited()
        assert ws_client._zombie_alert_sent is False

    async def test_missing_pong_triggers_reconnect_and_alert(
        self, ws_client: BybitWebSocketClient, mock_telegram: MagicMock
    ) -> None:
        _attach_mock_ws(ws_client)

        with (
            patch("asyncio.sleep", new_callable=AsyncMock),
            patch.object(ws_client, "_reconnect", new_callable=AsyncMock) as reconnect,
        ):
            await ws_client._ping_loop()
        await asyncio.sleep(0)

        reconnect.assert_awaited_once()
        mock_telegram.send.assert_awaited_once()
        assert "pong_timeout" in mock_telegram.send.await_args.args[0]
        assert ws_client._zombie_alert_sent is True
        assert ws_client.stats["errors"] == 1

    async def test_stale_pong_older_than_ping_is_missing(
        self, ws_client: BybitWebSocketClient, mock_telegram: MagicMock
    ) -> None:
        _attach_mock_ws(ws_client)
        ws_client._last_pong_time = datetime.now(UTC) - timedelta(seconds=45)

        with (
            patch("asyncio.sleep", new_callable=AsyncMock),
            patch.object(ws_client, "_reconnect", new_callable=AsyncMock) as reconnect,
        ):
            await ws_client._ping_loop()
        await asyncio.sleep(0)

        reconnect.assert_awaited_once()


# ---------------------------------------------------------------------------
# Aggregate data-flow watchdog
# ---------------------------------------------------------------------------


class TestDataFlowWatchdog:
    async def _run_watchdog(
        self, client: BybitWebSocketClient, *, stale_seconds: float, checks: int = 1
    ) -> tuple[AsyncMock, AsyncMock]:
        _attach_mock_ws(client)
        client._last_topic_message_time = datetime.now(UTC) - timedelta(seconds=stale_seconds)
        # sleep #1 = grace period, then one sleep per check; the loop is stopped on the
        # sleep *after* the last wanted check so that `_running` is still True during it.
        with (
            patch("asyncio.sleep", side_effect=_stop_after(client, checks + 2)),
            patch.object(client, "_resubscribe_all", new_callable=AsyncMock) as resub,
            patch.object(client, "_reconnect", new_callable=AsyncMock) as reconnect,
        ):
            await client._data_flow_watchdog()
        await asyncio.sleep(0)
        return resub, reconnect

    async def test_fresh_flow_does_nothing(
        self, ws_client: BybitWebSocketClient, mock_telegram: MagicMock
    ) -> None:
        resub, reconnect = await self._run_watchdog(ws_client, stale_seconds=30, checks=3)
        resub.assert_not_awaited()
        reconnect.assert_not_awaited()
        mock_telegram.send.assert_not_awaited()

    async def test_quiet_market_below_warn_threshold(self, ws_client: BybitWebSocketClient) -> None:
        resub, reconnect = await self._run_watchdog(ws_client, stale_seconds=WARN_SECONDS - 5)
        resub.assert_not_awaited()
        reconnect.assert_not_awaited()

    async def test_warn_threshold_resubscribes_once_silently(
        self, ws_client: BybitWebSocketClient, mock_telegram: MagicMock
    ) -> None:
        resub, reconnect = await self._run_watchdog(
            ws_client, stale_seconds=WARN_SECONDS + 100, checks=3
        )
        resub.assert_awaited_once()  # not repeated while the episode lasts
        reconnect.assert_not_awaited()
        mock_telegram.send.assert_not_awaited()
        assert ws_client._stale_resubscribed is True
        assert ws_client.stats["resubscribes"] == 1
        assert len(ws_client._resubscribe_events) == 1
        assert ws_client._zombie_alert_sent is False

    async def test_zombie_threshold_alerts_and_reconnects(
        self, ws_client: BybitWebSocketClient, mock_telegram: MagicMock
    ) -> None:
        ws_client._last_pong_time = datetime.now(UTC)  # connection alive, flow dead
        resub, reconnect = await self._run_watchdog(ws_client, stale_seconds=ZOMBIE_SECONDS + 1)
        reconnect.assert_awaited_once()
        mock_telegram.send.assert_awaited_once()
        text = mock_telegram.send.await_args.args[0]
        assert "data_flow_zombie" in text
        assert "pongs OK" in text
        assert ws_client._zombie_alert_sent is True

    async def test_resubscribe_storm_escalates_to_telegram(
        self, ws_client: BybitWebSocketClient, mock_telegram: MagicMock
    ) -> None:
        now = datetime.now(UTC)
        ws_client._resubscribe_events.extend([now - timedelta(hours=5), now - timedelta(hours=1)])
        resub, reconnect = await self._run_watchdog(ws_client, stale_seconds=WARN_SECONDS + 1)
        resub.assert_awaited_once()
        reconnect.assert_not_awaited()
        mock_telegram.send.assert_awaited_once()
        assert "recurring re-subscribes" in mock_telegram.send.await_args.args[0]
        assert ws_client._resubscribe_storm_alert_sent is True

    async def test_old_resubscribe_events_are_pruned(
        self, ws_client: BybitWebSocketClient, mock_telegram: MagicMock
    ) -> None:
        now = datetime.now(UTC)
        ws_client._resubscribe_events.extend(
            [now - timedelta(hours=30), now - timedelta(hours=25), now - timedelta(hours=1)]
        )
        resub, _ = await self._run_watchdog(ws_client, stale_seconds=WARN_SECONDS + 1)
        resub.assert_awaited_once()
        mock_telegram.send.assert_not_awaited()  # 2 within 24 h < threshold 3
        assert len(ws_client._resubscribe_events) == 2

    async def test_no_topic_yet_uses_connection_start(
        self, ws_client: BybitWebSocketClient
    ) -> None:
        _attach_mock_ws(ws_client)
        ws_client._connection_start_time = datetime.now(UTC) - timedelta(seconds=WARN_SECONDS + 1)
        ws_client._last_topic_message_time = None
        with (
            patch("asyncio.sleep", side_effect=_stop_after(ws_client, 2)),
            patch.object(ws_client, "_resubscribe_all", new_callable=AsyncMock) as resub,
            patch.object(ws_client, "_reconnect", new_callable=AsyncMock),
        ):
            await ws_client._data_flow_watchdog()
        resub.assert_awaited_once()

    async def test_disconnected_client_is_not_checked(
        self, ws_client: BybitWebSocketClient
    ) -> None:
        _attach_mock_ws(ws_client)
        ws_client._connected = False
        ws_client._last_topic_message_time = datetime.now(UTC) - timedelta(hours=2)
        with (
            patch("asyncio.sleep", side_effect=_stop_after(ws_client, 2)),
            patch.object(ws_client, "_resubscribe_all", new_callable=AsyncMock) as resub,
            patch.object(ws_client, "_reconnect", new_callable=AsyncMock) as reconnect,
        ):
            await ws_client._data_flow_watchdog()
        resub.assert_not_awaited()
        reconnect.assert_not_awaited()


# ---------------------------------------------------------------------------
# Reconnection
# ---------------------------------------------------------------------------


class TestReconnection:
    async def test_reconnect_restores_subscriptions(
        self, ws_client: BybitWebSocketClient, mock_telegram: MagicMock
    ) -> None:
        await _subscribe_all(ws_client)
        saved = dict(ws_client._subscriptions)

        with (
            patch("asyncio.sleep", new_callable=AsyncMock) as sleep,
            patch.object(ws_client, "connect", new_callable=AsyncMock) as connect,
            patch.object(ws_client, "_resubscribe_all", new_callable=AsyncMock) as resub,
        ):
            await ws_client._reconnect()

        sleep.assert_awaited_once_with(5)
        connect.assert_awaited_once()
        resub.assert_awaited_once()
        assert ws_client._subscriptions == saved
        assert ws_client.stats["reconnections"] == 1
        mock_telegram.send.assert_not_awaited()

    async def test_reconnect_backoff_doubles_and_caps(
        self, ws_client: BybitWebSocketClient
    ) -> None:
        ws_client._reconnect_count = 2
        with (
            patch("asyncio.sleep", new_callable=AsyncMock) as sleep,
            patch.object(ws_client, "connect", new_callable=AsyncMock),
            patch.object(ws_client, "_resubscribe_all", new_callable=AsyncMock),
        ):
            await ws_client._reconnect()
        sleep.assert_awaited_once_with(20)

        ws_client._reconnect_count = 8
        with (
            patch("asyncio.sleep", new_callable=AsyncMock) as sleep,
            patch.object(ws_client, "connect", new_callable=AsyncMock),
            patch.object(ws_client, "_resubscribe_all", new_callable=AsyncMock),
        ):
            await ws_client._reconnect()
        sleep.assert_awaited_once_with(300)

    async def test_recovery_alert_after_zombie(
        self, ws_client: BybitWebSocketClient, mock_telegram: MagicMock
    ) -> None:
        ws_client._zombie_alert_sent = True
        with (
            patch("asyncio.sleep", new_callable=AsyncMock),
            patch.object(ws_client, "connect", new_callable=AsyncMock),
            patch.object(ws_client, "_resubscribe_all", new_callable=AsyncMock),
        ):
            await ws_client._reconnect()
        assert ws_client._zombie_alert_sent is False
        mock_telegram.send.assert_awaited_once()
        assert "Recovered" in mock_telegram.send.await_args.args[0]

    async def test_max_attempts_sends_critical_alert(
        self, ws_client: BybitWebSocketClient, mock_telegram: MagicMock, event_bus: EventBus
    ) -> None:
        errors: list[dict[str, Any]] = []
        await event_bus.subscribe(EventType.SYSTEM_ERROR, lambda d: errors.append(d))
        ws_client._reconnect_count = ws_client._max_reconnect_attempts

        with patch.object(ws_client, "connect", new_callable=AsyncMock) as connect:
            await ws_client._reconnect()

        connect.assert_not_awaited()
        mock_telegram.send.assert_awaited_once()
        assert "CRITICAL" in mock_telegram.send.await_args.args[0]
        assert errors and errors[0]["component"] == "bybit_ws"

    async def test_preventive_reconnect_after_23h(self, ws_client: BybitWebSocketClient) -> None:
        ws_client._running = True
        ws_client._connected = True
        with (
            patch("asyncio.sleep", new_callable=AsyncMock) as sleep,
            patch.object(
                ws_client, "_force_disconnect_and_reconnect", new_callable=AsyncMock
            ) as force,
        ):
            await ws_client._preventive_reconnect_timer()
        sleep.assert_awaited_once_with(23 * 3600)
        force.assert_awaited_once()
        assert ws_client.stats["reconnections"] == 1

    async def test_force_disconnect_and_reconnect_resubscribes(
        self, ws_client: BybitWebSocketClient
    ) -> None:
        await _subscribe_all(ws_client)
        with (
            patch.object(ws_client, "connect", new_callable=AsyncMock) as connect,
            patch.object(ws_client, "_resubscribe_all", new_callable=AsyncMock) as resub,
        ):
            await ws_client._force_disconnect_and_reconnect()
        connect.assert_awaited_once()
        resub.assert_awaited_once()
        assert len(ws_client._subscriptions) == 24

    async def test_reconnect_aborted_after_close(self, ws_client: BybitWebSocketClient) -> None:
        """A backoff reconnect pending during close() must not resurrect the client."""
        _attach_mock_ws(ws_client)
        await ws_client.close()
        with (
            patch("asyncio.sleep", new_callable=AsyncMock),
            patch.object(ws_client, "connect", new_callable=AsyncMock) as connect,
        ):
            await ws_client._reconnect()
        connect.assert_not_awaited()

    async def test_cleanup_from_inside_background_task(
        self, ws_client: BybitWebSocketClient
    ) -> None:
        """_cleanup() called by one of its own tasks must not await itself."""
        _attach_mock_ws(ws_client)

        async def inner() -> None:
            await ws_client._cleanup()

        task = asyncio.create_task(inner())
        ws_client._data_flow_task = task
        await asyncio.wait_for(task, timeout=2)
        assert ws_client._data_flow_task is None
        assert ws_client.is_connected is False


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------


class TestFactory:
    def test_factory_builds_bybit_ws_client(
        self,
        mock_settings: Settings,
        event_bus: EventBus,
        mock_db_manager: MagicMock,
        mock_telegram: MagicMock,
    ) -> None:
        client = build_exchange_ws_client(
            mock_settings, event_bus, mock_db_manager, telegram_notifier=mock_telegram
        )
        assert isinstance(client, BybitWebSocketClient)
        assert client._db_manager is mock_db_manager
        assert client._telegram_notifier is mock_telegram


# ---------------------------------------------------------------------------
# Connection lifecycle (aiohttp mocked)
# ---------------------------------------------------------------------------


class TestConnection:
    async def test_connect_uses_settings_url_and_app_ping_only(
        self, ws_client: BybitWebSocketClient, mock_settings: Settings
    ) -> None:
        mock_ws = MagicMock()
        mock_ws.closed = False
        mock_ws.close = AsyncMock()
        mock_ws.send_json = AsyncMock()
        mock_ws.receive = AsyncMock(side_effect=asyncio.CancelledError)

        mock_session = MagicMock()
        mock_session.closed = False
        mock_session.close = AsyncMock()
        mock_session.ws_connect = AsyncMock(return_value=mock_ws)

        with patch("aiohttp.ClientSession", return_value=mock_session):
            await ws_client.connect()
            try:
                assert ws_client.is_connected
                mock_session.ws_connect.assert_awaited_once_with(
                    mock_settings.bybit.ws_url,
                    heartbeat=None,
                    receive_timeout=60.0,
                )
                assert ws_client._heartbeat_task is not None
                assert ws_client._data_flow_task is not None
                assert ws_client._preventive_reconnect_task is not None
                await asyncio.sleep(0)  # let the ping loop send its first ping
                mock_ws.send_json.assert_awaited_with({"req_id": "1", "op": "ping"})
            finally:
                await ws_client.close()

        assert ws_client.is_connected is False
        assert ws_client._ws is None
        mock_ws.close.assert_awaited_once()
        mock_session.close.assert_awaited_once()

    async def test_connect_failure_raises(self, ws_client: BybitWebSocketClient) -> None:
        from krakenbot.core.exceptions import WebSocketConnectionError

        mock_session = MagicMock()
        mock_session.closed = False
        mock_session.close = AsyncMock()
        mock_session.ws_connect = AsyncMock(side_effect=OSError("refused"))
        with (
            patch("aiohttp.ClientSession", return_value=mock_session),
            pytest.raises(WebSocketConnectionError),
        ):
            await ws_client.connect()
        assert ws_client.is_connected is False
