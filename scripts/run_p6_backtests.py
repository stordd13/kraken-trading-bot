"""Phase D — Run 24 cross-validated backtests (8 strategies × 3 pairs) in parallel.

Dispatches jobs across a ``multiprocessing.Pool`` (spawn context). Each worker
initializes its own ``DatabaseManager`` and runs train + test + all sequentially
for one strategy × pair combo. The parent handles resume, atomic save, status
monitoring, per-job timeout, and clean shutdown on SIGINT.

Usage:
    poetry run python scripts/run_p6_backtests.py                 # parallel, auto workers
    poetry run python scripts/run_p6_backtests.py --workers 8     # explicit
    poetry run python scripts/run_p6_backtests.py --serial        # debug / gate
    poetry run python scripts/run_p6_backtests.py --force         # rerun all
"""

from __future__ import annotations

import argparse
import asyncio
from dataclasses import dataclass
from datetime import UTC, datetime
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

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from krakenbot.config.settings import FEE_MODEL_NAMES
from krakenbot.core.logger import get_logger

logger = get_logger().bind(component="p6_backtests")

# --- Configuration ---
STRATEGIES = [
    "grok_grid_atr_adaptive_v4",
    "grok_supertrend_4h",
    "grok_ema_adx_atr",
    "grok_adaptive_dca_weekly",
    "grok_donchian_breakout_4h",
    "gemini_scalping_volatilite",
    "gemini_suivi_tendance_momentum",
    "gemini_retour_moyenne",
]
PAIRS = ["BTC/USDC", "ETH/USDC", "SOL/USDC"]
GRID_STRATEGIES = {"grok_grid_atr_adaptive_v4"}

P6_START = datetime(2023, 4, 1, tzinfo=UTC)
P6_END = datetime(2026, 4, 1, tzinfo=UTC)
TRAIN_RATIO = 0.7
CAPITAL = 1000.0
EXCHANGE = "binance"
CANDLE_INTERVAL = 5

ROOT = Path(__file__).resolve().parent.parent
OUTPUT_PATH = ROOT / "results" / "P6_phase_d_results.json"
STATUS_PATH = ROOT / "logs" / "p6_status.json"
WORKER_LOG_DIR = ROOT / "logs"

# Defaults
DEFAULT_TIMEOUT_SEC = 1800  # 30 min per job
DEFAULT_WORKER_CAP = 8
STATUS_WRITE_INTERVAL = 5.0

# Heuristic estimates (seconds) for job ordering
ESTIMATE_GRID_SEC = 300
ESTIMATE_SIGNAL_SEC = 30


# ---------------------------------------------------------------------------
# Job model
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Job:
    """One strategy × pair combo — the unit of parallelism."""

    strategy: str
    pair: str
    start_iso: str
    end_iso: str
    train_ratio: float
    capital: float
    exchange: str  # OHLC data source only
    candle_interval: int
    fees: str  # fee model applied by the engines (--fees), independent of exchange
    # B4.3 campaign configs (GATE B): per-pair spread/slippage file and the minimum order
    # notional; both recorded in every result entry and checked on resume like ``fees``.
    pair_costs_file: str | None = None
    min_order_usdc: float = 1.0

    @property
    def key(self) -> str:
        return make_key(self.strategy, self.pair)

    def to_dict(self) -> dict[str, Any]:
        return {
            "strategy": self.strategy,
            "pair": self.pair,
            "start_iso": self.start_iso,
            "end_iso": self.end_iso,
            "train_ratio": self.train_ratio,
            "capital": self.capital,
            "exchange": self.exchange,
            "candle_interval": self.candle_interval,
            "fees": self.fees,
            "pair_costs_file": self.pair_costs_file,
            "min_order_usdc": self.min_order_usdc,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> Job:
        return cls(**d)


def make_key(strategy: str, pair: str) -> str:
    return f"{strategy}_{pair.replace('/', '_')}"


def build_job_list(
    strategies: list[str] = STRATEGIES,
    pairs: list[str] = PAIRS,
    start: datetime = P6_START,
    end: datetime = P6_END,
    *,
    fees: str,
    pair_costs_file: str | None = None,
    min_order_usdc: float = 1.0,
) -> list[dict[str, Any]]:
    return [
        Job(
            strategy=s,
            pair=p,
            start_iso=start.isoformat(),
            end_iso=end.isoformat(),
            train_ratio=TRAIN_RATIO,
            capital=CAPITAL,
            exchange=EXCHANGE,
            candle_interval=CANDLE_INTERVAL,
            fees=fees,
            pair_costs_file=pair_costs_file,
            min_order_usdc=min_order_usdc,
        ).to_dict()
        for s in strategies
        for p in pairs
    ]


def estimate_duration(job: dict[str, Any]) -> int:
    """Grid strategies iterate 5min candles → ~10× slower than signal-based on 4h."""
    return ESTIMATE_GRID_SEC if "grid" in job["strategy"].lower() else ESTIMATE_SIGNAL_SEC


def sort_jobs_by_duration(jobs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Descending order — heavy jobs start first, light ones fill gaps."""
    return sorted(jobs, key=estimate_duration, reverse=True)


# ---------------------------------------------------------------------------
# Resume support
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


class FeeModelMismatchError(RuntimeError):
    """A results file entry was produced under another fee model (or none, pre-B4.2)."""


def _fee_mismatch_message(key: str, existing: str | None, requested: str, path: Path) -> str:
    return (
        f"Resume refused for {key}: {path} holds a result produced with fees="
        f"{existing if existing is not None else '<absent: pre-B4.2 file>'} but --fees "
        f"{requested} was requested. Mixed fee models would invalidate the ranking: write to "
        f"a fresh --output (e.g. a fee-suffixed file) or pass --force to overwrite everything."
    )


class CampaignConfigMismatchError(FeeModelMismatchError):
    """A results file entry was produced with other campaign costs (pair costs / min order)."""


def _campaign_signature(entry: dict[str, Any]) -> tuple[str | None, float]:
    """(pair_costs_file, min_order_usdc) of a result entry; pre-B4.3 entries = (None, 1.0)."""
    return (entry.get("pair_costs_file"), float(entry.get("min_order_usdc", 1.0)))


def filter_pending_jobs(
    jobs: list[dict[str, Any]],
    existing: dict[str, Any],
    force: bool,
    *,
    fees: str,
    path: Path | None = None,
) -> list[dict[str, Any]]:
    """Jobs not yet in ``existing``; refuses to skip a result made under another fee model
    or other campaign costs (``pair_costs_file`` / ``min_order_usdc``, B4.3)."""
    if force:
        return list(jobs)
    pending = []
    for job in jobs:
        key = make_key(job["strategy"], job["pair"])
        entry = existing.get(key)
        if entry is None or "error" in entry:
            pending.append(job)
            continue
        if entry.get("fees") != fees:
            raise FeeModelMismatchError(
                _fee_mismatch_message(key, entry.get("fees"), fees, path or OUTPUT_PATH)
            )
        wanted = (job.get("pair_costs_file"), float(job.get("min_order_usdc", 1.0)))
        if _campaign_signature(entry) != wanted:
            raise CampaignConfigMismatchError(
                f"Resume refused for {key}: {path or OUTPUT_PATH} holds a result produced with "
                f"(pair_costs_file, min_order_usdc)={_campaign_signature(entry)} but "
                f"{wanted} was requested. Write to a fresh --output or pass --force."
            )
    return pending


# ---------------------------------------------------------------------------
# Atomic save — shared between main thread and SIGINT handler
# ---------------------------------------------------------------------------

_save_lock = threading.Lock()


def save_result_atomic(results: dict[str, Any], path: Path) -> None:
    """Write JSON atomically via tempfile + os.replace. POSIX-atomic.

    Protected by a ``threading.Lock`` because the SIGINT handler may call this
    concurrently with the main thread's post-result save.
    """
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


# ---------------------------------------------------------------------------
# Status monitoring — single daemon thread writer, no lock needed
# ---------------------------------------------------------------------------


class StatusState:
    """Shared state updated by main thread, read by status writer thread.

    CPython dict ops on scalar values are GIL-protected ⇒ no Lock needed here.
    """

    def __init__(self, total: int) -> None:
        self.started_at = datetime.now(UTC).isoformat()
        self.total_jobs = total
        self.completed_jobs = 0
        self.failed_jobs: list[str] = []
        self.running_jobs: dict[str, str] = {}  # key → started_at iso
        self.finished_durations: list[float] = []
        self.n_workers = 0

    def snapshot(self) -> dict[str, Any]:
        remaining = self.total_jobs - self.completed_jobs - len(self.failed_jobs)
        if self.finished_durations and self.n_workers:
            avg = sum(self.finished_durations) / len(self.finished_durations)
            eta = int(avg * max(remaining, 0) / max(self.n_workers, 1))
        else:
            eta = None
        return {
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
    # Final snapshot on exit
    try:
        path.write_text(json.dumps(state.snapshot(), indent=2), encoding="utf-8")
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Worker — MUST be module-level for spawn pickling
# ---------------------------------------------------------------------------


def run_single_backtest_job(job_dict: dict[str, Any]) -> dict[str, Any]:
    """Worker entry point. Executes train + test + all for one combo.

    Returns a dict with ``status`` (success|failed), ``job``, and either
    ``result`` or ``error`` + ``traceback``. Never raises to the pool —
    exceptions are captured so a bad job does not kill sibling workers.
    """
    t0 = time.time()
    try:
        result = asyncio.run(_async_run_cross_validated(job_dict))
        return {
            "status": "success",
            "job": job_dict,
            "result": result,
            "duration_sec": time.time() - t0,
        }
    except BaseException as e:  # noqa: BLE001 — worker must never escape an exception
        return {
            "status": "failed",
            "job": job_dict,
            "error": f"{type(e).__name__}: {e}",
            "traceback": traceback.format_exc(),
            "duration_sec": time.time() - t0,
        }


async def _async_run_cross_validated(job_dict: dict[str, Any]) -> dict[str, Any]:
    """Per-worker async body: init DB, run 3 sub-runs, close DB."""
    # Deferred imports — avoid duplicating parent memory on spawn
    from krakenbot.config.settings import get_settings
    from krakenbot.core.database import DatabaseManager

    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from backtest import BacktestEngine, GridBacktester, load_pair_costs

    # Per-worker logger
    pid = os.getpid()
    worker_logger = get_logger().bind(component="p6_worker", pid=pid)

    settings = get_settings()
    db_manager = DatabaseManager()
    await db_manager.init_db(settings)

    try:
        job = Job.from_dict(job_dict)
        start = datetime.fromisoformat(job.start_iso)
        end = datetime.fromisoformat(job.end_iso)
        total_duration = end - start
        split_time = start + total_duration * job.train_ratio
        pair_costs = load_pair_costs(Path(job.pair_costs_file)) if job.pair_costs_file else None

        def _engine() -> Any:
            cls = GridBacktester if job.strategy in GRID_STRATEGIES else BacktestEngine
            return cls(
                settings,
                db_manager,
                strategy_name=job.strategy,
                candle_interval=job.candle_interval,
                exchange=job.exchange,
                starting_capital=job.capital,
                fee_model=job.fees,
                pair_costs=pair_costs,
                min_order_usdc=job.min_order_usdc,
            )

        liquidation: dict[str, Any] = {}
        effective_params: dict[str, Any] | None = None

        async def _run_segment(name: str, seg_start: datetime, seg_end: datetime) -> dict[str, Any]:
            nonlocal effective_params
            engine = _engine()
            await engine.run(job.pair, seg_start, seg_end)
            if hasattr(engine, "liquidation_summary"):
                liquidation[name] = engine.liquidation_summary()
            effective_params = getattr(engine, "effective_params", None)
            return engine.metrics.to_dict()

        worker_logger.info("worker_job_start", key=job.key)
        train = await _run_segment("train", start, split_time)
        test = await _run_segment("test", split_time, end)
        full = await _run_segment("all", start, end)
        worker_logger.info("worker_job_done", key=job.key)

        applied = pair_costs.get(job.pair) if pair_costs else None
        return {
            "strategy": job.strategy,
            "pair": job.pair,
            "exchange": job.exchange,
            "fees": job.fees,
            # B4.3 campaign configs, recorded for the resume check and the report
            "pair_costs_file": job.pair_costs_file,
            "pair_costs": (
                {"spread": str(applied.spread), "slippage": str(applied.slippage)}
                if applied is not None
                else None
            ),
            "min_order_usdc": job.min_order_usdc,
            "effective_params": effective_params,
            "liquidation": liquidation or None,
            "period": {
                "start": start.isoformat(),
                "end": end.isoformat(),
                "split": split_time.isoformat(),
            },
            "train": train,
            "test": test,
            "all": full,
        }
    finally:
        await db_manager.close_db()


# ---------------------------------------------------------------------------
# Worker count detection
# ---------------------------------------------------------------------------


def detect_n_workers(cli_arg: int | None = None) -> int:
    """Pick worker count. CLI wins. Else min(cpu-2, 8, ram_cap).

    If psutil is unavailable, skip the RAM cap.
    """
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
    """Post-process one worker result: merge into store, update state, save."""
    job = result["job"]
    key = make_key(job["strategy"], job["pair"])

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
            "exchange": job.get("exchange"),
            "fees": job.get("fees"),
            "pair_costs_file": job.get("pair_costs_file"),
            "min_order_usdc": job.get("min_order_usdc", 1.0),
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
    """Serial execution path — used for debugging and determinism gate tests."""
    for job in jobs:
        key = make_key(job["strategy"], job["pair"])
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
    """Fan out jobs across a spawn-context Pool with per-job timeout."""
    ctx = mp.get_context("spawn")
    pool = ctx.Pool(processes=n_workers)
    state.n_workers = n_workers

    _install_sigint_handler(pool, results_store, state, output_path)

    try:
        pending: list[tuple[str, Any]] = []
        for job in jobs:
            key = make_key(job["strategy"], job["pair"])
            state.running_jobs[key] = datetime.now(UTC).isoformat()
            async_res = pool.apply_async(run_single_backtest_job, args=(job,))
            pending.append((key, async_res))
            logger.info("job_dispatched", key=key)

        for key, async_res in pending:
            try:
                result = async_res.get(timeout=timeout_sec)
            except mp.TimeoutError:
                # Mirror the worker result shape
                job = next(j for j in jobs if make_key(j["strategy"], j["pair"]) == key)
                result = {
                    "status": "failed",
                    "job": job,
                    "error": f"TimeoutError: exceeded {timeout_sec}s",
                    "traceback": "",
                    "duration_sec": float(timeout_sec),
                }
            except Exception as e:  # noqa: BLE001 — must not let one job break the loop
                job = next(j for j in jobs if make_key(j["strategy"], j["pair"]) == key)
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
            state_snapshot = state.snapshot()
            logger.warning("sigint_shutdown", **state_snapshot)
            sys.exit(130)

    signal.signal(signal.SIGINT, handler)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="P6 Phase D parallel backtest runner.")
    parser.add_argument(
        "--fees",
        choices=FEE_MODEL_NAMES,
        required=True,
        help=(
            "Fee model applied by the engines (bybit | binance | kraken). Independent of the "
            "EXCHANGE data-source constant; recorded in every result entry. No default."
        ),
    )
    parser.add_argument("--workers", type=int, default=None, help="Worker count. Default: auto.")
    parser.add_argument(
        "--timeout",
        type=int,
        default=DEFAULT_TIMEOUT_SEC,
        help=f"Per-job timeout in seconds (default: {DEFAULT_TIMEOUT_SEC}).",
    )
    parser.add_argument("--force", action="store_true", help="Rerun combos already in results.")
    parser.add_argument(
        "--serial", action="store_true", help="Bypass pool, run jobs sequentially (debug)."
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=OUTPUT_PATH,
        help=f"Output JSON path (default: {OUTPUT_PATH}).",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Run only first N jobs (after sort). Useful for quick determinism tests.",
    )
    parser.add_argument(
        "--pair-costs-file",
        type=Path,
        default=None,
        help=(
            "Per-pair spread/slippage JSON (B4.3 campaign): signal market fills and grid "
            "terminal liquidation. Recorded in every result entry, checked on resume."
        ),
    )
    parser.add_argument(
        "--min-order-usdc",
        type=float,
        default=1.0,
        help="Smallest BUY notional the signal engine places (default 1.0; B4.3 campaign: 5).",
    )
    args = parser.parse_args(argv)
    if args.pair_costs_file is not None:
        try:
            sys.path.insert(0, str(Path(__file__).resolve().parent))
            from backtest import load_pair_costs

            load_pair_costs(args.pair_costs_file)  # validate early, workers reload it
        except (OSError, ValueError) as exc:
            parser.error(f"--pair-costs-file: {exc}")
    return args


def main(argv: list[str] | None = None) -> int:
    # Load .env here, not at import time: importing this module must not mutate os.environ
    # (tests import it at collection). Spawn workers inherit the parent's environment.
    load_dotenv(Path(__file__).parent.parent / ".env")
    args = parse_args(argv)

    jobs = build_job_list(
        fees=args.fees,
        pair_costs_file=str(args.pair_costs_file) if args.pair_costs_file else None,
        min_order_usdc=args.min_order_usdc,
    )
    jobs = sort_jobs_by_duration(jobs)

    existing = load_existing_results(args.output)
    try:
        pending = filter_pending_jobs(
            jobs, existing, force=args.force, fees=args.fees, path=args.output
        )
    except FeeModelMismatchError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    if args.limit is not None:
        pending = pending[: args.limit]

    if not pending:
        print(f"No pending jobs. {len(existing)} combos already in {args.output}.")
        return 0

    state = StatusState(total=len(pending))
    results_store = dict(existing)

    n_workers = 1 if args.serial else detect_n_workers(args.workers)
    state.n_workers = n_workers

    logger.info(
        "run_start",
        mode="serial" if args.serial else "parallel",
        n_workers=n_workers,
        pending=len(pending),
        existing=len(existing) - len(pending) if not args.force else 0,
        output=str(args.output),
    )

    stop_event = threading.Event()
    status_thread = threading.Thread(
        target=_status_writer_loop,
        args=(state, STATUS_PATH, stop_event, STATUS_WRITE_INTERVAL),
        daemon=True,
        name="p6-status-writer",
    )
    status_thread.start()

    t0 = time.time()
    try:
        if args.serial:
            run_serial(pending, results_store, state, args.output)
        else:
            run_parallel(
                pending,
                results_store,
                state,
                args.output,
                n_workers=n_workers,
                timeout_sec=args.timeout,
            )
    finally:
        stop_event.set()
        status_thread.join(timeout=10)

    elapsed = time.time() - t0
    print(f"\n{'=' * 60}")
    print("  P6 Phase D — Summary")
    print(f"{'=' * 60}")
    print(f"  Total jobs run: {len(pending)}")
    print(f"  Succeeded: {state.completed_jobs}")
    print(f"  Failed: {len(state.failed_jobs)}")
    print(f"  Mode: {'serial' if args.serial else f'parallel ({n_workers} workers)'}")
    print(f"  Elapsed: {elapsed / 60:.1f} min")
    print(f"  Results: {args.output}")

    return 0 if not state.failed_jobs else 1


if __name__ == "__main__":
    raise SystemExit(main())
