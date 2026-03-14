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
from typing import TYPE_CHECKING, Any

from krakenbot.connectors.kraken_rest import normalize_asset_balances, normalize_asset_symbol
from krakenbot.core.logger import get_logger
from krakenbot.models.base import TradeSide, TradeStatus

if TYPE_CHECKING:
    from krakenbot.config.settings import (
        MultiStrategySettings,
        Settings,
        StrategyBudget,
    )
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
            normalized_balance = normalize_asset_balances(balance)
            base_currency = normalize_asset_symbol(pair.split("/")[0])
            available = normalized_balance.get(base_currency, Decimal("0"))

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


class GlobalRiskManager:
    """Two-level risk manager for multi-strategy mode.

    Composes the existing RiskManager with an additional global check layer.
    Level 1: Global checks (all strategies combined, no bot_id filter)
    Level 2: Per-strategy checks (filtered by bot_id via StrategyBudget)

    When multi_strategy is disabled, delegates directly to the legacy RiskManager.
    """

    def __init__(
        self,
        settings: Settings,
        db_manager: DatabaseManager,
        multi_strategy_settings: MultiStrategySettings | None = None,
    ) -> None:
        self.settings = settings
        self.db_manager = db_manager
        self.logger = get_logger(__name__)

        self._multi_enabled = (
            multi_strategy_settings is not None and multi_strategy_settings.enabled
        )

        # Global limits
        if self._multi_enabled and multi_strategy_settings is not None:
            self._global_max_positions = multi_strategy_settings.global_max_open_positions
            self._global_daily_loss = Decimal(
                str(multi_strategy_settings.global_daily_loss_limit_eur)
            )
            self._global_max_exposure_pct = (
                multi_strategy_settings.global_max_portfolio_exposure_pct
            )
        else:
            self._global_max_positions = settings.risk.max_open_positions
            self._global_daily_loss = Decimal(str(settings.risk.daily_loss_limit_eur))
            self._global_max_exposure_pct = 100.0

        # Per-strategy budgets: bot_id -> StrategyBudget
        self._budgets: dict[str, StrategyBudget] = {}

        # Per-strategy RiskManagers (with bot_id filtering)
        self._strategy_risk_managers: dict[str, RiskManager] = {}

        # Legacy fallback RiskManager (no bot_id filter)
        self._legacy_risk_manager = RiskManager(settings, db_manager)

        # Global RiskManager (no bot_id filter for global checks)
        self._global_risk_manager = RiskManager(settings, db_manager)

        self.logger.info(
            "global_risk_manager_initialized",
            multi_strategy_enabled=self._multi_enabled,
            global_max_positions=self._global_max_positions,
            global_daily_loss=float(self._global_daily_loss),
        )

    def register_strategy(self, bot_id: str, budget: StrategyBudget) -> None:
        """Register a strategy with its budget for per-strategy risk checks.

        Args:
            bot_id: Unique strategy instance identifier.
            budget: Budget allocation for this strategy.
        """
        self._budgets[bot_id] = budget

        # Create a dedicated RiskManager scoped to this bot_id
        rm = RiskManager(self.settings, self.db_manager, bot_id=bot_id)
        # Override risk limits with per-strategy budget
        rm.max_open_positions = budget.max_open_positions
        rm.daily_loss_limit = Decimal(str(budget.daily_loss_limit_eur))
        rm.max_position_pct = budget.max_position_pct
        self._strategy_risk_managers[bot_id] = rm

        self.logger.info(
            "strategy_budget_registered",
            bot_id=bot_id,
            max_positions=budget.max_open_positions,
            daily_loss_limit=budget.daily_loss_limit_eur,
            max_position_pct=budget.max_position_pct,
            position_size_multiplier=budget.position_size_multiplier,
        )

    async def check_order(
        self,
        pair: str,
        side: TradeSide,
        amount: Decimal,
        price: Decimal,
        balance: dict[str, Decimal],
        bot_id: str | None = None,
        trading_mode: str = "spot",
        margin_balance: dict[str, Decimal] | None = None,
        leverage: int = 2,
    ) -> RiskCheckResult:
        """Validate order with two-level risk checks.

        Level 1 (Global): Balance, total positions, total daily loss, portfolio exposure
        Level 2 (Per-strategy): Strategy positions, strategy daily loss, position size, interval

        For margin orders:
        - BUY-to-close (closing a short): always approved
        - SELL-to-open (opening a short): margin + global checks

        Args:
            pair: Trading pair.
            side: Order side.
            amount: Order amount in base currency.
            price: Current market price.
            balance: Available balances by currency.
            bot_id: Strategy instance identifier for per-strategy checks.
            trading_mode: "spot" or "margin".
            margin_balance: Margin balance info (required for margin orders).
            leverage: Leverage level for margin orders.

        Returns:
            RiskCheckResult with approval status and rejection reasons.
        """
        # === Margin orders: special handling ===
        if trading_mode == "margin":
            # BUY-to-close (closing a short): always approved
            if side == TradeSide.BUY:
                self.logger.info(
                    "margin_buy_to_close_approved",
                    pair=pair,
                    bot_id=bot_id,
                )
                return RiskCheckResult(approved=True)

            # SELL-to-open (opening a short): margin + global checks
            result = RiskCheckResult(approved=True)

            # Check margin availability
            if margin_balance:
                await self._check_margin_available(result, amount, price, margin_balance, leverage)

            # Check liquidation distance
            await self._check_liquidation_distance(result, price, leverage)

            # Global position count
            if self._multi_enabled:
                global_positions = await self._get_global_open_positions_count()
                if global_positions >= self._global_max_positions:
                    result.add_reason(
                        f"Global max positions reached: {global_positions} "
                        f">= {self._global_max_positions}"
                    )

                # Global daily loss
                global_daily_pnl = await self._get_global_daily_pnl()
                if global_daily_pnl <= -self._global_daily_loss:
                    result.add_reason(
                        f"Global daily loss limit reached: {global_daily_pnl:.2f} "
                        f"<= -{self._global_daily_loss:.2f}"
                    )

            # Per-strategy checks
            if bot_id and bot_id in self._strategy_risk_managers:
                strategy_rm = self._strategy_risk_managers[bot_id]
                strategy_result = await strategy_rm.check_order(pair, side, amount, price, balance)
                if strategy_result.rejected:
                    for reason in strategy_result.reasons:
                        result.add_reason(f"[{bot_id}] {reason}")

            if result.approved:
                self.logger.info("margin_sell_to_open_approved", pair=pair, bot_id=bot_id)
            else:
                self.logger.warning(
                    "margin_sell_to_open_rejected",
                    pair=pair,
                    bot_id=bot_id,
                    reasons=result.reasons,
                )
            return result

        # === Spot orders: existing logic ===

        # Legacy mode: delegate directly to the existing RiskManager
        if not self._multi_enabled:
            if bot_id:
                self._legacy_risk_manager.set_bot_id(bot_id)
            return await self._legacy_risk_manager.check_order(pair, side, amount, price, balance)

        result = RiskCheckResult(approved=True)

        # === Level 1: Global checks (no bot_id filter) ===
        # Balance check (global - uses actual exchange balance)
        await self._global_risk_manager._check_balance(result, pair, side, amount, price, balance)

        if side == TradeSide.BUY:
            # Global position count (all strategies)
            global_positions = await self._get_global_open_positions_count()
            if global_positions >= self._global_max_positions:
                result.add_reason(
                    f"Global max positions reached: {global_positions} "
                    f">= {self._global_max_positions}"
                )

            # Global daily loss (all strategies)
            global_daily_pnl = await self._get_global_daily_pnl()
            if global_daily_pnl <= -self._global_daily_loss:
                result.add_reason(
                    f"Global daily loss limit reached: {global_daily_pnl:.2f} "
                    f"<= -{self._global_daily_loss:.2f}"
                )

            # Global portfolio exposure
            await self._check_global_exposure(result, pair, amount, price, balance)

        # === Level 2: Per-strategy checks (filtered by bot_id) ===
        if bot_id and bot_id in self._strategy_risk_managers:
            strategy_rm = self._strategy_risk_managers[bot_id]
            strategy_result = await strategy_rm.check_order(pair, side, amount, price, balance)
            if strategy_result.rejected:
                for reason in strategy_result.reasons:
                    result.add_reason(f"[{bot_id}] {reason}")

        # Log result
        if result.approved:
            self.logger.info(
                "global_risk_check_passed",
                pair=pair,
                side=side.value,
                bot_id=bot_id,
            )
        else:
            self.logger.warning(
                "global_risk_check_failed",
                pair=pair,
                side=side.value,
                bot_id=bot_id,
                reasons=result.reasons,
            )

        return result

    async def _check_margin_available(
        self,
        result: RiskCheckResult,
        amount: Decimal,
        price: Decimal,
        margin_balance: dict[str, Decimal],
        leverage: int = 2,
    ) -> None:
        """Check that sufficient margin collateral is available.

        Margin required = (amount * price) / leverage.

        Args:
            result: Risk check result to update.
            amount: Order amount in base currency.
            price: Current market price.
            margin_balance: Margin balance info with "available_margin" key.
            leverage: Leverage level.
        """
        margin_required = (amount * price) / Decimal(str(leverage))
        available = margin_balance.get("available_margin", Decimal("0"))
        if margin_required > available:
            result.add_reason(
                f"Insufficient margin: need {margin_required:.2f}, available {available:.2f}"
            )

    async def _check_liquidation_distance(
        self,
        result: RiskCheckResult,
        price: Decimal,
        leverage: int = 2,
        min_distance_pct: float = 20.0,
    ) -> None:
        """Check that liquidation price is far enough from current price.

        For a short at leverage L, liquidation occurs at approximately:
        liquidation_price = entry_price * (1 + 1/L)

        Args:
            result: Risk check result to update.
            price: Current market price (entry price for new short).
            leverage: Leverage level.
            min_distance_pct: Minimum acceptable distance to liquidation (%).
        """
        liquidation_price = price * (Decimal("1") + Decimal("1") / Decimal(str(leverage)))
        distance_pct = ((liquidation_price - price) / price) * Decimal("100")
        if distance_pct < Decimal(str(min_distance_pct)):
            result.add_reason(
                f"Liquidation too close: {float(distance_pct):.1f}% < {min_distance_pct}%"
            )

    async def check_emergency_stop_loss(
        self,
        entry_price: Decimal,
        current_price: Decimal,
    ) -> bool:
        """Delegate emergency stop-loss check to legacy RiskManager."""
        return await self._legacy_risk_manager.check_emergency_stop_loss(entry_price, current_price)

    async def _get_global_open_positions_count(self) -> int:
        """Get total open positions across ALL strategies (no bot_id filter)."""
        from sqlalchemy import func, select

        from krakenbot.models.base import PositionStatus
        from krakenbot.models.trades import OpenPosition

        async with self.db_manager.read_session() as session:
            result = await session.execute(
                select(func.count(OpenPosition.id)).where(
                    OpenPosition.status == PositionStatus.OPEN
                )
            )
            return result.scalar() or 0

    async def _get_global_daily_pnl(self) -> Decimal:
        """Get total daily P&L across ALL strategies (no bot_id filter)."""
        from sqlalchemy import func, select

        from krakenbot.models.trades import Trade

        async with self.db_manager.read_session() as session:
            today = datetime.now(UTC).date()
            result = await session.execute(
                select(func.coalesce(func.sum(Trade.pnl), 0))
                .where(func.date(Trade.timestamp) == today)
                .where(Trade.status == TradeStatus.FILLED)
            )
            scalar_result = result.scalar()
            return Decimal(str(scalar_result)) if scalar_result else Decimal("0")

    async def _check_global_exposure(
        self,
        result: RiskCheckResult,
        pair: str,
        amount: Decimal,
        price: Decimal,
        balance: dict[str, Decimal],
    ) -> None:
        """Check that total portfolio exposure doesn't exceed global limit."""
        from sqlalchemy import func, select

        from krakenbot.models.base import PositionStatus
        from krakenbot.models.trades import OpenPosition

        quote_currency = pair.split("/")[1] if "/" in pair else "EUR"
        portfolio_value = balance.get(quote_currency, Decimal("0"))
        if portfolio_value <= Decimal("0"):
            return

        # Sum of all open position values
        async with self.db_manager.read_session() as session:
            result_db = await session.execute(
                select(func.sum(OpenPosition.amount_btc * OpenPosition.entry_price)).where(
                    OpenPosition.status == PositionStatus.OPEN
                )
            )
            current_exposure = result_db.scalar() or Decimal("0")

        new_order_value = amount * price
        total_exposure = current_exposure + new_order_value
        exposure_pct = (total_exposure / portfolio_value) * Decimal("100")

        if exposure_pct > Decimal(str(self._global_max_exposure_pct)):
            result.add_reason(
                f"Global portfolio exposure too high: {exposure_pct:.1f}% "
                f"> {self._global_max_exposure_pct}%"
            )

    def get_risk_summary(self) -> dict[str, Any]:
        """Get a summary of global and per-strategy risk configuration."""
        summary: dict[str, Any] = {
            "multi_strategy_enabled": self._multi_enabled,
            "global_max_positions": self._global_max_positions,
            "global_daily_loss_limit": float(self._global_daily_loss),
            "global_max_exposure_pct": self._global_max_exposure_pct,
            "registered_strategies": list(self._budgets.keys()),
        }
        for bot_id, budget in self._budgets.items():
            summary[f"budget_{bot_id}"] = {
                "max_positions": budget.max_open_positions,
                "daily_loss_limit": budget.daily_loss_limit_eur,
                "max_position_pct": budget.max_position_pct,
                "position_size_multiplier": budget.position_size_multiplier,
            }
        return summary
