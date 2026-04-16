"""Phase G — Generate the final P6 backtest report in Markdown.

Reads all JSON outputs from phases C-F and produces a comprehensive
human-readable report.

Usage:
    poetry run python scripts/generate_p6_report.py
"""

from __future__ import annotations

import json
from pathlib import Path

RESULTS_DIR = Path(__file__).resolve().parent.parent / "results"
BENCHMARKS_PATH = RESULTS_DIR / "P6_benchmarks.json"
PHASE_D_PATH = RESULTS_DIR / "P6_phase_d_results.json"
SURVIVORS_PATH = RESULTS_DIR / "P6_phase_e_survivors.json"
WALKFORWARD_PATH = RESULTS_DIR / "P6_phase_f_walkforward.json"
COVERAGE_PATH = RESULTS_DIR / "P6_data_coverage.md"
REPORT_PATH = RESULTS_DIR / "P6_backtest_report.md"


def load_json(path: Path) -> dict:
    if path.exists():
        return json.loads(path.read_text())
    return {}


def main() -> None:
    benchmarks = load_json(BENCHMARKS_PATH)
    phase_d = load_json(PHASE_D_PATH)
    survivors = load_json(SURVIVORS_PATH)
    walkforward = load_json(WALKFORWARD_PATH)

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
    lines.append("- **Fees**: 0.075% maker/taker (BNB discount), 0.02% spread, 0.01% slippage")
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
                    f"{m.get('sharpe_ratio', 0):.2f} | "
                    f"{m.get('sortino_ratio', 0):.2f} | "
                    f"{m.get('max_drawdown_pct', 0):.1f}% | "
                    f"{m.get('calmar_ratio', 0):.2f} |"
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
            f"{train.get('sharpe_ratio', 0):.2f} | "
            f"{test.get('sharpe_ratio', 0):.2f} | "
            f"{test.get('max_drawdown_pct', 0):.1f}% | "
            f"{test.get('profit_factor', 0):.2f} | "
            f"{test.get('calmar_ratio', 0):.2f} | "
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
                f"{mm.get('sharpe_ratio', 0):.2f} | "
                f"{mm.get('total_return_pct', 0):+.1f}% | "
                f"{mm.get('max_drawdown_pct', 0):.1f}% | "
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
                f"mean Sharpe {mm.get('sharpe_ratio', 0):.2f})"
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
                f"mean Sharpe {mm.get('sharpe_ratio', 0):.2f})"
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
    REPORT_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"Report generated: {REPORT_PATH}")
    print(f"  Combinations: {total}")
    print(f"  Survivors: {n_survivors}")
    print(
        f"  Walk-forward confirmed: {sum(1 for v in walkforward.values() if v.get('consistency_score', 0) >= 0.5)}"
    )


if __name__ == "__main__":
    main()
