"""Trend following strategy based on EMA crossover.

The simplest and most proven strategy. Buys when trend is bullish
(EMA20 crosses above EMA50 on 1h), exits with a wide trailing stop.
Few trades (15-30 over 3 years), large gains per trade.

Uses its own EMA instances (NOT the shared MultiTimeframeAnalyzer).
Cross detection on 1h candles only. Position monitoring on 5min for reactivity.

Params (from strategies.yaml):
    ema_fast_period: Fast EMA period (default 20)
    ema_slow_period: Slow EMA period (default 50)
    trailing_stop_pct: Trailing stop % from highest (default 6.0)
    trailing_activation_pct: Min gain % before trailing activates (default 3.0)
    take_profit_pct: Take profit % (default 25.0)
    max_holding_days: Max holding period in days (default 30)
    hard_stop_below_ema50: Exit if price drops below EMA50 (default true)
    min_cross_strength_pct: Min EMA spread % to validate cross (default 0.1)
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import TYPE_CHECKING, Any

from krakenbot.indicators.ema import EMAIndicator
from krakenbot.models.base import PositionStatus, SignalType
from krakenbot.strategies.base import BaseStrategy, TradingSignal

if TYPE_CHECKING:
    from krakenbot.config.settings import Settings
    from krakenbot.core.database import DatabaseManager
    from krakenbot.core.event_bus import EventBus

from sqlalchemy import select

from krakenbot.models.trades import OpenPosition


@dataclass
class TrendPosition:
    """Position for trend following strategy."""

    entry_price: Decimal
    entry_time: datetime
    amount_btc: Decimal
    position_id: int
    highest_price: Decimal  # For trailing stop
    ema50_at_entry: Decimal  # For hard stop reference
    amount_usdc: Decimal = Decimal("0")  # For backtest compat


class TrendFollowingStrategy(BaseStrategy):
    """Trend following strategy with EMA crossover.

    Entry: EMA20 1h crosses above EMA50 1h (golden cross, one-shot).
    Exit: Hard stop < EMA50, death cross, trailing stop (after +3%), take profit 25%, timeout 30d.
    Max 1 position at a time (high conviction).

    After a SELL, a new BUY requires a death cross FIRST, then a new golden cross.
    This prevents whipsaw re-entries when EMAs are near each other.
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
        """Initialize TrendFollowingStrategy."""
        super().__init__(
            settings,
            event_bus,
            db_manager,
            bot_id=bot_id,
            strategy_params=strategy_params,
            analyzer=analyzer,
        )

        params = strategy_params or {}
        self.pair = self.effective_pair

        # Own EMA instances (NOT from analyzer)
        ema_fast = int(params.get("ema_fast_period", 20))
        ema_slow = int(params.get("ema_slow_period", 50))
        self._ema_fast = EMAIndicator(period=ema_fast)
        self._ema_slow = EMAIndicator(period=ema_slow)

        # Strategy params
        self.trailing_stop_pct = Decimal(str(params.get("trailing_stop_pct", 6.0)))
        self.trailing_activation_pct = Decimal(str(params.get("trailing_activation_pct", 3.0)))
        self.take_profit_pct = Decimal(str(params.get("take_profit_pct", 25.0)))
        self.max_holding_days = int(params.get("max_holding_days", 30))
        self.hard_stop_below_ema50 = bool(params.get("hard_stop_below_ema50", True))
        self.min_cross_strength_pct = Decimal(str(params.get("min_cross_strength_pct", 0.1)))

        # Budget params
        budget = None
        if settings.multi_strategy.enabled:
            for s in settings.multi_strategy.strategies:
                if s.bot_id == bot_id:
                    budget = s.budget
                    break
        self.position_size_multiplier = budget.position_size_multiplier if budget else 2.0

        # Position tracking (max 1)
        self._position: TrendPosition | None = None
        self._next_position_id: int = 1

        # Cross state machine (replaces stale _prev_ema comparisons)
        self._ema_position: str | None = None  # "above" | "below" — persistent EMA state
        self._cross_detected: bool = False  # one-shot flag: True only on new golden cross

        # Price state
        self._current_price: Decimal | None = None
        self._current_timestamp: datetime | None = None

        # Backtest compatibility
        self._skip_db_sync: bool = False

        self.logger.debug(
            "trend_following_initialized",
            bot_id=self.bot_id,
            ema_fast=ema_fast,
            ema_slow=ema_slow,
            trailing_stop_pct=float(self.trailing_stop_pct),
            trailing_activation_pct=float(self.trailing_activation_pct),
            take_profit_pct=float(self.take_profit_pct),
            max_holding_days=self.max_holding_days,
            min_cross_strength_pct=float(self.min_cross_strength_pct),
        )

    # ------------------------------------------------------------------
    # Startup
    # ------------------------------------------------------------------

    async def start(self) -> None:
        """Start strategy with position recovery from DB."""
        await super().start()
        if not self._skip_db_sync:
            await self._load_position_from_db()

    async def _load_position_from_db(self) -> None:
        """Recover open position from database after restart."""
        try:
            async with self.db_manager.read_session() as session:
                result = await session.execute(
                    select(OpenPosition)
                    .where(OpenPosition.bot_id == self.bot_id)
                    .where(OpenPosition.status == PositionStatus.OPEN)
                    .order_by(OpenPosition.position_id.desc())
                    .limit(1)
                )
                pos = result.scalar_one_or_none()

                if pos:
                    self._position = TrendPosition(
                        entry_price=pos.entry_price,
                        entry_time=pos.entry_time,
                        amount_btc=pos.amount_btc,
                        position_id=pos.position_id,
                        highest_price=pos.entry_price,
                        ema50_at_entry=pos.reference_price or pos.entry_price,
                    )
                    self._next_position_id = pos.position_id + 1

                    self.logger.info(
                        "trend_position_recovered",
                        position_id=pos.position_id,
                        entry_price=float(pos.entry_price),
                        bot_id=self.bot_id,
                    )
        except Exception as e:
            self.logger.warning(
                "trend_position_recovery_failed",
                error=str(e),
            )

    # ------------------------------------------------------------------
    # BaseStrategy overrides
    # ------------------------------------------------------------------

    async def on_tick(self, tick_data: dict[str, Any]) -> None:
        """Handle tick data — update current price and trailing."""
        price = tick_data.get("price")
        if price is not None:
            self._current_price = Decimal(str(price))
            # Update highest price for trailing stop
            if self._position and self._current_price > self._position.highest_price:
                self._position.highest_price = self._current_price

    async def on_ohlc(self, ohlc_data: dict[str, Any]) -> None:
        """Handle OHLC data — update price on all candles, EMAs on 1h only."""
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

        # Only update EMAs on 1h candles
        interval = ohlc_data.get("interval", 5)
        if interval != 60:
            return

        if self._current_price is None:
            return

        # Update EMAs
        self._ema_fast.update(self._current_price)
        self._ema_slow.update(self._current_price)

        # Update cross state after EMA update (one-shot flag)
        if self._ema_fast.is_ready and self._ema_slow.is_ready:
            self._update_cross_state()

        # Update highest price for trailing stop
        if self._position and self._current_price > self._position.highest_price:
            self._position.highest_price = self._current_price

    def _update_cross_state(self) -> None:
        """Update persistent cross state after 1h EMA update.

        Called only from on_ohlc when interval == 60 and both EMAs are ready.
        Detects golden cross (below→above) and death cross (above→below).
        Sets _cross_detected = True exactly once per golden cross.
        """
        curr_fast = self._ema_fast.value
        curr_slow = self._ema_slow.value
        if curr_fast is None or curr_slow is None:
            return

        current_position = "above" if curr_fast > curr_slow else "below"

        if self._ema_position is not None:
            # Golden cross: below → above
            if self._ema_position == "below" and current_position == "above":
                # Strength check: EMA diff must be >= min_cross_strength_pct
                diff_pct = (curr_fast - curr_slow) / curr_slow * Decimal("100")
                if diff_pct >= self.min_cross_strength_pct and not self.has_position:
                    self._cross_detected = True
                    self.logger.info(
                        "trend_golden_cross_state",
                        ema_fast=float(curr_fast),
                        ema_slow=float(curr_slow),
                        strength_pct=float(diff_pct),
                    )

            # Death cross: above → below
            elif self._ema_position == "above" and current_position == "below":
                self._cross_detected = False  # Cancel any pending cross
                self.logger.info(
                    "trend_death_cross_state",
                    ema_fast=float(curr_fast),
                    ema_slow=float(curr_slow),
                )

        self._ema_position = current_position

    async def generate_signal(self) -> TradingSignal | None:
        """Generate signal based on EMA crossover and exit conditions."""
        if self._current_price is None or self._current_timestamp is None:
            return None

        # Need both EMAs ready
        if not self._ema_fast.is_ready or not self._ema_slow.is_ready:
            return None

        # Check exits first
        if self._position:
            return self._check_exit()

        # Check entry
        return self._check_entry()

    def get_name(self) -> str:
        """Return strategy name."""
        return "trend_following"

    def get_config(self) -> dict[str, Any]:
        """Return strategy configuration."""
        return {
            "ema_fast_period": self._ema_fast.period,
            "ema_slow_period": self._ema_slow.period,
            "trailing_stop_pct": float(self.trailing_stop_pct),
            "trailing_activation_pct": float(self.trailing_activation_pct),
            "take_profit_pct": float(self.take_profit_pct),
            "max_holding_days": self.max_holding_days,
            "hard_stop_below_ema50": self.hard_stop_below_ema50,
            "min_cross_strength_pct": float(self.min_cross_strength_pct),
            "has_position": self._position is not None,
            "ema_position": self._ema_position,
            "cross_detected": self._cross_detected,
        }

    # ------------------------------------------------------------------
    # Entry logic
    # ------------------------------------------------------------------

    def _check_entry(self) -> TradingSignal | None:
        """Check for golden cross entry signal (one-shot)."""
        # Only enter if _cross_detected was set by _update_cross_state
        if not self._cross_detected:
            return None

        # Consume the flag immediately — prevents repeat entries on subsequent 5min candles
        self._cross_detected = False

        curr_fast = self._ema_fast.value
        curr_slow = self._ema_slow.value
        if curr_fast is None or curr_slow is None:
            return None

        # Price must be above fast EMA (confirmation)
        if self._current_price <= curr_fast:
            return None

        # Calculate limit price slightly below current
        limit_price = self._current_price * Decimal("0.999")

        self.logger.info(
            "trend_golden_cross_detected",
            price=float(self._current_price),
            ema_fast=float(curr_fast),
            ema_slow=float(curr_slow),
        )

        return TradingSignal(
            signal_type=SignalType.BUY,
            pair=self.pair,
            price=self._current_price,
            confidence=0.85,
            reason=f"Golden cross: EMA{self._ema_fast.period} crossed above EMA{self._ema_slow.period}",
            strategy=self.bot_id,
            timestamp=self._current_timestamp,
            metadata={
                "order_type": "limit",
                "limit_price": float(limit_price),
                "position_size_multiplier": self.position_size_multiplier,
                "mode": "spot",
                "reference_price": float(self._current_price),
                "ema_fast": float(curr_fast),
                "ema_slow": float(curr_slow),
            },
        )

    # ------------------------------------------------------------------
    # Exit logic
    # ------------------------------------------------------------------

    def _check_exit(self) -> TradingSignal | None:
        """Check exit conditions for open position.

        Priority order:
        1. Hard stop: price below EMA50
        2. Death cross: EMA fast crossed below EMA slow
        3. Trailing stop: activates after +trailing_activation_pct%, trails at trailing_stop_pct%
        4. Take profit: +take_profit_pct%
        5. Timeout: max_holding_days
        """
        pos = self._position
        if pos is None or self._current_price is None or self._current_timestamp is None:
            return None

        curr_slow = self._ema_slow.value

        # 1. Hard stop: price below EMA50
        if self.hard_stop_below_ema50 and curr_slow is not None:
            if self._current_price < curr_slow:
                return self._make_sell_signal(
                    reason=f"Hard stop: price {self._current_price} below EMA{self._ema_slow.period} {curr_slow}",
                    order_type="market",
                    position=pos,
                )

        # 2. Death cross: EMA fast crossed below EMA slow while in position
        if self._ema_position == "below":
            curr_fast = self._ema_fast.value
            if curr_fast is not None and curr_slow is not None and curr_fast < curr_slow:
                return self._make_sell_signal(
                    reason=f"Death cross: EMA{self._ema_fast.period} below EMA{self._ema_slow.period}",
                    order_type="market",
                    position=pos,
                )

        # 3. Trailing stop: only activates after price has risen trailing_activation_pct from entry
        activation_price = pos.entry_price * (
            Decimal("1") + self.trailing_activation_pct / Decimal("100")
        )
        if pos.highest_price >= activation_price:
            trailing_trigger = pos.highest_price * (
                Decimal("1") - self.trailing_stop_pct / Decimal("100")
            )
            if self._current_price <= trailing_trigger:
                drop_pct = (
                    (pos.highest_price - self._current_price) / pos.highest_price * Decimal("100")
                )
                return self._make_sell_signal(
                    reason=f"Trailing stop: dropped {drop_pct:.1f}% from high {pos.highest_price}",
                    order_type="market",
                    position=pos,
                )

        # 4. Take profit
        profit_pct = (self._current_price - pos.entry_price) / pos.entry_price * Decimal("100")
        if profit_pct >= self.take_profit_pct:
            limit_price = self._current_price * Decimal("1.001")
            return self._make_sell_signal(
                reason=f"Take profit: {profit_pct:.1f}% gain",
                order_type="limit",
                position=pos,
                limit_price=limit_price,
            )

        # 5. Timeout
        holding_time = self._current_timestamp - pos.entry_time
        max_holding = timedelta(days=self.max_holding_days)
        if holding_time >= max_holding:
            return self._make_sell_signal(
                reason=f"Timeout: held {holding_time.days} days (max {self.max_holding_days})",
                order_type="market",
                position=pos,
            )

        return None

    def _make_sell_signal(
        self,
        reason: str,
        order_type: str,
        position: TrendPosition,
        limit_price: Decimal | None = None,
    ) -> TradingSignal:
        """Create a SELL signal for the open position."""
        metadata: dict[str, Any] = {
            "order_type": order_type,
            "position_id": position.position_id,
            "position_size_multiplier": self.position_size_multiplier,
            "amount_btc": float(position.amount_btc),
            "mode": "spot",
            "entry_price": float(position.entry_price),
        }
        if limit_price is not None:
            metadata["limit_price"] = float(limit_price)

        self.logger.info(
            "trend_exit_signal",
            reason=reason,
            price=float(self._current_price) if self._current_price else 0,
            entry_price=float(position.entry_price),
            position_id=position.position_id,
        )

        return TradingSignal(
            signal_type=SignalType.SELL,
            pair=self.pair,
            price=self._current_price,
            confidence=0.9,
            reason=reason,
            strategy=self.bot_id,
            timestamp=self._current_timestamp,
            metadata=metadata,
        )

    # ------------------------------------------------------------------
    # Trade filled handling
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
        """Handle trade fill — track position."""
        now = self._current_timestamp or datetime.now(UTC)

        if side == "buy":
            pid = self._next_position_id
            self._next_position_id += 1

            ema50_val = self._ema_slow.value or price

            self._position = TrendPosition(
                entry_price=price,
                entry_time=now,
                amount_btc=amount,
                position_id=pid,
                highest_price=price,
                ema50_at_entry=ema50_val,
                amount_usdc=amount * price,
            )

            self.logger.info(
                "trend_position_opened",
                position_id=pid,
                entry_price=float(price),
                amount_btc=float(amount),
                ema50=float(ema50_val),
            )

        elif side == "sell":
            if self._position:
                pnl = (price - self._position.entry_price) * self._position.amount_btc - fee
                self.logger.info(
                    "trend_position_closed",
                    position_id=self._position.position_id,
                    entry_price=float(self._position.entry_price),
                    exit_price=float(price),
                    pnl=float(pnl),
                    holding_days=(now - self._position.entry_time).days,
                )
                self._position = None
                # After selling, require death cross before next golden cross
                self._cross_detected = False

    # ------------------------------------------------------------------
    # Backtest compatibility
    # ------------------------------------------------------------------

    def add_position(
        self,
        entry_price: Decimal,
        entry_time: datetime | None = None,
        amount_btc: Decimal | None = None,
        amount_usdc: Decimal | None = None,
        position_id: int | None = None,
        **_kwargs: Any,
    ) -> int:
        """Add a position (backtest compatibility).

        Accepts both amount_btc (direct) and amount_usdc (backtest engine pattern).
        Returns the position ID for backtest tracking.
        """
        if entry_time is None:
            entry_time = self._current_timestamp or datetime.now(UTC)

        if amount_btc is None and amount_usdc is not None:
            amount_btc = amount_usdc / entry_price if entry_price > 0 else Decimal("0")
        elif amount_btc is None:
            amount_btc = Decimal("0")

        pid = position_id if position_id is not None else self._next_position_id
        ema50_val = self._ema_slow.value or entry_price
        self._position = TrendPosition(
            entry_price=entry_price,
            entry_time=entry_time,
            amount_btc=amount_btc,
            position_id=pid,
            highest_price=entry_price,
            ema50_at_entry=ema50_val,
            amount_usdc=amount_usdc or (amount_btc * entry_price),
        )
        self._next_position_id = max(self._next_position_id, pid + 1)
        return pid

    def close_position(self, position_id: int) -> TrendPosition | None:
        """Close position (backtest compatibility).

        Returns the closed position for P&L calculation.
        """
        if self._position and self._position.position_id == position_id:
            closed = self._position
            self._position = None
            # After selling, require death cross before next golden cross
            self._cross_detected = False
            return closed
        return None

    @property
    def has_position(self) -> bool:
        """Check if there is an open position."""
        return self._position is not None

    @property
    def open_positions(self) -> list[TrendPosition]:
        """Return list of open positions (0 or 1)."""
        return [self._position] if self._position else []

    @property
    def open_positions_count(self) -> int:
        """Return number of open positions."""
        return 1 if self._position else 0

    @property
    def current_price(self) -> Decimal | None:
        """Return current price."""
        return self._current_price
