"""Tests for GeminiGlobalRiskManager.

This module tests:
- Position sizing (1% rule)
- ATR-based stop-loss calculation
- Crash protector (detection, suspension, recovery)
- Crash sell signal generation
- Signal processing pipeline (BUY enrichment, SELL passthrough, rejections)
- Strategy budget validation
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from unittest.mock import MagicMock

import pytest

from krakenbot.models.base import SignalType
from krakenbot.strategies.base import TradingSignal
from krakenbot.strategies.gemini_global_risk_manager import (
    GeminiGlobalRiskManager,
    PriceSnapshot,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_signal(
    signal_type: SignalType = SignalType.BUY,
    price: Decimal = Decimal("50000"),
    confidence: float = 0.8,
    strategy: str = "test_strategy",
    metadata: dict | None = None,
) -> TradingSignal:
    """Build a TradingSignal for testing."""
    return TradingSignal(
        signal_type=signal_type,
        pair="XBT/USDC",
        price=price,
        confidence=confidence,
        reason="test signal",
        strategy=strategy,
        timestamp=datetime.now(UTC),
        metadata=metadata or {"order_type": "limit", "position_size_multiplier": 1.0},
    )


def _make_analyzer(atr_value: Decimal | None = Decimal("500")) -> MagicMock:
    """Build a mock MultiTimeframeAnalyzer with configurable ATR."""
    analyzer = MagicMock()
    analyzer.get_atr.return_value = atr_value
    return analyzer


# ---------------------------------------------------------------------------
# TestPositionSizing
# ---------------------------------------------------------------------------


class TestPositionSizing:
    """Tests for 1% rule position sizing."""

    def test_basic_calculation(self) -> None:
        """1% of 10000 USDC = 100 risk, entry-SL = 1500 -> size = 100/1500."""
        rm = GeminiGlobalRiskManager()
        size = rm.calculate_position_size(
            capital=Decimal("10000"),
            entry_price=Decimal("50000"),
            stop_loss_price=Decimal("48500"),
        )
        # max_loss = 10000 * 1% = 100, risk_per_unit = 1500
        expected = Decimal("100") / Decimal("1500")
        assert float(size) == pytest.approx(float(expected), rel=1e-6)

    def test_zero_capital_returns_zero(self) -> None:
        rm = GeminiGlobalRiskManager()
        size = rm.calculate_position_size(
            capital=Decimal("0"),
            entry_price=Decimal("50000"),
            stop_loss_price=Decimal("48500"),
        )
        assert size == Decimal("0")

    def test_negative_capital_returns_zero(self) -> None:
        rm = GeminiGlobalRiskManager()
        size = rm.calculate_position_size(
            capital=Decimal("-1000"),
            entry_price=Decimal("50000"),
            stop_loss_price=Decimal("48500"),
        )
        assert size == Decimal("0")

    def test_entry_equals_sl_returns_zero(self) -> None:
        """When entry == stop_loss, risk per unit is 0 -> divide by zero guard."""
        rm = GeminiGlobalRiskManager()
        size = rm.calculate_position_size(
            capital=Decimal("10000"),
            entry_price=Decimal("50000"),
            stop_loss_price=Decimal("50000"),
        )
        assert size == Decimal("0")

    def test_zero_entry_price_returns_zero(self) -> None:
        rm = GeminiGlobalRiskManager()
        size = rm.calculate_position_size(
            capital=Decimal("10000"),
            entry_price=Decimal("0"),
            stop_loss_price=Decimal("0"),
        )
        assert size == Decimal("0")

    def test_custom_risk_pct(self) -> None:
        """2% risk per trade doubles the position size."""
        rm = GeminiGlobalRiskManager({"risk_per_trade_pct": 2.0})
        size = rm.calculate_position_size(
            capital=Decimal("10000"),
            entry_price=Decimal("50000"),
            stop_loss_price=Decimal("48500"),
        )
        expected = Decimal("200") / Decimal("1500")
        assert float(size) == pytest.approx(float(expected), rel=1e-6)

    def test_uses_abs_of_entry_minus_sl(self) -> None:
        """Position sizing works even if SL > entry (short scenario)."""
        rm = GeminiGlobalRiskManager()
        size = rm.calculate_position_size(
            capital=Decimal("10000"),
            entry_price=Decimal("48500"),
            stop_loss_price=Decimal("50000"),
        )
        expected = Decimal("100") / Decimal("1500")
        assert float(size) == pytest.approx(float(expected), rel=1e-6)


# ---------------------------------------------------------------------------
# TestATRStopLoss
# ---------------------------------------------------------------------------


class TestATRStopLoss:
    """Tests for ATR-based stop-loss calculation."""

    def test_basic_calculation(self) -> None:
        """SL = entry - multiplier * ATR = 50000 - 3 * 500 = 48500."""
        rm = GeminiGlobalRiskManager()
        sl = rm.calculate_stop_loss(
            entry_price=Decimal("50000"),
            atr=Decimal("500"),
        )
        assert sl == Decimal("48500")

    def test_custom_multiplier(self) -> None:
        """Custom multiplier overrides default."""
        rm = GeminiGlobalRiskManager()
        sl = rm.calculate_stop_loss(
            entry_price=Decimal("50000"),
            atr=Decimal("500"),
            multiplier=Decimal("2"),
        )
        assert sl == Decimal("49000")

    def test_sl_cannot_be_negative(self) -> None:
        """When ATR * multiplier > entry, SL is clamped to 0."""
        rm = GeminiGlobalRiskManager()
        sl = rm.calculate_stop_loss(
            entry_price=Decimal("100"),
            atr=Decimal("200"),
            multiplier=Decimal("3"),
        )
        assert sl == Decimal("0")

    def test_default_multiplier_from_config(self) -> None:
        """Config multiplier is used when no override provided."""
        rm = GeminiGlobalRiskManager({"atr_sl_multiplier": 2.5})
        sl = rm.calculate_stop_loss(
            entry_price=Decimal("50000"),
            atr=Decimal("1000"),
        )
        assert sl == Decimal("47500")

    def test_zero_atr(self) -> None:
        """Zero ATR means SL = entry."""
        rm = GeminiGlobalRiskManager()
        sl = rm.calculate_stop_loss(
            entry_price=Decimal("50000"),
            atr=Decimal("0"),
        )
        assert sl == Decimal("50000")


# ---------------------------------------------------------------------------
# TestCrashProtector
# ---------------------------------------------------------------------------


class TestCrashProtector:
    """Tests for crash detection and suspension."""

    def test_no_crash_with_empty_history(self) -> None:
        rm = GeminiGlobalRiskManager()
        assert rm.check_crash_protector() is False

    def test_no_crash_with_single_price(self) -> None:
        rm = GeminiGlobalRiskManager()
        now = datetime.now(UTC)
        rm.update_price(Decimal("50000"), now)
        assert rm.check_crash_protector(now) is False

    def test_no_crash_with_stable_prices(self) -> None:
        rm = GeminiGlobalRiskManager()
        base = datetime(2024, 1, 15, 12, 0, 0, tzinfo=UTC)
        for i in range(10):
            rm.update_price(Decimal("50000"), base + timedelta(minutes=i))
        assert rm.check_crash_protector(base + timedelta(minutes=10)) is False

    def test_crash_detected_7pct_drop(self) -> None:
        """A 7% drop within 30 minutes triggers crash protector."""
        rm = GeminiGlobalRiskManager()
        base = datetime(2024, 1, 15, 12, 0, 0, tzinfo=UTC)

        # Start at 50000, drop to 46500 (7% drop)
        rm.update_price(Decimal("50000"), base)
        rm.update_price(Decimal("48000"), base + timedelta(minutes=10))
        rm.update_price(Decimal("46500"), base + timedelta(minutes=20))

        assert rm.check_crash_protector(base + timedelta(minutes=20)) is True

    def test_crash_not_triggered_under_threshold(self) -> None:
        """A 5% drop does NOT trigger the 7% threshold."""
        rm = GeminiGlobalRiskManager()
        base = datetime(2024, 1, 15, 12, 0, 0, tzinfo=UTC)

        rm.update_price(Decimal("50000"), base)
        rm.update_price(Decimal("47500"), base + timedelta(minutes=20))  # 5% drop

        assert rm.check_crash_protector(base + timedelta(minutes=20)) is False

    def test_crash_suspension_lasts_2hours(self) -> None:
        """After crash, protector stays active for 2 hours from trigger time."""
        rm = GeminiGlobalRiskManager()
        base = datetime(2024, 1, 15, 12, 0, 0, tzinfo=UTC)

        rm.update_price(Decimal("50000"), base)
        rm.update_price(Decimal("46000"), base + timedelta(minutes=10))  # 8% drop

        # Trigger at base+10min -> _suspended_until = base+10min+2h = base+2h10min
        trigger_time = base + timedelta(minutes=10)
        assert rm.check_crash_protector(trigger_time) is True

        # Still suspended 1h after trigger
        assert rm.check_crash_protector(trigger_time + timedelta(hours=1)) is True

        # Not suspended after 2h+ from trigger time
        assert rm.check_crash_protector(trigger_time + timedelta(hours=2, minutes=1)) is False

    def test_crash_recovery_clears_state(self) -> None:
        """Crash state clears when drop recovers to < threshold/2."""
        rm = GeminiGlobalRiskManager()
        base = datetime(2024, 1, 15, 12, 0, 0, tzinfo=UTC)

        rm.update_price(Decimal("50000"), base)
        rm.update_price(Decimal("46000"), base + timedelta(minutes=5))

        # Trigger crash
        rm.check_crash_protector(base + timedelta(minutes=5))
        assert rm._crash_active is True

        # After suspension expires (trigger+2h = base+2h5m), add recovery prices
        # Need at least 2 prices within the 30-min window for crash check to evaluate
        recovery_time = base + timedelta(hours=3)
        rm.update_price(Decimal("49800"), recovery_time - timedelta(minutes=5))
        rm.update_price(Decimal("49500"), recovery_time)
        rm.check_crash_protector(recovery_time)

        # Crash state should be cleared (drop from 49800 to 49500 < 3.5%)
        assert rm._crash_active is False

    def test_custom_crash_threshold(self) -> None:
        """Custom threshold changes sensitivity."""
        rm = GeminiGlobalRiskManager({"crash_threshold_pct": 5.0})
        base = datetime(2024, 1, 15, 12, 0, 0, tzinfo=UTC)

        rm.update_price(Decimal("50000"), base)
        rm.update_price(Decimal("47400"), base + timedelta(minutes=10))  # 5.2% drop

        assert rm.check_crash_protector(base + timedelta(minutes=10)) is True

    def test_update_price_stores_snapshots(self) -> None:
        rm = GeminiGlobalRiskManager()
        now = datetime.now(UTC)
        rm.update_price(Decimal("50000"), now)
        rm.update_price(Decimal("51000"), now + timedelta(minutes=1))
        assert len(rm._price_history) == 2
        assert rm._price_history[0].price == Decimal("50000")
        assert rm._price_history[1].price == Decimal("51000")

    def test_prices_outside_window_ignored(self) -> None:
        """Only prices within the 30-min window count."""
        rm = GeminiGlobalRiskManager()
        base = datetime(2024, 1, 15, 12, 0, 0, tzinfo=UTC)

        # Old high price (outside window)
        rm.update_price(Decimal("60000"), base)
        # Recent prices (within window)
        rm.update_price(Decimal("50000"), base + timedelta(minutes=40))
        rm.update_price(Decimal("49000"), base + timedelta(minutes=50))  # 2% from 50000

        # Should NOT crash: the 60000 is outside the 30-min window
        assert rm.check_crash_protector(base + timedelta(minutes=50)) is False


# ---------------------------------------------------------------------------
# TestGenerateCrashSells
# ---------------------------------------------------------------------------


class TestGenerateCrashSells:
    """Tests for crash sell signal generation."""

    def test_empty_positions_returns_empty(self) -> None:
        rm = GeminiGlobalRiskManager()
        signals = rm.generate_crash_sells([], Decimal("50000"))
        assert signals == []

    def test_closes_50pct_of_positions(self) -> None:
        """4 positions -> 50% -> 2 signals."""
        rm = GeminiGlobalRiskManager()
        positions = [
            {"bot_id": f"s{i}", "position_id": i, "amount_btc": "0.1", "entry_price": "48000"}
            for i in range(4)
        ]
        signals = rm.generate_crash_sells(positions, Decimal("50000"))
        assert len(signals) == 2

    def test_single_position_still_generates_signal(self) -> None:
        """1 position -> at least 1 signal."""
        rm = GeminiGlobalRiskManager()
        positions = [
            {"bot_id": "s1", "position_id": 1, "amount_btc": "0.1", "entry_price": "48000"}
        ]
        signals = rm.generate_crash_sells(positions, Decimal("50000"))
        assert len(signals) == 1

    def test_prioritizes_largest_positions(self) -> None:
        """Largest positions (by value) are closed first."""
        rm = GeminiGlobalRiskManager()
        positions = [
            {"bot_id": "small", "position_id": 1, "amount_btc": "0.01", "entry_price": "48000"},
            {"bot_id": "big", "position_id": 2, "amount_btc": "1.0", "entry_price": "48000"},
            {"bot_id": "medium", "position_id": 3, "amount_btc": "0.1", "entry_price": "48000"},
        ]
        signals = rm.generate_crash_sells(positions, Decimal("50000"))
        # 3 positions * 0.5 = 1.5 -> round up to 2
        assert len(signals) == 2
        # First signal should be the biggest position
        assert signals[0].strategy == "big"
        assert signals[1].strategy == "medium"

    def test_signal_metadata_is_market_order(self) -> None:
        rm = GeminiGlobalRiskManager()
        positions = [
            {"bot_id": "s1", "position_id": 42, "amount_btc": "0.1", "entry_price": "48000"}
        ]
        signals = rm.generate_crash_sells(positions, Decimal("50000"))
        assert signals[0].metadata["order_type"] == "market"
        assert signals[0].metadata["crash_sell"] is True
        assert signals[0].metadata["position_id"] == 42

    def test_signal_type_is_sell(self) -> None:
        rm = GeminiGlobalRiskManager()
        positions = [
            {"bot_id": "s1", "position_id": 1, "amount_btc": "0.1", "entry_price": "48000"}
        ]
        signals = rm.generate_crash_sells(positions, Decimal("50000"))
        assert signals[0].signal_type == SignalType.SELL
        assert signals[0].confidence == 1.0


# ---------------------------------------------------------------------------
# TestProcessSignal
# ---------------------------------------------------------------------------


class TestProcessSignal:
    """Tests for the main signal processing pipeline."""

    def test_sell_signal_passes_through(self) -> None:
        rm = GeminiGlobalRiskManager()
        signal = _make_signal(signal_type=SignalType.SELL)
        analyzer = _make_analyzer()

        result = rm.process_signal(signal, Decimal("10000"), analyzer)
        assert result is signal  # Same object, unchanged

    def test_hold_signal_passes_through(self) -> None:
        rm = GeminiGlobalRiskManager()
        signal = _make_signal(signal_type=SignalType.HOLD)
        analyzer = _make_analyzer()

        result = rm.process_signal(signal, Decimal("10000"), analyzer)
        assert result is signal

    def test_buy_signal_enriched_with_risk_metadata(self) -> None:
        rm = GeminiGlobalRiskManager()
        signal = _make_signal(signal_type=SignalType.BUY, price=Decimal("50000"))
        analyzer = _make_analyzer(atr_value=Decimal("500"))

        result = rm.process_signal(signal, Decimal("10000"), analyzer)

        assert result is not None
        assert result.signal_type == SignalType.BUY
        assert "risk_stop_loss" in result.metadata
        assert "risk_atr" in result.metadata
        assert "risk_atr_multiplier" in result.metadata
        assert "risk_position_size_btc" in result.metadata
        assert "risk_max_loss_pct" in result.metadata

        # Verify SL = 50000 - 3*500 = 48500
        assert result.metadata["risk_stop_loss"] == pytest.approx(48500.0)
        assert result.metadata["risk_atr"] == pytest.approx(500.0)

    def test_buy_blocked_during_crash(self) -> None:
        rm = GeminiGlobalRiskManager()
        now = datetime.now(UTC)

        # Trigger crash with recent timestamps (process_signal uses datetime.now)
        rm.update_price(Decimal("50000"), now - timedelta(minutes=10))
        rm.update_price(Decimal("46000"), now)
        rm.check_crash_protector(now)

        signal = _make_signal(signal_type=SignalType.BUY)
        analyzer = _make_analyzer()

        result = rm.process_signal(signal, Decimal("10000"), analyzer)
        assert result is None

    def test_buy_blocked_when_no_atr(self) -> None:
        rm = GeminiGlobalRiskManager()
        signal = _make_signal(signal_type=SignalType.BUY)
        analyzer = _make_analyzer(atr_value=None)

        result = rm.process_signal(signal, Decimal("10000"), analyzer)
        assert result is None

    def test_buy_blocked_when_atr_zero(self) -> None:
        rm = GeminiGlobalRiskManager()
        signal = _make_signal(signal_type=SignalType.BUY, price=Decimal("50000"))
        analyzer = _make_analyzer(atr_value=Decimal("0"))

        result = rm.process_signal(signal, Decimal("10000"), analyzer)
        assert result is None

    def test_buy_blocked_when_zero_position_size(self) -> None:
        """Zero capital -> zero position size -> blocked."""
        rm = GeminiGlobalRiskManager()
        signal = _make_signal(signal_type=SignalType.BUY, price=Decimal("50000"))
        analyzer = _make_analyzer(atr_value=Decimal("500"))

        result = rm.process_signal(signal, Decimal("0"), analyzer)
        assert result is None

    def test_position_size_multiplier_conservative(self) -> None:
        """Risk manager uses the smaller of original and risk-derived multiplier."""
        rm = GeminiGlobalRiskManager()
        signal = _make_signal(
            signal_type=SignalType.BUY,
            price=Decimal("50000"),
            metadata={"order_type": "limit", "position_size_multiplier": 0.5},
        )
        analyzer = _make_analyzer(atr_value=Decimal("500"))

        result = rm.process_signal(signal, Decimal("10000"), analyzer)
        assert result is not None
        # Risk multiplier = (position_size_btc * entry) / capital
        # Should take min(0.5, risk_multiplier)
        assert result.metadata["position_size_multiplier"] <= 0.5

    def test_original_signal_not_mutated(self) -> None:
        """process_signal creates a new signal, original is unchanged."""
        rm = GeminiGlobalRiskManager()
        original_metadata = {"order_type": "limit", "position_size_multiplier": 1.0}
        signal = _make_signal(
            signal_type=SignalType.BUY,
            price=Decimal("50000"),
            metadata=original_metadata.copy(),
        )
        analyzer = _make_analyzer(atr_value=Decimal("500"))

        result = rm.process_signal(signal, Decimal("10000"), analyzer)
        assert result is not None
        assert "risk_stop_loss" not in signal.metadata


# ---------------------------------------------------------------------------
# TestStrategyBudget
# ---------------------------------------------------------------------------


class TestStrategyBudget:
    """Tests for strategy budget validation."""

    def test_within_budget_returns_true(self) -> None:
        rm = GeminiGlobalRiskManager()
        assert rm.check_strategy_budget(
            strategy_name="test",
            order_size_usdc=Decimal("100"),
            current_exposure_usdc=Decimal("400"),
            total_capital=Decimal("10000"),
            max_allocation_pct=Decimal("10"),  # 10% = 1000 USDC budget
        ) is True

    def test_over_budget_returns_false(self) -> None:
        rm = GeminiGlobalRiskManager()
        assert rm.check_strategy_budget(
            strategy_name="test",
            order_size_usdc=Decimal("200"),
            current_exposure_usdc=Decimal("900"),
            total_capital=Decimal("10000"),
            max_allocation_pct=Decimal("10"),  # budget = 1000, exposure would be 1100
        ) is False

    def test_exactly_at_budget_passes(self) -> None:
        rm = GeminiGlobalRiskManager()
        assert rm.check_strategy_budget(
            strategy_name="test",
            order_size_usdc=Decimal("100"),
            current_exposure_usdc=Decimal("900"),
            total_capital=Decimal("10000"),
            max_allocation_pct=Decimal("10"),  # budget = 1000, exposure = 1000
        ) is True

    def test_zero_capital_returns_false(self) -> None:
        rm = GeminiGlobalRiskManager()
        assert rm.check_strategy_budget(
            strategy_name="test",
            order_size_usdc=Decimal("100"),
            current_exposure_usdc=Decimal("0"),
            total_capital=Decimal("0"),
            max_allocation_pct=Decimal("10"),
        ) is False

    def test_negative_capital_returns_false(self) -> None:
        rm = GeminiGlobalRiskManager()
        assert rm.check_strategy_budget(
            strategy_name="test",
            order_size_usdc=Decimal("100"),
            current_exposure_usdc=Decimal("0"),
            total_capital=Decimal("-1000"),
            max_allocation_pct=Decimal("10"),
        ) is False


# ---------------------------------------------------------------------------
# TestGetConfig
# ---------------------------------------------------------------------------


class TestGetConfig:
    """Tests for configuration reporting."""

    def test_returns_all_keys(self) -> None:
        rm = GeminiGlobalRiskManager()
        config = rm.get_config()
        expected_keys = {
            "risk_per_trade_pct",
            "atr_sl_multiplier",
            "atr_sl_timeframe",
            "atr_sl_period",
            "crash_threshold_pct",
            "crash_window_min",
            "crash_close_pct",
            "crash_suspend_hours",
            "is_suspended",
        }
        assert set(config.keys()) == expected_keys

    def test_default_config_values(self) -> None:
        rm = GeminiGlobalRiskManager()
        config = rm.get_config()
        assert config["risk_per_trade_pct"] == 1.0
        assert config["atr_sl_multiplier"] == 3.0
        assert config["atr_sl_timeframe"] == "4h"
        assert config["atr_sl_period"] == 14
        assert config["crash_threshold_pct"] == 7.0
        assert config["crash_window_min"] == 30
        assert config["crash_close_pct"] == 0.5
        assert config["crash_suspend_hours"] == 2
        assert config["is_suspended"] is False

    def test_custom_config_values(self) -> None:
        rm = GeminiGlobalRiskManager({
            "risk_per_trade_pct": 2.0,
            "atr_sl_multiplier": 2.5,
            "crash_threshold_pct": 5.0,
        })
        config = rm.get_config()
        assert config["risk_per_trade_pct"] == 2.0
        assert config["atr_sl_multiplier"] == 2.5
        assert config["crash_threshold_pct"] == 5.0


# ---------------------------------------------------------------------------
# TestPriceSnapshot
# ---------------------------------------------------------------------------


class TestPriceSnapshot:
    """Tests for PriceSnapshot dataclass."""

    def test_creation(self) -> None:
        now = datetime.now(UTC)
        snap = PriceSnapshot(price=Decimal("50000"), timestamp=now)
        assert snap.price == Decimal("50000")
        assert snap.timestamp == now
