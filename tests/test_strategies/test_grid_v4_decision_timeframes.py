"""``GrokGridATRAdaptiveV4.decision_timeframes`` — classmethod pure (C3b lot 1).

Brief : ``agent/AGENT_C3B_PRODUCTEUR.md`` § « Lot 1 ». Protocole : ``docs/protocole_c3.md`` v2.1 § A.8 (D2 : liste de
décision **dérivée, jamais déclarée**). Référence : la sonde comportementale de ``tests/test_scripts/test_warmup_at.py``
(``_probe`` sur ``_handle_ohlc``) et ``warmup_at.class_of``, qu'elle épingle — jamais la table ``CLASSES`` recopiée,
jamais l'implémentation. Refus du non-booléen : brief, décision C3b (``"false"`` est vrai au test ``:384``).

Import de ``test_scripts.test_warmup_at`` : ``PROBE_CASES``, ``_instance`` et ``_probe`` sont importés, pas recopiés.
L'import ne marche **que sous pytest** : ``tests/`` n'a pas d'``__init__.py``, le mode ``prepend`` insère donc ``tests/``
dans ``sys.path`` pour les paquets ``test_scripts`` et ``test_strategies`` ; sous ``python -m`` nu, ``test_scripts``
n'est pas importable. ``warmup_at.default_strategy`` n'accepte pas d'override de paramètres : l'instance de référence
est ``_instance``, celle de la sonde (écart déclaré au plan du lot 1).
"""

# ruff: noqa: E402
from __future__ import annotations

from decimal import Decimal
import importlib
import inspect
from pathlib import Path
import pkgutil
import sys
from types import MappingProxyType
from typing import Any

import pytest

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_PROJECT_ROOT / "src"))
sys.path.insert(0, str(_PROJECT_ROOT / "scripts"))
sys.path.insert(0, str(_PROJECT_ROOT / "scripts" / "audit"))

from test_scripts.test_warmup_at import PROBE_CASES, _instance, _probe
import warmup_at as wa

import krakenbot.strategies as strategies_pkg
from krakenbot.strategies import grok_grid_atr_adaptive_v4 as grid_module
from krakenbot.strategies.base import BaseStrategy
from krakenbot.strategies.gemini_retour_moyenne import GeminiRetourMoyenne
from krakenbot.strategies.gemini_scalping_volatilite import GeminiScalpingVolatilite
from krakenbot.strategies.gemini_suivi_tendance_momentum import GeminiSuiviTendanceMomentum
from krakenbot.strategies.grok_adaptive_dca_weekly import GrokAdaptiveDCAWeekly
from krakenbot.strategies.grok_donchian_breakout_4h import GrokDonchianChannelBreakoutV1
from krakenbot.strategies.grok_ema_adx_atr import GrokEMA27_125_ADX_ATR
from krakenbot.strategies.grok_grid_atr_adaptive_v4 import GrokGridATRAdaptiveV4
from krakenbot.strategies.grok_supertrend_4h import GrokSuperTrend4hRegime
from krakenbot.strategies.multi_strategy_router import MultiStrategyRouter

#: Étiquettes de ``data.timeframes`` du manifeste (brief, lot 1) — pas des minutes.
MANIFEST_TFS = {"4h", "1d", "1w"}
PAUSE_KEY = "pause_1w_strong_bear"


def _decision(params: Any) -> tuple[str, ...]:
    return GrokGridATRAdaptiveV4.decision_timeframes(params)


def _is_refused(params: dict[str, Any]) -> bool:
    """Un cas que la classmethod doit refuser : flag de pause présent et pas un ``bool`` (brief, lot 1)."""
    return PAUSE_KEY in params and type(params[PAUSE_KEY]) is not bool


ACCEPTED = sorted(case for case, (params, _) in PROBE_CASES.items() if not _is_refused(params))
REFUSED = sorted(case for case, (params, _) in PROBE_CASES.items() if _is_refused(params))


# ---------------------------------------------------------------------------
# Les treize jeux de la sonde : douze égalités, un refus
# ---------------------------------------------------------------------------


def test_probe_cases_are_twelve_equalities_and_one_refusal() -> None:
    """Brief : « les treize jeux de paramètres de ``test_warmup_at.py`` » ; le treizième (``"false"``) tombe sous la
    règle de refus du même brief (écart 1 du plan, accepté au GO)."""
    assert len(PROBE_CASES) == 13
    assert len(ACCEPTED) == 12
    assert len(REFUSED) == 1
    ((params, _),) = [PROBE_CASES[case] for case in REFUSED]
    assert params[PAUSE_KEY] == "false"


@pytest.mark.parametrize("case", ACCEPTED)
async def test_probe_cases_equal_class_and_behavioural_probe(case: str) -> None:
    params, expected = PROBE_CASES[case]
    got = _decision(params)
    klass = wa.class_of(_instance(params))
    assert klass.name == expected
    assert set(got) == set(klass.decision_tfs)
    _reads, decisive = await _probe(params)
    assert set(got) == decisive


@pytest.mark.parametrize("case", REFUSED)
async def test_false_string_is_refused_where_the_instance_reads_it_true(case: str) -> None:
    """``__init__`` garde la chaîne (``:131``), ``:384`` la lit vraie : l'instance pause en 1 w strong bear, la sonde
    le montre. La classmethod refuse au lieu de rendre cette lecture."""
    params, expected = PROBE_CASES[case]
    strategy = _instance(params)
    assert strategy.pause_1w_strong_bear == "false"
    assert wa.class_of(strategy).name == expected == "C2"
    _reads, decisive = await _probe(params)
    assert "1w" in decisive
    with pytest.raises(TypeError, match=PAUSE_KEY):
        _decision(params)


# ---------------------------------------------------------------------------
# Balayage : égalité avec class_of sur chaque point
# ---------------------------------------------------------------------------

#: Brief, lot 1 : ``b ∈ {0, 0.05, 0.1, 0.16, 0.2, 0.5}``, ``G ∈ 1..24``.
SWEEP_BIASES: tuple[Any, ...] = (0, 0.05, 0.1, 0.16, 0.2, 0.5)
SWEEP_LEVELS = range(1, 25)


@pytest.mark.parametrize("pause", [True, False])
@pytest.mark.parametrize("mode", [None, "none", "1w_only", "1d_only"])
def test_sweep_equals_class_of(mode: str | None, pause: bool) -> None:
    for grid_levels in SWEEP_LEVELS:
        for bias in SWEEP_BIASES:
            params: dict[str, Any] = {
                PAUSE_KEY: pause,
                "grid_levels": grid_levels,
                "bias_1d": bias,
            }
            if mode is not None:
                params["bear_protection_mode"] = mode
            got = _decision(params)
            expected = wa.class_of(_instance(params)).decision_tfs
            assert set(got) == set(expected), params
            assert list(got) == sorted(got), params
            assert set(got) <= MANIFEST_TFS, params
            assert "4h" in got, params


@pytest.mark.parametrize(
    "params",
    [
        # int("13") = 13, G impair : le bras bear décide (test_warmup_at, cas G13-b0)
        {"bear_protection_mode": "none", "grid_levels": "13", "bias_1d": 0},
        {"bear_protection_mode": "none", "grid_levels": "12", "bias_1d": "0.1"},
        {"bear_protection_mode": "1w_only", "grid_levels": "12", "bias_1d": 0.16},
        {"bear_protection_mode": "1w_only", "grid_levels": "13", "bias_1d": "0"},
        {"grid_levels": 13.0, "bias_1d": Decimal("0.2")},
    ],
)
def test_coercion_is_that_of_init(params: dict[str, Any]) -> None:
    """``grid_levels`` par ``int(...)`` (``:122``), ``bias_1d`` par ``Decimal(str(...))`` (``:130``)."""
    got = _decision(params)
    assert set(got) == set(wa.class_of(_instance(params)).decision_tfs)


# ---------------------------------------------------------------------------
# Refus : flag non booléen, mode invalide
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("mode", [None, "none", "1w_only", "1d_only"])
@pytest.mark.parametrize("value", ["false", 0, 1, "True", None])
def test_non_bool_pause_is_refused(value: Any, mode: str | None) -> None:
    """Refus inconditionnel, y compris quand ``bear_protection_mode`` écrase le flag (écart 3, accepté au GO)."""
    params: dict[str, Any] = {PAUSE_KEY: value}
    if mode is not None:
        params["bear_protection_mode"] = mode
    with pytest.raises(TypeError) as excinfo:
        _decision(params)
    message = str(excinfo.value)
    assert PAUSE_KEY in message
    assert type(value).__name__ in message


def test_invalid_mode_raises_the_value_error_of_init() -> None:
    params = {"bear_protection_mode": "both"}
    with pytest.raises(ValueError) as from_init:
        _instance(params)
    with pytest.raises(ValueError) as from_classmethod:
        _decision(params)
    assert str(from_classmethod.value) == str(from_init.value)


# ---------------------------------------------------------------------------
# Pureté, domaine de l'oracle
# ---------------------------------------------------------------------------


def test_is_a_pure_classmethod() -> None:
    for cls in (GrokGridATRAdaptiveV4, BaseStrategy):
        assert isinstance(inspect.getattr_static(cls, "decision_timeframes"), classmethod)
    before = {cls: dict(vars(cls)) for cls in (GrokGridATRAdaptiveV4, BaseStrategy)}
    params = MappingProxyType({"grid_levels": 13, "bias_1d": 0, "bear_protection_mode": "none"})
    first = _decision(params)
    second = _decision(params)
    assert isinstance(first, tuple)
    assert first == second
    assert {cls: dict(vars(cls)) for cls in (GrokGridATRAdaptiveV4, BaseStrategy)} == before


def test_regime_domain_is_the_audited_one() -> None:
    """``warmup_at.REGIME_DOMAIN`` est épinglé à ``MarketRegime ∪ {None}`` (``multi_timeframe.py:750-777``) par
    ``test_warmup_at``."""
    domain = grid_module._REGIME_DOMAIN
    assert len(domain) == len(set(domain)) == 6
    assert set(domain) == set(wa.REGIME_DOMAIN)


# ---------------------------------------------------------------------------
# Toute autre stratégie refuse
# ---------------------------------------------------------------------------

OTHER_STRATEGIES: tuple[type[BaseStrategy], ...] = (
    GeminiRetourMoyenne,
    GeminiScalpingVolatilite,
    GeminiSuiviTendanceMomentum,
    GrokAdaptiveDCAWeekly,
    GrokDonchianChannelBreakoutV1,
    GrokEMA27_125_ADX_ATR,
    GrokSuperTrend4hRegime,
    MultiStrategyRouter,
)


def _package_strategies() -> set[type[BaseStrategy]]:
    """Toute sous-classe de ``BaseStrategy`` définie dans ``krakenbot.strategies``."""
    found: set[type[BaseStrategy]] = set()
    for info in pkgutil.iter_modules(strategies_pkg.__path__):
        module = importlib.import_module(f"{strategies_pkg.__name__}.{info.name}")
        for obj in vars(module).values():
            if (
                inspect.isclass(obj)
                and issubclass(obj, BaseStrategy)
                and obj is not BaseStrategy
                and obj.__module__ == module.__name__
            ):
                found.add(obj)
    return found


def test_other_strategies_are_every_strategy_of_the_package_but_the_grid() -> None:
    assert _package_strategies() - {GrokGridATRAdaptiveV4} == set(OTHER_STRATEGIES)


@pytest.mark.parametrize("cls", (BaseStrategy, *OTHER_STRATEGIES), ids=lambda cls: cls.__name__)
def test_other_strategies_refuse(cls: type[BaseStrategy]) -> None:
    """Décision 1 du brief : grid seule ; toute autre stratégie lève ``NotImplementedError`` nommant la classe."""
    with pytest.raises(NotImplementedError, match=cls.__name__):
        cls.decision_timeframes({})
