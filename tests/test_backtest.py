"""Tests for backtesting framework."""

import sys
from pathlib import Path

# Add scripts directory to path
scripts_dir = Path(__file__).parent.parent / "scripts"
sys.path.insert(0, str(scripts_dir))

import pytest
from datetime import datetime, timedelta, UTC
from decimal import Decimal

from krakenbot.models.market_data import OHLCData
from krakenbot.config.settings import get_settings
from krakenbot.core.database import DatabaseManager
from backtest import BacktestEngine, BacktestMetrics, BacktestTrade


@pytest.mark.asyncio
async def test_backtest_metrics_calculation():
    """Test calculation of backtest metrics."""
    metrics = BacktestMetrics(starting_balance=Decimal("1000"))

    # Simulate some trades
    metrics.trades = [
        BacktestTrade(
            timestamp=datetime.now(UTC),
            side="buy",
            price=Decimal("90000"),
            amount_usdc=Decimal("100"),
            amount_crypto=Decimal("0.001"),
            fee=Decimal("0.4"),
        ),
        BacktestTrade(
            timestamp=datetime.now(UTC),
            side="sell",
            price=Decimal("91000"),
            amount_usdc=Decimal("101"),
            amount_crypto=Decimal("0.001"),
            fee=Decimal("0.4"),
            pnl=Decimal("0.6"),  # Small profit
        ),
        BacktestTrade(
            timestamp=datetime.now(UTC),
            side="buy",
            price=Decimal("91000"),
            amount_usdc=Decimal("100"),
            amount_crypto=Decimal("0.0011"),
            fee=Decimal("0.4"),
        ),
        BacktestTrade(
            timestamp=datetime.now(UTC),
            side="sell",
            price=Decimal("90000"),
            amount_usdc=Decimal("99"),
            amount_crypto=Decimal("0.0011"),
            fee=Decimal("0.4"),
            pnl=Decimal("-1.4"),  # Small loss
        ),
    ]

    metrics.total_pnl = Decimal("0.6") + Decimal("-1.4")
    metrics.total_fees = Decimal("1.6")
    metrics.winning_trades = 1
    metrics.losing_trades = 1
    metrics.total_trades = 2

    # Calculate metrics
    engine = BacktestEngine(None, None)  # type: ignore
    engine.metrics = metrics
    engine.calculate_final_metrics()

    assert engine.metrics.total_trades == 2
    assert engine.metrics.winning_trades == 1
    assert engine.metrics.losing_trades == 1
    assert engine.metrics.win_rate == 0.5
    # Net P&L = total_pnl - total_fees = -0.8 - 1.6 = -2.4
    assert engine.metrics.net_pnl == Decimal("-2.4")


def test_backtest_trade_creation():
    """Test creating BacktestTrade instances."""
    trade = BacktestTrade(
        timestamp=datetime.now(UTC),
        side="buy",
        price=Decimal("90000"),
        amount_usdc=Decimal("100"),
        amount_crypto=Decimal("0.001111"),
        fee=Decimal("0.4"),
    )

    assert trade.side == "buy"
    assert trade.price == Decimal("90000")
    assert trade.pnl is None  # No P&L for buy trades


def test_backtest_metrics_initialization():
    """Test BacktestMetrics initializes with defaults."""
    metrics = BacktestMetrics()

    assert metrics.total_trades == 0
    assert metrics.winning_trades == 0
    assert metrics.losing_trades == 0
    assert metrics.total_pnl == Decimal("0")
    assert metrics.win_rate == 0.0
    assert metrics.starting_balance == Decimal("1000")
    assert len(metrics.trades) == 0
