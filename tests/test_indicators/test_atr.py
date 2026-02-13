"""Tests for ATR (Average True Range) indicator.

This module tests the ATRIndicator including:
- ATR calculation on known OHLC data
- Warmup behavior (returns None before period)
- Wilder's smoothing correctness
- Reset functionality
- is_ready and value properties
- Edge cases (first candle with no prev_close)
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from krakenbot.indicators.atr import ATRIndicator


class TestATRInitialization:
    """Tests for ATRIndicator initialization."""

    def test_default_period(self) -> None:
        """Test default period is 14."""
        atr = ATRIndicator()
        assert atr.period == 14

    def test_custom_period(self) -> None:
        """Test custom period is stored correctly."""
        atr = ATRIndicator(period=5)
        assert atr.period == 5

    def test_initial_state(self) -> None:
        """Test indicator starts not ready with no value."""
        atr = ATRIndicator(period=3)
        assert atr.is_ready is False
        assert atr.value is None

    def test_warmup_periods(self) -> None:
        """Test warmup_periods matches period."""
        atr = ATRIndicator(period=10)
        assert atr.warmup_periods == 10


class TestATRWarmup:
    """Tests for warmup behavior before enough data."""

    def test_returns_none_during_warmup(self) -> None:
        """Test update returns None before period candles are received."""
        atr = ATRIndicator(period=3)

        result1 = atr.update(Decimal("105"), Decimal("95"), Decimal("100"))
        assert result1 is None
        assert atr.is_ready is False

        result2 = atr.update(Decimal("110"), Decimal("98"), Decimal("107"))
        assert result2 is None
        assert atr.is_ready is False

    def test_returns_value_at_period(self) -> None:
        """Test update returns a value once period candles are received."""
        atr = ATRIndicator(period=3)

        atr.update(Decimal("105"), Decimal("95"), Decimal("100"))
        atr.update(Decimal("110"), Decimal("98"), Decimal("107"))
        result = atr.update(Decimal("112"), Decimal("102"), Decimal("109"))

        assert result is not None
        assert atr.is_ready is True
        assert atr.value == result


class TestATRFirstCandle:
    """Tests for edge case: first candle with no previous close."""

    def test_first_candle_tr_is_high_minus_low(self) -> None:
        """Test that first candle TR = high - low (no prev_close)."""
        atr = ATRIndicator(period=1)

        # With period=1, the first candle produces the ATR immediately.
        # TR should be high - low = 110 - 90 = 20
        result = atr.update(Decimal("110"), Decimal("90"), Decimal("100"))

        assert result == Decimal("20")

    def test_second_candle_uses_prev_close(self) -> None:
        """Test that second candle incorporates prev_close in TR calculation."""
        atr = ATRIndicator(period=1)

        # First candle: close = 100
        atr.update(Decimal("110"), Decimal("90"), Decimal("100"))

        # Gap up candle: high=120, low=115, close=118, prev_close=100
        # TR = max(120-115, |120-100|, |115-100|) = max(5, 20, 15) = 20
        result = atr.update(Decimal("120"), Decimal("115"), Decimal("118"))

        assert result == Decimal("20")


class TestATRCalculation:
    """Tests for ATR calculation on known OHLC data."""

    def test_simple_average_initialization(self) -> None:
        """Test that initial ATR is a simple average of TR values."""
        atr = ATRIndicator(period=3)

        # Candle 1: no prev_close, TR = 110 - 90 = 20
        atr.update(Decimal("110"), Decimal("90"), Decimal("100"))

        # Candle 2: prev_close=100, TR = max(108-95, |108-100|, |95-100|) = max(13, 8, 5) = 13
        atr.update(Decimal("108"), Decimal("95"), Decimal("105"))

        # Candle 3: prev_close=105, TR = max(115-100, |115-105|, |100-105|) = max(15, 10, 5) = 15
        result = atr.update(Decimal("115"), Decimal("100"), Decimal("110"))

        # Initial ATR = (20 + 13 + 15) / 3 = 48 / 3 = 16
        expected = Decimal("48") / Decimal("3")
        assert result == expected

    def test_known_sequence_with_period_3(self) -> None:
        """Test a full sequence with known values and period=3."""
        atr = ATRIndicator(period=3)

        # Candle 1: TR = 10 - 5 = 5
        atr.update(Decimal("10"), Decimal("5"), Decimal("8"))

        # Candle 2: prev_close=8, TR = max(12-7, |12-8|, |7-8|) = max(5, 4, 1) = 5
        atr.update(Decimal("12"), Decimal("7"), Decimal("11"))

        # Candle 3: prev_close=11, TR = max(14-9, |14-11|, |9-11|) = max(5, 3, 2) = 5
        result = atr.update(Decimal("14"), Decimal("9"), Decimal("13"))

        # Initial ATR = (5 + 5 + 5) / 3 = 5
        assert result == Decimal("5")

    def test_gap_down_increases_tr(self) -> None:
        """Test that a gap down produces a higher TR via abs(low - prev_close)."""
        atr = ATRIndicator(period=1)

        # First candle: close = 100
        atr.update(Decimal("105"), Decimal("95"), Decimal("100"))

        # Gap down candle: high=82, low=78, close=80, prev_close=100
        # TR = max(82-78, |82-100|, |78-100|) = max(4, 18, 22) = 22
        result = atr.update(Decimal("82"), Decimal("78"), Decimal("80"))

        # Wilder smoothing with period=1: ATR = (prev * 0 + 22) / 1 = 22
        assert result == Decimal("22")


class TestWilderSmoothing:
    """Tests for Wilder's smoothing correctness."""

    def test_wilder_smoothing_formula(self) -> None:
        """Test Wilder's smoothing: ATR = (ATR_prev * (period-1) + TR) / period."""
        atr = ATRIndicator(period=3)

        # Build up to get initial ATR
        # Candle 1: TR = 20 - 10 = 10
        atr.update(Decimal("20"), Decimal("10"), Decimal("15"))
        # Candle 2: prev_close=15, TR = max(22-12, |22-15|, |12-15|) = max(10, 7, 3) = 10
        atr.update(Decimal("22"), Decimal("12"), Decimal("18"))
        # Candle 3: prev_close=18, TR = max(25-15, |25-18|, |15-18|) = max(10, 7, 3) = 10
        result3 = atr.update(Decimal("25"), Decimal("15"), Decimal("20"))

        # Initial ATR = (10 + 10 + 10) / 3 = 10
        assert result3 == Decimal("10")

        # Candle 4: prev_close=20, TR = max(28-22, |28-20|, |22-20|) = max(6, 8, 2) = 8
        # Wilder: ATR = (10 * 2 + 8) / 3 = 28 / 3
        result4 = atr.update(Decimal("28"), Decimal("22"), Decimal("25"))

        expected = Decimal("28") / Decimal("3")
        assert result4 == expected

    def test_wilder_smoothing_decreasing_volatility(self) -> None:
        """Test ATR decreases when TR values decrease over time."""
        atr = ATRIndicator(period=2)

        # Candle 1: TR = 100 - 80 = 20
        atr.update(Decimal("100"), Decimal("80"), Decimal("90"))
        # Candle 2: prev_close=90, TR = max(95-85, |95-90|, |85-90|) = max(10, 5, 5) = 10
        result_initial = atr.update(Decimal("95"), Decimal("85"), Decimal("92"))

        # Initial ATR = (20 + 10) / 2 = 15
        assert result_initial == Decimal("15")

        # Candle 3: low volatility. prev_close=92, TR = max(93-91, |93-92|, |91-92|) = max(2, 1, 1) = 2
        # Wilder: ATR = (15 * 1 + 2) / 2 = 17 / 2 = 8.5
        result3 = atr.update(Decimal("93"), Decimal("91"), Decimal("92"))

        assert result3 == Decimal("17") / Decimal("2")
        assert result3 < result_initial

    def test_wilder_smoothing_increasing_volatility(self) -> None:
        """Test ATR increases when TR values increase over time."""
        atr = ATRIndicator(period=2)

        # Candle 1: TR = 51 - 49 = 2
        atr.update(Decimal("51"), Decimal("49"), Decimal("50"))
        # Candle 2: prev_close=50, TR = max(52-48, |52-50|, |48-50|) = max(4, 2, 2) = 4
        result_initial = atr.update(Decimal("52"), Decimal("48"), Decimal("50"))

        # Initial ATR = (2 + 4) / 2 = 3
        assert result_initial == Decimal("3")

        # Candle 3: high volatility. prev_close=50, TR = max(70-30, |70-50|, |30-50|) = max(40, 20, 20) = 40
        # Wilder: ATR = (3 * 1 + 40) / 2 = 43 / 2 = 21.5
        result3 = atr.update(Decimal("70"), Decimal("30"), Decimal("55"))

        assert result3 == Decimal("43") / Decimal("2")
        assert result3 > result_initial

    def test_multiple_smoothing_steps(self) -> None:
        """Test several consecutive Wilder smoothing steps for numerical accuracy."""
        atr = ATRIndicator(period=2)

        # Candle 1: TR = 10
        atr.update(Decimal("15"), Decimal("5"), Decimal("10"))
        # Candle 2: prev_close=10, TR = max(16-6, |16-10|, |6-10|) = max(10, 6, 4) = 10
        atr.update(Decimal("16"), Decimal("6"), Decimal("12"))
        # Initial ATR = (10 + 10) / 2 = 10

        # Candle 3: prev_close=12, TR = max(18-8, |18-12|, |8-12|) = max(10, 6, 4) = 10
        # ATR = (10*1 + 10) / 2 = 10
        result3 = atr.update(Decimal("18"), Decimal("8"), Decimal("14"))
        assert result3 == Decimal("10")

        # Candle 4: prev_close=14, TR = max(20-10, |20-14|, |10-14|) = max(10, 6, 4) = 10
        # ATR = (10*1 + 10) / 2 = 10
        result4 = atr.update(Decimal("20"), Decimal("10"), Decimal("16"))
        assert result4 == Decimal("10")

        # Constant TR = 10 keeps ATR = 10 indefinitely
        assert atr.value == Decimal("10")


class TestATRReset:
    """Tests for reset functionality."""

    def test_reset_clears_all_state(self) -> None:
        """Test reset returns indicator to initial state."""
        atr = ATRIndicator(period=2)

        # Feed some data to build state
        atr.update(Decimal("110"), Decimal("90"), Decimal("100"))
        atr.update(Decimal("115"), Decimal("95"), Decimal("105"))

        assert atr.is_ready is True

        atr.reset()

        assert atr.is_ready is False
        assert atr.value is None

    def test_reset_allows_reuse(self) -> None:
        """Test indicator works correctly after reset."""
        atr = ATRIndicator(period=2)

        # First run
        atr.update(Decimal("110"), Decimal("90"), Decimal("100"))
        atr.update(Decimal("120"), Decimal("80"), Decimal("105"))
        first_value = atr.value

        atr.reset()

        # Second run with different data
        # Candle 1: TR = 60 - 40 = 20
        atr.update(Decimal("60"), Decimal("40"), Decimal("50"))
        # Candle 2: prev_close=50, TR = max(62-42, |62-50|, |42-50|) = max(20, 12, 8) = 20
        result = atr.update(Decimal("62"), Decimal("42"), Decimal("55"))

        # ATR = (20 + 20) / 2 = 20
        assert result == Decimal("20")
        assert atr.is_ready is True
        assert atr.value != first_value

    def test_reset_first_candle_has_no_prev_close(self) -> None:
        """Test that after reset, first candle uses high-low (no prev_close)."""
        atr = ATRIndicator(period=1)

        atr.update(Decimal("200"), Decimal("100"), Decimal("150"))
        assert atr.value == Decimal("100")

        atr.reset()

        # After reset, TR should be high - low again (no prev_close memory)
        result = atr.update(Decimal("55"), Decimal("45"), Decimal("50"))
        assert result == Decimal("10")


class TestATRProperties:
    """Tests for is_ready and value properties."""

    def test_value_is_none_before_ready(self) -> None:
        """Test value property returns None before warmup complete."""
        atr = ATRIndicator(period=5)

        for i in range(4):
            atr.update(
                Decimal("100") + Decimal(str(i)),
                Decimal("90") + Decimal(str(i)),
                Decimal("95") + Decimal(str(i)),
            )

        assert atr.value is None

    def test_value_matches_last_update_return(self) -> None:
        """Test value property matches the return value of the last update."""
        atr = ATRIndicator(period=2)

        atr.update(Decimal("110"), Decimal("90"), Decimal("100"))
        returned = atr.update(Decimal("115"), Decimal("95"), Decimal("105"))

        assert atr.value == returned

    def test_is_ready_transitions_once(self) -> None:
        """Test is_ready transitions from False to True at period boundary."""
        atr = ATRIndicator(period=3)
        states: list[bool] = []

        for i in range(5):
            atr.update(
                Decimal("100") + Decimal(str(i * 2)),
                Decimal("90") + Decimal(str(i * 2)),
                Decimal("95") + Decimal(str(i * 2)),
            )
            states.append(atr.is_ready)

        # First two: not ready. Third onward: ready.
        assert states == [False, False, True, True, True]

    def test_value_updates_after_each_candle(self) -> None:
        """Test value changes with each new candle after warmup."""
        atr = ATRIndicator(period=2)

        atr.update(Decimal("110"), Decimal("90"), Decimal("100"))
        atr.update(Decimal("115"), Decimal("95"), Decimal("105"))
        first_value = atr.value

        # New candle with very different volatility
        atr.update(Decimal("200"), Decimal("100"), Decimal("150"))
        second_value = atr.value

        assert first_value is not None
        assert second_value is not None
        assert second_value != first_value
