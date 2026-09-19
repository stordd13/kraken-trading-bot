"""P7 — selection criteria, walk-forward aggregation, and report generation.

This module consumes the JSON outputs of phase 1 and phase 2 (produced by
``scripts/run_p7_grid_search.py``) and produces:

- ``results/P7_final_selection.json``: machine-readable summary of which
  configurations passed the selection criteria, and which were abandoned.
- ``results/P7_optimization_report.md``: human-readable synthesis with
  top-5 tables per combo, the final paper-trading shortlist, and the
  P6 → P7 delta.

The 7 selection criteria (all must pass) are applied on the walk-forward
aggregates per (strategy, pair, params_hash):

    1. mean_sharpe_oos > 0.4
    2. mean_profit_factor_oos > 1.3
    3. max_drawdown_global < 30%
    4. mean_trades_test >= 20 (relaxed for DCA: >= 5)
    5. consistency >= 5/8 windows with Sharpe > 0
    6. mean_sharpe_oos / mean_sharpe_train > 0.5 (anti-overfit)
    7. mean_sharpe_oos > buy_and_hold_sharpe OR > dca_fixed_sharpe

Benchmarks come from the P6 v2 report (or, B4.3, from ``--benchmarks``).

C1 (metrics_version 2, chantier 1 post-audit B4): the aggregation is None-aware — a metric a
window does not define (Sharpe with no daily variance, profit factor 0/0) stays undefined and
is never coerced to 0; means are taken over the windows that define the metric (``n_*``
reported); criterion 2 is evaluated on the **summed** net gains / losses over the windows
(``profit_factor_oos`` = Σ gains / Σ losses: finite, infinite without any loss -> passes, 0/0
-> undefined -> fails); an undefined metric fails its criterion with an explicit note.
Entries without the sums (pre-C1 files, e.g. the B4 campaign) take the **legacy v1 path**
(``_safe_float`` coercion, mean of per-window profit factors, v1 criterion names): their
verdicts are reproduced bit-identically (tests/test_scripts/test_p7_report.py). Mixing the two
contracts in one report is refused.

B4.3 — GO P7 rule 1 (Bruno, 2026-09-15): a configuration with at least one flagged run
(``scripts/b4_flags.py``: grid liquidation not reconciled — inventory divergence, residual,
or ``net_pnl != net_pnl_lot_basis``) in phase 1 or in any phase-2 window is **ineligible for
the paper selection whatever its score**. The 7 criteria are unchanged: the gate is applied
before the selection, the config is listed under ``ineligible_flagged`` and never under
``selected_for_paper``.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import UTC, datetime
import json
import math
from pathlib import Path
import sys
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from b4_flags import collect_flags, render_flags_markdown  # noqa: E402

from krakenbot.backtest_metrics import (  # noqa: E402
    METRICS_VERSION,
    MetricsVersionError,
    entry_metrics_version,
    fmt,
    mean_available,
    profit_factor_from_sums,
)
from krakenbot.replay_contract import require_replay_version  # noqa: E402

# ---------------------------------------------------------------------------
# Benchmarks (Sharpe ratios from P6_backtest_report_v2.md, period
# 2023-04-01 → 2026-04-01, Binance fees, 1k USDC capital)
#
# C1: **legacy v1 constants** — the DCA figures are contaminated by construction (defect D6:
# coins-only equity, deposits counted as returns) and the Sharpes are per-engine-step values.
# They only apply to pre-C1 (v1) result files; a metrics_version 2 report REQUIRES a v2
# ``--benchmarks`` file computed by scripts/compute_benchmarks.py through the shared module.
# ---------------------------------------------------------------------------

BENCHMARK_SHARPE: dict[str, dict[str, float | None]] = {
    "BTC/USDC": {"buy_and_hold": 0.85, "dca_fixed": 2.37},
    "ETH/USDC": {"buy_and_hold": 0.40, "dca_fixed": 2.10},
    "SOL/USDC": {"buy_and_hold": 0.31, "dca_fixed": 1.93},
}

# Strategies for which the min-trades criterion is relaxed (low-frequency by design)
LOW_FREQUENCY_STRATEGIES: set[str] = {"grok_adaptive_dca_weekly"}

MIN_TRADES_DEFAULT = 20
MIN_TRADES_DCA = 5
MIN_SHARPE_OOS = 0.4
MIN_PF_OOS = 1.3
MAX_DRAWDOWN_PCT = 30.0
MIN_CONSISTENCY = 5  # out of 8 windows
MIN_OVERFIT_RATIO = 0.5


# ---------------------------------------------------------------------------
# Aggregation
# ---------------------------------------------------------------------------


@dataclass
class WalkForwardAggregate:
    """Summary of one (strategy, pair, params) across all walk-forward windows.

    C1 (metrics_version 2): ``mean_sharpe_*`` / ``mean_pf_oos`` are None when no window defines
    the metric (``n_*`` = windows that do); ``profit_factor_oos`` is the ratio of the summed net
    gains / losses over the windows (finite, ``inf`` without any loss, None for 0/0).
    ``legacy`` marks a v1 aggregate (entries without the sums): the pre-C1 behaviour is kept
    bit-identically for the B4 files (missing values coerced to 0, mean of per-window PFs).
    """

    strategy: str
    pair: str
    params: dict[str, Any]
    params_hash: str
    n_windows: int
    mean_sharpe_train: float | None
    mean_sharpe_oos: float | None
    std_sharpe_oos: float
    mean_pf_oos: float | None
    mean_trades_test: float
    max_drawdown_global: float
    consistency: int  # number of windows where test Sharpe is defined and > 0
    per_window: list[dict[str, Any]] = field(default_factory=list)
    legacy: bool = False
    n_sharpe_train: int = 0
    n_sharpe_oos: int = 0
    n_pf_oos: int = 0
    gross_profit_net_oos: float | None = None
    gross_loss_net_oos: float | None = None
    pf_excluded_trades_oos: int = 0  # v2: lots at unknown cost excluded from the sums (incomplete)

    @property
    def profit_factor_oos(self) -> float | None:
        """v2: Σ gross_profit_net / Σ gross_loss_net over the windows (``inf`` without a loss,
        None for 0/0); legacy: the v1 mean of the per-window profit factors."""
        if self.legacy:
            return self.mean_pf_oos
        return profit_factor_from_sums(self.gross_profit_net_oos, self.gross_loss_net_oos)

    def to_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {
            "strategy": self.strategy,
            "pair": self.pair,
            "params": self.params,
            "params_hash": self.params_hash,
            "n_windows": self.n_windows,
            "mean_sharpe_train": self.mean_sharpe_train,
            "mean_sharpe_oos": self.mean_sharpe_oos,
            "std_sharpe_oos": self.std_sharpe_oos,
            "mean_pf_oos": self.mean_pf_oos,
            "mean_trades_test": self.mean_trades_test,
            "max_drawdown_global": self.max_drawdown_global,
            "consistency": self.consistency,
            "per_window": self.per_window,
        }
        if not self.legacy:
            out.update(_pf_fields(self))
            out["n_sharpe_train"] = self.n_sharpe_train
        return out


def _safe_float(v: Any, default: float = 0.0) -> float:
    """Coerce to float, treating None / NaN / inf / errors as ``default``.

    Legacy v1 behaviour (pre-C1 files only): the coercion of an undefined value to 0 is the
    defect D4 of the B4 audit; the v2 path uses ``_metric`` / ``mean_available`` instead.
    """
    if v is None:
        return default
    try:
        fv = float(v)
    except (TypeError, ValueError):
        return default
    if math.isnan(fv) or math.isinf(fv):
        return default
    return fv


def _metric(block: dict[str, Any] | None, key: str) -> float | None:
    """v2 reader: the metric as float, None when absent / null / NaN / infinite."""
    v = (block or {}).get(key)
    if v is None:
        return None
    try:
        fv = float(v)
    except (TypeError, ValueError):
        return None
    if math.isnan(fv) or math.isinf(fv):
        return None
    return fv


def _has_sums(block: dict[str, Any] | None) -> bool:
    return bool(block) and "gross_profit_net" in block and "gross_loss_net" in block  # type: ignore[operator]


def _rank(value: float | None) -> float:
    """Sort key: an undefined Sharpe ranks last."""
    return value if value is not None else float("-inf")


def _json_ratio(value: float | None) -> float | None:
    """JSON-safe ratio: an infinite profit factor is stored as null (the sums disambiguate)."""
    return None if value is None or math.isinf(value) else value


def _pf_fields(agg: WalkForwardAggregate) -> dict[str, Any]:
    """Profit-factor fields of a selection row: v1 key for legacy aggregates, the summed
    contract (ratio, sums, counts) for v2 ones."""
    if agg.legacy:
        return {"mean_profit_factor": agg.mean_pf_oos}
    return {
        "profit_factor_oos": _json_ratio(agg.profit_factor_oos),
        "gross_profit_net_oos": agg.gross_profit_net_oos,
        "gross_loss_net_oos": agg.gross_loss_net_oos,
        "pf_excluded_trades_oos": agg.pf_excluded_trades_oos,
        "mean_pf_oos_diagnostic": agg.mean_pf_oos,
        "n_pf_oos": agg.n_pf_oos,
        "n_sharpe_oos": agg.n_sharpe_oos,
    }


def _pf_text(row: dict[str, Any]) -> str:
    """Display of a selection row's profit factor: ratio, ∞ (sums without a loss) or n/a."""
    if "gross_profit_net_oos" in row:
        text = fmt(
            profit_factor_from_sums(row.get("gross_profit_net_oos"), row.get("gross_loss_net_oos"))
        )
        excluded = row.get("pf_excluded_trades_oos") or 0
        return f"{text} (incomplete: {excluded} excluded)" if excluded else text
    return fmt(row.get("mean_profit_factor"))


def _fmt_raw(value: Any, digits: int = 2) -> str:
    """Display of a raw metric value of a results entry (None -> n/a, inf -> ∞)."""
    if value is None:
        return "n/a"
    try:
        return fmt(float(value), digits)
    except (TypeError, ValueError):
        return "n/a"


def _mean(values: list[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def _stdev(values: list[float]) -> float:
    if len(values) < 2:
        return 0.0
    m = _mean(values)
    var = sum((v - m) ** 2 for v in values) / (len(values) - 1)
    return math.sqrt(var)


def aggregate_walk_forward(
    phase2_results: dict[str, Any],
) -> dict[tuple[str, str, str], WalkForwardAggregate]:
    """Group phase-2 windowed results by (strategy, pair, params_hash).

    Skips entries with an ``error`` key (failed jobs). A combo whose test windows all carry the
    C1 sums (``gross_profit_net`` / ``gross_loss_net``) is aggregated None-aware on the summed
    profit factor; otherwise the legacy v1 aggregation is applied unchanged.
    """
    # Group windows first
    grouped: dict[tuple[str, str, str], list[dict[str, Any]]] = defaultdict(list)
    params_by_combo: dict[tuple[str, str, str], dict[str, Any]] = {}
    for key, entry in phase2_results.items():
        if "error" in entry:
            continue
        strategy = entry.get("strategy")
        pair = entry.get("pair")
        params = entry.get("params") or {}
        if strategy is None or pair is None:
            continue
        # Derive params_hash from the key (last segment before _w<idx>)
        # Key format: "<strat>_<pair>_p2_<hash>_w<idx>"
        params_hash = _extract_params_hash(key)
        combo = (strategy, pair, params_hash)
        grouped[combo].append(entry)
        params_by_combo.setdefault(combo, params)

    out: dict[tuple[str, str, str], WalkForwardAggregate] = {}
    for combo, windows in grouped.items():
        strategy, pair, params_hash = combo
        per_window = sorted(
            [
                {
                    "window_idx": w.get("window_idx"),
                    "train_start": w.get("period", {}).get("train_start"),
                    "train_end": w.get("period", {}).get("train_end"),
                    "test_start": w.get("period", {}).get("test_start"),
                    "test_end": w.get("period", {}).get("test_end"),
                    "train_metrics": w.get("train", {}),
                    "test_metrics": w.get("test", {}),
                    "effective_params": w.get("effective_params"),
                    "liquidation": w.get("liquidation"),
                }
                for w in windows
            ],
            key=lambda d: d.get("window_idx") or 0,
        )
        legacy = not all(_has_sums(w.get("test")) for w in windows)
        if legacy:
            train_sharpes = [_safe_float(w.get("train", {}).get("sharpe_ratio")) for w in windows]
            test_sharpes = [_safe_float(w.get("test", {}).get("sharpe_ratio")) for w in windows]
            test_pfs = [_safe_float(w.get("test", {}).get("profit_factor")) for w in windows]
            test_trades = [_safe_float(w.get("test", {}).get("total_trades")) for w in windows]
            # max_drawdown_pct is reported as a positive number (5.4 = -5.4% drawdown)
            test_dds = [_safe_float(w.get("test", {}).get("max_drawdown_pct")) for w in windows]
            out[combo] = WalkForwardAggregate(
                strategy=strategy,
                pair=pair,
                params=params_by_combo[combo],
                params_hash=params_hash,
                n_windows=len(windows),
                mean_sharpe_train=_mean(train_sharpes),
                mean_sharpe_oos=_mean(test_sharpes),
                std_sharpe_oos=_stdev(test_sharpes),
                mean_pf_oos=_mean(test_pfs),
                mean_trades_test=_mean(test_trades),
                max_drawdown_global=max(test_dds) if test_dds else 0.0,
                consistency=sum(1 for s in test_sharpes if s > 0),
                per_window=per_window,
                legacy=True,
            )
            continue
        train_sharpes_v2 = [_metric(w.get("train"), "sharpe_ratio") for w in windows]
        test_sharpes_v2 = [_metric(w.get("test"), "sharpe_ratio") for w in windows]
        mean_train, n_train = mean_available(train_sharpes_v2)
        mean_oos, n_oos = mean_available(test_sharpes_v2)
        defined_oos = [x for x in test_sharpes_v2 if x is not None]
        mean_pf, n_pf = mean_available([_metric(w.get("test"), "profit_factor") for w in windows])
        gross_profit = sum(float(w["test"]["gross_profit_net"]) for w in windows)
        gross_loss = sum(float(w["test"]["gross_loss_net"]) for w in windows)
        excluded = sum(int(w["test"].get("pf_excluded_trades") or 0) for w in windows)
        test_dds_v2 = [_metric(w.get("test"), "max_drawdown_pct_daily") for w in windows]
        defined_dds = [x for x in test_dds_v2 if x is not None]
        out[combo] = WalkForwardAggregate(
            strategy=strategy,
            pair=pair,
            params=params_by_combo[combo],
            params_hash=params_hash,
            n_windows=len(windows),
            mean_sharpe_train=mean_train,
            mean_sharpe_oos=mean_oos,
            std_sharpe_oos=_stdev(defined_oos),
            mean_pf_oos=mean_pf,
            mean_trades_test=_mean(
                [_safe_float(w.get("test", {}).get("total_trades")) for w in windows]
            ),
            max_drawdown_global=max(defined_dds) if defined_dds else 0.0,
            consistency=sum(1 for x in test_sharpes_v2 if x is not None and x > 0),
            per_window=per_window,
            legacy=False,
            n_sharpe_train=n_train,
            n_sharpe_oos=n_oos,
            n_pf_oos=n_pf,
            gross_profit_net_oos=gross_profit,
            gross_loss_net_oos=gross_loss,
            pf_excluded_trades_oos=excluded,
        )
    return out


def _extract_params_hash(key: str) -> str:
    """Extract the 8-char params_hash from a phase-2 key.

    Key format: ``<strategy>_<pair_norm>_p2_<hash>_w<idx>``.
    """
    # Split on "_p2_" then take the 8 chars after it
    if "_p2_" in key:
        tail = key.split("_p2_", 1)[1]
        # tail = "<hash>_w<idx>"
        return tail.split("_w", 1)[0]
    if "_p1_" in key:
        tail = key.split("_p1_", 1)[1]
        return tail.split("_w", 1)[0] if "_w" in tail else tail
    return "unknown"


# ---------------------------------------------------------------------------
# Selection criteria
# ---------------------------------------------------------------------------


@dataclass
class CriterionResult:
    name: str
    passed: bool
    actual: float | None  # None = undefined metric (C1): the criterion fails with a note
    threshold: float
    note: str = ""


@dataclass
class ConfigVerdict:
    """Final per-config selection verdict."""

    aggregate: WalkForwardAggregate
    criteria: list[CriterionResult]
    benchmark_sharpe: dict[str, float | None]
    beats_benchmark: str | None  # "buy_and_hold" | "dca_fixed" | None

    @property
    def passed(self) -> bool:
        return all(c.passed for c in self.criteria)

    def failure_reasons(self) -> list[str]:
        return [
            f"{c.name} (actual={fmt(c.actual, 3)}, threshold={c.threshold:.3f})"
            for c in self.criteria
            if not c.passed
        ]

    def to_dict(self) -> dict[str, Any]:
        return {
            "strategy": self.aggregate.strategy,
            "pair": self.aggregate.pair,
            "params": self.aggregate.params,
            "params_hash": self.aggregate.params_hash,
            "passed": self.passed,
            "mean_sharpe_oos": self.aggregate.mean_sharpe_oos,
            **_pf_fields(self.aggregate),
            "max_drawdown_global": self.aggregate.max_drawdown_global,
            "consistency": self.aggregate.consistency,
            "mean_sharpe_train": self.aggregate.mean_sharpe_train,
            "mean_trades_test": self.aggregate.mean_trades_test,
            "benchmark_sharpe": self.benchmark_sharpe,
            "beats_benchmark": self.beats_benchmark,
            "criteria": [
                {
                    "name": c.name,
                    "passed": c.passed,
                    "actual": c.actual,
                    "threshold": c.threshold,
                    "note": c.note,
                }
                for c in self.criteria
            ],
            "failure_reasons": self.failure_reasons(),
        }


def apply_selection_criteria(
    aggregate: WalkForwardAggregate,
    benchmarks: dict[str, dict[str, float | None]] = BENCHMARK_SHARPE,
) -> ConfigVerdict:
    """Apply the 7 selection criteria to a single walk-forward aggregate.

    Legacy (v1) aggregates take the pre-C1 path unchanged; v2 aggregates are None-aware
    (an undefined metric fails its criterion) and evaluate criterion 2 on the summed profit
    factor. Thresholds are the same on both paths.
    """
    if aggregate.legacy:
        return _apply_selection_criteria_v1(aggregate, benchmarks)
    a = aggregate
    bench = benchmarks.get(a.pair, {})
    bh = bench.get("buy_and_hold")
    dca = bench.get("dca_fixed")
    oos = a.mean_sharpe_oos

    min_trades_threshold = (
        MIN_TRADES_DCA if a.strategy in LOW_FREQUENCY_STRATEGIES else MIN_TRADES_DEFAULT
    )

    # Criterion 2: the summed profit factor (Σ net gains / Σ net losses over the windows)
    pf = a.profit_factor_oos
    if pf is None:
        pf_passed, pf_actual, pf_note = False, None, "undefined (0/0: no net gain nor loss)"
    elif math.isinf(pf):
        pf_passed, pf_actual, pf_note = True, 999.0, "∞: no net loss over the windows"
    else:
        pf_passed, pf_actual, pf_note = pf > MIN_PF_OOS, pf, ""
    if a.pf_excluded_trades_oos:
        pf_note = (pf_note + "; " if pf_note else "") + (
            f"incomplete: {a.pf_excluded_trades_oos} lot(s) at unknown cost excluded from the sums"
        )

    # Criterion 6: anti-overfit ratio, undefined when either Sharpe is undefined
    overfit_ratio: float | None
    if oos is None or a.mean_sharpe_train is None:
        overfit_ratio = None
    elif a.mean_sharpe_train > 0:
        overfit_ratio = oos / a.mean_sharpe_train
    else:
        overfit_ratio = float("inf") if oos > 0 else 0.0

    # Criterion 7: an undefined leg (or an undefined OOS Sharpe) cannot be beaten
    beats_bh = oos is not None and bh is not None and oos > bh
    beats_dca = oos is not None and dca is not None and oos > dca
    beats_benchmark: str | None
    if beats_bh and beats_dca:
        beats_benchmark = "both"
    elif beats_bh:
        beats_benchmark = "buy_and_hold"
    elif beats_dca:
        beats_benchmark = "dca_fixed"
    else:
        beats_benchmark = None
    legs = [x for x in (bh, dca) if x is not None]
    bench_threshold = min(legs) if legs else 0.0
    bench_note = f"Buy&Hold={fmt(bh)}, DCA={fmt(dca)}"
    if not legs:
        bench_note += " (no benchmark available)"
    elif oos is None:
        bench_note += " (OOS Sharpe undefined)"

    criteria = [
        CriterionResult(
            name="mean_sharpe_oos > 0.4",
            passed=oos is not None and oos > MIN_SHARPE_OOS,
            actual=oos,
            threshold=MIN_SHARPE_OOS,
            note="" if oos is not None else "undefined (no window with a defined Sharpe)",
        ),
        CriterionResult(
            name="profit_factor_oos > 1.3",
            passed=pf_passed,
            actual=pf_actual,
            threshold=MIN_PF_OOS,
            note=pf_note,
        ),
        CriterionResult(
            name="max_drawdown_global < 30%",
            passed=a.max_drawdown_global < MAX_DRAWDOWN_PCT,
            actual=a.max_drawdown_global,
            threshold=MAX_DRAWDOWN_PCT,
        ),
        CriterionResult(
            name=f"mean_trades_test >= {min_trades_threshold}",
            passed=a.mean_trades_test >= min_trades_threshold,
            actual=a.mean_trades_test,
            threshold=float(min_trades_threshold),
            note="relaxed for low-freq strategy" if a.strategy in LOW_FREQUENCY_STRATEGIES else "",
        ),
        CriterionResult(
            name="consistency >= 5/8 windows",
            passed=a.consistency >= MIN_CONSISTENCY,
            actual=float(a.consistency),
            threshold=float(MIN_CONSISTENCY),
        ),
        CriterionResult(
            name="mean_sharpe_oos / mean_sharpe_train > 0.5 (anti-overfit)",
            passed=overfit_ratio is not None and overfit_ratio > MIN_OVERFIT_RATIO,
            actual=(
                None
                if overfit_ratio is None
                else (overfit_ratio if math.isfinite(overfit_ratio) else 999.0)
            ),
            threshold=MIN_OVERFIT_RATIO,
            note="" if overfit_ratio is not None else "undefined (a Sharpe is undefined)",
        ),
        CriterionResult(
            name="beats Buy&Hold OR DCA fixed",
            passed=beats_benchmark is not None,
            actual=oos,
            threshold=bench_threshold,
            note=bench_note,
        ),
    ]

    return ConfigVerdict(
        aggregate=a,
        criteria=criteria,
        benchmark_sharpe={"buy_and_hold": bh, "dca_fixed": dca},
        beats_benchmark=beats_benchmark,
    )


def _apply_selection_criteria_v1(
    a: WalkForwardAggregate,
    benchmarks: dict[str, dict[str, float | None]],
) -> ConfigVerdict:
    """Pre-C1 criteria, verbatim (legacy v1 aggregates only: B4 files)."""
    bench = benchmarks.get(a.pair, {})
    bh = bench.get("buy_and_hold", 0.0) or 0.0
    dca = bench.get("dca_fixed", 0.0) or 0.0
    assert a.mean_sharpe_oos is not None and a.mean_sharpe_train is not None
    assert a.mean_pf_oos is not None

    # Criterion 4: relaxed for low-frequency strategies (DCA)
    min_trades_threshold = (
        MIN_TRADES_DCA if a.strategy in LOW_FREQUENCY_STRATEGIES else MIN_TRADES_DEFAULT
    )

    # Criterion 6: anti-overfit ratio. If train Sharpe is non-positive, ratio
    # is undefined; treat as fail. Otherwise compare ratio.
    if a.mean_sharpe_train > 0:
        overfit_ratio = a.mean_sharpe_oos / a.mean_sharpe_train
    else:
        # If train was non-positive but OOS is positive, treat as passing the
        # overfit check (the model didn't memorize training noise to fail OOS).
        overfit_ratio = float("inf") if a.mean_sharpe_oos > 0 else 0.0

    # Criterion 7: benchmark — beat at least one (the OR makes this a permissive bar)
    beats_bh = a.mean_sharpe_oos > bh
    beats_dca = a.mean_sharpe_oos > dca
    beats_benchmark: str | None
    if beats_bh and beats_dca:
        beats_benchmark = "both"
    elif beats_bh:
        beats_benchmark = "buy_and_hold"
    elif beats_dca:
        beats_benchmark = "dca_fixed"
    else:
        beats_benchmark = None

    criteria = [
        CriterionResult(
            name="mean_sharpe_oos > 0.4",
            passed=a.mean_sharpe_oos > MIN_SHARPE_OOS,
            actual=a.mean_sharpe_oos,
            threshold=MIN_SHARPE_OOS,
        ),
        CriterionResult(
            name="mean_profit_factor_oos > 1.3",
            passed=a.mean_pf_oos > MIN_PF_OOS,
            actual=a.mean_pf_oos,
            threshold=MIN_PF_OOS,
        ),
        CriterionResult(
            name="max_drawdown_global < 30%",
            passed=a.max_drawdown_global < MAX_DRAWDOWN_PCT,
            actual=a.max_drawdown_global,
            threshold=MAX_DRAWDOWN_PCT,
        ),
        CriterionResult(
            name=f"mean_trades_test >= {min_trades_threshold}",
            passed=a.mean_trades_test >= min_trades_threshold,
            actual=a.mean_trades_test,
            threshold=float(min_trades_threshold),
            note="relaxed for low-freq strategy" if a.strategy in LOW_FREQUENCY_STRATEGIES else "",
        ),
        CriterionResult(
            name="consistency >= 5/8 windows",
            passed=a.consistency >= MIN_CONSISTENCY,
            actual=float(a.consistency),
            threshold=float(MIN_CONSISTENCY),
        ),
        CriterionResult(
            name="mean_sharpe_oos / mean_sharpe_train > 0.5 (anti-overfit)",
            passed=overfit_ratio > MIN_OVERFIT_RATIO,
            actual=overfit_ratio if math.isfinite(overfit_ratio) else 999.0,
            threshold=MIN_OVERFIT_RATIO,
        ),
        CriterionResult(
            name="beats Buy&Hold OR DCA fixed",
            passed=beats_benchmark is not None,
            actual=a.mean_sharpe_oos,
            threshold=min(bh, dca) if bh and dca else max(bh, dca),
            note=f"Buy&Hold={bh}, DCA={dca}",
        ),
    ]

    return ConfigVerdict(
        aggregate=a,
        criteria=criteria,
        benchmark_sharpe={"buy_and_hold": bh, "dca_fixed": dca},
        beats_benchmark=beats_benchmark,
    )


def ineligible_configs(
    flags: list[dict[str, Any]],
) -> dict[tuple[str, str, str], list[dict[str, Any]]]:
    """GO P7 rule 1: ``{(strategy, pair, params_hash): [flags…]}`` for every flagged run.

    The params hash is read from the run key (phase 1 ``…_p1_<hash>``, phase 2
    ``…_p2_<hash>_w<idx>``), so a flag on the phase-1 run or on any walk-forward window of a
    configuration makes that configuration ineligible.
    """
    out: dict[tuple[str, str, str], list[dict[str, Any]]] = defaultdict(list)
    for f in flags:
        strategy, pair = f.get("strategy"), f.get("pair")
        if strategy is None or pair is None:
            continue
        out[(strategy, pair, _extract_params_hash(str(f.get("run", ""))))].append(f)
    return dict(out)


def _min_trades_per_window(agg: WalkForwardAggregate) -> int:
    if not agg.per_window:
        return 0
    return min(int(_safe_float(w["test_metrics"].get("total_trades"))) for w in agg.per_window)


def build_selection(
    aggregates: dict[tuple[str, str, str], WalkForwardAggregate],
    benchmarks: dict[str, dict[str, float | None]] = BENCHMARK_SHARPE,
    ineligible: dict[tuple[str, str, str], list[dict[str, Any]]] | None = None,
) -> dict[str, Any]:
    """Apply selection criteria to every aggregate, return the final selection dict.

    ``ineligible`` (GO P7 rule 1) maps ``(strategy, pair, params_hash)`` to the flags of that
    configuration: such a config is never selected, whatever its score, and is listed under
    ``ineligible_flagged`` with its verdict on the 7 (unchanged) criteria.
    """
    ineligible = ineligible or {}
    verdicts: list[ConfigVerdict] = [
        apply_selection_criteria(agg, benchmarks) for agg in aggregates.values()
    ]

    def _key(v: ConfigVerdict) -> tuple[str, str, str]:
        return (v.aggregate.strategy, v.aggregate.pair, v.aggregate.params_hash)

    # Group by (strategy, pair). For each, keep the best PASSING and ELIGIBLE config (by
    # mean_sharpe_oos). If none passes, the combo is abandoned with the best
    # failing config's reasons as the rationale.
    by_combo: dict[tuple[str, str], list[ConfigVerdict]] = defaultdict(list)
    for v in verdicts:
        by_combo[(v.aggregate.strategy, v.aggregate.pair)].append(v)

    selected: list[dict[str, Any]] = []
    abandoned: list[dict[str, Any]] = []
    ineligible_flagged: list[dict[str, Any]] = []

    for (strategy, pair), combo_verdicts in by_combo.items():
        flagged = [v for v in combo_verdicts if _key(v) in ineligible]
        eligible = [v for v in combo_verdicts if _key(v) not in ineligible]
        for v in sorted(flagged, key=lambda v: _rank(v.aggregate.mean_sharpe_oos), reverse=True):
            runs = ineligible[_key(v)]
            ineligible_flagged.append(
                {
                    "strategy": strategy,
                    "pair": pair,
                    "params": v.aggregate.params,
                    "params_hash": v.aggregate.params_hash,
                    "mean_sharpe_oos": v.aggregate.mean_sharpe_oos,
                    **_pf_fields(v.aggregate),
                    "consistency": v.aggregate.consistency,
                    "max_drawdown_global": v.aggregate.max_drawdown_global,
                    "mean_trades_test": v.aggregate.mean_trades_test,
                    "passed_criteria": v.passed,
                    "n_flags": len(runs),
                    "flagged_runs": [f"{f['run']}/{f['segment']}" for f in runs],
                    "reason": (
                        f"{len(runs)} flagged run(s) (grid liquidation not reconciled) — "
                        "ineligible for paper whatever the score (GO P7 rule 1); "
                        f"7 criteria: {'passed' if v.passed else 'failed'}."
                    ),
                }
            )
        passing = [v for v in eligible if v.passed]
        if passing:
            # Best by mean_sharpe_oos (an undefined Sharpe ranks last)
            best = max(passing, key=lambda v: _rank(v.aggregate.mean_sharpe_oos))
            # B4.3 (GO GATE B, B.2a): the runtime-captured effective parameters of the
            # selected config — the machine-readable source for the B5 strategies.yaml.
            effective = next(
                (
                    w.get("effective_params")
                    for w in best.aggregate.per_window
                    if w.get("effective_params")
                ),
                None,
            )
            selected.append(
                {
                    "strategy": strategy,
                    "pair": pair,
                    "params": best.aggregate.params,
                    "params_hash": best.aggregate.params_hash,
                    "effective_params": effective,
                    "mean_sharpe_oos": best.aggregate.mean_sharpe_oos,
                    "std_sharpe_oos": best.aggregate.std_sharpe_oos,
                    **_pf_fields(best.aggregate),
                    "consistency": best.aggregate.consistency,
                    "max_drawdown_global": best.aggregate.max_drawdown_global,
                    "mean_trades_test": best.aggregate.mean_trades_test,
                    "min_trades_window": _min_trades_per_window(best.aggregate),
                    "beats_benchmark": best.beats_benchmark,
                    "rationale": (
                        f"Best of {len(passing)} passing config(s). "
                        f"Sharpe_oos={fmt(best.aggregate.mean_sharpe_oos)}, "
                        f"PF={fmt(best.aggregate.profit_factor_oos)}, "
                        f"consistency={best.aggregate.consistency}/8, "
                        f"std_oos={best.aggregate.std_sharpe_oos:.2f}, "
                        f"trades/window mean={best.aggregate.mean_trades_test:.0f} "
                        f"min={_min_trades_per_window(best.aggregate)}."
                    ),
                }
            )
        else:
            flagged_passing = [v for v in flagged if v.passed]
            if eligible:
                # Best eligible failing config (by sharpe) → its failure reasons
                best_fail = max(eligible, key=lambda v: _rank(v.aggregate.mean_sharpe_oos))
                reason = (
                    f"No eligible configuration passed all 7 criteria. "
                    f"Best eligible config failed on: {', '.join(best_fail.failure_reasons())}."
                )
            else:
                best_fail = max(combo_verdicts, key=lambda v: _rank(v.aggregate.mean_sharpe_oos))
                reason = (
                    f"All {len(combo_verdicts)} configuration(s) are flagged "
                    "(ineligible for paper, GO P7 rule 1)."
                )
            if flagged_passing:
                reason += (
                    f" {len(flagged_passing)} config(s) passing the 7 criteria are flagged "
                    "and ineligible (GO P7 rule 1)."
                )
            abandoned.append(
                {
                    "strategy": strategy,
                    "pair": pair,
                    "best_sharpe_oos": best_fail.aggregate.mean_sharpe_oos,
                    "best_params": best_fail.aggregate.params,
                    "best_mean_trades_test": best_fail.aggregate.mean_trades_test,
                    "n_ineligible": len(flagged),
                    "reason": reason,
                }
            )

    return {
        "selected_for_paper": selected,
        "abandoned": abandoned,
        "ineligible_flagged": ineligible_flagged,
        "all_verdicts": [v.to_dict() for v in verdicts],
        "benchmarks": benchmarks,
        "generated_at": datetime.now(UTC).isoformat(),
    }


# ---------------------------------------------------------------------------
# Report generation
# ---------------------------------------------------------------------------


def _format_params_inline(params: dict[str, Any]) -> str:
    items = [f"{k}={v}" for k, v in sorted(params.items())]
    return ", ".join(items)


def generate_report(
    phase1_path: Path,
    phase2_path: Path,
    output_md_path: Path,
    selection_json_path: Path,
    benchmarks: dict[str, dict[str, float | None]] | None = None,
    benchmark_details: dict[str, dict[str, dict[str, float | None]]] | None = None,
) -> dict[str, Any]:
    """Produce the human report + machine selection JSON. Returns the selection dict.

    C1: the two inputs must share one metrics contract (mixed / partially pre-C1 files are
    refused with ``MetricsVersionError``); metrics_version 2 entries require ``benchmarks``
    computed under the same contract (the v1 constants are never applied to them).

    ``benchmarks`` (``{pair: {"buy_and_hold": sharpe, "dca_fixed": sharpe}}``) replaces the
    P6 Binance constants for criterion 7 (B4.3: computed under the campaign fee model).
    ``benchmark_details`` (``{pair: {"buy_and_hold" | "dca_fixed": {"sharpe", "return_pct",
    "max_drawdown_pct"}}}``) only feeds the report's benchmark table (GO P7 rule 2: Sharpe is
    compared with Buy & Hold, return / MaxDD with the fixed DCA).
    """
    phase1_data = (
        json.loads(phase1_path.read_text(encoding="utf-8")) if phase1_path.exists() else {}
    )
    phase2_data = (
        json.loads(phase2_path.read_text(encoding="utf-8")) if phase2_path.exists() else {}
    )

    versions = {
        entry_metrics_version(entry)
        for data in (phase1_data, phase2_data)
        for entry in data.values()
        if isinstance(entry, dict) and "error" not in entry
    }
    if len(versions) > 1:
        raise MetricsVersionError(
            f"mixed metrics contracts in the inputs ({sorted(str(v) for v in versions)}): "
            "metrics of two contracts cannot be aggregated (regenerate under one contract)"
        )
    legacy = versions != {METRICS_VERSION}
    if not legacy:
        # C2: a metrics_version 2 report must also be one replay contract (the v1 legacy
        # path — frozen B4 files, no version key at all — is deliberately untouched).
        for data, label in ((phase1_data, str(phase1_path)), (phase2_data, str(phase2_path))):
            require_replay_version(data, path=label)
    if not legacy and benchmarks is None:
        raise MetricsVersionError(
            f"metrics_version {METRICS_VERSION} results require --benchmarks (a benchmarks file "
            "computed by scripts/compute_benchmarks.py under the same contract); the v1 "
            "constants of p7_report.BENCHMARK_SHARPE only apply to pre-C1 files"
        )
    bench = benchmarks if benchmarks is not None else BENCHMARK_SHARPE
    aggregates = aggregate_walk_forward(phase2_data)
    # B4.3 flag rule: name every phase-1 / phase-2 run whose grid liquidation did not reconcile;
    # GO P7 rule 1: those configurations are ineligible for the selection, whatever their score.
    flagged_runs = collect_flags(phase1_data) + collect_flags(phase2_data)
    selection = build_selection(aggregates, bench, ineligible=ineligible_configs(flagged_runs))
    selection["flagged_runs"] = flagged_runs

    # Write machine-readable selection
    selection_json_path.parent.mkdir(parents=True, exist_ok=True)
    selection_json_path.write_text(json.dumps(selection, indent=2, default=str), encoding="utf-8")

    # Write markdown
    md = _render_markdown(
        phase1_data, phase2_data, aggregates, selection, bench, benchmark_details, legacy=legacy
    )
    output_md_path.parent.mkdir(parents=True, exist_ok=True)
    output_md_path.write_text(md, encoding="utf-8")

    return selection


DCA_SHARPE_NOTE = (
    "**Reading rule (GO P7, rule 2).** Compare a strategy's **Sharpe with Buy & Hold only**; "
    "compare it with the **fixed DCA on return and MaxDD**. The fixed-DCA Sharpe is **not "
    "comparable**: its equity curve is coins-only and starts at 0, so every weekly deposit is "
    "counted as a return (a Sharpe ≈ 2 next to a negative return is impossible for a real "
    "equity curve), its MaxDD of 100 % is an artefact of the same construction, and its buys "
    "ignore the per-pair costs. Likewise `grok_adaptive_dca_weekly` keeps most of its 1 000 USDC "
    "in cash, so its Sharpe is not comparable with a fully invested strategy: read it on return "
    "and MaxDD. Every metric is shown with the number of trades it rests on. Criterion 7 is "
    "unchanged (an OR; Buy & Hold is the binding leg)."
)


DCA_SHARPE_NOTE_V2 = (
    "**Reading rule (C1, metrics_version 2).** Every ratio is computed by the shared module "
    "(`krakenbot.backtest_metrics`): daily resampling, Sharpe / Sortino on daily returns (sample "
    "std), MaxDD relative to the running peak on the daily NAV, profit factor net of both legs "
    "aggregated on the summed gains / losses (∞ without any loss, n/a for 0/0). The fixed-DCA "
    "benchmark books its deposits as external flows: its Sharpe is now comparable and its MaxDD "
    "is no longer the 100 % artefact. An undefined metric (n/a) fails its criterion. Every "
    "metric is shown with the number of trades it rests on; the number of windows that define "
    "each mean (`n_sharpe_oos`, `n_pf_oos`) is in the selection JSON. Criterion 7 is unchanged "
    "(an OR; a missing benchmark leg cannot be beaten)."
)


def _render_markdown(
    phase1_data: dict[str, Any],
    phase2_data: dict[str, Any],
    aggregates: dict[tuple[str, str, str], WalkForwardAggregate],
    selection: dict[str, Any],
    benchmarks: dict[str, dict[str, float | None]] = BENCHMARK_SHARPE,
    benchmark_details: dict[str, dict[str, dict[str, float | None]]] | None = None,
    *,
    legacy: bool = True,
) -> str:
    """Compose the P7 optimization report markdown."""
    note = DCA_SHARPE_NOTE if legacy else DCA_SHARPE_NOTE_V2
    lines: list[str] = []
    lines.append("# P7 — Parameter Optimization Report")
    lines.append("")
    lines.append(f"Generated: {datetime.now(UTC).isoformat()}")
    lines.append("")
    lines.append("## Executive Summary")
    lines.append("")
    n_phase1 = sum(1 for v in phase1_data.values() if "error" not in v)
    n_phase2 = sum(1 for v in phase2_data.values() if "error" not in v)
    n_aggregates = len(aggregates)
    n_selected = len(selection["selected_for_paper"])
    n_abandoned = len(selection["abandoned"])
    n_ineligible = len(selection.get("ineligible_flagged", []))
    lines.append(f"- Phase 1 backtests (succeeded): **{n_phase1}**")
    lines.append(f"- Phase 2 walk-forward windows (succeeded): **{n_phase2}**")
    lines.append(f"- Aggregated configurations evaluated: **{n_aggregates}**")
    lines.append(f"- Selected for paper trading: **{n_selected}**")
    lines.append(f"- Combos abandoned: **{n_abandoned}**")
    lines.append(
        f"- Configurations ineligible under the flag rule (GO P7 rule 1): **{n_ineligible}**"
    )
    lines.append("")
    lines.append(note)
    lines.append("")

    # Selection table (trade counts next to the metrics: GO P7 rule 2)
    lines.append("## Selected configurations for paper trading")
    lines.append("")
    if not selection["selected_for_paper"]:
        lines.append(
            "_No eligible configuration passed all 7 selection criteria "
            "(zero passing config = zero paper selection, GO P7 rule 3)._"
        )
    else:
        lines.append(
            "| Strategy | Pair | Sharpe OOS (n trades) | std | PF OOS (n trades) | Consistency | "
            "MaxDD | Trades/window mean / min | Beats | Params |"
        )
        lines.append("|---|---|---|---|---|---|---|---|---|---|")
        for s in selection["selected_for_paper"]:
            n = s.get("mean_trades_test", 0.0)
            lines.append(
                f"| {s['strategy']} | {s['pair']} | "
                f"{fmt(s['mean_sharpe_oos'])} (n={n:.0f}) | {s['std_sharpe_oos']:.2f} | "
                f"{_pf_text(s)} (n={n:.0f}) | {s['consistency']}/8 | "
                f"{s['max_drawdown_global']:.1f}% | {n:.0f} / {s.get('min_trades_window', 0)} | "
                f"{s['beats_benchmark']} | `{_format_params_inline(s['params'])}` |"
            )
    lines.append("")

    # Abandoned table
    lines.append("## Abandoned combos")
    lines.append("")
    if not selection["abandoned"]:
        lines.append("_All combos produced at least one passing config — none abandoned._")
    else:
        lines.append(
            "| Strategy | Pair | Best Sharpe OOS (n trades) | Ineligible configs | Reason |"
        )
        lines.append("|---|---|---|---|---|")
        for a in selection["abandoned"]:
            lines.append(
                f"| {a['strategy']} | {a['pair']} | {fmt(a['best_sharpe_oos'])} "
                f"(n={a.get('best_mean_trades_test', 0.0):.0f}) | {a.get('n_ineligible', 0)} | "
                f"{a['reason']} |"
            )
    lines.append("")

    # Ineligible configurations (GO P7 rule 1)
    lines.append("## Ineligible configurations (flag rule — GO P7 rule 1)")
    lines.append("")
    ineligible = selection.get("ineligible_flagged", [])
    if not ineligible:
        lines.append("_No configuration flagged: every grid liquidation reconciled._")
    else:
        lines.append(
            "A configuration with at least one flagged run (phase 1 or any walk-forward window) "
            "is ineligible for paper whatever its score; the 7 criteria are reported unchanged."
        )
        lines.append("")
        lines.append(
            "| Strategy | Pair | Params | Sharpe OOS (n trades) | PF OOS (n trades) | "
            "Consistency | MaxDD | 7 criteria | Flagged runs | Reason |"
        )
        lines.append("|---|---|---|---|---|---|---|---|---|---|")
        for i in ineligible:
            n = i.get("mean_trades_test", 0.0)
            lines.append(
                f"| {i['strategy']} | {i['pair']} | `{_format_params_inline(i['params'])}` | "
                f"{fmt(i['mean_sharpe_oos'])} (n={n:.0f}) | {_pf_text(i)} (n={n:.0f}) | "
                f"{i['consistency']}/8 | {i['max_drawdown_global']:.1f}% | "
                f"{'passed' if i['passed_criteria'] else 'failed'} | {i['n_flags']} | {i['reason']} |"
            )
    lines.append("")

    # Top-5 phase-1 table per combo (best by test Sharpe)
    lines.append("## Phase 1 — top 5 by test Sharpe per combo")
    lines.append("")
    grouped_p1 = _group_phase1_by_combo(phase1_data)
    for (strat, pair), entries in sorted(grouped_p1.items()):
        lines.append(f"### {strat} on {pair}")
        lines.append("")
        lines.append(
            "| Rank | Test Sharpe | Test PF | Test Trades | Train Sharpe (n trades) | Params |"
        )
        lines.append("|---|---|---|---|---|---|")
        for i, e in enumerate(entries[:5], start=1):
            ts = e.get("test", {})
            tr = e.get("train", {})
            lines.append(
                f"| {i} | {_fmt_raw(ts.get('sharpe_ratio'))} | "
                f"{_fmt_raw(ts.get('profit_factor'))} | "
                f"{int(_safe_float(ts.get('total_trades')))} | "
                f"{_fmt_raw(tr.get('sharpe_ratio'))} "
                f"(n={int(_safe_float(tr.get('total_trades')))}) | "
                f"`{_format_params_inline(e.get('params') or {})}` |"
            )
        lines.append("")

    # Walk-forward summaries per surviving combo
    lines.append("## Walk-forward summaries (top 5 by mean OOS Sharpe per combo)")
    lines.append("")
    by_combo: dict[tuple[str, str], list[WalkForwardAggregate]] = defaultdict(list)
    for agg in aggregates.values():
        by_combo[(agg.strategy, agg.pair)].append(agg)
    for (strat, pair), aggs in sorted(by_combo.items()):
        lines.append(f"### {strat} on {pair}")
        lines.append("")
        lines.append(
            "| Mean Sharpe OOS | std | Mean PF | Consistency | MaxDD | Mean Trades | "
            "Train Sharpe (n trades) | Min trades/window | Params |"
        )
        lines.append("|---|---|---|---|---|---|---|---|---|")
        for a in sorted(aggs, key=lambda x: _rank(x.mean_sharpe_oos), reverse=True)[:5]:
            min_trades_per_window = _min_trades_per_window(a)
            train_trades = _mean(
                [_safe_float(w["train_metrics"].get("total_trades")) for w in a.per_window]
            )
            lines.append(
                f"| {fmt(a.mean_sharpe_oos)} | {a.std_sharpe_oos:.2f} | "
                f"{fmt(a.profit_factor_oos)} | {a.consistency}/{a.n_windows} | "
                f"{a.max_drawdown_global:.1f}% | {a.mean_trades_test:.0f} | "
                f"{fmt(a.mean_sharpe_train)} (n={train_trades:.0f}) | {min_trades_per_window} | "
                f"`{_format_params_inline(a.params)}` |"
            )
        lines.append("")

    # Benchmarks reminder
    source = (
        "campaign benchmarks file"
        if benchmarks is not BENCHMARK_SHARPE
        else "P6_backtest_report_v2"
    )
    lines.append(f"## Benchmarks ({source})")
    lines.append("")
    if benchmark_details:
        lines.append(
            "| Pair | Buy & Hold Sharpe | Buy & Hold Return | Buy & Hold MaxDD | "
            "DCA fixed Return | DCA fixed MaxDD"
            + (" (artefact)" if legacy else " (flow-adjusted)")
            + " | DCA fixed Sharpe"
            + (" (not comparable)" if legacy else " (flow-adjusted)")
            + " |"
        )
        lines.append("|---|---|---|---|---|---|---|")
        for pair in sorted(set(benchmarks) | set(benchmark_details)):
            d = benchmark_details.get(pair, {})
            bh, dca = d.get("buy_and_hold", {}), d.get("dca_fixed", {})
            fallback = benchmarks.get(pair, {})
            lines.append(
                f"| {pair} | {_fmt_raw(bh.get('sharpe', fallback.get('buy_and_hold')))} | "
                f"{_safe_float(bh.get('return_pct')):+.1f}% | "
                f"{_fmt_raw(bh.get('max_drawdown_pct'), 1)}% | "
                f"{_safe_float(dca.get('return_pct')):+.1f}% | "
                f"{_fmt_raw(dca.get('max_drawdown_pct'), 1)}% | "
                f"{_fmt_raw(dca.get('sharpe', fallback.get('dca_fixed')))} |"
            )
    else:
        dca_label = (
            "DCA fixed Sharpe (not comparable)" if legacy else "DCA fixed Sharpe (flow-adjusted)"
        )
        lines.append(f"| Pair | Buy & Hold Sharpe | {dca_label} |")
        lines.append("|---|---|---|")
        for pair, bench in benchmarks.items():
            lines.append(
                f"| {pair} | {fmt(bench.get('buy_and_hold'))} | {fmt(bench.get('dca_fixed'))} |"
            )
    lines.append("")
    lines.append(note)
    lines.append("")

    # B4.3 flag rule
    lines.extend(render_flags_markdown(selection.get("flagged_runs", [])))

    # Effective parameters of the selected configs (runtime capture)
    lines.append("## Effective parameters of the selected configurations (runtime capture)")
    lines.append("")
    if not selection["selected_for_paper"]:
        lines.append("_No selected configuration._")
    for sel in selection["selected_for_paper"]:
        eff = sel.get("effective_params") or {}
        lines.append(f"### {sel['strategy']} on {sel['pair']}")
        lines.append("")
        if not eff:
            lines.append("_Not captured (pre-B4.3 entries)._")
            lines.append("")
            continue
        lines.append(f"Class: `{eff.get('strategy_class')}`")
        lines.append("")
        lines.append("| Param | Value | Source |")
        lines.append("|---|---|---|")
        for name, info in sorted((eff.get("params") or {}).items()):
            lines.append(f"| `{name}` | {info.get('value')} | {info.get('source')} |")
        lines.append("")

    return "\n".join(lines) + "\n"


def _group_phase1_by_combo(
    phase1_data: dict[str, Any],
) -> dict[tuple[str, str], list[dict[str, Any]]]:
    """Group phase-1 results by (strategy, pair), sorted by test Sharpe desc."""
    by_combo: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for entry in phase1_data.values():
        if "error" in entry:
            continue
        strat = entry.get("strategy")
        pair = entry.get("pair")
        if strat and pair:
            by_combo[(strat, pair)].append(entry)
    for combo in by_combo:
        by_combo[combo].sort(
            key=lambda e: _rank(_metric(e.get("test"), "sharpe_ratio")),
            reverse=True,
        )
    return by_combo
