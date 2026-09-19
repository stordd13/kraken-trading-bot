"""Tests for backtesting framework."""

# ruff: noqa: E402

from pathlib import Path
import sys
from types import SimpleNamespace
from unittest.mock import MagicMock

# Add scripts directory to path
scripts_dir = Path(__file__).parent.parent / "scripts"
sys.path.insert(0, str(scripts_dir))

from datetime import UTC, datetime, timedelta
from decimal import Decimal

from backtest import BacktestEngine, BacktestMetrics, BacktestTrade, GridBacktester
import pytest

from krakenbot.models.market_data import OHLCData


def _build_grid_settings() -> SimpleNamespace:
    """Build minimal settings object for grid backtest tests."""
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
                ),
                SimpleNamespace(
                    name="other_strategy",
                    bot_id="other_strategy_prod",
                    params={"order_amount_usdc": 999},
                ),
            ],
        ),
        trading=SimpleNamespace(pair="XBT/USDC", default_order_amount_eur=50),
    )


def _build_test_candle(
    *,
    timestamp: datetime | None = None,
    price: str = "95000.0",
) -> OHLCData:
    """Build a minimal OHLC candle for fill simulation tests."""
    ts = timestamp or datetime.now(UTC)
    value = Decimal(price)
    return OHLCData(
        timestamp=ts,
        pair="XBT/USDC",
        interval=240,
        exchange="kraken",
        open=value,
        high=value,
        low=value,
        close=value,
        volume=Decimal("1"),
        vwap=value,
        trades_count=1,
    )


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
    engine = BacktestEngine(None, None, fee_model="kraken")  # type: ignore
    engine.metrics = metrics
    engine.calculate_final_metrics()

    assert engine.metrics.total_trades == 2
    assert engine.metrics.winning_trades == 1
    assert engine.metrics.losing_trades == 1
    assert engine.metrics.win_rate == 0.5
    # Net P&L (B4.3) = total_pnl - buy fees = -0.8 - (0.4 + 0.4) = -1.6: each sell's pnl
    # already carries its own sell fee, so only the buy fees are subtracted once.
    assert engine.metrics.net_pnl == Decimal("-1.6")


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


@pytest.mark.asyncio
async def test_build_replay_sequence_skips_unused_1h_and_15m_for_4h_strategy():
    """Pure 4h strategies should not load lower-timeframe replay feeds."""
    engine = BacktestEngine(
        None,  # type: ignore[arg-type]
        None,  # type: ignore[arg-type]
        fee_model="kraken",
        strategy_name="grok_supertrend_4h",
        candle_interval=240,
    )
    start_time = datetime.now(UTC) - timedelta(days=30)
    end_time = datetime.now(UTC)
    loaded_intervals: list[int] = []

    async def fake_load(pair: str, interval: int, start: datetime, end: datetime):  # noqa: ARG001
        loaded_intervals.append(interval)
        return []

    engine._load_candles_for_interval = fake_load  # type: ignore[method-assign]

    sequence = await engine._build_replay_sequence("XBT/USDC", start_time, end_time, [])

    assert sequence == []
    assert 60 not in loaded_intervals
    assert 15 not in loaded_intervals
    assert 240 in loaded_intervals
    assert 1440 in loaded_intervals


def test_grid_backtester_routes_grok_grid_atr_adaptive_v4_to_grid_path():
    """The ATR adaptive grok grid should be handled by GridBacktester."""
    assert "grok_grid_atr_adaptive_v4" in GridBacktester.GRID_STRATEGIES


def test_grid_backtester_loads_inner_router_params_for_grok_grid_atr_v4():
    """Inner router params should override any unrelated top-level grid config."""
    backtester = GridBacktester(
        _build_grid_settings(),
        MagicMock(),
        fee_model="kraken",
        strategy_name="grok_grid_atr_adaptive_v4",
        candle_interval=240,
    )

    assert backtester._strategy_bot_id == "grid_atr_v4"
    assert backtester._strategy_params["order_size_usdc"] == 25
    assert backtester._strategy_params["atr_multiplier"] == 4.0
    assert "order_amount_usdc" not in backtester._strategy_params


@pytest.mark.asyncio
async def test_build_grok_grid_replay_sequence_uses_only_4h_1d_1w():
    """Faithful ATR-grid replay loads the 4h decision series plus the 1d/1w context (C2, R1)."""
    backtester = GridBacktester(
        _build_grid_settings(),
        MagicMock(),
        fee_model="kraken",
        strategy_name="grok_grid_atr_adaptive_v4",
        candle_interval=5,  # C2 (R1): the grid replay refuses a trading interval >= 4h
    )
    start_time = datetime.now(UTC) - timedelta(days=30)
    end_time = datetime.now(UTC)
    loaded: list[tuple[int, datetime, datetime]] = []

    async def fake_load(pair: str, interval: int, start: datetime, end: datetime):  # noqa: ARG001
        loaded.append((interval, start, end))
        return []

    backtester._load_candles_for_interval = fake_load  # type: ignore[method-assign]

    sequence = await backtester._build_grok_grid_replay_sequence(
        "XBT/USDC", start_time, end_time, []
    )

    assert sequence == []
    assert [interval for interval, _, _ in loaded] == [240, 1440, 10080]
    # C2 (R1): the 4h decision series is loaded over the whole run, no longer up to start
    assert all(end == end_time for _, _, end in loaded)


@pytest.mark.asyncio
async def test_grok_grid_buy_fill_creates_paired_sell_via_strategy():
    """A buy fill should open a position and create a paired sell target."""
    backtester = GridBacktester(
        _build_grid_settings(),
        MagicMock(),
        fee_model="kraken",
        strategy_name="grok_grid_atr_adaptive_v4",
        candle_interval=240,
    )
    strategy, _analyzer = await backtester._create_grok_grid_strategy()
    strategy._grid_spacing = Decimal("0.02")
    strategy._current_timestamp = datetime.now(UTC)
    level = SimpleNamespace(
        price=Decimal("95000.0"),
        side="buy",
        status="pending",
        amount_usdc=Decimal("25"),
    )
    strategy._grid_levels["buy_95000.0"] = level
    candle = _build_test_candle(price="95000.0")

    await backtester._process_grok_grid_buy_fill(
        strategy,
        {
            "order_id": "buy_95000.0",
            "side": "buy",
            "price": Decimal("95000.0"),
            "amount_usdc": Decimal("25"),
            "level": level,
        },
        candle,
    )

    assert level.status == "filled"
    assert len(strategy.open_positions) == 1
    assert backtester.usdc_balance == Decimal("975")
    assert backtester.btc_held > Decimal("0")

    pending_orders = backtester._get_grok_grid_pending_orders(strategy)
    assert any(order["side"] == "sell" for order in pending_orders)
    assert pending_orders[-1]["price"] == strategy.open_positions[0].sell_level


@pytest.mark.asyncio
async def test_grok_grid_sell_fill_closes_position_and_places_paired_buy():
    """A sell fill should close the matching position, book P&L, and recreate a buy target."""
    backtester = GridBacktester(
        _build_grid_settings(),
        MagicMock(),
        fee_model="kraken",
        strategy_name="grok_grid_atr_adaptive_v4",
        candle_interval=240,
    )
    strategy, _analyzer = await backtester._create_grok_grid_strategy()
    strategy._grid_spacing = Decimal("0.02")
    strategy._current_timestamp = datetime.now(UTC)
    buy_level = SimpleNamespace(
        price=Decimal("95000.0"),
        side="buy",
        status="pending",
        amount_usdc=Decimal("25"),
    )
    strategy._grid_levels["buy_95000.0"] = buy_level
    buy_candle = _build_test_candle(price="95000.0")
    await backtester._process_grok_grid_buy_fill(
        strategy,
        {
            "order_id": "buy_95000.0",
            "side": "buy",
            "price": Decimal("95000.0"),
            "amount_usdc": Decimal("25"),
            "level": buy_level,
        },
        buy_candle,
    )

    position = strategy.open_positions[0]
    backtester.total_orders_placed = 0
    sell_candle = _build_test_candle(
        timestamp=buy_candle.timestamp + timedelta(hours=4), price=str(position.sell_level)
    )

    await backtester._process_grok_grid_sell_fill(
        strategy,
        {
            "order_id": f"sell_pos_{position.position_id}",
            "side": "sell",
            "price": position.sell_level,
            "amount_btc": position.amount_btc,
            "position_id": position.position_id,
        },
        sell_candle,
    )

    assert strategy.open_positions == []
    assert backtester.pairs_completed == 1
    assert backtester.grid_profit > Decimal("0")
    pending_orders = backtester._get_grok_grid_pending_orders(strategy)
    assert any(order["side"] == "buy" for order in pending_orders)


@pytest.mark.asyncio
async def test_grok_grid_pending_orders_preserve_sell_targets_after_recalc():
    """Recalculation must not erase paired sell targets for already-open positions."""
    backtester = GridBacktester(
        _build_grid_settings(),
        MagicMock(),
        fee_model="kraken",
        strategy_name="grok_grid_atr_adaptive_v4",
        candle_interval=240,
    )
    strategy, _analyzer = await backtester._create_grok_grid_strategy()
    strategy._skip_db_sync = True
    strategy._grid_initialized = True
    strategy._grid_center = Decimal("100000")
    strategy._grid_spacing = Decimal("0.02")
    strategy._current_timestamp = datetime.now(UTC)
    strategy._grid_positions.append(
        SimpleNamespace(
            position_id=7,
            entry_price=Decimal("95000"),
            entry_time=datetime.now(UTC),
            amount_btc=Decimal("0.001"),
            amount_usdc=Decimal("95"),
            sell_level=Decimal("96900.0"),
        )
    )

    await strategy._recalculate_grid(
        current_price=Decimal("101000"),
        spacing=Decimal("0.021"),
        regime_1d="bull",
        now=datetime.now(UTC),
    )

    pending_orders = backtester._get_grok_grid_pending_orders(strategy)
    assert any(
        order["side"] == "sell"
        and order["position_id"] == 7
        and order["price"] == Decimal("96900.0")
        for order in pending_orders
    )
