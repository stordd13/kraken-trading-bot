"""Order lifecycle manager for limit orders.

This module manages the lifecycle of limit orders:
- Placement and tracking
- Periodic status checking (fill detection)
- Paper mode: candle-based fill simulation
- Live mode: Kraken API status polling
- Expiry and cancellation
- Profit target management per position

Workflow:
    1. Strategy requests limit order via ExecutionEngine
    2. OrderManager places order via REST client and tracks it
    3. Periodic check_pending_orders() detects fills or expiry
    4. On fill: publishes TRADE_ORDER_FILLED event
    5. On expiry: cancels on exchange and updates DB
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from decimal import Decimal
from typing import TYPE_CHECKING, Any

from sqlalchemy import select

from krakenbot.connectors.kraken.rest import normalize_asset_balances, normalize_asset_symbol
from krakenbot.core.event_bus import EventType
from krakenbot.core.logger import get_logger
from krakenbot.models.base import OrderStatus, TradeSide
from krakenbot.models.orders import Order

if TYPE_CHECKING:
    from krakenbot.config.settings import Settings
    from krakenbot.connectors.exchange import ExchangeRestClient
    from krakenbot.core.database import DatabaseManager
    from krakenbot.core.event_bus import EventBus

logger = get_logger(__name__)

_TIMEFRAME_TO_INTERVAL_MINUTES = {
    "1m": 1,
    "5m": 5,
    "15m": 15,
    "30m": 30,
    "1h": 60,
    "4h": 240,
    "1d": 1440,
    "1w": 10080,
}

_ROUTER_INNER_STRATEGY_INTERVALS = {
    "gemini_scalping_volatilite": 5,
    "gemini_retour_moyenne": 15,
    "gemini_suivi_tendance_momentum": 240,
    "grok_grid_atr_adaptive_v4": 240,
    "grok_supertrend_4h": 240,
    "grok_ema_adx_atr": 240,
    "grok_adaptive_dca_weekly": 1440,
}


def _parse_interval_minutes(value: Any) -> int | None:
    """Convert an interval or timeframe token to minutes."""
    if value is None:
        return None

    if isinstance(value, int):
        return value if value > 0 else None

    if isinstance(value, str):
        normalized = value.strip().lower()
        if not normalized:
            return None
        if normalized.isdigit():
            interval = int(normalized)
            return interval if interval > 0 else None
        return _TIMEFRAME_TO_INTERVAL_MINUTES.get(normalized)

    return None


class OrderManager:
    """Manages limit order lifecycle from placement to fill/cancel.

    Responsibilities:
        - Track pending orders in memory for fast access
        - Periodically check order status (paper: candle simulation, live: API)
        - Handle fills by publishing events and updating DB
        - Cancel expired orders
        - Manage profit target limit sells per position

    Attributes:
        rest_client: Kraken REST client for order operations.
        db_manager: Database manager for persistence.
        event_bus: Event bus for publishing fill events.
        settings: Application settings.
    """

    def __init__(
        self,
        rest_client: ExchangeRestClient,
        db_manager: DatabaseManager,
        event_bus: EventBus,
        settings: Settings,
    ) -> None:
        """Initialize OrderManager.

        Args:
            rest_client: Kraken REST client.
            db_manager: Database manager.
            event_bus: Event bus.
            settings: Application settings.
        """
        self._rest_client = rest_client
        self._db_manager = db_manager
        self._event_bus = event_bus
        self._settings = settings

        # In-memory tracking of pending orders (order_id -> Order)
        self._pending_orders: dict[str, Order] = {}

        # Profit target tracking (position_id -> order_id of limit sell)
        self._position_profit_targets: dict[int, str] = {}

        # Latest raw candle and keyed candle cache for paper fill simulation
        self._last_candle: dict[str, Any] | None = None
        self._last_candles: dict[tuple[str, int], dict[str, Any]] = {}
        self._strategy_execution_intervals = self._build_strategy_execution_intervals()

        # Statistics
        self._stats = {
            "orders_placed": 0,
            "orders_filled": 0,
            "orders_expired": 0,
            "orders_cancelled": 0,
            "check_cycles": 0,
        }
        self._fill_handler: Callable[[Order], Awaitable[None]] | None = None

    @property
    def stats(self) -> dict[str, int]:
        """Get order manager statistics."""
        return self._stats.copy()

    @property
    def pending_count(self) -> int:
        """Get number of currently pending orders."""
        return len(self._pending_orders)

    def set_fill_handler(self, handler: Callable[[Order], Awaitable[None]] | None) -> None:
        """Register a callback invoked after a limit fill event is published."""
        self._fill_handler = handler

    async def load_pending_from_db(self) -> None:
        """Load pending orders from database on startup.

        Recovers state after bot restart.
        """
        try:
            async with self._db_manager.read_session() as session:
                result = await session.execute(
                    select(Order).where(
                        Order.status.in_([OrderStatus.PENDING, OrderStatus.PARTIALLY_FILLED])
                    )
                )
                orders = result.scalars().all()

                for order in orders:
                    self._pending_orders[order.order_id] = order

                    # Rebuild profit target mapping
                    if (
                        order.side == TradeSide.SELL
                        and order.signal_metadata
                        and "position_id" in order.signal_metadata
                    ):
                        pos_id = order.signal_metadata["position_id"]
                        self._position_profit_targets[pos_id] = order.order_id

                if orders:
                    logger.info(
                        "pending_orders_loaded",
                        count=len(orders),
                    )
        except Exception as e:
            logger.error(
                "load_pending_orders_error",
                error=str(e),
                error_type=type(e).__name__,
            )

    async def place_and_track(
        self,
        pair: str,
        side: TradeSide,
        amount: Decimal,
        price: Decimal,
        strategy: str,
        signal_metadata: dict[str, Any] | None = None,
        expires_in_seconds: int | None = None,
    ) -> Order:
        """Place a limit order and track it.

        Args:
            pair: Trading pair.
            side: Order side (BUY or SELL).
            amount: Amount in base currency.
            price: Limit price.
            strategy: Strategy name / bot_id.
            signal_metadata: Metadata from the trading signal.
            expires_in_seconds: Override default expiry. None uses settings.

        Returns:
            Order object (PENDING or FILLED if immediately matched).
        """
        if expires_in_seconds is None:
            expires_in_seconds = self._settings.order.limit_order_expiry_minutes * 60

        metadata = self._enrich_signal_metadata(signal_metadata, strategy)

        order = await self._rest_client.place_limit_order(
            pair=pair,
            side=side,
            amount=amount,
            price=price,
            strategy=strategy,
            expires_in_seconds=expires_in_seconds,
        )

        # Attach signal metadata
        order.signal_metadata = metadata

        # Save metadata to DB
        if self._db_manager:
            try:
                async with self._db_manager.session() as session:
                    db_order = await session.get(Order, order.id)
                    if db_order:
                        db_order.signal_metadata = metadata
            except Exception as e:
                logger.warning("save_order_metadata_error", error=str(e))

        self._stats["orders_placed"] += 1

        if order.status == OrderStatus.FILLED:
            # Already filled (immediate fill in paper mode)
            self._stats["orders_filled"] += 1
            await self._publish_fill_event(order)
        else:
            # Track as pending
            self._pending_orders[order.order_id] = order

        logger.info(
            "order_placed_and_tracked",
            order_id=order.order_id,
            pair=pair,
            side=side.value,
            amount=str(amount),
            price=str(price),
            status=order.status.value,
            strategy=strategy,
        )

        # Telegram notification (fire-and-forget)
        from krakenbot.notifications.telegram import get_notifier

        notifier = get_notifier()
        if notifier:
            import asyncio

            asyncio.create_task(
                notifier.send_order_placed(
                    strategy=strategy,
                    pair=pair,
                    side=side.value,
                    amount=str(amount),
                    price=str(price),
                )
            )

        return order

    async def check_pending_orders(self) -> None:
        """Check all pending orders for fills or expiry.

        Paper mode: simulates fills using last candle data.
        Live mode: queries Kraken API for each pending order.

        Called periodically (default every 30 seconds).
        """
        if not self._pending_orders:
            return

        self._stats["check_cycles"] += 1
        now = datetime.now(UTC)

        # Snapshot keys to avoid modifying dict during iteration
        order_ids = list(self._pending_orders.keys())

        for order_id in order_ids:
            order = self._pending_orders.get(order_id)
            if order is None:
                continue

            try:
                # Check expiry first
                if order.expires_at and now >= order.expires_at:
                    await self._handle_expired_order(order)
                    continue

                # Check for fill
                if self._rest_client.is_paper_mode:
                    await self._check_paper_fill(order)
                else:
                    await self._check_live_fill(order)

            except Exception as e:
                logger.error(
                    "check_pending_order_error",
                    error=str(e),
                    error_type=type(e).__name__,
                    order_id=order_id,
                )

    async def _check_paper_fill(self, order: Order) -> None:
        """Check if a paper limit order should be filled based on candle data.

        Fill conditions:
            - BUY limit: candle low <= limit price
            - SELL limit: candle high >= limit price

        Args:
            order: The pending order to check.
        """
        candle = self._get_matching_paper_candle(order)
        if candle is None:
            return

        candle_low = Decimal(str(candle.get("low", 0)))
        candle_high = Decimal(str(candle.get("high", 0)))

        if candle_low <= Decimal("0") or candle_high <= Decimal("0"):
            return

        filled = False

        if order.side == TradeSide.BUY and order.price is not None:
            if candle_low <= order.price:
                filled = True
        elif order.side == TradeSide.SELL and order.price is not None:
            if candle_high >= order.price:
                filled = True

        if filled:
            await self._fill_paper_order(order)

    async def _fill_paper_order(self, order: Order) -> None:
        """Simulate filling a paper limit order.

        Updates paper balance and order status.

        Args:
            order: The order to fill.
        """
        fill_price = order.price or Decimal("0")
        value = order.amount * fill_price
        fee = value * Decimal("0.0016")  # Maker fee ~0.16%

        paper_balance = self._rest_client.paper_balance
        normalized_paper_balance = normalize_asset_balances(paper_balance)
        paper_balance.clear()
        paper_balance.update(normalized_paper_balance)
        pair = order.pair
        base_currency = normalize_asset_symbol(pair.split("/")[0])
        quote_currency = pair.split("/")[1]

        # Update paper balance
        if order.side == TradeSide.BUY:
            required = value + fee
            available = paper_balance.get(quote_currency, Decimal("0"))
            if available < required:
                logger.warning(
                    "paper_limit_fill_insufficient_balance",
                    order_id=order.order_id,
                    required=str(required),
                    available=str(available),
                )
                await self._handle_expired_order(order)
                return

            paper_balance[quote_currency] = available - required
            paper_balance[base_currency] = (
                paper_balance.get(base_currency, Decimal("0")) + order.amount
            )
        else:
            available = paper_balance.get(base_currency, Decimal("0"))
            if available < order.amount:
                logger.warning(
                    "paper_limit_fill_insufficient_balance",
                    order_id=order.order_id,
                    required=str(order.amount),
                    available=str(available),
                )
                await self._handle_expired_order(order)
                return

            paper_balance[base_currency] = available - order.amount
            paper_balance[quote_currency] = (
                paper_balance.get(quote_currency, Decimal("0")) + value - fee
            )

        # Persist paper balance to DB
        await self._rest_client.persist_paper_balance()

        # Update order state
        order.status = OrderStatus.FILLED
        order.filled_amount = order.amount
        order.filled_price = fill_price
        order.fee = fee

        # Update in DB
        await self._update_order_in_db(order)

        # Remove from pending tracking
        self._pending_orders.pop(order.order_id, None)

        # Remove from paper orders in REST client
        self._rest_client.remove_paper_order(order.order_id)

        # Clean up profit target mapping
        self._cleanup_profit_target(order)

        self._stats["orders_filled"] += 1

        logger.info(
            "paper_limit_order_filled",
            order_id=order.order_id,
            pair=order.pair,
            side=order.side.value,
            amount=str(order.amount),
            price=str(fill_price),
            fee=str(fee),
        )

        await self._publish_fill_event(order)

    async def _check_live_fill(self, order: Order) -> None:
        """Check live order status via Kraken API.

        Args:
            order: The pending order to check.
        """
        status_data = await self._rest_client.get_order_status(order.order_id, order.pair)

        exchange_status = status_data.get("status", "unknown")

        if exchange_status == "closed":
            # Order fully filled
            order.status = OrderStatus.FILLED
            order.filled_amount = status_data.get("filled", order.amount)
            order.filled_price = status_data.get("average", order.price)
            order.fee = status_data.get("fee", Decimal("0"))

            await self._update_order_in_db(order)
            self._pending_orders.pop(order.order_id, None)
            self._cleanup_profit_target(order)
            self._stats["orders_filled"] += 1

            logger.info(
                "live_limit_order_filled",
                order_id=order.order_id,
                pair=order.pair,
                side=order.side.value,
                filled_amount=str(order.filled_amount),
                filled_price=str(order.filled_price),
                fee=str(order.fee),
            )

            await self._publish_fill_event(order)

        elif exchange_status == "canceled":
            # Order was cancelled on exchange
            order.status = OrderStatus.CANCELLED
            await self._update_order_in_db(order)
            self._pending_orders.pop(order.order_id, None)
            self._cleanup_profit_target(order)
            self._stats["orders_cancelled"] += 1

            logger.info(
                "live_order_cancelled_on_exchange",
                order_id=order.order_id,
            )

    async def _handle_expired_order(self, order: Order) -> None:
        """Handle an expired order: cancel on exchange and update DB.

        Args:
            order: The expired order.
        """
        # Cancel on exchange (live mode) or remove from paper tracking
        try:
            await self._rest_client.cancel_order(order.order_id, order.pair)
        except Exception as e:
            logger.warning(
                "cancel_expired_order_error",
                error=str(e),
                order_id=order.order_id,
            )

        order.status = OrderStatus.EXPIRED
        await self._update_order_in_db(order)
        self._pending_orders.pop(order.order_id, None)
        self._cleanup_profit_target(order)
        self._stats["orders_expired"] += 1

        logger.info(
            "order_expired",
            order_id=order.order_id,
            pair=order.pair,
            side=order.side.value,
            price=str(order.price),
        )

    async def place_profit_target(
        self,
        position_id: int,
        pair: str,
        amount: Decimal,
        target_price: Decimal,
        strategy: str,
    ) -> Order:
        """Place a limit sell as profit target for a position.

        If a profit target already exists for this position, cancels
        it before placing the new one.

        Args:
            position_id: Position ID to set profit target for.
            pair: Trading pair.
            amount: Amount to sell.
            target_price: Target sell price.
            strategy: Strategy name.

        Returns:
            The placed Order.
        """
        # Cancel existing profit target if any
        await self.cancel_profit_target(position_id)

        order = await self.place_and_track(
            pair=pair,
            side=TradeSide.SELL,
            amount=amount,
            price=target_price,
            strategy=strategy,
            signal_metadata={"position_id": position_id, "order_type": "profit_target"},
            expires_in_seconds=86400,  # 24h for profit targets
        )

        if order.is_pending or order.status == OrderStatus.PARTIALLY_FILLED:
            self._position_profit_targets[position_id] = order.order_id

        logger.info(
            "profit_target_placed",
            position_id=position_id,
            order_id=order.order_id,
            target_price=str(target_price),
            amount=str(amount),
        )

        return order

    async def cancel_profit_target(self, position_id: int) -> bool:
        """Cancel existing profit target for a position.

        MUST be called before executing a market stop-loss/trailing-stop
        to avoid orphan limit sells.

        Args:
            position_id: Position ID whose profit target to cancel.

        Returns:
            True if a profit target was found and cancelled.
        """
        order_id = self._position_profit_targets.pop(position_id, None)
        if order_id is None:
            return False

        # Remove from pending tracking
        order = self._pending_orders.pop(order_id, None)

        # Cancel on exchange
        try:
            await self._rest_client.cancel_order(order_id)
        except Exception as e:
            logger.warning(
                "cancel_profit_target_error",
                error=str(e),
                order_id=order_id,
                position_id=position_id,
            )

        # Update DB if we have the order object
        if order:
            order.status = OrderStatus.CANCELLED
            await self._update_order_in_db(order)

        self._stats["orders_cancelled"] += 1

        logger.info(
            "profit_target_cancelled",
            position_id=position_id,
            order_id=order_id,
        )

        return True

    async def on_ohlc(self, data: dict[str, Any]) -> None:
        """Handle OHLC candle data for paper mode fill simulation.

        Stores the latest candle data for use in _check_paper_fill().

        Args:
            data: OHLC event data with keys: low, high, close, etc.
        """
        self._last_candle = data
        pair = data.get("pair")
        interval = _parse_interval_minutes(data.get("interval"))
        if interval is None:
            interval = _parse_interval_minutes(data.get("timeframe"))
        if pair and interval is not None:
            self._last_candles[(str(pair), interval)] = data

    def _build_strategy_execution_intervals(self) -> dict[str, int]:
        """Infer execution intervals for strategies from current runtime config."""
        intervals: dict[str, int] = {}

        if not self._settings.multi_strategy.enabled:
            return intervals

        for strat_config in self._settings.multi_strategy.strategies:
            if not strat_config.enabled:
                continue

            if strat_config.name != "multi_strategy_router":
                intervals[strat_config.bot_id] = self._settings.trading.candle_interval_min
                continue

            inner_configs = strat_config.params.get("strategies", {})
            if not isinstance(inner_configs, dict):
                continue

            for inner_name, inner_cfg in inner_configs.items():
                if not isinstance(inner_cfg, dict) or not inner_cfg.get("active", True):
                    continue

                interval = _ROUTER_INNER_STRATEGY_INTERVALS.get(inner_name)
                if interval is None:
                    continue

                bot_id = str(inner_cfg.get("bot_id", inner_name))
                intervals[bot_id] = interval

        return intervals

    def _resolve_execution_interval(
        self,
        strategy: str,
        signal_metadata: dict[str, Any] | None,
    ) -> int:
        """Resolve the candle interval that should drive paper fills for an order."""
        metadata = signal_metadata or {}

        for key in ("execution_interval", "interval"):
            interval = _parse_interval_minutes(metadata.get(key))
            if interval is not None:
                return interval

        for key in ("execution_timeframe", "timeframe"):
            interval = _parse_interval_minutes(metadata.get(key))
            if interval is not None:
                return interval

        strategy_interval = self._strategy_execution_intervals.get(strategy)
        if strategy_interval is not None:
            return strategy_interval

        trigger_interval = _parse_interval_minutes(
            getattr(getattr(self._settings, "multi_timeframe", None), "trigger_timeframe", None)
        )
        default_interval = _parse_interval_minutes(
            getattr(getattr(self._settings, "trading", None), "candle_interval_min", None)
        )
        if default_interval is None:
            default_interval = 5

        if bool(getattr(getattr(self._settings, "multi_strategy", None), "enabled", False)):
            return trigger_interval if trigger_interval is not None else default_interval

        return default_interval

    def _enrich_signal_metadata(
        self,
        signal_metadata: dict[str, Any] | None,
        strategy: str,
    ) -> dict[str, Any] | None:
        """Persist execution context needed for deterministic paper fills."""
        if signal_metadata is None:
            signal_metadata = {}
        else:
            signal_metadata = dict(signal_metadata)

        signal_metadata.setdefault(
            "execution_interval",
            self._resolve_execution_interval(strategy, signal_metadata),
        )
        return signal_metadata

    def _get_matching_paper_candle(self, order: Order) -> dict[str, Any] | None:
        """Return the latest candle matching the order pair and execution timeframe."""
        strategy = getattr(order, "strategy", "") or getattr(order, "bot_id", "")
        interval = self._resolve_execution_interval(strategy, order.signal_metadata)
        candle = self._last_candles.get((order.pair, interval))
        if candle is not None:
            return candle

        # Backward-compatible fallback for tests/legacy state that injected a raw candle only.
        if self._last_candle is None:
            return None

        if self._last_candle.get("pair") is None and self._last_candle.get("interval") is None:
            return self._last_candle

        return None

    def _cleanup_profit_target(self, order: Order) -> None:
        """Remove profit target mapping for a filled/cancelled order.

        Args:
            order: The order that was filled or cancelled.
        """
        if order.signal_metadata and "position_id" in order.signal_metadata:
            pos_id = order.signal_metadata["position_id"]
            if self._position_profit_targets.get(pos_id) == order.order_id:
                del self._position_profit_targets[pos_id]

    async def _update_order_in_db(self, order: Order) -> None:
        """Update order status in database.

        Args:
            order: Order with updated fields.
        """
        try:
            async with self._db_manager.session() as session:
                db_order = await session.get(Order, order.id)
                if db_order:
                    db_order.status = order.status
                    db_order.filled_amount = order.filled_amount
                    db_order.filled_price = order.filled_price
                    db_order.fee = order.fee
                    db_order.updated_at = datetime.now(UTC)
        except Exception as e:
            logger.error(
                "update_order_db_error",
                error=str(e),
                order_id=order.order_id,
            )

    async def _publish_fill_event(self, order: Order) -> None:
        """Publish TRADE_ORDER_FILLED event for a filled order.

        Args:
            order: The filled order.
        """
        await self._save_trade_record(order)

        metadata = order.signal_metadata if order.signal_metadata is not None else {}

        await self._event_bus.publish(
            EventType.TRADE_ORDER_FILLED,
            {
                "mode": "paper" if self._rest_client.is_paper_mode else "live",
                "trade_id": str(order.id),
                "order_id": order.order_id,
                "pair": order.pair,
                "side": order.side.value,
                "amount": str(order.filled_amount),
                "price": str(order.filled_price or order.price),
                "fee": str(order.fee),
                "strategy": order.strategy,
                "order_type": "limit",
                # Metadata from signal for position tracking
                "reference_price": str(metadata.get("reference_price", "0")),
                "position_id": metadata.get("position_id"),
                "signal_metadata": metadata,
            },
        )

        if self._fill_handler is not None:
            await self._fill_handler(order)

    async def _save_trade_record(self, order: Order) -> None:
        """Save a Trade record from a filled order.

        Ensures trades_history has an entry for limit order fills,
        consistent with how market orders are recorded.

        Args:
            order: The filled order.
        """
        from krakenbot.models.base import TradeStatus
        from krakenbot.models.trades import Trade

        try:
            trade = Trade(
                id=order.id,  # Use same UUID for linkage
                timestamp=datetime.now(UTC),
                pair=order.pair,
                side=order.side,
                amount=order.filled_amount,
                price=order.filled_price or order.price or Decimal("0"),
                fee=order.fee,
                fee_currency=order.pair.split("/")[1],
                strategy=order.strategy,
                status=TradeStatus.FILLED,
                order_id=order.order_id,
                notes=f"Limit order fill - {'paper' if self._rest_client.is_paper_mode else 'live'}",
            )

            async with self._db_manager.session() as session:
                session.add(trade)

        except Exception as e:
            logger.error(
                "save_trade_from_order_error",
                error=str(e),
                order_id=order.order_id,
            )

    async def cancel_all_pending(self) -> int:
        """Cancel all pending orders. Used during shutdown.

        Returns:
            Number of orders cancelled.
        """
        count = 0
        for order_id in list(self._pending_orders.keys()):
            order = self._pending_orders.pop(order_id, None)
            if order:
                try:
                    await self._rest_client.cancel_order(order_id, order.pair)
                    order.status = OrderStatus.CANCELLED
                    await self._update_order_in_db(order)
                    count += 1
                except Exception as e:
                    logger.warning(
                        "cancel_all_pending_error",
                        error=str(e),
                        order_id=order_id,
                    )

        self._position_profit_targets.clear()

        if count > 0:
            logger.info("all_pending_orders_cancelled", count=count)

        return count
