"""C1 — the engines on the shared metrics: buy-fee allocation at every sell site, the identity
``sum(pnl_net_trade) == net_pnl`` on reconciled runs (and its absence otherwise), daily metrics
from the run dates, the equity sidecar. No DB: synthetic candles through the real ``run()``."""

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

_project_root = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(_project_root))
sys.path.insert(0, str(_project_root / "src"))
sys.path.insert(0, str(_project_root / "scripts"))
sys.path.insert(0, str(_project_root / "tests"))

from krakenbot.backtest_metrics import TradeLeg, net_trade_pnls
from krakenbot.models.base import TradeSide
from krakenbot.strategies.base import SignalType, TradingSignal
from scripts.backtest import BacktestEngine, dump_equity_jsonl, parse_args
from test_scripts.test_grid_terminal_liquidation import (
    ORDER,
    PAIR,
    STEP,
    T0,
    _candle,
    _engine,
    _flat,
    _open_then_flat,
    _run,
)

TOL = Decimal("1e-9")  # b4_flags.NET_PNL_TOL: metrics are floats, the identity holds to ~1e-13


def _legs(engine: object) -> list[TradeLeg]:
    return [
        TradeLeg(
            side=t.side.value,
            timestamp=t.timestamp,
            amount_crypto=t.amount_crypto,
            fee=t.fee,
            pnl=t.pnl,
            buy_fee_alloc=t.buy_fee_alloc,
        )
        for t in engine.metrics.trades  # type: ignore[attr-defined]
    ]


# ---------------------------------------------------------------------------
# Grid engine through run()
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_grid_liquidated_lot_carries_its_buy_fee_and_the_identity_holds() -> None:
    """One maker buy (25 USDC, fee 0.025) liquidated at the end: the liquidation leg carries the
    lot's buy fee (derived from the cost basis) and sum(pnl_net_trade) == net_pnl (cash)."""
    engine = await _run(_engine("bybit"), _open_then_flat())
    buy, liq = engine.metrics.trades
    assert buy.buy_fee_alloc is None  # BUY legs never carry an allocation
    assert liq.forced_liquidation and liq.pnl is not None
    assert liq.buy_fee_alloc == buy.fee == Decimal("0.025")  # cost 24.975 * 0.001 / 0.999
    assert engine.btc_held == 0 and engine.metrics.pf_excluded_trades == 0  # precondition
    pf = net_trade_pnls(_legs(engine))
    assert abs(sum(pf.net_trade_pnls, Decimal("0")) - engine.metrics.net_pnl) <= TOL
    assert engine.metrics.net_pnl == engine.usdc_balance - engine.metrics.starting_balance
    # the lot lost: PF is a real ratio of the sums (0 / losses = 0.0, defined), the loss is
    # net of BOTH fees
    assert engine.metrics.profit_factor == 0.0
    assert engine.metrics.gross_profit_net == 0
    assert engine.metrics.gross_loss_net == -(liq.pnl - Decimal("0.025"))


@pytest.mark.asyncio
async def test_grid_completed_maker_pair_carries_the_buy_fee_and_reconciles() -> None:
    """c0 fills the BUY at 100000, c1 touches the paired SELL (102000): a maker round trip, no
    inventory left, no liquidation; the SELL leg carries the 0.025 buy fee."""
    candles = [
        _candle(0, "100500", "100500", "99500", "100000"),
        _candle(1, "100000", "102500", "99800", "101000"),
    ] + [_flat(i, "101000") for i in range(2, 10)]
    engine = await _run(_engine("bybit"), candles)
    sides = [t.side for t in engine.metrics.trades]
    assert sides == [TradeSide.BUY, TradeSide.SELL]
    sell = engine.metrics.trades[1]
    assert not sell.forced_liquidation and sell.liquidity == "maker"
    assert sell.buy_fee_alloc == Decimal("0.025")
    assert engine.btc_held == 0 and engine.metrics.pf_excluded_trades == 0
    pf = net_trade_pnls(_legs(engine))
    assert abs(sum(pf.net_trade_pnls, Decimal("0")) - engine.metrics.net_pnl) <= TOL
    # the pair is profitable net of both legs: sell 0.00024975 * 102000 * (1 - 0.001) - 24.975 - 0.025
    expected_net = Decimal("0.00024975") * Decimal("102000") * Decimal("0.999") - ORDER
    assert abs(pf.net_trade_pnls[0] - expected_net) <= TOL
    assert engine.metrics.profit_factor is None and engine.metrics.gross_profit_net > 0
    assert engine.metrics.profit_factor_display() == "∞"
    # daily grid of a 45-minute run: start and end only (partial edge), one return
    assert engine.metrics.equity_daily_dict() == {
        "start": T0.isoformat(),
        "end": (T0 + 9 * STEP).isoformat(),
        "values": [1000.0, float(engine.metrics.ending_balance)],
    }
    assert engine.metrics.n_daily_returns == 1
    assert engine.metrics.sharpe_ratio is None  # a single return has no std


def test_grid_unknown_cost_lot_is_excluded_and_no_identity_is_claimed() -> None:
    """BTC held without any lot (inventory divergence): liquidated with pnl None -> excluded from
    the PF, flagged incomplete; sum(pnl_net_trade) is NOT the cash net_pnl."""
    engine = _engine("bybit")
    now = datetime(2025, 3, 15, tzinfo=UTC)
    engine._last_close = Decimal("90000")
    engine._last_timestamp = now
    engine.metrics.start_time = now - timedelta(days=1)
    engine.metrics.end_time = now
    engine.btc_held = Decimal("0.001")
    engine._strategy_obj = SimpleNamespace(open_positions=[])
    engine.equity_curve = [(now, engine.usdc_balance + Decimal("0.001") * Decimal("90000"))]
    engine._calculate_final_metrics()
    liq = engine.metrics.trades[-1]
    assert liq.forced_liquidation and liq.pnl is None and liq.buy_fee_alloc is None
    assert engine.metrics.pf_excluded_trades == 1
    assert engine.metrics.profit_factor is None
    assert "incomplete: 1 lot(s)" in engine.metrics.profit_factor_display()
    pf = net_trade_pnls(_legs(engine))
    assert pf.net_trade_pnls == ()  # nothing invented for the unknown cost
    assert engine.metrics.net_pnl != 0  # the proceeds are real cash, counted in net_pnl only


# ---------------------------------------------------------------------------
# Signal engine
# ---------------------------------------------------------------------------


class _Spy:
    async def on_trade_filled(self, **kwargs: object) -> None:
        return None


def _signal_engine(strategy_name: str = "grok_supertrend_4h") -> BacktestEngine:
    settings = SimpleNamespace(trading=SimpleNamespace(pair=PAIR, default_order_amount_eur=100.0))
    engine = BacktestEngine(
        settings,
        MagicMock(),
        fee_model="bybit",
        strategy_name=strategy_name,
        candle_interval=240,
    )
    engine.strategy = _Spy()
    return engine


def _sig(kind: SignalType, ts: datetime, order: float = 50.0) -> TradingSignal:
    return TradingSignal(
        signal_type=kind,
        pair=PAIR,
        price=Decimal("50000"),
        confidence=0.9,
        reason="c1",
        strategy="grok_supertrend_4h",
        timestamp=ts,
        metadata={"order_size_usdc": order},
    )


@pytest.mark.asyncio
async def test_signal_sell_carries_the_open_buy_fees_including_accumulation() -> None:
    """Two buys without a sell in between (accumulation path) then one sell: the SELL leg carries
    the sum of the two buy fees, the accumulator is reset, and the identity holds."""
    engine = _signal_engine("grok_adaptive_dca_weekly")
    t = datetime(2025, 3, 1, tzinfo=UTC)
    await engine.execute_signal(_sig(SignalType.BUY, t), Decimal("50000"), is_limit_fill=True)
    await engine.execute_signal(
        _sig(SignalType.BUY, t + timedelta(days=1)), Decimal("40000"), is_limit_fill=True
    )
    await engine.execute_signal(
        _sig(SignalType.SELL, t + timedelta(days=2)), Decimal("60000"), is_limit_fill=False
    )
    buys = [x for x in engine.metrics.trades if x.side == TradeSide.BUY]
    sell = engine.metrics.trades[-1]
    assert sell.side == TradeSide.SELL
    assert sell.buy_fee_alloc == sum(b.fee for b in buys) == Decimal("0.1")  # 2 x 50 x 0.1 %
    assert engine._open_buy_fees == 0 and engine.crypto_balance == 0
    engine.calculate_final_metrics()
    pf = net_trade_pnls(_legs(engine))
    assert engine.metrics.pf_excluded_trades == 0
    assert abs(sum(pf.net_trade_pnls, Decimal("0")) - engine.metrics.net_pnl) <= TOL


def test_signal_daily_metrics_from_the_run_dates() -> None:
    """Equity at 4h closes over 3 days: the daily grid is anchored at start, the drawdown is
    relative to the running peak on the daily NAV and the engine-resolution one is separate."""
    engine = _signal_engine()
    start = datetime(2025, 3, 1, tzinfo=UTC)
    engine.metrics.start_time = start
    engine.metrics.end_time = start + timedelta(days=3)
    engine.metrics.duration_days = 3.0
    curve: list[tuple[datetime, Decimal]] = []
    values = {6: "700", 12: "900", 24: "1000", 36: "1200", 48: "2000", 60: "1950", 72: "1900"}
    for hours, eq in values.items():
        curve.append((start + timedelta(hours=hours), Decimal(eq)))
    engine.equity_curve = curve
    engine.usdc_balance = Decimal("1900")
    engine.calculate_final_metrics()
    m = engine.metrics
    assert m.equity_daily_dict() == {
        "start": start.isoformat(),
        "end": (start + timedelta(days=3)).isoformat(),
        "values": [1000.0, 1000.0, 2000.0, 1900.0],
    }
    assert m.max_drawdown_pct_daily == 5.0  # 2000 -> 1900
    assert m.max_drawdown_pct_engine == 30.0  # 1000 (anchor) -> 700 at 06:00
    assert m.max_drawdown == Decimal("300")  # money, engine resolution: unchanged by C1
    assert m.n_daily_returns == 3 and m.sharpe_ratio is not None
    assert m.ending_balance == Decimal("1900") and m.total_return_pct == pytest.approx(90.0)


def test_metrics_without_run_dates_still_compute_the_profit_factor() -> None:
    engine = _signal_engine()
    assert engine.metrics.start_time is None
    engine.calculate_final_metrics()
    assert engine.metrics.profit_factor is None and engine.metrics.sharpe_ratio is None
    assert engine.metrics.equity_daily_dict() is None


# ---------------------------------------------------------------------------
# Equity sidecar
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_equity_sidecar_jsonl(tmp_path: Path) -> None:
    engine = await _run(_engine("bybit"), _open_then_flat())
    out = tmp_path / "equity.jsonl"
    n = dump_equity_jsonl(engine, out, pair=PAIR)
    lines = out.read_text().splitlines()
    header, rows = json.loads(lines[0]), [json.loads(x) for x in lines[1:]]
    assert n == len(rows) == len(engine.equity_curve) == 11  # 10 candles + liquidation point
    assert header["metrics_version"] == 2 and header["engine"] == "GridBacktester"
    assert header["fees"] == "bybit" and header["resolution"] == "engine"
    assert list(rows[0]) == [
        "cash",
        "equity",
        "external_flow",
        "inventory_qty",
        "mark_price",
        "timestamp",
    ]
    assert all(r["external_flow"] == "0" for r in rows)
    # the sidecar mirrors equity_curve point by point (Decimals verbatim)
    assert [(r["timestamp"], r["equity"]) for r in rows] == [
        (ts.isoformat(), str(eq)) for ts, eq in engine.equity_curve
    ]
    assert rows[-1]["inventory_qty"] == "0"  # post-liquidation point
    assert Decimal(rows[-1]["cash"]) == engine.usdc_balance


def test_equity_out_refused_with_cross_validate(capsys: pytest.CaptureFixture[str]) -> None:
    base = ["--strategy", "grok_supertrend_4h", "--pair", "BTC/USDC", "--exchange", "binance"]
    with pytest.raises(SystemExit) as exc:
        parse_args([*base, "--fees", "bybit", "--cross-validate", "--equity-out", "e.jsonl"])
    assert exc.value.code == 2
    assert "--equity-out" in capsys.readouterr().err
    args = parse_args([*base, "--fees", "bybit", "--equity-out", "e.jsonl"])
    assert args.equity_out == Path("e.jsonl")
