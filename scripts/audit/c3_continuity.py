"""C3 — le contrat de continuité du portefeuille (§ B), cinq clauses avec l'état de leur vérifiabilité.

Étape 5 de la chaîne du § L.1. Depuis v2.1 (AM-24), une évaluation déclarée réelle est admise si et
seulement si elle porte ses trois porteurs (``flat_start_proof``, ``invocation.single_call``,
``first_fill_at``) — contrôle en tête, refus R0 sinon ; une évaluation synthétique reste admise.
Elle lit le manifeste, l'ancrage, un artefact d'évaluation et le bloc de comparabilité du
comparateur d'évaluation, et écrit ``continuity.json`` — l'état de chaque clause, **jamais une
issue**.

**Ce que vaut chaque état** (§ B.8 v2.1 ; ex-plan § 6.4) : ``VERIFIED`` ne naît que d'identités recalculées ;
**aucune déclaration ne produit ``VERIFIED``** — un bloc déclaratif cohérent avec le contrat vaut
``DECLARED`` ; ``NOT_VERIFIABLE`` est une réponse admissible du protocole (§ B l.723) ; ``FAILED`` est
une preuve fausse, qui n'est jamais admissible.

| Clause | Ce qui la décide |
|---|---|
| c1 — départ à plat à `T` (§ B.2) | ``flat_start_proof = {at, cash, qty, pending}`` (§ B.2 v2.1 ; un nom v2.0 est une erreur de forme) absent → ``NOT_VERIFIABLE`` ; présent et cohérent (``at == T``, cash = C, quantité 0, aucun ordre en attente) → ``DECLARED`` ; incohérent → ``FAILED`` |
| c2 — aucune réinitialisation interne (§ B.4) | ``invocation.single_call`` vrai **et** grille quotidienne continue de `[T, fin]` → ``DECLARED`` ; faux ou grille rompue → ``FAILED`` |
| c3 — liquidation terminale costée (§ B.3) | identités exactes **et preuve par lot** (``cc.liquidation_identities``, la même qu'en sélection) → ``VERIFIED`` ; identités exactes sans lots → ``NOT_VERIFIABLE`` ; bloc absent ou identité fausse → ``FAILED`` ; l'estampille de liquidation et la borne finale dans la même cellule quotidienne (§ B.4) sinon `E_STAMP_MISMATCH` |
| c4 — amorçage à `T` (§ B.5, W-ancrage) | ``sufficient`` recalculé sur chaque série de décision → ``VERIFIED`` / ``FAILED`` ; déclaré ≠ recalculé = violation |
| c5 — première exécution strictement après `T` (§ C.3) | ``first_fill_at`` absent → ``NOT_VERIFIABLE`` ; présent et `> T` → ``DECLARED`` ; `<= T` → ``FAILED`` |

| ``stamp_cell`` — estampille de liquidation dans la cellule quotidienne finale (§ B.4) | dans la cellule → ``VERIFIED`` ; hors cellule → ``FAILED`` ; aucune estampille (bloc absent, ou bloc qui ne liquide rien : `trades == 0`, estampille nulle) → ``NOT_VERIFIABLE``, satisfait à vide au verdict (§ B.4 v2.1) |
| ``comparator`` — comparateur d'évaluation (§ C.5) | conjonction recalculée des tests déclarés **et de la fenêtre recoupée à [T, fin]** (``tests.window_ok``) → ``VERIFIED`` / ``FAILED`` ; ``comparable`` déclaré ≠ conjonction des cinq tests = violation |

**La colonne « ce qui la décide » est une liste close par clause** (`cc.CLAUSE_ADMISSIBLE_STATES`,
revue Fin 2) : c1 {NOT_VERIFIABLE, DECLARED, FAILED}, c2 {DECLARED, FAILED}, c3 {VERIFIED,
NOT_VERIFIABLE, FAILED}, c4 {VERIFIED, FAILED}, c5 {NOT_VERIFIABLE, DECLARED, FAILED}. Un état hors
liste est refusé (code 2, rien publié) ici comme au verdict ; l'agrégat ``VERIFIED`` est donc
inconstructible (§ B.8).

**Les résumés sont dérivés des blocs, jamais recopiés** (revue Fin, défaut 2) :
``warmup_anchor_ok = (c4 == VERIFIED)``, ``liquidation_normalised`` par
``cc.LIQUIDATION_NORMALISED_OF_C3[c3]``, ``stamp_same_daily_cell = (stamp_cell == VERIFIED)``,
``benchmark_comparable = (comparator == VERIFIED)``, ``state = cc.continuity_aggregate(c1..c5)``.
Le consommateur (`c3_verdict`) refait ces dérivations et recoupe chaque résumé déclaré ; une
contradiction est une violation.

Ce que le verdict en fait est écrit là-bas, pas ici : une clause déclarative (c1, c2, c5) en échec
rend l'artefact non recevable ; une clause 3 en échec ou non vérifiable porte ``R1_NOT_NORMALISED``,
portée run (§ I.1 v2.1, ligne 10 bis). Un bloc de liquidation contradictoire (``trades > 0`` sans
estampille ou sans prix) n'est pas une clause 3 en échec : c'est une violation, code 1 (§ B.3 v2.1).

Pure, lecture seule hors de sa sortie. Aucun accès base.

Usage::

    poetry run python scripts/audit/c3_continuity.py \\
        --manifest m.json --anchor anchor.json --evaluation evaluation.json \\
        --benchmark-eval benchmark_eval.json --output continuity.json --now 2026-09-22T00:00:00+00:00

Exit codes: 0 ok, 1 violation, 2 usage ou entrée invalide (§ I.1).
"""

from __future__ import annotations

import argparse
from collections.abc import Mapping, Sequence
from datetime import datetime
from decimal import Decimal
from pathlib import Path
import sys
from typing import Any

_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(_ROOT / "src"))
sys.path.insert(0, str(_ROOT / "scripts"))
sys.path.insert(0, str(_ROOT / "scripts" / "audit"))

import c3_common as cc  # noqa: E402

STEP = "continuity"
CLAUSE_NAMES: dict[str, str] = {
    "c1": "départ à plat à l'ancrage (§ B.2)",
    "c2": "aucune réinitialisation interne (§ B.4)",
    "c3": "liquidation terminale costée (§ B.3)",
    "c4": "amorçage à l'ancrage (§ B.5)",
    "c5": "première exécution strictement après T (§ C.3)",
}
STAMP_CELL_NAME = "estampille de liquidation dans la cellule quotidienne finale (§ B.4)"
COMPARATOR_NAME = "comparateur d'évaluation (§ C.5)"
COMPARABILITY_TESTS = cc.COMPARABILITY_TESTS
#: Ordre de sévérité de l'agrégat : une seule définition, dans `c3_common` (partagée avec le verdict).
SEVERITY = cc.CONTINUITY_SEVERITY
aggregate_state = cc.continuity_aggregate


def _clause(state: str, detail: str) -> dict[str, str]:
    assert state in cc.CONTINUITY_STATES
    return {"state": state, "detail": detail}


# ---------------------------------------------------------------------------
# Les cinq clauses
# ---------------------------------------------------------------------------


#: § B.2 v2.1 (AM-10) — les noms v2.0 de la preuve, qui ne sont plus la preuve spécifiée.
FLAT_START_FIELDS_V20: tuple[str, ...] = ("cash_at_T", "inventory_qty_at_T", "pending_orders_at_T")


def clause_1_flat_start(
    evaluation: Mapping[str, Any], *, capital: Decimal, anchor: datetime
) -> dict[str, str]:
    """§ B.2 v2.1 — la preuve spécifiée `flat_start_proof = {at: T, cash: C, qty: 0, pending: 0}`, capturée
    avant la première bougie du run d'évaluation. Absente → ``NOT_VERIFIABLE`` ; cohérente (``at == T``,
    ``cash == C`` du manifeste, ``qty == 0``, ``pending == 0``) → ``DECLARED``, jamais ``VERIFIED`` (produite
    par le programme qu'elle décrit) ; incohérente → ``FAILED``. Un nom v2.0 est une erreur de forme."""
    proof = cc.optional_mapping(evaluation, "flat_start_proof", where="evaluation")
    if proof is None:
        return _clause(
            "NOT_VERIFIABLE",
            "aucune preuve de départ à plat (`flat_start_proof` absent, § B.2) : aucun point d'equity "
            "n'existe à T, et rien d'autre ne décrit l'état initial",
        )
    where = "evaluation.flat_start_proof"
    legacy = sorted(set(proof) & set(FLAT_START_FIELDS_V20))
    if legacy:
        raise cc.MissingEvidenceError(
            f"{where}: clés v2.0 {legacy} — la preuve spécifiée v2.1 est {{at, cash, qty, pending}} (§ B.2)"
        )
    at = cc.require_datetime(proof, "at", where=where)
    cash = cc.require_decimal(proof, "cash", where=where)
    qty = cc.require_decimal(proof, "qty", where=where)
    pending = cc.require_int(proof, "pending", where=where, minimum=0)
    problems: list[str] = []
    if at != anchor:
        problems.append(f"capturée à {at.isoformat()}, pas à T = {anchor.isoformat()}")
    if cash != capital:
        problems.append(f"cash {cash} ≠ C = {capital}")
    if qty != Decimal(0):
        problems.append(f"quantité {qty} ≠ 0")
    if pending != 0:
        problems.append(f"{pending} ordre(s) en attente")
    if problems:
        return _clause(
            "FAILED",
            " ; ".join(problems) + " — le portefeuille évalué ne démarre pas à plat à T (§ B.2)",
        )
    return _clause(
        "DECLARED",
        f"preuve cohérente avec le contrat (at = T, cash {cash} = C, quantité 0, 0 ordre en attente) — "
        "produite par le programme qu'elle décrit, elle vaut DECLARED, jamais VERIFIED",
    )


def clause_2_no_reset(
    evaluation: Mapping[str, Any], *, anchor: datetime, end: datetime
) -> dict[str, str]:
    invocation = cc.require_mapping(evaluation, "invocation", where="evaluation")
    single = cc.require_bool(invocation, "single_call", where="evaluation.invocation")
    equity = cc.require_mapping(evaluation, "equity_daily", where="evaluation")
    start_declared = cc.require_datetime(equity, "start", where="evaluation.equity_daily")
    end_declared = cc.require_datetime(equity, "end", where="evaluation.equity_daily")
    values = cc.require_finite_series(equity, "values", where="evaluation.equity_daily", min_len=2)
    expected = len(cc.daily_grid(anchor, end))
    problems: list[str] = []
    if not single:
        problems.append("invocation.single_call est faux : l'évaluation n'est pas un seul appel")
    if start_declared != anchor or end_declared != end:
        problems.append(
            f"grille [{start_declared.isoformat()}, {end_declared.isoformat()}] != [{anchor.isoformat()}, {end.isoformat()}]"
        )
    if len(values) != expected:
        problems.append(f"{len(values)} points sur une grille quotidienne de {expected}")
    if problems:
        return _clause("FAILED", " ; ".join(problems))
    return _clause(
        "DECLARED",
        f"un seul appel déclaré, grille quotidienne continue de {expected} points sur [T, fin] — "
        "la convention d'appel est déclarée, son intégration relève de C3b",
    )


def clause_3_costed_liquidation(
    evaluation: Mapping[str, Any],
    *,
    spread: Decimal,
    slippage: Decimal,
    taker: Decimal,
    anchor: datetime,
    end: datetime,
) -> tuple[dict[str, str], dict[str, Any], dict[str, str]]:
    """(clause c3, rapport D6, bloc ``stamp_cell``). Les résumés se dérivent des états, ici comme
    chez le consommateur — rien n'est renvoyé en double."""
    block = cc.optional_mapping(evaluation, "liquidation", where="evaluation")
    proof = cc.liquidation_identities(
        block,
        spread=spread,
        slippage=slippage,
        taker=taker,
        end=end,
        where="evaluation.liquidation",
    )
    stamp_cell = stamp_cell_block(block, anchor=anchor, end=end)
    if block is None:
        return _clause("FAILED", proof["details"][0]), proof, stamp_cell
    exact_failed = [k for k, v in proof["checks"].items() if v is False and k != "lots_present"]
    if exact_failed:
        return _clause("FAILED", " ; ".join(proof["details"])), proof, stamp_cell
    if not proof["lots_present"]:
        return (
            _clause(
                "NOT_VERIFIABLE",
                "identités exactes satisfaites mais aucun lot exporté : la magnitude du taker est "
                "indécidable sur l'export agrégé (exigence C3b : export des lots)",
            ),
            proof,
            stamp_cell,
        )
    return _clause("VERIFIED", "liquidation terminale costée, prouvée par lot"), proof, stamp_cell


def stamp_cell_block(
    block: Mapping[str, Any] | None, *, anchor: datetime, end: datetime
) -> dict[str, str]:
    """§ B.4 — l'estampille de liquidation et la borne finale dans la même cellule quotidienne.

    Aucune estampille (bloc absent, ou bloc qui ne liquide rien : ``trades == 0``, ``timestamp`` nul) →
    ``NOT_VERIFIABLE`` ; dans la cellule → ``VERIFIED`` ; hors cellule → ``FAILED``. Le verdict en dérive
    ``stamp_same_daily_cell`` (``VERIFIED`` seulement) et la raison ``E_STAMP_MISMATCH`` sur ``FAILED``
    seulement : ``NOT_VERIFIABLE`` satisfait l'assertion à vide (§ B.4 v2.1).
    """
    if block is None:
        return _clause("NOT_VERIFIABLE", "aucun bloc de liquidation, aucune estampille à situer")
    stamp = cc.nullable_datetime(block, "timestamp", where="evaluation.liquidation")
    if stamp is None:
        return _clause("NOT_VERIFIABLE", "estampille de liquidation nulle, rien à situer")
    grid = cc.daily_grid(anchor, end)
    same_cell = grid[-2] < stamp <= end if len(grid) >= 2 else stamp == end
    if same_cell:
        return _clause(
            "VERIFIED",
            f"estampille {stamp.isoformat()} dans la cellule finale de {end.isoformat()}",
        )
    return _clause(
        "FAILED",
        f"estampille {stamp.isoformat()} hors de la cellule quotidienne finale de {end.isoformat()} (§ B.4)",
    )


def clause_4_warmup_at_anchor(
    evaluation: Mapping[str, Any], *, timeframes: Sequence[str], violations: list[str]
) -> dict[str, str]:
    warmup = cc.require_mapping(evaluation, "warmup", where="evaluation")
    if not timeframes:
        # § B.8 c4 : VERIFIED = sufficient recalculé « sur chaque TF de décision » — sans série il
        # n'y a rien de recalculé, donc rien de vérifié.
        raise cc.MissingEvidenceError(
            "evaluation.warmup: aucune série de décision (decision_timeframes vide) — rien à recalculer"
        )
    insufficient: list[str] = []
    for tf in timeframes:
        block = cc.require_mapping(warmup, tf, where="evaluation.warmup")
        recomputed, declared = cc.warmup_sufficient(block, where=f"evaluation.warmup.{tf}")
        if recomputed != declared:
            violations.append(
                f"evaluation.warmup.{tf}.sufficient déclaré {declared!r}, recalculé {recomputed!r}"
            )
        if not recomputed:
            insufficient.append(tf)
    if insufficient:
        return _clause(
            "FAILED", f"amorçage insuffisant à T sur {', '.join(insufficient)} (W-ancrage, § B.5)"
        )
    return _clause("VERIFIED", f"amorçage recalculé suffisant sur {', '.join(timeframes)}")


def clause_5_first_execution(evaluation: Mapping[str, Any], *, anchor: datetime) -> dict[str, str]:
    raw = cc.optional_str(evaluation, "first_fill_at", where="evaluation")
    if raw is None:
        return _clause(
            "NOT_VERIFIABLE",
            "les runners n'exportent pas l'instant du premier remplissage ; la propriété tient par "
            "construction des moteurs (§ A.4), sans preuve dans l'artefact",
        )
    stamp = cc.parse_datetime(raw, where="evaluation.first_fill_at")
    if stamp > anchor:
        return _clause(
            "DECLARED", f"premier remplissage déclaré à {stamp.isoformat()}, strictement après T"
        )
    return _clause(
        "FAILED", f"premier remplissage déclaré à {stamp.isoformat()}, à T ou avant (§ C.3)"
    )


def comparator_block(
    block: Mapping[str, Any], *, anchor: datetime, end: datetime, violations: list[str]
) -> dict[str, Any]:
    """§ C.5 — le bloc ``comparator`` : les tests déclarés, la **fenêtre recoupée à [T, fin]**, l'état
    dérivé de leur conjonction, et le ``comparable`` déclaré recoupé.

    La fenêtre (revue Fin, défaut 3) n'est pas un test que le producteur peut asserter — il ne
    connaît pas T : C3a la **recalcule** depuis l'ancre et le manifeste et l'ajoute à la conjonction
    sous ``tests.window_ok``. Le ``comparable`` déclaré est recoupé à la conjonction des cinq tests
    déclarés (ce que le producteur affirme) ; une fenêtre discordante rend le comparateur ``FAILED``
    (voie ``E_NO_BENCHMARK``), sans violation. Le verdict refait les deux dérivations depuis
    ``tests`` et ``window``.
    """
    tests_block = cc.require_mapping(block, "comparability", where="benchmark_eval")
    # Revue Fin (5) : les cinq booléens sont lus et typés **tous**, la conjonction vient après —
    # un `all()` paresseux court-circuitait avant une clé absente (code 2 devenu code 0).
    tests: dict[str, bool] = {
        name: cc.require_bool(tests_block, name, where="benchmark_eval.comparability")
        for name in COMPARABILITY_TESTS
    }
    recomputed = all(tests.values())
    declared = cc.require_bool(block, "comparable", where="benchmark_eval")
    window = cc.require_mapping(block, "window", where="benchmark_eval")
    w_start = cc.require_datetime(window, "start", where="benchmark_eval.window")
    w_end = cc.require_datetime(window, "end", where="benchmark_eval.window")
    window_ok = (w_start, w_end) == (anchor, end)
    tests["window_ok"] = window_ok
    if declared != recomputed:
        violations.append(
            f"benchmark_eval.comparable déclaré {declared!r}, conjonction recalculée des tests § C.5 {recomputed!r}"
        )
    comparable = recomputed and window_ok
    failed = [name for name, ok in tests.items() if ok is False]
    return {
        **_clause(
            "VERIFIED" if comparable else "FAILED",
            "comparateur d'évaluation comparable (§ C.5), fenêtre [T, fin] recoupée"
            if comparable
            else f"tests § C.5 en échec : {', '.join(failed)}",
        ),
        "tests": tests,
        "window": {
            "declared": {"start": w_start.isoformat(), "end": w_end.isoformat()},
            "expected": {"start": anchor.isoformat(), "end": end.isoformat()},
        },
        "declared_comparable": declared,
    }


def benchmark_comparable(
    block: Mapping[str, Any], *, anchor: datetime, end: datetime, violations: list[str]
) -> bool:
    """Compatibilité : la conjonction recalculée (fenêtre comprise), dérivée du bloc ``comparator``."""
    return (
        comparator_block(block, anchor=anchor, end=end, violations=violations)["state"]
        == "VERIFIED"
    )


# ---------------------------------------------------------------------------
# Le run
# ---------------------------------------------------------------------------


def run_continuity(
    manifest: cc.Manifest,
    anchor_raw: Mapping[str, Any],
    evaluation: Mapping[str, Any],
    benchmark_eval: Mapping[str, Any],
    *,
    violations: list[str],
) -> dict[str, Any]:
    # § L.1 v2.1 (AM-24) : l'admission de l'évaluation, en tête — une évaluation réelle sans l'un de ses trois
    # porteurs est refusée R0, code 2, rien publié, avec le nom de ce qui manque.
    synthetic = cc.evaluation_admission(evaluation)
    anchor = manifest.anchor()
    declared_anchor = cc.require_datetime(anchor_raw, "anchor", where="anchor")
    if declared_anchor != anchor:
        violations.append(
            f"anchor.anchor déclaré {declared_anchor.isoformat()}, recalculé {anchor.isoformat()}"
        )
    end = manifest.window_end
    strategy = cc.require_str(evaluation, "strategy", where="evaluation")
    pair = cc.require_str(evaluation, "pair", where="evaluation")
    params = cc.require_mapping(evaluation, "params", where="evaluation")
    identity = cc.candidate_identity(strategy, pair, params)
    candidate = next((c for c in manifest.candidates if c.identity == identity), None)
    if candidate is None:
        raise cc.EntryRefusedError(
            "R0_INVALID_RUN",
            f"évaluation d'une configuration {identity[:16]} hors de l'univers du manifeste",
        )
    if pair not in manifest.pair_costs:
        raise cc.MissingEvidenceError(f"evaluation.pair: {pair!r} sans coûts déclarés")
    period = cc.require_mapping(evaluation, "period", where="evaluation")
    p_start = cc.require_datetime(period, "start", where="evaluation.period")
    p_end = cc.require_datetime(period, "end", where="evaluation.period")
    if (p_start, p_end) != (anchor, end):
        raise cc.EntryRefusedError(
            "R0_INVALID_RUN",
            f"evaluation.period [{p_start.isoformat()}, {p_end.isoformat()}] != [T, fin] = [{anchor.isoformat()}, {end.isoformat()}]",
        )
    bench_pair = cc.require_str(benchmark_eval, "pair", where="benchmark_eval")
    if bench_pair != pair:
        raise cc.EntryRefusedError(
            "R0_INVALID_RUN", f"benchmark_eval.pair {bench_pair!r} != evaluation.pair {pair!r}"
        )
    spread, slippage = manifest.pair_costs[pair]
    c1 = clause_1_flat_start(evaluation, capital=manifest.capital, anchor=anchor)
    c2 = clause_2_no_reset(evaluation, anchor=anchor, end=end)
    c3, d6_report, stamp_cell = clause_3_costed_liquidation(
        evaluation, spread=spread, slippage=slippage, taker=manifest.taker, anchor=anchor, end=end
    )
    c4 = clause_4_warmup_at_anchor(
        evaluation, timeframes=candidate.decision_timeframes, violations=violations
    )
    c5 = clause_5_first_execution(evaluation, anchor=anchor)
    comparator = comparator_block(benchmark_eval, anchor=anchor, end=end, violations=violations)
    clauses = {"c1": c1, "c2": c2, "c3": c3, "c4": c4, "c5": c5}
    states = {k: v["state"] for k, v in clauses.items()}
    # Revue Fin 2 (1) : la table du § B.8 s'applique en liste close côté producteur aussi — un état
    # hors de la liste de sa clause n'est jamais publié (code 2), quelle que soit son origine.
    for key, state in states.items():
        if state not in cc.CLAUSE_ADMISSIBLE_STATES[key]:
            raise cc.MissingEvidenceError(
                f"continuity.clauses.{key}.state: {state!r} hors liste close "
                f"{list(cc.CLAUSE_ADMISSIBLE_STATES[key])} (§ B.8)"
            )
    for name, block, allowed in (
        ("stamp_cell", stamp_cell, cc.STAMP_CELL_ADMISSIBLE_STATES),
        ("comparator", comparator, cc.COMPARATOR_ADMISSIBLE_STATES),
    ):
        if block["state"] not in allowed:
            raise cc.MissingEvidenceError(
                f"continuity.{name}.state: {block['state']!r} hors liste close {list(allowed)}"
            )
    # Les résumés sont **dérivés** des blocs (revue Fin, défaut 2) ; le verdict refait ces
    # dérivations et recoupe chaque résumé déclaré.
    return {
        "synthetic": synthetic,
        "strategy": strategy,
        "pair": pair,
        "identity": identity,
        "evaluation_window": {"start": anchor.isoformat(), "end": end.isoformat()},
        "clauses": {k: {"name": CLAUSE_NAMES[k], **v} for k, v in clauses.items()},
        "stamp_cell": {"name": STAMP_CELL_NAME, **stamp_cell},
        "comparator": {"name": COMPARATOR_NAME, **comparator},
        "state": cc.continuity_aggregate(states),
        "warmup_anchor_ok": states["c4"] == "VERIFIED",
        "benchmark_comparable": comparator["state"] == "VERIFIED",
        "stamp_same_daily_cell": stamp_cell["state"] == "VERIFIED",
        "liquidation_normalised": cc.LIQUIDATION_NORMALISED_OF_C3[states["c3"]],
        "d6_report": d6_report,
        "note": "aucune déclaration ne produit VERIFIED ; « non vérifiable » est une réponse admissible, une preuve fausse ne l'est pas (§ B)",
    }


def render_lines(payload: Mapping[str, Any]) -> list[str]:
    if payload["invalide"]:
        return ["ARTEFACT INVALIDE — continuité non publiée"] + [
            f"  violation : {v}" for v in payload["violations"]
        ]
    out = [
        f"continuité de {payload['identity'][:16]} ({payload['pair']}) sur "
        f"[{payload['evaluation_window']['start']}, {payload['evaluation_window']['end']}] — état {payload['state']}"
        + (" — évaluation synthétique" if payload["synthetic"] else "")
    ]
    for key, clause in payload["clauses"].items():
        out.append(f"  {key} {clause['state']:<14} {clause['name']} : {clause['detail']}")
    for key in ("stamp_cell", "comparator"):
        block = payload[key]
        out.append(f"  {key} {block['state']:<14} {block['name']} : {block['detail']}")
    out.append(
        f"  amorçage à T {payload['warmup_anchor_ok']} · comparateur {payload['benchmark_comparable']} · "
        f"cellule d'estampille {payload['stamp_same_daily_cell']} · liquidation normalisée {payload['liquidation_normalised']}"
    )
    return out


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    for name in ("manifest", "anchor", "evaluation", "benchmark-eval", "output"):
        parser.add_argument(f"--{name}", type=Path, required=True)
    parser.add_argument(
        "--now", default=None, help="Horodatage ISO UTC de generated_at, pour le déterminisme."
    )
    return parser


INPUT_NAMES: tuple[str, ...] = ("manifest", "anchor", "evaluation", "benchmark_eval")


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(list(argv) if argv is not None else None)
    try:
        now = cc.parse_now(args.now)
    except ValueError as exc:
        print(f"--now: {exc}", file=sys.stderr)
        return 2
    raws: dict[str, Any] = {}
    for name in INPUT_NAMES:
        try:
            raws[name] = cc.read_json(getattr(args, name))
        except (OSError, ValueError) as exc:
            print(f"--{name.replace('_', '-')}: {exc}", file=sys.stderr)
            return 2
    inputs = {name: getattr(args, name) for name in INPUT_NAMES}

    violations: list[str] = []
    core: dict[str, Any] | None = None
    try:
        manifest = cc.load_manifest(raws["manifest"])
        cc.require_upstream_ok(raws["anchor"], where="anchor")
        violations += cc.check_inputs_match(
            raws["anchor"], {"manifest": args.manifest}, where="anchor"
        )
        for name in ("evaluation", "benchmark_eval"):
            if not isinstance(raws[name], Mapping):
                raise cc.MissingEvidenceError(f"{name}: bloc attendu")
        core = run_continuity(
            manifest,
            raws["anchor"],
            raws["evaluation"],
            raws["benchmark_eval"],
            violations=violations,
        )
    except cc.EntryRefusedError as exc:
        if violations:
            violations.append(f"refus d'entrée constaté après violation : {exc}")
        else:
            print(f"ENTREE REFUSEE {exc}", file=sys.stderr)
            return 2
    except cc.MissingEvidenceError as exc:
        print(f"ENTREE INVALIDE {exc}", file=sys.stderr)
        return 2
    except (cc.InvalidValueError, cc.NonFiniteValueError) as exc:
        # Non fini fourni ou atteignant la canonicalisation : violation, code 1 (revue R3 d).
        violations.append(str(exc))

    if violations:
        payload = cc.envelope(STEP, now, inputs, exit_code=1, violations=violations)
        payload.update({"state": None, "clauses": {}, "diagnostic": core})
        digest = cc.write_json(args.output, payload)
        print("\n".join(render_lines(payload)))
        print(f"written {args.output} sha256 {digest}")
        for violation in violations:
            print(f"VIOLATION {violation}", file=sys.stderr)
        return 1
    assert core is not None
    payload = cc.envelope(STEP, now, inputs, exit_code=0)
    payload.update(core)
    digest = cc.write_json(args.output, payload)
    print("\n".join(render_lines(payload)))
    print(f"written {args.output} sha256 {digest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
