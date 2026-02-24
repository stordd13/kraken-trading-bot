"""Gemini Suivi Tendance Momentum — trend following on 4h with 1d confirmation.

Macro filter (1d):
- Golden cross: EMA(50) > EMA(200) on 1d
- ADX(14) > 20 on 1d (confirmed trend)
- Regime 1d in [bull, strong_bull]

Entry (4h):
- Pullback to EMA(20) on 4h: previous close <= EMA(20), current close > EMA(20)
- i.e. price dipped to or below EMA(20) then bounced above

Exit:
- Trailing stop: ATR(14, "4h") based, tightens as profit grows
- Regime shift: exit if regime_1d goes to bear or strong_bear
- Stop-loss: 2.5 × ATR(14, "4h") from entry (initial)

This is a swing strategy — positions last days to weeks.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from typing import TYPE_CHECKING, Any

from krakenbot.models.base import SignalType
from krakenbot.strategies.base import BaseStrategy, TradingSignal

if TYPE_CHECKING:
    from krakenbot.config.settings import Settings
    from krakenbot.core.database import DatabaseManager
    from krakenbot.core.event_bus import EventBus
    from krakenbot.indicators.multi_timeframe import MultiTimeframeAnalyzer

_ZERO = Decimal("0")
_HUNDRED = Decimal("100")


@dataclass
class TrendPosition:
    """Tracked trend-following position."""

    position_id: int
    entry_price: Decimal
    entry_time: datetime
    amount_usdc: Decimal
    initial_stop_loss: Decimal
    highest_price: Decimal


class GeminiSuiviTendanceMomentum(BaseStrategy):
    """Trend following strategy on 4h timeframe with 1d macro confirmation.

    Uses EMA golden cross + ADX trending on 1d to confirm macro trend.
    Enters on 4h pullbacks to EMA(20) with a bounce signal.
    Trailing stop based on ATR(14, "4h").
    """

    def __init__(
        self,
        settings: Settings,
        event_bus: EventBus,
        db_manager: DatabaseManager,
        bot_id: str | None = None,
        strategy_params: dict[str, Any] | None = None,
        analyzer: MultiTimeframeAnalyzer | None = None,
    ) -> None:
        super().__init__(
            settings,
            event_bus,
            db_manager,
            bot_id=bot_id,
            strategy_params=strategy_params,
            analyzer=analyzer,
        )

        params = strategy_params or {}
        self.pair: str = params.get("pair", "XBT/USDC")

        # Macro filter thresholds (1d)
        self.adx_min = Decimal(str(params.get("adx_min", 20)))

        # ATR-based stop-loss
        self.initial_sl_atr_mult = Decimal(str(params.get("initial_sl_atr_mult", 2.5)))
        self.trailing_atr_mult = Decimal(str(params.get("trailing_atr_mult", 2.0)))

        # Budget & position sizing (independent per strategy)
        self.order_size_usdc = Decimal(str(params.get("order_size_usdc", 50)))
        self.max_allocation_pct = Decimal(str(params.get("max_allocation_pct", 15.0)))
        self.max_open_positions: int = params.get("max_open_positions", 1)
        # Bridge for ExecutionEngine compat
        default_order = Decimal(str(settings.trading.default_order_amount_eur))
        self._position_size_multiplier = (
            float(self.order_size_usdc / default_order) if default_order > _ZERO else 1.0
        )

        # Internal state
        self._current_price: Decimal | None = None
        self._current_timestamp: datetime | None = None
        self._open_positions: list[TrendPosition] = []
        self._next_position_id: int = 1

        # Pullback detection on 4h: track previous close vs EMA(20)
        self._prev_close_4h: Decimal | None = None
        self._prev_ema20_4h: Decimal | None = None

        self.logger.info(
            "gemini_trend_momentum_initialized",
            bot_id=self.bot_id,
            order_size_usdc=float(self.order_size_usdc),
            max_allocation_pct=float(self.max_allocation_pct),
            adx_min=float(self.adx_min),
            initial_sl_atr_mult=float(self.initial_sl_atr_mult),
            trailing_atr_mult=float(self.trailing_atr_mult),
            max_positions=self.max_open_positions,
        )

    # ------------------------------------------------------------------
    # BaseStrategy interface
    # ------------------------------------------------------------------

    async def on_tick(self, tick_data: dict[str, Any]) -> None:
        if tick_data.get("pair") != self.pair:
            return
        price = Decimal(str(tick_data["price"]))
        self._current_price = price
        for pos in self._open_positions:
            if price > pos.highest_price:
                pos.highest_price = price

    async def on_ohlc(self, ohlc_data: dict[str, Any]) -> None:
        if ohlc_data.get("pair") != self.pair:
            return

        close = Decimal(str(ohlc_data["close"]))
        interval = ohlc_data.get("interval", 5)
        self._current_price = close

        # Update shared analyzer for ALL timeframes
        if self.analyzer is not None:
            self.analyzer.update(ohlc_data, interval)

        # Update highest price from candle highs
        candle_high = Decimal(str(ohlc_data.get("high", close)))
        for pos in self._open_positions:
            if candle_high > pos.highest_price:
                pos.highest_price = candle_high

        self._current_timestamp = self._parse_timestamp(ohlc_data)

        # Track 4h pullback state (only on complete 4h candles)
        if interval == 240 and ohlc_data.get("is_complete", False):
            self._update_pullback_state(close)

    async def generate_signal(self) -> TradingSignal | None:
        if self._current_price is None or self.analyzer is None:
            return None

        now = self._current_timestamp or datetime.now(UTC)

        # --- SELL LOGIC ---
        for pos in self._open_positions:
            sell = self._check_exit(pos, now)
            if sell is not None:
                return sell

        # --- BUY LOGIC ---
        if len(self._open_positions) >= self.max_open_positions:
            return None

        return self._check_entry(now)

    # ------------------------------------------------------------------
    # Exit logic
    # ------------------------------------------------------------------

    def _check_exit(self, pos: TrendPosition, now: datetime) -> TradingSignal | None:
        """Check exit conditions for a trend position."""
        if self._current_price is None or self.analyzer is None:
            return None

        profit_pct = (self._current_price - pos.entry_price) / pos.entry_price * _HUNDRED

        # Exit 1: Initial stop-loss
        if self._current_price <= pos.initial_stop_loss:
            return self._make_sell_signal(
                pos,
                now,
                reason="stop_loss",
                order_type="market",
                confidence=1.0,
                extra=(
                    f"STOP-LOSS: {float(self._current_price):.2f} "
                    f"<= {float(pos.initial_stop_loss):.2f} ({float(profit_pct):.2f}%)"
                ),
            )

        # Exit 2: Trailing stop (ATR-based)
        atr = self.analyzer.get_atr(14, "4h")
        if atr is not None and atr > _ZERO:
            trail_sl = pos.highest_price - self.trailing_atr_mult * atr
            # Trailing stop only applies when it's above initial SL
            effective_sl = max(trail_sl, pos.initial_stop_loss)
            if self._current_price <= effective_sl and trail_sl > pos.initial_stop_loss:
                return self._make_sell_signal(
                    pos,
                    now,
                    reason="trailing_stop",
                    order_type="market",
                    confidence=0.95,
                    extra=(
                        f"TRAILING: {float(self._current_price):.2f} "
                        f"<= {float(trail_sl):.2f} "
                        f"(high {float(pos.highest_price):.2f}, {float(profit_pct):.2f}%)"
                    ),
                )

        # Exit 3: Regime shift to bearish on 1d
        regime_1d = self.analyzer.get_regime("1d")
        if regime_1d in ("bear", "strong_bear"):
            return self._make_sell_signal(
                pos,
                now,
                reason="regime_shift",
                order_type="market",
                confidence=0.9,
                extra=f"REGIME SHIFT: 1d={regime_1d} ({float(profit_pct):.2f}%)",
            )

        return None

    # ------------------------------------------------------------------
    # Entry logic
    # ------------------------------------------------------------------

    def _check_entry(self, now: datetime) -> TradingSignal | None:
        """Check all entry conditions for a trend BUY."""
        if self.analyzer is None or self._current_price is None:
            return None

        # Macro 1: Regime must be bullish
        regime_1d = self.analyzer.get_regime("1d")
        if regime_1d not in ("bull", "strong_bull"):
            return None

        # Macro 2: Golden cross — EMA(50) > EMA(200) on 1d
        ema50_1d = self.analyzer.get_ema(50, "1d")
        ema200_1d = self.analyzer.get_ema(200, "1d")
        if ema50_1d is None or ema200_1d is None:
            return None
        if ema50_1d <= ema200_1d:
            return None

        # Macro 3: ADX > threshold on 1d (confirmed trend)
        adx_1d = self.analyzer.get_adx("1d")
        if adx_1d is None or adx_1d < self.adx_min:
            return None

        # Entry: Pullback bounce on 4h — prev close <= EMA(20), current close > EMA(20)
        ema20_4h = self.analyzer.get_ema(20, "4h")
        if ema20_4h is None:
            return None

        if not self._is_pullback_bounce(ema20_4h):
            return None

        # ATR for stop-loss
        atr = self.analyzer.get_atr(14, "4h")
        if atr is None or atr <= _ZERO:
            return None

        stop_loss = self._current_price - self.initial_sl_atr_mult * atr
        limit_price = self._current_price * Decimal("0.999")

        self.logger.info(
            "trend_buy_signal",
            regime_1d=regime_1d,
            ema50_1d=float(ema50_1d),
            ema200_1d=float(ema200_1d),
            adx_1d=float(adx_1d),
            ema20_4h=float(ema20_4h),
            entry=float(self._current_price),
            sl=float(stop_loss),
            atr=float(atr),
        )

        return TradingSignal(
            signal_type=SignalType.BUY,
            pair=self.pair,
            price=self._current_price,
            confidence=0.85,
            reason=(
                f"TREND BUY: EMA50>200 on 1d, ADX={float(adx_1d):.1f}, "
                f"pullback bounce on 4h EMA(20) (regime={regime_1d})"
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
                "ema50_1d": float(ema50_1d),
                "ema200_1d": float(ema200_1d),
                "adx_1d": float(adx_1d),
                "ema20_4h": float(ema20_4h),
                "atr_4h": float(atr),
                "regime_1d": regime_1d,
            },
        )

    def _update_pullback_state(self, close_4h: Decimal) -> None:
        """Track close vs EMA(20) on 4h for pullback detection."""
        if self.analyzer is None:
            return
        ema20 = self.analyzer.get_ema(20, "4h")
        # Store previous values before updating
        self._prev_close_4h = close_4h
        self._prev_ema20_4h = ema20

    def _is_pullback_bounce(self, current_ema20: Decimal) -> bool:
        """Detect pullback bounce: prev close <= EMA(20), now price > EMA(20)."""
        if self._prev_close_4h is None or self._prev_ema20_4h is None:
            return False
        if self._current_price is None:
            return False

        # Previous candle dipped to or below EMA(20)
        prev_touched = self._prev_close_4h <= self._prev_ema20_4h
        # Current price is above EMA(20)
        now_above = self._current_price > current_ema20

        return prev_touched and now_above

    # ------------------------------------------------------------------
    # Sell signal builder
    # ------------------------------------------------------------------

    def _make_sell_signal(
        self,
        pos: TrendPosition,
        now: datetime,
        *,
        reason: str,
        order_type: str,
        confidence: float,
        extra: str,
    ) -> TradingSignal:
        amount_btc = pos.amount_usdc / pos.entry_price if pos.entry_price > _ZERO else _ZERO
        profit_pct = (
            (self._current_price - pos.entry_price) / pos.entry_price * _HUNDRED
            if self._current_price and pos.entry_price > _ZERO
            else _ZERO
        )
        holding_hours = (now - pos.entry_time).total_seconds() / 3600 if pos.entry_time else 0

        return TradingSignal(
            signal_type=SignalType.SELL,
            pair=self.pair,
            price=self._current_price or _ZERO,
            confidence=confidence,
            reason=f"Position #{pos.position_id}: {extra}",
            strategy=self.bot_id,
            timestamp=now,
            metadata={
                "position_id": pos.position_id,
                "amount_btc": float(amount_btc),
                "entry_price": float(pos.entry_price),
                "profit_pct": float(profit_pct),
                "holding_hours": round(holding_hours, 1),
                "reason": reason,
                "order_type": order_type,
            },
        )

    # ------------------------------------------------------------------
    # Trade filled callback
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
        if side == "buy":
            atr = self.analyzer.get_atr(14, "4h") if self.analyzer else None
            sl_dist = (
                self.initial_sl_atr_mult * atr if atr and atr > _ZERO else price * Decimal("0.03")
            )

            pid = self._next_position_id
            self._next_position_id += 1

            self._open_positions.append(
                TrendPosition(
                    position_id=pid,
                    entry_price=price,
                    entry_time=datetime.now(UTC),
                    amount_usdc=amount * price,
                    initial_stop_loss=price - sl_dist,
                    highest_price=price,
                )
            )
            self.logger.info(
                "trend_position_opened",
                position_id=pid,
                entry=float(price),
                sl=float(price - sl_dist),
                bot_id=self.bot_id,
            )

        elif side == "sell":
            if position_id is None:
                return
            for i, pos in enumerate(self._open_positions):
                if pos.position_id == position_id:
                    closed = self._open_positions.pop(i)
                    pnl = (price - closed.entry_price) * (
                        closed.amount_usdc / closed.entry_price
                    ) - fee
                    self.logger.info(
                        "trend_position_closed",
                        position_id=position_id,
                        pnl=float(pnl),
                        bot_id=self.bot_id,
                    )
                    break

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _parse_timestamp(self, ohlc_data: dict[str, Any]) -> datetime:
        ts = ohlc_data.get("timestamp")
        if ts is None:
            return datetime.now(UTC)
        if isinstance(ts, datetime):
            return ts
        if isinstance(ts, str):
            try:
                return datetime.fromisoformat(ts.replace("Z", "+00:00"))
            except ValueError:
                return datetime.fromtimestamp(float(ts), tz=UTC)
        if isinstance(ts, (int, float)):
            return datetime.fromtimestamp(ts, tz=UTC)
        return datetime.now(UTC)

    def get_name(self) -> str:
        return "gemini_suivi_tendance_momentum"

    def get_config(self) -> dict[str, Any]:
        return {
            "name": self.get_name(),
            "bot_id": self.bot_id,
            "pair": self.pair,
            "order_size_usdc": float(self.order_size_usdc),
            "max_allocation_pct": float(self.max_allocation_pct),
            "adx_min": float(self.adx_min),
            "initial_sl_atr_mult": float(self.initial_sl_atr_mult),
            "trailing_atr_mult": float(self.trailing_atr_mult),
            "max_open_positions": self.max_open_positions,
            "open_positions": len(self._open_positions),
        }
