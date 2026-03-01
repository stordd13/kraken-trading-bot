"""Rolling VWAP (Volume-Weighted Average Price) indicator.

This is a *proxy* for true intraday VWAP, computed as a rolling
volume-weighted average of close prices over *N* candles:

    VWAP = sum(close_i * volume_i, N) / sum(volume_i, N)

Suitable for 4h candles where a session-anchored VWAP is not meaningful.
"""

from __future__ import annotations

from collections import deque
from decimal import Decimal

_ZERO = Decimal("0")


class VWAPIndicator:
    """Rolling VWAP indicator.

    Attributes:
        period: Number of candles in the rolling window.
    """

    def __init__(self, period: int = 20) -> None:
        self.period = period

        self._cv: deque[Decimal] = deque(maxlen=period)  # close * volume
        self._vol: deque[Decimal] = deque(maxlen=period)  # volume

        self._count: int = 0
        self._value: Decimal | None = None

    # ------------------------------------------------------------------
    # Core API
    # ------------------------------------------------------------------

    def update(self, close: Decimal, volume: Decimal) -> Decimal | None:
        """Feed a new candle.

        Args:
            close: Candle close price.
            volume: Candle volume.

        Returns:
            Rolling VWAP as Decimal, or ``None`` during warm-up.
        """
        self._cv.append(close * volume)
        self._vol.append(volume)
        self._count += 1

        if self._count < self.period:
            return None

        total_vol = sum(self._vol)
        if total_vol <= _ZERO:
            # Avoid division by zero — keep previous value if any
            return self._value

        self._value = sum(self._cv) / total_vol
        return self._value

    def reset(self) -> None:
        """Clear all internal state."""
        self._cv.clear()
        self._vol.clear()
        self._count = 0
        self._value = None

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def value(self) -> Decimal | None:
        """Current rolling VWAP or ``None`` if not ready."""
        return self._value

    @property
    def is_ready(self) -> bool:
        """True when enough data has been accumulated."""
        return self._value is not None

    @property
    def warmup_periods(self) -> int:
        """Number of candles needed before indicator is ready."""
        return self.period
