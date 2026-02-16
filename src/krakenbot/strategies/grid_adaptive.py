"""Grid adaptive strategy with ATR-based dynamic range.

Like GridSpot but the grid range adjusts automatically to volatility
via ATR. No need for MarketRegime — ATR does the work.

ATR high (volatile) -> wide range -> wide spacing -> fewer but bigger trades
ATR low (calm) -> tight range -> tight spacing -> more but smaller trades

Range recalculates every N hours (not continuously, to avoid churning orders).

Params (from strategies.yaml):
    grid_levels: Number of grid levels (default 8)
    atr_multiplier: Range = ATR * multiplier per side (default 3.0)
    recalculate_hours: Recalculate range every N hours (default 4)
    order_amount_usdc: USDC per grid level (default 25)
    min_spacing_pct: Minimum spacing to avoid fees > profit (default 0.5)
    allow_short: Allow shorts when price exits grid top (default false, V1)
"""

from __future__ import annotations

from datetime import datetime, timedelta
from decimal import Decimal
from typing import TYPE_CHECKING, Any

from krakenbot.strategies.grid_spot import GridSpotStrategy

if TYPE_CHECKING:
    from krakenbot.config.settings import Settings
    from krakenbot.core.database import DatabaseManager
    from krakenbot.core.event_bus import EventBus


class GridAdaptiveStrategy(GridSpotStrategy):
    """Grid strategy with ATR-based adaptive range.

    Inherits from GridSpotStrategy and overrides range calculation
    to use ATR from the shared MultiTimeframeAnalyzer.
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
        """Initialize GridAdaptiveStrategy."""
        # Set adaptive defaults before calling super
        params = strategy_params or {}
        params.setdefault("grid_levels", 8)
        params.setdefault("order_amount_usdc", 25)

        super().__init__(
            settings,
            event_bus,
            db_manager,
            bot_id=bot_id,
            strategy_params=params,
            analyzer=analyzer,
        )

        # Adaptive-specific params
        self.atr_multiplier = Decimal(str(params.get("atr_multiplier", 3.0)))
        self.recalculate_hours = int(params.get("recalculate_hours", 4))
        self.min_spacing_pct = Decimal(str(params.get("min_spacing_pct", 0.5)))
        self.allow_short = bool(params.get("allow_short", False))

        # Recalculation tracking
        self._last_recalc_time: datetime | None = None
        self._current_atr: Decimal | None = None

        self.logger.debug(
            "grid_adaptive_initialized",
            bot_id=self.bot_id,
            atr_multiplier=float(self.atr_multiplier),
            recalculate_hours=self.recalculate_hours,
            min_spacing_pct=float(self.min_spacing_pct),
        )

    # ------------------------------------------------------------------
    # Name override
    # ------------------------------------------------------------------

    def get_name(self) -> str:
        """Return strategy name."""
        return "grid_adaptive"

    def get_config(self) -> dict[str, Any]:
        """Return strategy configuration."""
        config = super().get_config()
        config.update(
            {
                "atr_multiplier": float(self.atr_multiplier),
                "recalculate_hours": self.recalculate_hours,
                "min_spacing_pct": float(self.min_spacing_pct),
                "allow_short": self.allow_short,
                "current_atr": float(self._current_atr) if self._current_atr else None,
            }
        )
        return config

    # ------------------------------------------------------------------
    # OHLC handling: feed analyzer + check recalculation
    # ------------------------------------------------------------------

    async def on_ohlc(self, ohlc_data: dict[str, Any]) -> None:
        """Handle OHLC: update price + feed analyzer for ATR."""
        # Update price state (parent)
        await super().on_ohlc(ohlc_data)

        # Feed the analyzer with ALL intervals for ATR warmup
        if self.analyzer is not None:
            interval = ohlc_data.get("interval", 5)
            self.analyzer.update(ohlc_data, interval)

    async def _handle_ohlc(self, data: dict[str, Any]) -> None:
        """Override to add periodic recalculation check."""
        if not self._running:
            return

        try:
            await self.on_ohlc(data)

            if self._current_price is None:
                return

            # Try to get ATR from analyzer
            atr = self._get_atr()
            if atr is not None:
                self._current_atr = atr

            # Initialize grid on first price (using ATR range if available)
            if not self._grid_initialized:
                if self._current_atr is not None:
                    self._update_range_from_atr(self._current_price)
                orders = self.initialize_grid(self._current_price)
                self._last_recalc_time = self._current_timestamp
                if not self._skip_db_sync:
                    for order in orders:
                        await self._emit_grid_signal(order)
                return

            # Check periodic recalculation
            if self._should_recalculate():
                await self._recalculate_grid()

            # Check rebalance (from parent)
            if self._should_rebalance(self._current_price):
                await self._rebalance_grid(self._current_price)

        except Exception as e:
            self.logger.error(
                "grid_adaptive_ohlc_error",
                error=str(e),
                error_type=type(e).__name__,
                exc_info=e,
            )

    # ------------------------------------------------------------------
    # ATR-based range calculation
    # ------------------------------------------------------------------

    def _get_atr(self) -> Decimal | None:
        """Get ATR value from the shared analyzer."""
        if self.analyzer is None:
            return None

        analysis = self.analyzer.analyze()
        if analysis is None:
            return None

        return analysis.volatility_atr

    def _update_range_from_atr(self, current_price: Decimal) -> None:
        """Update grid range parameters based on current ATR.

        Computes range_size_pct and grid_spacing_pct from ATR value.
        """
        if self._current_atr is None or current_price <= 0:
            return

        # Range = ATR * multiplier per side -> total range = 2 * ATR * multiplier
        half_range = self._current_atr * self.atr_multiplier
        total_range_pct = (half_range * Decimal("2")) / current_price * Decimal("100")

        # Spacing = total range / grid levels
        spacing_pct = total_range_pct / Decimal(str(self.grid_levels))

        # Enforce minimum spacing
        if spacing_pct < self.min_spacing_pct:
            spacing_pct = self.min_spacing_pct
            total_range_pct = spacing_pct * Decimal(str(self.grid_levels))

        self.range_size_pct = total_range_pct
        self.grid_spacing_pct = spacing_pct

        self.logger.info(
            "grid_adaptive_range_updated",
            atr=float(self._current_atr),
            range_size_pct=float(total_range_pct),
            spacing_pct=float(spacing_pct),
            current_price=float(current_price),
        )

    # ------------------------------------------------------------------
    # Periodic recalculation
    # ------------------------------------------------------------------

    def _should_recalculate(self) -> bool:
        """Check if it's time to recalculate the grid range."""
        if self._last_recalc_time is None or self._current_timestamp is None:
            return False
        elapsed = self._current_timestamp - self._last_recalc_time
        return elapsed >= timedelta(hours=self.recalculate_hours)

    async def _recalculate_grid(self) -> None:
        """Recalculate grid with updated ATR range."""
        if self._current_price is None:
            return

        atr = self._get_atr()
        if atr is None:
            return

        self._current_atr = atr
        old_range = self.range_size_pct
        self._update_range_from_atr(self._current_price)

        # Only reinitialize if range changed significantly (>10%)
        if old_range > 0:
            change_pct = abs(self.range_size_pct - old_range) / old_range * Decimal("100")
            if change_pct < Decimal("10"):
                self._last_recalc_time = self._current_timestamp
                return

        self.logger.info(
            "grid_adaptive_recalculating",
            old_range_pct=float(old_range),
            new_range_pct=float(self.range_size_pct),
            atr=float(atr),
        )

        await self._rebalance_grid(self._current_price)
        self._last_recalc_time = self._current_timestamp
