"""Tests for Telegram notification service."""

from __future__ import annotations

from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock

import pytest

from krakenbot.notifications.telegram import TelegramNotifier


def _mock_aiohttp_session(*, status: int = 200) -> MagicMock:
    """Create a mock aiohttp session whose post() returns an async context manager."""
    mock_resp = MagicMock()
    mock_resp.status = status
    mock_resp.text = AsyncMock(return_value="")

    @asynccontextmanager
    async def _fake_post(*args: object, **kwargs: object) -> object:
        yield mock_resp

    mock_session = MagicMock()
    mock_session.closed = False
    mock_session.post = MagicMock(side_effect=_fake_post)
    return mock_session


@pytest.mark.asyncio
async def test_telegram_send_success() -> None:
    """Message envoyé → retourne True."""
    notifier = TelegramNotifier("fake_token", "fake_chat", enabled=True)
    notifier._session = _mock_aiohttp_session(status=200)

    result = await notifier.send("test message")
    assert result is True


@pytest.mark.asyncio
async def test_telegram_disabled() -> None:
    """enabled=False → aucun appel HTTP, retourne False."""
    notifier = TelegramNotifier("fake_token", "fake_chat", enabled=False)
    result = await notifier.send("test message")
    assert result is False


@pytest.mark.asyncio
async def test_telegram_error_no_crash() -> None:
    """Si Telegram est down, le notifier ne crash PAS."""
    notifier = TelegramNotifier("fake_token", "fake_chat", enabled=True)
    mock_session = MagicMock()
    mock_session.closed = False
    mock_session.post = MagicMock(side_effect=Exception("connection refused"))
    notifier._session = mock_session

    result = await notifier.send("test message")
    assert result is False


@pytest.mark.asyncio
async def test_trade_fill_format() -> None:
    """Le message de trade fill contient les bonnes infos."""
    notifier = TelegramNotifier("fake_token", "fake_chat", enabled=True)
    notifier.send = AsyncMock(return_value=True)

    await notifier.send_trade_fill(
        strategy="supertrend_4h",
        pair="BTC/USDC",
        side="BUY",
        amount="0.0012 BTC",
        price="83,150",
        cost="100.00 USDC",
        fee="0.10 USDC",
    )
    msg = notifier.send.call_args[0][0]
    assert "supertrend_4h" in msg
    assert "BUY" in msg
    assert "83,150" in msg


@pytest.mark.asyncio
async def test_daily_summary_format() -> None:
    """Le résumé quotidien contient toutes les métriques."""
    notifier = TelegramNotifier("fake_token", "fake_chat", enabled=True)
    notifier.send = AsyncMock(return_value=True)

    await notifier.send_daily_summary(
        open_positions=3,
        pending_orders=8,
        trades_today=2,
        pnl_today="+2.15 USDC",
        equity="1,012.50 USDC",
    )
    msg = notifier.send.call_args[0][0]
    assert "DAILY SUMMARY" in msg
    assert "1,012.50" in msg


@pytest.mark.asyncio
async def test_hold_signals_not_sent() -> None:
    """Les signaux HOLD ne sont pas envoyés (anti-spam)."""
    notifier = TelegramNotifier("fake_token", "fake_chat", enabled=True)
    result = await notifier.send_strategy_tick(
        strategy="grid",
        pair="BTC/USDC",
        close="83000",
        signal="HOLD",
        reason="no conditions met",
    )
    assert result is False


@pytest.mark.asyncio
async def test_crash_protector_format() -> None:
    """Le message crash protector contient les infos clés."""
    notifier = TelegramNotifier("fake_token", "fake_chat", enabled=True)
    notifier.send = AsyncMock(return_value=True)

    await notifier.send_crash_protector(
        drop_pct="-8.5%",
        action="Closing 3 positions",
        suspend_hours=2,
    )
    msg = notifier.send.call_args[0][0]
    assert "CRASH PROTECTOR" in msg
    assert "-8.5%" in msg
    assert "2h" in msg


@pytest.mark.asyncio
async def test_error_format() -> None:
    """Le message d'erreur contient le composant et l'erreur."""
    notifier = TelegramNotifier("fake_token", "fake_chat", enabled=True)
    notifier.send = AsyncMock(return_value=True)

    await notifier.send_error(
        component="execution_engine",
        error="Connection reset by peer",
    )
    msg = notifier.send.call_args[0][0]
    assert "RUNTIME ERROR" in msg
    assert "execution_engine" in msg
    assert "Connection reset" in msg


@pytest.mark.asyncio
async def test_close_session() -> None:
    """close() ferme la session aiohttp proprement."""
    notifier = TelegramNotifier("fake_token", "fake_chat", enabled=True)
    mock_session = AsyncMock()
    mock_session.closed = False
    notifier._session = mock_session

    await notifier.close()
    mock_session.close.assert_called_once()
    assert notifier._session is None


@pytest.mark.asyncio
async def test_order_placed_silent() -> None:
    """Les ordres placés sont envoyés en silent (pas de notification push)."""
    notifier = TelegramNotifier("fake_token", "fake_chat", enabled=True)
    sent_messages: list[tuple[str, bool]] = []

    async def _capture_send(message: str, silent: bool = False) -> bool:
        sent_messages.append((message, silent))
        return True

    notifier.send = _capture_send  # type: ignore[assignment]

    await notifier.send_order_placed(
        strategy="grid_atr_v4",
        pair="BTC/USDC",
        side="BUY",
        amount="0.001",
        price="82000",
    )
    assert len(sent_messages) == 1
    msg, silent = sent_messages[0]
    assert silent is True
    assert "LIMIT BUY PLACED" in msg


@pytest.mark.asyncio
async def test_send_http_error_returns_false() -> None:
    """HTTP 400 retourne False et log un warning."""
    notifier = TelegramNotifier("fake_token", "fake_chat", enabled=True)
    notifier._session = _mock_aiohttp_session(status=400)

    result = await notifier.send("test")
    assert result is False
