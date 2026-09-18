"""C2 (preuve 4, réel) — the P6 rerun of the three grid jobs (BTC / ETH / SOL, train / test /
all, class defaults, --fees bybit, GATE B pair costs, 5 USDC floor) reconciles: the SOL
entry that B4 flagged (40 lots sold twice, dette 14) shows no inventory divergence and no
unmatched sell.

Order of the assertions (Bruno): presence / validity first — the entry exists WITHOUT an
``error`` key (``collect_flags`` skips error entries silently: a failed job would be a false
green), the three segments, the accounting fields and the liquidation block are present,
the values parse — then the tolerances of the canonical flag rule (``scripts/b4_flags.py``),
then the counters at zero. A negative test removes the liquidation block: the proof fails.
"""

# ruff: noqa: E402
from __future__ import annotations

import copy
from datetime import datetime, timedelta
from decimal import Decimal
import json
from pathlib import Path
import sys

import pytest

_project_root = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_project_root))
sys.path.insert(0, str(_project_root / "src"))
sys.path.insert(0, str(_project_root / "scripts"))

import b4_flags

ARTIFACT = _project_root / "results" / "c2_replay" / "P6_grid_rerun.json"
SEGMENTS = ("train", "test", "all")
ACCOUNTING = ("total_trades", "net_pnl", "ending_balance", "total_fees", "total_pnl")
ZERO_COUNTERS = ("unmatched_sell_fills", "unmatched_position_id", "ambiguous_sell_fill")

pytestmark = pytest.mark.skipif(not ARTIFACT.exists(), reason="P6 grid rerun artifact absent")


def _load() -> dict:
    return json.loads(ARTIFACT.read_text(encoding="utf-8"))


def _assert_reconciled(data: dict, key: str) -> None:
    # 1. presence / validity
    assert key in data, f"{key} missing from the artifact"
    entry = data[key]
    assert "error" not in entry, f"{key} is a failed job: {entry.get('error')}"
    assert entry["fees"] == "bybit" and entry["min_order_usdc"] == 5.0
    assert entry["replay_version"] == 2 and entry["metrics_version"] == 2
    for segment in SEGMENTS:
        metrics = entry[segment]
        for field in ACCOUNTING:
            assert field in metrics, f"{key}/{segment}: {field} missing"
            assert isinstance(metrics[field], int | float)
        liquidation = entry["liquidation"][segment]
        for field in ("inventory_divergence_btc", "net_pnl_lot_basis", "residual_net_proceeds"):
            Decimal(str(liquidation[field]))  # parses
        assert entry["rejections"][segment]["unit"] == "(order, cause)"
        assert entry["warmup"][segment]["4h"]["required"] >= 14
    # 2. tolerances — the canonical B4 flag rule, unchanged
    flags = b4_flags.flag_entry(key, entry)
    assert flags == [], f"{key}: flagged {flags}"
    # 3. counters at zero on every segment
    for segment in SEGMENTS:
        by_cause = entry["rejections"][segment]["by_cause"]
        assert all(by_cause[c] == 0 for c in ZERO_COUNTERS), f"{key}/{segment}: {by_cause}"


@pytest.mark.parametrize("pair", ["SOL_USDC", "BTC_USDC", "ETH_USDC"])
def test_grid_rerun_entry_is_present_valid_and_reconciled(pair: str) -> None:
    _assert_reconciled(_load(), f"grok_grid_atr_adaptive_v4_{pair}")


def _segment_start(entry: dict, segment: str) -> datetime:
    period = entry["period"]
    return datetime.fromisoformat(period["split" if segment == "test" else "start"])


def test_sol_warmup_is_reported_insufficient_per_segment_not_bridged() -> None:
    """SOL starts 2023-04-01 inside its 455-day hole: on train and all every timeframe is
    insufficient — the 4h history does not reach start, the 1d / 1w histories stop inside
    the hole, stale by exactly the stamps expected between their last candle and start (the
    candle stamped start included: commit 12 contract) — reported, never certified. The
    observed values (loaded / stale) live in the C2 report § 3.4, not here."""
    entry = _load()["grok_grid_atr_adaptive_v4_SOL_USDC"]
    for segment in ("train", "all"):
        start = _segment_start(entry, segment)
        for tf in ("4h", "1d", "1w"):
            report = entry["warmup"][segment][tf]
            assert report["sufficient"] is False, f"{segment}/{tf}"
            if report["last"] is None:
                assert report["loaded"] == 0 and report["stale_by_candles"] is None
                continue
            last = datetime.fromisoformat(report["last"])
            expected = int((start - last) / timedelta(minutes=report["interval"]))
            assert report["stale_by_candles"] == expected > 0, f"{segment}/{tf}"
    assert entry["warmup"]["test"]["4h"]["sufficient"] is True  # the test segment is clean


def test_every_warmup_block_reports_the_staleness_contract() -> None:
    """On every pair / segment / timeframe: ``stale_by_candles`` == the number of stamps
    ``last + k × interval`` (k >= 1) at or before the segment start (0 when the last loaded
    candle is the one stamped start, or when start is not aligned on the timeframe **and the
    next stamp after last falls past start** — a non-aligned start is not stale-free by
    itself: the SOL 1w history starts on a Saturday and is stale by 25)."""
    for key, entry in _load().items():
        for segment in SEGMENTS:
            start = _segment_start(entry, segment)
            for tf, report in entry["warmup"][segment].items():
                if report["last"] is None:
                    assert report["stale_by_candles"] is None, f"{key}/{segment}/{tf}"
                    continue
                last = datetime.fromisoformat(report["last"])
                assert last <= start
                expected = int((start - last) / timedelta(minutes=report["interval"]))
                assert report["stale_by_candles"] == expected, f"{key}/{segment}/{tf}"
                assert report["sufficient"] == (
                    report["loaded"] >= report["required"]
                    and expected == 0
                    and report["largest_gap_candles"] <= 1
                ), f"{key}/{segment}/{tf}"


def test_the_proof_fails_when_the_liquidation_block_is_missing_or_the_job_errored() -> None:
    data = _load()
    key = "grok_grid_atr_adaptive_v4_SOL_USDC"
    broken = copy.deepcopy(data)
    del broken[key]["liquidation"]
    with pytest.raises((AssertionError, KeyError)):
        _assert_reconciled(broken, key)
    errored = copy.deepcopy(data)
    errored[key] = {"strategy": "grok_grid_atr_adaptive_v4", "pair": "SOL/USDC", "error": "boom"}
    assert b4_flags.collect_flags(errored) == b4_flags.collect_flags(
        {k: v for k, v in data.items() if k != key}
    )
    with pytest.raises(AssertionError, match="failed job"):
        _assert_reconciled(errored, key)
