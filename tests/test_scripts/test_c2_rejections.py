"""C2 (R3) — rejections are visible: one count per (distinct order, cause), events apart.

Covers the ledger itself, the brief's exact DCA case (``bull_reduction`` 0.3 × 15 = 4.50 USDC
under the 5 USDC floor, counted once per weekly order), the grid level retested on several
candles (one distinct order, N events), a level re-created at the same price (a new order),
the five minimal causes present on both engines, and the ``rejections`` block in the dumps.
"""

# ruff: noqa: E402
from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
import json
from pathlib import Path
import sys
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

_project_root = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_project_root))
sys.path.insert(0, str(_project_root / "scripts"))
sys.path.insert(0, str(_project_root / "src"))

from krakenbot.core.event_bus import EventBus
from krakenbot.models.base import SignalType
from krakenbot.strategies.base import TradingSignal
from krakenbot.strategies.grok_adaptive_dca_weekly import GrokAdaptiveDCAWeekly
from krakenbot.strategies.grok_grid_atr_adaptive_v4 import GridATRLevel
from scripts.backtest import BacktestEngine, RejectionLedger, dump_trades_json
from test_scripts.test_grid_terminal_liquidation import _candle, _engine, _flat, _run

PAIR = "BTC/USDC"
MONDAY = datetime(2022, 1, 3, tzinfo=UTC)  # end-stamped daily candle of Sunday 2022-01-02


# ---------------------------------------------------------------------------
# The ledger
# ---------------------------------------------------------------------------


def test_ledger_counts_once_per_order_and_cause_events_apart() -> None:
    ledger = RejectionLedger()
    assert ledger.note("buy#1", "insufficient_cash") is True
    assert ledger.note("buy#1", "insufficient_cash") is False
    assert ledger.note("buy#1", "insufficient_cash") is False
    assert ledger.by_cause["insufficient_cash"] == 1
    assert ledger.events["insufficient_cash"] == 3
    ledger.prune(["buy#2"])  # buy#1 left the pending set: a re-created buy#1 counts anew
    assert ledger.note("buy#1", "insufficient_cash") is True
    assert ledger.by_cause["insufficient_cash"] == 2 and ledger.events["insufficient_cash"] == 4
    ledger.add_counts({"unmatched_sell_fills": 2, "ambiguous_sell_fill": 1})
    summary = ledger.summary()
    assert summary["unit"] == "(order, cause)"
    assert set(RejectionLedger.MINIMAL_CAUSES) <= set(summary["by_cause"])
    assert summary["by_cause"]["below_min_order"] == 0
    assert summary["by_cause"]["unmatched_sell_fills"] == 2
    assert summary["by_cause"]["ambiguous_sell_fill"] == 1


# ---------------------------------------------------------------------------
# Signal engine: the DCA bull_reduction case, cash clamp, silent no-ops
# ---------------------------------------------------------------------------


class _Analyzer:
    """Analyzer stub: regime 1w forced to strong_bull, no RSI / EMA200 (base amount only)."""

    def get_rsi(self, period, tf):  # noqa: ANN001, ANN201
        return None

    def get_ema(self, period, tf):  # noqa: ANN001, ANN201
        return None

    def get_regime(self, tf):  # noqa: ANN001, ANN201
        return "strong_bull" if tf == "1w" else "bull"


def _dca_engine(min_order_usdc: float, bull_reduction: float) -> BacktestEngine:
    settings = SimpleNamespace(
        multi_strategy=SimpleNamespace(enabled=False, strategies=[]),
        trading=SimpleNamespace(pair=PAIR, default_order_amount_eur=50),
    )
    engine = BacktestEngine(
        settings,
        MagicMock(),
        fee_model="bybit",
        strategy_name="grok_adaptive_dca_weekly",
        candle_interval=5,
        min_order_usdc=min_order_usdc,
    )
    strategy = GrokAdaptiveDCAWeekly(
        settings=settings,
        event_bus=EventBus(),
        db_manager=MagicMock(),
        bot_id="dca_btc",
        strategy_params={"pair": PAIR, "bull_reduction": bull_reduction},
        analyzer=_Analyzer(),
    )
    strategy._skip_db_sync = True
    strategy._running = True
    engine.strategy = strategy
    return engine


async def _weekly_signal(engine: BacktestEngine, when: datetime) -> TradingSignal:
    strategy = engine.strategy
    strategy._is_daily = True
    strategy._current_price = Decimal("46000")
    strategy._current_timestamp = when
    signal = await strategy.generate_signal()
    assert signal is not None and signal.signal_type == SignalType.BUY
    return signal


@pytest.mark.asyncio
async def test_dca_bull_reduction_under_the_floor_is_counted_once_per_weekly_order() -> None:
    """The exact B4 case: bull_reduction 0.3 × 15 USDC = 4.50 < 5 USDC (min order)."""
    engine = _dca_engine(min_order_usdc=5.0, bull_reduction=0.3)
    signal = await _weekly_signal(engine, MONDAY)
    assert signal.metadata["order_size_usdc"] == 4.5
    assert signal.metadata["multiplier_label"] == "bull_reduce"

    # the same order retested (a resting limit checked again) counts once, events twice
    await engine.execute_signal(signal, Decimal("46000"), is_limit_fill=True, order_id="sig#1")
    await engine.execute_signal(signal, Decimal("46000"), is_limit_fill=True, order_id="sig#1")
    assert engine.metrics.trades == []
    assert engine.usdc_balance == Decimal("1000")
    assert engine.rejections.by_cause["below_min_order"] == 1
    assert engine.rejections.events["below_min_order"] == 2

    # next week's signal is a distinct order
    next_signal = await _weekly_signal(engine, MONDAY + timedelta(days=7))
    await engine.execute_signal(next_signal, Decimal("46000"), is_limit_fill=True, order_id="sig#2")
    assert engine.rejections.by_cause["below_min_order"] == 2

    # with the class default (0.5): 7.5 USDC >= 5, the buy executes
    engine_ok = _dca_engine(min_order_usdc=5.0, bull_reduction=0.5)
    ok = await _weekly_signal(engine_ok, MONDAY)
    await engine_ok.execute_signal(ok, Decimal("46000"), is_limit_fill=True, order_id="sig#1")
    assert len(engine_ok.metrics.trades) == 1
    assert engine_ok.rejections.by_cause["below_min_order"] == 0
    assert engine_ok.dca_counters["buys_executed"] == 1


@pytest.mark.asyncio
async def test_signal_engine_cash_clamp_under_the_floor_is_insufficient_cash() -> None:
    engine = _dca_engine(min_order_usdc=5.0, bull_reduction=1.0)
    engine.usdc_balance = Decimal("3")  # 15 requested, clamped to 3 < 5
    signal = await _weekly_signal(engine, MONDAY)
    await engine.execute_signal(signal, Decimal("46000"), is_limit_fill=True, order_id="sig#1")
    assert engine.rejections.by_cause["insufficient_cash"] == 1
    assert engine.rejections.by_cause["below_min_order"] == 0


@pytest.mark.asyncio
async def test_signal_engine_silent_no_ops_are_now_counted() -> None:
    engine = _dca_engine(min_order_usdc=1.0, bull_reduction=1.0)
    engine.strategy_name = "grok_supertrend_4h"  # single-position semantics
    sell = TradingSignal(
        signal_type=SignalType.SELL,
        pair=PAIR,
        price=Decimal("46000"),
        confidence=0.9,
        reason="x",
        strategy="grok_supertrend_4h",
        timestamp=MONDAY,
        metadata={"order_type": "market"},
    )
    await engine.execute_signal(sell, Decimal("46000"), is_limit_fill=False, order_id="sig#1")
    assert engine.rejections.by_cause["sell_without_position"] == 1
    buy = TradingSignal(
        signal_type=SignalType.BUY,
        pair=PAIR,
        price=Decimal("46000"),
        confidence=0.9,
        reason="x",
        strategy="grok_supertrend_4h",
        timestamp=MONDAY,
        metadata={"order_type": "limit", "order_size_usdc": 50},
    )
    await engine.execute_signal(buy, Decimal("46000"), is_limit_fill=True, order_id="sig#2")
    await engine.execute_signal(buy, Decimal("46000"), is_limit_fill=True, order_id="sig#3")
    assert engine.in_position and len(engine.metrics.trades) == 1
    assert engine.rejections.by_cause["buy_while_in_position"] == 1


# ---------------------------------------------------------------------------
# Grid engine: one order retested on N candles, re-created level = new order
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_grid_buy_level_without_cash_is_one_order_over_ten_candles() -> None:
    # the seeded level (100000, 25 USDC) is touched on every candle; capital 10 < 25
    engine = await _run(
        _engine("bybit", starting_capital=10.0), [_flat(i, "99000") for i in range(10)]
    )
    rejections = engine.rejections_summary()
    assert rejections["by_cause"]["insufficient_cash"] == 1
    assert rejections["events"]["insufficient_cash"] == 10
    assert engine.metrics.trades == []


def test_grid_level_recreated_at_the_same_price_is_a_new_order() -> None:
    engine = _engine("bybit")
    level = GridATRLevel(
        price=Decimal("100000"), side="buy", status="pending", amount_usdc=Decimal("25")
    )
    twin = GridATRLevel(
        price=Decimal("100000"), side="buy", status="pending", amount_usdc=Decimal("25")
    )
    first = engine._order_id_for_level(level)
    assert engine._order_id_for_level(level) == first
    assert engine._order_id_for_level(twin) != first


@pytest.mark.asyncio
async def test_minimal_causes_present_and_rejections_block_in_the_dumps(tmp_path: Path) -> None:
    grid = await _run(
        _engine("bybit"),
        [_candle(0, "100500", "100500", "99500", "100000")]
        + [_flat(i, "90000") for i in range(1, 10)],
    )
    signal = _dca_engine(min_order_usdc=5.0, bull_reduction=0.5)
    for engine in (grid, signal):
        block = engine.rejections_summary()
        assert set(RejectionLedger.MINIMAL_CAUSES) <= set(block["by_cause"])
        assert block["unit"] == "(order, cause)"
    signal.calculate_final_metrics()
    for name, engine in (("grid", grid), ("signal", signal)):
        out = tmp_path / f"{name}.json"
        dump_trades_json(
            engine,
            out,
            pair=PAIR,
            start=MONDAY,
            end=MONDAY + timedelta(days=1),
            exchange="binance",
            interval=5,
            capital=1000.0,
        )
        payload = json.loads(out.read_text())
        assert payload["rejections"]["unit"] == "(order, cause)"
        assert "warmup" in payload
    assert "dca_counters" in json.loads((tmp_path / "signal.json").read_text())
    assert "dca_counters" not in json.loads((tmp_path / "grid.json").read_text())
