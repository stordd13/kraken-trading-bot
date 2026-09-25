"""Amorçage C2 du moteur grid mesuré au début du préfixe, en lecture seule — mesure SOL/D2 par classes.

Brief : ``agent/agent_sol_d2_1w_modes.md``. Protocole : ``docs/protocole_c3.md`` v2.1 § A.8 (D2 : ``sufficient``
sur **chaque timeframe qui alimente une porte de décision**, portée candidat ; liste dérivée, jamais déclarée) et
§ I.1 lignes 4-5 (promotion). Rapport : ``results/sol_d2_1w_modes/report.md``.

Ce que le script mesure
-----------------------
Au début du préfixe de la première campagne (``AT = 2021-03-01T00:00Z``, § A.3), sur ``BTC/USDT``, ``ETH/USDT`` et
``SOL/USDT`` (``exchange='binance'``), l'amorçage que le moteur grid donne à ``grok_grid_atr_adaptive_v4`` sur ses
séries ``5m``, ``4h``, ``1d``, ``1w`` — **par la règle C2 réelle** : ``load_context_series`` et ``warmup_needs``
importés de ``scripts/backtest.py`` sans modification, appelés avec **exactement** les arguments du moteur :

- chargeurs : ceux de ``GridBacktester`` (``backtest.py:3035-3054``) — ``_load_candles_chunked`` et
  ``_load_candles_before``, ``exchange='binance'`` (``engine_loaders``) ;
- ``window_start`` : ``start − 15 j`` (4 h), ``− 250 j`` (1 d), ``− 400 j`` (1 w) (``backtest.py:2424-2426``,
  ``GRID_CONTEXT_WINDOWS``) ; ``end = T``, recalculé par ``cc.anchor_of`` depuis les bornes du § A.3 et comparé
  à l'ancrage déclaré, jamais passé en paramètre ;
- ``required`` : ``warmup_needs(indicator_requirements(...))`` sur une instance réelle de la stratégie aux défauts
  de classe — le moteur tourne aux défauts de classe (décision B.2a : les clés YAML ``grid_atr_*`` ne matchent
  pas le nom de la stratégie) ; 4 h = ``atr_period`` = 14, 1 d = 1 w = 50 (régime, ``backtest.py:305``).

Le 5 m n'est **pas** une série de contexte du moteur grid : il est chargé sur ``[start, end]`` par ``_load_candles``
(``backtest.py:2880`` → ``:3022-3033``) et n'a aucune clé dans les besoins d'amorçage. Il est mesuré par la même
fonction avec ``window_start = start`` et ``required = 0`` : D1 le couvre, D2 non.

Tables du rapport. ``ANALYZER_READS`` (table A) et ``CLASSES`` (table B) sont recopiées de la lecture de
``src/krakenbot/strategies/grok_grid_atr_adaptive_v4.py`` et **épinglées au comportement** de la stratégie par les
tests (sonde sur ``_handle_ohlc``). ``class_of`` classe une instance par ses **flags effectifs** et par
**l'oracle** ``bias_live`` — la méthode réelle ``_get_directional_bias`` exécutée sur tout le domaine de
``get_regime`` —, jamais par une forme fermée : ``int(float(bias_1d) × (grid_levels // 2))`` passe par ``float``
et les clamps ``max(1, ·)`` font exception à ``grid_levels = 1``. Ce script n'est pas la méthode de classe
``decision_timeframes`` de C3b : il mesure ce qu'elle devra rendre.

Contrôles, constantes sourcées : SOL 1 w ``loaded == 29`` et ``first == 2020-08-17`` (§ A.8 l.603-604) ; aucune
row de ``ohlc_derived`` dans un historique d'amorçage (les 8 estampilles reconstruites sont postérieures à ``AT``) ;
``count(*)`` binance = 11 952 996 ; ``alembic_version`` = ``c3bd1e7a0001``, identique avant et après.

Conventions : lecture seule **garantie par Postgres** (``default_transaction_read_only = on`` posé à la connexion,
``transaction_read_only`` asserté ``on``) ; ``DATABASE_URL`` lue après ``load_dotenv`` dans ``main``, jamais
``Settings()`` (piège 5432) ni à l'import ; le tree suivi doit être propre et le script committé, pour que le git
sha de l'en-tête soit réel (``--allow-uncommitted`` : développement seulement, en-tête marqué provisoire) ; JSON
écrit sans ``default=str`` (``reconstruct_1w.write_json_strict``, dette 22).

Usage::

    poetry run python scripts/audit/warmup_at.py --output results/sol_d2_1w_modes/warmup_2021-03-01.json

Codes de sortie : 0 mesure écrite, contrôles verts ; 3 mesure écrite, au moins un contrôle en échec (le bloc
``controls`` le dit — s'arrêter et rapporter) ; 2 usage, ancrage recalculé différent, tree non propre,
``DATABASE_URL`` absente, base injoignable ou lecture seule non assertée — rien n'est écrit.
"""

from __future__ import annotations

import argparse
import asyncio
from collections.abc import Awaitable, Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal
import hashlib
import os
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace
from typing import Any, cast

_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(_ROOT / "src"))
sys.path.insert(0, str(_ROOT / "scripts"))
sys.path.insert(0, str(_ROOT / "scripts" / "audit"))

import backtest as bt  # noqa: E402
from backtest import indicator_requirements, load_context_series, warmup_needs  # noqa: E402
import c3_common as cc  # noqa: E402
from dotenv import load_dotenv  # noqa: E402
from reconstruct_1w import write_json_strict  # noqa: E402
from sqlalchemy import func, select, text  # noqa: E402
from sqlalchemy.engine import make_url  # noqa: E402
from sqlalchemy.ext.asyncio import (  # noqa: E402
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
import structlog  # noqa: E402

from krakenbot.core.database import DatabaseManager  # noqa: E402
from krakenbot.core.event_bus import EventBus  # noqa: E402
from krakenbot.indicators.multi_timeframe import TF_TO_INTERVAL, MarketRegime  # noqa: E402
from krakenbot.models.market_data import OHLCData, OHLCDerived  # noqa: E402
from krakenbot.strategies.grok_grid_atr_adaptive_v4 import GrokGridATRAdaptiveV4  # noqa: E402

logger = structlog.get_logger()

PROJECT_ROOT = _ROOT
SCRIPT_RELPATH = "scripts/audit/warmup_at.py"
SCHEMA = "warmup_at/1"

STRATEGY = "grok_grid_atr_adaptive_v4"
EXCHANGE = "binance"
PAIRS: tuple[str, ...] = ("BTC/USDT", "ETH/USDT", "SOL/USDT")
#: Fenêtre de la première campagne (§ A.3 l.237) ; l'amorçage se mesure à son début, début du préfixe.
AT = datetime(2021, 3, 1, tzinfo=UTC)
WINDOW_END = datetime(2026, 6, 29, tzinfo=UTC)
#: § A.3 l.238 — l'ancrage est recalculé par ``cc.anchor_of`` et comparé, jamais lu.
ANCHOR_DECLARED = datetime(2024, 11, 22, 4, 48, tzinfo=UTC)
#: Série d'exécution de toute campagne (``candle_interval = 5``), puis séries de contexte du moteur grid.
EXEC_TF = "5m"
SERIES: tuple[str, ...] = ("5m", "4h", "1d", "1w")
#: ``window_start = start − Δ`` du moteur grid, ``scripts/backtest.py:2424-2426`` (épinglé par test).
GRID_CONTEXT_WINDOWS: dict[str, timedelta] = {
    "4h": timedelta(days=15),
    "1d": timedelta(days=250),
    "1w": timedelta(days=400),
}
#: Domaine de retour de ``get_regime`` (``multi_timeframe.py:750-777``) : une valeur de ``MarketRegime`` ou None.
REGIME_DOMAIN: tuple[str | None, ...] = (*(regime.value for regime in MarketRegime), None)

#: Contrôles — constantes sourcées.
EXPECTED_SOL_1W_LOADED = 29  # docs/protocole_c3.md § A.8 l.603-604
EXPECTED_SOL_1W_FIRST = datetime(2020, 8, 17, tzinfo=UTC)  # idem
#: results/reconstruction_1w_2022_2025/evidence/independent_counts.txt:1
EXPECTED_BINANCE_ROWS = 11_952_996
#: Migration ohlc_derived (RESEARCH_LOG entrée 13) ; brief § Validation.
EXPECTED_ALEMBIC = "c3bd1e7a0001"

#: Table A — les appels ``self.analyzer.get_*`` de la stratégie, tous dans ``_handle_ohlc`` sur bougie 4 h.
#: Les lignes sont citées au rapport ; la liste (appel, TF) est épinglée au source par test.
ANALYZER_READS: tuple[dict[str, str], ...] = (
    {
        "call": "get_regime",
        "tf": "1w",
        "runs": "chaque décision 4 h",
        "feeds": "porte de pause 1 w si pause_1w_strong_bear, sinon logs seulement",
    },
    {
        "call": "get_regime",
        "tf": "1d",
        "runs": "si bear_protection_1d_enabled",
        "feeds": "porte de pause 1 d",
    },
    {
        "call": "get_atr",
        "tf": "4h",
        "runs": "hors pause",
        "feeds": "porte HOLD (None ou <= 0) et espacement",
    },
    {
        "call": "get_regime",
        "tf": "1d",
        "runs": "hors pause, ATR disponible",
        "feeds": "biais directionnel si bias_live, sinon logs seulement",
    },
)
#: TF lus par toute classe : ``get_regime("1w")`` à chaque décision, ``get_atr(·, "4h")`` et
#: ``get_regime("1d")`` hors pause.
READ_TFS: tuple[str, ...] = ("1d", "1w", "4h")


@dataclass(frozen=True)
class DecisionClass:
    """Classe d'équivalence de ``decision_timeframes`` (table B) — axes : flags effectifs, jamais le mode."""

    name: str
    pause_1w: bool
    bear_1d: bool
    bias_live: bool
    modes: tuple[str, ...]
    decision_tfs: tuple[str, ...]


MODES_1W: tuple[str, ...] = (
    "bear_protection_mode = '1w_only'",
    "bear_protection_mode = None, pause_1w_strong_bear vrai (défaut de classe)",
)
MODES_1D: tuple[str, ...] = ("bear_protection_mode = '1d_only'",)
MODES_NONE: tuple[str, ...] = (
    "bear_protection_mode = 'none'",
    "bear_protection_mode = None, pause_1w_strong_bear faux",
)
#: Table B. ``(pause_1w, bear_1d) = (True, True)`` est inatteignable : le setter (``:137-152``) ne pose jamais les
#: deux, et ``bear_protection_1d_enabled`` n'est lu d'aucun paramètre (``:132``).
CLASSES: tuple[DecisionClass, ...] = (
    DecisionClass("C1", True, False, True, MODES_1W, ("1d", "1w", "4h")),
    DecisionClass("C2", True, False, False, MODES_1W, ("1w", "4h")),
    DecisionClass("C3", False, True, True, MODES_1D, ("1d", "4h")),
    DecisionClass("C4", False, True, False, MODES_1D, ("1d", "4h")),
    DecisionClass("C5", False, False, True, MODES_NONE, ("1d", "4h")),
    DecisionClass("C6", False, False, False, MODES_NONE, ("4h",)),
)

LoadWindow = Callable[[int, datetime, datetime], Awaitable[list[OHLCData]]]
LoadBefore = Callable[[int, datetime, int, datetime], Awaitable[list[OHLCData]]]


# ---------------------------------------------------------------------------
# Couche pure — arguments du moteur, classes, D2, contrôles
# ---------------------------------------------------------------------------


def _iso(stamp: datetime | None) -> str | None:
    return None if stamp is None else stamp.isoformat()


def anchor() -> datetime:
    """``T`` recalculé depuis les bornes du § A.3 (``cc.anchor_of``), sans arrondi."""
    return cc.anchor_of(AT, WINDOW_END)


@dataclass(frozen=True)
class SeriesPlan:
    """Les arguments d'un appel ``load_context_series``, tels que le moteur grid les passerait."""

    tf: str
    interval: int
    window_start: datetime
    start: datetime
    end: datetime
    context: bool  # série de contexte du moteur (True) ; série d'exécution chargée sur [start, end] (False)


def context_args(start: datetime, end: datetime) -> tuple[SeriesPlan, ...]:
    """5 m sur ``[start, end]`` (``backtest.py:2880``), puis 4 h / 1 d / 1 w (``backtest.py:2424-2436``)."""
    plans = [SeriesPlan(EXEC_TF, TF_TO_INTERVAL[EXEC_TF], start, start, end, context=False)]
    plans += [
        SeriesPlan(tf, TF_TO_INTERVAL[tf], start - back, start, end, context=True)
        for tf, back in GRID_CONTEXT_WINDOWS.items()
    ]
    return tuple(plans)


def default_strategy(pair: str) -> GrokGridATRAdaptiveV4:
    """Instance réelle aux défauts de classe ; ``settings`` porte les seuls attributs que ``__init__`` lit.

    Si ``__init__`` lit un jour un attribut de plus, l'instanciation lève ``AttributeError`` et les tests tombent :
    c'est voulu.
    """
    # default_order_amount_eur n'est passé que parce que __init__ le lit (``_position_size_multiplier``,
    # dimensionnement des ordres) : il n'entre ni dans les besoins d'amorçage ni dans aucune classe, la valeur ne
    # pèse pas sur la mesure.
    settings = SimpleNamespace(
        trading=SimpleNamespace(pair=pair, default_order_amount_eur=Decimal("1"))
    )
    return GrokGridATRAdaptiveV4(
        settings=cast(Any, settings),
        event_bus=EventBus(),
        db_manager=cast(Any, None),
        bot_id=STRATEGY,
        strategy_params={"pair": pair},
        analyzer=None,
    )


def static_tfs(strategy: Any) -> tuple[str, ...]:
    """TF que ``indicator_requirements`` déclare pour la stratégie (``backtest.py:420-425``) — liste statique."""
    return tuple(sorted({req.tf for req in indicator_requirements(STRATEGY, strategy)}))


def required_by_tf(strategy: Any) -> dict[str, int]:
    """``warmup_needs(indicator_requirements(...))`` par série mesurée ; 0 pour une série absente des besoins."""
    needs = warmup_needs(indicator_requirements(STRATEGY, strategy))
    unknown = sorted(set(needs) - set(SERIES))
    if unknown:
        raise ValueError(f"besoins d'amorçage hors des séries mesurées : {unknown}")
    return {tf: needs.get(tf, 0) for tf in SERIES}


def engine_loaders(db: DatabaseManager, pair: str) -> tuple[LoadWindow, LoadBefore]:
    """Les deux chargeurs de ``GridBacktester`` (``backtest.py:3035-3054``), ``exchange='binance'``."""

    async def load_window(interval: int, start: datetime, end: datetime) -> list[OHLCData]:
        return await bt._load_candles_chunked(db, pair, interval, start, end, exchange=EXCHANGE)

    async def load_before(
        interval: int, before: datetime, limit: int, floor: datetime
    ) -> list[OHLCData]:
        return await bt._load_candles_before(db, pair, interval, before, limit, floor, EXCHANGE)

    return load_window, load_before


def bias_split(grid_levels: int, bias_1d: Decimal, regime: str | None) -> tuple[int, int]:
    """``(n_buy, n_sell)`` par la méthode réelle ``_get_directional_bias`` (``:224-249``), appelée non liée sur
    les deux attributs qu'elle lit."""
    probe = SimpleNamespace(grid_levels=grid_levels, bias_1d=bias_1d)
    return GrokGridATRAdaptiveV4._get_directional_bias(cast(GrokGridATRAdaptiveV4, probe), regime)


def bias_live(grid_levels: int, bias_1d: Decimal) -> bool:
    """L'oracle : ``regime_1d`` décide du partage si et seulement si la méthode n'est pas constante sur le domaine
    de ``get_regime``. Jamais la forme fermée (``float``, clamps)."""
    return len({bias_split(grid_levels, bias_1d, regime) for regime in REGIME_DOMAIN}) > 1


def class_of(strategy: GrokGridATRAdaptiveV4) -> DecisionClass:
    """Classe d'une instance : flags effectifs lus comme la stratégie les lit (vérité Python à ``:384`` et
    ``:404``), biais par l'oracle."""
    key = (
        bool(strategy.pause_1w_strong_bear),
        bool(strategy.bear_protection_1d_enabled),
        bias_live(strategy.grid_levels, strategy.bias_1d),
    )
    for klass in CLASSES:
        if (klass.pause_1w, klass.bear_1d, klass.bias_live) == key:
            return klass
    raise ValueError(f"flags effectifs hors des classes atteignables : {key}")


def history_stamps(stamps: Sequence[datetime], start: datetime) -> list[datetime]:
    """Estampilles ``<= start`` : la bougie estampillée ``start`` est close à ``start`` (B4.1, § A.4 ;
    ``backtest.py:502``)."""
    return [stamp for stamp in stamps if stamp <= start]


def ready_at(stamps: Sequence[datetime], required: int) -> datetime | None:
    """Estampille de la ``required``-ième bougie chargée — l'instant où l'indicateur devient prêt. None : sans
    objet (``required == 0``) ou jamais atteint sur la série chargée."""
    if required <= 0 or len(stamps) < required:
        return None
    return stamps[required - 1]


def derived_in_history(
    derived: Iterable[tuple[str, int, datetime]],
    pair: str,
    interval: int,
    history: Iterable[datetime],
) -> list[datetime]:
    """Rows de ``ohlc_derived`` (même paire, même intervalle) dont l'estampille est dans l'historique d'amorçage."""
    keys = {stamp for p, i, stamp in derived if p == pair and i == interval}
    return sorted(keys.intersection(history))


def _recomputed_sufficient(entry: Mapping[str, Any], *, where: str) -> bool:
    """``sufficient`` recalculé par la règle de la chaîne (``cc.warmup_sufficient``) et recoupé au déclaré."""
    recomputed, declared = cc.warmup_sufficient(entry, where=where)
    if recomputed != declared:
        raise ValueError(f"{where}: sufficient déclaré {declared!r}, recalculé {recomputed!r}")
    return recomputed


def series_entry(
    measured: Mapping[str, Any],
    *,
    pair: str,
    tf: str,
    required_tfs: Iterable[str],
    derived: Sequence[tuple[str, int, datetime]],
) -> dict[str, Any]:
    """Le rapport de ``load_context_series`` tel quel, plus ce que D2 et le rapport lisent."""
    report = dict(measured["report"])
    sufficient = _recomputed_sufficient(report, where=f"series.{pair}.{tf}")
    hits = derived_in_history(derived, pair, report["interval"], measured["history"])
    return {
        **report,
        "sufficient_recomputed_by_chain": sufficient,
        "in_requirements": tf in set(required_tfs),
        "ready_at": _iso(ready_at(measured["head"], report["required"])),
        "short_by": max(0, report["required"] - report["loaded"]),
        "derived_rows_in_history": [stamp.isoformat() for stamp in hits],
    }


def _failure_label(failure: Mapping[str, Any]) -> str:
    label = f"{failure['tf']}: {failure['loaded']}/{failure['required']}"
    if failure["stale_by_candles"] != 0:
        label += f", stale {failure['stale_by_candles']}"
    if failure["largest_gap_candles"] > cc.WARMUP_GAP_TOLERANCE:
        label += f", gap {failure['largest_gap_candles']}"
    return label


def d2_cell(
    series: Mapping[str, Mapping[str, Any]], decision_tfs: Sequence[str], *, where: str
) -> dict[str, Any]:
    """D2 d'une classe sur une paire : ``AND(sufficient[tf] for tf in decision_tfs)`` (§ A.8 l.452)."""
    failing: list[dict[str, Any]] = []
    for tf in decision_tfs:
        if tf not in series:
            raise KeyError(f"{where}: timeframe de décision {tf!r} non mesuré")
        entry = series[tf]
        if not _recomputed_sufficient(entry, where=f"{where}.{tf}"):
            failing.append(
                {
                    "tf": tf,
                    "loaded": entry["loaded"],
                    "required": entry["required"],
                    "stale_by_candles": entry["stale_by_candles"],
                    "largest_gap_candles": entry["largest_gap_candles"],
                }
            )
    if not failing:
        return {"status": "pass", "label": "pass", "failing": []}
    label = "fail(" + "; ".join(_failure_label(f) for f in failing) + ")"
    return {"status": "fail", "label": label, "failing": failing}


def d2_table(
    series_by_pair: Mapping[str, Mapping[str, Mapping[str, Any]]],
    classes: Sequence[DecisionClass] = CLASSES,
) -> dict[str, dict[str, dict[str, Any]]]:
    """Table C : classe × paire."""
    return {
        klass.name: {
            pair: d2_cell(series, klass.decision_tfs, where=f"d2.{klass.name}.{pair}")
            for pair, series in series_by_pair.items()
        }
        for klass in classes
    }


def d2_summary(table: Mapping[str, Mapping[str, Mapping[str, Any]]]) -> dict[str, dict[str, Any]]:
    """Par paire : classes qui passent, classes qui sortent, ensemble survivant vide ou non."""
    pairs: list[str] = []
    for row in table.values():
        pairs += [pair for pair in row if pair not in pairs]
    summary: dict[str, dict[str, Any]] = {}
    for pair in pairs:
        passing = [name for name, row in table.items() if row[pair]["status"] == "pass"]
        failing = [name for name, row in table.items() if row[pair]["status"] == "fail"]
        summary[pair] = {"pass": passing, "fail": failing, "survivors_empty": not passing}
    return summary


def evaluate_controls(
    series_by_pair: Mapping[str, Mapping[str, Mapping[str, Any]]],
    *,
    row_count: int,
    alembic_before: Sequence[str],
    alembic_after: Sequence[str],
) -> dict[str, dict[str, Any]]:
    """Les contrôles du brief, chacun avec sa constante sourcée ; ``ok`` faux → code 3."""
    sol = series_by_pair["SOL/USDT"]["1w"]
    first = EXPECTED_SOL_1W_FIRST.isoformat()
    hits = sum(
        len(entry["derived_rows_in_history"])
        for per_tf in series_by_pair.values()
        for entry in per_tf.values()
    )
    return {
        "sol_1w_at_start": {
            "expected": {"loaded": EXPECTED_SOL_1W_LOADED, "first": first},
            "observed": {"loaded": sol["loaded"], "first": sol["first"]},
            "ok": sol["loaded"] == EXPECTED_SOL_1W_LOADED and sol["first"] == first,
            "source": "docs/protocole_c3.md § A.8 l.603-604",
        },
        "derived_rows_in_warmup": {
            "expected": 0,
            "observed": hits,
            "ok": hits == 0,
            "source": "results/reconstruction_1w_2022_2025/report.md — 8 estampilles, toutes > AT",
        },
        "db_row_count_binance": {
            "expected": EXPECTED_BINANCE_ROWS,
            "observed": row_count,
            "ok": row_count == EXPECTED_BINANCE_ROWS,
            "source": "results/reconstruction_1w_2022_2025/evidence/independent_counts.txt:1",
        },
        "alembic_unchanged": {
            "expected": [EXPECTED_ALEMBIC],
            "before": list(alembic_before),
            "after": list(alembic_after),
            "ok": list(alembic_before) == list(alembic_after) == [EXPECTED_ALEMBIC],
            "source": "agent/agent_sol_d2_1w_modes.md § Validation",
        },
    }


def build_payload(
    collected: Mapping[str, Any],
    *,
    plans: Sequence[SeriesPlan],
    strategy: GrokGridATRAdaptiveV4,
    provenance: Mapping[str, Any],
    database: Mapping[str, Any],
    generated_at: datetime,
    argv: Sequence[str],
) -> dict[str, Any]:
    """L'artefact JSON — types natifs seulement (écrivain strict, dette 22)."""
    required = required_by_tf(strategy)
    in_requirements = [tf for tf, n in required.items() if n > 0]
    derived: list[tuple[str, int, datetime]] = list(collected["derived"])
    series = {
        pair: {
            tf: series_entry(
                measured, pair=pair, tf=tf, required_tfs=in_requirements, derived=derived
            )
            for tf, measured in per_tf.items()
        }
        for pair, per_tf in collected["series"].items()
    }
    table = d2_table(series)
    controls = evaluate_controls(
        series,
        row_count=collected["row_count"],
        alembic_before=collected["alembic_before"],
        alembic_after=collected["alembic_after"],
    )
    static = static_tfs(strategy)
    default_class = class_of(strategy)
    decision_sets = sorted({klass.decision_tfs for klass in CLASSES})
    return {
        "schema": SCHEMA,
        "generated_at": generated_at.isoformat(),
        "argv": list(argv),
        "git_sha": provenance["git_sha"],
        "provenance": dict(provenance),
        "database": {
            **database,
            "transaction_read_only": collected["read_only"],
            "alembic_version_before": list(collected["alembic_before"]),
            "alembic_version_after": list(collected["alembic_after"]),
        },
        "db_row_count_binance": collected["row_count"],
        "strategy": {
            "name": STRATEGY,
            "params": "défauts de classe",
            "effective": {
                "atr_period": strategy.atr_period,
                "grid_levels": strategy.grid_levels,
                "bias_1d": str(strategy.bias_1d),
                "pause_1w_strong_bear": bool(strategy.pause_1w_strong_bear),
                "bear_protection_1d_enabled": bool(strategy.bear_protection_1d_enabled),
                "bias_live": bias_live(strategy.grid_levels, strategy.bias_1d),
            },
            "class": default_class.name,
        },
        "window": {
            "start": AT.isoformat(),
            "end": WINDOW_END.isoformat(),
            "anchor_fraction": cc.ANCHOR_FRACTION,
            "anchor": anchor().isoformat(),
        },
        "measure": {"at": AT.isoformat(), "exchange": EXCHANGE, "pairs": list(PAIRS)},
        "engine_args": [
            {
                "tf": plan.tf,
                "interval": plan.interval,
                "window_start": plan.window_start.isoformat(),
                "start": plan.start.isoformat(),
                "end": plan.end.isoformat(),
                "context": plan.context,
            }
            for plan in plans
        ],
        "requirements": {"static_tfs": list(static), "required": required},
        "analyzer_reads": [dict(read) for read in ANALYZER_READS],
        "read_tfs": list(READ_TFS),
        "classes": [
            {
                "name": klass.name,
                "pause_1w": klass.pause_1w,
                "bear_1d": klass.bear_1d,
                "bias_live": klass.bias_live,
                "modes": list(klass.modes),
                "read_tfs": list(READ_TFS),
                "decision_tfs": list(klass.decision_tfs),
                "static_minus_decision": sorted(set(static) - set(klass.decision_tfs)),
            }
            for klass in CLASSES
        ],
        "decision_shape": {
            "distinct_sets": [list(s) for s in decision_sets],
            "empty_classes": [k.name for k in CLASSES if not k.decision_tfs],
            "classes_without_4h": [k.name for k in CLASSES if "4h" not in k.decision_tfs],
        },
        "series": series,
        "d2": table,
        "d2_summary": d2_summary(table),
        "ohlc_derived": {
            "rows_binance": len(derived),
            "rows": [
                {"pair": pair, "interval": interval, "timestamp": stamp.isoformat()}
                for pair, interval, stamp in sorted(derived)
            ],
        },
        "controls": controls,
        "controls_ok": all(control["ok"] for control in controls.values()),
    }


# ---------------------------------------------------------------------------
# Couche base — lecture seule garantie par Postgres
# ---------------------------------------------------------------------------


class ReadOnlyDatabaseManager(DatabaseManager):
    """Le ``DatabaseManager`` des chargeurs du moteur, en lecture seule **côté Postgres** : chaque connexion pose
    ``default_transaction_read_only = on``, donc toute transaction ouverte par ce moteur est ``READ ONLY`` — une
    écriture lèverait, elle n'est pas seulement évitée."""

    def __init__(self, url: str) -> None:
        super().__init__()
        self._engine = create_async_engine(
            url, connect_args={"server_settings": {"default_transaction_read_only": "on"}}
        )
        self._session_factory = async_sessionmaker(
            bind=self._engine, class_=AsyncSession, expire_on_commit=False, autoflush=False
        )
        self._initialized = True


ALEMBIC_SQL = text("SELECT version_num FROM alembic_version ORDER BY version_num")


async def _alembic_versions(session: AsyncSession) -> list[str]:
    return [str(v) for v in (await session.execute(ALEMBIC_SQL)).scalars()]


async def collect(
    url: str, plans: Sequence[SeriesPlan], required: Mapping[str, int]
) -> dict[str, Any]:
    """Le seul endroit qui touche la base."""
    db = ReadOnlyDatabaseManager(url)
    try:
        async with db.read_session() as session:
            read_only = (await session.execute(text("SHOW transaction_read_only"))).scalar_one()
            if read_only != "on":
                raise RuntimeError(f"transaction_read_only = {read_only!r}, 'on' exigé")
            alembic_before = await _alembic_versions(session)
            row_count = int(
                (
                    await session.execute(
                        select(func.count())
                        .select_from(OHLCData)
                        .where(OHLCData.exchange == EXCHANGE)
                    )
                ).scalar_one()
            )
            derived = [
                (str(row.pair), int(row.interval), row.timestamp)
                for row in await session.execute(
                    select(OHLCDerived.pair, OHLCDerived.interval, OHLCDerived.timestamp).where(
                        OHLCDerived.exchange == EXCHANGE
                    )
                )
            ]
        series: dict[str, dict[str, dict[str, Any]]] = {}
        for pair in PAIRS:
            load_window, load_before = engine_loaders(db, pair)
            per_tf: dict[str, dict[str, Any]] = {}
            for plan in plans:
                need = required[plan.tf]
                candles, report = await load_context_series(
                    load_window,
                    load_before,
                    interval=plan.interval,
                    window_start=plan.window_start,
                    start=plan.start,
                    end=plan.end,
                    required=need,
                )
                stamps = [candle.timestamp for candle in candles]
                del candles
                per_tf[plan.tf] = {
                    "report": report,
                    "history": history_stamps(stamps, plan.start),
                    "head": stamps[:need],
                }
                logger.info(
                    "series_measured",
                    pair=pair,
                    tf=plan.tf,
                    required=report["required"],
                    loaded=report["loaded"],
                    sufficient=report["sufficient"],
                )
            series[pair] = per_tf
        async with db.read_session() as session:
            alembic_after = await _alembic_versions(session)
    finally:
        await db.close_db()
    return {
        "read_only": read_only,
        "alembic_before": alembic_before,
        "alembic_after": alembic_after,
        "row_count": row_count,
        "derived": derived,
        "series": series,
    }


# ---------------------------------------------------------------------------
# Provenance, CLI
# ---------------------------------------------------------------------------


def _git(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args], cwd=PROJECT_ROOT, capture_output=True, text=True, check=False
    )


def git_provenance() -> dict[str, Any]:
    script = PROJECT_ROOT / SCRIPT_RELPATH
    return {
        "git_sha": _git("rev-parse", "HEAD").stdout.strip(),
        "branch": _git("branch", "--show-current").stdout.strip(),
        "script": SCRIPT_RELPATH,
        "script_sha256": hashlib.sha256(script.read_bytes()).hexdigest(),
        "script_tracked": _git("ls-files", "--error-unmatch", SCRIPT_RELPATH).returncode == 0,
        "tracked_tree_clean": _git("status", "--porcelain", "--untracked-files=no").stdout.strip()
        == "",
    }


def _database(url: str) -> dict[str, Any]:
    parsed = make_url(url)
    return {"host": parsed.host, "port": parsed.port, "database": parsed.database}


def _parse_iso(value: str) -> datetime:
    stamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if stamp.utcoffset() != timedelta(0):
        raise argparse.ArgumentTypeError("--generated-at doit être en UTC")
    return stamp


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Amorçage C2 du moteur grid mesuré au début du préfixe — lecture seule."
    )
    parser.add_argument("--output", type=Path, required=True, help="Artefact JSON.")
    parser.add_argument(
        "--allow-uncommitted",
        action="store_true",
        help="Développement seulement : accepte un script non committé, en-tête provisoire.",
    )
    parser.add_argument("--generated-at", type=_parse_iso, default=None)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    end = anchor()
    if end != ANCHOR_DECLARED:
        logger.error(
            "anchor_mismatch", recomputed=end.isoformat(), declared=ANCHOR_DECLARED.isoformat()
        )
        return 2
    provenance = git_provenance()
    committed = provenance["script_tracked"] and provenance["tracked_tree_clean"]
    if not committed and not args.allow_uncommitted:
        logger.error(
            "uncommitted_tree",
            script_tracked=provenance["script_tracked"],
            tracked_tree_clean=provenance["tracked_tree_clean"],
            hint="committer d'abord : le git sha de l'en-tête doit être réel",
        )
        return 2
    provenance["provisional"] = not committed
    # .env chargé ici, jamais à l'import (règle B4.2) ; jamais Settings() (piège 5432).
    load_dotenv(PROJECT_ROOT / ".env")
    url = os.getenv("DATABASE_URL")
    if not url:
        logger.error("database_url_missing")
        return 2
    strategy = default_strategy(PAIRS[0])
    plans = context_args(AT, end)
    try:
        collected = asyncio.run(collect(url, plans, required_by_tf(strategy)))
    except Exception as exc:  # noqa: BLE001 - base injoignable ou lecture seule non assertée = code 2
        logger.error("database_read_failed", error=f"{type(exc).__name__}: {exc}")
        return 2
    payload = build_payload(
        collected,
        plans=plans,
        strategy=strategy,
        provenance=provenance,
        database=_database(url),
        generated_at=args.generated_at or datetime.now(UTC),
        argv=sys.argv if argv is None else ["warmup_at.py", *argv],
    )
    digest = write_json_strict(args.output, payload)
    logger.info("warmup_json", path=str(args.output), sha256=digest)
    for name, control in payload["controls"].items():
        logger.info("control", name=name, ok=control["ok"])
    for pair, summary in payload["d2_summary"].items():
        logger.info("d2_summary", pair=pair, passing=summary["pass"], failing=summary["fail"])
    return 0 if payload["controls_ok"] else 3


if __name__ == "__main__":
    raise SystemExit(main())
