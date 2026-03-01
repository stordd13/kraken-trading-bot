"""RSI (Relative Strength Index) indicator implementation."""

from __future__ import annotations

from collections import deque
from decimal import Decimal

_ZERO = Decimal("0")
_ONE = Decimal("1")
_HUNDRED = Decimal("100")


class RSIIndicator:
    """Calculates RSI (Relative Strength Index).

    RSI = 100 - (100 / (1 + RS))
    RS = Average Gain / Average Loss (over period)

    Traditional levels:
    - Overbought: RSI > 70
    - Oversold: RSI < 30

    Uses Wilder's smoothing method (EMA-like) for average gain/loss.
    """

    def __init__(self, period: int = 14) -> None:
        """Initialize RSI indicator.

        Args:
            period: Number of periods for RSI calculation (default 14).
        """
        self.period = period
        self._prices: deque[Decimal] = deque(maxlen=period + 1)
        self._gains: list[Decimal] = []
        self._losses: list[Decimal] = []
        self._current_rsi: Decimal | None = None
        self._avg_gain: Decimal | None = None
        self._avg_loss: Decimal | None = None

    def update(self, close_price: Decimal) -> Decimal | None:
        """Update RSI with new price.

        Args:
            close_price: The closing price for this period.

        Returns:
            RSI value (0-100) as Decimal, or None if not enough data yet.
        """
        self._prices.append(close_price)

        if len(self._prices) < 2:
            return None

        # Calculate price change
        change = self._prices[-1] - self._prices[-2]
        gain = change if change > 0 else _ZERO
        loss = abs(change) if change < 0 else _ZERO

        # Collect gains/losses until we have enough for initial SMA
        if self._avg_gain is None:
            self._gains.append(gain)
            self._losses.append(loss)

            # Once we have 'period' changes, calculate initial SMA
            if len(self._gains) >= self.period:
                self._avg_gain = sum(self._gains) / len(self._gains)
                self._avg_loss = sum(self._losses) / len(self._losses)
        else:
            # Use Wilder's smoothing (EMA-like) for subsequent calculations
            self._avg_gain = (self._avg_gain * (self.period - 1) + gain) / self.period
            self._avg_loss = (self._avg_loss * (self.period - 1) + loss) / self.period

        # Calculate RSI
        if self._avg_gain is not None and self._avg_loss is not None:
            if self._avg_loss == 0:
                self._current_rsi = _HUNDRED
            else:
                rs = self._avg_gain / self._avg_loss
                self._current_rsi = _HUNDRED - (_HUNDRED / (_ONE + rs))

        return self._current_rsi

    def reset(self) -> None:
        """Reset indicator state."""
        self._prices.clear()
        self._gains.clear()
        self._losses.clear()
        self._current_rsi = None
        self._avg_gain = None
        self._avg_loss = None

    @property
    def value(self) -> Decimal | None:
        """Current RSI value."""
        return self._current_rsi

    @property
    def is_ready(self) -> bool:
        """Whether indicator has enough data to produce values."""
        return self._current_rsi is not None

    @property
    def warmup_periods(self) -> int:
        """Number of periods needed before indicator is ready."""
        return self.period + 1
