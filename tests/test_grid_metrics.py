"""Tests for GridBacktester._calculate_final_metrics (P6.5 bug 4 regression)."""

# ruff: noqa: E402

from pathlib import Path
import sys
from types import SimpleNamespace
from unittest.mock import MagicMock

scripts_dir = Path(__file__).parent.parent / "scripts"
sys.path.insert(0, str(scripts_dir))

from datetime import UTC, datetime, timedelta
from decimal import Decimal

from backtest import BacktestTrade, GridBacktester, TradeSide

from krakenbot.backtest_metrics import profit_factor_from_sums


def _build_grid_settings() -> SimpleNamespace:
    """Minimal settings object for GridBacktester instantiation."""
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
                                    "order_size_usdc": 25,
                                    "max_allocation_pct": 20.0,
                                },
                            }
                        }
                    },
                ),
            ],
        ),
        trading=SimpleNamespace(pair="BTC/USDC", default_order_amount_eur=50),
    )


def _new_backtester(fee_model: str = "kraken") -> GridBacktester:
    return GridBacktester(
        _build_grid_settings(),
        MagicMock(),
        fee_model=fee_model,
        strategy_name="grok_grid_atr_adaptive_v4",
        candle_interval=240,
    )


def test_profit_factor_all_winners_is_none_disambiguated_by_the_sums() -> None:
    """Only winning trades (C1): profit_factor is None (no losses), never 0 — the exported sums
    say "infinite" (gains > 0, losses == 0) and the display shows ∞."""
    engine = _new_backtester()
    now = datetime.now(UTC)
    engine.metrics.trades = [
        BacktestTrade(
            timestamp=now,
            side=TradeSide.SELL,
            price=Decimal("100"),
            amount_usdc=Decimal("100"),
            amount_crypto=Decimal("1"),
            fee=Decimal("0"),
            pnl=Decimal("10"),
        ),
        BacktestTrade(
            timestamp=now,
            side=TradeSide.SELL,
            price=Decimal("100"),
            amount_usdc=Decimal("100"),
            amount_crypto=Decimal("1"),
            fee=Decimal("0"),
            pnl=Decimal("20"),
        ),
    ]
    engine.pairs_completed = 2
    engine.metrics.winning_trades = 2
    engine.metrics.losing_trades = 0
    engine._calculate_final_metrics()
    assert engine.metrics.profit_factor is None
    assert engine.metrics.gross_profit_net == Decimal("30")
    assert engine.metrics.gross_loss_net == Decimal("0")
    assert profit_factor_from_sums(
        engine.metrics.gross_profit_net, engine.metrics.gross_loss_net
    ) == float("inf")
    assert engine.metrics.profit_factor_display() == "∞"
    assert engine.metrics.pf_excluded_trades == 0


def test_profit_factor_no_trades_is_undefined() -> None:
    """With no trades, profit_factor is None (0/0), shown as n/a — never a fake 0 (C1)."""
    engine = _new_backtester()
    engine._calculate_final_metrics()
    assert engine.metrics.profit_factor is None
    assert (engine.metrics.gross_profit_net, engine.metrics.gross_loss_net) == (0, 0)
    assert engine.metrics.profit_factor_display() == "n/a"
    assert engine.metrics.sharpe_ratio is None and engine.metrics.sortino_ratio is None


def test_profit_factor_normal_mix() -> None:
    """Standard case: 2 wins ($10+$20), 1 loss ($5) → profit_factor = 6.0 (fixture legs carry
    no buy_fee_alloc: taken at fee 0, a path the engines never produce)."""
    engine = _new_backtester()
    now = datetime.now(UTC)
    engine.metrics.trades = [
        BacktestTrade(
            timestamp=now,
            side=TradeSide.SELL,
            price=Decimal("100"),
            amount_usdc=Decimal("100"),
            amount_crypto=Decimal("1"),
            fee=Decimal("0"),
            pnl=Decimal("10"),
        ),
        BacktestTrade(
            timestamp=now,
            side=TradeSide.SELL,
            price=Decimal("100"),
            amount_usdc=Decimal("100"),
            amount_crypto=Decimal("1"),
            fee=Decimal("0"),
            pnl=Decimal("20"),
        ),
        BacktestTrade(
            timestamp=now,
            side=TradeSide.SELL,
            price=Decimal("100"),
            amount_usdc=Decimal("100"),
            amount_crypto=Decimal("1"),
            fee=Decimal("0"),
            pnl=Decimal("-5"),
        ),
    ]
    engine.pairs_completed = 3
    engine.metrics.winning_trades = 2
    engine.metrics.losing_trades = 1
    engine._calculate_final_metrics()
    assert engine.metrics.profit_factor == 6.0


def test_grid_force_close_adds_losing_trades_at_unfavorable_price() -> None:
    """Open sell orders at end of backtest get force-closed as losing virtual trades
    when current price is below their entry price.
    """
    engine = _new_backtester()
    now = datetime.now(UTC)
    engine._last_close = Decimal("90000")
    engine._last_timestamp = now
    engine.metrics.end_time = now
    engine.metrics.starting_balance = Decimal("1000")
    # One open sell order whose entry was way above current price → unrealized loss
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

    assert engine.metrics.losing_trades >= 1
    assert engine.metrics.unrealized_pnl < 0
    # win_rate < 1.0 because we just recorded a forced loss
    assert engine.metrics.win_rate < 1.0
    # active_sell_orders cleared after force-close, inventory settled into cash (B4.3)
    assert engine.active_sell_orders == []
    assert engine.btc_held == Decimal("0")
    assert engine.metrics.ending_balance == engine.equity_curve[-1][1] == engine.usdc_balance


def test_grid_avg_holding_time_calculated() -> None:
    """Average holding time should be computed from matched buy→sell trade timestamps."""
    engine = _new_backtester()
    buy_ts = datetime(2026, 1, 1, 0, 0, tzinfo=UTC)
    sell_ts = buy_ts + timedelta(minutes=60)
    engine.metrics.trades = [
        BacktestTrade(
            timestamp=buy_ts,
            side=TradeSide.BUY,
            price=Decimal("100"),
            amount_usdc=Decimal("100"),
            amount_crypto=Decimal("1"),
            fee=Decimal("0"),
        ),
        BacktestTrade(
            timestamp=sell_ts,
            side=TradeSide.SELL,
            price=Decimal("105"),
            amount_usdc=Decimal("105"),
            amount_crypto=Decimal("1"),
            fee=Decimal("0"),
            pnl=Decimal("5"),
        ),
    ]
    engine.pairs_completed = 1
    engine.metrics.winning_trades = 1
    engine._calculate_final_metrics()
    assert engine.metrics.average_holding_time_minutes == 60.0


def test_force_close_without_open_positions_is_noop() -> None:
    """Force-close must handle the normal case (no open positions) gracefully."""
    engine = _new_backtester()
    engine._last_close = Decimal("100000")
    engine._last_timestamp = datetime.now(UTC)
    engine.active_sell_orders = []
    engine._calculate_final_metrics()
    # No trades added; unrealized_pnl stays at default 0
    assert engine.metrics.unrealized_pnl == Decimal("0")
