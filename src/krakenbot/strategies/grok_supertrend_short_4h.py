"""Grok SuperTrend Short 4h — inverse of SuperTrend long strategy.

Opens SHORT positions when the 4h SuperTrend flips DOWN in bear regimes.
Uses margin trading with leverage 2x.

Key rules:
1. SHORT when close < SuperTrend(10, 3.0) AND direction = DOWN
   AND regime_1d in [bear, strong_bear]
2. COVER when close > SuperTrend (flip UP) OR regime_1d in [bull, strong_bull]
3. Initial SL = entry + 3.5 × ATR(14, "4h") above entry
4. Trailing SL follows the SuperTrend line downward
5. Single position at a time (no pyramiding)

Signal flow:
    Open short: SignalType.SELL with metadata mode="margin", is_short_open=True
    Close short: SignalType.BUY with metadata mode="margin", is_short_close=True

P&L: (entry_price - exit_price) / entry_price * 100 (inverted from long)

Params (from strategies.yaml):
    st_atr_period: SuperTrend ATR period (default 10)
    st_multiplier: SuperTrend multiplier (default 3.0)
    sl_atr_mult: Initial SL ATR multiplier (default 3.5)
    order_size_usdc: USDC per trade (default 50)
    max_allocation_pct: Max % of total capital (default 10.0)
    leverage: Margin leverage (default 2)
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from typing import TYPE_CHECKING, Any

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
class ShortPosition:
    """An open short position managed by the SuperTrend Short strategy."""

    position_id: int
    entry_price: Decimal
    entry_time: datetime
    amount_usdc: Decimal
    stop_loss: Decimal  # Above entry for shorts
    lowest_price: Decimal  # Track lowest for trailing


class GrokSuperTrendShort4hRegime(BaseStrategy):
    """Short-selling strategy using 4h SuperTrend + daily regime filter.

    Inverse of GrokSuperTrend4hRegime: short when SuperTrend says DOWN
    in a bear regime, cover when either flips. Uses margin with leverage 2x.
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
        """Initialize GrokSuperTrendShort4hRegime."""
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

        # SuperTrend parameters
        self.st_atr_period: int = int(params.get("st_atr_period", 10))
        self.st_multiplier = Decimal(str(params.get("st_multiplier", 3.0)))

        # Initial stop-loss (above entry for shorts)
        self.sl_atr_mult = Decimal(str(params.get("sl_atr_mult", 3.5)))

        # Budget & position sizing
        self.order_size_usdc = Decimal(str(params.get("order_size_usdc", 50)))
        self.max_allocation_pct = Decimal(str(params.get("max_allocation_pct", 10.0)))
        self.leverage: int = int(params.get("leverage", 2))

        # Bridge for ExecutionEngine compat
        default_order = Decimal(str(settings.trading.default_order_amount_eur))
        self._position_size_multiplier = (
            float(self.order_size_usdc / default_order) if default_order > _ZERO else 1.0
        )

        # Internal state
        self._is_4h: bool = False
        self._current_price: Decimal | None = None
        self._current_timestamp: datetime | None = None
        self._position: ShortPosition | None = None
        self._next_position_id: int = 1

        # Track previous SuperTrend direction for crossover detection
        self._prev_st_direction: int | None = None  # 1 = UP, -1 = DOWN

        self.logger.info(
            "grok_supertrend_short_4h_initialized",
            bot_id=self.bot_id,
            st_atr_period=self.st_atr_period,
            st_multiplier=float(self.st_multiplier),
            sl_atr_mult=float(self.sl_atr_mult),
            order_size_usdc=float(self.order_size_usdc),
            max_allocation_pct=float(self.max_allocation_pct),
            leverage=self.leverage,
        )

    # ------------------------------------------------------------------
    # BaseStrategy interface
    # ------------------------------------------------------------------

    async def on_tick(self, tick_data: dict[str, Any]) -> None:
        """Handle tick — update price and track lowest for trailing."""
        price = tick_data.get("price")
        if price is not None:
            self._current_price = Decimal(str(price))
            # Update lowest price for open short position
            if self._position is not None and self._current_price < self._position.lowest_price:
                self._position.lowest_price = self._current_price

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
        # Update lowest from candle low
        low = ohlc_data.get("low")
        if low is not None and self._position is not None:
            low_dec = Decimal(str(low))
            if low_dec < self._position.lowest_price:
                self._position.lowest_price = low_dec

    async def generate_signal(self) -> TradingSignal | None:
        """Generate signal based on 4h SuperTrend + 1d regime (inverted for shorts)."""
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

            # Update trailing stop: SuperTrend line moving DOWN = tighter stop for short
            # For shorts, lower ST = better trailing stop (price needs to go up less to hit it)
            if st_direction == -1 and st_value < self._position.stop_loss:
                self._position.stop_loss = st_value
                self.logger.debug(
                    "short_trailing_sl_updated",
                    new_sl=float(st_value),
                    price=float(price),
                )

            return None

        # --- Entry logic ---
        signal = self._check_entry(price, st_value, st_direction, regime_1d, now)

        # Update previous direction for next candle
        self._prev_st_direction = st_direction

        return signal

    # ------------------------------------------------------------------
    # Exit logic (cover short)
    # ------------------------------------------------------------------

    def _check_exit(
        self,
        price: Decimal,
        st_value: Decimal,
        st_direction: int,
        regime_1d: str | None,
        now: datetime,
    ) -> TradingSignal | None:
        """Check exit conditions for open short position.

        Cover when:
        1. SuperTrend flips UP (close > SuperTrend) → market buy to cover
        2. Regime_1d goes bull/strong_bull → market buy to cover
        3. Price > stop_loss → market buy to cover (stop-loss for shorts = price UP)
        """
        pos = self._position
        if pos is None:
            return None

        # Short P&L: profit when price drops
        profit_pct = (pos.entry_price - price) / pos.entry_price * _HUNDRED

        # 1. SuperTrend flip UP (close > SuperTrend)
        if st_direction == 1 or price > st_value:
            return self._make_cover_signal(
                pos,
                price,
                now,
                reason="supertrend_flip_up",
                extra=(
                    f"ST flip UP: price={float(price):.1f} > ST={float(st_value):.1f}"
                    f" ({float(profit_pct):+.2f}%)"
                ),
            )

        # 2. Regime shift to bull
        if regime_1d in ("bull", "strong_bull"):
            return self._make_cover_signal(
                pos,
                price,
                now,
                reason="regime_shift_bull",
                extra=f"Regime → {regime_1d}: covering ({float(profit_pct):+.2f}%)",
            )

        # 3. Stop-loss hit (price moved UP above stop)
        if price >= pos.stop_loss:
            return self._make_cover_signal(
                pos,
                price,
                now,
                reason="stop_loss",
                extra=(
                    f"SL hit: price={float(price):.1f} >= SL={float(pos.stop_loss):.1f}"
                    f" ({float(profit_pct):+.2f}%)"
                ),
            )

        return None

    def _make_cover_signal(
        self,
        pos: ShortPosition,
        price: Decimal,
        now: datetime,
        *,
        reason: str,
        extra: str,
    ) -> TradingSignal:
        """Build a BUY signal for covering an open short position."""
        amount_crypto = pos.amount_usdc / pos.entry_price if pos.entry_price > _ZERO else _ZERO

        return TradingSignal(
            signal_type=SignalType.BUY,
            pair=self.pair,
            price=price,
            confidence=0.9,
            reason=f"SHORT COVER: {extra}",
            strategy=self.bot_id,
            timestamp=now,
            metadata={
                "mode": "margin",
                "is_short_close": True,
                "order_type": "market",
                "position_id": pos.position_id,
                "amount_crypto": float(amount_crypto),
                "order_size_usdc": float(pos.amount_usdc),
                "position_size_multiplier": self._position_size_multiplier,
                "exit_reason": reason,
                "entry_price": float(pos.entry_price),
                "leverage": self.leverage,
            },
        )

    # ------------------------------------------------------------------
    # Entry logic (open short)
    # ------------------------------------------------------------------

    def _check_entry(
        self,
        price: Decimal,
        st_value: Decimal,
        st_direction: int,
        regime_1d: str | None,
        now: datetime,
    ) -> TradingSignal | None:
        """Check short entry conditions.

        SHORT when:
        1. close < SuperTrend (direction == -1, DOWN)
        2. regime_1d in [bear, strong_bear]
        3. No position already open
        4. Optional: direction just flipped from 1 to -1 (fresh crossover)
        """
        if self._position is not None:
            return None

        # Must be in downtrend on SuperTrend
        if st_direction != -1 or price >= st_value:
            return None

        # Daily regime must be bearish
        if regime_1d not in ("bear", "strong_bear"):
            return None

        # Prefer fresh crossovers (direction just flipped DOWN)
        is_fresh_cross = self._prev_st_direction is not None and self._prev_st_direction == 1
        confidence = 0.85 if is_fresh_cross else 0.7

        # ATR for initial stop-loss (ABOVE entry for shorts)
        atr = self.analyzer.get_atr(14, "4h")
        if atr is None or atr <= _ZERO:
            return None

        stop_loss = price + self.sl_atr_mult * atr

        self.logger.info(
            "short_entry_signal",
            price=float(price),
            st_value=float(st_value),
            regime_1d=regime_1d,
            fresh_cross=is_fresh_cross,
            stop_loss=float(stop_loss),
            atr=float(atr),
        )

        return TradingSignal(
            signal_type=SignalType.SELL,
            pair=self.pair,
            price=price,
            confidence=confidence,
            reason=(
                f"SHORT ENTRY: price={float(price):.1f} < ST={float(st_value):.1f}"
                f" (regime={regime_1d}, cross={'fresh' if is_fresh_cross else 'ongoing'})"
            ),
            strategy=self.bot_id,
            timestamp=now,
            metadata={
                "mode": "margin",
                "is_short_open": True,
                "order_type": "market",
                "order_size_usdc": float(self.order_size_usdc),
                "max_allocation_pct": float(self.max_allocation_pct),
                "position_size_multiplier": self._position_size_multiplier,
                "risk_stop_loss": float(stop_loss),
                "st_value": float(st_value),
                "st_direction": st_direction,
                "regime_1d": regime_1d,
                "atr_4h": float(atr),
                "fresh_crossover": is_fresh_cross,
                "leverage": self.leverage,
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
            if signal and signal.should_trade:
                self._last_signal_at = signal.timestamp
                from krakenbot.core.event_bus import EventType

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
                "supertrend_short_ohlc_error",
                error=str(e),
                error_type=type(e).__name__,
                exc_info=e,
            )

    # ------------------------------------------------------------------
    # Trade filled (for live/router mode)
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
        """Handle trade fill — track short position."""
        now = self._current_timestamp or datetime.now(UTC)

        if side == "sell":
            # Opening a short
            amount_usdc = amount * price
            pid = self._next_position_id
            self._next_position_id += 1

            atr = self.analyzer.get_atr(14, "4h") if self.analyzer else None
            sl = price + self.sl_atr_mult * (atr or price * Decimal("0.03"))

            self._position = ShortPosition(
                position_id=pid,
                entry_price=price,
                entry_time=now,
                amount_usdc=amount_usdc,
                stop_loss=sl,
                lowest_price=price,
            )

            self.logger.info(
                "short_position_opened",
                position_id=pid,
                entry_price=float(price),
                amount_usdc=float(amount_usdc),
                stop_loss=float(sl),
            )

        elif side == "buy":
            # Closing a short (covering)
            if self._position is not None:
                profit_pct = (
                    (self._position.entry_price - price) / self._position.entry_price * _HUNDRED
                )
                self.logger.info(
                    "short_position_closed",
                    position_id=self._position.position_id,
                    entry_price=float(self._position.entry_price),
                    exit_price=float(price),
                    profit_pct=float(profit_pct),
                    fee=float(fee),
                )
                self._position = None

    # ------------------------------------------------------------------
    # Backtest compatibility (add_position / close_position)
    # ------------------------------------------------------------------

    def add_position(
        self,
        entry_price: Decimal,
        amount_usdc: Decimal,
        reference_price: Decimal | None = None,
        entry_time: datetime | None = None,
    ) -> int:
        """Add a short position (for backtest engine compatibility)."""
        pid = self._next_position_id
        self._next_position_id += 1

        atr = self.analyzer.get_atr(14, "4h") if self.analyzer else None
        sl = entry_price + self.sl_atr_mult * (atr or entry_price * Decimal("0.03"))

        self._position = ShortPosition(
            position_id=pid,
            entry_price=entry_price,
            entry_time=entry_time or datetime.now(UTC),
            amount_usdc=amount_usdc,
            stop_loss=sl,
            lowest_price=entry_price,
        )
        return pid

    def close_position(self, position_id: int) -> ShortPosition | None:
        """Close a short position by ID (for backtest engine compatibility)."""
        if self._position is not None and self._position.position_id == position_id:
            closed = self._position
            self._position = None
            return closed
        return None

    @property
    def open_positions(self) -> list[ShortPosition]:
        """Get list of open short positions."""
        if self._position is not None:
            return [self._position]
        return []

    @property
    def open_positions_count(self) -> int:
        """Get number of open short positions."""
        return 1 if self._position is not None else 0

    # ------------------------------------------------------------------
    # Info
    # ------------------------------------------------------------------

    def get_name(self) -> str:
        """Return strategy name."""
        return "grok_supertrend_short_4h"

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
            "leverage": self.leverage,
            "has_position": self._position is not None,
            "position_entry": (float(self._position.entry_price) if self._position else None),
            "position_sl": (float(self._position.stop_loss) if self._position else None),
        }
