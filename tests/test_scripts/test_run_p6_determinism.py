"""Determinism tests for the P6 parallel backtest runner.

These tests run REAL backtests against the database — they require the SSH
tunnel to the Hetzner DB to be active (`nc -zv 127.0.0.1 5433`). They are
skipped automatically when the DB is unreachable.

Three levels:

1. ``test_determinism_serial_vs_serial`` (GATE) — same combo twice in serial
   must yield identical metrics. If this fails, there is a pre-existing
   non-determinism bug in the backtester itself, independent of P6.7.
2. ``test_determinism_parallel_vs_serial`` — same combo, serial vs
   ``multiprocessing.Pool`` must match bit-for-bit. Runs on quick combos in
   CI-friendly time (~minutes).
3. ``test_determinism_parallel_vs_serial_full`` (``@pytest.mark.slow``) —
   all 24 P6 combos. Run manually with ``pytest -m slow`` before merging
   P6.7 → ``dev``.

The hash function ignores keys that cannot be deterministic across runs
(e.g. wall-clock timestamps at the run level). Per-trade timestamps inside
metrics come from the candle data and ARE deterministic.
"""

# ruff: noqa: E402
from __future__ import annotations

from datetime import UTC, datetime
import hashlib
import json
from pathlib import Path
import socket
import sys
from typing import Any

import pytest

_project_root = str(Path(__file__).resolve().parent.parent.parent)
sys.path.insert(0, _project_root)
sys.path.insert(0, str(Path(_project_root) / "src"))
sys.path.insert(0, str(Path(_project_root) / "scripts"))

from scripts import run_p6_backtests as runner

# ---------------------------------------------------------------------------
# DB reachability check — skip module if tunnel is down
# ---------------------------------------------------------------------------


def _db_reachable() -> bool:
    """Return True if the DB at port 5433 (tunnel) or 5432 (local) responds."""
    for port in (5433, 5432):
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=1.0):
                return True
        except OSError:
            continue
    return False


pytestmark = pytest.mark.skipif(
    not _db_reachable(),
    reason="Database not reachable (tunnel down or no local Postgres). "
    "Start the tunnel with `tunnel_ssh_hetzner` then rerun.",
)


# ---------------------------------------------------------------------------
# Combo sets
# ---------------------------------------------------------------------------


# Light signal-based combos chosen to keep per-run < ~60 s.
# A 1-week window loads minimal history while still exercising the full
# warmup → signal → PnL path. Locally (with tunnel up) these tests take
# a few minutes total; on CI without DB access they are skipped entirely
# by ``pytestmark`` above.
QUICK_WINDOW_START = datetime(2025, 3, 1, tzinfo=UTC)
QUICK_WINDOW_END = datetime(2025, 3, 8, tzinfo=UTC)

QUICK_COMBOS = [
    ("grok_supertrend_4h", "BTC/USDC"),
    ("grok_ema_adx_atr", "ETH/USDC"),
    ("gemini_retour_moyenne", "SOL/USDC"),
]

# Full 24 combos for manual pre-merge validation
ALL_24_COMBOS = [(s, p) for s in runner.STRATEGIES for p in runner.PAIRS]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_job(
    strategy: str,
    pair: str,
    start: datetime = QUICK_WINDOW_START,
    end: datetime = QUICK_WINDOW_END,
) -> dict[str, Any]:
    return runner.Job(
        strategy=strategy,
        pair=pair,
        start_iso=start.isoformat(),
        end_iso=end.isoformat(),
        train_ratio=runner.TRAIN_RATIO,
        capital=runner.CAPITAL,
        exchange=runner.EXCHANGE,
        candle_interval=runner.CANDLE_INTERVAL,
        fees="binance",
    ).to_dict()


def _hash_metrics(result: dict[str, Any]) -> str:
    """Stable SHA256 of the numeric metrics. Ignores top-level period echo."""
    payload = {
        "strategy": result.get("strategy"),
        "pair": result.get("pair"),
        "train": result.get("train"),
        "test": result.get("test"),
        "all": result.get("all"),
    }
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, default=str).encode("utf-8")
    ).hexdigest()


def _run_one_combo(
    strategy: str,
    pair: str,
    tmp_path: Path,
    serial: bool,
    start: datetime = QUICK_WINDOW_START,
    end: datetime = QUICK_WINDOW_END,
) -> dict[str, Any]:
    """Run one combo through main() and return the result dict."""
    out = tmp_path / f"{runner.make_key(strategy, pair)}_{'serial' if serial else 'parallel'}.json"
    # Monkey patch the job list for this invocation
    jobs = [_make_job(strategy, pair, start, end)]
    original_build = runner.build_job_list
    runner.build_job_list = lambda **_: list(jobs)  # type: ignore[assignment]
    try:
        argv = ["--output", str(out), "--force", "--fees", "binance"]
        if serial:
            argv.append("--serial")
        else:
            argv.extend(["--workers", "2"])
        rc = runner.main(argv)
        assert rc == 0, f"run failed for {strategy} {pair}"
        data = json.loads(out.read_text())
        key = runner.make_key(strategy, pair)
        return data[key]
    finally:
        runner.build_job_list = original_build  # type: ignore[assignment]


# ---------------------------------------------------------------------------
# GATE — backtester itself must be deterministic
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("combo", QUICK_COMBOS)
def test_determinism_serial_vs_serial(combo: tuple[str, str], tmp_path: Path) -> None:
    """Gate test: two serial runs of the same combo must match exactly.

    Fails ⇒ pre-existing non-determinism bug in the backtester (seed, float
    aggregation order, dict ordering). Not a P6.7 blocker, but blocks the
    parallel-vs-serial interpretation below.
    """
    strategy, pair = combo
    r1 = _run_one_combo(strategy, pair, tmp_path, serial=True)
    r2 = _run_one_combo(strategy, pair, tmp_path, serial=True)
    assert _hash_metrics(r1) == _hash_metrics(r2), (
        f"Serial-vs-serial drift for {strategy} {pair}. "
        "Backtester is non-deterministic — file as a separate bug."
    )


# ---------------------------------------------------------------------------
# CI — parallel must match serial for the quick combos
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("combo", QUICK_COMBOS)
def test_determinism_parallel_vs_serial(combo: tuple[str, str], tmp_path: Path) -> None:
    """Parallel pool result must match serial result bit-for-bit."""
    strategy, pair = combo
    serial = _run_one_combo(strategy, pair, tmp_path, serial=True)
    parallel = _run_one_combo(strategy, pair, tmp_path, serial=False)
    assert _hash_metrics(serial) == _hash_metrics(parallel), (
        f"Parallel drift for {strategy} {pair} — "
        "jobs produced different metrics in the Pool vs. serial."
    )


# ---------------------------------------------------------------------------
# Pre-merge — all 24 combos over full P6 range
# ---------------------------------------------------------------------------


@pytest.mark.slow
@pytest.mark.parametrize("combo", ALL_24_COMBOS)
def test_determinism_parallel_vs_serial_full(combo: tuple[str, str], tmp_path: Path) -> None:
    """Full-range determinism check. Manual: `pytest -m slow`.

    Expected wall-clock: ~45 min total across 24 combos. Run before merging
    P6.7 into ``dev``.
    """
    strategy, pair = combo
    serial = _run_one_combo(
        strategy,
        pair,
        tmp_path,
        serial=True,
        start=runner.P6_START,
        end=runner.P6_END,
    )
    parallel = _run_one_combo(
        strategy,
        pair,
        tmp_path,
        serial=False,
        start=runner.P6_START,
        end=runner.P6_END,
    )
    assert _hash_metrics(serial) == _hash_metrics(parallel)
