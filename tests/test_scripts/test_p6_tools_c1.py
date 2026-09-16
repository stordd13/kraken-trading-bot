"""C1 — the P6 tools (survivor filter, report) on the None-aware contract (no DB)."""

# ruff: noqa: E402
from __future__ import annotations

import json
from pathlib import Path
import sys

import pytest

_project_root = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(_project_root))
sys.path.insert(0, str(_project_root / "src"))
sys.path.insert(0, str(_project_root / "scripts"))

from scripts import filter_p6_survivors as fs
from scripts import generate_p6_report as gr

GOOD = {
    "metrics_version": 2,
    "sharpe_ratio": 1.2,
    "sortino_ratio": 1.6,
    "max_drawdown_pct_daily": 10.0,
    "profit_factor": 1.8,
    "calmar_ratio": 0.9,
    "total_trades": 40,
}


def test_check_criteria_passes_and_fails_on_undefined() -> None:
    assert fs.check_criteria(GOOD, "grok_supertrend_4h") == []
    undefined = dict(GOOD, sharpe_ratio=None, profit_factor=None)
    failures = fs.check_criteria(undefined, "grok_supertrend_4h")
    assert any(f.startswith("Sharpe undefined") for f in failures)
    assert any(f.startswith("PF undefined") for f in failures)
    assert not any("0.00" in f for f in failures)  # never a fake 0
    legacy_dd = dict(GOOD)
    legacy_dd.pop("max_drawdown_pct_daily")
    assert fs.check_criteria(dict(legacy_dd, max_drawdown_pct=40.0), "s") == ["MaxDD 40.0% > 25.0%"]
    assert fs.check_criteria(legacy_dd, "s") == ["MaxDD undefined (n/a) — threshold 25.0% not met"]


def test_check_consistency_and_benchmark_are_none_aware() -> None:
    assert fs.check_consistency({"sharpe_ratio": None}, GOOD) == (
        "Overfit check undefined: a Sharpe is undefined (n/a)"
    )
    assert fs.check_consistency({"sharpe_ratio": 1.0}, {"sharpe_ratio": 0.9}) is None
    bench = {
        "buy_and_hold": {"BTC/USDC": {"sharpe_ratio": None}},
        "dca_fixed_15usd_weekly": {"BTC/USDC": {"sharpe_ratio": 0.5}},
    }
    assert fs.check_beats_benchmark(GOOD, "BTC/USDC", bench) is True
    assert fs.check_beats_benchmark({"sharpe_ratio": None}, "BTC/USDC", bench) is False
    assert fs.check_beats_benchmark({"sharpe_ratio": 5.0}, "ETH/USDC", bench) is False


def test_tools_refuse_a_pre_c1_phase_d_file(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    phase_d = tmp_path / "phase_d.json"
    phase_d.write_text(
        json.dumps(
            {"s_BTC_USDC": {"strategy": "s", "pair": "BTC/USDC", "fees": "bybit", "test": {}}}
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
    assert exc.value.code == 2 and "pre-C1" in capsys.readouterr().err


def test_report_helpers_display_undefined_as_na() -> None:
    assert gr._m({"sharpe_ratio": None}, "sharpe_ratio") == "n/a"
    assert gr._m({"profit_factor": float("inf")}, "profit_factor") == "∞"
    assert gr._m({"sharpe_ratio": 1.234}, "sharpe_ratio") == "1.23"
    assert gr._dd({"max_drawdown_pct_daily": 3.14}) == "3.1"
    assert gr._dd({"max_drawdown_pct": 2.5}) == "2.5"
    assert gr._dd({}) == "n/a"
