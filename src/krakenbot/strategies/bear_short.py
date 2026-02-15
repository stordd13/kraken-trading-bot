"""Bear short strategy: profit from bearish markets via margin shorts.

Entry conditions (ALL required):
    1. MarketRegime is BEAR or STRONG_BEAR
    2. RSI 15m > rsi_15m_min_entry (overbought in bear = local high)
    3. Price > EMA20 1h (rally into resistance)
    4. Volume ratio 5m >= min_volume_ratio
    5. Max positions not exceeded
    6. One short per candle

Exit conditions (priority order):
    1. Stop-loss: price moves UP stop_loss_pct from entry -> market BUY
    2. Regime change: NEUTRAL/BULL/STRONG_BULL -> immediate market BUY
    3. Profit target: 2% (BEAR) or 3% (STRONG_BEAR) -> market BUY
    4. Trailing stop: after min_profit_for_trailing_pct, trail from lowest
    5. Timeout: max_holding_minutes -> market BUY

Signal flow:
    Open short: SignalType.SELL with metadata mode="margin"
    Close short: SignalType.BUY with metadata mode="margin"

P&L: (entry_price - current_price) / entry_price * 100 (inverted from long)
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from typing import TYPE_CHECKING, Any

from krakenbot.indicators.multi_timeframe import MarketRegime
from krakenbot.models.base import SignalType
from krakenbot.strategies.base import BaseStrategy, TradingSignal

if TYPE_CHECKING:
    from krakenbot.config.settings import Settings
    from krakenbot.core.database import DatabaseManager
    from krakenbot.core.event_bus import EventBus
    from krakenbot.indicators.multi_timeframe import MultiTimeframeAnalyzer


@dataclass
class ShortPosition:
    """Position tracking for short trades."""

    entry_price: Decimal
    entry_time: datetime
    amount_usdc: Decimal
    position_id: int
    reference_price: Decimal
    lowest_price: Decimal  # For trailing stop (inverse of highest_price)


class BearShortStrategy(BaseStrategy):
    """Bear market short strategy using margin trading.

    Enters short positions when regime is BEAR/STRONG_BEAR and RSI 15m
    indicates a temporary overbought condition (rally in a bear = short entry).
    Exits on regime change, profit target, stop-loss, trailing, or timeout.
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
        """Initialize BearShortStrategy.

        Args:
            settings: Application settings.
            event_bus: Event bus.
            db_manager: Database manager.
            bot_id: Unique bot identifier.
            strategy_params: Custom params from strategies.yaml.
            analyzer: Shared MultiTimeframeAnalyzer instance.
        """
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

        # Strategy params from strategies.yaml
        self.profit_target_bear_pct = Decimal(str(params.get("profit_target_bear_pct", 2.0)))
        self.profit_target_strong_bear_pct = Decimal(
            str(params.get("profit_target_strong_bear_pct", 3.0))
        )
        self.stop_loss_pct = Decimal(str(params.get("stop_loss_pct", 2.0)))
        self.trailing_stop_pct = Decimal(str(params.get("trailing_stop_pct", 1.0)))
        self.min_profit_for_trailing_pct = Decimal(
            str(params.get("min_profit_for_trailing_pct", 1.5))
        )
        self.max_holding_minutes = int(params.get("max_holding_hours", 48)) * 60
        self.rsi_15m_min_entry = float(params.get("rsi_15m_min_entry", 60.0))
        self.min_volume_ratio = float(params.get("min_volume_ratio", 1.0))
        self.leverage = int(params.get("leverage", 2))

        # Budget params
        budget = None
        if settings.multi_strategy.enabled:
            for s in settings.multi_strategy.strategies:
                if s.bot_id == bot_id:
                    budget = s.budget
                    break
        self.max_open_positions = budget.max_open_positions if budget else 2
        self.position_size_multiplier = budget.position_size_multiplier if budget else 1.0

        # Position tracking
        self._open_positions: list[ShortPosition] = []
        self._next_position_id: int = 1
        self._current_price: Decimal | None = None
        self._current_timestamp: datetime | None = None
        self._shorted_this_candle: bool = False
        self._skip_db_sync: bool = False

        # Regimes for entry/exit
        self._entry_regimes = {MarketRegime.BEAR, MarketRegime.STRONG_BEAR}
        self._exit_regimes = {
            MarketRegime.NEUTRAL,
            MarketRegime.BULL,
            MarketRegime.STRONG_BULL,
        }

        self.logger.debug(
            "bear_short_strategy_initialized",
            bot_id=self.bot_id,
            profit_target_bear_pct=float(self.profit_target_bear_pct),
            profit_target_strong_bear_pct=float(self.profit_target_strong_bear_pct),
            stop_loss_pct=float(self.stop_loss_pct),
            trailing_stop_pct=float(self.trailing_stop_pct),
            leverage=self.leverage,
            max_open_positions=self.max_open_positions,
        )

    async def on_tick(self, tick_data: dict[str, Any]) -> None:
        """Update current price from tick data."""
        if tick_data.get("pair") != self.pair:
            return
        price = Decimal(str(tick_data["price"]))
        self._current_price = price
        # Update lowest price for trailing stops
        for pos in self._open_positions:
            if price < pos.lowest_price:
                pos.lowest_price = price

    async def on_ohlc(self, ohlc_data: dict[str, Any]) -> None:
        """Process OHLC data, update analyzer, track lowest prices."""
        if ohlc_data.get("pair") != self.pair:
            return

        close_price = Decimal(str(ohlc_data["close"]))
        interval = ohlc_data.get("interval", 5)
        self._current_price = close_price

        # Update shared analyzer for all timeframes
        if self.analyzer is not None:
            self.analyzer.update(ohlc_data, interval)

        # Update lowest price from candle low
        candle_low = Decimal(str(ohlc_data.get("low", close_price)))
        for pos in self._open_positions:
            if candle_low < pos.lowest_price:
                pos.lowest_price = candle_low

        # Only trade on trigger timeframe (5min)
        trigger_tf = self.settings.multi_timeframe.trigger_timeframe
        if interval != trigger_tf:
            return
        if not ohlc_data.get("is_complete", False):
            return

        self._shorted_this_candle = False
        self._current_timestamp = self._parse_timestamp(ohlc_data)

    async def generate_signal(self) -> TradingSignal | None:
        """Generate short entry or exit signal."""
        if not self._current_price:
            return None

        current_time = self._current_timestamp or datetime.now(UTC)
        analysis = self.analyzer.analyze() if self.analyzer else None
        if analysis is None:
            return None

        current_regime = analysis.regime

        # === EXIT LOGIC: check each short position ===
        for pos in self._open_positions:
            # Short P&L: profit when price drops
            profit_pct = ((pos.entry_price - self._current_price) / pos.entry_price) * Decimal(
                "100"
            )
            holding_minutes = (current_time - pos.entry_time).total_seconds() / 60
            amount_btc = pos.amount_usdc / pos.entry_price

            # Determine take-profit based on regime
            take_profit_pct = (
                self.profit_target_strong_bear_pct
                if current_regime == MarketRegime.STRONG_BEAR
                else self.profit_target_bear_pct
            )

            # 1. Stop-loss: price moved UP against us
            if profit_pct <= -self.stop_loss_pct:
                return self._close_signal(
                    pos,
                    amount_btc,
                    profit_pct,
                    holding_minutes,
                    current_time,
                    reason="stop_loss",
                    order_type="market",
                    confidence=1.0,
                    extra_reason=(
                        f"SHORT STOP-LOSS: price up {float(-profit_pct):.2f}% "
                        f">= {float(self.stop_loss_pct):.1f}%"
                    ),
                )

            # 2. Regime change to bullish -> immediate close
            if current_regime in self._exit_regimes:
                return self._close_signal(
                    pos,
                    amount_btc,
                    profit_pct,
                    holding_minutes,
                    current_time,
                    reason="regime_change",
                    order_type="market",
                    confidence=0.95,
                    extra_reason=(f"Regime changed to {current_regime.value} -> close short"),
                )

            # 3. Take profit
            if profit_pct >= take_profit_pct:
                return self._close_signal(
                    pos,
                    amount_btc,
                    profit_pct,
                    holding_minutes,
                    current_time,
                    reason="profit_target",
                    order_type="market",
                    confidence=0.9,
                    extra_reason=(
                        f"Short profit target: {float(profit_pct):.2f}% "
                        f">= {float(take_profit_pct):.1f}%"
                    ),
                )

            # 4. Trailing stop (after reaching min profit)
            profit_at_low = ((pos.entry_price - pos.lowest_price) / pos.entry_price) * Decimal(
                "100"
            )
            if profit_at_low >= self.min_profit_for_trailing_pct:
                rise_from_low = (
                    (self._current_price - pos.lowest_price) / pos.lowest_price
                ) * Decimal("100")
                if rise_from_low >= self.trailing_stop_pct:
                    return self._close_signal(
                        pos,
                        amount_btc,
                        profit_pct,
                        holding_minutes,
                        current_time,
                        reason="trailing_stop",
                        order_type="market",
                        confidence=0.95,
                        extra_reason=(
                            f"Trailing stop: +{float(rise_from_low):.2f}% from low "
                            f"{float(pos.lowest_price):.2f}"
                        ),
                    )

            # 5. Timeout
            if holding_minutes >= self.max_holding_minutes:
                return self._close_signal(
                    pos,
                    amount_btc,
                    profit_pct,
                    holding_minutes,
                    current_time,
                    reason="timeout",
                    order_type="market",
                    confidence=0.7,
                    extra_reason=(
                        f"TIMEOUT: {holding_minutes:.0f}min >= {self.max_holding_minutes}min"
                    ),
                )

        # === ENTRY LOGIC: open new short ===
        if len(self._open_positions) >= self.max_open_positions:
            return None
        if self._shorted_this_candle:
            return None
        if current_regime not in self._entry_regimes:
            return None

        # RSI 15m must be overbought (> threshold)
        rsi_15m = analysis.rsi_15m
        if rsi_15m is None or rsi_15m <= self.rsi_15m_min_entry:
            return None

        # Price must be above EMA20 1h (rally into resistance)
        ema_fast_1h = analysis.metadata.get("ema_fast_1h")
        if ema_fast_1h is not None and self._current_price <= Decimal(str(ema_fast_1h)):
            return None

        # Volume filter
        if analysis.volume_ratio_5m < self.min_volume_ratio:
            return None

        self._shorted_this_candle = True

        return TradingSignal(
            signal_type=SignalType.SELL,  # SELL to open short
            pair=self.pair,
            price=self._current_price,
            confidence=0.85,
            reason=(
                f"SHORT entry: regime={current_regime.value}, "
                f"RSI15m={rsi_15m:.1f}>{self.rsi_15m_min_entry:.0f}, price>EMA20"
            ),
            strategy=self.bot_id,
            timestamp=current_time,
            metadata={
                "mode": "margin",
                "is_short_open": True,
                "reference_price": float(self._current_price),
                "regime": current_regime.value,
                "rsi_15m": rsi_15m,
                "leverage": self.leverage,
                "order_type": "market",
                "position_size_multiplier": self.position_size_multiplier,
            },
        )

    def _close_signal(
        self,
        pos: ShortPosition,
        amount_btc: Decimal,
        profit_pct: Decimal,
        holding_minutes: float,
        current_time: datetime,
        *,
        reason: str,
        order_type: str,
        confidence: float,
        extra_reason: str,
    ) -> TradingSignal:
        """Build a BUY signal to close a short position."""
        return TradingSignal(
            signal_type=SignalType.BUY,  # BUY to close short
            pair=self.pair,
            price=self._current_price or Decimal("0"),
            confidence=confidence,
            reason=f"Short #{pos.position_id}: {extra_reason}",
            strategy=self.bot_id,
            timestamp=current_time,
            metadata={
                "mode": "margin",
                "is_short_close": True,
                "position_id": pos.position_id,
                "amount_btc": float(amount_btc),
                "entry_price": float(pos.entry_price),
                "profit_pct": float(profit_pct),
                "holding_time_minutes": holding_minutes,
                "reason": reason,
                "order_type": order_type,
            },
        )

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
        """Track short positions after trade execution.

        For shorts: side=="sell" opens, side=="buy" closes.
        """
        if side == "sell":
            # Opening a short
            amount_usdc = amount * price
            pid = self._next_position_id
            self._next_position_id += 1
            self._open_positions.append(
                ShortPosition(
                    entry_price=price,
                    entry_time=datetime.now(UTC),
                    amount_usdc=amount_usdc,
                    position_id=pid,
                    reference_price=reference_price or price,
                    lowest_price=price,
                )
            )
            self.logger.info(
                "short_position_opened",
                position_id=pid,
                entry_price=float(price),
                bot_id=self.bot_id,
            )

        elif side == "buy":
            # Closing a short
            if position_id is None:
                return
            for i, pos in enumerate(self._open_positions):
                if pos.position_id == position_id:
                    closed = self._open_positions.pop(i)
                    pnl = (closed.entry_price - price) * (
                        closed.amount_usdc / closed.entry_price
                    ) - fee
                    self.logger.info(
                        "short_position_closed",
                        position_id=position_id,
                        pnl=float(pnl),
                        bot_id=self.bot_id,
                    )
                    break

    # Backtest compatibility methods

    def add_position(
        self,
        entry_price: Decimal,
        amount_usdc: Decimal,
        reference_price: Decimal | None = None,
        entry_time: datetime | None = None,
    ) -> int:
        """Add a short position (for backtest compatibility).

        Args:
            entry_price: Entry price of the short.
            amount_usdc: Position size in USDC.
            reference_price: Reference price that triggered entry.
            entry_time: Entry timestamp.

        Returns:
            Position ID.
        """
        pid = self._next_position_id
        self._next_position_id += 1
        self._open_positions.append(
            ShortPosition(
                entry_price=entry_price,
                entry_time=entry_time or datetime.now(UTC),
                amount_usdc=amount_usdc,
                position_id=pid,
                reference_price=reference_price or entry_price,
                lowest_price=entry_price,
            )
        )
        return pid

    def close_position(self, position_id: int) -> ShortPosition | None:
        """Close a short position by ID (for backtest compatibility).

        Args:
            position_id: ID of position to close.

        Returns:
            The closed position, or None.
        """
        for i, pos in enumerate(self._open_positions):
            if pos.position_id == position_id:
                return self._open_positions.pop(i)
        return None

    @property
    def open_positions(self) -> list[ShortPosition]:
        """Get list of open short positions."""
        return self._open_positions.copy()

    @property
    def open_positions_count(self) -> int:
        """Get number of open short positions."""
        return len(self._open_positions)

    @property
    def current_price(self) -> Decimal | None:
        """Get current market price."""
        return self._current_price

    def get_name(self) -> str:
        """Return strategy name."""
        return "bear_short"

    def get_config(self) -> dict[str, Any]:
        """Return strategy configuration."""
        return {
            "name": self.get_name(),
            "bot_id": self.bot_id,
            "profit_target_bear_pct": float(self.profit_target_bear_pct),
            "profit_target_strong_bear_pct": float(self.profit_target_strong_bear_pct),
            "stop_loss_pct": float(self.stop_loss_pct),
            "trailing_stop_pct": float(self.trailing_stop_pct),
            "min_profit_for_trailing_pct": float(self.min_profit_for_trailing_pct),
            "max_holding_minutes": self.max_holding_minutes,
            "max_open_positions": self.max_open_positions,
            "leverage": self.leverage,
        }

    def reset_state(self) -> None:
        """Reset internal state."""
        super().reset_state()
        self._open_positions.clear()
        self._current_price = None
        self._current_timestamp = None
        self._next_position_id = 1
        self._shorted_this_candle = False

    def _parse_timestamp(self, ohlc_data: dict[str, Any]) -> datetime:
        """Parse timestamp from OHLC data."""
        if "timestamp" not in ohlc_data:
            return datetime.now(UTC)

        ts = ohlc_data["timestamp"]
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
