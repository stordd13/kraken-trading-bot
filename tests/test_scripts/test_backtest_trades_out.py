"""--trades-out dump of scripts/backtest.py vs the B4.2 harness capture (no DB)."""

# ruff: noqa: E402
from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
import json
from pathlib import Path
import sys
from unittest.mock import MagicMock

_project_root = str(Path(__file__).resolve().parent.parent.parent)
sys.path.insert(0, _project_root)
sys.path.insert(0, str(Path(_project_root) / "src"))
sys.path.insert(0, str(Path(_project_root) / "scripts"))
sys.path.insert(0, str(Path(_project_root) / "scripts" / "audit"))

import b4_2_reference_capture as harness

from krakenbot.models.base import TradeSide
from scripts.backtest import BacktestEngine, BacktestTrade, dump_trades_json

T0 = datetime(2025, 3, 1, tzinfo=UTC)
T1 = datetime(2025, 3, 15, tzinfo=UTC)


def _engine_with_trades() -> BacktestEngine:
    engine = BacktestEngine(MagicMock(), MagicMock(), fee_model="bybit", exchange="binance")
    engine.metrics.trades = [
        BacktestTrade(
            timestamp=T0,
            side=TradeSide.BUY,
            price=Decimal("28444.01751"),
            amount_usdc=Decimal("50.00"),
            amount_crypto=Decimal("0.001756520504968568344830835396"),
            fee=Decimal("0.0500000"),
            liquidity="maker",
            fee_rate=Decimal("0.0010"),
            fee_base_usdc=Decimal("50.00"),
            reference_price=Decimal("28444.01751"),
            spread_pct=Decimal("0"),
            slippage_pct=Decimal("0"),
        ),
        BacktestTrade(
            timestamp=T1,
            side=TradeSide.SELL,
            price=Decimal("29000") * Decimal("0.9996"),
            amount_usdc=Decimal("49.7"),
            amount_crypto=Decimal("0.001756520504968568344830835396"),
            fee=Decimal("0.125"),
            pnl=Decimal("-0.3"),
            regime="bull",
            liquidity="taker",
            fee_rate=Decimal("0.0025"),
            fee_base_usdc=Decimal("50"),
            reference_price=Decimal("29000"),
            spread_pct=Decimal("0.0002"),
            slippage_pct=Decimal("0.0002"),
        ),
    ]
    engine.metrics.total_fees = Decimal("0.1750000")
    return engine


def _dump(tmp_path: Path) -> dict:
    engine = _engine_with_trades()
    out = tmp_path / "trades.json"
    dump_trades_json(
        engine,
        out,
        pair="BTC/USDC",
        start=T0,
        end=T1,
        exchange="binance",
        interval=5,
        capital=1000.0,
    )
    return json.loads(out.read_text())


def test_dump_schema_and_decimal_strings(tmp_path: Path) -> None:
    payload = _dump(tmp_path)
    assert payload["schema_version"] == 1
    assert payload["engine"] == "BacktestEngine"
    assert payload["fees"] == "bybit"
    assert payload["fee_rates"] == {
        "maker": "0.0010",
        "taker": "0.0025",
        "spread": "0.0002",
        "slippage": "0.0002",
    }
    assert payload["metrics"] == _engine_with_trades().metrics.to_dict()
    buy, sell = payload["trades"]
    assert buy["price"] == "28444.01751"
    assert buy["amount_crypto"] == "0.001756520504968568344830835396"
    assert buy["liquidity"] == "maker"
    assert buy["fee_rate"] == "0.0010"
    assert buy["spread_pct"] == "0"
    assert sell["liquidity"] == "taker"
    assert sell["fee_base_usdc"] == "50"
    assert sell["reference_price"] == "29000"
    assert sell["pnl"] == "-0.3"


def test_dump_matches_the_harness_projection(tmp_path: Path) -> None:
    """The step-0 capture (harness) and the post-refactor dump project onto the same core."""
    payload = _dump(tmp_path)
    reference = harness.capture_payload(
        _engine_with_trades(),
        strategy=payload["strategy"],
        pair="BTC/USDC",
        exchange="binance",
        start=T0,
        end=T1,
        interval=5,
        capital=1000.0,
    )
    assert harness.compare_payloads(reference, payload) is None


def test_dump_passes_verify_fees(tmp_path: Path) -> None:
    payload = _dump(tmp_path)
    violations, counts = harness.verify_fees(payload, harness.FEE_FACTORIES["bybit"]())
    assert violations == []
    assert counts == {"buy/maker": 1, "sell/taker-market": 1}
