"""C3b — couche commune du producteur : fabrique du moteur, couche d'export, couverture, bougies.

Brief : ``agent/AGENT_C3B_PRODUCTEUR.md`` § « Lot 3 », décisions 1, 2, 3 et 6. Le producteur est un outillage
**hors chaîne** (§ L.1, ligne 0) : il fabrique les entrées que la chaîne C3 lit, et leur contrat de forme est
**ce que les accesseurs de la chaîne lisent, rien d'autre** — ``c3_entry`` (``_liquidation_form``,
``_segment_form``, ``a01_form`` … ``a08_d2``) et ``c3_benchmark.load_candles``.

Trois règles portées par ce module :

* **Une seule fonction, une seule convention** (décision 3, § F.2 c). Les primitives de la chaîne sont importées,
  jamais recopiées : ``cc.expected_candles``, ``cc.expected_units``, ``cc.coverage_unit``,
  ``cc.longest_missing_run``, ``cc.gap_days``, ``cc.unit_day_of``. La règle D1 du compte d'unités couvertes
  n'a pas de fonction publique (elle vit en ligne dans ``cc.coverage_recompute``) : elle est lue par **oracle**,
  en appelant ``cc.coverage_recompute`` elle-même — précédent : la fixture ``degrade_coverage`` des tests C3.
* **Le moteur est intouché** (décision 2). ``scripts/backtest.py`` est lu, jamais modifié : le renommage des
  clés ``_btc`` et la reconstruction des lots de liquidation vivent ici, dans la couche d'export (§ A.7).
* **Garde-fou 6** (décision 6) : aucune fenêtre qui dépasse le 2021-03-01 tant que
  ``results/c3b_producteur/CAMPAIGN_UNLOCK`` n'existe pas.

Les seules fonctions qui touchent la base sont ``probe_database``, ``fetch_stamps``, ``fetch_closes`` et
``fetch_derived_stamps`` ; elles reçoivent un gestionnaire en lecture seule (``_db.ReadOnlyDatabaseManager``,
construit par l'appelant) et sont appelées par attribut de module, pour que les tests les remplacent.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal, InvalidOperation
import math
import os
from pathlib import Path
import sys
import tempfile
from typing import Any

_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(_ROOT / "src"))
sys.path.insert(0, str(_ROOT / "scripts"))
sys.path.insert(0, str(_ROOT / "scripts" / "audit"))

import _common  # noqa: E402
import backtest as bt  # noqa: E402
import c3_common as cc  # noqa: E402
from sqlalchemy import select, text  # noqa: E402
from sqlalchemy.engine import make_url  # noqa: E402

from krakenbot.backtest_metrics import METRICS_VERSION  # noqa: E402
from krakenbot.models.market_data import OHLCData, OHLCDerived  # noqa: E402
from krakenbot.replay_contract import REPLAY_VERSION  # noqa: E402
from krakenbot.strategies.multi_strategy_router import _INNER_STRATEGY_CLASSES  # noqa: E402

PROJECT_ROOT = _ROOT

#: Garde-fou 6 (brief, décision 6 ; § A.3 l.237) : borne basse de la fenêtre de la première campagne. Un
#: manifeste dont la fenêtre finit **après** cet instant est refusé tant que le fichier de déverrouillage
#: n'existe pas — ``start ≥ 2021-03-01`` ou ``end > 2021-03-01`` (brief § Lot 3), soit ``end > 2021-03-01``.
CAMPAIGN_START = datetime(2021, 3, 1, tzinfo=UTC)
#: Créé par Bruno à la conversation manifeste, jamais par le producteur ni par ses tests.
CAMPAIGN_UNLOCK = PROJECT_ROOT / "results" / "c3b_producteur" / "CAMPAIGN_UNLOCK"

#: Décision 1 : grid seule — le seul moteur du producteur est ``GridBacktester``.
ENGINE_GRID = "grid"

#: § A.7 v2.1 : le moteur écrit ``_btc`` pour toutes les paires (convention ``btc_held``,
#: ``backtest.py:3288-3293``) ; la couche d'export renomme, liste fermée. ``amount_base`` est écrit
#: directement dans chaque lot reconstruit.
LIQUIDATION_RENAME: Mapping[str, str] = {
    "residual_trade_btc": "residual_trade_base",
    "dust_written_off_btc": "dust_written_off_base",
    "inventory_divergence_btc": "inventory_divergence_base",
}

#: Série quotidienne de ``candles.json`` (§ C.3 : les closes de minuit du comparateur).
DAILY_INTERVAL = 1440


class ProducerRefusal(Exception):
    """Refus d'entrée — code 2 : rien n'est lancé, rien n'est écrit au-delà de ce qui l'était."""

    def __init__(self, reason: str, problems: Sequence[str]) -> None:
        self.reason = reason
        self.problems = list(problems)
        super().__init__(f"{reason}: " + " ; ".join(self.problems))


class ProducerControlError(Exception):
    """Contrôle interne en échec — code 3 : l'artefact ne serait pas ce qu'il prétend être."""

    def __init__(self, control: str, problems: Sequence[str]) -> None:
        self.control = control
        self.problems = list(problems)
        super().__init__(f"{control}: " + " ; ".join(self.problems))


# ---------------------------------------------------------------------------
# Refus d'entrée — tout ce qui se décide avant la première lecture en base
# ---------------------------------------------------------------------------


def campaign_window_locked(start: datetime, end: datetime, *, unlock: Path) -> bool:
    """Garde-fou 6 : vrai si la fenêtre ``[start, end]`` n'est pas entièrement antérieure au 2021-03-01 **et**
    que le fichier de déverrouillage ``unlock`` n'existe pas. ``start`` ne décide rien seul : ``start ≥``
    la borne implique ``end >`` la borne."""
    del start
    return end > CAMPAIGN_START and not unlock.exists()


def non_finite_paths(raw: Any, path: str = "") -> list[str]:
    """Chemins (``a.b[3].c``) des valeurs non finies d'un manifeste brut : flottant ``nan``/``inf``, ou chaîne
    qui se lit comme un décimal non fini (``"NaN"``, ``"inf"``). C'est ce que la canonicalisation de l'identité
    (``cc.candidate_identity`` → ``rc.canon``) refuse dans ``cc.load_manifest`` ; ce parcours ne sert qu'à
    **nommer** la clé du refus."""
    where = path or "<racine>"
    if isinstance(raw, float):
        return [] if math.isfinite(raw) else [where]
    if isinstance(raw, str):
        try:
            value = Decimal(raw)
        except InvalidOperation:
            return []
        return [] if value.is_finite() else [where]
    if isinstance(raw, Mapping):
        found: list[str] = []
        for key, item in raw.items():
            found += non_finite_paths(item, f"{path}.{key}" if path else str(key))
        return found
    if isinstance(raw, list | tuple):
        found = []
        for index, item in enumerate(raw):
            found += non_finite_paths(item, f"{path}[{index}]")
        return found
    return []


def validate_params(params_list: Sequence[Mapping[str, Any]]) -> list[str]:
    """Amendement 2 du lot 3 : ``grid_levels`` entier et ``bias_1d`` fini, **avant** la classmethod.

    ``grid_levels`` : absent (défaut de classe) ou ``type(v) is int`` — ni ``bool``, ni ``float`` (``12.5``
    serait tronqué en silence par ``int()``), ni ``str`` : un manifeste est un JSON typé, la coercition de
    ``"12"`` par la classmethod n'est pas un contrat d'entrée. ``bias_1d`` : absent, ou ``int`` / ``float`` /
    ``str`` (jamais ``bool`` ni ``None``) dont ``Decimal(str(v))`` se lit et est fini — ce que ``__init__``
    fait de la valeur (``grok_grid_atr_adaptive_v4.py:144``). Rend la liste des fautes, chemin nommé.
    """
    problems: list[str] = []
    for index, params in enumerate(params_list):
        where = f"universe.candidates[{index}].params"
        if "grid_levels" in params:
            value = params["grid_levels"]
            if type(value) is not int:
                problems.append(
                    f"{where}.grid_levels: entier attendu (type exact int), reçu "
                    f"{type(value).__name__} {value!r}"
                )
        if "bias_1d" in params:
            value = params["bias_1d"]
            if type(value) not in (int, float, str):
                problems.append(
                    f"{where}.bias_1d: nombre ou décimal en chaîne attendu, reçu "
                    f"{type(value).__name__} {value!r}"
                )
                continue
            try:
                parsed = Decimal(str(value))
            except InvalidOperation:
                problems.append(f"{where}.bias_1d: décimal illisible {value!r}")
                continue
            if not parsed.is_finite():
                problems.append(f"{where}.bias_1d: valeur non finie {value!r}")
    return problems


def decision_timeframes_by_candidate(manifest: cc.Manifest) -> dict[str, list[str]]:
    """``decision_timeframes(params)`` de chaque candidat, **avant tout run** (brief § Lot 3).

    Décision 1 : moteur ``grid`` seul, stratégie résolue dans le registre du projet
    (``multi_strategy_router._INNER_STRATEGY_CLASSES``), classmethod implémentée. Un ``TypeError`` (drapeau non
    booléen), un ``ValueError`` (mode invalide) ou un ``NotImplementedError`` (stratégie non grid) sur **un**
    candidat refuse **tout** l'univers : un run partiel sur un univers mal formé n'existe pas. Sortie triée,
    étiquettes de ``data.timeframes``.
    """
    problems: list[str] = []
    out: dict[str, list[str]] = {}
    for index, candidate in enumerate(manifest.candidates):
        where = f"universe.candidates[{index}]"
        engine = manifest.engines[candidate.strategy]
        if engine != ENGINE_GRID:
            problems.append(
                f"{where}.strategy {candidate.strategy!r}: moteur {engine!r} — le producteur ne lance que "
                "GridBacktester (décision 1)"
            )
            continue
        if candidate.strategy not in _INNER_STRATEGY_CLASSES:
            problems.append(
                f"{where}.strategy {candidate.strategy!r}: absente du registre des stratégies du projet"
            )
            continue
        strategy_cls = _INNER_STRATEGY_CLASSES[candidate.strategy]
        try:
            timeframes = strategy_cls.decision_timeframes(candidate.params)
        except NotImplementedError as exc:
            problems.append(f"{where}.strategy {candidate.strategy!r}: {exc} (décision 1)")
            continue
        except (TypeError, ValueError) as exc:
            problems.append(f"{where}.params: {type(exc).__name__}: {exc}")
            continue
        outside = sorted(set(timeframes) - set(manifest.timeframes))
        if outside:
            problems.append(
                f"{where}: séries de décision {outside} hors de data.timeframes "
                f"{sorted(manifest.timeframes)}"
            )
            continue
        out[candidate.identity] = sorted(timeframes)
    if problems:
        raise ProducerRefusal("decision_timeframes_refused", problems)
    return out


def check_fee_model(manifest: cc.Manifest) -> None:
    """Le modèle de fees du manifeste est celui que le moteur résoudra, au même taker (identités de D6)."""
    try:
        fees, name = bt.resolve_fee_model(manifest.fee_model)
    except (TypeError, ValueError) as exc:
        raise ProducerRefusal(
            "fee_model_refused", [f"fees.model {manifest.fee_model!r}: {exc}"]
        ) from exc
    problems: list[str] = []
    if name != manifest.fee_model:
        problems.append(f"fees.model {manifest.fee_model!r}: le moteur le résout en {name!r}")
    if fees.taker != manifest.taker:
        problems.append(f"fees.taker {manifest.taker} != taker du modèle {name!r} {fees.taker}")
    if problems:
        raise ProducerRefusal("fee_model_refused", problems)


def engine_pair_costs(
    manifest: cc.Manifest, *, root: Path = PROJECT_ROOT
) -> dict[str, bt.PairCosts]:
    """Les coûts de liquidation passés au moteur, **tirés du manifeste** (la seule entrée) et recoupés avec le
    fichier qu'il nomme.

    ``config/pair_costs_b4.json`` ne porte que des paires ``*/USDC`` : sans entrée pour la paire de validation,
    le moteur retomberait sur le spread/slippage du modèle de fees (``backtest.py:2318-2323``) et les identités
    de liquidation (égalités ``Decimal`` exactes) échoueraient. Le recoupement passe par la transposition
    déclarée (§ A.6, ``universe.deployment_pairs``) : les coûts du manifeste pour la paire de validation sont
    ceux du fichier pour sa paire de déploiement. Même nom et même type d'argument que
    ``run_p7_grid_search._engine`` (``:704-717``), valeur construite ici.
    """
    path = root / manifest.pair_costs_file
    try:
        file_costs = bt.load_pair_costs(path)
    except (OSError, ValueError) as exc:
        raise ProducerRefusal(
            "pair_costs_refused", [f"fees.pair_costs_file {manifest.pair_costs_file!r}: {exc}"]
        ) from exc
    problems: list[str] = []
    out: dict[str, bt.PairCosts] = {}
    for pair in manifest.pairs:
        spread, slippage = manifest.pair_costs[pair]
        source = manifest.deployment_pairs[pair] if pair in manifest.deployment_pairs else pair
        if source not in file_costs:
            problems.append(
                f"fees.pair_costs.{pair}: aucune entrée {source!r} dans {manifest.pair_costs_file} "
                "(déclarer la paire de déploiement, § A.6)"
            )
            continue
        declared = (spread, slippage)
        recorded = (file_costs[source].spread, file_costs[source].slippage)
        if declared != recorded:
            problems.append(
                f"fees.pair_costs.{pair} {declared} != {manifest.pair_costs_file}[{source!r}] {recorded}"
            )
            continue
        out[pair] = bt.PairCosts(spread=spread, slippage=slippage)
    if problems:
        raise ProducerRefusal("pair_costs_refused", problems)
    return out


# ---------------------------------------------------------------------------
# Fabrique du moteur et couche d'export
# ---------------------------------------------------------------------------


def build_engine(
    settings: Any,
    db: Any,
    manifest: cc.Manifest,
    candidate: cc.Candidate,
    pair_costs: Mapping[str, bt.PairCosts],
) -> Any:
    """``GridBacktester`` construit avec **les arguments de** ``run_p7_grid_search._engine`` (``:704-717``) :
    deux positionnels (réglages, base) et huit nommés, valeurs lues au manifeste."""
    return bt.GridBacktester(
        settings,
        db,
        strategy_name=candidate.strategy,
        candle_interval=manifest.exec_interval,
        exchange=manifest.exchange,
        starting_capital=float(manifest.capital),
        strategy_params_override=dict(candidate.params),
        fee_model=manifest.fee_model,
        pair_costs=dict(pair_costs),
        min_order_usdc=manifest.min_order_usdc,
    )


def lots_from_trades(trades: Sequence[Any]) -> list[dict[str, str | None]]:
    """Les lots de la liquidation terminale, reconstruits depuis ``metrics.trades`` (brief § Lot 3).

    ``liquidation_summary`` ne porte pas ``lots`` : la liste de ``_force_close_open_positions`` est locale
    (``backtest.py:3185``). Chaque trade ``forced_liquidation`` (``:3124-3146``) est un lot, dans l'ordre :
    ``amount_base = amount_crypto``, ``gross_usdc = amount_usdc``, ``fee``, ``pnl``. Le prix d'entrée inverse
    ``pnl = net − amount × entry_price`` (``:3107``, ``net = gross − fee``) : ``entry_price = (gross − fee −
    pnl) / amount``, ``null`` avec ``pnl`` quand le coût est inconnu. **Exact à la précision du contexte
    ``Decimal`` seulement** (28 chiffres, contexte jamais modifié par le moteur ni la chaîne) ; la chaîne ne
    contrôle que la nullité conjointe de ``entry_price`` et ``pnl`` (``c3_common.py:2061``).
    """
    lots: list[dict[str, str | None]] = []
    for index, trade in enumerate(trades):
        if trade.forced_liquidation is not True:
            continue
        amount: Decimal = trade.amount_crypto
        gross: Decimal = trade.amount_usdc
        fee: Decimal = trade.fee
        pnl: Decimal | None = trade.pnl
        if not amount > 0:
            raise ProducerControlError(
                "liquidation_lots", [f"trades[{index}]: quantité liquidée {amount} non positive"]
            )
        entry = None if pnl is None else (gross - fee - pnl) / amount
        lots.append(
            {
                "amount_base": str(amount),
                "gross_usdc": str(gross),
                "fee": str(fee),
                "pnl": None if pnl is None else str(pnl),
                "entry_price": None if entry is None else str(entry),
            }
        )
    return lots


def liquidation_block(summary: Mapping[str, Any], trades: Sequence[Any]) -> dict[str, Any]:
    """``liquidation[<préfixe>]`` : ``engine.liquidation_summary()`` renommé (§ A.7), plus ``lots``.

    Aucune clé ``_btc`` ne survit ; une collision entre une clé renommée et une clé présente, une clé ``_btc``
    hors de la liste fermée, ou un ``lots`` déjà porté par le moteur sont des contrôles en échec (le moteur
    aurait changé sous le producteur). ``cc.check_base_quantity_keys`` est appliqué au bloc et à chaque lot.
    """
    block: dict[str, Any] = {}
    problems: list[str] = []
    for key, value in summary.items():
        target = LIQUIDATION_RENAME[key] if key in LIQUIDATION_RENAME else key
        if target in block:
            problems.append(f"liquidation: collision sur {target!r}")
        block[target] = value
    leftovers = sorted(key for key in block if key.endswith("_btc"))
    if leftovers:
        problems.append(f"liquidation: clés _btc hors de la liste de renommage {leftovers}")
    if "lots" in block:
        problems.append("liquidation: le moteur porte déjà `lots`")
    if problems:
        raise ProducerControlError("liquidation_rename", problems)
    block["lots"] = lots_from_trades(trades)
    try:
        cc.check_base_quantity_keys(block, where="liquidation")
        for index, lot in enumerate(block["lots"]):
            cc.check_base_quantity_keys(lot, where=f"liquidation.lots[{index}]")
    except cc.MissingEvidenceError as exc:
        raise ProducerControlError("liquidation_rename", [str(exc)]) from exc
    return block


def observation_entry(
    *,
    manifest: cc.Manifest,
    candidate: cc.Candidate,
    anchor: datetime,
    decision_timeframes: Sequence[str],
    pair_costs: bt.PairCosts,
    metrics: Mapping[str, Any],
    equity_daily: Mapping[str, Any] | None,
    liquidation: Mapping[str, Any],
    warmup: Mapping[str, Any],
    rejections: Mapping[str, Any],
    dca_counters: Mapping[str, Any] | None,
    effective_params: Mapping[str, Any] | None,
) -> dict[str, Any]:
    """Une entrée d'observation : le dict ``result`` de ``run_p7_grid_search.py:753-786`` sans ``phase``,
    ``window_idx``, ``test``, ``all`` ni bornes du segment ``test``, avec **un seul** segment — le préfixe du
    manifeste —, plus ``decision_timeframes`` (§ A.8 D2) et ``exec_interval`` (porteur de D5). Aucune
    provenance : elle vit dans ``prefix_run.json``.
    """
    prefix = manifest.prefix_segment
    return {
        "strategy": candidate.strategy,
        "pair": candidate.pair,
        "exchange": manifest.exchange,
        "fees": manifest.fee_model,
        "metrics_version": METRICS_VERSION,
        "replay_version": REPLAY_VERSION,
        "pair_costs_file": manifest.pair_costs_file,
        "pair_costs": {"spread": str(pair_costs.spread), "slippage": str(pair_costs.slippage)},
        "min_order_usdc": manifest.min_order_usdc,
        "effective_params": effective_params,
        "liquidation": {prefix: dict(liquidation)},
        "equity_daily": None if equity_daily is None else {prefix: dict(equity_daily)},
        "rejections": {prefix: dict(rejections)},
        "warmup": {prefix: dict(warmup)},
        "dca_counters": None if dca_counters is None else {prefix: dict(dca_counters)},
        "params": dict(candidate.params),
        "period": {
            f"{prefix}_start": manifest.window_start.isoformat(),
            f"{prefix}_end": anchor.isoformat(),
        },
        prefix: dict(metrics),
        "decision_timeframes": list(decision_timeframes),
        "exec_interval": manifest.exec_interval,
    }


def export_engine(
    engine: Any,
    *,
    manifest: cc.Manifest,
    candidate: cc.Candidate,
    anchor: datetime,
    decision_timeframes: Sequence[str],
    pair_costs: bt.PairCosts,
) -> dict[str, Any]:
    """L'entrée d'observation d'un moteur qui vient de finir son **unique** ``run`` — mêmes accesseurs que
    ``_run_segment`` du runner P7 (``:727-741``)."""
    return observation_entry(
        manifest=manifest,
        candidate=candidate,
        anchor=anchor,
        decision_timeframes=decision_timeframes,
        pair_costs=pair_costs,
        metrics=engine.metrics.to_dict(),
        equity_daily=engine.metrics.equity_daily_dict(),
        liquidation=liquidation_block(engine.liquidation_summary(), engine.metrics.trades),
        warmup=engine.warmup_summary(),
        rejections=engine.rejections_summary(),
        dca_counters=engine.dca_counters_summary(),
        effective_params=engine.effective_params,
    )


def passed_params_problems(
    effective: Any, *, params: Mapping[str, Any], pair: str, where: str
) -> list[str]:
    """E10 (écart du lot 3, partagé par le temps 3 depuis le lot 4a) : ``effective_params.passed_params == params
    + pair``. Le moteur fusionne l'entrée ``strategies.yaml`` de même nom de classe (``backtest.py:2372-2382``) ;
    sans ce contrôle, ``decision_timeframes`` pourrait décrire d'autres paramètres que ceux du run. Rend les
    fautes, préfixées par ``where``."""
    if not isinstance(effective, Mapping) or "passed_params" not in effective:
        return [f"{where}.effective_params: bloc absent ou sans passed_params"]
    expected = {**params, "pair": pair}
    if effective["passed_params"] != expected:
        return [
            f"{where}.effective_params.passed_params {effective['passed_params']!r} != paramètres du "
            f"manifeste + paire {expected!r}"
        ]
    return []


def entry_controls(
    entry: Mapping[str, Any], *, manifest: cc.Manifest, anchor: datetime
) -> list[str]:
    """Contrôles internes d'une entrée exportée (code 3), aucun n'arbitre une clause de la chaîne :

    * E10, ``effective_params.passed_params == params + pair`` (``passed_params_problems``) ;
    * ``cc.liquidation_identities(...)["passed"]`` avec les coûts du manifeste et ``end = T`` : la preuve de D6
      tient sur la sortie du producteur (brief § Lot 3, test de conformité).
    """
    problems: list[str] = []
    identity = cc.candidate_identity(entry["strategy"], entry["pair"], entry["params"])
    where = f"observations.{identity[:16]}"
    problems += passed_params_problems(
        entry["effective_params"], params=entry["params"], pair=entry["pair"], where=where
    )
    prefix = manifest.prefix_segment
    spread, slippage = manifest.pair_costs[entry["pair"]]
    try:
        proof = cc.liquidation_identities(
            entry["liquidation"][prefix],
            spread=spread,
            slippage=slippage,
            taker=manifest.taker,
            end=anchor,
            where=f"{where}.liquidation.{prefix}",
        )
    except (cc.MissingEvidenceError, cc.InvalidValueError) as exc:
        problems.append(str(exc))
    else:
        if proof["passed"] is not True:
            problems.append(f"{where}.liquidation.{prefix}: identités en échec {proof['details']}")
    return problems


# ---------------------------------------------------------------------------
# Artefact de couverture (§ A.7) — oracle de la chaîne, aucune règle recopiée
# ---------------------------------------------------------------------------


def _step(interval: int) -> timedelta:
    return timedelta(days=7) if interval == cc.WEEK_MINUTES else timedelta(minutes=interval)


def expected_stamps(start: datetime, end: datetime, interval: int) -> list[datetime]:
    """La grille attendue ``(start, end]`` de la série, recoupée au compte de ``cc.expected_candles``."""
    stamps: list[datetime] = []
    stamp = cc.first_stamp_strictly_after(start, interval)
    step = _step(interval)
    while stamp <= end:
        stamps.append(stamp)
        stamp += step
    if len(stamps) != cc.expected_candles(start, end, interval):
        raise ProducerControlError(
            "coverage_grid",
            [
                f"série {interval}: {len(stamps)} estampilles énumérées, cc.expected_candles en attend "
                f"{cc.expected_candles(start, end, interval)}"
            ],
        )
    return stamps


@dataclass(frozen=True)
class _Unit:
    """Une unité de D1 : un jour civil entier (5 min, 4 h, 1 j) ou une période hebdomadaire (1 w)."""

    lo: datetime
    hi: datetime
    first_day: date
    last_day: date


def _units(start: datetime, end: datetime, interval: int) -> list[_Unit]:
    """Les unités comptées par ``cc.expected_units`` : jours entiers ``[d, d+1 j]`` inclus dans ``[start,
    end]`` ; ou, pour 1 w, la période ``(M − 7 j, M]`` de chaque estampille ``M`` de ``(start, end]``."""
    units: list[_Unit] = []
    if interval == cc.WEEK_MINUTES:
        for stamp in expected_stamps(start, end, interval):
            lo = stamp - timedelta(days=7)
            units.append(_Unit(lo, stamp, lo.date(), (stamp - timedelta(days=1)).date()))
    else:
        day = start.replace(hour=0, minute=0, second=0, microsecond=0)
        if day < start:
            day += timedelta(days=1)
        while day + timedelta(days=1) <= end:
            units.append(_Unit(day, day + timedelta(days=1), day.date(), day.date()))
            day += timedelta(days=1)
    if len(units) != cc.expected_units(start, end, interval):
        raise ProducerControlError(
            "coverage_units",
            [
                f"série {interval}: {len(units)} unités énumérées, cc.expected_units en attend "
                f"{cc.expected_units(start, end, interval)}"
            ],
        )
    return units


def _unit_covered(unit: _Unit, missing: Sequence[datetime], interval: int) -> bool:
    """Oracle : l'unité est couverte si ``cc.coverage_recompute``, restreint à elle seule, rend une unité
    couverte — la règle D1 (5 min ≥ 144, 4 h les six, 1 j présent, 1 w présente) n'est lue qu'à cet endroit."""
    inside = [stamp for stamp in missing if unit.lo < stamp <= unit.hi]
    expected = cc.expected_candles(unit.lo, unit.hi, interval)
    probe = {
        "expected": expected,
        "observed": expected - len(inside),
        "covered_units": 0,
        "expected_units": 1,
        "missing_stamps": [stamp.isoformat() for stamp in inside],
        "longest_gap_days": cc.gap_days(cc.longest_missing_run(inside, interval), interval),
        "first_day": unit.lo.date().isoformat(),
        "last_day": unit.lo.date().isoformat(),
    }
    result = cc.coverage_recompute(
        probe, start=unit.lo, end=unit.hi, interval=interval, where="unité"
    )
    if result["expected_units_recomputed"] != 1:
        raise ProducerControlError(
            "coverage_units", [f"série {interval}: unité {unit.lo.isoformat()} hors de la règle"]
        )
    covered: int = result["covered_recomputed"]
    return covered == 1


def _unit_key(stamp: datetime, interval: int) -> date | datetime:
    """La clé de l'unité d'une estampille : son estampille pour 1 w (une période par estampille), le jour civil
    qu'elle couvre sinon — ``cc.unit_day_of``, la convention de la chaîne (fin de période)."""
    if interval == cc.WEEK_MINUTES:
        return stamp
    day: date = cc.unit_day_of(stamp, interval)
    return day


def covered_bounds(
    missing: Sequence[datetime], *, start: datetime, end: datetime, interval: int
) -> tuple[str, str]:
    """``first_day`` / ``last_day`` : premier jour de la première unité **couverte** et dernier jour de la
    dernière (§ A.7 l.416, « les premier et dernier jours couverts »), bornés à ``[start, end]``. Aucune unité
    couverte : les deux dates sont indéfinies et la forme en exige deux — refus (candidat v2.2)."""
    units = _units(start, end, interval)
    keys = {unit.hi if interval == cc.WEEK_MINUTES else unit.first_day: unit.hi for unit in units}
    by_unit: dict[datetime, list[datetime]] = {unit.hi: [] for unit in units}
    for stamp in missing:
        key = _unit_key(stamp, interval)
        if key in keys:  # une estampille d'un jour de bord partiel n'appartient à aucune unité
            by_unit[keys[key]].append(stamp)
    covered = [unit for unit in units if _unit_covered(unit, by_unit[unit.hi], interval)]
    if not covered:
        raise ProducerRefusal(
            "coverage_no_covered_unit",
            [
                f"série {interval}: aucune unité couverte sur ({start.isoformat()}, {end.isoformat()}] — "
                "premier et dernier jours couverts indéfinis (§ A.7), candidat v2.2"
            ],
        )
    first = max(covered[0].first_day, start.date())
    last = min(covered[-1].last_day, end.date())
    return first.isoformat(), last.isoformat()


def coverage_series(
    observed: Sequence[datetime],
    derived: Sequence[datetime],
    *,
    start: datetime,
    end: datetime,
    interval: int,
) -> dict[str, Any]:
    """Un bloc de couverture (§ A.7) sur ``(start, end]`` — exactement les clés que ``a07_coverage`` lit.

    Les rows dérivées (``ohlc_derived``) **comptent comme observées** (décision C3 du 23/09) : elles sont dans
    ``market_data_ohlc`` ; une dérivée absente des observées ou une observée hors grille est un contrôle en
    échec. ``covered_units`` est le ``covered_recomputed`` de ``cc.coverage_recompute`` sur le bloc lui-même,
    puis le bloc final doit rendre ``problems == []``.
    """
    if cc.expected_units(start, end, interval) < 1:
        raise ProducerRefusal(
            "coverage_prefix_too_short",
            [f"série {interval}: aucune unité sur ({start.isoformat()}, {end.isoformat()}]"],
        )
    grid = expected_stamps(start, end, interval)
    grid_set = set(grid)
    seen = set(observed)
    problems: list[str] = []
    if len(seen) != len(observed):
        problems.append(f"série {interval}: estampilles observées en double")
    off_grid = sorted(seen - grid_set)
    if off_grid:
        problems.append(
            f"série {interval}: {len(off_grid)} estampille(s) observée(s) hors de la grille (début, T], "
            f"première {off_grid[0].isoformat()}"
        )
    stray = sorted(set(derived) - seen)
    if stray:
        problems.append(
            f"série {interval}: {len(stray)} estampille(s) dérivée(s) absente(s) des observées, première "
            f"{stray[0].isoformat()}"
        )
    if problems:
        raise ProducerControlError("coverage_input", problems)
    missing = [stamp for stamp in grid if stamp not in seen]
    first_day, last_day = covered_bounds(missing, start=start, end=end, interval=interval)
    series: dict[str, Any] = {
        "observed": len(grid) - len(missing),
        "expected": len(grid),
        "covered_units": 0,
        "expected_units": cc.expected_units(start, end, interval),
        "unit": cc.coverage_unit(interval),
        "missing_stamps": [stamp.isoformat() for stamp in missing],
        "longest_gap_days": cc.gap_days(cc.longest_missing_run(missing, interval), interval),
        "first_day": first_day,
        "last_day": last_day,
    }
    where = f"coverage.{interval}"
    draft = cc.coverage_recompute(series, start=start, end=end, interval=interval, where=where)
    series["covered_units"] = draft["covered_recomputed"]
    final = cc.coverage_recompute(series, start=start, end=end, interval=interval, where=where)
    if final["problems"]:
        raise ProducerControlError("coverage_recompute", list(final["problems"]))
    return series


def coverage_artefact(
    observed: Mapping[str, Mapping[int, Sequence[datetime]]],
    derived: Mapping[str, Mapping[int, Sequence[datetime]]],
    *,
    start: datetime,
    end: datetime,
) -> dict[str, Any]:
    """``coverage.json`` : ``{window: {start, end: T}, pairs: {pair: {"5", "240", "1440", "10080"}}}``, rien
    d'autre (les estampilles dérivées vont dans ``prefix_run.json``)."""
    pairs: dict[str, Any] = {}
    for pair in sorted(observed):
        pairs[pair] = {
            str(interval): coverage_series(
                observed[pair][interval],
                derived[pair][interval],
                start=start,
                end=end,
                interval=interval,
            )
            for interval in cc.D1_INTERVALS
        }
    return {"window": {"start": start.isoformat(), "end": end.isoformat()}, "pairs": pairs}


# ---------------------------------------------------------------------------
# Export de bougies (§ L.1 ligne 0, § C.3)
# ---------------------------------------------------------------------------


def _candle_rows(
    rows: Sequence[tuple[datetime, Decimal]], *, start: datetime, end: datetime, where: str
) -> list[dict[str, str]]:
    ordered = sorted(rows, key=lambda row: row[0])
    problems: list[str] = []
    stamps = [stamp for stamp, _ in ordered]
    if len(set(stamps)) != len(stamps):
        problems.append(f"{where}: estampille en double")
    late = [stamp for stamp in stamps if stamp > end]
    if late:
        problems.append(f"{where}: {len(late)} estampille(s) > T, première {late[0].isoformat()}")
    early = [stamp for stamp in stamps if stamp < start]
    if early:
        problems.append(
            f"{where}: {len(early)} estampille(s) < début, première {early[0].isoformat()}"
        )
    for stamp, close in ordered:
        if type(close) is not Decimal:
            problems.append(
                f"{where}.{stamp.isoformat()}: close {type(close).__name__}, Decimal attendu"
            )
            break
        if not (close.is_finite() and close > 0):
            problems.append(f"{where}.{stamp.isoformat()}: close {close} non fini ou non positif")
            break
    if problems:
        raise ProducerControlError("candles", problems)
    return [{"t": stamp.isoformat(), "close": str(close)} for stamp, close in ordered]


def candles_artefact(
    rows: Mapping[str, Mapping[str, Sequence[tuple[datetime, Decimal]]]],
    *,
    start: datetime,
    end: datetime,
    exec_interval: int,
) -> dict[str, Any]:
    """``candles.json`` : ``{pairs: {pair: {exec_interval, exec: [{t, close}], daily: [{t, close}]}}}`` sur
    ``[start, end]``, ``close`` en chaîne de ``Decimal``, triées. Une estampille ``> T``, un doublon ou un close
    non décimal est refusé **par le producteur** (contrôle, code 3), pas seulement par la chaîne."""
    pairs: dict[str, Any] = {}
    for pair in sorted(rows):
        pairs[pair] = {
            "exec_interval": exec_interval,
            "exec": _candle_rows(rows[pair]["exec"], start=start, end=end, where=f"{pair}.exec"),
            "daily": _candle_rows(rows[pair]["daily"], start=start, end=end, where=f"{pair}.daily"),
        }
    return {"pairs": pairs}


# ---------------------------------------------------------------------------
# Base — les seules fonctions qui la touchent (lecture seule, gestionnaire fourni par l'appelant)
# ---------------------------------------------------------------------------


def _utc(stamp: datetime) -> datetime:
    return stamp.astimezone(UTC) if stamp.tzinfo else stamp.replace(tzinfo=UTC)


async def probe_database(db: Any) -> dict[str, Any]:
    """Lecture seule **assertée côté Postgres** et révision Alembic, avant toute autre lecture."""
    async with db.read_session() as session:
        read_only = (await session.execute(text("SHOW transaction_read_only"))).scalar_one()
        if read_only != "on":
            raise RuntimeError(f"transaction_read_only = {read_only!r}, 'on' exigé")
        versions = sorted(
            str(v)
            for v in (
                await session.execute(text("SELECT version_num FROM alembic_version"))
            ).scalars()
        )
    return {"transaction_read_only": str(read_only), "alembic_version": versions}


async def fetch_stamps(
    db: Any, *, exchange: str, pair: str, interval: int, start: datetime, end: datetime
) -> list[datetime]:
    """Estampilles d'une série sur ``(start, end]`` — la grille de ``cc.coverage_recompute``."""
    async with db.read_session() as session:
        result = await session.execute(
            select(OHLCData.timestamp)
            .where(OHLCData.exchange == exchange)
            .where(OHLCData.pair == pair)
            .where(OHLCData.interval == interval)
            .where(OHLCData.timestamp > start)
            .where(OHLCData.timestamp <= end)
            .order_by(OHLCData.timestamp.asc())
        )
        return [_utc(stamp) for stamp in result.scalars()]


async def fetch_closes(
    db: Any, *, exchange: str, pair: str, interval: int, start: datetime, end: datetime
) -> list[tuple[datetime, Decimal]]:
    """Closes d'une série sur ``[start, end]`` (brief § Lot 3, ``candles.json``)."""
    async with db.read_session() as session:
        result = await session.execute(
            select(OHLCData.timestamp, OHLCData.close)
            .where(OHLCData.exchange == exchange)
            .where(OHLCData.pair == pair)
            .where(OHLCData.interval == interval)
            .where(OHLCData.timestamp >= start)
            .where(OHLCData.timestamp <= end)
            .order_by(OHLCData.timestamp.asc())
        )
        return [(_utc(row.timestamp), row.close) for row in result]


async def fetch_derived_stamps(
    db: Any,
    *,
    exchange: str,
    pairs: Sequence[str],
    intervals: Sequence[int],
    start: datetime,
    end: datetime,
) -> dict[str, dict[int, list[datetime]]]:
    """Estampilles de ``ohlc_derived`` sur ``(start, end]`` : comptées observées, recopiées dans
    ``prefix_run.json`` (décision C3 du 23/09)."""
    out: dict[str, dict[int, list[datetime]]] = {
        pair: {interval: [] for interval in intervals} for pair in pairs
    }
    async with db.read_session() as session:
        result = await session.execute(
            select(OHLCDerived.pair, OHLCDerived.interval, OHLCDerived.timestamp)
            .where(OHLCDerived.exchange == exchange)
            .where(OHLCDerived.pair.in_(list(pairs)))
            .where(OHLCDerived.interval.in_(list(intervals)))
            .where(OHLCDerived.timestamp > start)
            .where(OHLCDerived.timestamp <= end)
            .order_by(OHLCDerived.pair, OHLCDerived.interval, OHLCDerived.timestamp)
        )
        for row in result:
            out[str(row.pair)][int(row.interval)].append(_utc(row.timestamp))
    return out


def masked_url(url: str) -> str:
    """L'URL de la base sans son mot de passe (provenance)."""
    return make_url(url).render_as_string(hide_password=True)


# ---------------------------------------------------------------------------
# Écriture
# ---------------------------------------------------------------------------


def stage_json(path: Path, payload: Any) -> tuple[Path, str]:
    """Écrit ``payload`` par ``_common.write_json_strict`` dans un temporaire du répertoire de ``path`` ; rend le
    temporaire et le sha256 du texte. Un refus du writer (type non JSON, non-fini) ne laisse aucun fichier."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    handle, name = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp")
    os.close(handle)
    staged = Path(name)
    try:
        digest = _common.write_json_strict(staged, payload)
    except BaseException:
        staged.unlink(missing_ok=True)
        raise
    return staged, digest


def write_json_atomic(path: Path, payload: Any) -> str:
    """Écriture atomique (``save_result_atomic``-like, réimplémentée ici, jamais importée du runner) : writer
    strict vers un temporaire du même répertoire, puis ``os.replace``."""
    staged, digest = stage_json(path, payload)
    os.replace(staged, path)
    return digest
