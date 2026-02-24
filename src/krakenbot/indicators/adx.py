"""Average Directional Index (ADX) indicator.

Measures trend strength regardless of direction using Wilder's method.

Algorithm:
    1. +DM / -DM from consecutive candles (directional movement)
    2. Smooth +DM, -DM, TR with Wilder's smoothing (same as ATR)
    3. +DI = smoothed(+DM) / smoothed(TR) * 100
    4. -DI = smoothed(-DM) / smoothed(TR) * 100
    5. DX = |+DI - -DI| / (+DI + -DI) * 100
    6. ADX = Wilder-smoothed DX
"""

from __future__ import annotations

from collections import deque
from decimal import Decimal

_ZERO = Decimal("0")
_ONE = Decimal("1")
_HUNDRED = Decimal("100")


class ADXIndicator:
    """Average Directional Index (ADX) trend strength indicator.

    ADX values interpretation:
        0-25  : Absent or weak trend
        25-50 : Strong trend
        50-75 : Very strong trend
        75-100: Extremely strong trend

    Attributes:
        period: Number of periods for smoothing.

    Example:
        >>> adx = ADXIndicator(period=14)
        >>> for candle in candles:
        ...     result = adx.update(candle.high, candle.low, candle.close)
        ...     if result is not None:
        ...         print(f"ADX: {result}, +DI: {adx.plus_di}, -DI: {adx.minus_di}")
    """

    def __init__(self, period: int = 14) -> None:
        """Initialize ADX indicator.

        Args:
            period: Smoothing period (default 14).
        """
        self.period = period
        self._period_d = Decimal(str(period))

        # Previous candle values for directional movement calculation
        self._prev_high: Decimal | None = None
        self._prev_low: Decimal | None = None
        self._prev_close: Decimal | None = None

        # Wilder-smoothed values (initialized after `period` candles)
        self._smoothed_plus_dm: Decimal | None = None
        self._smoothed_minus_dm: Decimal | None = None
        self._smoothed_tr: Decimal | None = None

        # Warmup accumulators
        self._plus_dm_sum: Decimal = _ZERO
        self._minus_dm_sum: Decimal = _ZERO
        self._tr_sum: Decimal = _ZERO

        # DX values for ADX initialization (need `period` DX to SMA)
        self._dx_values: deque[Decimal] = deque(maxlen=period)

        # Final ADX
        self._adx: Decimal | None = None
        self._plus_di: Decimal | None = None
        self._minus_di: Decimal | None = None

        self._count: int = 0

    def update(self, high: Decimal, low: Decimal, close: Decimal) -> Decimal | None:
        """Update ADX with a new OHLC candle.

        Args:
            high: Candle high price.
            low: Candle low price.
            close: Candle close price.

        Returns:
            Current ADX value, or None if not enough data.
        """
        self._count += 1

        if self._prev_high is None:
            # First candle: store and return
            self._prev_high = high
            self._prev_low = low
            self._prev_close = close
            return None

        # --- Calculate True Range ---
        tr = max(
            high - low,
            abs(high - self._prev_close),
            abs(low - self._prev_close),
        )

        # --- Calculate Directional Movement ---
        up_move = high - self._prev_high
        down_move = self._prev_low - low

        plus_dm = up_move if (up_move > down_move and up_move > _ZERO) else _ZERO
        minus_dm = down_move if (down_move > up_move and down_move > _ZERO) else _ZERO

        self._prev_high = high
        self._prev_low = low
        self._prev_close = close

        if self._smoothed_tr is None:
            # --- Phase 1: Accumulate for first smoothed values ---
            self._plus_dm_sum += plus_dm
            self._minus_dm_sum += minus_dm
            self._tr_sum += tr

            if self._count - 1 < self.period:
                # Need `period` DM/TR pairs (candle 2 through candle period+1)
                return None

            # Initialize smoothed values with sums (Wilder's method)
            self._smoothed_plus_dm = self._plus_dm_sum
            self._smoothed_minus_dm = self._minus_dm_sum
            self._smoothed_tr = self._tr_sum
        else:
            # --- Phase 2: Wilder's smoothing ---
            self._smoothed_plus_dm = (
                self._smoothed_plus_dm - self._smoothed_plus_dm / self._period_d + plus_dm
            )
            self._smoothed_minus_dm = (
                self._smoothed_minus_dm - self._smoothed_minus_dm / self._period_d + minus_dm
            )
            self._smoothed_tr = self._smoothed_tr - self._smoothed_tr / self._period_d + tr

        # --- Calculate +DI and -DI ---
        if self._smoothed_tr == _ZERO:
            self._plus_di = _ZERO
            self._minus_di = _ZERO
        else:
            self._plus_di = self._smoothed_plus_dm / self._smoothed_tr * _HUNDRED
            self._minus_di = self._smoothed_minus_dm / self._smoothed_tr * _HUNDRED

        # --- Calculate DX ---
        di_sum = self._plus_di + self._minus_di
        if di_sum == _ZERO:
            dx = _ZERO
        else:
            dx = abs(self._plus_di - self._minus_di) / di_sum * _HUNDRED

        # --- Calculate ADX ---
        if self._adx is None:
            # Accumulate DX values for initial ADX (SMA of first `period` DX values)
            self._dx_values.append(dx)
            if len(self._dx_values) < self.period:
                return None
            # Initialize ADX as SMA of DX values
            self._adx = sum(self._dx_values) / self._period_d
        else:
            # Wilder's smoothing for ADX
            self._adx = (self._adx * (self._period_d - _ONE) + dx) / self._period_d

        return self._adx

    def reset(self) -> None:
        """Clear all internal state."""
        self._prev_high = None
        self._prev_low = None
        self._prev_close = None
        self._smoothed_plus_dm = None
        self._smoothed_minus_dm = None
        self._smoothed_tr = None
        self._plus_dm_sum = _ZERO
        self._minus_dm_sum = _ZERO
        self._tr_sum = _ZERO
        self._dx_values.clear()
        self._adx = None
        self._plus_di = None
        self._minus_di = None
        self._count = 0

    @property
    def value(self) -> Decimal | None:
        """Current ADX value.

        Returns:
            ADX value (0-100), or None if not ready.
        """
        return self._adx

    @property
    def plus_di(self) -> Decimal | None:
        """Current +DI (positive directional indicator).

        Returns:
            +DI value, or None if not ready.
        """
        return self._plus_di

    @property
    def minus_di(self) -> Decimal | None:
        """Current -DI (negative directional indicator).

        Returns:
            -DI value, or None if not ready.
        """
        return self._minus_di

    @property
    def is_ready(self) -> bool:
        """Check if indicator has enough data.

        Returns:
            True if ADX is available (needs 2*period candles).
        """
        return self._adx is not None

    @property
    def warmup_periods(self) -> int:
        """Number of periods needed before indicator is ready.

        Returns:
            2 * period + 1 (period for smoothed TR/DM, period for DX SMA, +1 for first candle).
        """
        return 2 * self.period + 1
