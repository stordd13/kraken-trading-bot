"""Unit tests for the funding structural analysis script.

Tests the pure computation functions with synthetic data — no API keys needed.
"""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path
import sys

# Add scripts dir to path so we can import the analysis module
scripts_dir = Path(__file__).parent.parent.parent / "scripts"
sys.path.insert(0, str(scripts_dir))

from funding_structural_analysis import (  # noqa: E402
    compute_runs,
    describe_distribution,
    simulate_scenario_a,
    simulate_scenario_b,
    simulate_scenario_c,
)


def test_describe_distribution_basic() -> None:
    """Test distribution stats on simple data."""
    values = [0.0001, 0.0002, -0.0001, 0.0003]
    result = describe_distribution(values, "Test")
    assert result["label"] == "Test"
    assert result["count"] == 4
    assert result["positive_pct"] == 75.0
    assert result["negative_pct"] == 25.0
    assert result["min"] == -0.0001
    assert result["max"] == 0.0003


def test_describe_distribution_empty() -> None:
    """Empty list returns count=0."""
    result = describe_distribution([], "Empty")
    assert result["count"] == 0


def test_compute_runs_basic() -> None:
    """Test run detection with alternating signs."""
    rates = [
        {"timestamp": 1, "rate": 0.001},
        {"timestamp": 2, "rate": 0.002},
        {"timestamp": 3, "rate": -0.001},
        {"timestamp": 4, "rate": -0.002},
        {"timestamp": 5, "rate": 0.001},
    ]
    result = compute_runs(rates)
    assert result["positive"]["count"] == 2
    assert result["positive"]["max_hours"] == 2
    assert result["negative"]["count"] == 1
    assert result["negative"]["max_hours"] == 2


def test_compute_runs_empty() -> None:
    """Empty rates returns zero counts."""
    result = compute_runs([])
    assert result["positive"]["count"] == 0
    assert result["negative"]["count"] == 0


def test_scenario_a_profitable() -> None:
    """Constant positive funding should be profitable in scenario A."""
    rates = [{"timestamp": i, "rate": 0.0001} for i in range(8760)]
    result = simulate_scenario_a(rates, Decimal("1000"), Decimal("0.5"))
    assert result["net_pnl"] > 0


def test_scenario_b_cheaper_fees() -> None:
    """Scenario B should have lower fees than Scenario A for same position."""
    rates = [{"timestamp": i, "rate": 0.0001} for i in range(1000)]
    result_a = simulate_scenario_a(rates, Decimal("1000"), Decimal("0.5"))
    result_b = simulate_scenario_b(rates, Decimal("1000"), Decimal("0.5"))
    assert result_b["total_fees"] < result_a["total_fees"]
    assert result_b["net_pnl"] > result_a["net_pnl"]  # same funding, lower fees


def test_scenario_c_includes_directional() -> None:
    """Scenario C should include directional PnL from BTC price change."""
    rates = [{"timestamp": i, "rate": 0.0001} for i in range(1000)]
    # Simulate BTC going from 50000 to 55000 (+10%)
    result = simulate_scenario_c(
        rates,
        Decimal("1000"),
        Decimal("0.5"),
        price_start=Decimal("50000"),
        price_end=Decimal("55000"),
        leverage=Decimal("3"),
    )
    # With 3x leverage on 500 USDC, 10% move = +30% = 150 USDC directional profit
    assert result["directional_pnl"] > 140
    assert result["directional_pnl"] < 160


def test_scenario_c_negative_direction() -> None:
    """Scenario C with BTC drop should show negative directional PnL."""
    rates = [{"timestamp": i, "rate": 0.0001} for i in range(100)]
    result = simulate_scenario_c(
        rates,
        Decimal("1000"),
        Decimal("0.5"),
        price_start=Decimal("50000"),
        price_end=Decimal("45000"),  # -10%
        leverage=Decimal("3"),
    )
    assert result["directional_pnl"] < 0
