"""B4.3 campaign — post-P6 CHECKPOINT summary (GO GATE B sequence, before P7 phase 1).

Pure, read-only. Reads the P6 phase-D results file (and optionally the benchmarks file) and
prints the ten-line checkpoint Bruno asked for: completion (n/24), survivors of the 5 strict
criteria (+ consistency + benchmark, same code as ``filter_p6_survivors``), runs flagged by the
campaign rule (``b4_flags``), anomalies (crashes, PF inf / 0 trades / extreme returns / grid
liquidation not reconciled / min-order skips), campaign signature and timings.

Usage::

    poetry run python scripts/audit/b4_p6_checkpoint.py results/B4_P6_phase_d_results.json \\
        [--benchmarks results/B4_benchmarks.json] [--markdown out.md]
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
import filter_p6_survivors as f6  # noqa: E402

STRATEGIES_EXPECTED = 8
PAIRS_EXPECTED = 3


def _f(v: Any, default: float = 0.0) -> float:
    try:
        x = float(v)
    except (TypeError, ValueError):
        return default
    return x


def summarize(results: dict[str, Any], benchmarks: dict[str, Any] | None) -> list[str]:
    entries = {k: v for k, v in results.items() if isinstance(v, dict)}
    ok = {k: v for k, v in entries.items() if "error" not in v}
    crashed = {k: v for k, v in entries.items() if "error" in v}
    expected = STRATEGIES_EXPECTED * PAIRS_EXPECTED
    lines: list[str] = []
    lines.append(
        f"1. Completion: {len(ok)}/{expected} combos succeeded, {len(crashed)} crashed, "
        f"{expected - len(entries)} missing"
        + (f" — crashed: {', '.join(sorted(crashed))}" if crashed else "")
    )
    sigs = Counter(
        (v.get("fees"), v.get("pair_costs_file"), v.get("min_order_usdc")) for v in ok.values()
    )
    lines.append(
        "2. Campaign signature (fees, pair_costs_file, min_order_usdc): "
        + "; ".join(f"{s} x{n}" for s, n in sigs.items())
    )
    survivors, failures_by_key = [], {}
    for key, data in ok.items():
        fails = f6.check_criteria(data.get("test", {}), data.get("strategy", key))
        warn = f6.check_consistency(data.get("train", {}), data.get("test", {}))
        if warn:
            fails.append(warn)
        if benchmarks and not f6.check_beats_benchmark(
            data.get("test", {}), data.get("pair", "?"), benchmarks
        ):
            fails.append("Does not beat any benchmark in Sharpe")
        failures_by_key[key] = fails
        if not fails:
            survivors.append(key)
    lines.append(
        f"3. Survivors (5 strict criteria + consistency + benchmark): {len(survivors)}"
        + (" — " + ", ".join(survivors) if survivors else " — none")
    )
    best = sorted(ok.items(), key=lambda kv: -_f(kv[1].get("test", {}).get("sharpe_ratio")))[:3]
    lines.append(
        "4. Best test Sharpe: "
        + "; ".join(
            f"{k} Sharpe {_f(v['test'].get('sharpe_ratio')):.2f} PF {_f(v['test'].get('profit_factor')):.2f} "
            f"ret {_f(v['test'].get('total_return_pct')):+.1f}% trades {int(_f(v['test'].get('total_trades')))}"
            for k, v in best
        )
    )
    flags = b4_flags.collect_flags(results)
    lines.append(
        f"5. Flag rule (divergence / formula vs cash): {len(flags)} flagged"
        + (
            " — "
            + "; ".join(f"{f['run']}/{f['segment']}: {'; '.join(f['reasons'])}" for f in flags)
            if flags
            else " — none"
        )
    )
    anomalies: list[str] = []
    for key, v in ok.items():
        for seg in ("train", "test", "all"):
            m = v.get(seg, {})
            trades = int(_f(m.get("total_trades")))
            pf = m.get("profit_factor")
            ret = _f(m.get("total_return_pct"))
            if trades == 0:
                anomalies.append(f"{key}/{seg}: 0 trades")
            if pf in (float("inf"), "Infinity") or (isinstance(pf, float) and pf == float("inf")):
                anomalies.append(f"{key}/{seg}: PF inf ({trades} trades)")
            if abs(ret) > 200:
                anomalies.append(f"{key}/{seg}: return {ret:+.1f}%")
            if _f(m.get("max_drawdown_pct")) > 60:
                anomalies.append(f"{key}/{seg}: MaxDD {_f(m.get('max_drawdown_pct')):.1f}%")
            liq = (v.get("liquidation") or {}).get(seg)
            if liq and int(liq.get("positions") or 0) > 0 and _f(liq.get("pnl")) > 0:
                anomalies.append(
                    f"{key}/{seg}: liquidation pnl positive ({_f(liq.get('pnl')):+.2f})"
                )
    lines.append(
        f"6. Anomalies: {len(anomalies)}"
        + (" — " + "; ".join(anomalies) if anomalies else " — none")
    )
    grid_liq = [
        (k, seg, v["liquidation"][seg])
        for k, v in ok.items()
        if v.get("liquidation")
        for seg in v["liquidation"]
    ]
    lines.append(
        f"7. Grid liquidations: {len(grid_liq)} segments — "
        + "; ".join(
            f"{k}/{seg}: {int(liq.get('positions') or 0)} lots pnl {_f(liq.get('pnl')):+.2f} fees {_f(liq.get('fees')):.2f} "
            f"residual {liq.get('residual_net_proceeds')} div {liq.get('inventory_divergence_btc')}"
            for k, seg, liq in grid_liq
        )
    )
    reasons = Counter(f.split(" ")[0] for fails in failures_by_key.values() for f in fails)
    lines.append(
        "8. Failure reasons (first token): "
        + ", ".join(f"{r} x{n}" for r, n in reasons.most_common())
    )
    by_strategy: dict[str, list[str]] = {}
    for v in ok.values():
        by_strategy.setdefault(v.get("strategy", "?"), []).append(
            f"{v.get('pair', '?').split('/')[0]} {_f(v['test'].get('sharpe_ratio')):.2f}/{_f(v['test'].get('profit_factor')):.2f}"
        )
    lines.append(
        "9. Per strategy (test Sharpe/PF per pair): "
        + "; ".join(f"{s}: {', '.join(x)}" for s, x in sorted(by_strategy.items()))
    )
    lines.append(
        "10. Verdict for P7: "
        + (
            f"{len(survivors)} survivor(s) → P7 on the survivors"
            if survivors
            else "0 survivors → P7 on the 4 historical grid-search strategies (brief § 6.2)"
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
    benchmarks = (
        json.loads(args.benchmarks.read_text(encoding="utf-8")) if args.benchmarks else None
    )
    lines = summarize(results, benchmarks)
    text = "\n".join(lines) + "\n"
    print(text)
    if args.markdown:
        args.markdown.write_text("# B4 — CHECKPOINT post-P6\n\n" + text, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
