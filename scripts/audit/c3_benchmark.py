"""C3 — le comparateur du préfixe, `λ` et son mode (§ C.3, § C.4, § C.5, § C.6, § F.2 g).

Étape 3 de la chaîne du § L.1. Elle lit le manifeste, l'ancrage, la validation d'entrée (qui doit
être **verte** : sans quoi elle refuse de tourner), les observations et un fichier de **bougies**
— quatrième entrée hors chaîne, produite avant, jamais par l'outillage (§ A.7 interdit la base) —
et écrit ``benchmark.json``.

**Par paire, le B&H plein notionnel reconstruit sous la convention du § C.3** — décider à la
borne, exécuter à la bougie d'exécution suivante :

* entrée au **close de la première bougie d'exécution estampillée strictement après le début**,
  liquidation au **close de la dernière estampillée `<= T`** ; les deux estampilles sont
  **calculées** (`c3_common`), jamais « la première disponible » : absentes du fichier, le
  comparateur n'est **pas constructible** — aucune bougie de substitution (écart déclaré avec
  `rejeu_benchmark.select_entry_candle`) ;
* taker + spread + slippage sur les **deux** jambes ; marques `quantité × close 1 j` à chaque minuit
  intérieur ; le point à `T` est la valeur liquidée ;
* comparabilité § C.5 : jours forward-fillés sous la règle de D1, présence des deux estampilles,
  compte de rendements égal à `len(grille) − 1` (la ruine), finitude. Un échec rend la paire
  non comparable (`E_NO_BENCHMARK`) et **aucun repli sur `compute_benchmarks.py`** n'existe.

**Par candidat, l'appariement de budget de risque** (§ C.4, § F.2 g) : blend statique
`(1−λ)·C + λ·NAV_bh` sur la grille quotidienne, `λ_dd` apparié sur le `max_drawdown_pct_daily`
**recalculé** de la trajectoire projetée du candidat, `λ_σ` sur son écart-type quotidien, par
**recherche sur les NAV réellement construites** — grille grossière au pas 0,005 puis raffinement
±0,005 au pas 0,001, plus petit croisement retenu, croisements comptés, cible nulle → `λ = 0`
imprimé, aucun croisement dans `[0, 1]` (cible au-delà du B&H comprise) ou résidu > 10 % →
`NOT_ESTIMABLE` (écart déclaré avec `rejeu_effect.match_lambda`, qui retenait `λ = 1`).

**Tolérance bornée aux défauts d'admissibilité** (plan § 6.2) : ce script n'est pas une autorité
d'admissibilité. Un candidat correctement décrit mais dont la cible n'est pas calculable pour une
raison que `c3_select` tranchera (NAV atteignant 0 : D4) est consigné ``estimable: false`` avec son
premier gate, sans score, et les autres continuent. Une valeur **non finie fournie** reste une
violation (code 1) ; une rupture du contrat d'entrée reste un refus (code 2).

Pure, lecture seule hors de sa sortie. Aucun accès base.

Usage::

    poetry run python scripts/audit/c3_benchmark.py \\
        --manifest m.json --anchor anchor.json --entry entry.json \\
        --observations observations.json --candles candles.json \\
        --output benchmark.json --now 2026-09-22T00:00:00+00:00

Exit codes: 0 ok, 1 violation, 2 usage ou entrée invalide (§ I.1).
"""

from __future__ import annotations

import argparse
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
import math
from pathlib import Path
import statistics
import sys
from typing import Any

_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(_ROOT / "src"))
sys.path.insert(0, str(_ROOT / "scripts"))
sys.path.insert(0, str(_ROOT / "scripts" / "audit"))

import c3_common as cc  # noqa: E402

STEP = "benchmark"
ONE = Decimal(1)


# ---------------------------------------------------------------------------
# Bougies (entrée hors chaîne) — forme, bornes, jamais tronquées
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class PairCandles:
    exec_closes: Mapping[datetime, Decimal]
    daily_closes: Mapping[datetime, Decimal]


def _closes(rows: Sequence[Any], *, where: str, end: datetime) -> dict[datetime, Decimal]:
    out: dict[datetime, Decimal] = {}
    for i, row in enumerate(rows):
        rwhere = f"{where}[{i}]"
        if not isinstance(row, Mapping):
            raise cc.MissingEvidenceError(f"{rwhere}: bloc attendu, reçu {type(row).__name__}")
        stamp = cc.require_datetime(row, "t", where=rwhere)
        close = cc.require_decimal(row, "close", where=rwhere)
        if stamp > end:
            raise cc.EntryRefusedError(
                "R0_INVALID_RUN",
                f"{rwhere}.t: {stamp.isoformat()} postérieur à T {end.isoformat()} — une bougie "
                "postérieure à l'ancrage est une erreur d'entrée, jamais tronquée (§ A.7, § G.2)",
            )
        if close <= 0:
            raise cc.InvalidValueError(f"{rwhere}.close: {close} n'est pas strictement positif")
        if stamp in out:
            raise cc.EntryRefusedError(
                "R0_INVALID_RUN", f"{rwhere}.t: estampille {stamp.isoformat()} en double"
            )
        out[stamp] = close
    return out


def load_candles(raw: Any, manifest: cc.Manifest, *, end: datetime) -> dict[str, PairCandles]:
    where = "candles"
    if not isinstance(raw, Mapping):
        raise cc.MissingEvidenceError(f"{where}: bloc attendu, reçu {type(raw).__name__}")
    pairs = cc.require_mapping(raw, "pairs", where=where)
    out: dict[str, PairCandles] = {}
    for pair in manifest.pairs:
        if pair not in pairs:
            raise cc.MissingEvidenceError(f"{where}.pairs: paire {pair!r} de l'univers absente")
        block = cc.require_mapping(pairs, pair, where=f"{where}.pairs")
        pwhere = f"{where}.pairs.{pair}"
        interval = cc.require_int(block, "exec_interval", where=pwhere, minimum=1)
        if interval != manifest.exec_interval:
            raise cc.EntryRefusedError(
                "R0_INVALID_RUN",
                f"{pwhere}.exec_interval: {interval} != intervalle d'exécution déclaré {manifest.exec_interval} (§ C.3)",
            )
        out[pair] = PairCandles(
            exec_closes=_closes(
                cc.require_sequence(block, "exec", where=pwhere), where=f"{pwhere}.exec", end=end
            ),
            daily_closes=_closes(
                cc.require_sequence(block, "daily", where=pwhere), where=f"{pwhere}.daily", end=end
            ),
        )
    return out


# ---------------------------------------------------------------------------
# § C.3 — construction du B&H plein notionnel sur [début, T]
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class PairBenchmark:
    pair: str
    buildable: bool
    comparable: bool
    reason: str | None
    entry_stamp: str
    exit_stamp: str
    entry_price: Decimal | None
    exit_price: Decimal | None
    qty: Decimal | None
    nav: tuple[Decimal, ...]
    returns: tuple[float, ...]
    cagr_pct: float | None
    comparability: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "buildable": self.buildable,
            "comparable": self.comparable,
            "reason": self.reason,
            "entry_stamp": self.entry_stamp,
            "exit_stamp": self.exit_stamp,
            "entry_price": None if self.entry_price is None else str(self.entry_price),
            "exit_price": None if self.exit_price is None else str(self.exit_price),
            "qty": None if self.qty is None else str(self.qty),
            "nav": [float(v) for v in self.nav],
            "returns": list(self.returns),
            "cagr_pct": self.cagr_pct,
            "comparability": self.comparability,
        }


def build_pair(
    pair: str,
    candles: PairCandles,
    *,
    start: datetime,
    end: datetime,
    exec_interval: int,
    spread: Decimal,
    slippage: Decimal,
    taker: Decimal,
    capital: Decimal,
) -> PairBenchmark:
    entry_stamp = cc.first_stamp_strictly_after(start, exec_interval)
    exit_stamp = cc.last_stamp_at_or_before(end, exec_interval)
    grid = cc.daily_grid(start, end)
    days = (end - start).total_seconds() / 86400.0
    entry_present = entry_stamp in candles.exec_closes
    exit_present = exit_stamp in candles.exec_closes
    comparability: dict[str, Any] = {
        "entry_stamp_present": entry_present,
        "exit_stamp_present": exit_present,
        "ff_days": None,
        "longest_ff_run_days": None,
        "ff_ok": False,
        "n_returns_ok": False,
        "all_finite": False,
    }
    if not (entry_present and exit_present):
        missing = [
            s.isoformat()
            for s, ok in ((entry_stamp, entry_present), (exit_stamp, exit_present))
            if not ok
        ]
        return PairBenchmark(
            pair,
            False,
            False,
            f"non constructible : estampille(s) d'exécution requise(s) absente(s) {missing} — aucune bougie de substitution (§ C.3)",
            entry_stamp.isoformat(),
            exit_stamp.isoformat(),
            None,
            None,
            None,
            (),
            (),
            None,
            comparability,
        )
    close_in = candles.exec_closes[entry_stamp]
    close_out = candles.exec_closes[exit_stamp]
    exec_in = close_in * (ONE + spread + slippage)
    exec_out = close_out * (ONE - spread - slippage)
    qty = capital * (ONE - taker) / exec_in
    nav: list[Decimal] = [capital]
    last_close = close_in
    ff_days = 0
    run = 0
    longest_run = 0
    for stamp in grid[1:-1]:
        if stamp in candles.daily_closes:
            last_close = candles.daily_closes[stamp]
            run = 0
        else:
            ff_days += 1
            run += 1
            longest_run = max(longest_run, run)
        nav.append(qty * last_close)
    nav.append(qty * exec_out * (ONE - taker))
    n_midnights = len(grid) - 2
    covered_ratio = 1.0 if n_midnights == 0 else (n_midnights - ff_days) / n_midnights
    ff_ok = covered_ratio >= cc.COVERAGE_MIN_RATIO and float(longest_run) <= cc.max_gap_days(days)
    returns: list[float] = []
    for prev, cur in zip(nav, nav[1:], strict=False):
        if prev > 0:
            returns.append(float(cur / prev - ONE))
    n_ok = len(returns) == len(grid) - 1
    finite = all(math.isfinite(r) for r in returns)
    comparability.update(
        {
            "ff_days": ff_days,
            "longest_ff_run_days": longest_run,
            "ff_ok": ff_ok,
            "n_returns_ok": n_ok,
            "all_finite": finite,
        }
    )
    comparable = ff_ok and n_ok and finite
    failures = [
        name
        for name, ok in (("ff_ok", ff_ok), ("n_returns_ok", n_ok), ("all_finite", finite))
        if not ok
    ]
    reason = None if comparable else "non comparable : " + ", ".join(failures) + " (§ C.5)"
    cagr = cc.cagr_pct(returns, days) if comparable else None
    return PairBenchmark(
        pair,
        True,
        comparable,
        reason,
        entry_stamp.isoformat(),
        exit_stamp.isoformat(),
        exec_in,
        exec_out,
        qty,
        tuple(nav),
        tuple(returns),
        cagr,
        comparability,
    )


# ---------------------------------------------------------------------------
# § C.4 / § F.2 (g) — blends statiques et appariement de λ par recherche
# ---------------------------------------------------------------------------


def blend_nav(nav_bh: Sequence[Decimal], lam: Decimal, capital: Decimal) -> list[Decimal]:
    cash = (ONE - lam) * capital
    return [cash + lam * v for v in nav_bh]


def mdd_of(nav: Sequence[Decimal]) -> float:
    index: list[Decimal] = [ONE]
    for prev, cur in zip(nav, nav[1:], strict=False):
        index.append(index[-1] * (ONE + (cur - prev) / prev) if prev > 0 else index[-1])
    return cc.max_drawdown_pct(index)


def sigma_of(nav: Sequence[Decimal]) -> float | None:
    returns = [float(cur / prev - ONE) for prev, cur in zip(nav, nav[1:], strict=False) if prev > 0]
    return statistics.stdev(returns) if len(returns) > 1 else None


def cagr_of(nav: Sequence[Decimal], days: float) -> float | None:
    returns = [float(cur / prev - ONE) for prev, cur in zip(nav, nav[1:], strict=False) if prev > 0]
    if not returns or any(r <= cc.RETURN_DOMAIN_FLOOR for r in returns):
        return None
    return cc.cagr_pct(returns, days)


class LambdaCurve:
    """`λ -> cible(NAV_λ)` d'une paire, construite sur les NAV réellement construites, mémoïsée."""

    def __init__(self, nav_bh: Sequence[Decimal], capital: Decimal, matching: str) -> None:
        self.nav_bh = tuple(nav_bh)
        self.capital = capital
        self.matching = matching
        self._cache: dict[Decimal, float | None] = {}

    def value(self, lam: Decimal) -> float | None:
        if lam not in self._cache:
            blend = blend_nav(self.nav_bh, lam, self.capital)
            self._cache[lam] = mdd_of(blend) if self.matching == "dd" else sigma_of(blend)
        return self._cache[lam]


def _grid(start: Decimal, stop: Decimal, step: Decimal) -> list[Decimal]:
    out: list[Decimal] = []
    lam = start
    while lam <= stop:
        out.append(lam)
        lam += step
    return out


@dataclass(frozen=True)
class Match:
    lam: float | None
    residual: float | None
    crossings: int
    value: float | None
    note: str | None
    estimable: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "lambda": self.lam,
            "residual": self.residual,
            "crossings": self.crossings,
            "value_at_lambda": self.value,
            "note": self.note,
            "estimable": self.estimable,
        }


def match_lambda(curve: LambdaCurve, target: float) -> Match:
    """§ F.2 (g) : cible nulle → λ = 0 ; croisements comptés, plus petit retenu, raffiné ; aucun
    croisement dans [0, 1] ou résidu > 10 % → non estimable. Jamais λ = 1 par défaut."""
    if target <= 0.0:
        return Match(
            0.0,
            0.0,
            0,
            curve.value(Decimal(0)),
            "cible nulle : comparateur tout en cash (λ = 0)",
            True,
        )
    coarse = _grid(Decimal(0), ONE, cc.LAMBDA_COARSE_STEP)
    flags: list[bool] = []
    first: Decimal | None = None
    for lam in coarse:
        value = curve.value(lam)
        above = value is not None and value >= target
        flags.append(above)
        if above and first is None:
            first = lam
    crossings = sum(1 for a, b in zip(flags, flags[1:], strict=False) if a != b)
    if first is None:
        return Match(
            None,
            None,
            crossings,
            curve.value(ONE),
            "aucun croisement dans [0, 1] : cible au-delà du B&H plein notionnel",
            False,
        )
    low = max(Decimal(0), first - cc.LAMBDA_REFINE_HALFWIDTH)
    high = min(ONE, first + cc.LAMBDA_REFINE_HALFWIDTH)
    refined = first
    for lam in _grid(low, high, cc.LAMBDA_FINE_STEP):
        value = curve.value(lam)
        if value is not None and value >= target:
            refined = lam
            break
    value_at = curve.value(refined)
    assert value_at is not None
    residual = abs(value_at - target) / target
    if residual > cc.LAMBDA_RESIDUAL_MAX:
        return Match(
            float(refined),
            residual,
            crossings,
            value_at,
            f"résidu d'appariement {residual:.3f} > {cc.LAMBDA_RESIDUAL_MAX} (§ 0.5, § C.6)",
            False,
        )
    note = f"{crossings} croisement(s), plus petit λ retenu" if crossings > 1 else None
    return Match(float(refined), residual, crossings, value_at, note, True)


# ---------------------------------------------------------------------------
# Par candidat
# ---------------------------------------------------------------------------


def candidate_block(
    projection: Mapping[str, Any],
    *,
    candidate: cc.Candidate,
    manifest: cc.Manifest,
    anchor: datetime,
    pair_benchmark: PairBenchmark,
    curves: Mapping[str, LambdaCurve],
    days: float,
    capital: Decimal,
    where: str,
) -> tuple[dict[str, Any], float]:
    """Le bloc d'un candidat, et son MDD recalculé (pour que `c3_select` le recoupe exactement)."""
    equity = cc.require_mapping(projection, "equity_daily", where=where)
    values = cc.require_finite_series(equity, "values", where=f"{where}.equity_daily", min_len=2)
    rec = cc.recompute_daily(values, days=days)
    block: dict[str, Any] = {
        "pair": pair_benchmark.pair,
        "target_dd": rec.mdd_daily,
        "target_sigma": rec.sigma_daily,
        "cagr_pct": rec.cagr_pct,
        "estimable": False,
        "first_failed": None,
        "reason": None,
        "lambda_dd": None,
        "lambda_sigma": None,
        "cagr_blend_dd": None,
        "cagr_blend_sigma": None,
        "delta_dd": None,
        "delta_sigma": None,
        "match_dd": None,
        "match_sigma": None,
    }
    # Revue R3 (c) : aucun score décisionnel pour un candidat inadmissible — D3 et D6 sont
    # pré-contrôlés avec les **mêmes règles** que c3_select (helpers partagés de c3_common), à
    # côté de D4 ; le candidat est consigné avec son premier gate, les autres continuent.
    # Revue Fin (5) : **tout est lu et typé avant le premier pré-contrôle** — un retour anticipé
    # (« pas de comparateur », « D3 en échec ») ne laisse aucune clé obligatoire non lue.
    metrics = cc.require_mapping(projection, "metrics", where=where)
    liquidation = cc.optional_mapping(projection, "liquidation", where=where)
    cycles, _ = cc.clause_d3(
        manifest.engines[candidate.strategy],
        total_trades=cc.require_int(metrics, "total_trades", where=f"{where}.metrics", minimum=0),
        winning=cc.require_int(metrics, "winning_trades", where=f"{where}.metrics", minimum=0),
        losing=cc.require_int(metrics, "losing_trades", where=f"{where}.metrics", minimum=0),
        liquidation=liquidation,
        where=f"{where}.liquidation",
    )
    spread, slippage = manifest.pair_costs[candidate.pair]
    proof = cc.liquidation_identities(
        liquidation,
        spread=spread,
        slippage=slippage,
        taker=manifest.taker,
        end=anchor,
        where=f"{where}.liquidation",
    )
    if not pair_benchmark.comparable:
        block.update({"first_failed": "benchmark", "reason": "E_NO_BENCHMARK"})
        return block, rec.mdd_daily
    if not cc.d3_passes(cycles):
        block.update({"first_failed": "D3", "reason": "C_COVERAGE"})
        return block, rec.mdd_daily
    if not rec.domain_ok or rec.sigma_daily is None or rec.cagr_pct is None:
        block.update({"first_failed": "D4", "reason": "F_NOT_ESTIMABLE"})
        return block, rec.mdd_daily
    if not proof["passed"]:
        block.update({"first_failed": "D6", "reason": "R1_NOT_NORMALISED"})
        return block, rec.mdd_daily
    matches = {
        "dd": match_lambda(curves["dd"], rec.mdd_daily),
        "sigma": match_lambda(curves["sigma"], rec.sigma_daily),
    }
    block["match_dd"] = matches["dd"].to_dict()
    block["match_sigma"] = matches["sigma"].to_dict()
    for name in ("dd", "sigma"):
        if not matches[name].estimable:
            block.update({"first_failed": f"λ_{name}", "reason": "F_NOT_ESTIMABLE"})
            return block, rec.mdd_daily
    for name in ("dd", "sigma"):
        lam = matches[name].lam
        assert lam is not None
        cagr_blend = cagr_of(blend_nav(pair_benchmark.nav, Decimal(str(lam)), capital), days)
        if cagr_blend is None:
            block.update({"first_failed": f"blend_{name}", "reason": "F_NOT_ESTIMABLE"})
            return block, rec.mdd_daily
        block[f"lambda_{name}"] = lam
        block[f"cagr_blend_{name}"] = cagr_blend
        block[f"delta_{name}"] = rec.cagr_pct - cagr_blend
    block["estimable"] = True
    return block, rec.mdd_daily


# ---------------------------------------------------------------------------
# Artefact et CLI
# ---------------------------------------------------------------------------


def render_lines(payload: Mapping[str, Any]) -> list[str]:
    if payload["invalide"]:
        return ["ARTEFACT INVALIDE — comparateur non publié"] + [
            f"  violation : {v}" for v in payload["violations"]
        ]
    out = [
        f"comparateur du préfixe [{payload['window']['start']} -> {payload['window']['end']}], "
        f"mode λ = {payload['lambda_mode']} ({payload['lambda_label']})"
    ]
    for pair, block in sorted(payload["pairs"].items()):
        out.append(
            f"  {pair}: constructible={block['buildable']} comparable={block['comparable']} "
            f"entrée {block['entry_stamp']} sortie {block['exit_stamp']} "
            f"ff_days={block['comparability']['ff_days']} CAGR={block['cagr_pct']}"
            + (f" — {block['reason']}" if block["reason"] else "")
        )
    n = len(payload["candidates"])
    estimable = sum(1 for b in payload["candidates"].values() if b["estimable"])
    out.append(f"  candidats : {estimable}/{n} avec λ apparié et Δ publiés")
    return out


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    for name in ("manifest", "anchor", "entry", "observations", "candles", "output"):
        parser.add_argument(f"--{name}", type=Path, required=True)
    parser.add_argument(
        "--now", default=None, help="Horodatage ISO UTC de generated_at, pour le déterminisme."
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(list(argv) if argv is not None else None)
    try:
        now = cc.parse_now(args.now)
    except ValueError as exc:
        print(f"--now: {exc}", file=sys.stderr)
        return 2
    raws: dict[str, Any] = {}
    for name in ("manifest", "anchor", "entry", "observations", "candles"):
        try:
            raws[name] = cc.read_json(getattr(args, name))
        except (OSError, ValueError) as exc:
            print(f"--{name}: {exc}", file=sys.stderr)
            return 2
    inputs = {
        name: getattr(args, name)
        for name in ("manifest", "anchor", "entry", "observations", "candles")
    }

    violations: list[str] = []
    payload: dict[str, Any] | None = None
    try:
        manifest = cc.load_manifest(raws["manifest"])
        cc.require_upstream_ok(raws["anchor"], where="anchor")
        cc.require_upstream_ok(raws["entry"], where="entry")
        violations += cc.check_inputs_match(
            raws["anchor"], {"manifest": args.manifest}, where="anchor"
        )
        violations += cc.check_inputs_match(
            raws["entry"],
            {"manifest": args.manifest, "anchor": args.anchor, "observations": args.observations},
            where="entry",
        )
        anchor = manifest.anchor()
        declared = cc.require_datetime(raws["anchor"], "anchor", where="anchor")
        if declared != anchor:
            violations.append(
                f"anchor.anchor déclaré {declared.isoformat()}, recalculé {anchor.isoformat()}"
            )
        start = manifest.window_start
        days = (anchor - start).total_seconds() / 86400.0
        candles = load_candles(raws["candles"], manifest, end=anchor)
        pairs: dict[str, PairBenchmark] = {}
        curves: dict[str, dict[str, LambdaCurve]] = {}
        for pair in manifest.pairs:
            spread, slippage = manifest.pair_costs[pair]
            bench = build_pair(
                pair,
                candles[pair],
                start=start,
                end=anchor,
                exec_interval=manifest.exec_interval,
                spread=spread,
                slippage=slippage,
                taker=manifest.taker,
                capital=manifest.capital,
            )
            pairs[pair] = bench
            if bench.comparable:
                curves[pair] = {
                    "dd": LambdaCurve(bench.nav, manifest.capital, "dd"),
                    "sigma": LambdaCurve(bench.nav, manifest.capital, "sigma"),
                }
        observations = raws["observations"]
        if not isinstance(observations, Mapping):
            raise cc.MissingEvidenceError("observations: bloc attendu")
        by_identity: dict[str, Mapping[str, Any]] = {}
        for key in observations:
            entry = cc.require_mapping(observations, key, where="observations")
            identity = cc.candidate_identity(
                cc.require_str(entry, "strategy", where=f"observations.{key}"),
                cc.require_str(entry, "pair", where=f"observations.{key}"),
                cc.require_mapping(entry, "params", where=f"observations.{key}"),
            )
            by_identity[identity] = entry
        candidates: dict[str, Any] = {}
        for candidate in sorted(manifest.candidates, key=lambda c: c.identity):
            if candidate.identity not in by_identity:
                raise cc.EntryRefusedError(
                    "R0_INVALID_RUN", f"candidat {candidate.identity[:16]} sans observation"
                )
            projection = cc.project_prefix(
                by_identity[candidate.identity],
                manifest.prefix_segment,
                where=f"observations[{candidate.identity[:16]}]",
            )
            block, _ = candidate_block(
                projection,
                candidate=candidate,
                manifest=manifest,
                anchor=anchor,
                pair_benchmark=pairs[candidate.pair],
                curves=curves[candidate.pair] if candidate.pair in curves else {},
                days=days,
                capital=manifest.capital,
                where=f"observations[{candidate.identity[:16]}]",
            )
            candidates[candidate.identity] = block
        payload = cc.envelope(
            STEP, now, inputs, exit_code=1 if violations else 0, violations=violations
        )
        payload.update(
            {
                "window": {"start": start.isoformat(), "end": anchor.isoformat()},
                "prefix_days": days,
                "lambda_mode": cc.LAMBDA_MODE_DECISIONAL,
                "lambda_mode_declared": manifest.lambda_mode,
                "lambda_label": cc.LAMBDA_LABEL,
                "lambda_grid": {
                    "coarse_step": str(cc.LAMBDA_COARSE_STEP),
                    "fine_step": str(cc.LAMBDA_FINE_STEP),
                    "refine_halfwidth": str(cc.LAMBDA_REFINE_HALFWIDTH),
                    "residual_max": cc.LAMBDA_RESIDUAL_MAX,
                },
                "costs": {
                    "taker": str(manifest.taker),
                    "pair_costs": {
                        p: {"spread": str(s), "slippage": str(sl)}
                        for p, (s, sl) in manifest.pair_costs.items()
                    },
                },
                "capital": str(manifest.capital),
                "pairs": {pair: bench.to_dict() for pair, bench in pairs.items()},
                "candidates": candidates,
            }
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
        payload["pairs"] = {}
        payload["candidates"] = {}
        digest = cc.write_json(args.output, payload)
        print("\n".join(render_lines(payload)))
        print(f"written {args.output} sha256 {digest}")
        for violation in violations:
            print(f"VIOLATION {violation}", file=sys.stderr)
        return 1
    assert payload is not None
    digest = cc.write_json(args.output, payload)
    print("\n".join(render_lines(payload)))
    print(f"written {args.output} sha256 {digest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
