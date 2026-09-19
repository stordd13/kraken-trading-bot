"""C2 — provenance: results produced before and after the replay chantier are never mixed.

Same pattern as the C1 ``metrics_version`` guard: every P6 / P7 / walk-forward entry, every
``--trades-out`` dump and equity sidecar carries ``replay_version`` at the top level; a file
whose entries lack it (every B4 / C1 file) or carry another value is refused by the resume,
the phase-2 seeding, the survivors, the report tools — ``--force`` included. The replay check
is the last of the four (fees → campaign costs → metrics → replay).
"""

# ruff: noqa: E402
from __future__ import annotations

from datetime import UTC, datetime
import json
from pathlib import Path
import sys
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

_project_root = str(Path(__file__).resolve().parents[2])
sys.path.insert(0, _project_root)
sys.path.insert(0, str(Path(_project_root) / "src"))
sys.path.insert(0, str(Path(_project_root) / "scripts"))

import filter_p6_survivors as fs

from krakenbot.replay_contract import REPLAY_VERSION
from scripts import run_p6_backtests as p6
from scripts import run_p6_walkforward as wf
from scripts import run_p7_grid_search as p7
from scripts.backtest import BacktestEngine, dump_equity_jsonl, dump_trades_json

KEY = "grok_supertrend_4h_BTC_USDC"


def _job(fees: str = "bybit") -> dict:
    return {
        "strategy": "grok_supertrend_4h",
        "pair": "BTC/USDC",
        "fees": fees,
        "pair_costs_file": None,
        "min_order_usdc": 1.0,
    }


def _entry(**overrides: object) -> dict:
    base: dict = {
        "fees": "bybit",
        "metrics_version": 2,
        "replay_version": REPLAY_VERSION,
        "test": {},
    }
    base.update(overrides)
    return base


# ---------------------------------------------------------------------------
# P6 runner
# ---------------------------------------------------------------------------


def test_p6_resume_refuses_a_post_c1_pre_c2_file_force_included() -> None:
    jobs = [_job()]
    post_c1 = {KEY: _entry(replay_version=None)}
    del post_c1[KEY]["replay_version"]
    with pytest.raises(p6.ReplayVersionMismatchError, match="absent: pre-C2 file"):
        p6.filter_pending_jobs(jobs, post_c1, force=False, fees="bybit")
    with pytest.raises(p6.ReplayVersionMismatchError):
        p6.filter_pending_jobs(jobs, post_c1, force=True, fees="bybit")  # no escape
    with pytest.raises(p6.ReplayVersionMismatchError, match="replay_version=1"):
        p6.filter_pending_jobs(jobs, {KEY: _entry(replay_version=1)}, force=False, fees="bybit")
    # a disjoint key never lets a job into a pre-C2 file either
    with pytest.raises(p6.ReplayVersionMismatchError):
        p6.filter_pending_jobs([dict(_job(), pair="ETH/USDC")], post_c1, force=False, fees="bybit")
    # homogeneous post-C2 file: the finished key is skipped, --force recomputes it
    assert p6.filter_pending_jobs(jobs, {KEY: _entry()}, force=False, fees="bybit") == []
    assert p6.filter_pending_jobs(jobs, {KEY: _entry()}, force=True, fees="bybit") == jobs
    # error entries are exempt (as for every other guard)
    assert p6.filter_pending_jobs(jobs, {KEY: {"error": "boom"}}, force=False, fees="bybit") == jobs


def test_p6_check_order_is_fees_then_campaign_then_metrics_then_replay() -> None:
    path = Path("x.json")
    with pytest.raises(p6.FeeModelMismatchError) as exc:
        p6._check_entry(KEY, {"fees": "binance"}, fees="bybit", wanted=None, path=path)
    assert not isinstance(exc.value, p6.ReplayVersionMismatchError)
    with pytest.raises(p6.CampaignConfigMismatchError):
        p6._check_entry(KEY, {"fees": "bybit"}, fees="bybit", wanted=("c.json", 5.0), path=path)
    with pytest.raises(p6.MetricsVersionMismatchError):
        p6._check_entry(KEY, {"fees": "bybit"}, fees="bybit", wanted=None, path=path)
    with pytest.raises(p6.ReplayVersionMismatchError):
        p6._check_entry(
            KEY, {"fees": "bybit", "metrics_version": 2}, fees="bybit", wanted=None, path=path
        )
    p6._check_entry(KEY, _entry(), fees="bybit", wanted=None, path=path)


# ---------------------------------------------------------------------------
# P7 runner
# ---------------------------------------------------------------------------


def test_p7_phase2_seeding_and_resume_refuse_pre_c2_entries(tmp_path: Path) -> None:
    top_k = {
        ("grok_supertrend_4h", "BTC/USDC"): [{"fees": "bybit", "metrics_version": 2, "params": {}}]
    }
    with pytest.raises(p7.ReplayVersionMismatchError, match="pre-C2"):
        p7.build_phase2_jobs(top_k, fees="bybit")
    ok = {("grok_supertrend_4h", "BTC/USDC"): [_entry(params={})]}
    assert p7.build_phase2_jobs(ok, fees="bybit")
    with pytest.raises(p7.ReplayVersionMismatchError):
        p7._assert_results_fee_model(
            {"k": {"fees": "bybit", "metrics_version": 2}}, "bybit", tmp_path / "p.json"
        )
    p7._assert_results_fee_model({"k": _entry(), "e": {"error": "x"}}, "bybit", tmp_path / "p.json")


# ---------------------------------------------------------------------------
# Walk-forward and the P6 tools
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_walkforward_refuses_post_c1_pre_c2_survivors(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    survivors = tmp_path / "survivors.json"
    survivors.write_text(
        json.dumps(
            {
                KEY: {
                    "strategy": "grok_supertrend_4h",
                    "pair": "BTC/USDC",
                    "fees": "bybit",
                    "metrics_version": 2,
                }
            }
        )
    )
    rc = await wf.main(["--fees", "bybit", "--survivors", str(survivors)])
    assert rc == 2 and "pre-C2" in capsys.readouterr().err


def test_filter_survivors_refuses_a_pre_c2_phase_d_file(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    phase_d = tmp_path / "phase_d.json"
    phase_d.write_text(
        json.dumps(
            {
                "s_BTC_USDC": {
                    "strategy": "s",
                    "pair": "BTC/USDC",
                    "fees": "bybit",
                    "metrics_version": 2,
                    "test": {},
                }
            }
        )
    )
    with pytest.raises(SystemExit) as exc:
        fs.main(
            [
                "--input",
                str(phase_d),
                "--benchmarks",
                str(tmp_path / "none.json"),
                "--survivors",
                str(tmp_path / "s.json"),
                "--report",
                str(tmp_path / "r.md"),
            ]
        )
    assert exc.value.code == 2 and "pre-C2" in capsys.readouterr().err


# ---------------------------------------------------------------------------
# Dumps
# ---------------------------------------------------------------------------


def test_dumps_carry_the_replay_version_at_the_top_level_only(tmp_path: Path) -> None:
    settings = SimpleNamespace(
        trading=SimpleNamespace(pair="BTC/USDC", default_order_amount_eur=50)
    )
    engine = BacktestEngine(
        settings,
        MagicMock(),
        fee_model="bybit",
        strategy_name="grok_supertrend_4h",
        candle_interval=5,
    )
    engine.calculate_final_metrics()
    t0 = datetime(2024, 1, 1, tzinfo=UTC)
    out = tmp_path / "d.json"
    dump_trades_json(
        engine,
        out,
        pair="BTC/USDC",
        start=t0,
        end=t0,
        exchange="binance",
        interval=5,
        capital=1000.0,
    )
    payload = json.loads(out.read_text())
    assert payload["replay_version"] == REPLAY_VERSION == 2
    assert "replay_version" not in payload["metrics"]  # never inside the metrics contract
    sidecar = tmp_path / "e.jsonl"
    dump_equity_jsonl(engine, sidecar, pair="BTC/USDC")
    assert json.loads(sidecar.read_text().splitlines()[0])["replay_version"] == 2


# ---------------------------------------------------------------------------
# p7_report: a metrics_version 2 report must be one replay contract; the v1 legacy path
# (frozen B4 files, no version key at all) is untouched — see the C12 reproduction test.
# ---------------------------------------------------------------------------


def test_p7_report_refuses_v2_inputs_without_a_replay_version(tmp_path: Path) -> None:
    import p7_report as r

    from krakenbot.replay_contract import ReplayVersionError

    phase1 = tmp_path / "p1.json"
    phase2 = tmp_path / "p2.json"
    phase1.write_text(
        json.dumps(
            {
                "k_p1_x": {
                    "strategy": "s",
                    "pair": "BTC/USDC",
                    "fees": "bybit",
                    "metrics_version": 2,
                    "params": {},
                    "phase": "1",
                    "test": {"metrics_version": 2},
                }
            }
        )
    )
    phase2.write_text(json.dumps({}))
    with pytest.raises(ReplayVersionError, match="pre-C2"):
        r.generate_report(phase1, phase2, tmp_path / "r.md", tmp_path / "s.json", benchmarks={})
