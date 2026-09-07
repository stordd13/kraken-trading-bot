"""Unit tests for scripts/p7_report.py — aggregation + selection + report."""

# ruff: noqa: E402
from __future__ import annotations

import json
from pathlib import Path
import sys

_project_root = str(Path(__file__).resolve().parent.parent.parent)
sys.path.insert(0, _project_root)
sys.path.insert(0, str(Path(_project_root) / "scripts"))

import pytest

from scripts import p7_report as r

# ---------------------------------------------------------------------------
# Aggregation
# ---------------------------------------------------------------------------


def _wf_entry(
    strategy: str,
    pair: str,
    params_hash: str,
    window_idx: int,
    *,
    train_sharpe: float = 0.5,
    test_sharpe: float = 0.5,
    test_pf: float = 1.5,
    test_trades: int = 30,
    test_dd: float = 10.0,
    params: dict | None = None,
) -> tuple[str, dict]:
    """Build (key, value) tuple for a phase-2 entry."""
    pair_norm = pair.replace("/", "_")
    key = f"{strategy}_{pair_norm}_p2_{params_hash}_w{window_idx}"
    value = {
        "strategy": strategy,
        "pair": pair,
        "params": params or {"a": 1},
        "phase": "2",
        "window_idx": window_idx,
        "period": {
            "train_start": "2024-01-01T00:00:00+00:00",
            "train_end": "2025-01-01T00:00:00+00:00",
            "test_start": "2025-01-01T00:00:00+00:00",
            "test_end": "2025-04-01T00:00:00+00:00",
        },
        "train": {"sharpe_ratio": train_sharpe, "total_trades": 50},
        "test": {
            "sharpe_ratio": test_sharpe,
            "profit_factor": test_pf,
            "total_trades": test_trades,
            "max_drawdown_pct": test_dd,
        },
    }
    return key, value


class TestAggregateWalkForward:
    def test_groups_by_combo_and_params(self) -> None:
        results = dict(
            [_wf_entry("s1", "BTC/USDC", "abc12345", i, test_sharpe=0.5) for i in range(1, 9)]
            + [_wf_entry("s2", "BTC/USDC", "def67890", 1)]
        )
        aggs = r.aggregate_walk_forward(results)
        assert len(aggs) == 2
        assert ("s1", "BTC/USDC", "abc12345") in aggs
        assert ("s2", "BTC/USDC", "def67890") in aggs

    def test_mean_sharpe_oos(self) -> None:
        results = dict(
            [_wf_entry("s", "BTC/USDC", "h1", i, test_sharpe=float(i)) for i in range(1, 9)]
        )
        agg = r.aggregate_walk_forward(results)[("s", "BTC/USDC", "h1")]
        # Sharpes 1..8 → mean = 4.5
        assert agg.mean_sharpe_oos == pytest.approx(4.5)

    def test_consistency_counts_positive(self) -> None:
        results = dict(
            [
                _wf_entry("s", "BTC/USDC", "h1", i, test_sharpe=(1.0 if i <= 5 else -1.0))
                for i in range(1, 9)
            ]
        )
        agg = r.aggregate_walk_forward(results)[("s", "BTC/USDC", "h1")]
        assert agg.consistency == 5

    def test_max_drawdown_global_is_worst_window(self) -> None:
        results = dict(
            [_wf_entry("s", "BTC/USDC", "h1", i, test_dd=float(i * 5)) for i in range(1, 9)]
        )
        agg = r.aggregate_walk_forward(results)[("s", "BTC/USDC", "h1")]
        assert agg.max_drawdown_global == 40.0  # window 8 had 40%

    def test_skips_failed_entries(self) -> None:
        ok_key, ok_val = _wf_entry("s", "BTC/USDC", "h1", 1)
        results = {
            ok_key: ok_val,
            "fail_key_p2_h2_w1": {
                "strategy": "s",
                "pair": "BTC/USDC",
                "error": "TimeoutError",
            },
        }
        aggs = r.aggregate_walk_forward(results)
        assert len(aggs) == 1


# ---------------------------------------------------------------------------
# Selection criteria
# ---------------------------------------------------------------------------


def _agg(
    *,
    strategy: str = "grok_supertrend_4h",
    pair: str = "BTC/USDC",
    mean_sharpe_train: float = 0.6,
    mean_sharpe_oos: float = 0.5,
    mean_pf_oos: float = 1.5,
    mean_trades_test: float = 30.0,
    max_drawdown_global: float = 10.0,
    consistency: int = 6,
) -> r.WalkForwardAggregate:
    return r.WalkForwardAggregate(
        strategy=strategy,
        pair=pair,
        params={"st_atr_period": 10},
        params_hash="abc12345",
        n_windows=8,
        mean_sharpe_train=mean_sharpe_train,
        mean_sharpe_oos=mean_sharpe_oos,
        std_sharpe_oos=0.1,
        mean_pf_oos=mean_pf_oos,
        mean_trades_test=mean_trades_test,
        max_drawdown_global=max_drawdown_global,
        consistency=consistency,
        per_window=[],
    )


class TestApplySelectionCriteria:
    def test_passes_when_all_criteria_met(self) -> None:
        """ETH Buy&Hold Sharpe = 0.40, so default _agg() (oos=0.5) passes there."""
        v = r.apply_selection_criteria(_agg(pair="ETH/USDC"))
        assert v.passed is True
        assert v.beats_benchmark == "buy_and_hold"

    def test_btc_05_does_not_beat_buy_and_hold(self) -> None:
        """BTC Buy&Hold Sharpe = 0.85. A config with OOS 0.5 must fail criterion 7."""
        v = r.apply_selection_criteria(_agg(mean_sharpe_oos=0.5))
        # passes criteria 1-6 (Sharpe > 0.4) but fails 7 (0.5 < 0.85 and 0.5 < 2.37)
        # → overall FAIL
        assert v.beats_benchmark is None
        assert v.passed is False

    def test_btc_passes_when_beats_buy_and_hold(self) -> None:
        v = r.apply_selection_criteria(_agg(mean_sharpe_oos=1.0))
        # 1.0 > 0.85 ✓, all other criteria ok
        assert v.beats_benchmark == "buy_and_hold"
        assert v.passed is True

    def test_fails_low_sharpe(self) -> None:
        v = r.apply_selection_criteria(_agg(mean_sharpe_oos=0.3))
        assert v.passed is False
        assert any("mean_sharpe_oos" in c.name and not c.passed for c in v.criteria)

    def test_fails_low_pf(self) -> None:
        v = r.apply_selection_criteria(_agg(mean_pf_oos=1.0))
        assert v.passed is False
        assert any("mean_profit_factor" in c.name and not c.passed for c in v.criteria)

    def test_fails_high_drawdown(self) -> None:
        v = r.apply_selection_criteria(_agg(max_drawdown_global=35.0))
        assert v.passed is False
        assert any("max_drawdown" in c.name and not c.passed for c in v.criteria)

    def test_fails_few_trades(self) -> None:
        v = r.apply_selection_criteria(_agg(mean_trades_test=10.0))
        assert v.passed is False
        assert any("mean_trades_test" in c.name and not c.passed for c in v.criteria)

    def test_dca_relaxed_trade_threshold(self) -> None:
        """DCA is allowed >= 5 trades instead of 20."""
        v = r.apply_selection_criteria(
            _agg(
                strategy="grok_adaptive_dca_weekly",
                mean_trades_test=10.0,
                mean_sharpe_oos=1.0,  # ensure other criteria pass
            )
        )
        trade_crit = next(c for c in v.criteria if "trades" in c.name)
        assert trade_crit.passed
        assert trade_crit.threshold == 5.0

    def test_fails_low_consistency(self) -> None:
        v = r.apply_selection_criteria(_agg(consistency=4))
        assert v.passed is False

    def test_fails_overfit(self) -> None:
        # train 2.0 / oos 0.5 → ratio 0.25 < 0.5
        v = r.apply_selection_criteria(_agg(mean_sharpe_train=2.0, mean_sharpe_oos=0.5))
        assert v.passed is False
        assert any("anti-overfit" in c.name and not c.passed for c in v.criteria)

    def test_handles_zero_train_sharpe(self) -> None:
        """train_sharpe = 0 with positive OOS → treated as passing overfit check."""
        v = r.apply_selection_criteria(
            _agg(
                mean_sharpe_train=0.0,
                mean_sharpe_oos=1.0,  # > 0.85 BTC bench
            )
        )
        overfit = next(c for c in v.criteria if "anti-overfit" in c.name)
        assert overfit.passed


# ---------------------------------------------------------------------------
# build_selection
# ---------------------------------------------------------------------------


class TestBuildSelection:
    def test_keeps_best_passing_config_per_combo(self) -> None:
        """When multiple configs pass, the one with highest mean_sharpe_oos wins."""
        aggs = {
            ("grok_supertrend_4h", "BTC/USDC", "h1"): _agg(mean_sharpe_oos=1.0),
            ("grok_supertrend_4h", "BTC/USDC", "h2"): _agg(mean_sharpe_oos=1.5),
            ("grok_supertrend_4h", "BTC/USDC", "h3"): _agg(mean_sharpe_oos=0.5),  # fails bench
        }
        out = r.build_selection(aggs)
        assert len(out["selected_for_paper"]) == 1
        assert out["selected_for_paper"][0]["mean_sharpe_oos"] == 1.5
        assert len(out["abandoned"]) == 0

    def test_abandons_combo_if_no_pass(self) -> None:
        aggs = {
            ("grok_supertrend_4h", "BTC/USDC", "h1"): _agg(mean_sharpe_oos=0.3),
            ("grok_supertrend_4h", "BTC/USDC", "h2"): _agg(mean_sharpe_oos=0.5),
        }
        out = r.build_selection(aggs)
        assert len(out["selected_for_paper"]) == 0
        assert len(out["abandoned"]) == 1
        assert out["abandoned"][0]["strategy"] == "grok_supertrend_4h"
        assert out["abandoned"][0]["pair"] == "BTC/USDC"


# ---------------------------------------------------------------------------
# Markdown generation (smoke)
# ---------------------------------------------------------------------------


class TestGenerateReport:
    def test_generate_report_writes_files(self, tmp_path: Path) -> None:
        phase1 = tmp_path / "P7_phase1.json"
        phase2 = tmp_path / "P7_phase2.json"
        md = tmp_path / "P7_report.md"
        sel = tmp_path / "P7_final.json"

        # Minimal phase1/2 dataset: 1 config × 8 windows on supertrend BTC
        phase2_data = dict(
            [
                _wf_entry(
                    "grok_supertrend_4h",
                    "BTC/USDC",
                    "h1",
                    i,
                    test_sharpe=1.0,  # passes
                    train_sharpe=0.9,
                    test_pf=1.6,
                    test_trades=40,
                    test_dd=8.0,
                )
                for i in range(1, 9)
            ]
        )
        phase1_data = {
            "k1": {
                "strategy": "grok_supertrend_4h",
                "pair": "BTC/USDC",
                "params": {"st_atr_period": 10, "st_multiplier": 3.0},
                "train": {"sharpe_ratio": 0.9},
                "test": {"sharpe_ratio": 1.0, "profit_factor": 1.6, "total_trades": 40},
            }
        }

        phase1.write_text(json.dumps(phase1_data))
        phase2.write_text(json.dumps(phase2_data))

        selection = r.generate_report(phase1, phase2, md, sel)

        assert md.exists()
        assert sel.exists()
        assert len(selection["selected_for_paper"]) == 1
        assert "P7 — Parameter Optimization Report" in md.read_text()
        assert "grok_supertrend_4h" in md.read_text()


# ---------------------------------------------------------------------------
# _extract_params_hash
# ---------------------------------------------------------------------------


class TestExtractParamsHash:
    def test_phase2_key(self) -> None:
        assert r._extract_params_hash("grok_supertrend_4h_BTC_USDC_p2_abc12345_w3") == "abc12345"

    def test_phase1_key(self) -> None:
        assert r._extract_params_hash("grok_supertrend_4h_BTC_USDC_p1_def67890") == "def67890"

    def test_unknown_key(self) -> None:
        assert r._extract_params_hash("bogus_key") == "unknown"
