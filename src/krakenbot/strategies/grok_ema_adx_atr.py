"""Grok EMA 27/125 + ADX + ATR — trend crossover strategy.

Uses EMA(27) / EMA(125) crossover on 4h as the primary entry signal,
confirmed by ADX strength and daily regime. Features a 3-stage stop
management: initial ATR stop → break-even → trailing ATR.

Key rules:
1. BUY when EMA(27) crosses above EMA(125) + ADX >= threshold + regime bull
2. Initial SL = entry - 3.5 × ATR(14, "4h")
3. Break-even: move SL to entry when profit >= 1.5 × ATR
4. Trailing: SL = highest_price - 3.0 × ATR (once break-even activated)
5. EXIT if regime_1d goes bear/strong_bear
6. Single position at a time

Params (from strategies.yaml):
    ema_fast: Fast EMA period (default 27)
    ema_slow: Slow EMA period (default 125)
    adx_threshold: Minimum ADX for entry (default 14)
    atr_mult_stop: Initial SL multiplier (default 3.5)
    breakeven_atr: ATR multiples profit to move SL to break-even (default 1.5)
    trailing_atr: Trailing stop ATR multiplier (default 3.0)
    order_size_usdc: USDC per trade (default 40)
    max_allocation_pct: Max % of total capital (default 15.0)
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from typing import TYPE_CHECKING, Any

from krakenbot.core.event_bus import EventType
from krakenbot.core.logger import get_logger
from krakenbot.models.base import SignalType
from krakenbot.strategies.base import BaseStrategy, TradingSignal

if TYPE_CHECKING:
    from krakenbot.config.settings import Settings
    from krakenbot.core.database import DatabaseManager
    from krakenbot.core.event_bus import EventBus

logger = get_logger(__name__)

_ZERO = Decimal("0")
_ONE = Decimal("1")
_HUNDRED = Decimal("100")


@dataclass
class EMACrossPosition:
    """An open position managed by the EMA cross strategy."""

    position_id: int
    entry_price: Decimal
    entry_time: datetime
    amount_usdc: Decimal
    stop_loss: Decimal
    highest_price: Decimal
    breakeven_activated: bool = False


class GrokEMA27_125_ADX_ATR(BaseStrategy):
    """EMA 27/125 crossover strategy with ADX filter and 3-stage stop.

    Detects golden cross (EMA27 > EMA125) on 4h, confirmed by ADX strength
    and daily bull regime. Uses progressive stop management:
    initial → break-even → trailing.
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
        """Initialize GrokEMA27_125_ADX_ATR."""
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

        # EMA periods
        self.ema_fast_period: int = int(params.get("ema_fast", 27))
        self.ema_slow_period: int = int(params.get("ema_slow", 125))

        # ADX filter
        self.adx_threshold = Decimal(str(params.get("adx_threshold", 14)))

        # Stop management
        self.atr_mult_stop = Decimal(str(params.get("atr_mult_stop", 3.5)))
        self.breakeven_atr = Decimal(str(params.get("breakeven_atr", 1.5)))
        self.trailing_atr = Decimal(str(params.get("trailing_atr", 3.0)))

        # Budget & position sizing (independent per strategy)
        self.order_size_usdc = Decimal(str(params.get("order_size_usdc", 40)))
        self.max_allocation_pct = Decimal(str(params.get("max_allocation_pct", 15.0)))
        # Bridge for ExecutionEngine compat
        default_order = Decimal(str(settings.trading.default_order_amount_eur))
        self._position_size_multiplier = (
            float(self.order_size_usdc / default_order) if default_order > _ZERO else 1.0
        )

        # Internal state
        self._is_4h: bool = False
        self._current_price: Decimal | None = None

        # Pre-register lazy EMAs so warmup data feeds them
        if self.analyzer:
            self.analyzer.get_ema(self.ema_fast_period, "4h")
            self.analyzer.get_ema(self.ema_slow_period, "4h")
        self._current_timestamp: datetime | None = None
        self._position: EMACrossPosition | None = None
        self._next_position_id: int = 1

        # Crossover detection: track previous EMA values
        self._prev_ema_fast: Decimal | None = None
        self._prev_ema_slow: Decimal | None = None

        self.logger.info(
            "grok_ema_adx_atr_initialized",
            bot_id=self.bot_id,
            ema_fast=self.ema_fast_period,
            ema_slow=self.ema_slow_period,
            adx_threshold=float(self.adx_threshold),
            atr_mult_stop=float(self.atr_mult_stop),
            breakeven_atr=float(self.breakeven_atr),
            trailing_atr=float(self.trailing_atr),
            order_size_usdc=float(self.order_size_usdc),
            max_allocation_pct=float(self.max_allocation_pct),
        )

    # ------------------------------------------------------------------
    # BaseStrategy interface
    # ------------------------------------------------------------------

    async def on_tick(self, tick_data: dict[str, Any]) -> None:
        """Handle tick — update price."""
        price = tick_data.get("price")
        if price is not None:
            self._current_price = Decimal(str(price))

    async def on_ohlc(self, ohlc_data: dict[str, Any]) -> None:
        """Handle OHLC — update price and timestamp."""
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
        """Generate signal based on EMA crossover + ADX + regime.

        Only triggers on 4h candles.
        """
        if self._current_price is None or self._current_price <= _ZERO:
            return None
        if self.analyzer is None:
            return None
        if not self._is_4h:
            return None

        now = self._current_timestamp or datetime.now(UTC)
        price = self._current_price

        # Get EMA values (lazy creation via get_ema)
        ema_fast = self.analyzer.get_ema(self.ema_fast_period, "4h")
        ema_slow = self.analyzer.get_ema(self.ema_slow_period, "4h")

        if ema_fast is None or ema_slow is None:
            return None

        # Get ADX and regime
        adx = self.analyzer.get_adx("4h")
        regime_1d = self.analyzer.get_regime("1d")

        # --- Exit logic (check before entry) ---
        if self._position is not None:
            signal = self._check_exit(price, ema_fast, ema_slow, regime_1d, now)
            if signal:
                return signal

            # Update stop management
            self._update_stop_management(price)

            return None

        # --- Entry logic ---
        signal = self._check_entry(price, ema_fast, ema_slow, adx, regime_1d, now)

        # Save current EMA values for next crossover detection
        self._prev_ema_fast = ema_fast
        self._prev_ema_slow = ema_slow

        return signal

    # ------------------------------------------------------------------
    # Stop management (3 stages)
    # ------------------------------------------------------------------

    def _update_stop_management(self, price: Decimal) -> None:
        """Update the 3-stage stop: initial → break-even → trailing."""
        pos = self._position
        if pos is None or self.analyzer is None:
            return

        atr = self.analyzer.get_atr(14, "4h")
        if atr is None or atr <= _ZERO:
            return

        # Track highest price
        if price > pos.highest_price:
            pos.highest_price = price

        profit = price - pos.entry_price

        # Stage 2: Break-even activation
        if not pos.breakeven_activated and profit >= self.breakeven_atr * atr:
            pos.stop_loss = pos.entry_price
            pos.breakeven_activated = True
            self.logger.info(
                "ema_cross_breakeven_activated",
                position_id=pos.position_id,
                entry=float(pos.entry_price),
                price=float(price),
                profit_atr=float(profit / atr),
            )

        # Stage 3: Trailing stop (only after break-even)
        if pos.breakeven_activated:
            trailing_sl = pos.highest_price - self.trailing_atr * atr
            if trailing_sl > pos.stop_loss:
                pos.stop_loss = trailing_sl
                self.logger.debug(
                    "ema_cross_trailing_sl_updated",
                    new_sl=float(trailing_sl),
                    highest=float(pos.highest_price),
                    price=float(price),
                )

    # ------------------------------------------------------------------
    # Exit logic
    # ------------------------------------------------------------------

    def _check_exit(
        self,
        price: Decimal,
        ema_fast: Decimal,
        ema_slow: Decimal,
        regime_1d: str | None,
        now: datetime,
    ) -> TradingSignal | None:
        """Check exit conditions.

        Exit when:
        1. EMA(27) crosses below EMA(125) (death cross) → market
        2. Regime_1d goes bear/strong_bear → market
        3. Price <= stop_loss → market
        """
        pos = self._position
        if pos is None:
            return None

        profit_pct = (price - pos.entry_price) / pos.entry_price * _HUNDRED

        # 1. Death cross: EMA fast crosses below slow
        if ema_fast < ema_slow and self._prev_ema_fast is not None:
            if self._prev_ema_fast >= (self._prev_ema_slow or ema_slow):
                return self._make_exit_signal(
                    pos,
                    price,
                    now,
                    reason="death_cross",
                    extra=(
                        f"EMA{self.ema_fast_period} crossed below EMA{self.ema_slow_period}"
                        f" ({float(profit_pct):+.2f}%)"
                    ),
                )

        # 2. Regime shift to bear
        if regime_1d in ("bear", "strong_bear"):
            return self._make_exit_signal(
                pos,
                price,
                now,
                reason="regime_shift_bear",
                extra=f"Regime → {regime_1d} ({float(profit_pct):+.2f}%)",
            )

        # 3. Stop-loss hit
        if price <= pos.stop_loss:
            stage = "trailing" if pos.breakeven_activated else "initial"
            return self._make_exit_signal(
                pos,
                price,
                now,
                reason=f"stop_loss_{stage}",
                extra=(
                    f"SL hit ({stage}): price={float(price):.1f}"
                    f" <= SL={float(pos.stop_loss):.1f} ({float(profit_pct):+.2f}%)"
                ),
            )

        return None

    def _make_exit_signal(
        self,
        pos: EMACrossPosition,
        price: Decimal,
        now: datetime,
        *,
        reason: str,
        extra: str,
    ) -> TradingSignal:
        """Build a SELL signal for exiting."""
        amount_btc = pos.amount_usdc / pos.entry_price if pos.entry_price > _ZERO else _ZERO

        return TradingSignal(
            signal_type=SignalType.SELL,
            pair=self.pair,
            price=price,
            confidence=0.9,
            reason=f"EMA CROSS EXIT: {extra}",
            strategy=self.bot_id,
            timestamp=now,
            metadata={
                "order_type": "market",
                "position_id": pos.position_id,
                "amount_btc": float(amount_btc),
                "order_size_usdc": float(pos.amount_usdc),
                "position_size_multiplier": self._position_size_multiplier,
                "exit_reason": reason,
                "entry_price": float(pos.entry_price),
                "breakeven_was_active": pos.breakeven_activated,
            },
        )

    # ------------------------------------------------------------------
    # Entry logic
    # ------------------------------------------------------------------

    def _check_entry(
        self,
        price: Decimal,
        ema_fast: Decimal,
        ema_slow: Decimal,
        adx: Decimal | None,
        regime_1d: str | None,
        now: datetime,
    ) -> TradingSignal | None:
        """Check entry conditions.

        BUY when:
        1. EMA(27) crosses above EMA(125) (golden cross)
        2. ADX >= adx_threshold (trend has strength)
        3. regime_1d in [bull, strong_bull]
        4. No position already open
        """
        if self._position is not None:
            return None

        # Need previous values for crossover detection
        if self._prev_ema_fast is None or self._prev_ema_slow is None:
            return None

        # Golden cross: fast was below slow, now above
        is_cross = self._prev_ema_fast <= self._prev_ema_slow and ema_fast > ema_slow
        if not is_cross:
            return None

        # ADX filter: trend must have minimum strength
        if adx is None or adx < self.adx_threshold:
            self.logger.debug(
                "ema_cross_blocked_adx",
                adx=float(adx) if adx else None,
                threshold=float(self.adx_threshold),
            )
            return None

        # Regime filter
        if regime_1d not in ("bull", "strong_bull"):
            return None

        # ATR for initial stop-loss
        atr = self.analyzer.get_atr(14, "4h")
        if atr is None or atr <= _ZERO:
            return None

        stop_loss = price - self.atr_mult_stop * atr
        if stop_loss <= _ZERO:
            stop_loss = price * Decimal("0.90")

        # Limit order
        limit_price = price * Decimal("0.999")

        self.logger.info(
            "ema_cross_entry_signal",
            price=float(price),
            ema_fast=float(ema_fast),
            ema_slow=float(ema_slow),
            adx=float(adx),
            regime_1d=regime_1d,
            stop_loss=float(stop_loss),
            atr=float(atr),
        )

        return TradingSignal(
            signal_type=SignalType.BUY,
            pair=self.pair,
            price=price,
            confidence=0.8,
            reason=(
                f"EMA CROSS BUY: EMA({self.ema_fast_period})={float(ema_fast):.1f}"
                f" > EMA({self.ema_slow_period})={float(ema_slow):.1f},"
                f" ADX={float(adx):.1f} (regime={regime_1d})"
            ),
            strategy=self.bot_id,
            timestamp=now,
            metadata={
                "order_type": "limit",
                "limit_price": float(limit_price),
                "max_allocation_pct": float(self.max_allocation_pct),
                "position_size_multiplier": self._position_size_multiplier,
                "risk_stop_loss": float(stop_loss),
                "ema_fast": float(ema_fast),
                "ema_slow": float(ema_slow),
                "adx_4h": float(adx),
                "atr_4h": float(atr),
                "regime_1d": regime_1d,
            },
        )

    # ------------------------------------------------------------------
    # OHLC filtering (4h only)
    # ------------------------------------------------------------------

    async def _handle_ohlc(self, data: dict[str, Any]) -> None:
        """Override to filter on 4h candles."""
        if not self._running:
            return

        try:
            tf = data.get("timeframe", data.get("interval"))
            self._is_4h = tf in ("4h", 240, "240")

            await self.on_ohlc(data)

            if not self._is_4h:
                return

            signal = await self.generate_signal()
            if signal and signal.should_trade:
                self._last_signal_at = signal.timestamp
                await self.event_bus.publish(
                    EventType.TRADE_SIGNAL,
                    {"signal": signal, "strategy": self.get_name()},
                )

                self.logger.info(
                    "signal_generated",
                    signal_type=signal.signal_type.value,
                    pair=signal.pair,
                    price=float(signal.price),
                    confidence=signal.confidence,
                    reason=signal.reason,
                )
        except Exception as e:
            self.logger.error(
                "ema_cross_ohlc_error",
                error=str(e),
                error_type=type(e).__name__,
                exc_info=e,
            )

    # ------------------------------------------------------------------
    # Trade filled
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
            amount_usdc = amount * price
            pid = self._next_position_id
            self._next_position_id += 1

            # Initial stop-loss
            atr = self.analyzer.get_atr(14, "4h") if self.analyzer else None
            sl = price - self.atr_mult_stop * (atr or price * Decimal("0.03"))
            if sl <= _ZERO:
                sl = price * Decimal("0.90")

            self._position = EMACrossPosition(
                position_id=pid,
                entry_price=price,
                entry_time=now,
                amount_usdc=amount_usdc,
                stop_loss=sl,
                highest_price=price,
            )

            self.logger.info(
                "ema_cross_position_opened",
                position_id=pid,
                entry_price=float(price),
                amount_btc=float(amount),
                amount_usdc=float(amount_usdc),
                stop_loss=float(sl),
            )

        elif side == "sell":
            if self._position is not None:
                profit_pct = (
                    (price - self._position.entry_price) / self._position.entry_price * _HUNDRED
                )
                self.logger.info(
                    "ema_cross_position_closed",
                    position_id=self._position.position_id,
                    entry_price=float(self._position.entry_price),
                    exit_price=float(price),
                    profit_pct=float(profit_pct),
                    breakeven_was_active=self._position.breakeven_activated,
                    fee=float(fee),
                )
                self._position = None

    # ------------------------------------------------------------------
    # Info
    # ------------------------------------------------------------------

    def get_name(self) -> str:
        """Return strategy name."""
        return "grok_ema_adx_atr"

    def get_config(self) -> dict[str, Any]:
        """Return strategy configuration."""
        return {
            "name": self.get_name(),
            "bot_id": self.bot_id,
            "pair": self.pair,
            "ema_fast": self.ema_fast_period,
            "ema_slow": self.ema_slow_period,
            "adx_threshold": float(self.adx_threshold),
            "atr_mult_stop": float(self.atr_mult_stop),
            "breakeven_atr": float(self.breakeven_atr),
            "trailing_atr": float(self.trailing_atr),
            "order_size_usdc": float(self.order_size_usdc),
            "max_allocation_pct": float(self.max_allocation_pct),
            "has_position": self._position is not None,
            "position_entry": (float(self._position.entry_price) if self._position else None),
            "position_sl": (float(self._position.stop_loss) if self._position else None),
            "breakeven_active": (self._position.breakeven_activated if self._position else False),
        }
