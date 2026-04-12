"""Kraken REST API client for trading operations.

This module provides an async REST client for interacting with the Kraken
exchange API. It uses the ccxt library for simplified API access and
handles authentication, rate limiting, and error management.

Features:
    - Account balance queries
    - Market order placement
    - Order management (query, cancel)
    - Paper trading mode simulation
    - Rate limiting
    - Comprehensive error handling

Trading Modes:
    - PAPER: Simulates trades without calling the real API
    - LIVE: Executes real trades (requires explicit confirmation)

Documentation:
    https://docs.kraken.com/rest/

Example:
    >>> from krakenbot.connectors.kraken.rest import KrakenRestClient
    >>> client = KrakenRestClient(settings, event_bus)
    >>> balance = await client.get_balance()
    >>> trade = await client.place_market_order("XBT/EUR", TradeSide.BUY, Decimal("0.001"))
    >>> await client.close()
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import TYPE_CHECKING, Any
import uuid

import ccxt.async_support as ccxt

from krakenbot.config.settings import TradingMode
from krakenbot.core.event_bus import EventBus, EventType
from krakenbot.core.exceptions import (
    InsufficientBalanceError,
    KrakenAPIError,
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


# Pair name mapping from standard to Kraken format (CCXT normalized symbols)
# CCXT uses BTC instead of XBT for Kraken
PAIR_TO_KRAKEN = {
    "XBT/EUR": "BTC/EUR",
    "BTC/EUR": "BTC/EUR",
    "XBT/USD": "BTC/USD",
    "BTC/USD": "BTC/USD",
    "XBT/USDC": "BTC/USDC",
    "BTC/USDC": "BTC/USDC",
    "XBT/USDT": "BTC/USDT",
    "BTC/USDT": "BTC/USDT",
    "ETH/EUR": "ETH/EUR",
    "ETH/USD": "ETH/USD",
    "ETH/USDC": "ETH/USDC",
    "ETH/USDT": "ETH/USDT",
}

# Minimum order sizes (in base currency)
MIN_ORDER_SIZE = {
    "XBT/EUR": Decimal("0.0001"),
    "XBT/USD": Decimal("0.0001"),
    "ETH/EUR": Decimal("0.001"),
    "ETH/USD": Decimal("0.001"),
}


def normalize_asset_symbol(asset: str) -> str:
    """Return the canonical asset symbol used by paper balances."""
    return "BTC" if asset in ("BTC", "XBT") else asset


def normalize_asset_balances(balance: dict[str, Decimal]) -> dict[str, Decimal]:
    """Merge asset aliases so paper balances keep a single canonical key."""
    normalized: dict[str, Decimal] = {}
    for asset, amount in balance.items():
        canonical_asset = normalize_asset_symbol(asset)
        normalized[canonical_asset] = normalized.get(canonical_asset, Decimal("0")) + amount
    return normalized


class KrakenRestClient:
    """Async REST client for Kraken API using ccxt.

    This client handles all REST API interactions with Kraken including
    balance queries and order management. It supports both paper trading
    (simulation) and live trading modes.

    Attributes:
        settings: Application settings.
        event_bus: Event bus for publishing events.
        db_manager: Database manager for trade persistence (optional).

    Example:
        >>> client = KrakenRestClient(settings, event_bus, db_manager)
        >>> balance = await client.get_balance()
        >>> print(f"EUR balance: {balance.get('EUR', 0)}")
    """

    def __init__(
        self,
        settings: Settings,
        event_bus: EventBus,
        db_manager: DatabaseManager | None = None,
    ) -> None:
        """Initialize the REST client.

        Args:
            settings: Application settings.
            event_bus: Event bus for publishing events.
            db_manager: Database manager for trade persistence.
        """
        self._settings = settings
        self._event_bus = event_bus
        self._db_manager = db_manager

        # Trading mode prefix for logging
        self._mode_prefix = "[PAPER]" if settings.trading.mode == TradingMode.PAPER else "[LIVE]"

        # Initialize ccxt exchange
        self._exchange = ccxt.kraken(
            {
                "apiKey": settings.kraken.api_key.get_secret_value(),
                "secret": settings.kraken.api_secret.get_secret_value(),
                "enableRateLimit": True,
                "rateLimit": 1000,  # 1 request per second default
            }
        )

        # Paper trading state — populated by initialize_paper_balance() at startup
        pair = settings.trading.pair
        _base = pair.split("/")[0]
        _quote = pair.split("/")[1]
        _base_norm = normalize_asset_symbol(_base)
        self._paper_balance: dict[str, Decimal] = {
            _quote: Decimal("0"),
            _base_norm: Decimal("0"),
        }
        self._paper_orders: dict[str, dict[str, Any]] = {}

        # Paper margin trading state
        self._paper_margin_balance: Decimal = Decimal("500.00")
        self._paper_margin_positions: list[dict[str, Any]] = []
        self._paper_margin_used: Decimal = Decimal("0")

        # Last known price for paper trading simulation
        self._last_prices: dict[str, Decimal] = {}

        # Statistics
        self._stats = {
            "orders_placed": 0,
            "orders_filled": 0,
            "orders_failed": 0,
            "api_calls": 0,
        }

        logger.info(
            "kraken_rest_initialized",
            mode=settings.trading.mode.value,
            has_api_key=bool(settings.kraken.api_key.get_secret_value()),
        )

    @property
    def exchange_name(self) -> str:
        """Return the canonical exchange identifier for this client."""
        return "kraken"

    @property
    def is_paper_mode(self) -> bool:
        """Check if running in paper trading mode.

        Returns:
            True if paper trading mode.
        """
        return self._settings.trading.mode == TradingMode.PAPER

    @property
    def stats(self) -> dict[str, int]:
        """Get client statistics.

        Returns:
            Dictionary of statistics.
        """
        return self._stats.copy()

    @property
    def paper_balance(self) -> dict[str, Decimal]:
        """Expose the mutable paper balance for runtime paper-fill simulation."""
        self._normalize_paper_balance()
        return self._paper_balance

    async def close(self) -> None:
        """Close the ccxt exchange connection.

        Should be called during application shutdown.
        """
        await self._exchange.close()
        logger.info("kraken_rest_closed")

    def update_last_price(self, pair: str, price: Decimal) -> None:
        """Update the last known price for a pair.

        Used by paper trading to simulate order execution at current price.

        Args:
            pair: Trading pair.
            price: Current price.
        """
        self._last_prices[pair] = price

    def _normalize_paper_balance(self) -> None:
        """Collapse asset aliases in the in-memory paper balance."""
        self._paper_balance = normalize_asset_balances(self._paper_balance)

    async def get_balance(self) -> dict[str, Decimal]:
        """Get account balance.

        Returns:
            Dictionary mapping currency to available balance.

        Raises:
            KrakenAPIError: If API call fails.

        Example:
            >>> balance = await client.get_balance()
            >>> print(f"EUR: {balance['EUR']}, XBT: {balance.get('XBT', 0)}")
        """
        if self.is_paper_mode:
            self._normalize_paper_balance()
            logger.info(
                f"{self._mode_prefix} get_balance",
                balance=str(self._paper_balance),
            )
            return self._paper_balance.copy()

        try:
            self._stats["api_calls"] += 1
            balance = await self._exchange.fetch_balance()

            # Extract free (available) balances
            result: dict[str, Decimal] = {}
            for currency, amounts in balance.get("free", {}).items():
                if amounts and float(amounts) > 0:
                    result[currency] = Decimal(str(amounts))

            logger.info(
                f"{self._mode_prefix} get_balance",
                currencies=list(result.keys()),
            )

            return result

        except ccxt.ExchangeError as e:
            logger.error(
                "kraken_rest_balance_error",
                error=str(e),
            )
            raise KrakenAPIError(
                message=f"Failed to fetch balance: {e}",
                response={"error": str(e)},
            ) from e

    async def get_ticker(self, pair: str) -> dict[str, Any]:
        """Get current ticker information for a pair.

        Args:
            pair: Trading pair (e.g., "XBT/EUR").

        Returns:
            Ticker data including bid, ask, last price, volume.

        Raises:
            KrakenAPIError: If API call fails.
        """
        kraken_pair = PAIR_TO_KRAKEN.get(pair, pair)

        try:
            self._stats["api_calls"] += 1
            ticker = await self._exchange.fetch_ticker(kraken_pair)

            # Update last price for paper trading
            if ticker.get("last"):
                self._last_prices[pair] = Decimal(str(ticker["last"]))

            return {
                "pair": pair,
                "bid": Decimal(str(ticker.get("bid", 0))) if ticker.get("bid") else None,
                "ask": Decimal(str(ticker.get("ask", 0))) if ticker.get("ask") else None,
                "last": Decimal(str(ticker.get("last", 0))) if ticker.get("last") else None,
                "volume": Decimal(str(ticker.get("baseVolume", 0)))
                if ticker.get("baseVolume")
                else None,
                "high": Decimal(str(ticker.get("high", 0))) if ticker.get("high") else None,
                "low": Decimal(str(ticker.get("low", 0))) if ticker.get("low") else None,
                "timestamp": ticker.get("timestamp"),
            }

        except ccxt.ExchangeError as e:
            logger.error(
                "kraken_rest_ticker_error",
                error=str(e),
                pair=pair,
            )
            raise KrakenAPIError(
                message=f"Failed to fetch ticker: {e}",
                response={"error": str(e), "pair": pair},
            ) from e

    async def place_market_order(
        self,
        pair: str,
        side: TradeSide,
        amount: Decimal,
        strategy: str = "manual",
        signal_price: Decimal | None = None,
    ) -> Trade:
        """Place a market order.

        In paper mode, simulates the order execution.
        In live mode, places a real market order.

        Args:
            pair: Trading pair (e.g., "XBT/EUR").
            side: Order side (BUY or SELL).
            amount: Order amount in base currency.
            strategy: Strategy name for tracking.

        Returns:
            Trade object representing the executed order.

        Raises:
            InsufficientBalanceError: If not enough balance.
            OrderExecutionError: If order execution fails.
            KrakenAPIError: If API call fails.

        Example:
            >>> trade = await client.place_market_order(
            ...     "XBT/EUR",
            ...     TradeSide.BUY,
            ...     Decimal("0.001"),
            ...     strategy="threshold"
            ... )
            >>> print(f"Executed at {trade.price}")
        """
        kraken_pair = PAIR_TO_KRAKEN.get(pair, pair)

        # Validate minimum order size
        min_size = MIN_ORDER_SIZE.get(pair, Decimal("0.0001"))
        if amount < min_size:
            raise OrderExecutionError(
                message=f"Order amount below minimum ({min_size})",
                pair=pair,
                side=side.value,
                amount=amount,
            )

        if self.is_paper_mode:
            return await self._paper_market_order(pair, side, amount, strategy)
        else:
            return await self._live_market_order(kraken_pair, side, amount, strategy, signal_price)

    async def _paper_market_order(
        self,
        pair: str,
        side: TradeSide,
        amount: Decimal,
        strategy: str,
    ) -> Trade:
        """Simulate a market order in paper trading mode.

        Args:
            pair: Trading pair.
            side: Order side.
            amount: Order amount.
            strategy: Strategy name.

        Returns:
            Simulated Trade object.
        """
        # Get current price
        price = self._last_prices.get(pair)
        if price is None:
            # Fetch current price if not available
            ticker = await self.get_ticker(pair)
            price = ticker.get("last") or Decimal("42000")  # Fallback price

        # Calculate order value
        value = amount * price
        fee = value * Decimal("0.0026")  # Kraken maker/taker fee ~0.26%

        # Get currency symbols
        self._normalize_paper_balance()
        base_currency = normalize_asset_symbol(pair.split("/")[0])
        quote_currency = pair.split("/")[1]

        # Check balance
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
            # Update paper balance
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
            # Update paper balance
            self._paper_balance[base_currency] = available - amount
            self._paper_balance[quote_currency] = (
                self._paper_balance.get(quote_currency, Decimal("0")) + value - fee
            )

        # Persist paper balance to DB
        await self.persist_paper_balance()

        # Create trade record
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

        # Save to database if available
        if self._db_manager:
            await self._save_trade(trade)

        self._stats["orders_placed"] += 1
        self._stats["orders_filled"] += 1

        # Publish event
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
    ) -> Trade:
        """Execute a real market order.

        Args:
            pair: Trading pair.
            side: Order side.
            amount: Order amount.
            strategy: Strategy name.

        Returns:
            Trade object with execution details.
        """
        try:
            self._stats["api_calls"] += 1
            self._stats["orders_placed"] += 1

            # Place order via ccxt
            order_side = "buy" if side == TradeSide.BUY else "sell"
            order = await self._exchange.create_market_order(
                pair,
                order_side,
                float(amount),
            )

            # Parse order response - use 'or' to handle None values
            order_id = order.get("id")
            filled_raw = order.get("filled") or amount
            filled_amount = Decimal(str(filled_raw))
            # Use signal_price as fallback before 0 to avoid DivisionByZero
            avg_price_raw = order.get("average") or order.get("price") or signal_price or 0
            avg_price = Decimal(str(avg_price_raw))

            # Calculate fee - handle None values
            fee_info = order.get("fee") or {}
            fee_cost = fee_info.get("cost") if fee_info else 0
            fee = Decimal(str(fee_cost or 0))
            fee_currency = fee_info.get("currency", "EUR") if fee_info else "EUR"

            # Create trade record
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
                notes=f"Live trade - {self._mode_prefix}",
            )

            # Save to database if available
            if self._db_manager:
                await self._save_trade(trade)

            self._stats["orders_filled"] += 1

            # Publish event
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
                    "strategy": strategy,
                },
            )

            logger.info(
                f"{self._mode_prefix} market_order_filled",
                order_id=order_id,
                pair=pair,
                side=side.value,
                amount=str(filled_amount),
                price=str(avg_price),
            )

            return trade

        except ccxt.InsufficientFunds as e:
            self._stats["orders_failed"] += 1
            logger.error(
                "kraken_rest_insufficient_funds",
                error=str(e),
                pair=pair,
                amount=str(amount),
            )

            await self._event_bus.publish(
                EventType.TRADE_ORDER_FAILED,
                {
                    "pair": pair,
                    "side": side.value,
                    "amount": str(amount),
                    "error": "Insufficient funds",
                },
            )

            raise InsufficientBalanceError(
                message=f"Insufficient funds: {e}",
            ) from e

        except ccxt.RateLimitExceeded as e:
            self._stats["orders_failed"] += 1
            logger.error(
                "kraken_rest_rate_limit",
                error=str(e),
            )
            raise RateLimitError(
                message=f"Rate limit exceeded: {e}",
            ) from e

        except ccxt.ExchangeError as e:
            self._stats["orders_failed"] += 1
            logger.error(
                "kraken_rest_order_error",
                error=str(e),
                pair=pair,
                side=side.value,
            )

            await self._event_bus.publish(
                EventType.TRADE_ORDER_FAILED,
                {
                    "pair": pair,
                    "side": side.value,
                    "amount": str(amount),
                    "error": str(e),
                },
            )

            raise OrderExecutionError(
                message=f"Order execution failed: {e}",
                pair=pair,
                side=side.value,
                amount=amount,
            ) from e

    # =========================================================================
    # Margin Trading Methods
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
        """Place a margin order (for short selling).

        For shorts: SELL opens the position (borrow + sell BTC),
        BUY closes it (buy BTC + repay).

        Args:
            pair: Trading pair (e.g., "XBT/USDC").
            side: Order side (SELL to open short, BUY to close short).
            amount: Order amount in base currency.
            strategy: Strategy name for tracking.
            signal_price: Expected price (fallback).
            leverage: Leverage level (default 2x).

        Returns:
            Trade object representing the executed margin order.

        Raises:
            InsufficientBalanceError: If not enough margin.
            OrderExecutionError: If order execution fails.
        """
        kraken_pair = PAIR_TO_KRAKEN.get(pair, pair)

        # Validate minimum order size
        min_size = MIN_ORDER_SIZE.get(pair, Decimal("0.0001"))
        if amount < min_size:
            raise OrderExecutionError(
                message=f"Order amount below minimum ({min_size})",
                pair=pair,
                side=side.value,
                amount=amount,
            )

        if self.is_paper_mode:
            return await self._paper_margin_order(pair, side, amount, strategy, leverage)
        else:
            return await self._live_margin_order(
                kraken_pair, side, amount, strategy, signal_price, leverage
            )

    async def _paper_margin_order(
        self,
        pair: str,
        side: TradeSide,
        amount: Decimal,
        strategy: str,
        leverage: int,
    ) -> Trade:
        """Simulate a margin order in paper trading mode.

        Args:
            pair: Trading pair.
            side: Order side (SELL to open, BUY to close).
            amount: Order amount in base currency.
            strategy: Strategy name.
            leverage: Leverage level.

        Returns:
            Simulated Trade object.
        """
        # Get current price
        price = self._last_prices.get(pair)
        if price is None:
            ticker = await self.get_ticker(pair)
            price = ticker.get("last") or Decimal("42000")

        value = amount * price
        fee = value * Decimal("0.0026")  # Same fee as spot
        quote_currency = pair.split("/")[1]

        if side == TradeSide.SELL:
            # Opening a short: lock margin collateral
            margin_required = value / Decimal(str(leverage))
            available_margin = self._paper_margin_balance - self._paper_margin_used
            if available_margin < margin_required:
                raise InsufficientBalanceError(
                    message="Insufficient margin for paper short",
                    required=margin_required,
                    available=available_margin,
                    currency=quote_currency,
                )
            self._paper_margin_used += margin_required
            self._paper_margin_positions.append(
                {
                    "pair": pair,
                    "amount": amount,
                    "entry_price": price,
                    "leverage": leverage,
                    "margin_required": margin_required,
                    "strategy": strategy,
                }
            )
        elif side == TradeSide.BUY:
            # Closing a short: find matching position, release margin
            closed = False
            for i, pos in enumerate(self._paper_margin_positions):
                if pos["pair"] == pair and pos["strategy"] == strategy:
                    self._paper_margin_used -= pos["margin_required"]
                    # PnL: entry sold high, now buying back (hopefully lower)
                    pnl = (pos["entry_price"] - price) * pos["amount"] - fee
                    self._paper_margin_balance += pnl
                    self._paper_margin_positions.pop(i)
                    closed = True
                    break
            if not closed:
                raise OrderExecutionError(
                    message="No matching margin position to close",
                    pair=pair,
                    side=side.value,
                    amount=amount,
                )

        # Create trade record
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
            order_id=f"paper-margin-{uuid.uuid4().hex[:8]}",
            notes=f"Paper margin trade - {self._mode_prefix}",
            trading_mode="margin",
        )

        # Save to database if available
        if self._db_manager:
            await self._save_trade(trade)

        self._stats["orders_placed"] += 1
        self._stats["orders_filled"] += 1

        # Publish event
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
                "trading_mode": "margin",
            },
        )

        logger.info(
            f"{self._mode_prefix} margin_order_filled",
            pair=pair,
            side=side.value,
            amount=str(amount),
            price=str(price),
            fee=str(fee),
            leverage=leverage,
        )

        return trade

    async def _live_margin_order(
        self,
        pair: str,
        side: TradeSide,
        amount: Decimal,
        strategy: str,
        signal_price: Decimal | None,
        leverage: int,
    ) -> Trade:
        """Execute a real margin order via Kraken API.

        Args:
            pair: Trading pair (Kraken format).
            side: Order side.
            amount: Order amount in base currency.
            strategy: Strategy name.
            signal_price: Expected price (fallback).
            leverage: Leverage level.

        Returns:
            Trade object with execution details.
        """
        try:
            self._stats["api_calls"] += 1
            self._stats["orders_placed"] += 1

            order_side = "buy" if side == TradeSide.BUY else "sell"
            order = await self._exchange.create_market_order(
                pair,
                order_side,
                float(amount),
                params={"leverage": leverage},
            )

            # Parse order response
            order_id = order.get("id")
            filled_raw = order.get("filled") or amount
            filled_amount = Decimal(str(filled_raw))
            avg_price_raw = order.get("average") or order.get("price") or signal_price or 0
            avg_price = Decimal(str(avg_price_raw))

            fee_info = order.get("fee") or {}
            fee_cost = fee_info.get("cost") if fee_info else 0
            fee = Decimal(str(fee_cost or 0))
            fee_currency = fee_info.get("currency", "USDC") if fee_info else "USDC"

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
                notes=f"Live margin trade - {self._mode_prefix}",
                trading_mode="margin",
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
                    "strategy": strategy,
                    "trading_mode": "margin",
                },
            )

            logger.info(
                f"{self._mode_prefix} margin_order_filled",
                order_id=order_id,
                pair=pair,
                side=side.value,
                amount=str(filled_amount),
                price=str(avg_price),
                leverage=leverage,
            )

            return trade

        except ccxt.InsufficientFunds as e:
            self._stats["orders_failed"] += 1
            logger.error(
                "kraken_rest_margin_insufficient_funds",
                error=str(e),
                pair=pair,
                amount=str(amount),
            )
            raise InsufficientBalanceError(
                message=f"Insufficient margin funds: {e}",
            ) from e

        except ccxt.ExchangeError as e:
            self._stats["orders_failed"] += 1
            logger.error(
                "kraken_rest_margin_order_error",
                error=str(e),
                pair=pair,
                side=side.value,
            )
            raise OrderExecutionError(
                message=f"Margin order execution failed: {e}",
                pair=pair,
                side=side.value,
                amount=amount,
            ) from e

    async def get_margin_balance(self) -> dict[str, Decimal]:
        """Get margin balance information.

        Returns:
            Dictionary with total_margin, used_margin, available_margin.
        """
        if self.is_paper_mode:
            return {
                "total_margin": self._paper_margin_balance,
                "used_margin": self._paper_margin_used,
                "available_margin": self._paper_margin_balance - self._paper_margin_used,
            }

        try:
            self._stats["api_calls"] += 1
            balance = await self._exchange.fetch_balance(params={"type": "margin"})
            total = Decimal(str(balance.get("total", {}).get("USDC", 0)))
            used = Decimal(str(balance.get("used", {}).get("USDC", 0)))
            return {
                "total_margin": total,
                "used_margin": used,
                "available_margin": total - used,
            }
        except ccxt.ExchangeError as e:
            logger.error("kraken_rest_margin_balance_error", error=str(e))
            raise KrakenAPIError(message=f"Failed to fetch margin balance: {e}") from e

    async def get_open_margin_positions(self) -> list[dict[str, Any]]:
        """Get currently open margin positions.

        Returns:
            List of open margin position dictionaries.
        """
        if self.is_paper_mode:
            return self._paper_margin_positions.copy()

        try:
            self._stats["api_calls"] += 1
            positions = await self._exchange.fetch_positions()
            return [
                {
                    "pair": p.get("symbol", ""),
                    "amount": Decimal(str(p.get("contracts", 0))),
                    "entry_price": Decimal(str(p.get("entryPrice", 0))),
                    "leverage": p.get("leverage", 2),
                    "unrealized_pnl": Decimal(str(p.get("unrealizedPnl", 0))),
                }
                for p in positions
                if p.get("contracts", 0) != 0
            ]
        except ccxt.ExchangeError as e:
            logger.error("kraken_rest_margin_positions_error", error=str(e))
            raise KrakenAPIError(message=f"Failed to fetch margin positions: {e}") from e

    async def get_open_orders(self, pair: str | None = None) -> list[dict[str, Any]]:
        """Get open orders.

        Args:
            pair: Filter by trading pair, or None for all.

        Returns:
            List of open order dictionaries.

        Raises:
            KrakenAPIError: If API call fails.
        """
        if self.is_paper_mode:
            orders = list(self._paper_orders.values())
            if pair:
                orders = [o for o in orders if o.get("pair") == pair]
            logger.info(
                f"{self._mode_prefix} get_open_orders",
                count=len(orders),
            )
            return orders

        try:
            self._stats["api_calls"] += 1
            kraken_pair = PAIR_TO_KRAKEN.get(pair, pair) if pair else None
            orders = await self._exchange.fetch_open_orders(kraken_pair)

            result = []
            for order in orders:
                result.append(
                    {
                        "order_id": order.get("id"),
                        "pair": order.get("symbol"),
                        "side": order.get("side"),
                        "amount": Decimal(str(order.get("amount", 0))),
                        "filled": Decimal(str(order.get("filled", 0))),
                        "price": Decimal(str(order.get("price", 0)))
                        if order.get("price")
                        else None,
                        "status": order.get("status"),
                        "timestamp": order.get("timestamp"),
                    }
                )

            logger.info(
                f"{self._mode_prefix} get_open_orders",
                count=len(result),
            )

            return result

        except ccxt.ExchangeError as e:
            logger.error(
                "kraken_rest_open_orders_error",
                error=str(e),
            )
            raise KrakenAPIError(
                message=f"Failed to fetch open orders: {e}",
            ) from e

    async def cancel_order(self, order_id: str, pair: str | None = None) -> bool:
        """Cancel an open order.

        Args:
            order_id: Order ID to cancel.
            pair: Trading pair (required by some exchanges).

        Returns:
            True if successfully cancelled.

        Raises:
            OrderCancelError: If cancellation fails.
            KrakenAPIError: If API call fails.
        """
        if self.is_paper_mode:
            if order_id in self._paper_orders:
                del self._paper_orders[order_id]
                logger.info(
                    f"{self._mode_prefix} order_cancelled",
                    order_id=order_id,
                )

                await self._event_bus.publish(
                    EventType.TRADE_ORDER_CANCELLED,
                    {"order_id": order_id, "mode": "paper"},
                )
                return True
            else:
                logger.warning(
                    f"{self._mode_prefix} cancel_order_not_found",
                    order_id=order_id,
                )
                return False

        try:
            self._stats["api_calls"] += 1
            await self._exchange.cancel_order(order_id, pair)

            logger.info(
                f"{self._mode_prefix} order_cancelled",
                order_id=order_id,
            )

            await self._event_bus.publish(
                EventType.TRADE_ORDER_CANCELLED,
                {"order_id": order_id, "mode": "live"},
            )

            return True

        except ccxt.OrderNotFound:
            logger.warning(
                "kraken_rest_cancel_not_found",
                order_id=order_id,
            )
            return False

        except ccxt.ExchangeError as e:
            logger.error(
                "kraken_rest_cancel_error",
                error=str(e),
                order_id=order_id,
            )
            raise OrderCancelError(
                message=f"Failed to cancel order: {e}",
                order_id=order_id,
            ) from e

    async def place_limit_order(
        self,
        pair: str,
        side: TradeSide,
        amount: Decimal,
        price: Decimal,
        strategy: str = "manual",
        expires_in_seconds: int = 900,
    ) -> Order:
        """Place a limit order.

        In paper mode: fills immediately if price is favorable,
        otherwise creates a PENDING order.
        In live mode: places a real limit order via ccxt.

        Args:
            pair: Trading pair (e.g., "XBT/USDC").
            side: Order side (BUY or SELL).
            amount: Order amount in base currency.
            price: Limit price.
            strategy: Strategy name for tracking.
            expires_in_seconds: Auto-cancel after this many seconds.

        Returns:
            Order object with current status.

        Raises:
            InsufficientBalanceError: If not enough balance (paper mode).
            OrderExecutionError: If order placement fails.
            KrakenAPIError: If API call fails (live mode).
        """
        kraken_pair = PAIR_TO_KRAKEN.get(pair, pair)

        # Validate minimum order size
        min_size = MIN_ORDER_SIZE.get(pair, Decimal("0.0001"))
        if amount < min_size:
            raise OrderExecutionError(
                message=f"Order amount below minimum ({min_size})",
                pair=pair,
                side=side.value,
                amount=amount,
            )

        expires_at = datetime.now(UTC) + timedelta(seconds=expires_in_seconds)

        if self.is_paper_mode:
            return await self._paper_limit_order(pair, side, amount, price, strategy, expires_at)
        else:
            return await self._live_limit_order(
                kraken_pair, pair, side, amount, price, strategy, expires_at
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
        """Simulate a limit order in paper mode.

        Fills immediately if price is favorable (BUY at price >= current,
        SELL at price <= current), otherwise creates PENDING order.

        Args:
            pair: Trading pair.
            side: Order side.
            amount: Order amount.
            price: Limit price.
            strategy: Strategy name.
            expires_at: Order expiry time.

        Returns:
            Order object (FILLED or PENDING).
        """
        current_price = self._last_prices.get(pair)
        order_id = f"paper-limit-{uuid.uuid4().hex[:8]}"

        # Check if order should fill immediately
        immediate_fill = False
        if current_price is not None:
            if side == TradeSide.BUY and price >= current_price:
                immediate_fill = True
            elif side == TradeSide.SELL and price <= current_price:
                immediate_fill = True

        if immediate_fill:
            # Check balance for immediate fill
            value = amount * price
            fee = value * Decimal("0.0016")  # Maker fee ~0.16%
            quote_currency = pair.split("/")[1]
            self._normalize_paper_balance()
            base_currency = normalize_asset_symbol(pair.split("/")[0])

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

            # Persist paper balance to DB
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
            # Create PENDING order
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

            # Track in paper orders for cancel support
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

        # Save to database if available
        if self._db_manager:
            await self._save_order(order)

        return order

    async def _live_limit_order(
        self,
        kraken_pair: str,
        original_pair: str,
        side: TradeSide,
        amount: Decimal,
        price: Decimal,
        strategy: str,
        expires_at: datetime,
    ) -> Order:
        """Place a real limit order via ccxt.

        Args:
            kraken_pair: Kraken-format trading pair.
            original_pair: Original pair format.
            side: Order side.
            amount: Order amount.
            price: Limit price.
            strategy: Strategy name.
            expires_at: Order expiry time.

        Returns:
            Order object with exchange order ID.
        """
        try:
            self._stats["api_calls"] += 1
            self._stats["orders_placed"] += 1

            order_side = "buy" if side == TradeSide.BUY else "sell"
            ccxt_order = await self._exchange.create_limit_order(
                kraken_pair,
                order_side,
                float(amount),
                float(price),
            )

            exchange_order_id = ccxt_order.get("id", f"kraken-{uuid.uuid4().hex[:8]}")

            # Check if already filled (rare for limit orders)
            ccxt_status = ccxt_order.get("status", "open")
            filled_raw = ccxt_order.get("filled") or Decimal("0")
            filled_amount = Decimal(str(filled_raw))

            if ccxt_status == "closed":
                status = OrderStatus.FILLED
                avg_price = Decimal(str(ccxt_order.get("average") or price))
                fee_info = ccxt_order.get("fee") or {}
                fee = Decimal(str(fee_info.get("cost", 0) or 0))
                self._stats["orders_filled"] += 1
            else:
                status = OrderStatus.PENDING
                avg_price = None
                fee = Decimal("0")

            order = Order(
                id=uuid.uuid4(),
                order_id=exchange_order_id,
                bot_id=strategy,
                pair=original_pair,
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
            )

            if self._db_manager:
                await self._save_order(order)

            logger.info(
                f"{self._mode_prefix} limit_order_placed",
                order_id=exchange_order_id,
                pair=original_pair,
                side=side.value,
                amount=str(amount),
                price=str(price),
                status=status.value,
            )

            return order

        except ccxt.InsufficientFunds as e:
            self._stats["orders_failed"] += 1
            raise InsufficientBalanceError(
                message=f"Insufficient funds for limit order: {e}",
            ) from e
        except ccxt.ExchangeError as e:
            self._stats["orders_failed"] += 1
            raise OrderExecutionError(
                message=f"Limit order placement failed: {e}",
                pair=original_pair,
                side=side.value,
                amount=amount,
            ) from e

    async def get_order_status(self, order_id: str, pair: str | None = None) -> dict[str, Any]:
        """Get the current status of an order.

        Args:
            order_id: Exchange order ID.
            pair: Trading pair (used for API call).

        Returns:
            Dictionary with order status details.

        Raises:
            KrakenAPIError: If API call fails.
        """
        if self.is_paper_mode:
            # Paper mode: return from tracked paper orders
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
            self._stats["api_calls"] += 1
            kraken_pair = PAIR_TO_KRAKEN.get(pair, pair) if pair else None
            order = await self._exchange.fetch_order(order_id, kraken_pair)

            filled_raw = order.get("filled") or 0
            avg_price_raw = order.get("average") or order.get("price") or 0
            fee_info = order.get("fee") or {}

            return {
                "order_id": order_id,
                "status": order.get("status", "unknown"),
                "filled": Decimal(str(filled_raw)),
                "amount": Decimal(str(order.get("amount", 0))),
                "price": Decimal(str(order.get("price", 0))),
                "average": Decimal(str(avg_price_raw)),
                "fee": Decimal(str(fee_info.get("cost", 0) or 0)),
                "fee_currency": fee_info.get("currency", ""),
            }

        except ccxt.OrderNotFound:
            logger.warning(
                "order_not_found",
                order_id=order_id,
            )
            return {
                "order_id": order_id,
                "status": "not_found",
                "filled": Decimal("0"),
                "amount": Decimal("0"),
            }
        except ccxt.ExchangeError as e:
            logger.error(
                "get_order_status_error",
                error=str(e),
                order_id=order_id,
            )
            raise KrakenAPIError(
                message=f"Failed to get order status: {e}",
            ) from e

    async def _save_order(self, order: Order) -> None:
        """Save order to database.

        Args:
            order: Order to save.
        """
        if not self._db_manager:
            return

        try:
            async with self._db_manager.session() as session:
                session.add(order)
        except Exception as e:
            logger.error(
                "save_order_error",
                error=str(e),
                order_id=order.order_id,
            )

    async def get_trade_history(
        self,
        pair: str | None = None,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        """Get trade history from exchange.

        Args:
            pair: Filter by trading pair, or None for all.
            limit: Maximum number of trades to return.

        Returns:
            List of trade dictionaries.

        Raises:
            KrakenAPIError: If API call fails.
        """
        if self.is_paper_mode:
            # Paper trades are stored in database, not here
            logger.info(
                f"{self._mode_prefix} get_trade_history",
                message="Paper trades stored in database",
            )
            return []

        try:
            self._stats["api_calls"] += 1
            kraken_pair = PAIR_TO_KRAKEN.get(pair, pair) if pair else None
            trades = await self._exchange.fetch_my_trades(kraken_pair, limit=limit)

            result = []
            for trade in trades:
                result.append(
                    {
                        "trade_id": trade.get("id"),
                        "order_id": trade.get("order"),
                        "pair": trade.get("symbol"),
                        "side": trade.get("side"),
                        "amount": Decimal(str(trade.get("amount", 0))),
                        "price": Decimal(str(trade.get("price", 0))),
                        "fee": Decimal(str(trade.get("fee", {}).get("cost", 0))),
                        "fee_currency": trade.get("fee", {}).get("currency"),
                        "timestamp": trade.get("timestamp"),
                    }
                )

            logger.info(
                f"{self._mode_prefix} get_trade_history",
                count=len(result),
            )

            return result

        except ccxt.ExchangeError as e:
            logger.error(
                "kraken_rest_trade_history_error",
                error=str(e),
            )
            raise KrakenAPIError(
                message=f"Failed to fetch trade history: {e}",
            ) from e

    async def _save_trade(self, trade: Trade) -> None:
        """Save trade to database.

        Args:
            trade: Trade to save.
        """
        if not self._db_manager:
            return

        try:
            async with self._db_manager.session() as session:
                session.add(trade)
        except Exception as e:
            logger.error(
                "kraken_rest_save_trade_error",
                error=str(e),
                trade_id=str(trade.id),
            )

    async def fetch_ohlcv(
        self,
        pair: str,
        interval: int,
        since: datetime | None = None,
        limit: int = 720,
    ) -> list[dict[str, Any]]:
        """Fetch historical OHLC candles from Kraken REST API.

        This method retrieves historical OHLC (Open, High, Low, Close) data
        using the CCXT library. It's used for backtesting and historical
        data collection.

        Args:
            pair: Trading pair (e.g., "XBT/EUR", "XBT/USDC").
            interval: Candle interval in minutes (1, 5, 15, 30, 60, 240, 1440).
            since: Start time (UTC). If None, fetches most recent candles.
            limit: Max candles to fetch (max 720 per Kraken API limit).

        Returns:
            List of OHLC dictionaries with keys:
                - timestamp: Candle timestamp (datetime)
                - pair: Trading pair
                - interval: Candle interval in minutes
                - open: Opening price
                - high: Highest price
                - low: Lowest price
                - close: Closing price
                - volume: Trading volume

        Raises:
            KrakenAPIError: On API errors.
            RateLimitError: If rate limit exceeded.
            ValueError: If interval is not supported.

        Example:
            >>> client = KrakenRestClient(settings, event_bus)
            >>> candles = await client.fetch_ohlcv("XBT/EUR", 15, limit=100)
            >>> print(f"Fetched {len(candles)} candles")
        """
        from krakenbot.utils.time_utils import minutes_to_ccxt_timeframe

        try:
            # Convert interval to CCXT timeframe format
            timeframe = minutes_to_ccxt_timeframe(interval)

            # Convert pair to Kraken format
            kraken_pair = PAIR_TO_KRAKEN.get(pair, pair)

            # Convert since to milliseconds timestamp if provided
            since_ms = None
            if since:
                since_ms = int(since.timestamp() * 1000)

            # Log the request
            logger.debug(
                "fetching_ohlcv",
                pair=kraken_pair,
                timeframe=timeframe,
                since=since.isoformat() if since else None,
                limit=limit,
            )

            # Fetch OHLC data from Kraken via CCXT
            self._stats["api_calls"] += 1
            ohlcv_data = await self._exchange.fetch_ohlcv(
                symbol=kraken_pair,
                timeframe=timeframe,
                since=since_ms,
                limit=limit,
            )

            # Parse CCXT response format: [[timestamp_ms, open, high, low, close, volume], ...]
            result = []
            for candle in ohlcv_data:
                timestamp_ms, open_price, high, low, close, volume = candle

                # Convert timestamp from milliseconds to datetime
                timestamp = datetime.fromtimestamp(timestamp_ms / 1000, tz=UTC)

                result.append(
                    {
                        "timestamp": timestamp,
                        "pair": pair,  # Use original pair format
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
                first_timestamp=result[0]["timestamp"].isoformat() if result else None,
                last_timestamp=result[-1]["timestamp"].isoformat() if result else None,
            )

            return result

        except ccxt.RateLimitExceeded as e:
            logger.warning(
                "kraken_rest_rate_limit",
                error=str(e),
            )
            raise RateLimitError(
                message=f"Rate limit exceeded when fetching OHLCV: {e}",
            ) from e
        except ccxt.ExchangeError as e:
            logger.error(
                "kraken_rest_ohlcv_error",
                pair=pair,
                interval=interval,
                error=str(e),
            )
            raise KrakenAPIError(
                message=f"Failed to fetch OHLCV data: {e}",
            ) from e
        except ValueError as e:
            # From minutes_to_ccxt_timeframe
            logger.error(
                "invalid_interval",
                interval=interval,
                error=str(e),
            )
            raise

    async def set_paper_balance(self, currency: str, amount: Decimal) -> None:
        """Set paper trading balance for a currency and persist to DB.

        Args:
            currency: Currency symbol (e.g., "USDC", "BTC").
            amount: Balance amount.
        """
        if not self.is_paper_mode:
            logger.warning("set_paper_balance_not_paper_mode")
            return

        self._normalize_paper_balance()
        self._paper_balance[normalize_asset_symbol(currency)] = amount
        await self.persist_paper_balance()
        logger.info(
            f"{self._mode_prefix} set_balance",
            currency=normalize_asset_symbol(currency),
            amount=str(amount),
        )

    def get_paper_balance(self) -> dict[str, Decimal]:
        """Get current paper trading balance.

        Returns:
            Dictionary of paper balances.
        """
        self._normalize_paper_balance()
        return self._paper_balance.copy()

    def remove_paper_order(self, order_id: str) -> None:
        """Remove a tracked paper order from the in-memory exchange state."""
        self._paper_orders.pop(order_id, None)

    async def initialize_paper_balance(
        self,
        force_reset: bool = False,
    ) -> None:
        """Initialize paper balance from DB or real Kraken balance.

        On first startup (empty DB), fetches real balance from Kraken API
        and saves it as both initial and current balance. On subsequent
        startups, loads from DB to continue where it left off.

        Args:
            force_reset: If True, re-fetch from Kraken and overwrite DB.
        """
        if not self.is_paper_mode:
            return

        if not self._db_manager:
            logger.warning("paper_balance_init_no_db_manager")
            return

        if not force_reset:
            loaded = await self._load_paper_balance_from_db()
            if loaded:
                logger.info(
                    "paper_balance_loaded_from_db",
                    balance=str(self._paper_balance),
                )
                return

        # First startup or force reset: fetch real balance from Kraken
        real_balance = normalize_asset_balances(await self._fetch_real_balance())

        pair = self._settings.trading.pair
        base = pair.split("/")[0]
        quote = pair.split("/")[1]
        base_norm = normalize_asset_symbol(base)

        btc_amount = real_balance.get(base_norm, Decimal("0"))
        quote_amount = real_balance.get(quote, Decimal("0"))

        self._paper_balance = {
            base_norm: btc_amount,
            quote: quote_amount,
        }

        await self._save_paper_balance_to_db(initial=True)

        logger.info(
            "paper_balance_initialized_from_kraken",
            base=str(btc_amount),
            base_currency=base_norm,
            quote=str(quote_amount),
            quote_currency=quote,
        )

    async def persist_paper_balance(self) -> None:
        """Persist current paper balance to DB after a trade."""
        self._normalize_paper_balance()
        if self._db_manager:
            await self._save_paper_balance_to_db(initial=False)

    async def _fetch_real_balance(self) -> dict[str, Decimal]:
        """Fetch real balance from Kraken API (even in paper mode).

        The CCXT exchange object already has real API credentials.

        Returns:
            Dictionary of currency -> amount from real Kraken account.
        """
        try:
            self._stats["api_calls"] += 1
            balance = await self._exchange.fetch_balance()
            result: dict[str, Decimal] = {}
            for currency, amounts in balance.get("free", {}).items():
                if amounts and float(amounts) > 0:
                    result[currency] = Decimal(str(amounts))

            logger.info(
                "real_balance_fetched_for_paper",
                currencies=list(result.keys()),
            )
            return result

        except Exception as e:
            logger.error(
                "real_balance_fetch_failed",
                error=str(e),
                error_type=type(e).__name__,
            )
            return {}

    async def _load_paper_balance_from_db(self) -> bool:
        """Load paper balance from paper_balance table.

        Returns:
            True if records were found and loaded.
        """
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
                    canonical_currency = normalize_asset_symbol(row.currency)
                    loaded_balance[canonical_currency] = (
                        loaded_balance.get(canonical_currency, Decimal("0")) + row.amount
                    )

                self._paper_balance = loaded_balance

                return True

        except Exception as e:
            logger.error("load_paper_balance_db_error", error=str(e))
            return False

    async def _save_paper_balance_to_db(self, initial: bool = False) -> None:
        """Save current paper balance to paper_balance table.

        Args:
            initial: If True, also update initial_amount (first-time snapshot).
        """
        from krakenbot.models.trades import PaperBalance

        if not self._db_manager:
            return

        try:
            self._normalize_paper_balance()
            async with self._db_manager.session() as session:
                for currency, amount in self._paper_balance.items():
                    existing = await session.get(PaperBalance, currency)
                    if existing:
                        existing.amount = amount
                        existing.updated_at = datetime.now(UTC)
                        if initial:
                            existing.initial_amount = amount
                    else:
                        record = PaperBalance(
                            currency=currency,
                            amount=amount,
                            initial_amount=amount if initial else Decimal("0"),
                        )
                        session.add(record)

                legacy_btc_alias = await session.get(PaperBalance, "XBT")
                if legacy_btc_alias is not None:
                    await session.delete(legacy_btc_alias)

        except Exception as e:
            logger.error("save_paper_balance_db_error", error=str(e))
