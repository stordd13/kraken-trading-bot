"""Risk management module for validating orders before execution.

This module provides the RiskManager class that validates all trading orders
against configurable risk limits before execution.

Risk Checks Performed:
    1. Sufficient balance for the order
    2. Position size within portfolio limits
    3. Daily loss limit not exceeded
    4. Maximum open positions not reached
    5. Minimum trade interval respected

Example:
    >>> from krakenbot.execution.risk import RiskManager, RiskCheckResult
    >>> risk_manager = RiskManager(settings, db_manager)
    >>> result = await risk_manager.check_order(
    ...     pair="XBT/EUR",
    ...     side=TradeSide.BUY,
    ...     amount=Decimal("0.001"),
    ...     price=Decimal("42000"),
    ...     balance={"EUR": Decimal("1000")}
    ... )
    >>> if result.approved:
    ...     # Execute the order
    ...     pass
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import TYPE_CHECKING

from krakenbot.core.logger import get_logger
from krakenbot.models.base import TradeSide, TradeStatus

if TYPE_CHECKING:
    from krakenbot.config.settings import Settings
    from krakenbot.core.database import DatabaseManager


@dataclass
class RiskCheckResult:
    """Result of a risk validation check.

    This dataclass holds the outcome of a risk check, including whether
    the order was approved and any reasons for rejection.

    Attributes:
        approved: Whether the order is approved (True) or rejected (False).
        reasons: List of rejection reasons (empty if approved).

    Example:
        >>> result = RiskCheckResult(approved=True)
        >>> result.add_reason("Daily loss limit exceeded")
        >>> print(result.approved)  # False
        >>> print(result.reasons)  # ["Daily loss limit exceeded"]
    """

    approved: bool
    reasons: list[str] = field(default_factory=list)

    @property
    def rejected(self) -> bool:
        """Check if the order is rejected.

        Returns:
            True if the order was rejected, False if approved.
        """
        return not self.approved

    def add_reason(self, reason: str) -> None:
        """Add a rejection reason and mark the order as not approved.

        Args:
            reason: Human-readable explanation for the rejection.
        """
        self.reasons.append(reason)
        self.approved = False

    def to_dict(self) -> dict[str, bool | list[str]]:
        """Convert result to dictionary for logging.

        Returns:
            Dictionary representation of the result.
        """
        return {
            "approved": self.approved,
            "reasons": self.reasons,
        }


class RiskManager:
    """Risk management validator for trading orders.

    The RiskManager validates all orders against configured risk limits
    before they are sent to the exchange. It performs multiple checks
    and aggregates all rejection reasons.

    Risk Limits Checked:
        - Sufficient balance available
        - Position size within max % of portfolio
        - Daily loss limit not exceeded
        - Maximum number of open positions
        - Minimum interval between trades

    Attributes:
        settings: Application settings containing risk configuration.
        db_manager: Database manager for querying historical data.
        max_position_pct: Maximum position size as percentage of portfolio.
        daily_loss_limit: Maximum daily loss allowed in EUR.
        max_open_positions: Maximum number of simultaneous positions.
        min_trade_interval: Minimum time between trades.
        emergency_stop_loss_pct: Emergency stop-loss percentage.

    Example:
        >>> risk_manager = RiskManager(settings, db_manager)
        >>> result = await risk_manager.check_order(
        ...     pair="XBT/EUR",
        ...     side=TradeSide.BUY,
        ...     amount=Decimal("0.001"),
        ...     price=Decimal("42000"),
        ...     balance={"EUR": Decimal("1000"), "XBT": Decimal("0")}
        ... )
        >>> if result.rejected:
        ...     logger.warning("Order rejected", reasons=result.reasons)
    """

    def __init__(
        self,
        settings: Settings,
        db_manager: DatabaseManager,
        bot_id: str | None = None,
    ) -> None:
        """Initialize the RiskManager.

        Args:
            settings: Application settings containing risk configuration.
            db_manager: Database manager for querying trade history.
            bot_id: Optional bot instance identifier for filtering queries.
                    If provided, queries will be scoped to this bot only.
        """
        self.settings = settings
        self.db_manager = db_manager
        self.bot_id = bot_id
        self.logger = get_logger(__name__)

        # Extract risk limits from settings
        self.max_position_pct = settings.risk.max_position_pct
        self.daily_loss_limit = Decimal(str(settings.risk.daily_loss_limit_eur))
        self.max_open_positions = settings.risk.max_open_positions
        self.min_trade_interval = timedelta(seconds=settings.risk.min_trade_interval_sec)
        self.emergency_stop_loss_pct = settings.risk.emergency_stop_loss_pct

        self.logger.info(
            "risk_manager_initialized",
            bot_id=bot_id,
            max_position_pct=self.max_position_pct,
            daily_loss_limit_eur=float(self.daily_loss_limit),
            max_open_positions=self.max_open_positions,
            min_trade_interval_sec=self.min_trade_interval.total_seconds(),
        )

    def set_bot_id(self, bot_id: str) -> None:
        """Set the bot_id for filtering queries.

        This is useful when bot_id is not known at initialization time.

        Args:
            bot_id: Bot instance identifier.
        """
        self.bot_id = bot_id
        self.logger.debug("risk_manager_bot_id_set", bot_id=bot_id)

    async def check_order(
        self,
        pair: str,
        side: TradeSide,
        amount: Decimal,
        price: Decimal,
        balance: dict[str, Decimal],
    ) -> RiskCheckResult:
        """Validate an order against all risk rules.

        This method performs comprehensive risk validation by running
        all configured checks and aggregating results.

        Args:
            pair: Trading pair (e.g., "XBT/EUR").
            side: Order side (BUY or SELL).
            amount: Order amount in base currency.
            price: Current market price.
            balance: Available balances by currency.

        Returns:
            RiskCheckResult with approval status and rejection reasons.

        Example:
            >>> result = await risk_manager.check_order(
            ...     pair="XBT/EUR",
            ...     side=TradeSide.BUY,
            ...     amount=Decimal("0.001"),
            ...     price=Decimal("42000"),
            ...     balance={"EUR": Decimal("1000")}
            ... )
            >>> if result.approved:
            ...     execute_order()
        """
        result = RiskCheckResult(approved=True)

        # Run all risk checks
        await self._check_balance(result, pair, side, amount, price, balance)
        await self._check_position_size(result, pair, side, amount, price, balance)
        await self._check_daily_loss_limit(result)
        await self._check_max_open_positions(result, side)
        await self._check_trade_interval(result)

        # Log the result
        if result.approved:
            self.logger.info(
                "risk_check_passed",
                pair=pair,
                side=side.value,
                amount=float(amount),
                price=float(price),
            )
        else:
            self.logger.warning(
                "risk_check_failed",
                pair=pair,
                side=side.value,
                amount=float(amount),
                price=float(price),
                reasons=result.reasons,
            )

        return result

    async def _check_balance(
        self,
        result: RiskCheckResult,
        pair: str,
        side: TradeSide,
        amount: Decimal,
        price: Decimal,
        balance: dict[str, Decimal],
    ) -> None:
        """Verify sufficient balance for the order.

        For BUY orders, checks if enough quote currency (EUR) is available.
        For SELL orders, checks if enough base currency is available.

        Args:
            result: RiskCheckResult to update.
            pair: Trading pair.
            side: Order side.
            amount: Order amount in base currency.
            price: Current price.
            balance: Available balances.
        """
        if side == TradeSide.BUY:
            # For BUY: need quote currency (EUR)
            required = amount * price
            quote_currency = pair.split("/")[1]
            available = balance.get(quote_currency, Decimal("0"))

            if required > available:
                result.add_reason(
                    f"Insufficient balance: need {required:.2f} {quote_currency}, "
                    f"have {available:.2f} {quote_currency}"
                )
        else:
            # For SELL: need base currency
            base_currency = pair.split("/")[0]
            # Normalize XBT to BTC (Kraken uses XBT in pairs but BTC in balances via ccxt)
            if base_currency == "XBT":
                base_currency = "BTC"
            available = balance.get(base_currency, Decimal("0"))

            if amount > available:
                result.add_reason(
                    f"Insufficient {base_currency}: need {amount:.8f}, have {available:.8f}"
                )

    async def _check_position_size(
        self,
        result: RiskCheckResult,
        pair: str,
        side: TradeSide,
        amount: Decimal,
        price: Decimal,
        balance: dict[str, Decimal],
    ) -> None:
        """Verify position size is within portfolio limits.

        Calculates the order value as a percentage of total portfolio
        and rejects if it exceeds the configured maximum.
        Only applies to BUY orders (opening new positions).
        SELL orders are always allowed as they close existing positions.

        Args:
            result: RiskCheckResult to update.
            pair: Trading pair (e.g., "XBT/USDC").
            side: Order side (BUY or SELL).
            amount: Order amount in base currency.
            price: Current price.
            balance: Available balances.
        """
        # Only check position size for BUY orders (opening positions)
        # SELL orders close existing positions, so no size limit applies
        if side != TradeSide.BUY:
            return

        # Get the quote currency from the trading pair (e.g., "XBT/USDC" -> "USDC")
        quote_currency = pair.split("/")[1] if "/" in pair else "EUR"

        # Calculate total portfolio value in the quote currency
        total_portfolio_value = balance.get(quote_currency, Decimal("0"))

        # Also check EUR as fallback if quote currency not found
        if total_portfolio_value <= Decimal("0") and quote_currency != "EUR":
            total_portfolio_value = balance.get("EUR", Decimal("0"))

        if total_portfolio_value <= Decimal("0"):
            result.add_reason(
                f"Portfolio value is zero: no {quote_currency} or EUR balance available"
            )
            return

        # Calculate position size as percentage
        order_value = amount * price
        position_pct = (order_value / total_portfolio_value) * Decimal("100")

        if position_pct > Decimal(str(self.max_position_pct)):
            result.add_reason(
                f"Position size too large: {position_pct:.1f}% > {self.max_position_pct}% limit"
            )

    async def _check_daily_loss_limit(self, result: RiskCheckResult) -> None:
        """Verify daily loss limit is not exceeded.

        Queries the database for today's realized P&L and rejects
        if the loss limit has been reached.

        Args:
            result: RiskCheckResult to update.
        """
        daily_pnl = await self._get_daily_pnl()

        if daily_pnl <= -self.daily_loss_limit:
            result.add_reason(
                f"Daily loss limit reached: {daily_pnl:.2f} EUR <= -{self.daily_loss_limit:.2f} EUR"
            )

    async def _check_max_open_positions(
        self,
        result: RiskCheckResult,
        side: TradeSide,
    ) -> None:
        """Verify maximum open positions limit is not exceeded.

        Only applies to BUY orders (opening new positions).
        SELL orders are always allowed as they close positions.

        Args:
            result: RiskCheckResult to update.
            side: Order side.
        """
        # Only check for BUY orders (opening positions)
        if side != TradeSide.BUY:
            return

        open_positions = await self._get_open_positions_count()

        if open_positions >= self.max_open_positions:
            result.add_reason(
                f"Max open positions reached: {open_positions} >= {self.max_open_positions}"
            )

    async def _check_trade_interval(self, result: RiskCheckResult) -> None:
        """Verify minimum trade interval has elapsed.

        Queries the database for the last trade timestamp and rejects
        if not enough time has passed.

        Args:
            result: RiskCheckResult to update.
        """
        last_trade_at = await self._get_last_trade_time()

        if last_trade_at is not None:
            time_since_last = datetime.now(UTC) - last_trade_at

            if time_since_last < self.min_trade_interval:
                remaining = self.min_trade_interval - time_since_last
                result.add_reason(
                    f"Trade too soon: {time_since_last.total_seconds():.0f}s since "
                    f"last trade, minimum is {self.min_trade_interval.total_seconds():.0f}s "
                    f"(wait {remaining.total_seconds():.0f}s)"
                )

    async def _get_daily_pnl(self) -> Decimal:
        """Get the total realized P&L for today.

        Queries the trades_history table for all filled trades today
        and sums up their P&L values. If bot_id is set, only counts
        trades for this bot instance.

        Returns:
            Total P&L for today in EUR.
        """
        from sqlalchemy import func, select

        from krakenbot.models.trades import Trade

        async with self.db_manager.read_session() as session:
            today = datetime.now(UTC).date()
            query = (
                select(func.coalesce(func.sum(Trade.pnl), 0))
                .where(func.date(Trade.timestamp) == today)
                .where(Trade.status == TradeStatus.FILLED)
            )

            # Filter by bot_id (strategy name) if set
            if self.bot_id:
                query = query.where(Trade.strategy == self.bot_id)

            result = await session.execute(query)
            scalar_result = result.scalar()
            return Decimal(str(scalar_result)) if scalar_result else Decimal("0")

    async def _get_open_positions_count(self) -> int:
        """Get the number of currently open positions.

        Queries the open_positions table for positions with status='open'.
        If bot_id is set, only counts positions for this bot instance.

        Returns:
            Number of open positions.
        """
        from sqlalchemy import func, select

        from krakenbot.models.base import PositionStatus
        from krakenbot.models.trades import OpenPosition

        async with self.db_manager.read_session() as session:
            query = select(func.count(OpenPosition.id)).where(
                OpenPosition.status == PositionStatus.OPEN
            )

            # Filter by bot_id if set (for multi-instance isolation)
            if self.bot_id:
                query = query.where(OpenPosition.bot_id == self.bot_id)

            result = await session.execute(query)
            return result.scalar() or 0

    async def _get_last_trade_time(self) -> datetime | None:
        """Get the timestamp of the most recent filled trade.

        Queries the trades_history table for the latest filled trade.
        If bot_id is set, only considers trades for this bot instance.

        Returns:
            Datetime of last trade, or None if no trades exist.
        """
        from sqlalchemy import select

        from krakenbot.models.trades import Trade

        async with self.db_manager.read_session() as session:
            query = (
                select(Trade.timestamp)
                .where(Trade.status == TradeStatus.FILLED)
                .order_by(Trade.timestamp.desc())
                .limit(1)
            )

            # Filter by bot_id if set
            if self.bot_id:
                query = query.where(Trade.strategy == self.bot_id)

            result = await session.execute(query)
            return result.scalar()

    async def check_emergency_stop_loss(
        self,
        entry_price: Decimal,
        current_price: Decimal,
    ) -> bool:
        """Check if emergency stop-loss should be triggered.

        Calculates the percentage loss from entry price and triggers
        emergency stop-loss if it exceeds the configured threshold.

        Args:
            entry_price: Position entry price.
            current_price: Current market price.

        Returns:
            True if emergency stop-loss should be triggered.
        """
        if entry_price <= Decimal("0"):
            return False

        loss_pct = ((entry_price - current_price) / entry_price) * Decimal("100")

        if loss_pct >= Decimal(str(self.emergency_stop_loss_pct)):
            self.logger.warning(
                "emergency_stop_loss_triggered",
                entry_price=float(entry_price),
                current_price=float(current_price),
                loss_pct=float(loss_pct),
                threshold_pct=self.emergency_stop_loss_pct,
            )
            return True

        return False

    def get_risk_summary(self) -> dict[str, float | int]:
        """Get a summary of current risk configuration.

        Returns:
            Dictionary with all risk limit configurations.
        """
        return {
            "max_position_pct": self.max_position_pct,
            "daily_loss_limit_eur": float(self.daily_loss_limit),
            "max_open_positions": self.max_open_positions,
            "min_trade_interval_sec": self.min_trade_interval.total_seconds(),
            "emergency_stop_loss_pct": self.emergency_stop_loss_pct,
        }
