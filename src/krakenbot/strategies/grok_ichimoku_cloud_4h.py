"""Grok Ichimoku Cloud Breakout 4h — trend-following cloud breakout strategy.

Uses the Ichimoku Cloud on the 4h timeframe as the primary signal,
filtered by the daily regime and ADX trend strength.

Key rules:
1. BUY when close breaks above cloud_top AND prev_close <= prev_cloud_top
   AND regime_1d in [bull, strong_bull] AND ADX(14, 1d) > 20
2. EXIT when close < cloud_bottom → market order
3. EXIT when regime_1d in [bear, strong_bear] → market order
4. Initial SL = 3.0 × ATR(14, 4h) below entry
5. Trailing: after +1.5×ATR profit → trail at cloud_bottom (dynamic)
6. Single position at a time

Params (from strategies.yaml):
    sl_atr_mult: Initial SL ATR multiplier (default 3.0)
    trail_atr_threshold: ATR profit before trailing activates (default 1.5)
    adx_threshold: Min ADX(14, 1d) for entry (default 20)
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
class IchimokuPosition:
    """An open position managed by the Ichimoku strategy."""

    position_id: int
    entry_price: Decimal
    entry_time: datetime
    amount_usdc: Decimal
    stop_loss: Decimal
    highest_price: Decimal
    trailing_activated: bool = False


class GrokIchimokuCloudBreakoutV1(BaseStrategy):
    """Trend-following strategy using 4h Ichimoku Cloud breakout + daily regime.

    Enters on a fresh breakout above the cloud top, exits when price drops
    below cloud bottom or regime turns bearish.
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
        """Initialize GrokIchimokuCloudBreakoutV1."""
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

        # Parameters
        self.sl_atr_mult = Decimal(str(params.get("sl_atr_mult", 3.0)))
        self.trail_atr_threshold = Decimal(str(params.get("trail_atr_threshold", 1.5)))
        self.adx_threshold = Decimal(str(params.get("adx_threshold", 20)))
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
        self._position: IchimokuPosition | None = None
        self._next_position_id: int = 1
        self._is_4h: bool = False

        # Track previous values for crossover detection
        self._prev_close: Decimal | None = None
        self._prev_cloud_top: Decimal | None = None

        self.logger.info(
            "grok_ichimoku_cloud_4h_initialized",
            bot_id=self.bot_id,
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
        """Generate signal based on 4h Ichimoku Cloud + 1d regime."""
        if self._current_price is None or self._current_price <= _ZERO:
            return None
        if self.analyzer is None:
            return None
        if not self._is_4h:
            return None

        now = self._current_timestamp or datetime.now(UTC)
        price = self._current_price

        # Get Ichimoku on 4h
        ichi = self.analyzer.get_ichimoku("4h")
        if ichi is None:
            return None

        cloud_top = ichi["cloud_top"]
        cloud_bottom = ichi["cloud_bottom"]

        # Get daily regime & ADX
        regime_1d = self.analyzer.get_regime("1d")
        adx_4h = self.analyzer.get_adx("4h")

        # --- Exit logic (check before entry) ---
        if self._position is not None:
            signal = self._check_exit(price, cloud_bottom, regime_1d, now)
            if signal:
                self._prev_close = price
                self._prev_cloud_top = cloud_top
                return signal

            # Update trailing stop
            self._update_trailing(price, cloud_bottom)

            # Track highest price
            if price > self._position.highest_price:
                self._position.highest_price = price

            self._prev_close = price
            self._prev_cloud_top = cloud_top
            return None

        # --- Entry logic ---
        adx_1d = self.analyzer.get_adx("1d")
        signal = self._check_entry(price, cloud_top, regime_1d, adx_1d, adx_4h, now)

        # Update previous values for crossover detection
        self._prev_close = price
        self._prev_cloud_top = cloud_top

        return signal

    # ------------------------------------------------------------------
    # Exit logic
    # ------------------------------------------------------------------

    def _check_exit(
        self,
        price: Decimal,
        cloud_bottom: Decimal,
        regime_1d: str | None,
        now: datetime,
    ) -> TradingSignal | None:
        """Check exit conditions."""
        pos = self._position
        if pos is None:
            return None

        profit_pct = (price - pos.entry_price) / pos.entry_price * _HUNDRED

        # 1. Price below cloud bottom
        if price < cloud_bottom:
            return self._make_exit_signal(
                pos,
                price,
                now,
                reason="below_cloud",
                extra=(
                    f"Below cloud: price={float(price):.1f} < bottom={float(cloud_bottom):.1f}"
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

    def _update_trailing(self, price: Decimal, cloud_bottom: Decimal) -> None:
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
            self.logger.debug("ichimoku_trailing_activated", price=float(price))

        if pos.trailing_activated and cloud_bottom > pos.stop_loss:
            pos.stop_loss = cloud_bottom
            self.logger.debug(
                "ichimoku_trailing_sl_updated",
                new_sl=float(cloud_bottom),
                price=float(price),
            )

    def _make_exit_signal(
        self,
        pos: IchimokuPosition,
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
            reason=f"ICHIMOKU EXIT: {extra}",
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
        cloud_top: Decimal,
        regime_1d: str | None,
        adx_1d: Decimal | None,
        adx_4h: Decimal | None,
        now: datetime,
    ) -> TradingSignal | None:
        """Check entry conditions.

        BUY when:
        1. close > cloud_top AND prev_close <= prev_cloud_top (fresh breakout)
        2. regime_1d in [bull, strong_bull]
        3. ADX(14, 1d) > adx_threshold
        """
        if self._position is not None:
            return None

        # Must break above cloud
        if price <= cloud_top:
            return None

        # Fresh breakout: previous candle was at or below cloud top
        if self._prev_close is None or self._prev_cloud_top is None:
            return None
        if self._prev_close > self._prev_cloud_top:
            return None  # Already above cloud — not a fresh breakout

        # Daily regime must be bullish
        if regime_1d not in ("bull", "strong_bull"):
            return None

        # ADX filter on daily
        if adx_1d is None or adx_1d < self.adx_threshold:
            return None

        # ATR for initial stop-loss
        atr = self.analyzer.get_atr(14, "4h")
        if atr is None or atr <= _ZERO:
            return None

        stop_loss = price - self.sl_atr_mult * atr
        if stop_loss <= _ZERO:
            stop_loss = price * Decimal("0.90")

        # Confidence = ADX(14, 4h) / 100
        confidence = float(adx_4h / _HUNDRED) if adx_4h is not None else 0.5
        confidence = max(0.3, min(confidence, 1.0))

        limit_price = price * Decimal("0.999")

        self.logger.info(
            "ichimoku_entry_signal",
            price=float(price),
            cloud_top=float(cloud_top),
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
                f"ICHIMOKU BUY: breakout above cloud "
                f"price={float(price):.1f} > top={float(cloud_top):.1f}"
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
                "cloud_top": float(cloud_top),
                "regime_1d": regime_1d,
                "adx_1d": float(adx_1d),
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
                "ichimoku_ohlc_error",
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

            self._position = IchimokuPosition(
                position_id=pid,
                entry_price=price,
                entry_time=now,
                amount_usdc=amount_usdc,
                stop_loss=sl,
                highest_price=price,
            )

            self.logger.info(
                "ichimoku_position_opened",
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
                    "ichimoku_position_closed",
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
        return "grok_ichimoku_cloud_4h"

    def get_config(self) -> dict[str, Any]:
        """Return strategy configuration."""
        return {
            "name": self.get_name(),
            "bot_id": self.bot_id,
            "pair": self.pair,
            "sl_atr_mult": float(self.sl_atr_mult),
            "trail_atr_threshold": float(self.trail_atr_threshold),
            "adx_threshold": float(self.adx_threshold),
            "order_size_usdc": float(self.order_size_usdc),
            "max_allocation_pct": float(self.max_allocation_pct),
            "has_position": self._position is not None,
            "position_entry": (float(self._position.entry_price) if self._position else None),
            "position_sl": (float(self._position.stop_loss) if self._position else None),
        }
