"""B4.3 campaign — P7 CHECKPOINT summary (after phase 1, after phase 2; before the next step).

Pure, read-only. Reads a P7 results file (phase 1: ``…_p1_<hash>`` entries with train / test /
all segments; phase 2: ``…_p2_<hash>_w<idx>`` entries with train / test) and prints the ten-line
checkpoint: completion vs the expected job count, campaign signature, runs flagged by the
campaign rule (``b4_flags``) and the configurations they make ineligible (GO P7 rule 1),
anomalies ("too good" results are suspected before being accepted — brief § 6.3), best
configs per combo **with their trade counts** (GO P7 rule 2), grid liquidations, and — for
phase 2 with ``--benchmarks`` — the verdict of the 7 unchanged criteria (GO P7 rule 3).

Usage::

    poetry run python scripts/audit/b4_p7_checkpoint.py results/B4_P7_phase1_cross_validate.json
    poetry run python scripts/audit/b4_p7_checkpoint.py results/B4_P7_phase2_walk_forward.json \\
        --benchmarks results/B4_benchmarks.json [--markdown out.md]
"""

from __future__ import annotations

import argparse
from collections import Counter
import json
from pathlib import Path
import sys
from typing import Any

_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(_ROOT / "scripts"))

import b4_flags  # noqa: E402
import p7_grids  # noqa: E402
import p7_report  # noqa: E402

PHASE1_EXPECTED = len(p7_grids.build_phase1_combos())  # 212
PHASE2_EXPECTED = 7 * 5 * 8  # combos × top-k × windows = 280


def _f(v: Any, default: float = 0.0) -> float:
    try:
        x = float(v)
    except (TypeError, ValueError):
        return default
    if x != x:  # NaN
        return default
    return x


def _is_inf(v: Any) -> bool:
    return v in ("Infinity", "inf") or (isinstance(v, float) and v == float("inf"))


def _phase(entries: dict[str, Any]) -> str:
    phases = Counter(str(v.get("phase")) for v in entries.values())
    return phases.most_common(1)[0][0] if phases else "?"


def summarize(results: dict[str, Any], benchmarks: dict[str, Any] | None = None) -> list[str]:
    entries = {k: v for k, v in results.items() if isinstance(v, dict)}
    ok = {k: v for k, v in entries.items() if "error" not in v}
    crashed = {k: v for k, v in entries.items() if "error" in v}
    phase = _phase(entries)
    expected = PHASE1_EXPECTED if phase == "1" else PHASE2_EXPECTED
    segments = ("train", "test", "all") if phase == "1" else ("train", "test")
    lines: list[str] = []

    per_strategy = Counter(v.get("strategy", "?") for v in ok.values())
    lines.append(
        f"1. Completion (phase {phase}): {len(ok)}/{expected} jobs succeeded, {len(crashed)} crashed, "
        f"{expected - len(entries)} missing — per strategy: "
        + ", ".join(f"{s} {n}" for s, n in sorted(per_strategy.items()))
        + (f" — crashed: {', '.join(sorted(crashed))}" if crashed else "")
    )
    sigs = Counter(
        (v.get("fees"), v.get("pair_costs_file"), v.get("min_order_usdc")) for v in ok.values()
    )
    lines.append(
        "2. Campaign signature (fees, pair_costs_file, min_order_usdc): "
        + "; ".join(f"{s} x{n}" for s, n in sigs.items())
    )

    flags = b4_flags.collect_flags(results)
    ineligible = p7_report.ineligible_configs(flags)
    lines.append(
        f"3. Flag rule: {len(flags)} flagged run(s) → {len(ineligible)} ineligible config(s) "
        "(GO P7 rule 1)"
        + (
            " — "
            + "; ".join(
                f"{s}×{p.split('/')[0]}#{h} ({len(fl)} flag(s): "
                + ", ".join(sorted({f["segment"] for f in fl}))
                + ")"
                for (s, p, h), fl in sorted(ineligible.items())
            )
            if ineligible
            else " — none"
        )
    )

    anomalies: list[str] = []
    for key, v in ok.items():
        for seg in segments:
            m = v.get(seg) or {}
            trades = int(_f(m.get("total_trades")))
            pf = m.get("profit_factor")
            ret = _f(m.get("total_return_pct"))
            sharpe = _f(m.get("sharpe_ratio"))
            if trades == 0:
                anomalies.append(f"{key}/{seg}: 0 trades")
            if _is_inf(pf):
                anomalies.append(f"{key}/{seg}: PF inf ({trades} trades)")
            if abs(ret) > 200:
                anomalies.append(f"{key}/{seg}: return {ret:+.1f}% ({trades} trades)")
            if _f(m.get("max_drawdown_pct")) > 60:
                anomalies.append(f"{key}/{seg}: MaxDD {_f(m.get('max_drawdown_pct')):.1f}%")
            if not _is_inf(pf) and _f(pf) > 10 and trades < 10:
                anomalies.append(f"{key}/{seg}: too good — PF {_f(pf):.1f} on {trades} trades")
            if sharpe > 3:
                anomalies.append(f"{key}/{seg}: too good — Sharpe {sharpe:.2f} ({trades} trades)")
            liq = (v.get("liquidation") or {}).get(seg)
            if liq and int(liq.get("positions") or 0) > 0 and _f(liq.get("pnl")) > 0:
                anomalies.append(
                    f"{key}/{seg}: liquidation pnl positive ({_f(liq.get('pnl')):+.2f})"
                )
    lines.append(
        f"4. Anomalies (0 trades / PF inf / |return| > 200 % / MaxDD > 60 % / too good / "
        f"liquidation in profit): {len(anomalies)}"
        + (" — " + "; ".join(anomalies) if anomalies else " — none")
    )

    if phase == "1":
        best_by_combo: dict[tuple[str, str], tuple[str, dict[str, Any]]] = {}
        for key, v in ok.items():
            combo = (v.get("strategy", "?"), v.get("pair", "?"))
            cur = best_by_combo.get(combo)
            if cur is None or _f(v["test"].get("sharpe_ratio")) > _f(
                cur[1]["test"].get("sharpe_ratio")
            ):
                best_by_combo[combo] = (key, v)
        lines.append(
            "5. Best test Sharpe per combo (Sharpe / PF / return, n trades; train Sharpe, n): "
            + "; ".join(
                f"{s}×{p.split('/')[0]}: {_f(v['test'].get('sharpe_ratio')):.2f} / "
                f"{_f(v['test'].get('profit_factor')):.2f} / {_f(v['test'].get('total_return_pct')):+.1f}% "
                f"(n={int(_f(v['test'].get('total_trades')))}; train {_f(v['train'].get('sharpe_ratio')):.2f}, "
                f"n={int(_f(v['train'].get('total_trades')))}) params {v.get('params')}"
                for (s, p), (k, v) in sorted(best_by_combo.items())
            )
        )
        pre = [
            k
            for k, v in ok.items()
            if _f(v["test"].get("sharpe_ratio")) > p7_report.MIN_SHARPE_OOS
            and _f(v["test"].get("profit_factor")) > p7_report.MIN_PF_OOS
            and int(_f(v["test"].get("total_trades")))
            >= (
                p7_report.MIN_TRADES_DCA
                if v.get("strategy") in p7_report.LOW_FREQUENCY_STRATEGIES
                else p7_report.MIN_TRADES_DEFAULT
            )
        ]
        lines.append(
            f"6. Phase-1 configs clearing criteria 1-2-4 on the single 70/30 test split "
            f"(informational, the verdict is phase 2): {len(pre)}"
            + (" — " + ", ".join(sorted(pre)) if pre else " — none")
        )
    else:
        aggregates = p7_report.aggregate_walk_forward(results)
        bench = benchmarks or p7_report.BENCHMARK_SHARPE
        verdicts = [p7_report.apply_selection_criteria(a, bench) for a in aggregates.values()]
        passing = [v for v in verdicts if v.passed]
        eligible_passing = [
            v
            for v in passing
            if (v.aggregate.strategy, v.aggregate.pair, v.aggregate.params_hash) not in ineligible
        ]
        best_by_combo2: dict[tuple[str, str], p7_report.ConfigVerdict] = {}
        for v in verdicts:
            combo = (v.aggregate.strategy, v.aggregate.pair)
            if combo not in best_by_combo2 or (
                v.aggregate.mean_sharpe_oos > best_by_combo2[combo].aggregate.mean_sharpe_oos
            ):
                best_by_combo2[combo] = v
        lines.append(
            "5. Best mean OOS Sharpe per combo (Sharpe / PF / MaxDD, consistency, mean n trades; "
            "train Sharpe): "
            + "; ".join(
                f"{s}×{p.split('/')[0]}: {v.aggregate.mean_sharpe_oos:.2f} / {v.aggregate.mean_pf_oos:.2f} / "
                f"{v.aggregate.max_drawdown_global:.1f}% ({v.aggregate.consistency}/{v.aggregate.n_windows}, "
                f"n={v.aggregate.mean_trades_test:.0f}; train {v.aggregate.mean_sharpe_train:.2f}) "
                f"params {v.aggregate.params}"
                + (" [flagged→ineligible]" if (s, p, v.aggregate.params_hash) in ineligible else "")
                for (s, p), v in sorted(best_by_combo2.items())
            )
        )
        lines.append(
            f"6. 7 criteria (unchanged, GO P7 rule 3) over {len(verdicts)} aggregated configs: "
            f"{len(passing)} passing, {len(eligible_passing)} passing AND eligible"
            + (
                " — "
                + "; ".join(
                    f"{v.aggregate.strategy}×{v.aggregate.pair.split('/')[0]}#{v.aggregate.params_hash} "
                    f"Sharpe {v.aggregate.mean_sharpe_oos:.2f} (n={v.aggregate.mean_trades_test:.0f}) "
                    f"beats {v.beats_benchmark}"
                    for v in passing
                )
                if passing
                else " — none"
            )
        )

    grid_liq = [
        (k, seg, v["liquidation"][seg])
        for k, v in ok.items()
        if v.get("liquidation")
        for seg in v["liquidation"]
    ]
    non_zero_div = [
        (k, seg)
        for k, seg, liq in grid_liq
        if abs(_f(liq.get("inventory_divergence_btc"))) > 1e-12
        or _f(liq.get("residual_net_proceeds")) != 0
    ]
    lots = [int(liq.get("positions") or 0) for _, _, liq in grid_liq]
    pnls = [_f(liq.get("pnl")) for _, _, liq in grid_liq]
    lines.append(
        f"7. Grid liquidations: {len(grid_liq)} segments, lots min/max {min(lots) if lots else 0}/"
        f"{max(lots) if lots else 0}, pnl min/max {min(pnls) if pnls else 0:+.2f}/{max(pnls) if pnls else 0:+.2f}, "
        f"{sum(1 for x in lots if x == 0)} with empty inventory, {len(non_zero_div)} not reconciled"
        + (
            " — "
            + ", ".join(f"{k}/{seg}" for k, seg in non_zero_div[:12])
            + (" …" if len(non_zero_div) > 12 else "")
            if non_zero_div
            else ""
        )
    )

    by_strategy: dict[str, list[float]] = {}
    for v in ok.values():
        by_strategy.setdefault(v.get("strategy", "?"), []).append(_f(v["test"].get("sharpe_ratio")))
    lines.append(
        "8. Test Sharpe distribution per strategy (min / median / max over its jobs): "
        + "; ".join(
            f"{s}: {min(x):.2f} / {sorted(x)[len(x) // 2]:.2f} / {max(x):.2f} ({len(x)} jobs)"
            for s, x in sorted(by_strategy.items())
        )
    )
    per_pair = Counter(v.get("pair", "?") for v in ok.values())
    lines.append("9. Jobs per pair: " + ", ".join(f"{p} {n}" for p, n in sorted(per_pair.items())))
    complete = len(ok) == expected and not crashed
    lines.append(
        f"10. Verdict: phase {phase} "
        + ("complete" if complete else "INCOMPLETE")
        + (
            f" → {'phase 2' if phase == '1' else 'report'}"
            if complete
            else " → resume (no --force) or STOP"
        )
        + (
            "; STOP if any crash / flag / anomaly above is unexplained"
            if (crashed or flags or anomalies)
            else "; no crash, no flag, no anomaly"
        )
    )
    return lines


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("results", type=Path)
    parser.add_argument("--benchmarks", type=Path, default=None)
    parser.add_argument("--markdown", type=Path, default=None)
    args = parser.parse_args(argv)
    results = json.loads(args.results.read_text(encoding="utf-8"))
    benchmarks = None
    if args.benchmarks:
        sys.path.insert(0, str(_ROOT / "scripts"))
        import run_p7_grid_search as p7  # noqa: PLC0415

        benchmarks = p7.load_benchmark_sharpe(args.benchmarks)
    lines = summarize(results, benchmarks)
    text = "\n".join(lines) + "\n"
    print(text)
    if args.markdown:
        args.markdown.write_text("# B4 — CHECKPOINT P7\n\n" + text, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
