"""Unit tests for scripts/p7_report.py — aggregation + selection + report."""

# ruff: noqa: E402
from __future__ import annotations

import json
import math
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


def _wf_entry_v2(
    strategy: str,
    pair: str,
    params_hash: str,
    window_idx: int,
    *,
    train_sharpe: float | None = 0.5,
    test_sharpe: float | None = 0.5,
    gross_profit: float = 15.0,
    gross_loss: float = 10.0,
    test_trades: int = 30,
    test_dd: float = 10.0,
) -> tuple[str, dict]:
    """Phase-2 entry under the C1 contract (metrics_version 2, sums, daily MaxDD)."""
    key, value = _wf_entry(strategy, pair, params_hash, window_idx, test_trades=test_trades)
    value["metrics_version"] = 2
    value["train"] = {"metrics_version": 2, "sharpe_ratio": train_sharpe, "total_trades": 50}
    value["test"] = {
        "metrics_version": 2,
        "sharpe_ratio": test_sharpe,
        "profit_factor": r.profit_factor_from_sums(gross_profit, gross_loss)
        if gross_loss > 0
        else None,
        "gross_profit_net": gross_profit,
        "gross_loss_net": gross_loss,
        "pf_excluded_trades": 0,
        "total_trades": test_trades,
        "max_drawdown_pct_daily": test_dd,
        "max_drawdown_pct_engine": test_dd + 1.0,
    }
    return key, value


class TestAggregateWalkForwardV2:
    """C1: None-aware aggregation, summed profit factor, legacy detection."""

    def test_sharpe_none_windows_are_skipped_with_n_reported(self) -> None:
        sharpes = [0.5, None, 1.0]
        results = dict(
            [
                _wf_entry_v2("s", "BTC/USDC", "h1", i, test_sharpe=x)
                for i, x in enumerate(sharpes, 1)
            ]
        )
        agg = r.aggregate_walk_forward(results)[("s", "BTC/USDC", "h1")]
        assert agg.legacy is False
        assert agg.mean_sharpe_oos == pytest.approx(0.75) and agg.n_sharpe_oos == 2
        assert agg.consistency == 2  # defined and > 0

    def test_all_sharpe_none_propagates_none(self) -> None:
        results = dict(
            [
                _wf_entry_v2("s", "BTC/USDC", "h1", i, test_sharpe=None, train_sharpe=None)
                for i in (1, 2)
            ]
        )
        agg = r.aggregate_walk_forward(results)[("s", "BTC/USDC", "h1")]
        assert agg.mean_sharpe_oos is None and agg.mean_sharpe_train is None
        assert agg.n_sharpe_oos == 0 and agg.consistency == 0
        assert (
            r.apply_selection_criteria(
                agg, benchmarks={"BTC/USDC": {"buy_and_hold": 0.1, "dca_fixed": 0.1}}
            ).passed
            is False
        )

    def test_pf_aggregated_on_the_sums_infinite_window_never_becomes_zero(self) -> None:
        windows = [(10.0, 5.0), (8.0, 0.0), (6.0, 3.0)]  # PF 2, ∞, 2
        results = dict(
            [
                _wf_entry_v2("s", "BTC/USDC", "h1", i, gross_profit=gp, gross_loss=gl)
                for i, (gp, gl) in enumerate(windows, 1)
            ]
        )
        agg = r.aggregate_walk_forward(results)[("s", "BTC/USDC", "h1")]
        assert (agg.gross_profit_net_oos, agg.gross_loss_net_oos) == (24.0, 8.0)
        assert agg.profit_factor_oos == 3.0
        assert agg.n_pf_oos == 2 and agg.mean_pf_oos == 2.0  # diagnostic mean skips the ∞ window
        only_wins = dict(
            [
                _wf_entry_v2("s", "BTC/USDC", "h2", i, gross_profit=5.0, gross_loss=0.0)
                for i in (1, 2)
            ]
        )
        agg2 = r.aggregate_walk_forward(only_wins)[("s", "BTC/USDC", "h2")]
        assert agg2.profit_factor_oos == math.inf and agg2.mean_pf_oos is None
        v = r.apply_selection_criteria(
            agg2, benchmarks={"BTC/USDC": {"buy_and_hold": 0.1, "dca_fixed": 0.1}}
        )
        assert next(c for c in v.criteria if c.name == "profit_factor_oos > 1.3").passed is True

    def test_excluded_lots_make_the_summed_pf_incomplete(self) -> None:
        key, value = _wf_entry_v2("s", "BTC/USDC", "h1", 1, gross_profit=10.0, gross_loss=2.0)
        value["test"]["pf_excluded_trades"] = 2
        agg = r.aggregate_walk_forward({key: value})[("s", "BTC/USDC", "h1")]
        assert agg.pf_excluded_trades_oos == 2 and agg.profit_factor_oos == 5.0
        v = r.apply_selection_criteria(
            agg, benchmarks={"BTC/USDC": {"buy_and_hold": 0.1, "dca_fixed": 0.1}}
        )
        c2 = next(c for c in v.criteria if c.name == "profit_factor_oos > 1.3")
        assert c2.passed is True and "incomplete: 2 lot(s)" in c2.note
        assert r._pf_text(v.to_dict()) == "5.00 (incomplete: 2 excluded)"

    def test_build_selection_ranks_an_undefined_sharpe_last(self) -> None:
        undefined = _agg(pair="ETH/USDC", mean_sharpe_oos=None, params_hash="h_none")
        defined = _agg(pair="ETH/USDC", mean_sharpe_oos=0.5, params_hash="h_ok")
        sel = r.build_selection(
            {("s", "ETH/USDC", "h_none"): undefined, ("s", "ETH/USDC", "h_ok"): defined}
        )
        assert [x["params_hash"] for x in sel["selected_for_paper"]] == ["h_ok"]
        only_none = r.build_selection({("s", "ETH/USDC", "h_none"): undefined})
        assert only_none["selected_for_paper"] == []
        assert only_none["abandoned"][0]["best_sharpe_oos"] is None

    def test_daily_drawdown_key_and_to_dict_keys(self) -> None:
        results = dict(
            [_wf_entry_v2("s", "BTC/USDC", "h1", i, test_dd=float(i * 5)) for i in (1, 2, 3)]
        )
        agg = r.aggregate_walk_forward(results)[("s", "BTC/USDC", "h1")]
        assert agg.max_drawdown_global == 15.0
        d = agg.to_dict()
        assert {
            "profit_factor_oos",
            "gross_profit_net_oos",
            "gross_loss_net_oos",
            "n_pf_oos",
            "n_sharpe_oos",
        } <= set(d)
        assert "mean_profit_factor" not in d

    def test_entries_without_the_sums_take_the_legacy_path(self) -> None:
        results = dict(
            [
                _wf_entry("s", "BTC/USDC", "h1", i, test_pf=float("inf") if i == 2 else 2.0)
                for i in (1, 2, 3)
            ]
        )
        agg = r.aggregate_walk_forward(results)[("s", "BTC/USDC", "h1")]
        assert agg.legacy is True
        assert agg.mean_pf_oos == pytest.approx(
            4.0 / 3
        )  # v1: inf coerced to 0 (defect D4, kept for v1)
        assert agg.profit_factor_oos == agg.mean_pf_oos
        assert "mean_pf_oos" in agg.to_dict() and "profit_factor_oos" not in agg.to_dict()
        verdict = r.apply_selection_criteria(agg).to_dict()
        assert "mean_profit_factor" in verdict and "profit_factor_oos" not in verdict
        mixed = dict([_wf_entry("s", "BTC/USDC", "h1", 1), _wf_entry_v2("s", "BTC/USDC", "h1", 2)])
        assert r.aggregate_walk_forward(mixed)[("s", "BTC/USDC", "h1")].legacy is True


_B4_DIR = Path(__file__).resolve().parent.parent.parent / "results"


@pytest.mark.skipif(
    not (_B4_DIR / "B4_P7_final_selection.json").exists(), reason="B4 campaign files absent"
)
def test_b4_campaign_verdicts_are_reproduced_bit_identically(tmp_path: Path) -> None:
    """C12: the legacy v1 path must reproduce the frozen B4 selection (v1 files, campaign
    benchmarks) — all verdicts, selected / abandoned / ineligible lists and flagged runs."""
    sys.path.insert(0, str(_B4_DIR.parent / "scripts"))
    from scripts import run_p7_grid_search as p7

    bench_path = _B4_DIR / "B4_benchmarks.json"
    selection = r.generate_report(
        _B4_DIR / "B4_P7_phase1_cross_validate.json",
        _B4_DIR / "B4_P7_phase2_walk_forward.json",
        tmp_path / "r.md",
        tmp_path / "s.json",
        benchmarks=p7.load_benchmark_sharpe(bench_path),
        benchmark_details=p7.load_benchmark_details(bench_path),
    )
    produced = json.loads((tmp_path / "s.json").read_text())
    frozen = json.loads((_B4_DIR / "B4_P7_final_selection.json").read_text())
    for key in (
        "all_verdicts",
        "selected_for_paper",
        "abandoned",
        "ineligible_flagged",
        "flagged_runs",
        "benchmarks",
    ):
        assert produced[key] == frozen[key], key
    assert len(selection["all_verdicts"]) == 35 and selection["selected_for_paper"] == []


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
    params_hash: str = "abc12345",
    legacy: bool = False,
    gross_profit: float | None = None,
    gross_loss: float | None = None,
) -> r.WalkForwardAggregate:
    """v2 aggregate whose summed PF equals ``mean_pf_oos`` (gains = pf x 100, losses = 100)
    unless the sums are given; ``legacy=True`` builds a v1 aggregate (mean of PFs)."""
    if not legacy and gross_profit is None and gross_loss is None:
        gross_profit, gross_loss = (mean_pf_oos or 0.0) * 100.0, 100.0
    return r.WalkForwardAggregate(
        strategy=strategy,
        pair=pair,
        params={"st_atr_period": 10},
        params_hash=params_hash,
        n_windows=8,
        mean_sharpe_train=mean_sharpe_train,
        mean_sharpe_oos=mean_sharpe_oos,
        std_sharpe_oos=0.1,
        mean_pf_oos=mean_pf_oos,
        mean_trades_test=mean_trades_test,
        max_drawdown_global=max_drawdown_global,
        consistency=consistency,
        per_window=[],
        legacy=legacy,
        n_sharpe_train=8,
        n_sharpe_oos=8 if mean_sharpe_oos is not None else 0,
        n_pf_oos=8 if mean_pf_oos is not None else 0,
        gross_profit_net_oos=None if legacy else gross_profit,
        gross_loss_net_oos=None if legacy else gross_loss,
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
        assert any(c.name == "profit_factor_oos > 1.3" and not c.passed for c in v.criteria)
        legacy = r.apply_selection_criteria(_agg(mean_pf_oos=1.0, legacy=True))
        assert any(
            c.name == "mean_profit_factor_oos > 1.3" and not c.passed for c in legacy.criteria
        )

    # ---- C1 (metrics_version 2): None-aware criteria on the summed profit factor -----------

    def test_undefined_sharpe_fails_with_a_note_never_a_zero(self) -> None:
        v = r.apply_selection_criteria(_agg(pair="ETH/USDC", mean_sharpe_oos=None))
        assert v.passed is False
        c1 = next(c for c in v.criteria if c.name == "mean_sharpe_oos > 0.4")
        assert c1.passed is False and c1.actual is None and "undefined" in c1.note
        c6 = next(c for c in v.criteria if "anti-overfit" in c.name)
        assert c6.passed is False and c6.actual is None and "undefined" in c6.note
        c7 = next(c for c in v.criteria if c.name == "beats Buy&Hold OR DCA fixed")
        assert c7.passed is False and "undefined" in c7.note
        assert "actual=n/a" in v.failure_reasons()[0]

    def test_pf_without_any_loss_is_infinite_and_passes(self) -> None:
        v = r.apply_selection_criteria(_agg(pair="ETH/USDC", gross_profit=50.0, gross_loss=0.0))
        c2 = next(c for c in v.criteria if c.name == "profit_factor_oos > 1.3")
        assert c2.passed is True and c2.actual == 999.0 and "∞" in c2.note
        assert v.aggregate.profit_factor_oos == math.inf
        assert v.to_dict()["profit_factor_oos"] is None  # JSON-safe: the sums disambiguate
        assert (
            v.to_dict()["gross_loss_net_oos"] == 0.0 and v.to_dict()["gross_profit_net_oos"] == 50.0
        )
        assert r._pf_text(v.to_dict()) == "∞"

    def test_pf_zero_over_zero_is_undefined_and_fails(self) -> None:
        v = r.apply_selection_criteria(_agg(pair="ETH/USDC", gross_profit=0.0, gross_loss=0.0))
        c2 = next(c for c in v.criteria if c.name == "profit_factor_oos > 1.3")
        assert c2.passed is False and c2.actual is None and "0/0" in c2.note
        assert r._pf_text(v.to_dict()) == "n/a"

    def test_benchmark_leg_none_cannot_be_beaten(self) -> None:
        only_dca = {"BTC/USDC": {"buy_and_hold": None, "dca_fixed": 0.3}}
        v = r.apply_selection_criteria(_agg(mean_sharpe_oos=0.5), benchmarks=only_dca)
        assert v.beats_benchmark == "dca_fixed" and v.benchmark_sharpe["buy_and_hold"] is None
        none_bench = {"BTC/USDC": {"buy_and_hold": None, "dca_fixed": None}}
        v2 = r.apply_selection_criteria(_agg(mean_sharpe_oos=5.0), benchmarks=none_bench)
        c7 = next(c for c in v2.criteria if c.name == "beats Buy&Hold OR DCA fixed")
        assert c7.passed is False and "no benchmark available" in c7.note

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

    def test_ineligible_config_is_never_selected(self) -> None:
        """GO P7 rule 1: a flagged config is skipped whatever its score; the next eligible
        passing config wins; the 7 criteria are untouched (its verdict still says passed)."""
        aggs = {
            ("grok_supertrend_4h", "BTC/USDC", "h1"): _agg(mean_sharpe_oos=1.0, params_hash="h1"),
            ("grok_supertrend_4h", "BTC/USDC", "h2"): _agg(mean_sharpe_oos=1.5, params_hash="h2"),
        }
        flag = {"run": "grok_supertrend_4h_BTC_USDC_p2_h2_w3", "segment": "test"}
        out = r.build_selection(aggs, ineligible={("grok_supertrend_4h", "BTC/USDC", "h2"): [flag]})
        assert [s["params_hash"] for s in out["selected_for_paper"]] == ["h1"]
        assert out["ineligible_flagged"][0]["params_hash"] == "h2"
        assert out["ineligible_flagged"][0]["passed_criteria"] is True
        assert out["abandoned"] == []
        assert {v["params_hash"]: v["passed"] for v in out["all_verdicts"]} == {
            "h1": True,
            "h2": True,
        }

    def test_ineligible_configs_from_flags(self) -> None:
        flags = [
            {
                "run": "s_BTC_USDC_p1_aaaa1111",
                "strategy": "s",
                "pair": "BTC/USDC",
                "segment": "all",
            },
            {
                "run": "s_BTC_USDC_p2_aaaa1111_w2",
                "strategy": "s",
                "pair": "BTC/USDC",
                "segment": "test",
            },
            {
                "run": "s_SOL_USDC_p2_bbbb2222_w0",
                "strategy": "s",
                "pair": "SOL/USDC",
                "segment": "train",
            },
        ]
        out = r.ineligible_configs(flags)
        assert set(out) == {("s", "BTC/USDC", "aaaa1111"), ("s", "SOL/USDC", "bbbb2222")}
        assert len(out[("s", "BTC/USDC", "aaaa1111")]) == 2


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
