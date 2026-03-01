"""Ichimoku Cloud indicator implementation.

Computes Tenkan-sen, Kijun-sen, Senkou Span A/B, Chikou Span, and the cloud
boundaries.  All values are Decimal.

Simplified for trading use: the cloud values returned are the *current* cloud
(senkou_a = (tenkan + kijun) / 2, senkou_b = mid-range of 52 periods).
"""

from __future__ import annotations

from collections import deque
from decimal import Decimal
from typing import Any

_ZERO = Decimal("0")
_TWO = Decimal("2")


class IchimokuIndicator:
    """Ichimoku Cloud indicator.

    Parameters are the standard Ichimoku settings:
        tenkan_period  = 9   (conversion line)
        kijun_period   = 26  (base line)
        senkou_b_period = 52 (leading span B)

    The ``update`` method accepts (high, low, close) for each candle.

    Attributes:
        tenkan_period: Tenkan-sen look-back.
        kijun_period: Kijun-sen look-back.
        senkou_b_period: Senkou Span B look-back.
    """

    def __init__(
        self,
        tenkan_period: int = 9,
        kijun_period: int = 26,
        senkou_b_period: int = 52,
    ) -> None:
        self.tenkan_period = tenkan_period
        self.kijun_period = kijun_period
        self.senkou_b_period = senkou_b_period

        # Rolling windows — sized to the largest look-back
        self._highs: deque[Decimal] = deque(maxlen=senkou_b_period)
        self._lows: deque[Decimal] = deque(maxlen=senkou_b_period)
        self._closes: deque[Decimal] = deque(maxlen=senkou_b_period)

        self._count: int = 0
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
            Dict with ichimoku values, or ``None`` during warm-up.
        """
        self._highs.append(high)
        self._lows.append(low)
        self._closes.append(close)
        self._count += 1

        if self._count < self.senkou_b_period:
            return None

        # --- Tenkan-sen (conversion line) ---
        highs_t = list(self._highs)[-self.tenkan_period :]
        lows_t = list(self._lows)[-self.tenkan_period :]
        tenkan = (max(highs_t) + min(lows_t)) / _TWO

        # --- Kijun-sen (base line) ---
        highs_k = list(self._highs)[-self.kijun_period :]
        lows_k = list(self._lows)[-self.kijun_period :]
        kijun = (max(highs_k) + min(lows_k)) / _TWO

        # --- Senkou Span A (current cloud) ---
        senkou_a = (tenkan + kijun) / _TWO

        # --- Senkou Span B ---
        senkou_b = (max(self._highs) + min(self._lows)) / _TWO

        # --- Chikou Span = current close (normally plotted 26 periods back) ---
        chikou = close

        # --- Cloud boundaries ---
        cloud_top = max(senkou_a, senkou_b)
        cloud_bottom = min(senkou_a, senkou_b)

        self._result = {
            "tenkan": tenkan,
            "kijun": kijun,
            "senkou_a": senkou_a,
            "senkou_b": senkou_b,
            "chikou": chikou,
            "cloud_top": cloud_top,
            "cloud_bottom": cloud_bottom,
        }
        return self._result

    def reset(self) -> None:
        """Clear all internal state."""
        self._highs.clear()
        self._lows.clear()
        self._closes.clear()
        self._count = 0
        self._result = None

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def value(self) -> dict[str, Decimal] | None:
        """Current Ichimoku values or ``None`` if not ready."""
        return self._result

    @property
    def is_ready(self) -> bool:
        """True when enough data has been accumulated."""
        return self._result is not None

    @property
    def warmup_periods(self) -> int:
        """Number of candles needed before indicator is ready."""
        return self.senkou_b_period
