"""Phase G — Generate the final P6 backtest report in Markdown.

Reads all JSON outputs from phases C-F and produces a comprehensive
human-readable report.

Usage:
    poetry run python scripts/generate_p6_report.py
    poetry run python scripts/generate_p6_report.py --output P6_backtest_report_v2.md
    poetry run python scripts/generate_p6_report.py --phase-d B4_P6_phase_d_results.json \
        --benchmarks B4_benchmarks.json --survivors B4_P6_phase_e_survivors.json \
        --walkforward B4_P6_phase_f_walkforward.json --output B4_P6_backtest_report.md

B4.3: the report names every run flagged by the campaign rule (grid liquidation not
reconciled) and embeds the runtime-captured effective parameters of the survivors.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))

from b4_flags import collect_flags, render_flags_markdown  # noqa: E402

from krakenbot.backtest_metrics import (  # noqa: E402
    METRICS_VERSION,
    MetricsVersionError,
    fmt,
    require_metrics_version,
)


def _m(block: dict | None, key: str, digits: int = 2) -> str:
    """C1: display of a metric that may be undefined (None -> n/a, inf -> ∞)."""
    value = (block or {}).get(key)
    if value is None:
        return "n/a"
    try:
        return fmt(float(value), digits)
    except (TypeError, ValueError):
        return "n/a"


def _dd(block: dict | None) -> str:
    """Daily-NAV running-peak drawdown (C1 key), pre-C1 key as fallback."""
    block = block or {}
    key = "max_drawdown_pct_daily" if "max_drawdown_pct_daily" in block else "max_drawdown_pct"
    return _m(block, key, 1)


RESULTS_DIR = Path(__file__).resolve().parent.parent / "results"
BENCHMARKS_PATH = RESULTS_DIR / "P6_benchmarks.json"
PHASE_D_PATH = RESULTS_DIR / "P6_phase_d_results.json"
SURVIVORS_PATH = RESULTS_DIR / "P6_phase_e_survivors.json"
WALKFORWARD_PATH = RESULTS_DIR / "P6_phase_f_walkforward.json"
COVERAGE_PATH = RESULTS_DIR / "P6_data_coverage.md"


def load_json(path: Path) -> dict:
    if path.exists():
        return json.loads(path.read_text())
    return {}


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output",
        default="P6_backtest_report.md",
        help="Output filename (relative to results/ directory)",
    )
    parser.add_argument(
        "--phase-d",
        default="P6_phase_d_results.json",
        help="Phase D results filename (relative to results/ directory)",
    )
    parser.add_argument(
        "--benchmarks",
        default=BENCHMARKS_PATH.name,
        help="Benchmarks filename (relative to results/ directory)",
    )
    parser.add_argument(
        "--survivors",
        default=SURVIVORS_PATH.name,
        help="Phase E survivors filename (relative to results/ directory)",
    )
    parser.add_argument(
        "--walkforward",
        default=WALKFORWARD_PATH.name,
        help="Phase F walk-forward filename (relative to results/ directory)",
    )
    args = parser.parse_args(argv)
    report_path = RESULTS_DIR / args.output
    phase_d_path = RESULTS_DIR / args.phase_d

    benchmarks = load_json(RESULTS_DIR / args.benchmarks)
    phase_d = load_json(phase_d_path)
    try:  # C1: one metrics contract per file, never a pre-C1 / mixed one
        require_metrics_version(phase_d, METRICS_VERSION, path=str(phase_d_path))
    except MetricsVersionError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(2)
    survivors = load_json(RESULTS_DIR / args.survivors)
    walkforward = load_json(RESULTS_DIR / args.walkforward)

    lines: list[str] = []

    # ── a. Executive Summary ──
    lines.append("# P6 — Binance Backtest Validation Report")
    lines.append("")

    total = len(phase_d)
    n_survivors = len(survivors)
    n_wf = len(walkforward)
    crashed = sum(1 for v in phase_d.values() if "error" in v)

    lines.append("## Executive Summary")
    lines.append("")
    lines.append(
        f"We tested **{total} combinations** (8 strategies x 3 pairs) over 3 years "
        f"of Binance data (2023-04 to 2026-04) with cross-validation (70/30 train/test split). "
        f"**{n_survivors}** combinations passed all 5 acceptance criteria on the test set. "
    )
    if n_wf > 0:
        wf_ok = sum(1 for v in walkforward.values() if v.get("consistency_score", 0) >= 0.5)
        lines.append(
            f"Walk-forward validation confirmed **{wf_ok}/{n_wf}** survivors "
            f"with consistency score >= 50%."
        )
    if crashed:
        lines.append(f"{crashed} combinations crashed during backtesting.")
    lines.append("")

    # ── b. Methodology ──
    lines.append("## Methodology")
    lines.append("")
    lines.append("- **Period**: 2023-04-01 to 2026-04-01 (3 years)")
    lines.append("- **Exchange**: Binance (historical data from Binance Vision)")
    fee_models = sorted({str(v.get("fees")) for v in phase_d.values() if isinstance(v, dict)})
    cost_files = sorted(
        {str(v.get("pair_costs_file")) for v in phase_d.values() if v.get("pair_costs_file")}
    )
    min_orders = sorted({str(v.get("min_order_usdc", 1.0)) for v in phase_d.values()})
    lines.append(
        f"- **Fees**: model `{', '.join(fee_models) or 'unknown'}` (maker/taker per fill site; "
        f"per-pair costs: {', '.join(cost_files) or 'model globals'}; min order: "
        f"{', '.join(min_orders)} USDC)"
    )
    lines.append("- **Starting capital**: $1,000 USDC per backtest")
    lines.append("- **Cross-validation**: 70% train / 30% test temporal split")
    lines.append("- **Walk-forward**: 12-month train / 3-month test, 3-month advance (8 windows)")
    lines.append("- **Execution model**: Next-bar (signal on candle N, fill at open of candle N+1)")
    lines.append("")
    lines.append("### Acceptance Criteria (all must pass on TEST set)")
    lines.append("")
    lines.append("| Metric | Threshold |")
    lines.append("|--------|-----------|")
    lines.append("| Sharpe Ratio | > 1.0 |")
    lines.append("| Sortino Ratio | > 1.5 |")
    lines.append("| Max Drawdown | < 25% |")
    lines.append("| Profit Factor | > 1.5 |")
    lines.append("| Calmar Ratio | > 0.5 |")
    lines.append("| Min Trades | >= 30 (except DCA) |")
    lines.append("| Consistency | test_sharpe / train_sharpe > 0.5 |")
    lines.append("| Benchmark | Must beat Buy & Hold or DCA in Sharpe |")
    lines.append("")

    # ── c. Data Coverage ──
    lines.append("## Data Coverage")
    lines.append("")
    if COVERAGE_PATH.exists():
        coverage_text = COVERAGE_PATH.read_text()
        # Extract the tables (skip the title)
        in_table = False
        for line in coverage_text.split("\n"):
            if line.startswith("## 2.") or in_table:
                in_table = True
                if line.startswith("## 3."):
                    break
                lines.append(line)
        lines.append("")
    else:
        lines.append("*Coverage report not found.*")
        lines.append("")

    # ── d. Benchmarks ──
    lines.append("## Benchmarks")
    lines.append("")
    lines.append("| Pair | Strategy | Return % | Sharpe | Sortino | MaxDD % | Calmar |")
    lines.append("|------|----------|----------|--------|---------|---------|--------|")

    for bm_type, bm_label in [
        ("buy_and_hold", "Buy & Hold"),
        ("dca_fixed_15usd_weekly", "DCA $15/wk"),
    ]:
        bm_data = benchmarks.get(bm_type, {})
        for pair in ["BTC/USDC", "ETH/USDC", "SOL/USDC"]:
            m = bm_data.get(pair, {})
            if "error" in m:
                lines.append(f"| {pair} | {bm_label} | N/A | N/A | N/A | N/A | N/A |")
            else:
                lines.append(
                    f"| {pair} | {bm_label} | "
                    f"{m.get('total_return_pct', 0):+.1f}% | "
                    f"{_m(m, 'sharpe_ratio')} | "
                    f"{_m(m, 'sortino_ratio')} | "
                    f"{_dd(m)}% | "
                    f"{_m(m, 'calmar_ratio')} |"
                )
    lines.append("")

    # ── e. First Pass Results ──
    lines.append("## First Pass Results (Cross-Validated)")
    lines.append("")
    lines.append(
        "| Strategy | Pair | Train Ret | Test Ret | Train Sharpe | Test Sharpe | "
        "MaxDD | PF | Calmar | Trades | Status |"
    )
    lines.append("|---|---|---|---|---|---|---|---|---|---|---|")

    for key in sorted(phase_d.keys()):
        data = phase_d[key]
        strategy = data.get("strategy", key)
        pair = data.get("pair", "?")

        if "error" in data:
            lines.append(f"| {strategy} | {pair} | - | - | - | - | - | - | - | - | CRASH |")
            continue

        train = data.get("train", {})
        test = data.get("test", {})
        is_survivor = key in survivors
        status = "PASS" if is_survivor else "FAIL"

        lines.append(
            f"| {strategy} | {pair} | "
            f"{train.get('total_return_pct', 0):+.1f}% | "
            f"{test.get('total_return_pct', 0):+.1f}% | "
            f"{_m(train, 'sharpe_ratio')} | "
            f"{_m(test, 'sharpe_ratio')} | "
            f"{_dd(test)}% | "
            f"{_m(test, 'profit_factor')} | "
            f"{_m(test, 'calmar_ratio')} | "
            f"{test.get('total_trades', 0)} | "
            f"{status} |"
        )
    lines.append("")

    # ── f. Walk-Forward Results ──
    lines.append("## Walk-Forward Results")
    lines.append("")
    if walkforward:
        lines.append(
            "| Strategy | Pair | Consistency | Mean Sharpe | Mean Return | "
            "Mean MaxDD | Positive Windows | Verdict |"
        )
        lines.append("|---|---|---|---|---|---|---|---|")

        for _key, wf in walkforward.items():
            cs = wf.get("consistency_score", 0)
            mm = wf.get("mean_metrics", {})
            pw = wf.get("positive_windows", 0)
            tw = wf.get("total_windows", 0)
            verdict = "CONFIRMED" if cs >= 0.5 else "AT RISK"
            lines.append(
                f"| {wf['strategy']} | {wf['pair']} | "
                f"{cs:.0%} | "
                f"{_m(mm, 'sharpe_ratio')} | "
                f"{mm.get('total_return_pct', 0):+.1f}% | "
                f"{_dd(mm)}% | "
                f"{pw}/{tw} | {verdict} |"
            )
        lines.append("")
    else:
        lines.append("*No walk-forward results available (no survivors or Phase F not run).*")
        lines.append("")

    # ── g. Recommendations ──
    lines.append("## Recommendations")
    lines.append("")

    priority1 = []
    priority2 = []
    abandon = []

    for _key, wf in walkforward.items():
        cs = wf.get("consistency_score", 0)
        if cs >= 0.625:  # 5/8 or more windows positive
            priority1.append(wf)
        elif cs >= 0.5:  # 4/8
            priority2.append(wf)
        else:
            abandon.append(wf)

    # Also add non-survivors to abandon
    for key, data in phase_d.items():
        if key not in survivors and "error" not in data:
            abandon.append({"strategy": data["strategy"], "pair": data["pair"]})

    lines.append("### Priority 1 — Activate in Paper Trading")
    lines.append("")
    if priority1:
        for wf in priority1:
            mm = wf.get("mean_metrics", {})
            lines.append(
                f"- **{wf['strategy']}** on {wf['pair']} "
                f"(consistency {wf.get('consistency_score', 0):.0%}, "
                f"mean Sharpe {_m(mm, 'sharpe_ratio')})"
            )
    else:
        lines.append("*None*")
    lines.append("")

    lines.append("### Priority 2 — Observe in Paper with Reduced Capital")
    lines.append("")
    if priority2:
        for wf in priority2:
            mm = wf.get("mean_metrics", {})
            lines.append(
                f"- **{wf['strategy']}** on {wf['pair']} "
                f"(consistency {wf.get('consistency_score', 0):.0%}, "
                f"mean Sharpe {_m(mm, 'sharpe_ratio')})"
            )
    else:
        lines.append("*None*")
    lines.append("")

    lines.append("### Abandon")
    lines.append("")
    if abandon:
        for item in abandon:
            lines.append(f"- {item.get('strategy', '?')} on {item.get('pair', '?')}")
    else:
        lines.append("*None*")
    lines.append("")

    # ── h. Surprising Findings ──
    lines.append("## Surprising Findings")
    lines.append("")
    # Auto-detect interesting patterns
    findings = []

    # Check if any strategy works on one pair but not another
    strategy_pairs: dict[str, list[str]] = {}
    for key, data in phase_d.items():
        if "error" not in data:
            s = data["strategy"]
            p = data["pair"]
            if key in survivors:
                strategy_pairs.setdefault(s, []).append(p)

    for s, pairs in strategy_pairs.items():
        if len(pairs) < 3:
            works_on = ", ".join(pairs)
            findings.append(f"**{s}** works on {works_on} but not all 3 pairs.")

    if not findings:
        findings.append("No particularly surprising patterns detected.")

    for f in findings:
        lines.append(f"- {f}")
    lines.append("")

    # ── h2. B4.3 flag rule — runs whose grid liquidation did not reconcile ──
    flags = collect_flags(phase_d) + collect_flags(walkforward, walkforward=True)
    lines.extend(render_flags_markdown(flags))

    # ── h3. Effective parameters captured at runtime (survivors) ──
    lines.append("## Effective parameters (runtime capture, survivors)")
    lines.append("")
    if not survivors:
        lines.append(
            "_No survivor: the effective parameters of every combo are in the phase D JSON "
            "(`effective_params` per entry)._"
        )
    for key in sorted(survivors):
        entry = phase_d.get(key, survivors[key])
        eff = entry.get("effective_params") or {}
        lines.append(f"### {entry.get('strategy', key)} on {entry.get('pair', '?')}")
        lines.append("")
        if not eff:
            lines.append("_Not captured (pre-B4.3 entry)._")
            lines.append("")
            continue
        lines.append(f"Class: `{eff.get('strategy_class')}`")
        lines.append("")
        lines.append("| Param | Value | Source |")
        lines.append("|---|---|---|")
        for name, info in sorted((eff.get("params") or {}).items()):
            lines.append(f"| `{name}` | {info.get('value')} | {info.get('source')} |")
        lines.append("")
    lines.append("")

    # ── i. Next Steps ──
    lines.append("## Next Steps")
    lines.append("")
    lines.append("1. Activate Priority 1 combinations in paper trading (2-4 weeks)")
    lines.append("2. Monitor Priority 2 with reduced capital")
    lines.append("3. P7: Parameter optimization on survivors (grid search or Bayesian)")
    lines.append("4. P8: ML feature engineering (XGBoost/RF on technical features)")
    lines.append("5. Scale capital progressively on confirmed winners (1k -> 10k -> 20k USDC)")
    lines.append("")

    # Write report
    report_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"Report generated: {report_path}")
    print(f"  Combinations: {total}")
    print(f"  Survivors: {n_survivors}")
    print(f"  Flagged runs: {len(flags)}")
    print(
        f"  Walk-forward confirmed: {sum(1 for v in walkforward.values() if v.get('consistency_score', 0) >= 0.5)}"
    )


if __name__ == "__main__":
    main()
