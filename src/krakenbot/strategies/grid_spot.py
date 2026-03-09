"""Grid spot trading strategy.

Places a grid of BUY and SELL limit orders at regular intervals around the
current price. When a BUY fills -> place a SELL at the upper level.
When a SELL fills -> place a BUY at the lower level.
Each completed buy/sell pair = guaranteed profit (the grid spacing).

The grid does NOT depend on MarketRegime — it works in all regimes.
It uses geometric spacing (better for crypto than linear).

Params (from strategies.yaml):
    grid_levels: Number of grid levels (default 10)
    grid_spacing_pct: Minimum spacing between levels in % (default 2.0)
    range_size_pct: Total range as % of price (default 20.0)
    rebalance_threshold_pct: Rebalance if price exits center by this % (default 5.0)
    order_amount_usdc: USDC amount per grid level (default 30)
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from typing import TYPE_CHECKING, Any

from krakenbot.core.event_bus import EventType
from krakenbot.models.base import SignalType
from krakenbot.strategies.base import BaseStrategy, TradingSignal

if TYPE_CHECKING:
    from krakenbot.config.settings import Settings
    from krakenbot.core.database import DatabaseManager
    from krakenbot.core.event_bus import EventBus


@dataclass
class GridOrder:
    """A single limit order in the grid."""

    price: Decimal
    side: str  # "buy" or "sell"
    status: str  # "pending", "filled", "cancelled"
    amount_usdc: Decimal
    position_id: int | None = None


@dataclass
class GridPosition:
    """A completed buy that is waiting for its sell pair."""

    entry_price: Decimal
    entry_time: datetime
    amount_btc: Decimal
    amount_usdc: Decimal
    position_id: int
    sell_level: Decimal


class GridSpotStrategy(BaseStrategy):
    """Grid spot trading strategy with geometric spacing.

    Manages an ensemble of limit orders at fixed price levels.
    Overrides _handle_ohlc() to manage multiple simultaneous orders
    instead of the one-signal-per-candle pattern.
    """

    def __init__(
        self,
        settings: Settings,
        event_bus: EventBus,
        db_manager: DatabaseManager,
        bot_id: str | None = None,
        strategy_params: dict[str, Any] | None = None,
        analyzer: Any | None = None,
    ) -> None:
        """Initialize GridSpotStrategy."""
        super().__init__(
            settings,
            event_bus,
            db_manager,
            bot_id=bot_id,
            strategy_params=strategy_params,
            analyzer=analyzer,
        )

        params = strategy_params or {}
        self.pair = settings.trading.pair

        # Grid parameters
        self.grid_levels: int = int(params.get("grid_levels", 10))
        self.grid_spacing_pct: Decimal = Decimal(str(params.get("grid_spacing_pct", 2.0)))
        self.range_size_pct: Decimal = Decimal(str(params.get("range_size_pct", 20.0)))
        self.rebalance_threshold_pct: Decimal = Decimal(
            str(params.get("rebalance_threshold_pct", 5.0))
        )
        self.order_amount_usdc: Decimal = Decimal(str(params.get("order_amount_usdc", 30)))

        # Budget params
        budget = None
        if settings.multi_strategy.enabled:
            for s in settings.multi_strategy.strategies:
                if s.bot_id == bot_id:
                    budget = s.budget
                    break
        self.max_open_positions = budget.max_open_positions if budget else self.grid_levels
        self.position_size_multiplier = budget.position_size_multiplier if budget else 1.0

        # Grid state
        self._grid_orders: dict[str, GridOrder] = {}  # key = f"{side}_{price}"
        self._grid_positions: list[GridPosition] = []
        self._grid_center: Decimal | None = None
        self._grid_initialized: bool = False
        self._next_position_id: int = 1

        # Price state
        self._current_price: Decimal | None = None
        self._current_timestamp: datetime | None = None

        # Tracking
        self._total_grid_profit: Decimal = Decimal("0")
        self._completed_pairs: int = 0
        self._total_orders_placed: int = 0
        self._rebalance_count: int = 0

        # Backtest compatibility
        self._skip_db_sync: bool = False

        self.logger.debug(
            "grid_spot_initialized",
            bot_id=self.bot_id,
            grid_levels=self.grid_levels,
            grid_spacing_pct=float(self.grid_spacing_pct),
            range_size_pct=float(self.range_size_pct),
            order_amount_usdc=float(self.order_amount_usdc),
        )

    # ------------------------------------------------------------------
    # Grid initialization
    # ------------------------------------------------------------------

    def initialize_grid(self, current_price: Decimal) -> list[GridOrder]:
        """Calculate grid levels and create initial orders.

        Uses geometric spacing (better than linear for crypto).

        Args:
            current_price: Current market price to center the grid around.

        Returns:
            List of GridOrder objects created.
        """
        half_range = current_price * self.range_size_pct / Decimal("200")
        grid_low = current_price - half_range
        grid_high = current_price + half_range

        self._grid_center = current_price
        self._grid_orders.clear()

        orders: list[GridOrder] = []

        for i in range(self.grid_levels):
            # Geometric spacing
            ratio = Decimal(str(i)) / Decimal(str(self.grid_levels - 1))
            level_price = grid_low * (grid_high / grid_low) ** ratio
            # Round to 1 decimal (Kraken BTC precision)
            level_price = level_price.quantize(Decimal("0.1"))

            if level_price < current_price:
                order = GridOrder(
                    price=level_price,
                    side="buy",
                    status="pending",
                    amount_usdc=self.order_amount_usdc,
                )
            elif level_price > current_price:
                order = GridOrder(
                    price=level_price,
                    side="sell",
                    status="pending",
                    amount_usdc=self.order_amount_usdc,
                )
            else:
                # Exactly at price — skip or place as buy
                continue

            key = f"{order.side}_{order.price}"
            self._grid_orders[key] = order
            orders.append(order)
            self._total_orders_placed += 1

        self._grid_initialized = True

        self.logger.info(
            "grid_initialized",
            center=float(current_price),
            low=float(grid_low),
            high=float(grid_high),
            levels=len(orders),
            buy_levels=sum(1 for o in orders if o.side == "buy"),
            sell_levels=sum(1 for o in orders if o.side == "sell"),
        )

        return orders

    # ------------------------------------------------------------------
    # Grid level computation (overridable by GridAdaptive)
    # ------------------------------------------------------------------

    def _calculate_grid_range(self, current_price: Decimal) -> tuple[Decimal, Decimal] | None:
        """Calculate the grid range (low, high).

        Override this in GridAdaptiveStrategy to use ATR.

        Returns:
            Tuple of (grid_low, grid_high) or None if cannot compute.
        """
        half_range = current_price * self.range_size_pct / Decimal("200")
        return (current_price - half_range, current_price + half_range)

    # ------------------------------------------------------------------
    # BaseStrategy overrides
    # ------------------------------------------------------------------

    async def on_tick(self, tick_data: dict[str, Any]) -> None:
        """Handle tick data — update current price."""
        price = tick_data.get("price")
        if price is not None:
            self._current_price = Decimal(str(price))

    async def on_ohlc(self, ohlc_data: dict[str, Any]) -> None:
        """Handle OHLC data — update price state."""
        close = ohlc_data.get("close")
        if close is not None:
            self._current_price = Decimal(str(close))
        ts = ohlc_data.get("timestamp")
        if ts:
            self._current_timestamp = (
                ts
                if isinstance(ts, datetime)
                else datetime.fromisoformat(ts)
                if isinstance(ts, str)
                else datetime.fromtimestamp(ts, tz=UTC)
            )

    async def generate_signal(self) -> TradingSignal | None:
        """Grid manages its own signals — always returns None."""
        return None

    def get_name(self) -> str:
        """Return strategy name."""
        return "grid_spot"

    def get_config(self) -> dict[str, Any]:
        """Return strategy configuration."""
        return {
            "grid_levels": self.grid_levels,
            "grid_spacing_pct": float(self.grid_spacing_pct),
            "range_size_pct": float(self.range_size_pct),
            "rebalance_threshold_pct": float(self.rebalance_threshold_pct),
            "order_amount_usdc": float(self.order_amount_usdc),
            "grid_center": float(self._grid_center) if self._grid_center else None,
            "completed_pairs": self._completed_pairs,
            "total_grid_profit": float(self._total_grid_profit),
        }

    async def _handle_ohlc(self, data: dict[str, Any]) -> None:
        """Override base _handle_ohlc to manage grid orders.

        Instead of one-signal-per-candle, the grid:
        1. Updates price state
        2. Initializes the grid if first candle
        3. In live mode: emits limit order signals for new grid orders
        4. Checks if rebalance is needed
        """
        if not self._running:
            return

        try:
            await self.on_ohlc(data)

            if self._current_price is None:
                return

            # Initialize grid on first price
            if not self._grid_initialized:
                orders = self.initialize_grid(self._current_price)
                # In live mode, emit signals for initial orders
                if not self._skip_db_sync:
                    for order in orders:
                        await self._emit_grid_signal(order)
                return

            # Update highest price for trailing in positions
            for pos in self._grid_positions:
                if self._current_price > pos.entry_price:
                    # Track for potential sell level adjustment
                    pass

            # Check rebalance
            if self._should_rebalance(self._current_price):
                await self._rebalance_grid(self._current_price)

        except Exception as e:
            self.logger.error(
                "grid_ohlc_handler_error",
                error=str(e),
                error_type=type(e).__name__,
                exc_info=e,
            )

    # ------------------------------------------------------------------
    # Live mode: signal emission
    # ------------------------------------------------------------------

    async def _emit_grid_signal(self, order: GridOrder) -> None:
        """Emit a TRADE_SIGNAL for a grid order (live/paper mode)."""
        if self._current_price is None or self._current_timestamp is None:
            return

        signal_type = SignalType.BUY if order.side == "buy" else SignalType.SELL
        signal = TradingSignal(
            signal_type=signal_type,
            pair=self.pair,
            price=self._current_price,
            confidence=0.8,
            reason=f"Grid {order.side.upper()} at level {order.price}",
            strategy=self.bot_id,
            timestamp=self._current_timestamp,
            metadata={
                "order_type": "limit",
                "limit_price": float(order.price),
                "position_size_multiplier": self.position_size_multiplier,
                "grid_level": float(order.price),
                "reference_price": float(self._current_price),
                "mode": "spot",
            },
        )

        await self.event_bus.publish(
            EventType.TRADE_SIGNAL,
            {"signal": signal, "strategy": self.get_name()},
        )

        self.logger.debug(
            "grid_signal_emitted",
            side=order.side,
            level_price=float(order.price),
            current_price=float(self._current_price),
        )

    # ------------------------------------------------------------------
    # Trade filled handling (live/paper mode)
    # ------------------------------------------------------------------

    async def on_trade_filled(
        self,
        trade_id: str,
        pair: str,
        side: str,
        amount: Decimal,
        price: Decimal,
        fee: Decimal,
        reference_price: Decimal | None,
        position_id: int | None,
    ) -> None:
        """Handle trade fill — place paired opposite order."""
        now = self._current_timestamp or datetime.now(UTC)

        if side == "buy":
            # BUY filled -> open grid position, place SELL at upper level
            pid = self._next_position_id
            self._next_position_id += 1
            sell_level = price * (Decimal("1") + self.grid_spacing_pct / Decimal("100"))
            sell_level = sell_level.quantize(Decimal("0.1"))

            # Ensure sell level is profitable (covers 2× round-trip fees = 0.64%)
            min_profitable_sell = price * Decimal("1.0064")
            if sell_level < min_profitable_sell:
                sell_level = min_profitable_sell.quantize(Decimal("0.1"))

            pos = GridPosition(
                entry_price=price,
                entry_time=now,
                amount_btc=amount,
                amount_usdc=amount * price,
                position_id=pid,
                sell_level=sell_level,
            )
            self._grid_positions.append(pos)

            # Place paired SELL
            sell_order = GridOrder(
                price=sell_level,
                side="sell",
                status="pending",
                amount_usdc=pos.amount_usdc,
                position_id=pid,
            )
            key = f"sell_{sell_level}"
            self._grid_orders[key] = sell_order
            self._total_orders_placed += 1

            if not self._skip_db_sync:
                await self._emit_grid_signal(sell_order)

            self.logger.info(
                "grid_buy_filled",
                price=float(price),
                amount_btc=float(amount),
                sell_target=float(sell_level),
                position_id=pid,
            )

        elif side == "sell":
            # SELL filled -> close grid position, place BUY at lower level, record profit
            buy_level = price * (Decimal("1") - self.grid_spacing_pct / Decimal("100"))
            buy_level = buy_level.quantize(Decimal("0.1"))

            # Find and close the matching position
            matched_pos = None
            for i, pos in enumerate(self._grid_positions):
                if abs(pos.sell_level - price) < Decimal("1"):  # Close match
                    matched_pos = self._grid_positions.pop(i)
                    break

            if matched_pos:
                profit = (price - matched_pos.entry_price) * matched_pos.amount_btc - fee
                self._total_grid_profit += profit
                self._completed_pairs += 1

                self.logger.info(
                    "grid_pair_completed",
                    buy_price=float(matched_pos.entry_price),
                    sell_price=float(price),
                    profit=float(profit),
                    total_pairs=self._completed_pairs,
                    total_profit=float(self._total_grid_profit),
                )

            # Place paired BUY at lower level
            buy_order = GridOrder(
                price=buy_level,
                side="buy",
                status="pending",
                amount_usdc=self.order_amount_usdc,
            )
            key = f"buy_{buy_level}"
            self._grid_orders[key] = buy_order
            self._total_orders_placed += 1

            if not self._skip_db_sync:
                await self._emit_grid_signal(buy_order)

            self.logger.info(
                "grid_sell_filled",
                price=float(price),
                buy_target=float(buy_level),
            )

    # ------------------------------------------------------------------
    # Rebalance
    # ------------------------------------------------------------------

    def _should_rebalance(self, current_price: Decimal) -> bool:
        """Check if the grid needs rebalancing."""
        if self._grid_center is None:
            return False
        deviation_pct = abs(current_price - self._grid_center) / self._grid_center * Decimal("100")
        return deviation_pct > self.rebalance_threshold_pct

    async def _rebalance_grid(self, current_price: Decimal) -> None:
        """Rebalance the grid around a new center price.

        Cancels orders far from price, reinitializes around new center.
        Does NOT cancel orders close to price (they might fill soon).
        """
        self._rebalance_count += 1

        self.logger.info(
            "grid_rebalancing",
            old_center=float(self._grid_center) if self._grid_center else None,
            new_center=float(current_price),
            rebalance_count=self._rebalance_count,
        )

        # Cancel all pending orders
        cancelled = 0
        for _key, order in list(self._grid_orders.items()):
            if order.status == "pending":
                order.status = "cancelled"
                cancelled += 1

        # Reinitialize
        orders = self.initialize_grid(current_price)

        if not self._skip_db_sync:
            for order in orders:
                await self._emit_grid_signal(order)

        self.logger.info(
            "grid_rebalanced",
            cancelled_orders=cancelled,
            new_orders=len(orders),
        )

    # ------------------------------------------------------------------
    # Backtest compatibility (used by GridBacktester)
    # ------------------------------------------------------------------

    def add_position(
        self,
        entry_price: Decimal,
        entry_time: datetime,
        amount_btc: Decimal,
        position_id: int,
        sell_level: Decimal,
    ) -> None:
        """Add a grid position (backtest compatibility)."""
        self._grid_positions.append(
            GridPosition(
                entry_price=entry_price,
                entry_time=entry_time,
                amount_btc=amount_btc,
                amount_usdc=amount_btc * entry_price,
                position_id=position_id,
                sell_level=sell_level,
            )
        )
        self._next_position_id = max(self._next_position_id, position_id + 1)

    def close_position(self, position_id: int, sell_price: Decimal, fee: Decimal) -> Decimal:
        """Close a grid position and return profit (backtest compatibility)."""
        for i, pos in enumerate(self._grid_positions):
            if pos.position_id == position_id:
                self._grid_positions.pop(i)
                profit = (sell_price - pos.entry_price) * pos.amount_btc - fee
                self._total_grid_profit += profit
                self._completed_pairs += 1
                return profit
        return Decimal("0")

    @property
    def open_positions(self) -> list[GridPosition]:
        """Return list of open grid positions."""
        return list(self._grid_positions)

    @property
    def open_positions_count(self) -> int:
        """Return number of open grid positions."""
        return len(self._grid_positions)

    @property
    def current_price(self) -> Decimal | None:
        """Return current price."""
        return self._current_price

    @property
    def grid_orders(self) -> dict[str, GridOrder]:
        """Return current grid orders."""
        return dict(self._grid_orders)

    @property
    def pending_orders(self) -> list[GridOrder]:
        """Return only pending grid orders."""
        return [o for o in self._grid_orders.values() if o.status == "pending"]

    @property
    def pending_buy_orders(self) -> list[GridOrder]:
        """Return pending buy orders sorted by price descending."""
        return sorted(
            [o for o in self._grid_orders.values() if o.status == "pending" and o.side == "buy"],
            key=lambda o: o.price,
            reverse=True,
        )

    @property
    def pending_sell_orders(self) -> list[GridOrder]:
        """Return pending sell orders sorted by price ascending."""
        return sorted(
            [o for o in self._grid_orders.values() if o.status == "pending" and o.side == "sell"],
            key=lambda o: o.price,
        )

    @property
    def grid_profit(self) -> Decimal:
        """Return total grid profit from completed pairs."""
        return self._total_grid_profit

    @property
    def completed_pairs(self) -> int:
        """Return number of completed buy/sell pairs."""
        return self._completed_pairs

    @property
    def grid_efficiency(self) -> float:
        """Return grid efficiency: completed pairs / total orders placed."""
        if self._total_orders_placed == 0:
            return 0.0
        return (self._completed_pairs * 2) / self._total_orders_placed
