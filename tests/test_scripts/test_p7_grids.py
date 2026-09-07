"""Unit tests for the P7 parameter grids module."""

# ruff: noqa: E402
from __future__ import annotations

from pathlib import Path
import sys

_project_root = str(Path(__file__).resolve().parent.parent.parent)
sys.path.insert(0, _project_root)
sys.path.insert(0, str(Path(_project_root) / "scripts"))

from scripts import p7_grids as g


class TestExpandGrid:
    def test_empty_grid_yields_single_empty_dict(self) -> None:
        assert g.expand_grid({}) == [{}]

    def test_single_axis(self) -> None:
        out = g.expand_grid({"a": [1, 2, 3]})
        assert out == [{"a": 1}, {"a": 2}, {"a": 3}]

    def test_two_axes_cartesian(self) -> None:
        out = g.expand_grid({"a": [1, 2], "b": ["x", "y"]})
        assert len(out) == 4
        assert {"a": 1, "b": "x"} in out
        assert {"a": 2, "b": "y"} in out

    def test_keys_preserve_order(self) -> None:
        out = g.expand_grid({"z": [1], "a": [2], "m": [3]})
        for entry in out:
            assert list(entry.keys()) == ["z", "a", "m"]


class TestGridCardinalities:
    """Verify the documented combo counts match the actual grids."""

    def test_supertrend_grid_20(self) -> None:
        assert len(g.expand_grid(g.SUPERTREND_GRID)) == 20

    def test_grid_atr_grid_48(self) -> None:
        assert len(g.expand_grid(g.GRID_ATR_GRID)) == 48

    def test_dca_grid_48(self) -> None:
        assert len(g.expand_grid(g.DCA_GRID)) == 48

    def test_donchian_grid_8(self) -> None:
        assert len(g.expand_grid(g.DONCHIAN_GRID)) == 8


class TestPhase1Combos:
    def test_total_212(self) -> None:
        assert g.total_phase1_jobs() == 212

    def test_breakdown_per_strategy(self) -> None:
        combos = g.build_phase1_combos()
        by_strat: dict[str, int] = {}
        for strat, _pair, _params in combos:
            by_strat[strat] = by_strat.get(strat, 0) + 1
        assert by_strat["grok_supertrend_4h"] == 60  # 20 × 3 pairs
        assert by_strat["grok_grid_atr_adaptive_v4"] == 96  # 48 × 2 pairs
        assert by_strat["grok_adaptive_dca_weekly"] == 48  # 48 × 1 pair
        assert by_strat["grok_donchian_breakout_4h"] == 8  # 8 × 1 pair

    def test_supertrend_uses_three_pairs(self) -> None:
        combos = g.build_phase1_combos()
        pairs = {pair for strat, pair, _ in combos if strat == "grok_supertrend_4h"}
        assert pairs == {"BTC/USDC", "ETH/USDC", "SOL/USDC"}

    def test_grid_atr_uses_btc_and_sol_only(self) -> None:
        combos = g.build_phase1_combos()
        pairs = {pair for strat, pair, _ in combos if strat == "grok_grid_atr_adaptive_v4"}
        assert pairs == {"BTC/USDC", "SOL/USDC"}

    def test_dca_uses_btc_only(self) -> None:
        combos = g.build_phase1_combos()
        pairs = {pair for strat, pair, _ in combos if strat == "grok_adaptive_dca_weekly"}
        assert pairs == {"BTC/USDC"}

    def test_donchian_uses_sol_only(self) -> None:
        combos = g.build_phase1_combos()
        pairs = {pair for strat, pair, _ in combos if strat == "grok_donchian_breakout_4h"}
        assert pairs == {"SOL/USDC"}

    def test_params_are_real_kwargs(self) -> None:
        """Spot-check that we use the real kwarg names, not the spec aliases."""
        combos = g.build_phase1_combos()
        # SuperTrend uses st_atr_period (not atr_period)
        st_params = next(p for s, _, p in combos if s == "grok_supertrend_4h")
        assert "st_atr_period" in st_params
        assert "st_multiplier" in st_params
        # DCA uses oversold_multiplier (not boost_multiplier)
        dca_params = next(p for s, _, p in combos if s == "grok_adaptive_dca_weekly")
        assert "oversold_multiplier" in dca_params
        assert "bull_reduction" in dca_params
        assert "rsi_oversold" in dca_params
        # Donchian uses donchian_upper_period (not channel_period)
        dc_params = next(p for s, _, p in combos if s == "grok_donchian_breakout_4h")
        assert "donchian_upper_period" in dc_params
        assert "breakout_confirmation" in dc_params
