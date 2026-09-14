"""Maker / taker classification per fill site of the signal engine (B4.2, no DB).

Limit fills (resting order touched by the candle) pay the maker rate with no spread or
slippage; market fills pay the taker rate and move the execution price by spread + slippage.
Every BacktestTrade records the audit fields used by scripts/audit/b4_2_reference_capture.py.
"""

# ruff: noqa: E402
from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
import sys
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

_project_root = str(Path(__file__).resolve().parent.parent.parent)
sys.path.insert(0, _project_root)
sys.path.insert(0, str(Path(_project_root) / "src"))
sys.path.insert(0, str(Path(_project_root) / "scripts"))

from krakenbot.config.settings import FEE_MODEL_NAMES, ExchangeFees
from krakenbot.models.base import TradeSide
from krakenbot.strategies.base import SignalType, TradingSignal
from scripts.backtest import BacktestEngine

PRICE = Decimal("50000")
ORDER = Decimal("50")


class _Spy:
    """Strategy stub with on_trade_filled (grok_supertrend_4h routes through it)."""

    def __init__(self) -> None:
        self.fills: list[dict[str, object]] = []

    async def on_trade_filled(self, **kwargs: object) -> None:
        self.fills.append(kwargs)


def _engine(fee_model: str, **kwargs: object) -> BacktestEngine:
    settings = SimpleNamespace(
        trading=SimpleNamespace(pair="BTC/USDC", default_order_amount_eur=100.0)
    )
    engine = BacktestEngine(
        settings,
        MagicMock(),
        fee_model=fee_model,
        strategy_name="grok_supertrend_4h",
        candle_interval=240,
        **kwargs,
    )
    engine.strategy = _Spy()
    return engine


def _signal(signal_type: SignalType, pair: str = "BTC/USDC") -> TradingSignal:
    return TradingSignal(
        signal_type=signal_type,
        pair=pair,
        price=PRICE,
        confidence=0.9,
        reason="fee-site-test",
        strategy="grok_supertrend_4h",
        timestamp=datetime(2025, 1, 1, tzinfo=UTC),
        metadata={"order_size_usdc": float(ORDER)},
    )


def _open_position(engine: BacktestEngine, crypto: Decimal = Decimal("0.001")) -> None:
    engine.in_position = True
    engine.crypto_balance = crypto
    engine.entry_price = PRICE


@pytest.mark.asyncio
@pytest.mark.parametrize("model", FEE_MODEL_NAMES)
async def test_limit_buy_bills_maker_without_costs(model: str) -> None:
    engine = _engine(model)
    fees = ExchangeFees.from_name(model)
    await engine.execute_signal(_signal(SignalType.BUY), PRICE, is_limit_fill=True)
    trade = engine.metrics.trades[-1]
    assert trade.side == TradeSide.BUY
    assert trade.price == PRICE
    assert trade.fee == ORDER * fees.maker
    assert trade.liquidity == "maker"
    assert trade.fee_rate == fees.maker
    assert trade.fee_base_usdc == ORDER
    assert trade.reference_price == PRICE
    assert trade.spread_pct == Decimal("0")
    assert trade.slippage_pct == Decimal("0")


@pytest.mark.asyncio
@pytest.mark.parametrize("model", FEE_MODEL_NAMES)
async def test_market_buy_bills_taker_plus_costs(model: str) -> None:
    engine = _engine(model)
    fees = ExchangeFees.from_name(model)
    await engine.execute_signal(_signal(SignalType.BUY), PRICE, is_limit_fill=False)
    trade = engine.metrics.trades[-1]
    assert trade.price == PRICE * (Decimal("1") + fees.spread + fees.slippage)
    assert trade.fee == ORDER * fees.taker
    assert trade.liquidity == "taker"
    assert trade.fee_rate == fees.taker
    assert trade.fee_base_usdc == ORDER
    assert trade.reference_price == PRICE
    assert (trade.spread_pct, trade.slippage_pct) == (fees.spread, fees.slippage)


@pytest.mark.asyncio
@pytest.mark.parametrize("model", FEE_MODEL_NAMES)
async def test_market_sell_bills_taker_on_proceeds(model: str) -> None:
    engine = _engine(model)
    fees = ExchangeFees.from_name(model)
    _open_position(engine)
    await engine.execute_signal(_signal(SignalType.SELL), PRICE, is_limit_fill=False)
    trade = engine.metrics.trades[-1]
    execution = PRICE * (Decimal("1") - fees.spread - fees.slippage)
    proceeds = Decimal("0.001") * execution
    assert trade.side == TradeSide.SELL
    assert trade.price == execution
    assert trade.fee == proceeds * fees.taker
    assert trade.amount_usdc == proceeds - trade.fee
    assert trade.liquidity == "taker"
    assert trade.fee_rate == fees.taker
    assert trade.fee_base_usdc == proceeds
    assert trade.reference_price == PRICE


@pytest.mark.asyncio
async def test_limit_sell_bills_maker_without_costs() -> None:
    engine = _engine("bybit")
    _open_position(engine)
    await engine.execute_signal(_signal(SignalType.SELL), PRICE, is_limit_fill=True)
    trade = engine.metrics.trades[-1]
    proceeds = Decimal("0.001") * PRICE
    assert trade.price == PRICE
    assert trade.fee == proceeds * Decimal("0.0010")
    assert trade.liquidity == "maker"
    assert trade.spread_pct == trade.slippage_pct == Decimal("0")


@pytest.mark.asyncio
async def test_bybit_exact_rates_end_to_end() -> None:
    """Brief §7.2: entries 0.10 %, market exits 0.25 % + 0.02 % spread + 0.02 % slippage."""
    engine = _engine("bybit")
    await engine.execute_signal(_signal(SignalType.BUY), PRICE, is_limit_fill=True)
    await engine.execute_signal(_signal(SignalType.SELL), PRICE, is_limit_fill=False)
    entry, exit_ = engine.metrics.trades
    assert entry.fee_rate == Decimal("0.0010")
    assert exit_.fee_rate == Decimal("0.0025")
    assert exit_.price == PRICE * Decimal("0.9996")
    assert engine.metrics.total_fees == entry.fee + exit_.fee
