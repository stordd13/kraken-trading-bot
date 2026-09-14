"""End-of-run market liquidation of the GridBacktester terminal inventory (B4.3, no DB).

Chantier 0 of B4.3: on the grok path ``run()`` records the last tradeable close, so the
terminal inventory is liquidated at MARKET (``close × (1 − spread − slippage)``, taker fee),
settled into the balances, tagged ``forced_liquidation`` and reflected by a final equity
point; and ``net_pnl`` counts every fee once (``total_pnl − buy fees``), which makes the cash
identity ``net_pnl == ending_balance − starting_balance`` hold whenever the run ends flat.

The reachability tests drive the real ``GridBacktester.run()`` with synthetic 5-minute candles
and the real ``GrokGridATRAdaptiveV4`` (its 4h grid logic stubbed, one pending BUY level).
"""

# ruff: noqa: E402
from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
import json
from pathlib import Path
import sys
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

_project_root = str(Path(__file__).resolve().parent.parent.parent)
sys.path.insert(0, _project_root)
sys.path.insert(0, str(Path(_project_root) / "src"))
sys.path.insert(0, str(Path(_project_root) / "scripts"))
sys.path.insert(0, str(Path(_project_root) / "scripts" / "audit"))

import b4_2_reference_capture as harness

from krakenbot.models.base import TradeSide
from krakenbot.models.market_data import OHLCData
from krakenbot.strategies.grok_grid_atr_adaptive_v4 import GridATRLevel
from scripts.backtest import (
    BacktestEngine,
    BacktestMetrics,
    BacktestTrade,
    GridBacktester,
    PairCosts,
    dump_trades_json,
)

T0 = datetime(2025, 3, 1, 0, 5, tzinfo=UTC)
STEP = timedelta(minutes=5)
PAIR = "BTC/USDC"
LEVEL = Decimal("100000.0")  # pending BUY level, 25 USDC
ORDER = Decimal("25")
TAKER_BYBIT = Decimal("0.0025")


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
        trading=SimpleNamespace(pair=PAIR, default_order_amount_eur=50),
    )


def _candle(i: int, o: str, h: str, low: str, c: str) -> OHLCData:
    return OHLCData(
        timestamp=T0 + i * STEP,
        pair=PAIR,
        interval=5,
        exchange="binance",
        open=Decimal(o),
        high=Decimal(h),
        low=Decimal(low),
        close=Decimal(c),
        volume=Decimal("1"),
        vwap=Decimal(c),
        trades_count=1,
    )


def _flat(i: int, price: str) -> OHLCData:
    return _candle(i, price, price, price, price)


def _engine(fee_model: str = "bybit", **kwargs: object) -> GridBacktester:
    return GridBacktester(
        _grid_settings(),
        MagicMock(),
        fee_model=fee_model,
        strategy_name="grok_grid_atr_adaptive_v4",
        candle_interval=5,
        exchange="binance",
        **kwargs,  # type: ignore[arg-type]
    )


async def _run(engine: GridBacktester, candles: list[OHLCData]) -> GridBacktester:
    """Drive the real run() over synthetic candles with the real strategy (grid logic stubbed)."""
    strategy, _analyzer = await engine._create_grok_grid_strategy()
    strategy._handle_ohlc = AsyncMock()  # no ATR/regime warm-up: the grid is seeded below
    strategy._grid_spacing = Decimal("0.02")
    strategy._grid_center = LEVEL
    strategy._grid_levels[f"buy_{LEVEL}"] = GridATRLevel(
        price=LEVEL, side="buy", status="pending", amount_usdc=ORDER
    )
    engine._create_grok_grid_strategy = AsyncMock(return_value=(strategy, MagicMock()))  # type: ignore[method-assign]
    engine._load_candles = AsyncMock(return_value=candles)  # type: ignore[method-assign]
    engine._load_candles_for_interval = AsyncMock(return_value=[])  # type: ignore[method-assign]
    await engine.run(PAIR, candles[0].timestamp, candles[-1].timestamp)
    return engine


def _open_then_flat(after: str = "90000") -> list[OHLCData]:
    """c0 fills the BUY at 100000 (low 99500); c1..c9 flat below the paired sell (102000)."""
    return [_candle(0, "100500", "100500", "99500", "100000")] + [
        _flat(i, after) for i in range(1, 10)
    ]


# ---------------------------------------------------------------------------
# Reachability through run() — T1 / T2 / T3
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_grok_path_liquidates_terminal_inventory_at_market(tmp_path: Path) -> None:
    engine = await _run(_engine("bybit"), _open_then_flat())

    assert [t.side for t in engine.metrics.trades] == [TradeSide.BUY, TradeSide.SELL]
    buy, liq = engine.metrics.trades
    assert buy.liquidity == "maker" and buy.forced_liquidation is False
    assert buy.amount_crypto == Decimal("0.00024975")  # (25 - 0.025) / 100000

    assert liq.forced_liquidation is True
    assert liq.liquidity == "taker"
    assert liq.fee_rate == TAKER_BYBIT
    assert liq.reference_price == Decimal("90000")
    assert liq.price == Decimal("90000") * (Decimal("1") - Decimal("0.0002") - Decimal("0.0002"))
    assert liq.price == Decimal("89964")
    assert liq.spread_pct == liq.slippage_pct == Decimal("0.0002")
    assert liq.amount_crypto == Decimal("0.00024975")
    assert liq.amount_usdc == liq.fee_base_usdc == Decimal("22.468509")
    assert liq.fee == Decimal("0.0561712725")
    assert liq.pnl == Decimal("-2.5626622725")
    assert liq.timestamp == T0 + 9 * STEP  # last tradeable candle

    m = engine.metrics
    assert m.total_trades == engine.liquidated_positions == 1
    assert engine.pairs_completed == 0
    assert m.losing_trades == 1 and m.winning_trades == 0
    assert m.win_rate == 0.0 and m.profit_factor == 0.0
    assert m.unrealized_pnl == liq.pnl
    assert m.total_fees == Decimal("0.0811712725")
    assert engine.buy_fees == Decimal("0.025")
    assert engine.btc_held == Decimal("0")
    assert engine.liquidation_dust_btc == Decimal("0")
    assert engine.inventory_divergence_btc == Decimal("0")
    assert engine.usdc_balance == Decimal("997.4123377275")

    # Equity: 10 candle points + the liquidation point; ending balance == cash.
    assert len(engine.equity_curve) == 11
    assert engine.equity_curve[-2][1] == Decimal("975") + Decimal("0.00024975") * Decimal("90000")
    assert engine.equity_curve[-1] == (T0 + 9 * STEP, engine.usdc_balance)
    assert m.ending_balance == engine.usdc_balance
    assert m.total_return_pct == pytest.approx(-0.25876622725)
    assert m.max_drawdown == Decimal("2.5876622725")  # peak = starting balance
    # Cash identity (fix b): every fee counted once.
    assert m.net_pnl == Decimal("-2.5876622725") == engine.usdc_balance - m.starting_balance

    # Harness parity: the capture counts the taker liquidation; the dump tags it and passes
    # verify-fees; both project onto the same schema-1 core (the liquidation block is outside).
    capture = harness.capture_payload(
        engine,
        strategy="grok_grid_atr_adaptive_v4",
        pair=PAIR,
        exchange="binance",
        start=T0,
        end=T0 + 9 * STEP,
        interval=5,
        capital=1000.0,
    )
    assert capture["grid"]["fills"] == {"buy": 1, "sell": 1, "force_closed": 1}
    out = tmp_path / "dump.json"
    dump_trades_json(
        engine,
        out,
        pair=PAIR,
        start=T0,
        end=T0 + 9 * STEP,
        exchange="binance",
        interval=5,
        capital=1000.0,
    )
    payload = json.loads(out.read_text())
    assert payload["trades"][-1]["forced_liquidation"] is True
    assert payload["trades"][0]["forced_liquidation"] is False
    assert payload["liquidation"]["positions"] == 1
    assert payload["liquidation"]["trades"] == 1
    assert payload["liquidation"]["residual_trade_btc"] == "0"
    assert Decimal(payload["liquidation"]["price"]) == Decimal("89964")
    assert Decimal(payload["liquidation"]["reference_price"]) == Decimal("90000")
    assert Decimal(payload["liquidation"]["buy_fees"]) == Decimal("0.025")
    assert Decimal(payload["liquidation"]["sell_fees"]) == liq.fee
    assert Decimal(payload["liquidation"]["pnl"]) == liq.pnl
    assert payload["grid"]["btc_held"] == "0"
    violations, counts = harness.verify_fees(payload, harness.FEE_FACTORIES["bybit"]())
    assert violations == []
    assert counts == {"buy/maker": 1, "sell/taker-market": 1}
    assert harness.compare_payloads(capture, payload) is None


@pytest.mark.asyncio
async def test_liquidation_under_binance_model_uses_its_globals() -> None:
    engine = await _run(_engine("binance"), _open_then_flat())
    liq = engine.metrics.trades[-1]
    assert liq.forced_liquidation is True
    assert liq.price == Decimal("90000") * (Decimal("1") - Decimal("0.0002") - Decimal("0.0001"))
    assert liq.price == Decimal("89973")
    assert liq.fee_rate == Decimal("0.00075")
    assert liq.fee == liq.amount_usdc * Decimal("0.00075")
    assert engine.btc_held == Decimal("0")
    assert engine.metrics.net_pnl == engine.usdc_balance - engine.metrics.starting_balance
    assert engine.metrics.ending_balance == engine.usdc_balance


@pytest.mark.asyncio
async def test_pair_costs_override_applies_only_to_the_liquidation(tmp_path: Path) -> None:
    override = {PAIR: PairCosts(Decimal("0.0010"), Decimal("0.0005"))}
    engine = await _run(_engine("bybit", pair_costs=override), _open_then_flat())
    buy, liq = engine.metrics.trades
    assert buy.liquidity == "maker" and buy.spread_pct == buy.slippage_pct == Decimal("0")
    assert liq.price == Decimal("90000") * (Decimal("1") - Decimal("0.0015")) == Decimal("89865")
    assert liq.spread_pct == Decimal("0.0010") and liq.slippage_pct == Decimal("0.0005")
    out = tmp_path / "dump.json"
    dump_trades_json(
        engine,
        out,
        pair=PAIR,
        start=T0,
        end=T0 + 9 * STEP,
        exchange="binance",
        interval=5,
        capital=1000.0,
    )
    payload = json.loads(out.read_text())
    assert payload["pair_costs"] == {PAIR: {"spread": "0.0010", "slippage": "0.0005"}}
    # verify-fees is deliberately NOT run here: the harness checks the fee-model globals
    # (per-pair overrides are taught to it in the campaign commit).

    # An override for another pair falls back to the model globals ...
    other = await _run(
        _engine("bybit", pair_costs={"ETH/USDC": PairCosts(Decimal("0.0010"), Decimal("0.0005"))}),
        _open_then_flat(),
    )
    # ... and is bit-identical to the bare engine (absent kwarg == pair_costs=None).
    bare = await _run(_engine("bybit"), _open_then_flat())
    explicit = await _run(_engine("bybit", pair_costs=None), _open_then_flat())
    for e in (other, explicit):
        assert [(t.price, t.fee, t.pnl) for t in e.metrics.trades] == [
            (t.price, t.fee, t.pnl) for t in bare.metrics.trades
        ]
        assert e.metrics.to_dict() == bare.metrics.to_dict()


# ---------------------------------------------------------------------------
# Empty inventory — T4a / T4b
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_empty_inventory_without_any_fill_books_no_liquidation() -> None:
    engine = await _run(_engine("bybit"), [_flat(i, "101000") for i in range(10)])
    assert engine.metrics.trades == []
    assert len(engine.equity_curve) == 10
    assert engine.btc_held == Decimal("0")
    assert engine.metrics.unrealized_pnl == Decimal("0")
    assert engine.metrics.ending_balance == Decimal("1000")
    assert engine.metrics.net_pnl == Decimal("0")
    assert engine.liquidated_positions == 0


@pytest.mark.asyncio
async def test_completed_pair_leaves_nothing_to_liquidate(tmp_path: Path) -> None:
    candles = [
        _candle(0, "100500", "100500", "99500", "100000"),  # BUY fills at 100000
        _candle(1, "100500", "102000", "100500", "101000"),  # paired SELL fills at 102000
    ] + [_flat(i, "100500") for i in range(2, 10)]  # the new buy at 99960 never fills
    engine = await _run(_engine("bybit"), candles)

    assert [t.side for t in engine.metrics.trades] == [TradeSide.BUY, TradeSide.SELL]
    assert all(t.liquidity == "maker" and not t.forced_liquidation for t in engine.metrics.trades)
    sell = engine.metrics.trades[-1]
    assert sell.pnl == Decimal("0.4740255")  # 0.00024975 * 102000 * (1 - 0.001) - 24.975
    assert len(engine.equity_curve) == 10
    assert engine.btc_held == Decimal("0")
    assert engine.pairs_completed == engine.metrics.total_trades == 1
    assert engine.liquidated_positions == 0
    assert engine.metrics.unrealized_pnl == Decimal("0")
    assert engine.buy_fees == Decimal("0.025")
    m = engine.metrics
    assert m.net_pnl == Decimal("0.4490255") == engine.usdc_balance - m.starting_balance
    assert m.net_pnl != m.total_pnl - m.total_fees  # the old formula double-counted the sell fee
    out = tmp_path / "dump.json"
    dump_trades_json(
        engine,
        out,
        pair=PAIR,
        start=T0,
        end=T0 + 9 * STEP,
        exchange="binance",
        interval=5,
        capital=1000.0,
    )
    payload = json.loads(out.read_text())
    assert payload["liquidation"]["positions"] == 0
    assert payload["liquidation"]["trades"] == 0
    assert payload["liquidation"]["timestamp"] is None


# ---------------------------------------------------------------------------
# net_pnl accounting — T5 (grid) / T5b (signal)
# ---------------------------------------------------------------------------


def test_grid_net_pnl_counts_each_fee_once() -> None:
    engine = _engine("bybit")
    now = datetime(2025, 3, 1, tzinfo=UTC)
    engine.metrics.trades = [
        BacktestTrade(
            timestamp=now,
            side=TradeSide.BUY,
            price=Decimal("100000"),
            amount_usdc=ORDER,
            amount_crypto=Decimal("0.00024975"),
            fee=Decimal("0.025"),
        ),
        BacktestTrade(
            timestamp=now + STEP,
            side=TradeSide.SELL,
            price=Decimal("102000"),
            amount_usdc=Decimal("25.4745"),
            amount_crypto=Decimal("0.00024975"),
            fee=Decimal("0.0254745"),
            pnl=Decimal("0.4740255"),
        ),
    ]
    engine.total_fees = Decimal("0.0504745")
    engine.metrics.total_pnl = Decimal("0.4740255")
    engine.pairs_completed = 1
    engine.metrics.winning_trades = 1
    engine._calculate_final_metrics()
    assert engine.buy_fees == Decimal("0.025")
    assert engine.metrics.net_pnl == Decimal("0.4490255")  # old formula: 0.4235510
    assert engine.metrics.total_fees == Decimal("0.0504745")
    assert engine.metrics.total_trades == 1


def test_signal_net_pnl_counts_each_fee_once_and_matches_cash() -> None:
    """One flat round trip: buy 50 USDC @100 (fee 0.05), sell @110 (fee 0.25 %)."""
    engine = BacktestEngine(MagicMock(), MagicMock(), fee_model="bybit", exchange="binance")
    now = datetime(2025, 3, 1, tzinfo=UTC)
    crypto = (Decimal("50") - Decimal("0.05")) / Decimal("100")  # 0.4995
    proceeds = crypto * Decimal("110")  # 54.945
    sell_fee = proceeds * TAKER_BYBIT  # 0.1373625
    pnl = proceeds - sell_fee - crypto * Decimal("100")  # 4.8576375
    engine.metrics.trades = [
        BacktestTrade(
            timestamp=now,
            side=TradeSide.BUY,
            price=Decimal("100"),
            amount_usdc=Decimal("50"),
            amount_crypto=crypto,
            fee=Decimal("0.05"),
        ),
        BacktestTrade(
            timestamp=now + STEP,
            side=TradeSide.SELL,
            price=Decimal("110"),
            amount_usdc=proceeds - sell_fee,
            amount_crypto=crypto,
            fee=sell_fee,
            pnl=pnl,
        ),
    ]
    engine.metrics.total_pnl = pnl
    engine.metrics.total_fees = Decimal("0.05") + sell_fee
    engine.metrics.winning_trades = 1
    engine.usdc_balance = Decimal("1000") - Decimal("50") + proceeds - sell_fee
    engine.crypto_balance = Decimal("0")
    engine.calculate_final_metrics()
    assert engine.metrics.net_pnl == pnl - Decimal("0.05") == Decimal("4.8076375")
    assert engine.metrics.ending_balance == engine.usdc_balance
    assert engine.metrics.net_pnl == engine.metrics.ending_balance - engine.metrics.starting_balance


# ---------------------------------------------------------------------------
# Inventory reconciliation — T6 / T7 / T8 / T9 / T11
# ---------------------------------------------------------------------------


def _liquidation_engine(btc_held: Decimal, lots: list[tuple[str, str]]) -> GridBacktester:
    engine = _engine("bybit")
    now = datetime(2025, 3, 15, tzinfo=UTC)
    engine._last_close = Decimal("90000")
    engine._last_timestamp = now
    engine.metrics.end_time = now
    engine.btc_held = btc_held
    engine._strategy_obj = SimpleNamespace(
        open_positions=[
            SimpleNamespace(amount_btc=Decimal(a), entry_price=Decimal(e)) for a, e in lots
        ]
    )
    engine.equity_curve = [(now, engine.usdc_balance + btc_held * Decimal("90000"))]
    return engine


def test_phantom_lot_is_clamped_to_the_btc_actually_held() -> None:
    engine = _liquidation_engine(Decimal("0.025"), [("0.02", "95000"), ("0.01", "95000")])
    engine._calculate_final_metrics()
    tagged = [t for t in engine.metrics.trades if t.forced_liquidation]
    assert [t.amount_crypto for t in tagged] == [Decimal("0.02"), Decimal("0.005")]
    assert all(t.pnl is not None for t in tagged)
    assert engine.liquidated_positions == engine.metrics.total_trades == 2
    assert engine.inventory_divergence_btc == Decimal("-0.005")
    assert engine.liquidation_dust_btc == Decimal("0")
    assert engine.btc_held == Decimal("0")
    assert engine.metrics.ending_balance == engine.usdc_balance == engine.equity_curve[-1][1]


def test_btc_without_a_lot_is_liquidated_with_unknown_cost_basis() -> None:
    engine = _liquidation_engine(Decimal("0.025"), [("0.02", "95000")])
    engine._calculate_final_metrics()
    tagged = [t for t in engine.metrics.trades if t.forced_liquidation]
    assert [t.amount_crypto for t in tagged] == [Decimal("0.02"), Decimal("0.005")]
    assert tagged[0].pnl is not None and tagged[1].pnl is None
    assert engine.liquidated_positions == engine.metrics.total_trades == 1
    assert engine.metrics.unrealized_pnl == tagged[0].pnl
    assert engine.inventory_divergence_btc == Decimal("0.005")
    assert engine.btc_held == Decimal("0")
    net = sum((t.amount_usdc - t.fee for t in tagged), Decimal("0"))
    assert engine.usdc_balance == Decimal("1000") + net
    assert engine.metrics.ending_balance == engine.usdc_balance


@pytest.mark.parametrize("dust", [Decimal("-1E-20"), Decimal("1E-20")])
def test_decimal_dust_is_written_off_without_a_trade(dust: Decimal) -> None:
    engine = _liquidation_engine(Decimal("0.02") + dust, [("0.02", "95000")])
    engine._calculate_final_metrics()
    tagged = [t for t in engine.metrics.trades if t.forced_liquidation]
    assert [t.amount_crypto for t in tagged] == [Decimal("0.02")]
    assert tagged[0].pnl is not None
    assert engine.btc_held == Decimal("0")
    assert engine.liquidation_dust_btc == dust
    assert engine.inventory_divergence_btc == dust
    assert engine.equity_curve[-1][1] == engine.usdc_balance


def test_legacy_branch_uses_the_same_liquidation_semantics() -> None:
    engine = _engine("bybit")
    now = datetime(2025, 3, 15, tzinfo=UTC)
    engine._last_close = Decimal("90000")
    engine._last_timestamp = now
    engine.metrics.end_time = now
    engine.btc_held = Decimal("0.01")
    engine.usdc_balance = Decimal("0")
    engine.active_sell_orders = [
        {
            "price": Decimal("105000"),
            "amount_btc": Decimal("0.01"),
            "entry_price": Decimal("100000"),
        }
    ]
    engine._calculate_final_metrics()
    (trade,) = engine.metrics.trades
    assert trade.forced_liquidation is True
    assert trade.price == Decimal("89964")
    assert trade.fee == Decimal("2.2491")
    assert trade.pnl == Decimal("-102.6091")
    assert engine.btc_held == Decimal("0")
    assert engine.active_sell_orders == []
    assert engine.usdc_balance == Decimal("897.3909")
    assert engine.metrics.ending_balance == engine.usdc_balance == engine.equity_curve[-1][1]


def test_no_tradeable_candle_means_no_liquidation() -> None:
    engine = _liquidation_engine(Decimal("0.02"), [("0.02", "95000")])
    engine._last_close = None
    curve = list(engine.equity_curve)
    engine._calculate_final_metrics()
    assert engine.metrics.trades == []
    assert engine.metrics.unrealized_pnl == Decimal("0")
    assert engine.equity_curve == curve
    assert engine.btc_held == Decimal("0.02")  # untouched: nothing was marked


@pytest.mark.asyncio
async def test_final_metrics_are_idempotent_after_the_liquidation() -> None:
    engine = await _run(_engine("bybit"), _open_then_flat())
    trades, curve, net = (
        list(engine.metrics.trades),
        list(engine.equity_curve),
        engine.metrics.net_pnl,
    )
    engine._calculate_final_metrics()
    assert engine.metrics.trades == trades
    assert engine.equity_curve == curve
    assert engine.metrics.net_pnl == net
    assert engine.btc_held == Decimal("0")


# ---------------------------------------------------------------------------
# Schema guards — T10
# ---------------------------------------------------------------------------


def test_metrics_schema_and_signal_dump_are_unchanged(tmp_path: Path) -> None:
    assert list(BacktestMetrics().to_dict()) == [
        "total_trades",
        "winning_trades",
        "losing_trades",
        "win_rate",
        "total_return_pct",
        "sharpe_ratio",
        "sortino_ratio",
        "max_drawdown_pct",
        "profit_factor",
        "calmar_ratio",
        "net_pnl",
        "total_fees",
        "total_pnl",
        "unrealized_pnl",
        "starting_balance",
        "ending_balance",
        "duration_days",
        "average_holding_time_minutes",
    ]
    trade = BacktestTrade(
        timestamp=T0,
        side=TradeSide.BUY,
        price=Decimal("1"),
        amount_usdc=Decimal("1"),
        amount_crypto=Decimal("1"),
        fee=Decimal("0"),
    )
    assert trade.forced_liquidation is False
    assert "forced_liquidation" not in harness.CORE_TRADE_KEYS

    engine = BacktestEngine(MagicMock(), MagicMock(), fee_model="bybit", exchange="binance")
    engine.metrics.trades = [trade]
    out = tmp_path / "signal.json"
    dump_trades_json(
        engine,
        out,
        pair=PAIR,
        start=T0,
        end=T0 + STEP,
        exchange="binance",
        interval=5,
        capital=1000.0,
    )
    payload = json.loads(out.read_text())
    assert "forced_liquidation" not in payload["trades"][0]
    assert "liquidation" not in payload
    assert "grid" not in payload
