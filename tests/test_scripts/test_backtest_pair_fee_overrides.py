"""Per-pair spread/slippage overrides of the signal engine (B4.2, no DB).

The default path must return the fee model's own Decimal objects (bit-exact), an override
must only touch its pair, and limit fills never see spread or slippage.
"""

# ruff: noqa: E402
from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
import json
from pathlib import Path
import sys
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

_project_root = str(Path(__file__).resolve().parent.parent.parent)
sys.path.insert(0, _project_root)
sys.path.insert(0, str(Path(_project_root) / "src"))
sys.path.insert(0, str(Path(_project_root) / "scripts"))

from krakenbot.strategies.base import SignalType, TradingSignal
from scripts.backtest import BacktestEngine, PairCosts, load_pair_costs

PRICE = Decimal("50000")
OVERRIDE = PairCosts(spread=Decimal("0.0005"), slippage=Decimal("0.0007"))


class _Spy:
    async def on_trade_filled(self, **kwargs: object) -> None:
        pass


def _engine(pair_costs=None) -> BacktestEngine:
    settings = SimpleNamespace(
        trading=SimpleNamespace(pair="BTC/USDC", default_order_amount_eur=100.0)
    )
    engine = BacktestEngine(
        settings,
        MagicMock(),
        fee_model="bybit",
        strategy_name="grok_supertrend_4h",
        candle_interval=240,
        pair_costs=pair_costs,
    )
    engine.strategy = _Spy()
    return engine


def _sell_signal(pair: str) -> TradingSignal:
    return TradingSignal(
        signal_type=SignalType.SELL,
        pair=pair,
        price=PRICE,
        confidence=0.9,
        reason="override-test",
        strategy="grok_supertrend_4h",
        timestamp=datetime(2025, 1, 1, tzinfo=UTC),
        metadata={},
    )


def _open(engine: BacktestEngine) -> None:
    engine.in_position = True
    engine.crypto_balance = Decimal("0.001")
    engine.entry_price = PRICE


class TestPairCosts:
    def test_rejects_negative(self) -> None:
        with pytest.raises(ValueError, match="negative"):
            PairCosts(spread=Decimal("-0.0001"), slippage=Decimal("0"))

    def test_load_happy(self, tmp_path: Path) -> None:
        path = tmp_path / "costs.json"
        path.write_text(
            json.dumps(
                {
                    "BTC/USDC": {"spread": "0.0002", "slippage": "0.0002"},
                    "ETH/USDC": {"spread": 0.0003, "slippage": "0.0004"},
                }
            )
        )
        costs = load_pair_costs(path)
        assert costs == {
            "BTC/USDC": PairCosts(Decimal("0.0002"), Decimal("0.0002")),
            "ETH/USDC": PairCosts(Decimal("0.0003"), Decimal("0.0004")),
        }

    @pytest.mark.parametrize(
        ("content", "message"),
        [
            ('{"BTCUSDC": {"spread": "0.0002", "slippage": "0.0002"}}', "BTCUSDC"),
            ('{"BTC/USDC": {"spread": "0.0002"}}', "slippage"),
            ('{"BTC/USDC": {"spread": "0.0002", "slippage": "0.0002", "fee": "1"}}', "fee"),
            ('[{"BTC/USDC": {}}]', "object"),
            ('{"BTC/USDC": "0.0002"}', "object"),
        ],
    )
    def test_load_rejects_malformed(self, tmp_path: Path, content: str, message: str) -> None:
        path = tmp_path / "costs.json"
        path.write_text(content)
        with pytest.raises(ValueError, match=message):
            load_pair_costs(path)


class TestEngineOverrides:
    def test_default_returns_the_model_objects(self) -> None:
        engine = _engine()
        spread, slippage = engine._costs_for_pair("BTC/USDC")
        assert spread is engine.fees.spread
        assert slippage is engine.fees.slippage
        assert _engine({})._costs_for_pair("BTC/USDC") == (spread, slippage)

    def test_override_applies_only_to_its_pair(self) -> None:
        engine = _engine({"ETH/USDC": OVERRIDE})
        assert engine._costs_for_pair("ETH/USDC") == (OVERRIDE.spread, OVERRIDE.slippage)
        assert engine._costs_for_pair("BTC/USDC") == (engine.fees.spread, engine.fees.slippage)

    @pytest.mark.asyncio
    async def test_market_fill_uses_the_override(self) -> None:
        engine = _engine({"BTC/USDC": OVERRIDE})
        _open(engine)
        await engine.execute_signal(_sell_signal("BTC/USDC"), PRICE, is_limit_fill=False)
        trade = engine.metrics.trades[-1]
        assert trade.price == PRICE * (Decimal("1") - OVERRIDE.spread - OVERRIDE.slippage)
        assert (trade.spread_pct, trade.slippage_pct) == (OVERRIDE.spread, OVERRIDE.slippage)
        assert trade.fee_rate == engine.fees.taker

    @pytest.mark.asyncio
    async def test_no_override_paths_are_identical(self) -> None:
        trades = []
        for pair_costs in (None, {}, {"ETH/USDC": OVERRIDE}):
            engine = _engine(pair_costs)
            _open(engine)
            await engine.execute_signal(_sell_signal("BTC/USDC"), PRICE, is_limit_fill=False)
            trades.append(engine.metrics.trades[-1])
        assert trades[0] == trades[1] == trades[2]
        assert trades[0].spread_pct == engine.fees.spread

    @pytest.mark.asyncio
    async def test_limit_fill_ignores_overrides(self) -> None:
        engine = _engine({"BTC/USDC": OVERRIDE})
        _open(engine)
        await engine.execute_signal(_sell_signal("BTC/USDC"), PRICE, is_limit_fill=True)
        trade = engine.metrics.trades[-1]
        assert trade.price == PRICE
        assert trade.spread_pct == trade.slippage_pct == Decimal("0")
