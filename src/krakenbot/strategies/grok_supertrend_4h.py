"""Grok SuperTrend 4h Regime — trend-following strategy on 4h SuperTrend.

Uses the SuperTrend indicator on the 4h timeframe as the primary signal,
filtered by the daily regime. Only takes long positions when the 4h trend
is UP and the 1d regime confirms bullish conditions.

Key rules:
1. BUY when close > SuperTrend AND regime_1d in [bull, strong_bull]
2. EXIT when close < SuperTrend OR regime_1d in [bear, strong_bear]
3. Initial SL = 3.5 × ATR(14, "4h") below entry
4. Trailing SL follows the SuperTrend line (natural trailing stop)
5. Single position at a time (no pyramiding)

Params (from strategies.yaml):
    st_atr_period: SuperTrend ATR period (default 10)
    st_multiplier: SuperTrend multiplier (default 3.0)
    sl_atr_mult: Initial SL ATR multiplier (default 3.5)
    order_size_usdc: USDC per trade (default 50)
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
class SuperTrendPosition:
    """An open position managed by the SuperTrend strategy."""

    position_id: int
    entry_price: Decimal
    entry_time: datetime
    amount_usdc: Decimal
    stop_loss: Decimal
    highest_price: Decimal


class GrokSuperTrend4hRegime(BaseStrategy):
    """Trend-following strategy using 4h SuperTrend + daily regime filter.

    Simple and mechanical: long when SuperTrend says UP in a bull regime,
    exit when either flips. The SuperTrend line itself acts as a natural
    trailing stop.
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
        """Initialize GrokSuperTrend4hRegime."""
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

        # SuperTrend parameters
        self.st_atr_period: int = int(params.get("st_atr_period", 10))
        self.st_multiplier = Decimal(str(params.get("st_multiplier", 3.0)))

        # Initial stop-loss
        self.sl_atr_mult = Decimal(str(params.get("sl_atr_mult", 3.5)))

        # Budget & position sizing (independent per strategy)
        self.order_size_usdc = Decimal(str(params.get("order_size_usdc", 50)))
        self.max_allocation_pct = Decimal(str(params.get("max_allocation_pct", 15.0)))
        # Bridge for ExecutionEngine compat
        default_order = Decimal(str(settings.trading.default_order_amount_eur))
        self._position_size_multiplier = (
            float(self.order_size_usdc / default_order) if default_order > _ZERO else 1.0
        )

        # Internal state
        self._is_4h: bool = False
        self._current_price: Decimal | None = None
        self._current_timestamp: datetime | None = None
        self._position: SuperTrendPosition | None = None
        self._next_position_id: int = 1

        # Track previous SuperTrend direction for crossover detection
        self._prev_st_direction: int | None = None  # 1 = UP, -1 = DOWN

        self.logger.info(
            "grok_supertrend_4h_initialized",
            bot_id=self.bot_id,
            st_atr_period=self.st_atr_period,
            st_multiplier=float(self.st_multiplier),
            sl_atr_mult=float(self.sl_atr_mult),
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
        """Generate signal based on 4h SuperTrend + 1d regime.

        Only triggers on 4h candles (checked in on_ohlc via _is_4h flag).
        """
        if self._current_price is None or self._current_price <= _ZERO:
            return None
        if self.analyzer is None:
            return None
        if not self._is_4h:
            return None

        now = self._current_timestamp or datetime.now(UTC)
        price = self._current_price

        # Get SuperTrend on 4h
        st = self.analyzer.get_supertrend("4h", self.st_atr_period, float(self.st_multiplier))
        if st is None:
            return None

        st_value = st["supertrend"]  # Decimal
        st_direction = st["direction"]  # 1 = UP, -1 = DOWN

        # Get daily regime
        regime_1d = self.analyzer.get_regime("1d")

        # --- Exit logic (check before entry) ---
        if self._position is not None:
            signal = self._check_exit(price, st_value, st_direction, regime_1d, now)
            if signal:
                return signal

            # Update trailing stop to SuperTrend line (if higher than current SL)
            if st_direction == 1 and st_value > self._position.stop_loss:
                self._position.stop_loss = st_value
                self.logger.debug(
                    "supertrend_trailing_sl_updated",
                    new_sl=float(st_value),
                    price=float(price),
                )

            # Track highest price
            if price > self._position.highest_price:
                self._position.highest_price = price

            return None

        # --- Entry logic ---
        signal = self._check_entry(price, st_value, st_direction, regime_1d, now)

        # Update previous direction for next candle
        self._prev_st_direction = st_direction

        return signal

    # ------------------------------------------------------------------
    # Exit logic
    # ------------------------------------------------------------------

    def _check_exit(
        self,
        price: Decimal,
        st_value: Decimal,
        st_direction: int,
        regime_1d: str | None,
        now: datetime,
    ) -> TradingSignal | None:
        """Check exit conditions for open position.

        Exit when:
        1. Price < SuperTrend (trend flip) → market order
        2. Regime_1d goes bear/strong_bear → market order
        3. Price < stop_loss → market order
        """
        pos = self._position
        if pos is None:
            return None

        profit_pct = (price - pos.entry_price) / pos.entry_price * _HUNDRED

        # 1. SuperTrend flip (close < SuperTrend line)
        if st_direction == -1 or price < st_value:
            return self._make_exit_signal(
                pos,
                price,
                now,
                reason="supertrend_flip",
                extra=(
                    f"ST flip DOWN: price={float(price):.1f} < ST={float(st_value):.1f}"
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
                extra=(f"Regime → {regime_1d}: exiting ({float(profit_pct):+.2f}%)"),
            )

        # 3. Stop-loss hit
        if price <= pos.stop_loss:
            return self._make_exit_signal(
                pos,
                price,
                now,
                reason="stop_loss",
                extra=(
                    f"SL hit: price={float(price):.1f} <= SL={float(pos.stop_loss):.1f}"
                    f" ({float(profit_pct):+.2f}%)"
                ),
            )

        return None

    def _make_exit_signal(
        self,
        pos: SuperTrendPosition,
        price: Decimal,
        now: datetime,
        *,
        reason: str,
        extra: str,
    ) -> TradingSignal:
        """Build a SELL signal for exiting an open position."""
        amount_btc = pos.amount_usdc / pos.entry_price if pos.entry_price > _ZERO else _ZERO

        return TradingSignal(
            signal_type=SignalType.SELL,
            pair=self.pair,
            price=price,
            confidence=0.9,
            reason=f"SUPERTREND EXIT: {extra}",
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
            },
        )

    # ------------------------------------------------------------------
    # Entry logic
    # ------------------------------------------------------------------

    def _check_entry(
        self,
        price: Decimal,
        st_value: Decimal,
        st_direction: int,
        regime_1d: str | None,
        now: datetime,
    ) -> TradingSignal | None:
        """Check entry conditions.

        BUY when:
        1. close > SuperTrend (direction == 1, UP)
        2. regime_1d in [bull, strong_bull]
        3. No position already open
        4. Optional: direction just flipped from -1 to 1 (fresh crossover)
        """
        if self._position is not None:
            return None

        # Must be in uptrend on SuperTrend
        if st_direction != 1 or price <= st_value:
            self.logger.info(
                "supertrend_entry_filtered",
                bot_id=self.bot_id,
                close=str(price),
                signal="FILTERED",
                reason="st_direction_down" if st_direction != 1 else "price_below_st",
                st_value=float(st_value),
                st_direction=st_direction,
                regime_1d=regime_1d,
            )
            return None

        # Daily regime must be bullish
        if regime_1d not in ("bull", "strong_bull"):
            self.logger.info(
                "supertrend_entry_filtered",
                bot_id=self.bot_id,
                close=str(price),
                signal="FILTERED",
                reason="regime_not_bullish",
                st_value=float(st_value),
                st_direction=st_direction,
                regime_1d=regime_1d,
            )
            return None

        # Prefer fresh crossovers (direction just flipped)
        # But also allow entry if we just started and direction is already UP
        is_fresh_cross = self._prev_st_direction is not None and self._prev_st_direction == -1
        confidence = 0.85 if is_fresh_cross else 0.7

        # ATR for initial stop-loss
        atr = self.analyzer.get_atr(14, "4h")
        if atr is None or atr <= _ZERO:
            return None

        stop_loss = price - self.sl_atr_mult * atr
        if stop_loss <= _ZERO:
            stop_loss = price * Decimal("0.90")  # Fallback: 10% below

        # Limit order slightly below current price (maker fee)
        limit_price = price * Decimal("0.999")

        self.logger.info(
            "supertrend_entry_signal",
            price=float(price),
            st_value=float(st_value),
            regime_1d=regime_1d,
            fresh_cross=is_fresh_cross,
            stop_loss=float(stop_loss),
            atr=float(atr),
        )

        return TradingSignal(
            signal_type=SignalType.BUY,
            pair=self.pair,
            price=price,
            confidence=confidence,
            reason=(
                f"SUPERTREND BUY: price={float(price):.1f} > ST={float(st_value):.1f}"
                f" (regime={regime_1d}, cross={'fresh' if is_fresh_cross else 'ongoing'})"
            ),
            strategy=self.bot_id,
            timestamp=now,
            metadata={
                "order_type": "limit",
                "limit_price": float(limit_price),
                "max_allocation_pct": float(self.max_allocation_pct),
                "position_size_multiplier": self._position_size_multiplier,
                "risk_stop_loss": float(stop_loss),
                "st_value": float(st_value),
                "st_direction": st_direction,
                "regime_1d": regime_1d,
                "atr_4h": float(atr),
                "fresh_crossover": is_fresh_cross,
            },
        )

    # ------------------------------------------------------------------
    # OHLC filtering
    # ------------------------------------------------------------------

    async def _handle_ohlc(self, data: dict[str, Any]) -> None:
        """Override to set _is_4h flag before generate_signal."""
        if not self._running:
            return

        try:
            tf = data.get("timeframe", data.get("interval"))
            self._is_4h = tf in ("4h", 240, "240")

            await self.on_ohlc(data)

            # Only generate signals on 4h candles
            if not self._is_4h:
                return

            signal = await self.generate_signal()

            # Summary strategy_tick on every 4h candle
            tick_signal = "HOLD"
            tick_reason = "no_signal"
            if signal and signal.should_trade:
                tick_signal = signal.signal_type.value
                tick_reason = signal.reason
            elif self._position is not None:
                tick_signal = "HOLD"
                tick_reason = "in_position"
            self.logger.info(
                "strategy_tick",
                strategy=self.get_name(),
                bot_id=self.bot_id,
                pair=data.get("pair", self.pair),
                timeframe="4h",
                close=str(self._current_price),
                signal=tick_signal,
                reason=tick_reason,
                metadata={
                    "has_position": self._position is not None,
                    "position_entry": (
                        float(self._position.entry_price) if self._position else None
                    ),
                },
            )

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
                "supertrend_ohlc_error",
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
            sl = price - self.sl_atr_mult * (atr or price * Decimal("0.03"))
            if sl <= _ZERO:
                sl = price * Decimal("0.90")

            self._position = SuperTrendPosition(
                position_id=pid,
                entry_price=price,
                entry_time=now,
                amount_usdc=amount_usdc,
                stop_loss=sl,
                highest_price=price,
            )

            self.logger.info(
                "supertrend_position_opened",
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
                    "supertrend_position_closed",
                    position_id=self._position.position_id,
                    entry_price=float(self._position.entry_price),
                    exit_price=float(price),
                    profit_pct=float(profit_pct),
                    fee=float(fee),
                )
                self._position = None

    # ------------------------------------------------------------------
    # Info
    # ------------------------------------------------------------------

    def get_name(self) -> str:
        """Return strategy name."""
        return "grok_supertrend_4h"

    def get_config(self) -> dict[str, Any]:
        """Return strategy configuration."""
        return {
            "name": self.get_name(),
            "bot_id": self.bot_id,
            "pair": self.pair,
            "st_atr_period": self.st_atr_period,
            "st_multiplier": float(self.st_multiplier),
            "sl_atr_mult": float(self.sl_atr_mult),
            "order_size_usdc": float(self.order_size_usdc),
            "max_allocation_pct": float(self.max_allocation_pct),
            "has_position": self._position is not None,
            "position_entry": (float(self._position.entry_price) if self._position else None),
            "position_sl": (float(self._position.stop_loss) if self._position else None),
        }
