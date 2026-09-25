"""``scripts/audit/warmup_at.py`` — couche pure (aucun test ne touche la base).

Brief : ``agent/agent_sol_d2_1w_modes.md``. Les attendus viennent du texte, appui cité : protocole § A.3 (fenêtre,
ancrage), § A.4 (estampille ``start`` close à ``start``), § A.8 (D2, SOL 29 / 2020-08-17 / 2021-07-26, liste de
décision non vide), table B du brief (six classes), lecture de la stratégie (``:131-152``, ``:224-249``). Les
constantes du script sont épinglées **au moteur** (arguments de ``load_context_series``, chargeurs, besoins
d'amorçage) et **au comportement** de la stratégie (sonde sur ``_handle_ohlc``), jamais recopiées de
l'implémentation.

Imports : le module ``backtest`` est celui que le script a importé (``wa.bt``), pour qu'un seul objet module
porte ``GridBacktester`` et les chargeurs remplacés.
"""

# ruff: noqa: E402
from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
import inspect
import json
import os
from pathlib import Path
import re
import subprocess
import sys
from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock

import pytest

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_PROJECT_ROOT))
sys.path.insert(0, str(_PROJECT_ROOT / "src"))
sys.path.insert(0, str(_PROJECT_ROOT / "scripts"))
sys.path.insert(0, str(_PROJECT_ROOT / "scripts" / "audit"))

import c3_common as cc
import warmup_at as wa

from krakenbot.core.event_bus import EventBus
from krakenbot.indicators.multi_timeframe import MarketRegime
from krakenbot.strategies.grok_grid_atr_adaptive_v4 import GrokGridATRAdaptiveV4

PAIR = "SOL/USDT"
UTC0 = datetime(2021, 3, 1, tzinfo=UTC)
#: § A.3 l.237-238.
T_DECLARED = datetime(2024, 11, 22, 4, 48, tzinfo=UTC)
WEEK = timedelta(weeks=1)


def _settings() -> SimpleNamespace:
    """``multi_strategy`` désactivé : le moteur retombe sur les défauts de classe, comme sur la vraie config
    (décision B.2a — les clés YAML ``grid_atr_*`` ne matchent pas le nom de la stratégie)."""
    return SimpleNamespace(
        multi_strategy=SimpleNamespace(enabled=False, strategies=[]),
        trading=SimpleNamespace(pair=PAIR, default_order_amount_eur=50),
    )


def _engine(db: Any = None) -> Any:
    return wa.bt.GridBacktester(
        _settings(),
        MagicMock() if db is None else db,
        fee_model="bybit",
        strategy_name=wa.STRATEGY,
        candle_interval=5,
        exchange="binance",
    )


def _instance(params: dict[str, Any]) -> GrokGridATRAdaptiveV4:
    strategy = GrokGridATRAdaptiveV4(
        settings=_settings(),  # type: ignore[arg-type]
        event_bus=EventBus(),
        db_manager=MagicMock(),
        bot_id="probe",
        strategy_params={"pair": PAIR, **params},
        analyzer=None,
    )
    strategy._skip_db_sync = True
    strategy._running = True
    return strategy


# ---------------------------------------------------------------------------
# Fenêtre, ancrage, besoins d'amorçage — attendus du texte
# ---------------------------------------------------------------------------


def test_window_and_anchor_are_those_of_protocol_a3() -> None:
    """§ A.3 l.237-238 : fenêtre 2021-03-01 → 2026-06-29, ``T = 2024-11-22T04:48Z`` sans arrondi."""
    assert wa.AT == UTC0
    assert wa.WINDOW_END == datetime(2026, 6, 29, tzinfo=UTC)
    assert wa.anchor() == T_DECLARED == wa.ANCHOR_DECLARED


def test_required_at_class_defaults() -> None:
    """Brief l.95-96 (``atr_period = 14``) ; régime 50 bougies (§ A.8 l.603, ``backtest.py:305``) ; le 5 m est
    absent des besoins et mesuré avec 0."""
    strategy = wa.default_strategy(PAIR)
    assert wa.required_by_tf(strategy) == {"5m": 0, "4h": 14, "1d": 50, "1w": 50}
    assert wa.static_tfs(strategy) == ("1d", "1w", "4h")


def test_required_rejects_a_need_outside_the_measured_series(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(wa, "warmup_needs", lambda _reqs: {"4h": 14, "1h": 20})
    with pytest.raises(ValueError, match="1h"):
        wa.required_by_tf(wa.default_strategy(PAIR))


# ---------------------------------------------------------------------------
# Épinglage au moteur — arguments, chargeurs, besoins
# ---------------------------------------------------------------------------


async def test_context_args_are_the_arguments_the_grid_engine_passes() -> None:
    """Le moteur, rejoué avec un enregistreur à la place de ``_load_context_series`` : même ``(tf, interval,
    window_start, start, end)`` pour 4 h / 1 d / 1 w, mêmes besoins que ``required_by_tf``."""
    engine = _engine()
    calls: list[tuple[Any, ...]] = []

    async def recorder(
        pair: str, tf: str, interval: int, ws: datetime, s: datetime, e: datetime
    ) -> list:
        calls.append((tf, interval, ws, s, e))
        return []

    engine._load_context_series = recorder
    await engine._create_grok_grid_strategy()
    await engine._build_grok_grid_replay_sequence(PAIR, wa.AT, T_DECLARED, [])
    plans = [p for p in wa.context_args(wa.AT, T_DECLARED) if p.context]
    assert calls == [(p.tf, p.interval, p.window_start, p.start, p.end) for p in plans]
    required = wa.required_by_tf(wa.default_strategy(PAIR))
    assert engine._warmup_needs == {tf: n for tf, n in required.items() if n > 0}
    assert "5m" not in engine._warmup_needs


async def test_exec_series_is_loaded_on_start_end_outside_the_context_rule(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``_load_candles`` (``backtest.py:3022-3033``, appelé à ``:2880``) charge le 5 m sur ``[start, end]`` :
    ``window_start = start``, hors de ``load_context_series``."""
    calls: list[tuple[Any, ...]] = []

    async def chunked(
        db: Any, pair: str, interval: int, s: datetime, e: datetime, exchange: str = "kraken"
    ) -> list:
        calls.append((interval, s, e, exchange))
        return []

    monkeypatch.setattr(wa.bt, "_load_candles_chunked", chunked)
    await _engine()._load_candles(PAIR, wa.AT, T_DECLARED)
    (plan,) = [p for p in wa.context_args(wa.AT, T_DECLARED) if p.tf == "5m"]
    assert calls == [(plan.interval, plan.window_start, plan.end, "binance")]
    assert plan.start == plan.window_start == wa.AT
    assert plan.context is False


async def test_loaders_are_the_engine_loaders(monkeypatch: pytest.MonkeyPatch) -> None:
    """Mêmes appels que ``GridBacktester._load_candles_for_interval`` / ``_load_candles_before``
    (``backtest.py:3035-3054``), même base, ``exchange='binance'``."""
    calls: list[tuple[Any, ...]] = []

    async def chunked(
        db: Any, pair: str, interval: int, s: datetime, e: datetime, exchange: str = "kraken"
    ) -> list:
        calls.append(("window", db, pair, interval, s, e, exchange))
        return []

    async def before(
        db: Any, pair: str, interval: int, b: datetime, n: int, f: datetime, exchange: str
    ) -> list:
        calls.append(("before", db, pair, interval, b, n, f, exchange))
        return []

    monkeypatch.setattr(wa.bt, "_load_candles_chunked", chunked)
    monkeypatch.setattr(wa.bt, "_load_candles_before", before)
    db = MagicMock()
    s, e, f = UTC0 - timedelta(days=250), T_DECLARED, UTC0 - timedelta(days=400)
    engine = _engine(db)
    await engine._load_candles_for_interval(PAIR, 1440, s, e)
    await engine._load_candles_before(PAIR, 1440, s, 7, f)
    engine_calls = list(calls)
    calls.clear()
    load_window, load_before = wa.engine_loaders(db, PAIR)
    await load_window(1440, s, e)
    await load_before(1440, s, 7, f)
    assert calls == engine_calls
    assert {c[-1] for c in calls} == {"binance"}


# ---------------------------------------------------------------------------
# Table A — épinglée au source
# ---------------------------------------------------------------------------


def test_analyzer_reads_are_every_call_site_of_the_strategy() -> None:
    source = inspect.getsource(GrokGridATRAdaptiveV4)
    found = sorted(
        (call, re.search(r'"(\w+)"', args).group(1))  # type: ignore[union-attr]
        for call, args in re.findall(r"analyzer\.(get_\w+)\(([^)]*)\)", source)
    )
    assert found == sorted((r["call"], r["tf"]) for r in wa.ANALYZER_READS)
    assert {r["tf"] for r in wa.ANALYZER_READS} == set(wa.READ_TFS)


# ---------------------------------------------------------------------------
# Table B — l'oracle du biais, les classes, la sonde comportementale
# ---------------------------------------------------------------------------

BIASES = tuple(
    Decimal(x)
    for x in ("0", "0.05", "0.1", "0.16", "0.17", "0.2", "0.25", "0.3", "0.5", "1", "-0.2")
)


def test_regime_domain_is_every_value_get_regime_can_return() -> None:
    """``multi_timeframe.py:750-777`` : une valeur de ``MarketRegime`` ou None."""
    assert set(wa.REGIME_DOMAIN) == {r.value for r in MarketRegime} | {None}


def test_bias_live_refutes_the_bias_1d_nonzero_axis() -> None:
    """Le fait nouveau (``:224-249``) : ``bias_1d ≠ 0`` n'est ni suffisant (G = 12, b = 0,1 : ``int(0,6) = 0``)
    ni nécessaire (G = 13, b = 0 : le bras bear rend (7, 6) contre (6, 7))."""
    assert wa.bias_live(12, Decimal("0.1")) is False
    assert (
        wa.bias_split(12, Decimal("0.1"), "bull")
        == wa.bias_split(12, Decimal("0.1"), "bear")
        == (6, 6)
    )
    assert wa.bias_live(13, Decimal("0")) is True
    assert wa.bias_split(13, Decimal("0"), "bear") == (7, 6)
    assert (
        wa.bias_split(13, Decimal("0"), "bull") == wa.bias_split(13, Decimal("0"), None) == (6, 7)
    )
    assert wa.bias_live(12, Decimal("0.2")) is True  # défauts de classe (:122, :130)


@pytest.mark.parametrize("grid_levels", range(2, 41))
def test_closed_form_explains_the_oracle_from_two_levels(grid_levels: int) -> None:
    """Explication, pas mesure : pour G ≥ 2, vivant ⟺ ``int(float(b) × (G // 2)) ≠ 0`` ou G impair."""
    for b in BIASES:
        closed = int(float(b) * (grid_levels // 2)) != 0 or grid_levels % 2 == 1
        assert wa.bias_live(grid_levels, b) is closed, (grid_levels, b)


def test_one_level_is_the_edge_the_closed_form_misses() -> None:
    """G = 1 : ``half = 0``, les clamps ``max(1, ·)`` (``:249``) rendent (1, 1) sous tout régime — la forme
    fermée dirait « G impair, vivant »."""
    for b in BIASES:
        assert wa.bias_live(1, b) is False
    assert (int(float(Decimal("0")) * (1 // 2)) != 0 or 1 % 2 == 1) is True


def test_classes_cover_the_reachable_flags_once() -> None:
    """Six classes (brief, table B) ; ``(pause_1w, bear_1d) = (T, T)`` absent ; flags distincts."""
    keys = [(k.pause_1w, k.bear_1d, k.bias_live) for k in wa.CLASSES]
    assert len(keys) == len(set(keys)) == 6
    assert all(not (p and b) for p, b, _ in keys)
    assert [k.name for k in wa.CLASSES] == ["C1", "C2", "C3", "C4", "C5", "C6"]


@pytest.mark.parametrize("pause", [True, False])
@pytest.mark.parametrize("mode", [None, "none", "1w_only", "1d_only"])
def test_pause_1w_and_bear_1d_are_never_both_on(mode: str | None, pause: bool) -> None:
    """Setter ``:137-152`` ; ``bear_protection_1d_enabled`` n'est lu d'aucun paramètre (``:132``)."""
    params: dict[str, Any] = {"pause_1w_strong_bear": pause}
    if mode is not None:
        params["bear_protection_mode"] = mode
    strategy = _instance(params)
    assert not (strategy.pause_1w_strong_bear and strategy.bear_protection_1d_enabled)


def test_invalid_mode_is_refused() -> None:
    with pytest.raises(ValueError, match="bear_protection_mode"):
        _instance({"bear_protection_mode": "both"})


#: Texte de la table B → paramètres qui le réalisent.
MODE_PARAMS: dict[str, dict[str, Any]] = {
    "bear_protection_mode = '1w_only'": {"bear_protection_mode": "1w_only"},
    "bear_protection_mode = None, pause_1w_strong_bear vrai (défaut de classe)": {},
    "bear_protection_mode = '1d_only'": {"bear_protection_mode": "1d_only"},
    "bear_protection_mode = 'none'": {"bear_protection_mode": "none"},
    "bear_protection_mode = None, pause_1w_strong_bear faux": {"pause_1w_strong_bear": False},
}


def test_every_listed_mode_reaches_the_flags_of_its_class() -> None:
    for klass in wa.CLASSES:
        for mode in klass.modes:
            strategy = _instance(MODE_PARAMS[mode])
            flags = (bool(strategy.pause_1w_strong_bear), strategy.bear_protection_1d_enabled)
            assert flags == (klass.pause_1w, klass.bear_1d), (klass.name, mode)


def test_decision_sets_are_never_empty_and_always_carry_4h() -> None:
    """§ A.8 l.521 : une liste vide est une erreur d'entrée ; l'ATR 4 h est une porte dans toute classe
    (``:429-440``) ; écart à la liste statique ``{4h, 1d, 1w}`` (``backtest.py:420-425``)."""
    static = set(wa.static_tfs(wa.default_strategy(PAIR)))
    expected_gap = {
        "C1": set(),
        "C2": {"1d"},
        "C3": {"1w"},
        "C4": {"1w"},
        "C5": {"1w"},
        "C6": {"1d", "1w"},
    }
    for klass in wa.CLASSES:
        assert klass.decision_tfs and "4h" in klass.decision_tfs
        assert list(klass.decision_tfs) == sorted(set(klass.decision_tfs))
        assert static - set(klass.decision_tfs) == expected_gap[klass.name]


class _Analyzer:
    """``get_regime`` / ``get_atr`` aux valeurs imposées ; enregistre les TF lus. Un appel hors table A lève — et
    ``_handle_ohlc`` avalant les exceptions, la sonde exige zéro ``logger.error``."""

    def __init__(self, r1w: str | None, r1d: str | None, atr: Decimal | None) -> None:
        self.values = {"1w": r1w, "1d": r1d}
        self.atr = atr
        self.reads: set[str] = set()

    def get_regime(self, tf: str) -> str | None:
        self.reads.add(tf)
        return self.values[tf]

    def get_atr(self, period: int, tf: str) -> Decimal | None:
        assert tf == "4h"
        self.reads.add(tf)
        return self.atr


ATR_DOMAIN: tuple[Decimal | None, ...] = (None, Decimal("0"), Decimal("0.5"))
T0 = datetime(2024, 1, 1, tzinfo=UTC)


async def _probe(params: dict[str, Any]) -> tuple[set[str], set[str]]:
    """TF lus, TF qui décident : un TF décide s'il existe une combinaison des autres entrées où faire varier sa
    valeur change l'issue ``(_paused, _grid_initialized, niveaux)`` d'une décision 4 h."""
    outcomes: dict[tuple[Any, ...], tuple[Any, ...]] = {}
    reads: set[str] = set()
    for r1w in wa.REGIME_DOMAIN:
        for r1d in wa.REGIME_DOMAIN:
            for atr in ATR_DOMAIN:
                strategy = _instance(params)
                analyzer = _Analyzer(r1w, r1d, atr)
                strategy.analyzer = analyzer
                strategy.logger = MagicMock()
                await strategy._handle_ohlc(
                    {"timeframe": "4h", "close": Decimal("100"), "timestamp": T0}
                )
                assert strategy.logger.error.call_count == 0, strategy.logger.error.call_args
                outcomes[(r1w, r1d, atr)] = (
                    strategy._paused,
                    strategy._grid_initialized,
                    tuple(sorted(strategy._grid_levels)),
                )
                reads |= analyzer.reads
    decisive: set[str] = set()
    for (r1w, r1d, atr), outcome in outcomes.items():
        if any(outcomes[(x, r1d, atr)] != outcome for x in wa.REGIME_DOMAIN):
            decisive.add("1w")
        if any(outcomes[(r1w, x, atr)] != outcome for x in wa.REGIME_DOMAIN):
            decisive.add("1d")
        if any(outcomes[(r1w, r1d, x)] != outcome for x in ATR_DOMAIN):
            decisive.add("4h")
    return reads, decisive


#: (params, classe attendue) — classe dérivée de la table B du brief et de la lecture ``:131-152``, ``:224-249``.
PROBE_CASES: dict[str, tuple[dict[str, Any], str]] = {
    "defaults": ({}, "C1"),
    "1w_only": ({"bear_protection_mode": "1w_only"}, "C1"),
    "1w_only-G13-b0 (G impair, le bras bear décide)": (
        {"bear_protection_mode": "1w_only", "bias_1d": 0, "grid_levels": 13},
        "C1",
    ),
    "1w_only-b0": ({"bear_protection_mode": "1w_only", "bias_1d": 0}, "C2"),
    "defaults-b0.1 (int(0.6) = 0)": ({"bias_1d": 0.1}, "C2"),
    "pause 'false' en chaîne (:131 ne coerce pas, dette C3b)": (
        {"pause_1w_strong_bear": "false", "bias_1d": 0},
        "C2",
    ),
    "1d_only": ({"bear_protection_mode": "1d_only"}, "C3"),
    "1d_only-b0": ({"bear_protection_mode": "1d_only", "bias_1d": 0}, "C4"),
    "none": ({"bear_protection_mode": "none"}, "C5"),
    "pause False": ({"pause_1w_strong_bear": False}, "C5"),
    "none-b0": ({"bear_protection_mode": "none", "bias_1d": 0}, "C6"),
    "none-b0.16 (int(0.96) = 0)": ({"bear_protection_mode": "none", "bias_1d": 0.16}, "C6"),
    "none-G1-b0 (clamps)": ({"bear_protection_mode": "none", "bias_1d": 0, "grid_levels": 1}, "C6"),
}


@pytest.mark.parametrize("case", sorted(PROBE_CASES))
async def test_table_b_is_the_behaviour_of_the_strategy(case: str) -> None:
    params, expected = PROBE_CASES[case]
    klass = wa.class_of(_instance(params))
    assert klass.name == expected
    reads, decisive = await _probe(params)
    assert reads == set(wa.READ_TFS)
    assert decisive == set(klass.decision_tfs)


# ---------------------------------------------------------------------------
# Historique, disponibilité, rows dérivées
# ---------------------------------------------------------------------------


def test_history_includes_the_candle_stamped_start() -> None:
    """§ A.4 l.287-289 : la bougie estampillée ``t`` est close à ``t`` et appartient au passé de ``t``."""
    stamps = [UTC0 - WEEK, UTC0, UTC0 + WEEK]
    assert wa.history_stamps(stamps, UTC0) == [UTC0 - WEEK, UTC0]


def _sol_weekly(count: int) -> list[datetime]:
    first = datetime(2020, 8, 17, tzinfo=UTC)
    return [first + k * WEEK for k in range(count)]


def test_ready_at_is_the_fiftieth_weekly_stamp_on_sol() -> None:
    """§ A.8 l.603-604 : 29 bougies au 2021-03-01, première le 2020-08-17, la 50ᵉ tombe le 2021-07-26."""
    stamps = _sol_weekly(120)
    assert len(wa.history_stamps(stamps, UTC0)) == 29
    assert wa.ready_at(stamps, 50) == datetime(2021, 7, 26, tzinfo=UTC)
    assert wa.ready_at(stamps, 0) is None
    assert wa.ready_at(stamps[:49], 50) is None


def test_derived_rows_are_matched_on_pair_interval_and_stamp() -> None:
    # Chaque témoin porte sa propre estampille, présente dans l'historique hebdomadaire : seul le filtre
    # (paire, intervalle) peut l'écarter — une estampille partagée serait absorbée par l'ensemble.
    derived = [
        ("SOL/USDT", 10080, datetime(2022, 6, 6, tzinfo=UTC)),
        ("SOL/USDT", 10080, UTC0 - WEEK),  # témoin adverse : une row dérivée dans l'historique
        ("BTC/USDT", 10080, UTC0 - 2 * WEEK),
        ("SOL/USDT", 1440, UTC0 - 3 * WEEK),
    ]
    history = wa.history_stamps(_sol_weekly(120), UTC0)
    assert wa.derived_in_history(derived, "SOL/USDT", 10080, history) == [UTC0 - WEEK]
    assert wa.derived_in_history(derived[:1], "SOL/USDT", 10080, history) == []


# ---------------------------------------------------------------------------
# D2 — cellule, table C, résumé
# ---------------------------------------------------------------------------


def _report(
    required: int, loaded: int, *, interval: int, stale: int = 0, gap: int = 0
) -> dict[str, Any]:
    return {
        "interval": interval,
        "required": required,
        "loaded": loaded,
        "extended_by": 0,
        "stale_by_candles": stale,
        "largest_gap_candles": gap,
        "sufficient": loaded >= required and stale == 0 and gap <= 1,
        "first": None,
        "last": None,
    }


SOL_LIKE = {
    "5m": _report(0, 1, interval=5),
    "4h": _report(14, 91, interval=240),
    "1d": _report(50, 202, interval=1440),
    "1w": _report(50, 29, interval=10080),
}
BTC_LIKE = {**SOL_LIKE, "1w": _report(50, 58, interval=10080)}


def test_d2_reads_only_the_decision_timeframes() -> None:
    """§ A.8 l.452 : ``sufficient`` sur chaque TF **de décision** — le 1 w insuffisant ne retire pas C6."""
    assert wa.d2_cell(SOL_LIKE, ("4h",), where="t")["status"] == "pass"
    assert wa.d2_cell(SOL_LIKE, ("1d", "4h"), where="t")["status"] == "pass"
    cell = wa.d2_cell(SOL_LIKE, ("1w", "4h"), where="t")
    assert cell["status"] == "fail"
    assert cell["label"] == "fail(1w: 29/50)"


def test_d2_label_names_stale_and_gap_when_the_count_is_met() -> None:
    """§ A.8 l.503 : ``1 d loaded 88, largest_gap_candles 163, sufficient False``."""
    series = {
        "1d": _report(50, 88, interval=1440, gap=163),
        "4h": _report(14, 91, interval=240, stale=1),
    }
    assert (
        wa.d2_cell(series, ("1d", "4h"), where="t")["label"]
        == "fail(1d: 88/50, gap 163; 4h: 91/14, stale 1)"
    )


def test_d2_refuses_a_declared_sufficient_the_rule_contradicts() -> None:
    series = {"1w": {**_report(50, 29, interval=10080), "sufficient": True}}
    with pytest.raises(ValueError, match="recalculé"):
        wa.d2_cell(series, ("1w",), where="t")


def test_d2_refuses_an_unmeasured_decision_timeframe() -> None:
    with pytest.raises(KeyError, match="1h"):
        wa.d2_cell(SOL_LIKE, ("1h",), where="t")


def test_d2_table_and_summary_by_class_and_pair() -> None:
    table = wa.d2_table({"BTC/USDT": BTC_LIKE, "SOL/USDT": SOL_LIKE})
    summary = wa.d2_summary(table)
    assert summary["BTC/USDT"] == {
        "pass": ["C1", "C2", "C3", "C4", "C5", "C6"],
        "fail": [],
        "survivors_empty": False,
    }
    assert summary["SOL/USDT"] == {
        "pass": ["C3", "C4", "C5", "C6"],
        "fail": ["C1", "C2"],
        "survivors_empty": False,
    }
    only_1w = [wa.DecisionClass("X", True, False, False, (), ("1w", "4h"))]
    assert (
        wa.d2_summary(wa.d2_table({"SOL/USDT": SOL_LIKE}, only_1w))["SOL/USDT"]["survivors_empty"]
        is True
    )


# ---------------------------------------------------------------------------
# Entrées de série, contrôles, payload
# ---------------------------------------------------------------------------


def _measured(report: dict[str, Any], stamps: list[datetime]) -> dict[str, Any]:
    return {
        "report": report,
        "history": wa.history_stamps(stamps, UTC0),
        "head": stamps[: report["required"]],
    }


def _sol_1w_report(loaded: int = 29, first: datetime | None = None) -> dict[str, Any]:
    return {
        **_report(50, loaded, interval=10080),
        "first": (first or datetime(2020, 8, 17, tzinfo=UTC)).isoformat(),
    }


def test_series_entry_carries_ready_at_short_by_and_the_chain_recomputation() -> None:
    entry = wa.series_entry(
        _measured(_sol_1w_report(), _sol_weekly(120)),
        pair="SOL/USDT",
        tf="1w",
        required_tfs=("4h", "1d", "1w"),
        derived=[("SOL/USDT", 10080, datetime(2022, 6, 6, tzinfo=UTC))],
    )
    assert entry["ready_at"] == "2021-07-26T00:00:00+00:00"
    assert entry["short_by"] == 21
    assert entry["sufficient"] is entry["sufficient_recomputed_by_chain"] is False
    assert entry["in_requirements"] is True
    assert entry["derived_rows_in_history"] == []
    for key in (
        "interval",
        "required",
        "loaded",
        "extended_by",
        "stale_by_candles",
        "largest_gap_candles",
        "sufficient",
        "first",
        "last",
    ):
        assert key in entry  # brief § Étape 3, sortie


def _series_for_controls(sol_1w: dict[str, Any], hits: list[str] | None = None) -> dict[str, Any]:
    return {"SOL/USDT": {"1w": {**sol_1w, "derived_rows_in_history": hits or []}}}


@pytest.mark.parametrize(
    ("variant", "failing"),
    [
        ("sain", None),
        ("sol 30 bougies", "sol_1w_at_start"),
        ("sol première 2020-08-10", "sol_1w_at_start"),
        ("row dérivée dans l'amorçage", "derived_rows_in_warmup"),
        ("compte binance", "db_row_count_binance"),
        ("alembic change", "alembic_unchanged"),
        ("alembic autre tête", "alembic_unchanged"),
    ],
)
def test_controls(variant: str, failing: str | None) -> None:
    sol = _sol_1w_report()
    hits: list[str] = []
    rows, before, after = 11_952_996, ["c3bd1e7a0001"], ["c3bd1e7a0001"]
    if variant == "sol 30 bougies":
        sol = _sol_1w_report(loaded=30)
    elif variant == "sol première 2020-08-10":
        sol = _sol_1w_report(first=datetime(2020, 8, 10, tzinfo=UTC))
    elif variant == "row dérivée dans l'amorçage":
        hits = ["2021-02-22T00:00:00+00:00"]
    elif variant == "compte binance":
        rows = 11_952_972
    elif variant == "alembic change":
        after = ["c1ae7a1c0001"]
    elif variant == "alembic autre tête":
        before = after = ["c1ae7a1c0001"]
    controls = wa.evaluate_controls(
        _series_for_controls(sol, hits), row_count=rows, alembic_before=before, alembic_after=after
    )
    assert [name for name, c in controls.items() if not c["ok"]] == (
        [] if failing is None else [failing]
    )


def _collected() -> dict[str, Any]:
    per_pair: dict[str, dict[str, Any]] = {}
    for pair, reports in (("BTC/USDT", BTC_LIKE), ("ETH/USDT", BTC_LIKE), ("SOL/USDT", SOL_LIKE)):
        per_pair[pair] = {}
        for tf, report in reports.items():
            if pair == "SOL/USDT" and tf == "1w":
                report = _sol_1w_report()
                stamps = _sol_weekly(120)
            else:
                step = timedelta(minutes=report["interval"])
                stamps = [UTC0 - k * step for k in range(report["loaded"] - 1, -1, -1)]
            per_pair[pair][tf] = _measured(dict(report), stamps)
    return {
        "read_only": "on",
        "alembic_before": ["c3bd1e7a0001"],
        "alembic_after": ["c3bd1e7a0001"],
        "row_count": 11_952_996,
        "derived": [("SOL/USDT", 10080, datetime(2022, 6, 6, tzinfo=UTC))],
        "series": per_pair,
    }


def test_payload_is_native_json_and_carries_what_the_report_reads() -> None:
    """Écrivain strict (dette 22) : aucun ``default`` — un ``datetime`` oublié lèverait."""
    payload = wa.build_payload(
        _collected(),
        plans=wa.context_args(wa.AT, T_DECLARED),
        strategy=wa.default_strategy(PAIR),
        provenance={"git_sha": "0" * 40},
        database={"host": "localhost", "port": 5432, "database": "krakenbot"},
        generated_at=datetime(2026, 9, 25, tzinfo=UTC),
        argv=["warmup_at.py"],
    )
    json.dumps(payload, allow_nan=False)
    assert payload["controls_ok"] is True
    assert payload["strategy"]["class"] == "C1"
    assert payload["window"]["anchor"] == T_DECLARED.isoformat()
    assert [a["tf"] for a in payload["engine_args"]] == ["5m", "4h", "1d", "1w"]
    assert payload["d2"]["C2"]["SOL/USDT"]["label"] == "fail(1w: 29/50)"
    assert payload["d2_summary"]["SOL/USDT"]["pass"] == ["C3", "C4", "C5", "C6"]
    assert (
        payload["decision_shape"]["empty_classes"]
        == payload["decision_shape"]["classes_without_4h"]
        == []
    )
    assert payload["series"]["SOL/USDT"]["5m"]["in_requirements"] is False
    with pytest.raises(TypeError):
        json.dumps({**payload, "oops": datetime(2021, 3, 1, tzinfo=UTC)})


def test_import_does_not_mutate_environ() -> None:
    """Règle B4.2 : ``.env`` chargé dans ``main``, jamais à l'import."""
    probe = (
        "import importlib, json, os, sys\n"
        "root = sys.argv[1]\n"
        "sys.path[:0] = [root + '/scripts/audit', root + '/scripts', root + '/src', root]\n"
        "before = dict(os.environ)\n"
        "importlib.import_module('warmup_at')\n"
        "print(json.dumps(sorted(k for k in os.environ if before.get(k) != os.environ[k])))\n"
    )
    env = {k: v for k, v in os.environ.items() if k != "DATABASE_URL"}
    proc = subprocess.run(
        [sys.executable, "-c", probe, str(_PROJECT_ROOT)],
        cwd=_PROJECT_ROOT,
        capture_output=True,
        text=True,
        check=False,
        timeout=120,
        env=env,
    )
    assert proc.returncode == 0, proc.stderr[-2000:]
    assert json.loads(proc.stdout.strip().splitlines()[-1]) == []


def test_chain_gap_tolerance_is_the_engine_one() -> None:
    """Le libellé ``gap`` suit la tolérance de la chaîne, elle-même celle du moteur (``backtest.py:309``)."""
    assert cc.WARMUP_GAP_TOLERANCE == wa.bt._WARMUP_GAP_TOLERANCE == 1
