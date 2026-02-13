"""Tests for EMA indicator.

This module tests the EMAIndicator including:
- EMA calculation against known values
- Warmup behavior (returns None before period)
- Convergence behavior
- Reset functionality
- is_ready and value properties
- warmup_periods property
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from krakenbot.indicators.ema import EMAIndicator


class TestEMAInitialization:
    """Tests for EMAIndicator initialization."""

    def test_default_period(self) -> None:
        """Test default period is 20."""
        ema = EMAIndicator()
        assert ema.period == 20

    def test_custom_period(self) -> None:
        """Test custom period is stored correctly."""
        ema = EMAIndicator(period=10)
        assert ema.period == 10

    def test_initial_value_is_none(self) -> None:
        """Test initial value is None before any updates."""
        ema = EMAIndicator(period=5)
        assert ema.value is None

    def test_initial_is_ready_false(self) -> None:
        """Test is_ready is False before any updates."""
        ema = EMAIndicator(period=5)
        assert ema.is_ready is False


class TestEMAWarmup:
    """Tests for warmup behavior (returns None before period)."""

    def test_returns_none_during_warmup(self) -> None:
        """Test update returns None for each price before period is reached."""
        ema = EMAIndicator(period=5)
        for i in range(4):
            result = ema.update(Decimal("100"))
            assert result is None, f"Expected None at update {i + 1}, got {result}"

    def test_is_ready_false_during_warmup(self) -> None:
        """Test is_ready remains False during warmup."""
        ema = EMAIndicator(period=5)
        for _ in range(4):
            ema.update(Decimal("100"))
            assert ema.is_ready is False

    def test_value_none_during_warmup(self) -> None:
        """Test value property is None during warmup."""
        ema = EMAIndicator(period=5)
        for _ in range(4):
            ema.update(Decimal("100"))
            assert ema.value is None

    def test_first_value_at_period(self) -> None:
        """Test first non-None value is returned exactly at period count."""
        ema = EMAIndicator(period=3)
        assert ema.update(Decimal("10")) is None
        assert ema.update(Decimal("20")) is None
        result = ema.update(Decimal("30"))
        assert result is not None

    def test_first_value_is_sma(self) -> None:
        """Test first EMA value equals the SMA of warmup prices."""
        ema = EMAIndicator(period=3)
        ema.update(Decimal("10"))
        ema.update(Decimal("20"))
        result = ema.update(Decimal("30"))

        expected_sma = (Decimal("10") + Decimal("20") + Decimal("30")) / Decimal("3")
        assert result == expected_sma

    def test_is_ready_true_at_period(self) -> None:
        """Test is_ready becomes True once period prices are provided."""
        ema = EMAIndicator(period=3)
        ema.update(Decimal("10"))
        ema.update(Decimal("20"))
        ema.update(Decimal("30"))
        assert ema.is_ready is True


class TestEMACalculation:
    """Tests for EMA calculation against known values."""

    def test_constant_series_equals_constant(self) -> None:
        """Test EMA of a constant series equals that constant."""
        ema = EMAIndicator(period=5)
        price = Decimal("100")
        for _ in range(10):
            result = ema.update(price)

        assert result == price

    def test_known_ema_values(self) -> None:
        """Test EMA calculation against hand-computed values.

        Period=3, k = 2/(3+1) = 0.5
        Prices: 2, 4, 6, 8, 10, 12
        SMA of first 3 = (2+4+6)/3 = 4
        EMA after 8:  8 * 0.5 + 4 * 0.5 = 6
        EMA after 10: 10 * 0.5 + 6 * 0.5 = 8
        EMA after 12: 12 * 0.5 + 8 * 0.5 = 10
        """
        ema = EMAIndicator(period=3)
        k = Decimal("2") / (Decimal("3") + Decimal("1"))

        # Warmup
        assert ema.update(Decimal("2")) is None
        assert ema.update(Decimal("4")) is None

        # First value = SMA
        sma = (Decimal("2") + Decimal("4") + Decimal("6")) / Decimal("3")
        result = ema.update(Decimal("6"))
        assert result == sma  # 4

        # Subsequent EMA values
        expected = Decimal("8") * k + sma * (Decimal("1") - k)
        result = ema.update(Decimal("8"))
        assert result == expected  # 6

        expected2 = Decimal("10") * k + expected * (Decimal("1") - k)
        result = ema.update(Decimal("10"))
        assert result == expected2  # 8

        expected3 = Decimal("12") * k + expected2 * (Decimal("1") - k)
        result = ema.update(Decimal("12"))
        assert result == expected3  # 10

    def test_ema_value_property_matches_last_update(self) -> None:
        """Test value property matches the most recent update result."""
        ema = EMAIndicator(period=3)
        ema.update(Decimal("10"))
        ema.update(Decimal("20"))
        result = ema.update(Decimal("30"))
        assert ema.value == result

        result2 = ema.update(Decimal("40"))
        assert ema.value == result2

    def test_ema_with_decimal_precision(self) -> None:
        """Test EMA handles precise Decimal values correctly."""
        ema = EMAIndicator(period=3)
        ema.update(Decimal("42000.12345678"))
        ema.update(Decimal("42100.98765432"))
        result = ema.update(Decimal("42050.55555555"))

        expected_sma = (
            Decimal("42000.12345678")
            + Decimal("42100.98765432")
            + Decimal("42050.55555555")
        ) / Decimal("3")
        assert result == expected_sma


class TestEMAConvergence:
    """Tests for EMA convergence behavior."""

    def test_converges_toward_new_level(self) -> None:
        """Test EMA converges toward a new constant price level."""
        ema = EMAIndicator(period=5)

        # Initialize at 100
        for _ in range(5):
            ema.update(Decimal("100"))

        # Switch to 200 and verify convergence
        prev_distance = abs(Decimal("200") - ema.value)
        for _ in range(20):
            result = ema.update(Decimal("200"))
            current_distance = abs(Decimal("200") - result)
            assert current_distance <= prev_distance
            prev_distance = current_distance

        # After many updates at 200, EMA should be very close to 200
        assert abs(ema.value - Decimal("200")) < Decimal("0.1")

    def test_shorter_period_converges_faster(self) -> None:
        """Test shorter period EMA converges faster than longer period."""
        ema_short = EMAIndicator(period=3)
        ema_long = EMAIndicator(period=10)

        # Initialize both at 100
        for _ in range(10):
            ema_short.update(Decimal("100"))
            ema_long.update(Decimal("100"))

        # Feed 200 to both for a few steps
        for _ in range(5):
            ema_short.update(Decimal("200"))
            ema_long.update(Decimal("200"))

        # Short period EMA should be closer to 200
        short_distance = abs(Decimal("200") - ema_short.value)
        long_distance = abs(Decimal("200") - ema_long.value)
        assert short_distance < long_distance

    def test_ema_responds_to_rising_prices(self) -> None:
        """Test EMA follows an upward trend but lags behind."""
        ema = EMAIndicator(period=5)

        # Initialize
        for _ in range(5):
            ema.update(Decimal("100"))

        # Feed rising prices
        for i in range(1, 11):
            price = Decimal("100") + Decimal(str(i * 10))
            result = ema.update(price)
            # EMA should lag behind the current price in an uptrend
            assert result < price


class TestEMAReset:
    """Tests for reset functionality."""

    def test_reset_clears_value(self) -> None:
        """Test reset sets value back to None."""
        ema = EMAIndicator(period=3)
        ema.update(Decimal("10"))
        ema.update(Decimal("20"))
        ema.update(Decimal("30"))
        assert ema.value is not None

        ema.reset()
        assert ema.value is None

    def test_reset_clears_is_ready(self) -> None:
        """Test reset sets is_ready back to False."""
        ema = EMAIndicator(period=3)
        ema.update(Decimal("10"))
        ema.update(Decimal("20"))
        ema.update(Decimal("30"))
        assert ema.is_ready is True

        ema.reset()
        assert ema.is_ready is False

    def test_reset_allows_reuse(self) -> None:
        """Test indicator can be reused after reset with new data."""
        ema = EMAIndicator(period=3)

        # First usage
        ema.update(Decimal("10"))
        ema.update(Decimal("20"))
        first_result = ema.update(Decimal("30"))

        ema.reset()

        # Second usage with same data should yield same result
        ema.update(Decimal("10"))
        ema.update(Decimal("20"))
        second_result = ema.update(Decimal("30"))

        assert first_result == second_result

    def test_reset_requires_full_warmup_again(self) -> None:
        """Test reset requires full warmup period before producing values."""
        ema = EMAIndicator(period=5)

        # Warm up and get a value
        for _ in range(5):
            ema.update(Decimal("100"))
        assert ema.is_ready is True

        ema.reset()

        # Need full warmup again
        for i in range(4):
            result = ema.update(Decimal("100"))
            assert result is None, f"Expected None at update {i + 1} after reset"

        result = ema.update(Decimal("100"))
        assert result is not None


class TestEMAWarmupPeriods:
    """Tests for warmup_periods property."""

    def test_warmup_periods_equals_period(self) -> None:
        """Test warmup_periods returns the configured period."""
        ema = EMAIndicator(period=10)
        assert ema.warmup_periods == 10

    def test_warmup_periods_unchanged_after_updates(self) -> None:
        """Test warmup_periods does not change after processing data."""
        ema = EMAIndicator(period=5)
        assert ema.warmup_periods == 5

        for _ in range(10):
            ema.update(Decimal("100"))

        assert ema.warmup_periods == 5

    def test_warmup_periods_unchanged_after_reset(self) -> None:
        """Test warmup_periods does not change after reset."""
        ema = EMAIndicator(period=7)
        for _ in range(10):
            ema.update(Decimal("100"))

        ema.reset()
        assert ema.warmup_periods == 7
