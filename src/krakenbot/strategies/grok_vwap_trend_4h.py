"""Grok VWAP Trend 4h — trend-following VWAP crossover strategy.

Uses a rolling VWAP(20) proxy on the 4h timeframe as the primary signal,
filtered by the daily regime.

Key rules:
1. BUY when close crosses above VWAP(20, 4h) AND prev_close <= prev_vwap
   AND regime_1d in [bull, strong_bull]
2. EXIT when close crosses below VWAP(20, 4h) → market order
3. EXIT when regime_1d in [bear, strong_bear] → market order
4. Initial SL = 3.0 × ATR(14, 4h) below entry
5. Trailing: after +2.0×ATR profit → trail at VWAP (dynamic)
6. Single position at a time

Note: The VWAP is a rolling proxy = sum(close*vol, 20) / sum(vol, 20),
not a true session-anchored VWAP.

Params (from strategies.yaml):
    vwap_period: VWAP look-back (default 20)
    sl_atr_mult: Initial SL ATR multiplier (default 3.0)
    trail_atr_threshold: ATR profit before trailing activates (default 2.0)
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
class VWAPPosition:
    """An open position managed by the VWAP strategy."""

    position_id: int
    entry_price: Decimal
    entry_time: datetime
    amount_usdc: Decimal
    stop_loss: Decimal
    highest_price: Decimal
    trailing_activated: bool = False


class GrokVWAPTrendV1(BaseStrategy):
    """Trend-following strategy using 4h rolling VWAP crossover + daily regime.

    Enters when price crosses above the rolling VWAP in a bullish regime,
    exits when price crosses back below or regime turns bearish.
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
        """Initialize GrokVWAPTrendV1."""
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

        # VWAP parameters
        self.vwap_period: int = int(params.get("vwap_period", 20))

        # Risk parameters
        self.sl_atr_mult = Decimal(str(params.get("sl_atr_mult", 3.0)))
        self.trail_atr_threshold = Decimal(str(params.get("trail_atr_threshold", 2.0)))

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
        self._position: VWAPPosition | None = None
        self._next_position_id: int = 1
        self._is_4h: bool = False

        # Track previous values for crossover detection
        self._prev_close: Decimal | None = None
        self._prev_vwap: Decimal | None = None

        self.logger.info(
            "grok_vwap_trend_4h_initialized",
            bot_id=self.bot_id,
            vwap_period=self.vwap_period,
            sl_atr_mult=float(self.sl_atr_mult),
            trail_atr_threshold=float(self.trail_atr_threshold),
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
        """Generate signal based on 4h VWAP crossover + 1d regime."""
        if self._current_price is None or self._current_price <= _ZERO:
            return None
        if self.analyzer is None:
            return None
        if not self._is_4h:
            return None

        now = self._current_timestamp or datetime.now(UTC)
        price = self._current_price

        # Get VWAP on 4h
        vwap = self.analyzer.get_vwap(self.vwap_period, "4h")
        if vwap is None:
            return None

        # Get daily regime
        regime_1d = self.analyzer.get_regime("1d")

        # --- Exit logic (check before entry) ---
        if self._position is not None:
            signal = self._check_exit(price, vwap, regime_1d, now)
            if signal:
                self._prev_close = price
                self._prev_vwap = vwap
                return signal

            # Update trailing stop
            self._update_trailing(price, vwap)

            # Track highest price
            if price > self._position.highest_price:
                self._position.highest_price = price

            self._prev_close = price
            self._prev_vwap = vwap
            return None

        # --- Entry logic ---
        rsi_4h = self.analyzer.get_rsi(14, "4h")
        signal = self._check_entry(price, vwap, regime_1d, rsi_4h, now)

        # Update previous values
        self._prev_close = price
        self._prev_vwap = vwap

        return signal

    # ------------------------------------------------------------------
    # Exit logic
    # ------------------------------------------------------------------

    def _check_exit(
        self,
        price: Decimal,
        vwap: Decimal,
        regime_1d: str | None,
        now: datetime,
    ) -> TradingSignal | None:
        """Check exit conditions."""
        pos = self._position
        if pos is None:
            return None

        profit_pct = (price - pos.entry_price) / pos.entry_price * _HUNDRED

        # 1. Price crosses below VWAP
        if price < vwap:
            return self._make_exit_signal(
                pos,
                price,
                now,
                reason="below_vwap",
                extra=(
                    f"Below VWAP: price={float(price):.1f} < vwap={float(vwap):.1f}"
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

    def _update_trailing(self, price: Decimal, vwap: Decimal) -> None:
        """Update trailing stop after profit threshold."""
        pos = self._position
        if pos is None:
            return

        atr = self.analyzer.get_atr(14, "4h") if self.analyzer else None
        if atr is None or atr <= _ZERO:
            return

        profit = price - pos.entry_price
        if not pos.trailing_activated and profit >= self.trail_atr_threshold * atr:
            pos.trailing_activated = True
            self.logger.debug("vwap_trailing_activated", price=float(price))

        if pos.trailing_activated and vwap > pos.stop_loss:
            pos.stop_loss = vwap
            self.logger.debug(
                "vwap_trailing_sl_updated",
                new_sl=float(vwap),
                price=float(price),
            )

    def _make_exit_signal(
        self,
        pos: VWAPPosition,
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
            reason=f"VWAP EXIT: {extra}",
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
        vwap: Decimal,
        regime_1d: str | None,
        rsi_4h: Decimal | None,
        now: datetime,
    ) -> TradingSignal | None:
        """Check entry conditions.

        BUY when:
        1. close > VWAP AND prev_close <= prev_vwap (crossover)
        2. regime_1d in [bull, strong_bull]
        """
        if self._position is not None:
            return None

        # Must be above VWAP
        if price <= vwap:
            return None

        # Fresh crossover: previous close was at or below VWAP
        if self._prev_close is None or self._prev_vwap is None:
            return None
        if self._prev_close > self._prev_vwap:
            return None  # Already above — not a fresh crossover

        # Daily regime must be bullish
        if regime_1d not in ("bull", "strong_bull"):
            return None

        # ATR for initial stop-loss
        atr = self.analyzer.get_atr(14, "4h")
        if atr is None or atr <= _ZERO:
            return None

        stop_loss = price - self.sl_atr_mult * atr
        if stop_loss <= _ZERO:
            stop_loss = price * Decimal("0.90")

        # Confidence = RSI(14, 4h) / 100
        confidence = float(rsi_4h / _HUNDRED) if rsi_4h is not None else 0.5
        confidence = max(0.3, min(confidence, 1.0))

        limit_price = price * Decimal("0.999")

        self.logger.info(
            "vwap_entry_signal",
            price=float(price),
            vwap=float(vwap),
            regime_1d=regime_1d,
            rsi_4h=float(rsi_4h) if rsi_4h else None,
            stop_loss=float(stop_loss),
        )

        return TradingSignal(
            signal_type=SignalType.BUY,
            pair=self.pair,
            price=price,
            confidence=confidence,
            reason=(
                f"VWAP BUY: crossover above VWAP "
                f"price={float(price):.1f} > vwap={float(vwap):.1f}"
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
                "vwap": float(vwap),
                "regime_1d": regime_1d,
                "rsi_4h": float(rsi_4h) if rsi_4h else None,
                "atr_4h": float(atr),
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
                "vwap_ohlc_error",
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

            self._position = VWAPPosition(
                position_id=pid,
                entry_price=price,
                entry_time=now,
                amount_usdc=amount_usdc,
                stop_loss=sl,
                highest_price=price,
            )

            self.logger.info(
                "vwap_position_opened",
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
                    "vwap_position_closed",
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
        return "grok_vwap_trend_4h"

    def get_config(self) -> dict[str, Any]:
        """Return strategy configuration."""
        return {
            "name": self.get_name(),
            "bot_id": self.bot_id,
            "pair": self.pair,
            "vwap_period": self.vwap_period,
            "sl_atr_mult": float(self.sl_atr_mult),
            "trail_atr_threshold": float(self.trail_atr_threshold),
            "order_size_usdc": float(self.order_size_usdc),
            "max_allocation_pct": float(self.max_allocation_pct),
            "has_position": self._position is not None,
            "position_entry": (float(self._position.entry_price) if self._position else None),
            "position_sl": (float(self._position.stop_loss) if self._position else None),
        }
