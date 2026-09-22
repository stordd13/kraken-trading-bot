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

**Continuité → verdict (plan § 6.4, validé).** Clauses déclaratives c1/c2/c5 ``FAILED`` : l'artefact
déclare lui-même une rupture du contrat § B → refus ``R0_INVALID_RUN``, code 2. Clause 3 ``FAILED``
(liquidation terminale non normalisée) : § B.3 et § G.2 interdisent tout verdict directionnel et § I.1
ne porte aucune ligne de portée run pour ce cas → ``UndefinedIssueError``, **code 2, rien publié** —
**convention d'outillage datée du 21/09** (plan § 6.1, conduite (b)), une assignation de code hors
table assumée comme telle ; l'amendement daté (a) est dû à l'ouverture de C3b.

**Confinement des verdicts synthétiques (plan § 6.6, validé).** § L.1 : sur données réelles, C3a ne
peut produire que non-recevabilité et abstention ; ``validé`` / ``réfuté`` sont structurellement
inatteignables tant que C3b n'a pas livré l'exécution continue et la preuve de départ à plat.
L'outillage l'exécute : ``evaluation.synthetic`` est **obligatoire et strictement typé** ; ``false``
(évaluation réelle) est **refusé** (code 2, rien publié) ; ``true`` préfixe la chaîne ``C3_SYNTH_``
et écrit ``portee`` en première ligne.

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
UNDEFINED_ISSUE_MESSAGE = (
    "issue non définie par le texte gelé, amendement pendant (§ 6.1) : liquidation terminale non "
    "normalisée sur l'artefact d'évaluation — § B.3 et § G.2 interdisent tout verdict directionnel, "
    "§ I.1 ne porte aucune ligne de portée run pour ce cas ; convention d'outillage datée du 21/09 : "
    "refus de produire une issue, code 2, rien publié"
)
REAL_EVALUATION_MESSAGE = (
    "évaluation réelle non exerçable par l'outillage C3a — § L.1 : l'exécution continue et la preuve "
    "de départ à plat relèvent de C3b ; seule une évaluation déclarée synthétique est admise"
)


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


def _continuity_gates(continuity: Mapping[str, Any], *, retained: str) -> tuple[list[str], str]:
    """Ce que la continuité impose au verdict (plan § 6.4) ; renvoie (raisons run, état agrégé).

    * l'évaluation doit être celle de la configuration retenue (§ H.1) — sinon refus R0 ;
    * c1, c2, c5 ``FAILED`` : l'artefact déclare une rupture du contrat § B — refus R0, code 2 ;
    * c3 ``FAILED`` ou ``liquidation_normalised`` faux : issue non définie par le texte gelé —
      ``UndefinedIssueError``, code 2, rien publié (convention datée du 21/09, plan § 6.1) ;
    * ``warmup_anchor_ok``, ``benchmark_comparable``, ``stamp_same_daily_cell`` faux : raisons run
      ``D_WARMUP_ANCHOR``, ``E_NO_BENCHMARK``, ``E_STAMP_MISMATCH`` (§ I.1 l.10-12).

    Les contrôles sont obligatoires et typés : une clé absente ou nulle est une erreur d'entrée,
    jamais un contrôle réputé satisfait.
    """
    state = cc.require_str(continuity, "state", where="continuity", allowed=cc.CONTINUITY_STATES)
    clauses = cc.require_mapping(continuity, "clauses", where="continuity")
    states: dict[str, str] = {}
    for key in ("c1", "c2", "c3", "c4", "c5"):
        block = cc.require_mapping(clauses, key, where="continuity.clauses")
        states[key] = cc.require_str(
            block, "state", where=f"continuity.clauses.{key}", allowed=cc.CONTINUITY_STATES
        )
    identity = cc.require_str(continuity, "identity", where="continuity")
    if identity != retained:
        raise cc.EntryRefusedError(
            "R0_INVALID_RUN",
            f"l'artefact de continuité porte la configuration {identity[:16]}, la sélection a retenu "
            f"{retained[:16]} — ce n'est pas l'évaluation de la configuration retenue (§ H.1)",
        )
    for key in ("c1", "c2", "c5"):
        if states[key] == "FAILED":
            detail = cc.require_str(clauses[key], "detail", where=f"continuity.clauses.{key}")
            raise cc.EntryRefusedError(
                "R0_INVALID_RUN",
                f"clause {key} de continuité en échec — l'artefact déclare une rupture du contrat "
                f"§ B : {detail}",
            )
    normalised = cc.nullable_bool(continuity, "liquidation_normalised", where="continuity")
    if states["c3"] == "FAILED" or normalised is False:
        raise cc.UndefinedIssueError(UNDEFINED_ISSUE_MESSAGE)
    reasons: list[str] = []
    for key, reason in (
        ("warmup_anchor_ok", "D_WARMUP_ANCHOR"),
        ("benchmark_comparable", "E_NO_BENCHMARK"),
        ("stamp_same_daily_cell", "E_STAMP_MISMATCH"),
    ):
        if not cc.require_bool(continuity, key, where="continuity"):
            reasons.append(reason)
    return reasons, state


def decide(artifacts: Mapping[str, Mapping[str, Any]], *, violations: list[str]) -> Decision:
    """L'issue du § H, et rien d'autre. Fonction pure des artefacts fournis.

    Lève ``MissingEvidenceError`` dès qu'une preuve obligatoire est absente, nulle, mal typée ou hors
    liste close — **erreur d'entrée** (§ I.1 ligne 2, code 2), pas un verdict — et
    ``InvalidValueError`` sur une valeur non finie ou hors domaine — **violation** (§ I.1 ligne 15,
    code 1), pas un verdict non plus. Aucun verdict économique n'est prononcé sur une preuve manquante
    ou invalide. ``UndefinedIssueError`` (clause 3 en échec) et ``EntryRefusedError`` (refus) sortent
    en code 2 sans rien publier.
    """
    entry = cc.require_mapping(artifacts, "entry", where="artefacts")
    entry_ok = cc.require_bool(entry, "ok", where="entry")
    refusal = cc.nullable_mapping(entry, "refusal", where="entry")
    # Le contrat de `entry.json` (c3_entry) : `ok` <=> `refusal` est null. Les combinaisons
    # incohérentes sont des violations de l'instrument (§ I.1 l.15), jamais un verdict.
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
        # § I.1, lignes 2 et 5 : refus d'entrée -> code 2, la chaîne s'arrête, rien n'est publié.
        raise cc.EntryRefusedError(reason, cc.require_str(refusal, "detail", where="entry.refusal"))

    anchor = cc.require_mapping(artifacts, "anchor", where="artefacts")
    provenance = cc.require_str(
        anchor, "universe_provenance", where="anchor", allowed=cc.PROVENANCES
    )
    selection = cc.require_mapping(artifacts, "selection", where="artefacts")
    selection_status = cc.require_str(
        selection, "status", where="selection", allowed=cc.STATUS_SELECTION
    )
    # Le statut de sélection est **dérivable** de la provenance et du résultat (table de
    # `c3_select`) : il est recalculé ici et recoupé au déclaré — un désaccord est une violation.
    selection_provenance = cc.require_str(
        selection, "provenance", where="selection", allowed=cc.PROVENANCES
    )
    if selection_provenance != provenance:
        violations.append(
            f"selection.provenance {selection_provenance!r} != anchor.universe_provenance "
            f"{provenance!r} — le manifeste n'a qu'une provenance"
        )
    retained_block = cc.nullable_mapping(selection, "retained", where="selection")
    if retained_block is None:
        derived_status = "ABSTENTION"
    elif cc.PROVENANCE_CAN_SUPPORT_VALIDE[provenance]:
        derived_status = "SÉLECTION_VALIDE"
    else:
        derived_status = "SÉLECTION_DESCRIPTIVE"
    if derived_status != selection_status:
        violations.append(
            f"selection.status déclaré {selection_status!r}, dérivé {derived_status!r} de "
            f"(provenance {provenance!r}, retenu {retained_block is not None}) — le statut dérivé fait foi"
        )

    reasons: list[str] = []
    if not cc.PROVENANCE_CAN_SUPPORT_VALIDE[provenance]:
        reasons.append("P_PROVENANCE")

    if retained_block is None:
        reasons.append(
            cc.require_str(
                selection,
                "reason",
                where="selection",
                allowed=("A_NO_ADMISSIBLE_CANDIDATE", "A_BELOW_FLOOR"),
            )
        )
        return Decision(
            issue=cc.ISSUE_INCONCLUSIF,
            reason=cc.worst_reason(*reasons),
            retained=None,
            selection_status=selection_status,
            provenance=provenance,
        )

    retained = cc.require_str(retained_block, "identity", where="selection.retained")

    # § B — la continuité (plan § 6.4) : refus, issue non définie, ou raisons run.
    continuity = cc.require_mapping(artifacts, "continuity", where="artefacts")
    continuity_reasons, continuity_state = _continuity_gates(continuity, retained=retained)
    reasons.extend(continuity_reasons)

    evaluation = cc.require_mapping(artifacts, "evaluation", where="artefacts")
    # Confinement (§ L.1, plan § 6.6) : déclaration obligatoire, strictement typée ; une évaluation
    # réelle n'est pas exerçable par l'outillage C3a — refus, code 2, rien publié.
    synthetic = cc.require_bool(evaluation, "synthetic", where="evaluation")
    if not synthetic:
        raise cc.EntryRefusedError("R0_INVALID_RUN", REAL_EVALUATION_MESSAGE)

    # § H.0 — l'estimabilité est préalable au verdict économique, et elle est **recalculée**.
    estimable, estimability_payload = _estimability_of(evaluation, violations=violations)
    if not estimable:
        reasons.append("F_NOT_ESTIMABLE")

    common: dict[str, Any] = {
        "retained": retained,
        "selection_status": selection_status,
        "provenance": provenance,
        "estimability": estimability_payload,
        "continuity_state": continuity_state,
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

    gates = _gate_results(evaluation)
    if not all(gates.values()):
        return Decision(
            issue=cc.ISSUE_REFUTE, reason=None, gates=gates, bounds_positive=None, **common
        )

    bounds_positive = _bounds_all_positive(evaluation)
    if not bounds_positive:
        return Decision(
            issue=cc.ISSUE_INCONCLUSIF,
            reason="F_CANNOT_SEPARATE",
            gates=gates,
            bounds_positive=False,
            **common,
        )

    return Decision(issue=cc.ISSUE_VALIDE, reason=None, gates=gates, bounds_positive=True, **common)


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


def verify_chain(
    raws: Mapping[str, Mapping[str, Any]], paths: Mapping[str, Path]
) -> tuple[list[str], list[dict[str, Any]]]:
    """Exige le succès enregistré de chaque amont (sinon refus, code 2) et recoupe les empreintes
    entre elles et avec les fichiers fournis (discordance = violation, code 1).

    Recoupements : ``manifest`` identique entre anchor, entry, selection et continuity ;
    ``observations`` identique entre entry et selection ; ``anchor.json`` tel que consommé par entry,
    selection et continuity ; ``entry.json`` tel que consommé par selection ; ``evaluation.json`` tel
    que consommé par continuity ; ``protocole.sha256`` identique partout et égal au courant.
    """
    for name in ("anchor", "selection", "continuity"):
        cc.require_upstream_ok(raws[name], where=name)
    entry = raws["entry"]
    if cc.require_bool(entry, "invalide", where="entry"):
        raise cc.EntryRefusedError(
            "R0_INVALID_RUN", "entry.json est l'artefact diagnostic d'une violation (invalide)"
        )
    checks: list[dict[str, Any]] = []
    violations: list[str] = []

    def record(name: str, ok: bool, detail: str) -> None:
        checks.append({"check": name, "ok": ok, "detail": detail})
        if not ok:
            violations.append(f"chaîne : {name} — {detail}")

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
    if payload["invalide"]:
        out = ["ARTEFACT INVALIDE — aucun verdict, aucune chaîne citable"]
        out += [f"  violation : {v}" for v in payload["violations"]]
        return out
    out: list[str] = []
    if payload["portee"] is not None:
        # Plan § 6.6 (3) : la portée d'un exercice synthétique s'imprime avant la chaîne.
        out.append(f"PORTEE : {payload['portee']}")
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
    """Lit les cinq artefacts, vérifie la chaîne, décide, écrit ``verdict.json`` (0 ou 1) ou rien (2)."""
    artifacts: dict[str, Mapping[str, Any]] = {}
    for name in INPUT_NAMES:
        try:
            artifacts[name] = cc.read_json(paths[name])
        except (OSError, ValueError) as exc:
            print(f"--{name}: {exc}", file=sys.stderr)
            return 2
    inputs: dict[str, Path] = {name: Path(paths[name]) for name in INPUT_NAMES}
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
        chain_violations, chain["checks"] = verify_chain(artifacts, inputs)
        chain["verified"] = not chain_violations
        violations += chain_violations
        variant_key = cc.require_str(artifacts["anchor"], "variant_key", where="anchor")
        recorded = cc.require_mapping(artifacts["entry"], "inputs_sha256", where="entry")
        observations_sha256 = cc.require_str(recorded, "observations", where="entry.inputs_sha256")
        decision = decide(artifacts, violations=violations)
    except cc.UndefinedIssueError as exc:
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
        # § I.1 — preuve obligatoire absente, nulle, mal typée ou hors liste close : code 2.
        print(f"ENTREE INVALIDE {exc}", file=sys.stderr)
        return 2
    except (cc.InvalidValueError, cc.NonFiniteValueError) as exc:
        # § F.7 -> § I.1, ligne 15 — non-finitude ou domaine : violation, code 1, diagnostic écrit.
        # `NonFiniteValueError` (levée par `canon`) n'est pas une `InvalidValueError` : routée ici
        # explicitement, comme dans les quatre autres modules (revue R3 d).
        violations.append(str(exc))

    if violations:
        # § I.1, ligne 15 — une violation n'est pas un résultat : aucun verdict normal n'est publié.
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
