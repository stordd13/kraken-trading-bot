"""Phase E — Filter P6 backtest survivors based on 5-metric decision framework.

Reads Phase D results + benchmarks, applies acceptance criteria, and
produces a list of survivors + filtering report.

Usage:
    poetry run python scripts/filter_p6_survivors.py
    poetry run python scripts/filter_p6_survivors.py --input results/B4_P6_phase_d_results.json \
        --benchmarks results/B4_benchmarks.json --survivors results/B4_P6_phase_e_survivors.json \
        --report results/B4_P6_phase_e_filtering.md

B4.3: the filtering report names every run flagged by the campaign rule (grid liquidation
not reconciled: residual proceeds, inventory divergence, net_pnl != lot basis).
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

RESULTS_DIR = Path(__file__).resolve().parent.parent / "results"
PHASE_D_PATH = RESULTS_DIR / "P6_phase_d_results.json"
BENCHMARKS_PATH = RESULTS_DIR / "P6_benchmarks.json"
SURVIVORS_PATH = RESULTS_DIR / "P6_phase_e_survivors.json"
REPORT_PATH = RESULTS_DIR / "P6_phase_e_filtering.md"

# Acceptance thresholds (applied on TEST set)
THRESHOLDS = {
    "sharpe_ratio": 1.0,
    "sortino_ratio": 1.5,
    "max_drawdown_pct": 25.0,  # must be BELOW this
    "profit_factor": 1.5,
    "calmar_ratio": 0.5,
    "min_trades": 30,
}

# DCA strategy has fewer discrete trades — exempt from min_trades
DCA_STRATEGIES = {"grok_adaptive_dca_weekly"}

# Train/test consistency: test_sharpe / train_sharpe > 0.5
CONSISTENCY_RATIO = 0.5


def metric(block: dict | None, key: str) -> float | None:
    """C1: a metric absent or null is undefined (None) — never coerced to 0."""
    value = (block or {}).get(key)
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def max_dd(block: dict | None) -> float | None:
    """Daily-NAV running-peak drawdown (C1 key), pre-C1 key as fallback."""
    value = metric(block, "max_drawdown_pct_daily")
    return value if value is not None else metric(block, "max_drawdown_pct")


def check_criteria(test: dict, strategy: str) -> list[str]:
    """Return list of failed criteria names. Empty = all pass.

    C1: an undefined metric (None) fails its threshold with an explicit ``undefined`` reason.
    """
    failures = []

    for key, label in (
        ("sharpe_ratio", "Sharpe"),
        ("sortino_ratio", "Sortino"),
        ("profit_factor", "PF"),
        ("calmar_ratio", "Calmar"),
    ):
        value = metric(test, key)
        if value is None:
            failures.append(f"{label} undefined (n/a) — threshold {THRESHOLDS[key]} not met")
        elif value < THRESHOLDS[key]:
            failures.append(f"{label} {fmt(value)} < {THRESHOLDS[key]}")

    dd = max_dd(test)
    if dd is None:
        failures.append(
            f"MaxDD undefined (n/a) — threshold {THRESHOLDS['max_drawdown_pct']}% not met"
        )
    elif dd > THRESHOLDS["max_drawdown_pct"]:
        failures.append(f"MaxDD {fmt(dd, 1)}% > {THRESHOLDS['max_drawdown_pct']}%")

    if strategy not in DCA_STRATEGIES:
        if test.get("total_trades", 0) < THRESHOLDS["min_trades"]:
            failures.append(f"Trades {test.get('total_trades', 0)} < {THRESHOLDS['min_trades']}")

    return failures


def check_consistency(train: dict, test: dict) -> str | None:
    """Check train/test consistency. Returns warning or None (C1: undefined -> warning)."""
    train_sharpe = metric(train, "sharpe_ratio")
    test_sharpe = metric(test, "sharpe_ratio")

    if train_sharpe is None or test_sharpe is None:
        return "Overfit check undefined: a Sharpe is undefined (n/a)"
    if train_sharpe > 0 and test_sharpe / train_sharpe < CONSISTENCY_RATIO:
        return (
            f"Overfit risk: test/train Sharpe ratio = "
            f"{test_sharpe:.2f}/{train_sharpe:.2f} = {test_sharpe / train_sharpe:.2f}"
        )
    return None


def check_beats_benchmark(test: dict, pair: str, benchmarks: dict) -> bool:
    """Check if strategy beats at least one benchmark in Sharpe on the same pair (C1: an
    undefined Sharpe or benchmark leg cannot be beaten)."""
    test_sharpe = metric(test, "sharpe_ratio")
    if test_sharpe is None:
        return False

    bh_sharpe = metric(benchmarks.get("buy_and_hold", {}).get(pair, {}), "sharpe_ratio")
    dca_sharpe = metric(benchmarks.get("dca_fixed_15usd_weekly", {}).get(pair, {}), "sharpe_ratio")

    return (bh_sharpe is not None and test_sharpe > bh_sharpe) or (
        dca_sharpe is not None and test_sharpe > dca_sharpe
    )


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="P6 Phase E — survivor filtering.")
    parser.add_argument("--input", type=Path, default=PHASE_D_PATH, help="Phase D results JSON.")
    parser.add_argument(
        "--benchmarks", type=Path, default=BENCHMARKS_PATH, help="Benchmarks JSON (B&H / DCA)."
    )
    parser.add_argument("--survivors", type=Path, default=SURVIVORS_PATH, help="Output JSON.")
    parser.add_argument("--report", type=Path, default=REPORT_PATH, help="Output markdown.")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    args = parse_args(argv)
    phase_d_path: Path = args.input
    benchmarks_path: Path = args.benchmarks
    survivors_path: Path = args.survivors
    report_path: Path = args.report

    # Load data
    if not phase_d_path.exists():
        print(f"ERROR: {phase_d_path} not found. Run Phase D first.")
        sys.exit(1)

    phase_d = json.loads(phase_d_path.read_text())
    try:  # C1: one metrics contract per file, never a pre-C1 / mixed one
        require_metrics_version(phase_d, METRICS_VERSION, path=str(phase_d_path))
    except MetricsVersionError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(2)

    benchmarks = {}
    if benchmarks_path.exists():
        benchmarks = json.loads(benchmarks_path.read_text())

    survivors: dict = {}
    all_rows: list[dict] = []

    for key, data in phase_d.items():
        strategy = data.get("strategy", key)
        pair = data.get("pair", "?")

        # Skip crashed backtests
        if "error" in data:
            all_rows.append(
                {
                    "key": key,
                    "strategy": strategy,
                    "pair": pair,
                    "status": "CRASH",
                    "reason": data["error"][:80],
                    "test": {},
                    "train": {},
                }
            )
            continue

        train = data.get("train", {})
        test = data.get("test", {})

        # Check 5 criteria
        failures = check_criteria(test, strategy)

        # Check consistency
        consistency_warn = check_consistency(train, test)
        if consistency_warn:
            failures.append(consistency_warn)

        # Check beats benchmark
        beats_bm = check_beats_benchmark(test, pair, benchmarks)
        if not beats_bm and benchmarks:
            failures.append("Does not beat any benchmark in Sharpe")

        status = "PASS" if not failures else "FAIL"
        reason = failures[0] if failures else ""

        row = {
            "key": key,
            "strategy": strategy,
            "pair": pair,
            "status": status,
            "reason": reason,
            "all_failures": failures,
            "test": test,
            "train": train,
        }
        all_rows.append(row)

        if status == "PASS":
            survivors[key] = data

    # Save survivors JSON
    survivors_path.parent.mkdir(parents=True, exist_ok=True)
    survivors_path.write_text(json.dumps(survivors, indent=2, default=str), encoding="utf-8")

    # Generate markdown report
    lines = []
    lines.append("# P6 Phase E — Survivor Filtering Report")
    lines.append("")
    lines.append(f"**Total combinations**: {len(all_rows)}")
    lines.append(f"**Survivors**: {len(survivors)}")
    lines.append(f"**Rejected**: {len(all_rows) - len(survivors)}")
    lines.append("")

    # Thresholds
    lines.append("## Acceptance Criteria (applied on TEST set)")
    lines.append("")
    lines.append(f"- Sharpe > {THRESHOLDS['sharpe_ratio']}")
    lines.append(f"- Sortino > {THRESHOLDS['sortino_ratio']}")
    lines.append(f"- Max Drawdown < {THRESHOLDS['max_drawdown_pct']}%")
    lines.append(f"- Profit Factor > {THRESHOLDS['profit_factor']}")
    lines.append(f"- Calmar > {THRESHOLDS['calmar_ratio']}")
    lines.append(f"- Min {THRESHOLDS['min_trades']} trades (except DCA)")
    lines.append(f"- Train/test consistency > {CONSISTENCY_RATIO}")
    lines.append("- Must beat Buy & Hold or DCA benchmark in Sharpe")
    lines.append("")

    # Full results table
    lines.append("## Full Results")
    lines.append("")
    lines.append(
        "| Strategy | Pair | Return (test) | Sharpe | Sortino | MaxDD | PF | "
        "Calmar | Trades | Status | Primary Reason |"
    )
    lines.append("|---|---|---|---|---|---|---|---|---|---|---|")

    for row in sorted(all_rows, key=lambda r: (r["status"], r["strategy"], r["pair"])):
        test = row.get("test", {})
        ret = test.get("total_return_pct", 0)
        trades = test.get("total_trades", 0)
        icon = {"PASS": "PASS", "FAIL": "FAIL", "CRASH": "CRASH"}.get(row["status"], "?")

        lines.append(
            f"| {row['strategy']} | {row['pair']} | "
            f"{ret:+.1f}% | {fmt(metric(test, 'sharpe_ratio'))} | "
            f"{fmt(metric(test, 'sortino_ratio'))} | "
            f"{fmt(max_dd(test), 1)}% | {fmt(metric(test, 'profit_factor'))} | "
            f"{fmt(metric(test, 'calmar_ratio'))} | {trades} | "
            f"{icon} | {row['reason'][:50]} |"
        )

    lines.append("")

    # Survivors list
    lines.append("## Survivors")
    lines.append("")
    if survivors:
        for key in survivors:
            s = survivors[key]
            test = s.get("test", {})
            lines.append(
                f"- **{s['strategy']}** on {s['pair']}: "
                f"Sharpe {fmt(metric(test, 'sharpe_ratio'))}, "
                f"Return {test.get('total_return_pct', 0):+.1f}%, "
                f"MaxDD {fmt(max_dd(test), 1)}%"
            )
    else:
        lines.append("No combinations passed all criteria.")
    lines.append("")

    # B4.3 flag rule: name every run whose grid liquidation did not reconcile
    flags = collect_flags(phase_d)
    lines.extend(render_flags_markdown(flags))

    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"Survivors: {len(survivors)}/{len(all_rows)}")
    print(f"Flagged runs: {len(flags)}")
    print(f"Report: {report_path}")
    print(f"JSON: {survivors_path}")

    if survivors:
        print("\nSurvivors:")
        for key in survivors:
            s = survivors[key]
            test = s.get("test", {})
            print(
                f"  {s['strategy']:40s} {s['pair']:10s} "
                f"Sharpe={fmt(metric(test, 'sharpe_ratio'))} "
                f"Return={test.get('total_return_pct', 0):+.1f}%"
            )


if __name__ == "__main__":
    main()
