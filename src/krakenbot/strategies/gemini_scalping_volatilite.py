"""Gemini Scalping Volatilite — fast scalping on 5m with 1h confirmation.

Entry conditions (all must be true):
- RSI(7) on 5m < 30 (oversold)
- MACD histogram on 5m crosses positive (momentum reversal)
- Regime on 1h is NOT strong_bear

Exit conditions:
- Take-Profit: +1.0 × ATR(14, "5m") as LIMIT order
- Stop-Loss: -1.5 × ATR(14, "5m") as MARKET order
- Trailing stop: once in profit > 0.5 × ATR, trail at 1.0 × ATR
- No overnight: close ALL positions at 23:00 UTC

This is a fast intraday strategy — positions last minutes to hours, never overnight.
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
class ScalpPosition:
    """Tracked scalping position."""

    position_id: int
    entry_price: Decimal
    entry_time: datetime
    amount_usdc: Decimal
    stop_loss: Decimal
    take_profit: Decimal
    highest_price: Decimal


class GeminiScalpingVolatilite(BaseStrategy):
    """Fast scalping strategy on 5m candles with 1h regime filter.

    Uses RSI(7) oversold + MACD histogram momentum reversal for entries.
    Tight ATR-based SL/TP for quick scalps. Flat by 23:00 UTC.
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

        # Entry conditions
        self.rsi_period: int = params.get("rsi_period", 7)
        self.rsi_oversold = Decimal(str(params.get("rsi_oversold", 30)))

        # ATR-based SL/TP multipliers
        self.sl_atr_mult = Decimal(str(params.get("sl_atr_mult", 1.5)))
        self.tp_atr_mult = Decimal(str(params.get("tp_atr_mult", 1.0)))

        # Trailing stop (activates after profit > trail_activation × ATR)
        self.trail_activation_atr = Decimal(str(params.get("trail_activation_atr", 0.5)))
        self.trail_atr_mult = Decimal(str(params.get("trail_atr_mult", 1.0)))

        # Budget & position sizing (independent per strategy)
        self.order_size_usdc = Decimal(str(params.get("order_size_usdc", 25)))
        self.max_allocation_pct = Decimal(str(params.get("max_allocation_pct", 15.0)))
        self.max_open_positions: int = params.get("max_open_positions", 2)
        # Bridge for ExecutionEngine compat: multiplier = order_size / default_order_amount
        default_order = Decimal(str(settings.trading.default_order_amount_eur))
        self._position_size_multiplier = (
            float(self.order_size_usdc / default_order) if default_order > _ZERO else 1.0
        )

        # No overnight: close hour (UTC)
        self.close_hour_utc: int = params.get("close_hour_utc", 23)

        # Internal state
        self._current_price: Decimal | None = None
        self._current_timestamp: datetime | None = None
        self._open_positions: list[ScalpPosition] = []
        self._next_position_id: int = 1

        # MACD crossover detection: track previous histogram sign
        self._prev_macd_hist: Decimal | None = None
        self._macd_hist_crossed_positive: bool = False

        self.logger.info(
            "gemini_scalping_initialized",
            bot_id=self.bot_id,
            order_size_usdc=float(self.order_size_usdc),
            max_allocation_pct=float(self.max_allocation_pct),
            rsi_period=self.rsi_period,
            rsi_oversold=float(self.rsi_oversold),
            sl_atr_mult=float(self.sl_atr_mult),
            tp_atr_mult=float(self.tp_atr_mult),
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

        # Parse timestamp
        self._current_timestamp = self._parse_timestamp(ohlc_data)

        # Only trade on 5m candles
        if interval != 5:
            return
        if not ohlc_data.get("is_complete", False):
            return

        # Track MACD histogram crossover on 5m
        self._update_macd_crossover()

    async def generate_signal(self) -> TradingSignal | None:
        if self._current_price is None or self.analyzer is None:
            return None

        now = self._current_timestamp or datetime.now(UTC)

        # --- SELL LOGIC: check existing positions ---

        # Priority 1: No overnight — close everything at close_hour_utc
        if now.hour >= self.close_hour_utc:
            for pos in self._open_positions:
                return self._make_sell_signal(
                    pos,
                    now,
                    reason="no_overnight",
                    order_type="market",
                    confidence=1.0,
                    extra=f"NO OVERNIGHT: closing at {self.close_hour_utc}:00 UTC",
                )

        atr = self.analyzer.get_atr(14, "5m")

        for pos in self._open_positions:
            profit_pct = (self._current_price - pos.entry_price) / pos.entry_price * _HUNDRED

            # Priority 2: Stop-loss (market)
            if self._current_price <= pos.stop_loss:
                return self._make_sell_signal(
                    pos,
                    now,
                    reason="stop_loss",
                    order_type="market",
                    confidence=1.0,
                    extra=f"STOP-LOSS hit at {float(pos.stop_loss):.2f} ({float(profit_pct):.2f}%)",
                )

            # Priority 3: Take-profit (limit)
            if self._current_price >= pos.take_profit:
                return self._make_sell_signal(
                    pos,
                    now,
                    reason="take_profit",
                    order_type="limit",
                    confidence=0.95,
                    extra=f"TP hit at {float(pos.take_profit):.2f} ({float(profit_pct):.2f}%)",
                    limit_price=pos.take_profit,
                )

            # Priority 4: Trailing stop
            if atr is not None and atr > _ZERO:
                profit_in_atr = (self._current_price - pos.entry_price) / atr
                if profit_in_atr >= self.trail_activation_atr:
                    trail_sl = pos.highest_price - self.trail_atr_mult * atr
                    if self._current_price <= trail_sl:
                        return self._make_sell_signal(
                            pos,
                            now,
                            reason="trailing_stop",
                            order_type="market",
                            confidence=0.95,
                            extra=(
                                f"TRAILING STOP: price {float(self._current_price):.2f} "
                                f"<= trail {float(trail_sl):.2f} "
                                f"(high {float(pos.highest_price):.2f})"
                            ),
                        )

        # --- BUY LOGIC ---

        # Guard: max positions
        if len(self._open_positions) >= self.max_open_positions:
            return None

        # Guard: no new entries near close
        if now.hour >= self.close_hour_utc - 1:
            return None

        # Check entry conditions
        buy_signal = self._check_entry_conditions()
        if buy_signal is None:
            return None

        return buy_signal

    # ------------------------------------------------------------------
    # Entry logic
    # ------------------------------------------------------------------

    def _check_entry_conditions(self) -> TradingSignal | None:
        """Check all entry conditions for a scalp BUY."""
        if self.analyzer is None or self._current_price is None:
            return None

        now = self._current_timestamp or datetime.now(UTC)

        # Condition 1: RSI(7) < 30 on 5m
        rsi = self.analyzer.get_rsi(self.rsi_period, "5m")
        if rsi is None or rsi >= self.rsi_oversold:
            return None

        # Condition 2: MACD histogram crossed positive on 5m
        if not self._macd_hist_crossed_positive:
            return None

        # Condition 3: Regime on 1h is NOT strong_bear
        regime_1h = self.analyzer.get_regime("1h")
        if regime_1h is not None and regime_1h == "strong_bear":
            return None

        # Condition 4: ATR available for SL/TP calculation
        atr = self.analyzer.get_atr(14, "5m")
        if atr is None or atr <= _ZERO:
            return None

        # Calculate SL and TP
        stop_loss = self._current_price - self.sl_atr_mult * atr
        take_profit = self._current_price + self.tp_atr_mult * atr

        # Limit price slightly below current for maker fee
        limit_price = self._current_price * Decimal("0.999")

        self.logger.info(
            "scalping_buy_signal",
            rsi=float(rsi),
            regime_1h=regime_1h,
            atr=float(atr),
            entry=float(self._current_price),
            sl=float(stop_loss),
            tp=float(take_profit),
        )

        return TradingSignal(
            signal_type=SignalType.BUY,
            pair=self.pair,
            price=self._current_price,
            confidence=0.8,
            reason=(
                f"SCALP BUY: RSI({self.rsi_period})={float(rsi):.1f} < {float(self.rsi_oversold)} "
                f"+ MACD hist cross+ (regime_1h={regime_1h})"
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
                "risk_take_profit": float(take_profit),
                "rsi_5m": float(rsi),
                "atr_5m": float(atr),
                "regime_1h": regime_1h,
            },
        )

    def _update_macd_crossover(self) -> None:
        """Detect MACD histogram crossing from negative to positive on 5m."""
        if self.analyzer is None:
            return

        macd_data = self.analyzer.get_macd("5m")
        if macd_data is None:
            return

        current_hist = macd_data.get("hist")
        if current_hist is None:
            return

        # Crossover: prev < 0 and current >= 0
        if self._prev_macd_hist is not None and self._prev_macd_hist < _ZERO <= current_hist:
            self._macd_hist_crossed_positive = True
        else:
            self._macd_hist_crossed_positive = False

        self._prev_macd_hist = current_hist

    # ------------------------------------------------------------------
    # Sell signal builder
    # ------------------------------------------------------------------

    def _make_sell_signal(
        self,
        pos: ScalpPosition,
        now: datetime,
        *,
        reason: str,
        order_type: str,
        confidence: float,
        extra: str,
        limit_price: Decimal | None = None,
    ) -> TradingSignal:
        """Build a SELL signal for a scalp position."""
        amount_btc = pos.amount_usdc / pos.entry_price if pos.entry_price > _ZERO else _ZERO
        profit_pct = (
            (self._current_price - pos.entry_price) / pos.entry_price * _HUNDRED
            if self._current_price and pos.entry_price > _ZERO
            else _ZERO
        )

        metadata: dict[str, Any] = {
            "position_id": pos.position_id,
            "amount_btc": float(amount_btc),
            "entry_price": float(pos.entry_price),
            "profit_pct": float(profit_pct),
            "reason": reason,
            "order_type": order_type,
        }
        if limit_price is not None:
            metadata["limit_price"] = float(limit_price)

        return TradingSignal(
            signal_type=SignalType.SELL,
            pair=self.pair,
            price=self._current_price or _ZERO,
            confidence=confidence,
            reason=f"Position #{pos.position_id}: {extra}",
            strategy=self.bot_id,
            timestamp=now,
            metadata=metadata,
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
            atr = self.analyzer.get_atr(14, "5m") if self.analyzer else None
            sl_dist = self.sl_atr_mult * atr if atr and atr > _ZERO else price * Decimal("0.02")
            tp_dist = self.tp_atr_mult * atr if atr and atr > _ZERO else price * Decimal("0.01")

            pid = self._next_position_id
            self._next_position_id += 1

            self._open_positions.append(
                ScalpPosition(
                    position_id=pid,
                    entry_price=price,
                    entry_time=datetime.now(UTC),
                    amount_usdc=amount * price,
                    stop_loss=price - sl_dist,
                    take_profit=price + tp_dist,
                    highest_price=price,
                )
            )
            self.logger.info(
                "scalp_position_opened",
                position_id=pid,
                entry=float(price),
                sl=float(price - sl_dist),
                tp=float(price + tp_dist),
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
                        "scalp_position_closed",
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
        return "gemini_scalping_volatilite"

    def get_config(self) -> dict[str, Any]:
        return {
            "name": self.get_name(),
            "bot_id": self.bot_id,
            "pair": self.pair,
            "order_size_usdc": float(self.order_size_usdc),
            "max_allocation_pct": float(self.max_allocation_pct),
            "rsi_period": self.rsi_period,
            "rsi_oversold": float(self.rsi_oversold),
            "sl_atr_mult": float(self.sl_atr_mult),
            "tp_atr_mult": float(self.tp_atr_mult),
            "trail_activation_atr": float(self.trail_activation_atr),
            "trail_atr_mult": float(self.trail_atr_mult),
            "max_open_positions": self.max_open_positions,
            "close_hour_utc": self.close_hour_utc,
            "open_positions": len(self._open_positions),
        }
