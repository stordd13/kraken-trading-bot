"""SuperTrend indicator implementation.

ATR-based trend indicator that draws a trailing line above or below price.

Algorithm:
    1. Calculate ATR(period) using the existing ATRIndicator.
    2. Basic upper band = (high + low) / 2 + (multiplier * ATR)
    3. Basic lower band = (high + low) / 2 - (multiplier * ATR)
    4. Final upper band = min(basic_upper, prev_final_upper) if prev_close > prev_final_upper
    5. Final lower band = max(basic_lower, prev_final_lower) if prev_close < prev_final_lower
    6. Direction flips based on close vs final bands.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from krakenbot.indicators.atr import ATRIndicator

_ZERO = Decimal("0")
_TWO = Decimal("2")


class SuperTrendIndicator:
    """SuperTrend trend-following indicator.

    Uses ATR to create dynamic support/resistance levels.
    Direction = 1 means bullish (price above SuperTrend line).
    Direction = -1 means bearish (price below SuperTrend line).

    Attributes:
        atr_period: ATR calculation period.
        multiplier: ATR band multiplier.

    Example:
        >>> st = SuperTrendIndicator(atr_period=10, multiplier=Decimal("3.0"))
        >>> for candle in candles:
        ...     result = st.update(candle.high, candle.low, candle.close)
        ...     if result is not None:
        ...         print(f"ST: {result['supertrend']}, Dir: {result['direction']}")
    """

    def __init__(
        self,
        atr_period: int = 10,
        multiplier: Decimal | float = Decimal("3.0"),
    ) -> None:
        """Initialize SuperTrend indicator.

        Args:
            atr_period: ATR period for volatility band calculation.
            multiplier: ATR multiplier for band width (default 3.0).
        """
        self.atr_period = atr_period
        self.multiplier = (
            Decimal(str(multiplier)) if not isinstance(multiplier, Decimal) else multiplier
        )

        # Internal ATR
        self._atr = ATRIndicator(period=atr_period)

        # Band tracking
        self._prev_final_upper: Decimal | None = None
        self._prev_final_lower: Decimal | None = None
        self._prev_close: Decimal | None = None

        # SuperTrend state
        self._supertrend: Decimal | None = None
        self._direction: int = 1  # 1 = bullish, -1 = bearish
        self._prev_supertrend: Decimal | None = None

        self._count: int = 0

    def update(self, high: Decimal, low: Decimal, close: Decimal) -> dict[str, Any] | None:
        """Update SuperTrend with a new OHLC candle.

        Args:
            high: Candle high price.
            low: Candle low price.
            close: Candle close price.

        Returns:
            Dict with 'supertrend' (Decimal) and 'direction' (int), or None if not ready.
        """
        atr_value = self._atr.update(high, low, close)
        self._count += 1

        if atr_value is None:
            self._prev_close = close
            return None

        # --- Calculate basic bands ---
        hl2 = (high + low) / _TWO
        basic_upper = hl2 + self.multiplier * atr_value
        basic_lower = hl2 - self.multiplier * atr_value

        # --- Calculate final bands with trailing logic ---
        if self._prev_final_upper is None:
            # First ATR-ready candle: initialize bands
            final_upper = basic_upper
            final_lower = basic_lower
        else:
            # Upper band: can only move DOWN (tighten) in a downtrend
            if basic_upper < self._prev_final_upper or (
                self._prev_close is not None and self._prev_close > self._prev_final_upper
            ):
                final_upper = basic_upper
            else:
                final_upper = self._prev_final_upper

            # Lower band: can only move UP (tighten) in an uptrend
            if basic_lower > self._prev_final_lower or (
                self._prev_close is not None and self._prev_close < self._prev_final_lower
            ):
                final_lower = basic_lower
            else:
                final_lower = self._prev_final_lower

        # --- Determine direction and SuperTrend value ---
        if self._prev_supertrend is None:
            # First calculation: determine initial direction from close vs bands
            if close > final_upper:
                self._direction = 1
                self._supertrend = final_lower
            else:
                self._direction = -1
                self._supertrend = final_upper
        else:
            if self._prev_supertrend == self._prev_final_upper:
                # Was bearish
                if close > final_upper:
                    # Flip to bullish
                    self._direction = 1
                    self._supertrend = final_lower
                else:
                    self._direction = -1
                    self._supertrend = final_upper
            else:
                # Was bullish
                if close < final_lower:
                    # Flip to bearish
                    self._direction = -1
                    self._supertrend = final_upper
                else:
                    self._direction = 1
                    self._supertrend = final_lower

        # Store state for next iteration
        self._prev_final_upper = final_upper
        self._prev_final_lower = final_lower
        self._prev_close = close
        self._prev_supertrend = self._supertrend

        return {
            "supertrend": self._supertrend,
            "direction": self._direction,
        }

    def reset(self) -> None:
        """Clear all internal state."""
        self._atr.reset()
        self._prev_final_upper = None
        self._prev_final_lower = None
        self._prev_close = None
        self._supertrend = None
        self._direction = 1
        self._prev_supertrend = None
        self._count = 0

    @property
    def value(self) -> Decimal | None:
        """Current SuperTrend line value.

        Returns:
            SuperTrend price level, or None if not ready.
        """
        return self._supertrend

    @property
    def direction(self) -> int:
        """Current trend direction.

        Returns:
            1 for bullish (price above ST), -1 for bearish (price below ST).
        """
        return self._direction

    @property
    def is_ready(self) -> bool:
        """Check if indicator has enough data.

        Returns:
            True if SuperTrend value is available.
        """
        return self._supertrend is not None

    @property
    def warmup_periods(self) -> int:
        """Number of periods needed before indicator is ready.

        Returns:
            ATR period (SuperTrend is ready as soon as ATR is).
        """
        return self.atr_period
