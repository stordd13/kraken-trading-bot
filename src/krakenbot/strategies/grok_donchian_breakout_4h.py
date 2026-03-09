"""Grok Donchian Channel Breakout 4h — trend-following breakout strategy.

Uses asymmetric Donchian Channels (upper=20, lower=10) on the 4h timeframe
as the primary signal, filtered by the daily regime and ADX.

Key rules:
1. BUY when close breaks above Donchian upper(20) AND prev_close <= prev_upper
   AND regime_1d in [bull, strong_bull] AND ADX(14, 1d) > 18
2. EXIT when close < Donchian lower(10) → market order (natural trailing stop)
3. EXIT when regime_1d in [bear, strong_bear] → market order
4. Initial SL = 3.5 × ATR(14, 4h) below entry
5. Trailing: Donchian lower(10) acts as a natural trailing stop
6. Single position at a time

Params (from strategies.yaml):
    donchian_upper_period: Upper band period (default 20)
    donchian_lower_period: Lower band period (default 10)
    sl_atr_mult: Initial SL ATR multiplier (default 3.5)
    adx_threshold: Min ADX(14, 1d) for entry (default 18)
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
_HUNDRED = Decimal("100")


@dataclass
class DonchianPosition:
    """An open position managed by the Donchian strategy."""

    position_id: int
    entry_price: Decimal
    entry_time: datetime
    amount_usdc: Decimal
    stop_loss: Decimal
    highest_price: Decimal


class GrokDonchianChannelBreakoutV1(BaseStrategy):
    """Trend-following strategy using 4h Donchian Channel breakout + daily regime.

    Classic Turtle-style breakout: enter on new highs, exit on new lows.
    The asymmetric periods (20 upper, 10 lower) create faster exits than entries.
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
        """Initialize GrokDonchianChannelBreakoutV1."""
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

        # Donchian parameters
        self.donchian_upper_period: int = int(params.get("donchian_upper_period", 20))
        self.donchian_lower_period: int = int(params.get("donchian_lower_period", 10))

        # Risk parameters
        self.sl_atr_mult = Decimal(str(params.get("sl_atr_mult", 3.5)))
        self.adx_threshold = Decimal(str(params.get("adx_threshold", 18)))

        # Budget
        self.order_size_usdc = Decimal(str(params.get("order_size_usdc", 50)))
        self.max_allocation_pct = Decimal(str(params.get("max_allocation_pct", 15.0)))

        # Bridge for ExecutionEngine compat
        default_order = Decimal(str(settings.trading.default_order_amount_eur))
        self._position_size_multiplier = (
            float(self.order_size_usdc / default_order) if default_order > _ZERO else 1.0
        )

        # Internal state
        self._current_price: Decimal | None = None
        self._current_timestamp: datetime | None = None
        self._position: DonchianPosition | None = None
        self._next_position_id: int = 1
        self._is_4h: bool = False

        # Track previous values for crossover detection
        self._prev_close: Decimal | None = None
        self._prev_donchian_upper: Decimal | None = None

        self.logger.info(
            "grok_donchian_breakout_4h_initialized",
            bot_id=self.bot_id,
            donchian_upper=self.donchian_upper_period,
            donchian_lower=self.donchian_lower_period,
            sl_atr_mult=float(self.sl_atr_mult),
            adx_threshold=float(self.adx_threshold),
            order_size_usdc=float(self.order_size_usdc),
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
        """Generate signal based on 4h Donchian breakout + 1d regime."""
        if self._current_price is None or self._current_price <= _ZERO:
            return None
        if self.analyzer is None:
            return None
        if not self._is_4h:
            return None

        now = self._current_timestamp or datetime.now(UTC)
        price = self._current_price

        # Get Donchian on 4h
        dc = self.analyzer.get_donchian(
            "4h", self.donchian_upper_period, self.donchian_lower_period
        )
        if dc is None:
            return None

        dc_upper = dc["upper"]
        dc_lower = dc["lower"]

        # Get daily regime
        regime_1d = self.analyzer.get_regime("1d")

        # --- Exit logic (check before entry) ---
        if self._position is not None:
            signal = self._check_exit(price, dc_lower, regime_1d, now)
            if signal:
                self._prev_close = price
                self._prev_donchian_upper = dc_upper
                return signal

            # Donchian lower acts as natural trailing stop
            if dc_lower > self._position.stop_loss:
                self._position.stop_loss = dc_lower
                self.logger.debug(
                    "donchian_trailing_sl_updated",
                    new_sl=float(dc_lower),
                    price=float(price),
                )

            # Track highest price
            if price > self._position.highest_price:
                self._position.highest_price = price

            self._prev_close = price
            self._prev_donchian_upper = dc_upper
            return None

        # --- Entry logic ---
        adx_1d = self.analyzer.get_adx("1d")
        atr_4h = self.analyzer.get_atr(14, "4h")
        signal = self._check_entry(price, dc_upper, regime_1d, adx_1d, atr_4h, now)

        # Update previous values
        self._prev_close = price
        self._prev_donchian_upper = dc_upper

        return signal

    # ------------------------------------------------------------------
    # Exit logic
    # ------------------------------------------------------------------

    def _check_exit(
        self,
        price: Decimal,
        dc_lower: Decimal,
        regime_1d: str | None,
        now: datetime,
    ) -> TradingSignal | None:
        """Check exit conditions."""
        pos = self._position
        if pos is None:
            return None

        profit_pct = (price - pos.entry_price) / pos.entry_price * _HUNDRED

        # 1. Price below Donchian lower (natural exit)
        if price < dc_lower:
            return self._make_exit_signal(
                pos,
                price,
                now,
                reason="donchian_lower_break",
                extra=(
                    f"Below lower: price={float(price):.1f} < lower={float(dc_lower):.1f}"
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
        pos: DonchianPosition,
        price: Decimal,
        now: datetime,
        *,
        reason: str,
        extra: str,
    ) -> TradingSignal:
        """Build a SELL signal."""
        amount_btc = pos.amount_usdc / pos.entry_price if pos.entry_price > _ZERO else _ZERO

        return TradingSignal(
            signal_type=SignalType.SELL,
            pair=self.pair,
            price=price,
            confidence=0.9,
            reason=f"DONCHIAN EXIT: {extra}",
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
        dc_upper: Decimal,
        regime_1d: str | None,
        adx_1d: Decimal | None,
        atr_4h: Decimal | None,
        now: datetime,
    ) -> TradingSignal | None:
        """Check entry conditions.

        BUY when:
        1. close > Donchian upper(20) AND prev_close <= prev_upper (fresh breakout)
        2. regime_1d in [bull, strong_bull]
        3. ADX(14, 1d) > adx_threshold
        """
        if self._position is not None:
            return None

        # Must break above previous upper band (current dc_upper includes
        # the current candle's high, so close > dc_upper is impossible)
        if self._prev_donchian_upper is None or self._prev_close is None:
            return None
        if price <= self._prev_donchian_upper:
            return None

        # Fresh breakout: previous close was at or below previous upper
        if self._prev_close > self._prev_donchian_upper:
            return None  # Already above — not a fresh breakout

        # Daily regime must be bullish
        if regime_1d not in ("bull", "strong_bull"):
            return None

        # ADX filter
        if adx_1d is None or adx_1d < self.adx_threshold:
            return None

        # ATR for initial stop-loss
        if atr_4h is None or atr_4h <= _ZERO:
            return None

        stop_loss = price - self.sl_atr_mult * atr_4h
        if stop_loss <= _ZERO:
            stop_loss = price * Decimal("0.90")

        # Confidence = (close - upper) / ATR, clamped [0.3, 1.0]
        breakout_strength = (price - dc_upper) / atr_4h
        confidence = max(0.3, min(float(breakout_strength), 1.0))

        limit_price = price * Decimal("0.999")

        self.logger.info(
            "donchian_entry_signal",
            price=float(price),
            dc_upper=float(dc_upper),
            regime_1d=regime_1d,
            adx_1d=float(adx_1d),
            stop_loss=float(stop_loss),
        )

        return TradingSignal(
            signal_type=SignalType.BUY,
            pair=self.pair,
            price=price,
            confidence=confidence,
            reason=(
                f"DONCHIAN BUY: breakout above upper "
                f"price={float(price):.1f} > upper={float(dc_upper):.1f}"
                f" (regime={regime_1d})"
            ),
            strategy=self.bot_id,
            timestamp=now,
            metadata={
                "order_type": "limit",
                "limit_price": float(limit_price),
                "order_size_usdc": float(self.order_size_usdc),
                "max_allocation_pct": float(self.max_allocation_pct),
                "position_size_multiplier": self._position_size_multiplier,
                "risk_stop_loss": float(stop_loss),
                "dc_upper": float(dc_upper),
                "regime_1d": regime_1d,
                "adx_1d": float(adx_1d),
                "atr_4h": float(atr_4h),
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
                "donchian_ohlc_error",
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

            atr = self.analyzer.get_atr(14, "4h") if self.analyzer else None
            sl = price - self.sl_atr_mult * (atr or price * Decimal("0.03"))
            if sl <= _ZERO:
                sl = price * Decimal("0.90")

            self._position = DonchianPosition(
                position_id=pid,
                entry_price=price,
                entry_time=now,
                amount_usdc=amount_usdc,
                stop_loss=sl,
                highest_price=price,
            )

            self.logger.info(
                "donchian_position_opened",
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
                    "donchian_position_closed",
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
        return "grok_donchian_breakout_4h"

    def get_config(self) -> dict[str, Any]:
        """Return strategy configuration."""
        return {
            "name": self.get_name(),
            "bot_id": self.bot_id,
            "pair": self.pair,
            "donchian_upper_period": self.donchian_upper_period,
            "donchian_lower_period": self.donchian_lower_period,
            "sl_atr_mult": float(self.sl_atr_mult),
            "adx_threshold": float(self.adx_threshold),
            "order_size_usdc": float(self.order_size_usdc),
            "max_allocation_pct": float(self.max_allocation_pct),
            "has_position": self._position is not None,
            "position_entry": (float(self._position.entry_price) if self._position else None),
            "position_sl": (float(self._position.stop_loss) if self._position else None),
        }
