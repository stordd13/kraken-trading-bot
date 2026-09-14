"""CLI contract of scripts/backtest.py after B4.2 (--fees mandatory, no DB)."""

# ruff: noqa: E402
from __future__ import annotations

from pathlib import Path
import sys

import pytest

_project_root = str(Path(__file__).resolve().parent.parent.parent)
sys.path.insert(0, _project_root)
sys.path.insert(0, str(Path(_project_root) / "src"))
sys.path.insert(0, str(Path(_project_root) / "scripts"))

from scripts.backtest import parse_args

BASE = ["--strategy", "grok_supertrend_4h", "--pair", "BTC/USDC", "--exchange", "binance"]


def test_missing_fees_exits_2(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as exc:
        parse_args(BASE)
    assert exc.value.code == 2
    assert "--fees" in capsys.readouterr().err


def test_invalid_fees_choice_exits_2(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as exc:
        parse_args([*BASE, "--fees", "ftx"])
    assert exc.value.code == 2
    assert "invalid choice" in capsys.readouterr().err


@pytest.mark.parametrize("model", ["bybit", "binance", "kraken"])
def test_each_fee_model_is_accepted(model: str) -> None:
    args = parse_args([*BASE, "--fees", model])
    assert args.fees == model
    assert args.exchange == "binance"
    assert args.pair_costs_file is None
    assert args.trades_out is None


def test_pair_costs_file_refused_with_grid_strategy(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    costs = tmp_path / "costs.json"
    costs.write_text('{"BTC/USDC": {"spread": "0.0002", "slippage": "0.0002"}}')
    with pytest.raises(SystemExit) as exc:
        parse_args(
            [
                "--strategy",
                "grok_grid_atr_adaptive_v4",
                "--pair",
                "BTC/USDC",
                "--exchange",
                "binance",
                "--fees",
                "bybit",
                "--pair-costs-file",
                str(costs),
            ]
        )
    assert exc.value.code == 2
    assert "GridBacktester" in capsys.readouterr().err


def test_trades_out_refused_with_cross_validate(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    with pytest.raises(SystemExit) as exc:
        parse_args(
            [*BASE, "--fees", "bybit", "--cross-validate", "--trades-out", str(tmp_path / "t.json")]
        )
    assert exc.value.code == 2
    assert "--trades-out" in capsys.readouterr().err


def test_help_states_fees_are_independent_of_exchange(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit):
        parse_args(["--help"])
    out = capsys.readouterr().out
    assert "--fees" in out
    assert "data source" in out
