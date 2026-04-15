"""Gemini Global Risk Manager — overlay module for all strategies.

This module is NOT a BaseStrategy. It sits between strategies and execution,
applying three mandatory rules to every signal:

1. **1% Rule**: Position size calculated so max loss at SL ≤ 1% of total capital.
2. **Systematic ATR Stop-Loss**: SL = entry - multiplier × ATR (default 3×).
3. **Crash Protector**: If price drops ≥ 7% in 30 min (1m/5m candles),
   close 50% of long positions + suspend new entries for 2h.

Usage:
    The MultiStrategyRouter instantiates this module and calls:
    - update_price() on every 1m candle (for crash detection)
    - process_signal() on every strategy signal before emission
    - generate_crash_sells() when crash is detected
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import TYPE_CHECKING, Any

from krakenbot.core.logger import get_logger
from krakenbot.models.base import SignalType
from krakenbot.strategies.base import TradingSignal

if TYPE_CHECKING:
    from krakenbot.indicators.multi_timeframe import MultiTimeframeAnalyzer

logger = get_logger(__name__)

_ZERO = Decimal("0")
_ONE = Decimal("1")
_HUNDRED = Decimal("100")


@dataclass
class PriceSnapshot:
    """A timestamped price for crash detection."""

    price: Decimal
    timestamp: datetime


class GeminiGlobalRiskManager:
    """Global risk overlay applied to all strategy signals.

    This is NOT a strategy — it's a risk filter that the MultiStrategyRouter
    calls on every signal before publishing to the ExecutionEngine.

    Attributes:
        atr_sl_multiplier: ATR multiplier for stop-loss calculation.
        risk_per_trade_pct: Max capital risk per trade (default 1%).
        crash_threshold_pct: Price drop % triggering crash protector.
        crash_window_min: Rolling window in minutes for crash detection.
        crash_close_pct: Fraction of long positions to close on crash.
        crash_suspend_hours: Hours to suspend new entries after crash.
    """

    def __init__(
        self,
        config: dict[str, Any] | None = None,
    ) -> None:
        """Initialize risk manager with configurable parameters.

        Args:
            config: Risk configuration dict from strategies.yaml 'risk' section.
                    Keys: atr_sl_multiplier, risk_per_trade_pct,
                          crash_threshold_pct, crash_window_min,
                          crash_close_pct, crash_suspend_hours.
        """
        cfg = config or {}

        # Rule 1: Position sizing
        self.risk_per_trade_pct = Decimal(str(cfg.get("risk_per_trade_pct", 1.0)))

        # Rule 2: ATR stop-loss
        self.atr_sl_multiplier = Decimal(str(cfg.get("atr_sl_multiplier", 3.0)))
        self.atr_sl_timeframe: str = cfg.get("atr_sl_timeframe", "4h")
        self.atr_sl_period: int = cfg.get("atr_sl_period", 14)

        # Rule 3: Crash protector
        self.crash_threshold_pct = Decimal(str(cfg.get("crash_threshold_pct", 7.0)))
        self.crash_window_min: int = cfg.get("crash_window_min", 30)
        self.crash_close_pct = Decimal(str(cfg.get("crash_close_pct", 0.5)))
        self.crash_suspend_hours: int = cfg.get("crash_suspend_hours", 2)

        # Internal state for crash detection
        # Rolling window of 1m close prices (last 30 min = 30 entries)
        self._price_history: deque[PriceSnapshot] = deque(maxlen=60)
        self._suspended_until: datetime | None = None
        self._crash_active: bool = False

        logger.info(
            "gemini_risk_manager_initialized",
            risk_per_trade_pct=float(self.risk_per_trade_pct),
            atr_sl_multiplier=float(self.atr_sl_multiplier),
            crash_threshold_pct=float(self.crash_threshold_pct),
            crash_window_min=self.crash_window_min,
            crash_suspend_hours=self.crash_suspend_hours,
        )

    # ------------------------------------------------------------------
    # Rule 1: Position Sizing (1% Rule)
    # ------------------------------------------------------------------

    def calculate_position_size(
        self,
        capital: Decimal,
        entry_price: Decimal,
        stop_loss_price: Decimal,
    ) -> Decimal:
        """Calculate position size so max loss at SL ≤ risk_per_trade_pct of capital.

        Formula: size = (capital × risk%) / |entry - SL|

        Args:
            capital: Total portfolio value in quote currency (USDC).
            entry_price: Expected entry price.
            stop_loss_price: Stop-loss price level.

        Returns:
            Position size in base currency (BTC), or 0 if invalid.
        """
        risk_per_unit = abs(entry_price - stop_loss_price)
        if risk_per_unit == _ZERO or capital <= _ZERO or entry_price <= _ZERO:
            return _ZERO

        max_loss = capital * self.risk_per_trade_pct / _HUNDRED
        size_base = max_loss / risk_per_unit

        logger.debug(
            "position_size_calculated",
            capital=float(capital),
            entry=float(entry_price),
            sl=float(stop_loss_price),
            risk_per_unit=float(risk_per_unit),
            max_loss=float(max_loss),
            size_btc=float(size_base),
        )

        return size_base

    # ------------------------------------------------------------------
    # Rule 2: Systematic ATR Stop-Loss
    # ------------------------------------------------------------------

    def calculate_stop_loss(
        self,
        entry_price: Decimal,
        atr: Decimal,
        multiplier: Decimal | None = None,
    ) -> Decimal:
        """Calculate stop-loss price using ATR.

        SL = entry_price - multiplier × ATR (for long positions).

        Args:
            entry_price: Entry or current price.
            atr: ATR value for the relevant timeframe.
            multiplier: ATR multiplier (defaults to self.atr_sl_multiplier).

        Returns:
            Stop-loss price level.
        """
        mult = multiplier if multiplier is not None else self.atr_sl_multiplier
        sl = entry_price - mult * atr
        # SL cannot be negative
        return max(sl, _ZERO)

    # ------------------------------------------------------------------
    # Rule 3: Crash Protector
    # ------------------------------------------------------------------

    def update_price(self, price: Decimal, timestamp: datetime) -> None:
        """Record a price snapshot for crash detection.

        Should be called on every 1m candle close by the router.

        Args:
            price: Close price.
            timestamp: Candle timestamp (UTC).
        """
        self._price_history.append(PriceSnapshot(price=price, timestamp=timestamp))

    def check_crash_protector(self, now: datetime | None = None) -> bool:
        """Check if a crash event is currently active.

        A crash is detected when the price drops ≥ crash_threshold_pct
        within the crash_window_min rolling window.

        Args:
            now: Current timestamp (defaults to utcnow).

        Returns:
            True if crash is detected and protector is active.
        """
        now = now or datetime.now(UTC)

        # Check if we're in a suspension period from a previous crash
        if self._suspended_until is not None and now < self._suspended_until:
            return True

        if len(self._price_history) < 2:
            return False

        # Find the highest price within the window
        window_start = now - timedelta(minutes=self.crash_window_min)
        window_prices = [s for s in self._price_history if s.timestamp >= window_start]

        if len(window_prices) < 2:
            return False

        max_price = max(s.price for s in window_prices)
        current_price = window_prices[-1].price

        if max_price <= _ZERO:
            return False

        drop_pct = (max_price - current_price) / max_price * _HUNDRED

        if drop_pct >= self.crash_threshold_pct:
            if not self._crash_active:
                logger.warning(
                    "crash_protector_triggered",
                    drop_pct=float(drop_pct),
                    max_price=float(max_price),
                    current_price=float(current_price),
                    threshold_pct=float(self.crash_threshold_pct),
                )
                self._crash_active = True
                self._suspended_until = now + timedelta(hours=self.crash_suspend_hours)
            return True

        # Reset crash state if drop has recovered
        if self._crash_active and drop_pct < self.crash_threshold_pct / Decimal("2"):
            self._crash_active = False
            logger.info("crash_protector_cleared", drop_pct=float(drop_pct))

        return False

    @property
    def is_suspended(self) -> bool:
        """Check if new entries are suspended (crash protector active)."""
        if self._suspended_until is None:
            return False
        return datetime.now(UTC) < self._suspended_until

    def generate_crash_sells(
        self,
        open_positions: list[dict[str, Any]],
        current_price: Decimal,
        pair: str = "BTC/USDC",
    ) -> list[TradingSignal]:
        """Generate SELL signals to close a fraction of long positions.

        Called by the router when crash protector triggers.
        Closes crash_close_pct (default 50%) of open long positions,
        prioritizing the largest ones.

        Args:
            open_positions: List of position dicts with keys:
                            bot_id, position_id, amount_btc, entry_price.
            current_price: Current market price.
            pair: Trading pair.

        Returns:
            List of SELL TradingSignals (market orders).
        """
        if not open_positions:
            return []

        # Sort by position value descending (close biggest first)
        sorted_positions = sorted(
            open_positions,
            key=lambda p: Decimal(str(p.get("amount_btc", 0))) * current_price,
            reverse=True,
        )

        # Close crash_close_pct of positions (round up)
        n_to_close = max(1, int(len(sorted_positions) * float(self.crash_close_pct) + 0.5))
        positions_to_close = sorted_positions[:n_to_close]

        now = datetime.now(UTC)
        signals: list[TradingSignal] = []

        for pos in positions_to_close:
            signal = TradingSignal(
                signal_type=SignalType.SELL,
                pair=pair,
                price=current_price,
                confidence=1.0,
                reason=f"CRASH PROTECTOR: closing position {pos.get('position_id')}",
                strategy=str(pos.get("bot_id", "crash_protector")),
                timestamp=now,
                metadata={
                    "order_type": "market",
                    "position_id": pos.get("position_id"),
                    "crash_sell": True,
                    "position_size_multiplier": 1.0,
                },
            )
            signals.append(signal)

        logger.warning(
            "crash_sells_generated",
            total_positions=len(open_positions),
            positions_to_close=n_to_close,
            signals_count=len(signals),
        )

        return signals

    # ------------------------------------------------------------------
    # Main pipeline: process a strategy signal through all 3 rules
    # ------------------------------------------------------------------

    def process_signal(
        self,
        signal: TradingSignal,
        capital: Decimal,
        analyzer: MultiTimeframeAnalyzer,
    ) -> TradingSignal | None:
        """Apply all risk rules to a strategy signal.

        Pipeline:
        1. If crash protector is active and signal is BUY → reject
        2. If BUY signal: calculate ATR-based SL, then 1% position sizing
        3. SELL signals pass through (always allow exits)

        Args:
            signal: Original signal from a strategy.
            capital: Total portfolio value in quote currency.
            analyzer: Shared multi-timeframe analyzer for ATR queries.

        Returns:
            Modified signal with SL and position size in metadata,
            or None if signal is rejected.
        """
        # SELL signals always pass through (exits must not be blocked)
        if signal.is_sell:
            return signal

        # HOLD signals pass through
        if not signal.should_trade:
            return signal

        # BUY signals: apply full pipeline
        now = datetime.now(UTC)

        # Rule 3: Crash protector blocks new entries
        if self.check_crash_protector(now):
            logger.info(
                "signal_blocked_crash_protector",
                strategy=signal.strategy,
                reason=signal.reason,
                suspended_until=self._suspended_until.isoformat()
                if self._suspended_until
                else None,
            )
            return None

        # Rule 2: Calculate ATR-based stop-loss
        atr = analyzer.get_atr(self.atr_sl_period, self.atr_sl_timeframe)
        if atr is None or atr <= _ZERO:
            logger.warning(
                "signal_blocked_no_atr",
                strategy=signal.strategy,
                tf=self.atr_sl_timeframe,
                period=self.atr_sl_period,
            )
            return None

        entry_price = signal.price
        stop_loss_price = self.calculate_stop_loss(entry_price, atr)

        # Rule 1: Position sizing based on 1% risk
        position_size_btc = self.calculate_position_size(capital, entry_price, stop_loss_price)

        if position_size_btc <= _ZERO:
            logger.warning(
                "signal_blocked_zero_size",
                strategy=signal.strategy,
                capital=float(capital),
                entry=float(entry_price),
                sl=float(stop_loss_price),
            )
            return None

        # Inject risk parameters into signal metadata
        metadata = dict(signal.metadata)
        metadata["risk_stop_loss"] = float(stop_loss_price)
        metadata["risk_atr"] = float(atr)
        metadata["risk_atr_multiplier"] = float(self.atr_sl_multiplier)
        metadata["risk_position_size_btc"] = float(position_size_btc)
        metadata["risk_max_loss_pct"] = float(self.risk_per_trade_pct)

        # Override position_size_multiplier if signal didn't set one,
        # or if the 1% rule gives a smaller size
        if entry_price > _ZERO:
            position_value_usdc = position_size_btc * entry_price
            if capital > _ZERO:
                risk_multiplier = float(position_value_usdc / capital)
                current_mult = metadata.get("position_size_multiplier", 1.0)
                # Use the more conservative (smaller) multiplier
                metadata["position_size_multiplier"] = min(current_mult, risk_multiplier)

        # Build modified signal
        modified = TradingSignal(
            signal_type=signal.signal_type,
            pair=signal.pair,
            price=signal.price,
            confidence=signal.confidence,
            reason=signal.reason,
            strategy=signal.strategy,
            timestamp=signal.timestamp,
            metadata=metadata,
        )

        logger.info(
            "signal_risk_processed",
            strategy=signal.strategy,
            entry=float(entry_price),
            sl=float(stop_loss_price),
            size_btc=float(position_size_btc),
            atr=float(atr),
        )

        return modified

    def check_strategy_budget(
        self,
        strategy_name: str,
        order_size_usdc: Decimal,
        current_exposure_usdc: Decimal,
        total_capital: Decimal,
        max_allocation_pct: Decimal,
    ) -> bool:
        """Validate that a strategy's proposed order stays within its budget.

        Each strategy has a max_allocation_pct of total capital. This method
        checks that the current exposure + proposed order doesn't exceed it.

        Args:
            strategy_name: Strategy bot_id for logging.
            order_size_usdc: Proposed order amount in USDC.
            current_exposure_usdc: Strategy's current open exposure in USDC.
            total_capital: Total portfolio value in USDC.
            max_allocation_pct: Max % of total capital for this strategy.

        Returns:
            True if within budget, False if over-allocated.
        """
        if total_capital <= _ZERO:
            return False

        budget = total_capital * max_allocation_pct / _HUNDRED
        new_exposure = current_exposure_usdc + order_size_usdc

        if new_exposure > budget:
            logger.info(
                "signal_blocked_budget_exceeded",
                strategy=strategy_name,
                order_usdc=float(order_size_usdc),
                current_exposure=float(current_exposure_usdc),
                budget=float(budget),
                max_allocation_pct=float(max_allocation_pct),
            )
            return False

        return True

    def get_config(self) -> dict[str, Any]:
        """Return current risk configuration for logging/display."""
        return {
            "risk_per_trade_pct": float(self.risk_per_trade_pct),
            "atr_sl_multiplier": float(self.atr_sl_multiplier),
            "atr_sl_timeframe": self.atr_sl_timeframe,
            "atr_sl_period": self.atr_sl_period,
            "crash_threshold_pct": float(self.crash_threshold_pct),
            "crash_window_min": self.crash_window_min,
            "crash_close_pct": float(self.crash_close_pct),
            "crash_suspend_hours": self.crash_suspend_hours,
            "is_suspended": self.is_suspended,
        }
