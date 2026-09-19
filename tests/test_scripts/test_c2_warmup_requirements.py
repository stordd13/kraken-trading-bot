"""C2 (R2) — every indicator a strategy reads is pre-registered at its effective parameters
and ready after a warmup sized in candles; insufficient or stale history is reported, never
bridged silently; the DCA oversold branch is proven synthetically (preuve 6).

Parametrised over the 8 strategies × {class defaults, one non-default variant per
parameterised indicator}. The requirements table is checked against the strategy sources
(every ``analyzer.get_*`` call site is covered) and against what the engines load.
"""

# ruff: noqa: E402
from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
import inspect
from pathlib import Path
import re
import sys
from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock

import pytest

_project_root = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_project_root))
sys.path.insert(0, str(_project_root / "scripts"))
sys.path.insert(0, str(_project_root / "src"))

import p7_grids

from krakenbot.core.event_bus import EventBus
from krakenbot.indicators.multi_timeframe import TF_TO_INTERVAL, MultiTimeframeAnalyzer
from krakenbot.strategies.gemini_retour_moyenne import GeminiRetourMoyenne
from krakenbot.strategies.gemini_scalping_volatilite import GeminiScalpingVolatilite
from krakenbot.strategies.gemini_suivi_tendance_momentum import GeminiSuiviTendanceMomentum
from krakenbot.strategies.grok_adaptive_dca_weekly import GrokAdaptiveDCAWeekly
from krakenbot.strategies.grok_donchian_breakout_4h import GrokDonchianChannelBreakoutV1
from krakenbot.strategies.grok_ema_adx_atr import GrokEMA27_125_ADX_ATR
from krakenbot.strategies.grok_grid_atr_adaptive_v4 import GrokGridATRAdaptiveV4
from krakenbot.strategies.grok_supertrend_4h import GrokSuperTrend4hRegime
from scripts.backtest import (
    BacktestEngine,
    GridBacktester,
    IndicatorRequirement,
    indicator_requirements,
    load_context_series,
    preregister_indicators,
    warmup_needs,
)

PAIR = "BTC/USDC"
T0 = datetime(2024, 1, 1, tzinfo=UTC)

STRATEGIES: dict[str, tuple[type, dict[str, Any]]] = {
    # name: (class, non-default variant params)
    "grok_supertrend_4h": (GrokSuperTrend4hRegime, {"st_atr_period": 8, "st_multiplier": 2.0}),
    "grok_ema_adx_atr": (GrokEMA27_125_ADX_ATR, {"ema_fast": 20, "ema_slow": 125}),
    "grok_donchian_breakout_4h": (
        GrokDonchianChannelBreakoutV1,
        {"donchian_upper_period": 15, "donchian_lower_period": 10},
    ),
    "grok_adaptive_dca_weekly": (GrokAdaptiveDCAWeekly, {"bull_reduction": 0.3}),
    "grok_grid_atr_adaptive_v4": (GrokGridATRAdaptiveV4, {"atr_period": 21}),
    "gemini_scalping_volatilite": (GeminiScalpingVolatilite, {"rsi_period": 9}),
    "gemini_retour_moyenne": (GeminiRetourMoyenne, {}),
    "gemini_suivi_tendance_momentum": (GeminiSuiviTendanceMomentum, {}),
}
_KIND_OF_GETTER = {
    "rsi": "rsi",
    "atr": "atr",
    "ema": "ema",
    "adx": "adx",
    "macd": "macd",
    "bollinger": "bb",
    "supertrend": "supertrend",
    "donchian": "donchian",
    "regime": "regime",
}
_CALL_RE = re.compile(r"analyzer\.get_(\w+)\(([^)]*)\)")
_TF_RE = re.compile(r'"(1m|5m|15m|1h|4h|1d|1w)"')


def _settings() -> SimpleNamespace:
    return SimpleNamespace(
        multi_strategy=SimpleNamespace(enabled=False, strategies=[]),
        trading=SimpleNamespace(pair=PAIR, default_order_amount_eur=50),
    )


def _instantiate(name: str, params: dict[str, Any], analyzer: Any) -> Any:
    cls, _ = STRATEGIES[name]
    strategy = cls(
        settings=_settings(),
        event_bus=EventBus(),
        db_manager=MagicMock(),
        bot_id=name,
        strategy_params={"pair": PAIR, **params},
        analyzer=analyzer,
    )
    strategy._skip_db_sync = True
    strategy._running = True
    return strategy


def _candle(i: int, tf: str) -> dict[str, Decimal]:
    # a deterministic, non-monotone series with real ranges (no zero True Range)
    base = Decimal(50000) + Decimal(((i * 37) % 101) - 50) * Decimal("13.7")
    return {
        "open": base,
        "high": base + Decimal(25) + Decimal(i % 7),
        "low": base - Decimal(25) - Decimal(i % 5),
        "close": base + Decimal(((i * 11) % 13) - 6),
        "volume": Decimal(10 + i % 9),
    }


def _feed(analyzer: MultiTimeframeAnalyzer, tf: str, count: int, offset: int = 0) -> None:
    for i in range(offset, offset + count):
        analyzer.update(_candle(i, tf), TF_TO_INTERVAL[tf])


def _ready(analyzer: MultiTimeframeAnalyzer, req: IndicatorRequirement) -> bool:
    k, tf, p = req.kind, req.tf, req.params
    if k == "ema":
        return analyzer.get_ema(int(p[0]), tf) is not None
    if k == "atr":
        return analyzer.get_atr(int(p[0]), tf) is not None
    if k == "rsi":
        return analyzer.get_rsi(int(p[0]), tf) is not None
    if k == "supertrend":
        return analyzer.get_supertrend(tf, int(p[0]), p[1]) is not None
    if k == "donchian":
        return analyzer.get_donchian(tf, int(p[0]), int(p[1])) is not None
    if k == "adx":
        return analyzer.get_adx(tf) is not None
    if k == "macd":
        return analyzer.get_macd(tf) is not None
    if k == "bb":
        return analyzer.get_bollinger(tf) is not None
    if k == "regime":
        return analyzer.get_regime(tf) is not None
    raise AssertionError(k)


def _registry_keys(analyzer: MultiTimeframeAnalyzer) -> set[tuple[str, str, Any]]:
    return {
        (tf, kind, key)
        for tf, kinds in analyzer._indicators.items()
        for kind, members in kinds.items()
        for key in members
    }


# ---------------------------------------------------------------------------
# 1. The table covers every analyzer call site of every strategy (grep)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("name", sorted(STRATEGIES))
def test_requirements_cover_every_analyzer_call_site(name: str) -> None:
    cls, _ = STRATEGIES[name]
    source = inspect.getsource(cls)
    called: set[tuple[str, str]] = set()
    for getter, args in _CALL_RE.findall(source):
        kind = _KIND_OF_GETTER[getter]
        tf = _TF_RE.search(args)
        assert tf is not None, f"{name}: no timeframe literal in get_{getter}({args})"
        called.add((kind, tf.group(1)))
    reqs = indicator_requirements(name, _instantiate(name, {}, MagicMock()))
    covered = {(r.kind, r.tf) for r in reqs}
    assert called <= covered, f"{name}: uncovered {called - covered}"
    assert covered <= called, f"{name}: requirements not read by the strategy {covered - called}"


# ---------------------------------------------------------------------------
# 2. Pre-registered at the effective params, ready after `need` candles, not before
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("variant", ["defaults", "variant"])
@pytest.mark.parametrize("name", sorted(STRATEGIES))
def test_every_requirement_is_preregistered_and_ready_after_its_warmup(
    name: str, variant: str
) -> None:
    params = STRATEGIES[name][1] if variant == "variant" else {}
    analyzer = MultiTimeframeAnalyzer()
    strategy = _instantiate(name, params, analyzer)
    reqs = indicator_requirements(name, strategy)
    assert reqs, name
    preregister_indicators(analyzer, reqs)
    keys_after_prereg = _registry_keys(analyzer)
    # every lazy requirement now exists in the registry under the exact key of the call site
    for req in reqs:
        if not req.lazy:
            continue
        bucket = analyzer._indicators[req.tf][req.kind]
        key = req.params if req.kind in ("supertrend", "donchian") else int(req.params[0])
        assert key in bucket, f"{name} {variant}: {req} not pre-registered (keys {list(bucket)})"

    needs = warmup_needs(reqs)
    for tf, need in needs.items():
        binding = [r for r in reqs if r.tf == tf and r.candles == need]
        _feed(analyzer, tf, need - 1)
        assert not all(_ready(analyzer, r) for r in binding), f"{name} {tf}: ready before {need}"
        _feed(analyzer, tf, 1, offset=need - 1)
    for req in reqs:
        assert _ready(analyzer, req), f"{name} {variant}: {req} not ready after {needs[req.tf]}"
    # readiness reads never created anything: the registry is unchanged since pre-registration
    assert _registry_keys(analyzer) == keys_after_prereg


# ---------------------------------------------------------------------------
# 3. Consumed timeframes ⊆ timeframes the engine loads for that strategy
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("name", sorted(STRATEGIES))
def test_consumed_timeframes_are_loaded_by_the_engine(name: str) -> None:
    reqs = indicator_requirements(name, _instantiate(name, {}, MagicMock()))
    consumed = {r.tf for r in reqs}
    if name in GridBacktester.GRID_STRATEGIES:
        loaded = {"5m", "4h", "1d", "1w"}
    else:
        e = BacktestEngine
        loaded = {"5m"}  # trading interval of every campaign
        loaded |= {"1h"} if name in e._NEEDS_1H else set()
        loaded |= {"15m"} if name in e._NEEDS_15M else set()
        loaded |= {"4h"} if name in e._NEEDS_4H else set()
        loaded |= {"1d"} if name in e._NEEDS_1D else set()
        loaded |= {"1w"} if name in e._NEEDS_1W else set()
    assert consumed <= loaded, f"{name}: {consumed - loaded} consumed but never loaded"


# ---------------------------------------------------------------------------
# 4. Value == independent recomputation (same window, same seed conventions)
# ---------------------------------------------------------------------------


def _ema_ref(closes: list[Decimal], period: int) -> Decimal:
    ema = sum(closes[:period]) / Decimal(period)
    k = Decimal(2) / (Decimal(period) + 1)
    for c in closes[period:]:
        ema = c * k + ema * (1 - k)
    return ema


def _atr_ref(candles: list[dict[str, Decimal]], period: int) -> Decimal:
    trs: list[Decimal] = []
    prev_close: Decimal | None = None
    for c in candles:
        tr = (
            c["high"] - c["low"]
            if prev_close is None
            else max(c["high"] - c["low"], abs(c["high"] - prev_close), abs(c["low"] - prev_close))
        )
        trs.append(tr)
        prev_close = c["close"]
    atr = sum(trs[:period]) / Decimal(period)
    for tr in trs[period:]:
        atr = (atr * (period - 1) + tr) / Decimal(period)
    return atr


def _rsi_ref(closes: list[Decimal], period: int) -> Decimal:
    changes = [b - a for a, b in zip(closes, closes[1:], strict=False)]
    gains = [max(x, Decimal(0)) for x in changes]
    losses = [max(-x, Decimal(0)) for x in changes]
    avg_gain = sum(gains[:period]) / Decimal(period)
    avg_loss = sum(losses[:period]) / Decimal(period)
    for g, loss in zip(gains[period:], losses[period:], strict=False):
        avg_gain = (avg_gain * (period - 1) + g) / Decimal(period)
        avg_loss = (avg_loss * (period - 1) + loss) / Decimal(period)
    if avg_loss == 0:
        return Decimal(100)
    return Decimal(100) - Decimal(100) / (1 + avg_gain / avg_loss)


def _close(a: Decimal, b: Decimal, rel: str = "1e-12") -> bool:
    return abs(a - b) <= abs(b) * Decimal(rel)


@pytest.mark.parametrize(
    ("kind", "params"),
    [("ema", (125,)), ("ema", (200,)), ("atr", (21,)), ("rsi", (9,)), ("donchian", (15, 10))],
)
def test_preregistered_value_equals_independent_recomputation(kind: str, params: tuple) -> None:
    analyzer = MultiTimeframeAnalyzer()
    req = IndicatorRequirement(kind, "4h", params)
    preregister_indicators(analyzer, [req])
    n = req.candles + 60
    candles = [_candle(i, "4h") for i in range(n)]
    for c in candles:
        analyzer.update(c, 240)
    closes = [c["close"] for c in candles]
    if kind == "ema":
        assert _close(analyzer.get_ema(params[0], "4h"), _ema_ref(closes, params[0]))
    elif kind == "atr":
        assert _close(analyzer.get_atr(params[0], "4h"), _atr_ref(candles, params[0]))
    elif kind == "rsi":
        assert _close(analyzer.get_rsi(params[0], "4h"), _rsi_ref(closes, params[0]))
    else:
        dc = analyzer.get_donchian("4h", *params)
        assert dc["upper"] == max(c["high"] for c in candles[-params[0] :])
        assert dc["lower"] == min(c["low"] for c in candles[-params[1] :])


# ---------------------------------------------------------------------------
# 5. Candle-sized warmup loader: monotone, bounded, reported — never bridged silently
# ---------------------------------------------------------------------------


def _mk(ts: datetime) -> SimpleNamespace:
    return SimpleNamespace(timestamp=ts)


def _series(start: datetime, count: int, minutes: int, skip: set[int] = frozenset()) -> list:
    return [_mk(start + timedelta(minutes=minutes * i)) for i in range(count) if i not in skip]


async def _load(window_rows: list, before_rows: list, **kw: Any) -> tuple[list, dict, list]:
    calls: list[tuple] = []

    async def load_window(interval: int, s: datetime, e: datetime) -> list:
        calls.append(("window", interval, s, e))
        return [r for r in window_rows if s <= r.timestamp <= e]

    async def load_before(interval: int, before: datetime, limit: int, floor: datetime) -> list:
        calls.append(("before", interval, before, limit, floor))
        rows = [r for r in before_rows if floor <= r.timestamp < before]
        return rows[-limit:]

    candles, report = await load_context_series(load_window, load_before, **kw)
    return candles, report, calls


@pytest.mark.asyncio
async def test_enough_history_is_a_no_op_and_sufficient() -> None:
    start = T0
    window_start = start - timedelta(hours=4 * 90)
    rows = _series(window_start, 90 + 1 + 10, 240)  # 90 before, one at start, 10 after
    candles, report, calls = await _load(
        rows,
        [],
        interval=240,
        window_start=window_start,
        start=start,
        end=start + timedelta(hours=40),
        required=14,
    )
    assert [c[0] for c in calls] == ["window"]  # never extended
    assert report["loaded"] == 91 and report["extended_by"] == 0
    assert report["stale_by_candles"] == 0 and report["largest_gap_candles"] == 0
    assert report["sufficient"] is True
    assert len(candles) == 101


@pytest.mark.asyncio
async def test_short_history_is_extended_backwards_by_count_within_the_floor() -> None:
    start = T0
    window_start = start - timedelta(hours=4 * 5)
    window_rows = _series(window_start, 6, 240)  # 5 before + the one at start
    older = _series(window_start - timedelta(hours=4 * 200), 200, 240)
    candles, report, calls = await _load(
        window_rows,
        older,
        interval=240,
        window_start=window_start,
        start=start,
        end=start,
        required=20,
    )
    before_call = [c for c in calls if c[0] == "before"][0]
    assert before_call[3] == 14  # required - loaded
    assert before_call[4] == window_start - timedelta(minutes=240 * 20 * 3)  # bounded floor
    assert report["loaded"] == 20 and report["extended_by"] == 14
    assert report["sufficient"] is True
    assert candles[0].timestamp < window_start and candles == sorted(
        candles, key=lambda c: c.timestamp
    )


@pytest.mark.asyncio
async def test_hole_before_start_is_stale_and_insufficient_even_when_the_count_is_met() -> None:
    # SOL 2023-04-01 shape: the calendar window is empty. (a) an old block within the bounded
    # floor (required x interval x 3 before the window) is reached, the count is met, but the
    # history stops far before start: stale, insufficient. (b) a block beyond the floor is
    # never reached: nothing loaded, insufficient — a hole is reported, not bridged.
    start = T0
    window_start = start - timedelta(hours=4 * 90)
    within_floor = _series(window_start - timedelta(days=5), 30, 240)
    candles, report, calls = await _load(
        [],
        within_floor,
        interval=240,
        window_start=window_start,
        start=start,
        end=start,
        required=14,
    )
    assert report["loaded"] == 14 and report["extended_by"] == 14
    assert report["stale_by_candles"] > 0  # the history stops well before start
    assert report["sufficient"] is False
    before_call = [c for c in calls if c[0] == "before"][0]
    assert before_call[4] == window_start - timedelta(minutes=240 * 14 * 3)

    beyond_floor = _series(window_start - timedelta(days=200), 30, 240)
    _, report, _ = await _load(
        [],
        beyond_floor,
        interval=240,
        window_start=window_start,
        start=start,
        end=start,
        required=14,
    )
    assert report["loaded"] == 0 and report["stale_by_candles"] is None
    assert report["sufficient"] is False


@pytest.mark.asyncio
async def test_internal_gap_above_tolerance_is_insufficient_one_missing_candle_is_tolerated() -> (
    None
):
    start = T0
    window_start = start - timedelta(hours=4 * 60)
    with_gap = _series(window_start, 61, 240, skip={30, 31, 32})
    _, report, _ = await _load(
        with_gap, [], interval=240, window_start=window_start, start=start, end=start, required=14
    )
    assert report["largest_gap_candles"] == 3 and report["sufficient"] is False
    one_missing = _series(window_start, 61, 240, skip={30})
    _, report, _ = await _load(
        one_missing,
        [],
        interval=240,
        window_start=window_start,
        start=start,
        end=start,
        required=14,
    )
    assert report["largest_gap_candles"] == 1 and report["sufficient"] is True


@pytest.mark.asyncio
async def test_staleness_aligned_start_counts_the_candle_stamped_start_as_expected() -> None:
    """Contract (C2 review, commit 12): candles are stamped at their period end, so the candle
    stamped exactly ``start`` is closed and expected. A history ending on it is not stale; the
    same history without it is stale by exactly one candle (and insufficient); two candles
    short, stale by two. ``loaded`` / ``required`` / the extension floor are untouched."""
    start = T0
    window_start = start - timedelta(hours=4 * 90)
    ending_at_start = _series(window_start, 91, 240)  # 90 before + the one stamped start
    kw: dict[str, Any] = {
        "interval": 240,
        "window_start": window_start,
        "start": start,
        "end": start,
        "required": 14,
    }
    _, report, _ = await _load(ending_at_start, [], **kw)
    assert report["stale_by_candles"] == 0 and report["sufficient"] is True
    assert report["last"] == start.isoformat()

    _, report, calls = await _load(ending_at_start[:-1], [], **kw)
    assert report["stale_by_candles"] == 1  # only the candle stamped start is missing
    assert report["sufficient"] is False
    assert report["loaded"] == 90 and report["extended_by"] == 0
    assert [c[0] for c in calls] == ["window"]  # the count is met: no extension attempted

    _, report, _ = await _load(ending_at_start[:-2], [], **kw)
    assert report["stale_by_candles"] == 2 and report["sufficient"] is False


@pytest.mark.asyncio
async def test_staleness_non_aligned_start_expects_nothing_after_the_last_closed_candle() -> None:
    """A 1d series and a start at 04:48 (the P6 test-segment shape): the last daily candle
    stamped at or before ``start`` closes the history — nothing is missing, not stale; drop
    that candle and exactly one is missing (start - last = 1.2 days -> 1)."""
    start = T0 + timedelta(hours=4, minutes=48)
    window_start = T0 - timedelta(days=250)
    daily = _series(window_start, 251, 1440)  # ..., T0 - 1d, T0 (<= start); nothing at start
    kw: dict[str, Any] = {
        "interval": 1440,
        "window_start": window_start,
        "start": start,
        "end": start,
        "required": 50,
    }
    _, report, _ = await _load(daily, [], **kw)
    assert report["last"] == T0.isoformat()
    assert report["stale_by_candles"] == 0 and report["sufficient"] is True

    _, report, _ = await _load(daily[:-1], [], **kw)
    assert report["last"] == (T0 - timedelta(days=1)).isoformat()
    assert report["stale_by_candles"] == 1 and report["sufficient"] is False


@pytest.mark.asyncio
async def test_no_history_at_all_is_reported_not_invented() -> None:
    _, report, _ = await _load(
        [], [], interval=1440, window_start=T0 - timedelta(days=250), start=T0, end=T0, required=50
    )
    assert report["loaded"] == 0 and report["stale_by_candles"] is None
    assert report["sufficient"] is False


# ---------------------------------------------------------------------------
# 6. Signal engine: the candle stamped `start` is fed once (5m trigger), warmup sized
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_signal_engine_feeds_the_candle_at_start_once_and_reports_warmup() -> None:
    engine = BacktestEngine(
        _settings(),
        MagicMock(),
        fee_model="bybit",
        strategy_name="gemini_scalping_volatilite",
        candle_interval=5,
    )
    start = T0
    end = start + timedelta(minutes=5 * 10)
    rows_5m = {t.timestamp: t for t in _series(start - timedelta(hours=3), 36 + 11, 5)}
    rows_1h = _series(start - timedelta(days=3), 72 + 1, 60)

    async def load(pair: str, interval: int, s: datetime, e: datetime) -> list:  # noqa: ARG001
        src = rows_5m.values() if interval == 5 else rows_1h
        return [r for r in src if s <= r.timestamp <= e]

    async def load_before(pair, interval, before, limit, floor):  # noqa: ANN001, ARG001
        return []

    engine._load_candles_for_interval = load  # type: ignore[method-assign]
    engine._load_candles_before = load_before  # type: ignore[method-assign]
    engine._warmup_needs = warmup_needs(
        indicator_requirements(
            "gemini_scalping_volatilite",
            _instantiate("gemini_scalping_volatilite", {}, MagicMock()),
        )
    )
    trading = [r for r in rows_5m.values() if start <= r.timestamp <= end]
    sequence = await engine._build_replay_sequence(PAIR, start, end, trading)
    at_start = [item for item in sequence if item[0].timestamp == start and item[1] == 5]
    assert len(at_start) == 1 and at_start[0][2] is True  # once, and tradeable
    assert (
        engine.warmup["5m"]["required"]
        == warmup_needs(
            engine._requirements
            or indicator_requirements(
                "gemini_scalping_volatilite",
                _instantiate("gemini_scalping_volatilite", {}, MagicMock()),
            )
        )["5m"]
    )
    assert engine.warmup["1h"]["required"] == 50 and engine.warmup["1h"]["sufficient"] is True


# ---------------------------------------------------------------------------
# 7. Preuve 6: the DCA oversold branch, all conditions forced
# ---------------------------------------------------------------------------


class _DcaAnalyzer:
    def __init__(self, rsi: float, ema200: str, regime_1w: str) -> None:
        self.rsi, self.ema200, self.regime_1w = Decimal(str(rsi)), Decimal(ema200), regime_1w

    def get_rsi(self, period, tf):  # noqa: ANN001, ANN201
        assert (period, tf) == (14, "1d")
        return self.rsi

    def get_ema(self, period, tf):  # noqa: ANN001, ANN201
        assert (period, tf) == (200, "1d")
        return self.ema200

    def get_regime(self, tf):  # noqa: ANN001, ANN201
        return self.regime_1w if tf == "1w" else "bull"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("rsi", "ema200", "regime_1w", "amount", "label"),
    [
        (25, "50000", "bull", 37.5, "oversold_boost"),  # 15 x 2.5
        (25, "50000", "strong_bull", 18.75, "oversold_boost+bull_reduce"),  # 15 x 2.5 x 0.5
        (35, "50000", "bull", 15.0, "base"),  # RSI not oversold
        (25, "40000", "bull", 15.0, "base"),  # price above EMA200
    ],
)
async def test_dca_oversold_boost_when_all_conditions_are_forced(
    rsi: float, ema200: str, regime_1w: str, amount: float, label: str
) -> None:
    strategy = _instantiate("grok_adaptive_dca_weekly", {}, _DcaAnalyzer(rsi, ema200, regime_1w))
    strategy._is_daily = True
    strategy._current_price = Decimal("46000")
    strategy._current_timestamp = datetime(2022, 1, 3, tzinfo=UTC)  # Monday stamp
    signal = await strategy.generate_signal()
    assert signal is not None
    assert signal.metadata["order_size_usdc"] == amount
    assert signal.metadata["multiplier_label"] == label


# ---------------------------------------------------------------------------
# 8. The retroactive constat of the report: what P7 swept vs what was pre-registered
# ---------------------------------------------------------------------------


def test_p7_variants_created_their_indicators_lazily_before_c2() -> None:
    st = p7_grids.expand_grid(p7_grids.SUPERTREND_GRID)
    assert len(st) == 20
    assert sum(1 for v in st if (v["st_atr_period"], v["st_multiplier"]) != (10, 3.0)) == 19
    dc = p7_grids.expand_grid(p7_grids.DONCHIAN_GRID)
    assert len({v["donchian_upper_period"] for v in dc}) == 4
    assert sum(1 for u in {v["donchian_upper_period"] for v in dc} if u != 20) == 3
