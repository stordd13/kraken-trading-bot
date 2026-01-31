"""Technical indicators-based multi-position trading strategy.

This strategy uses RSI, MACD, and Bollinger Bands with a confluence approach
(multiple indicators must agree) to generate trading signals.

Entry conditions (confluence required):
- RSI oversold (<30) + Price below lower Bollinger Band
- OR RSI oversold + MACD bullish cross

Exit conditions:
- Profit target reached
- RSI overbought (>70) + MACD bearish
- Price above upper Bollinger Band (with profit)
- Stop-loss or timeout
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from typing import TYPE_CHECKING, Any

from krakenbot.indicators.bollinger import BollingerBandsIndicator
from krakenbot.indicators.macd import MACDIndicator
from krakenbot.indicators.rsi import RSIIndicator
from krakenbot.models.base import SignalType
from krakenbot.strategies.base import BaseStrategy, TradingSignal

if TYPE_CHECKING:
    from krakenbot.config.settings import Settings
    from krakenbot.core.database import DatabaseManager
    from krakenbot.core.event_bus import EventBus


@dataclass
class TechnicalPosition:
    """Represents a single open position with indicator context."""

    entry_price: Decimal
    entry_time: datetime
    amount_usdc: Decimal
    position_id: int
    entry_rsi: float | None = None
    entry_bb_percent_b: float | None = None


class TechnicalIndicatorStrategy(BaseStrategy):
    """Multi-position strategy using RSI, MACD, and Bollinger Bands.

    Entry conditions (confluence required):
    - RSI oversold (<30) + Price below lower Bollinger Band
    - OR RSI oversold + MACD bullish cross

    Exit conditions:
    - Profit target reached
    - RSI overbought (>70) + MACD bearish
    - Price above upper Bollinger Band
    - Stop-loss or timeout
    """

    def __init__(
        self,
        settings: Settings,
        event_bus: EventBus,
        db_manager: DatabaseManager,
    ) -> None:
        """Initialize technical indicator strategy.

        Args:
            settings: Application settings.
            event_bus: Event bus for pub/sub.
            db_manager: Database manager.
        """
        super().__init__(settings, event_bus, db_manager)

        # Get technical indicator settings
        ti_settings = settings.technical_indicator

        # Initialize indicators
        self.rsi = RSIIndicator(period=ti_settings.rsi_period)
        self.macd = MACDIndicator(
            fast_period=ti_settings.macd_fast,
            slow_period=ti_settings.macd_slow,
            signal_period=ti_settings.macd_signal,
        )
        self.bollinger = BollingerBandsIndicator(
            period=ti_settings.bb_period,
            multiplier=ti_settings.bb_multiplier,
        )

        # Configuration
        self.rsi_oversold = ti_settings.rsi_oversold
        self.rsi_overbought = ti_settings.rsi_overbought
        self.sell_threshold_pct = settings.strategy.sell_threshold_pct
        self.stop_loss_pct = settings.risk.emergency_stop_loss_pct
        self.max_holding_minutes = settings.strategy.max_holding_minutes
        self.max_open_positions = settings.risk.max_open_positions
        self.pair = settings.trading.pair

        # State
        self._current_price: Decimal | None = None
        self._current_timestamp: datetime | None = None
        self._open_positions: list[TechnicalPosition] = []
        self._next_position_id: int = 1
        self._skip_db_sync: bool = False
        self._warmup_complete: bool = False
        self._candle_count: int = 0

        self.logger.debug(
            "technical_indicator_strategy_initialized",
            rsi_period=ti_settings.rsi_period,
            macd_settings=f"{ti_settings.macd_fast}/{ti_settings.macd_slow}/{ti_settings.macd_signal}",
            bb_period=ti_settings.bb_period,
        )

    @property
    def warmup_periods_required(self) -> int:
        """Minimum candles needed before generating signals."""
        return max(
            self.rsi.warmup_periods,
            self.macd.warmup_periods,
            self.bollinger.warmup_periods,
        )

    async def on_tick(self, tick_data: dict[str, Any]) -> None:
        """Update current price from tick data.

        Args:
            tick_data: Tick data with pair and price.
        """
        if tick_data.get("pair") != self.pair:
            return
        self._current_price = Decimal(str(tick_data["price"]))

    async def on_ohlc(self, ohlc_data: dict[str, Any]) -> None:
        """Process OHLC and update all indicators.

        Args:
            ohlc_data: OHLC candle data.
        """
        if ohlc_data.get("pair") != self.pair:
            return

        close_price = Decimal(str(ohlc_data["close"]))
        self._current_price = close_price
        self._candle_count += 1

        # Parse timestamp
        self._current_timestamp = self._parse_timestamp(ohlc_data.get("timestamp"))

        # Update all indicators
        self.rsi.update(close_price)
        self.macd.update(close_price)
        self.bollinger.update(close_price)

        # Check warmup
        if self._candle_count >= self.warmup_periods_required:
            self._warmup_complete = True

        self.logger.debug(
            "indicators_updated",
            rsi=self.rsi.value,
            macd_histogram=self.macd.value.histogram if self.macd.value else None,
            bb_percent_b=self.bollinger.value.percent_b if self.bollinger.value else None,
            warmup_complete=self._warmup_complete,
            candle_count=self._candle_count,
        )

    async def generate_signal(self) -> TradingSignal | None:
        """Generate signal based on technical indicator confluence.

        Returns:
            TradingSignal or None if no signal conditions met.
        """
        if not self._current_price or not self._warmup_complete:
            return None

        if not self.rsi.is_ready or not self.macd.is_ready or not self.bollinger.is_ready:
            return None

        current_time = self._current_timestamp or datetime.now(UTC)

        # Check SELL conditions for open positions first
        sell_signal = self._check_sell_conditions(current_time)
        if sell_signal:
            return sell_signal

        # Check BUY conditions if we have capacity
        if len(self._open_positions) < self.max_open_positions:
            buy_signal = self._check_buy_conditions(current_time)
            if buy_signal:
                return buy_signal

        # Default HOLD
        return TradingSignal(
            signal_type=SignalType.HOLD,
            pair=self.pair,
            price=self._current_price,
            confidence=1.0,
            reason=self._get_hold_reason(),
            strategy=self.get_name(),
            timestamp=current_time,
            metadata=self._get_indicator_metadata(),
        )

    def _check_buy_conditions(self, current_time: datetime) -> TradingSignal | None:
        """Check for BUY signal based on indicator confluence.

        Args:
            current_time: Current timestamp.

        Returns:
            TradingSignal for BUY or None.
        """
        rsi_value = self.rsi.value
        macd_result = self.macd.value
        bb_result = self.bollinger.value

        if rsi_value is None or macd_result is None or bb_result is None:
            return None

        confidence = 0.5  # Base confidence
        reasons = []

        # RSI oversold check
        rsi_oversold = rsi_value < self.rsi_oversold
        if rsi_oversold:
            confidence += 0.2
            reasons.append(f"RSI oversold ({rsi_value:.1f} < {self.rsi_oversold})")
            if rsi_value < 20:  # Extremely oversold
                confidence += 0.1
                reasons.append("RSI extremely oversold")

        # Bollinger Bands check
        price_below_lower_bb = bb_result.is_price_below_lower(self._current_price)
        if price_below_lower_bb:
            confidence += 0.2
            reasons.append(
                f"Price below lower BB ({float(self._current_price):.2f} < {float(bb_result.lower):.2f})"
            )

        # MACD check
        macd_bullish = macd_result.is_bullish_cross
        if macd_bullish:
            confidence += 0.2
            reasons.append(f"MACD bullish (histogram={macd_result.histogram:.4f})")

        # Require confluence: RSI oversold + (below BB OR MACD bullish)
        if rsi_oversold and (price_below_lower_bb or macd_bullish):
            return TradingSignal(
                signal_type=SignalType.BUY,
                pair=self.pair,
                price=self._current_price,
                confidence=min(confidence, 1.0),
                reason=" | ".join(reasons),
                strategy=self.get_name(),
                timestamp=current_time,
                metadata={
                    **self._get_indicator_metadata(),
                    "current_positions": len(self._open_positions),
                    "max_positions": self.max_open_positions,
                },
            )

        return None

    def _check_sell_conditions(self, current_time: datetime) -> TradingSignal | None:
        """Check SELL conditions for each open position.

        Args:
            current_time: Current timestamp.

        Returns:
            TradingSignal for SELL or None.
        """
        rsi_value = self.rsi.value
        macd_result = self.macd.value
        bb_result = self.bollinger.value

        if rsi_value is None or macd_result is None or bb_result is None:
            return None

        for position in self._open_positions:
            profit_pct = (
                (self._current_price - position.entry_price) / position.entry_price
            ) * Decimal("100")

            holding_time = current_time - position.entry_time
            holding_minutes = holding_time.total_seconds() / 60

            # Profit target
            if profit_pct >= Decimal(str(self.sell_threshold_pct)):
                return self._create_sell_signal(
                    position,
                    current_time,
                    profit_pct,
                    holding_minutes,
                    f"Profit target: {float(profit_pct):.2f}% >= {self.sell_threshold_pct}%",
                    "profit_target",
                    confidence=0.9,
                )

            # Stop loss
            if profit_pct <= -Decimal(str(self.stop_loss_pct)):
                return self._create_sell_signal(
                    position,
                    current_time,
                    profit_pct,
                    holding_minutes,
                    f"STOP-LOSS: {float(profit_pct):.2f}% <= -{self.stop_loss_pct}%",
                    "stop_loss",
                    confidence=1.0,
                )

            # Technical exit: RSI overbought + MACD bearish
            if rsi_value > self.rsi_overbought and macd_result.is_bearish_cross:
                return self._create_sell_signal(
                    position,
                    current_time,
                    profit_pct,
                    holding_minutes,
                    f"Technical exit: RSI overbought ({rsi_value:.1f}) + MACD bearish",
                    "technical_exit",
                    confidence=0.8,
                )

            # Price above upper BB with profit
            if bb_result.is_price_above_upper(self._current_price) and profit_pct > 0:
                return self._create_sell_signal(
                    position,
                    current_time,
                    profit_pct,
                    holding_minutes,
                    f"Price above upper BB with {float(profit_pct):.2f}% profit",
                    "bb_upper_exit",
                    confidence=0.75,
                )

            # Timeout
            if holding_minutes >= self.max_holding_minutes:
                return self._create_sell_signal(
                    position,
                    current_time,
                    profit_pct,
                    holding_minutes,
                    f"TIMEOUT: held {holding_minutes:.0f} min",
                    "timeout",
                    confidence=0.7,
                )

        return None

    def _create_sell_signal(
        self,
        position: TechnicalPosition,
        current_time: datetime,
        profit_pct: Decimal,
        holding_minutes: float,
        reason: str,
        exit_reason: str,
        confidence: float,
    ) -> TradingSignal:
        """Create a SELL signal for a specific position.

        Args:
            position: The position to sell.
            current_time: Current timestamp.
            profit_pct: Current profit percentage.
            holding_minutes: How long position has been held.
            reason: Human-readable reason.
            exit_reason: Machine-readable exit reason.
            confidence: Signal confidence.

        Returns:
            TradingSignal for SELL.
        """
        return TradingSignal(
            signal_type=SignalType.SELL,
            pair=self.pair,
            price=self._current_price,
            confidence=confidence,
            reason=f"Position #{position.position_id} {reason}",
            strategy=self.get_name(),
            timestamp=current_time,
            metadata={
                "position_id": position.position_id,
                "entry_price": float(position.entry_price),
                "profit_pct": float(profit_pct),
                "holding_time_minutes": holding_minutes,
                "exit_reason": exit_reason,
                **self._get_indicator_metadata(),
            },
        )

    def _get_indicator_metadata(self) -> dict[str, Any]:
        """Get current indicator values as metadata.

        Returns:
            Dictionary with all indicator values.
        """
        return {
            "rsi": self.rsi.value,
            "macd_line": self.macd.value.macd_line if self.macd.value else None,
            "macd_signal": self.macd.value.signal_line if self.macd.value else None,
            "macd_histogram": self.macd.value.histogram if self.macd.value else None,
            "bb_upper": float(self.bollinger.value.upper) if self.bollinger.value else None,
            "bb_middle": float(self.bollinger.value.middle) if self.bollinger.value else None,
            "bb_lower": float(self.bollinger.value.lower) if self.bollinger.value else None,
            "bb_percent_b": self.bollinger.value.percent_b if self.bollinger.value else None,
        }

    def _get_hold_reason(self) -> str:
        """Generate descriptive HOLD reason.

        Returns:
            Human-readable reason for holding.
        """
        rsi = self.rsi.value
        macd = self.macd.value

        if rsi is None:
            return "Indicators not ready"

        if rsi >= self.rsi_overbought:
            return f"RSI overbought ({rsi:.1f}), waiting for pullback"
        if rsi <= self.rsi_oversold:
            return f"RSI oversold ({rsi:.1f}), awaiting confirmation"
        if macd and macd.histogram > 0:
            return "Bullish momentum but no entry signal"
        return f"Neutral ({len(self._open_positions)}/{self.max_open_positions} positions)"

    def add_position(
        self,
        entry_price: Decimal,
        amount_usdc: Decimal,
        entry_time: datetime | None = None,
    ) -> int:
        """Add new position to tracking.

        Args:
            entry_price: Entry price for the position.
            amount_usdc: Amount in USDC.
            entry_time: Entry timestamp (defaults to now).

        Returns:
            Position ID for tracking.
        """
        position_id = self._next_position_id
        self._next_position_id += 1

        position = TechnicalPosition(
            entry_price=entry_price,
            entry_time=entry_time or datetime.now(UTC),
            amount_usdc=amount_usdc,
            position_id=position_id,
            entry_rsi=self.rsi.value,
            entry_bb_percent_b=self.bollinger.value.percent_b if self.bollinger.value else None,
        )

        self._open_positions.append(position)
        self.logger.debug(
            "position_added",
            position_id=position_id,
            entry_price=float(entry_price),
            rsi=self.rsi.value,
        )
        return position_id

    def close_position(self, position_id: int) -> TechnicalPosition | None:
        """Close position by ID.

        Args:
            position_id: ID of position to close.

        Returns:
            Closed position or None if not found.
        """
        for i, position in enumerate(self._open_positions):
            if position.position_id == position_id:
                closed = self._open_positions.pop(i)
                self.logger.debug("position_closed", position_id=position_id)
                return closed
        return None

    def get_name(self) -> str:
        """Return strategy name.

        Returns:
            Strategy identifier.
        """
        return "technical_indicator"

    def get_config(self) -> dict[str, Any]:
        """Return strategy configuration.

        Returns:
            Dictionary with all configuration parameters.
        """
        return {
            "name": self.get_name(),
            "rsi_period": self.rsi.period,
            "rsi_oversold": self.rsi_oversold,
            "rsi_overbought": self.rsi_overbought,
            "macd_fast": self.macd.fast_period,
            "macd_slow": self.macd.slow_period,
            "macd_signal": self.macd.signal_period,
            "bb_period": self.bollinger.period,
            "bb_multiplier": float(self.bollinger.multiplier),
            "sell_threshold_pct": self.sell_threshold_pct,
            "stop_loss_pct": self.stop_loss_pct,
            "max_open_positions": self.max_open_positions,
        }

    def reset_state(self) -> None:
        """Reset strategy internal state."""
        super().reset_state()
        self._current_price = None
        self._current_timestamp = None
        self._open_positions.clear()
        self._next_position_id = 1
        self._warmup_complete = False
        self._candle_count = 0

        # Reset indicators
        self.rsi.reset()
        self.macd.reset()
        self.bollinger.reset()

        self.logger.debug("technical_indicator_strategy_reset")

    def set_position_state(self, has_position: bool, entry_price: Decimal | None) -> None:
        """Set position state for backtest compatibility.

        Args:
            has_position: Whether there's an open position.
            entry_price: Entry price if has_position is True.
        """
        # For single-position backtest compatibility
        if not has_position:
            self._open_positions.clear()
        elif entry_price and not self._open_positions:
            self.add_position(
                entry_price=entry_price,
                amount_usdc=Decimal("100"),  # Default amount
            )

    def _parse_timestamp(self, timestamp_value: Any) -> datetime:
        """Parse timestamp from various formats.

        Args:
            timestamp_value: Timestamp in various formats.

        Returns:
            Parsed datetime in UTC.
        """
        if timestamp_value is None:
            return datetime.now(UTC)
        if isinstance(timestamp_value, datetime):
            if timestamp_value.tzinfo is None:
                return timestamp_value.replace(tzinfo=UTC)
            return timestamp_value
        if isinstance(timestamp_value, str):
            return datetime.fromisoformat(timestamp_value.replace("Z", "+00:00"))
        if isinstance(timestamp_value, int | float):
            return datetime.fromtimestamp(timestamp_value, tz=UTC)
        return datetime.now(UTC)

    # Properties for compatibility
    @property
    def open_positions_count(self) -> int:
        """Number of open positions."""
        return len(self._open_positions)

    @property
    def open_positions(self) -> list[TechnicalPosition]:
        """Copy of open positions list."""
        return self._open_positions.copy()

    @property
    def current_price(self) -> Decimal | None:
        """Current market price."""
        return self._current_price

    @property
    def has_position(self) -> bool:
        """Whether there are any open positions."""
        return len(self._open_positions) > 0

    @property
    def entry_price(self) -> Decimal | None:
        """Entry price of first position (for single-position compatibility)."""
        if self._open_positions:
            return self._open_positions[0].entry_price
        return None
