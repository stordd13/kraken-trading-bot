"""Rejeu diagnostic grid — verdict de famille (prespec § G, § H).

Ce script est le dernier pas de la chaîne (§ L, étape 11). Il ne consomme que les artefacts JSON
gelés — ``validation_campaign.json``, ``data_coverage.json``, ``benchmark.json``,
``signatures.json``, ``clamp.json``, ``effect.json``, ``validation_analysis.json`` — n'a **aucun
paramètre libre et aucune entrée humaine**, et émet ``verdict.json`` plus la **chaîne de verdict**
canonique. Deux personnes l'exécutant sur les mêmes artefacts obtiennent la même chaîne : c'est le
contrat de falsifiabilité du chantier, et le rapport **cite** la chaîne au lieu de la paraphraser.

Ce qu'il fait, dans l'ordre gelé :

* § G.2 — porte au niveau du run, **avant tout le reste** : une assertion § I-A en échec donne
  ``inconclusif (R0_INVALID_RUN)`` et STOP ; ``b4_flags`` non muet **après** les assertions de
  présence (I-A.13) donne ``inconclusif (R1_ACCOUNTING_FLAG)`` et STOP. Pas de sauvetage partiel ;
* § G.1 — statut de config, premier match l'emporte, **recalculé** depuis les artefacts (le statut
  que ``effect.json`` porte est recoupé, jamais recopié : un désaccord est une violation) ;
* § G.3 — verdict de paire, puis choix du représentant **après** coup, parmi ``C`` ;
* § G.4 — verdict de famille ;
* § H — la chaîne de verdict et la liste fermée ``rc.REASON_PRIORITY``, dans cet ordre de priorité.

Les non-règles du § G.5 sont codées en creux, et chacune est prouvée par un test : la
**dégénérescence** (§ A), le **clamp** (§ B), ``train`` / ``test``, le **Sharpe** (§ F.1) et le
multiple de frais **G3** (§ F.3) ne changent jamais un verdict, dans aucune direction.

Pure, read-only.

Usage::

    poetry run python scripts/audit/rejeu_verdict.py \\
        --validation-campaign results/rejeu_grid_20260919/validation_campaign.json \\
        --validation-analysis results/rejeu_grid_20260919/validation_analysis.json \\
        --data-coverage results/rejeu_grid_20260919/data_coverage.json \\
        --benchmark results/rejeu_grid_20260919/benchmark.json \\
        --signatures results/rejeu_grid_20260919/signatures.json \\
        --clamp results/rejeu_grid_20260919/clamp.json \\
        --effect results/rejeu_grid_20260919/effect.json \\
        --output results/rejeu_grid_20260919/verdict.json

Exit codes: 0 ok, 1 violation, 2 usage or input error.
"""

from __future__ import annotations

import argparse
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
import hashlib
import math
from pathlib import Path
import sys
from typing import Any

_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(_ROOT / "src"))
sys.path.insert(0, str(_ROOT / "scripts"))
sys.path.insert(0, str(_ROOT / "scripts" / "audit"))

import rejeu_common as rc  # noqa: E402
import run_p7_grid_search as p7  # noqa: E402

PRESPEC_RELPATH = "docs/rejeu_grid_prespec.md"
OUTPUT_DIR = rc.PROJECT_ROOT / "results" / "rejeu_grid_20260919"
DEFAULT_VALIDATION_CAMPAIGN = OUTPUT_DIR / "validation_campaign.json"
DEFAULT_VALIDATION_ANALYSIS = OUTPUT_DIR / "validation_analysis.json"
DEFAULT_DATA_COVERAGE = OUTPUT_DIR / "data_coverage.json"
DEFAULT_BENCHMARK = OUTPUT_DIR / "benchmark.json"
DEFAULT_SIGNATURES = OUTPUT_DIR / "signatures.json"
DEFAULT_CLAMP = OUTPUT_DIR / "clamp.json"
DEFAULT_EFFECT = OUTPUT_DIR / "effect.json"
DEFAULT_OUTPUT = OUTPUT_DIR / "verdict.json"

#: § I-A.13 is the ONLY assertion whose failure means "b4_flags spoke": the frozen order of § I-A
#: stops the validation at the first failure, so I-A.13 is evaluated only once I-A.1..I-A.12 have
#: passed — exactly the "APRÈS § I-A.8 et § I-A.12" of § G.2. Any other failed assertion is R0.
B4_FLAGS_ASSERTION = "I-A.13"

#: § F.6 clause 1, per pair. The closed list of § H carries the family-level D_NO_ADMISSIBLE_PAIR;
#: this is the per-pair name the pre-specification uses for the same fact.
REASON_NOT_ADMISSIBLE = "D_NOT_ADMISSIBLE"
#: § G.3 — the reason of a `dépriorisation`. It is NOT in ``rc.REASON_PRIORITY``, which is the
#: closed list of the *inconclusif* reasons (§ H).
REASON_POINT_NEGATIVE = "G_POINT_NEGATIVE"

#: § D.3, frozen: "aucun résultat SOL ne peut produire un verdict candidat — ni un verdict
#: dépriorisation", and "chaque ligne SOL porte le tag DESCRIPTIF". A descriptif pair does not
#: vote (§ G.4), so SOL is excluded from the economic verdict while staying fully inside the
#: technical diagnosis (§ A, § B, warmup, raw metrics). This is an extension of the literal brief
#: (which only forbids `candidat`), flagged as such in the report.
NON_VOTING_PAIRS: tuple[str, ...] = ("SOL/USDC",)

#: § F.4 — the declared fallback. With a frozen λ the bound is "une analyse de sensibilité, sans
#: garantie de couverture 95 %", so **no `candidat` can rest on it**: the run can then only return
#: `dépriorisation` or `inconclusif`.
LAMBDA_MODE_REESTIMATED = "reestimated"
LAMBDA_MODE_FROZEN = "frozen_sensitivity"

#: The single canonical line the report cites (§ L).
VERDICT_LINE_TAG = "REJEU_GRID_20260919"

#: The six frozen combinations of § G.3: 3 block lengths x 2 matchings. A `candidat` needs
#: ``LB_j > 0`` in **all six**, on the **same** configuration.
SIX_COMBINATIONS: tuple[tuple[str, str], ...] = tuple(
    (str(length), matching) for length in rc.BLOCK_LENGTHS for matching in rc.MATCHINGS
)

POINT_GATES: tuple[str, ...] = ("G1", "G2", "G4")

#: The per-pair reasons the ladder of § G.1 can produce, used to filter the modal gate of § F.6
#: (an ELIGIBLE config carries a point gate name there, never a coverage reason).
LADDER_REASONS: frozenset[str] = frozenset(
    {
        REASON_NOT_ADMISSIBLE,
        "D_WARMUP_W2",
        "E_NO_BENCHMARK",
        "C_COVERAGE",
        "F_NOT_ESTIMABLE",
    }
)


# ---------------------------------------------------------------------------
# Inputs
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Artifact:
    """One frozen JSON input: its payload (None when absent or unreadable) and its sha256."""

    name: str
    path: Path
    payload: Any
    sha256: str | None
    error: str | None

    @property
    def mapping(self) -> Mapping[str, Any]:
        return self.payload if isinstance(self.payload, Mapping) else {}


def load_artifact(name: str, path: Path) -> Artifact:
    """Read one artifact. A missing or malformed file is a fact of the verdict, never a crash."""
    path = Path(path)
    if not path.exists():
        return Artifact(name, path, None, None, "missing")
    raw = path.read_bytes()
    digest = hashlib.sha256(raw).hexdigest()
    try:
        payload = rc.read_json(path)
    except (ValueError, UnicodeDecodeError) as exc:
        return Artifact(name, path, None, digest, f"unparseable: {exc}")
    return Artifact(name, path, payload, digest, None)


def prespec_descriptor() -> dict[str, str]:
    path = rc.PROJECT_ROOT / PRESPEC_RELPATH
    digest = hashlib.sha256(path.read_bytes()).hexdigest() if path.exists() else ""
    return {"path": PRESPEC_RELPATH, "sha256": digest}


def _finite(value: Any) -> bool:
    """True for a real, finite number. None / NaN / Inf are never compared to a threshold."""
    if value is None or isinstance(value, bool):
        return False
    try:
        return math.isfinite(float(value))
    except (TypeError, ValueError):
        return False


def _as_int(value: Any) -> int | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


# ---------------------------------------------------------------------------
# § G.2 — the run-level gate, before everything else
# ---------------------------------------------------------------------------


def run_gate(validation: Artifact) -> tuple[str | None, str]:
    """§ G.2 — R0 / R1 or nothing. Returns (reason, detail).

    No partial salvage: the same engine produced the 96 entries, so one unresolved accounting
    anomaly is evidence that the accounting is not reconciled in general. An entry carrying
    ``"error"`` is a **job** failure, owned by the resume rule of § 0.4, and then R0.
    """
    if validation.payload is None:
        return "R0_INVALID_RUN", f"validation_campaign.json {validation.error or 'unreadable'}"
    block = validation.mapping
    failed = [str(item) for item in block.get("failed") or []]
    others = [item for item in failed if item != B4_FLAGS_ASSERTION]
    if others:
        return "R0_INVALID_RUN", "failed campaign assertions: " + ", ".join(sorted(others))
    if B4_FLAGS_ASSERTION in failed:
        return (
            "R1_ACCOUNTING_FLAG",
            f"{B4_FLAGS_ASSERTION} failed: b4_flags spoke after the presence assertions",
        )
    if block.get("ok") is not True or _as_int(block.get("exit_code")) != 0:
        return (
            "R0_INVALID_RUN",
            f"validation_campaign ok={block.get('ok')!r} exit_code={block.get('exit_code')!r}",
        )
    return None, "campaign validity ok (exit 0), b4_flags mute after I-A.8 / I-A.12"


def analysis_gate(validation: Artifact) -> tuple[bool, str]:
    """§ I-B — a failure gives ``inconclusif (F_NOT_ESTIMABLE)`` WITHOUT touching § I-A.

    The analyses are not the campaign: an unusable inference never makes the run invalid, it makes
    the inference unusable. The reason still competes by priority with the pair's own reason
    (``rc.REASON_PRIORITY``), so a pair that is below coverage keeps ``C_COVERAGE``.
    """
    if validation.payload is None:
        return False, f"validation_analysis.json {validation.error or 'unreadable'}"
    block = validation.mapping
    if block.get("ok") is not True or _as_int(block.get("exit_code")) != 0:
        failed = ", ".join(str(item) for item in block.get("failed") or []) or "unstated"
        return False, f"analysis validity failed: {failed}"
    return True, "analysis validity ok (exit 0)"


# ---------------------------------------------------------------------------
# § G.1 — config status, first match wins
# ---------------------------------------------------------------------------


def config_status(
    *,
    admissible: bool,
    warmup_class: str,
    benchmark_comparable: bool,
    cycles: int | None,
    nnz_value: int | None,
    delta_dd: Any,
    delta_sigma: Any,
) -> tuple[str, str | None]:
    """The § G.1 ladder. ``cycles`` unmeasurable falls to clause 4-5, never to "below coverage":
    pretending the quantity was measured would be a defect, not a conservative choice.
    """
    if not admissible:
        return rc.STATUS_DESCRIPTIF, REASON_NOT_ADMISSIBLE
    if warmup_class == "W2":
        return rc.STATUS_DESCRIPTIF, "D_WARMUP_W2"
    if not benchmark_comparable:
        return rc.STATUS_NO_BENCHMARK, "E_NO_BENCHMARK"
    if cycles is None:
        return rc.STATUS_NOT_ESTIMABLE, "F_NOT_ESTIMABLE"
    if cycles < rc.CYCLES_MIN:
        return rc.STATUS_BELOW_COVERAGE, "C_COVERAGE"
    if nnz_value is None or nnz_value < rc.NNZ_MIN:
        return rc.STATUS_NOT_ESTIMABLE, "F_NOT_ESTIMABLE"
    if not _finite(delta_dd) or not _finite(delta_sigma):
        return rc.STATUS_NOT_ESTIMABLE, "F_NOT_ESTIMABLE"
    return rc.STATUS_ELIGIBLE, None


def first_failing_point_gate(gates: Mapping[str, Any]) -> str | None:
    """G1, then G2, then G4 — the order the report prints, so the reason is never a taste."""
    for name in POINT_GATES:
        if gates.get(name) is not True:
            return name
    return None


def lb_all_six_positive(lb: Any) -> bool:
    """``LB_j > 0`` in the SIX frozen combinations (3 block lengths x 2 matchings).

    Recomputed from ``LB`` itself, never read from ``LB_all_six_positive``: a published flag that
    disagrees with the numbers it summarises is a violation, and § G.3 names the numbers.
    A missing combination is **not** six combinations, so it can never carry a `candidat`.
    """
    if not isinstance(lb, Mapping):
        return False
    for label, matching in SIX_COMBINATIONS:
        block = lb.get(label)
        if not isinstance(block, Mapping):
            return False
        value = block.get(matching)
        if not _finite(value) or float(value) <= 0.0:
            return False
    return True


@dataclass(frozen=True)
class ConfigView:
    """One configuration as the verdict reads it — nothing else of the entry is decisional."""

    key: str
    status: str
    first_failing_gate: str | None
    passes_gates: bool
    holds_six_bounds: bool
    delta_dd: float | None
    delta_sigma: float | None
    mdd_daily: float | None
    params_hash: str

    @property
    def eligible(self) -> bool:
        return self.status == rc.STATUS_ELIGIBLE


def _params_hash(params: Any) -> str:
    """``run_p7_grid_search.params_hash`` — the last, always-deterministic tie-break of § G.3."""
    return p7.params_hash(params if isinstance(params, dict) else {})


def read_config(
    key: str,
    config: Mapping[str, Any],
    *,
    admissible: bool,
    warmup_class: str,
    benchmark_comparable: bool,
    violations: list[str],
) -> ConfigView:
    """Recompute § G.1 for one config and cross-check what ``effect.json`` recorded."""
    cycles = _as_int(config.get("cycles"))
    nnz_value = _as_int(config.get("nnz"))
    delta_dd = config.get("delta_dd")
    delta_sigma = config.get("delta_sigma")
    status, gate = config_status(
        admissible=admissible,
        warmup_class=warmup_class,
        benchmark_comparable=benchmark_comparable,
        cycles=cycles,
        nnz_value=nnz_value,
        delta_dd=delta_dd,
        delta_sigma=delta_sigma,
    )
    gates = config.get("gates") if isinstance(config.get("gates"), Mapping) else {}
    passes = False
    if status == rc.STATUS_ELIGIBLE:
        passes = all(gates.get(name) is True for name in POINT_GATES)
        gate = first_failing_point_gate(gates)
    recorded_status = config.get("status")
    if recorded_status is not None and recorded_status != status:
        violations.append(
            f"{key}: effect.json records status {recorded_status!r}, the § G.1 ladder "
            f"recomputes {status!r}"
        )
    recorded_passes = config.get("passes_gates")
    if isinstance(recorded_passes, bool) and recorded_passes != passes:
        violations.append(
            f"{key}: effect.json records passes_gates {recorded_passes}, G1 ∧ G2 ∧ G4 "
            f"recomputes {passes}"
        )
    holds = lb_all_six_positive(config.get("LB"))
    recorded_six = config.get("LB_all_six_positive")
    if isinstance(recorded_six, bool) and recorded_six != holds:
        violations.append(
            f"{key}: effect.json records LB_all_six_positive {recorded_six}, the six frozen "
            f"combinations recompute {holds}"
        )
    return ConfigView(
        key=key,
        status=status,
        first_failing_gate=gate,
        passes_gates=passes,
        holds_six_bounds=holds,
        delta_dd=float(delta_dd) if _finite(delta_dd) else None,
        delta_sigma=float(delta_sigma) if _finite(delta_sigma) else None,
        mdd_daily=float(config.get("mdd_daily")) if _finite(config.get("mdd_daily")) else None,
        params_hash=_params_hash(config.get("params")),
    )


def modal_failing_gate(configs: Sequence[ConfigView]) -> str | None:
    """§ F.6 — the reason of an empty eligible set is the **modal** failing gate, never a taste.

    Ties are broken by ``rc.REASON_PRIORITY`` then alphabetically, so the answer is a function of
    the artifacts alone. Point gates are filtered out: an empty ``J`` means no config reached them.
    """
    counts: dict[str, int] = {}
    for view in configs:
        gate = view.first_failing_gate
        if gate in LADDER_REASONS:
            counts[gate] = counts.get(gate, 0) + 1
    if not counts:
        return None
    best = max(counts.values())
    tied = sorted(gate for gate, count in counts.items() if count == best)
    order = {name: position for position, name in enumerate(rc.REASON_PRIORITY)}
    return min(tied, key=lambda gate: (order.get(gate, len(order)), gate))


def worst_reason(*reasons: str | None) -> str | None:
    """The highest-priority reason of ``rc.REASON_PRIORITY`` among those given (§ H)."""
    order = {name: position for position, name in enumerate(rc.REASON_PRIORITY)}
    known = [reason for reason in reasons if reason]
    if not known:
        return None
    return min(known, key=lambda reason: (order.get(reason, len(order)), reason))


# ---------------------------------------------------------------------------
# § G.3 — pair verdict, then the representative, chosen AFTER
# ---------------------------------------------------------------------------


def choose_representative(candidates: Sequence[ConfigView]) -> str | None:
    """§ G.3 — ``argmax Δ̂^dd``; ties by larger ``Δ̂^σ``, then smaller ``max_drawdown_pct_daily``,
    then lexicographically smallest ``params_hash``. Deterministic down to the last step.

    The representative is named as the **carrier of the evidence**, never as a selection: this run
    selects nothing (§ 0.1, § G.5).
    """
    if not candidates:
        return None
    ranked = sorted(
        candidates,
        key=lambda view: (
            -(view.delta_dd if view.delta_dd is not None else -math.inf),
            -(view.delta_sigma if view.delta_sigma is not None else -math.inf),
            view.mdd_daily if view.mdd_daily is not None else math.inf,
            view.params_hash,
        ),
    )
    return ranked[0].key


@dataclass
class PairVerdict:
    pair: str
    verdict: str
    reason: str | None
    representative: str | None
    n_eligible: int
    n_passing_gates: int
    n_candidat: int
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "verdict": self.verdict,
            "reason": self.reason,
            "representative": self.representative,
            "n_eligible": self.n_eligible,
            "n_passing_gates": self.n_passing_gates,
            "n_candidat": self.n_candidat,
        }


def pair_verdict(
    pair: str,
    *,
    effect_pair: Mapping[str, Any] | None,
    admissible: bool,
    benchmark_comparable: bool,
    analysis_ok: bool,
    lambda_mode: str,
    violations: list[str],
) -> PairVerdict:
    """§ G.3, applied to one pair. Every branch is a fact of the artifacts, never a judgement."""
    notes: list[str] = []
    if effect_pair is None:
        # No analysis block at all: the pair is descriptif if the data already said so, and
        # otherwise the inference simply does not exist — never a silent pass.
        if not admissible:
            return PairVerdict(pair, rc.VERDICT_DESCRIPTIF, REASON_NOT_ADMISSIBLE, None, 0, 0, 0,
                               ["no effect.json block for this pair"])
        return PairVerdict(pair, rc.VERDICT_INCONCLUSIF, "F_NOT_ESTIMABLE", None, 0, 0, 0,
                           ["no effect.json block for this pair"])

    warmup_class = str(effect_pair.get("warmup_class") or "")
    if warmup_class not in {"W0", "W1", "W2"}:
        # § I-A.8 / § D.4: an unresolved warmup class is resolved by keeping the strictest one.
        notes.append(f"warmup class {warmup_class!r} unknown — strictest (W2) kept")
        warmup_class = "W2"
    recorded_admissible = effect_pair.get("admissible")
    if isinstance(recorded_admissible, bool) and recorded_admissible != admissible:
        violations.append(
            f"{pair}: data_coverage.json says admissible={admissible}, effect.json recorded "
            f"{recorded_admissible}"
        )
    recorded_comparable = effect_pair.get("benchmark_comparable")
    if isinstance(recorded_comparable, bool) and recorded_comparable != benchmark_comparable:
        violations.append(
            f"{pair}: benchmark.json says comparable={benchmark_comparable}, effect.json "
            f"recorded {recorded_comparable}"
        )

    configs_block = effect_pair.get("configs")
    configs_block = configs_block if isinstance(configs_block, Mapping) else {}
    views = [
        read_config(
            key,
            config if isinstance(config, Mapping) else {},
            admissible=admissible,
            warmup_class=warmup_class,
            benchmark_comparable=benchmark_comparable,
            violations=violations,
        )
        for key, config in sorted(configs_block.items())
    ]
    eligible = [view for view in views if view.eligible]
    passing = [view for view in eligible if view.passes_gates]
    # § G.3 — C needs the SAME configuration to pass the gates AND to hold the six bounds.
    carriers = [view for view in passing if view.holds_six_bounds]
    counts = (len(eligible), len(passing), len(carriers))

    # --- the § G.3 ladder, first match wins -------------------------------------------------
    if not admissible or warmup_class == "W2":
        reason = REASON_NOT_ADMISSIBLE if not admissible else "D_WARMUP_W2"
        return PairVerdict(pair, rc.VERDICT_DESCRIPTIF, reason, None, *counts, notes)
    if not benchmark_comparable:
        return PairVerdict(pair, rc.VERDICT_INCONCLUSIF, "E_NO_BENCHMARK", None, *counts, notes)
    if not eligible:
        reason = modal_failing_gate(views) or "F_NOT_ESTIMABLE"
        return PairVerdict(pair, rc.VERDICT_INCONCLUSIF, reason, None, *counts, notes)

    if carriers:
        verdict, reason = rc.VERDICT_CANDIDAT, None
    elif not passing:
        verdict, reason = rc.VERDICT_DEPRIORISATION, REASON_POINT_NEGATIVE
    else:
        verdict, reason = rc.VERDICT_INCONCLUSIF, "F_CANNOT_SEPARATE"

    # § F.4 — with a frozen λ the bound carries no 95 % coverage guarantee: `candidat` becomes
    # UNREACHABLE and the run can only return `dépriorisation` or `inconclusif`.
    if verdict == rc.VERDICT_CANDIDAT and lambda_mode != LAMBDA_MODE_REESTIMATED:
        verdict, reason = rc.VERDICT_INCONCLUSIF, "F_NOT_ESTIMABLE"
        notes.append(
            "λ frozen (analyse de sensibilité, sans garantie de couverture 95 %) — candidat "
            "unreachable (§ F.4)"
        )

    # § I-B — an unusable inference gives inconclusif (F_NOT_ESTIMABLE) without touching § I-A.
    if not analysis_ok:
        reason = worst_reason(reason if verdict == rc.VERDICT_INCONCLUSIF else None,
                              "F_NOT_ESTIMABLE")
        verdict = rc.VERDICT_INCONCLUSIF
        notes.append("validation_analysis.json is not ok — the inference is unusable (§ I-B)")

    representative = choose_representative(carriers) if verdict == rc.VERDICT_CANDIDAT else None
    return PairVerdict(pair, verdict, reason, representative, *counts, notes)


def apply_non_voting(result: PairVerdict) -> PairVerdict:
    """§ D.3 — SOL contributes NEITHER `candidat` NOR `dépriorisation`, and carries DESCRIPTIF.

    A descriptif pair does not vote (§ G.4), so the pair is excluded from the **economic** verdict
    while staying fully inside the technical diagnosis. Its measured reason is kept, so the
    artifact still says *why* — the exclusion is never silent.
    """
    if result.pair not in NON_VOTING_PAIRS:
        return result
    if result.verdict == rc.VERDICT_DESCRIPTIF:
        return result
    result.notes.append(
        f"{result.pair} measured {result.verdict} ({result.reason or '-'}) — § D.3 freezes it as "
        "descriptif: it can found neither candidat nor dépriorisation"
    )
    # The measured reason is kept verbatim: the exclusion is a rule of § D.3, not a re-measurement,
    # and rewriting the reason would hide what the data actually said.
    result.verdict = rc.VERDICT_DESCRIPTIF
    result.representative = None
    return result


# ---------------------------------------------------------------------------
# § G.4 — family verdict
# ---------------------------------------------------------------------------


def family_verdict(
    pairs: Sequence[PairVerdict], *, run_reason: str | None, coverage_measurable: bool
) -> tuple[str, str | None, str | None]:
    """§ G.4 — (verdict, reason, representative of the pair that carries the evidence)."""
    if run_reason is not None:
        return rc.VERDICT_INCONCLUSIF, run_reason, None
    if not coverage_measurable:
        # § D.3 — "Si data_coverage.json ne peut pas être produit, aucune paire n'est admissible".
        return rc.VERDICT_INCONCLUSIF, "D_UNMEASURABLE", None
    voting = [result for result in pairs if result.verdict != rc.VERDICT_DESCRIPTIF]
    if not voting:
        return rc.VERDICT_INCONCLUSIF, "D_NO_ADMISSIBLE_PAIR", None
    for result in voting:
        if result.verdict == rc.VERDICT_CANDIDAT:
            return rc.VERDICT_CANDIDAT, None, result.representative
    if all(result.verdict == rc.VERDICT_DEPRIORISATION for result in voting):
        return rc.VERDICT_DEPRIORISATION, REASON_POINT_NEGATIVE, None
    reason = worst_reason(
        *[result.reason for result in voting if result.verdict == rc.VERDICT_INCONCLUSIF]
    )
    return rc.VERDICT_INCONCLUSIF, reason, None


# ---------------------------------------------------------------------------
# The verdict line and the artifact
# ---------------------------------------------------------------------------


def build_verdict_string(
    *,
    family: str,
    reason: str | None,
    pairs: Mapping[str, Mapping[str, Any]],
    representative: str | None,
    prespec_sha: str,
    campaign_sha: str | None,
) -> str:
    """The single canonical line of § L. It carries no timestamp: two people, same string."""
    parts = [VERDICT_LINE_TAG, f"famille={family}", f"raison={reason or '-'}"]
    for pair in rc.PAIRS:
        parts.append(f"{pair}={(pairs.get(pair) or {}).get('verdict', '-')}")
    parts.append(f"representant={representative or '-'}")
    parts.append(f"prespec={(prespec_sha or '-')[:16]}")
    parts.append(f"campagne={(campaign_sha or '-')[:16]}")
    return " | ".join(parts)


@dataclass(frozen=True)
class Decision:
    """The whole decision: the per-pair objects, the family verdict and its carrier."""

    results: list[PairVerdict]
    family: str
    reason: str | None
    representative: str | None
    run_reason: str | None
    run_detail: str
    analysis_detail: str
    coverage_measurable: bool


def decide(artifacts: Mapping[str, Artifact], *, violations: list[str]) -> Decision:
    """§ G.1 -> § G.3 -> § G.4, from the frozen artifacts alone. No free parameter anywhere."""
    coverage = artifacts["data_coverage"]
    benchmark = artifacts["benchmark"]
    effect = artifacts["effect"]

    run_reason, run_detail = run_gate(artifacts["validation_campaign"])
    ok_analysis, analysis_detail = analysis_gate(artifacts["validation_analysis"])
    coverage_measurable = isinstance(coverage.mapping.get("pairs"), Mapping)

    effect_pairs = effect.mapping.get("pairs")
    effect_pairs = effect_pairs if isinstance(effect_pairs, Mapping) else {}
    lambda_mode = str(effect.mapping.get("lambda_mode") or LAMBDA_MODE_FROZEN)

    results: list[PairVerdict] = []
    for pair in rc.PAIRS:
        coverage_block = (coverage.mapping.get("pairs") or {}).get(pair)
        admissible = bool(
            coverage_measurable
            and isinstance(coverage_block, Mapping)
            and coverage_block.get("admissible") is True
        )
        benchmark_block = (benchmark.mapping.get("pairs") or {}).get(pair)
        comparable = bool(
            isinstance(benchmark_block, Mapping)
            and benchmark_block.get("buildable") is True
            and isinstance(benchmark_block.get("comparability"), Mapping)
            and benchmark_block["comparability"].get("comparable") is True
            and benchmark_block.get("nav")
        )
        block = effect_pairs.get(pair)
        result = pair_verdict(
            pair,
            effect_pair=block if isinstance(block, Mapping) else None,
            admissible=admissible,
            benchmark_comparable=comparable,
            analysis_ok=ok_analysis,
            lambda_mode=lambda_mode,
            violations=violations,
        )
        results.append(apply_non_voting(result))

    # § G.2 — the run-level gate short-circuits EVERYTHING, however perfect the other artifacts.
    family, reason, representative = family_verdict(
        results, run_reason=run_reason, coverage_measurable=coverage_measurable
    )
    if run_reason is not None:
        # "Pas de sauvetage partiel": the run does not exist, so no pair may keep an economic
        # verdict either. The counts stay visible — they are facts about effect.json, not votes.
        for result in results:
            result.notes.append(
                f"{result.verdict} measured, voided by the run-level gate ({run_reason})"
            )
            result.verdict = rc.VERDICT_INCONCLUSIF
            result.reason = run_reason
            result.representative = None
    if run_reason is not None or not coverage_measurable:
        representative = None
    return Decision(
        results=results,
        family=family,
        reason=reason,
        representative=representative,
        run_reason=run_reason,
        run_detail=run_detail,
        analysis_detail=analysis_detail,
        coverage_measurable=coverage_measurable,
    )


def build_payload(
    artifacts: Mapping[str, Artifact], decision: Decision, *, now: datetime
) -> dict[str, Any]:
    """The frozen ``verdict.json`` object — a pure function of the artifacts and ``now``."""
    pairs_block = {result.pair: result.to_dict() for result in decision.results}
    prespec = prespec_descriptor()
    campaign_sha = artifacts["validation_campaign"].mapping.get("artifact_sha256")
    line = build_verdict_string(
        family=decision.family,
        reason=decision.reason,
        pairs=pairs_block,
        representative=decision.representative,
        prespec_sha=prespec["sha256"],
        campaign_sha=str(campaign_sha) if isinstance(campaign_sha, str) else None,
    )
    return {
        "generated_at": now.isoformat(),
        "base_sha": rc.BASE_SHA,
        "prespec": prespec,
        "family_verdict": decision.family,
        "reason": decision.reason,
        "verdict_string": line,
        "pairs": pairs_block,
        "inputs_sha256": {name: artifacts[name].sha256 for name in sorted(artifacts)},
    }


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------


#: § H — the epistemic scope each verdict carries, so the line is never quoted without it.
SCOPE_STATEMENTS: dict[str, str] = {
    rc.VERDICT_CANDIDAT: (
        "La famille mérite davantage de travail, et rien d'autre : ni déploiement, ni sélection "
        "paper, ni sélection d'une configuration — C3 reste un prérequis (§ H)."
    ),
    rc.VERDICT_DEPRIORISATION: (
        "L'effet mesuré sur cette fenêtre est sous le minimum gelé ; ce n'est pas une affirmation "
        "que l'effet vrai est nul (§ H). La famille ne revient qu'avec un mécanisme nouveau."
    ),
    rc.VERDICT_INCONCLUSIF: (
        "Pas de déploiement et pas de tuning supplémentaire ; la raison est écrite, et le "
        "périmètre n'est pas élargi pour chercher une autre réponse (§ H)."
    ),
}


def render_lines(payload: Mapping[str, Any], decision: Decision) -> list[str]:
    results = decision.results
    lines = [
        "Rejeu diagnostic grid — verdict (§ G, § H)",
        "",
        payload["verdict_string"],
        "",
        f"  porte du run (§ G.2)     : {decision.run_detail}",
        f"  validité des analyses    : {decision.analysis_detail}",
        "",
    ]
    for result in results:
        lines.append(
            f"  {result.pair:<9} {result.verdict:<15} raison={result.reason or '-':<20} "
            f"éligibles={result.n_eligible} passent_les_gates={result.n_passing_gates} "
            f"six_bornes={result.n_candidat} représentant={result.representative or '-'}"
        )
        for note in result.notes:
            lines.append(f"      note: {note}")
    lines.append("")
    lines.append(SCOPE_STATEMENTS.get(str(payload["family_verdict"]), ""))
    lines.append(
        "Non-règles (§ G.5) : la dégénérescence, le clamp, train/test, le Sharpe et le multiple "
        "de frais G3 ne changent jamais un verdict."
    )
    return lines


def render_markdown(payload: Mapping[str, Any], results: Sequence[PairVerdict]) -> str:
    lines = [
        "# Rejeu diagnostic grid — verdict (§ G, § H)",
        "",
        "```",
        payload["verdict_string"],
        "```",
        "",
        "| Paire | Verdict | Raison | Éligibles | Passent G1∧G2∧G4 | Six bornes | Représentant |",
        "|---|---|---|---|---|---|---|",
    ]
    for result in results:
        lines.append(
            f"| {result.pair} | {result.verdict} | {result.reason or '-'} | "
            f"{result.n_eligible} | {result.n_passing_gates} | {result.n_candidat} | "
            f"{result.representative or '-'} |"
        )
    lines.append("")
    lines.append(
        "Le représentant est le **porteur de la preuve**, jamais une sélection (§ G.3, § G.5)."
    )
    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--validation-campaign", type=Path, default=DEFAULT_VALIDATION_CAMPAIGN)
    parser.add_argument("--validation-analysis", type=Path, default=DEFAULT_VALIDATION_ANALYSIS)
    parser.add_argument("--data-coverage", type=Path, default=DEFAULT_DATA_COVERAGE)
    parser.add_argument("--benchmark", type=Path, default=DEFAULT_BENCHMARK)
    parser.add_argument("--signatures", type=Path, default=DEFAULT_SIGNATURES)
    parser.add_argument("--clamp", type=Path, default=DEFAULT_CLAMP)
    parser.add_argument("--effect", type=Path, default=DEFAULT_EFFECT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--markdown", type=Path, default=None)
    parser.add_argument(
        "--now", default=None, help="ISO UTC stamp of generated_at (default: now), for determinism"
    )
    return parser


def collect_artifacts(args: argparse.Namespace) -> dict[str, Artifact]:
    """The seven frozen inputs. ``signatures`` and ``clamp`` are read for their sha256 only:
    § G.5 freezes that degeneracy and the clamp never change a verdict, in any direction.
    """
    return {
        "validation_campaign": load_artifact("validation_campaign", args.validation_campaign),
        "validation_analysis": load_artifact("validation_analysis", args.validation_analysis),
        "data_coverage": load_artifact("data_coverage", args.data_coverage),
        "benchmark": load_artifact("benchmark", args.benchmark),
        "signatures": load_artifact("signatures", args.signatures),
        "clamp": load_artifact("clamp", args.clamp),
        "effect": load_artifact("effect", args.effect),
    }


def compute(
    artifacts: Mapping[str, Artifact], *, now: datetime
) -> tuple[dict[str, Any], Decision, list[str]]:
    """Payload, per-pair detail and cross-check violations — the whole decision, in one call."""
    violations: list[str] = []
    decision = decide(artifacts, violations=violations)
    payload = build_payload(artifacts, decision, now=now)
    return payload, decision, violations


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.now is None:
        now = datetime.now(UTC)
    else:
        try:
            parsed = datetime.fromisoformat(args.now)
        except ValueError as exc:
            print(f"--now: {exc}", file=sys.stderr)
            return 2
        now = parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)

    artifacts = collect_artifacts(args)
    payload, decision, violations = compute(artifacts, now=now)
    digest = rc.write_json(args.output, payload)
    print("\n".join(render_lines(payload, decision)))
    print(f"written {args.output} sha256 {digest}")
    if args.markdown:
        Path(args.markdown).parent.mkdir(parents=True, exist_ok=True)
        Path(args.markdown).write_text(
            render_markdown(payload, decision.results), encoding="utf-8"
        )
        print(f"written {args.markdown}")
    for violation in violations:
        print(f"VIOLATION {violation}", file=sys.stderr)
    return 1 if violations else 0


if __name__ == "__main__":
    raise SystemExit(main())
