"""Phase D — Run 24 cross-validated backtests (8 strategies × 3 pairs).

Imports BacktestEngine/GridBacktester directly and captures structured
metrics for train/test/all periods.

Usage:
    poetry run python scripts/run_p6_backtests.py
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
import json
from pathlib import Path
import sys
import time
import traceback

from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / ".env")

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from krakenbot.config.settings import get_settings
from krakenbot.core.database import DatabaseManager
from krakenbot.core.logger import get_logger

# Import engines from backtest module
sys.path.insert(0, str(Path(__file__).resolve().parent))
from backtest import BacktestEngine, GridBacktester

logger = get_logger().bind(component="p6_backtests")

# --- Configuration ---
STRATEGIES = [
    "grok_grid_atr_adaptive_v4",
    "grok_supertrend_4h",
    "grok_ema_adx_atr",
    "grok_adaptive_dca_weekly",
    "grok_donchian_breakout_4h",
    "gemini_scalping_volatilite",
    "gemini_suivi_tendance_momentum",
    "gemini_retour_moyenne",
]
PAIRS = ["BTC/USDC", "ETH/USDC", "SOL/USDC"]
GRID_STRATEGIES = {"grok_grid_atr_adaptive_v4"}

P6_START = datetime(2023, 4, 1, tzinfo=UTC)
P6_END = datetime(2026, 4, 1, tzinfo=UTC)
TRAIN_RATIO = 0.7
CAPITAL = 1000.0
EXCHANGE = "binance"

OUTPUT_PATH = Path(__file__).resolve().parent.parent / "results" / "P6_phase_d_results.json"


def make_key(strategy: str, pair: str) -> str:
    """Create a unique key for a strategy×pair combination."""
    return f"{strategy}_{pair.replace('/', '_')}"


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


async def run_cross_validated(
    settings: object,
    db_manager: DatabaseManager,
    strategy: str,
    pair: str,
) -> dict:
    """Run cross-validated backtest (train 70% / test 30% / all)."""
    total_duration = P6_END - P6_START
    split_time = P6_START + total_duration * TRAIN_RATIO

    # Train
    train_metrics = await run_single_backtest(
        settings, db_manager, strategy, pair, P6_START, split_time
    )

    # Test
    test_metrics = await run_single_backtest(
        settings, db_manager, strategy, pair, split_time, P6_END
    )

    # Full period
    all_metrics = await run_single_backtest(settings, db_manager, strategy, pair, P6_START, P6_END)

    return {
        "strategy": strategy,
        "pair": pair,
        "exchange": EXCHANGE,
        "period": {
            "start": P6_START.isoformat(),
            "end": P6_END.isoformat(),
            "split": split_time.isoformat(),
        },
        "train": train_metrics,
        "test": test_metrics,
        "all": all_metrics,
    }


async def main() -> None:
    settings = get_settings()
    db_manager = DatabaseManager()
    await db_manager.init_db(settings)

    results: dict = {}
    total = len(STRATEGIES) * len(PAIRS)
    completed = 0
    crashed = 0
    t0 = time.time()

    # Load existing results (resume support)
    if OUTPUT_PATH.exists():
        results = json.loads(OUTPUT_PATH.read_text())
        logger.info("resumed_from_existing", existing_keys=len(results))

    try:
        for strategy in STRATEGIES:
            for pair in PAIRS:
                key = make_key(strategy, pair)
                completed += 1

                if key in results and "error" not in results[key]:
                    logger.info(
                        "skipping_existing",
                        key=key,
                        progress=f"{completed}/{total}",
                    )
                    continue

                logger.info(
                    "backtest_starting",
                    strategy=strategy,
                    pair=pair,
                    progress=f"{completed}/{total}",
                )

                try:
                    result = await run_cross_validated(settings, db_manager, strategy, pair)
                    results[key] = result

                    logger.info(
                        "backtest_complete",
                        key=key,
                        train_return=f"{result['train']['total_return_pct']:+.1f}%",
                        test_return=f"{result['test']['total_return_pct']:+.1f}%",
                        test_sharpe=f"{result['test']['sharpe_ratio']:.2f}",
                        test_trades=result["test"]["total_trades"],
                    )
                except Exception as e:
                    crashed += 1
                    error_msg = f"{type(e).__name__}: {e}"
                    results[key] = {
                        "strategy": strategy,
                        "pair": pair,
                        "error": error_msg,
                        "traceback": traceback.format_exc(),
                    }
                    logger.error(
                        "backtest_crashed",
                        key=key,
                        error=error_msg,
                    )

                # Save after each backtest (crash-resilient)
                OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
                OUTPUT_PATH.write_text(
                    json.dumps(results, indent=2, default=str),
                    encoding="utf-8",
                )

    finally:
        await db_manager.close_db()

    elapsed = time.time() - t0
    ok = total - crashed
    print(f"\n{'=' * 60}")
    print("  P6 Phase D — Summary")
    print(f"{'=' * 60}")
    print(f"  Total combinations: {total}")
    print(f"  Succeeded: {ok}")
    print(f"  Crashed: {crashed}")
    print(f"  Elapsed: {elapsed / 60:.1f} min")
    print(f"  Results: {OUTPUT_PATH}")


if __name__ == "__main__":
    asyncio.run(main())
