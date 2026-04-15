"""Grok Grid ATR Adaptive V4 — ATR-based adaptive grid with directional bias.

Places a grid of BUY/SELL limit orders with spacing derived from ATR(14, "4h").
The grid adapts to volatility (wider spacing when ATR rises) and applies a
directional bias based on the daily regime (more BUY in bull, more SELL in bear).

Key innovations over basic grid:
1. Spacing = max(min_spacing_pct, ATR × multiplier / price)
2. Directional bias: more BUY levels in BULL, more SELL in BEAR
3. Regime filter: pauses entirely in weekly STRONG_BEAR
4. Periodic recalculation (every recalc_hours)

Params (from strategies.yaml):
    grid_levels: Number of grid levels (default 12)
    min_spacing_pct: Minimum spacing floor as fraction (default 0.015 = 1.5%)
    atr_period: ATR period (default 14)
    atr_multiplier: ATR multiplier for spacing calc (default 4.0)
    recalc_hours: Recalculate grid every N hours (default 6)
    order_size_usdc: USDC per grid level (default 25)
    max_allocation_pct: Max % of total capital (default 20.0)
    bias_1d: Directional bias strength (default 0.2)
    pause_1w_strong_bear: Pause in weekly strong bear (default true)
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
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
class GridATRLevel:
    """A single level in the ATR-adaptive grid."""

    price: Decimal
    side: str  # "buy" or "sell"
    status: str  # "pending", "filled", "cancelled"
    amount_usdc: Decimal


@dataclass
class GridATRPosition:
    """An open grid position (buy filled, awaiting paired sell)."""

    position_id: int
    entry_price: Decimal
    entry_time: datetime
    amount_btc: Decimal
    amount_usdc: Decimal
    sell_level: Decimal


class GrokGridATRAdaptiveV4(BaseStrategy):
    """ATR-adaptive grid with regime-based directional bias.

    Overrides ``_handle_ohlc()`` to manage multiple simultaneous limit orders
    instead of the one-signal-per-candle pattern.  Grid logic triggers only
    on 4h candles; price state is updated on every candle.
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
        """Initialize GrokGridATRAdaptiveV4."""
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

        # Grid parameters
        self.grid_levels: int = int(params.get("grid_levels", 12))
        self.min_spacing_pct = Decimal(str(params.get("min_spacing_pct", 0.015)))
        self.max_spacing_pct = Decimal(str(params.get("max_spacing_pct", 0.05)))
        self.atr_period: int = int(params.get("atr_period", 14))
        self.atr_multiplier = Decimal(str(params.get("atr_multiplier", 4.0)))
        self.recalc_hours: int = int(params.get("recalc_hours", 6))

        # Directional bias
        self.bias_1d = Decimal(str(params.get("bias_1d", 0.2)))
        self.pause_1w_strong_bear: bool = params.get("pause_1w_strong_bear", True)

        # Budget & position sizing (independent per strategy)
        self.order_size_usdc = Decimal(str(params.get("order_size_usdc", 25)))
        self.max_allocation_pct = Decimal(str(params.get("max_allocation_pct", 20.0)))
        # Bridge for ExecutionEngine compat
        default_order = Decimal(str(settings.trading.default_order_amount_eur))
        self._position_size_multiplier = (
            float(self.order_size_usdc / default_order) if default_order > _ZERO else 1.0
        )

        # Grid state
        self._grid_levels: dict[str, GridATRLevel] = {}  # key = f"{side}_{price}"
        self._grid_positions: list[GridATRPosition] = []
        self._grid_center: Decimal | None = None
        self._grid_spacing: Decimal | None = None
        self._grid_initialized: bool = False
        self._next_position_id: int = 1
        self._last_recalc: datetime | None = None
        self._paused: bool = False

        # Price state
        self._current_price: Decimal | None = None
        self._current_timestamp: datetime | None = None

        # Tracking
        self._total_grid_profit: Decimal = _ZERO
        self._completed_pairs: int = 0

        # Backtest compatibility
        self._skip_db_sync: bool = False

        self.logger.info(
            "grok_grid_atr_v4_initialized",
            bot_id=self.bot_id,
            grid_levels=self.grid_levels,
            min_spacing_pct=float(self.min_spacing_pct),
            max_spacing_pct=float(self.max_spacing_pct),
            atr_multiplier=float(self.atr_multiplier),
            recalc_hours=self.recalc_hours,
            order_size_usdc=float(self.order_size_usdc),
            max_allocation_pct=float(self.max_allocation_pct),
            bias_1d=float(self.bias_1d),
            pause_1w_strong_bear=self.pause_1w_strong_bear,
        )

    # ------------------------------------------------------------------
    # Grid construction
    # ------------------------------------------------------------------

    def _calculate_spacing(self, atr: Decimal, price: Decimal) -> Decimal:
        """Calculate grid spacing from ATR.

        spacing = clamp(atr × atr_multiplier / price, min_spacing_pct, max_spacing_pct)

        Returns:
            Spacing as a fraction of price (e.g. 0.02 = 2%).
        """
        if price <= _ZERO:
            return self.min_spacing_pct
        atr_spacing = atr * self.atr_multiplier / price
        return max(self.min_spacing_pct, min(self.max_spacing_pct, atr_spacing))

    def _get_directional_bias(self, regime_1d: str | None) -> tuple[int, int]:
        """Return (n_buy_levels, n_sell_levels) based on daily regime.

        BULL → more buys below (buy the dips)
        BEAR → more sells above (exit rallies)
        NEUTRAL → even split

        Returns:
            Tuple of (n_buy, n_sell).
        """
        total = self.grid_levels
        half = total // 2

        if regime_1d in ("bull", "strong_bull"):
            buy_extra = int(float(self.bias_1d) * half)
            n_buy = half + buy_extra
            n_sell = total - n_buy
        elif regime_1d in ("bear", "strong_bear"):
            sell_extra = int(float(self.bias_1d) * half)
            n_sell = half + sell_extra
            n_buy = total - n_sell
        else:
            n_buy = half
            n_sell = total - n_buy

        return max(1, n_buy), max(1, n_sell)

    def _build_grid(
        self,
        current_price: Decimal,
        spacing: Decimal,
        regime_1d: str | None,
    ) -> list[GridATRLevel]:
        """Build grid levels around current price with directional bias.

        Args:
            current_price: Center price for the grid.
            spacing: Spacing as a fraction of price (e.g. 0.02 = 2%).
            regime_1d: Daily regime for bias calculation.

        Returns:
            List of GridATRLevel objects created.
        """
        n_buy, n_sell = self._get_directional_bias(regime_1d)

        self._grid_center = current_price
        self._grid_spacing = spacing
        self._grid_levels.clear()

        levels: list[GridATRLevel] = []

        # BUY levels below current price
        for i in range(1, n_buy + 1):
            level_price = current_price * (_ONE - spacing * Decimal(str(i)))
            level_price = level_price.quantize(Decimal("0.1"))
            if level_price <= _ZERO:
                continue
            order = GridATRLevel(
                price=level_price,
                side="buy",
                status="pending",
                amount_usdc=self.order_size_usdc,
            )
            self._grid_levels[f"buy_{level_price}"] = order
            levels.append(order)

        # SELL levels above current price
        for i in range(1, n_sell + 1):
            level_price = current_price * (_ONE + spacing * Decimal(str(i)))
            level_price = level_price.quantize(Decimal("0.1"))
            order = GridATRLevel(
                price=level_price,
                side="sell",
                status="pending",
                amount_usdc=self.order_size_usdc,
            )
            self._grid_levels[f"sell_{level_price}"] = order
            levels.append(order)

        self._grid_initialized = True

        self.logger.info(
            "grid_atr_built",
            center=float(current_price),
            spacing_pct=float(spacing * _HUNDRED),
            n_buy=n_buy,
            n_sell=n_sell,
            regime_1d=regime_1d,
            total_levels=len(levels),
        )

        return levels

    # ------------------------------------------------------------------
    # BaseStrategy interface
    # ------------------------------------------------------------------

    async def on_tick(self, tick_data: dict[str, Any]) -> None:
        """Handle tick — update price."""
        price = tick_data.get("price")
        if price is not None:
            self._current_price = Decimal(str(price))

    async def on_ohlc(self, ohlc_data: dict[str, Any]) -> None:
        """Handle OHLC — update price state."""
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
        """Grid manages its own signals via _handle_ohlc — always None."""
        return None

    # ------------------------------------------------------------------
    # _handle_ohlc override (multi-order grid pattern)
    # ------------------------------------------------------------------

    async def _handle_ohlc(self, data: dict[str, Any]) -> None:
        """Override base _handle_ohlc for grid multi-order management.

        Price state is updated on every candle, but grid logic only
        triggers on 4h candles.

        Steps:
        1. Update price (all candles)
        2. Check regime_1w → pause if STRONG_BEAR
        3. Get ATR(14, "4h") → calculate spacing
        4. Initialize or recalculate grid
        5. Emit limit order signals for new levels
        """
        if not self._running:
            return

        try:
            await self.on_ohlc(data)

            if self._current_price is None or self._current_price <= _ZERO:
                return

            # Grid logic only on 4h candles
            tf = data.get("timeframe", data.get("interval"))
            if tf not in ("4h", 240, "240"):
                return

            if self.analyzer is None:
                return

            now = self._current_timestamp or datetime.now(UTC)

            # Rule: Pause in weekly STRONG_BEAR
            regime_1w = self.analyzer.get_regime("1w")
            if self.pause_1w_strong_bear and regime_1w == "strong_bear":
                if not self._paused:
                    self.logger.info("grid_paused_strong_bear_1w", regime_1w=regime_1w)
                    self._paused = True
                self.logger.info(
                    "strategy_tick",
                    strategy=self.get_name(),
                    bot_id=self.bot_id,
                    pair=self.pair,
                    timeframe="4h",
                    close=str(self._current_price),
                    signal="PAUSED",
                    reason="weekly_strong_bear",
                    metadata={"regime_1w": regime_1w},
                )
                return
            if self._paused:
                self._paused = False
                self.logger.info("grid_resumed", regime_1w=regime_1w)

            # Get ATR for spacing calculation
            atr = self.analyzer.get_atr(self.atr_period, "4h")
            if atr is None or atr <= _ZERO:
                self.logger.info(
                    "strategy_tick",
                    strategy=self.get_name(),
                    bot_id=self.bot_id,
                    pair=self.pair,
                    timeframe="4h",
                    close=str(self._current_price),
                    signal="HOLD",
                    reason="atr_unavailable",
                )
                return

            spacing = self._calculate_spacing(atr, self._current_price)
            regime_1d = self.analyzer.get_regime("1d")

            # Diagnostic logging for every 4h candle
            n_buy, n_sell = self._get_directional_bias(regime_1d)
            lowest_buy = self._current_price * (_ONE - spacing * Decimal(str(n_buy)))
            highest_sell = self._current_price * (_ONE + spacing * Decimal(str(n_sell)))
            self.logger.info(
                "strategy_tick",
                strategy=self.get_name(),
                bot_id=self.bot_id,
                pair=self.pair,
                timeframe="4h",
                close=str(self._current_price),
                signal="HOLD",
                reason="grid_evaluation",
                metadata={
                    "atr_4h": float(atr),
                    "spacing_pct": float(spacing * _HUNDRED),
                    "regime_1d": regime_1d,
                    "regime_1w": regime_1w,
                    "n_buy": n_buy,
                    "n_sell": n_sell,
                    "lowest_buy_level": float(lowest_buy),
                    "highest_sell_level": float(highest_sell),
                    "grid_initialized": self._grid_initialized,
                },
            )

            # Initialize grid on first 4h candle
            if not self._grid_initialized:
                levels = self._build_grid(self._current_price, spacing, regime_1d)
                self._last_recalc = now
                if not self._skip_db_sync:
                    for level in levels:
                        await self._emit_grid_signal(level)
                return

            # Periodic recalculation
            if self._last_recalc is None or now >= self._last_recalc + timedelta(
                hours=self.recalc_hours
            ):
                await self._recalculate_grid(self._current_price, spacing, regime_1d, now)

        except Exception as e:
            self.logger.error(
                "grid_atr_ohlc_error",
                error=str(e),
                error_type=type(e).__name__,
                exc_info=e,
            )

    # ------------------------------------------------------------------
    # Grid recalculation
    # ------------------------------------------------------------------

    async def _recalculate_grid(
        self,
        current_price: Decimal,
        spacing: Decimal,
        regime_1d: str | None,
        now: datetime,
    ) -> None:
        """Recalculate grid around new center, preserving open positions.

        Open positions keep their sell targets. Only pending orders
        are cancelled and rebuilt.
        """
        old_center = self._grid_center
        old_spacing = self._grid_spacing

        cancelled = sum(1 for o in self._grid_levels.values() if o.status == "pending")

        # Rebuild grid
        levels = self._build_grid(current_price, spacing, regime_1d)
        self._last_recalc = now

        # Avoid duplicate sell levels at existing position targets
        existing_sell_targets = {pos.sell_level for pos in self._grid_positions}

        if not self._skip_db_sync:
            for level in levels:
                if level.side == "sell" and level.price in existing_sell_targets:
                    continue
                await self._emit_grid_signal(level)

        self.logger.info(
            "grid_atr_recalculated",
            old_center=float(old_center) if old_center else None,
            new_center=float(current_price),
            old_spacing_pct=float(old_spacing * _HUNDRED) if old_spacing else None,
            new_spacing_pct=float(spacing * _HUNDRED),
            cancelled=cancelled,
            new_levels=len(levels),
            regime_1d=regime_1d,
        )

    # ------------------------------------------------------------------
    # Signal emission
    # ------------------------------------------------------------------

    async def _emit_grid_signal(self, level: GridATRLevel) -> None:
        """Emit a TRADE_SIGNAL for a grid level (limit order)."""
        if self._current_price is None or self._current_timestamp is None:
            return

        spacing_pct = float(self._grid_spacing * _HUNDRED) if self._grid_spacing else 0.0

        signal_type = SignalType.BUY if level.side == "buy" else SignalType.SELL
        signal = TradingSignal(
            signal_type=signal_type,
            pair=self.pair,
            price=self._current_price,
            confidence=0.8,
            reason=(
                f"GRID ATR {level.side.upper()} at {float(level.price):.1f}"
                f" (spacing={spacing_pct:.2f}%)"
            ),
            strategy=self.bot_id,
            timestamp=self._current_timestamp,
            metadata={
                "order_type": "limit",
                "limit_price": float(level.price),
                "order_size_usdc": float(self.order_size_usdc),
                "max_allocation_pct": float(self.max_allocation_pct),
                "position_size_multiplier": self._position_size_multiplier,
                "grid_level": float(level.price),
                "grid_spacing_pct": spacing_pct,
                "reference_price": float(self._current_price),
            },
        )

        await self.event_bus.publish(
            EventType.TRADE_SIGNAL,
            {"signal": signal, "strategy": self.get_name()},
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
        """Handle trade fill — place paired opposite order.

        BUY filled  → open position, place SELL one spacing up.
        SELL filled → close position, place BUY one spacing down, record profit.
        """
        now = self._current_timestamp or datetime.now(UTC)
        spacing = self._grid_spacing or self.min_spacing_pct

        if side == "buy":
            pid = self._next_position_id
            self._next_position_id += 1

            sell_level = price * (_ONE + spacing)
            sell_level = sell_level.quantize(Decimal("0.1"))

            # Ensure profitability (covers 2× round-trip fees ~ 0.64%)
            min_profitable = price * Decimal("1.0064")
            if sell_level < min_profitable:
                sell_level = min_profitable.quantize(Decimal("0.1"))

            pos = GridATRPosition(
                position_id=pid,
                entry_price=price,
                entry_time=now,
                amount_btc=amount,
                amount_usdc=amount * price,
                sell_level=sell_level,
            )
            self._grid_positions.append(pos)

            # Place paired SELL
            sell_order = GridATRLevel(
                price=sell_level,
                side="sell",
                status="pending",
                amount_usdc=pos.amount_usdc,
            )
            self._grid_levels[f"sell_{sell_level}"] = sell_order

            if not self._skip_db_sync:
                await self._emit_grid_signal(sell_order)

            self.logger.info(
                "grid_atr_buy_filled",
                price=float(price),
                amount_btc=float(amount),
                sell_target=float(sell_level),
                position_id=pid,
                spacing_pct=float(spacing * _HUNDRED),
            )

        elif side == "sell":
            buy_level = price * (_ONE - spacing)
            buy_level = buy_level.quantize(Decimal("0.1"))

            # Find and close matching position
            matched = None
            for i, pos in enumerate(self._grid_positions):
                if abs(pos.sell_level - price) < Decimal("1"):
                    matched = self._grid_positions.pop(i)
                    break

            if matched:
                profit = (price - matched.entry_price) * matched.amount_btc - fee
                self._total_grid_profit += profit
                self._completed_pairs += 1

                self.logger.info(
                    "grid_atr_pair_completed",
                    buy_price=float(matched.entry_price),
                    sell_price=float(price),
                    profit=float(profit),
                    total_pairs=self._completed_pairs,
                    total_profit=float(self._total_grid_profit),
                )

            # Place paired BUY
            buy_order = GridATRLevel(
                price=buy_level,
                side="buy",
                status="pending",
                amount_usdc=self.order_size_usdc,
            )
            self._grid_levels[f"buy_{buy_level}"] = buy_order

            if not self._skip_db_sync:
                await self._emit_grid_signal(buy_order)

            self.logger.info(
                "grid_atr_sell_filled",
                price=float(price),
                buy_target=float(buy_level),
            )

    # ------------------------------------------------------------------
    # Backtest compatibility
    # ------------------------------------------------------------------

    @property
    def open_positions(self) -> list[GridATRPosition]:
        """Return list of open grid positions."""
        return list(self._grid_positions)

    @property
    def open_positions_count(self) -> int:
        """Return number of open grid positions."""
        return len(self._grid_positions)

    @property
    def grid_profit(self) -> Decimal:
        """Return total grid profit from completed pairs."""
        return self._total_grid_profit

    # ------------------------------------------------------------------
    # Info
    # ------------------------------------------------------------------

    def get_name(self) -> str:
        """Return strategy name."""
        return "grok_grid_atr_adaptive_v4"

    def get_config(self) -> dict[str, Any]:
        """Return strategy configuration."""
        return {
            "name": self.get_name(),
            "bot_id": self.bot_id,
            "pair": self.pair,
            "grid_levels": self.grid_levels,
            "min_spacing_pct": float(self.min_spacing_pct),
            "max_spacing_pct": float(self.max_spacing_pct),
            "atr_period": self.atr_period,
            "atr_multiplier": float(self.atr_multiplier),
            "recalc_hours": self.recalc_hours,
            "order_size_usdc": float(self.order_size_usdc),
            "max_allocation_pct": float(self.max_allocation_pct),
            "bias_1d": float(self.bias_1d),
            "pause_1w_strong_bear": self.pause_1w_strong_bear,
            "grid_center": float(self._grid_center) if self._grid_center else None,
            "grid_spacing_pct": (
                float(self._grid_spacing * _HUNDRED) if self._grid_spacing else None
            ),
            "open_positions": len(self._grid_positions),
            "completed_pairs": self._completed_pairs,
            "total_grid_profit": float(self._total_grid_profit),
            "paused": self._paused,
        }
