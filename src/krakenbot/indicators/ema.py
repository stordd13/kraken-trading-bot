"""Exponential Moving Average (EMA) indicator.

Provides an incremental EMA implementation that processes prices
one at a time, compatible with the streaming indicator interface.

EMA formula:
    EMA_t = close * k + EMA_{t-1} * (1 - k)
    where k = 2 / (period + 1)
"""

from __future__ import annotations

from collections import deque
from decimal import Decimal


class EMAIndicator:
    """Exponential Moving Average indicator.

    Calculates EMA incrementally as new prices arrive.
    Uses SMA for the initial value, then switches to exponential smoothing.

    Attributes:
        period: Number of periods for EMA calculation.

    Example:
        >>> ema = EMAIndicator(period=20)
        >>> for price in prices:
        ...     result = ema.update(price)
        ...     if result is not None:
        ...         print(f"EMA: {result}")
    """

    def __init__(self, period: int = 20) -> None:
        """Initialize EMA indicator.

        Args:
            period: EMA period (number of smoothing periods).
        """
        self.period = period
        self._k = Decimal("2") / (Decimal(str(period)) + Decimal("1"))
        self._ema: Decimal | None = None
        self._warmup_prices: deque[Decimal] = deque(maxlen=period)
        self._count: int = 0

    def update(self, close_price: Decimal) -> Decimal | None:
        """Update EMA with a new close price.

        During warmup (< period prices), uses SMA as initial EMA.
        After warmup, uses exponential smoothing.

        Args:
            close_price: New closing price.

        Returns:
            Current EMA value, or None if not enough data.
        """
        self._count += 1

        if self._ema is None:
            # Warmup phase: collect prices for initial SMA
            self._warmup_prices.append(close_price)
            if self._count >= self.period:
                # Initialize EMA with SMA
                sma = sum(self._warmup_prices) / Decimal(str(self.period))
                self._ema = sma
                return self._ema
            return None
        else:
            # Exponential smoothing
            self._ema = close_price * self._k + self._ema * (Decimal("1") - self._k)
            return self._ema

    def reset(self) -> None:
        """Clear all internal state."""
        self._ema = None
        self._warmup_prices.clear()
        self._count = 0

    @property
    def value(self) -> Decimal | None:
        """Current EMA value.

        Returns:
            Current EMA, or None if not ready.
        """
        return self._ema

    @property
    def is_ready(self) -> bool:
        """Check if indicator has enough data.

        Returns:
            True if at least `period` prices have been processed.
        """
        return self._ema is not None

    @property
    def warmup_periods(self) -> int:
        """Number of periods needed before indicator is ready.

        Returns:
            The EMA period.
        """
        return self.period
