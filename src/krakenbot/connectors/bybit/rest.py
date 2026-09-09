"""Bybit EU REST API client for spot trading operations.

Structural clone of :mod:`krakenbot.connectors.binance.rest` targeting the
Bybit **EU** instance (``api.bybit.eu``), a separate exchange from the global
``api.bybit.com`` (own instrument filters, own matching engine, own API keys).
Constants and pitfalls come from ``skills/bybit.md`` (audit B0/B1).

Bybit-specific behaviour:
    - ``load_markets()`` is mandatory on the EU hostname (lot filters differ from
      global). It is loaded lazily, once, before the first exchange call.
    - Fees are NEVER read from ccxt (``describe()`` returns generic values); they
      come from :class:`ExchangeFees` (Bybit defaults: maker 0.10 %, taker 0.25 %).
    - Market BUY never passes ``price`` to ccxt (ccxt would reinterpret ``qty`` in
      quote currency). A quote-denominated buy goes through ``params={"cost": ...}``.
    - Limit orders default to ``timeInForce=PostOnly`` (maker guaranteed). A
      PostOnly rejection (price would cross) is returned as a normalised
      ``CANCELLED`` order with ``signal_metadata["reject_reason"]`` so the caller
      can re-quote — it is not a fatal exception.
    - ``clientOrderId`` maps to Bybit ``orderLinkId`` (36 chars max).
    - Business errors arrive as HTTP 200 with ``retCode != 0``; they are mapped to
      the project exceptions in :meth:`BybitRestClient._translate_error`.

Example:
    >>> from krakenbot.connectors.bybit.rest import BybitRestClient
    >>> client = BybitRestClient(settings, event_bus, db_manager)
    >>> balance = await client.get_balance()
    >>> order = await client.place_limit_order("BTC/USDC", TradeSide.BUY, amount, price)
    >>> await client.close()
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from decimal import ROUND_DOWN, ROUND_UP, Decimal
import re
from typing import TYPE_CHECKING, Any
import uuid

import ccxt.async_support as ccxt

from krakenbot.config.settings import BybitKeyRole, ExchangeFees, TradingMode
from krakenbot.core.event_bus import EventBus, EventType
from krakenbot.core.exceptions import (
    InsufficientBalanceError,
    KrakenAPIError,
    KrakenBotError,
    OrderCancelError,
    OrderExecutionError,
    RateLimitError,
)
from krakenbot.core.logger import get_logger
from krakenbot.models.base import OrderStatus, OrderType, TradeSide, TradeStatus
from krakenbot.models.orders import Order
from krakenbot.models.trades import Trade

if TYPE_CHECKING:
    from krakenbot.config.settings import Settings
    from krakenbot.core.database import DatabaseManager

logger = get_logger(__name__)

# Lot filters — api.bybit.eu instruments-info (2026-09-07/08). minOrderQty == qtyStep on EU.
MIN_ORDER_SIZE: dict[str, Decimal] = {
    "BTC/USDC": Decimal("0.000001"),
    "ETH/USDC": Decimal("0.0001"),
    "SOL/USDC": Decimal("0.001"),
}
QTY_STEP: dict[str, Decimal] = MIN_ORDER_SIZE
TICK_SIZE: dict[str, Decimal] = {
    "BTC/USDC": Decimal("0.1"),
    "ETH/USDC": Decimal("0.01"),
    "SOL/USDC": Decimal("0.01"),
}
_DEFAULT_QTY_STEP = Decimal("0.000001")
_DEFAULT_TICK = Decimal("0.01")

# Minimum notional for all USDC pairs (BTC accepts 1 USDC on EU, 5 kept for safety)
MIN_NOTIONAL = Decimal("5")

# Bybit orderLinkId limit
MAX_CLIENT_ORDER_ID_LEN = 36

# Normalised reject reason exposed in Order.signal_metadata on PostOnly rejection
POST_ONLY_REJECT_REASON = "post_only_would_cross"

# Bybit v5 retCodes (skills/bybit.md) — kept explicit even though ccxt maps most of them
RET_INSUFFICIENT_BALANCE = 170131
RET_ORDER_NOT_EXISTS = 170213
RET_RATE_LIMIT = 10006
RET_CLOCK_DRIFT = 10002
RET_PARAM_ERROR = 10001
RET_PERMISSION_DENIED = 10005
RET_BUY_PRICE_TOO_HIGH = 170193
RET_SELL_PRICE_TOO_LOW = 170194
PRICE_LIMIT_CODES = frozenset({RET_BUY_PRICE_TOO_HIGH, RET_SELL_PRICE_TOO_LOW})

_RET_CODE_RE = re.compile(r'"retCode"\s*:\s*"?(\d+)"?')
_POST_ONLY_MSG_RE = re.compile(r"post[\s_-]?only", re.IGNORECASE)


class BybitRestClient:
    """Async REST client for Bybit EU spot using ccxt.

    Supports paper trading (simulation, same mechanics as the Binance client)
    and live trading on ``api.bybit.eu``.

    Attributes:
        settings: Application settings (``settings.bybit`` for credentials/hostname).
        event_bus: Event bus for publishing trade events.
        db_manager: Database manager for trade persistence (optional).
    """

    def __init__(
        self,
        settings: Settings,
        event_bus: EventBus,
        db_manager: DatabaseManager | None = None,
        *,
        key_role: BybitKeyRole | None = None,
    ) -> None:
        """Build the client.

        Args:
            settings: Application settings (``settings.bybit`` holds both key pairs).
            event_bus: Event bus for trade events.
            db_manager: Optional DB manager for persistence.
            key_role: Which API key pair to sign with. Defaults to ``"trade"``
                (``BYBIT_TRADE_*``) in LIVE mode and ``"readonly"`` (``BYBIT_*``) in
                PAPER mode. Pass ``"readonly"`` explicitly for read-only checks in
                LIVE mode (audits).

        Raises:
            ValueError: If the trade key pair is required but missing.
        """
        self._settings = settings
        self._event_bus = event_bus
        self._db_manager = db_manager

        is_live = settings.trading.mode == TradingMode.LIVE
        self._mode_prefix = "[LIVE]" if is_live else "[PAPER]"
        self._key_role: BybitKeyRole = key_role or ("trade" if is_live else "readonly")

        bybit_settings = settings.bybit
        api_key, api_secret = bybit_settings.credentials(self._key_role)
        self._exchange = ccxt.bybit(
            {
                "apiKey": api_key,
                "secret": api_secret,
                "hostname": bybit_settings.hostname,
                "enableRateLimit": True,
                "options": {
                    "defaultType": "spot",
                    "recvWindow": bybit_settings.recv_window,
                    "adjustForTimeDifference": True,
                    # Deterministic UTA branch in ccxt (market BUY in base qty, no lazy
                    # private call to detect the account type).
                    "enableUnifiedAccount": bybit_settings.account_type.upper() == "UNIFIED",
                },
            }
        )

        # Fees: never from ccxt. Explicit settings.exchange_fees wins, else Bybit defaults.
        self._fees: ExchangeFees = (
            settings.exchange_fees
            if "exchange_fees" in settings.model_fields_set
            else ExchangeFees.bybit_defaults()
        )

        # Markets are loaded lazily (async) before the first exchange call.
        self._markets_loaded = False
        self._markets_lock = asyncio.Lock()

        # Paper trading state — populated by initialize_paper_balance() at startup
        pair = settings.trading.pair
        _base, _quote = pair.split("/")
        self._paper_balance: dict[str, Decimal] = {
            _quote: Decimal("0"),
            _base: Decimal("0"),
        }
        self._paper_orders: dict[str, dict[str, Any]] = {}
        self._last_prices: dict[str, Decimal] = {}

        self._stats: dict[str, int] = {
            "orders_placed": 0,
            "orders_filled": 0,
            "orders_failed": 0,
            "api_calls": 0,
        }

        logger.info(
            "bybit_rest_initialized",
            mode=settings.trading.mode.value,
            hostname=bybit_settings.hostname,
            account_type=bybit_settings.account_type,
            key_role=self._key_role,
            has_api_key=bool(api_key),
            maker_fee=str(self._fees.maker),
            taker_fee=str(self._fees.taker),
        )

    # =========================================================================
    # Properties (ExchangeRestClient Protocol)
    # =========================================================================

    @property
    def exchange_name(self) -> str:
        """Return the canonical exchange identifier for this client."""
        return "bybit"

    @property
    def is_paper_mode(self) -> bool:
        """Check if running in paper trading mode."""
        return self._settings.trading.mode == TradingMode.PAPER

    @property
    def stats(self) -> dict[str, int]:
        """Get client statistics."""
        return self._stats.copy()

    @property
    def paper_balance(self) -> dict[str, Decimal]:
        """Expose the mutable paper balance for runtime paper-fill simulation."""
        return self._paper_balance

    @property
    def fees(self) -> ExchangeFees:
        """Fee schedule used by this client (paper fills and notional checks)."""
        return self._fees

    @property
    def key_role(self) -> BybitKeyRole:
        """Which API key pair signs requests (``readonly`` or ``trade``)."""
        return self._key_role

    @property
    def markets_loaded(self) -> bool:
        """Whether ``load_markets()`` has completed on the EU hostname."""
        return self._markets_loaded

    async def close(self) -> None:
        """Close the ccxt exchange connection."""
        await self._exchange.close()
        logger.info("bybit_rest_closed")

    def update_last_price(self, pair: str, price: Decimal) -> None:
        """Update the last known price for a pair (paper fill simulation)."""
        self._last_prices[pair] = price

    # =========================================================================
    # Markets / precision
    # =========================================================================

    async def load_markets(self, reload: bool = False) -> None:
        """Load EU instrument filters via ccxt (mandatory before any order).

        Args:
            reload: Force a reload even if markets are already loaded.

        Raises:
            KrakenAPIError: If the exchange cannot be reached.
        """
        async with self._markets_lock:
            if self._markets_loaded and not reload:
                return
            try:
                self._stats["api_calls"] += 1
                await self._exchange.load_markets(reload=reload)
            except ccxt.BaseError as e:
                logger.error("bybit_rest_load_markets_error", error=str(e))
                raise KrakenAPIError(
                    message=f"Failed to load Bybit markets on {self._settings.bybit.hostname}: {e}",
                    response={"error": str(e)},
                ) from e
            self._markets_loaded = True
            logger.info(
                "bybit_rest_markets_loaded",
                hostname=self._settings.bybit.hostname,
                symbols=len(self._exchange.markets or {}),
            )

    async def _ensure_markets(self) -> None:
        if not self._markets_loaded:
            await self.load_markets()

    def _market_precision(self, pair: str, key: str) -> Decimal | None:
        """Return the tick/step from loaded markets (ccxt TICK_SIZE mode), or None."""
        if not self._markets_loaded:
            return None
        markets = getattr(self._exchange, "markets", None) or {}
        market = markets.get(pair)
        if not market:
            return None
        value = (market.get("precision") or {}).get(key)
        if value is None:
            return None
        return Decimal(str(value))

    def _amount_step(self, pair: str) -> Decimal:
        return self._market_precision(pair, "amount") or QTY_STEP.get(pair, _DEFAULT_QTY_STEP)

    def _price_tick(self, pair: str) -> Decimal:
        return self._market_precision(pair, "price") or TICK_SIZE.get(pair, _DEFAULT_TICK)

    def _round_amount(self, pair: str, amount: Decimal) -> Decimal:
        """Round an amount DOWN to the pair's qtyStep."""
        step = self._amount_step(pair)
        return (amount / step).to_integral_value(rounding=ROUND_DOWN) * step

    def _round_price(self, pair: str, price: Decimal, side: TradeSide) -> Decimal:
        """Round a price to the tickSize, away from the market (BUY down, SELL up)."""
        tick = self._price_tick(pair)
        rounding = ROUND_DOWN if side == TradeSide.BUY else ROUND_UP
        return (price / tick).to_integral_value(rounding=rounding) * tick

    @staticmethod
    def _new_client_order_id() -> str:
        """Generate a unique orderLinkId (<= 36 chars)."""
        return f"kb-{uuid.uuid4().hex}"[:MAX_CLIENT_ORDER_ID_LEN]

    # =========================================================================
    # Error mapping (retCode -> project exceptions)
    # =========================================================================

    @staticmethod
    def _extract_ret_code(exc: BaseException) -> int | None:
        """Extract Bybit ``retCode`` from a ccxt exception message, if present."""
        match = _RET_CODE_RE.search(str(exc))
        return int(match.group(1)) if match else None

    @classmethod
    def _is_post_only_rejection(cls, exc: BaseException) -> bool:
        """True if the exception is a PostOnly "would take liquidity" rejection."""
        if isinstance(exc, ccxt.OrderImmediatelyFillable):
            return True
        return bool(_POST_ONLY_MSG_RE.search(str(exc)))

    def _translate_error(
        self,
        exc: BaseException,
        *,
        pair: str | None = None,
        side: str | None = None,
        amount: Decimal | None = None,
        order_id: str | None = None,
        context: str = "order",
    ) -> KrakenBotError:
        """Map a ccxt exception (typed or raw retCode) to a project exception.

        ``context`` selects the fallback class: ``"order"`` -> OrderExecutionError,
        ``"cancel"`` -> OrderCancelError, anything else -> KrakenAPIError.
        """
        ret_code = self._extract_ret_code(exc)
        message = str(exc)
        details: dict[str, Any] = {"ret_code": ret_code} if ret_code is not None else {}

        if isinstance(exc, ccxt.InsufficientFunds) or ret_code == RET_INSUFFICIENT_BALANCE:
            return InsufficientBalanceError(
                message=f"Insufficient balance (Bybit retCode {ret_code}): {message}",
                details=details,
            )

        if (
            isinstance(exc, ccxt.RateLimitExceeded | ccxt.DDoSProtection)
            or ret_code == RET_RATE_LIMIT
            or "403" in message
        ):
            return RateLimitError(
                message=f"Bybit rate limit exceeded (retCode {ret_code}): {message}",
                retry_after=1,
                details=details,
            )

        if isinstance(exc, ccxt.InvalidNonce) or ret_code == RET_CLOCK_DRIFT:
            return KrakenAPIError(
                message=(
                    "Bybit rejected the request timestamp (retCode 10002): local clock drift "
                    f"exceeds recv_window={self._settings.bybit.recv_window} ms. "
                    "Sync the system clock with NTP (timedatectl set-ntp true / sntp -sS "
                    "time.apple.com) — adjustForTimeDifference is already enabled. "
                    f"Raw: {message}"
                ),
                details=details,
            )

        if ret_code in PRICE_LIMIT_CODES:
            details["reason"] = "price_limit_ratio"
            return OrderExecutionError(
                message=(
                    f"Limit price too far from last price (Bybit priceLimitRatio, "
                    f"retCode {ret_code}): {message}"
                ),
                pair=pair,
                side=side,
                amount=amount,
                details=details,
            )

        if ret_code == RET_PERMISSION_DENIED:
            details["reason"] = "permission_denied"
            return KrakenAPIError(
                message=(
                    "Bybit refused the action (retCode 10005): the API key is read-only, lacks "
                    "the Spot Trade permission, or the caller IP is not whitelisted. Create a key "
                    f"with readOnly=0 + Spot Trade on bybit.eu. Raw: {message}"
                ),
                details=details,
            )

        if isinstance(exc, ccxt.AuthenticationError):
            return KrakenAPIError(
                message=f"Bybit authentication failed (check BYBIT_API_KEY/SECRET, EU keys): {message}",
                details=details,
            )

        if context == "cancel":
            return OrderCancelError(
                message=f"Failed to cancel Bybit order: {message}",
                order_id=order_id,
                details=details,
            )
        if context == "order":
            if ret_code == RET_PARAM_ERROR:
                details["reason"] = "parameter_error"
            return OrderExecutionError(
                message=f"Bybit order failed (retCode {ret_code}): {message}",
                order_id=order_id,
                pair=pair,
                side=side,
                amount=amount,
                details=details,
            )
        return KrakenAPIError(
            message=f"Bybit API error during {context} (retCode {ret_code}): {message}",
            response={"error": message},
            details=details,
        )

    # =========================================================================
    # Read-only methods
    # =========================================================================

    async def get_balance(self) -> dict[str, Decimal]:
        """Get available balance per currency (UTA wallet-balance in live mode)."""
        if self.is_paper_mode:
            logger.info(f"{self._mode_prefix} get_balance", balance=str(self._paper_balance))
            return self._paper_balance.copy()

        try:
            await self._ensure_markets()
            self._stats["api_calls"] += 1
            balance = await self._exchange.fetch_balance()
            result = self._parse_free_balance(balance)
            logger.info(f"{self._mode_prefix} get_balance", currencies=list(result.keys()))
            return result
        except ccxt.BaseError as e:
            logger.error("bybit_rest_balance_error", error=str(e))
            raise self._translate_error(e, context="balance") from e

    @staticmethod
    def _parse_free_balance(balance: dict[str, Any]) -> dict[str, Decimal]:
        result: dict[str, Decimal] = {}
        for currency, amount in (balance.get("free") or {}).items():
            if amount and float(amount) > 0:
                result[currency] = Decimal(str(amount))
        return result

    async def get_ticker(self, pair: str) -> dict[str, Any]:
        """Get current ticker information for a pair."""
        try:
            await self._ensure_markets()
            self._stats["api_calls"] += 1
            ticker = await self._exchange.fetch_ticker(pair)

            if ticker.get("last"):
                self._last_prices[pair] = Decimal(str(ticker["last"]))

            def _dec(key: str) -> Decimal | None:
                value = ticker.get(key)
                return Decimal(str(value)) if value else None

            return {
                "pair": pair,
                "bid": _dec("bid"),
                "ask": _dec("ask"),
                "last": _dec("last"),
                "volume": _dec("baseVolume"),
                "high": _dec("high"),
                "low": _dec("low"),
                "timestamp": ticker.get("timestamp"),
            }
        except ccxt.BaseError as e:
            logger.error("bybit_rest_ticker_error", error=str(e), pair=pair)
            raise self._translate_error(e, pair=pair, context="ticker") from e

    async def fetch_ohlcv(
        self,
        pair: str,
        interval: int,
        since: datetime | None = None,
        limit: int = 1000,
    ) -> list[dict[str, Any]]:
        """Fetch historical OHLC candles (max 1000 per call on Bybit v5).

        Raises:
            KrakenAPIError: On API errors.
            RateLimitError: If rate limit exceeded.
            ValueError: If interval is not supported.
        """
        from krakenbot.utils.time_utils import minutes_to_ccxt_timeframe

        timeframe = minutes_to_ccxt_timeframe(interval)
        since_ms = int(since.timestamp() * 1000) if since else None

        try:
            await self._ensure_markets()
            logger.debug(
                "fetching_ohlcv",
                pair=pair,
                timeframe=timeframe,
                since=since.isoformat() if since else None,
                limit=limit,
            )
            self._stats["api_calls"] += 1
            ohlcv_data = await self._exchange.fetch_ohlcv(
                symbol=pair,
                timeframe=timeframe,
                since=since_ms,
                limit=min(limit, 1000),
            )

            result: list[dict[str, Any]] = []
            for candle in ohlcv_data:
                timestamp_ms, open_price, high, low, close, volume = candle[:6]
                result.append(
                    {
                        "timestamp": datetime.fromtimestamp(timestamp_ms / 1000, tz=UTC),
                        "pair": pair,
                        "interval": interval,
                        "open": Decimal(str(open_price)),
                        "high": Decimal(str(high)),
                        "low": Decimal(str(low)),
                        "close": Decimal(str(close)),
                        "volume": Decimal(str(volume)),
                    }
                )

            logger.info(
                "ohlcv_fetched",
                pair=pair,
                interval=interval,
                candles=len(result),
                first_timestamp=str(result[0]["timestamp"]) if result else None,
                last_timestamp=str(result[-1]["timestamp"]) if result else None,
            )
            return result

        except ccxt.BaseError as e:
            logger.error("bybit_rest_ohlcv_error", pair=pair, interval=interval, error=str(e))
            raise self._translate_error(e, pair=pair, context="ohlcv") from e

    async def get_open_orders(self, pair: str | None = None) -> list[dict[str, Any]]:
        """Get open orders (paper: in-memory pending limits)."""
        if self.is_paper_mode:
            orders = list(self._paper_orders.values())
            if pair:
                orders = [o for o in orders if o.get("pair") == pair]
            logger.info(f"{self._mode_prefix} get_open_orders", count=len(orders))
            return orders

        try:
            await self._ensure_markets()
            self._stats["api_calls"] += 1
            orders = await self._exchange.fetch_open_orders(pair)
            result = [
                {
                    "order_id": order.get("id"),
                    "client_order_id": order.get("clientOrderId"),
                    "pair": order.get("symbol"),
                    "side": order.get("side"),
                    "amount": Decimal(str(order.get("amount") or 0)),
                    "filled": Decimal(str(order.get("filled") or 0)),
                    "price": Decimal(str(order["price"])) if order.get("price") else None,
                    "status": order.get("status"),
                    "timestamp": order.get("timestamp"),
                }
                for order in orders
            ]
            logger.info(f"{self._mode_prefix} get_open_orders", count=len(result))
            return result
        except ccxt.BaseError as e:
            logger.error("bybit_rest_open_orders_error", error=str(e))
            raise self._translate_error(e, pair=pair, context="open_orders") from e

    async def get_trade_history(
        self,
        pair: str | None = None,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        """Get executions (fees are charged in the received currency on Bybit)."""
        if self.is_paper_mode:
            logger.info(
                f"{self._mode_prefix} get_trade_history",
                message="Paper trades stored in database",
            )
            return []

        try:
            await self._ensure_markets()
            self._stats["api_calls"] += 1
            trades = await self._exchange.fetch_my_trades(pair, limit=limit)
            result = []
            for trade in trades:
                fee_info = trade.get("fee") or {}
                result.append(
                    {
                        "trade_id": trade.get("id"),
                        "order_id": trade.get("order"),
                        "pair": trade.get("symbol"),
                        "side": trade.get("side"),
                        "amount": Decimal(str(trade.get("amount") or 0)),
                        "price": Decimal(str(trade.get("price") or 0)),
                        "fee": Decimal(str(fee_info.get("cost") or 0)),
                        "fee_currency": fee_info.get("currency"),
                        "timestamp": trade.get("timestamp"),
                    }
                )
            logger.info(f"{self._mode_prefix} get_trade_history", count=len(result))
            return result
        except ccxt.BaseError as e:
            logger.error("bybit_rest_trade_history_error", error=str(e))
            raise self._translate_error(e, pair=pair, context="trade_history") from e

    # =========================================================================
    # Order validation
    # =========================================================================

    def _validate_min_notional(self, pair: str, amount: Decimal, price: Decimal) -> None:
        """Raise if ``amount * price`` is below MIN_NOTIONAL (5 USDC)."""
        notional = amount * price
        if notional < MIN_NOTIONAL:
            raise OrderExecutionError(
                message=(
                    f"Order notional {notional} USDC below Bybit minimum "
                    f"{MIN_NOTIONAL} USDC for {pair}"
                ),
                pair=pair,
                amount=amount,
            )

    def _prepare_amount(self, pair: str, side: TradeSide, amount: Decimal) -> Decimal:
        """Round the amount to qtyStep and validate against minOrderQty."""
        rounded = self._round_amount(pair, amount)
        min_size = MIN_ORDER_SIZE.get(pair, _DEFAULT_QTY_STEP)
        if rounded < min_size or rounded <= 0:
            raise OrderExecutionError(
                message=(
                    f"Order amount {amount} (rounded {rounded}) below minimum "
                    f"({min_size}) for {pair}"
                ),
                pair=pair,
                side=side.value,
                amount=amount,
            )
        return rounded

    # =========================================================================
    # Market orders
    # =========================================================================

    async def place_market_order(
        self,
        pair: str,
        side: TradeSide,
        amount: Decimal,
        strategy: str = "manual",
        signal_price: Decimal | None = None,
        *,
        quote_amount: Decimal | None = None,
    ) -> Trade:
        """Place a market order.

        Args:
            pair: Trading pair (e.g., "BTC/USDC").
            side: Order side (BUY or SELL).
            amount: Order amount in base currency (rounded down to qtyStep).
            strategy: Strategy name for tracking.
            signal_price: Expected price (paper fill fallback / notional check).
            quote_amount: Optional quote-denominated size for a BUY (Bybit
                ``marketUnit=quoteCoin`` via ccxt ``params={"cost": ...}``). When
                given, ``amount`` is ignored for the exchange request.

        Returns:
            Trade object representing the executed order.

        Raises:
            InsufficientBalanceError: If not enough balance.
            OrderExecutionError: If order execution fails or below MIN_NOTIONAL.
        """
        price = self._last_prices.get(pair) or signal_price

        if quote_amount is not None:
            if side != TradeSide.BUY:
                raise OrderExecutionError(
                    message="quote_amount is only supported for market BUY orders",
                    pair=pair,
                    side=side.value,
                    amount=amount,
                )
            if quote_amount < MIN_NOTIONAL:
                raise OrderExecutionError(
                    message=(
                        f"Order notional {quote_amount} USDC below Bybit minimum "
                        f"{MIN_NOTIONAL} USDC for {pair}"
                    ),
                    pair=pair,
                    side=side.value,
                    amount=amount,
                )
            if price and price > 0:
                amount = self._round_amount(pair, quote_amount / price)
        else:
            amount = self._prepare_amount(pair, side, amount)
            if price:
                self._validate_min_notional(pair, amount, price)

        if self.is_paper_mode:
            return await self._paper_market_order(pair, side, amount, strategy)
        return await self._live_market_order(
            pair, side, amount, strategy, signal_price, quote_amount=quote_amount
        )

    async def _paper_market_order(
        self,
        pair: str,
        side: TradeSide,
        amount: Decimal,
        strategy: str,
    ) -> Trade:
        """Simulate a market order in paper trading mode (taker fee)."""
        price = self._last_prices.get(pair)
        if price is None:
            ticker = await self.get_ticker(pair)
            price = ticker.get("last") or Decimal("60000")

        value = amount * price
        fee = value * self._fees.taker
        base_currency, quote_currency = pair.split("/")

        if side == TradeSide.BUY:
            required = value + fee
            available = self._paper_balance.get(quote_currency, Decimal("0"))
            if available < required:
                raise InsufficientBalanceError(
                    message="Insufficient balance for paper trade",
                    required=required,
                    available=available,
                    currency=quote_currency,
                )
            self._paper_balance[quote_currency] = available - required
            self._paper_balance[base_currency] = (
                self._paper_balance.get(base_currency, Decimal("0")) + amount
            )
        else:
            available = self._paper_balance.get(base_currency, Decimal("0"))
            if available < amount:
                raise InsufficientBalanceError(
                    message="Insufficient balance for paper trade",
                    required=amount,
                    available=available,
                    currency=base_currency,
                )
            self._paper_balance[base_currency] = available - amount
            self._paper_balance[quote_currency] = (
                self._paper_balance.get(quote_currency, Decimal("0")) + value - fee
            )

        await self.persist_paper_balance()

        trade = Trade(
            id=uuid.uuid4(),
            timestamp=datetime.now(UTC),
            pair=pair,
            side=side,
            amount=amount,
            price=price,
            fee=fee,
            fee_currency=quote_currency,
            strategy=strategy,
            status=TradeStatus.FILLED,
            order_id=f"paper-{uuid.uuid4().hex[:8]}",
            notes=f"Paper trade - {self._mode_prefix}",
        )

        if self._db_manager:
            await self._save_trade(trade)

        self._stats["orders_placed"] += 1
        self._stats["orders_filled"] += 1

        await self._event_bus.publish(
            EventType.TRADE_ORDER_FILLED,
            {
                "mode": "paper",
                "trade_id": str(trade.id),
                "pair": pair,
                "side": side.value,
                "amount": str(amount),
                "price": str(price),
                "fee": str(fee),
                "strategy": strategy,
            },
        )

        logger.info(
            f"{self._mode_prefix} market_order_filled",
            pair=pair,
            side=side.value,
            amount=str(amount),
            price=str(price),
            fee=str(fee),
        )
        return trade

    async def _live_market_order(
        self,
        pair: str,
        side: TradeSide,
        amount: Decimal,
        strategy: str,
        signal_price: Decimal | None = None,
        *,
        quote_amount: Decimal | None = None,
    ) -> Trade:
        """Execute a real market order. NEVER passes ``price`` to ccxt."""
        order_side = "buy" if side == TradeSide.BUY else "sell"
        client_order_id = self._new_client_order_id()
        params: dict[str, Any] = {"clientOrderId": client_order_id}
        request_amount: float | None = float(amount)
        if quote_amount is not None:
            params["cost"] = str(quote_amount)
            request_amount = None

        try:
            await self._ensure_markets()
            self._stats["api_calls"] += 1
            self._stats["orders_placed"] += 1

            order = await self._exchange.create_order(
                pair,
                "market",
                order_side,
                request_amount,
                None,  # price: never for Bybit market orders (qty would be read as quote)
                params,
            )

            order_id = order.get("id")
            filled_amount = Decimal(str(order.get("filled") or amount))
            avg_price_raw = order.get("average") or order.get("price") or signal_price or 0
            avg_price = Decimal(str(avg_price_raw))

            fee_info = order.get("fee") or {}
            fee = Decimal(str(fee_info.get("cost") or 0))
            base_currency, quote_currency = pair.split("/")
            received = base_currency if side == TradeSide.BUY else quote_currency
            fee_currency = fee_info.get("currency") or received

            trade = Trade(
                id=uuid.uuid4(),
                timestamp=datetime.now(UTC),
                pair=pair,
                side=side,
                amount=filled_amount,
                price=avg_price,
                fee=fee,
                fee_currency=fee_currency,
                strategy=strategy,
                status=TradeStatus.FILLED,
                order_id=order_id,
                notes=f"Live trade - {self._mode_prefix} orderLinkId={client_order_id}",
            )

            if self._db_manager:
                await self._save_trade(trade)

            self._stats["orders_filled"] += 1

            await self._event_bus.publish(
                EventType.TRADE_ORDER_FILLED,
                {
                    "mode": "live",
                    "trade_id": str(trade.id),
                    "order_id": order_id,
                    "pair": pair,
                    "side": side.value,
                    "amount": str(filled_amount),
                    "price": str(avg_price),
                    "fee": str(fee),
                    "fee_currency": fee_currency,
                    "strategy": strategy,
                },
            )

            logger.info(
                f"{self._mode_prefix} market_order_filled",
                order_id=order_id,
                client_order_id=client_order_id,
                pair=pair,
                side=side.value,
                amount=str(filled_amount),
                price=str(avg_price),
            )
            return trade

        except ccxt.BaseError as e:
            self._stats["orders_failed"] += 1
            error = self._translate_error(e, pair=pair, side=side.value, amount=amount)
            logger.error(
                "bybit_rest_order_error",
                error=str(e),
                error_type=type(error).__name__,
                pair=pair,
                side=side.value,
            )
            await self._event_bus.publish(
                EventType.TRADE_ORDER_FAILED,
                {
                    "pair": pair,
                    "side": side.value,
                    "amount": str(amount),
                    "error": error.message,
                },
            )
            raise error from e

    # =========================================================================
    # Limit orders
    # =========================================================================

    async def place_limit_order(
        self,
        pair: str,
        side: TradeSide,
        amount: Decimal,
        price: Decimal,
        strategy: str = "manual",
        expires_in_seconds: int = 900,
        *,
        post_only: bool = True,
    ) -> Order:
        """Place a limit order (PostOnly by default to guarantee the maker fee).

        In paper mode: fills immediately if the price is favorable, otherwise
        creates a PENDING order. In live mode: places a real limit order; a
        PostOnly rejection (price would cross the book) is returned as a
        ``CANCELLED`` order with ``signal_metadata["reject_reason"] ==
        "post_only_would_cross"`` so the caller can re-quote.

        Args:
            pair: Trading pair (e.g., "BTC/USDC").
            side: Order side (BUY or SELL).
            amount: Order amount in base currency (rounded down to qtyStep).
            price: Limit price (rounded to tickSize, away from the market).
            strategy: Strategy name for tracking.
            expires_in_seconds: Client-side expiry (Bybit spot has no GTD).
            post_only: Use ``timeInForce=PostOnly`` (default) instead of GTC.

        Raises:
            InsufficientBalanceError: If not enough balance.
            OrderExecutionError: If order placement fails or below MIN_NOTIONAL.
        """
        amount = self._prepare_amount(pair, side, amount)
        price = self._round_price(pair, price, side)
        self._validate_min_notional(pair, amount, price)

        expires_at = datetime.now(UTC) + timedelta(seconds=expires_in_seconds)

        if self.is_paper_mode:
            return await self._paper_limit_order(pair, side, amount, price, strategy, expires_at)
        return await self._live_limit_order(
            pair, side, amount, price, strategy, expires_at, post_only=post_only
        )

    async def _paper_limit_order(
        self,
        pair: str,
        side: TradeSide,
        amount: Decimal,
        price: Decimal,
        strategy: str,
        expires_at: datetime,
    ) -> Order:
        """Simulate a limit order in paper mode (maker fee on immediate fill)."""
        current_price = self._last_prices.get(pair)
        order_id = f"paper-limit-{uuid.uuid4().hex[:8]}"

        immediate_fill = current_price is not None and (
            (side == TradeSide.BUY and price >= current_price)
            or (side == TradeSide.SELL and price <= current_price)
        )

        if immediate_fill:
            value = amount * price
            fee = value * self._fees.maker
            base_currency, quote_currency = pair.split("/")

            if side == TradeSide.BUY:
                required = value + fee
                available = self._paper_balance.get(quote_currency, Decimal("0"))
                if available < required:
                    raise InsufficientBalanceError(
                        message="Insufficient balance for paper limit order",
                        required=required,
                        available=available,
                        currency=quote_currency,
                    )
                self._paper_balance[quote_currency] = available - required
                self._paper_balance[base_currency] = (
                    self._paper_balance.get(base_currency, Decimal("0")) + amount
                )
            else:
                available = self._paper_balance.get(base_currency, Decimal("0"))
                if available < amount:
                    raise InsufficientBalanceError(
                        message="Insufficient balance for paper limit order",
                        required=amount,
                        available=available,
                        currency=base_currency,
                    )
                self._paper_balance[base_currency] = available - amount
                self._paper_balance[quote_currency] = (
                    self._paper_balance.get(quote_currency, Decimal("0")) + value - fee
                )

            await self.persist_paper_balance()

            order = Order(
                id=uuid.uuid4(),
                order_id=order_id,
                bot_id=strategy,
                pair=pair,
                side=side,
                order_type=OrderType.LIMIT,
                amount=amount,
                price=price,
                filled_amount=amount,
                filled_price=price,
                fee=fee,
                status=OrderStatus.FILLED,
                strategy=strategy,
                expires_at=expires_at,
            )
            self._stats["orders_placed"] += 1
            self._stats["orders_filled"] += 1
            logger.info(
                f"{self._mode_prefix} limit_order_filled_immediately",
                order_id=order_id,
                pair=pair,
                side=side.value,
                amount=str(amount),
                price=str(price),
                fee=str(fee),
            )
        else:
            order = Order(
                id=uuid.uuid4(),
                order_id=order_id,
                bot_id=strategy,
                pair=pair,
                side=side,
                order_type=OrderType.LIMIT,
                amount=amount,
                price=price,
                filled_amount=Decimal("0"),
                fee=Decimal("0"),
                status=OrderStatus.PENDING,
                strategy=strategy,
                expires_at=expires_at,
            )
            self._paper_orders[order_id] = {
                "order_id": order_id,
                "pair": pair,
                "side": side.value,
                "amount": str(amount),
                "price": str(price),
                "type": "limit",
                "status": "pending",
            }
            self._stats["orders_placed"] += 1
            logger.info(
                f"{self._mode_prefix} limit_order_pending",
                order_id=order_id,
                pair=pair,
                side=side.value,
                amount=str(amount),
                price=str(price),
                expires_at=expires_at.isoformat(),
            )

        if self._db_manager:
            await self._save_order(order)
        return order

    def _rejected_post_only_order(
        self,
        *,
        pair: str,
        side: TradeSide,
        amount: Decimal,
        price: Decimal,
        strategy: str,
        expires_at: datetime,
        exchange_order_id: str | None,
        client_order_id: str,
        reason: str,
    ) -> Order:
        """Build the normalised CANCELLED order returned on a PostOnly rejection."""
        logger.warning(
            f"{self._mode_prefix} limit_order_post_only_rejected",
            pair=pair,
            side=side.value,
            amount=str(amount),
            price=str(price),
            exchange_order_id=exchange_order_id,
            client_order_id=client_order_id,
            reason=reason,
        )
        return Order(
            id=uuid.uuid4(),
            order_id=exchange_order_id or client_order_id,
            bot_id=strategy,
            pair=pair,
            side=side,
            order_type=OrderType.LIMIT,
            amount=amount,
            price=price,
            filled_amount=Decimal("0"),
            fee=Decimal("0"),
            status=OrderStatus.CANCELLED,
            strategy=strategy,
            expires_at=expires_at,
            signal_metadata={
                "reject_reason": POST_ONLY_REJECT_REASON,
                "exchange_order_id": exchange_order_id,
                "client_order_id": client_order_id,
                "raw_reason": reason,
            },
        )

    async def _live_limit_order(
        self,
        pair: str,
        side: TradeSide,
        amount: Decimal,
        price: Decimal,
        strategy: str,
        expires_at: datetime,
        *,
        post_only: bool = True,
    ) -> Order:
        """Place a real limit order via ccxt (PostOnly or GTC)."""
        order_side = "buy" if side == TradeSide.BUY else "sell"
        client_order_id = self._new_client_order_id()
        params: dict[str, Any] = {
            "timeInForce": "PostOnly" if post_only else "GTC",
            "clientOrderId": client_order_id,
        }

        try:
            await self._ensure_markets()
            self._stats["api_calls"] += 1
            self._stats["orders_placed"] += 1

            ccxt_order = await self._exchange.create_order(
                pair,
                "limit",
                order_side,
                float(amount),
                float(price),
                params,
            )
            exchange_order_id = ccxt_order.get("id")

            # Bybit's create response carries no status: fetch it once so a PostOnly
            # rejection (order Rejected/Cancelled with 0 fill) is surfaced here.
            ccxt_status = ccxt_order.get("status")
            if ccxt_status is None and exchange_order_id:
                self._stats["api_calls"] += 1
                ccxt_order = await self._exchange.fetch_order(exchange_order_id, pair)
                ccxt_status = ccxt_order.get("status")

            filled_amount = Decimal(str(ccxt_order.get("filled") or 0))
            if post_only and ccxt_status in {"rejected", "canceled"} and filled_amount == 0:
                info = ccxt_order.get("info") or {}
                reason = str(
                    info.get("rejectReason") or info.get("cancelType") or ccxt_status or ""
                )
                return self._rejected_post_only_order(
                    pair=pair,
                    side=side,
                    amount=amount,
                    price=price,
                    strategy=strategy,
                    expires_at=expires_at,
                    exchange_order_id=exchange_order_id,
                    client_order_id=client_order_id,
                    reason=reason,
                )

            if ccxt_status == "closed":
                status = OrderStatus.FILLED
                avg_price: Decimal | None = Decimal(str(ccxt_order.get("average") or price))
                fee_info = ccxt_order.get("fee") or {}
                fee = Decimal(str(fee_info.get("cost") or 0))
                self._stats["orders_filled"] += 1
            elif filled_amount > 0:
                status = OrderStatus.PARTIALLY_FILLED
                avg_price = Decimal(str(ccxt_order.get("average") or price))
                fee = Decimal("0")
            else:
                status = OrderStatus.PENDING
                avg_price = None
                fee = Decimal("0")

            order = Order(
                id=uuid.uuid4(),
                order_id=exchange_order_id or client_order_id,
                bot_id=strategy,
                pair=pair,
                side=side,
                order_type=OrderType.LIMIT,
                amount=amount,
                price=price,
                filled_amount=filled_amount,
                filled_price=avg_price,
                fee=fee,
                status=status,
                strategy=strategy,
                expires_at=expires_at,
                signal_metadata={"client_order_id": client_order_id, "post_only": post_only},
            )

            if self._db_manager:
                await self._save_order(order)

            logger.info(
                f"{self._mode_prefix} limit_order_placed",
                order_id=exchange_order_id,
                client_order_id=client_order_id,
                pair=pair,
                side=side.value,
                amount=str(amount),
                price=str(price),
                time_in_force=params["timeInForce"],
                status=status.value,
            )
            return order

        except ccxt.BaseError as e:
            if post_only and self._is_post_only_rejection(e):
                return self._rejected_post_only_order(
                    pair=pair,
                    side=side,
                    amount=amount,
                    price=price,
                    strategy=strategy,
                    expires_at=expires_at,
                    exchange_order_id=None,
                    client_order_id=client_order_id,
                    reason=str(e),
                )
            self._stats["orders_failed"] += 1
            error = self._translate_error(e, pair=pair, side=side.value, amount=amount)
            logger.error(
                "bybit_rest_limit_order_error",
                error=str(e),
                error_type=type(error).__name__,
                pair=pair,
                side=side.value,
            )
            raise error from e

    # =========================================================================
    # Order status / cancel
    # =========================================================================

    async def get_order_status(self, order_id: str, pair: str | None = None) -> dict[str, Any]:
        """Get the current status of an order (``pair`` required by Bybit v5)."""
        if self.is_paper_mode:
            paper_order = self._paper_orders.get(order_id)
            if paper_order:
                return {
                    "order_id": order_id,
                    "status": paper_order.get("status", "pending"),
                    "filled": Decimal("0"),
                    "amount": Decimal(paper_order.get("amount", "0")),
                    "price": Decimal(paper_order.get("price", "0")),
                }
            return {
                "order_id": order_id,
                "status": "not_found",
                "filled": Decimal("0"),
                "amount": Decimal("0"),
            }

        try:
            await self._ensure_markets()
            self._stats["api_calls"] += 1
            order = await self._exchange.fetch_order(order_id, pair)
            fee_info = order.get("fee") or {}
            return {
                "order_id": order_id,
                "client_order_id": order.get("clientOrderId"),
                "status": order.get("status", "unknown"),
                "filled": Decimal(str(order.get("filled") or 0)),
                "amount": Decimal(str(order.get("amount") or 0)),
                "price": Decimal(str(order.get("price") or 0)),
                "average": Decimal(str(order.get("average") or order.get("price") or 0)),
                "fee": Decimal(str(fee_info.get("cost") or 0)),
                "fee_currency": fee_info.get("currency", ""),
            }
        except ccxt.BaseError as e:
            if isinstance(e, ccxt.OrderNotFound) or (
                self._extract_ret_code(e) == RET_ORDER_NOT_EXISTS
            ):
                logger.warning("bybit_order_not_found", order_id=order_id)
                return {
                    "order_id": order_id,
                    "status": "not_found",
                    "filled": Decimal("0"),
                    "amount": Decimal("0"),
                }
            logger.error("bybit_get_order_status_error", error=str(e), order_id=order_id)
            raise self._translate_error(e, order_id=order_id, context="order_status") from e

    async def cancel_order(self, order_id: str, pair: str | None = None) -> bool:
        """Cancel an open order. Returns False if the order no longer exists."""
        if self.is_paper_mode:
            if order_id in self._paper_orders:
                del self._paper_orders[order_id]
                logger.info(f"{self._mode_prefix} order_cancelled", order_id=order_id)
                await self._event_bus.publish(
                    EventType.TRADE_ORDER_CANCELLED,
                    {"order_id": order_id, "mode": "paper"},
                )
                return True
            logger.warning(f"{self._mode_prefix} cancel_order_not_found", order_id=order_id)
            return False

        try:
            await self._ensure_markets()
            self._stats["api_calls"] += 1
            await self._exchange.cancel_order(order_id, pair)
            logger.info(f"{self._mode_prefix} order_cancelled", order_id=order_id)
            await self._event_bus.publish(
                EventType.TRADE_ORDER_CANCELLED,
                {"order_id": order_id, "mode": "live"},
            )
            return True
        except ccxt.BaseError as e:
            if isinstance(e, ccxt.OrderNotFound) or (
                self._extract_ret_code(e) == RET_ORDER_NOT_EXISTS
            ):
                logger.warning("bybit_rest_cancel_not_found", order_id=order_id)
                return False
            logger.error("bybit_rest_cancel_error", error=str(e), order_id=order_id)
            raise self._translate_error(e, order_id=order_id, context="cancel") from e

    # =========================================================================
    # Margin (not supported — spot only)
    # =========================================================================

    async def place_margin_order(
        self,
        pair: str,
        side: TradeSide,
        amount: Decimal,
        strategy: str = "manual",
        signal_price: Decimal | None = None,
        leverage: int = 2,
    ) -> Trade:
        """Not supported — spot only."""
        raise NotImplementedError("Bybit margin trading not supported (spot only)")

    async def get_margin_balance(self) -> dict[str, Decimal]:
        """Return empty margin balance (spot only)."""
        return {
            "total_margin": Decimal("0"),
            "used_margin": Decimal("0"),
            "available_margin": Decimal("0"),
        }

    async def get_open_margin_positions(self) -> list[dict[str, Any]]:
        """Return empty list (spot only)."""
        return []

    # =========================================================================
    # Paper trading helpers
    # =========================================================================

    async def initialize_paper_balance(self, force_reset: bool = False) -> None:
        """Initialize paper balance from DB or from the real Bybit balance.

        First startup (empty DB): fetch the real balance (if keys) or default to
        1000 USDC. Subsequent startups: load from DB.
        """
        if not self.is_paper_mode:
            return
        if not self._db_manager:
            logger.warning("paper_balance_init_no_db_manager")
            return

        if not force_reset:
            loaded = await self._load_paper_balance_from_db()
            if loaded:
                logger.info("paper_balance_loaded_from_db", balance=str(self._paper_balance))
                return

        real_balance = await self._fetch_real_balance()
        base, quote = self._settings.trading.pair.split("/")

        if real_balance:
            base_amount = real_balance.get(base, Decimal("0"))
            quote_amount = real_balance.get(quote, Decimal("0"))
        else:
            base_amount = Decimal("0")
            quote_amount = Decimal("1000")

        self._paper_balance = {base: base_amount, quote: quote_amount}
        await self._save_paper_balance_to_db(initial=True)

        logger.info(
            "paper_balance_initialized",
            base=str(base_amount),
            base_currency=base,
            quote=str(quote_amount),
            quote_currency=quote,
        )

    async def persist_paper_balance(self) -> None:
        """Persist current paper balance to DB after a trade."""
        if self._db_manager:
            await self._save_paper_balance_to_db(initial=False)

    async def set_paper_balance(self, currency: str, amount: Decimal) -> None:
        """Set paper trading balance for a currency and persist to DB."""
        if not self.is_paper_mode:
            logger.warning("set_paper_balance_not_paper_mode")
            return
        self._paper_balance[currency] = amount
        await self.persist_paper_balance()
        logger.info(f"{self._mode_prefix} set_balance", currency=currency, amount=str(amount))

    def get_paper_balance(self) -> dict[str, Decimal]:
        """Get current paper trading balance."""
        return self._paper_balance.copy()

    def remove_paper_order(self, order_id: str) -> None:
        """Remove a tracked paper order from the in-memory exchange state."""
        self._paper_orders.pop(order_id, None)

    # =========================================================================
    # Internal helpers
    # =========================================================================

    async def _fetch_real_balance(self) -> dict[str, Decimal]:
        """Fetch the real Bybit balance (even in paper mode); empty dict on failure."""
        if not self._settings.bybit.credentials(self._key_role)[0]:
            logger.info("no_bybit_api_key_for_real_balance", key_role=self._key_role)
            return {}
        try:
            await self._ensure_markets()
            self._stats["api_calls"] += 1
            balance = await self._exchange.fetch_balance()
            result = self._parse_free_balance(balance)
            logger.info("real_balance_fetched_for_paper", currencies=list(result.keys()))
            return result
        except Exception as e:
            logger.error(
                "real_balance_fetch_failed",
                error=str(e),
                error_type=type(e).__name__,
            )
            return {}

    async def _load_paper_balance_from_db(self) -> bool:
        """Load paper balance from the paper_balance table."""
        from krakenbot.models.trades import PaperBalance

        if not self._db_manager:
            return False
        try:
            from sqlalchemy import select

            async with self._db_manager.session() as session:
                result = await session.execute(select(PaperBalance))
                rows = result.scalars().all()
                if not rows:
                    return False
                loaded_balance: dict[str, Decimal] = {}
                for row in rows:
                    loaded_balance[row.currency] = (
                        loaded_balance.get(row.currency, Decimal("0")) + row.amount
                    )
                self._paper_balance = loaded_balance
                return True
        except Exception as e:
            logger.error("load_paper_balance_db_error", error=str(e))
            return False

    async def _save_paper_balance_to_db(self, initial: bool = False) -> None:
        """Save current paper balance to the paper_balance table."""
        from krakenbot.models.trades import PaperBalance

        if not self._db_manager:
            return
        try:
            async with self._db_manager.session() as session:
                for currency, amount in self._paper_balance.items():
                    existing = await session.get(PaperBalance, currency)
                    if existing:
                        existing.amount = amount
                        existing.updated_at = datetime.now(UTC)
                        if initial:
                            existing.initial_amount = amount
                    else:
                        session.add(
                            PaperBalance(
                                currency=currency,
                                amount=amount,
                                initial_amount=amount if initial else Decimal("0"),
                            )
                        )
        except Exception as e:
            logger.error("save_paper_balance_db_error", error=str(e))

    async def _save_trade(self, trade: Trade) -> None:
        """Save trade to database."""
        if not self._db_manager:
            return
        try:
            async with self._db_manager.session() as session:
                session.add(trade)
        except Exception as e:
            logger.error("bybit_rest_save_trade_error", error=str(e), trade_id=str(trade.id))

    async def _save_order(self, order: Order) -> None:
        """Save order to database."""
        if not self._db_manager:
            return
        try:
            async with self._db_manager.session() as session:
                session.add(order)
        except Exception as e:
            logger.error("save_order_error", error=str(e), order_id=order.order_id)
