"""Exchange abstraction and factory functions for runtime execution.

This module keeps the current Kraken behavior unchanged while giving the
runtime a stable surface that can later be implemented by another exchange.
Provides factory functions for both REST and WebSocket clients.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING, Any, Protocol, runtime_checkable

from krakenbot.models.base import TradeSide
from krakenbot.models.orders import Order
from krakenbot.models.trades import Trade

if TYPE_CHECKING:
    from krakenbot.config.settings import Settings
    from krakenbot.connectors.base_ws import BaseWebSocketClient
    from krakenbot.core.database import DatabaseManager
    from krakenbot.core.event_bus import EventBus


@runtime_checkable
class ExchangeRestClient(Protocol):
    """Runtime REST surface consumed by KrakenBot execution code."""

    @property
    def exchange_name(self) -> str: ...

    @property
    def is_paper_mode(self) -> bool: ...

    @property
    def stats(self) -> dict[str, int]: ...

    @property
    def paper_balance(self) -> dict[str, Decimal]: ...

    async def close(self) -> None: ...

    def update_last_price(self, pair: str, price: Decimal) -> None: ...

    async def get_balance(self) -> dict[str, Decimal]: ...

    async def get_ticker(self, pair: str) -> dict[str, Any]: ...

    async def get_margin_balance(self) -> dict[str, Decimal]: ...

    async def place_market_order(
        self,
        pair: str,
        side: TradeSide,
        amount: Decimal,
        strategy: str,
        *,
        reference_price: Decimal | None = None,
        position_id: int | None = None,
    ) -> Trade: ...

    async def place_margin_order(
        self,
        pair: str,
        side: TradeSide,
        amount: Decimal,
        leverage: int,
        strategy: str,
        *,
        reference_price: Decimal | None = None,
        position_id: int | None = None,
    ) -> Trade: ...

    async def place_limit_order(
        self,
        pair: str,
        side: TradeSide,
        amount: Decimal,
        price: Decimal,
        strategy: str,
        *,
        expires_in_seconds: int | None = None,
    ) -> Order: ...

    async def get_order_status(self, order_id: str, pair: str | None = None) -> dict[str, Any]: ...

    async def cancel_order(self, order_id: str, pair: str | None = None) -> bool: ...

    async def initialize_paper_balance(self, force_reset: bool = False) -> None: ...

    async def persist_paper_balance(self) -> None: ...

    def remove_paper_order(self, order_id: str) -> None: ...

    async def fetch_ohlcv(
        self,
        pair: str,
        interval: int,
        since: datetime | None = None,
        limit: int = 720,
    ) -> list[dict[str, Any]]:
        """Fetch historical OHLC candles, oldest first.

        Each candle is a dict ``{timestamp, pair, interval, open, high, low,
        close, volume}`` (Decimals, aware UTC datetime) with an optional
        ``vwap`` key.

        Timestamp convention — honest statement of the invariant:

        * **Bybit** (B3): ``timestamp = open_time + interval`` (period end),
          exactly as the WebSocket collector stores ``exchange='bybit'`` rows;
          ``vwap = turnover / volume``; the in-progress candle is excluded.
          This is the only client on which ``krakenbot.data.backfill`` is
          guaranteed correct.
        * **Binance / Kraken**: ccxt *open* time, no ``vwap``.  Binance rows in
          DB are a mix of Vision (open-stamped) and WS (end-stamped) data, so
          no single invariant holds there.  A gap backfill on these exchanges
          would insert candles shifted by one interval without any error.
        """
        ...

    async def get_open_orders(self, pair: str | None = None) -> list[dict[str, Any]]:
        """Get open/pending orders."""
        ...

    async def get_trade_history(
        self, pair: str | None = None, limit: int = 50
    ) -> list[dict[str, Any]]:
        """Get completed trade history."""
        ...

    async def get_open_margin_positions(self) -> list[dict[str, Any]]:
        """Get open margin positions."""
        ...

    async def set_paper_balance(self, currency: str, amount: Decimal) -> None:
        """Set paper trading balance for a currency."""
        ...

    def get_paper_balance(self) -> dict[str, Decimal]:
        """Get current paper trading balance."""
        ...


def build_exchange_rest_client(
    settings: Settings,
    event_bus: EventBus,
    db_manager: DatabaseManager | None = None,
    *,
    read_only: bool = False,
) -> ExchangeRestClient:
    """Build the REST client used by runtime execution.

    Dispatches on ``settings.exchange_name`` (required, validated by Settings).

    Args:
        read_only: Sign with the read-only API key even in LIVE mode.  Used by
            the collector / gap backfill, which never place orders, so the
            trade key is never loaded there once the shared ``.env`` switches
            to ``TRADING_MODE=live`` (B5).  Only Bybit distinguishes key roles
            (``BYBIT_*`` vs ``BYBIT_TRADE_*``); Binance and Kraken ignore the flag.
    """
    exchange_name = settings.exchange_name.lower()

    if exchange_name == "binance":
        from krakenbot.connectors.binance.rest import BinanceRestClient

        return BinanceRestClient(settings, event_bus, db_manager)

    if exchange_name == "bybit":
        from krakenbot.connectors.bybit.rest import BybitRestClient

        return BybitRestClient(
            settings, event_bus, db_manager, key_role="readonly" if read_only else None
        )

    # Kraken (legacy)
    from krakenbot.connectors.kraken.rest import KrakenRestClient

    return KrakenRestClient(settings, event_bus, db_manager)


def build_exchange_ws_client(
    settings: Settings,
    event_bus: EventBus,
    db_manager: DatabaseManager | None = None,
    telegram_notifier: Any | None = None,
) -> BaseWebSocketClient:
    """Build the WebSocket client for the configured exchange.

    Dispatches on ``settings.exchange_name`` (required, validated by Settings).
    """
    exchange_name = settings.exchange_name.lower()

    if exchange_name == "bybit":
        from krakenbot.connectors.bybit.ws import BybitWebSocketClient

        return BybitWebSocketClient(
            settings,
            event_bus,
            db_manager=db_manager,
            telegram_notifier=telegram_notifier,
        )

    if exchange_name == "binance":
        from krakenbot.connectors.binance.ws import BinanceWebSocketClient

        return BinanceWebSocketClient(
            settings,
            event_bus,
            db_manager=db_manager,
            telegram_notifier=telegram_notifier,
        )

    # Kraken (legacy)
    from krakenbot.connectors.kraken.ws import KrakenWebSocketClient

    return KrakenWebSocketClient(settings, event_bus, db_manager)
