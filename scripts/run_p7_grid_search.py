"""P7 — Targeted parameter grid search for the P6 survivors.

Two phases:

- **Phase 1** (cross-validate 70/30): sweep all grids defined in
  :mod:`scripts.p7_grids`, store metrics per (strategy, pair, params) in
  ``results/P7_phase1_cross_validate.json``.

- **Phase 2** (walk-forward): for each combo, take the top 5 configs by
  test Sharpe and run an 8-window walk-forward (12 month train /
  3 month test / 3 month advance), store per-window metrics in
  ``results/P7_phase2_walk_forward.json``.

Reuses the multiprocessing infrastructure of P6.7
(:mod:`scripts.run_p6_backtests`) — spawn-context Pool, atomic save with
threading lock, daemon status writer, SIGINT handler — with the new bits
for grid-search-specific keys (params hash + phase + window index) and
the engine-level ``strategy_params_override`` plumbed through.

Usage::

    poetry run python scripts/run_p7_grid_search.py --phase 1
    poetry run python scripts/run_p7_grid_search.py --phase 2
    poetry run python scripts/run_p7_grid_search.py --phase 1 --workers 4 --limit 10
"""

# ruff: noqa: E402

from __future__ import annotations

import argparse
import asyncio
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime, timedelta
import hashlib
import json
import multiprocessing as mp
import os
from pathlib import Path
import signal
import sys
import tempfile
import threading
import time
import traceback
from typing import Any

from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / ".env")

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from krakenbot.core.logger import get_logger

try:
    from scripts import p7_grids
except ModuleNotFoundError:
    # When run directly (python scripts/run_p7_grid_search.py) the project
    # root is on sys.path but the package marker may be missing; fall back
    # to a sibling import which works because we added the scripts dir to
    # sys.path above.
    import p7_grids  # type: ignore[no-redef]

logger = get_logger().bind(component="p7_grid_search")


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

P7_START = datetime(2023, 4, 1, tzinfo=UTC)
P7_END = datetime(2026, 4, 1, tzinfo=UTC)
TRAIN_RATIO = 0.7
CAPITAL = 1000.0
EXCHANGE = "binance"
CANDLE_INTERVAL = 5
GRID_STRATEGIES = {"grok_grid_atr_adaptive_v4"}

# Walk-forward window config (Phase 2)
WF_TRAIN_MONTHS = 12
WF_TEST_MONTHS = 3
WF_ADVANCE_MONTHS = 3
WF_N_WINDOWS = 8
WF_TOP_K = 5  # top-K configs by Phase 1 test Sharpe to walk-forward

ROOT = Path(__file__).resolve().parent.parent
PHASE1_OUTPUT = ROOT / "results" / "P7_phase1_cross_validate.json"
PHASE2_OUTPUT = ROOT / "results" / "P7_phase2_walk_forward.json"
STATUS_PATH = ROOT / "logs" / "p7_status.json"

DEFAULT_TIMEOUT_SEC = 3600
DEFAULT_WORKER_CAP = 8
STATUS_WRITE_INTERVAL = 5.0

ESTIMATE_GRID_SEC = 300
ESTIMATE_SIGNAL_SEC = 30


# ---------------------------------------------------------------------------
# Job model
# ---------------------------------------------------------------------------


@dataclass
class P7Job:
    """One backtest unit — covers a single config × pair × (train,test) segment.

    For phase 1, train/test split comes from the 70/30 ratio over the full
    P7 period. For phase 2, train/test come from one walk-forward window.
    """

    strategy: str
    pair: str
    params: dict[str, Any]
    phase: str  # "1" or "2"
    train_start_iso: str
    train_end_iso: str
    test_start_iso: str
    test_end_iso: str
    capital: float = CAPITAL
    exchange: str = EXCHANGE
    candle_interval: int = CANDLE_INTERVAL
    window_idx: int | None = None  # phase 2 only

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> P7Job:
        return cls(**d)

    @property
    def key(self) -> str:
        return make_key(self.strategy, self.pair, self.params, self.phase, self.window_idx)


def params_hash(params: dict[str, Any]) -> str:
    """Stable short hash of a params dict (key order-independent)."""
    blob = json.dumps(params, sort_keys=True, default=str).encode("utf-8")
    return hashlib.md5(blob).hexdigest()[:8]  # noqa: S324 — non-cryptographic id


def make_key(
    strategy: str,
    pair: str,
    params: dict[str, Any],
    phase: str,
    window_idx: int | None = None,
) -> str:
    """Build a JSON-key-friendly identifier unique per (combo × config × window)."""
    pair_norm = pair.replace("/", "_")
    window_part = f"_w{window_idx}" if window_idx is not None else ""
    return f"{strategy}_{pair_norm}_p{phase}_{params_hash(params)}{window_part}"


# ---------------------------------------------------------------------------
# Phase 1 — job builder (cross-validate 70/30 on the full P7 period)
# ---------------------------------------------------------------------------


def build_phase1_jobs(
    strategy_filter: str | None = None,
    pair_filter: str | None = None,
) -> list[dict[str, Any]]:
    """Build the full phase-1 job list as picklable dicts.

    Optional filters narrow the list to a single strategy and/or pair —
    useful for smoke tests.
    """
    split = P7_START + (P7_END - P7_START) * TRAIN_RATIO
    out: list[dict[str, Any]] = []
    for strategy, pair, params in p7_grids.build_phase1_combos():
        if strategy_filter and strategy != strategy_filter:
            continue
        if pair_filter and pair != pair_filter:
            continue
        out.append(
            P7Job(
                strategy=strategy,
                pair=pair,
                params=params,
                phase="1",
                train_start_iso=P7_START.isoformat(),
                train_end_iso=split.isoformat(),
                test_start_iso=split.isoformat(),
                test_end_iso=P7_END.isoformat(),
            ).to_dict()
        )
    return out


def estimate_duration(job: dict[str, Any]) -> int:
    return ESTIMATE_GRID_SEC if "grid" in job["strategy"].lower() else ESTIMATE_SIGNAL_SEC


def sort_jobs_by_duration(jobs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(jobs, key=estimate_duration, reverse=True)


# ---------------------------------------------------------------------------
# Phase 2 — walk-forward windows + top-K selection
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class WalkForwardWindow:
    idx: int
    train_start: datetime
    train_end: datetime
    test_start: datetime
    test_end: datetime


def generate_walk_forward_windows(
    start: datetime = P7_START,
    end: datetime = P7_END,
    train_months: int = WF_TRAIN_MONTHS,
    test_months: int = WF_TEST_MONTHS,
    advance_months: int = WF_ADVANCE_MONTHS,
    n_windows: int = WF_N_WINDOWS,
) -> list[WalkForwardWindow]:
    """Generate ``n_windows`` glissantes (train_months train / test_months test).

    Each window advances by ``advance_months``. Default config produces 8
    windows that exactly cover 2023-04 → 2026-04 (12 train + 8 × 3 test).
    """
    windows: list[WalkForwardWindow] = []
    cursor_train_start = start
    for i in range(n_windows):
        train_end = _add_months(cursor_train_start, train_months)
        test_end = _add_months(train_end, test_months)
        if test_end > end:
            break
        windows.append(
            WalkForwardWindow(
                idx=i + 1,
                train_start=cursor_train_start,
                train_end=train_end,
                test_start=train_end,
                test_end=test_end,
            )
        )
        cursor_train_start = _add_months(cursor_train_start, advance_months)
    return windows


def _add_months(d: datetime, months: int) -> datetime:
    """Naive month-add: handles 30/31 by clamping to month-end."""
    year = d.year + (d.month - 1 + months) // 12
    month = (d.month - 1 + months) % 12 + 1
    # Day clamp: month has at most 28-31 days. Use day 1 + delta so we don't
    # land on an invalid date.
    day = min(d.day, _days_in_month(year, month))
    return d.replace(year=year, month=month, day=day)


def _days_in_month(year: int, month: int) -> int:
    if month == 12:
        next_month = datetime(year + 1, 1, 1, tzinfo=UTC)
    else:
        next_month = datetime(year, month + 1, 1, tzinfo=UTC)
    last_day = next_month - timedelta(days=1)
    return last_day.day


def select_top_k_per_combo(
    phase1_results: dict[str, Any],
    k: int = WF_TOP_K,
) -> dict[tuple[str, str], list[dict[str, Any]]]:
    """Group phase-1 results by (strategy, pair) and keep the top-K by test Sharpe.

    Skips entries that have an ``error`` key (failed jobs).
    Configurations with missing/null test Sharpe sort last (treated as -inf).
    """
    by_combo: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for entry in phase1_results.values():
        if "error" in entry:
            continue
        strat = entry.get("strategy")
        pair = entry.get("pair")
        if strat is None or pair is None:
            continue
        by_combo.setdefault((strat, pair), []).append(entry)

    out: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for combo, entries in by_combo.items():
        sorted_entries = sorted(
            entries,
            key=lambda e: _safe_sharpe(e.get("test", {})),
            reverse=True,
        )
        out[combo] = sorted_entries[:k]
    return out


def _safe_sharpe(metrics: dict[str, Any]) -> float:
    """Return Sharpe as float, or -inf if missing/NaN/non-numeric."""
    v = metrics.get("sharpe_ratio")
    if v is None:
        return float("-inf")
    try:
        fv = float(v)
    except (TypeError, ValueError):
        return float("-inf")
    if fv != fv:  # NaN
        return float("-inf")
    return fv


def build_phase2_jobs(
    top_k_per_combo: dict[tuple[str, str], list[dict[str, Any]]],
    windows: list[WalkForwardWindow] | None = None,
) -> list[dict[str, Any]]:
    """Cross top-K configs with walk-forward windows → list of P7Job dicts."""
    if windows is None:
        windows = generate_walk_forward_windows()
    out: list[dict[str, Any]] = []
    for (strategy, pair), entries in top_k_per_combo.items():
        for entry in entries:
            params = entry.get("params") or {}
            for window in windows:
                out.append(
                    P7Job(
                        strategy=strategy,
                        pair=pair,
                        params=dict(params),
                        phase="2",
                        train_start_iso=window.train_start.isoformat(),
                        train_end_iso=window.train_end.isoformat(),
                        test_start_iso=window.test_start.isoformat(),
                        test_end_iso=window.test_end.isoformat(),
                        window_idx=window.idx,
                    ).to_dict()
                )
    return out


# ---------------------------------------------------------------------------
# Resume support (shared between phases)
# ---------------------------------------------------------------------------


def load_existing_results(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        raise RuntimeError(
            f"Existing results file is corrupted JSON: {path}. "
            f"Delete it or fix it before resuming. Error: {e}"
        ) from e


def filter_pending_jobs(
    jobs: list[dict[str, Any]],
    existing: dict[str, Any],
    force: bool,
) -> list[dict[str, Any]]:
    if force:
        return list(jobs)
    pending = []
    for job in jobs:
        key = make_key(
            job["strategy"],
            job["pair"],
            job["params"],
            job["phase"],
            job.get("window_idx"),
        )
        entry = existing.get(key)
        if entry is None or "error" in entry:
            pending.append(job)
    return pending


# ---------------------------------------------------------------------------
# Atomic save + status writer (verbatim from P6, kept local to avoid coupling)
# ---------------------------------------------------------------------------

_save_lock = threading.Lock()


def save_result_atomic(results: dict[str, Any], path: Path) -> None:
    with _save_lock:
        path.parent.mkdir(parents=True, exist_ok=True)
        dir_ = str(path.parent)
        tmp_path: str | None = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w",
                dir=dir_,
                delete=False,
                suffix=".tmp",
                encoding="utf-8",
            ) as f:
                json.dump(results, f, indent=2, default=str)
                f.flush()
                os.fsync(f.fileno())
                tmp_path = f.name
            os.replace(tmp_path, path)
            tmp_path = None
        finally:
            if tmp_path is not None and os.path.exists(tmp_path):
                try:
                    os.unlink(tmp_path)
                except OSError:
                    pass


@dataclass
class StatusState:
    started_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    total_jobs: int = 0
    completed_jobs: int = 0
    failed_jobs: list[str] = field(default_factory=list)
    running_jobs: dict[str, str] = field(default_factory=dict)
    finished_durations: list[float] = field(default_factory=list)
    n_workers: int = 0
    phase: str = ""

    def snapshot(self) -> dict[str, Any]:
        remaining = self.total_jobs - self.completed_jobs - len(self.failed_jobs)
        if self.finished_durations and self.n_workers:
            avg = sum(self.finished_durations) / len(self.finished_durations)
            eta = int(avg * max(remaining, 0) / max(self.n_workers, 1))
        else:
            eta = None
        return {
            "phase": self.phase,
            "started_at": self.started_at,
            "total_jobs": self.total_jobs,
            "completed_jobs": self.completed_jobs,
            "running_jobs": sorted(self.running_jobs.keys()),
            "failed_jobs": list(self.failed_jobs),
            "estimated_remaining_seconds": eta,
            "n_workers": self.n_workers,
        }


def _status_writer_loop(
    state: StatusState, path: Path, stop_event: threading.Event, interval: float
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    while not stop_event.wait(interval):
        try:
            path.write_text(json.dumps(state.snapshot(), indent=2), encoding="utf-8")
        except Exception:
            logger.warning("status_write_failed", exc_info=True)
    try:
        path.write_text(json.dumps(state.snapshot(), indent=2), encoding="utf-8")
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Worker
# ---------------------------------------------------------------------------


def run_single_backtest_job(job_dict: dict[str, Any]) -> dict[str, Any]:
    """Worker entry. Runs train + test segments with the override applied."""
    t0 = time.time()
    try:
        result = asyncio.run(_async_run_job(job_dict))
        return {
            "status": "success",
            "job": job_dict,
            "result": result,
            "duration_sec": time.time() - t0,
        }
    except BaseException as e:  # noqa: BLE001 — worker must never escape
        return {
            "status": "failed",
            "job": job_dict,
            "error": f"{type(e).__name__}: {e}",
            "traceback": traceback.format_exc(),
            "duration_sec": time.time() - t0,
        }


async def _async_run_job(job_dict: dict[str, Any]) -> dict[str, Any]:
    from krakenbot.config.settings import get_settings
    from krakenbot.core.database import DatabaseManager

    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from backtest import BacktestEngine, GridBacktester

    pid = os.getpid()
    worker_logger = get_logger().bind(component="p7_worker", pid=pid)

    settings = get_settings()
    db_manager = DatabaseManager()
    await db_manager.init_db(settings)

    try:
        job = P7Job.from_dict(job_dict)
        train_start = datetime.fromisoformat(job.train_start_iso)
        train_end = datetime.fromisoformat(job.train_end_iso)
        test_start = datetime.fromisoformat(job.test_start_iso)
        test_end = datetime.fromisoformat(job.test_end_iso)

        def _engine() -> Any:
            cls = GridBacktester if job.strategy in GRID_STRATEGIES else BacktestEngine
            return cls(
                settings,
                db_manager,
                strategy_name=job.strategy,
                candle_interval=job.candle_interval,
                exchange=job.exchange,
                starting_capital=job.capital,
                strategy_params_override=dict(job.params),
            )

        async def _run_segment(seg_start: datetime, seg_end: datetime) -> dict[str, Any]:
            engine = _engine()
            await engine.run(job.pair, seg_start, seg_end)
            return engine.metrics.to_dict()

        worker_logger.info("worker_job_start", key=job.key)
        train_metrics = await _run_segment(train_start, train_end)
        test_metrics = await _run_segment(test_start, test_end)
        # For phase 1 we also run "all" (train + test combined) to mirror P6
        all_metrics: dict[str, Any] | None = None
        if job.phase == "1":
            all_metrics = await _run_segment(train_start, test_end)
        worker_logger.info("worker_job_done", key=job.key)

        result: dict[str, Any] = {
            "strategy": job.strategy,
            "pair": job.pair,
            "exchange": job.exchange,
            "params": dict(job.params),
            "phase": job.phase,
            "window_idx": job.window_idx,
            "period": {
                "train_start": train_start.isoformat(),
                "train_end": train_end.isoformat(),
                "test_start": test_start.isoformat(),
                "test_end": test_end.isoformat(),
            },
            "train": train_metrics,
            "test": test_metrics,
        }
        if all_metrics is not None:
            result["all"] = all_metrics
        return result
    finally:
        await db_manager.close_db()


# ---------------------------------------------------------------------------
# Worker count detection (same heuristic as P6)
# ---------------------------------------------------------------------------


def detect_n_workers(cli_arg: int | None = None) -> int:
    if cli_arg is not None and cli_arg > 0:
        return cli_arg
    n_cpu = mp.cpu_count()
    ram_cap: int | None = None
    try:
        import psutil

        ram_gb = psutil.virtual_memory().total / (1024**3)
        if ram_gb < 16:
            ram_cap = max(1, int(ram_gb // 2))
    except ImportError:
        pass
    candidates = [max(1, n_cpu - 2), DEFAULT_WORKER_CAP]
    if ram_cap is not None:
        candidates.append(ram_cap)
    return max(1, min(candidates))


# ---------------------------------------------------------------------------
# Parent orchestration
# ---------------------------------------------------------------------------


def _apply_result(
    result: dict[str, Any],
    results_store: dict[str, Any],
    state: StatusState,
    output_path: Path,
) -> None:
    job = result["job"]
    key = make_key(
        job["strategy"],
        job["pair"],
        job["params"],
        job["phase"],
        job.get("window_idx"),
    )

    if result["status"] == "success":
        results_store[key] = result["result"]
        state.completed_jobs += 1
        state.finished_durations.append(result.get("duration_sec", 0.0))
        logger.info(
            "job_done",
            key=key,
            duration_sec=f"{result.get('duration_sec', 0):.1f}",
            progress=f"{state.completed_jobs + len(state.failed_jobs)}/{state.total_jobs}",
        )
    else:
        results_store[key] = {
            "strategy": job["strategy"],
            "pair": job["pair"],
            "params": job["params"],
            "phase": job["phase"],
            "window_idx": job.get("window_idx"),
            "error": result["error"],
            "traceback": result.get("traceback", ""),
        }
        state.failed_jobs.append(key)
        logger.error("job_failed", key=key, error=result["error"])

    state.running_jobs.pop(key, None)
    save_result_atomic(results_store, output_path)


def run_serial(
    jobs: list[dict[str, Any]],
    results_store: dict[str, Any],
    state: StatusState,
    output_path: Path,
) -> None:
    for job in jobs:
        key = make_key(
            job["strategy"], job["pair"], job["params"], job["phase"], job.get("window_idx")
        )
        state.running_jobs[key] = datetime.now(UTC).isoformat()
        logger.info("job_start", key=key, mode="serial")
        result = run_single_backtest_job(job)
        _apply_result(result, results_store, state, output_path)


def run_parallel(
    jobs: list[dict[str, Any]],
    results_store: dict[str, Any],
    state: StatusState,
    output_path: Path,
    n_workers: int,
    timeout_sec: int,
) -> None:
    ctx = mp.get_context("spawn")
    pool = ctx.Pool(processes=n_workers)
    state.n_workers = n_workers

    _install_sigint_handler(pool, results_store, state, output_path)

    try:
        pending: list[tuple[str, Any]] = []
        for job in jobs:
            key = make_key(
                job["strategy"],
                job["pair"],
                job["params"],
                job["phase"],
                job.get("window_idx"),
            )
            state.running_jobs[key] = datetime.now(UTC).isoformat()
            async_res = pool.apply_async(run_single_backtest_job, args=(job,))
            pending.append((key, async_res))
            logger.info("job_dispatched", key=key)

        for key, async_res in pending:
            try:
                result = async_res.get(timeout=timeout_sec)
            except mp.TimeoutError:
                job = next(
                    j
                    for j in jobs
                    if make_key(
                        j["strategy"],
                        j["pair"],
                        j["params"],
                        j["phase"],
                        j.get("window_idx"),
                    )
                    == key
                )
                result = {
                    "status": "failed",
                    "job": job,
                    "error": f"TimeoutError: exceeded {timeout_sec}s",
                    "traceback": "",
                    "duration_sec": float(timeout_sec),
                }
            except Exception as e:  # noqa: BLE001
                job = next(
                    j
                    for j in jobs
                    if make_key(
                        j["strategy"],
                        j["pair"],
                        j["params"],
                        j["phase"],
                        j.get("window_idx"),
                    )
                    == key
                )
                result = {
                    "status": "failed",
                    "job": job,
                    "error": f"{type(e).__name__}: {e}",
                    "traceback": traceback.format_exc(),
                    "duration_sec": 0.0,
                }
            _apply_result(result, results_store, state, output_path)
    finally:
        pool.close()
        pool.join()


def _install_sigint_handler(
    pool: Any,
    results_store: dict[str, Any],
    state: StatusState,
    output_path: Path,
) -> None:
    def handler(_sig: int, _frame: Any) -> None:  # noqa: ANN401
        logger.warning("sigint_received_saving_partial")
        try:
            save_result_atomic(results_store, output_path)
        finally:
            try:
                pool.terminate()
                pool.join()
            except Exception:  # noqa: BLE001
                pass
            logger.warning("sigint_shutdown", **state.snapshot())
            sys.exit(130)

    signal.signal(signal.SIGINT, handler)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="P7 parameter grid search runner.")
    parser.add_argument(
        "--phase",
        choices=("1", "2"),
        required=True,
        help="Which phase to run: 1 = cross-validate grid search, 2 = walk-forward top-5.",
    )
    parser.add_argument("--workers", type=int, default=None, help="Worker count. Default: auto.")
    parser.add_argument(
        "--timeout",
        type=int,
        default=DEFAULT_TIMEOUT_SEC,
        help=f"Per-job timeout in seconds (default: {DEFAULT_TIMEOUT_SEC}).",
    )
    parser.add_argument("--force", action="store_true", help="Rerun jobs already in results.")
    parser.add_argument("--serial", action="store_true", help="Bypass pool (debug).")
    parser.add_argument(
        "--strategy", default=None, help="Phase 1 filter: restrict to this strategy."
    )
    parser.add_argument("--pair", default=None, help="Phase 1 filter: restrict to this pair.")
    parser.add_argument(
        "--phase1-input",
        type=Path,
        default=PHASE1_OUTPUT,
        help="Phase 2 only: JSON containing phase-1 results (default: results/P7_phase1_cross_validate.json).",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Output path. Defaults: P7_phase1_cross_validate.json or P7_phase2_walk_forward.json.",
    )
    parser.add_argument(
        "--limit", type=int, default=None, help="Run only first N pending jobs (after sort)."
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)

    if args.phase == "1":
        output_path = args.output or PHASE1_OUTPUT
        jobs = build_phase1_jobs(strategy_filter=args.strategy, pair_filter=args.pair)
    else:
        output_path = args.output or PHASE2_OUTPUT
        if not args.phase1_input.exists():
            print(f"Phase-1 results not found at {args.phase1_input}.", file=sys.stderr)
            return 2
        phase1 = load_existing_results(args.phase1_input)
        top_k = select_top_k_per_combo(phase1, k=WF_TOP_K)
        windows = generate_walk_forward_windows()
        jobs = build_phase2_jobs(top_k, windows=windows)
        logger.info(
            "phase2_built",
            n_combos=len(top_k),
            n_windows=len(windows),
            n_jobs=len(jobs),
        )

    jobs = sort_jobs_by_duration(jobs)

    existing = load_existing_results(output_path)
    pending = filter_pending_jobs(jobs, existing, force=args.force)
    if args.limit is not None:
        pending = pending[: args.limit]

    if not pending:
        print(f"No pending jobs. {len(existing)} entries already in {output_path}.")
        return 0

    state = StatusState(total_jobs=len(pending), phase=args.phase)
    results_store = dict(existing)

    n_workers = 1 if args.serial else detect_n_workers(args.workers)
    state.n_workers = n_workers

    logger.info(
        "run_start",
        phase=args.phase,
        mode="serial" if args.serial else "parallel",
        n_workers=n_workers,
        pending=len(pending),
        existing=len(existing) - len(pending) if not args.force else 0,
        output=str(output_path),
    )

    stop_event = threading.Event()
    status_thread = threading.Thread(
        target=_status_writer_loop,
        args=(state, STATUS_PATH, stop_event, STATUS_WRITE_INTERVAL),
        daemon=True,
        name="p7-status-writer",
    )
    status_thread.start()

    t0 = time.time()
    try:
        if args.serial:
            run_serial(pending, results_store, state, output_path)
        else:
            run_parallel(
                pending,
                results_store,
                state,
                output_path,
                n_workers=n_workers,
                timeout_sec=args.timeout,
            )
    finally:
        stop_event.set()
        status_thread.join(timeout=10)

    elapsed = time.time() - t0
    print(f"\n{'=' * 60}")
    print(f"  P7 Phase {args.phase} — Summary")
    print(f"{'=' * 60}")
    print(f"  Total jobs run: {len(pending)}")
    print(f"  Succeeded: {state.completed_jobs}")
    print(f"  Failed: {len(state.failed_jobs)}")
    print(f"  Mode: {'serial' if args.serial else f'parallel ({n_workers} workers)'}")
    print(f"  Elapsed: {elapsed / 60:.1f} min")
    print(f"  Results: {output_path}")

    return 0 if not state.failed_jobs else 1


if __name__ == "__main__":
    raise SystemExit(main())
