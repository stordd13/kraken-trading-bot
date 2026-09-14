"""Maker / taker classification per fill site of GridBacktester (B4.2 + B4.3, no DB).

Grid fills are resting limit orders touched by the candle (maker); the only taker site is the
end-of-run liquidation of the terminal inventory in ``_force_close_open_positions`` — since
B4.3 a MARKET sell at ``last_close × (1 − spread − slippage)`` billed taker, settled in the
balances and tagged ``forced_liquidation``, reachable on the grok path (``run()`` records the
last tradeable close on both replay paths — end-to-end coverage lives in
``test_grid_terminal_liquidation.py``).
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

from krakenbot.models.base import TradeSide
from krakenbot.models.market_data import OHLCData
from scripts.backtest import GridBacktester

MAKER, TAKER = Decimal("0.0010"), Decimal("0.0025")  # bybit
SPREAD, SLIPPAGE = Decimal("0.0002"), Decimal("0.0002")  # bybit market costs


def _grid_settings() -> SimpleNamespace:
    return SimpleNamespace(
        multi_strategy=SimpleNamespace(
            enabled=True,
            strategies=[
                SimpleNamespace(
                    name="multi_strategy_router",
                    bot_id="multi_router",
                    params={
                        "strategies": {
                            "grok_grid_atr_adaptive_v4": {
                                "bot_id": "grid_atr_v4",
                                "params": {
                                    "grid_levels": 12,
                                    "min_spacing_pct": 0.015,
                                    "atr_period": 14,
                                    "atr_multiplier": 4.0,
                                    "recalc_hours": 6,
                                    "order_size_usdc": 25,
                                    "max_allocation_pct": 20.0,
                                    "bias_1d": 0.2,
                                    "pause_1w_strong_bear": True,
                                },
                            }
                        }
                    },
                )
            ],
        ),
        trading=SimpleNamespace(pair="BTC/USDC", default_order_amount_eur=50),
    )


def _candle(price: str, timestamp: datetime | None = None) -> OHLCData:
    value = Decimal(price)
    return OHLCData(
        timestamp=timestamp or datetime(2025, 3, 1, tzinfo=UTC),
        pair="BTC/USDC",
        interval=240,
        exchange="binance",
        open=value,
        high=value,
        low=value,
        close=value,
        volume=Decimal("1"),
        vwap=value,
        trades_count=1,
    )


def _engine() -> GridBacktester:
    return GridBacktester(
        _grid_settings(),
        MagicMock(),
        fee_model="bybit",
        strategy_name="grok_grid_atr_adaptive_v4",
        candle_interval=240,
    )


@pytest.mark.asyncio
async def test_grok_grid_buy_and_sell_fills_bill_maker() -> None:
    engine = _engine()
    strategy, _analyzer = await engine._create_grok_grid_strategy()
    strategy._grid_spacing = Decimal("0.02")
    strategy._current_timestamp = datetime(2025, 3, 1, tzinfo=UTC)
    level = SimpleNamespace(
        price=Decimal("95000.0"), side="buy", status="pending", amount_usdc=Decimal("25")
    )
    strategy._grid_levels["buy_95000.0"] = level
    await engine._process_grok_grid_buy_fill(
        strategy,
        {
            "order_id": "buy_95000.0",
            "side": "buy",
            "price": Decimal("95000.0"),
            "amount_usdc": Decimal("25"),
            "level": level,
        },
        _candle("95000.0"),
    )
    buy = engine.metrics.trades[-1]
    assert buy.side == TradeSide.BUY
    assert buy.fee == Decimal("25") * MAKER
    assert buy.liquidity == "maker"
    assert buy.fee_rate == MAKER
    assert buy.fee_base_usdc == Decimal("25")
    assert buy.reference_price == Decimal("95000.0")
    assert buy.spread_pct == buy.slippage_pct == Decimal("0")

    position = strategy.open_positions[0]
    await engine._process_grok_grid_sell_fill(
        strategy,
        {
            "order_id": f"sell_pos_{position.position_id}",
            "side": "sell",
            "price": position.sell_level,
            "amount_btc": position.amount_btc,
            "position_id": position.position_id,
        },
        _candle(str(position.sell_level), datetime(2025, 3, 1, 4, tzinfo=UTC)),
    )
    sell = engine.metrics.trades[-1]
    gross = position.amount_btc * position.sell_level
    assert sell.side == TradeSide.SELL
    assert sell.fee == gross * MAKER
    assert sell.liquidity == "maker"
    assert sell.fee_base_usdc == gross
    assert engine.total_fees == buy.fee + sell.fee


def test_force_close_legacy_orders_bills_taker_with_market_costs() -> None:
    engine = _engine()
    now = datetime(2025, 3, 15, tzinfo=UTC)
    engine._last_close = Decimal("90000")
    engine._last_timestamp = now
    engine.metrics.end_time = now
    engine.btc_held = Decimal("0.01")
    engine.active_sell_orders = [
        {
            "price": Decimal("105000"),
            "amount_btc": Decimal("0.01"),
            "entry_price": Decimal("100000"),
        }
    ]
    engine.equity_curve = [(now, engine.usdc_balance + Decimal("0.01") * Decimal("90000"))]

    engine._calculate_final_metrics()

    trade = engine.metrics.trades[-1]
    price = Decimal("90000") * (Decimal("1") - SPREAD - SLIPPAGE)  # 89964
    gross = Decimal("0.01") * price
    assert trade.price == price == Decimal("89964")
    assert trade.reference_price == Decimal("90000")
    assert trade.spread_pct == SPREAD
    assert trade.slippage_pct == SLIPPAGE
    assert trade.fee == gross * TAKER == Decimal("2.2491")
    assert trade.liquidity == "taker"
    assert trade.fee_rate == TAKER
    assert trade.fee_base_usdc == gross
    assert trade.forced_liquidation is True
    assert trade.pnl == gross - trade.fee - Decimal("0.01") * Decimal("100000")
    assert trade.pnl == Decimal("-102.6091")
    assert engine.metrics.total_fees == trade.fee
    # Balances settled and the liquidation is the last equity point.
    assert engine.btc_held == Decimal("0")
    assert engine.usdc_balance == Decimal("1000") + gross - trade.fee
    assert engine.active_sell_orders == []
    assert len(engine.equity_curve) == 2
    assert engine.equity_curve[-1] == (now, engine.usdc_balance)
    assert engine.metrics.ending_balance == engine.usdc_balance
    assert engine.metrics.total_trades == engine.liquidated_positions == 1
    assert engine.pairs_completed == 0


def test_force_close_grok_positions_bills_taker_with_market_costs() -> None:
    """Grok branch: the inner strategy's open positions are liquidated at market (B4.3)."""
    engine = _engine()
    now = datetime(2025, 3, 15, tzinfo=UTC)
    engine._last_close = Decimal("90000")
    engine._last_timestamp = now
    engine.metrics.end_time = now
    engine.btc_held = Decimal("0.02")
    engine._strategy_obj = SimpleNamespace(
        open_positions=[SimpleNamespace(amount_btc=Decimal("0.02"), entry_price=Decimal("95000"))]
    )
    engine.equity_curve = [(now, engine.usdc_balance + Decimal("0.02") * Decimal("90000"))]

    engine._calculate_final_metrics()

    trade = engine.metrics.trades[-1]
    gross = Decimal("0.02") * Decimal("89964")
    assert trade.price == Decimal("89964")
    assert trade.fee == gross * TAKER == Decimal("4.4982")
    assert trade.liquidity == "taker"
    assert trade.forced_liquidation is True
    assert engine.metrics.losing_trades == 1
    assert engine.metrics.unrealized_pnl == gross - trade.fee - Decimal("0.02") * Decimal("95000")
    assert engine.metrics.unrealized_pnl == Decimal("-105.2182")
    assert engine.btc_held == Decimal("0")
    assert engine.inventory_divergence_btc == Decimal("0")
    assert engine.liquidation_dust_btc == Decimal("0")
    assert engine.metrics.ending_balance == engine.usdc_balance == engine.equity_curve[-1][1]


def test_force_close_is_a_noop_without_last_close() -> None:
    """Unit-level guard: without run(), _last_close stays None and nothing is booked.

    (run() always records the last tradeable close since B4.3 — see
    test_grid_terminal_liquidation.py for the end-to-end path.)
    """
    engine = _engine()
    engine.metrics.end_time = datetime(2025, 3, 15, tzinfo=UTC)
    engine._strategy_obj = SimpleNamespace(
        open_positions=[SimpleNamespace(amount_btc=Decimal("0.02"), entry_price=Decimal("95000"))]
    )
    engine.equity_curve = [(engine.metrics.end_time, Decimal("900"))]

    engine._calculate_final_metrics()

    assert engine.metrics.trades == []
    assert engine.metrics.unrealized_pnl == Decimal("0")
    assert engine.metrics.total_fees == Decimal("0")
