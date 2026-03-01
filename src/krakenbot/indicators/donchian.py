"""Donchian Channel indicator implementation.

Tracks the highest high and lowest low over configurable look-back periods.
Asymmetric periods are supported (e.g. upper=20, lower=10) for the classic
Turtle Trading variant.
"""

from __future__ import annotations

from collections import deque
from decimal import Decimal
from typing import Any

_ZERO = Decimal("0")
_TWO = Decimal("2")


class DonchianIndicator:
    """Donchian Channel indicator.

    Attributes:
        period_upper: Look-back for the upper band (highest high).
        period_lower: Look-back for the lower band (lowest low).
    """

    def __init__(
        self,
        period_upper: int = 20,
        period_lower: int = 10,
    ) -> None:
        self.period_upper = period_upper
        self.period_lower = period_lower

        max_period = max(period_upper, period_lower)
        self._highs: deque[Decimal] = deque(maxlen=max_period)
        self._lows: deque[Decimal] = deque(maxlen=max_period)

        self._count: int = 0
        self._last_close: Decimal = _ZERO
        self._result: dict[str, Decimal] | None = None

    # ------------------------------------------------------------------
    # Core API
    # ------------------------------------------------------------------

    def update(self, high: Decimal, low: Decimal, close: Decimal) -> dict[str, Any] | None:
        """Feed a new OHLC candle.

        Args:
            high: Candle high.
            low: Candle low.
            close: Candle close.

        Returns:
            Dict with channel values, or ``None`` during warm-up.
        """
        self._highs.append(high)
        self._lows.append(low)
        self._last_close = close
        self._count += 1

        needed = max(self.period_upper, self.period_lower)
        if self._count < needed:
            return None

        # Upper = highest high over period_upper most recent candles
        upper = max(list(self._highs)[-self.period_upper :])
        # Lower = lowest low over period_lower most recent candles
        lower = min(list(self._lows)[-self.period_lower :])
        middle = (upper + lower) / _TWO

        # Width normalised by close
        width = (upper - lower) / close if close > _ZERO else _ZERO

        self._result = {
            "upper": upper,
            "lower": lower,
            "middle": middle,
            "width": width,
        }
        return self._result

    def reset(self) -> None:
        """Clear all internal state."""
        self._highs.clear()
        self._lows.clear()
        self._count = 0
        self._last_close = _ZERO
        self._result = None

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def value(self) -> dict[str, Decimal] | None:
        """Current Donchian channel values or ``None`` if not ready."""
        return self._result

    @property
    def is_ready(self) -> bool:
        """True when enough data has been accumulated."""
        return self._result is not None

    @property
    def warmup_periods(self) -> int:
        """Number of candles needed before indicator is ready."""
        return max(self.period_upper, self.period_lower)
