"""Maker / taker classification per fill site of GridBacktester (B4.2, no DB).

Grid fills are resting limit orders touched by the candle (maker); the only taker site is the
end-of-run forced liquidation in ``_force_close_open_positions`` (mark-to-market, no spread or
slippage on the price — gate decision n1). The grok path never reaches it today because
``_last_close`` is only set on the legacy loop (annex, B4.3): the no-op is pinned here.
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


def test_force_close_legacy_orders_bills_taker_without_costs() -> None:
    engine = _engine()
    now = datetime(2025, 3, 15, tzinfo=UTC)
    engine._last_close = Decimal("90000")
    engine._last_timestamp = now
    engine.metrics.end_time = now
    engine.active_sell_orders = [
        {
            "price": Decimal("105000"),
            "amount_btc": Decimal("0.01"),
            "entry_price": Decimal("100000"),
        }
    ]
    engine.equity_curve = [(now, Decimal("900"))]

    engine._calculate_final_metrics()

    trade = engine.metrics.trades[-1]
    gross = Decimal("0.01") * Decimal("90000")
    assert trade.fee == gross * TAKER
    assert trade.liquidity == "taker"
    assert trade.fee_rate == TAKER
    assert trade.fee_base_usdc == gross
    assert trade.price == trade.reference_price == Decimal("90000")
    assert trade.spread_pct == trade.slippage_pct == Decimal("0")
    assert trade.pnl == gross - trade.fee - Decimal("0.01") * Decimal("100000")
    assert engine.metrics.total_fees == trade.fee


def test_force_close_grok_positions_bills_taker() -> None:
    """First coverage of the grok branch (:2338-2369 on dev @ 10a2df8)."""
    engine = _engine()
    now = datetime(2025, 3, 15, tzinfo=UTC)
    engine._last_close = Decimal("90000")
    engine._last_timestamp = now
    engine.metrics.end_time = now
    engine._strategy_obj = SimpleNamespace(
        open_positions=[SimpleNamespace(amount_btc=Decimal("0.02"), entry_price=Decimal("95000"))]
    )
    engine.equity_curve = [(now, Decimal("900"))]

    engine._calculate_final_metrics()

    trade = engine.metrics.trades[-1]
    gross = Decimal("0.02") * Decimal("90000")
    assert trade.fee == gross * TAKER
    assert trade.liquidity == "taker"
    assert engine.metrics.losing_trades == 1
    assert engine.metrics.unrealized_pnl == gross - trade.fee - Decimal("0.02") * Decimal("95000")


def test_force_close_is_a_noop_without_last_close() -> None:
    """Grok runs never set _last_close today (annex B4.3): nothing is booked."""
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
