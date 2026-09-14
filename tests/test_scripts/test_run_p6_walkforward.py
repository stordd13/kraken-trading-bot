"""CLI and fee-model plumbing of scripts/run_p6_walkforward.py (B4.2, no DB)."""

# ruff: noqa: E402
from __future__ import annotations

from datetime import UTC, datetime
import json
from pathlib import Path
import sys
from typing import Any

import pytest

_project_root = str(Path(__file__).resolve().parent.parent.parent)
sys.path.insert(0, _project_root)
sys.path.insert(0, str(Path(_project_root) / "src"))
sys.path.insert(0, str(Path(_project_root) / "scripts"))

import run_p6_walkforward as wf


def test_missing_fees_exits_2(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as exc:
        wf.parse_args([])
    assert exc.value.code == 2
    assert "--fees" in capsys.readouterr().err


def test_defaults_with_fees(tmp_path: Path) -> None:
    args = wf.parse_args(["--fees", "bybit", "--survivors", str(tmp_path / "s.json")])
    assert args.fees == "bybit"
    assert args.survivors == tmp_path / "s.json"
    assert args.output == wf.OUTPUT_PATH


@pytest.mark.asyncio
async def test_survivor_fee_mismatch_returns_2(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    survivors = tmp_path / "survivors.json"
    survivors.write_text(
        json.dumps({"k": {"strategy": "grok_supertrend_4h", "pair": "BTC/USDC", "fees": "binance"}})
    )
    rc = await wf.main(["--fees", "bybit", "--survivors", str(survivors)])
    assert rc == 2
    assert "fees=binance" in capsys.readouterr().err


@pytest.mark.asyncio
async def test_legacy_survivors_without_fees_return_2(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    survivors = tmp_path / "survivors.json"
    survivors.write_text(json.dumps({"k": {"strategy": "grok_supertrend_4h", "pair": "BTC/USDC"}}))
    rc = await wf.main(["--fees", "bybit", "--survivors", str(survivors)])
    assert rc == 2
    assert "pre-B4.2" in capsys.readouterr().err


@pytest.mark.asyncio
async def test_missing_survivors_file_returns_1(tmp_path: Path) -> None:
    rc = await wf.main(["--fees", "bybit", "--survivors", str(tmp_path / "none.json")])
    assert rc == 1


class _FakeEngine:
    calls: list[dict[str, Any]] = []

    def __init__(self, settings: object, db_manager: object, **kwargs: Any) -> None:
        _FakeEngine.calls.append(kwargs)
        self.metrics = type("M", (), {"to_dict": staticmethod(lambda: {"sharpe_ratio": 1.0})})()

    async def run(self, pair: str, start: datetime, end: datetime) -> None:
        pass


@pytest.mark.asyncio
async def test_fee_model_is_passed_to_both_engines(monkeypatch: pytest.MonkeyPatch) -> None:
    _FakeEngine.calls.clear()
    monkeypatch.setattr(wf, "GridBacktester", _FakeEngine)
    monkeypatch.setattr(wf, "BacktestEngine", _FakeEngine)
    t0, t1 = datetime(2024, 1, 1, tzinfo=UTC), datetime(2024, 4, 1, tzinfo=UTC)
    await wf.run_single_backtest(
        object(), object(), "grok_grid_atr_adaptive_v4", "BTC/USDC", t0, t1, fee_model="bybit"
    )
    await wf.run_single_backtest(
        object(), object(), "grok_supertrend_4h", "BTC/USDC", t0, t1, fee_model="bybit"
    )
    assert [c["fee_model"] for c in _FakeEngine.calls] == ["bybit", "bybit"]
    assert {c["exchange"] for c in _FakeEngine.calls} == {wf.EXCHANGE}
