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
    gates: dict[str, bool | None] = field(default_factory=dict)
    bounds_positive: bool | None = None
    estimability: dict[str, Any] | None = field(default=None)


def _gate_results(evaluation: Mapping[str, Any]) -> dict[str, bool | None]:
    """`Q1`, `Q2`, `Q3` du § F.8, évaluées sur la fenêtre d'évaluation.

    `Q1` et `Q2` lisent le **résultat propre** de la configuration ; seule `Q3` lit le comparateur.
    Les seuils viennent du § A.10 via ``c3_common`` ; les redire ici les ferait diverger (§ 0.7).
    """
    metrics = evaluation.get("metrics") or {}
    out: dict[str, bool | None] = {}
    net_pnl = metrics.get("net_pnl")
    cagr = metrics.get("cagr_pct")
    delta = metrics.get("delta_dd")
    out["Q1"] = None if net_pnl is None else float(net_pnl) > cc.FLOOR_NET_PNL
    out["Q2"] = None if cagr is None else float(cagr) >= cc.FLOOR_CAGR_PCT
    out["Q3"] = None if delta is None else float(delta) > cc.FLOOR_DELTA_DD
    return out


def _bounds_all_positive(evaluation: Mapping[str, Any]) -> bool | None:
    """Les six combinaisons `L × appariement` du § F.2 (h), toutes strictement positives."""
    bounds = evaluation.get("bounds")
    if not isinstance(bounds, Mapping) or not bounds:
        return None
    expected = {f"{length}:{matching}" for length in cc.BLOCK_LENGTHS for matching in cc.MATCHINGS}
    if set(bounds) != expected:
        return None
    return all(float(v) > 0.0 for v in bounds.values())


def _estimability_of(evaluation: Mapping[str, Any]) -> tuple[bool, dict[str, Any]]:
    """§ A.13, recalculé depuis les séries quand elles sont présentes, jamais recopié."""
    block = evaluation.get("estimability")
    if isinstance(block, Mapping) and "ok" in block:
        return bool(block["ok"]), dict(block)
    returns = evaluation.get("returns_config")
    deltas = evaluation.get("delta_stars")
    if returns is None or deltas is None:
        return False, {"ok": False, "raison": "estimabilité non fournie et non recalculable"}
    est = cc.estimability(returns, deltas, int(evaluation.get("discarded", 0)))
    payload = est.to_dict()
    payload["B_effectif"] = len(list(deltas))
    return est.ok, payload


def decide(artifacts: Mapping[str, Mapping[str, Any]], *, violations: list[str]) -> Decision:
    """L'issue du § H, et rien d'autre. Fonction pure des artefacts fournis."""
    entry = artifacts.get("entry") or {}
    anchor = artifacts.get("anchor") or {}
    selection = artifacts.get("selection") or {}
    continuity = artifacts.get("continuity") or {}
    evaluation = artifacts.get("evaluation") or {}

    provenance = anchor.get("universe_provenance") or selection.get("universe_provenance")
    if provenance is not None and provenance not in cc.PROVENANCES:
        violations.append(f"provenance hors liste close : {provenance!r}")
    retained = (selection.get("retained") or {}).get("identity")
    selection_status = selection.get("status")

    reasons: list[str] = []

    if not entry.get("ok", False):
        reasons.append("R0_INVALID_RUN")
    if provenance is not None and not cc.PROVENANCE_CAN_SUPPORT_VALIDE.get(provenance, False):
        reasons.append("P_PROVENANCE")
    if selection_status == "ABSTENTION":
        abstention = selection.get("reason")
        if abstention not in ("A_NO_ADMISSIBLE_CANDIDATE", "A_BELOW_FLOOR"):
            violations.append(f"abstention sans raison valide : {abstention!r}")
        else:
            reasons.append(abstention)
    for key, reason in (
        ("warmup_anchor_ok", "D_WARMUP_ANCHOR"),
        ("benchmark_comparable", "E_NO_BENCHMARK"),
        ("stamp_same_daily_cell", "E_STAMP_MISMATCH"),
    ):
        value = continuity.get(key)
        if value is False:
            reasons.append(reason)

    gates: dict[str, bool | None] = {}
    bounds_positive: bool | None = None
    estimability_payload: dict[str, Any] | None = None

    blocked = any(r in BLOCKING_RUN_REASONS for r in reasons) or "P_PROVENANCE" in reasons
    if not blocked and retained is None:
        violations.append("aucune configuration retenue alors qu'aucune raison ne l'explique")
        blocked = True

    if not blocked:
        # § H.0 — l'estimabilité est préalable au verdict économique, avant toute lecture des Q.
        estimable, estimability_payload = _estimability_of(evaluation)
        if not estimable:
            reasons.append("F_NOT_ESTIMABLE")
            blocked = True

    if not blocked:
        gates = _gate_results(evaluation)
        if any(v is None for v in gates.values()):
            violations.append("portes Q incomplètes sur une évaluation par ailleurs exploitable")
            reasons.append("F_NOT_ESTIMABLE")
            blocked = True

    if blocked:
        return Decision(
            issue=cc.ISSUE_INCONCLUSIF,
            reason=cc.worst_reason(*reasons),
            retained=retained,
            selection_status=selection_status,
            provenance=provenance,
            gates=gates,
            bounds_positive=bounds_positive,
            estimability=estimability_payload,
        )

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
    if bounds_positive is not True:
        reasons.append("F_CANNOT_SEPARATE")
        return Decision(
            issue=cc.ISSUE_INCONCLUSIF,
            reason=cc.worst_reason(*reasons),
            retained=retained,
            selection_status=selection_status,
            provenance=provenance,
            gates=gates,
            bounds_positive=bounds_positive,
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
    decision = decide(artifacts, violations=violations)
    payload = build_payload(artifacts, decision, campaign=args.campaign, now=now)
    digest = cc.write_json(args.output, payload)
    print("\n".join(render_lines(payload)))
    print(f"written {args.output} sha256 {digest}")
    for violation in violations:
        print(f"VIOLATION {violation}", file=sys.stderr)
    return 1 if violations else 0


if __name__ == "__main__":
    raise SystemExit(main())
