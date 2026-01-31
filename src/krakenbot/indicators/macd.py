"""MACD (Moving Average Convergence Divergence) indicator implementation."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal


@dataclass
class MACDResult:
    """MACD calculation result."""

    macd_line: float  # Fast EMA - Slow EMA
    signal_line: float  # EMA of MACD line
    histogram: float  # MACD - Signal (momentum)

    @property
    def is_bullish_cross(self) -> bool:
        """MACD is above signal line (bullish momentum)."""
        return self.histogram > 0

    @property
    def is_bearish_cross(self) -> bool:
        """MACD is below signal line (bearish momentum)."""
        return self.histogram < 0


class MACDIndicator:
    """Calculates MACD (Moving Average Convergence Divergence).

    MACD Line = Fast EMA - Slow EMA
    Signal Line = EMA of MACD Line
    Histogram = MACD Line - Signal Line

    Standard settings:
    - Fast EMA: 12 periods
    - Slow EMA: 26 periods
    - Signal EMA: 9 periods
    """

    def __init__(
        self,
        fast_period: int = 12,
        slow_period: int = 26,
        signal_period: int = 9,
    ) -> None:
        """Initialize MACD indicator.

        Args:
            fast_period: Fast EMA period (default 12).
            slow_period: Slow EMA period (default 26).
            signal_period: Signal line EMA period (default 9).
        """
        self.fast_period = fast_period
        self.slow_period = slow_period
        self.signal_period = signal_period

        self._fast_ema: Decimal | None = None
        self._slow_ema: Decimal | None = None
        self._signal_ema: float | None = None
        self._price_count: int = 0
        self._macd_values: list[float] = []
        self._result: MACDResult | None = None

    def _ema_multiplier(self, period: int) -> Decimal:
        """Calculate EMA smoothing multiplier: 2 / (period + 1)."""
        return Decimal("2") / Decimal(str(period + 1))

    def update(self, close_price: Decimal) -> MACDResult | None:
        """Update MACD with new price.

        Args:
            close_price: The closing price for this period.

        Returns:
            MACDResult or None if not enough data yet.
        """
        self._price_count += 1

        # Initialize EMAs with first price
        if self._price_count == 1:
            self._fast_ema = close_price
            self._slow_ema = close_price
            return None

        # Update EMAs
        fast_mult = self._ema_multiplier(self.fast_period)
        slow_mult = self._ema_multiplier(self.slow_period)

        self._fast_ema = (close_price * fast_mult) + (self._fast_ema * (Decimal("1") - fast_mult))
        self._slow_ema = (close_price * slow_mult) + (self._slow_ema * (Decimal("1") - slow_mult))

        # Need slow_period prices minimum for meaningful MACD
        if self._price_count < self.slow_period:
            return None

        macd_line = float(self._fast_ema - self._slow_ema)
        self._macd_values.append(macd_line)

        # Need signal_period MACD values for signal line
        if len(self._macd_values) < self.signal_period:
            return None

        if self._signal_ema is None:
            # Initialize signal EMA with SMA
            self._signal_ema = sum(self._macd_values[-self.signal_period :]) / self.signal_period
        else:
            signal_mult = float(self._ema_multiplier(self.signal_period))
            self._signal_ema = (macd_line * signal_mult) + (self._signal_ema * (1 - signal_mult))

        histogram = macd_line - self._signal_ema

        self._result = MACDResult(
            macd_line=macd_line,
            signal_line=self._signal_ema,
            histogram=histogram,
        )

        return self._result

    def reset(self) -> None:
        """Reset indicator state."""
        self._fast_ema = None
        self._slow_ema = None
        self._signal_ema = None
        self._price_count = 0
        self._macd_values.clear()
        self._result = None

    @property
    def value(self) -> MACDResult | None:
        """Current MACD result."""
        return self._result

    @property
    def is_ready(self) -> bool:
        """Whether indicator has enough data to produce values."""
        return self._result is not None

    @property
    def warmup_periods(self) -> int:
        """Number of periods needed before indicator is ready."""
        return self.slow_period + self.signal_period
