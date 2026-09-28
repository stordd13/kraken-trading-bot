"""C3b — producteur, temps 3 (partie 1) : le run d'évaluation ``[T, fin]`` d'un candidat, et ses preuves § B.

Brief : ``agent/AGENT_C3B_PRODUCTEUR.md`` § « Lot 4a » ; plan du lot validé le 2026-09-28. Outillage **hors chaîne**
(§ L.1, ligne 0). Pour **le** candidat retenu par ``c3_select`` (``--selection``), ou pour un candidat désigné
mécaniquement sur une fenêtre hors campagne (``--candidate``), **un seul** ``engine.run(pair, T, fin)`` et les trois
porteurs sans lesquels une évaluation réelle n'est pas admise (§ L.1 v2.1, ``cc.evaluation_admission``) :

* ``flat_start_proof`` (§ B.2, § J item 10) — lue sur le moteur **avant** ``run`` ; elle vaut ``DÉCLARÉ``, jamais
  plus : elle est produite par le programme dont elle décrit l'état ;
* ``invocation.single_call`` (§ B.4) — écrit par le seul chemin qui appelle ``run`` une fois (``run_once``) ;
* ``first_fill_at`` (§ C.3) — la plus petite estampille de ``metrics.trades``, strictement après ``T`` ; ``null``
  sans trade (la chaîne le traite : l'admission le refuse).

Sorties : ``evaluation_run.json`` — intermédiaire, **pas** l'artefact lu par la chaîne (lot 4b) ; ses clés sont
celles de l'artefact d'évaluation moins celles du § F.2 — et ``evaluation_run_provenance.json``, à part.

Ordre des contrôles — tout ce qui précède la base est pur, et un refus n'écrit rien :

1. ``--now`` ; 2. manifeste (``cc.read_json`` + ``cc.load_manifest``, mêmes refus que la chaîne) ; 3. **garde-fou 6**,
   puis, pour ``--candidate``, **garde de désignation** (fenêtre au-delà du 2021-03-01, ``CAMPAIGN_UNLOCK`` ou non) ;
   4. paramètres, séries de décision, fees et coûts (mêmes refus que le préfixe) ; 5. ancrage : amont en succès,
   empreinte du manifeste ; ``T``, paires et fenêtre recoupés au manifeste (code 3) ; 6. cible — sélection : amont en
   succès, empreintes du manifeste et de l'ancrage, retenu recoupé à la tête du classement et à son identité (code
   3), **aucun retenu → 2 « rien à évaluer »** ; désignation : identité de l'univers ; 7. arbre git committé ;
   8. répertoire de sortie ; 9. ``DATABASE_URL``, lecture seule assertée ; 10. moteur, preuve de départ à plat,
   ``run`` unique, export, contrôles internes ; 11. écriture en deux temps (temporaires puis renommage).

Journal : en succès, les événements de ce script ne portent ni identité, ni paire, ni métrique (plan du lot,
point 1) ; le moteur, lui, journalise sa paire (``backtest.py:2884-2890``).

Usage::

    poetry run python scripts/audit/c3b_evaluate.py \\
        --manifest results/c3b_producteur/prefix_conformite/manifest.json \\
        --anchor results/c3b_producteur/prefix_conformite/server/chain/anchor.json \\
        --selection results/c3b_producteur/prefix_conformite/server/chain/selection.json \\
        --output-dir ~/runs/c3b_eval4a/out/select/run1 --now 2026-09-28T00:00:00+00:00

Codes de sortie : 0 évalué ; 2 refus d'entrée, dont « rien à évaluer » ; 3 contrôle interne ou moteur en échec.
Jamais les codes du § I.1, qui appartiennent à la chaîne.
"""

from __future__ import annotations

import argparse
import asyncio
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
import os
from pathlib import Path
import sys
import time
import traceback
from typing import Any

_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(_ROOT / "src"))
sys.path.insert(0, str(_ROOT / "scripts"))
sys.path.insert(0, str(_ROOT / "scripts" / "audit"))

from _common import git_provenance  # noqa: E402
from _db import ReadOnlyDatabaseManager  # noqa: E402
import c3_common as cc  # noqa: E402
import c3_continuity as ccont  # noqa: E402
import c3b_common as c3bc  # noqa: E402
from dotenv import load_dotenv  # noqa: E402
import structlog  # noqa: E402

import krakenbot  # noqa: E402
from krakenbot.backtest_metrics import daily_grid  # noqa: E402
from krakenbot.config.settings import get_settings  # noqa: E402

logger = structlog.get_logger()

PROJECT_ROOT = _ROOT
SCRIPT_RELPATH = "scripts/audit/c3b_evaluate.py"
COMMON_RELPATH = "scripts/audit/c3b_common.py"
SCHEMA = "c3b_evaluate_run/1"
EVALUATION_RUN = "evaluation_run.json"
PROVENANCE = "evaluation_run_provenance.json"
FINAL_ARTEFACTS: tuple[str, ...] = (EVALUATION_RUN, PROVENANCE)
SOURCE_SELECTION = "selection"
SOURCE_DESIGNATION = "designation"
#: § B.2 l.870 : « l'identité ``|net_pnl − (ending_balance − starting_balance)| ≤ 1e-6`` » — nécessaire, pas
#: suffisante (le contre-exemple du texte suit) ; contrôle interne du producteur, jamais une preuve de départ à plat.
NET_PNL_IDENTITY_TOL = 1e-6


# ---------------------------------------------------------------------------
# Entrées : ancrage et cible
# ---------------------------------------------------------------------------


def read_anchor(raw: Any, *, manifest: cc.Manifest, manifest_path: Path) -> datetime:
    """``T`` depuis ``anchor.json``, recoupé au manifeste (brief § Lot 4a). Amont en échec ou empreinte du
    manifeste discordante : refus (2) — ce ne sont pas les entrées d'une même chaîne. ``T``, paires triées ou
    fenêtre différents du recalcul : contrôle en échec (3) — l'ancrage d'un manifeste identique ne peut pas
    différer. Rend ``T`` recalculé (§ A.3 : jamais un paramètre)."""
    if not isinstance(raw, Mapping):
        raise cc.MissingEvidenceError(f"anchor: bloc attendu, reçu {type(raw).__name__}")
    cc.require_upstream_ok(raw, where="anchor")
    mismatch = cc.check_inputs_match(raw, {"manifest": manifest_path}, where="anchor")
    if mismatch:
        raise c3bc.ProducerRefusal("anchor_inputs_mismatch", mismatch)
    declared = cc.require_datetime(raw, "anchor", where="anchor")
    pairs = cc.require_sequence(raw, "pairs", where="anchor")
    window = cc.require_mapping(raw, "window", where="anchor")
    w_start = cc.require_datetime(window, "start", where="anchor.window")
    w_end = cc.require_datetime(window, "end", where="anchor.window")
    anchor = manifest.anchor()
    problems: list[str] = []
    if declared != anchor:
        problems.append(f"anchor.anchor {declared.isoformat()} != T recalculé {anchor.isoformat()}")
    if list(pairs) != sorted(manifest.pairs):
        problems.append(f"anchor.pairs {list(pairs)} != paires triées du manifeste")
    if (w_start, w_end) != (manifest.window_start, manifest.window_end):
        problems.append(
            f"anchor.window [{w_start.isoformat()}, {w_end.isoformat()}] != fenêtre du manifeste"
        )
    if problems:
        raise c3bc.ProducerControlError("anchor_mismatch", problems)
    return anchor


def retained_candidate(
    raw: Any, *, manifest: cc.Manifest, manifest_path: Path, anchor_path: Path
) -> cc.Candidate | None:
    """Le candidat retenu de ``selection.json``, consommé **mécaniquement** : seuls ``retained`` et ``ranking``
    sont lus, jamais le statut ni une métrique. ``None`` quand rien n'est retenu (``retained`` nul, classement
    vide). Amont en échec, empreintes du manifeste ou de l'ancrage discordantes : refus (2). Retenu qui contredit
    la tête du classement (``c3_verdict.py:830`` : le classement fait foi), identité qui ne dérive pas de ses
    champs, ou retenu hors univers : contrôle en échec (3). Les messages ne portent aucune identité."""
    if not isinstance(raw, Mapping):
        raise cc.MissingEvidenceError(f"selection: bloc attendu, reçu {type(raw).__name__}")
    cc.require_upstream_ok(raw, where="selection")
    mismatch = cc.check_inputs_match(
        raw, {"manifest": manifest_path, "anchor": anchor_path}, where="selection"
    )
    if mismatch:
        raise c3bc.ProducerRefusal("selection_inputs_mismatch", mismatch)
    retained = cc.nullable_mapping(raw, "retained", where="selection")
    ranking = cc.require_sequence(raw, "ranking", where="selection")
    for index, item in enumerate(ranking):
        if type(item) is not str:
            raise cc.MissingEvidenceError(
                f"selection.ranking[{index}]: identité attendue, reçu {type(item).__name__}"
            )
    head = ranking[0] if ranking else None
    if retained is None:
        if head is not None:
            raise c3bc.ProducerControlError(
                "selection_inconsistent",
                [
                    "selection.retained nul alors que selection.ranking a une tête (le classement fait foi)"
                ],
            )
        return None
    identity = cc.require_str(retained, "identity", where="selection.retained")
    derived = cc.candidate_identity(
        cc.require_str(retained, "strategy", where="selection.retained"),
        cc.require_str(retained, "pair", where="selection.retained"),
        cc.require_mapping(retained, "params", where="selection.retained"),
    )
    problems: list[str] = []
    if derived != identity:
        problems.append("selection.retained.identity ne dérive pas de strategy / pair / params")
    if head != identity:
        problems.append("selection.retained.identity != tête de selection.ranking")
    candidate = next((c for c in manifest.candidates if c.identity == identity), None)
    if candidate is None:
        problems.append("selection.retained hors de universe.candidates du manifeste")
    if problems:
        raise c3bc.ProducerControlError("selection_inconsistent", problems)
    assert candidate is not None
    return candidate


def designated_candidate(identity: str, *, manifest: cc.Manifest) -> cc.Candidate:
    """``--candidate`` : une identité de l'univers, rien d'autre. La règle de désignation (première identité BTC/ETH
    dans l'ordre lexicographique, plan du lot) est appliquée par l'appelant, déclarée avant le run et recalculée par
    le pilote ; ce script n'en connaît que la garde de fenêtre (``c3bc.designation_window_forbidden``)."""
    candidate = next((c for c in manifest.candidates if c.identity == identity), None)
    if candidate is None:
        raise c3bc.ProducerRefusal(
            "candidate_not_in_universe",
            ["--candidate: identité absente de universe.candidates du manifeste"],
        )
    return candidate


# ---------------------------------------------------------------------------
# Preuves § B
# ---------------------------------------------------------------------------


def capture_flat_start(
    engine: Any, *, capital: Decimal, anchor: datetime
) -> tuple[dict[str, Any], dict[str, Any]]:
    """§ B.2 (l.885-893), § J item 10 : l'état du moteur **après sa construction et avant** ``run`` — donc avant la
    première bougie, quand aucun point d'equity n'existe. Rend ``(flat_start_proof, observé)``.

    Lectures, sur les noms réels de ``GridBacktester.__init__`` : ``usdc_balance`` (``backtest.py:2250``,
    ``Decimal(str(starting_capital))``) et ``btc_held`` (``:2251``) — les deux lectures probantes ;
    ``active_buy_orders`` / ``active_sell_orders`` (``:2268-2269``), ``_strategy_obj`` (``:2257``, créée dans
    ``run`` ``:2893-2895``) et ``metrics.trades`` (``:2291``, défaut vide) — préconditions : sur le chemin grok, les
    ordres vivent dans la stratégie interne, qui n'existe pas avant ``run``, et ``pending`` est vide **par
    construction**.

    ``cash == C`` en ``Decimal`` **numérique** : la fabrique passe ``float(C)`` (``c3b_common.py:302``), le moteur
    stocke ``Decimal(str(float(C)))`` — ``Decimal("1000.0")`` pour ``C = 1000`` ; une comparaison de chaînes
    casserait dès ``1000``, une comparaison en ``float`` passerait sur un ``C`` que le ``float`` ne porte pas.
    Exporté : ``{"at": T, "cash": str(C), "qty": "0", "pending": 0}`` — le ``C`` du manifeste, forme de la
    fixture ``flat_start_proof`` (``test_c3_common.py:1620-1625``). Incohérence : contrôle en échec (3), l'artefact
    ne déclare jamais lui-même une rupture du contrat § B."""
    balance = engine.usdc_balance
    held = engine.btc_held
    buys = len(engine.active_buy_orders)
    sells = len(engine.active_sell_orders)
    strategy_built = engine._strategy_obj is not None
    trades = len(engine.metrics.trades)
    problems: list[str] = []
    if type(balance) is not Decimal:
        problems.append(f"usdc_balance {type(balance).__name__}, Decimal attendu")
    elif balance != capital:
        problems.append(f"usdc_balance {balance} != C = {capital} (égalité Decimal numérique)")
    if type(held) is not Decimal:
        problems.append(f"btc_held {type(held).__name__}, Decimal attendu")
    elif held != 0:
        problems.append(f"btc_held {held} != 0")
    if buys + sells != 0:
        problems.append(f"{buys} ordre(s) d'achat et {sells} de vente en attente avant run")
    if strategy_built:
        problems.append("stratégie interne déjà construite avant run")
    if trades != 0:
        problems.append(f"{trades} trade(s) avant run")
    if problems:
        raise c3bc.ProducerControlError("flat_start_proof", problems)
    observed = {
        "usdc_balance": str(balance),
        "btc_held": str(held),
        "active_buy_orders": buys,
        "active_sell_orders": sells,
        "strategy_built": strategy_built,
        "trades": trades,
    }
    proof = {"at": anchor.isoformat(), "cash": str(capital), "qty": "0", "pending": buys + sells}
    return proof, observed


async def run_once(engine: Any, pair: str, start: datetime, end: datetime) -> dict[str, bool]:
    """§ B.4 : l'évaluation est **un seul appel** ``engine.run(pair, T, fin)``. Seul site qui écrit le bloc
    ``invocation`` : l'assemblage le prend de ce retour, jamais d'ailleurs."""
    await engine.run(pair, start, end)
    return {"single_call": True}


def first_fill_at(trades: Sequence[Any], *, anchor: datetime) -> str | None:
    """§ C.3 : la plus petite estampille de ``metrics.trades`` (achats, ventes et liquidation terminale),
    **strictement** après ``T`` ; ``None`` sans trade. Estampille sans fuseau ou ``≤ T`` : contrôle en échec (3)."""
    if not trades:
        return None
    stamps: list[datetime] = [trade.timestamp for trade in trades]
    naive = [stamp for stamp in stamps if stamp.tzinfo is None]
    if naive:
        raise c3bc.ProducerControlError(
            "first_fill_at", [f"{len(naive)} estampille(s) de trade sans fuseau"]
        )
    first = min(stamps)
    if first <= anchor:
        raise c3bc.ProducerControlError(
            "first_fill_at",
            [f"premier remplissage {first.isoformat()} <= T {anchor.isoformat()} (§ C.3)"],
        )
    return first.isoformat()


def evaluation_controls(
    *,
    metrics: Mapping[str, Any],
    equity_daily: Mapping[str, Any] | None,
    liquidation: Mapping[str, Any],
    anchor: datetime,
    end: datetime,
) -> list[str]:
    """Contrôles internes du run (code 3), aucun n'arbitre une clause de la chaîne :

    * ``|net_pnl − (ending − starting)| ≤ 1e-6`` (§ B.2 l.870) — nécessaire, pas suffisant ;
    * ``equity_daily`` présent, ``start == T``, ``end == fin``, un point par instant de ``cc.daily_grid(T, fin)``
      (la grille que la clause 2 recompte ; ``daily_grid`` est la fonction que ``c3_common`` réexporte, ``:50``) ;
    * ``trades == 0``, ou l'estampille de liquidation dans la cellule quotidienne finale
      (``c3_continuity.stamp_cell_block`` ``== VERIFIED``, § B.4).
    """
    problems: list[str] = []
    gap = abs(metrics["net_pnl"] - (metrics["ending_balance"] - metrics["starting_balance"]))
    if not gap <= NET_PNL_IDENTITY_TOL:
        problems.append(f"|net_pnl − (ending − starting)| = {gap!r} > {NET_PNL_IDENTITY_TOL}")
    if equity_daily is None:
        problems.append("equity_daily absent : aucune série quotidienne exportée par le moteur")
    else:
        start = cc.require_datetime(equity_daily, "start", where="evaluation.equity_daily")
        stop = cc.require_datetime(equity_daily, "end", where="evaluation.equity_daily")
        values = cc.require_sequence(equity_daily, "values", where="evaluation.equity_daily")
        if start != anchor:
            problems.append(f"equity_daily.start {start.isoformat()} != T {anchor.isoformat()}")
        if stop != end:
            problems.append(f"equity_daily.end {stop.isoformat()} != fin {end.isoformat()}")
        expected = len(daily_grid(anchor, end))
        if len(values) != expected:
            problems.append(f"equity_daily: {len(values)} points, grille [T, fin] de {expected}")
    trades = cc.require_int(liquidation, "trades", where="evaluation.liquidation", minimum=0)
    if trades > 0:
        cell = ccont.stamp_cell_block(liquidation, anchor=anchor, end=end)
        if cell["state"] != "VERIFIED":
            problems.append(f"liquidation : {cell['detail']}")
    return problems


def evaluation_payload(
    *,
    candidate: cc.Candidate,
    anchor: datetime,
    end: datetime,
    equity_daily: Mapping[str, Any],
    liquidation: Mapping[str, Any],
    warmup: Mapping[str, Any],
    invocation: Mapping[str, bool],
    first_fill: str | None,
    proof: Mapping[str, Any],
    net_pnl: float,
) -> dict[str, Any]:
    """``evaluation_run.json`` : les clés de l'artefact d'évaluation (fixture ``evaluation``, ``test_c3_common.py:
    1680-1708``) **moins** celles du § F.2 (``returns_config``, ``returns_bench``, ``environment``, ``B``,
    ``replications``) et moins ``cagr_pct`` / ``delta_dd`` dans ``metrics`` — le lot 4b les ajoute. Aucune
    provenance : elle vit dans ``evaluation_run_provenance.json``."""
    return {
        "synthetic": False,
        "strategy": candidate.strategy,
        "pair": candidate.pair,
        "params": dict(candidate.params),
        "period": {"start": anchor.isoformat(), "end": end.isoformat()},
        "equity_daily": dict(equity_daily),
        "liquidation": dict(liquidation),
        "warmup": dict(warmup),
        "invocation": dict(invocation),
        "first_fill_at": first_fill,
        "flat_start_proof": dict(proof),
        "metrics": {"net_pnl": net_pnl},
    }


# ---------------------------------------------------------------------------
# Le run
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Evaluated:
    """Ce que le run rend à ``main`` : l'artefact, l'état lu avant ``run``, la sonde de base et la durée."""

    payload: dict[str, Any]
    observed: dict[str, Any]
    probe: dict[str, Any]
    duration_s: float


async def evaluate(
    url: str,
    manifest: cc.Manifest,
    candidate: cc.Candidate,
    *,
    anchor: datetime,
    pair_costs: Mapping[str, Any],
) -> Evaluated:
    """Un gestionnaire en lecture seule (assertée par Postgres avant tout), le moteur de la fabrique, la preuve
    de départ à plat **avant** ``run``, **un seul** ``run(pair, T, fin)``, l'export et les contrôles. Base
    injoignable ou lecture seule non assertée : refus (2) ; toute autre exception du moteur : contrôle (3)."""
    db = ReadOnlyDatabaseManager(url)
    try:
        try:
            probe = await c3bc.probe_database(db)
        except Exception as exc:  # noqa: BLE001 - base injoignable ou lecture seule non assertée = refus
            raise c3bc.ProducerRefusal(
                "database_read_failed", [f"{type(exc).__name__}: {exc}"]
            ) from exc
        started = time.monotonic()
        end = manifest.window_end
        try:
            engine = c3bc.build_engine(get_settings(), db, manifest, candidate, pair_costs)
            proof, observed = capture_flat_start(engine, capital=manifest.capital, anchor=anchor)
            invocation = await run_once(engine, candidate.pair, anchor, end)
            metrics = engine.metrics.to_dict()
            equity_daily = engine.metrics.equity_daily_dict()
            liquidation = c3bc.liquidation_block(
                engine.liquidation_summary(), engine.metrics.trades
            )
            first_fill = first_fill_at(engine.metrics.trades, anchor=anchor)
            problems = evaluation_controls(
                metrics=metrics,
                equity_daily=equity_daily,
                liquidation=liquidation,
                anchor=anchor,
                end=end,
            )
            problems += c3bc.passed_params_problems(
                engine.effective_params,
                params=candidate.params,
                pair=candidate.pair,
                where="evaluation",
            )
            if problems:
                raise c3bc.ProducerControlError("evaluation_controls", problems)
            assert equity_daily is not None
            payload = evaluation_payload(
                candidate=candidate,
                anchor=anchor,
                end=end,
                equity_daily=equity_daily,
                liquidation=liquidation,
                warmup=engine.warmup_summary(),
                invocation=invocation,
                first_fill=first_fill,
                proof=proof,
                net_pnl=metrics["net_pnl"],
            )
        except c3bc.ProducerControlError:
            raise
        except Exception as exc:  # noqa: BLE001 - un moteur en échec est un contrôle en échec, jamais un refus
            print(traceback.format_exc(), file=sys.stderr)
            raise c3bc.ProducerControlError(
                "engine_failed", [f"{type(exc).__name__}: {exc}"]
            ) from exc
        return Evaluated(payload, observed, probe, round(time.monotonic() - started, 3))
    finally:
        await db.close_db()


# ---------------------------------------------------------------------------
# Provenance et CLI
# ---------------------------------------------------------------------------


def provenance() -> dict[str, Any]:
    """Le commit, la branche et le sha des deux scripts ; refus si l'un n'est pas suivi ou si l'arbre suivi n'est
    pas propre (``uncommitted_tree``, comme ``warmup_at`` et le préfixe)."""
    script = git_provenance(SCRIPT_RELPATH)
    common = git_provenance(COMMON_RELPATH)
    return {
        "git_sha": script["git_sha"],
        "branch": script["branch"],
        "tracked_tree_clean": script["tracked_tree_clean"] and common["tracked_tree_clean"],
        "scripts": {
            SCRIPT_RELPATH: {
                "sha256": script["script_sha256"],
                "tracked": script["script_tracked"],
            },
            COMMON_RELPATH: {
                "sha256": common["script_sha256"],
                "tracked": common["script_tracked"],
            },
        },
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0] if __doc__ else None)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--anchor", type=Path, required=True, help="anchor.json de c3_anchor")
    target = parser.add_mutually_exclusive_group(required=True)
    target.add_argument("--selection", type=Path, default=None, help="selection.json de c3_select")
    target.add_argument(
        "--candidate",
        default=None,
        help="identité désignée mécaniquement — refusée si la fenêtre dépasse le 2021-03-01",
    )
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--now", default=None, help="ISO UTC — n'entre que dans la provenance")
    return parser


def _refuse(reason: str, problems: Sequence[str]) -> int:
    logger.error(reason, problems=list(problems))
    return 2


def _control(control: str, problems: Sequence[str]) -> int:
    logger.error(control, problems=list(problems))
    return 3


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(list(argv) if argv is not None else None)
    # 1. --now
    try:
        now = cc.parse_now(args.now)
    except ValueError as exc:
        return _refuse("invalid_now", [str(exc)])
    # 2. manifeste — mêmes refus que la chaîne
    try:
        raw = cc.read_json(args.manifest)
    except (OSError, ValueError) as exc:
        return _refuse("manifest_unreadable", [f"{args.manifest}: {exc}"])
    try:
        manifest = cc.load_manifest(raw)
    except cc.NonFiniteValueError as exc:
        return _refuse("manifest_refused", [str(exc), *c3bc.non_finite_paths(raw)])
    except (cc.MissingEvidenceError, cc.InvalidValueError) as exc:
        return _refuse("manifest_refused", [str(exc)])
    # 3. garde-fou 6, puis garde de désignation — avant toute autre lecture
    if c3bc.campaign_window_locked(
        manifest.window_start, manifest.window_end, unlock=c3bc.CAMPAIGN_UNLOCK
    ):
        return _refuse(
            "campaign_window_locked",
            [
                f"fenêtre [{manifest.window_start.isoformat()}, {manifest.window_end.isoformat()}] au-delà "
                f"du {c3bc.CAMPAIGN_START.isoformat()} et {c3bc.CAMPAIGN_UNLOCK} absent (garde-fou 6)"
            ],
        )
    if args.candidate is not None and c3bc.designation_window_forbidden(manifest.window_end):
        return _refuse(
            "designation_on_campaign_window",
            [
                f"--candidate sur une fenêtre qui finit le {manifest.window_end.isoformat()}, après le "
                f"{c3bc.CAMPAIGN_START.isoformat()} : sur la campagne, seul le retenu de c3_select s'évalue "
                "(CAMPAIGN_UNLOCK n'y change rien)"
            ],
        )
    # 4. paramètres, séries de décision, fees et coûts
    param_problems = c3bc.validate_params([candidate.params for candidate in manifest.candidates])
    if param_problems:
        return _refuse("invalid_params", param_problems)
    try:
        timeframes = c3bc.decision_timeframes_by_candidate(manifest)
        c3bc.check_fee_model(manifest)
        pair_costs = c3bc.engine_pair_costs(manifest)
    except c3bc.ProducerRefusal as exc:
        return _refuse(exc.reason, exc.problems)
    # 5. ancrage
    try:
        anchor_raw = cc.read_json(args.anchor)
    except (OSError, ValueError) as exc:
        return _refuse("anchor_unreadable", [f"{args.anchor}: {exc}"])
    try:
        anchor = read_anchor(anchor_raw, manifest=manifest, manifest_path=args.manifest)
    except c3bc.ProducerRefusal as exc:
        return _refuse(exc.reason, exc.problems)
    except c3bc.ProducerControlError as exc:
        return _control(exc.control, exc.problems)
    except (cc.MissingEvidenceError, cc.InvalidValueError, cc.NonFiniteValueError) as exc:
        return _refuse("anchor_refused", [str(exc)])
    # 6. cible
    source: dict[str, Any]
    if args.selection is not None:
        try:
            selection_raw = cc.read_json(args.selection)
        except (OSError, ValueError) as exc:
            return _refuse("selection_unreadable", [f"{args.selection}: {exc}"])
        try:
            retained = retained_candidate(
                selection_raw,
                manifest=manifest,
                manifest_path=args.manifest,
                anchor_path=args.anchor,
            )
        except c3bc.ProducerRefusal as exc:
            return _refuse(exc.reason, exc.problems)
        except c3bc.ProducerControlError as exc:
            return _control(exc.control, exc.problems)
        except (cc.MissingEvidenceError, cc.InvalidValueError, cc.NonFiniteValueError) as exc:
            return _refuse("selection_refused", [str(exc)])
        if retained is None:
            return _refuse(
                "nothing_to_evaluate",
                ["selection.retained nul : aucun candidat retenu, rien à évaluer (brief § Lot 4a)"],
            )
        candidate = retained
        source = {
            "kind": SOURCE_SELECTION,
            "path": str(args.selection),
            "sha256": cc.file_sha256(args.selection),
        }
    else:
        try:
            candidate = designated_candidate(args.candidate, manifest=manifest)
        except c3bc.ProducerRefusal as exc:
            return _refuse(exc.reason, exc.problems)
        source = {"kind": SOURCE_DESIGNATION, "identity": candidate.identity}
    # 7. arbre committé
    origin = provenance()
    untracked = [path for path, info in origin["scripts"].items() if info["tracked"] is not True]
    if untracked or origin["tracked_tree_clean"] is not True:
        return _refuse(
            "uncommitted_tree",
            [f"scripts non suivis {untracked}, arbre suivi propre {origin['tracked_tree_clean']}"],
        )
    # 8. répertoire de sortie
    present = [name for name in FINAL_ARTEFACTS if (args.output_dir / name).exists()]
    if present:
        return _refuse("output_dir_not_empty", [f"{args.output_dir}: {present} déjà présent(s)"])
    # 9. base : URL (jamais Settings()), puis lecture seule assertée dans le run
    load_dotenv(PROJECT_ROOT / ".env")
    url = os.getenv("DATABASE_URL")
    if not url:
        return _refuse("database_url_missing", ["DATABASE_URL absente (jamais Settings())"])
    # 10. moteur, preuve, run unique, export, contrôles
    try:
        result = asyncio.run(
            evaluate(url, manifest, candidate, anchor=anchor, pair_costs=pair_costs)
        )
    except c3bc.ProducerRefusal as exc:
        return _refuse(exc.reason, exc.problems)
    except c3bc.ProducerControlError as exc:
        return _control(exc.control, exc.problems)
    # 11. écriture en deux temps
    staged: list[tuple[Path, Path]] = []
    try:
        tmp, run_digest = c3bc.stage_json(args.output_dir / EVALUATION_RUN, result.payload)
        staged.append((tmp, args.output_dir / EVALUATION_RUN))
        provenance_payload = {
            "schema": SCHEMA,
            "generated_at": now.isoformat(),
            "argv": list(sys.argv if argv is None else ["c3b_evaluate.py", *argv]),
            "provenance": origin,
            "manifest": {
                "path": str(args.manifest),
                "sha256": cc.file_sha256(args.manifest),
                "variant_key": cc.sig(raw),
            },
            "anchor": {"path": str(args.anchor), "sha256": cc.file_sha256(args.anchor)},
            "source": source,
            "candidate": {
                "identity": candidate.identity,
                "strategy": candidate.strategy,
                "pair": candidate.pair,
                "decision_timeframes": timeframes[candidate.identity],
                "exec_interval": manifest.exec_interval,
            },
            "window": {"anchor": anchor.isoformat(), "end": manifest.window_end.isoformat()},
            "database": {"url": c3bc.masked_url(url), **result.probe},
            "environment": cc.replay_environment(),
            "interpreter": {"executable": sys.executable, "krakenbot": str(krakenbot.__file__)},
            "outputs": {EVALUATION_RUN: run_digest},
            "flat_start_observed": result.observed,
            "duration_s": result.duration_s,
        }
        tmp, provenance_digest = c3bc.stage_json(args.output_dir / PROVENANCE, provenance_payload)
        staged.append((tmp, args.output_dir / PROVENANCE))
    except (TypeError, ValueError) as exc:
        for tmp, _ in staged:
            tmp.unlink(missing_ok=True)
        return _control("writer_refused", [str(exc)])
    for tmp, final in staged:
        os.replace(tmp, final)
    logger.info("evaluated", source=source["kind"], duration_s=result.duration_s)
    for name, digest in ((EVALUATION_RUN, run_digest), (PROVENANCE, provenance_digest)):
        logger.info("written", path=str(args.output_dir / name), sha256=digest)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
