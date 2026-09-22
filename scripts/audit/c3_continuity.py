"""C3 — le contrat de continuité du portefeuille (§ B), cinq clauses avec l'état de leur vérifiabilité.

Étape 5 de la chaîne du § L.1, **sans entrée réelle en C3a** : l'exécution continue post-ancrage
relève de C3b, et cette étape ne s'exerce que sur des fixtures synthétiques. Elle lit le manifeste,
l'ancrage, un artefact d'évaluation et le bloc de comparabilité du comparateur d'évaluation, et
écrit ``continuity.json`` — l'état de chaque clause, **jamais une issue**.

**Ce que vaut chaque état** (plan § 6.4, validé) : ``VERIFIED`` ne naît que d'identités recalculées ;
**aucune déclaration ne produit ``VERIFIED``** — un bloc déclaratif cohérent avec le contrat vaut
``DECLARED`` ; ``NOT_VERIFIABLE`` est une réponse admissible du protocole (§ B l.723) ; ``FAILED`` est
une preuve fausse, qui n'est jamais admissible.

| Clause | Ce qui la décide |
|---|---|
| c1 — départ à plat à `T` (§ B.2) | ``flat_start_proof`` absent → ``NOT_VERIFIABLE`` ; présent et cohérent (cash = C, quantité 0, aucun ordre en attente) → ``DECLARED`` ; incohérent → ``FAILED`` |
| c2 — aucune réinitialisation interne (§ B.4) | ``invocation.single_call`` vrai **et** grille quotidienne continue de `[T, fin]` → ``DECLARED`` ; faux ou grille rompue → ``FAILED`` |
| c3 — liquidation terminale costée (§ B.3) | identités exactes **et preuve par lot** (``cc.liquidation_identities``, la même qu'en sélection) → ``VERIFIED`` ; identités exactes sans lots → ``NOT_VERIFIABLE`` ; bloc absent ou identité fausse → ``FAILED`` ; l'estampille de liquidation et la borne finale dans la même cellule quotidienne (§ B.4) sinon `E_STAMP_MISMATCH` |
| c4 — amorçage à `T` (§ B.5, W-ancrage) | ``sufficient`` recalculé sur chaque série de décision → ``VERIFIED`` / ``FAILED`` ; déclaré ≠ recalculé = violation |
| c5 — première exécution strictement après `T` (§ C.3) | ``first_fill_at`` absent → ``NOT_VERIFIABLE`` ; présent et `> T` → ``DECLARED`` ; `<= T` → ``FAILED`` |

Le comparateur d'évaluation : ``benchmark_comparable`` est la **conjonction recalculée** des tests
du § C.5, recoupée au ``comparable`` déclaré (désaccord = violation).

Ce que le verdict en fait est écrit là-bas, pas ici : une clause déclarative (c1, c2, c5) en échec
rend l'artefact non recevable ; une clause 3 en échec n'a **aucune issue définie par le texte gelé**
(``UndefinedIssueError``, convention datée du 21/09).

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
#: Ordre de sévérité de l'agrégat (plan § 3.14) : la pire clause donne l'état.
SEVERITY: tuple[str, ...] = ("FAILED", "NOT_VERIFIABLE", "DECLARED", "VERIFIED")


def aggregate_state(states: Mapping[str, str]) -> str:
    for candidate in SEVERITY:
        if candidate in states.values():
            return candidate
    return "VERIFIED"


def _clause(state: str, detail: str) -> dict[str, str]:
    assert state in cc.CONTINUITY_STATES
    return {"state": state, "detail": detail}


# ---------------------------------------------------------------------------
# Les cinq clauses
# ---------------------------------------------------------------------------


def clause_1_flat_start(evaluation: Mapping[str, Any], *, capital: Decimal) -> dict[str, str]:
    proof = cc.optional_mapping(evaluation, "flat_start_proof", where="evaluation")
    if proof is None:
        return _clause(
            "NOT_VERIFIABLE",
            "aucune preuve de départ à plat : les runners n'exportent ni cash, ni quantité, ni ordres "
            "en attente à T, et aucun point d'equity n'existe à T (§ B.2, § J.1) — C3b doit spécifier la preuve",
        )
    where = "evaluation.flat_start_proof"
    cash = cc.require_decimal(proof, "cash_at_T", where=where)
    qty = cc.require_decimal(proof, "inventory_qty_at_T", where=where)
    pending = cc.require_int(proof, "pending_orders_at_T", where=where, minimum=0)
    if cash == capital and qty == Decimal(0) and pending == 0:
        return _clause(
            "DECLARED",
            f"bloc déclaratif cohérent avec le contrat (cash {cash} = C, quantité 0, 0 ordre en attente) — "
            "une déclaration ne vaut jamais VERIFIED",
        )
    return _clause(
        "FAILED",
        f"le bloc déclare cash {cash} (C = {capital}), quantité {qty}, {pending} ordre(s) en attente : "
        "le portefeuille évalué ne démarre pas à plat",
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
) -> tuple[dict[str, str], dict[str, Any], bool | None, bool]:
    """(clause, rapport D6, liquidation_normalised, stamp_same_daily_cell)."""
    block = cc.optional_mapping(evaluation, "liquidation", where="evaluation")
    proof = cc.liquidation_identities(
        block,
        spread=spread,
        slippage=slippage,
        taker=taker,
        end=end,
        where="evaluation.liquidation",
    )
    same_cell = False
    if block is not None:
        stamp = cc.nullable_datetime(block, "timestamp", where="evaluation.liquidation")
        if stamp is not None:
            grid = cc.daily_grid(anchor, end)
            same_cell = grid[-2] < stamp <= end if len(grid) >= 2 else stamp == end
    if block is None:
        return (
            _clause("FAILED", proof["details"][0]),
            proof,
            False,
            same_cell,
        )
    exact_failed = [k for k, v in proof["checks"].items() if v is False and k != "lots_present"]
    if exact_failed:
        return _clause("FAILED", " ; ".join(proof["details"])), proof, False, same_cell
    if not proof["lots_present"]:
        return (
            _clause(
                "NOT_VERIFIABLE",
                "identités exactes satisfaites mais aucun lot exporté : la magnitude du taker est "
                "indécidable sur l'export agrégé (exigence C3b : export des lots)",
            ),
            proof,
            None,
            same_cell,
        )
    return (
        _clause("VERIFIED", "liquidation terminale costée, prouvée par lot"),
        proof,
        True,
        same_cell,
    )


def clause_4_warmup_at_anchor(
    evaluation: Mapping[str, Any], *, timeframes: Sequence[str], violations: list[str]
) -> dict[str, str]:
    warmup = cc.require_mapping(evaluation, "warmup", where="evaluation")
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


def benchmark_comparable(block: Mapping[str, Any], *, violations: list[str]) -> bool:
    tests = cc.require_mapping(block, "comparability", where="benchmark_eval")
    recomputed = all(
        cc.require_bool(tests, name, where="benchmark_eval.comparability")
        for name in (
            "entry_stamp_present",
            "exit_stamp_present",
            "ff_ok",
            "n_returns_ok",
            "all_finite",
        )
    )
    declared = cc.require_bool(block, "comparable", where="benchmark_eval")
    if declared != recomputed:
        violations.append(
            f"benchmark_eval.comparable déclaré {declared!r}, conjonction recalculée des tests § C.5 {recomputed!r}"
        )
    return recomputed


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
    anchor = manifest.anchor()
    declared_anchor = cc.require_datetime(anchor_raw, "anchor", where="anchor")
    if declared_anchor != anchor:
        violations.append(
            f"anchor.anchor déclaré {declared_anchor.isoformat()}, recalculé {anchor.isoformat()}"
        )
    end = manifest.window_end
    synthetic = cc.require_bool(evaluation, "synthetic", where="evaluation")
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
    c1 = clause_1_flat_start(evaluation, capital=manifest.capital)
    c2 = clause_2_no_reset(evaluation, anchor=anchor, end=end)
    c3, d6_report, normalised, same_cell = clause_3_costed_liquidation(
        evaluation, spread=spread, slippage=slippage, taker=manifest.taker, anchor=anchor, end=end
    )
    c4 = clause_4_warmup_at_anchor(
        evaluation, timeframes=candidate.decision_timeframes, violations=violations
    )
    c5 = clause_5_first_execution(evaluation, anchor=anchor)
    comparable = benchmark_comparable(benchmark_eval, violations=violations)
    clauses = {"c1": c1, "c2": c2, "c3": c3, "c4": c4, "c5": c5}
    states = {k: v["state"] for k, v in clauses.items()}
    return {
        "synthetic": synthetic,
        "strategy": strategy,
        "pair": pair,
        "identity": identity,
        "evaluation_window": {"start": anchor.isoformat(), "end": end.isoformat()},
        "clauses": {k: {"name": CLAUSE_NAMES[k], **v} for k, v in clauses.items()},
        "state": aggregate_state(states),
        "warmup_anchor_ok": states["c4"] == "VERIFIED",
        "benchmark_comparable": comparable,
        "stamp_same_daily_cell": same_cell,
        "liquidation_normalised": normalised,
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
