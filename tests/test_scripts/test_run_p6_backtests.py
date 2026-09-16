"""Unit tests for the P6 parallel backtest runner."""

# ruff: noqa: E402
from __future__ import annotations

import json
from pathlib import Path
import sys
import threading
from unittest.mock import MagicMock

import pytest

_project_root = str(Path(__file__).resolve().parent.parent.parent)
sys.path.insert(0, _project_root)
sys.path.insert(0, str(Path(_project_root) / "src"))
sys.path.insert(0, str(Path(_project_root) / "scripts"))

from scripts import run_p6_backtests as runner

# ---------------------------------------------------------------------------
# Job list construction and keys
# ---------------------------------------------------------------------------


class TestBuildJobList:
    def test_24_combos(self) -> None:
        jobs = runner.build_job_list(fees="binance")
        assert len(jobs) == 24
        assert len(runner.STRATEGIES) == 8
        assert len(runner.PAIRS) == 3

    def test_all_pairs_present_per_strategy(self) -> None:
        jobs = runner.build_job_list(fees="binance")
        by_strategy: dict[str, set[str]] = {}
        for j in jobs:
            by_strategy.setdefault(j["strategy"], set()).add(j["pair"])
        for pairs in by_strategy.values():
            assert pairs == set(runner.PAIRS)

    def test_job_dict_is_picklable(self) -> None:
        import pickle

        for job in runner.build_job_list(fees="binance"):
            pickle.loads(pickle.dumps(job))


class TestMakeKey:
    def test_replaces_slash(self) -> None:
        assert runner.make_key("grok_supertrend_4h", "BTC/USDC") == "grok_supertrend_4h_BTC_USDC"

    def test_unique_across_all_combos(self) -> None:
        keys = [
            runner.make_key(j["strategy"], j["pair"]) for j in runner.build_job_list(fees="binance")
        ]
        assert len(keys) == len(set(keys))


# ---------------------------------------------------------------------------
# Duration estimate + sorting
# ---------------------------------------------------------------------------


class TestEstimateDuration:
    def test_grid_is_heavy(self) -> None:
        job = {"strategy": "grok_grid_atr_adaptive_v4", "pair": "BTC/USDC"}
        assert runner.estimate_duration(job) == runner.ESTIMATE_GRID_SEC

    def test_signal_is_light(self) -> None:
        for strat in [
            "grok_supertrend_4h",
            "gemini_scalping_volatilite",
            "grok_adaptive_dca_weekly",
        ]:
            assert runner.estimate_duration({"strategy": strat, "pair": "BTC/USDC"}) == (
                runner.ESTIMATE_SIGNAL_SEC
            )


class TestSortJobsByDuration:
    def test_grid_first_desc(self) -> None:
        jobs = runner.build_job_list(fees="binance")
        sorted_jobs = runner.sort_jobs_by_duration(jobs)
        # First 3 must be grid (one per pair)
        first_three_strats = {j["strategy"] for j in sorted_jobs[:3]}
        assert first_three_strats == {"grok_grid_atr_adaptive_v4"}
        # All following must be signal-based
        for j in sorted_jobs[3:]:
            assert "grid" not in j["strategy"].lower()


# ---------------------------------------------------------------------------
# Resume / filter_pending_jobs
# ---------------------------------------------------------------------------


class TestLoadExistingResults:
    def test_missing_file_returns_empty(self, tmp_path: Path) -> None:
        assert runner.load_existing_results(tmp_path / "nope.json") == {}

    def test_valid_json_loads(self, tmp_path: Path) -> None:
        p = tmp_path / "r.json"
        p.write_text(json.dumps({"key1": {"strategy": "x", "pair": "BTC/USDC"}}))
        assert runner.load_existing_results(p) == {"key1": {"strategy": "x", "pair": "BTC/USDC"}}

    def test_malformed_json_raises(self, tmp_path: Path) -> None:
        p = tmp_path / "bad.json"
        p.write_text("{not json")
        with pytest.raises(RuntimeError, match="corrupted JSON"):
            runner.load_existing_results(p)


class TestFilterPendingJobs:
    def _mkjob(self, strategy: str, pair: str, fees: str = "binance") -> dict:
        return {"strategy": strategy, "pair": pair, "fees": fees}

    def test_skips_completed(self) -> None:
        jobs = [self._mkjob("grok_supertrend_4h", "BTC/USDC")]
        existing = {
            "grok_supertrend_4h_BTC_USDC": {
                "strategy": "grok_supertrend_4h",
                "fees": "binance",
                "metrics_version": 2,
                "test": {},
            }
        }
        assert runner.filter_pending_jobs(jobs, existing, force=False, fees="binance") == []

    def test_reruns_errored(self) -> None:
        jobs = [self._mkjob("grok_supertrend_4h", "BTC/USDC")]
        existing = {"grok_supertrend_4h_BTC_USDC": {"error": "boom", "fees": "bybit"}}
        assert runner.filter_pending_jobs(jobs, existing, force=False, fees="binance") == jobs

    def test_force_flag_reruns_all_inside_a_homogeneous_file(self) -> None:
        """C1: --force recomputes every job of a file produced under the same fee model and
        metrics contract; it never overwrites a foreign (pre-B4.2 / pre-C1 / other-model) file."""
        jobs = [self._mkjob("grok_supertrend_4h", "BTC/USDC")]
        same = {
            "grok_supertrend_4h_BTC_USDC": {
                "strategy": "grok_supertrend_4h",
                "fees": "binance",
                "metrics_version": 2,
                "test": {},
            }
        }
        assert runner.filter_pending_jobs(jobs, same, force=True, fees="binance") == jobs
        foreign = {"grok_supertrend_4h_BTC_USDC": {"strategy": "grok_supertrend_4h", "test": {}}}
        with pytest.raises(runner.FeeModelMismatchError, match="pre-B4.2"):
            runner.filter_pending_jobs(jobs, foreign, force=True, fees="binance")
        pre_c1 = {"grok_supertrend_4h_BTC_USDC": {"fees": "binance", "test": {}}}
        with pytest.raises(runner.MetricsVersionMismatchError, match="pre-C1"):
            runner.filter_pending_jobs(jobs, pre_c1, force=True, fees="binance")
        with pytest.raises(runner.MetricsVersionMismatchError, match="pre-C1"):
            runner.filter_pending_jobs(jobs, pre_c1, force=False, fees="binance")
        assert "--force to overwrite" not in runner._fee_mismatch_message(
            "k", None, "binance", Path("x")
        )

    def test_missing_key_returns_job(self) -> None:
        jobs = [self._mkjob("grok_supertrend_4h", "ETH/USDC")]
        assert runner.filter_pending_jobs(jobs, {}, force=False, fees="binance") == jobs

    def test_disjoint_key_never_appended_to_a_foreign_file(self) -> None:
        """C1 review: a job whose key is absent from the file must still be refused when the
        file holds entries of another fee model / contract — the historical B4 JSONs can never
        become mixed files."""
        jobs = [self._mkjob("brand_new_strategy", "ETH/USDC", fees="bybit")]
        pre_c1 = {"grok_supertrend_4h_BTC_USDC": {"fees": "bybit", "test": {}}}
        with pytest.raises(runner.MetricsVersionMismatchError, match="pre-C1"):
            runner.filter_pending_jobs(jobs, pre_c1, force=False, fees="bybit")
        other_model = {"grok_supertrend_4h_BTC_USDC": {"fees": "binance", "metrics_version": 2}}
        with pytest.raises(runner.FeeModelMismatchError, match="fees=binance"):
            runner.filter_pending_jobs(jobs, other_model, force=False, fees="bybit")
        same = {"grok_supertrend_4h_BTC_USDC": {"fees": "bybit", "metrics_version": 2}}
        assert runner.filter_pending_jobs(jobs, same, force=False, fees="bybit") == jobs

    def test_other_fee_model_is_refused(self) -> None:
        jobs = [self._mkjob("grok_supertrend_4h", "BTC/USDC", fees="bybit")]
        existing = {"grok_supertrend_4h_BTC_USDC": {"fees": "binance", "test": {}}}
        with pytest.raises(runner.FeeModelMismatchError, match="fees=binance") as exc:
            runner.filter_pending_jobs(jobs, existing, force=False, fees="bybit")
        assert "--fees bybit" in str(exc.value)
        assert "--force" in str(exc.value)

    def test_legacy_entry_without_fees_is_refused(self) -> None:
        """Pre-B4.2 results files carry 'exchange' but no 'fees': never assume a model."""
        jobs = [self._mkjob("grok_supertrend_4h", "BTC/USDC")]
        existing = {"grok_supertrend_4h_BTC_USDC": {"exchange": "binance", "test": {}}}
        with pytest.raises(runner.FeeModelMismatchError, match="pre-B4.2"):
            runner.filter_pending_jobs(jobs, existing, force=False, fees="binance")


# ---------------------------------------------------------------------------
# Atomic save
# ---------------------------------------------------------------------------


class TestSaveResultAtomic:
    def test_creates_file(self, tmp_path: Path) -> None:
        out = tmp_path / "r.json"
        runner.save_result_atomic({"a": 1}, out)
        assert out.exists()
        assert json.loads(out.read_text()) == {"a": 1}

    def test_no_temp_file_leftover(self, tmp_path: Path) -> None:
        out = tmp_path / "r.json"
        runner.save_result_atomic({"k": "v"}, out)
        # After save, no .tmp files should remain in the dir
        tmps = list(tmp_path.glob("*.tmp"))
        assert tmps == []

    def test_concurrent_writes_no_corruption(self, tmp_path: Path) -> None:
        out = tmp_path / "r.json"
        barrier = threading.Barrier(20)
        store: dict[str, int] = {}
        store_lock = threading.Lock()

        def writer(i: int) -> None:
            with store_lock:
                store[f"k{i}"] = i
                snapshot = dict(store)
            barrier.wait()
            runner.save_result_atomic(snapshot, out)

        threads = [threading.Thread(target=writer, args=(i,)) for i in range(20)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # File must still be valid JSON and must include at least one key
        data = json.loads(out.read_text())
        assert isinstance(data, dict)
        assert len(data) >= 1

    def test_existing_file_untouched_if_write_fails(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        out = tmp_path / "r.json"
        runner.save_result_atomic({"original": True}, out)

        # Force os.replace to fail; the prior file content must remain readable.
        import os as real_os

        original_replace = real_os.replace

        def failing_replace(src: str, dst: str) -> None:
            raise OSError("simulated disk full")

        monkeypatch.setattr(real_os, "replace", failing_replace)
        with pytest.raises(OSError, match="simulated disk full"):
            runner.save_result_atomic({"new": True}, out)

        monkeypatch.setattr(real_os, "replace", original_replace)
        # Original file still intact
        assert json.loads(out.read_text()) == {"original": True}
        # And no stray temp file
        assert list(tmp_path.glob("*.tmp")) == []


# ---------------------------------------------------------------------------
# Worker count detection
# ---------------------------------------------------------------------------


class TestDetectNWorkers:
    def test_cli_override(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(runner.mp, "cpu_count", lambda: 32)
        assert runner.detect_n_workers(4) == 4

    def test_caps_at_default(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(runner.mp, "cpu_count", lambda: 32)
        import psutil

        mem = MagicMock()
        mem.total = 64 * 1024**3  # 64 GB → no ram cap
        monkeypatch.setattr(psutil, "virtual_memory", lambda: mem)
        assert runner.detect_n_workers(None) == runner.DEFAULT_WORKER_CAP

    def test_low_ram_caps_workers(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(runner.mp, "cpu_count", lambda: 32)
        import psutil

        mem = MagicMock()
        mem.total = 4 * 1024**3  # 4 GB → ram cap = 2
        monkeypatch.setattr(psutil, "virtual_memory", lambda: mem)
        assert runner.detect_n_workers(None) == 2

    def test_few_cpus(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(runner.mp, "cpu_count", lambda: 3)
        import psutil

        mem = MagicMock()
        mem.total = 64 * 1024**3
        monkeypatch.setattr(psutil, "virtual_memory", lambda: mem)
        # max(1, 3-2) = 1, cap = 8 → min = 1
        assert runner.detect_n_workers(None) == 1


# ---------------------------------------------------------------------------
# Worker entry point (without real backtest)
# ---------------------------------------------------------------------------


class TestRunSingleBacktestJob:
    def test_success(self, monkeypatch: pytest.MonkeyPatch) -> None:
        fake_result = {"strategy": "x", "pair": "BTC/USDC", "train": {}, "test": {}, "all": {}}

        def fake_async_run(coro: object) -> dict:
            # Close the coroutine so Python doesn't warn about an unawaited coro
            if hasattr(coro, "close"):
                coro.close()
            return fake_result

        monkeypatch.setattr(runner.asyncio, "run", fake_async_run)

        job = {"strategy": "grok_supertrend_4h", "pair": "BTC/USDC"}
        out = runner.run_single_backtest_job(job)
        assert out["status"] == "success"
        assert out["result"] == fake_result
        assert out["job"] == job
        assert "duration_sec" in out

    def test_catches_exception(self, monkeypatch: pytest.MonkeyPatch) -> None:
        def fake_async_run(coro: object) -> dict:
            if hasattr(coro, "close"):
                coro.close()
            raise RuntimeError("db fell over")

        monkeypatch.setattr(runner.asyncio, "run", fake_async_run)

        out = runner.run_single_backtest_job({"strategy": "x", "pair": "BTC/USDC"})
        assert out["status"] == "failed"
        assert "RuntimeError" in out["error"]
        assert "db fell over" in out["error"]
        assert "traceback" in out


# ---------------------------------------------------------------------------
# Parent orchestration (serial mode — avoids multiprocessing in unit tests)
# ---------------------------------------------------------------------------


class TestRunSerial:
    def test_dispatches_all_jobs(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        out = tmp_path / "r.json"
        jobs = [
            {"strategy": "grok_supertrend_4h", "pair": "BTC/USDC"},
            {"strategy": "grok_supertrend_4h", "pair": "ETH/USDC"},
            {"strategy": "grok_supertrend_4h", "pair": "SOL/USDC"},
        ]

        calls = {"n": 0}

        def fake_worker(job: dict) -> dict:
            calls["n"] += 1
            return {
                "status": "success",
                "job": job,
                "result": {
                    "strategy": job["strategy"],
                    "pair": job["pair"],
                    "fees": job.get("fees"),
                    "metrics_version": 2,
                },
                "duration_sec": 0.1,
            }

        monkeypatch.setattr(runner, "run_single_backtest_job", fake_worker)

        state = runner.StatusState(total=len(jobs))
        store: dict = {}
        runner.run_serial(jobs, store, state, out)

        assert calls["n"] == 3
        assert state.completed_jobs == 3
        assert len(state.failed_jobs) == 0
        saved = json.loads(out.read_text())
        assert set(saved.keys()) == {
            "grok_supertrend_4h_BTC_USDC",
            "grok_supertrend_4h_ETH_USDC",
            "grok_supertrend_4h_SOL_USDC",
        }

    def test_failure_does_not_stop_others(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        out = tmp_path / "r.json"
        jobs = [
            {"strategy": "good", "pair": "BTC/USDC"},
            {"strategy": "bad", "pair": "ETH/USDC"},
            {"strategy": "good", "pair": "SOL/USDC"},
        ]

        def fake_worker(job: dict) -> dict:
            if job["strategy"] == "bad":
                return {
                    "status": "failed",
                    "job": job,
                    "error": "boom",
                    "traceback": "tb",
                    "duration_sec": 0.0,
                }
            return {
                "status": "success",
                "job": job,
                "result": {
                    "strategy": job["strategy"],
                    "pair": job["pair"],
                    "fees": job.get("fees"),
                    "metrics_version": 2,
                },
                "duration_sec": 0.1,
            }

        monkeypatch.setattr(runner, "run_single_backtest_job", fake_worker)

        state = runner.StatusState(total=len(jobs))
        store: dict = {}
        runner.run_serial(jobs, store, state, out)

        assert state.completed_jobs == 2
        assert state.failed_jobs == ["bad_ETH_USDC"]
        saved = json.loads(out.read_text())
        assert "error" in saved["bad_ETH_USDC"]
        assert "error" not in saved["good_BTC_USDC"]


# ---------------------------------------------------------------------------
# StatusState snapshot shape
# ---------------------------------------------------------------------------


class TestStatusState:
    def test_initial_snapshot(self) -> None:
        s = runner.StatusState(total=24)
        snap = s.snapshot()
        assert snap["total_jobs"] == 24
        assert snap["completed_jobs"] == 0
        assert snap["running_jobs"] == []
        assert snap["failed_jobs"] == []
        assert snap["estimated_remaining_seconds"] is None

    def test_eta_computed_from_finished(self) -> None:
        s = runner.StatusState(total=10)
        s.n_workers = 2
        s.finished_durations = [10.0, 10.0]
        s.completed_jobs = 2
        snap = s.snapshot()
        # 8 remaining, avg 10s, 2 workers → 40s
        assert snap["estimated_remaining_seconds"] == 40


# ---------------------------------------------------------------------------
# Argparse wiring
# ---------------------------------------------------------------------------


class TestParseArgs:
    def test_missing_fees_exits_2(self, capsys: pytest.CaptureFixture[str]) -> None:
        with pytest.raises(SystemExit) as exc:
            runner.parse_args([])
        assert exc.value.code == 2
        assert "--fees" in capsys.readouterr().err

    def test_invalid_fees_exits_2(self) -> None:
        with pytest.raises(SystemExit) as exc:
            runner.parse_args(["--fees", "ftx"])
        assert exc.value.code == 2

    def test_defaults_with_fees(self) -> None:
        args = runner.parse_args(["--fees", "binance"])
        assert args.fees == "binance"
        assert args.workers is None
        assert args.timeout == runner.DEFAULT_TIMEOUT_SEC
        assert args.force is False
        assert args.serial is False
        assert args.output == runner.OUTPUT_PATH
        assert args.limit is None

    def test_override_all(self, tmp_path: Path) -> None:
        out = tmp_path / "x.json"
        args = runner.parse_args(
            [
                "--fees",
                "bybit",
                "--workers",
                "4",
                "--timeout",
                "60",
                "--force",
                "--serial",
                "--output",
                str(out),
                "--limit",
                "3",
            ]
        )
        assert args.fees == "bybit"
        assert args.workers == 4
        assert args.timeout == 60
        assert args.force is True
        assert args.serial is True
        assert args.output == out
        assert args.limit == 3


# ---------------------------------------------------------------------------
# End-to-end main() in serial mode with mocked worker
# ---------------------------------------------------------------------------


class TestMainSerial:
    def test_resumes_after_interrupt(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """First run completes 2 jobs. Second run sees them as done and runs 1."""
        out = tmp_path / "r.json"
        call_log: list[str] = []

        def fake_worker(job: dict) -> dict:
            call_log.append(runner.make_key(job["strategy"], job["pair"]))
            return {
                "status": "success",
                "job": job,
                "result": {
                    "strategy": job["strategy"],
                    "pair": job["pair"],
                    "fees": job.get("fees"),
                    "metrics_version": 2,
                },
                "duration_sec": 0.01,
            }

        monkeypatch.setattr(runner, "run_single_backtest_job", fake_worker)
        # Shrink the jobs to 3 for test speed
        small = [
            {
                "strategy": "grok_supertrend_4h",
                "pair": "BTC/USDC",
                "start_iso": runner.P6_START.isoformat(),
                "end_iso": runner.P6_END.isoformat(),
                "train_ratio": 0.7,
                "capital": 1000.0,
                "exchange": "binance",
                "candle_interval": 5,
                "fees": "binance",
            },
            {
                "strategy": "grok_supertrend_4h",
                "pair": "ETH/USDC",
                "start_iso": runner.P6_START.isoformat(),
                "end_iso": runner.P6_END.isoformat(),
                "train_ratio": 0.7,
                "capital": 1000.0,
                "exchange": "binance",
                "candle_interval": 5,
                "fees": "binance",
            },
            {
                "strategy": "grok_supertrend_4h",
                "pair": "SOL/USDC",
                "start_iso": runner.P6_START.isoformat(),
                "end_iso": runner.P6_END.isoformat(),
                "train_ratio": 0.7,
                "capital": 1000.0,
                "exchange": "binance",
                "candle_interval": 5,
                "fees": "binance",
            },
        ]
        monkeypatch.setattr(runner, "build_job_list", lambda **_: list(small))

        # First pass — simulate crash after 2 jobs by pre-populating existing
        rc = runner.main(["--fees", "binance", "--serial", "--output", str(out), "--limit", "2"])
        assert rc == 0
        assert len(call_log) == 2

        # Second pass — no limit, same output → only the missing one runs
        call_log.clear()
        rc = runner.main(["--fees", "binance", "--serial", "--output", str(out)])
        assert rc == 0
        assert len(call_log) == 1  # only the third job
        saved = json.loads(out.read_text())
        assert len(saved) == 3

    def test_force_reruns_all(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        out = tmp_path / "r.json"
        # Pre-populate with a completed entry
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(
            json.dumps(
                {
                    "grok_supertrend_4h_BTC_USDC": {
                        "strategy": "grok_supertrend_4h",
                        "pair": "BTC/USDC",
                        "fees": "binance",
                        "metrics_version": 2,
                        "train": {},
                        "test": {},
                        "all": {},
                    }
                }
            )
        )

        call_log: list[str] = []

        def fake_worker(job: dict) -> dict:
            call_log.append(runner.make_key(job["strategy"], job["pair"]))
            return {
                "status": "success",
                "job": job,
                "result": {
                    "strategy": job["strategy"],
                    "pair": job["pair"],
                    "fees": job.get("fees"),
                    "metrics_version": 2,
                },
                "duration_sec": 0.01,
            }

        monkeypatch.setattr(runner, "run_single_backtest_job", fake_worker)
        small = [
            {
                "strategy": "grok_supertrend_4h",
                "pair": "BTC/USDC",
                "start_iso": runner.P6_START.isoformat(),
                "end_iso": runner.P6_END.isoformat(),
                "train_ratio": 0.7,
                "capital": 1000.0,
                "exchange": "binance",
                "candle_interval": 5,
                "fees": "binance",
            },
        ]
        monkeypatch.setattr(runner, "build_job_list", lambda **_: list(small))

        rc = runner.main(["--fees", "binance", "--serial", "--output", str(out), "--force"])
        assert rc == 0
        assert call_log == ["grok_supertrend_4h_BTC_USDC"]

    def test_resume_mismatch_returns_2(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """A results file made under another fee model is never resumed silently."""
        out = tmp_path / "r.json"
        out.write_text(
            json.dumps(
                {
                    "grok_supertrend_4h_BTC_USDC": {
                        "strategy": "grok_supertrend_4h",
                        "pair": "BTC/USDC",
                        "fees": "binance",
                        "train": {},
                        "test": {},
                        "all": {},
                    }
                }
            )
        )
        called: list[dict] = []
        monkeypatch.setattr(runner, "run_single_backtest_job", lambda job: called.append(job))
        small = [
            {
                "strategy": "grok_supertrend_4h",
                "pair": "BTC/USDC",
                "start_iso": runner.P6_START.isoformat(),
                "end_iso": runner.P6_END.isoformat(),
                "train_ratio": 0.7,
                "capital": 1000.0,
                "exchange": "binance",
                "candle_interval": 5,
                "fees": "bybit",
            }
        ]
        monkeypatch.setattr(runner, "build_job_list", lambda **_: list(small))

        rc = runner.main(["--fees", "bybit", "--serial", "--output", str(out)])
        assert rc == 2
        assert called == []
        err = capsys.readouterr().err
        assert "fees=binance" in err and "--fees bybit" in err and str(out) in err

    def test_failure_entry_records_exchange_and_fees(self, tmp_path: Path) -> None:
        job = runner.build_job_list(fees="bybit")[0]
        result = {
            "status": "failed",
            "job": job,
            "error": "boom",
            "traceback": "",
            "duration_sec": 0.0,
        }
        store: dict = {}
        state = runner.StatusState(total=1)
        runner._apply_result(result, store, state, tmp_path / "out.json")
        entry = store[runner.make_key(job["strategy"], job["pair"])]
        assert entry["fees"] == "bybit"
        assert entry["exchange"] == "binance"
        assert entry["error"] == "boom"
