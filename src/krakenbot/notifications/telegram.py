"""Telegram notification service for KrakenBot.

Sends alerts for trade fills, order placements, crash protector
activations, errors, and daily summaries via the Telegram Bot API.

Usage:
    from krakenbot.notifications.telegram import get_notifier

    notifier = get_notifier()
    if notifier:
        await notifier.send("Hello from KrakenBot!")
"""

from __future__ import annotations

import asyncio

import aiohttp
import structlog

log = structlog.get_logger()

# Module-level singleton (same pattern as get_event_bus / get_settings)
_notifier: TelegramNotifier | None = None


def get_notifier() -> TelegramNotifier | None:
    """Return the global TelegramNotifier instance, or None if not configured."""
    return _notifier


def set_notifier(notifier: TelegramNotifier) -> None:
    """Register the global TelegramNotifier instance."""
    global _notifier  # noqa: PLW0603
    _notifier = notifier


class TelegramNotifier:
    """Envoie des notifications Telegram. Silencieux si désactivé ou en erreur."""

    def __init__(self, token: str, chat_id: str, enabled: bool = True) -> None:
        self.token = token
        self.chat_id = chat_id
        self.enabled = enabled
        self.url = f"https://api.telegram.org/bot{token}/sendMessage"
        self._session: aiohttp.ClientSession | None = None
        self._send_lock = asyncio.Lock()

    async def _ensure_session(self) -> aiohttp.ClientSession:
        """Lazily create the aiohttp session."""
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=10),
            )
        return self._session

    async def close(self) -> None:
        """Close the aiohttp session."""
        if self._session and not self._session.closed:
            await self._session.close()
            self._session = None

    async def send(self, message: str, silent: bool = False) -> bool:
        """Envoie un message. Retourne True si envoyé, False sinon. Ne lève jamais d'exception."""
        if not self.enabled:
            return False
        try:
            async with self._send_lock:
                session = await self._ensure_session()
                async with session.post(
                    self.url,
                    json={
                        "chat_id": self.chat_id,
                        "text": message[:4096],
                        "parse_mode": "HTML",
                        "disable_notification": silent,
                        "disable_web_page_preview": True,
                    },
                ) as resp:
                    if resp.status != 200:
                        body = await resp.text()
                        log.warning(
                            "telegram_send_failed",
                            status=resp.status,
                            body=body[:200],
                        )
                        return False
                    return True
        except Exception as e:
            log.warning("telegram_error", error=str(e))
            return False

    async def send_trade_fill(
        self,
        strategy: str,
        pair: str,
        side: str,
        amount: str,
        price: str,
        cost: str,
        fee: str,
    ) -> bool:
        """Notify on trade fill."""
        emoji = "\U0001f7e2" if side == "BUY" else "\U0001f534"
        msg = (
            f"{emoji} <b>{side} FILLED</b>\n"
            f"Strategy: <code>{strategy}</code>\n"
            f"Pair: {pair}\n"
            f"Amount: {amount}\n"
            f"Price: {price}\n"
            f"Cost: {cost} (fee: {fee})"
        )
        return await self.send(msg)

    async def send_order_placed(
        self,
        strategy: str,
        pair: str,
        side: str,
        amount: str,
        price: str,
    ) -> bool:
        """Notify on limit order placement (sent silently)."""
        msg = (
            f"\U0001f4cb <b>LIMIT {side} PLACED</b>\n"
            f"Strategy: <code>{strategy}</code>\n"
            f"Pair: {pair}\n"
            f"Amount: {amount} @ {price}"
        )
        return await self.send(msg, silent=True)

    async def send_error(self, component: str, error: str) -> bool:
        """Notify on runtime error."""
        msg = (
            f"\U0001f534 <b>RUNTIME ERROR</b>\n"
            f"Component: <code>{component}</code>\n"
            f"Error: {error[:500]}"
        )
        return await self.send(msg)

    async def send_daily_summary(
        self,
        open_positions: int,
        pending_orders: int,
        trades_today: int,
        pnl_today: str,
        equity: str,
    ) -> bool:
        """Send the daily summary."""
        msg = (
            f"\U0001f4ca <b>DAILY SUMMARY</b>\n"
            f"Open positions: {open_positions}\n"
            f"Pending orders: {pending_orders}\n"
            f"Trades today: {trades_today}\n"
            f"P&L today: {pnl_today}\n"
            f"Total equity: {equity}"
        )
        return await self.send(msg)

    async def send_crash_protector(
        self,
        drop_pct: str,
        action: str,
        suspend_hours: int,
    ) -> bool:
        """Notify on crash protector activation."""
        msg = (
            f"\u26a0\ufe0f <b>CRASH PROTECTOR ACTIVATED</b>\n"
            f"Drop: {drop_pct}\n"
            f"Action: {action}\n"
            f"Suspended: {suspend_hours}h"
        )
        return await self.send(msg)

    async def send_strategy_tick(
        self,
        strategy: str,
        pair: str,
        close: str,
        signal: str,
        reason: str,
    ) -> bool:
        """Log de chaque évaluation de stratégie. Envoyé en silent (pas de notification push)."""
        if signal in ("HOLD", "NO_SIGNAL"):
            return False  # Ne pas spammer les HOLD
        emoji = {"BUY": "\U0001f7e2", "SELL": "\U0001f534", "FILTERED": "\u26a1"}.get(
            signal, "\u2139\ufe0f"
        )
        msg = (
            f"{emoji} <b>{signal}</b>\n"
            f"Strategy: <code>{strategy}</code>\n"
            f"Pair: {pair} @ {close}\n"
            f"Reason: {reason}"
        )
        return await self.send(msg, silent=(signal == "FILTERED"))

    async def send_bot_started(self, mode: str, strategies: list[str]) -> bool:
        """Notify on bot startup."""
        msg = f"\u2705 <b>KrakenBot Started</b>\nMode: {mode}\nStrategies: {', '.join(strategies)}"
        return await self.send(msg)

    async def send_bot_stopped(self) -> bool:
        """Notify on bot shutdown."""
        return await self.send("\U0001f6d1 <b>KrakenBot Stopped</b>")
