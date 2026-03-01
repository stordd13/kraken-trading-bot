"""Bollinger Bands indicator implementation."""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from decimal import Decimal

_ZERO = Decimal("0")


@dataclass
class BollingerBandsResult:
    """Bollinger Bands calculation result."""

    upper: Decimal  # SMA + (std_dev * multiplier)
    middle: Decimal  # SMA (Simple Moving Average)
    lower: Decimal  # SMA - (std_dev * multiplier)
    bandwidth: Decimal  # (Upper - Lower) / Middle (volatility measure)
    percent_b: Decimal  # (Price - Lower) / (Upper - Lower) (position within bands)

    def is_price_below_lower(self, price: Decimal) -> bool:
        """Check if price is below lower band (potential buy signal)."""
        return price < self.lower

    def is_price_above_upper(self, price: Decimal) -> bool:
        """Check if price is above upper band (potential sell signal)."""
        return price > self.upper


class BollingerBandsIndicator:
    """Calculates Bollinger Bands.

    Upper Band = SMA + (multiplier * standard deviation)
    Middle Band = SMA (Simple Moving Average)
    Lower Band = SMA - (multiplier * standard deviation)

    Standard settings:
    - Period: 20 (SMA period)
    - Multiplier: 2.0 (standard deviations)
    """

    def __init__(self, period: int = 20, multiplier: float = 2.0) -> None:
        """Initialize Bollinger Bands indicator.

        Args:
            period: SMA calculation period (default 20).
            multiplier: Standard deviation multiplier (default 2.0).
        """
        self.period = period
        self.multiplier = Decimal(str(multiplier))
        self._prices: deque[Decimal] = deque(maxlen=period)
        self._result: BollingerBandsResult | None = None
        self._last_price: Decimal | None = None

    def update(self, close_price: Decimal) -> BollingerBandsResult | None:
        """Update Bollinger Bands with new price.

        Args:
            close_price: The closing price for this period.

        Returns:
            BollingerBandsResult or None if not enough data yet.
        """
        self._prices.append(close_price)
        self._last_price = close_price

        if len(self._prices) < self.period:
            return None

        # Calculate SMA (middle band)
        prices_list = list(self._prices)
        sma = sum(prices_list) / len(prices_list)

        # Calculate standard deviation
        variance = sum((p - sma) ** 2 for p in prices_list) / len(prices_list)
        std_dev = variance.sqrt()

        # Calculate bands
        upper = sma + (std_dev * self.multiplier)
        lower = sma - (std_dev * self.multiplier)

        # Calculate metrics
        bandwidth = (upper - lower) / sma if sma != _ZERO else _ZERO

        band_width = upper - lower
        if band_width != _ZERO:
            percent_b = (close_price - lower) / band_width
        else:
            percent_b = Decimal("0.5")

        self._result = BollingerBandsResult(
            upper=upper,
            middle=sma,
            lower=lower,
            bandwidth=bandwidth,
            percent_b=percent_b,
        )

        return self._result

    def reset(self) -> None:
        """Reset indicator state."""
        self._prices.clear()
        self._result = None
        self._last_price = None

    @property
    def value(self) -> BollingerBandsResult | None:
        """Current Bollinger Bands result."""
        return self._result

    @property
    def is_ready(self) -> bool:
        """Whether indicator has enough data to produce values."""
        return self._result is not None

    @property
    def warmup_periods(self) -> int:
        """Number of periods needed before indicator is ready."""
        return self.period
