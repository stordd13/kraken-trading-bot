"""C3 — l'issue, la chaîne de verdict et l'orchestration (§ G, § H, § I.1, § L.2).

Ce script n'a **aucun paramètre libre et aucune entrée humaine** : deux personnes l'exécutant sur
les mêmes artefacts obtiennent **la même chaîne**. C'est le contrat de falsifiabilité du protocole
(§ 0.6), et le rapport **cite** la chaîne au lieu de la paraphraser.

Ce qu'il fait, dans l'ordre gelé :

* § I.1 — les raisons de niveau run sont collectées, et la chaîne porte **la première de la liste de
  priorité du § H qui s'applique**. La portée d'une raison n'est ni redite ici ni transcrite dans une
  table raison → portée : elle se lit dans la **ligne du § I.1 qui s'applique** — une même raison
  peut être de portée candidat ou run selon la ligne (`F_NOT_ESTIMABLE`, lignes 6 et 13). Ce script
  n'émet que des raisons de niveau run ; l'ordre de son code suffit à dire que `F_CANNOT_SEPARATE`
  se constate **après** que les portes ont été franchies.
* **§ H.0 — la préséance de l'estimabilité sur le verdict économique.** Tant que `E1` et `E2` ne
  sont pas satisfaites, **ni ``validé`` ni ``réfuté``** ne peuvent être prononcés, quel que soit le
  résultat des portes `Q1`, `Q2`, `Q3` : l'issue est ``inconclusif (F_NOT_ESTIMABLE)``.
* § H.1 — les trois issues en conditions nécessaires et suffisantes.
* § A.5 — un univers ``contaminated`` **ou ``unknown``** ne peut porter ni ``validé`` ni ``réfuté``.

Les statuts sont **recalculés** depuis les artefacts et **recoupés** contre ceux qu'ils portent :
un désaccord est une **violation** (exit 1), jamais une valeur recopiée.

**Fin de chaîne § L.2.** La chaîne porte **neuf champs** — issue, raison, identité retenue, statut de
sélection, état de la continuité, identité de variante (la clé ``sig(canon(manifeste))``,
plan § 4 l.5′), provenance, sha256 du protocole, sha256 des observations. ``verdict.json`` porte les
empreintes de ses cinq entrées (``inputs_sha256``) dans ses deux formes, normale et diagnostic ;
``verify_chain`` exige le succès enregistré de chaque amont et recoupe leurs empreintes entre elles et
avec les fichiers fournis — une discordance est une violation. Les empreintes **détectent une
discordance** ; elles ne prouvent pas que l'invocation courante a réussi : c'est le rôle de la
sous-commande ``chain``, qui invoque chaque étape en processus et **contrôle son code de retour
effectif** avant le verdict (plan § 5.3).

**``chain.verified`` — définition fixée (revue Fin 2).** ``chain.verified`` signifie l'**intégrité
mécanique de la chaîne** : codes de succès enregistrés des amonts, cohérence interne de chaque
enveloppe amont, empreintes concordantes. Il ne porte pas la qualité économique de l'issue — elle se
lit dans ``verdict`` / ``raison``. Donc ``verified: true`` avec un ``inconclusif`` (``E_NO_BENCHMARK``,
``F_NOT_ESTIMABLE``, abstention…) est cohérent ; ``verified: false`` sur **toute** violation (de
chaîne ou non) **ou refus** — un refus sans violation ne publie rien (aucun ``verified`` à porter) ;
un refus consigné après une violation publie un diagnostic, qui porte ``verified: false``.

**Précédence violation → issue non définie (revue Fin 2).** Une contradiction déclaré / dérivé
constatée est un diagnostic code 1 (``invalide: true``, violations listées), même quand la clause 3
est en échec ; le refus 2 ``UndefinedIssueError`` reste réservé au cas cohérent (c3 en échec,
résumés et agrégat concordants) — c'est lui que la convention datée couvre. **Règle générale :
l'ordre de constat** — après une violation, la violation prime (diagnostic, code 1), qu'un refus ou
une issue non définie survienne ensuite ; **sauf lecture inachevable** : une preuve obligatoire
absente, nulle, mal typée ou hors liste close constatée après une violation sort en code 2, rien
publié, les violations dites sur stderr — **convention d'outillage datée du 22/09** (validation Fin),
fondement : un diagnostic se bâtit sur une lecture complète ; clarification normative au paquet C3b.
Le « précédent du chantier 0 » couvre le refus de contrat évalué **avant toute lecture** (``B``
hors contrat → 2), pas cet ordre de constat.

**Continuité → verdict (plan § 6.4, validé ; revue Fin, défaut 2).** Les résumés
(``warmup_anchor_ok``, ``benchmark_comparable``, ``stamp_same_daily_cell``, ``liquidation_normalised``)
et l'agrégat sont **dérivés des clauses par le consommateur** et recoupés au déclaré — une
contradiction est une violation ; les actions se branchent sur les clauses, jamais sur les résumés.
Clauses déclaratives c1/c2/c5 ``FAILED`` : l'artefact
déclare lui-même une rupture du contrat § B → refus ``R0_INVALID_RUN``, code 2. Clause 3 ``FAILED``
(liquidation terminale non normalisée) : § B.3 et § G.2 interdisent tout verdict directionnel et § I.1
ne porte aucune ligne de portée run pour ce cas → ``UndefinedIssueError`` — **convention d'outillage
datée du 21/09** (plan révisé § 6.1, hors dépôt, conduite (b) ; rapport de session § 7), une
assignation de code hors table assumée comme telle ; l'amendement daté (a) est dû à l'ouverture de
C3b. Sa sortie (code 2, rien publié) ne vaut que pour le cas **cohérent** — voir la précédence
ci-dessus.

**Confinement des verdicts synthétiques (plan § 6.6, validé).** § L.1 : sur données réelles, C3a ne
peut produire que non-recevabilité et abstention ; ``validé`` / ``réfuté`` sont structurellement
inatteignables tant que C3b n'a pas livré l'exécution continue et la preuve de départ à plat.
L'outillage l'exécute : ``evaluation.synthetic`` est **obligatoire et strictement typé** ; ``false``
(évaluation réelle) est **refusé** (code 2, rien publié) ; ``true`` préfixe la chaîne ``C3_SYNTH_``
et écrit ``portee`` en première ligne. Ce contrôle est le **premier** de ``decide()`` et de
``run_verdict()`` : aucun chemin de publication — verdict calculé, abstention, diagnostic — ne le
précède (revue Fin, défaut 1).

Pure, read-only hors de sa sortie. Aucun accès base de données.

Usage::

    poetry run python scripts/audit/c3_verdict.py \\
        --entry entry.json --anchor anchor.json --selection selection.json \\
        --continuity continuity.json --evaluation evaluation.json --output verdict.json

    poetry run python scripts/audit/c3_verdict.py chain \\
        --manifest m.json --observations o.json --coverage c.json --candles k.json \\
        --evaluation e.json --benchmark-eval b.json --registry variants.json --out-dir out/

Exit codes: 0 ok, 1 violation, 2 usage ou entrée invalide (§ I.1).
"""

from __future__ import annotations

import argparse
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
import sys
from typing import Any

_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(_ROOT / "src"))
sys.path.insert(0, str(_ROOT / "scripts"))
sys.path.insert(0, str(_ROOT / "scripts" / "audit"))

import c3_common as cc  # noqa: E402

STEP = "verdict"
INPUT_NAMES: tuple[str, ...] = ("entry", "anchor", "selection", "continuity", "evaluation")
SYNTH_PREFIX = "C3_SYNTH_"
PORTEE_SYNTH = "exercice synthétique de l'outillage — aucune portée économique (§ L.1)"
#: Convention d'outillage datée du 21/09 (plan § 6.1, conduite (b)) — le message cité par le test.
UNDEFINED_ISSUE_MOTIF = (
    "issue non définie par le texte gelé, amendement pendant (§ 6.1) : liquidation terminale non "
    "normalisée sur l'artefact d'évaluation — § B.3 et § G.2 interdisent tout verdict directionnel, "
    "§ I.1 ne porte aucune ligne de portée run pour ce cas"
)
#: Le motif, puis la conduite (b) de la convention datée — celle-ci ne s'applique qu'au cas cohérent.
UNDEFINED_ISSUE_MESSAGE = (
    f"{UNDEFINED_ISSUE_MOTIF} ; convention d'outillage datée du 21/09 : "
    "refus de produire une issue, code 2, rien publié"
)
ABSTENTION_REASONS: tuple[str, ...] = ("A_NO_ADMISSIBLE_CANDIDATE", "A_BELOW_FLOOR")
REAL_EVALUATION_MESSAGE = (
    "évaluation réelle non exerçable par l'outillage C3a — § L.1 : l'exécution continue et la preuve "
    "de départ à plat relèvent de C3b ; seule une évaluation déclarée synthétique est admise"
)


def require_synthetic(evaluation: Mapping[str, Any]) -> bool:
    """Le confinement des verdicts synthétiques (§ L.1, plan § 6.6), **avant tout chemin de publication**.

    ``evaluation.synthetic`` est une déclaration non dérivable, exigée explicite et strictement
    typée : absent / null / ``"true"`` → erreur d'entrée (code 2, rien écrit) ; ``false`` → une
    évaluation réelle n'est pas exerçable par l'outillage C3a → refus ``R0_INVALID_RUN`` (code 2,
    rien publié — ni verdict, ni abstention, ni diagnostic). Renvoie ``True`` ou lève.
    """
    synthetic = cc.require_bool(evaluation, "synthetic", where="evaluation")
    if not synthetic:
        raise cc.EntryRefusedError("R0_INVALID_RUN", REAL_EVALUATION_MESSAGE)
    return True


@dataclass(frozen=True)
class Decision:
    """L'issue, sa raison, et de quoi la relire sans la recalculer à la main."""

    issue: str
    reason: str | None
    retained: str | None
    selection_status: str | None
    provenance: str | None
    gates: dict[str, bool] = field(default_factory=dict)
    bounds_positive: bool | None = None
    estimability: dict[str, Any] | None = field(default=None)
    continuity_state: str | None = None
    synthetic: bool | None = None


def _gate_results(evaluation: Mapping[str, Any]) -> dict[str, bool]:
    """`Q1`, `Q2`, `Q3` du § F.8, évaluées sur la fenêtre d'évaluation.

    `Q1` et `Q2` lisent le **résultat propre** de la configuration ; seule `Q3` lit le comparateur.
    Les seuils viennent du § A.10 via ``c3_common`` ; les redire ici les ferait diverger (§ 0.7).
    Les trois métriques sont **obligatoires et finies**, et jamais une porte en échec : absente,
    nulle ou mal typée → erreur d'entrée (code 2) ; `NaN` ou infinie → violation (code 1, § I.1 l.15).
    """
    metrics = cc.require_mapping(evaluation, "metrics", where="evaluation")
    where = "evaluation.metrics"
    return {
        "Q1": cc.require_float(metrics, "net_pnl", where=where) > cc.FLOOR_NET_PNL,
        "Q2": cc.require_float(metrics, "cagr_pct", where=where) >= cc.FLOOR_CAGR_PCT,
        "Q3": cc.require_float(metrics, "delta_dd", where=where) > cc.FLOOR_DELTA_DD,
    }


def _bounds_all_positive(evaluation: Mapping[str, Any]) -> bool:
    """Les six combinaisons `L × appariement` du § F.2 (h), toutes **finies** et strictement positives.

    La finitude est vérifiée **avant** la comparaison : sans elle, `+inf` franchirait le plancher et
    un `NaN` le ferait échouer silencieusement.
    """
    bounds = cc.require_mapping(evaluation, "bounds", where="evaluation")
    expected = {f"{length}:{matching}" for length in cc.BLOCK_LENGTHS for matching in cc.MATCHINGS}
    missing = expected - set(bounds)
    extra = set(bounds) - expected
    if missing or extra:
        raise cc.MissingEvidenceError(
            f"evaluation.bounds: attendu exactement {len(expected)} combinaisons ; "
            f"manquantes={sorted(missing)} en trop={sorted(extra)}"
        )
    values = [cc.require_float(bounds, key, where="evaluation.bounds") for key in sorted(expected)]
    return all(v > 0.0 for v in values)


def _estimability_of(
    evaluation: Mapping[str, Any], *, violations: list[str]
) -> tuple[bool, dict[str, Any]]:
    """§ A.13, **recalculé depuis les séries**, puis recoupé contre toute valeur déclarée.

    Le statut déclaré n'est **jamais** recopié : il est recalculé et comparé, et un désaccord est une
    **violation** (§ I.1, ligne 15). Le bloc déclaré est optionnel ; **s'il est présent, chaque champ
    est strictement typé** — une chaîne ``"false"`` est une erreur de type, pas un ``True``.

    Le compteur ``discarded`` et le total ``B`` sont **obligatoires** : un compteur absent n'est pas
    zéro. Deux contrôles sur ``B``, dans cet ordre :

    1. **contrat, en tête de fonction, avant tout parsing** — ``B`` est un paramètre de la procédure
       d'incertitude que le manifeste déclare (§ A.6) et que D5 asserte « égal à ce qui est déclaré » ;
       la valeur gelée est ``BOOTSTRAP_B`` (§ F.2 b). Un ``B`` différent est un **contrat d'instrument
       rompu** : ``R0_INVALID_RUN``, code 2, rien n'est publié (§ I.1, ligne 2). « ``R0_INVALID_RUN``
       est évalué avant toute autre chose » (§ H) vaut aussi contre les erreurs de parsing des séries :
       un ``B`` hors contrat accompagné d'un compteur contradictoire **ou** d'un non-fini dans
       ``delta_stars`` sort en refus de contrat (2, rien d'écrit), jamais en violation (1) par accident
       d'ordre de lecture. Précédent : ``rejeu_validate_analysis.b02_frozen_parameters``.
    2. **cohérence** — ``B_effectif`` est recalculé comme ``len(delta_stars)`` ;
       ``B != B_effectif + discarded`` est un désaccord recalculé / enregistré, donc une violation
       (§ I.1, ligne 15).

    Une suite ``delta_stars`` **vide mais documentée** (toutes les réplications écartées) n'est pas une
    erreur d'entrée : elle mène à ``F_NOT_ESTIMABLE`` par le § F.2 (e), comme tout ``discarded`` au-delà
    de ``DISCARDED_MAX`` avec un compte cohérent.
    """
    total = cc.require_int(evaluation, "B", where="evaluation")
    if total != cc.BOOTSTRAP_B:
        raise cc.EntryRefusedError(
            "R0_INVALID_RUN",
            f"evaluation.B = {total} ; la valeur gelée du § F.2 (b) est {cc.BOOTSTRAP_B} "
            "— contrat d'instrument rompu, aucun verdict",
        )
    returns = cc.require_finite_series(
        evaluation, "returns_config", where="evaluation", domain_floor=cc.RETURN_DOMAIN_FLOOR
    )
    deltas = cc.require_finite_series(evaluation, "delta_stars", where="evaluation", min_len=0)
    discarded = cc.require_int(evaluation, "discarded", where="evaluation", minimum=0)
    b_effectif = len(deltas)
    if total != b_effectif + discarded:
        violations.append(
            f"réplications : B déclaré {total}, recalculé B_effectif {b_effectif} + écartées "
            f"{discarded} = {b_effectif + discarded} — le compte recalculé fait foi"
        )

    est = cc.estimability(returns, deltas, discarded)
    payload = est.to_dict()
    payload["B"] = total
    payload["B_effectif"] = b_effectif

    if "estimability" in evaluation and evaluation["estimability"] is not None:
        declared = cc.require_mapping(evaluation, "estimability", where="evaluation")
        for key, recomputed in (("E1", est.e1), ("E2", est.e2), ("ok", est.ok)):
            if key in declared:
                stated = cc.require_bool(declared, key, where="evaluation.estimability")
                if stated != recomputed:
                    violations.append(
                        f"estimabilité {key} déclarée {stated!r}, recalculée {recomputed!r} "
                        "— le statut recalculé fait foi"
                    )
        payload["declared"] = dict(declared)
    return est.ok, payload


def _identity_list(selection: Mapping[str, Any], key: str) -> list[str]:
    """Une liste d'identités (chaînes), lue strictement — élément non typé = erreur d'entrée."""
    out: list[str] = []
    for i, item in enumerate(cc.require_sequence(selection, key, where="selection")):
        if not isinstance(item, str):
            raise cc.MissingEvidenceError(
                f"selection.{key}[{i}]: chaîne attendue, reçu {type(item).__name__}"
            )
        out.append(item)
    return out


def _window_of(block: Mapping[str, Any], key: str, *, where: str) -> tuple[datetime, datetime]:
    inner = cc.require_mapping(block, key, where=where)
    return (
        cc.require_datetime(inner, "start", where=f"{where}.{key}"),
        cc.require_datetime(inner, "end", where=f"{where}.{key}"),
    )


def _iso(window: tuple[datetime, datetime]) -> str:
    return f"[{window[0].isoformat()}, {window[1].isoformat()}]"


@dataclass(frozen=True)
class ContinuityView:
    """Ce que `continuity.json` établit une fois lu strictement, dérivé et recoupé — sans action."""

    states: dict[str, str]
    details: dict[str, str]
    stamp_state: str
    comparator_state: str
    derived_state: str
    derived_identity: str


def _continuity_view(
    continuity: Mapping[str, Any],
    *,
    evaluation: Mapping[str, Any],
    anchor: Mapping[str, Any],
    violations: list[str],
) -> ContinuityView:
    """Lecture stricte, complète, de `continuity.json` ; dérivations ; recoupements (plan § 6.4).

    **Rien n'est recopié** (revue Fin, défaut 2) :

    * chaque état de clause est lu **contre la liste close de sa clause** (table § 6.4,
      ``cc.CLAUSE_ADMISSIBLE_STATES``, revue Fin 2) : hors liste → erreur d'entrée, code 2, rien
      publié ; les clés de ``clauses`` sont exactement c1..c5 ; ``stamp_cell`` et ``comparator``
      ont leur propre liste close ;
    * l'agrégat est **recalculé** des cinq clauses (précédence ``cc.CONTINUITY_SEVERITY``) et recoupé
      au ``state`` déclaré ; l'état du comparateur est recalculé de ses tests § C.5 et de sa fenêtre
      (revue Fin 3) et recoupé ;
    * les quatre résumés — ``warmup_anchor_ok`` (c4 ``VERIFIED``), ``benchmark_comparable``
      (comparateur ``VERIFIED``), ``stamp_same_daily_cell`` (``stamp_cell`` ``VERIFIED``),
      ``liquidation_normalised`` (``cc.LIQUIDATION_NORMALISED_OF_C3[c3]``) — sont dérivés et
      recoupés ; **toute contradiction déclaré / dérivé est une violation** (§ I.1 l.15) ;
    * ``identity`` est dérivée de ``evaluation.{strategy, pair, params}``, ``pair`` et ``synthetic``
      recoupés à l'évaluation, ``evaluation_window`` à ``[anchor.anchor, anchor.window.end]``
      (revue Fin 6).

    Cette lecture précède **tout** chemin de publication, abstention comprise (passe interne de la
    revue Fin 2) : un état hors liste close n'est jamais publié, sur aucun chemin.
    """
    where = "continuity"
    strategy = cc.require_str(evaluation, "strategy", where="evaluation")
    pair_eval = cc.require_str(evaluation, "pair", where="evaluation")
    params = cc.require_mapping(evaluation, "params", where="evaluation")
    anchor_t = cc.require_datetime(anchor, "anchor", where="anchor")
    window_end = cc.require_datetime(
        cc.require_mapping(anchor, "window", where="anchor"), "end", where="anchor.window"
    )
    declared_state = cc.require_str(continuity, "state", where=where, allowed=cc.CONTINUITY_STATES)
    clauses = cc.require_mapping(continuity, "clauses", where=where)
    if set(clauses) != set(cc.CLAUSE_ADMISSIBLE_STATES):
        raise cc.MissingEvidenceError(
            f"{where}.clauses: clés {sorted(clauses)} != {sorted(cc.CLAUSE_ADMISSIBLE_STATES)} "
            "(les cinq clauses § B, ni plus ni moins)"
        )
    states: dict[str, str] = {}
    details: dict[str, str] = {}
    for key in ("c1", "c2", "c3", "c4", "c5"):
        block = cc.require_mapping(clauses, key, where=f"{where}.clauses")
        states[key] = cc.require_str(
            block,
            "state",
            where=f"{where}.clauses.{key}",
            allowed=cc.CLAUSE_ADMISSIBLE_STATES[key],
        )
        details[key] = cc.require_str(block, "detail", where=f"{where}.clauses.{key}")
    stamp_cell = cc.require_mapping(continuity, "stamp_cell", where=where)
    stamp_state = cc.require_str(
        stamp_cell, "state", where=f"{where}.stamp_cell", allowed=cc.STAMP_CELL_ADMISSIBLE_STATES
    )
    comparator = cc.require_mapping(continuity, "comparator", where=where)
    comparator_state = cc.require_str(
        comparator, "state", where=f"{where}.comparator", allowed=cc.COMPARATOR_ADMISSIBLE_STATES
    )
    tests_block = cc.require_mapping(comparator, "tests", where=f"{where}.comparator")
    tests = {
        name: cc.require_bool(tests_block, name, where=f"{where}.comparator.tests")
        for name in cc.COMPARABILITY_TESTS
    }
    window_ok_declared = cc.require_bool(
        tests_block, "window_ok", where=f"{where}.comparator.tests"
    )
    comparator_window = cc.require_mapping(comparator, "window", where=f"{where}.comparator")
    window_declared = _window_of(comparator_window, "declared", where=f"{where}.comparator.window")
    window_expected = _window_of(comparator_window, "expected", where=f"{where}.comparator.window")
    identity = cc.require_str(continuity, "identity", where=where)
    pair = cc.require_str(continuity, "pair", where=where)
    synthetic = cc.require_bool(continuity, "synthetic", where=where)
    evaluation_window = _window_of(continuity, "evaluation_window", where=where)
    declared: dict[str, bool | None] = {
        "warmup_anchor_ok": cc.require_bool(continuity, "warmup_anchor_ok", where=where),
        "benchmark_comparable": cc.require_bool(continuity, "benchmark_comparable", where=where),
        "stamp_same_daily_cell": cc.require_bool(continuity, "stamp_same_daily_cell", where=where),
        "liquidation_normalised": cc.nullable_bool(
            continuity, "liquidation_normalised", where=where
        ),
    }

    # Dérivations, puis recoupements — une contradiction est une violation.
    derived_identity = cc.candidate_identity(strategy, pair_eval, params)
    if identity != derived_identity:
        violations.append(
            f"{where}.identity déclaré {identity[:16]}, dérivé {derived_identity[:16]} de "
            "evaluation.{strategy, pair, params} — l'identité dérivée fait foi"
        )
    if pair != pair_eval:
        violations.append(f"{where}.pair {pair!r} != evaluation.pair {pair_eval!r}")
    if synthetic is not True:
        violations.append(
            f"{where}.synthetic déclaré {synthetic!r} alors que evaluation.synthetic est vrai"
        )
    if evaluation_window != (anchor_t, window_end):
        violations.append(
            f"{where}.evaluation_window {_iso(evaluation_window)} != [anchor.anchor, anchor.window.end] "
            f"= {_iso((anchor_t, window_end))}"
        )
    if window_expected != evaluation_window:
        violations.append(
            f"{where}.comparator.window.expected {_iso(window_expected)} != evaluation_window "
            f"{_iso(evaluation_window)}"
        )
    window_ok = window_declared == window_expected
    if window_ok != window_ok_declared:
        violations.append(
            f"{where}.comparator.tests.window_ok déclaré {window_ok_declared!r}, dérivé {window_ok!r} "
            f"(déclarée {_iso(window_declared)}, attendue {_iso(window_expected)})"
        )
    derived_comparator = "VERIFIED" if all(tests.values()) and window_ok else "FAILED"
    if derived_comparator != comparator_state:
        violations.append(
            f"{where}.comparator.state déclaré {comparator_state!r}, dérivé {derived_comparator!r} "
            f"des tests § C.5 {tests}"
        )
    derived_state = cc.continuity_aggregate(states)
    if derived_state != declared_state:
        violations.append(
            f"{where}.state déclaré {declared_state!r}, dérivé {derived_state!r} des clauses {states} "
            "(précédence FAILED > NOT_VERIFIABLE > DECLARED > VERIFIED)"
        )
    derived: dict[str, bool | None] = {
        "warmup_anchor_ok": states["c4"] == "VERIFIED",
        "benchmark_comparable": derived_comparator == "VERIFIED",
        "stamp_same_daily_cell": stamp_state == "VERIFIED",
        # défini sur la liste close de c3 (lue ci-dessus avec `allowed=`), et sur elle seule
        "liquidation_normalised": cc.LIQUIDATION_NORMALISED_OF_C3[states["c3"]],
    }
    for key, value in derived.items():
        if declared[key] != value:
            violations.append(
                f"{where}.{key} déclaré {declared[key]!r}, dérivé {value!r} des clauses "
                "— le résumé dérivé fait foi"
            )
    return ContinuityView(
        states=states,
        details=details,
        stamp_state=stamp_state,
        comparator_state=derived_comparator,
        derived_state=derived_state,
        derived_identity=derived_identity,
    )


def _continuity_actions(view: ContinuityView, *, retained: str) -> list[str]:
    """Ce que la continuité impose au verdict (table § 6.4) — sur les **clauses**, jamais sur les
    résumés : l'évaluation doit être celle de la configuration retenue (§ H.1, sinon refus R0) ;
    c1, c2, c5 ``FAILED`` → refus R0 (l'artefact déclare une rupture du contrat § B) ; c3 ``FAILED``
    → ``UndefinedIssueError`` (convention datée du 21/09, plan § 6.1) ; c4 ``FAILED`` →
    ``D_WARMUP_ANCHOR`` ; comparateur ``FAILED`` → ``E_NO_BENCHMARK`` ; ``stamp_cell`` non
    ``VERIFIED`` → ``E_STAMP_MISMATCH`` (§ I.1 l.10-12). Quand plusieurs clauses sont ``FAILED``,
    le refus R0 précède l'issue non définie (§ H : R0 avant toute autre chose)."""
    if view.derived_identity != retained:
        raise cc.EntryRefusedError(
            "R0_INVALID_RUN",
            f"l'évaluation porte la configuration {view.derived_identity[:16]}, la sélection a retenu "
            f"{retained[:16]} — ce n'est pas l'évaluation de la configuration retenue (§ H.1)",
        )
    for key in ("c1", "c2", "c5"):
        if view.states[key] == "FAILED":
            raise cc.EntryRefusedError(
                "R0_INVALID_RUN",
                f"clause {key} de continuité en échec — l'artefact déclare une rupture du contrat "
                f"§ B : {view.details[key]}",
            )
    if view.states["c3"] == "FAILED":
        raise cc.UndefinedIssueError(UNDEFINED_ISSUE_MESSAGE)
    reasons: list[str] = []
    if view.states["c4"] == "FAILED":
        reasons.append("D_WARMUP_ANCHOR")
    if view.comparator_state == "FAILED":
        reasons.append("E_NO_BENCHMARK")
    if view.stamp_state != "VERIFIED":
        reasons.append("E_STAMP_MISMATCH")
    return reasons


def decide(artifacts: Mapping[str, Mapping[str, Any]], *, violations: list[str]) -> Decision:
    """L'issue du § H, et rien d'autre. Fonction pure des artefacts fournis.

    Lève ``MissingEvidenceError`` dès qu'une preuve obligatoire est absente, nulle, mal typée ou hors
    liste close — **erreur d'entrée** (§ I.1 ligne 2, code 2), pas un verdict — et
    ``InvalidValueError`` sur une valeur non finie ou hors domaine — **violation** (§ I.1 ligne 15,
    code 1), pas un verdict non plus. Aucun verdict économique n'est prononcé sur une preuve manquante
    ou invalide. ``EntryRefusedError`` (refus) et ``UndefinedIssueError`` (clause 3 en échec) : sans
    violation constatée, code 2 et rien publié ; après une violation, **l'ordre de constat** fait
    foi — la violation prime (§ I.1 l.15) et l'exception est consignée dans le diagnostic, code 1 —
    sauf lecture inachevable (``MissingEvidenceError`` après une violation → code 2, rien publié,
    violations dites sur stderr ; convention d'outillage datée du 22/09, voir ``run_verdict``).

    **Contrat de couche.** La cohérence d'enveloppe des amonts (``ok`` / ``exit_code`` / ``invalide``,
    ``refusal`` pour entry) est le contrat de l'**appelant**, appliqué à la frontière fichier par
    ``artifact_coherence`` (via ``verify_chain``) **avant tout appel** — ``decide()`` ne la revérifie
    pas et ne doit jamais être appelée sur du contenu de fichier non gardé.

    **Ordre : tout lire, puis décider** (revue Fin 5 et passe interne de la revue Fin 2). Le
    confinement (§ L.1, plan § 6.6) vient en tête — ``evaluation.synthetic`` strict, ``false``
    refusé — puis le contrat d'entrée (refus R0 avant toute autre chose, § H), puis **la lecture
    stricte complète des cinq artefacts** : ancre, sélection (listes, statut dérivé), continuité
    (états contre leur liste close, résumés dérivés et recoupés), évaluation (``B`` contre le
    contrat, séries, métriques des portes, six bornes). Aucun chemin de publication — abstention,
    inconclusif par raison run, réfuté, validé — ne précède cette lecture : une preuve manquante est
    un code 2, jamais un inconclusif publié. La décision suit ensuite l'ordre du § H : abstention,
    continuité (clauses), estimabilité (§ H.0), portes, bornes.
    """
    # 0. Confinement, puis contrat d'entrée (R0 avant toute autre chose).
    evaluation = cc.require_mapping(artifacts, "evaluation", where="artefacts")
    synthetic = require_synthetic(evaluation)
    entry = cc.require_mapping(artifacts, "entry", where="artefacts")
    _entry_contract(entry, violations=violations)

    # 1. Lecture stricte complète — ancre, sélection, continuité, évaluation.
    anchor = cc.require_mapping(artifacts, "anchor", where="artefacts")
    provenance = cc.require_str(
        anchor, "universe_provenance", where="anchor", allowed=cc.PROVENANCES
    )
    selection = cc.require_mapping(artifacts, "selection", where="artefacts")
    selection_status, derived_retained, derived_reason = _selection_view(
        selection, provenance=provenance, violations=violations
    )
    continuity = cc.require_mapping(artifacts, "continuity", where="artefacts")
    view = _continuity_view(continuity, evaluation=evaluation, anchor=anchor, violations=violations)
    estimable, estimability_payload = _estimability_of(evaluation, violations=violations)
    gates = _gate_results(evaluation)
    bounds_positive = _bounds_all_positive(evaluation)

    # 2. La décision, dans l'ordre du § H.
    reasons: list[str] = []
    if not cc.PROVENANCE_CAN_SUPPORT_VALIDE[provenance]:
        reasons.append("P_PROVENANCE")

    if derived_retained is None:
        # Abstention : aucune configuration retenue, l'évaluation n'est pas celle d'une retenue —
        # la continuité et l'évaluation ont été lues et recoupées (contrat), elles ne sont pas
        # rapportées ; la chaîne porte `continuite=-`.
        assert derived_reason is not None
        reasons.append(derived_reason)
        return Decision(
            issue=cc.ISSUE_INCONCLUSIF,
            reason=cc.worst_reason(*reasons),
            retained=None,
            selection_status=selection_status,
            provenance=provenance,
            synthetic=synthetic,
        )

    retained = derived_retained
    reasons.extend(_continuity_actions(view, retained=retained))
    # § H.0 — l'estimabilité est préalable au verdict économique, et elle est **recalculée**.
    if not estimable:
        reasons.append("F_NOT_ESTIMABLE")

    common: dict[str, Any] = {
        "retained": retained,
        "selection_status": selection_status,
        "provenance": provenance,
        "estimability": estimability_payload,
        "continuity_state": view.derived_state,
        "synthetic": synthetic,
    }
    if reasons:
        return Decision(
            issue=cc.ISSUE_INCONCLUSIF,
            reason=cc.worst_reason(*reasons),
            gates={},
            bounds_positive=None,
            **common,
        )
    if not all(gates.values()):
        return Decision(
            issue=cc.ISSUE_REFUTE, reason=None, gates=gates, bounds_positive=None, **common
        )
    if not bounds_positive:
        return Decision(
            issue=cc.ISSUE_INCONCLUSIF,
            reason="F_CANNOT_SEPARATE",
            gates=gates,
            bounds_positive=False,
            **common,
        )
    return Decision(issue=cc.ISSUE_VALIDE, reason=None, gates=gates, bounds_positive=True, **common)


def _entry_contract(entry: Mapping[str, Any], *, violations: list[str]) -> None:
    """Le contrat de `entry.json` (c3_entry) : `ok` <=> `refusal` est null. Les combinaisons
    incohérentes sont des violations de l'instrument (§ I.1 l.15), jamais un verdict ; un refus
    porteur de sa raison est relevé (§ I.1 lignes 2 et 5 : code 2, rien publié, sauf violation
    antérieure)."""
    entry_ok = cc.require_bool(entry, "ok", where="entry")
    refusal = cc.nullable_mapping(entry, "refusal", where="entry")
    if entry_ok and refusal is not None:
        violations.append(
            "entry.ok vrai alors qu'un refus est porté "
            f"({cc.require_str(refusal, 'reason', where='entry.refusal')}) — contrat d'entrée incohérent"
        )
    if not entry_ok:
        if refusal is None:
            violations.append("entry.ok faux sans bloc `refusal` — contrat d'entrée incohérent")
            raise cc.EntryRefusedError("R0_INVALID_RUN", "la validité d'entrée (§ I-A) a échoué")
        reason = cc.require_str(
            refusal, "reason", where="entry.refusal", allowed=("R0_INVALID_RUN", "D_WARMUP_PREFIX")
        )
        cc.require_str(refusal, "scope", where="entry.refusal", allowed=("run", "artefact"))
        raise cc.EntryRefusedError(reason, cc.require_str(refusal, "detail", where="entry.refusal"))


def _selection_view(
    selection: Mapping[str, Any], *, provenance: str, violations: list[str]
) -> tuple[str, str | None, str | None]:
    """Lecture stricte de `selection.json` ; retenue, raison et statut **dérivés** des listes
    (§ A.10 : filtrer → filtrer → classer ; revue Fin 6) et recoupés au déclaré. Renvoie
    (statut déclaré, retenue dérivée, raison dérivée)."""
    selection_status = cc.require_str(
        selection, "status", where="selection", allowed=cc.STATUS_SELECTION
    )
    selection_provenance = cc.require_str(
        selection, "provenance", where="selection", allowed=cc.PROVENANCES
    )
    if selection_provenance != provenance:
        violations.append(
            f"selection.provenance {selection_provenance!r} != anchor.universe_provenance "
            f"{provenance!r} — le manifeste n'a qu'une provenance"
        )
    retained_block = cc.nullable_mapping(selection, "retained", where="selection")
    declared_retained = (
        None
        if retained_block is None
        else cc.require_str(retained_block, "identity", where="selection.retained")
    )
    declared_reason = cc.nullable_str(selection, "reason", where="selection")
    if declared_reason is not None and declared_reason not in ABSTENTION_REASONS:
        raise cc.MissingEvidenceError(
            f"selection.reason: {declared_reason!r} hors liste close {sorted(ABSTENTION_REASONS)}"
        )
    lists = {
        name: _identity_list(selection, name) for name in ("admissible", "survivors", "ranking")
    }
    derived_retained = lists["ranking"][0] if lists["ranking"] else None
    if declared_retained != derived_retained:
        violations.append(
            f"selection.retained déclaré {(declared_retained or '-')[:16]}, dérivé "
            f"{(derived_retained or '-')[:16]} de la tête de selection.ranking — le classement fait foi"
        )
    if sorted(lists["ranking"]) != sorted(lists["survivors"]):
        violations.append(
            f"selection.ranking ({len(lists['ranking'])}) n'est pas une permutation de "
            f"selection.survivors ({len(lists['survivors'])})"
        )
    if not set(lists["survivors"]) <= set(lists["admissible"]):
        violations.append("selection.survivors n'est pas inclus dans selection.admissible")
    if lists["survivors"]:
        derived_reason: str | None = None
    elif lists["admissible"]:
        derived_reason = "A_BELOW_FLOOR"
    else:
        derived_reason = "A_NO_ADMISSIBLE_CANDIDATE"
    if declared_reason != derived_reason:
        violations.append(
            f"selection.reason déclaré {declared_reason!r}, dérivé {derived_reason!r} des listes "
            f"(admissible {len(lists['admissible'])}, survivors {len(lists['survivors'])}) — la raison dérivée fait foi"
        )
    if derived_retained is None:
        derived_status = "ABSTENTION"
    elif cc.PROVENANCE_CAN_SUPPORT_VALIDE[provenance]:
        derived_status = "SÉLECTION_VALIDE"
    else:
        derived_status = "SÉLECTION_DESCRIPTIVE"
    if derived_status != selection_status:
        violations.append(
            f"selection.status déclaré {selection_status!r}, dérivé {derived_status!r} de "
            f"(provenance {provenance!r}, retenu {derived_retained is not None}) — le statut dérivé fait foi"
        )
    return selection_status, derived_retained, derived_reason


# ---------------------------------------------------------------------------
# § L.2 — la chaîne à neuf champs
# ---------------------------------------------------------------------------


def build_verdict_string(
    campaign: str,
    decision: Decision,
    protocol_sha: str,
    *,
    continuity_state: str | None,
    variant_key: str,
    observations_sha256: str,
    synthetic: bool,
) -> str:
    """La chaîne canonique du § L.2 — neuf champs, **sans horodatage**, pour qu'elle soit reproductible.

    Le label est ``C3_<campagne>`` ; une évaluation synthétique le préfixe ``C3_SYNTH_`` (plan § 6.6)
    pour qu'un rapport ne puisse pas citer la chaîne sans citer sa portée. ``variante`` est la clé
    ``sig(canon(manifeste))`` enregistrée par ``c3_anchor`` ; ``observations`` l'empreinte du fichier
    d'observations enregistrée par ``c3_entry`` (et recoupée à celle de ``c3_select``).
    """
    label = f"{SYNTH_PREFIX}{campaign}" if synthetic else f"C3_{campaign}"
    parts = [
        label,
        f"verdict={decision.issue}",
        f"raison={decision.reason or '-'}",
        f"selection={decision.retained or '-'}",
        f"statut_selection={decision.selection_status or '-'}",
        f"continuite={continuity_state or '-'}",
        f"variante={variant_key[:16]}",
        f"provenance={decision.provenance or '-'}",
        f"protocole={protocol_sha[:16]}",
        f"observations={observations_sha256[:16]}",
    ]
    return " | ".join(parts)


# ---------------------------------------------------------------------------
# § L.2 — succès enregistré des amonts et empreintes recoupées
# ---------------------------------------------------------------------------


def artifact_coherence(artifact: Mapping[str, Any], *, where: str) -> list[str]:
    """Le contrat interne d'une enveloppe `c3_*` (``cc.envelope``) : ``ok ⟺ exit_code == 0``,
    ``invalide ⟺ exit_code == 1`` ; pour ``entry`` (qui écrit toujours) : ``exit_code == 2 ⟹ refus
    porté`` et ``refus porté ⟹ exit_code ≠ 0`` (un refus peut coexister avec une violation, code 1 —
    `c3_entry.main`). ``exit_code`` hors de {0, 1, 2} est hors liste close : erreur d'entrée.
    Renvoie les contradictions ; elles sont des violations (revue Fin, défaut 4)."""
    ok = cc.require_bool(artifact, "ok", where=where)
    invalide = cc.require_bool(artifact, "invalide", where=where)
    code = cc.require_int(artifact, "exit_code", where=where, minimum=0)
    if code not in (0, 1, 2):
        raise cc.MissingEvidenceError(f"{where}.exit_code: {code} hors liste close (0, 1, 2)")
    problems: list[str] = []
    if ok != (code == 0):
        problems.append(f"{where}: ok={ok} avec exit_code={code} (ok ⟺ exit_code == 0)")
    if invalide != (code == 1):
        problems.append(
            f"{where}: invalide={invalide} avec exit_code={code} (invalide ⟺ exit_code == 1)"
        )
    if where == "entry":
        refusal = cc.nullable_mapping(artifact, "refusal", where=where)
        if code == 2 and refusal is None:
            problems.append(f"{where}: exit_code=2 sans bloc refusal (refus ⟺ exit_code == 2)")
        if refusal is not None and code == 0:
            problems.append(
                f"{where}: refusal porté avec exit_code=0 (un refus n'est jamais un succès)"
            )
    return problems


def verify_chain(
    raws: Mapping[str, Mapping[str, Any]],
    paths: Mapping[str, Path],
    *,
    violations: list[str] | None = None,
    checks: list[dict[str, Any]] | None = None,
) -> tuple[list[str], list[dict[str, Any]]]:
    """Exige le succès enregistré de chaque amont (sinon refus, code 2) et recoupe les empreintes
    entre elles et avec les fichiers fournis (discordance = violation, code 1).

    Cohérence interne d'abord (``artifact_coherence``, revue Fin 4) : une contradiction entre ``ok``,
    ``invalide``, ``exit_code`` (et ``refusal`` pour entry) est une violation, code 1 ; un échec
    amont **cohérent** reste un refus, code 2.

    Recoupements : ``manifest`` identique entre anchor, entry, selection et continuity ;
    ``observations`` identique entre entry et selection ; ``anchor.json`` tel que consommé par entry,
    selection et continuity ; ``entry.json`` tel que consommé par selection ; ``evaluation.json`` tel
    que consommé par continuity ; ``protocole.sha256`` identique partout et égal au courant.
    """
    # Les listes du demandeur, quand il les passe : une contradiction consignée ici n'est jamais
    # perdue si un refus (`require_upstream_ok`) ou une erreur d'entrée lève ensuite — le refus
    # après violation reste consigné au diagnostic, code 1 (chantier 0 ; passe interne, revue Fin 2).
    checks = checks if checks is not None else []
    violations = violations if violations is not None else []

    def record(name: str, ok: bool, detail: str) -> None:
        checks.append({"check": name, "ok": ok, "detail": detail})
        if not ok:
            violations.append(f"chaîne : {name} — {detail}")

    # Revue Fin (4) — cohérence interne de chaque amont, **avant** d'en lire le succès : trois
    # champs qui ne peuvent pas venir du même run sont une violation, jamais un refus silencieux.
    coherent: dict[str, bool] = {}
    for name in ("entry", "anchor", "selection", "continuity"):
        problems = artifact_coherence(raws[name], where=name)
        coherent[name] = not problems
        record(
            f"{name}.coherence",
            not problems,
            " ; ".join(problems) or "ok ⟺ exit 0, invalide ⟺ exit 1, refus ⟺ exit 2",
        )
    for name in ("anchor", "selection", "continuity"):
        if coherent[name]:
            cc.require_upstream_ok(raws[name], where=name)
    entry = raws["entry"]
    if coherent["entry"] and cc.require_bool(entry, "invalide", where="entry"):
        raise cc.EntryRefusedError(
            "R0_INVALID_RUN", "entry.json est l'artefact diagnostic d'une violation (invalide)"
        )

    def stated(name: str, key: str) -> str:
        recorded = cc.require_mapping(raws[name], "inputs_sha256", where=name)
        return cc.require_str(recorded, key, where=f"{name}.inputs_sha256")

    anchor_sha = cc.file_sha256(paths["anchor"])
    entry_sha = cc.file_sha256(paths["entry"])
    evaluation_sha = cc.file_sha256(paths["evaluation"])
    manifest_sha = stated("anchor", "manifest")
    observations_sha = stated("entry", "observations")
    expected: list[tuple[str, str, str, str]] = [
        ("entry", "manifest", manifest_sha, "manifeste identique entre anchor et entry"),
        ("entry", "anchor", anchor_sha, "entry calculée sur ce anchor.json"),
        ("selection", "manifest", manifest_sha, "manifeste identique entre anchor et selection"),
        ("selection", "anchor", anchor_sha, "selection calculée sur ce anchor.json"),
        ("selection", "entry", entry_sha, "selection calculée sur cette entry.json"),
        (
            "selection",
            "observations",
            observations_sha,
            "observations identiques entre entry et selection",
        ),
        ("continuity", "manifest", manifest_sha, "manifeste identique entre anchor et continuity"),
        ("continuity", "anchor", anchor_sha, "continuity calculée sur ce anchor.json"),
        (
            "continuity",
            "evaluation",
            evaluation_sha,
            "continuity calculée sur cette evaluation.json",
        ),
    ]
    for name, key, actual, detail in expected:
        value = stated(name, key)
        record(
            f"{name}.{key}",
            value == actual,
            f"{detail} (enregistré {value[:16]}, attendu {actual[:16]})",
        )
    current = cc.protocol_descriptor()["sha256"]
    for name in ("anchor", "entry", "selection", "continuity"):
        descriptor = cc.require_mapping(raws[name], "protocole", where=name)
        value = cc.require_str(descriptor, "sha256", where=f"{name}.protocole")
        record(
            f"{name}.protocole",
            value == current,
            f"protocole gelé identique (enregistré {value[:16]}, courant {current[:16]})",
        )
    return violations, checks


# ---------------------------------------------------------------------------
# Artefact
# ---------------------------------------------------------------------------


def build_payload(
    decision: Decision,
    *,
    campaign: str,
    now: datetime,
    inputs: Mapping[str, Path],
    variant_key: str,
    observations_sha256: str,
    chain: Mapping[str, Any],
) -> dict[str, Any]:
    """L'artefact **normal** : un verdict et sa chaîne citable. Jamais construit si une violation existe."""
    descriptor = cc.protocol_descriptor()
    synthetic = decision.synthetic is True
    payload = cc.envelope(STEP, now, inputs, exit_code=0)
    payload.update(
        {
            "campagne": campaign,
            "synthetic": decision.synthetic,
            "portee": PORTEE_SYNTH if synthetic else None,
            "verdict": decision.issue,
            "raison": decision.reason,
            "selection": decision.retained,
            "statut_selection": decision.selection_status,
            "continuite": decision.continuity_state,
            "variante": variant_key,
            "provenance": decision.provenance,
            "observations_sha256": observations_sha256,
            "portes_Q": decision.gates,
            "bornes_toutes_positives": decision.bounds_positive,
            "estimabilite": decision.estimability,
            "chain": dict(chain),
            "verdict_string": build_verdict_string(
                campaign,
                decision,
                descriptor["sha256"],
                continuity_state=decision.continuity_state,
                variant_key=variant_key,
                observations_sha256=observations_sha256,
                synthetic=synthetic,
            ),
        }
    )
    return payload


def build_diagnostic_payload(
    violations: Sequence[str],
    *,
    campaign: str,
    now: datetime,
    inputs: Mapping[str, Path],
    partial: Decision | None,
    chain: Mapping[str, Any],
) -> dict[str, Any]:
    """L'artefact **diagnostic** d'une violation (§ I.1, ligne 15) : explicitement invalide.

    Il porte les violations, les empreintes de ses entrées et, à titre de diagnostic, ce que le
    calcul avait produit avant d'être invalidé — mais **aucun verdict, aucune raison, aucune chaîne
    citable**. Un rapport ne peut pas le citer comme un résultat, parce qu'il n'en contient pas.
    """
    payload = cc.envelope(STEP, now, inputs, exit_code=1, violations=violations)
    payload.update(
        {
            "campagne": campaign,
            # Le confinement a été franchi avant toute publication : un diagnostic est lui aussi un
            # exercice synthétique, et il le dit.
            "synthetic": True,
            "portee": PORTEE_SYNTH,
            "verdict": None,
            "raison": None,
            "verdict_string": None,
            "chain": dict(chain),
            "diagnostic": None
            if partial is None
            else {
                "issue_calculee_puis_invalidee": partial.issue,
                "portes_Q": partial.gates,
                "estimabilite": partial.estimability,
            },
        }
    )
    return payload


def render_lines(payload: Mapping[str, Any]) -> list[str]:
    out: list[str] = []
    if payload["portee"] is not None:
        # Plan § 6.6 (3) : la portée d'un exercice synthétique s'imprime en première ligne, avant
        # la chaîne comme avant un diagnostic.
        out.append(f"PORTEE : {payload['portee']}")
    if payload["invalide"]:
        out.append("ARTEFACT INVALIDE — aucun verdict, aucune chaîne citable")
        out += [f"  violation : {v}" for v in payload["violations"]]
        return out
    out += [payload["verdict_string"], ""]
    est = payload["estimabilite"]
    if est is not None:
        out.append(
            f"estimabilité : E1={est['E1']} E2={est['E2']} nnz={est['nonzero_ratio']:.3f} "
            f"distincts={est['distinct_delta_stars']} B={est['B']} B_effectif={est['B_effectif']} "
            f"écartées={est['discarded']}"
        )
    gates = payload["portes_Q"]
    if gates:
        out.append("portes Q : " + " ".join(f"{k}={v}" for k, v in sorted(gates.items())))
    return out


# ---------------------------------------------------------------------------
# Le verdict sur fichiers
# ---------------------------------------------------------------------------


def _warn_stale_output(output: Path, inputs: Mapping[str, Path]) -> None:
    """Un ``verdict.json`` antérieur n'est jamais supprimé (§ L.4) ; s'il ne correspond pas aux
    entrées courantes, il est signalé sur stderr — c'est au consommateur de recouper les empreintes."""
    if not Path(output).exists():
        return
    try:
        previous = cc.read_json(output)
    except (OSError, ValueError):
        print(
            f"AVERTISSEMENT un fichier illisible est présent à {output} ; il n'est pas supprimé",
            file=sys.stderr,
        )
        return
    if not isinstance(previous, Mapping) or "inputs_sha256" not in previous:
        return
    recorded = previous["inputs_sha256"]
    if not isinstance(recorded, Mapping):
        return
    for name, path in inputs.items():
        if name not in recorded or recorded[name] != cc.file_sha256(path):
            print(
                f"AVERTISSEMENT un verdict antérieur discordant est présent à {output} (empreinte "
                f"{name} différente) ; il n'est pas supprimé — si l'invocation courante échoue, il "
                "reste lisible et ne la représente pas",
                file=sys.stderr,
            )
            return


def run_verdict(
    paths: Mapping[str, Path],
    *,
    output: Path,
    campaign: str,
    now: datetime,
    chain_steps: Sequence[Mapping[str, Any]] = (),
) -> int:
    """Lit les cinq artefacts, vérifie la chaîne, décide, écrit ``verdict.json`` (0 ou 1) ou rien (2).

    ``chain.verified`` (définition fixée, revue Fin 2) : intégrité mécanique de la chaîne — codes
    de succès des amonts, cohérence interne de chaque amont, empreintes concordantes ; vrai
    seulement dans un artefact normal (code 0), faux sur toute violation (chaîne ou non) ou refus —
    un refus sans violation ne publie rien (code 2), un refus après violation publie un diagnostic
    ``verified: false``. Il ne dit rien de la qualité de l'issue (``verdict`` / ``raison``).
    """
    artifacts: dict[str, Mapping[str, Any]] = {}
    for name in INPUT_NAMES:
        try:
            artifacts[name] = cc.read_json(paths[name])
        except (OSError, ValueError) as exc:
            print(f"--{name}: {exc}", file=sys.stderr)
            return 2
    inputs: dict[str, Path] = {name: Path(paths[name]) for name in INPUT_NAMES}
    # Revue Fin (1) : le confinement précède tout chemin de publication, diagnostic compris — une
    # violation constatée ensuite ne peut pas ramener une évaluation réelle sur disque.
    try:
        if not isinstance(artifacts["evaluation"], Mapping):
            raise cc.MissingEvidenceError("evaluation: bloc attendu")
        require_synthetic(artifacts["evaluation"])
    except cc.EntryRefusedError as exc:
        print(f"ENTREE REFUSEE {exc}", file=sys.stderr)
        return 2
    except cc.MissingEvidenceError as exc:
        print(f"ENTREE INVALIDE {exc}", file=sys.stderr)
        return 2
    _warn_stale_output(output, inputs)

    violations: list[str] = []
    decision: Decision | None = None
    chain: dict[str, Any] = {
        "mode": "chain" if chain_steps else "verdict",
        "steps": [dict(step) for step in chain_steps],
        "verified": False,
        "checks": [],
    }
    variant_key = ""
    observations_sha256 = ""
    try:
        chain_violations, _ = verify_chain(
            artifacts, inputs, violations=violations, checks=chain["checks"]
        )
        chain["verified"] = not chain_violations
        variant_key = cc.require_str(artifacts["anchor"], "variant_key", where="anchor")
        recorded = cc.require_mapping(artifacts["entry"], "inputs_sha256", where="entry")
        observations_sha256 = cc.require_str(recorded, "observations", where="entry.inputs_sha256")
        decision = decide(artifacts, violations=violations)
    except cc.UndefinedIssueError as exc:
        if violations:
            # Revue Fin 2 (2) — précédence : une contradiction déclaré / dérivé constatée avant
            # est une violation (§ I.1 l.15) ; elle prime, l'issue non définie est consignée dans
            # le diagnostic, code 1. Le refus 2 de la convention datée reste réservé au cas cohérent.
            # Le diagnostic consigne le motif, pas la conduite (b) qui ne s'est pas appliquée.
            violations.append(
                f"issue non définie constatée après violation : {UNDEFINED_ISSUE_MOTIF}"
            )
        else:
            # Convention datée du 21/09 (plan § 6.1) : aucune issue, code 2, rien publié.
            print(f"ISSUE NON DEFINIE {exc}", file=sys.stderr)
            return 2
    except cc.EntryRefusedError as exc:
        if violations:
            # Une violation constatée avant le refus prime (§ I.1 l.15 : « c'est une violation,
            # pas un résultat ») : artefact diagnostic, code 1, le refus y est consigné.
            violations.append(f"refus d'entrée constaté après violation : {exc}")
        else:
            # § I.1, lignes 2 et 5 — refus d'entrée : code 2, la chaîne s'arrête, rien n'est publié.
            print(f"ENTREE REFUSEE {exc}", file=sys.stderr)
            return 2
    except cc.MissingEvidenceError as exc:
        # § I.1 — preuve obligatoire absente, nulle, mal typée ou hors liste close : code 2, rien
        # d'écrit (chantier 0). Constatée après une violation : lecture inachevable, un diagnostic
        # se bâtit sur une lecture complète → 2 quand même, rien publié, les violations dites sur
        # stderr (convention d'outillage datée du 22/09, validation Fin ; clarification au paquet C3b).
        for violation in violations:
            print(f"VIOLATION {violation}", file=sys.stderr)
        print(f"ENTREE INVALIDE {exc}", file=sys.stderr)
        return 2
    except (cc.InvalidValueError, cc.NonFiniteValueError) as exc:
        # § F.7 -> § I.1, ligne 15 — non-finitude ou domaine : violation, code 1, diagnostic écrit.
        # `NonFiniteValueError` (levée par `canon`) n'est pas une `InvalidValueError` : routée ici
        # explicitement, comme dans les quatre autres modules (revue R3 d).
        violations.append(str(exc))

    if violations:
        # § I.1, ligne 15 — une violation n'est pas un résultat : aucun verdict normal n'est publié,
        # et `chain.verified` est faux sur toute violation, de chaîne ou non (définition fixée,
        # revue Fin 2 ; revue Fin 3) ; les `checks` disent quels recoupements ont passé ou échoué.
        chain["verified"] = False
        payload = build_diagnostic_payload(
            violations, campaign=campaign, now=now, inputs=inputs, partial=decision, chain=chain
        )
        digest = cc.write_json(output, payload)
        print("\n".join(render_lines(payload)))
        print(f"written {output} sha256 {digest}")
        for violation in violations:
            print(f"VIOLATION {violation}", file=sys.stderr)
        return 1

    assert decision is not None
    payload = build_payload(
        decision,
        campaign=campaign,
        now=now,
        inputs=inputs,
        variant_key=variant_key,
        observations_sha256=observations_sha256,
        chain=chain,
    )
    digest = cc.write_json(output, payload)
    print("\n".join(render_lines(payload)))
    print(f"written {output} sha256 {digest}")
    return 0


# ---------------------------------------------------------------------------
# Sous-commande chain — le site réel de l'orchestration (§ L.1, plan § 5.3)
# ---------------------------------------------------------------------------

#: Les étapes, dans l'ordre gelé du § L.1 ; le nom de fichier de chacune sous ``--out-dir``.
CHAIN_FILES: tuple[tuple[str, str], ...] = (
    ("anchor", "anchor.json"),
    ("entry", "entry.json"),
    ("benchmark", "benchmark.json"),
    ("select", "selection.json"),
    ("continuity", "continuity.json"),
)


def run_chain(args: argparse.Namespace) -> int:
    """Invoque chaque étape **en processus**, contrôle son **code de retour effectif** (≠ 0 → la
    chaîne s'arrête et rend ce code, rien d'autre n'est écrit), puis ``verify_chain`` et le verdict.

    Sur données réelles la chaîne s'arrête à ``entry`` (refus D2 ou ``not_assertable``) : aucun
    chemin réel n'atteint le verdict en C3a (plan § 6.6 (4)).
    """
    import c3_anchor
    import c3_benchmark
    import c3_continuity
    import c3_entry
    import c3_select

    try:
        now = cc.parse_now(args.now)
    except ValueError as exc:
        print(f"--now: {exc}", file=sys.stderr)
        return 2
    out = Path(args.out_dir)
    out.mkdir(parents=True, exist_ok=True)
    files = {name: out / filename for name, filename in CHAIN_FILES}
    now_argv = ["--now", args.now] if args.now is not None else []
    steps: list[dict[str, Any]] = []

    def run_step(name: str, main_fn: Any, argv: list[str]) -> int:
        code = int(main_fn(argv + now_argv))
        steps.append({"name": name, "exit_code": code})
        if code != 0:
            print(
                f"CHAINE ARRETEE à l'étape {name} (code de retour {code}) — aucun verdict",
                file=sys.stderr,
            )
        return code

    manifest = str(args.manifest)
    code = run_step(
        "anchor",
        c3_anchor.main,
        [
            "--manifest",
            manifest,
            "--registry",
            str(args.registry),
            "--output",
            str(files["anchor"]),
        ],
    )
    if code != 0:
        return code
    entry_argv = [
        "--manifest",
        manifest,
        "--anchor",
        str(files["anchor"]),
        "--observations",
        str(args.observations),
        "--output",
        str(files["entry"]),
        "--markdown",
        str(out / "entry.md"),
    ]
    if args.coverage is not None:
        entry_argv += ["--coverage", str(args.coverage)]
    code = run_step("entry", c3_entry.main, entry_argv)
    if code != 0:
        return code
    if args.candles is None:
        steps.append({"name": "benchmark", "exit_code": 2})
        print("CHAINE ARRETEE à l'étape benchmark : --candles requis (§ C.3)", file=sys.stderr)
        return 2
    code = run_step(
        "benchmark",
        c3_benchmark.main,
        [
            "--manifest",
            manifest,
            "--anchor",
            str(files["anchor"]),
            "--entry",
            str(files["entry"]),
            "--observations",
            str(args.observations),
            "--candles",
            str(args.candles),
            "--output",
            str(files["benchmark"]),
        ],
    )
    if code != 0:
        return code
    if args.coverage is None:
        # Inatteignable aujourd'hui : sans couverture, `c3_entry` consigne I-A.7 `not_assertable`
        # et refuse en fin de parcours (R0). Gardé pour qu'aucun `SystemExit` d'argparse ne sorte
        # de `c3_select.main` en processus si cette règle changeait.
        steps.append({"name": "select", "exit_code": 2})
        print("CHAINE ARRETEE à l'étape select : --coverage requis (D1, § A.8)", file=sys.stderr)
        return 2
    code = run_step(
        "select",
        c3_select.main,
        [
            "--manifest",
            manifest,
            "--anchor",
            str(files["anchor"]),
            "--entry",
            str(files["entry"]),
            "--observations",
            str(args.observations),
            "--coverage",
            str(args.coverage),
            "--benchmark",
            str(files["benchmark"]),
            "--output",
            str(files["select"]),
            "--markdown",
            str(out / "selection.md"),
        ],
    )
    if code != 0:
        return code
    code = run_step(
        "continuity",
        c3_continuity.main,
        [
            "--manifest",
            manifest,
            "--anchor",
            str(files["anchor"]),
            "--evaluation",
            str(args.evaluation),
            "--benchmark-eval",
            str(args.benchmark_eval),
            "--output",
            str(files["continuity"]),
        ],
    )
    if code != 0:
        return code
    paths = {
        "entry": files["entry"],
        "anchor": files["anchor"],
        "selection": files["select"],
        "continuity": files["continuity"],
        "evaluation": Path(args.evaluation),
    }
    return run_verdict(
        paths, output=out / "verdict.json", campaign=args.campaign, now=now, chain_steps=steps
    )


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--entry", type=Path, required=True)
    parser.add_argument("--anchor", type=Path, required=True)
    parser.add_argument("--selection", type=Path, required=True)
    parser.add_argument("--continuity", type=Path, required=True)
    parser.add_argument("--evaluation", type=Path, required=True)
    parser.add_argument("--campaign", default="C3A")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--now", default=None, help="Horodatage ISO UTC de generated_at, pour le déterminisme."
    )
    return parser


def build_chain_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="c3_verdict.py chain",
        description="Chaîne § L.1 complète, chaque étape en processus, code de retour contrôlé.",
    )
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--observations", type=Path, required=True)
    parser.add_argument("--coverage", type=Path, default=None)
    parser.add_argument("--candles", type=Path, default=None)
    parser.add_argument("--evaluation", type=Path, required=True)
    parser.add_argument("--benchmark-eval", type=Path, required=True)
    parser.add_argument("--registry", type=Path, required=True)
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--campaign", default="C3A")
    parser.add_argument("--now", default=None)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args_list = list(argv) if argv is not None else sys.argv[1:]
    if args_list[:1] == ["chain"]:
        return run_chain(build_chain_parser().parse_args(args_list[1:]))
    args = build_parser().parse_args(args_list)
    try:
        now = cc.parse_now(args.now)
    except ValueError as exc:
        print(f"--now: {exc}", file=sys.stderr)
        return 2
    paths = {name: getattr(args, name) for name in INPUT_NAMES}
    return run_verdict(paths, output=args.output, campaign=args.campaign, now=now)


if __name__ == "__main__":
    raise SystemExit(main())
