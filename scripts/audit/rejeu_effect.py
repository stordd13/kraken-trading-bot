"""Rejeu diagnostic grid — effet, gates ponctuels, bootstrap par blocs (prespec § C, § E.3, § F).

Ce script porte le coeur de la campagne : la couverture en cycles achevés (§ C), les deux
appariements de budget de risque **par recherche** sur les blends statiques construits en forme
fermée (§ E.3), l'effet Δ et les gates ponctuels (§ F.3), la règle d'éligibilité « échantillon trop
petit » (§ F.6), et la borne simultanée mono-étape par bootstrap de blocs circulaires (§ F.4).

Deux modes :

* ``--calibrate`` écrit ``calibration.json`` (§ F.5) depuis la seule courbe d'equity grid post-C2
  existante et le benchmark reconstruit : SE mono-config **pré-enregistré** de Δ par longueur de
  bloc, plus la vérification d'équivalence du MDD vectorisé contre la routine Decimal de
  ``krakenbot.backtest_metrics`` avec son temps mesuré et son résidu. Aucune extrapolation au
  quantile FWE n'y est écrite, ni ici ni dans ce qu'il imprime.
* le mode par défaut écrit ``effect.json`` depuis l'artefact de campagne, ``benchmark.json``,
  ``data_coverage.json`` et ``validation_campaign.json`` (qui doit porter ``ok: true`` — § I-A est
  bloquant et le § G.2 arrête tout avant le reste).

Points d'implémentation qui méritent d'être lus avant de relire un chiffre :

* le blend est **statique** : ``NAV_λ(t) = (1-λ)*1000 + λ*NAV_bh(t)`` sur les 1097 instants de la
  grille, jamais une série rééquilibrée ``λ*r_bh`` (qui serait biaisée en faveur de la stratégie) ;
* ``λ_dd`` est cherché sur la grille gelée {0.000 … 1.000 pas 0.001}, la monotonie étant prouvée
  au § E.3 ; ``λ_σ`` est cherché de la même façon mais la monotonie n'est **pas** prouvée : le
  nombre de croisements est compté et rapporté, et le plus petit λ est retenu ;
* le MDD du chemin de référence passe par ``backtest_metrics.max_drawdown_pct`` (routine
  **Decimal**), des deux côtés de la comparaison et sur l'indice (``index[0] = 1``), exactement
  comme la sonde de ``rejeu_validate_campaign`` ; l'implémentation numpy n'est utilisée **que**
  dans le bootstrap, et seulement après la vérification d'équivalence ;
* la famille de correction est l'ensemble des courbes **calculables** de la paire (``J_calc``) :
  aucun remplissage ``-inf``, et l'admissibilité / la couverture / les gates ne filtrent qu'au
  stade du verdict. Un Δ décisionnel n'est **publié** que pour une config éligible — une config
  sous 25 cycles reste donc dans ``J_calc`` et dans le maximum de la correction, sans que son Δ
  n'apparaisse dans l'artefact ;
* dans le bootstrap, la courbe ``λ -> cible(NAV_λ)`` est calculée **une fois par réplication** sur
  la grille gelée au pas 0.001 puis inversée pour les configs par première traversée. Le raffinage
  à deux étages de § F.4 (grossier 0.005 puis ±0.005) est une optimisation qui ne vaut plus une
  fois les réplications batchées — l'union des fenêtres de raffinage d'un chunk couvre la grille —
  et la grille pleine rend le **même** λ sur une courbe monotone tout en restant la définition
  littérale de § E.3 sur une courbe qui ne l'est pas. :func:`invert_curve_two_stage` garde la
  version écrite de la pré-spec et le test prouve l'égalité ;
* G3 (``net_pnl >= 10 × total_fees``) est calculé et exporté sous ``fee_multiple`` : il est
  **descriptif**, n'est jamais un gate, et n'entre jamais dans ``passes_gates`` ;
* ``se`` par config est celui de Δ^dd (le schéma gelé n'en porte qu'un par longueur de bloc, et
  § G.3 choisit son représentant sur ``Δ̂^dd``) ; ``calibration.json`` porte les deux
  appariements. ``LB_all_six_positive`` porte sur les six combinaisons gelées (3 longueurs × 2
  appariements) ou, si ``--block-lengths`` / ``--bootstrap-b`` sont surchargés pour un test, sur
  ce qui a réellement été publié — la surcharge est écrite dans l'artefact.

Pure, read-only.

Usage::

    poetry run python scripts/audit/rejeu_effect.py --calibrate \\
        --source results/c2_replay/P6_grid_rerun.json \\
        --benchmark results/rejeu_grid_20260919/benchmark.json \\
        --output results/rejeu_grid_20260919/calibration.json

    poetry run python scripts/audit/rejeu_effect.py \\
        --campaign results/rejeu_grid_20260919/P7_phase1_grid.json \\
        --benchmark results/rejeu_grid_20260919/benchmark.json \\
        --coverage results/rejeu_grid_20260919/data_coverage.json \\
        --validation results/rejeu_grid_20260919/validation_campaign.json \\
        --output results/rejeu_grid_20260919/effect.json \\
        --markdown results/rejeu_grid_20260919/effect.md

Exit codes: 0 ok, 1 violation, 2 usage or input error.
"""

from __future__ import annotations

import argparse
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal
import hashlib
import math
from pathlib import Path
import sys
from time import perf_counter
from typing import Any

import numpy as np

_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(_ROOT / "src"))
sys.path.insert(0, str(_ROOT / "scripts"))
sys.path.insert(0, str(_ROOT / "scripts" / "audit"))

from p7_grids import GRID_ATR_GRID  # noqa: E402
import rejeu_common as rc  # noqa: E402

from krakenbot.backtest_metrics import max_drawdown_pct  # noqa: E402

PRESPEC_RELPATH = "docs/rejeu_grid_prespec.md"
OUTPUT_DIR = rc.PROJECT_ROOT / "results" / "rejeu_grid_20260919"
DEFAULT_CAMPAIGN = OUTPUT_DIR / "P7_phase1_grid.json"
DEFAULT_BENCHMARK = OUTPUT_DIR / "benchmark.json"
DEFAULT_COVERAGE = OUTPUT_DIR / "data_coverage.json"
DEFAULT_VALIDATION = OUTPUT_DIR / "validation_campaign.json"
DEFAULT_CALIBRATION = OUTPUT_DIR / "calibration.json"
DEFAULT_EFFECT = OUTPUT_DIR / "effect.json"
DEFAULT_SOURCE = rc.PROJECT_ROOT / "results" / "c2_replay" / "P6_grid_rerun.json"

#: § F.4 — the replications are chunked, and the chunks apply to the ALREADY drawn ``starts``
#: matrix, so the chunk size cannot change a single draw.
DEFAULT_CHUNK = 2000
#: § F.4 — the numpy MDD is only used inside the bootstrap once this residual is met.
MDD_EQUIVALENCE_TOL = 1e-9
CAPITAL_FLOAT = float(rc.CAPITAL)
LAMBDA_COUNT = 1001  # {0.000, 0.001, ..., 1.000}
COARSE_EVERY = 5  # frozen two-stage grid: coarse step 0.005 = 5 x 0.001

LAMBDA_MODE_REESTIMATED = "reestimated"
LAMBDA_MODE_FROZEN = "frozen_sensitivity"
FROZEN_LABEL = "analyse de sensibilité, sans garantie de couverture 95 %"

#: Per-config / per-pair reason codes. ``D_NOT_ADMISSIBLE`` is the name § F.6 gives to clause 1
#: for a single pair; the closed list of § H carries the family-level ``D_NO_ADMISSIBLE_PAIR``.
REASON_NOT_ADMISSIBLE = "D_NOT_ADMISSIBLE"
REASON_WARMUP_W2 = "D_WARMUP_W2"
REASON_NO_BENCHMARK = "E_NO_BENCHMARK"
REASON_COVERAGE = "C_COVERAGE"
REASON_NOT_ESTIMABLE = "F_NOT_ESTIMABLE"

#: § E.3 — labels of the two frozen no-match cases.
MATCH_PURE_CASH = "pure_cash"
MATCH_ABOVE_BH = "above_bh"

#: § I-A.3 — an entry carrying an error should never reach this script.
ENTRY_ERROR_NOTE = "entry carries an error block"

#: § E.3 — the mandatory statement that goes with every matched comparison.
RETROSPECTIVE_STATEMENT = (
    "L'appariement sur le drawdown (ou la volatilité) observé est une comparaison "
    "rétrospective, jamais une allocation validée pour l'avenir."
)
#: § E.3 — below this λ the frozen paragraph below is printed verbatim next to the figures.
SMALL_LAMBDA = 0.02
SMALL_LAMBDA_STATEMENT = (
    "Le comparateur apparié détient moins de 2 % du capital dans l'actif ; la comparaison porte "
    "sur l'efficience à très petit budget de risque, pas sur une allocation alternative réaliste. "
    "Ce qui empêche un effet absolu trivialement petit de fonder un verdict est le plancher G2, "
    "pas cette comparaison."
)
#: § D.4 — the qualifier a W1 pair must carry next to EVERY figure of that pair.
W1_QUALIFIER = (
    "Le warmup 1d/1w de {pair} est `sufficient=False` par `largest_gap_candles` {gap_1d} / "
    "{gap_1w} : les EMA20/50 qui alimentent `get_regime` ont été amorcées à travers le trou "
    "pré-fenêtre. `bias_1d` faisant vivre `regime_1d` dans tous les modes, **tout** résultat de "
    "cette paire — quel que soit `bear_protection_mode` — repose sur une porte dont l'amorçage "
    "n'est pas propre ; le réexaminer est une entrée obligatoire de C3."
)

#: § F.5 — the reference curve is disclosed as a quasi-member of the swept family.
REFERENCE_DISCLOSURE = (
    "Référence divulguée comme quasi-membre de la famille balayée : min_spacing_pct 0.015 est le "
    "minimum balayé et bear_protection_mode nul laisse pause_1w_strong_bear = True, soit le bras "
    "comportemental 1w_only ; seul atr_multiplier 4.0 est hors balayage. Aucun seuil de la "
    "pré-spécification n'en est dérivé."
)


# ---------------------------------------------------------------------------
# λ grid, blends and the two targets (§ E.3)
# ---------------------------------------------------------------------------


def lambda_values() -> list[Decimal]:
    """The frozen λ grid ``{0.000, 0.001, ..., 1.000}`` as Decimals."""
    return [Decimal(k) * rc.LAMBDA_STEP for k in range(LAMBDA_COUNT)]


def lambda_array() -> np.ndarray:
    """The same grid as float64 — used by the bootstrap only."""
    return np.arange(LAMBDA_COUNT, dtype=np.float64) / (LAMBDA_COUNT - 1)


def decimal_index(values: Sequence[float]) -> list[Decimal] | None:
    """The C1 index of a NAV path (``index[0] = 1``), or None when the path is unusable.

    Mirrors the self-test probe of ``rejeu_validate_campaign`` exactly: the index compounds the
    Decimal daily returns, and ``max_drawdown_pct`` reads it. A non-finite value or a
    non-positive predecessor makes the path unusable — never a silently patched number.
    """
    navs = [rc.dec(v) for v in values]
    if len(navs) < 2 or any(v is None or not v.is_finite() for v in navs):
        return None
    index: list[Decimal] = [Decimal(1)]
    for prev, cur in zip(navs[:-1], navs[1:], strict=True):
        if prev is None or prev <= 0:
            return None
        index.append(index[-1] * (Decimal(1) + (cur - prev) / prev))
    return index


def mdd_of_values(values: Sequence[float]) -> float | None:
    """``max_drawdown_pct`` of the index of a NAV path — the Decimal routine, as § E.3 requires."""
    index = decimal_index(values)
    return None if index is None else max_drawdown_pct(index)


def sigma_of_returns(returns: Sequence[float]) -> float | None:
    """Sample standard deviation (ddof 1) of the daily returns; None when undefined."""
    if len(returns) < 2 or not all(math.isfinite(r) for r in returns):
        return None
    return float(np.std(np.asarray(returns, dtype=np.float64), ddof=1))


def blend_values(nav_bh: Sequence[Decimal], lam: Decimal) -> list[Decimal]:
    """``NAV_λ(t) = (1-λ)*1000 + λ*NAV_bh(t)`` — closed form, never a rebalanced λ*r series."""
    cash = (Decimal(1) - lam) * rc.CAPITAL
    return [cash + lam * v for v in nav_bh]


def dd_curve(nav_bh: Sequence[float]) -> list[float]:
    """``λ -> MDD_daily(index of NAV_λ)`` on the frozen grid, through the Decimal routine."""
    navs = [Decimal(str(v)) for v in nav_bh]
    return [
        max_drawdown_pct(_index_of_decimals(blend_values(navs, lam))) for lam in lambda_values()
    ]


def sigma_curve(nav_bh: Sequence[float]) -> list[float]:
    """``λ -> σ_daily(NAV_λ)`` on the frozen grid (float: no Decimal-only routine is involved).

    The blend NAV is built, then its simple daily returns exactly as ``rc.daily_returns`` does
    (``v_k / v_{k-1} - 1``), so both sides of the matching are measured by the same instrument.
    """
    nav = np.asarray(nav_bh, dtype=np.float64)
    out: list[float] = []
    for lam in lambda_array():
        blend = (1.0 - lam) * CAPITAL_FLOAT + lam * nav
        out.append(float(np.std(blend[1:] / blend[:-1] - 1.0, ddof=1)))
    return out


def _index_of_decimals(values: Sequence[Decimal]) -> list[Decimal]:
    index: list[Decimal] = [Decimal(1)]
    for prev, cur in zip(values[:-1], values[1:], strict=True):
        index.append(index[-1] * (Decimal(1) + (cur - prev) / prev))
    return index


@dataclass(frozen=True)
class Match:
    """One risk-budget matching: the λ retained, its relative residual, and what happened."""

    lam: float
    residual: float
    crossings: int
    label: str | None

    @property
    def approximate(self) -> bool:
        """§ E.3 — above 10 % the matching is labelled approximate (descriptive, non blocking)."""
        return self.residual > rc.MATCH_RESIDUAL_WARN


def count_crossings(curve: Sequence[float], target: float) -> int:
    """Transitions of ``[curve(λ) >= target]`` along the grid — monotonicity is not assumed."""
    flags = [value >= target for value in curve]
    return sum(1 for a, b in zip(flags[:-1], flags[1:], strict=True) if a != b)


def match_lambda(curve: Sequence[float], target: float) -> Match:
    """``min{λ : cible(NAV_λ) >= cible(config)}``, else 1 — with the two frozen no-match cases.

    (i) ``cible(config) > cible(NAV_1)`` -> λ = 1, labelled ``above_bh``: leverage is forbidden by
    § 7, so a config riskier than the full-notional B&H asks for no risk rebate.
    (ii) ``cible(config) == 0`` -> λ = 0, labelled ``pure_cash``: the 100 % cash comparator, which
    is the other benchmark § 8 names. The residual is 0 there by construction (NAV_0 is flat).
    """
    crossings = count_crossings(curve, target)
    if target <= 0.0:
        return Match(lam=0.0, residual=0.0, crossings=crossings, label=MATCH_PURE_CASH)
    grid = lambda_values()
    for position, value in enumerate(curve):
        if value >= target:
            lam = float(grid[position])
            return Match(lam, abs(value - target) / target, crossings, None)
    return Match(1.0, abs(curve[-1] - target) / target, crossings, MATCH_ABOVE_BH)


# ---------------------------------------------------------------------------
# Vectorised MDD — used inside the bootstrap ONLY after the equivalence check (§ F.4)
# ---------------------------------------------------------------------------


def mdd_numpy(paths: np.ndarray) -> np.ndarray:
    """Largest peak-to-trough decline in % along the last axis (cumulative running maximum)."""
    peak = np.maximum.accumulate(paths, axis=-1)
    return ((peak - paths) / peak).max(axis=-1) * 100.0


def relative_residual(reference: float, other: float) -> float:
    if reference == other:
        return 0.0
    if reference == 0.0:
        return abs(other)
    return abs(other - reference) / abs(reference)


def mdd_equivalence(series: Sequence[Sequence[float]]) -> dict[str, Any]:
    """Compare the numpy MDD to the Decimal routine on the observed curves (§ F.4)."""
    started = perf_counter()
    decimal_values = [mdd_of_values(values) for values in series]
    time_decimal = perf_counter() - started
    matrix = np.asarray(series, dtype=np.float64)
    started = perf_counter()
    numpy_values = mdd_numpy(matrix)
    time_numpy = perf_counter() - started
    worst = 0.0
    for reference, other in zip(decimal_values, numpy_values, strict=True):
        if reference is None or not math.isfinite(float(other)):
            worst = float("inf")
            break
        worst = max(worst, relative_residual(reference, float(other)))
    return {
        "verified": worst <= MDD_EQUIVALENCE_TOL,
        "max_relative_residual": worst,
        "n_series": len(series),
        "time_decimal_sec": time_decimal,
        "time_numpy_sec": time_numpy,
        "speedup": (time_decimal / time_numpy) if time_numpy > 0 else float("inf"),
    }


# ---------------------------------------------------------------------------
# Warmup classes (§ D.4) — exhaustive, the strictest class wins
# ---------------------------------------------------------------------------

WARMUP_TFS = ("4h", "1d", "1w")
WARMUP_ORDER = {"W0": 0, "W1": 1, "W2": 2}


def _tf_clean(block: Any) -> bool:
    """A timeframe whose prefix is loaded, not stale, and holed by at most one candle."""
    if not isinstance(block, Mapping):
        return False
    loaded, required = block.get("loaded"), block.get("required")
    stale, gap = block.get("stale_by_candles"), block.get("largest_gap_candles")
    if loaded is None or required is None or stale is None or gap is None:
        return False
    return bool(loaded >= required and stale == 0 and gap <= 1)


def _tf_only_internal_gap(block: Any) -> bool:
    """§ D.4 W1 — the only cause of insufficiency is an internal hole (``largest_gap > 1``)."""
    if not isinstance(block, Mapping):
        return False
    if block.get("sufficient") is True:
        return True
    loaded, required = block.get("loaded"), block.get("required")
    stale, gap = block.get("stale_by_candles"), block.get("largest_gap_candles")
    if loaded is None or required is None or stale is None or gap is None:
        return False
    return bool(loaded >= required and stale == 0 and gap > 1)


def warmup_class(block: Any) -> str:
    """W0 / W1 / W2 for one ``warmup[seg]`` block — anything that is not W0 or W1 is W2."""
    if not isinstance(block, Mapping) or any(tf not in block for tf in WARMUP_TFS):
        return "W2"
    if all(isinstance(block[tf], Mapping) and block[tf].get("sufficient") is True
           for tf in WARMUP_TFS):
        return "W0"
    four_hour = block["4h"]
    sufficient_4h = isinstance(four_hour, Mapping) and four_hour.get("sufficient") is True
    if sufficient_4h and _tf_clean(four_hour) and all(
        _tf_only_internal_gap(block[tf]) for tf in ("1d", "1w")
    ):
        return "W1"
    return "W2"


def pair_warmup_class(entries: Sequence[Mapping[str, Any]]) -> tuple[str, int]:
    """The strictest class over the configs of a pair, plus how many distinct classes were seen.

    § D.4 / § I-A.8: the block depends only on (pair, segment); a difference between two configs
    is reported and resolved by keeping the strictest class, never averaged away. An entry that
    carries **no** block at all (a failed job — § I-A.3 stops the run for it) is not a difference
    of warmup: it is skipped here, so a crashed job cannot silently downgrade its 47 neighbours.
    """
    blocks = [
        (entry.get("warmup") or {}).get("all")
        for entry in entries
        if isinstance((entry.get("warmup") or {}).get("all"), Mapping)
    ]
    classes = {warmup_class(block) for block in blocks}
    if not classes:
        return "W2", 0
    return max(classes, key=lambda name: WARMUP_ORDER[name]), len(classes)


# ---------------------------------------------------------------------------
# Per-config analysis (§ C, § E.3, § F.2, § F.3, § F.6, § G.1)
# ---------------------------------------------------------------------------


@dataclass
class PairContext:
    """Everything a config of one pair is read against. Built once per pair."""

    pair: str
    pair_index: int
    admissible: bool
    warmup: str
    benchmark_comparable: bool
    bench_nav: list[float] | None = None
    bench_returns: list[float] | None = None
    curves: dict[str, list[float]] = field(default_factory=dict)
    #: ``largest_gap_candles`` of 1d / 1w, for the mandatory W1 qualifier of § D.4.
    warmup_gaps: dict[str, Any] = field(default_factory=dict)

    def curve(self, matching: str) -> list[float]:
        """The λ -> target curve of the static blends, built once per (pair, matching)."""
        if matching not in self.curves:
            nav = self.bench_nav or []
            self.curves[matching] = dd_curve(nav) if matching == "dd" else sigma_curve(nav)
        return self.curves[matching]


@dataclass
class ConfigResult:
    """One config: its published payload plus what the bootstrap needs internally."""

    key: str
    pair: str
    params: dict[str, Any]
    payload: dict[str, Any]
    returns: list[float] | None
    cagr: float | None
    deltas: dict[str, float | None]
    lambdas: dict[str, float | None]
    computable: bool
    eligible: bool
    notes: list[str] = field(default_factory=list)


def _metric(metrics: Any, name: str) -> Any:
    return metrics.get(name) if isinstance(metrics, Mapping) else None


def _finite(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def returns_usable(returns: Sequence[float] | None) -> bool:
    """§ F.6 clause 5 on one side: 1096 defined finite returns, all above the ``log1p`` domain."""
    if returns is None or len(returns) != rc.SEGMENT_RETURNS["all"]:
        return False
    if not all(math.isfinite(r) for r in returns):
        return False
    return min(returns) > rc.MIN_RETURN_DOMAIN


def analyse_config(key: str, entry: Mapping[str, Any], ctx: PairContext) -> ConfigResult:
    """Point estimates, status ladder (§ G.1) and gates (§ F.3) for one config."""
    notes: list[str] = []
    broken = "error" in entry
    if broken:
        notes.append(ENTRY_ERROR_NOTE)
    metrics = entry.get("all")
    values = ((entry.get("equity_daily") or {}).get("all") or {}).get("values")
    if not isinstance(values, list) or not values:
        values = None
        notes.append("equity_daily.all.values missing")
    if not isinstance((entry.get("liquidation") or {}).get("all"), Mapping):
        notes.append("liquidation.all missing")
    cycles = rc.cycles_of(entry, "all")
    returns = rc.daily_returns(values) if values else None
    usable = returns_usable(returns)
    count_nnz = rc.nnz(returns) if returns is not None else None
    mdd_daily = mdd_of_values(values) if values else None
    sigma_daily = sigma_of_returns(returns) if returns is not None else None
    cagr = rc.cagr_from_returns(returns) if usable else None

    net_pnl = _finite(_metric(metrics, "net_pnl"))
    total_return = _finite(_metric(metrics, "total_return_pct"))
    total_fees = _finite(_metric(metrics, "total_fees"))
    sharpe = _finite(_metric(metrics, "sharpe_ratio"))  # descriptive, never a threshold
    fee_multiple = None
    if net_pnl is not None and total_fees is not None and total_fees > 0:
        fee_multiple = net_pnl / total_fees

    bench_returns = ctx.bench_returns if ctx.benchmark_comparable else None
    beta_hat = None
    if bench_returns is not None and usable and returns is not None:
        beta_hat = rc.ols_beta(returns, bench_returns)

    matches: dict[str, Match | None] = dict.fromkeys(rc.MATCHINGS)
    deltas: dict[str, float | None] = dict.fromkeys(rc.MATCHINGS)
    jackknife: float | None = None
    computable = False
    if bench_returns is not None and usable and cagr is not None:
        targets = {"dd": mdd_daily, "sigma": sigma_daily}
        computable = True
        for name in rc.MATCHINGS:
            target = targets[name]
            if target is None or not math.isfinite(target):
                computable = False
                break
            match = match_lambda(ctx.curve(name), target)
            if not math.isfinite(match.lam):
                computable = False
                break
            matches[name] = match
            blend = blend_cagr(ctx.bench_nav or [], match.lam)
            if blend is None or not math.isfinite(blend):
                computable = False
                break
            deltas[name] = cagr - blend
        if computable and matches["dd"] is not None:
            jackknife = jackknife_delta(returns or [], ctx.bench_nav or [], matches["dd"].lam)
        if not computable:
            notes.append("delta not computable")
            deltas = dict.fromkeys(rc.MATCHINGS)

    status, gate = status_of(
        ctx, cycles=cycles, nnz_value=count_nnz, computable=computable, broken=broken
    )
    eligible = status == rc.STATUS_ELIGIBLE
    gates: dict[str, bool | None] = {"G1": None, "G2": None, "G4": None}
    passes = False
    if eligible:
        evaluated = point_gates(net_pnl=net_pnl, total_return_pct=total_return, deltas=deltas)
        gates.update(evaluated)
        passes = all(evaluated.values())
        gate = first_failing_point_gate(evaluated)

    published = eligible
    payload: dict[str, Any] = {
        "params": dict(entry.get("params") or {}),
        "cycles": cycles,
        "nnz": count_nnz,
        "status": status,
        "first_failing_gate": gate,
        "net_pnl": net_pnl,
        "total_return_pct": total_return,
        "total_fees": total_fees,
        "fee_multiple": fee_multiple,
        "mdd_daily": mdd_daily,
        "sharpe_ratio": sharpe,
        "lambda_dd": matches["dd"].lam if published and matches["dd"] else None,
        "lambda_sigma": matches["sigma"].lam if published and matches["sigma"] else None,
        "match_residual_dd": matches["dd"].residual if published and matches["dd"] else None,
        "match_residual_sigma": (
            matches["sigma"].residual if published and matches["sigma"] else None
        ),
        "lambda_sigma_crossings": (
            matches["sigma"].crossings if published and matches["sigma"] else None
        ),
        "beta_hat": beta_hat,
        "delta_dd": deltas["dd"] if published else None,
        "delta_sigma": deltas["sigma"] if published else None,
        "gates": gates,
        "passes_gates": passes,
        "se": None,
        "LB": None,
        "LB_all_six_positive": False,
        "jackknife_delta_dd": jackknife if published else None,
        "degenerate_replications": 0,
    }
    return ConfigResult(
        key=key,
        pair=ctx.pair,
        params=dict(entry.get("params") or {}),
        payload=payload,
        returns=returns if usable else None,
        cagr=cagr,
        deltas=deltas,
        lambdas={name: (matches[name].lam if matches[name] else None) for name in rc.MATCHINGS},
        computable=computable,
        eligible=eligible,
        notes=notes,
    )


def point_gates(
    *,
    net_pnl: float | None,
    total_return_pct: float | None,
    deltas: Mapping[str, float | None],
) -> dict[str, bool]:
    """§ F.3 — the three decisional point gates, evaluated on EVERY eligible config.

    ``G1`` is strict (``net_pnl > 0``), ``G2`` is inclusive (``total_return_pct >= 6.0``), ``G4``
    needs both Δ strictly positive. ``G3`` (``net_pnl >= 10 × total_fees``) is **not here**: it is
    descriptive, exported as ``fee_multiple``, and never enters ``passes_gates``.
    """
    return {
        "G1": net_pnl is not None and net_pnl > 0,
        "G2": total_return_pct is not None and total_return_pct >= rc.G2_MIN_RETURN_PCT,
        "G4": all(
            deltas.get(name) is not None and float(deltas[name] or 0.0) > 0
            for name in rc.MATCHINGS
        ),
    }


def first_failing_point_gate(gates: Mapping[str, bool]) -> str | None:
    """G1, then G2, then G4 — the order the report prints, so the reason is never a taste."""
    for name in ("G1", "G2", "G4"):
        if not gates.get(name):
            return name
    return None


def status_of(
    ctx: PairContext, *, cycles: int | None, nnz_value: int | None, computable: bool, broken: bool
) -> tuple[str, str | None]:
    """The § G.1 ladder, first match wins. ``cycles`` unmeasurable falls to clause 4-5, not 3."""
    if not ctx.admissible:
        return rc.STATUS_DESCRIPTIF, REASON_NOT_ADMISSIBLE
    if ctx.warmup == "W2":
        return rc.STATUS_DESCRIPTIF, REASON_WARMUP_W2
    if not ctx.benchmark_comparable:
        return rc.STATUS_NO_BENCHMARK, REASON_NO_BENCHMARK
    if broken or cycles is None:
        return rc.STATUS_NOT_ESTIMABLE, REASON_NOT_ESTIMABLE
    if cycles < rc.CYCLES_MIN:
        return rc.STATUS_BELOW_COVERAGE, REASON_COVERAGE
    if nnz_value is None or nnz_value < rc.NNZ_MIN or not computable:
        return rc.STATUS_NOT_ESTIMABLE, REASON_NOT_ESTIMABLE
    return rc.STATUS_ELIGIBLE, None


def blend_cagr(nav_bh: Sequence[float], lam: float) -> float | None:
    """CAGR of the static blend at λ, by the § F.2 formula applied to the blend's own returns.

    The bootstrap uses the closed form instead (``Σ log1p`` telescopes, so the end NAV suffices):
    the two agree to floating-point noise, and the replication cost is what forbids rebuilding
    1096 returns per (replication, config) there.
    """
    if not nav_bh:
        return None
    blend = [(1.0 - lam) * CAPITAL_FLOAT + lam * float(v) for v in nav_bh]
    if any(value <= 0 or not math.isfinite(value) for value in blend):
        return None
    returns = rc.daily_returns(blend)
    if not returns or any(not math.isfinite(r) or r <= rc.MIN_RETURN_DOMAIN for r in returns):
        return None
    return rc.cagr_from_returns(returns)


def jackknife_delta(returns: Sequence[float], nav_bh: Sequence[float], lam: float) -> float | None:
    """Δ recomputed after dropping the largest and the smallest daily log return (§ F.4).

    Descriptive, decisional nowhere: the kurtosis measured on the reference curve makes a single
    liquidation day dominate, so the tail's contribution is printed rather than assumed away. The
    annualisation stays on the 1096 days of the window and λ is NOT re-matched.
    """
    if len(returns) < 3:
        return None
    logs = sorted(math.log1p(r) for r in returns)
    trimmed = math.fsum(logs[1:-1])
    cagr = (math.exp(trimmed * rc.ANNUALISATION_DAYS / rc.WINDOW_DAYS) - 1.0) * 100.0
    blend = blend_cagr(nav_bh, lam)
    return None if blend is None else cagr - blend


# ---------------------------------------------------------------------------
# Block bootstrap (§ F.4)
# ---------------------------------------------------------------------------


class BudgetExceeded(RuntimeError):
    """The measured λ re-estimation cost does not fit the declared wall-clock budget."""


def stream_seed(pair_index: int, block_length: int) -> int:
    """A reproducible integer identifier of the stream ``default_rng([SEED_BASE, pair, L])``.

    The seed itself is a triple; the frozen schema carries an int, so the first 32-bit word of
    ``SeedSequence(triple).generate_state(1)`` is recorded. Deriving it consumes nothing: the
    generator used by the bootstrap is built from the triple, never from this word.
    """
    sequence = np.random.SeedSequence([rc.SEED_BASE, pair_index, block_length])
    return int(sequence.generate_state(1)[0])


def block_indices(starts: np.ndarray, block_length: int, n: int) -> np.ndarray:
    """Circular blocks: ``(starts + arange(L)) % N`` truncated to N, paired config <-> benchmark."""
    offsets = np.arange(block_length, dtype=np.int64)
    idx = (starts[:, :, None] + offsets).reshape(starts.shape[0], -1)[:, :n]
    return idx % n


def date_counts(idx: np.ndarray, n: int) -> np.ndarray:
    """``C`` of § F.4 (B x N, int32): how many times each date appears in each replication."""
    rows = idx.shape[0]
    flat = (idx + (np.arange(rows, dtype=np.int64) * n)[:, None]).ravel()
    return np.bincount(flat, minlength=rows * n).astype(np.int32).reshape(rows, n)


def bootstrap_dd_curve(nav: np.ndarray, lams: np.ndarray) -> np.ndarray:
    """``λ -> MDD(NAV_λ)`` for every replication at once (numpy, bootstrap only)."""
    peak = np.maximum.accumulate(nav, axis=1)
    drop = peak - nav
    out = np.empty((nav.shape[0], lams.size), dtype=np.float64)
    for position, lam in enumerate(lams):
        den = (1.0 - lam) * CAPITAL_FLOAT + lam * peak
        out[:, position] = (lam * drop / den).max(axis=1) * 100.0
    return out


def bootstrap_sigma_curve(nav: np.ndarray, lams: np.ndarray) -> np.ndarray:
    """``λ -> σ_daily(NAV_λ)`` for every replication at once."""
    out = np.empty((nav.shape[0], lams.size), dtype=np.float64)
    for position, lam in enumerate(lams):
        blend = (1.0 - lam) * CAPITAL_FLOAT + lam * nav
        out[:, position] = (blend[:, 1:] / blend[:, :-1] - 1.0).std(axis=1, ddof=1)
    return out


def invert_curve(curve: np.ndarray, targets: np.ndarray, lams: np.ndarray) -> np.ndarray:
    """``min{λ : curve(λ) >= target}`` per (replication, config), else 1 — no monotonicity needed.

    On a monotone curve this is exactly ``searchsorted``; on a non-monotone one it is the § E.3
    definition itself (the smallest crossing), which ``searchsorted`` would not return.
    """
    out = np.empty(targets.shape, dtype=np.float64)
    for column in range(targets.shape[1]):
        mask = curve >= targets[:, column][:, None]
        out[:, column] = np.where(mask.any(axis=1), lams[mask.argmax(axis=1)], 1.0)
    return out


def invert_curve_two_stage(
    curve: np.ndarray, targets: np.ndarray, lams: np.ndarray, every: int = COARSE_EVERY
) -> np.ndarray:
    """The frozen two-stage inversion (coarse 0.005, then ±0.005 at 0.001) over the same curve.

    Kept as the written reference of § F.4. Production uses :func:`invert_curve`: once the
    replications are batched, the coarse stage saves nothing (the union of the refinement windows
    over the configs of a chunk covers the grid), and the full 0.001 grid returns the same λ on a
    monotone curve while staying the § E.3 definition on a non-monotone one.
    """
    out = np.full(targets.shape, 1.0, dtype=np.float64)
    coarse = curve[:, ::every]
    for column in range(targets.shape[1]):
        target = targets[:, column][:, None]
        hit = (coarse >= target).any(axis=1)
        position = (coarse >= target).argmax(axis=1) * every
        for row in np.nonzero(hit)[0]:
            low = max(0, int(position[row]) - every)
            high = min(curve.shape[1] - 1, int(position[row]) + every)
            window = curve[row, low : high + 1]
            found = np.nonzero(window >= targets[row, column])[0]
            out[row, column] = lams[low + int(found[0])] if found.size else 1.0
    return out


def bootstrap_config_mdd(returns: np.ndarray, idx: np.ndarray) -> np.ndarray:
    """MDD of each config's bootstrap index path — order matters, so the paths are rebuilt."""
    rows = idx.shape[0]
    out = np.empty((rows, returns.shape[1]), dtype=np.float64)
    ones = np.ones((rows, 1), dtype=np.float64)
    for column in range(returns.shape[1]):
        path = np.concatenate(
            [ones, np.cumprod(1.0 + returns[:, column][idx], axis=1)], axis=1
        )
        out[:, column] = mdd_numpy(path)
    return out


def bootstrap_config_sigma(counts: np.ndarray, returns: np.ndarray, n: int) -> np.ndarray:
    """σ of each config's resampled sample — order-free, so the date counts are enough."""
    weights = counts.astype(np.float64)
    total = weights @ returns
    squared = weights @ (returns * returns)
    mean = total / n
    var = (squared - n * mean * mean) / (n - 1)
    return np.sqrt(np.maximum(var, 0.0))


@dataclass
class BootstrapOutcome:
    """What one pair's bootstrap produced, per block length and per matching.

    ``lb`` and ``se`` are keyed ``config -> block length -> matching``. The frozen ``effect.json``
    schema carries one ``se`` per block length only: the **dd** matching is published there (it is
    the headline of § G.3, whose representative maximises ``Δ̂^dd``), and ``calibration.json``
    carries both.
    """

    q_fwe: dict[str, dict[str, float]]
    lb: dict[str, dict[str, dict[str, float]]]
    se: dict[str, dict[str, dict[str, float]]]
    degenerate: dict[str, int]
    cost_sec: dict[str, dict[str, float]]
    mode: str


def bootstrap_pair(
    *,
    keys: Sequence[str],
    returns: np.ndarray,
    bench_returns: np.ndarray,
    delta_hat: Mapping[str, np.ndarray],
    frozen_lambda: Mapping[str, np.ndarray],
    pair_index: int,
    block_lengths: Sequence[int],
    replications: int,
    chunk_size: int = DEFAULT_CHUNK,
    reestimate: bool = True,
    budget_sec: float = rc.LAMBDA_REESTIMATION_BUDGET_SEC,
) -> BootstrapOutcome:
    """Circular block bootstrap of Δ with the single-step simultaneous correction of § F.4.

    ``returns`` is (N, |J_calc|) — the correction family is the set of **computable** curves, with
    no ``-inf`` padding: admissibility, coverage and gates are applied at the verdict stage. λ is
    re-estimated inside every replication unless ``reestimate`` is False, in which case the bound
    is the declared fallback (λ frozen, "analyse de sensibilité, sans garantie de couverture
    95 %"). ``starts`` is drawn ONCE per block length, before any chunking.
    """
    n = returns.shape[0]
    lams = lambda_array()
    with np.errstate(invalid="ignore", divide="ignore"):
        # A return at or below -1 cannot reach here through the eligibility clauses (min r > -0.5),
        # but a degenerate series must be COUNTED, never raise: § F.7 reports it.
        log_returns = np.log1p(returns)
    q_fwe: dict[str, dict[str, float]] = {}
    lb: dict[str, dict[str, dict[str, float]]] = {key: {} for key in keys}
    se: dict[str, dict[str, dict[str, float]]] = {key: {} for key in keys}
    degenerate = dict.fromkeys(keys, 0)
    cost: dict[str, dict[str, float]] = {}
    for block_length in block_lengths:
        label = str(block_length)
        rng = np.random.default_rng([rc.SEED_BASE, pair_index, block_length])
        blocks = math.ceil(n / block_length)
        starts = rng.integers(0, n, size=(replications, blocks))
        stars = {name: np.empty((replications, len(keys)), dtype=np.float64)
                 for name in rc.MATCHINGS}
        cost[label] = dict.fromkeys(rc.MATCHINGS, 0.0)
        done = 0
        for begin in range(0, replications, chunk_size):
            chunk = starts[begin : begin + chunk_size]
            idx = block_indices(chunk, block_length, n)
            counts = date_counts(idx, n)
            weights = counts.astype(np.float64)
            with np.errstate(invalid="ignore"):
                total_log = weights @ log_returns
                cagr_config = np.expm1(total_log * rc.ANNUALISATION_DAYS / rc.WINDOW_DAYS) * 100.0
            nav = np.concatenate(
                [
                    np.full((idx.shape[0], 1), CAPITAL_FLOAT),
                    CAPITAL_FLOAT * np.cumprod(1.0 + bench_returns[idx], axis=1),
                ],
                axis=1,
            )
            done += idx.shape[0]
            for name in rc.MATCHINGS:
                if reestimate:
                    started = perf_counter()
                    curve = (
                        bootstrap_dd_curve(nav, lams)
                        if name == "dd"
                        else bootstrap_sigma_curve(nav, lams)
                    )
                    targets = (
                        bootstrap_config_mdd(returns, idx)
                        if name == "dd"
                        else bootstrap_config_sigma(counts, returns, n)
                    )
                    lam_star = invert_curve(curve, targets, lams)
                    cost[label][name] += perf_counter() - started
                    projected = cost[label][name] * replications / done
                    if projected > budget_sec:
                        raise BudgetExceeded(
                            f"L={block_length} {name}: {projected:.1f} s projected over "
                            f"{replications} replications, budget {budget_sec:.1f} s"
                        )
                else:
                    lam_star = np.broadcast_to(
                        np.asarray(frozen_lambda[name], dtype=np.float64), (idx.shape[0], len(keys))
                    )
                end = (1.0 - lam_star) * CAPITAL_FLOAT + lam_star * nav[:, -1][:, None]
                with np.errstate(invalid="ignore", divide="ignore"):
                    ratio = np.where(end > 0, end / CAPITAL_FLOAT, np.nan)
                    cagr_blend = (
                        np.power(ratio, rc.ANNUALISATION_DAYS / rc.WINDOW_DAYS) - 1.0
                    ) * 100.0
                stars[name][begin : begin + idx.shape[0]] = cagr_config - cagr_blend
        for name in rc.MATCHINGS:
            matrix = stars[name]
            finite = np.isfinite(matrix)
            centred = np.where(finite, matrix - np.asarray(delta_hat[name]), np.nan)
            usable_rows = finite.any(axis=1)
            maxima = np.full(replications, np.nan)
            if usable_rows.any():
                maxima[usable_rows] = np.nanmax(centred[usable_rows], axis=1)
            finite_maxima = maxima[np.isfinite(maxima)]
            quantile = (
                float(np.quantile(finite_maxima, 1.0 - rc.ALPHA, method="linear"))
                if finite_maxima.size
                else float("nan")
            )
            q_fwe.setdefault(label, {})[name] = quantile
            for column, key in enumerate(keys):
                lb[key].setdefault(label, {})[name] = float(delta_hat[name][column]) - quantile
                degenerate[key] = max(
                    degenerate[key], int(replications - int(finite[:, column].sum()))
                )
                column_values = matrix[:, column][finite[:, column]]
                se[key].setdefault(label, {})[name] = (
                    float(np.std(column_values, ddof=1))
                    if column_values.size > 1
                    else float("nan")
                )
    return BootstrapOutcome(
        q_fwe=q_fwe,
        lb=lb,
        se=se,
        degenerate=degenerate,
        cost_sec=cost,
        mode=LAMBDA_MODE_REESTIMATED if reestimate else LAMBDA_MODE_FROZEN,
    )


# ---------------------------------------------------------------------------
# Pair analysis and artefact
# ---------------------------------------------------------------------------


@dataclass
class PairAnalysis:
    ctx: PairContext
    results: list[ConfigResult]
    j_calc: list[str]
    j_eligible: list[str]
    not_estimable: bool = False
    reason: str | None = None
    warmup_classes_seen: int = 1
    outcome: BootstrapOutcome | None = None


def modal_failing_gate(results: Sequence[ConfigResult]) -> str | None:
    """§ F.6 — the reason of an empty eligible set is the modal failing gate, never a taste."""
    counts: dict[str, int] = {}
    for result in results:
        gate = result.payload["first_failing_gate"]
        if gate:
            counts[gate] = counts.get(gate, 0) + 1
    if not counts:
        return None
    best = max(counts.values())
    tied = sorted(gate for gate, count in counts.items() if count == best)
    order = {name: position for position, name in enumerate(rc.REASON_PRIORITY)}
    return min(tied, key=lambda gate: (order.get(gate, len(order)), gate))


def analyse_pair(
    pair: str,
    entries: Mapping[str, Mapping[str, Any]],
    *,
    admissible: bool,
    benchmark: Mapping[str, Any] | None,
) -> PairAnalysis:
    """Point estimates for the 48 configs of one pair, then ``J_calc`` and ``J_eligible``."""
    ordered = sorted(entries.items(), key=lambda item: grid_sort_key(item[1].get("params")))
    warmup, seen = pair_warmup_class([entry for _, entry in ordered])
    comparable = bool(
        benchmark
        and benchmark.get("buildable")
        and (benchmark.get("comparability") or {}).get("comparable")
        and benchmark.get("nav")
    )
    ctx = PairContext(
        pair=pair,
        pair_index=rc.PAIRS.index(pair) if pair in rc.PAIRS else len(rc.PAIRS),
        admissible=admissible,
        warmup=warmup,
        benchmark_comparable=comparable,
    )
    for _, entry in ordered:
        block = (entry.get("warmup") or {}).get("all")
        if isinstance(block, Mapping):
            ctx.warmup_gaps = {
                tf: (block.get(tf) or {}).get("largest_gap_candles") for tf in ("1d", "1w")
            }
            break
    if comparable and benchmark is not None:
        ctx.bench_nav = [float(v) for v in benchmark["nav"]]
        ctx.bench_returns = rc.daily_returns(ctx.bench_nav)
        if not returns_usable(ctx.bench_returns):
            ctx.benchmark_comparable = False
            ctx.bench_nav = None
            ctx.bench_returns = None
    results = [analyse_config(key, entry, ctx) for key, entry in ordered]
    j_calc = [r.key for r in results if r.computable]
    j_eligible = [r.key for r in results if r.eligible]
    analysis = PairAnalysis(
        ctx=ctx,
        results=results,
        j_calc=j_calc,
        j_eligible=j_eligible,
        warmup_classes_seen=seen,
    )
    if not j_eligible:
        analysis.not_estimable = True
        analysis.reason = modal_failing_gate(results)
    return analysis


def grid_sort_key(params: Any) -> tuple[float, float, int]:
    """Deterministic grid order: (min_spacing_pct, atr_multiplier, bear_protection_mode)."""
    if not isinstance(params, Mapping):
        return (math.inf, math.inf, len(GRID_ATR_GRID["bear_protection_mode"]))
    modes = list(GRID_ATR_GRID["bear_protection_mode"])
    mode = params.get("bear_protection_mode")
    spacing = _finite(params.get("min_spacing_pct"))
    multiplier = _finite(params.get("atr_multiplier"))
    return (
        math.inf if spacing is None else spacing,
        math.inf if multiplier is None else multiplier,
        modes.index(mode) if mode in modes else len(modes),
    )


def run_pair_bootstrap(
    analysis: PairAnalysis,
    *,
    block_lengths: Sequence[int],
    replications: int,
    chunk_size: int,
    reestimate: bool,
    budget_sec: float,
) -> None:
    """Run the bootstrap on ``J_calc`` and publish only what an eligible config may carry."""
    ctx = analysis.ctx
    if not analysis.j_eligible or ctx.bench_returns is None:
        return
    by_key = {result.key: result for result in analysis.results}
    keys = list(analysis.j_calc)
    matrix = np.asarray([by_key[key].returns for key in keys], dtype=np.float64).T
    delta_hat = {
        name: np.asarray([by_key[key].deltas[name] for key in keys], dtype=np.float64)
        for name in rc.MATCHINGS
    }
    frozen = {
        name: np.asarray([by_key[key].lambdas[name] for key in keys], dtype=np.float64)
        for name in rc.MATCHINGS
    }
    outcome = bootstrap_pair(
        keys=keys,
        returns=matrix,
        bench_returns=np.asarray(ctx.bench_returns, dtype=np.float64),
        delta_hat=delta_hat,
        frozen_lambda=frozen,
        pair_index=ctx.pair_index,
        block_lengths=block_lengths,
        replications=replications,
        chunk_size=chunk_size,
        reestimate=reestimate,
        budget_sec=budget_sec,
    )
    analysis.outcome = outcome
    degenerate_pair = False
    for key in keys:
        result = by_key[key]
        result.payload["degenerate_replications"] = outcome.degenerate[key]
        if outcome.degenerate[key] > rc.DEGENERATE_MAX:
            degenerate_pair = True
        if not result.eligible:
            continue
        result.payload["se"] = {
            label: values["dd"] for label, values in outcome.se[key].items()
        }
        result.payload["LB"] = {
            label: dict(values) for label, values in outcome.lb[key].items()
        }
        result.payload["LB_all_six_positive"] = all(
            values[name] > 0
            for values in outcome.lb[key].values()
            for name in rc.MATCHINGS
        )
    if degenerate_pair:
        # § F.7 — the inference is declared unusable for the pair; the numbers stay visible but
        # the decisional flag cannot carry a candidat.
        analysis.not_estimable = True
        analysis.reason = REASON_NOT_ESTIMABLE
        for key in keys:
            by_key[key].payload["LB_all_six_positive"] = False


def reset_bootstrap_state(analysis: PairAnalysis) -> None:
    """Undo what the bootstrap published, so a fallback pass restarts from the point estimates."""
    analysis.outcome = None
    analysis.not_estimable = not analysis.j_eligible
    analysis.reason = modal_failing_gate(analysis.results) if analysis.not_estimable else None
    for result in analysis.results:
        result.payload["se"] = None
        result.payload["LB"] = None
        result.payload["LB_all_six_positive"] = False
        result.payload["degenerate_replications"] = 0


def se_ratio(analysis: PairAnalysis) -> float | None:
    """``max_j se_j / min_j se_j`` over ``J_calc`` at the headline block length (dd matching)."""
    outcome = analysis.outcome
    if outcome is None:
        return None
    label = str(rc.BLOCK_LENGTH_HEADLINE)
    values = [
        outcome.se[key][label]["dd"]
        for key in analysis.j_calc
        if label in outcome.se.get(key, {}) and math.isfinite(outcome.se[key][label]["dd"])
    ]
    if not values or min(values) <= 0:
        return None
    return max(values) / min(values)


def coverage_rows(analysis: PairAnalysis) -> list[dict[str, Any]]:
    """The 4 x 4 x 3 table of § C.2 — the truncation of the design has to be visible."""
    by_params: dict[tuple[Any, Any, Any], ConfigResult] = {}
    for result in analysis.results:
        params = result.params
        by_params[(
            _finite(params.get("min_spacing_pct")),
            _finite(params.get("atr_multiplier")),
            params.get("bear_protection_mode"),
        )] = result
    rows: list[dict[str, Any]] = []
    for spacing in GRID_ATR_GRID["min_spacing_pct"]:
        for multiplier in GRID_ATR_GRID["atr_multiplier"]:
            for mode in GRID_ATR_GRID["bear_protection_mode"]:
                result = by_params.get((float(spacing), float(multiplier), mode))
                cycles = result.payload["cycles"] if result else None
                rows.append({
                    "min_spacing_pct": float(spacing),
                    "atr_multiplier": float(multiplier),
                    "bear_protection_mode": mode,
                    "cycles": cycles,
                    "below": cycles is None or cycles < rc.CYCLES_MIN,
                })
    return rows


def prespec_descriptor() -> dict[str, str]:
    path = rc.PROJECT_ROOT / PRESPEC_RELPATH
    digest = hashlib.sha256(path.read_bytes()).hexdigest() if path.exists() else ""
    return {"path": PRESPEC_RELPATH, "sha256": digest}


def build_effect_payload(
    analyses: Mapping[str, PairAnalysis],
    *,
    now: datetime,
    replications: int,
    block_lengths: Sequence[int],
    lambda_mode: str,
) -> dict[str, Any]:
    """The frozen ``effect.json`` object (§ L step 9), deterministic for a given ``now``."""
    pairs: dict[str, Any] = {}
    for pair, analysis in analyses.items():
        outcome = analysis.outcome
        pairs[pair] = {
            "admissible": analysis.ctx.admissible,
            "warmup_class": analysis.ctx.warmup,
            "benchmark_comparable": analysis.ctx.benchmark_comparable,
            "n_J_calc": len(analysis.j_calc),
            "J_calc": list(analysis.j_calc),
            "J_eligible": list(analysis.j_eligible),
            "q_FWE": (
                {label: dict(values) for label, values in outcome.q_fwe.items()}
                if outcome
                else None
            ),
            "se_ratio_max_min": se_ratio(analysis),
            "configs": {result.key: result.payload for result in analysis.results},
            "not_estimable": analysis.not_estimable,
            "reason": analysis.reason,
        }
    return {
        "generated_at": now.isoformat(),
        "base_sha": rc.BASE_SHA,
        "prespec": prespec_descriptor(),
        "B": replications,
        "block_lengths": [int(length) for length in block_lengths],
        "seeds": {
            pair: {
                str(length): stream_seed(analysis.ctx.pair_index, length)
                for length in block_lengths
            }
            for pair, analysis in analyses.items()
        },
        "numpy_version": np.__version__,
        "lambda_mode": lambda_mode,
        "lambda_mode_label": FROZEN_LABEL if lambda_mode == LAMBDA_MODE_FROZEN else None,
        "pairs": pairs,
        "coverage_table": {
            pair: coverage_rows(analysis) for pair, analysis in analyses.items()
        },
    }


def effect_violations(
    payload: Mapping[str, Any], analyses: Mapping[str, PairAnalysis]
) -> list[str]:
    """Self-checks: a published λ / Δ must be finite (§ F.7), and no entry may carry an error."""
    violations: list[str] = []
    for pair, analysis in analyses.items():
        for result in analysis.results:
            if ENTRY_ERROR_NOTE in result.notes:
                violations.append(
                    f"{result.key}: {ENTRY_ERROR_NOTE} (§ I-A.3 should have stopped the run)"
                )
        if analysis.warmup_classes_seen > 1:
            violations.append(
                f"{pair}: the warmup block differs between configs "
                f"({analysis.warmup_classes_seen} classes) — strictest kept (§ I-A.8)"
            )
    for pair, block in payload["pairs"].items():
        for key, config in block["configs"].items():
            for name in ("lambda_dd", "lambda_sigma", "delta_dd", "delta_sigma"):
                value = config[name]
                if value is not None and not math.isfinite(float(value)):
                    violations.append(f"{pair}/{key}: {name} is not finite")
    return violations


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------


def render_lines(payload: Mapping[str, Any]) -> list[str]:
    lines = [
        f"effect B={payload['B']} L={payload['block_lengths']} "
        f"lambda_mode={payload['lambda_mode']} numpy {payload['numpy_version']}"
    ]
    if payload["lambda_mode"] == LAMBDA_MODE_FROZEN:
        lines.append(f"    {FROZEN_LABEL}")
    for pair, block in payload["pairs"].items():
        lines.append(
            f"{pair}: admissible={block['admissible']} warmup={block['warmup_class']} "
            f"benchmark_comparable={block['benchmark_comparable']} "
            f"|J_calc|={block['n_J_calc']} |J_eligible|={len(block['J_eligible'])}"
            + (f" not_estimable ({block['reason']})" if block["not_estimable"] else "")
        )
        statuses: dict[str, int] = {}
        for config in block["configs"].values():
            statuses[config["status"]] = statuses.get(config["status"], 0) + 1
        lines.append("    statuts: " + ", ".join(f"{k} {v}" for k, v in sorted(statuses.items())))
        passing = [key for key, c in block["configs"].items() if c["passes_gates"]]
        lines.append(f"    passes_gates: {len(passing)}")
        six = [key for key, c in block["configs"].items() if c["LB_all_six_positive"]]
        lines.append(f"    LB positives sur les six combinaisons: {len(six)}")
        below = sum(1 for row in payload["coverage_table"].get(pair, []) if row["below"])
        lines.append(f"    couverture: {below}/48 cellules sous {rc.CYCLES_MIN} cycles")
    return lines


def render_markdown(
    payload: Mapping[str, Any], analyses: Mapping[str, PairAnalysis] | None = None
) -> str:
    """The § G.6 report line per config, the 4 x 4 x 3 coverage table, the mandated statements."""
    analyses = analyses or {}
    out = ["# Rejeu diagnostic grid — effet (§ C, § E.3, § F)", ""]
    out.append(f"Généré le {payload['generated_at']} · base_sha `{payload['base_sha'][:12]}`")
    out.append("")
    out.append(
        f"`B` = {payload['B']} · `L` = {payload['block_lengths']} · "
        f"λ = {payload['lambda_mode']} · numpy {payload['numpy_version']}"
    )
    out += ["", f"> {RETROSPECTIVE_STATEMENT}"]
    if payload["lambda_mode"] == LAMBDA_MODE_FROZEN:
        out.append("")
        out.append(f"> {FROZEN_LABEL}")
    for pair, block in payload["pairs"].items():
        out += ["", f"## {pair}", ""]
        out.append(
            f"admissible **{block['admissible']}** · warmup **{block['warmup_class']}** · "
            f"benchmark comparable **{block['benchmark_comparable']}** · "
            f"|J_calc| {block['n_J_calc']} · |J_eligible| {len(block['J_eligible'])}"
        )
        if block["warmup_class"] == "W1":
            gaps = analyses[pair].ctx.warmup_gaps if pair in analyses else {}
            out += ["", "> " + W1_QUALIFIER.format(
                pair=pair, gap_1d=gaps.get("1d"), gap_1w=gaps.get("1w")
            )]
        lambdas = [
            config["lambda_dd"]
            for config in block["configs"].values()
            if config["lambda_dd"] is not None
        ]
        if lambdas and min(lambdas) < SMALL_LAMBDA:
            out += ["", f"> {SMALL_LAMBDA_STATEMENT}"]
        out.append("")
        if block["se_ratio_max_min"] is not None:
            out.append(f"`max se / min se` sur J_calc (L = {rc.BLOCK_LENGTH_HEADLINE}, dd) : "
                       f"{block['se_ratio_max_min']:.2f}")
        out += ["", "| config | cycles | nnz | statut | gate | net_pnl | return % | "
                    "net/fees | MDD | λ_dd | λ_σ | Δ_dd | Δ_σ | LB(21,dd) |",
                "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
        for key, config in block["configs"].items():
            lb = (config["LB"] or {}).get(str(rc.BLOCK_LENGTH_HEADLINE), {}).get("dd")
            out.append(
                f"| `{key}` | {_cell(config['cycles'])} | {_cell(config['nnz'])} | "
                f"{config['status']} | {config['first_failing_gate'] or '—'} | "
                f"{_cell(config['net_pnl'])} | {_cell(config['total_return_pct'])} | "
                f"{_cell(config['fee_multiple'])} | {_cell(config['mdd_daily'])} | "
                f"{_cell(config['lambda_dd'])} | {_cell(config['lambda_sigma'])} | "
                f"{_cell(config['delta_dd'])} | {_cell(config['delta_sigma'])} | {_cell(lb)} |"
            )
        rows = payload["coverage_table"].get(pair, [])
        out += ["", f"### Couverture (§ C.2) — cellules sous {rc.CYCLES_MIN} cycles", ""]
        out += ["| plancher | multiplicateur | mode | cycles | sous le seuil |",
                "|---|---|---|---|---|"]
        for row in rows:
            out.append(
                f"| {row['min_spacing_pct']} | {row['atr_multiplier']} | "
                f"{row['bear_protection_mode']} | {_cell(row['cycles'])} | "
                f"{'oui' if row['below'] else 'non'} |"
            )
        out += ["", "Configs perdues au filtre par cellule (plancher × multiplicateur), "
                    "sur les trois modes :", ""]
        multipliers = [float(m) for m in GRID_ATR_GRID["atr_multiplier"]]
        out += ["| plancher \\ m | " + " | ".join(str(m) for m in multipliers) + " |",
                "|---" * (len(multipliers) + 1) + "|"]
        for spacing in GRID_ATR_GRID["min_spacing_pct"]:
            cells = []
            for multiplier in multipliers:
                lost = sum(
                    1
                    for row in rows
                    if row["min_spacing_pct"] == float(spacing)
                    and row["atr_multiplier"] == multiplier
                    and row["below"]
                )
                cells.append(f"{lost}/3")
            out.append(f"| {float(spacing)} | " + " | ".join(cells) + " |")
    out.append("")
    return "\n".join(out)


def _cell(value: Any, digits: int = 4) -> str:
    if value is None:
        return "—"
    if isinstance(value, float):
        return f"{value:.{digits}f}"
    return str(value)


# ---------------------------------------------------------------------------
# Modes
# ---------------------------------------------------------------------------


def load_json(path: Path, label: str) -> Any:
    try:
        return rc.read_json(path)
    except (OSError, ValueError) as exc:
        raise SystemExit(f"--{label}: {exc}") from exc


def run_effect(args: argparse.Namespace, now: datetime) -> int:
    validation = load_json(args.validation, "validation")
    if not isinstance(validation, Mapping) or validation.get("ok") is not True:
        print(
            f"--validation: {args.validation} does not carry ok=true; § G.2 stops the run "
            "before the analyses (R0_INVALID_RUN)",
            file=sys.stderr,
        )
        return 2
    campaign = load_json(args.campaign, "campaign")
    benchmark = load_json(args.benchmark, "benchmark")
    coverage = load_json(args.coverage, "coverage")
    if not isinstance(campaign, Mapping) or not campaign:
        print(f"--campaign: {args.campaign} is not a non-empty JSON object", file=sys.stderr)
        return 2
    entries_by_pair: dict[str, dict[str, Mapping[str, Any]]] = {}
    for key, entry in campaign.items():
        if not isinstance(entry, Mapping):
            continue
        pair = entry.get("pair")
        if not isinstance(pair, str):
            continue
        entries_by_pair.setdefault(pair, {})[key] = entry
    analyses: dict[str, PairAnalysis] = {}
    for pair in rc.PAIRS:
        if pair not in entries_by_pair:
            continue
        analyses[pair] = analyse_pair(
            pair,
            entries_by_pair[pair],
            admissible=bool(
                ((coverage.get("pairs") or {}).get(pair) or {}).get("admissible")
                if isinstance(coverage, Mapping)
                else False
            ),
            benchmark=(
                (benchmark.get("pairs") or {}).get(pair) if isinstance(benchmark, Mapping) else None
            ),
        )
    for pair in sorted(set(entries_by_pair) - set(rc.PAIRS)):
        print(f"note: {pair} is outside the frozen perimeter, ignored", file=sys.stderr)

    calibration = None
    if args.calibration and Path(args.calibration).exists():
        calibration = rc.read_json(args.calibration)
    reestimate = args.reestimate
    if isinstance(calibration, Mapping):
        verified = (calibration.get("mdd_vectorised") or {}).get("verified")
        if verified is not True:
            reestimate = False
            print(
                "note: calibration.json does not carry a verified vectorised MDD — the bound "
                "falls back to a frozen λ",
                file=sys.stderr,
            )
    checked = inline_equivalence(analyses)
    if checked is not None and not checked["verified"]:
        reestimate = False
        print(
            f"note: the vectorised MDD does not match the Decimal routine "
            f"(residual {checked['max_relative_residual']:.3e}) — the bound falls back to a "
            "frozen λ",
            file=sys.stderr,
        )
    lambda_mode = LAMBDA_MODE_REESTIMATED if reestimate else LAMBDA_MODE_FROZEN
    try:
        for analysis in analyses.values():
            run_pair_bootstrap(
                analysis,
                block_lengths=args.block_lengths,
                replications=args.bootstrap_b,
                chunk_size=args.chunk_size,
                reestimate=reestimate,
                budget_sec=args.reestimation_budget_sec,
            )
    except BudgetExceeded as exc:
        print(f"note: λ re-estimation over budget ({exc}) — frozen λ fallback", file=sys.stderr)
        lambda_mode = LAMBDA_MODE_FROZEN
        for analysis in analyses.values():
            reset_bootstrap_state(analysis)
            run_pair_bootstrap(
                analysis,
                block_lengths=args.block_lengths,
                replications=args.bootstrap_b,
                chunk_size=args.chunk_size,
                reestimate=False,
                budget_sec=args.reestimation_budget_sec,
            )
    payload = build_effect_payload(
        analyses,
        now=now,
        replications=args.bootstrap_b,
        block_lengths=args.block_lengths,
        lambda_mode=lambda_mode,
    )
    digest = rc.write_json(args.output, payload)
    print("\n".join(render_lines(payload)))
    print(f"written {args.output} sha256 {digest}")
    if args.markdown:
        Path(args.markdown).parent.mkdir(parents=True, exist_ok=True)
        Path(args.markdown).write_text(render_markdown(payload, analyses), encoding="utf-8")
        print(f"written {args.markdown}")
    violations = effect_violations(payload, analyses)
    for violation in violations:
        print(f"VIOLATION {violation}", file=sys.stderr)
    return 1 if violations else 0


def inline_equivalence(analyses: Mapping[str, PairAnalysis]) -> dict[str, Any] | None:
    """Check the numpy MDD against the Decimal routine on the curves this run actually uses."""
    series: list[Sequence[float]] = []
    for analysis in analyses.values():
        if analysis.ctx.bench_nav is None:
            continue
        series.append(analysis.ctx.bench_nav)
        navs = [Decimal(str(v)) for v in analysis.ctx.bench_nav]
        for lam in (Decimal("0.25"), Decimal("0.5"), Decimal("1")):
            series.append([float(v) for v in blend_values(navs, lam)])
    return mdd_equivalence(series) if series else None


def run_calibration(args: argparse.Namespace, now: datetime) -> int:
    """§ F.5 — the pre-registered single-config SE of Δ, and the MDD equivalence check."""
    source = load_json(args.source, "source")
    benchmark = load_json(args.benchmark, "benchmark")
    pair = args.pair
    entry = None
    entry_key = ""
    for key, candidate in (source or {}).items():
        if isinstance(candidate, Mapping) and candidate.get("pair") == pair:
            entry, entry_key = candidate, key
            break
    if entry is None:
        print(f"--source: no entry for {pair} in {args.source}", file=sys.stderr)
        return 2
    block = (benchmark.get("pairs") or {}).get(pair) if isinstance(benchmark, Mapping) else None
    if not block or not block.get("buildable") or not block.get("nav"):
        print(f"--benchmark: no buildable benchmark for {pair}", file=sys.stderr)
        return 2
    ctx = PairContext(
        pair=pair,
        pair_index=rc.PAIRS.index(pair) if pair in rc.PAIRS else 0,
        admissible=True,
        warmup=warmup_class((entry.get("warmup") or {}).get("all")),
        benchmark_comparable=True,
        bench_nav=[float(v) for v in block["nav"]],
    )
    ctx.bench_returns = rc.daily_returns(ctx.bench_nav or [])
    result = analyse_config(entry_key, entry, ctx)
    if not result.computable:
        print(f"--source: Δ is not computable on {entry_key}", file=sys.stderr)
        return 2
    navs = [Decimal(str(v)) for v in ctx.bench_nav or []]
    series: list[Sequence[float]] = [ctx.bench_nav or []]
    values = ((entry.get("equity_daily") or {}).get("all") or {}).get("values")
    if isinstance(values, list):
        series.append([float(v) for v in values])
    series += [[float(v) for v in blend_values(navs, lam)] for lam in lambda_values()]
    equivalence = mdd_equivalence(series)

    keys = [entry_key]
    matrix = np.asarray([result.returns], dtype=np.float64).T
    delta_hat = {
        name: np.asarray([result.deltas[name]], dtype=np.float64) for name in rc.MATCHINGS
    }
    frozen = {
        name: np.asarray([result.lambdas[name]], dtype=np.float64) for name in rc.MATCHINGS
    }
    reestimate = equivalence["verified"]
    try:
        outcome = bootstrap_pair(
            keys=keys,
            returns=matrix,
            bench_returns=np.asarray(ctx.bench_returns, dtype=np.float64),
            delta_hat=delta_hat,
            frozen_lambda=frozen,
            pair_index=ctx.pair_index,
            block_lengths=args.block_lengths,
            replications=args.bootstrap_b,
            chunk_size=args.chunk_size,
            reestimate=reestimate,
            budget_sec=args.reestimation_budget_sec,
        )
        over_budget = False
    except BudgetExceeded as exc:
        print(f"note: λ re-estimation over budget ({exc})", file=sys.stderr)
        over_budget = True
        outcome = bootstrap_pair(
            keys=keys,
            returns=matrix,
            bench_returns=np.asarray(ctx.bench_returns, dtype=np.float64),
            delta_hat=delta_hat,
            frozen_lambda=frozen,
            pair_index=ctx.pair_index,
            block_lengths=args.block_lengths,
            replications=args.bootstrap_b,
            chunk_size=args.chunk_size,
            reestimate=False,
            budget_sec=args.reestimation_budget_sec,
        )
    # The budget of § F.4 is declared per (L, matching): the cost recorded per L is the worst of
    # the two matchings, so the comparison to the budget is the one the fallback rule reads.
    cost = {
        label: max(measured.values()) if measured else 0.0
        for label, measured in outcome.cost_sec.items()
    }
    planned = (
        LAMBDA_MODE_REESTIMATED
        if equivalence["verified"]
        and not over_budget
        and all(value <= args.reestimation_budget_sec for value in cost.values())
        else LAMBDA_MODE_FROZEN
    )
    payload = {
        "generated_at": now.isoformat(),
        "base_sha": rc.BASE_SHA,
        "prespec": prespec_descriptor(),
        "source": _relpath(args.source),
        "pair": pair,
        "reference_disclosure": REFERENCE_DISCLOSURE,
        "mdd_vectorised": equivalence,
        "observed": {
            "cagr_pct": result.cagr,
            "sigma_daily": sigma_of_returns(result.returns or []),
            "nnz": result.payload["nnz"],
            "lambda_dd": result.lambdas["dd"],
            "lambda_sigma": result.lambdas["sigma"],
            "delta_dd": result.deltas["dd"],
            "delta_sigma": result.deltas["sigma"],
        },
        "se_delta_single_config": {
            label: dict(values) for label, values in sorted(
                outcome.se[entry_key].items(), key=lambda item: int(item[0])
            )
        },
        "B": args.bootstrap_b,
        "seeds": {
            str(length): stream_seed(ctx.pair_index, length) for length in args.block_lengths
        },
        "numpy_version": np.__version__,
        "reestimation_cost_sec": cost,
        "reestimation_budget_sec": args.reestimation_budget_sec,
        "lambda_mode_planned": planned,
    }
    digest = rc.write_json(args.output, payload)
    for line in render_calibration(payload):
        print(line)
    print(f"written {args.output} sha256 {digest}")
    return 0


def render_calibration(payload: Mapping[str, Any]) -> list[str]:
    """Stdout of the calibration. No extrapolation to the FWE quantile is written here."""
    observed = payload["observed"]
    equivalence = payload["mdd_vectorised"]
    lines = [
        f"calibration {payload['pair']} depuis {payload['source']}",
        f"    MDD vectorisé: verified={equivalence['verified']} "
        f"résidu relatif max {equivalence['max_relative_residual']:.3e} sur "
        f"{equivalence['n_series']} séries "
        f"(Decimal {equivalence['time_decimal_sec']:.3f} s, numpy "
        f"{equivalence['time_numpy_sec']:.3f} s, x{equivalence['speedup']:.0f})",
        f"    observé: CAGR {observed['cagr_pct']:.4f} %/an · σ_daily "
        f"{observed['sigma_daily']:.6f} · nnz {observed['nnz']} · "
        f"λ_dd {observed['lambda_dd']} · λ_σ {observed['lambda_sigma']}",
        f"    Δ_dd {observed['delta_dd']:.4f} pp/an · Δ_σ {observed['delta_sigma']:.4f} pp/an",
    ]
    for label, values in payload["se_delta_single_config"].items():
        lines.append(
            f"    SE mono-config L={label}: dd {values['dd']:.4f} · sigma {values['sigma']:.4f}"
        )
    lines.append(
        f"    coût de ré-estimation (s): {payload['reestimation_cost_sec']} "
        f"vs budget {payload['reestimation_budget_sec']} — λ prévu: "
        f"{payload['lambda_mode_planned']}"
    )
    return lines


def _relpath(path: Path) -> str:
    path = Path(path)
    try:
        return path.resolve().relative_to(rc.PROJECT_ROOT).as_posix()
    except ValueError:
        return path.as_posix()


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _block_lengths(text: str) -> list[int]:
    try:
        values = [int(part) for part in text.split(",") if part.strip()]
    except ValueError as exc:
        raise argparse.ArgumentTypeError(f"block lengths: {exc}") from exc
    if not values or any(value <= 0 for value in values):
        raise argparse.ArgumentTypeError("block lengths must be positive integers")
    return values


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--calibrate", action="store_true", help="write calibration.json (§ F.5)")
    parser.add_argument("--campaign", type=Path, default=DEFAULT_CAMPAIGN)
    parser.add_argument("--benchmark", type=Path, default=DEFAULT_BENCHMARK)
    parser.add_argument("--coverage", type=Path, default=DEFAULT_COVERAGE)
    parser.add_argument("--validation", type=Path, default=DEFAULT_VALIDATION)
    parser.add_argument(
        "--calibration",
        type=Path,
        default=DEFAULT_CALIBRATION,
        help="read only: its verified vectorised MDD gates the re-estimated λ",
    )
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE, help="--calibrate input")
    parser.add_argument("--pair", default=rc.PAIRS[0], help="--calibrate pair (frozen: BTC/USDC)")
    parser.add_argument("--output", type=Path, default=None)
    parser.add_argument("--markdown", type=Path, default=None)
    parser.add_argument(
        "--bootstrap-b",
        type=int,
        default=rc.BOOTSTRAP_B,
        help=f"replications (frozen: {rc.BOOTSTRAP_B}; an override is recorded in the artefact)",
    )
    parser.add_argument(
        "--block-lengths",
        type=_block_lengths,
        default=list(rc.BLOCK_LENGTHS),
        help=f"comma separated (frozen: {','.join(str(v) for v in rc.BLOCK_LENGTHS)})",
    )
    parser.add_argument("--chunk-size", type=int, default=DEFAULT_CHUNK)
    parser.add_argument(
        "--reestimation-budget-sec", type=float, default=rc.LAMBDA_REESTIMATION_BUDGET_SEC
    )
    parser.add_argument(
        "--no-reestimate",
        dest="reestimate",
        action="store_false",
        help="declared fallback: λ frozen, 'analyse de sensibilité, sans garantie de couverture'",
    )
    parser.add_argument("--now", default=None, help="ISO UTC stamp written as generated_at")
    return parser


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
    if args.bootstrap_b < 2:
        print("--bootstrap-b: at least 2 replications are needed", file=sys.stderr)
        return 2
    if args.chunk_size < 1:
        print("--chunk-size: must be positive", file=sys.stderr)
        return 2
    if args.output is None:
        args.output = DEFAULT_CALIBRATION if args.calibrate else DEFAULT_EFFECT
    try:
        return run_calibration(args, now) if args.calibrate else run_effect(args, now)
    except SystemExit as exc:
        print(str(exc), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
