"""C2 (R1) — the grok grid replay decides on true 4h closes and executes on the trading
candles; every input the decision consumes is recomputed independently from the closed
candles available at that instant; same-timestamp order is execution → contexts → decision.

Synthetic, DB-less: four coherent series (5m / 4h / 1d / 1w, end-stamped on a common grid)
are served by monkeypatched loaders to the real ``GridBacktester`` + real strategy.
"""

# ruff: noqa: E402
from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
import math
from pathlib import Path
import sys
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

_project_root = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_project_root))
sys.path.insert(0, str(_project_root / "scripts"))
sys.path.insert(0, str(_project_root / "src"))

from krakenbot.indicators.multi_timeframe import MultiTimeframeAnalyzer
from krakenbot.models.base import TradeSide
from krakenbot.models.market_data import OHLCData
from scripts.backtest import GridBacktester, ReplayEvent, parse_args

PAIR = "BTC/USDC"
START = datetime(2024, 3, 4, tzinfo=UTC)  # a Monday 00:00: 5m, 4h, 1d and 1w stamps coincide
END = START + timedelta(days=3)


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
                                    "grid_levels": 6,
                                    "min_spacing_pct": 0.015,
                                    "atr_period": 14,
                                    "atr_multiplier": 1.0,  # ATR ~0.5 % x 1.0 < the 1.5 % floor: spacing is the floor
                                    "recalc_hours": 6,
                                    "order_size_usdc": 25,
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


def _price(ts: datetime) -> Decimal:
    """A smooth, deterministic path: trend + two sines (non-trivial regimes and ATR)."""
    days = (ts - START).total_seconds() / 86400
    value = 50000 * (1 + 0.0009 * days + 0.02 * math.sin(days / 9) + 0.006 * math.sin(days * 1.7))
    return Decimal(f"{value:.1f}")


def _candle(ts_end: datetime, interval: int, *, low_override: Decimal | None = None) -> OHLCData:
    o = _price(ts_end - timedelta(minutes=interval))
    c = _price(ts_end)
    hi = max(o, c) * Decimal("1.002")
    lo = min(o, c) * Decimal("0.998") if low_override is None else low_override
    return OHLCData(
        timestamp=ts_end,
        pair=PAIR,
        interval=interval,
        exchange="binance",
        open=o,
        high=hi.quantize(Decimal("0.1")),
        low=lo.quantize(Decimal("0.1")),
        close=c,
        volume=Decimal("5"),
        vwap=c,
        trades_count=1,
    )


def _series(interval: int, first_end: datetime, last_end: datetime) -> list[OHLCData]:
    out, ts = [], first_end
    while ts <= last_end:
        out.append(_candle(ts, interval))
        ts += timedelta(minutes=interval)
    return out


class _Data:
    """The four series + loaders shaped like the engine's (window and count-before)."""

    def __init__(self, *, trading: list[OHLCData] | None = None) -> None:
        step = timedelta(minutes=5)
        self.series: dict[int, list[OHLCData]] = {
            5: trading if trading is not None else _series(5, START + step, END),
            240: _series(240, START - timedelta(days=15), END),
            1440: _series(1440, START - timedelta(days=300), END),
            10080: _series(10080, START - timedelta(weeks=60), END),
        }

    async def window(self, pair: str, interval: int, s: datetime, e: datetime) -> list[OHLCData]:  # noqa: ARG002
        return [c for c in self.series[interval] if s <= c.timestamp <= e]

    async def before(
        self, pair: str, interval: int, before: datetime, limit: int, floor: datetime
    ) -> list[OHLCData]:  # noqa: ARG002
        rows = [c for c in self.series[interval] if floor <= c.timestamp < before]
        return rows[-limit:]


async def _run(data: _Data, **kwargs: object) -> GridBacktester:
    engine = GridBacktester(
        _grid_settings(),
        MagicMock(),
        fee_model="bybit",
        strategy_name="grok_grid_atr_adaptive_v4",
        candle_interval=5,
        exchange="binance",
        **kwargs,  # type: ignore[arg-type]
    )
    engine._load_candles = lambda pair, s, e: data.window(pair, 5, s, e)  # type: ignore[method-assign]
    engine._load_candles_for_interval = data.window  # type: ignore[method-assign]
    if hasattr(engine, "_load_candles_before"):
        engine._load_candles_before = data.before  # type: ignore[method-assign]
    await engine.run(PAIR, START, END)
    return engine


# ---------------------------------------------------------------------------
# Independent recomputation (pure functions, same seed conventions as the indicator classes)
# ---------------------------------------------------------------------------


def _atr_wilder(candles: list[OHLCData], period: int) -> Decimal | None:
    trs: list[Decimal] = []
    prev_close: Decimal | None = None
    for c in candles:
        tr = (
            c.high - c.low
            if prev_close is None
            else max(c.high - c.low, abs(c.high - prev_close), abs(c.low - prev_close))
        )
        trs.append(tr)
        prev_close = c.close
    if len(trs) < period:
        return None
    atr = sum(trs[:period]) / Decimal(period)
    for tr in trs[period:]:
        atr = (atr * (period - 1) + tr) / Decimal(period)
    return atr


def _ema(closes: list[Decimal], period: int) -> Decimal | None:
    if len(closes) < period:
        return None
    ema = sum(closes[:period]) / Decimal(period)
    k = Decimal(2) / (Decimal(period) + 1)
    for c in closes[period:]:
        ema = c * k + ema * (1 - k)
    return ema


def _regime(candles: list[OHLCData]) -> str | None:
    closes = [c.close for c in candles]
    fast, slow = _ema(closes, 20), _ema(closes, 50)
    if fast is None or slow is None or slow == 0:
        return None
    spread_pct = float((fast - slow) / slow * Decimal(100))
    return MultiTimeframeAnalyzer()._classify_regime(spread_pct).value  # the documented rule


def _rel_close(a: Decimal, b: Decimal) -> bool:
    return abs(a - b) <= abs(b) * Decimal("1e-12")


# ---------------------------------------------------------------------------
# Proof 1 — every decision input == independent recomputation on closed candles <= T
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_grid_decision_inputs_match_independent_recomputation() -> None:
    data = _Data()
    engine = await _run(data)
    trace = engine.decision_trace
    assert trace, "no 4h decision was taken"
    assert trace[0]["timestamp"] >= START
    assert all(t["timestamp"].minute == 0 and t["timestamp"].hour % 4 == 0 for t in trace)
    assert {t["timestamp"] for t in trace} == {
        c.timestamp for c in data.series[240] if c.timestamp >= START
    }
    # Recompute on the bounds the engine REALLY loaded (its warmup report, like the DB test):
    # EMA / ATR seed on their first candles, so the reference must start where the fed
    # history starts — never on the test's own idea of the calendar window.
    first = {tf: datetime.fromisoformat(engine.warmup[tf]["first"]) for tf in ("4h", "1d", "1w")}
    loaded = {
        tf: [c for c in data.series[interval] if first[tf] <= c.timestamp <= END]
        for tf, interval in (("4h", 240), ("1d", 1440), ("1w", 10080))
    }
    for tf, series in loaded.items():
        assert series[0].timestamp == first[tf] and engine.warmup[tf]["extended_by"] == 0, tf
    assert first["4h"] == START - timedelta(days=15)  # the calendar floor, no extension here
    for entry in trace[::3] + [trace[-1]]:
        T = entry["timestamp"]
        closed = {tf: [c for c in series if c.timestamp <= T] for tf, series in loaded.items()}
        expected_atr = _atr_wilder(closed["4h"], 14)
        assert expected_atr is not None and _rel_close(entry["atr_4h"], expected_atr), T
        assert entry["regime_1d"] == _regime(closed["1d"]) is not None, T
        assert entry["regime_1w"] == _regime(closed["1w"]) is not None, T
        # no look-ahead: the next 4h candle changes the ATR the decision saw
        closed_4h = closed["4h"]
        nxt = [c for c in loaded["4h"] if c.timestamp > T][:1]
        if nxt:
            assert not _rel_close(entry["atr_4h"], _atr_wilder(closed_4h + nxt, 14))
    # the grid placed orders on those decisions; regimes were non-trivial inputs
    assert engine.total_orders_placed > 0
    assert {t["regime_1d"] for t in trace} <= {
        "strong_bull",
        "bull",
        "neutral",
        "bear",
        "strong_bear",
    }


# ---------------------------------------------------------------------------
# Temporal order at a common timestamp T
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_order_created_at_T_does_not_fill_on_the_candle_ending_at_T() -> None:
    # The first decision is the 4h close at START; the 5m candle ending at START and the next
    # one both dive far below every grid level. The BUY created by the decision at START must
    # fill on START + 5m, never on the candle of START (execution precedes the decision).
    step = timedelta(minutes=5)
    trading = _series(5, START, END)
    deep = Decimal("40000")
    trading[0] = _candle(START, 5, low_override=deep)
    trading[1] = _candle(START + step, 5, low_override=deep)
    engine = await _run(_Data(trading=trading))
    buys = [t for t in engine.metrics.trades if t.side == TradeSide.BUY]
    assert buys, "the deep candle should have filled the grid's buy levels"
    assert min(t.timestamp for t in buys) == START + step
    assert all(t.timestamp != START for t in buys)


@pytest.mark.asyncio
async def test_preexisting_order_touched_at_T_fills_before_the_recalc_at_T_cancels_it() -> None:
    # With recalc_hours = 6 evaluated at 4h closes the grid is rebuilt at START + 8h. The 5m
    # candle ending exactly then touches the first buy level of the initial grid: the fill
    # (execution phase) happens before the rebuild (decision phase) wipes the level.
    t_recalc = START + timedelta(hours=8)
    trading = _series(5, START + timedelta(minutes=5), END)
    idx = next(i for i, c in enumerate(trading) if c.timestamp == t_recalc)
    # keep every candle before the recalc flat above the levels (no earlier fill)
    for i in range(idx):
        c = trading[i]
        trading[i] = OHLCData(
            timestamp=c.timestamp,
            pair=PAIR,
            interval=5,
            exchange="binance",
            open=c.open,
            high=c.high,
            low=c.close,
            close=c.close,
            volume=c.volume,
            vwap=c.vwap,
            trades_count=1,
        )
    first_level = (_price(START) * Decimal("0.985")).quantize(Decimal("0.1"))  # spacing floor 1.5 %
    trading[idx] = _candle(t_recalc, 5, low_override=first_level)
    engine = await _run(_Data(trading=trading))
    buys = [t for t in engine.metrics.trades if t.side == TradeSide.BUY]
    assert [t.timestamp for t in buys][:1] == [t_recalc], buys
    assert engine.rebalance_count >= 1  # the grid was rebuilt at t_recalc, after the fill


@pytest.mark.asyncio
async def test_replay_events_are_ordered_execution_contexts_decision_and_warmup_only_feeds() -> (
    None
):
    data = _Data()
    engine = GridBacktester(
        _grid_settings(),
        MagicMock(),
        fee_model="bybit",
        strategy_name="grok_grid_atr_adaptive_v4",
        candle_interval=5,
    )
    engine._load_candles_for_interval = data.window  # type: ignore[method-assign]
    if hasattr(engine, "_load_candles_before"):
        engine._load_candles_before = data.before  # type: ignore[method-assign]
    events = await engine._build_grok_grid_replay_sequence(PAIR, START, END, data.series[5])
    assert all(isinstance(e, ReplayEvent) for e in events)
    at_start = [e for e in events if e.candle.timestamp == START]
    assert [(e.role, e.interval) for e in at_start] == [
        ("ctx", 10080),
        ("ctx", 1440),
        ("decision", 240),
    ]
    at_4h = [e for e in events if e.candle.timestamp == START + timedelta(hours=4)]
    assert [(e.role, e.interval) for e in at_4h] == [("exec", 5), ("decision", 240)]
    assert all(not e.decides for e in events if e.role == "decision" and e.candle.timestamp < START)
    assert all(e.decides for e in events if e.role == "decision" and e.candle.timestamp >= START)
    stamps = [(e.candle.timestamp, e.phase) for e in events]
    assert stamps == sorted(stamps)


@pytest.mark.asyncio
async def test_no_order_and_no_equity_during_the_warmup() -> None:
    engine = await _run(_Data())
    assert all(t.timestamp >= START for t in engine.metrics.trades)
    assert engine.equity_curve[0][0] >= START
    assert engine.decision_trace[0]["timestamp"] >= START


# ---------------------------------------------------------------------------
# Guards: candle_interval >= 4h refused; --cross-validate × grid refused (N1)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_grid_replay_refuses_a_trading_interval_of_4h_or_more() -> None:
    engine = GridBacktester(
        _grid_settings(),
        MagicMock(),
        fee_model="bybit",
        strategy_name="grok_grid_atr_adaptive_v4",
        candle_interval=240,
    )
    with pytest.raises(ValueError, match="shorter than 4h"):
        await engine._build_grok_grid_replay_sequence(PAIR, START, END, [])


@pytest.mark.parametrize(
    "argv",
    [
        ["--strategy", "grok_grid_atr_adaptive_v4", "--fees", "bybit", "--interval", "240"],
        [
            "--strategy",
            "grok_grid_atr_adaptive_v4",
            "--fees",
            "bybit",
            "--interval",
            "5",
            "--cross-validate",
        ],
    ],
)
def test_cli_refuses_grid_with_4h_interval_or_cross_validate(argv: list[str]) -> None:
    with pytest.raises(SystemExit) as exc:
        parse_args(argv)
    assert exc.value.code == 2


def test_cli_still_accepts_the_campaign_shape() -> None:
    args = parse_args(
        ["--strategy", "grok_grid_atr_adaptive_v4", "--fees", "bybit", "--interval", "5"]
    )
    assert args.interval == 5 and not args.cross_validate
