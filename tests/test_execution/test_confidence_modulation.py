"""Tests for confidence-based position sizing in GeminiGlobalRiskManager.

Validates that:
- Confidence 1.0 → full size (no reduction)
- Confidence 0.5 → 50% size
- Confidence 0.2 → clamped to 0.3 → 30% size
- risk_confidence_factor appears in metadata
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from unittest.mock import MagicMock

from krakenbot.models.base import SignalType
from krakenbot.strategies.base import TradingSignal
from krakenbot.strategies.gemini_global_risk_manager import GeminiGlobalRiskManager


def _make_signal(confidence: float, price: Decimal | None = None) -> TradingSignal:
    """Build a BUY signal with the given confidence."""
    return TradingSignal(
        signal_type=SignalType.BUY,
        pair="BTC/USDC",
        price=price or Decimal("84000"),
        confidence=confidence,
        reason="test-confidence",
        strategy="test_strategy",
        timestamp=datetime.now(UTC),
        metadata={
            "order_type": "limit",
            "position_size_multiplier": 1.0,
        },
    )


def _make_analyzer(atr: Decimal) -> MagicMock:
    """Build a mock analyzer returning a fixed ATR."""
    analyzer = MagicMock()
    analyzer.get_atr.return_value = atr
    return analyzer


class TestConfidenceModulation:
    """Confidence-based position sizing."""

    def _base_size(self, capital: Decimal, entry: Decimal, atr: Decimal) -> Decimal:
        """Calculate the raw 1% rule size without confidence modulation."""
        sl = entry - Decimal("3") * atr
        risk_per_unit = abs(entry - sl)
        return (capital * Decimal("0.01")) / risk_per_unit

    def test_confidence_1_full_size(self) -> None:
        """Confidence 1.0 should give full position size."""
        rm = GeminiGlobalRiskManager()
        capital = Decimal("10000")
        atr = Decimal("3000")
        entry = Decimal("84000")

        signal = _make_signal(1.0, entry)
        result = rm.process_signal(signal, capital, _make_analyzer(atr))

        assert result is not None
        expected = self._base_size(capital, entry, atr) * Decimal("1.0")
        actual = Decimal(str(result.metadata["risk_position_size_btc"]))
        assert abs(actual - expected) < Decimal("1E-10")
        assert result.metadata["risk_confidence_factor"] == 1.0

    def test_confidence_05_half_size(self) -> None:
        """Confidence 0.5 should give 50% of base size."""
        rm = GeminiGlobalRiskManager()
        capital = Decimal("10000")
        atr = Decimal("3000")
        entry = Decimal("84000")

        signal = _make_signal(0.5, entry)
        result = rm.process_signal(signal, capital, _make_analyzer(atr))

        assert result is not None
        expected = self._base_size(capital, entry, atr) * Decimal("0.5")
        actual = Decimal(str(result.metadata["risk_position_size_btc"]))
        assert abs(actual - expected) < Decimal("1E-10")
        assert result.metadata["risk_confidence_factor"] == 0.5

    def test_confidence_02_clamped_to_03(self) -> None:
        """Confidence 0.2 should be clamped to 0.3 minimum."""
        rm = GeminiGlobalRiskManager()
        capital = Decimal("10000")
        atr = Decimal("3000")
        entry = Decimal("84000")

        signal = _make_signal(0.2, entry)
        result = rm.process_signal(signal, capital, _make_analyzer(atr))

        assert result is not None
        expected = self._base_size(capital, entry, atr) * Decimal("0.3")
        actual = Decimal(str(result.metadata["risk_position_size_btc"]))
        assert abs(actual - expected) < Decimal("1E-10")
        assert result.metadata["risk_confidence_factor"] == 0.3

    def test_confidence_0_clamped_to_03(self) -> None:
        """Confidence 0.0 should be clamped to 0.3 minimum."""
        rm = GeminiGlobalRiskManager()
        capital = Decimal("10000")
        atr = Decimal("3000")
        entry = Decimal("84000")

        signal = _make_signal(0.0, entry)
        result = rm.process_signal(signal, capital, _make_analyzer(atr))

        assert result is not None
        assert result.metadata["risk_confidence_factor"] == 0.3

    def test_confidence_09(self) -> None:
        """Confidence 0.9 → factor 0.9."""
        rm = GeminiGlobalRiskManager()
        capital = Decimal("10000")
        atr = Decimal("3000")
        entry = Decimal("84000")

        signal = _make_signal(0.9, entry)
        result = rm.process_signal(signal, capital, _make_analyzer(atr))

        assert result is not None
        expected = self._base_size(capital, entry, atr) * Decimal("0.9")
        actual = Decimal(str(result.metadata["risk_position_size_btc"]))
        assert abs(actual - expected) < Decimal("1E-10")
        assert result.metadata["risk_confidence_factor"] == 0.9

    def test_sell_signal_bypasses_confidence(self) -> None:
        """SELL signals should pass through without confidence modulation."""
        rm = GeminiGlobalRiskManager()
        signal = TradingSignal(
            signal_type=SignalType.SELL,
            pair="BTC/USDC",
            price=Decimal("84000"),
            confidence=0.5,
            reason="test-sell",
            strategy="test_strategy",
            timestamp=datetime.now(UTC),
            metadata={"order_type": "market"},
        )

        result = rm.process_signal(signal, Decimal("10000"), _make_analyzer(Decimal("3000")))
        assert result is not None
        # SELL signals pass through unchanged — no risk_confidence_factor
        assert "risk_confidence_factor" not in result.metadata

    def test_position_size_multiplier_reflects_confidence(self) -> None:
        """position_size_multiplier should be reduced by confidence modulation."""
        rm = GeminiGlobalRiskManager()
        capital = Decimal("10000")
        atr = Decimal("3000")
        entry = Decimal("84000")

        # Full confidence
        sig_full = _make_signal(1.0, entry)
        res_full = rm.process_signal(sig_full, capital, _make_analyzer(atr))

        # Half confidence
        sig_half = _make_signal(0.5, entry)
        res_half = rm.process_signal(sig_half, capital, _make_analyzer(atr))

        assert res_full is not None
        assert res_half is not None

        mult_full = res_full.metadata["position_size_multiplier"]
        mult_half = res_half.metadata["position_size_multiplier"]

        # Half confidence should give approximately half the multiplier
        assert mult_half < mult_full
        assert abs(mult_half / mult_full - 0.5) < 0.01
