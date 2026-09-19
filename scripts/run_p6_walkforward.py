"""Phase F — Walk-forward validation on P6 survivors.

Runs each survivor strategy on 8 rolling 3-month test windows
(12-month train, 3-month test, advance 3 months) to validate
temporal stability.

Usage:
    poetry run python scripts/run_p6_walkforward.py
"""

from __future__ import annotations

import argparse
import asyncio
from datetime import UTC, datetime
import json
from pathlib import Path
import sys
import time

from dateutil.relativedelta import relativedelta
from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from krakenbot.backtest_metrics import METRICS_VERSION, entry_metrics_version, fmt, mean_available
from krakenbot.config.settings import FEE_MODEL_NAMES, get_settings
from krakenbot.core.database import DatabaseManager
from krakenbot.core.logger import get_logger
from krakenbot.replay_contract import REPLAY_VERSION, entry_replay_version

sys.path.insert(0, str(Path(__file__).resolve().parent))
from backtest import BacktestEngine, GridBacktester, PairCosts, load_pair_costs

logger = get_logger().bind(component="p6_walkforward")

# --- Configuration ---
P6_START = datetime(2023, 4, 1, tzinfo=UTC)
P6_END = datetime(2026, 4, 1, tzinfo=UTC)
TRAIN_MONTHS = 12
TEST_MONTHS = 3
CAPITAL = 1000.0
EXCHANGE = "binance"
GRID_STRATEGIES = {"grok_grid_atr_adaptive_v4"}

RESULTS_DIR = Path(__file__).resolve().parent.parent / "results"
SURVIVORS_PATH = RESULTS_DIR / "P6_phase_e_survivors.json"
OUTPUT_PATH = RESULTS_DIR / "P6_phase_f_walkforward.json"


def generate_windows(
    start: datetime, end: datetime, train_months: int, test_months: int
) -> list[dict]:
    """Generate walk-forward windows.

    Each window has a train period and a test period.
    Windows advance by test_months each step.
    """
    windows = []
    window_start = start

    while True:
        train_end = window_start + relativedelta(months=train_months)
        test_end = train_end + relativedelta(months=test_months)

        if test_end > end:
            break

        windows.append(
            {
                "train_start": window_start,
                "train_end": train_end,
                "test_start": train_end,
                "test_end": test_end,
            }
        )
        window_start += relativedelta(months=test_months)

    return windows


async def run_single_backtest(
    settings: object,
    db_manager: DatabaseManager,
    strategy: str,
    pair: str,
    start: datetime,
    end: datetime,
    *,
    fee_model: str,
    pair_costs: dict[str, PairCosts] | None = None,
    min_order_usdc: float = 1.0,
) -> tuple[dict, dict | None, dict | None, dict]:
    """Run a single backtest; return (metrics dict, grid liquidation summary or None, daily
    equity grid or None — C1, replay blocks — C2: rejections / warmup / dca_counters)."""
    cls = GridBacktester if strategy in GRID_STRATEGIES else BacktestEngine
    engine = cls(
        settings,
        db_manager,
        strategy_name=strategy,
        candle_interval=5,
        exchange=EXCHANGE,
        starting_capital=CAPITAL,
        fee_model=fee_model,
        pair_costs=pair_costs,
        min_order_usdc=min_order_usdc,
    )

    await engine.run(pair, start, end)
    liquidation = engine.liquidation_summary() if hasattr(engine, "liquidation_summary") else None
    equity_daily = getattr(engine.metrics, "equity_daily_dict", lambda: None)()
    replay = {  # C2: rejections per (order, cause), warmup really fed, DCA counters (None outside DCA)
        "rejections": getattr(engine, "rejections_summary", lambda: None)(),
        "warmup": getattr(engine, "warmup_summary", lambda: None)(),
        "dca_counters": getattr(engine, "dca_counters_summary", lambda: None)(),
    }
    return engine.metrics.to_dict(), liquidation, equity_daily, replay


def aggregate_windows(
    window_results: list[dict], n_windows: int
) -> tuple[dict[str, float | int | None], dict[str, int], int, float]:
    """C1 None-aware summary of the valid windows: per-metric mean over the windows that
    define it (``None`` when none does) with the count used, and the consistency score
    (windows whose test Sharpe is defined and > 0)."""
    valid = [w for w in window_results if "metrics" in w]
    sharpes = [w["metrics"].get("sharpe_ratio") for w in valid]
    positive = sum(1 for s in sharpes if s is not None and s > 0)
    consistency = positive / n_windows if n_windows else 0.0
    mean_metrics: dict[str, float | int | None] = {}
    n_defined: dict[str, int] = {}
    if valid:
        for key in valid[0]["metrics"]:
            if key == "metrics_version":
                mean_metrics[key] = METRICS_VERSION
                continue
            values = [w["metrics"].get(key) for w in valid]
            numeric = [float(v) for v in values if isinstance(v, int | float)]
            mean, n = mean_available(numeric if numeric else [None])
            mean_metrics[key] = round(mean, 4) if mean is not None else None
            n_defined[key] = n
    return mean_metrics, n_defined, positive, consistency


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="P6 Phase F walk-forward validation.")
    parser.add_argument(
        "--fees",
        choices=FEE_MODEL_NAMES,
        required=True,
        help=(
            "Fee model applied by the engines (bybit | binance | kraken); the survivors file "
            "must have been produced under the same model. No default."
        ),
    )
    parser.add_argument("--survivors", type=Path, default=SURVIVORS_PATH)
    parser.add_argument("--output", type=Path, default=OUTPUT_PATH)
    parser.add_argument(
        "--pair-costs-file",
        type=Path,
        default=None,
        help="Per-pair spread/slippage JSON (B4.3 campaign); must match the survivors' file.",
    )
    parser.add_argument(
        "--min-order-usdc",
        type=float,
        default=1.0,
        help="Smallest BUY notional (default 1.0; B4.3 campaign: 5); must match the survivors.",
    )
    args = parser.parse_args(argv)
    args.pair_costs = None
    if args.pair_costs_file is not None:
        try:
            args.pair_costs = load_pair_costs(args.pair_costs_file)
        except (OSError, ValueError) as exc:
            parser.error(f"--pair-costs-file: {exc}")
    return args


async def main(argv: list[str] | None = None) -> int:
    # Load .env here, not at import time (see run_p6_backtests.main).
    load_dotenv(Path(__file__).parent.parent / ".env")
    args = parse_args(argv)
    survivors_path: Path = args.survivors
    output_path: Path = args.output
    if not survivors_path.exists():
        print(f"ERROR: {survivors_path} not found. Run Phase E first.", file=sys.stderr)
        return 1

    survivors = json.loads(survivors_path.read_text())
    if not survivors:
        print("No survivors to validate. Exiting.")
        return 0
    # Survivors are verbatim P6 result entries: they carry the fee model and the campaign
    # costs they were selected under.
    wanted_costs = str(args.pair_costs_file) if args.pair_costs_file else None
    for key, data in survivors.items():
        if data.get("fees") != args.fees:
            print(
                f"ERROR: survivor {key} was selected under fees="
                f"{data.get('fees', '<absent: pre-B4.2 file>')}, not --fees {args.fees}; "
                "regenerate the survivors from a P6 results file produced with the same --fees.",
                file=sys.stderr,
            )
            return 2
        existing_costs = (data.get("pair_costs_file"), float(data.get("min_order_usdc", 1.0)))
        if existing_costs != (wanted_costs, float(args.min_order_usdc)):
            print(
                f"ERROR: survivor {key} was selected with (pair_costs_file, min_order_usdc)="
                f"{existing_costs}, not {(wanted_costs, float(args.min_order_usdc))}; pass the "
                "same --pair-costs-file / --min-order-usdc as the P6 run.",
                file=sys.stderr,
            )
            return 2
        found = entry_metrics_version(data)
        if found != METRICS_VERSION:  # C1: one metrics contract, never a pre-C1 survivor
            print(
                f"ERROR: survivor {key} carries metrics_version="
                f"{found if found is not None else '<absent: pre-C1 file>'}, not "
                f"{METRICS_VERSION}; regenerate the survivors from a phase-D file produced by "
                "this code.",
                file=sys.stderr,
            )
            return 2
        found_replay = entry_replay_version(data)
        if found_replay != REPLAY_VERSION:  # C2: one replay contract, never a pre-C2 survivor
            print(
                f"ERROR: survivor {key} carries replay_version="
                f"{found_replay if found_replay is not None else '<absent: pre-C2 file>'}, not "
                f"{REPLAY_VERSION}; regenerate the survivors from a phase-D file produced by "
                "this code.",
                file=sys.stderr,
            )
            return 2
    print(
        f"Fee model: {args.fees}; pair costs: {wanted_costs or 'model globals'}; "
        f"min order: {args.min_order_usdc} USDC"
    )

    settings = get_settings()
    db_manager = DatabaseManager()
    await db_manager.init_db(settings)

    windows = generate_windows(P6_START, P6_END, TRAIN_MONTHS, TEST_MONTHS)
    print(f"Walk-forward windows: {len(windows)}")
    for i, w in enumerate(windows):
        print(
            f"  [{i}] Train: {w['train_start'].date()} → {w['train_end'].date()} | "
            f"Test: {w['test_start'].date()} → {w['test_end'].date()}"
        )

    results: dict = {}
    t0 = time.time()

    try:
        for key, data in survivors.items():
            strategy = data["strategy"]
            pair = data["pair"]
            logger.info("walkforward_starting", strategy=strategy, pair=pair)

            window_results = []
            for i, w in enumerate(windows):
                try:
                    # Only run the TEST window (no re-training in P6)
                    test_metrics, liquidation, equity_daily, replay = await run_single_backtest(
                        settings,
                        db_manager,
                        strategy,
                        pair,
                        w["test_start"],
                        w["test_end"],
                        fee_model=args.fees,
                        pair_costs=args.pair_costs,
                        min_order_usdc=args.min_order_usdc,
                    )
                    window_results.append(
                        {
                            "window": i,
                            "train_start": w["train_start"].isoformat(),
                            "train_end": w["train_end"].isoformat(),
                            "test_start": w["test_start"].isoformat(),
                            "test_end": w["test_end"].isoformat(),
                            "metrics": test_metrics,
                            "liquidation": liquidation,
                            "equity_daily": equity_daily,
                            **replay,  # C2: rejections, warmup, dca_counters
                        }
                    )
                    logger.info(
                        "window_complete",
                        strategy=strategy,
                        pair=pair,
                        window=i,
                        sharpe=fmt(test_metrics.get("sharpe_ratio")),
                        return_pct=f"{test_metrics['total_return_pct']:+.1f}%",
                    )
                except Exception as e:
                    window_results.append(
                        {
                            "window": i,
                            "test_start": w["test_start"].isoformat(),
                            "test_end": w["test_end"].isoformat(),
                            "error": str(e),
                        }
                    )
                    logger.error(
                        "window_crashed",
                        strategy=strategy,
                        pair=pair,
                        window=i,
                        error=str(e),
                    )

            # Aggregate (C1: None-aware means with the number of windows used)
            valid_windows = [w for w in window_results if "metrics" in w]
            mean_metrics, n_defined, positive_sharpe_count, consistency_score = aggregate_windows(
                window_results, len(windows)
            )

            results[key] = {
                "strategy": strategy,
                "pair": pair,
                "fees": args.fees,
                "metrics_version": METRICS_VERSION,
                "replay_version": REPLAY_VERSION,  # C2
                "pair_costs_file": wanted_costs,
                "min_order_usdc": args.min_order_usdc,
                "windows": window_results,
                "mean_metrics": mean_metrics,
                "mean_metrics_n": n_defined,
                "consistency_score": round(consistency_score, 2),
                "positive_windows": positive_sharpe_count,
                "total_windows": len(windows),
                "valid_windows": len(valid_windows),
            }

            logger.info(
                "walkforward_complete",
                strategy=strategy,
                pair=pair,
                consistency=f"{consistency_score:.0%}",
                mean_sharpe=fmt(mean_metrics.get("sharpe_ratio")),
                mean_return=f"{mean_metrics.get('total_return_pct', 0):+.1f}%",
            )

            # Save progressively
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_text(json.dumps(results, indent=2, default=str), encoding="utf-8")

    finally:
        await db_manager.close_db()

    elapsed = time.time() - t0
    print(f"\n{'=' * 60}")
    print("  P6 Phase F — Walk-Forward Summary")
    print(f"{'=' * 60}")
    print(f"  Survivors tested: {len(results)}")
    print(f"  Elapsed: {elapsed / 60:.1f} min")

    for _key, r in results.items():
        cs = r["consistency_score"]
        ms = r["mean_metrics"].get("sharpe_ratio")
        flag = "OK" if cs >= 0.5 else "AT RISK"
        print(
            f"  {r['strategy']:40s} {r['pair']:10s} "
            f"consistency={cs:.0%} mean_sharpe={fmt(ms)} [{flag}]"
        )

    print(f"\n  Results: {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
