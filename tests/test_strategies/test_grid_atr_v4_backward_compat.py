"""Backward-compatibility gold-hash test for grok_grid_atr_adaptive_v4.

This test is the strict gate for any modification to GrokGridATRAdaptiveV4:
running a backtest against historical Binance data with the CURRENT
strategies.yaml params MUST produce a bit-identical metrics hash to the
``EXPECTED_HASH`` baseline frozen below.

The baseline was captured on branch ``feat/p7-parameter-optimization``
BEFORE the introduction of ``bear_protection_mode``. Any code change that
shifts a trade timestamp, fee calc, fill price, or PnL aggregation will
break this hash — which is the intent.

Skip behavior: auto-skip if the DB tunnel is unreachable (same pattern
as ``test_run_p6_determinism.py``).
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
# Frozen baseline
# ---------------------------------------------------------------------------

STRATEGY = "grok_grid_atr_adaptive_v4"
PAIR = "BTC/USDC"
WINDOW_START = datetime(2025, 3, 1, tzinfo=UTC)
WINDOW_END = datetime(2025, 3, 15, tzinfo=UTC)

# Set to None to print the actual hash on first run, then paste it back here.
# Baseline captured 2026-05-29 on branch feat/p7-parameter-optimization,
# pre-bear_protection_mode introduction. See plan in
# .claude/plans/ok-c-est-parti-pour-binary-bunny.md (Phase A, point 4-bis).
EXPECTED_HASH: str | None = "32c157cd30dfe3858eb6cb36876fef3c13e9ee0e8e1725d308ee6bc0dcfe955a"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _hash_metrics(result: dict[str, Any]) -> str:
    """Stable SHA256 of the numeric metrics (ignores wall-clock period echo)."""
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


def _run_combo(tmp_path: Path) -> dict[str, Any]:
    """Run grok_grid_atr_adaptive_v4 on BTC/USDC over the frozen window."""
    out = tmp_path / "grid_atr_v4_backward_compat.json"
    job = runner.Job(
        strategy=STRATEGY,
        pair=PAIR,
        start_iso=WINDOW_START.isoformat(),
        end_iso=WINDOW_END.isoformat(),
        train_ratio=runner.TRAIN_RATIO,
        capital=runner.CAPITAL,
        exchange=runner.EXCHANGE,
        candle_interval=runner.CANDLE_INTERVAL,
    ).to_dict()

    original_build = runner.build_job_list
    runner.build_job_list = lambda: [job]  # type: ignore[assignment]
    try:
        argv = ["--output", str(out), "--force", "--serial"]
        rc = runner.main(argv)
        assert rc == 0, "backtest run failed"
        data = json.loads(out.read_text())
        key = runner.make_key(STRATEGY, PAIR)
        return data[key]
    finally:
        runner.build_job_list = original_build  # type: ignore[assignment]


# ---------------------------------------------------------------------------
# Test
# ---------------------------------------------------------------------------


def test_grid_atr_v4_backward_compat_hash(tmp_path: Path) -> None:
    """Frozen bit-exact hash on the current grid_atr_v4 + binance YAML config.

    If this fails, the current branch has drifted from the pre-P7 baseline.
    Investigate before continuing.
    """
    result = _run_combo(tmp_path)
    actual = _hash_metrics(result)

    if EXPECTED_HASH is None:
        pytest.fail(
            "EXPECTED_HASH is None — initial baseline run.\n"
            f"Computed hash: {actual}\n"
            "Paste this value into EXPECTED_HASH at the top of this file."
        )

    assert actual == EXPECTED_HASH, (
        f"grid_atr_v4 backward-compat hash drifted.\n"
        f"  expected: {EXPECTED_HASH}\n"
        f"  actual:   {actual}\n"
        "A change in this branch altered the strategy's deterministic output. "
        "If intentional, update EXPECTED_HASH; otherwise investigate."
    )
