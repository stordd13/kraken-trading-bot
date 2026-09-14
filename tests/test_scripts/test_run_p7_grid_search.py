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
import json
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
        jobs = p7.build_phase1_jobs(fees="binance")
        assert len(jobs) == 212

    def test_filter_by_strategy(self) -> None:
        jobs = p7.build_phase1_jobs(strategy_filter="grok_supertrend_4h", fees="binance")
        assert len(jobs) == 60
        for j in jobs:
            assert j["strategy"] == "grok_supertrend_4h"

    def test_filter_by_pair(self) -> None:
        jobs = p7.build_phase1_jobs(pair_filter="SOL/USDC", fees="binance")
        # SuperTrend (20) + Grid ATR (48) + Donchian (8) → 76 on SOL
        assert len(jobs) == 76
        for j in jobs:
            assert j["pair"] == "SOL/USDC"

    def test_filter_combined(self) -> None:
        jobs = p7.build_phase1_jobs(
            strategy_filter="grok_grid_atr_adaptive_v4",
            pair_filter="BTC/USDC",
            fees="binance",
        )
        assert len(jobs) == 48

    def test_jobs_are_picklable(self) -> None:
        import pickle

        jobs = p7.build_phase1_jobs(fees="binance")
        for j in jobs[:10]:  # spot-check first 10
            pickle.loads(pickle.dumps(j))

    def test_train_test_split(self) -> None:
        jobs = p7.build_phase1_jobs(
            strategy_filter="grok_supertrend_4h", pair_filter="BTC/USDC", fees="binance"
        )
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
        jobs = p7.build_phase1_jobs(fees="binance")
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
                {"strategy": "s", "pair": "BTC/USDC", "params": {"a": 1}, "fees": "binance"},
                {"strategy": "s", "pair": "BTC/USDC", "params": {"a": 2}, "fees": "binance"},
            ]
        }
        windows = p7.generate_walk_forward_windows()
        jobs = p7.build_phase2_jobs(top_k, windows=windows, fees="binance")
        # 2 configs × 8 windows = 16
        assert len(jobs) == 16
        # Every job has phase="2" and a window_idx between 1 and 8
        for j in jobs:
            assert j["phase"] == "2"
            assert j["window_idx"] in range(1, 9)

    def test_keys_unique(self) -> None:
        top_k = {
            ("s", "BTC/USDC"): [
                {"strategy": "s", "pair": "BTC/USDC", "params": {"a": i}, "fees": "binance"}
                for i in range(3)
            ]
        }
        jobs = p7.build_phase2_jobs(top_k, fees="binance")
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
            strategy_filter="grok_donchian_breakout_4h", pair_filter="SOL/USDC", fees="binance"
        )

    def test_no_existing_returns_all(self) -> None:
        jobs = self._build_jobs()
        pending = p7.filter_pending_jobs(jobs, existing={}, force=False, fees="binance")
        assert pending == jobs

    def test_existing_keys_excluded(self) -> None:
        jobs = self._build_jobs()
        existing_key = p7.make_key(
            jobs[0]["strategy"], jobs[0]["pair"], jobs[0]["params"], jobs[0]["phase"]
        )
        pending = p7.filter_pending_jobs(
            jobs, existing={existing_key: {"ok": 1, "fees": "binance"}}, force=False, fees="binance"
        )
        assert len(pending) == len(jobs) - 1

    def test_failed_entries_retried(self) -> None:
        jobs = self._build_jobs()
        existing_key = p7.make_key(
            jobs[0]["strategy"], jobs[0]["pair"], jobs[0]["params"], jobs[0]["phase"]
        )
        pending = p7.filter_pending_jobs(
            jobs, existing={existing_key: {"error": "timeout"}}, force=False, fees="binance"
        )
        assert len(pending) == len(jobs)

    def test_force_rerun_all(self) -> None:
        jobs = self._build_jobs()
        existing = {
            p7.make_key(j["strategy"], j["pair"], j["params"], j["phase"]): {"ok": 1} for j in jobs
        }
        pending = p7.filter_pending_jobs(jobs, existing=existing, force=True, fees="binance")
        assert len(pending) == len(jobs)

    def test_other_fee_model_is_refused(self) -> None:
        jobs = self._build_jobs()
        key = p7.make_key(jobs[0]["strategy"], jobs[0]["pair"], jobs[0]["params"], jobs[0]["phase"])
        with pytest.raises(p7.FeeModelMismatchError, match="fees=bybit"):
            p7.filter_pending_jobs(
                jobs, existing={key: {"fees": "bybit"}}, force=False, fees="binance"
            )

    def test_legacy_entry_without_fees_is_refused(self) -> None:
        jobs = self._build_jobs()
        key = p7.make_key(jobs[0]["strategy"], jobs[0]["pair"], jobs[0]["params"], jobs[0]["phase"])
        with pytest.raises(p7.FeeModelMismatchError, match="pre-B4.2"):
            p7.filter_pending_jobs(jobs, existing={key: {"ok": 1}}, force=False, fees="binance")


class TestFeeModelPlumbing:
    def test_missing_fees_exits_2(self, capsys: pytest.CaptureFixture[str]) -> None:
        for phase in ("1", "2", "report"):
            with pytest.raises(SystemExit) as exc:
                p7.parse_args(["--phase", phase])
            assert exc.value.code == 2
            assert "--fees" in capsys.readouterr().err

    def test_invalid_fees_exits_2(self) -> None:
        with pytest.raises(SystemExit) as exc:
            p7.parse_args(["--phase", "1", "--fees", "ftx"])
        assert exc.value.code == 2

    def test_fees_accepted_and_propagated(self) -> None:
        args = p7.parse_args(["--phase", "report", "--fees", "bybit"])
        assert args.fees == "bybit"
        jobs = p7.build_phase1_jobs(
            strategy_filter="grok_supertrend_4h", pair_filter="BTC/USDC", fees="bybit"
        )
        assert {j["fees"] for j in jobs} == {"bybit"}
        assert p7.P7Job.from_dict(jobs[0]).fees == "bybit"

    def test_p7job_requires_fees(self) -> None:
        with pytest.raises(TypeError, match="fees"):
            p7.P7Job(  # type: ignore[call-arg]
                strategy="s",
                pair="BTC/USDC",
                params={},
                phase="1",
                train_start_iso="2023-04-01T00:00:00+00:00",
                train_end_iso="2025-04-01T00:00:00+00:00",
                test_start_iso="2025-04-01T00:00:00+00:00",
                test_end_iso="2026-04-01T00:00:00+00:00",
            )

    def test_phase2_refuses_phase1_entries_of_another_model(self) -> None:
        top_k = {
            ("s", "BTC/USDC"): [
                {"strategy": "s", "pair": "BTC/USDC", "params": {}, "fees": "binance"}
            ]
        }
        with pytest.raises(p7.FeeModelMismatchError, match="fees=binance"):
            p7.build_phase2_jobs(top_k, fees="bybit")
        legacy = {("s", "BTC/USDC"): [{"strategy": "s", "pair": "BTC/USDC", "params": {}}]}
        with pytest.raises(p7.FeeModelMismatchError, match="pre-B4.2"):
            p7.build_phase2_jobs(legacy, fees="bybit")

    def test_assert_results_fee_model(self, tmp_path: Path) -> None:
        path = tmp_path / "phase1.json"
        p7._assert_results_fee_model({"k": {"fees": "bybit"}, "e": {"error": "x"}}, "bybit", path)
        with pytest.raises(p7.FeeModelMismatchError):
            p7._assert_results_fee_model({"k": {"fees": "binance"}}, "bybit", path)
        with pytest.raises(p7.FeeModelMismatchError):
            p7._assert_results_fee_model({"k": {"exchange": "binance"}}, "bybit", path)

    def test_report_phase_refuses_mismatched_inputs(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        phase1 = tmp_path / "p1.json"
        phase2 = tmp_path / "p2.json"
        phase1.write_text(json.dumps({"k": {"fees": "binance", "test": {}}}))
        phase2.write_text(json.dumps({"k": {"fees": "bybit", "test": {}}}))
        rc = p7._run_report_phase(phase1, phase2, fees="bybit")
        assert rc == 2
        assert "fees=binance" in capsys.readouterr().err


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
