"""Execution engine for processing trading signals.

This module provides the ExecutionEngine class that orchestrates the execution
of trading signals by validating them through the RiskManager and executing
orders via the Kraken REST client.

Workflow:
    1. Receive trading signal from EventBus
    2. Validate signal via RiskManager
    3. Execute order via KrakenRestClient
    4. Update BotState in database
    5. Log all decisions and outcomes

Example:
    >>> from krakenbot.execution.engine import ExecutionEngine
    >>> engine = ExecutionEngine(settings, event_bus, db_manager, rest_client)
    >>> await engine.start()
    >>> # Engine now listens for TRADE_SIGNAL events
    >>> await engine.stop()
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from typing import TYPE_CHECKING, Any

from krakenbot.core.event_bus import EventType
from krakenbot.core.logger import get_logger
from krakenbot.execution.risk import GlobalRiskManager, RiskManager
from krakenbot.models.base import BotStatus, SignalType, TradeSide
from krakenbot.strategies.base import TradingSignal

if TYPE_CHECKING:
    from krakenbot.config.settings import Settings
    from krakenbot.connectors.kraken_rest import KrakenRestClient
    from krakenbot.core.database import DatabaseManager
    from krakenbot.core.event_bus import EventBus
    from krakenbot.execution.order_manager import OrderManager
    from krakenbot.models.trades import Trade


class ExecutionEngine:
    """Engine that processes trading signals and executes orders.

    The ExecutionEngine is the central component that connects strategy
    signals to actual order execution. It listens for signals on the
    EventBus, validates them through risk management, and executes
    approved orders.

    Responsibilities:
        - Subscribe to trading signal events
        - Validate orders through RiskManager
        - Execute orders via KrakenRestClient
        - Update BotState after trades
        - Log all trading decisions

    Attributes:
        settings: Application settings.
        event_bus: Event bus for pub/sub communication.
        db_manager: Database manager for persistence.
        rest_client: Kraken REST API client.
        risk_manager: Risk management validator.

    Example:
        >>> engine = ExecutionEngine(
        ...     settings=settings,
        ...     event_bus=event_bus,
        ...     db_manager=db_manager,
        ...     rest_client=rest_client,
        ... )
        >>> await engine.start()
        >>> # Signal handling happens automatically
        >>> await engine.stop()
    """

    def __init__(
        self,
        settings: Settings,
        event_bus: EventBus,
        db_manager: DatabaseManager,
        rest_client: KrakenRestClient,
        risk_manager: GlobalRiskManager | RiskManager | None = None,
        order_manager: OrderManager | None = None,
    ) -> None:
        """Initialize the execution engine.

        Args:
            settings: Application settings.
            event_bus: Event bus for pub/sub communication.
            db_manager: Database manager for persistence.
            rest_client: Kraken REST API client.
            risk_manager: Optional risk manager (GlobalRiskManager for multi-strategy,
                         RiskManager for legacy). If None, creates a default RiskManager.
            order_manager: Optional order manager for limit order support.
        """
        self.settings = settings
        self.event_bus = event_bus
        self.db_manager = db_manager
        self.rest_client = rest_client
        self.risk_manager: GlobalRiskManager | RiskManager = (
            risk_manager if risk_manager is not None else RiskManager(settings, db_manager)
        )
        self.order_manager: OrderManager | None = order_manager
        self.logger = get_logger(__name__)
        if self.order_manager is not None and hasattr(self.order_manager, "set_fill_handler"):
            self.order_manager.set_fill_handler(self._handle_limit_order_fill)

        self._running = False

        # Statistics
        self._stats = {
            "signals_received": 0,
            "signals_executed": 0,
            "signals_rejected": 0,
            "signals_ignored": 0,
            "execution_errors": 0,
        }

    async def start(self) -> None:
        """Start the execution engine.

        Subscribes to trading signal events and begins processing.
        """
        if self._running:
            self.logger.warning("execution_engine_already_running")
            return

        self._running = True
        await self.event_bus.subscribe(EventType.TRADE_SIGNAL, self._handle_signal)

        self.logger.info(
            "execution_engine_started",
            trading_mode=self.settings.trading.mode.value,
            default_order_eur=self.settings.trading.default_order_amount_eur,
        )

    async def stop(self) -> None:
        """Stop the execution engine.

        Unsubscribes from events and stops processing signals.
        """
        if not self._running:
            self.logger.warning("execution_engine_not_running")
            return

        self._running = False
        await self.event_bus.unsubscribe(EventType.TRADE_SIGNAL, self._handle_signal)

        self.logger.info(
            "execution_engine_stopped",
            stats=self._stats,
        )

    async def _handle_signal(self, data: dict[str, Any]) -> None:
        """Handle incoming trading signal events.

        This is the callback registered with the EventBus for
        TRADE_SIGNAL events.

        Args:
            data: Event data containing the trading signal.
        """
        if not self._running:
            return

        self._stats["signals_received"] += 1

        # Extract the signal from event data
        signal: TradingSignal = data.get("signal")  # type: ignore[assignment]
        if signal is None:
            self.logger.error("signal_missing_from_event", data=data)
            return

        # Ignore HOLD signals
        if not signal.should_trade:
            self._stats["signals_ignored"] += 1
            self.logger.debug(
                "signal_ignored_hold",
                strategy=signal.strategy,
                pair=signal.pair,
                reason=signal.reason,
            )
            return

        self.logger.info(
            "signal_received",
            signal_type=signal.signal_type.value,
            pair=signal.pair,
            price=float(signal.price),
            confidence=signal.confidence,
            reason=signal.reason,
            strategy=signal.strategy,
        )

        try:
            await self._execute_signal(signal)
        except Exception as e:
            self._stats["execution_errors"] += 1
            self.logger.error(
                "signal_execution_error",
                error=str(e),
                error_type=type(e).__name__,
                signal_type=signal.signal_type.value,
                pair=signal.pair,
                strategy=signal.strategy,
                exc_info=e,
            )
            # Publish error event
            await self.event_bus.publish(
                EventType.SYSTEM_ERROR,
                {
                    "error": str(e),
                    "error_type": type(e).__name__,
                    "context": "signal_execution",
                    "signal": signal.to_dict(),
                },
            )

    async def _execute_signal(self, signal: TradingSignal) -> None:
        """Execute a trading signal after validation.

        This method:
        1. Determines order parameters
        2. Gets current balance
        3. Validates through RiskManager
        4. Executes the order if approved
        5. Updates BotState

        Args:
            signal: The trading signal to execute.
        """
        # Determine order side and trading mode
        side = TradeSide.BUY if signal.is_buy else TradeSide.SELL
        trading_mode = signal.metadata.get("mode", "spot")
        is_margin = trading_mode == "margin"

        # Calculate order amount (pass signal for SELL metadata)
        amount = await self._calculate_order_amount(signal.pair, side, signal.price, signal)

        if amount <= Decimal("0"):
            self.logger.warning(
                "order_skipped_zero_amount",
                signal_type=signal.signal_type.value,
                pair=signal.pair,
                side=side.value,
            )
            self._stats["signals_ignored"] += 1
            return

        # Get current balance for risk checks
        balance = await self.rest_client.get_balance()

        # Perform risk validation
        # Pass bot_id for per-strategy checks in GlobalRiskManager
        risk_kwargs: dict[str, Any] = {
            "pair": signal.pair,
            "side": side,
            "amount": amount,
            "price": signal.price,
            "balance": balance,
        }
        if isinstance(self.risk_manager, GlobalRiskManager):
            risk_kwargs["bot_id"] = signal.strategy
            # Add margin-specific risk kwargs
            if is_margin:
                margin_balance = await self.rest_client.get_margin_balance()
                risk_kwargs["trading_mode"] = "margin"
                risk_kwargs["margin_balance"] = margin_balance
                risk_kwargs["leverage"] = signal.metadata.get("leverage", 2)
        risk_result = await self.risk_manager.check_order(**risk_kwargs)

        if risk_result.rejected:
            self._stats["signals_rejected"] += 1
            self.logger.warning(
                "order_rejected_by_risk",
                pair=signal.pair,
                side=side.value,
                amount=float(amount),
                price=float(signal.price),
                reasons=risk_result.reasons,
                strategy=signal.strategy,
            )
            # Publish rejection event
            await self.event_bus.publish(
                EventType.TRADE_ORDER_FAILED,
                {
                    "pair": signal.pair,
                    "side": side.value,
                    "amount": str(amount),
                    "reasons": risk_result.reasons,
                    "context": "risk_rejected",
                },
            )
            return

        # Determine order type from signal metadata
        order_type = signal.metadata.get("order_type", self.settings.order.default_order_type)
        limit_price = signal.metadata.get("limit_price")

        # Before executing a SELL (stop-loss/trailing), cancel any existing profit target
        # For margin: before closing a short (BUY), also cancel pending orders
        if side == TradeSide.SELL and self.order_manager and not is_margin:
            position_id = signal.metadata.get("position_id")
            if position_id is not None:
                await self.order_manager.cancel_profit_target(position_id)
        elif is_margin and side == TradeSide.BUY and self.order_manager:
            position_id = signal.metadata.get("position_id")
            if position_id is not None:
                await self.order_manager.cancel_profit_target(position_id)

        # Route to margin or spot order
        if is_margin:
            # Margin order (all margin orders are market for guaranteed execution)
            trade = await self.rest_client.place_margin_order(
                pair=signal.pair,
                side=side,
                amount=amount,
                strategy=signal.strategy,
                signal_price=signal.price,
                leverage=signal.metadata.get("leverage", 2),
            )

            self._stats["signals_executed"] += 1
            if self._fill_opens_position(signal, side):
                await self._publish_trade_fill_event(
                    trade=trade,
                    side=side,
                    signal=signal,
                    trading_mode="margin",
                )
                await self._update_bot_state(trade, signal)
            else:
                await self._update_bot_state(trade, signal)
                await self._publish_trade_fill_event(
                    trade=trade,
                    side=side,
                    signal=signal,
                    trading_mode="margin",
                )

            self.logger.info(
                "margin_order_executed",
                trade_id=str(trade.id),
                pair=trade.pair,
                side=trade.side.value,
                amount=float(trade.amount),
                price=float(trade.price),
                fee=float(trade.fee),
                strategy=trade.strategy,
                trading_mode="margin",
            )
            return

        # Spot order routing (existing logic unchanged)
        if order_type == "limit" and self.order_manager and limit_price:
            # Limit order via OrderManager
            order = await self.order_manager.place_and_track(
                pair=signal.pair,
                side=side,
                amount=amount,
                price=Decimal(str(limit_price)),
                strategy=signal.strategy,
                signal_metadata=signal.metadata,
            )

            self._stats["signals_executed"] += 1
            self.logger.info(
                "limit_order_placed",
                order_id=order.order_id,
                pair=signal.pair,
                side=side.value,
                amount=float(amount),
                limit_price=float(Decimal(str(limit_price))),
                status=order.status.value,
                strategy=signal.strategy,
            )
        else:
            # Market order (default / stop-loss / trailing)
            trade = await self.rest_client.place_market_order(
                pair=signal.pair,
                side=side,
                amount=amount,
                strategy=signal.strategy,
                signal_price=signal.price,  # Fallback price if Kraken returns None
            )

            self._stats["signals_executed"] += 1

            if self._fill_opens_position(signal, side):
                await self._publish_trade_fill_event(trade=trade, side=side, signal=signal)
                await self._update_bot_state(trade, signal)
            else:
                await self._update_bot_state(trade, signal)
                await self._publish_trade_fill_event(trade=trade, side=side, signal=signal)

            self.logger.info(
                "order_executed",
                trade_id=str(trade.id),
                pair=trade.pair,
                side=trade.side.value,
                amount=float(trade.amount),
                price=float(trade.price),
                fee=float(trade.fee),
                strategy=trade.strategy,
                status=trade.status.value,
            )

    async def _calculate_order_amount(
        self,
        pair: str,
        side: TradeSide,
        price: Decimal,
        signal: TradingSignal | None = None,
    ) -> Decimal:
        """Calculate the order amount based on side and settings.

        For BUY orders, converts the default EUR amount to base currency.
        For SELL orders, reads amount from signal metadata if available,
        otherwise falls back to querying BotState.

        Args:
            pair: Trading pair.
            side: Order side.
            price: Current price.
            signal: Optional signal containing position metadata for SELL orders.

        Returns:
            Order amount in base currency.
        """
        # Margin signals: short-open calculates like BUY, short-close uses exact amount
        if signal and signal.metadata.get("mode") == "margin":
            if signal.metadata.get("is_short_open"):
                # Opening short: calculate size from USDC like a BUY
                eur_amount = Decimal(str(self.settings.trading.default_order_amount_eur))
                multiplier = Decimal("1.0")
                if "position_size_multiplier" in signal.metadata:
                    multiplier = Decimal(str(signal.metadata["position_size_multiplier"]))
                eur_amount = eur_amount * multiplier
                return (eur_amount / price).quantize(Decimal("0.00000001"))
            elif "amount_btc" in signal.metadata:
                # Closing short: use exact position amount
                return Decimal(str(signal.metadata["amount_btc"])).quantize(Decimal("0.00000001"))

        if side == TradeSide.BUY:
            # For BUY: convert default EUR amount to base currency
            eur_amount = Decimal(str(self.settings.trading.default_order_amount_eur))

            # Apply position size multiplier from signal metadata (multi-strategy support)
            multiplier = Decimal("1.0")
            if signal and "position_size_multiplier" in signal.metadata:
                multiplier = Decimal(str(signal.metadata["position_size_multiplier"]))
            eur_amount = eur_amount * multiplier

            amount = eur_amount / price

            # Round to appropriate precision (8 decimal places for crypto)
            return amount.quantize(Decimal("0.00000001"))
        else:
            # For SELL: prefer amount from signal metadata (multi-position support)
            if signal and "amount_btc" in signal.metadata:
                amount = Decimal(str(signal.metadata["amount_btc"]))
                return amount.quantize(Decimal("0.00000001"))

            # Fallback: get position size from BotState (legacy single-position)
            position_size = await self._get_position_size(pair)
            return position_size

    async def _get_position_size(self, pair: str) -> Decimal:
        """Get the current position size for a trading pair.

        Queries the BotState table for the position associated with
        the trading pair.

        Args:
            pair: Trading pair.

        Returns:
            Current position size, or 0 if no position exists.
        """
        from sqlalchemy import select

        from krakenbot.models.trades import BotState

        async with self.db_manager.read_session() as session:
            # Query for bot states that might hold this pair
            # The bot_id typically includes the pair or strategy name
            result = await session.execute(
                select(BotState.position_size)
                .where(BotState.position_size > Decimal("0"))
                .order_by(BotState.updated_at.desc())
                .limit(1)
            )
            position = result.scalar()
            return position if position else Decimal("0")

    async def _update_bot_state(self, trade: Trade, signal: TradingSignal) -> None:
        """Update the BotState after a trade execution.

        Creates or updates the BotState record with position information
        and P&L tracking.

        Args:
            trade: The executed trade.
            signal: The original trading signal.
        """
        from sqlalchemy import select

        from krakenbot.models.trades import BotState

        async with self.db_manager.session() as session:
            # Find or create BotState
            result = await session.execute(
                select(BotState).where(BotState.bot_id == signal.strategy)
            )
            bot_state = result.scalar_one_or_none()

            if bot_state is None:
                # Create new BotState
                bot_state = BotState(
                    bot_id=signal.strategy,
                    strategy=signal.strategy,
                    status=BotStatus.RUNNING,
                    position_size=Decimal("0"),
                    daily_pnl=Decimal("0"),
                    total_pnl=Decimal("0"),
                    daily_trades_count=0,
                )
                session.add(bot_state)

            # Update based on trade type
            if signal.metadata.get("mode") == "margin":
                # Margin: SELL opens position, BUY closes position (inverted)
                if signal.metadata.get("is_short_open"):
                    await self._handle_buy_trade(session, bot_state, trade, signal)
                elif signal.metadata.get("is_short_close"):
                    await self._handle_sell_trade(session, bot_state, trade, signal)
            elif trade.side == TradeSide.BUY:
                # Spot: Opening or adding to position
                await self._handle_buy_trade(session, bot_state, trade, signal)
            else:
                # Spot: Closing position
                await self._handle_sell_trade(session, bot_state, trade, signal)

            # Common updates
            bot_state.last_signal_at = signal.timestamp
            bot_state.updated_at = datetime.now(UTC)

    async def _handle_buy_trade(
        self,
        session: Any,
        bot_state: Any,
        trade: Trade,
        signal: TradingSignal,
    ) -> None:
        """Handle BotState update for a buy trade.

        Creates an OpenPosition record and updates BotState aggregates.

        Args:
            session: Database session.
            bot_state: BotState to update.
            trade: Executed buy trade.
            signal: Original signal.
        """
        import uuid

        from krakenbot.models.base import PositionStatus
        from krakenbot.models.trades import OpenPosition

        position_id = signal.metadata.get("position_id")
        if position_id is None:
            position_id = await self._allocate_fallback_position_id(session, signal.strategy)
            self.logger.warning(
                "position_id_missing_on_open_fill",
                strategy=signal.strategy,
                trade_id=str(trade.id),
                fallback_position_id=position_id,
            )
        reference_price = Decimal(str(signal.metadata.get("reference_price", 0)))

        # Create OpenPosition record
        open_position = OpenPosition(
            id=uuid.uuid4(),
            bot_id=signal.strategy,
            strategy=signal.strategy,
            position_id=position_id,
            pair=trade.pair,
            entry_price=trade.price,
            amount_btc=trade.amount,
            reference_price=reference_price,
            entry_time=trade.timestamp,
            entry_trade_id=trade.id,
            status=PositionStatus.OPEN,
            trading_mode=signal.metadata.get("mode", "spot"),
        )
        session.add(open_position)

        # Update BotState aggregates (cumulative instead of overwrite)
        bot_state.position_size += trade.amount
        # Keep entry_price as latest for backward compatibility
        bot_state.entry_price = trade.price
        bot_state.last_trade_at = trade.timestamp
        bot_state.daily_trades_count += 1

        self.logger.info(
            "position_opened",
            strategy=signal.strategy,
            pair=trade.pair,
            amount=float(trade.amount),
            entry_price=float(trade.price),
            reference_price=float(reference_price),
            position_id=position_id,
            trade_id=str(trade.id),
        )

    async def _allocate_fallback_position_id(self, session: Any, bot_id: str) -> int:
        """Allocate a unique fallback position_id when the strategy did not expose one."""
        from sqlalchemy import func, select

        from krakenbot.models.trades import OpenPosition

        try:
            result = await session.execute(
                select(func.max(OpenPosition.position_id)).where(OpenPosition.bot_id == bot_id)
            )
            current_max = result.scalar_one_or_none()
            if isinstance(current_max, int) and current_max > 0:
                return current_max + 1
        except Exception as e:
            self.logger.warning(
                "fallback_position_id_query_failed",
                strategy=bot_id,
                error=str(e),
                error_type=type(e).__name__,
            )

        return 1

    def _fill_opens_position(self, signal: TradingSignal, side: TradeSide) -> bool:
        """Return True when the fill creates a new runtime position."""
        if signal.metadata.get("mode") == "margin":
            return bool(signal.metadata.get("is_short_open"))
        return side == TradeSide.BUY

    async def _publish_trade_fill_event(
        self,
        *,
        trade: Trade,
        side: TradeSide,
        signal: TradingSignal,
        trading_mode: str | None = None,
    ) -> None:
        """Publish a trade fill event with mutable signal metadata attached."""
        payload: dict[str, Any] = {
            "trade_id": str(trade.id),
            "pair": trade.pair,
            "side": side.value,
            "amount": str(trade.amount),
            "price": str(trade.price),
            "fee": str(trade.fee),
            "strategy": trade.strategy,
            "timestamp": trade.timestamp.isoformat(),
            "reference_price": str(signal.metadata.get("reference_price", "0")),
            "position_id": signal.metadata.get("position_id"),
            "signal_metadata": signal.metadata,
        }
        if trading_mode is not None:
            payload["trading_mode"] = trading_mode

        await self.event_bus.publish(EventType.TRADE_ORDER_FILLED, payload)

    async def _handle_limit_order_fill(self, order: Any) -> None:
        """Persist BotState/OpenPosition updates for limit order fills."""
        from krakenbot.models.trades import Trade as TradeModel

        async with self.db_manager.read_session() as session:
            trade_record = await session.get(TradeModel, order.id)

        if trade_record is None:
            self.logger.warning(
                "limit_fill_trade_record_missing",
                order_id=getattr(order, "order_id", None),
                trade_id=str(getattr(order, "id", "")),
                strategy=getattr(order, "strategy", None),
            )
            return

        signal = TradingSignal(
            signal_type=SignalType.BUY if trade_record.side == TradeSide.BUY else SignalType.SELL,
            pair=trade_record.pair,
            price=trade_record.price,
            confidence=1.0,
            reason="limit_fill_sync",
            strategy=trade_record.strategy,
            timestamp=trade_record.timestamp,
            metadata=dict(getattr(order, "signal_metadata", None) or {}),
        )
        await self._update_bot_state(trade_record, signal)

    async def _handle_sell_trade(
        self,
        session: Any,
        bot_state: Any,
        trade: Trade,
        signal: TradingSignal,
    ) -> None:
        """Handle BotState update for a sell trade.

        Closes the specific OpenPosition and updates BotState aggregates.

        Args:
            session: Database session.
            bot_state: BotState to update.
            trade: Executed sell trade.
            signal: Original signal.
        """
        from sqlalchemy import select

        from krakenbot.models.base import PositionStatus
        from krakenbot.models.trades import OpenPosition
        from krakenbot.models.trades import Trade as TradeModel

        pnl = Decimal("0")
        position_id = signal.metadata.get("position_id")
        entry_price = Decimal(str(signal.metadata.get("entry_price", 0)))

        # Try to find and close the specific OpenPosition
        if position_id is not None:
            result = await session.execute(
                select(OpenPosition)
                .where(OpenPosition.position_id == position_id)
                .where(OpenPosition.bot_id == signal.strategy)
                .where(OpenPosition.status == PositionStatus.OPEN)
            )
            open_position = result.scalar_one_or_none()

            if open_position:
                # Calculate P&L from the actual position entry price
                if open_position.trading_mode == "margin":
                    # Short position: profit when price drops
                    pnl = (open_position.entry_price - trade.price) * trade.amount - trade.fee
                else:
                    pnl = (trade.price - open_position.entry_price) * trade.amount - trade.fee

                # Update OpenPosition
                open_position.status = PositionStatus.CLOSED
                open_position.closed_at = trade.timestamp
                open_position.exit_trade_id = trade.id
                open_position.pnl = pnl
                entry_price = open_position.entry_price

                self.logger.info(
                    "position_closed",
                    strategy=signal.strategy,
                    pair=trade.pair,
                    amount=float(trade.amount),
                    entry_price=float(open_position.entry_price),
                    exit_price=float(trade.price),
                    pnl=float(pnl),
                    position_id=position_id,
                    trade_id=str(trade.id),
                )
            else:
                self.logger.warning(
                    "position_not_found_for_close",
                    position_id=position_id,
                    strategy=signal.strategy,
                )
        else:
            # Legacy: no position_id, use BotState entry_price
            if bot_state.entry_price is not None and bot_state.entry_price > Decimal("0"):
                pnl = (trade.price - bot_state.entry_price) * trade.amount - trade.fee
                entry_price = bot_state.entry_price
                self.logger.info(
                    "position_closed_legacy",
                    strategy=signal.strategy,
                    pair=trade.pair,
                    amount=float(trade.amount),
                    entry_price=float(entry_price),
                    exit_price=float(trade.price),
                    pnl=float(pnl),
                    trade_id=str(trade.id),
                )
            else:
                self.logger.warning(
                    "position_closed_no_entry_price",
                    strategy=signal.strategy,
                    pair=trade.pair,
                    amount=float(trade.amount),
                    exit_price=float(trade.price),
                )

        # Update P&L tracking in BotState
        bot_state.daily_pnl += pnl
        bot_state.total_pnl += pnl

        # Update the trade with P&L
        trade_record = await session.get(TradeModel, trade.id)
        if trade_record:
            trade_record.pnl = pnl

        # Update BotState aggregates (decrement position size)
        bot_state.position_size = max(Decimal("0"), bot_state.position_size - trade.amount)
        if bot_state.position_size == Decimal("0"):
            bot_state.entry_price = None
        bot_state.last_trade_at = trade.timestamp
        bot_state.daily_trades_count += 1

        self.logger.info(
            "bot_state_updated",
            strategy=signal.strategy,
            remaining_position_size=float(bot_state.position_size),
            daily_pnl=float(bot_state.daily_pnl),
            total_pnl=float(bot_state.total_pnl),
        )

    @property
    def is_running(self) -> bool:
        """Check if the execution engine is running.

        Returns:
            True if the engine is active and processing signals.
        """
        return self._running

    @property
    def stats(self) -> dict[str, int]:
        """Get execution statistics.

        Returns:
            Dictionary of execution statistics.
        """
        return self._stats.copy()

    def reset_stats(self) -> None:
        """Reset execution statistics to zero."""
        self._stats = {
            "signals_received": 0,
            "signals_executed": 0,
            "signals_rejected": 0,
            "signals_ignored": 0,
            "execution_errors": 0,
        }

    async def execute_manual_order(
        self,
        pair: str,
        side: TradeSide,
        amount: Decimal,
        strategy: str = "manual",
    ) -> Trade | None:
        """Execute a manual order outside of signal flow.

        This method allows direct order execution while still
        respecting risk management rules.

        Args:
            pair: Trading pair.
            side: Order side.
            amount: Order amount in base currency.
            strategy: Strategy name for tracking.

        Returns:
            Trade object if executed, None if rejected.

        Example:
            >>> trade = await engine.execute_manual_order(
            ...     pair="XBT/EUR",
            ...     side=TradeSide.BUY,
            ...     amount=Decimal("0.001"),
            ... )
        """
        self.logger.info(
            "manual_order_requested",
            pair=pair,
            side=side.value,
            amount=float(amount),
            strategy=strategy,
        )

        # Get current balance and price
        balance = await self.rest_client.get_balance()
        ticker = await self.rest_client.get_ticker(pair)
        price = ticker.get("last", Decimal("0"))

        if price <= Decimal("0"):
            self.logger.error(
                "manual_order_failed_no_price",
                pair=pair,
            )
            return None

        # Risk check
        risk_result = await self.risk_manager.check_order(
            pair=pair,
            side=side,
            amount=amount,
            price=price,
            balance=balance,
        )

        if risk_result.rejected:
            self.logger.warning(
                "manual_order_rejected",
                pair=pair,
                side=side.value,
                reasons=risk_result.reasons,
            )
            return None

        # Execute
        trade = await self.rest_client.place_market_order(
            pair=pair,
            side=side,
            amount=amount,
            strategy=strategy,
        )

        self.logger.info(
            "manual_order_executed",
            trade_id=str(trade.id),
            pair=trade.pair,
            side=trade.side.value,
            amount=float(trade.amount),
            price=float(trade.price),
        )

        return trade
