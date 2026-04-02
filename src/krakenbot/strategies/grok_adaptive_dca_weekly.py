"""Grok Adaptive DCA Weekly — weekly Bitcoin accumulation strategy.

Buys BTC every Monday at 00:00 UTC (on the daily candle) with an amount
that adapts to market conditions:

Key rules:
1. BASE BUY every Monday: base_amount_usdc (default 15 USDC)
2. OVERSOLD BOOST: if RSI(14, "1d") < 30 AND close < EMA(200, "1d")
   → amount *= oversold_multiplier (default 2.5x)
3. BULL REDUCTION: if regime_1w == "strong_bull"
   → amount *= bull_reduction (default 0.5x)
4. Limit order at price * 0.999 (maker fee optimization)
5. NO automatic SELL — pure accumulation strategy

Params (from strategies.yaml):
    base_amount_usdc: Weekly buy amount in USDC (default 15)
    oversold_multiplier: Multiplier when RSI oversold + below EMA200 (default 2.5)
    bull_reduction: Multiplier when strong bull (reduces FOMO buys) (default 0.5)
    rsi_oversold: RSI threshold for oversold detection (default 30)
    max_allocation_pct: Max % of total capital (default 25.0)
"""

from __future__ import annotations

from dataclasses import dataclass, field
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
class DCABuy:
    """Record of a DCA purchase."""

    buy_id: int
    price: Decimal
    amount_usdc: Decimal
    amount_btc: Decimal
    timestamp: datetime
    rsi_1d: float | None = None
    regime_1w: str | None = None
    multiplier_applied: str = "base"


@dataclass
class DCAStats:
    """Aggregated DCA statistics for logging."""

    total_buys: int = 0
    total_usdc_invested: Decimal = _ZERO
    total_btc_accumulated: Decimal = _ZERO
    avg_entry_price: Decimal = _ZERO
    buys: list[DCABuy] = field(default_factory=list)


class GrokAdaptiveDCAWeekly(BaseStrategy):
    """Weekly adaptive DCA strategy for Bitcoin accumulation.

    Mechanical buying every Monday with amount adjusted by market conditions.
    No selling — designed for long-term BTC accumulation.
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
        """Initialize GrokAdaptiveDCAWeekly."""
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

        # DCA parameters
        self.base_amount_usdc = Decimal(str(params.get("base_amount_usdc", 15)))
        self.oversold_multiplier = Decimal(str(params.get("oversold_multiplier", 2.5)))
        self.bull_reduction = Decimal(str(params.get("bull_reduction", 0.5)))
        self.rsi_oversold = Decimal(str(params.get("rsi_oversold", 30)))

        # Budget (independent per strategy)
        self.max_allocation_pct = Decimal(str(params.get("max_allocation_pct", 25.0)))
        # Bridge for ExecutionEngine compat
        default_order = Decimal(str(settings.trading.default_order_amount_eur))
        self._position_size_multiplier = (
            float(self.base_amount_usdc / default_order) if default_order > _ZERO else 1.0
        )

        # Internal state
        self._current_price: Decimal | None = None
        self._current_timestamp: datetime | None = None
        self._is_daily: bool = False
        self._last_buy_week: int | None = None  # ISO week number of last buy
        self._pending_week_key: int | None = None  # Set on signal, committed on fill

        # Statistics tracking
        self._stats = DCAStats()
        self._next_buy_id: int = 1

        self.logger.info(
            "grok_adaptive_dca_weekly_initialized",
            bot_id=self.bot_id,
            base_amount_usdc=float(self.base_amount_usdc),
            oversold_multiplier=float(self.oversold_multiplier),
            bull_reduction=float(self.bull_reduction),
            rsi_oversold=float(self.rsi_oversold),
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
        """Generate weekly DCA buy signal on Monday daily candles.

        Conditions:
        1. Daily candle (tf == "1d")
        2. Monday (weekday == 0)
        3. Haven't bought this ISO week yet
        4. Adapts amount based on RSI + regime
        """
        if self._current_price is None or self._current_price <= _ZERO:
            return None
        if self.analyzer is None:
            return None
        if not self._is_daily:
            return None

        now = self._current_timestamp or datetime.now(UTC)
        price = self._current_price

        # Only trigger on Monday
        if now.weekday() != 0:
            return None

        # Prevent duplicate buys in the same ISO week
        iso_week = now.isocalendar()[1]
        iso_year = now.isocalendar()[0]
        week_key = iso_year * 100 + iso_week  # Unique per year+week
        if self._last_buy_week == week_key:
            return None

        # Calculate adaptive amount
        amount_usdc = self.base_amount_usdc
        multiplier_label = "base"

        # Check oversold condition: RSI < 30 AND price < EMA(200, "1d")
        rsi_1d = self.analyzer.get_rsi(14, "1d")
        ema200_1d = self.analyzer.get_ema(200, "1d")

        if rsi_1d is not None and ema200_1d is not None:
            if rsi_1d < self.rsi_oversold and price < ema200_1d:
                amount_usdc = amount_usdc * self.oversold_multiplier
                multiplier_label = "oversold_boost"
                self.logger.info(
                    "dca_oversold_boost",
                    rsi_1d=float(rsi_1d),
                    ema200_1d=float(ema200_1d),
                    price=float(price),
                    amount_usdc=float(amount_usdc),
                )

        # Check bull reduction: regime_1w == "strong_bull"
        regime_1w = self.analyzer.get_regime("1w")

        if regime_1w == "strong_bull":
            amount_usdc = amount_usdc * self.bull_reduction
            multiplier_label = (
                "oversold_boost+bull_reduce"
                if multiplier_label == "oversold_boost"
                else "bull_reduce"
            )
            self.logger.info(
                "dca_bull_reduction",
                regime_1w=regime_1w,
                amount_usdc=float(amount_usdc),
            )

        # Limit order slightly below current price (maker fee)
        limit_price = price * Decimal("0.999")

        # Compute position_size_multiplier for this specific amount
        default_order = Decimal(str(self.settings.trading.default_order_amount_eur))
        psm = float(amount_usdc / default_order) if default_order > _ZERO else 1.0

        regime_1d = self.analyzer.get_regime("1d")

        self.logger.info(
            "dca_weekly_buy_signal",
            price=float(price),
            amount_usdc=float(amount_usdc),
            multiplier=multiplier_label,
            rsi_1d=float(rsi_1d) if rsi_1d is not None else None,
            ema200_1d=float(ema200_1d) if ema200_1d is not None else None,
            regime_1w=regime_1w,
            regime_1d=regime_1d,
            iso_week=iso_week,
        )

        # Remember which week this signal is for (committed on fill)
        self._pending_week_key = week_key

        return TradingSignal(
            signal_type=SignalType.BUY,
            pair=self.pair,
            price=price,
            confidence=0.8,
            reason=(
                f"DCA WEEKLY: {float(amount_usdc):.0f} USDC "
                f"({multiplier_label}, RSI={float(rsi_1d):.0f})"
                if rsi_1d is not None
                else f"DCA WEEKLY: {float(amount_usdc):.0f} USDC ({multiplier_label})"
            ),
            strategy=self.bot_id,
            timestamp=now,
            metadata={
                "order_type": "limit",
                "limit_price": float(limit_price),
                "order_size_usdc": float(amount_usdc),
                "max_allocation_pct": float(self.max_allocation_pct),
                "position_size_multiplier": psm,
                "multiplier_label": multiplier_label,
                "rsi_1d": float(rsi_1d) if rsi_1d is not None else None,
                "ema200_1d": float(ema200_1d) if ema200_1d is not None else None,
                "regime_1w": regime_1w,
                "regime_1d": regime_1d,
                "iso_week": iso_week,
            },
        )

    # ------------------------------------------------------------------
    # OHLC filtering
    # ------------------------------------------------------------------

    async def _handle_ohlc(self, data: dict[str, Any]) -> None:
        """Override to set _is_daily flag before generate_signal."""
        if not self._running:
            return

        try:
            tf = data.get("timeframe", data.get("interval"))
            self._is_daily = tf in ("1d", 1440, "1440")

            await self.on_ohlc(data)

            # Only generate signals on daily candles
            if not self._is_daily:
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
                "dca_weekly_ohlc_error",
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
        """Handle trade fill — record DCA purchase for stats."""
        now = self._current_timestamp or datetime.now(UTC)

        if side == "buy":
            # Confirm the week as bought only when the fill actually arrives
            if self._pending_week_key is not None:
                self._last_buy_week = self._pending_week_key
                self._pending_week_key = None

            amount_usdc = amount * price
            buy_id = self._next_buy_id
            self._next_buy_id += 1

            buy = DCABuy(
                buy_id=buy_id,
                price=price,
                amount_usdc=amount_usdc,
                amount_btc=amount,
                timestamp=now,
            )
            self._stats.buys.append(buy)
            self._stats.total_buys += 1
            self._stats.total_usdc_invested += amount_usdc
            self._stats.total_btc_accumulated += amount

            # Recalculate weighted average entry
            if self._stats.total_btc_accumulated > _ZERO:
                self._stats.avg_entry_price = (
                    self._stats.total_usdc_invested / self._stats.total_btc_accumulated
                )

            self.logger.info(
                "dca_weekly_buy_filled",
                buy_id=buy_id,
                price=float(price),
                amount_btc=float(amount),
                amount_usdc=float(amount_usdc),
                fee=float(fee),
                total_buys=self._stats.total_buys,
                total_btc=float(self._stats.total_btc_accumulated),
                total_usdc=float(self._stats.total_usdc_invested),
                avg_entry=float(self._stats.avg_entry_price),
            )

        # No sell handling — this is a pure accumulation strategy

    # ------------------------------------------------------------------
    # Info
    # ------------------------------------------------------------------

    def get_name(self) -> str:
        """Return strategy name."""
        return "grok_adaptive_dca_weekly"

    def get_config(self) -> dict[str, Any]:
        """Return strategy configuration."""
        return {
            "name": self.get_name(),
            "bot_id": self.bot_id,
            "pair": self.pair,
            "base_amount_usdc": float(self.base_amount_usdc),
            "oversold_multiplier": float(self.oversold_multiplier),
            "bull_reduction": float(self.bull_reduction),
            "rsi_oversold": float(self.rsi_oversold),
            "max_allocation_pct": float(self.max_allocation_pct),
            "total_buys": self._stats.total_buys,
            "total_btc": float(self._stats.total_btc_accumulated),
            "total_usdc_invested": float(self._stats.total_usdc_invested),
            "avg_entry_price": float(self._stats.avg_entry_price),
            "last_buy_week": self._last_buy_week,
            "pending_week_key": self._pending_week_key,
        }
