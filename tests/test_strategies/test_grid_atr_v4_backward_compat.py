"""Backward-compatibility gold-hash test for grok_grid_atr_adaptive_v4.

This test is the strict gate for any modification to GrokGridATRAdaptiveV4:
running a backtest against historical Binance data with the CURRENT
strategies.yaml params MUST produce a bit-identical metrics hash to the
``EXPECTED_HASH`` baseline frozen below.

The baseline was captured on branch ``feat/p7-parameter-optimization``
BEFORE the introduction of ``bear_protection_mode``, re-baselined in B4.2 on
the re-stamped Binance data and again in B4.3 after the grid engine fixes
(see ``EXPECTED_HASHES``: one hash per fee model, binance and bybit). Any code
change that shifts a trade timestamp, fee calc, fill price, liquidation or
PnL aggregation will break these hashes — which is the intent.

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

# Set a value to None to print the actual hash on first run, then paste it back here.
# History:
# - 2026-05-29 (feat/p7-parameter-optimization, pre-bear_protection_mode, open-stamped
#   Binance data): 32c157cd30dfe3858eb6cb36876fef3c13e9ee0e8e1725d308ee6bc0dcfe955a
# - 2026-09-14 (B4.2, gate decision n3): re-baselined on the B4.1 re-stamped data
#   (period-end timestamps, results/B4_1_timestamp_restamp_report.md § 7.2) under the
#   Binance BNB flat fee model (maker == taker == 0.075 %, the runner's model since P6):
#   abb3a6d80c918eb8d3ec1ebf9a16b3fc8ba29b23c785ccfb057cf90a3076a60b
# - 2026-09-14 (B4.3 chantier 0, GO Bruno D10): re-baselined once, after the two engine
#   fixes — (a) the terminal inventory is liquidated at MARKET on the last tradeable close
#   (taker + spread + slippage, balances settled, final equity point) and (b) net_pnl =
#   total_pnl - buy fees (sell fees were counted twice). The window ends with open lots in
#   the train and all segments (5-minute bars, split 2025-03-10T19:12Z). Under --fees binance:
#     train: 38 trades (25 W / 13 L, 13 liquidated lots, liquidation P&L -30.42),
#            net_pnl -21.99 == ending 978.01 - 1000, MaxDD 2.84 %
#     test:   6 trades (6 W, inventory empty at the end, 0 liquidation), net_pnl 2.02
#     all:   45 trades (37 W / 8 L = the 8 open lots, liquidation P&L -11.12, PF 1.2125,
#            ending 1001.52, return +0.152 %, MaxDD 3.05 %), net_pnl 1.52 == ending - 1000
#   Fix (b) alone moved net_pnl by exactly +sum(sell fees): +0.6965 / +0.1141 / +0.8455.
#   A second hash pins the campaign fee model (--fees bybit, same window): all = 45 trades,
#   8 L, PF 1.1552, liquidation P&L -11.47, net_pnl 0.65 == ending 1000.65 - 1000.
#   First values (commit 19d1ded): binance 71d68b95…, bybit 97cae113….
# - 2026-09-14 (B4.3 chantier 0, review fix): average_holding_time_minutes excludes the
#   forced liquidations (they share the final timestamp and were each matched to the run's
#   last buy: all 594.22 -> 323.78 = the pre-chantier value, train 227.76 -> 286.40); the
#   liquidated lots' real holding time now lives in the dump's liquidation block. Every other
#   key of the three segments is unchanged (binance and bybit).
EXPECTED_HASHES: dict[str, str | None] = {
    "binance": "43dcdf8d283db5c837f9d98d5e38dbddf1717f71177d4a19d9ea36460cf39faf",
    "bybit": "818d7fa875d5626bda6f7862739eadda5fb7e24622703a86841f00162397f39a",
}


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


def _run_combo(tmp_path: Path, fees: str) -> dict[str, Any]:
    """Run grok_grid_atr_adaptive_v4 on BTC/USDC over the frozen window under ``fees``."""
    out = tmp_path / f"grid_atr_v4_backward_compat_{fees}.json"
    job = runner.Job(
        strategy=STRATEGY,
        pair=PAIR,
        start_iso=WINDOW_START.isoformat(),
        end_iso=WINDOW_END.isoformat(),
        train_ratio=runner.TRAIN_RATIO,
        capital=runner.CAPITAL,
        exchange=runner.EXCHANGE,
        candle_interval=runner.CANDLE_INTERVAL,
        fees=fees,
    ).to_dict()

    original_build = runner.build_job_list
    runner.build_job_list = lambda **_: [job]  # type: ignore[assignment]
    try:
        argv = ["--output", str(out), "--force", "--serial", "--fees", fees]
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


@pytest.mark.parametrize("fees", sorted(EXPECTED_HASHES))
def test_grid_atr_v4_backward_compat_hash(tmp_path: Path, fees: str) -> None:
    """Frozen bit-exact hash on the current grid_atr_v4 YAML config, per fee model.

    If this fails, the current branch has drifted from the B4.3 baseline.
    Investigate before continuing.
    """
    result = _run_combo(tmp_path, fees)
    actual = _hash_metrics(result)
    expected = EXPECTED_HASHES[fees]

    if expected is None:
        pytest.fail(
            f"EXPECTED_HASHES[{fees!r}] is None — initial baseline run.\n"
            f"Computed hash: {actual}\n"
            "Paste this value into EXPECTED_HASHES at the top of this file."
        )

    assert actual == expected, (
        f"grid_atr_v4 backward-compat hash drifted ({fees}).\n"
        f"  expected: {expected}\n"
        f"  actual:   {actual}\n"
        "A change in this branch altered the engine's deterministic output. "
        "If intentional, update EXPECTED_HASHES; otherwise investigate."
    )
