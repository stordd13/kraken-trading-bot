"""C3 — projection, admissibilité, scores, classement, choix ou abstention (§ A.7 à § A.11, § G.1).

Étape 4 de la chaîne du § L.1. Elle refuse de tourner tant que la validation d'entrée n'est pas
verte, ne lit les observations qu'à travers la **projection d'ancrage π_T** (§ A.7, liste blanche
exhaustive — un futur différent n'y change rien, c'est ce que `test_c3_chronology` prouve), et
applique **la séquence du § A.10, dans cet ordre et sans exception** :

```
1.  FILTRER   — D1 à D6 (§ A.8) sur chaque candidat.            -> ensemble ADMISSIBLE
2.  FILTRER   — P1 ∧ P2 ∧ P3 sur chaque candidat admissible.    -> ensemble SURVIVANT
3.  CLASSER   — l'ordre total du § A.9 sur le seul ensemble SURVIVANT ; le retenu est son PREMIER.
```

Ce qui est **recalculé, jamais recopié** : le CAGR § F.2 (c), le MDD quotidien et le σ depuis la
trajectoire projetée ; `sufficient` selon la règle C2 ; les cycles de D3 selon le moteur déclaré ;
les identités exactes de D6 sur le bloc `liquidation`, **preuve par lot comprise** (chaque `fee_i ==
gross_i × taker` dans le contexte Decimal du moteur, agrégats égaux aux sommes) — `lots` absent ⇒ la
magnitude du taker est indécidable ⇒ D6 n'est pas vérifié et le candidat n'est pas admissible ;
le **statut de sélection**, dérivé de la provenance et du résultat par une table explicite. Ce qui
est **rapporté sans être classé** : l'écart entre le MDD enregistré et le MDD recalculé (l'export
en `float` a perdu la précision Decimal du moteur — contre-exemple mesuré sur l'artefact réel),
la poussière et la divergence d'inventaire (24/96 préfixes réels contredisent leur égalité).

`NOT_ESTIMABLE` — par D3, D4, ou par un λ non calculable (§ C.6) — **n'est pas dans l'ensemble
admissible** ; si l'ensemble se vide, l'abstention est `A_NO_ADMISSIBLE_CANDIDATE` (§ A.11,
priorité § H). Une paire dont D1 échoue ou dont le comparateur n'est pas constructible est
`DESCRIPTIF` : ses chiffres sont imprimés, ils n'entrent dans aucun ordre (§ G.1).

Pure, lecture seule hors de sa sortie. Aucun accès base.

Usage::

    poetry run python scripts/audit/c3_select.py \\
        --manifest m.json --anchor anchor.json --entry entry.json --observations o.json \\
        --coverage coverage.json --benchmark benchmark.json \\
        --output selection.json --markdown selection.md --now 2026-09-22T00:00:00+00:00

Exit codes: 0 ok, 1 violation, 2 usage ou entrée invalide (§ I.1).
"""

from __future__ import annotations

import argparse
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
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

from krakenbot.backtest_metrics import METRICS_VERSION  # noqa: E402
from krakenbot.replay_contract import REPLAY_VERSION  # noqa: E402

STEP = "select"
ZERO = Decimal(0)
ONE = Decimal(1)

#: Un scoreur reçoit la projection, l'observation brute et le bloc de comparateur du candidat, et
#: rend `(Δ^dd, Δ^σ)`. Le scoreur par défaut **ne lit que le bloc de comparateur** ; l'observation
#: brute n'est passée que pour que le contrôle négatif du § A.12 puisse injecter un scoreur fuyant.
Scorer = Callable[[Mapping[str, Any], Mapping[str, Any], Mapping[str, Any]], tuple[float, float]]


def default_scorer(
    projection: Mapping[str, Any], raw: Mapping[str, Any], bench: Mapping[str, Any]
) -> tuple[float, float]:
    del projection, raw
    return (
        cc.require_float(bench, "delta_dd", where="benchmark.candidate"),
        cc.require_float(bench, "delta_sigma", where="benchmark.candidate"),
    )


# ---------------------------------------------------------------------------
# § A.8 D1 — couverture par paire ; comparateur par paire
# ---------------------------------------------------------------------------


def d1_for_pair(
    coverage_pair: Mapping[str, Any],
    *,
    start: datetime,
    end: datetime,
    prefix_days: float,
    where: str,
) -> dict[str, Any]:
    """D1 sur les **valeurs recoupées** (`cc.coverage_recompute`, revue R3 b) : `covered_units`
    est recalculé depuis `missing_stamps` et les bornes ; une contradiction est un refus, jamais
    un D1 vert par déclaration."""
    gap_max = cc.max_gap_days(prefix_days)
    per_interval: dict[str, Any] = {}
    ok_all = True
    for iv in cc.D1_INTERVALS:
        block = cc.require_mapping(coverage_pair, str(iv), where=where)
        bwhere = f"{where}.{iv}"
        recomputed = cc.coverage_recompute(block, start=start, end=end, interval=iv, where=bwhere)
        if recomputed["problems"]:
            raise cc.EntryRefusedError(
                "R0_INVALID_RUN", "couverture incohérente : " + " ; ".join(recomputed["problems"])
            )
        covered = recomputed["covered_recomputed"]
        expected = recomputed["expected_units_recomputed"]
        gap = cc.require_float(block, "longest_gap_days", where=bwhere)
        ratio = covered / expected
        ok = ratio >= cc.COVERAGE_MIN_RATIO and gap <= gap_max
        ok_all = ok_all and ok
        per_interval[str(iv)] = {
            "unit": cc.coverage_unit(iv),
            "covered_units": covered,
            "expected_units": expected,
            "ratio": ratio,
            "longest_gap_days": gap,
            "ok": ok,
        }
    return {"ok": ok_all, "gap_max_days": gap_max, "per_interval": per_interval}


# ---------------------------------------------------------------------------
# § A.8 D6 — la preuve est partagée (`cc.liquidation_identities`) avec la clause 3 de continuité
# ---------------------------------------------------------------------------


def liquidation_proof(
    block: Mapping[str, Any] | None,
    *,
    spread: Decimal,
    slippage: Decimal,
    taker: Decimal,
    anchor: datetime,
    where: str,
) -> dict[str, Any]:
    """D6 au préfixe : la borne est l'ancrage `T`."""
    return cc.liquidation_identities(
        block, spread=spread, slippage=slippage, taker=taker, end=anchor, where=where
    )


# ---------------------------------------------------------------------------
# Par candidat
# ---------------------------------------------------------------------------


@dataclass
class CandidateRecord:
    identity: str
    key: str
    strategy: str
    pair: str
    params: Mapping[str, Any]
    projection_sha256: str
    clauses: dict[str, bool] = field(default_factory=dict)
    clause_details: dict[str, str] = field(default_factory=dict)
    status: str = ""
    first_failed_gate: str | None = None
    candidate_reason: str | None = None
    metrics_prefix: dict[str, Any] = field(default_factory=dict)
    recomputed: dict[str, Any] = field(default_factory=dict)
    mdd_report: dict[str, Any] = field(default_factory=dict)
    d6_report: dict[str, Any] = field(default_factory=dict)
    alerts: list[str] = field(default_factory=list)
    floor: dict[str, bool] | None = None
    scores: dict[str, float] | None = None
    rank: int | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "identity": self.identity,
            "key": self.key,
            "strategy": self.strategy,
            "pair": self.pair,
            "params": dict(self.params),
            "projection_sha256": self.projection_sha256,
            "status": self.status,
            "clauses": dict(self.clauses),
            "clause_details": dict(self.clause_details),
            "first_failed_gate": self.first_failed_gate,
            "candidate_reason": self.candidate_reason,
            "metrics_prefix": self.metrics_prefix,
            "recomputed": self.recomputed,
            "mdd_report": self.mdd_report,
            "d6_report": self.d6_report,
            "alerts": list(self.alerts),
            "floor": self.floor,
            "scores": self.scores,
            "rank": self.rank,
        }


def _status_after_clauses(first_failed: str) -> str:
    if first_failed in ("D1", "D2"):
        return "NON_ADMISSIBLE"
    if first_failed in ("D3", "D4"):
        return "NOT_ESTIMABLE"
    return "HORS_USAGE_DÉCISIONNEL"


def _assert_d5(
    projection: Mapping[str, Any], manifest: cc.Manifest, pair: str, *, where: str
) -> None:
    contracts = cc.require_mapping(projection, "contracts", where=where)
    metrics = cc.require_mapping(projection, "metrics", where=where)
    costs = cc.require_mapping(contracts, "pair_costs", where=f"{where}.contracts")
    spread, slippage = manifest.pair_costs[pair]
    checks = (
        (
            "metrics_version",
            cc.require_int(contracts, "metrics_version", where=where),
            METRICS_VERSION,
        ),
        (
            "replay_version",
            cc.require_int(contracts, "replay_version", where=where),
            REPLAY_VERSION,
        ),
        ("exchange", cc.require_str(contracts, "exchange", where=where), manifest.exchange),
        ("fees", cc.require_str(contracts, "fees", where=where), manifest.fee_model),
        (
            "pair_costs_file",
            cc.require_str(contracts, "pair_costs_file", where=where),
            manifest.pair_costs_file,
        ),
        (
            "min_order_usdc",
            cc.require_float(contracts, "min_order_usdc", where=where),
            manifest.min_order_usdc,
        ),
        ("pair_costs.spread", cc.require_decimal(costs, "spread", where=where), spread),
        ("pair_costs.slippage", cc.require_decimal(costs, "slippage", where=where), slippage),
        (
            "starting_balance",
            Decimal(str(cc.require_float(metrics, "starting_balance", where=where))),
            manifest.capital,
        ),
    )
    for name, observed, expected in checks:
        if observed != expected:
            raise cc.EntryRefusedError(
                "R0_INVALID_RUN", f"{where}.{name}: {observed!r} != manifeste {expected!r} (D5)"
            )


def evaluate_candidate(
    candidate: cc.Candidate,
    key: str,
    raw: Mapping[str, Any],
    *,
    manifest: cc.Manifest,
    anchor: datetime,
    prefix_days: float,
    pair_d1_ok: bool,
    bench_candidate: Mapping[str, Any],
    scorer: Scorer,
    violations: list[str],
) -> CandidateRecord:
    where = f"observations[{key}]"
    projection = cc.project_prefix(raw, manifest.prefix_segment, where=where)
    # La finitude est validée **avant** toute empreinte : un NaN fourni est une violation (§ F.7),
    # pas une exception de canonicalisation.
    equity = cc.require_mapping(projection, "equity_daily", where=where)
    values = cc.require_finite_series(equity, "values", where=f"{where}.equity_daily", min_len=2)
    record = CandidateRecord(
        identity=candidate.identity,
        key=key,
        strategy=candidate.strategy,
        pair=candidate.pair,
        params=candidate.params,
        projection_sha256=cc.sig(projection),
    )
    _assert_d5(projection, manifest, candidate.pair, where=where)
    metrics = cc.require_mapping(projection, "metrics", where=where)
    mwhere = f"{where}.metrics"
    rec = cc.recompute_daily(values, days=prefix_days)
    net_pnl = cc.require_float(metrics, "net_pnl", where=mwhere)
    total_trades = cc.require_int(metrics, "total_trades", where=mwhere, minimum=0)
    winning = cc.require_int(metrics, "winning_trades", where=mwhere, minimum=0)
    losing = cc.require_int(metrics, "losing_trades", where=mwhere, minimum=0)
    mdd_recorded = cc.require_float(metrics, "max_drawdown_pct_daily", where=mwhere)
    record.metrics_prefix = {
        "net_pnl": net_pnl,
        "total_trades": total_trades,
        "winning_trades": winning,
        "losing_trades": losing,
        "max_drawdown_pct_daily": mdd_recorded,
        "n_daily_returns": cc.require_int(metrics, "n_daily_returns", where=mwhere, minimum=0),
    }
    record.mdd_report = {
        "recorded": mdd_recorded,
        "recomputed": rec.mdd_daily,
        "abs_diff": abs(mdd_recorded - rec.mdd_daily),
        "note": "écart rapporté, non classé (export float, § 6.3) ; les décisions lisent le recalculé",
    }
    if rec.alert_days:
        record.alerts.append(
            f"{len(rec.alert_days)} jour(s) à rendement <= -0,5 : alerte de qualité des données, aucun retrait (§ A.8 D4)"
        )

    # D1 — portée paire.
    record.clauses["D1"] = pair_d1_ok
    record.clause_details["D1"] = "couverture de la paire" + (
        " ok" if pair_d1_ok else " insuffisante (§ A.8 D1)"
    )
    # D2 — recalculé sur les séries de décision du candidat.
    warmup = cc.require_mapping(projection, "warmup", where=where)
    insufficient: list[str] = []
    for tf in candidate.decision_timeframes:
        block = cc.require_mapping(warmup, tf, where=f"{where}.warmup")
        recomputed, declared = cc.warmup_sufficient(block, where=f"{where}.warmup.{tf}")
        if recomputed != declared:
            violations.append(
                f"{where}.warmup.{tf}.sufficient déclaré {declared!r}, recalculé {recomputed!r}"
            )
        if not recomputed:
            insufficient.append(tf)
    record.clauses["D2"] = not insufficient
    record.clause_details["D2"] = (
        "amorçage suffisant"
        if not insufficient
        else f"séries insuffisantes au début du préfixe : {', '.join(insufficient)}"
    )
    # D3 — cycles selon le moteur déclaré (helper partagé avec c3_benchmark).
    engine = manifest.engines[candidate.strategy]
    liquidation = cc.optional_mapping(projection, "liquidation", where=where)
    cycles, d3_detail = cc.clause_d3(
        engine,
        total_trades=total_trades,
        winning=winning,
        losing=losing,
        liquidation=liquidation,
        where=f"{where}.liquidation",
    )
    record.clauses["D3"] = cc.d3_passes(cycles)
    record.clause_details["D3"] = d3_detail
    # D4 — rendements dérivés définis, dénominateurs non nuls.
    record.clauses["D4"] = rec.domain_ok
    record.clause_details["D4"] = (
        "rendements quotidiens définis"
        if rec.domain_ok
        else f"{rec.undefined_returns} rendement(s) indéfini(s) (NAV <= 0)"
    )
    # D5 — réasserté ci-dessus (un écart est un refus, jamais un candidat retiré).
    record.clauses["D5"] = True
    record.clause_details["D5"] = "contrats égaux au manifeste"
    # D6 — liquidation costée, identités exactes et preuve par lot.
    spread, slippage = manifest.pair_costs[candidate.pair]
    proof = liquidation_proof(
        liquidation,
        spread=spread,
        slippage=slippage,
        taker=manifest.taker,
        anchor=anchor,
        where=f"{where}.liquidation",
    )
    record.d6_report = proof
    record.clauses["D6"] = proof["passed"]
    record.clause_details["D6"] = (
        "liquidation terminale costée, prouvée par lot"
        if proof["passed"]
        else " ; ".join(proof["details"])
    )
    record.recomputed = {
        "cagr_pct": rec.cagr_pct,
        "mdd_daily": rec.mdd_daily,
        "sigma_daily": rec.sigma_daily,
        "cycles": cycles,
        "n_returns": len(rec.returns),
        "undefined_returns": rec.undefined_returns,
        "alert_days": len(rec.alert_days),
    }

    first_failed = next((c for c in cc.CLAUSE_ORDER if not record.clauses[c]), None)
    if first_failed is not None:
        record.status = _status_after_clauses(first_failed)
        record.first_failed_gate = first_failed
        record.candidate_reason = cc.CLAUSE_REASON[first_failed]
        return record

    # Recoupement des cibles calculées par c3_benchmark depuis les mêmes valeurs : exact.
    bwhere = f"benchmark.candidates[{candidate.identity[:16]}]"
    target_dd = cc.require_float(bench_candidate, "target_dd", where=bwhere)
    if target_dd != rec.mdd_daily:
        violations.append(f"{bwhere}.target_dd {target_dd!r} != MDD recalculé {rec.mdd_daily!r}")
    estimable = cc.require_bool(bench_candidate, "estimable", where=bwhere)
    if not estimable:
        record.status = "NOT_ESTIMABLE"
        record.first_failed_gate = cc.require_str(bench_candidate, "first_failed", where=bwhere)
        record.candidate_reason = cc.require_str(
            bench_candidate, "reason", where=bwhere, allowed=("F_NOT_ESTIMABLE", "E_NO_BENCHMARK")
        )
        return record
    delta_dd, delta_sigma = scorer(projection, raw, bench_candidate)
    assert rec.cagr_pct is not None and rec.sigma_daily is not None
    record.status = "ADMISSIBLE"
    record.scores = {
        "cagr_pct": rec.cagr_pct,
        "delta_dd": delta_dd,
        "delta_sigma": delta_sigma,
        "lambda_dd": cc.require_float(bench_candidate, "lambda_dd", where=bwhere),
        "lambda_sigma": cc.require_float(bench_candidate, "lambda_sigma", where=bwhere),
        "mdd_daily": rec.mdd_daily,
    }
    record.floor = {
        "P1": net_pnl > cc.FLOOR_NET_PNL,
        "P2": rec.cagr_pct >= cc.FLOOR_CAGR_PCT,
        "P3": delta_dd > cc.FLOOR_DELTA_DD,
    }
    return record


# ---------------------------------------------------------------------------
# § A.10 / § A.9 / § A.11 — la séquence, pure, sur des enregistrements
# ---------------------------------------------------------------------------


def selection_status(provenance: str, retained: bool) -> str:
    """La table provenance × résultat (plan § 4 l.7) — calculée, jamais recopiée."""
    if not retained:
        return "ABSTENTION"
    return (
        "SÉLECTION_VALIDE"
        if cc.PROVENANCE_CAN_SUPPORT_VALIDE[provenance]
        else "SÉLECTION_DESCRIPTIVE"
    )


def filter_and_rank(records: Sequence[CandidateRecord]) -> dict[str, Any]:
    """Filtrer (D1-D6), filtrer (P1∧P2∧P3), classer les survivants par l'ordre total du § A.9."""
    admissible = [r for r in records if r.status == "ADMISSIBLE"]
    survivors = [r for r in admissible if r.floor is not None and all(r.floor.values())]

    def order(r: CandidateRecord) -> tuple[float, float, float, str]:
        assert r.scores is not None
        return (
            -r.scores["delta_dd"],
            *cc.tie_break_key(r.scores["delta_sigma"], r.scores["mdd_daily"], r.identity),
        )

    ranking = sorted(survivors, key=order)
    for position, r in enumerate(ranking, start=1):
        r.rank = position
    if not admissible:
        reason: str | None = "A_NO_ADMISSIBLE_CANDIDATE"
    elif not survivors:
        reason = "A_BELOW_FLOOR"
    else:
        reason = None
    return {
        "admissible": [r.identity for r in admissible],
        "survivors": [r.identity for r in survivors],
        "ranking": [r.identity for r in ranking],
        "retained": ranking[0] if ranking else None,
        "reason": reason,
    }


# ---------------------------------------------------------------------------
# Le run complet — fonction pure des artefacts chargés
# ---------------------------------------------------------------------------


def run_selection(
    manifest: cc.Manifest,
    anchor_raw: Mapping[str, Any],
    entry_raw: Mapping[str, Any],
    observations: Mapping[str, Any],
    coverage_raw: Mapping[str, Any],
    benchmark_raw: Mapping[str, Any],
    *,
    violations: list[str],
    scorer: Scorer | None = None,
) -> dict[str, Any]:
    scorer = scorer or default_scorer
    anchor = manifest.anchor()
    prefix_days = (anchor - manifest.window_start).total_seconds() / 86400.0
    declared_anchor = cc.require_datetime(anchor_raw, "anchor", where="anchor")
    if declared_anchor != anchor:
        violations.append(
            f"anchor.anchor déclaré {declared_anchor.isoformat()}, recalculé {anchor.isoformat()}"
        )
    declared_provenance = cc.require_str(
        anchor_raw, "universe_provenance", where="anchor", allowed=cc.PROVENANCES
    )
    if declared_provenance != manifest.provenance:
        violations.append(
            f"anchor.universe_provenance {declared_provenance!r} != manifeste {manifest.provenance!r}"
        )
    variant_key = cc.require_str(anchor_raw, "variant_key", where="anchor")

    # Couverture et comparateur par paire.
    if not isinstance(coverage_raw, Mapping):
        raise cc.MissingEvidenceError("coverage: bloc attendu")
    coverage_pairs = cc.require_mapping(coverage_raw, "pairs", where="coverage")
    bench_pairs = cc.require_mapping(benchmark_raw, "pairs", where="benchmark")
    bench_candidates = cc.require_mapping(benchmark_raw, "candidates", where="benchmark")
    pairs: dict[str, Any] = {}
    for pair in manifest.pairs:
        d1 = d1_for_pair(
            cc.require_mapping(coverage_pairs, pair, where="coverage.pairs"),
            start=manifest.window_start,
            end=anchor,
            prefix_days=prefix_days,
            where=f"coverage.pairs.{pair}",
        )
        bench = cc.require_mapping(bench_pairs, pair, where="benchmark.pairs")
        comparable = cc.require_bool(bench, "comparable", where=f"benchmark.pairs.{pair}")
        pairs[pair] = {
            "status": "VOTANTE" if d1["ok"] and comparable else "DESCRIPTIF",
            "d1": d1,
            "benchmark_ok": comparable,
            "benchmark_reason": cc.nullable_str(bench, "reason", where=f"benchmark.pairs.{pair}"),
        }

    # Observations par identité (l'entrée a établi l'égalité avec l'univers).
    if not isinstance(observations, Mapping):
        raise cc.MissingEvidenceError("observations: bloc attendu")
    by_identity: dict[str, tuple[str, Mapping[str, Any]]] = {}
    for key in observations:
        raw = cc.require_mapping(observations, key, where="observations")
        identity = cc.candidate_identity(
            cc.require_str(raw, "strategy", where=f"observations.{key}"),
            cc.require_str(raw, "pair", where=f"observations.{key}"),
            cc.require_mapping(raw, "params", where=f"observations.{key}"),
        )
        by_identity[identity] = (key, raw)

    # D2 selon l'entrée, pour recoupement.
    entry_d2 = {
        cc.require_str(d, "identity", where="entry.candidate_diagnostics")
        for d in cc.require_sequence(entry_raw, "candidate_diagnostics", where="entry")
        if isinstance(d, Mapping)
        and cc.require_str(d, "clause", where="entry.candidate_diagnostics") == "D2"
    }

    records: list[CandidateRecord] = []
    for candidate in sorted(manifest.candidates, key=lambda c: c.identity):
        if candidate.identity not in by_identity:
            raise cc.EntryRefusedError(
                "R0_INVALID_RUN", f"candidat {candidate.identity[:16]} sans observation"
            )
        key, raw = by_identity[candidate.identity]
        if candidate.identity not in bench_candidates:
            raise cc.MissingEvidenceError(f"benchmark.candidates: {candidate.identity[:16]} absent")
        record = evaluate_candidate(
            candidate,
            key,
            raw,
            manifest=manifest,
            anchor=anchor,
            prefix_days=prefix_days,
            pair_d1_ok=pairs[candidate.pair]["d1"]["ok"],
            bench_candidate=cc.require_mapping(
                bench_candidates, candidate.identity, where="benchmark.candidates"
            ),
            scorer=scorer,
            violations=violations,
        )
        records.append(record)
    recomputed_d2 = {r.identity for r in records if not r.clauses["D2"]}
    if recomputed_d2 != entry_d2:
        violations.append(
            f"D2 : {len(recomputed_d2)} candidat(s) en échec au recalcul, {len(entry_d2)} selon entry.candidate_diagnostics — désaccord"
        )

    outcome = filter_and_rank(records)
    retained: CandidateRecord | None = outcome["retained"]
    status = selection_status(manifest.provenance, retained is not None)
    projections_all = [{"identity": r.identity, "sha256": r.projection_sha256} for r in records]
    core: dict[str, Any] = {
        "provenance": manifest.provenance,
        "prefix_segment": manifest.prefix_segment,
        "anchor": anchor.isoformat(),
        "prefix_days": prefix_days,
        "projection_sha256": {r.identity: r.projection_sha256 for r in records},
        "projection_sha256_all": cc.sig(projections_all),
        "candidates": [r.to_dict() for r in records],
        "pairs": pairs,
        "admissible": outcome["admissible"],
        "survivors": outcome["survivors"],
        "ranking": outcome["ranking"],
        "status": status,
        "reason": outcome["reason"],
        "retained": None
        if retained is None
        else {
            "identity": retained.identity,
            "key": retained.key,
            "strategy": retained.strategy,
            "pair": retained.pair,
            "params": dict(retained.params),
        },
        "abstention_clause": cc.ABSTENTION_CLAUSE if retained is None else None,
        "multiplicity": {
            "n_candidates": len(records),
            "n_admissible": len(outcome["admissible"]),
            "n_survivors": len(outcome["survivors"]),
            "variant_key": variant_key,
            "provenance": manifest.provenance,
            "window_already_swept": True,
            "note": "multiplicité déclarée et non quantifiée (§ F.3) : historique déjà exploré",
        },
        "lambda_mode": cc.LAMBDA_MODE_DECISIONAL,
        "lambda_label": cc.LAMBDA_LABEL,
    }
    return core


# ---------------------------------------------------------------------------
# Rendu et CLI
# ---------------------------------------------------------------------------


def render_lines(payload: Mapping[str, Any]) -> list[str]:
    if payload["invalide"]:
        return ["ARTEFACT INVALIDE — sélection non publiée"] + [
            f"  violation : {v}" for v in payload["violations"]
        ]
    out = [
        f"sélection sur le préfixe [{payload['anchor']} ← {payload['prefix_days']:.1f} j], provenance {payload['provenance']}"
    ]
    for pair, block in sorted(payload["pairs"].items()):
        out.append(
            f"  paire {pair}: {block['status']} (D1 {'ok' if block['d1']['ok'] else 'échec'}, comparateur {'ok' if block['benchmark_ok'] else 'absent'})"
        )
    for r in payload["candidates"]:
        gate = f" premier gate en échec {r['first_failed_gate']}" if r["first_failed_gate"] else ""
        score = (
            f" Δ^dd={r['scores']['delta_dd']:+.3f} rang={r['rank']}"
            if r["scores"] and r["rank"]
            else (
                f" Δ^dd={r['scores']['delta_dd']:+.3f} (plancher non franchi)"
                if r["scores"]
                else ""
            )
        )
        out.append(f"  {r['identity'][:16]} {r['pair']} {r['status']}{gate}{score}")
    if payload["retained"]:
        out.append(
            f"{payload['status']} — retenu {payload['retained']['identity'][:16]} ({payload['retained']['pair']}) ; {len(payload['admissible'])} admissibles, {len(payload['survivors'])} survivants"
        )
    else:
        out.append(f"{payload['status']} ({payload['reason']}) — {payload['abstention_clause']}")
    out.append(f"λ : mode {payload['lambda_mode']} — {payload['lambda_label']}")
    return out


def render_markdown(payload: Mapping[str, Any]) -> str:
    out = [
        "# C3 — sélection chronologique (§ A.7 à § A.11)",
        "",
        f"généré {payload['generated_at']} · protocole {payload['protocole']['sha256'][:16]} · ancrage `{payload['anchor']}` · "
        f"provenance `{payload['provenance']}` · π_T `{payload['projection_sha256_all'][:16]}`",
        "",
        "| candidat | paire | statut | premier gate | CAGR %/an | MDD % | Δ^dd | Δ^σ | rang |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for r in payload["candidates"]:
        s = r["scores"] or {}
        rec = r["recomputed"]
        cagr = "—" if rec["cagr_pct"] is None else f"{rec['cagr_pct']:.2f}"
        delta_dd = "—" if "delta_dd" not in s else f"{s['delta_dd']:+.2f}"
        delta_sigma = "—" if "delta_sigma" not in s else f"{s['delta_sigma']:+.2f}"
        out.append(
            f"| `{r['identity'][:12]}` | {r['pair']} | {r['status']} | {r['first_failed_gate'] or '—'} | "
            f"{cagr} | {rec['mdd_daily']:.2f} | {delta_dd} | {delta_sigma} | {r['rank'] or '—'} |"
        )
    out.append("")
    if payload["retained"]:
        out.append(
            f"**{payload['status']}** — configuration retenue `{payload['retained']['identity'][:16]}` ({payload['retained']['pair']}), porteuse du résultat, jamais « la meilleure » (§ G.1)."
        )
    else:
        out.append(f"**{payload['status']}** (`{payload['reason']}`)")
        out.append("")
        out.append(f"> {payload['abstention_clause']}")
    out.append("")
    out.append(f"λ : mode `{payload['lambda_mode']}` — {payload['lambda_label']}.")
    return "\n".join(out) + "\n"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    for name in ("manifest", "anchor", "entry", "observations", "coverage", "benchmark", "output"):
        parser.add_argument(f"--{name}", type=Path, required=True)
    parser.add_argument("--markdown", type=Path, default=None)
    parser.add_argument(
        "--now", default=None, help="Horodatage ISO UTC de generated_at, pour le déterminisme."
    )
    return parser


INPUT_NAMES: tuple[str, ...] = (
    "manifest",
    "anchor",
    "entry",
    "observations",
    "coverage",
    "benchmark",
)


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
            print(f"--{name}: {exc}", file=sys.stderr)
            return 2
    inputs = {name: getattr(args, name) for name in INPUT_NAMES}

    violations: list[str] = []
    core: dict[str, Any] | None = None
    try:
        manifest = cc.load_manifest(raws["manifest"])
        for name in ("anchor", "entry", "benchmark"):
            cc.require_upstream_ok(raws[name], where=name)
        violations += cc.check_inputs_match(
            raws["anchor"], {"manifest": args.manifest}, where="anchor"
        )
        violations += cc.check_inputs_match(
            raws["entry"],
            {"manifest": args.manifest, "anchor": args.anchor, "observations": args.observations},
            where="entry",
        )
        violations += cc.check_inputs_match(
            raws["benchmark"],
            {
                "manifest": args.manifest,
                "anchor": args.anchor,
                "entry": args.entry,
                "observations": args.observations,
            },
            where="benchmark",
        )
        entry_cov = cc.require_mapping(raws["entry"], "coverage", where="entry")
        if cc.require_str(entry_cov, "status", where="entry.coverage") != "evaluated":
            raise cc.EntryRefusedError(
                "R0_INVALID_RUN", "entrée validée sans artefact de couverture évalué"
            )
        if cc.require_str(entry_cov, "sha256", where="entry.coverage") != cc.file_sha256(
            args.coverage
        ):
            violations.append(
                "entry.coverage.sha256 ne correspond pas au fichier de couverture fourni"
            )
        core = run_selection(
            manifest,
            raws["anchor"],
            raws["entry"],
            raws["observations"],
            raws["coverage"],
            raws["benchmark"],
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
        violations.append(str(exc))

    if violations:
        payload = cc.envelope(STEP, now, inputs, exit_code=1, violations=violations)
        payload.update(
            {
                "status": None,
                "reason": None,
                "retained": None,
                "ranking": [],
                "candidates": [],
                "diagnostic": core,
            }
        )
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
    if args.markdown is not None:
        Path(args.markdown).parent.mkdir(parents=True, exist_ok=True)
        Path(args.markdown).write_text(render_markdown(payload), encoding="utf-8")
        print(f"written {args.markdown}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
