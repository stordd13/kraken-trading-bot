"""Unit tests for scripts/run_p7_grid_search.py.

These verify the pure-Python pieces that do not touch the DB:
- key construction and uniqueness
- phase-1 job builder + cardinality + filter
- walk-forward window generation
- top-K selection
- phase-2 job cross-product
- resume filter
"""

# ruff: noqa: E402
from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
import sys

_project_root = str(Path(__file__).resolve().parent.parent.parent)
sys.path.insert(0, _project_root)
sys.path.insert(0, str(Path(_project_root) / "src"))
sys.path.insert(0, str(Path(_project_root) / "scripts"))

import pytest

from scripts import run_p7_grid_search as p7

# ---------------------------------------------------------------------------
# make_key & params_hash
# ---------------------------------------------------------------------------


class TestKeyConstruction:
    def test_hash_is_stable(self) -> None:
        h1 = p7.params_hash({"a": 1, "b": 2})
        h2 = p7.params_hash({"b": 2, "a": 1})  # different insertion order
        assert h1 == h2

    def test_hash_changes_with_values(self) -> None:
        h1 = p7.params_hash({"a": 1})
        h2 = p7.params_hash({"a": 2})
        assert h1 != h2

    def test_key_includes_phase_and_window(self) -> None:
        k1 = p7.make_key("s", "BTC/USDC", {"a": 1}, phase="1")
        k2 = p7.make_key("s", "BTC/USDC", {"a": 1}, phase="2", window_idx=3)
        assert k1 != k2
        assert "p1_" in k1
        assert "p2_" in k2
        assert k2.endswith("_w3")

    def test_pair_slash_replaced(self) -> None:
        k = p7.make_key("s", "BTC/USDC", {"a": 1}, phase="1")
        assert "BTC_USDC" in k
        assert "/" not in k


# ---------------------------------------------------------------------------
# Phase 1 job builder
# ---------------------------------------------------------------------------


class TestBuildPhase1Jobs:
    def test_total_212(self) -> None:
        jobs = p7.build_phase1_jobs()
        assert len(jobs) == 212

    def test_filter_by_strategy(self) -> None:
        jobs = p7.build_phase1_jobs(strategy_filter="grok_supertrend_4h")
        assert len(jobs) == 60
        for j in jobs:
            assert j["strategy"] == "grok_supertrend_4h"

    def test_filter_by_pair(self) -> None:
        jobs = p7.build_phase1_jobs(pair_filter="SOL/USDC")
        # SuperTrend (20) + Grid ATR (48) + Donchian (8) → 76 on SOL
        assert len(jobs) == 76
        for j in jobs:
            assert j["pair"] == "SOL/USDC"

    def test_filter_combined(self) -> None:
        jobs = p7.build_phase1_jobs(
            strategy_filter="grok_grid_atr_adaptive_v4",
            pair_filter="BTC/USDC",
        )
        assert len(jobs) == 48

    def test_jobs_are_picklable(self) -> None:
        import pickle

        jobs = p7.build_phase1_jobs()
        for j in jobs[:10]:  # spot-check first 10
            pickle.loads(pickle.dumps(j))

    def test_train_test_split(self) -> None:
        jobs = p7.build_phase1_jobs(strategy_filter="grok_supertrend_4h", pair_filter="BTC/USDC")
        j = jobs[0]
        # 70/30 split of 2023-04 → 2026-04 (3 years = 1095 days) → 766.5 train, 328.5 test
        train_start = datetime.fromisoformat(j["train_start_iso"])
        train_end = datetime.fromisoformat(j["train_end_iso"])
        test_start = datetime.fromisoformat(j["test_start_iso"])
        test_end = datetime.fromisoformat(j["test_end_iso"])
        assert train_start == p7.P7_START
        assert test_end == p7.P7_END
        assert train_end == test_start  # continuous split

    def test_keys_unique(self) -> None:
        jobs = p7.build_phase1_jobs()
        keys = [
            p7.make_key(j["strategy"], j["pair"], j["params"], j["phase"], j.get("window_idx"))
            for j in jobs
        ]
        assert len(keys) == len(set(keys))


# ---------------------------------------------------------------------------
# Walk-forward windows
# ---------------------------------------------------------------------------


class TestWalkForwardWindows:
    def test_default_yields_8_windows(self) -> None:
        windows = p7.generate_walk_forward_windows()
        assert len(windows) == 8

    def test_window_indices(self) -> None:
        windows = p7.generate_walk_forward_windows()
        assert [w.idx for w in windows] == [1, 2, 3, 4, 5, 6, 7, 8]

    def test_first_window_starts_at_p7_start(self) -> None:
        windows = p7.generate_walk_forward_windows()
        assert windows[0].train_start == p7.P7_START

    def test_window_continuous_train_test(self) -> None:
        windows = p7.generate_walk_forward_windows()
        for w in windows:
            assert w.train_end == w.test_start

    def test_windows_advance_by_3_months(self) -> None:
        windows = p7.generate_walk_forward_windows()
        # zip pairs each window with its successor — len(windows)-1 pairs
        for w_prev, w_next in zip(windows, windows[1:], strict=False):
            # train_start advances by ~3 months
            delta_days = (w_next.train_start - w_prev.train_start).days
            assert 89 <= delta_days <= 92  # 3 months ≈ 90 days, ±1

    def test_last_test_within_p7_end(self) -> None:
        windows = p7.generate_walk_forward_windows()
        for w in windows:
            assert w.test_end <= p7.P7_END

    def test_train_is_12_months(self) -> None:
        windows = p7.generate_walk_forward_windows()
        for w in windows:
            delta_days = (w.train_end - w.train_start).days
            assert 364 <= delta_days <= 366  # 12 months ≈ 365 days

    def test_test_is_3_months(self) -> None:
        windows = p7.generate_walk_forward_windows()
        for w in windows:
            delta_days = (w.test_end - w.test_start).days
            assert 89 <= delta_days <= 92


# ---------------------------------------------------------------------------
# Top-K selection
# ---------------------------------------------------------------------------


class TestSelectTopK:
    def _entry(self, strat: str, pair: str, sharpe: float, params: dict) -> dict:
        return {
            "strategy": strat,
            "pair": pair,
            "params": params,
            "phase": "1",
            "train": {"sharpe_ratio": 0.0},
            "test": {"sharpe_ratio": sharpe},
        }

    def test_groups_by_combo(self) -> None:
        results = {
            "k1": self._entry("supertrend_4h", "BTC/USDC", 0.5, {"a": 1}),
            "k2": self._entry("supertrend_4h", "ETH/USDC", 0.3, {"a": 2}),
            "k3": self._entry("grid", "BTC/USDC", 0.4, {"a": 3}),
        }
        top = p7.select_top_k_per_combo(results, k=5)
        assert set(top.keys()) == {
            ("supertrend_4h", "BTC/USDC"),
            ("supertrend_4h", "ETH/USDC"),
            ("grid", "BTC/USDC"),
        }

    def test_sorts_by_test_sharpe_desc(self) -> None:
        results = {f"k{i}": self._entry("s", "BTC/USDC", float(i), {"i": i}) for i in range(10)}
        top = p7.select_top_k_per_combo(results, k=3)
        entries = top[("s", "BTC/USDC")]
        assert len(entries) == 3
        sharpes = [e["test"]["sharpe_ratio"] for e in entries]
        assert sharpes == sorted(sharpes, reverse=True)
        assert sharpes == [9.0, 8.0, 7.0]

    def test_skips_failed_entries(self) -> None:
        results = {
            "ok": self._entry("s", "BTC/USDC", 0.5, {"a": 1}),
            "bad": {"strategy": "s", "pair": "BTC/USDC", "error": "TimeoutError"},
        }
        top = p7.select_top_k_per_combo(results, k=5)
        entries = top[("s", "BTC/USDC")]
        assert len(entries) == 1
        assert entries[0]["params"] == {"a": 1}

    def test_handles_missing_sharpe(self) -> None:
        results = {
            "good": self._entry("s", "BTC/USDC", 1.0, {"a": 1}),
            "missing": {
                "strategy": "s",
                "pair": "BTC/USDC",
                "params": {"a": 2},
                "test": {},  # no sharpe_ratio
            },
        }
        top = p7.select_top_k_per_combo(results, k=5)
        entries = top[("s", "BTC/USDC")]
        # good (sharpe=1.0) comes first; missing entry treated as -inf comes last
        assert entries[0]["params"] == {"a": 1}
        assert entries[1]["params"] == {"a": 2}


# ---------------------------------------------------------------------------
# Phase 2 job builder
# ---------------------------------------------------------------------------


class TestBuildPhase2Jobs:
    def test_cross_product(self) -> None:
        top_k = {
            ("s", "BTC/USDC"): [
                {"strategy": "s", "pair": "BTC/USDC", "params": {"a": 1}, "test": {}},
                {"strategy": "s", "pair": "BTC/USDC", "params": {"a": 2}, "test": {}},
            ]
        }
        windows = p7.generate_walk_forward_windows()
        jobs = p7.build_phase2_jobs(top_k, windows=windows)
        # 2 configs × 8 windows = 16
        assert len(jobs) == 16
        # Every job has phase="2" and a window_idx between 1 and 8
        for j in jobs:
            assert j["phase"] == "2"
            assert j["window_idx"] in range(1, 9)

    def test_keys_unique(self) -> None:
        top_k = {
            ("s", "BTC/USDC"): [
                {"strategy": "s", "pair": "BTC/USDC", "params": {"a": i}, "test": {}}
                for i in range(3)
            ]
        }
        jobs = p7.build_phase2_jobs(top_k)
        keys = [
            p7.make_key(j["strategy"], j["pair"], j["params"], j["phase"], j["window_idx"])
            for j in jobs
        ]
        assert len(keys) == len(set(keys))


# ---------------------------------------------------------------------------
# Resume filter
# ---------------------------------------------------------------------------


class TestFilterPending:
    def _build_jobs(self) -> list[dict]:
        return p7.build_phase1_jobs(
            strategy_filter="grok_donchian_breakout_4h", pair_filter="SOL/USDC"
        )

    def test_no_existing_returns_all(self) -> None:
        jobs = self._build_jobs()
        pending = p7.filter_pending_jobs(jobs, existing={}, force=False)
        assert pending == jobs

    def test_existing_keys_excluded(self) -> None:
        jobs = self._build_jobs()
        existing_key = p7.make_key(
            jobs[0]["strategy"], jobs[0]["pair"], jobs[0]["params"], jobs[0]["phase"]
        )
        pending = p7.filter_pending_jobs(jobs, existing={existing_key: {"ok": 1}}, force=False)
        assert len(pending) == len(jobs) - 1

    def test_failed_entries_retried(self) -> None:
        jobs = self._build_jobs()
        existing_key = p7.make_key(
            jobs[0]["strategy"], jobs[0]["pair"], jobs[0]["params"], jobs[0]["phase"]
        )
        pending = p7.filter_pending_jobs(
            jobs, existing={existing_key: {"error": "timeout"}}, force=False
        )
        assert len(pending) == len(jobs)

    def test_force_rerun_all(self) -> None:
        jobs = self._build_jobs()
        existing = {
            p7.make_key(j["strategy"], j["pair"], j["params"], j["phase"]): {"ok": 1} for j in jobs
        }
        pending = p7.filter_pending_jobs(jobs, existing=existing, force=True)
        assert len(pending) == len(jobs)


# ---------------------------------------------------------------------------
# _add_months edge cases
# ---------------------------------------------------------------------------


class TestAddMonths:
    def test_simple(self) -> None:
        d = datetime(2024, 1, 15, tzinfo=UTC)
        assert p7._add_months(d, 3) == datetime(2024, 4, 15, tzinfo=UTC)

    def test_year_rollover(self) -> None:
        d = datetime(2024, 11, 15, tzinfo=UTC)
        assert p7._add_months(d, 3) == datetime(2025, 2, 15, tzinfo=UTC)

    def test_day_clamp_at_month_end(self) -> None:
        d = datetime(2024, 1, 31, tzinfo=UTC)
        # February only has 29 days in 2024 (leap)
        assert p7._add_months(d, 1) == datetime(2024, 2, 29, tzinfo=UTC)

    def test_day_clamp_feb_non_leap(self) -> None:
        d = datetime(2025, 1, 31, tzinfo=UTC)
        assert p7._add_months(d, 1) == datetime(2025, 2, 28, tzinfo=UTC)


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
