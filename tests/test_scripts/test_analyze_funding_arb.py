"""Unit tests for the funding rate arb analysis script.

Tests the pure computation functions (analyze_distribution, simulate_strategy)
with synthetic data — no API keys or network access required.
"""

from __future__ import annotations

from pathlib import Path
import sys

import pytest

# Add scripts dir to path so we can import the analysis module
scripts_dir = Path(__file__).parent.parent.parent / "scripts"
sys.path.insert(0, str(scripts_dir))

from analyze_funding_arb_kraken import (  # noqa: E402
    analyze_distribution,
    simulate_strategy,
)


def test_analyze_distribution_basic() -> None:
    """Test distribution stats on simple fake data."""
    rates = [
        {"timestamp": 1000, "rate": 0.0001},
        {"timestamp": 2000, "rate": 0.0002},
        {"timestamp": 3000, "rate": -0.0001},
        {"timestamp": 4000, "rate": 0.0},
    ]
    result = analyze_distribution(rates)
    assert result["count"] == 4
    assert result["positive_count"] == 2
    assert result["negative_count"] == 1
    assert result["zero_count"] == 1
    assert result["positive_pct"] == pytest.approx(50.0)


def test_analyze_distribution_empty() -> None:
    """Test distribution with no data returns empty dict."""
    result = analyze_distribution([])
    assert result == {}


def test_simulate_strategy_profitable() -> None:
    """Test with consistently high positive funding -> should be profitable."""
    rates = [
        {"timestamp": i * 3600000, "rate": 0.0002}  # 0.02% / hour, high
        for i in range(1000)  # ~42 days
    ]
    result = simulate_strategy(rates)
    assert result["num_open_trades"] >= 1
    assert result["annualized_apr"] > 0


def test_simulate_strategy_negative_funding() -> None:
    """Test with consistently negative funding -> no trades should open."""
    rates = [{"timestamp": i * 3600000, "rate": -0.0001} for i in range(1000)]
    result = simulate_strategy(rates)
    assert result["num_open_trades"] == 0
    assert result["net_pnl"] == 0


def test_simulate_strategy_break_even_duration() -> None:
    """Verify entry/exit logic with mixed rates."""
    # 50 hours of positive funding, then 50 hours of negative -> triggers close
    rates = [{"timestamp": i * 3600000, "rate": 0.0001} for i in range(50)] + [
        {"timestamp": i * 3600000, "rate": -0.0001} for i in range(50, 100)
    ]
    result = simulate_strategy(rates)
    # Should open one trade at the beginning, close it when rate drops
    assert result["num_open_trades"] >= 1
    assert result["num_close_trades"] >= 1


def test_simulate_strategy_empty() -> None:
    """Test simulation with no data returns empty dict."""
    result = simulate_strategy([])
    assert result == {}
