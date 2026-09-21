"""C3 — l'issue et la chaîne de verdict (§ G, § H, § I.1, § L.2).

Ce script n'a **aucun paramètre libre et aucune entrée humaine** : deux personnes l'exécutant sur
les mêmes artefacts obtiennent **la même chaîne**. C'est le contrat de falsifiabilité du protocole
(§ 0.6), et le rapport **cite** la chaîne au lieu de la paraphraser.

Ce qu'il fait, dans l'ordre gelé :

* § I.1 — les raisons de niveau run sont collectées, et la chaîne porte **la première de la liste de
  priorité du § H qui s'applique**. La portée d'une raison n'est jamais redite ici : elle vient de
  ``c3_common.REASON_SCOPE``, qui transcrit la table du § I.1.
* **§ H.0 — la préséance de l'estimabilité sur le verdict économique.** Tant que `E1` et `E2` ne
  sont pas satisfaites, **ni ``validé`` ni ``réfuté``** ne peuvent être prononcés, quel que soit le
  résultat des portes `Q1`, `Q2`, `Q3` : l'issue est ``inconclusif (F_NOT_ESTIMABLE)``.
* § H.1 — les trois issues en conditions nécessaires et suffisantes.
* § A.5 — un univers ``contaminated`` **ou ``unknown``** ne peut porter ni ``validé`` ni ``réfuté``.

Les statuts sont **recalculés** depuis les artefacts et **recoupés** contre ceux qu'ils portent :
un désaccord est une **violation** (exit 1), jamais une valeur recopiée.

Pure, read-only. Aucun accès base de données.

Usage::

    poetry run python scripts/audit/c3_verdict.py \\
        --entry results/c3a_entry_validation/entry.json \\
        --selection results/c3/selection.json \\
        --continuity results/c3/continuity.json \\
        --evaluation results/c3/evaluation.json \\
        --output results/c3/verdict.json

Exit codes: 0 ok, 1 violation, 2 usage ou entrée invalide (§ I.1).
"""

from __future__ import annotations

import argparse
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
import sys
from typing import Any

_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(_ROOT / "src"))
sys.path.insert(0, str(_ROOT / "scripts"))
sys.path.insert(0, str(_ROOT / "scripts" / "audit"))

import c3_common as cc  # noqa: E402

#: Raisons de niveau run qui rendent l'évaluation économique impossible (§ I.1, lignes 2 et 8 à 14).
#: `F_CANNOT_SEPARATE` n'y figure pas : elle se constate **après** que les portes ont été franchies.
BLOCKING_RUN_REASONS: tuple[str, ...] = (
    "R0_INVALID_RUN",
    "A_NO_ADMISSIBLE_CANDIDATE",
    "A_BELOW_FLOOR",
    "D_WARMUP_ANCHOR",
    "E_NO_BENCHMARK",
    "E_STAMP_MISMATCH",
    "F_NOT_ESTIMABLE",
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


def _gate_results(evaluation: Mapping[str, Any]) -> dict[str, bool]:
    """`Q1`, `Q2`, `Q3` du § F.8, évaluées sur la fenêtre d'évaluation.

    `Q1` et `Q2` lisent le **résultat propre** de la configuration ; seule `Q3` lit le comparateur.
    Les seuils viennent du § A.10 via ``c3_common`` ; les redire ici les ferait diverger (§ 0.7).
    Les trois métriques sont **obligatoires et finies** : une métrique absente ou `NaN` est une
    erreur d'entrée, pas une porte en échec.
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
    **violation**. Croire une déclaration que les séries contredisent transformerait l'estimabilité
    en champ décoratif — une configuration inactive déclarée estimable repartirait en `réfuté`.
    """
    returns = cc.require_finite_series(evaluation, "returns_config", where="evaluation")
    deltas = cc.require_finite_series(evaluation, "delta_stars", where="evaluation")
    discarded = cc.require_int(evaluation, "discarded", where="evaluation", default=0)
    if discarded < 0:
        raise cc.MissingEvidenceError("evaluation.discarded: compte négatif")

    est = cc.estimability(returns, deltas, discarded)
    payload = est.to_dict()
    payload["B_effectif"] = len(deltas)

    declared = evaluation.get("estimability")
    if declared is not None:
        if not isinstance(declared, Mapping):
            raise cc.MissingEvidenceError("evaluation.estimability: bloc attendu")
        for key, recomputed in (("E1", est.e1), ("E2", est.e2), ("ok", est.ok)):
            if key in declared and bool(declared[key]) != recomputed:
                violations.append(
                    f"estimabilité {key} déclarée {declared[key]!r}, recalculée {recomputed!r} "
                    "— le statut recalculé fait foi"
                )
        payload["declared"] = dict(declared)
    return est.ok, payload


def decide(artifacts: Mapping[str, Mapping[str, Any]], *, violations: list[str]) -> Decision:
    """L'issue du § H, et rien d'autre. Fonction pure des artefacts fournis.

    Lève ``MissingEvidenceError`` dès qu'une preuve obligatoire est absente, nulle, mal typée ou non
    finie : c'est une **erreur d'entrée** (§ I.1, code 2), pas un verdict. Aucun verdict économique
    n'est prononcé sur une preuve manquante.
    """
    entry = cc.require_mapping(artifacts, "entry", where="artefacts")
    if not cc.require_bool(entry, "ok", where="entry"):
        return Decision(
            issue=cc.ISSUE_INCONCLUSIF,
            reason="R0_INVALID_RUN",
            retained=None,
            selection_status=None,
            provenance=None,
        )

    anchor = cc.require_mapping(artifacts, "anchor", where="artefacts")
    provenance = cc.require_str(
        anchor, "universe_provenance", where="anchor", allowed=cc.PROVENANCES
    )
    selection = cc.require_mapping(artifacts, "selection", where="artefacts")
    selection_status = cc.require_str(
        selection, "status", where="selection", allowed=cc.STATUS_SELECTION
    )

    reasons: list[str] = []
    if not cc.PROVENANCE_CAN_SUPPORT_VALIDE[provenance]:
        reasons.append("P_PROVENANCE")

    if selection_status == "ABSTENTION":
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

    retained = cc.require_str(
        cc.require_mapping(selection, "retained", where="selection"),
        "identity",
        where="selection.retained",
    )

    # § B — les contrôles obligatoires de continuité, présents et typés. Une clé absente ou nulle
    # est une erreur d'entrée, jamais un contrôle réputé satisfait.
    continuity = cc.require_mapping(artifacts, "continuity", where="artefacts")
    for key, reason in (
        ("warmup_anchor_ok", "D_WARMUP_ANCHOR"),
        ("benchmark_comparable", "E_NO_BENCHMARK"),
        ("stamp_same_daily_cell", "E_STAMP_MISMATCH"),
    ):
        if not cc.require_bool(continuity, key, where="continuity"):
            reasons.append(reason)

    evaluation = cc.require_mapping(artifacts, "evaluation", where="artefacts")

    # § H.0 — l'estimabilité est préalable au verdict économique, et elle est **recalculée**.
    estimable, estimability_payload = _estimability_of(evaluation, violations=violations)
    if not estimable:
        reasons.append("F_NOT_ESTIMABLE")

    if reasons:
        return Decision(
            issue=cc.ISSUE_INCONCLUSIF,
            reason=cc.worst_reason(*reasons),
            retained=retained,
            selection_status=selection_status,
            provenance=provenance,
            gates={},
            bounds_positive=None,
            estimability=estimability_payload,
        )

    gates = _gate_results(evaluation)
    if not all(gates.values()):
        return Decision(
            issue=cc.ISSUE_REFUTE,
            reason=None,
            retained=retained,
            selection_status=selection_status,
            provenance=provenance,
            gates=gates,
            bounds_positive=None,
            estimability=estimability_payload,
        )

    bounds_positive = _bounds_all_positive(evaluation)
    if not bounds_positive:
        return Decision(
            issue=cc.ISSUE_INCONCLUSIF,
            reason="F_CANNOT_SEPARATE",
            retained=retained,
            selection_status=selection_status,
            provenance=provenance,
            gates=gates,
            bounds_positive=False,
            estimability=estimability_payload,
        )

    return Decision(
        issue=cc.ISSUE_VALIDE,
        reason=None,
        retained=retained,
        selection_status=selection_status,
        provenance=provenance,
        gates=gates,
        bounds_positive=True,
        estimability=estimability_payload,
    )


def build_verdict_string(campaign: str, decision: Decision, protocol_sha: str) -> str:
    """La chaîne canonique du § L.2 — **sans horodatage**, pour qu'elle soit reproductible."""
    parts = [
        f"C3_{campaign}",
        f"verdict={decision.issue}",
        f"raison={decision.reason or '-'}",
        f"selection={decision.retained or '-'}",
        f"statut_selection={decision.selection_status or '-'}",
        f"provenance={decision.provenance or '-'}",
        f"protocole={protocol_sha[:16]}",
    ]
    return " | ".join(parts)


def build_payload(
    artifacts: Mapping[str, Mapping[str, Any]], decision: Decision, *, campaign: str, now: datetime
) -> dict[str, Any]:
    descriptor = cc.protocol_descriptor()
    payload: dict[str, Any] = dict(cc.artifact_header(now))
    payload.update(
        {
            "campagne": campaign,
            "verdict": decision.issue,
            "raison": decision.reason,
            "selection": decision.retained,
            "statut_selection": decision.selection_status,
            "provenance": decision.provenance,
            "portes_Q": decision.gates,
            "bornes_toutes_positives": decision.bounds_positive,
            "estimabilite": decision.estimability,
            "verdict_string": build_verdict_string(campaign, decision, descriptor["sha256"]),
        }
    )
    return payload


def render_lines(payload: Mapping[str, Any]) -> list[str]:
    out = [payload["verdict_string"], ""]
    est = payload.get("estimabilite") or {}
    if est:
        out.append(
            "estimabilité : E1={E1} E2={E2} nnz={nonzero_ratio:.3f} "
            "distincts={distinct_delta_stars} écartées={discarded}".format(
                E1=est.get("E1"), E2=est.get("E2"), nonzero_ratio=est.get("nonzero_ratio", 0.0),
                distinct_delta_stars=est.get("distinct_delta_stars"), discarded=est.get("discarded"),
            )
        )
    gates = payload.get("portes_Q") or {}
    if gates:
        out.append("portes Q : " + " ".join(f"{k}={v}" for k, v in sorted(gates.items())))
    return out


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


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(list(argv) if argv is not None else None)
    if args.now is None:
        now = datetime.now(UTC)
    else:
        try:
            parsed = datetime.fromisoformat(args.now)
        except ValueError as exc:
            print(f"--now: {exc}", file=sys.stderr)
            return 2
        now = parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)

    artifacts: dict[str, Mapping[str, Any]] = {}
    for name in ("entry", "anchor", "selection", "continuity", "evaluation"):
        path = getattr(args, name)
        try:
            artifacts[name] = cc.read_json(path)
        except (OSError, ValueError) as exc:
            print(f"--{name}: {exc}", file=sys.stderr)
            return 2

    violations: list[str] = []
    try:
        decision = decide(artifacts, violations=violations)
    except cc.MissingEvidenceError as exc:
        # § I.1 — preuve obligatoire absente, nulle, mal typée ou non finie : erreur d'entrée.
        # Aucun artefact n'est écrit, aucun verdict n'est prononcé.
        print(f"ENTREE INVALIDE {exc}", file=sys.stderr)
        return 2
    payload = build_payload(artifacts, decision, campaign=args.campaign, now=now)
    digest = cc.write_json(args.output, payload)
    print("\n".join(render_lines(payload)))
    print(f"written {args.output} sha256 {digest}")
    for violation in violations:
        print(f"VIOLATION {violation}", file=sys.stderr)
    return 1 if violations else 0


if __name__ == "__main__":
    raise SystemExit(main())
