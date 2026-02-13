"""Average True Range (ATR) indicator.

Provides an incremental ATR implementation for measuring volatility.

True Range (TR) = max(high - low, |high - prev_close|, |low - prev_close|)
ATR = Moving average of TR over N periods (Wilder's smoothing)
"""

from __future__ import annotations

from collections import deque
from decimal import Decimal


class ATRIndicator:
    """Average True Range volatility indicator.

    Calculates ATR incrementally as new OHLC candles arrive.
    Uses Wilder's smoothing method (same as RSI).

    Attributes:
        period: Number of periods for ATR calculation.

    Example:
        >>> atr = ATRIndicator(period=14)
        >>> for candle in candles:
        ...     result = atr.update(candle.high, candle.low, candle.close)
        ...     if result is not None:
        ...         print(f"ATR: {result}")
    """

    def __init__(self, period: int = 14) -> None:
        """Initialize ATR indicator.

        Args:
            period: ATR period (number of smoothing periods).
        """
        self.period = period
        self._atr: Decimal | None = None
        self._prev_close: Decimal | None = None
        self._tr_values: deque[Decimal] = deque(maxlen=period)
        self._count: int = 0

    def update(
        self, high: Decimal, low: Decimal, close: Decimal
    ) -> Decimal | None:
        """Update ATR with a new OHLC candle.

        Args:
            high: Candle high price.
            low: Candle low price.
            close: Candle close price.

        Returns:
            Current ATR value, or None if not enough data.
        """
        # Calculate True Range
        if self._prev_close is None:
            # First candle: TR = high - low
            tr = high - low
        else:
            tr = max(
                high - low,
                abs(high - self._prev_close),
                abs(low - self._prev_close),
            )

        self._prev_close = close
        self._count += 1

        if self._atr is None:
            # Warmup phase: collect TR values
            self._tr_values.append(tr)
            if self._count >= self.period:
                # Initialize ATR with simple average of TR values
                self._atr = sum(self._tr_values) / Decimal(str(self.period))
                return self._atr
            return None
        else:
            # Wilder's smoothing: ATR = (ATR_prev * (period-1) + TR) / period
            period_d = Decimal(str(self.period))
            self._atr = (self._atr * (period_d - Decimal("1")) + tr) / period_d
            return self._atr

    def reset(self) -> None:
        """Clear all internal state."""
        self._atr = None
        self._prev_close = None
        self._tr_values.clear()
        self._count = 0

    @property
    def value(self) -> Decimal | None:
        """Current ATR value.

        Returns:
            Current ATR, or None if not ready.
        """
        return self._atr

    @property
    def is_ready(self) -> bool:
        """Check if indicator has enough data.

        Returns:
            True if at least `period` candles have been processed.
        """
        return self._atr is not None

    @property
    def warmup_periods(self) -> int:
        """Number of periods needed before indicator is ready.

        Returns:
            The ATR period.
        """
        return self.period
