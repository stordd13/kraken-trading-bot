"""``scripts/audit/c3b_common.py`` — fabrique du moteur, couche d'export, couverture, bougies (C3b lot 3).

Brief : ``agent/AGENT_C3B_PRODUCTEUR.md`` § « Lot 3 » et décisions 1, 2, 3, 6 ; plan du lot validé le 2026-09-27
(écarts E1-E12). Le contrat de forme de chaque artefact est **ce que la chaîne lit** : les attendus sont ceux des
accesseurs de ``c3_entry`` / ``c3_benchmark`` / ``c3_common`` (appelés tels quels), des tableaux du protocole
(§ A.7, § A.8) et des lignes du runner et du moteur citées — jamais l'implémentation du producteur.

Aucun test ne touche la base : le vrai ``GridBacktester`` tourne sur des bougies synthétiques par ses chargeurs
remplacés (précédent ``test_grid_terminal_liquidation.py``), avec une base ``MagicMock`` qui n'est jamais lue.
"""

# ruff: noqa: E402
from __future__ import annotations

import ast
import asyncio
from collections.abc import Callable, Mapping, Sequence
import copy
from datetime import UTC, datetime, timedelta
from decimal import Decimal
import hashlib
import json
from pathlib import Path
import sys
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_PROJECT_ROOT))
sys.path.insert(0, str(_PROJECT_ROOT / "src"))
sys.path.insert(0, str(_PROJECT_ROOT / "scripts"))
sys.path.insert(0, str(_PROJECT_ROOT / "scripts" / "audit"))
sys.path.insert(0, str(_PROJECT_ROOT / "tests"))

import _common as ac
import c3_benchmark as cb
import c3_common as cc
import c3_entry as ce
import c3b_common as c3bc

from krakenbot.models.base import TradeSide
from krakenbot.models.market_data import OHLCData
from krakenbot.strategies.grok_grid_atr_adaptive_v4 import GridATRLevel
from test_scripts import test_c3_common as fx

#: Un seul objet module porte ``GridBacktester`` et les chargeurs remplacés (précédent ``test_warmup_at.py``).
bt = c3bc.bt

# ---------------------------------------------------------------------------
# Monde de test : fenêtre pré-2021 courte, paires de validation USDT (§ A.6)
# ---------------------------------------------------------------------------

STRATEGY = "grok_grid_atr_adaptive_v4"
WINDOW_START = datetime(2020, 1, 6, tzinfo=UTC)  # un lundi : la période hebdomadaire est alignée
WINDOW_END = datetime(2020, 1, 20, tzinfo=UTC)
#: § A.3 : ``T = début + 0,70 × (fin − début)`` ; 0,70 × 14 j = 9,8 j = 9 j 19 h 12 min — calcul à la main.
ANCHOR = datetime(2020, 1, 15, 19, 12, tzinfo=UTC)
PAIRS: tuple[str, ...] = ("BTC/USDT", "SOL/USDT")
#: § A.6 v2.1 : transposition déclarée, validation USDT → déploiement USDC.
DEPLOYMENT = {"BTC/USDT": "BTC/USDC", "ETH/USDT": "ETH/USDC", "SOL/USDT": "SOL/USDC"}
#: Les valeurs de ``config/pair_costs_b4.json`` pour la paire de déploiement (README du fichier, GO GATE B).
COSTS = {
    "BTC/USDT": ("0.0002", "0.0002"),
    "ETH/USDT": ("0.0003", "0.0002"),
    "SOL/USDT": ("0.0011", "0.0002"),
}
#: Classes du rapport SOL/D2 (``results/sol_d2_1w_modes/report.md`` § 3.1) : un paramétrage par ensemble,
#: pris aux cas-sondes de ``test_warmup_at.py:375-395``, et l'ensemble de séries de décision de sa classe.
CLASS_PARAMS: dict[str, dict[str, Any]] = {
    "C1": {},
    "C2": {"bear_protection_mode": "1w_only", "bias_1d": 0},
    "C5": {"bear_protection_mode": "none"},
    "C6": {"bear_protection_mode": "none", "bias_1d": 0},
}
CLASS_TFS: dict[str, list[str]] = {
    "C1": ["1d", "1w", "4h"],
    "C2": ["1w", "4h"],
    "C5": ["1d", "4h"],
    "C6": ["4h"],
}
LEVEL = Decimal("100000")  # niveau d'achat amorcé, précédent test_grid_terminal_liquidation.py
ORDER = Decimal("25")


def producer_manifest(
    *,
    classes: Sequence[str] = ("C1", "C6"),
    pairs: Sequence[str] = PAIRS,
    start: datetime = WINDOW_START,
    end: datetime = WINDOW_END,
    provenance: str = cc.PROVENANCE_UNKNOWN,
) -> dict[str, Any]:
    """Un manifeste de producteur **conforme** : la fixture de la chaîne (valeurs gelées, seuils, sha du
    protocole) surchargée en fenêtre pré-2021, stratégie grid réelle, paires USDT transposées, surcharge
    ``decision_timeframes`` par candidat (E8)."""
    candidates = [
        {
            "strategy": STRATEGY,
            "pair": pair,
            "params": dict(CLASS_PARAMS[name]),
            "decision_timeframes": list(CLASS_TFS[name]),
        }
        for pair in pairs
        for name in classes
    ]
    payload = fx.manifest(candidates=candidates, provenance=provenance)
    payload["window"] = {"start": start.isoformat(), "end": end.isoformat()}
    payload["strategies"] = {
        STRATEGY: {"engine": "grid", "decision_timeframes": ["1d", "1w", "4h"]}
    }
    payload["fees"]["pair_costs"] = {
        pair: {"spread": COSTS[pair][0], "slippage": COSTS[pair][1]} for pair in pairs
    }
    payload["universe"]["deployment_pairs"] = {pair: DEPLOYMENT[pair] for pair in pairs}
    return payload


def loaded(payload: Mapping[str, Any]) -> cc.Manifest:
    return cc.load_manifest(json.loads(json.dumps(payload)))


def engine_settings(*, router_entry: Mapping[str, Any] | None = None) -> SimpleNamespace:
    """Les réglages lus par ``GridBacktester`` et la stratégie : le routeur **sans** entrée de nom de classe (le
    cas réel, ``strategies.yaml`` indexe par instance) sauf si ``router_entry`` est donné."""
    strategies = {} if router_entry is None else {STRATEGY: dict(router_entry)}
    return SimpleNamespace(
        multi_strategy=SimpleNamespace(
            enabled=True,
            strategies=[
                SimpleNamespace(
                    name="multi_strategy_router",
                    bot_id="multi_router",
                    params={"strategies": strategies},
                )
            ],
        ),
        trading=SimpleNamespace(pair=PAIRS[0], default_order_amount_eur=50),
    )


# ---------------------------------------------------------------------------
# Marché synthétique et vrai moteur
# ---------------------------------------------------------------------------

Market = dict[tuple[str, int], list[OHLCData]]


def series_stamps(lo: datetime, hi: datetime, interval: int) -> list[datetime]:
    """Les estampilles de la série sur ``[lo, hi]`` (fin de période, 1 w au lundi)."""
    stamp = cc.last_stamp_at_or_before(lo, interval)
    if stamp < lo:
        stamp = cc.first_stamp_strictly_after(lo, interval)
    step = timedelta(days=7) if interval == cc.WEEK_MINUTES else timedelta(minutes=interval)
    out: list[datetime] = []
    while stamp <= hi:
        out.append(stamp)
        stamp += step
    return out


def _ohlc(
    pair: str, interval: int, stamp: datetime, close: Decimal, low: Decimal | None = None
) -> OHLCData:
    return OHLCData(
        timestamp=stamp,
        pair=pair,
        interval=interval,
        exchange="binance",
        open=close,
        high=close,
        low=close if low is None else low,
        close=close,
        volume=Decimal("1"),
        vwap=close,
        trades_count=1,
    )


def market(anchor: datetime = ANCHOR) -> Market:
    """BTC/USDT amorcé (historique depuis ``début − 400 j``, au-delà de tous les amorçages) ; SOL/USDT sans
    historique, ses données commencent au ``début + 2 j`` (le cas réel de SOL en 2020, en réduit). La première
    bougie 5 min de BTC traverse le niveau d'achat amorcé, puis le prix reste sous la vente appariée : la position
    finit ouverte et la liquidation terminale est forcée (précédent ``test_grid_terminal_liquidation.py``)."""
    out: Market = {}
    for pair, first in (
        ("BTC/USDT", WINDOW_START - timedelta(days=400)),
        ("SOL/USDT", WINDOW_START + timedelta(days=2)),
    ):
        for interval in (240, 1440, 10080):
            out[(pair, interval)] = [
                _ohlc(pair, interval, s, LEVEL) for s in series_stamps(first, anchor, interval)
            ]
        exec_first = max(first, WINDOW_START)
        stamps = series_stamps(exec_first, anchor, 5)
        rows = []
        for index, stamp in enumerate(stamps):
            if pair == "BTC/USDT" and index == 1:
                rows.append(_ohlc(pair, 5, stamp, LEVEL, low=Decimal("99500")))
            elif pair == "BTC/USDT" and index > 1:
                rows.append(_ohlc(pair, 5, stamp, Decimal("90000")))
            else:
                rows.append(_ohlc(pair, 5, stamp, LEVEL))
        out[(pair, 5)] = rows
    return out


def install_market(monkeypatch: pytest.MonkeyPatch, data: Market) -> None:
    """Remplace les trois chargeurs du moteur (les seuls sites de lecture en base de ``run``) et amorce la
    grille de BTC comme le précédent (logique 4 h bouchonnée, un niveau d'achat en attente)."""

    async def load_candles(self: Any, pair: str, start: datetime, end: datetime) -> list[OHLCData]:
        return [
            c for c in data.get((pair, self.candle_interval), []) if start <= c.timestamp <= end
        ]

    async def load_interval(
        self: Any, pair: str, interval: int, start: datetime, end: datetime
    ) -> list[OHLCData]:
        return [c for c in data.get((pair, interval), []) if start <= c.timestamp <= end]

    async def load_before(
        self: Any, pair: str, interval: int, before: datetime, limit: int, floor: datetime
    ) -> list[OHLCData]:
        rows = [c for c in data.get((pair, interval), []) if floor <= c.timestamp < before]
        return rows[-limit:] if limit > 0 else []

    original = bt.GridBacktester._create_grok_grid_strategy

    async def seeded(self: Any) -> Any:
        strategy, analyzer = await original(self)
        strategy._handle_ohlc = AsyncMock()
        if self._pair == "BTC/USDT":
            strategy._grid_spacing = Decimal("0.02")
            strategy._grid_center = LEVEL
            strategy._grid_levels[f"buy_{LEVEL}"] = GridATRLevel(
                price=LEVEL, side="buy", status="pending", amount_usdc=ORDER
            )
        return strategy, analyzer

    monkeypatch.setattr(bt.GridBacktester, "_load_candles", load_candles)
    monkeypatch.setattr(bt.GridBacktester, "_load_candles_for_interval", load_interval)
    monkeypatch.setattr(bt.GridBacktester, "_load_candles_before", load_before)
    monkeypatch.setattr(bt.GridBacktester, "_create_grok_grid_strategy", seeded)


def run_real_engine(
    payload: Mapping[str, Any], *, settings: Any = None
) -> tuple[cc.Manifest, datetime, dict[str, dict[str, Any]]]:
    """Chaque candidat : ``build_engine`` → **un** ``run(pair, début, T)`` → ``export_engine`` (vrai moteur)."""
    manifest = loaded(payload)
    anchor = manifest.anchor()
    costs = c3bc.engine_pair_costs(manifest)
    timeframes = c3bc.decision_timeframes_by_candidate(manifest)
    entries: dict[str, dict[str, Any]] = {}
    for candidate in manifest.candidates:
        engine = c3bc.build_engine(
            settings if settings is not None else engine_settings(),
            MagicMock(),
            manifest,
            candidate,
            costs,
        )
        asyncio.run(engine.run(candidate.pair, manifest.window_start, anchor))
        entries[candidate.identity] = c3bc.export_engine(
            engine,
            manifest=manifest,
            candidate=candidate,
            anchor=anchor,
            decision_timeframes=timeframes[candidate.identity],
            pair_costs=costs[candidate.pair],
        )
    return manifest, anchor, entries


def entry_context(
    manifest: cc.Manifest, anchor: datetime, entries: Mapping[str, Any]
) -> ce.Context:
    return ce.Context(
        manifest=manifest,
        anchor=anchor,
        prefix_days=(anchor - manifest.window_start).total_seconds() / 86400.0,
        observations=entries,
        coverage_path=None,
    )


# ---------------------------------------------------------------------------
# Liquidation synthétique, aux formules du moteur
# ---------------------------------------------------------------------------


def engine_like_liquidation(
    lots: Sequence[tuple[Decimal, Decimal | None]],
    *,
    reference: Decimal = Decimal("90000"),
    spread: Decimal = Decimal("0.0002"),
    slippage: Decimal = Decimal("0.0002"),
    taker: Decimal = Decimal("0.0025"),
    stamp: datetime = ANCHOR - timedelta(minutes=2),
) -> tuple[dict[str, Any], list[Any]]:
    """Un ``liquidation_summary`` et ses trades **aux formules du moteur** : prix ``:3183``, lot ``:3104-3107``,
    agrégats ``:3269-3302`` (clés ``_btc`` comprises). ``lots`` : ``(quantité, prix d'entrée | None)``."""
    price = reference * (1 - spread - slippage)
    trades: list[Any] = [
        bt.BacktestTrade(
            timestamp=stamp - timedelta(days=1),
            side=TradeSide.BUY,
            price=reference,
            amount_usdc=Decimal("25"),
            amount_crypto=Decimal("0.00025"),
            fee=Decimal("0.025"),
        ),
        bt.BacktestTrade(
            timestamp=stamp - timedelta(hours=1),
            side=TradeSide.SELL,
            price=reference,
            amount_usdc=Decimal("25"),
            amount_crypto=Decimal("0.00025"),
            fee=Decimal("0.025"),
            pnl=Decimal("1"),
        ),
    ]
    tagged: list[Any] = []
    for amount, entry in lots:
        gross = amount * price
        fee = gross * taker
        net = gross - fee
        pnl = None if entry is None else net - amount * entry
        trade = bt.BacktestTrade(
            timestamp=stamp,
            side=TradeSide.SELL,
            price=price,
            amount_usdc=gross,
            amount_crypto=amount,
            fee=fee,
            pnl=pnl,
            liquidity="taker",
            fee_rate=taker,
            fee_base_usdc=gross,
            reference_price=reference,
            spread_pct=spread,
            slippage_pct=slippage,
            forced_liquidation=True,
        )
        trades.append(trade)
        tagged.append(trade)
    first = tagged[0] if tagged else None
    summary: dict[str, Any] = {
        "buy_fees": "0.05",
        "sell_fees": "0.07",
        "net_pnl_lot_basis": "-1.5",
        "residual_net_proceeds": str(
            sum((t.amount_usdc - t.fee for t in tagged if t.pnl is None), Decimal("0"))
        ),
        "avg_holding_minutes": 60.0 if tagged else None,
        "positions": sum(1 for t in tagged if t.pnl is not None),
        "trades": len(tagged),
        "residual_trade_btc": str(
            sum((t.amount_crypto for t in tagged if t.pnl is None), Decimal("0"))
        ),
        "dust_written_off_btc": "0",
        "inventory_divergence_btc": "0",
        "pnl": "-2.5",
        "fees": str(sum((t.fee for t in tagged), Decimal("0"))),
        "gross_usdc": str(sum((t.amount_usdc for t in tagged), Decimal("0"))),
        "timestamp": first.timestamp.isoformat() if first else None,
        "reference_price": str(first.reference_price) if first else None,
        "price": str(first.price) if first else None,
        "spread_pct": str(first.spread_pct) if first else None,
        "slippage_pct": str(first.slippage_pct) if first else None,
    }
    return summary, trades


def _identities(block: Mapping[str, Any], *, spread: str = "0.0002") -> dict[str, Any]:
    result: dict[str, Any] = cc.liquidation_identities(
        block,
        spread=Decimal(spread),
        slippage=Decimal("0.0002"),
        taker=Decimal("0.0025"),
        end=ANCHOR,
        where="test",
    )
    return result


# ---------------------------------------------------------------------------
# Garde-fou 6 (décision 6) — la fonction pure ; l'ordre dans main est testé dans test_c3b_prefix
# ---------------------------------------------------------------------------


def test_campaign_constants_are_those_of_the_brief() -> None:
    """Brief § Lot 3 : « ``window.start >= 2021-03-01`` ou ``window.end > 2021-03-01`` … tant que le fichier
    ``results/c3b_producteur/CAMPAIGN_UNLOCK`` n'existe pas »."""
    assert c3bc.CAMPAIGN_START == datetime(2021, 3, 1, tzinfo=UTC)
    assert c3bc.CAMPAIGN_UNLOCK == _PROJECT_ROOT / "results" / "c3b_producteur" / "CAMPAIGN_UNLOCK"


@pytest.mark.parametrize(
    ("start", "end", "locked"),
    [
        (datetime(2020, 1, 6, tzinfo=UTC), datetime(2020, 12, 28, tzinfo=UTC), False),
        (datetime(2020, 6, 1, tzinfo=UTC), datetime(2021, 3, 1, tzinfo=UTC), False),
        (datetime(2020, 6, 1, tzinfo=UTC), datetime(2021, 3, 1, 0, 0, 0, 1, tzinfo=UTC), True),
        (datetime(2021, 3, 1, tzinfo=UTC), datetime(2026, 6, 29, tzinfo=UTC), True),
        (datetime(2020, 1, 6, tzinfo=UTC), datetime(2026, 6, 29, tzinfo=UTC), True),
        (datetime(2026, 7, 6, tzinfo=UTC), datetime(2026, 8, 3, tzinfo=UTC), True),
    ],
    ids=[
        "conformite-2020",
        "fin-a-la-borne",
        "fin-borne-plus-1us",
        "debut-a-la-borne",
        "chevauche",
        "apres-2026",
    ],
)
def test_the_campaign_window_is_locked_without_the_unlock_file(
    tmp_path: Path, start: datetime, end: datetime, locked: bool
) -> None:
    """Brief § Lot 3 (règle retenue, écart E6 du plan) : refus dès que la fenêtre n'est pas entièrement
    antérieure au 2021-03-01 — y compris une fenêtre postérieure au 2026-06-29."""
    assert c3bc.campaign_window_locked(start, end, unlock=tmp_path / "absent") is locked


def test_an_existing_unlock_file_unlocks(tmp_path: Path) -> None:
    """Témoin : le déverrouillage existe par un fichier. Le chemin est injecté — ce test ne crée jamais
    ``results/c3b_producteur/CAMPAIGN_UNLOCK``."""
    unlock = tmp_path / "unlock"
    unlock.write_text("test\n", encoding="utf-8")
    campaign = (datetime(2021, 3, 1, tzinfo=UTC), datetime(2026, 6, 29, tzinfo=UTC))
    assert c3bc.campaign_window_locked(*campaign, unlock=unlock) is False


@pytest.mark.parametrize(
    "end",
    [
        datetime(2021, 3, 1, 0, 0, 0, 1, tzinfo=UTC),
        datetime(2026, 6, 29, tzinfo=UTC),
        datetime(2026, 8, 3, tzinfo=UTC),
    ],
    ids=["fin-borne-plus-1us", "campagne", "apres-2026"],
)
def test_designation_is_forbidden_past_the_campaign_start_even_unlocked(
    tmp_path: Path, end: datetime
) -> None:
    """Plan du lot 4a, point 1 (GO du 28/09) : la désignation mécanique ``--candidate`` est « refusée en code 2 dès
    que la fenêtre touche la campagne — même garde que ``CAMPAIGN_UNLOCK`` » ; « une porte de désignation qui
    existerait sur la fenêtre de campagne n'est pas une option ». Même prédicat que le garde-fou 6 (``end >
    2021-03-01``, écart E6), **sans** la porte : un déverrouillage existant ouvre la fenêtre au retenu de
    ``c3_select``, jamais à la désignation."""
    unlock = tmp_path / "unlock"
    unlock.write_text("test\n", encoding="utf-8")
    start = datetime(2020, 6, 1, tzinfo=UTC)
    assert c3bc.campaign_window_locked(start, end, unlock=unlock) is False
    assert c3bc.designation_window_forbidden(end) is True


@pytest.mark.parametrize(
    "end",
    [datetime(2021, 3, 1, tzinfo=UTC), datetime(2020, 12, 28, tzinfo=UTC)],
    ids=["fin-a-la-borne", "conformite-2020"],
)
def test_designation_is_allowed_up_to_the_campaign_start(end: datetime) -> None:
    """Borne du garde-fou 6 (écart E6) : une fenêtre qui finit au 2021-03-01 inclus est entièrement antérieure à la
    campagne ; la désignation y est admise."""
    assert c3bc.designation_window_forbidden(end) is False


# ---------------------------------------------------------------------------
# Paramètres (amendement 2) et séries de décision (décision 1)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("params", "key"),
    [
        ({"grid_levels": 12.5}, "grid_levels"),
        ({"grid_levels": "12"}, "grid_levels"),
        ({"grid_levels": True}, "grid_levels"),
        ({"grid_levels": None}, "grid_levels"),
        ({"grid_levels": float("nan")}, "grid_levels"),
        ({"bias_1d": "abc"}, "bias_1d"),
        ({"bias_1d": None}, "bias_1d"),
        ({"bias_1d": True}, "bias_1d"),
        ({"bias_1d": "NaN"}, "bias_1d"),
        ({"bias_1d": "inf"}, "bias_1d"),
        ({"bias_1d": float("nan")}, "bias_1d"),
    ],
)
def test_grid_levels_must_be_an_int_and_bias_1d_finite(params: dict[str, Any], key: str) -> None:
    """Amendement 2 : « ``grid_levels`` entier, ``bias_1d`` fini, refus nommé » — ``"12"`` compris : un manifeste
    est un JSON typé (décision du 27/09, dit au rapport)."""
    problems = c3bc.validate_params([{}, params])
    assert len(problems) == 1
    assert problems[0].startswith(f"universe.candidates[1].params.{key}")


@pytest.mark.parametrize(
    "params",
    [
        {},
        {"grid_levels": 12},
        {"bias_1d": 0},
        {"bias_1d": 0.2},
        {"bias_1d": "0.16"},
        {"grid_levels": 1, "bias_1d": 0},
    ],
)
def test_well_typed_params_pass(params: dict[str, Any]) -> None:
    assert c3bc.validate_params([params]) == []


def test_non_finite_values_of_a_raw_manifest_are_named() -> None:
    """Écart E9 : ``cc.load_manifest`` refuse un non-fini par la canonicalisation de l'identité, sans nommer la
    clé ; ce parcours la nomme."""
    raw = {
        "universe": {
            "candidates": [
                {"params": {"bias_1d": "NaN"}},
                {"params": {"grid_levels": float("inf")}},
            ]
        }
    }
    assert c3bc.non_finite_paths(raw) == [
        "universe.candidates[0].params.bias_1d",
        "universe.candidates[1].params.grid_levels",
    ]


@pytest.mark.parametrize("name", sorted(CLASS_PARAMS))
def test_decision_timeframes_are_those_of_the_class(name: str) -> None:
    """Rapport SOL/D2 § 3.1 : C1 ``{1d, 1w, 4h}``, C2 ``{1w, 4h}``, C5 ``{1d, 4h}``, C6 ``{4h}`` ; sortie triée
    (brief § Lot 1)."""
    manifest = loaded(producer_manifest(classes=(name,), pairs=("BTC/USDT",)))
    (candidate,) = manifest.candidates
    assert c3bc.decision_timeframes_by_candidate(manifest) == {candidate.identity: CLASS_TFS[name]}


def _single_candidate(
    strategy: str, params: Mapping[str, Any], *, engine: str = "grid"
) -> dict[str, Any]:
    payload = producer_manifest(classes=("C1",), pairs=("BTC/USDT",))
    payload["strategies"] = {strategy: {"engine": engine, "decision_timeframes": ["4h"]}}
    payload["universe"]["candidates"] = [
        {
            "strategy": strategy,
            "pair": "BTC/USDT",
            "params": dict(params),
            "decision_timeframes": ["4h"],
        }
    ]
    return payload


@pytest.mark.parametrize(
    ("strategy", "params", "engine", "needle"),
    [
        (STRATEGY, {"pause_1w_strong_bear": "false"}, "grid", "pause_1w_strong_bear"),
        (STRATEGY, {"pause_1w_strong_bear": 0}, "grid", "pause_1w_strong_bear"),
        (STRATEGY, {"bear_protection_mode": "both"}, "grid", "bear_protection_mode"),
        ("gemini_retour_moyenne", {}, "grid", "does not implement decision_timeframes"),
        ("no_such_strategy", {}, "grid", "absente du registre"),
        (STRATEGY, {}, "signal", "GridBacktester"),
    ],
    ids=["pause-str", "pause-int", "mode-invalide", "non-grid", "inconnue", "moteur-signal"],
)
def test_a_bad_candidate_refuses_the_whole_universe(
    strategy: str, params: dict[str, Any], engine: str, needle: str
) -> None:
    """Brief § Lot 3 : « un ``TypeError`` (non-booléen) ou ``NotImplementedError`` → refus **global** code 2,
    aucun run, la clé fautive nommée » ; décision 1 : grid seule, ``GridBacktester`` seul."""
    payload = _single_candidate(strategy, params, engine=engine)
    payload["universe"]["candidates"].append(
        {
            "strategy": strategy,
            "pair": "BTC/USDT",
            "params": {"grid_levels": 13, **params},
            "decision_timeframes": ["4h"],
        }
    )
    with pytest.raises(c3bc.ProducerRefusal) as caught:
        c3bc.decision_timeframes_by_candidate(loaded(payload))
    assert caught.value.reason == "decision_timeframes_refused"
    assert len(caught.value.problems) == 2  # les deux candidats, jamais un sous-ensemble lancé
    assert all(needle in problem for problem in caught.value.problems)


# ---------------------------------------------------------------------------
# Fees et coûts par paire (écart E1)
# ---------------------------------------------------------------------------


def test_engine_costs_come_from_the_manifest_cross_checked_with_the_file() -> None:
    """Écart E1 : le fichier réel ne porte que ``*/USDC`` ; la paire de validation prend les coûts déclarés au
    manifeste, égaux à ceux du fichier pour sa paire de déploiement (§ A.6)."""
    manifest = loaded(producer_manifest())
    costs = c3bc.engine_pair_costs(manifest)
    assert costs == {
        "BTC/USDT": bt.PairCosts(spread=Decimal("0.0002"), slippage=Decimal("0.0002")),
        "SOL/USDT": bt.PairCosts(spread=Decimal("0.0011"), slippage=Decimal("0.0002")),
    }


def test_costs_different_from_the_file_are_refused() -> None:
    payload = producer_manifest()
    payload["fees"]["pair_costs"]["SOL/USDT"]["spread"] = "0.0003"
    with pytest.raises(c3bc.ProducerRefusal) as caught:
        c3bc.engine_pair_costs(loaded(payload))
    assert caught.value.reason == "pair_costs_refused"
    assert [p.split(" ")[0] for p in caught.value.problems] == ["fees.pair_costs.SOL/USDT"]


def test_a_validation_pair_without_transposition_is_refused() -> None:
    payload = producer_manifest()
    del payload["universe"]["deployment_pairs"]
    with pytest.raises(c3bc.ProducerRefusal) as caught:
        c3bc.engine_pair_costs(loaded(payload))
    assert len(caught.value.problems) == 2
    assert all("déclarer la paire de déploiement" in p for p in caught.value.problems)


def test_the_costs_file_is_read_from_the_project_root(tmp_path: Path) -> None:
    (tmp_path / "config").mkdir()
    (tmp_path / "config" / "pair_costs_b4.json").write_text(
        json.dumps({"BTC/USDC": {"spread": "0.0002", "slippage": "0.0002"}}), encoding="utf-8"
    )
    manifest = loaded(producer_manifest(pairs=("BTC/USDT",)))
    assert c3bc.engine_pair_costs(manifest, root=tmp_path)["BTC/USDT"].spread == Decimal("0.0002")


@pytest.mark.parametrize(
    ("model", "taker"),
    [("Bybit", "0.0025"), ("bybit", "0.0010"), ("nope", "0.0025")],
    ids=["nom-non-canonique", "taker-different", "modele-inconnu"],
)
def test_the_fee_model_must_be_the_one_the_engine_resolves(model: str, taker: str) -> None:
    payload = producer_manifest()
    payload["fees"]["model"] = model
    payload["fees"]["taker"] = taker
    with pytest.raises(c3bc.ProducerRefusal):
        c3bc.check_fee_model(loaded(payload))


def test_the_bybit_model_at_its_taker_passes() -> None:
    c3bc.check_fee_model(loaded(producer_manifest()))


# ---------------------------------------------------------------------------
# Fabrique du moteur : les arguments du runner P7, épinglés à sa source
# ---------------------------------------------------------------------------


def _p7_engine_call() -> ast.Call:
    tree = ast.parse(
        (_PROJECT_ROOT / "scripts" / "run_p7_grid_search.py").read_text(encoding="utf-8")
    )
    engines = [n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name == "_engine"]
    assert len(engines) == 1
    returns = [n for n in ast.walk(engines[0]) if isinstance(n, ast.Return)]
    assert len(returns) == 1 and isinstance(returns[0].value, ast.Call)
    return returns[0].value


def test_the_engine_is_built_with_the_arguments_of_the_p7_runner(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Brief § Lot 3 : « les mêmes arguments que ``run_p7_grid_search._engine``, cite la ligne » — le ``cls(...)``
    de ``:704-717`` lu dans la source : deux positionnels, huit nommés."""
    call = _p7_engine_call()
    p7_keywords = {kw.arg for kw in call.keywords}
    assert len(call.args) == 2
    seen: dict[str, Any] = {}

    class Recorder:
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            seen["args"] = args
            seen["kwargs"] = kwargs

    monkeypatch.setattr(bt, "GridBacktester", Recorder)
    manifest = loaded(producer_manifest(classes=("C2",), pairs=("BTC/USDT",)))
    costs = c3bc.engine_pair_costs(manifest)
    settings, db = object(), object()
    c3bc.build_engine(settings, db, manifest, manifest.candidates[0], costs)
    assert seen["args"] == (settings, db)
    assert set(seen["kwargs"]) == p7_keywords
    assert seen["kwargs"] == {
        "strategy_name": STRATEGY,
        "candle_interval": 5,
        "exchange": "binance",
        "starting_capital": 1000.0,
        "strategy_params_override": CLASS_PARAMS["C2"],
        "fee_model": "bybit",
        "pair_costs": costs,
        "min_order_usdc": 5.0,
    }


# ---------------------------------------------------------------------------
# Couche d'export : liquidation (§ A.7), lots, identités (D6)
# ---------------------------------------------------------------------------


def test_the_export_leaves_no_btc_key() -> None:
    """§ A.7 v2.1 : « les clés ``amount_base``, ``residual_trade_base``, ``dust_written_off_base``,
    ``inventory_divergence_base``, dans le bloc et dans chaque lot » ; un bloc ``_btc`` est une erreur de forme."""
    summary, trades = engine_like_liquidation([(Decimal("0.00024975"), Decimal("100000"))])
    block = c3bc.liquidation_block(summary, trades)
    keys = set(block) | {key for lot in block["lots"] for key in lot}
    assert not [key for key in keys if key.endswith("_btc")]
    assert {"residual_trade_base", "dust_written_off_base", "inventory_divergence_base"} <= set(
        block
    )
    assert block["residual_trade_base"] == summary["residual_trade_btc"]
    cc.check_base_quantity_keys(block, where="test")
    ce._liquidation_form(block, "BTC/USDT", where="test")


@pytest.mark.parametrize(
    "extra",
    [{"foo_btc": "1"}, {"residual_trade_base": "0"}, {"lots": []}],
    ids=["cle-btc-hors-liste", "collision", "lots-deja-portes"],
)
def test_an_engine_change_under_the_export_is_a_control_error(extra: dict[str, Any]) -> None:
    summary, trades = engine_like_liquidation([(Decimal("0.00024975"), Decimal("100000"))])
    summary.update(extra)
    with pytest.raises(c3bc.ProducerControlError):
        c3bc.liquidation_block(summary, trades)


def test_lots_are_the_forced_liquidation_trades_in_order() -> None:
    """Brief § Lot 3 : « les lots se reconstruisent … depuis ``metrics.trades`` tagués ``forced_liquidation``
    (``:3125-3145``) — ``amount_base = amount_crypto``, ``gross_usdc = amount_usdc``, ``fee``, ``pnl`` »."""
    summary, trades = engine_like_liquidation(
        [
            (Decimal("0.5"), Decimal("100")),
            (Decimal("0.25"), Decimal("80")),
            (Decimal("0.1"), None),
        ],
        reference=Decimal("90"),
    )
    lots = c3bc.lots_from_trades(trades)
    tagged = [t for t in trades if t.forced_liquidation]
    assert len(trades) == 5 and len(lots) == 3
    # La clé du montant en cotation vit dans le jumeau R-16 : § A.7 v2.2 (AM-04) nomme `gross_quote`.
    assert [{k: v for k, v in lot.items() if not k.startswith("gross_")} for lot in lots] == [
        {
            "amount_base": str(t.amount_crypto),
            "fee": str(t.fee),
            "pnl": None if t.pnl is None else str(t.pnl),
            "entry_price": lots[i]["entry_price"],
        }
        for i, t in enumerate(tagged)
    ]


def test_entry_price_inverts_the_engine_pnl() -> None:
    """``pnl = net − amount × entry_price`` (``backtest.py:3107``) ⇒ ``entry_price = (gross − fee − pnl) /
    amount``, ``null`` avec ``pnl`` — exact en arithmétique exacte."""
    _, trades = engine_like_liquidation(
        [
            (Decimal("0.5"), Decimal("100")),
            (Decimal("0.25"), Decimal("80")),
            (Decimal("0.1"), None),
        ],
        reference=Decimal("90"),
    )
    lots = c3bc.lots_from_trades(trades)
    # 0,5 × 89,964 = 44,982 ; fee 0,112455 ; pnl = 44,869545 − 50 = −5,130455 ⇒ (44,982 − 0,112455 + 5,130455) / 0,5 = 100
    assert [Decimal(str(lot["entry_price"])) for lot in lots[:2]] == [Decimal("100"), Decimal("80")]
    assert lots[2]["entry_price"] is None and lots[2]["pnl"] is None


def test_entry_price_is_exact_to_the_decimal_context_only() -> None:
    """Sur des valeurs à 28 chiffres (celles du moteur réel) l'inverse n'est exact qu'à la précision du
    contexte ``Decimal`` — limite écrite ; la chaîne ne contrôle que la nullité conjointe (``c3_common.py:2061``)."""
    entry = Decimal("100123.4567890123456789012345")
    _, trades = engine_like_liquidation(
        [(Decimal("0.0002497502497502497502497502"), entry)],
        reference=Decimal("98765.43210987654321"),
    )
    (lot,) = c3bc.lots_from_trades(trades)
    assert lot["entry_price"] is not None
    assert abs(Decimal(lot["entry_price"]) - entry) / entry <= Decimal("1e-25")


def test_a_coherent_export_passes_the_liquidation_identities() -> None:
    """Brief § Lot 3 : « ``cc.liquidation_identities(block, …)["passed"]`` vrai sur ta sortie » — un lot connu
    et un lot résiduel à coût inconnu ; témoin adverse : sans lots, la preuve échoue."""
    summary, trades = engine_like_liquidation(
        [(Decimal("0.00024975"), Decimal("100000")), (Decimal("0.00001"), None)]
    )
    block = c3bc.liquidation_block(summary, trades)
    assert _identities(block)["passed"] is True
    without_lots = {k: v for k, v in block.items() if k != "lots"}
    assert _identities(without_lots)["passed"] is False


def test_an_export_without_forced_trade_passes_the_identities() -> None:
    """``trades == 0`` : ``positions == 0``, ``fees == gross == 0``, ``lots == []`` (``c3_common.py:1990-2000``)."""
    summary, trades = engine_like_liquidation([])
    block = c3bc.liquidation_block(summary, trades)
    assert block["lots"] == [] and block["trades"] == 0
    assert _identities(block)["passed"] is True


def test_a_non_positive_lot_is_a_control_error() -> None:
    summary, trades = engine_like_liquidation(
        [(Decimal("0.5"), Decimal("100"))], reference=Decimal("90")
    )
    trades[-1].amount_crypto = Decimal("0")
    with pytest.raises(c3bc.ProducerControlError):
        c3bc.lots_from_trades(trades)


# ---------------------------------------------------------------------------
# Vrai moteur, sans base : la sortie est ce que c3_entry lit
# ---------------------------------------------------------------------------


@pytest.fixture
def real_world(
    monkeypatch: pytest.MonkeyPatch,
) -> tuple[cc.Manifest, datetime, dict[str, dict[str, Any]]]:
    install_market(monkeypatch, market())
    return run_real_engine(producer_manifest())


def _by_pair(entries: Mapping[str, dict[str, Any]], pair: str) -> list[dict[str, Any]]:
    return [entry for entry in entries.values() if entry["pair"] == pair]


def test_the_real_engine_export_passes_the_entry_form(
    real_world: tuple[cc.Manifest, datetime, dict[str, dict[str, Any]]],
) -> None:
    """Brief § Lot 3 : « sortie de l'export → ``c3_entry.a01_form`` sur un contexte synthétique = zéro problème » —
    et D5 (aucune clause non assertable : ``exec_interval`` porté), les bornes ``[début, T]``, l'amorçage recoupé."""
    manifest, anchor, entries = real_world
    ctx = entry_context(manifest, anchor, entries)
    assert ce.a01_form(ctx).problems == []
    d5 = ce.a02_d5(ctx)
    assert d5.problems == [] and d5.not_assertable == []
    assert ce.a03_bounds(ctx).problems == []
    assert ce.a04_identities(ctx).problems == []
    assert ce.a06_warmup(ctx).problems == [] and ctx.violations == []


def test_the_real_engine_export_carries_a_proven_liquidation(
    real_world: tuple[cc.Manifest, datetime, dict[str, dict[str, Any]]],
) -> None:
    """BTC : une position ouverte liquidée au marché — un lot, coût connu, identités exactes avec les coûts du
    manifeste ; SOL : aucun trade. Contrôles internes (E10, D6) vides."""
    manifest, anchor, entries = real_world
    for entry in _by_pair(entries, "BTC/USDT"):
        block = entry["liquidation"]["train"]
        assert block["trades"] == 1 and block["positions"] == 1 and len(block["lots"]) == 1
        assert block["lots"][0]["entry_price"] is not None
    for entry in _by_pair(entries, "SOL/USDT"):
        assert entry["liquidation"]["train"]["trades"] == 0
        assert entry["liquidation"]["train"]["lots"] == []
    for entry in entries.values():
        assert c3bc.entry_controls(entry, manifest=manifest, anchor=anchor) == []


def test_sol_without_history_exports_an_insufficient_warmup(
    real_world: tuple[cc.Manifest, datetime, dict[str, dict[str, Any]]],
) -> None:
    """Le cas de SOL au 2020-01-06 : ``loaded 0``, ``stale_by_candles`` et ``first``/``last`` nuls, ``sufficient``
    faux sur chaque série — forme acceptée par ``_segment_form``, D2 en échec pour la chaîne."""
    _, _, entries = real_world
    for entry in _by_pair(entries, "SOL/USDT"):
        for tf in ("4h", "1d", "1w"):
            block = entry["warmup"]["train"][tf]
            assert (
                block["loaded"],
                block["stale_by_candles"],
                block["first"],
                block["sufficient"],
            ) == (
                0,
                None,
                None,
                False,
            )
    for entry in _by_pair(entries, "BTC/USDT"):
        assert all(entry["warmup"]["train"][tf]["sufficient"] is True for tf in ("4h", "1d", "1w"))


def test_the_entry_keys_are_those_of_the_p7_result(
    real_world: tuple[cc.Manifest, datetime, dict[str, dict[str, Any]]],
) -> None:
    """Brief § Lot 3 : « le dict ``result`` de ``run_p7_grid_search:748-786`` avec un seul segment …, sans
    ``phase`` / ``window_idx``, plus » ``decision_timeframes`` et ``exec_interval`` — clés lues dans la source,
    aucune provenance."""
    tree = ast.parse(
        (_PROJECT_ROOT / "scripts" / "run_p7_grid_search.py").read_text(encoding="utf-8")
    )
    results = [
        n.value
        for n in ast.walk(tree)
        if isinstance(n, ast.AnnAssign)
        and isinstance(n.target, ast.Name)
        and n.target.id == "result"
        and isinstance(n.value, ast.Dict)
    ]
    assert len(results) == 1
    p7 = {k.value for k in results[0].keys if isinstance(k, ast.Constant)}
    (period,) = [
        v
        for k, v in zip(results[0].keys, results[0].values, strict=True)
        if isinstance(k, ast.Constant) and k.value == "period"
    ]
    assert isinstance(period, ast.Dict)
    p7_period = {k.value for k in period.keys if isinstance(k, ast.Constant)}
    expected = (p7 - {"phase", "window_idx", "test"}) | {"decision_timeframes", "exec_interval"}
    expected_period = {key for key in p7_period if not key.startswith("test_")}
    _, _, entries = real_world
    # Le nom du plancher d'ordre vit dans le jumeau R-16 : § A.7 v2.2 (AM-04), `min_order_quote`.
    plancher = {"min_order_usdc", "min_order_quote"}
    for entry in entries.values():
        assert set(entry) - plancher == expected - plancher
        assert set(entry["period"]) == expected_period
        for block in ("liquidation", "equity_daily", "rejections", "warmup"):
            assert set(entry[block]) == {"train"}


def test_the_exported_lists_and_bounds(
    real_world: tuple[cc.Manifest, datetime, dict[str, dict[str, Any]]],
) -> None:
    """``decision_timeframes`` triée, ``exec_interval`` = celui du manifeste, ``period`` finit **exactement** à
    ``T`` (brief § Lot 3), ``params`` ceux du manifeste."""
    manifest, anchor, entries = real_world
    for candidate in manifest.candidates:
        entry = entries[candidate.identity]
        assert entry["decision_timeframes"] == sorted(candidate.decision_timeframes)
        assert entry["exec_interval"] == manifest.exec_interval == 5
        assert entry["period"] == {
            "train_start": WINDOW_START.isoformat(),
            "train_end": ANCHOR.isoformat(),
        }
        assert anchor == ANCHOR
        assert entry["params"] == dict(candidate.params)


def test_removing_a_carrier_is_seen_by_the_chain(
    real_world: tuple[cc.Manifest, datetime, dict[str, dict[str, Any]]],
) -> None:
    """Brief § Lot 3 : « retirer ``decision_timeframes`` → problème nommé » ; sans ``exec_interval``, D5 est
    ``not_assertable`` (§ I.2)."""
    manifest, anchor, entries = real_world
    identity = sorted(entries)[0]
    without_tfs = copy.deepcopy(entries)
    del without_tfs[identity]["decision_timeframes"]
    problems = ce.a01_form(entry_context(manifest, anchor, without_tfs)).problems
    assert len(problems) == 1 and "decision_timeframes" in problems[0]
    without_exec = copy.deepcopy(entries)
    del without_exec[identity]["exec_interval"]
    assert ce.a02_d5(entry_context(manifest, anchor, without_exec)).not_assertable


def test_a_router_entry_under_the_class_name_breaks_passed_params(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Écart E10 : une entrée ``strategies.yaml`` au nom de classe serait fusionnée (``backtest.py:2372-2382``) et
    ``decision_timeframes`` ne décrirait plus le run — contrôle interne en échec."""
    install_market(monkeypatch, market())
    settings = engine_settings(router_entry={"params": {"atr_period": 21}})
    manifest, anchor, entries = run_real_engine(
        producer_manifest(pairs=("BTC/USDT",)), settings=settings
    )
    for entry in entries.values():
        problems = c3bc.entry_controls(entry, manifest=manifest, anchor=anchor)
        assert len(problems) == 1 and "passed_params" in problems[0]


# ---------------------------------------------------------------------------
# Couverture (§ A.7, § A.8 D1) — attendus tirés du tableau du § A.8 l.475-480
# ---------------------------------------------------------------------------


def _full(start: datetime, end: datetime, interval: int) -> list[datetime]:
    return c3bc.expected_stamps(start, end, interval)


def _series(
    observed: Sequence[datetime],
    interval: int,
    *,
    derived: Sequence[datetime] = (),
    start: datetime = WINDOW_START,
    end: datetime = ANCHOR,
) -> dict[str, Any]:
    series = c3bc.coverage_series(observed, derived, start=start, end=end, interval=interval)
    assert (
        cc.coverage_recompute(series, start=start, end=end, interval=interval, where="t")[
            "problems"
        ]
        == []
    )
    return series


def test_a_complete_series() -> None:
    """9 jours entiers dans ``[2020-01-06, 2020-01-15T19:12]``, une période hebdomadaire (``2020-01-13``)."""
    for interval, units, unit in (
        (5, 9, "day"),
        (240, 9, "day"),
        (1440, 9, "day"),
        (10080, 1, "week"),
    ):
        series = _series(_full(WINDOW_START, ANCHOR, interval), interval)
        assert (series["covered_units"], series["expected_units"], series["unit"]) == (
            units,
            units,
            unit,
        )
        assert series["missing_stamps"] == [] and series["longest_gap_days"] == 0.0
    assert set(_series(_full(WINDOW_START, ANCHOR, 5), 5)) == {
        "observed",
        "expected",
        "covered_units",
        "expected_units",
        "unit",
        "missing_stamps",
        "longest_gap_days",
        "first_day",
        "last_day",
    }


def _day(day: int, interval: int) -> list[datetime]:
    """Les estampilles couvrant le jour civil ``2020-01-day`` (fin de période : ``(d, d+1 j]``)."""
    lo = datetime(2020, 1, day, tzinfo=UTC)
    return [s for s in _full(WINDOW_START, ANCHOR, interval) if lo < s <= lo + timedelta(days=1)]


@pytest.mark.parametrize(
    ("removed", "covered"), [(144, 9), (145, 8)], ids=["144-restent", "143-restent"]
)
def test_a_5m_day_is_covered_from_144_candles(removed: int, covered: int) -> None:
    """§ A.8 : « 5 min — jours dont le compte observé atteint **au moins 144** »."""
    gone = set(_day(8, 5)[:removed])
    observed = [s for s in _full(WINDOW_START, ANCHOR, 5) if s not in gone]
    assert _series(observed, 5)["covered_units"] == covered


def test_a_4h_day_with_five_of_six_stamps_is_not_covered() -> None:
    """§ A.8 : « 4 h — jours dont les 6 estampilles sont présentes »."""
    gone = _day(9, 240)[0]
    series = _series([s for s in _full(WINDOW_START, ANCHOR, 240) if s != gone], 240)
    assert series["covered_units"] == 8 and series["missing_stamps"] == [gone.isoformat()]
    assert series["longest_gap_days"] == 240 / 1440


def test_the_week_is_a_unit_never_days() -> None:
    """§ A.8 : « 1 w — **périodes hebdomadaires** présentes, jamais des jours » ; sur six semaines, une
    estampille manquante retire une unité, et le trou vaut 7 jours."""
    end = datetime(2020, 2, 18, tzinfo=UTC)
    weeks = _full(WINDOW_START, end, 10080)
    series = _series([w for w in weeks if w != weeks[2]], 10080, end=end)
    assert (series["expected_units"], series["covered_units"], series["longest_gap_days"]) == (
        6,
        5,
        7.0,
    )


def test_a_late_start_is_an_edge_gap() -> None:
    """Revue R3 (``c3_common.longest_missing_run``) : une série qui commence en retard est un trou au bord, compté
    comme les autres ; premier jour couvert = premier jour entier présent."""
    first = datetime(2020, 1, 8, tzinfo=UTC)
    observed = [s for s in _full(WINDOW_START, ANCHOR, 1440) if s > first]
    series = _series(observed, 1440)
    assert series["longest_gap_days"] == 2.0
    assert series["first_day"] == "2020-01-08" and series["covered_units"] == 7


def test_first_and_last_days_are_covered_days() -> None:
    """§ A.7 l.416 : « les premier et dernier jours **couverts** » — un 6 janvier 4 h à 5/6 n'est pas couvert,
    le premier jour couvert est le 7 (écart E3)."""
    gone = _day(6, 240)[-1]
    series = _series([s for s in _full(WINDOW_START, ANCHOR, 240) if s != gone], 240)
    assert (series["first_day"], series["last_day"]) == ("2020-01-07", "2020-01-14")


def test_derived_rows_count_as_observed() -> None:
    """Décision C3 du 23/09 (brief § Lot 3) : « les rows de ``ohlc_derived`` **comptent comme observées** »."""
    weeks = _full(WINDOW_START, datetime(2020, 2, 18, tzinfo=UTC), 10080)
    series = _series(weeks, 10080, derived=[weeks[1]], end=datetime(2020, 2, 18, tzinfo=UTC))
    assert series["covered_units"] == 6 and series["missing_stamps"] == []


def test_a_derived_stamp_absent_from_the_observed_is_a_control_error() -> None:
    weeks = _full(WINDOW_START, datetime(2020, 2, 18, tzinfo=UTC), 10080)
    with pytest.raises(c3bc.ProducerControlError):
        c3bc.coverage_series(
            weeks[:-1],
            [weeks[-1]],
            start=WINDOW_START,
            end=datetime(2020, 2, 18, tzinfo=UTC),
            interval=10080,
        )


@pytest.mark.parametrize(
    "bad",
    [lambda s: [*s, s[0]], lambda s: [*s, s[-1] + timedelta(minutes=1)]],
    ids=["doublon", "hors-grille"],
)
def test_duplicate_or_off_grid_observed_stamps_are_control_errors(
    bad: Callable[[list[datetime]], list[datetime]],
) -> None:
    observed = bad(_full(WINDOW_START, ANCHOR, 1440))
    with pytest.raises(c3bc.ProducerControlError):
        c3bc.coverage_series(observed, [], start=WINDOW_START, end=ANCHOR, interval=1440)


R20 = pytest.mark.xfail(
    strict=True,
    raises=AssertionError,
    reason="R-20 : § A.7 v2.2 (AM-09), dates de couverture nulles ssi aucune unité couverte — outillage à venir",
)


@R20
def test_R20_a_series_without_covered_unit_is_written_with_null_dates() -> None:
    """§ A.7 v2.2 (AM-09) : « Ces deux dates sont nulles si et seulement si la série n'a aucune unité couverte au
    sens de D1 » — la série est écrite, elle n'est plus refusée (ancien test : refus `coverage_no_covered_unit`,
    écart E3 de C3b, candidat v2.2 tranché)."""
    try:
        series = c3bc.coverage_series([], [], start=WINDOW_START, end=ANCHOR, interval=240)
    except c3bc.ProducerRefusal as exc:
        raise AssertionError(
            f"refus {exc.reason} : § A.7 v2.2 veut une série à dates nulles"
        ) from exc
    assert series["covered_units"] == 0
    assert series["first_day"] is None and series["last_day"] is None


def test_the_coverage_artefact_is_what_a07_reads(tmp_path: Path) -> None:
    """``coverage.json`` : ``{window: {start, end: T}, pairs: {pair: {"5", "240", "1440", "10080"}}}`` — lu par
    ``c3_entry.a07_coverage`` sans problème."""
    data = market()
    observed = {
        pair: {
            iv: [c.timestamp for c in data[(pair, iv)] if WINDOW_START < c.timestamp <= ANCHOR]
            for iv in cc.D1_INTERVALS
        }
        for pair in PAIRS
    }
    derived: dict[str, dict[int, list[datetime]]] = {
        pair: {iv: [] for iv in cc.D1_INTERVALS} for pair in PAIRS
    }
    artefact = c3bc.coverage_artefact(observed, derived, start=WINDOW_START, end=ANCHOR)
    assert set(artefact) == {"window", "pairs"}
    assert artefact["window"] == {"start": WINDOW_START.isoformat(), "end": ANCHOR.isoformat()}
    path = tmp_path / "coverage.json"
    ac.write_json_strict(path, artefact)
    manifest = loaded(producer_manifest())
    ctx = ce.Context(
        manifest=manifest,
        anchor=ANCHOR,
        prefix_days=(ANCHOR - WINDOW_START).total_seconds() / 86400.0,
        observations={},
        coverage_path=path,
    )
    assert ce.a07_coverage(ctx).problems == [] and ctx.coverage_status == "evaluated"


# ---------------------------------------------------------------------------
# Bougies (§ L.1 ligne 0, § C.3)
# ---------------------------------------------------------------------------


def _rows(pair: str, interval: int, lo: datetime = WINDOW_START) -> list[tuple[datetime, Decimal]]:
    return [
        (c.timestamp, c.close) for c in market()[(pair, interval)] if lo <= c.timestamp <= ANCHOR
    ]


def _candle_input() -> dict[str, dict[str, list[tuple[datetime, Decimal]]]]:
    return {pair: {"exec": _rows(pair, 5), "daily": _rows(pair, 1440)} for pair in PAIRS}


def test_the_candles_are_what_c3_benchmark_reads() -> None:
    """Brief § Lot 3 : ``{pairs: {pair: {exec_interval, exec: [{t, close}], daily: [{t, close}]}}}``, ``close`` en
    ``str`` de ``Decimal``, triées — lu par ``c3_benchmark.load_candles`` sans refus."""
    rows = _candle_input()
    rows["BTC/USDT"]["exec"] = list(reversed(rows["BTC/USDT"]["exec"]))
    artefact = c3bc.candles_artefact(rows, start=WINDOW_START, end=ANCHOR, exec_interval=5)
    assert set(artefact) == {"pairs"}
    btc = artefact["pairs"]["BTC/USDT"]
    assert set(btc) == {"exec_interval", "exec", "daily"} and btc["exec_interval"] == 5
    assert [r["t"] for r in btc["exec"]] == sorted(r["t"] for r in btc["exec"])
    assert all(isinstance(r["close"], str) for r in btc["exec"] + btc["daily"])
    cb.load_candles(json.loads(json.dumps(artefact)), loaded(producer_manifest()), end=ANCHOR)


@pytest.mark.parametrize(
    "corrupt",
    [
        lambda r: r.append((ANCHOR + timedelta(minutes=5), Decimal("1"))),
        lambda r: r.append(r[0]),
        lambda r: r.__setitem__(0, (r[0][0], float(r[0][1]))),
        lambda r: r.append((WINDOW_START - timedelta(minutes=5), Decimal("1"))),
    ],
    ids=["estampille-apres-T", "doublon", "close-float", "avant-debut"],
)
def test_the_producer_itself_refuses_bad_candles(corrupt: Callable[[list[Any]], None]) -> None:
    """Brief § Lot 3 : « une estampille ``> T`` injectée → refus **du producteur** (pas seulement de la chaîne) »."""
    rows = _candle_input()
    corrupt(rows["SOL/USDT"]["exec"])
    with pytest.raises(c3bc.ProducerControlError):
        c3bc.candles_artefact(rows, start=WINDOW_START, end=ANCHOR, exec_interval=5)


# ---------------------------------------------------------------------------
# Écriture
# ---------------------------------------------------------------------------


def test_the_atomic_writer_is_the_strict_writer(tmp_path: Path) -> None:
    """Conventions du brief : « toute sortie JSON par ``write_json_strict`` » ; atomique (``save_result_atomic``-
    like, réimplémenté) — aucun temporaire ne reste."""
    payload = {"b": [1, 2.5, None], "a": "x"}
    digest = c3bc.write_json_atomic(tmp_path / "out" / "f.json", payload)
    text = (tmp_path / "out" / "f.json").read_text(encoding="utf-8")
    assert digest == hashlib.sha256(text.encode("utf-8")).hexdigest()
    assert digest == ac.write_json_strict(tmp_path / "ref.json", payload)
    assert sorted(p.name for p in (tmp_path / "out").iterdir()) == ["f.json"]


def test_the_atomic_writer_refuses_a_decimal_and_leaves_nothing(tmp_path: Path) -> None:
    with pytest.raises(TypeError, match=r"^a\.b\[0\]"):
        c3bc.write_json_atomic(tmp_path / "f.json", {"a": {"b": [Decimal("1")]}})
    assert list(tmp_path.iterdir()) == []


# ---------------------------------------------------------------------------
# Discipline de source (leçon « contrôle de présence qui passe »)
# ---------------------------------------------------------------------------


def assert_source_discipline(relpath: str) -> None:
    """Aucun ``bool(...)`` (``"false"`` est vrai, rapport SOL/D2 § 8.2-1), aucun ``.get(...)`` de dictionnaire (une
    absence doit se voir) — seul ``AsyncResult.get(timeout=…)`` du pool est admis ; aucune connexion hors du
    gestionnaire en lecture seule importé (``DatabaseManager(``, ``create_async_engine``, ``Settings(``). Chaque
    fichier de tests l'applique à son module (``test_c3b_prefix`` à ``c3b_prefix.py``)."""
    tree = ast.parse((_PROJECT_ROOT / relpath).read_text(encoding="utf-8"))
    calls = [n for n in ast.walk(tree) if isinstance(n, ast.Call)]
    names = {c.func.id for c in calls if isinstance(c.func, ast.Name)}
    getters = [
        c
        for c in calls
        if isinstance(c.func, ast.Attribute)
        and c.func.attr == "get"
        and [kw.arg for kw in c.keywords] != ["timeout"]
    ]
    assert not {"bool", "DatabaseManager", "create_async_engine", "Settings"} & names
    assert getters == []


def test_the_common_layer_never_coerces_nor_opens_a_database_by_itself() -> None:
    assert_source_discipline("scripts/audit/c3b_common.py")


R16 = pytest.mark.xfail(
    strict=True,
    raises=AssertionError,
    reason="R-16 : § A.7 v2.2 (AM-04), clés `_quote` aux positions nommées — outillage à venir",
)


@R16
def test_R16_les_lots_et_le_bloc_de_liquidation_portent_gross_quote() -> None:
    """§ A.7 v2.2, ligne Comptabilité : « la clé `gross_quote`, dans le bloc et dans chaque lot, quelle que soit
    la paire » ; aucune clé `gross_` suffixée par une monnaie."""
    summary, trades = engine_like_liquidation(
        [(Decimal("0.5"), Decimal("100")), (Decimal("0.25"), Decimal("80"))],
        reference=Decimal("90"),
    )
    tagged = [t for t in trades if t.forced_liquidation]
    lots = c3bc.lots_from_trades(trades)
    assert [lot.get("gross_quote") for lot in lots] == [str(t.amount_usdc) for t in tagged]
    block = c3bc.liquidation_block(summary, trades)
    assert "gross_quote" in block
    assert not [k for k in block if k.startswith("gross_") and k != "gross_quote"]
    assert not [
        k for lot in block["lots"] for k in lot if k.startswith("gross_") and k != "gross_quote"
    ]


@R16
def test_R16_l_observation_exportee_porte_min_order_quote(
    real_world: tuple[cc.Manifest, datetime, dict[str, dict[str, Any]]],
) -> None:
    """§ A.7 v2.2, ligne Contrats : la clé du plancher d'ordre est `min_order_quote` quelle que soit la paire ;
    l'argument `min_order_usdc` du moteur ne bouge pas (test `build_engine`, inchangé)."""
    _, _, entries = real_world
    for entry in entries.values():
        assert "min_order_quote" in entry and "min_order_usdc" not in entry
