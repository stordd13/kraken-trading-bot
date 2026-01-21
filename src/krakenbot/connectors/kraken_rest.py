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
    >>> from krakenbot.connectors.kraken_rest import KrakenRestClient
    >>> client = KrakenRestClient(settings, event_bus)
    >>> balance = await client.get_balance()
    >>> trade = await client.place_market_order("XBT/EUR", TradeSide.BUY, Decimal("0.001"))
    >>> await client.close()
"""

from __future__ import annotations

from datetime import UTC, datetime
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
from krakenbot.models.base import TradeSide, TradeStatus
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

        # Paper trading state
        self._paper_balance: dict[str, Decimal] = {
            "EUR": Decimal("1000.00"),  # Default paper balance
            "XBT": Decimal("0.0"),
            "ETH": Decimal("0.0"),
        }
        self._paper_orders: dict[str, dict[str, Any]] = {}

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
            return await self._live_market_order(kraken_pair, side, amount, strategy)

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
        base_currency = pair.split("/")[0]
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

            # Parse order response
            order_id = order.get("id")
            filled_amount = Decimal(str(order.get("filled", amount)))
            avg_price = Decimal(str(order.get("average", order.get("price", 0))))

            # Calculate fee
            fee_info = order.get("fee", {})
            fee = Decimal(str(fee_info.get("cost", 0))) if fee_info else Decimal("0")
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

    def set_paper_balance(self, currency: str, amount: Decimal) -> None:
        """Set paper trading balance for a currency.

        Args:
            currency: Currency symbol (e.g., "EUR", "XBT").
            amount: Balance amount.
        """
        if not self.is_paper_mode:
            logger.warning("set_paper_balance_not_paper_mode")
            return

        self._paper_balance[currency] = amount
        logger.info(
            f"{self._mode_prefix} set_balance",
            currency=currency,
            amount=str(amount),
        )

    def get_paper_balance(self) -> dict[str, Decimal]:
        """Get current paper trading balance.

        Returns:
            Dictionary of paper balances.
        """
        return self._paper_balance.copy()
