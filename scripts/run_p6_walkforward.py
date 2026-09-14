"""Phase F — Walk-forward validation on P6 survivors.

Runs each survivor strategy on 8 rolling 3-month test windows
(12-month train, 3-month test, advance 3 months) to validate
temporal stability.

Usage:
    poetry run python scripts/run_p6_walkforward.py
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
import json
from pathlib import Path
import sys
import time

from dateutil.relativedelta import relativedelta
from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from krakenbot.config.settings import get_settings
from krakenbot.core.database import DatabaseManager
from krakenbot.core.logger import get_logger

sys.path.insert(0, str(Path(__file__).resolve().parent))
from backtest import BacktestEngine, GridBacktester

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
) -> dict:
    """Run a single backtest and return metrics dict."""
    if strategy in GRID_STRATEGIES:
        engine = GridBacktester(
            settings,
            db_manager,
            strategy_name=strategy,
            candle_interval=5,
            exchange=EXCHANGE,
            starting_capital=CAPITAL,
        )
    else:
        engine = BacktestEngine(
            settings,
            db_manager,
            strategy_name=strategy,
            candle_interval=5,
            exchange=EXCHANGE,
            starting_capital=CAPITAL,
        )

    await engine.run(pair, start, end)
    return engine.metrics.to_dict()


async def main() -> None:
    # Load .env here, not at import time (see run_p6_backtests.main).
    load_dotenv(Path(__file__).parent.parent / ".env")
    if not SURVIVORS_PATH.exists():
        print(f"ERROR: {SURVIVORS_PATH} not found. Run Phase E first.")
        sys.exit(1)

    survivors = json.loads(SURVIVORS_PATH.read_text())
    if not survivors:
        print("No survivors to validate. Exiting.")
        sys.exit(0)

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
                    test_metrics = await run_single_backtest(
                        settings,
                        db_manager,
                        strategy,
                        pair,
                        w["test_start"],
                        w["test_end"],
                    )
                    window_results.append(
                        {
                            "window": i,
                            "train_start": w["train_start"].isoformat(),
                            "train_end": w["train_end"].isoformat(),
                            "test_start": w["test_start"].isoformat(),
                            "test_end": w["test_end"].isoformat(),
                            "metrics": test_metrics,
                        }
                    )
                    logger.info(
                        "window_complete",
                        strategy=strategy,
                        pair=pair,
                        window=i,
                        sharpe=f"{test_metrics['sharpe_ratio']:.2f}",
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

            # Aggregate
            valid_windows = [w for w in window_results if "metrics" in w]
            sharpes = [w["metrics"]["sharpe_ratio"] for w in valid_windows]

            positive_sharpe_count = sum(1 for s in sharpes if s > 0)
            consistency_score = positive_sharpe_count / len(windows) if windows else 0

            mean_metrics = {}
            if valid_windows:
                # Average across all metric keys
                all_keys = valid_windows[0]["metrics"].keys()
                for mk in all_keys:
                    vals = [w["metrics"][mk] for w in valid_windows]
                    mean_metrics[mk] = round(sum(vals) / len(vals), 4)

            results[key] = {
                "strategy": strategy,
                "pair": pair,
                "windows": window_results,
                "mean_metrics": mean_metrics,
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
                mean_sharpe=f"{mean_metrics.get('sharpe_ratio', 0):.2f}",
                mean_return=f"{mean_metrics.get('total_return_pct', 0):+.1f}%",
            )

            # Save progressively
            OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
            OUTPUT_PATH.write_text(json.dumps(results, indent=2, default=str), encoding="utf-8")

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
        ms = r["mean_metrics"].get("sharpe_ratio", 0)
        flag = "OK" if cs >= 0.5 else "AT RISK"
        print(
            f"  {r['strategy']:40s} {r['pair']:10s} "
            f"consistency={cs:.0%} mean_sharpe={ms:.2f} [{flag}]"
        )

    print(f"\n  Results: {OUTPUT_PATH}")


if __name__ == "__main__":
    asyncio.run(main())
