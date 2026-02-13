"""Capitulation strategy: catch crash bounces.

Trades rarely (2-3x/month) with high conviction on extreme sell-offs.
Uses MultiTimeframeAnalyzer for RSI/volume data and tracks hourly closes
internally to detect statistical outlier drops.

Entry conditions (ALL 4 required):
    1. 24h price drop > 2 standard deviations of hourly changes
    2. RSI 1h < rsi_1h_threshold (default 20)
    3. Volume 5m > volume_spike_multiplier x 20-candle average (default 3.0)
    4. RSI 5m < rsi_5m_threshold (default 15)

Exit (priority order):
    - Trailing stop: price drops trailing_stop_pct from highest -> market
    - Take profit: profit >= max_profit_target_pct -> limit
    - Timeout: held > max_holding_minutes -> market

Params (from strategies.yaml + CapitulationSettings):
    rsi_1h_threshold, rsi_5m_threshold, volume_spike_multiplier,
    trailing_stop_pct, max_profit_target_pct, max_holding_minutes,
    cooldown_hours
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal
import math
from typing import TYPE_CHECKING, Any

from krakenbot.models.base import SignalType
from krakenbot.strategies.base import BaseStrategy, TradingSignal

if TYPE_CHECKING:
    from krakenbot.config.settings import Settings
    from krakenbot.core.database import DatabaseManager
    from krakenbot.core.event_bus import EventBus
    from krakenbot.indicators.multi_timeframe import MultiTimeframeAnalyzer


@dataclass
class CapitulationPosition:
    """Open position for capitulation strategy."""

    entry_price: Decimal
    entry_time: datetime
    amount_btc: Decimal
    amount_usdc: Decimal  # For backtest compatibility
    position_id: int
    highest_price: Decimal  # For trailing stop


class CapitulationStrategy(BaseStrategy):
    """Capitulation bounce strategy - trades extreme sell-offs.

    Detects statistical outlier drops (>2 sigma) combined with extreme
    oversold conditions (RSI) and volume spikes, then enters for a bounce.
    Uses tight trailing stop and profit target for exits.
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
        """Initialize CapitulationStrategy.

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

        # Capitulation params (from strategies.yaml, fallback to CapitulationSettings)
        cap = settings.capitulation
        self.rsi_1h_threshold = float(params.get("rsi_1h_threshold", cap.rsi_1h_threshold))
        self.rsi_5m_threshold = float(params.get("rsi_5m_threshold", cap.rsi_5m_threshold))
        self.volume_spike_multiplier = float(
            params.get("volume_spike_multiplier", cap.volume_spike_multiplier)
        )
        self.trailing_stop_pct = Decimal(
            str(params.get("trailing_stop_pct", cap.trailing_stop_pct))
        )
        self.max_profit_target_pct = Decimal(
            str(params.get("max_profit_target_pct", cap.max_profit_target_pct))
        )
        self.max_holding_minutes = int(params.get("max_holding_minutes", cap.max_holding_minutes))
        self.cooldown_hours = int(params.get("cooldown_hours", cap.cooldown_hours))

        # Budget params
        budget = None
        if settings.multi_strategy.enabled:
            for s in settings.multi_strategy.strategies:
                if s.bot_id == bot_id:
                    budget = s.budget
                    break
        self.max_open_positions = (
            budget.max_open_positions if budget else settings.risk.max_open_positions
        )
        self.position_size_multiplier = budget.position_size_multiplier if budget else 2.0

        # Position tracking
        self._open_positions: list[CapitulationPosition] = []
        self._next_position_id: int = 1
        self._skip_db_sync: bool = False

        # Cooldown tracking
        self._last_buy_time: datetime | None = None

        # Current price
        self._current_price: Decimal | None = None
        self._current_timestamp: datetime | None = None

        # Hourly close tracking for 24h drop + std dev calculation
        # Store (close_price, timestamp) for the last 24 hours of 1h candles
        self._hourly_closes: deque[Decimal] = deque(maxlen=25)  # 24h + 1 extra
        self._hourly_changes: deque[float] = deque(maxlen=24)  # pct changes between hourly closes

        self.logger.debug(
            "capitulation_strategy_initialized",
            bot_id=self.bot_id,
            rsi_1h_threshold=self.rsi_1h_threshold,
            rsi_5m_threshold=self.rsi_5m_threshold,
            volume_spike_multiplier=self.volume_spike_multiplier,
            trailing_stop_pct=float(self.trailing_stop_pct),
            max_profit_target_pct=float(self.max_profit_target_pct),
            cooldown_hours=self.cooldown_hours,
            max_open_positions=self.max_open_positions,
        )

    async def on_tick(self, tick_data: dict[str, Any]) -> None:
        """Update current price and trailing stop tracking."""
        if tick_data.get("pair") != self.pair:
            return

        price = Decimal(str(tick_data["price"]))
        self._current_price = price

        # Update highest price for trailing stops
        for pos in self._open_positions:
            if price > pos.highest_price:
                pos.highest_price = price

    async def on_ohlc(self, ohlc_data: dict[str, Any]) -> None:
        """Process OHLC candle: update analyzer + hourly tracking.

        Updates the shared MultiTimeframeAnalyzer for ALL intervals.
        Tracks 1h closes internally for 24h drop / std dev calculation.
        Trading logic executes on 5min trigger timeframe.
        """
        if ohlc_data.get("pair") != self.pair:
            return

        close_price = Decimal(str(ohlc_data["close"]))
        interval = ohlc_data.get("interval", 5)

        # Always update current price
        self._current_price = close_price

        # Update shared analyzer for ALL timeframes
        if self.analyzer is not None:
            self.analyzer.update(ohlc_data, interval)

        # Update highest price for trailing stops from candle highs
        candle_high = Decimal(str(ohlc_data.get("high", close_price)))
        for pos in self._open_positions:
            if candle_high > pos.highest_price:
                pos.highest_price = candle_high

        # Track 1h closes for 24h drop calculation
        if interval == 60 and ohlc_data.get("is_complete", False):
            prev_close = self._hourly_closes[-1] if self._hourly_closes else None
            self._hourly_closes.append(close_price)

            # Calculate hourly change percentage
            if prev_close and prev_close > 0:
                pct_change = float((close_price - prev_close) / prev_close * 100)
                self._hourly_changes.append(pct_change)

        # Only process trading logic on trigger timeframe (5min)
        trigger_tf = self.settings.multi_timeframe.trigger_timeframe
        if interval != trigger_tf:
            return

        # Only on complete candles
        if not ohlc_data.get("is_complete", False):
            return

        # Parse timestamp
        self._current_timestamp = self._parse_timestamp(ohlc_data)

    async def generate_signal(self) -> TradingSignal | None:
        """Generate capitulation signal: check exits first, then entry."""
        if not self._current_price:
            return None

        current_time = self._current_timestamp or datetime.now(UTC)

        # SELL LOGIC: Check each position for exit
        for pos in self._open_positions:
            profit_pct = ((self._current_price - pos.entry_price) / pos.entry_price) * Decimal(
                "100"
            )
            holding_minutes = (current_time - pos.entry_time).total_seconds() / 60

            # 1. Trailing stop
            if pos.highest_price > pos.entry_price:
                drop_from_high = (
                    (pos.highest_price - self._current_price) / pos.highest_price
                ) * Decimal("100")
                if drop_from_high >= self.trailing_stop_pct:
                    return self._sell_signal(
                        pos,
                        profit_pct,
                        holding_minutes,
                        current_time,
                        reason="trailing_stop",
                        order_type="market",
                        confidence=0.95,
                        detail=f"trailing stop: -{float(drop_from_high):.2f}% from high {float(pos.highest_price):.2f}",
                    )

            # 2. Take profit (limit order)
            if profit_pct >= self.max_profit_target_pct:
                return self._sell_signal(
                    pos,
                    profit_pct,
                    holding_minutes,
                    current_time,
                    reason="take_profit",
                    order_type="limit",
                    confidence=0.9,
                    detail=f"take profit: {float(profit_pct):.2f}% >= {float(self.max_profit_target_pct)}%",
                    limit_price=self._current_price,
                )

            # 3. Timeout
            if holding_minutes >= self.max_holding_minutes:
                return self._sell_signal(
                    pos,
                    profit_pct,
                    holding_minutes,
                    current_time,
                    reason="timeout",
                    order_type="market",
                    confidence=0.7,
                    detail=f"TIMEOUT: {holding_minutes:.0f}min >= {self.max_holding_minutes}min",
                )

        # BUY LOGIC: Check capitulation conditions
        if len(self._open_positions) >= self.max_open_positions:
            return None

        # Cooldown check
        if self._last_buy_time:
            cooldown_delta = timedelta(hours=self.cooldown_hours)
            if current_time - self._last_buy_time < cooldown_delta:
                return None

        # Check all 4 entry conditions
        entry_result = self._check_entry_conditions()
        if entry_result is None:
            return None

        drop_24h, sigma_mult, rsi_1h, rsi_5m, vol_ratio = entry_result

        # Calculate limit price
        offset_pct = Decimal(str(self.settings.order.limit_buy_offset_pct))
        limit_price = self._current_price * (Decimal("1") - offset_pct / Decimal("100"))

        return TradingSignal(
            signal_type=SignalType.BUY,
            pair=self.pair,
            price=self._current_price,
            confidence=0.95,
            reason=(
                f"CAPITULATION BUY: 24h drop {drop_24h:.1f}% ({sigma_mult:.1f}σ), "
                f"RSI 1h={rsi_1h:.0f}, RSI 5m={rsi_5m:.0f}, vol={vol_ratio:.1f}x"
            ),
            strategy=self.bot_id,
            timestamp=current_time,
            metadata={
                "drop_24h_pct": drop_24h,
                "sigma_multiplier": sigma_mult,
                "rsi_1h": rsi_1h,
                "rsi_5m": rsi_5m,
                "volume_ratio_5m": vol_ratio,
                "order_type": "limit",
                "limit_price": float(limit_price),
                "position_size_multiplier": self.position_size_multiplier,
            },
        )

    def _check_entry_conditions(self) -> tuple[float, float, float, float, float] | None:
        """Check all 4 capitulation entry conditions.

        Returns:
            Tuple of (drop_24h, sigma_mult, rsi_1h, rsi_5m, vol_ratio) if all
            conditions met, None otherwise.
        """
        # Need at least 12 hourly candles for meaningful std dev
        if len(self._hourly_changes) < 12:
            return None

        # Get analysis from shared analyzer
        analysis = self.analyzer.analyze() if self.analyzer else None
        if analysis is None:
            return None

        # Condition 1: 24h drop > 2 standard deviations
        if len(self._hourly_closes) < 2:
            return None

        oldest_close = self._hourly_closes[0]
        newest_close = self._hourly_closes[-1]
        if oldest_close <= 0:
            return None

        drop_24h = float((newest_close - oldest_close) / oldest_close * 100)

        # Calculate standard deviation of hourly changes
        changes = list(self._hourly_changes)
        mean_change = sum(changes) / len(changes)
        variance = sum((c - mean_change) ** 2 for c in changes) / len(changes)
        std_dev = math.sqrt(variance) if variance > 0 else 0.0

        if std_dev == 0:
            return None

        # How many sigmas is the 24h drop?
        sigma_mult = abs(drop_24h) / std_dev if drop_24h < 0 else 0.0

        if sigma_mult < 2.0:
            return None

        # Condition 2: RSI 1h < threshold
        rsi_1h = analysis.rsi_1h
        if rsi_1h is None or rsi_1h >= self.rsi_1h_threshold:
            return None

        # Condition 3: Volume 5m spike > multiplier
        vol_ratio = analysis.volume_ratio_5m
        if vol_ratio < self.volume_spike_multiplier:
            return None

        # Condition 4: RSI 5m < threshold
        rsi_5m = analysis.rsi_5m
        if rsi_5m is None or rsi_5m >= self.rsi_5m_threshold:
            return None

        return (drop_24h, sigma_mult, rsi_1h, rsi_5m, vol_ratio)

    def _sell_signal(
        self,
        pos: CapitulationPosition,
        profit_pct: Decimal,
        holding_minutes: float,
        current_time: datetime,
        *,
        reason: str,
        order_type: str,
        confidence: float,
        detail: str,
        limit_price: Decimal | None = None,
    ) -> TradingSignal:
        """Build a SELL signal for a position."""
        metadata: dict[str, Any] = {
            "position_id": pos.position_id,
            "amount_btc": float(pos.amount_btc),
            "entry_price": float(pos.entry_price),
            "profit_pct": float(profit_pct),
            "holding_time_minutes": holding_minutes,
            "reason": reason,
            "order_type": order_type,
        }
        if limit_price is not None:
            metadata["limit_price"] = float(limit_price)

        return TradingSignal(
            signal_type=SignalType.SELL,
            pair=self.pair,
            price=self._current_price or Decimal("0"),
            confidence=confidence,
            reason=f"Position #{pos.position_id}: {detail} (held {holding_minutes:.1f}min)",
            strategy=self.bot_id,
            timestamp=current_time,
            metadata=metadata,
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
        """Track positions after trade execution."""
        if side == "buy":
            pid = self._next_position_id
            self._next_position_id += 1
            self._last_buy_time = datetime.now(UTC)

            self._open_positions.append(
                CapitulationPosition(
                    entry_price=price,
                    entry_time=datetime.now(UTC),
                    amount_btc=amount,
                    amount_usdc=amount * price,
                    position_id=pid,
                    highest_price=price,
                )
            )

            self.logger.info(
                "capitulation_position_opened",
                position_id=pid,
                entry_price=float(price),
                amount_btc=float(amount),
                bot_id=self.bot_id,
            )

        elif side == "sell":
            if position_id is None:
                return

            for i, pos in enumerate(self._open_positions):
                if pos.position_id == position_id:
                    closed = self._open_positions.pop(i)
                    pnl = (price - closed.entry_price) * closed.amount_btc - fee
                    self.logger.info(
                        "capitulation_position_closed",
                        position_id=position_id,
                        pnl=float(pnl),
                        bot_id=self.bot_id,
                    )
                    break

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

    def get_name(self) -> str:
        """Return strategy name."""
        return "capitulation"

    def get_config(self) -> dict[str, Any]:
        """Return strategy configuration."""
        return {
            "name": self.get_name(),
            "bot_id": self.bot_id,
            "rsi_1h_threshold": self.rsi_1h_threshold,
            "rsi_5m_threshold": self.rsi_5m_threshold,
            "volume_spike_multiplier": self.volume_spike_multiplier,
            "trailing_stop_pct": float(self.trailing_stop_pct),
            "max_profit_target_pct": float(self.max_profit_target_pct),
            "max_holding_minutes": self.max_holding_minutes,
            "cooldown_hours": self.cooldown_hours,
            "max_open_positions": self.max_open_positions,
            "position_size_multiplier": self.position_size_multiplier,
        }

    def reset_state(self) -> None:
        """Reset internal state."""
        super().reset_state()
        self._open_positions.clear()
        self._current_price = None
        self._current_timestamp = None
        self._next_position_id = 1
        self._last_buy_time = None
        self._hourly_closes.clear()
        self._hourly_changes.clear()

    def add_position(
        self,
        entry_price: Decimal,
        amount_usdc: Decimal,
        entry_time: datetime | None = None,
    ) -> int:
        """Add a position (for backtest compatibility).

        Args:
            entry_price: Entry price.
            amount_usdc: Position size in USDC.
            entry_time: Entry timestamp.

        Returns:
            Position ID.
        """
        pid = self._next_position_id
        self._next_position_id += 1

        amount_btc = amount_usdc / entry_price
        self._open_positions.append(
            CapitulationPosition(
                entry_price=entry_price,
                entry_time=entry_time or datetime.now(UTC),
                amount_btc=amount_btc,
                amount_usdc=amount_usdc,
                position_id=pid,
                highest_price=entry_price,
            )
        )
        return pid

    def close_position(self, position_id: int) -> CapitulationPosition | None:
        """Close a position by ID (for backtest compatibility).

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
    def open_positions(self) -> list[CapitulationPosition]:
        """Get list of open positions."""
        return self._open_positions.copy()

    @property
    def open_positions_count(self) -> int:
        """Get number of open positions."""
        return len(self._open_positions)

    @property
    def current_price(self) -> Decimal | None:
        """Get current market price."""
        return self._current_price
