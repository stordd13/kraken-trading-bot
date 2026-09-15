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

Benchmarks come from the P6 v2 report.
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

sys.path.insert(0, str(Path(__file__).resolve().parent))

from b4_flags import collect_flags, render_flags_markdown  # noqa: E402

# ---------------------------------------------------------------------------
# Benchmarks (Sharpe ratios from P6_backtest_report_v2.md, period
# 2023-04-01 → 2026-04-01, Binance fees, 1k USDC capital)
# ---------------------------------------------------------------------------

BENCHMARK_SHARPE: dict[str, dict[str, float]] = {
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
    """Summary of one (strategy, pair, params) across all walk-forward windows."""

    strategy: str
    pair: str
    params: dict[str, Any]
    params_hash: str
    n_windows: int
    mean_sharpe_train: float
    mean_sharpe_oos: float
    std_sharpe_oos: float
    mean_pf_oos: float
    mean_trades_test: float
    max_drawdown_global: float
    consistency: int  # number of windows where test Sharpe > 0
    per_window: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
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


def _safe_float(v: Any, default: float = 0.0) -> float:
    """Coerce to float, treating None / NaN / errors as ``default``."""
    if v is None:
        return default
    try:
        fv = float(v)
    except (TypeError, ValueError):
        return default
    if math.isnan(fv) or math.isinf(fv):
        return default
    return fv


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

    Skips entries with an ``error`` key (failed jobs).
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
        train_sharpes = [_safe_float(w.get("train", {}).get("sharpe_ratio")) for w in windows]
        test_sharpes = [_safe_float(w.get("test", {}).get("sharpe_ratio")) for w in windows]
        test_pfs = [_safe_float(w.get("test", {}).get("profit_factor")) for w in windows]
        test_trades = [_safe_float(w.get("test", {}).get("total_trades")) for w in windows]
        # max_drawdown_pct is reported as a positive number (5.4 = -5.4% drawdown)
        test_dds = [_safe_float(w.get("test", {}).get("max_drawdown_pct")) for w in windows]

        consistency = sum(1 for s in test_sharpes if s > 0)

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
            consistency=consistency,
            per_window=sorted(
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
            ),
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
    actual: float
    threshold: float
    note: str = ""


@dataclass
class ConfigVerdict:
    """Final per-config selection verdict."""

    aggregate: WalkForwardAggregate
    criteria: list[CriterionResult]
    benchmark_sharpe: dict[str, float]
    beats_benchmark: str | None  # "buy_and_hold" | "dca_fixed" | None

    @property
    def passed(self) -> bool:
        return all(c.passed for c in self.criteria)

    def failure_reasons(self) -> list[str]:
        return [
            f"{c.name} (actual={c.actual:.3f}, threshold={c.threshold:.3f})"
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
            "mean_profit_factor": self.aggregate.mean_pf_oos,
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
    benchmarks: dict[str, dict[str, float]] = BENCHMARK_SHARPE,
) -> ConfigVerdict:
    """Apply the 7 selection criteria to a single walk-forward aggregate."""
    a = aggregate
    bench = benchmarks.get(a.pair, {})
    bh = bench.get("buy_and_hold", 0.0)
    dca = bench.get("dca_fixed", 0.0)

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


def build_selection(
    aggregates: dict[tuple[str, str, str], WalkForwardAggregate],
    benchmarks: dict[str, dict[str, float]] = BENCHMARK_SHARPE,
) -> dict[str, Any]:
    """Apply selection criteria to every aggregate, return the final selection dict."""
    verdicts: list[ConfigVerdict] = [
        apply_selection_criteria(agg, benchmarks) for agg in aggregates.values()
    ]

    # Group by (strategy, pair). For each, keep the best PASSING config (by
    # mean_sharpe_oos). If none passes, the combo is abandoned with the best
    # failing config's reasons as the rationale.
    by_combo: dict[tuple[str, str], list[ConfigVerdict]] = defaultdict(list)
    for v in verdicts:
        by_combo[(v.aggregate.strategy, v.aggregate.pair)].append(v)

    selected: list[dict[str, Any]] = []
    abandoned: list[dict[str, Any]] = []

    for (strategy, pair), combo_verdicts in by_combo.items():
        passing = [v for v in combo_verdicts if v.passed]
        if passing:
            # Best by mean_sharpe_oos
            best = max(passing, key=lambda v: v.aggregate.mean_sharpe_oos)
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
                    "effective_params": effective,
                    "mean_sharpe_oos": best.aggregate.mean_sharpe_oos,
                    "std_sharpe_oos": best.aggregate.std_sharpe_oos,
                    "mean_profit_factor": best.aggregate.mean_pf_oos,
                    "consistency": best.aggregate.consistency,
                    "max_drawdown_global": best.aggregate.max_drawdown_global,
                    "beats_benchmark": best.beats_benchmark,
                    "rationale": (
                        f"Best of {len(passing)} passing config(s). "
                        f"Sharpe_oos={best.aggregate.mean_sharpe_oos:.2f}, "
                        f"PF={best.aggregate.mean_pf_oos:.2f}, "
                        f"consistency={best.aggregate.consistency}/8, "
                        f"std_oos={best.aggregate.std_sharpe_oos:.2f}."
                    ),
                }
            )
        else:
            # Best failing config (by sharpe) → its failure reasons
            best_fail = max(combo_verdicts, key=lambda v: v.aggregate.mean_sharpe_oos)
            abandoned.append(
                {
                    "strategy": strategy,
                    "pair": pair,
                    "best_sharpe_oos": best_fail.aggregate.mean_sharpe_oos,
                    "best_params": best_fail.aggregate.params,
                    "reason": (
                        f"No configuration passed all 7 criteria. "
                        f"Best config failed on: {', '.join(best_fail.failure_reasons())}."
                    ),
                }
            )

    return {
        "selected_for_paper": selected,
        "abandoned": abandoned,
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
    benchmarks: dict[str, dict[str, float]] | None = None,
) -> dict[str, Any]:
    """Produce the human report + machine selection JSON. Returns the selection dict.

    ``benchmarks`` (``{pair: {"buy_and_hold": sharpe, "dca_fixed": sharpe}}``) replaces the
    P6 Binance constants for criterion 7 (B4.3: computed under the campaign fee model).
    """
    phase1_data = (
        json.loads(phase1_path.read_text(encoding="utf-8")) if phase1_path.exists() else {}
    )
    phase2_data = (
        json.loads(phase2_path.read_text(encoding="utf-8")) if phase2_path.exists() else {}
    )

    bench = benchmarks if benchmarks is not None else BENCHMARK_SHARPE
    aggregates = aggregate_walk_forward(phase2_data)
    selection = build_selection(aggregates, bench)
    # B4.3 flag rule: name every phase-1 / phase-2 run whose grid liquidation did not reconcile
    selection["flagged_runs"] = collect_flags(phase1_data) + collect_flags(phase2_data)

    # Write machine-readable selection
    selection_json_path.parent.mkdir(parents=True, exist_ok=True)
    selection_json_path.write_text(json.dumps(selection, indent=2, default=str), encoding="utf-8")

    # Write markdown
    md = _render_markdown(phase1_data, phase2_data, aggregates, selection, bench)
    output_md_path.parent.mkdir(parents=True, exist_ok=True)
    output_md_path.write_text(md, encoding="utf-8")

    return selection


def _render_markdown(
    phase1_data: dict[str, Any],
    phase2_data: dict[str, Any],
    aggregates: dict[tuple[str, str, str], WalkForwardAggregate],
    selection: dict[str, Any],
    benchmarks: dict[str, dict[str, float]] = BENCHMARK_SHARPE,
) -> str:
    """Compose the P7 optimization report markdown."""
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
    lines.append(f"- Phase 1 backtests (succeeded): **{n_phase1}**")
    lines.append(f"- Phase 2 walk-forward windows (succeeded): **{n_phase2}**")
    lines.append(f"- Aggregated configurations evaluated: **{n_aggregates}**")
    lines.append(f"- Selected for paper trading: **{n_selected}**")
    lines.append(f"- Combos abandoned: **{n_abandoned}**")
    lines.append("")

    # Selection table
    lines.append("## Selected configurations for paper trading")
    lines.append("")
    if not selection["selected_for_paper"]:
        lines.append("_No configuration passed all 7 selection criteria._")
    else:
        lines.append(
            "| Strategy | Pair | Sharpe OOS | std | PF OOS | Consistency | MaxDD | Beats | Params |"
        )
        lines.append("|---|---|---|---|---|---|---|---|---|")
        for s in selection["selected_for_paper"]:
            lines.append(
                f"| {s['strategy']} | {s['pair']} | "
                f"{s['mean_sharpe_oos']:.2f} | {s['std_sharpe_oos']:.2f} | "
                f"{s['mean_profit_factor']:.2f} | {s['consistency']}/8 | "
                f"{s['max_drawdown_global']:.1f}% | {s['beats_benchmark']} | "
                f"`{_format_params_inline(s['params'])}` |"
            )
    lines.append("")

    # Abandoned table
    lines.append("## Abandoned combos")
    lines.append("")
    if not selection["abandoned"]:
        lines.append("_All combos produced at least one passing config — none abandoned._")
    else:
        lines.append("| Strategy | Pair | Best Sharpe OOS | Reason |")
        lines.append("|---|---|---|---|")
        for a in selection["abandoned"]:
            lines.append(
                f"| {a['strategy']} | {a['pair']} | {a['best_sharpe_oos']:.2f} | {a['reason']} |"
            )
    lines.append("")

    # Top-5 phase-1 table per combo (best by test Sharpe)
    lines.append("## Phase 1 — top 5 by test Sharpe per combo")
    lines.append("")
    grouped_p1 = _group_phase1_by_combo(phase1_data)
    for (strat, pair), entries in sorted(grouped_p1.items()):
        lines.append(f"### {strat} on {pair}")
        lines.append("")
        lines.append("| Rank | Test Sharpe | Test PF | Test Trades | Train Sharpe | Params |")
        lines.append("|---|---|---|---|---|---|")
        for i, e in enumerate(entries[:5], start=1):
            ts = e.get("test", {})
            tr = e.get("train", {})
            lines.append(
                f"| {i} | {_safe_float(ts.get('sharpe_ratio')):.2f} | "
                f"{_safe_float(ts.get('profit_factor')):.2f} | "
                f"{int(_safe_float(ts.get('total_trades')))} | "
                f"{_safe_float(tr.get('sharpe_ratio')):.2f} | "
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
            "| Mean Sharpe OOS | std | Mean PF | Consistency | MaxDD | Mean Trades | Train Sharpe | Min trades/window | Params |"
        )
        lines.append("|---|---|---|---|---|---|---|---|---|")
        for a in sorted(aggs, key=lambda x: x.mean_sharpe_oos, reverse=True)[:5]:
            min_trades_per_window = (
                min(int(_safe_float(w["test_metrics"].get("total_trades"))) for w in a.per_window)
                if a.per_window
                else 0
            )
            lines.append(
                f"| {a.mean_sharpe_oos:.2f} | {a.std_sharpe_oos:.2f} | "
                f"{a.mean_pf_oos:.2f} | {a.consistency}/{a.n_windows} | "
                f"{a.max_drawdown_global:.1f}% | {a.mean_trades_test:.0f} | "
                f"{a.mean_sharpe_train:.2f} | {min_trades_per_window} | "
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
    lines.append("| Pair | Buy & Hold Sharpe | DCA fixed Sharpe |")
    lines.append("|---|---|---|")
    for pair, bench in benchmarks.items():
        lines.append(f"| {pair} | {bench['buy_and_hold']:.2f} | {bench['dca_fixed']:.2f} |")
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
            key=lambda e: _safe_float(e.get("test", {}).get("sharpe_ratio")),
            reverse=True,
        )
    return by_combo
