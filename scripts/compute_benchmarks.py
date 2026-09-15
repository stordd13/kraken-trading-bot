"""Phase C — Compute Buy-and-Hold and DCA benchmarks for P6 comparison.

Calculates baseline performance for each pair over the P6 period (3 years).

Usage:
    poetry run python scripts/compute_benchmarks.py --fees bybit \
        [--pair-costs-file config/pair_costs_b4.json] [--output results/B4_benchmarks.json]

Fees (B4.3 GATE B, mandatory ``--fees``): the Buy & Hold entry is a market buy (taker +
spread + slippage, per-pair override through ``--pair-costs-file``), each weekly DCA buy is
a resting limit order (maker); positions are valued at the last close without an exit —
the signal engine's convention (no end-of-run liquidation). ``--fees none`` reproduces the
historical fee-free P6 benchmarks.
"""

from __future__ import annotations

import argparse
import asyncio
from datetime import UTC, datetime
from decimal import Decimal
import json
import math
from pathlib import Path
import sys

from dotenv import load_dotenv
from sqlalchemy import select

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from backtest import PairCosts, load_pair_costs  # noqa: E402

from krakenbot.config.settings import FEE_MODEL_NAMES, ExchangeFees, Settings
from krakenbot.core.database import DatabaseManager
from krakenbot.models.market_data import OHLCData

NO_FEES = ExchangeFees(
    maker=Decimal("0"), taker=Decimal("0"), spread=Decimal("0"), slippage=Decimal("0")
)

# P6 period
P6_START = datetime(2023, 4, 1, tzinfo=UTC)
P6_END = datetime(2026, 4, 1, tzinfo=UTC)

PAIRS = ["BTC/USDC", "ETH/USDC", "SOL/USDC"]
EXCHANGE = "binance"
DCA_AMOUNT = Decimal("15")  # $15 per week


def compute_risk_metrics(
    equity_curve: list[tuple[datetime, float]],
    starting_balance: float,
) -> dict[str, float]:
    """Compute Sharpe, Sortino, MaxDD, Calmar from an equity curve."""
    if len(equity_curve) < 2:
        return {
            "sharpe_ratio": 0.0,
            "sortino_ratio": 0.0,
            "max_drawdown_pct": 0.0,
            "calmar_ratio": 0.0,
        }

    # Returns
    returns = []
    for i in range(1, len(equity_curve)):
        prev = equity_curve[i - 1][1]
        curr = equity_curve[i][1]
        if prev > 0:
            returns.append((curr - prev) / prev)

    # Sharpe
    sharpe = 0.0
    if returns:
        avg_ret = sum(returns) / len(returns)
        variance = sum((r - avg_ret) ** 2 for r in returns) / len(returns)
        std_dev = math.sqrt(variance)
        if std_dev > 0:
            sharpe = (avg_ret / std_dev) * math.sqrt(365)

    # Sortino
    sortino = 0.0
    if returns:
        avg_ret = sum(returns) / len(returns)
        neg_returns = [r for r in returns if r < 0]
        if neg_returns:
            ds_var = sum(r**2 for r in neg_returns) / len(returns)
            ds_std = math.sqrt(ds_var)
            if ds_std > 0:
                sortino = (avg_ret / ds_std) * math.sqrt(365)

    # Max drawdown
    peak = starting_balance
    max_dd = 0.0
    for _ts, equity in equity_curve:
        if equity > peak:
            peak = equity
        dd = (peak - equity) / peak * 100 if peak > 0 else 0
        if dd > max_dd:
            max_dd = dd

    # Calmar
    final = equity_curve[-1][1]
    total_return_pct = (final - starting_balance) / starting_balance * 100
    duration_days = (equity_curve[-1][0] - equity_curve[0][0]).total_seconds() / 86400
    calmar = 0.0
    if max_dd > 0 and duration_days > 0:
        annualized = total_return_pct * (365 / duration_days)
        calmar = annualized / max_dd

    return {
        "sharpe_ratio": round(sharpe, 4),
        "sortino_ratio": round(sortino, 4),
        "max_drawdown_pct": round(max_dd, 2),
        "calmar_ratio": round(calmar, 4),
    }


async def load_daily_candles(db_manager: DatabaseManager, pair: str) -> list[OHLCData]:
    """Load daily candles for a pair in the P6 period."""
    async with db_manager.read_session() as session:
        stmt = (
            select(OHLCData)
            .where(OHLCData.pair == pair)
            .where(OHLCData.interval == 1440)
            .where(OHLCData.exchange == EXCHANGE)
            .where(OHLCData.timestamp >= P6_START)
            .where(OHLCData.timestamp < P6_END)
            .order_by(OHLCData.timestamp.asc())
        )
        result = await session.execute(stmt)
        return list(result.scalars().all())


def _costs(fees: ExchangeFees, pair_costs: dict[str, PairCosts] | None, pair: str):
    override = (pair_costs or {}).get(pair)
    if override is None:
        return fees.spread, fees.slippage
    return override.spread, override.slippage


def buy_and_hold(
    candles: list[OHLCData],
    capital: float = 1000.0,
    *,
    fees: ExchangeFees = NO_FEES,
    pair_costs: dict[str, PairCosts] | None = None,
) -> dict:
    """Simulate Buy and Hold: market buy at the first candle open, hold until end.

    With a fee model the entry pays taker + spread + slippage on the notional (the coins
    bought are ``capital × (1 − taker) / (open × (1 + spread + slippage))``).
    """
    if not candles:
        return {"error": "no data"}

    pair = candles[0].pair
    spread, slippage = _costs(fees, pair_costs, pair)
    entry_price = float(candles[0].open * (Decimal("1") + spread + slippage))
    amount = capital * float(Decimal("1") - fees.taker) / entry_price

    equity_curve: list[tuple[datetime, float]] = []
    for c in candles:
        equity = amount * float(c.close)
        equity_curve.append((c.timestamp, equity))

    final = equity_curve[-1][1]
    total_return_pct = (final - capital) / capital * 100

    metrics = compute_risk_metrics(equity_curve, capital)
    metrics["total_return_pct"] = round(total_return_pct, 2)
    metrics["starting_balance"] = capital
    metrics["ending_balance"] = round(final, 2)
    metrics["entry_price"] = entry_price
    metrics["exit_price"] = float(candles[-1].close)
    metrics["entry_fee_usdc"] = round(capital * float(fees.taker), 4)
    return metrics


def dca_fixed_weekly(
    candles: list[OHLCData],
    weekly_amount: Decimal = DCA_AMOUNT,
    *,
    fees: ExchangeFees = NO_FEES,
) -> dict:
    """Simulate DCA: buy $15 every Monday at close price (resting limit: maker fee)."""
    if not candles:
        return {"error": "no data"}

    total_invested = Decimal("0")
    total_coins = Decimal("0")
    equity_curve: list[tuple[datetime, float]] = []
    buys = 0

    last_buy_week: int | None = None

    for c in candles:
        # Buy every Monday (weekday 0)
        iso_week = c.timestamp.isocalendar()[1]
        iso_year = c.timestamp.isocalendar()[0]
        week_key = iso_year * 100 + iso_week

        if c.timestamp.weekday() == 0 and week_key != last_buy_week:
            # Buy at close price, maker fee taken from the notional
            coins = weekly_amount * (Decimal("1") - fees.maker) / c.close
            total_coins += coins
            total_invested += weekly_amount
            buys += 1
            last_buy_week = week_key

        # Equity = coins held × current close
        equity = float(total_coins * c.close)
        equity_curve.append((c.timestamp, equity))

    if not equity_curve or total_invested == 0:
        return {"error": "no trades"}

    final = equity_curve[-1][1]
    invested = float(total_invested)
    total_return_pct = (final - invested) / invested * 100

    metrics = compute_risk_metrics(equity_curve, float(weekly_amount))
    metrics["total_return_pct"] = round(total_return_pct, 2)
    metrics["total_invested"] = invested
    metrics["ending_balance"] = round(final, 2)
    metrics["num_buys"] = buys
    metrics["avg_cost_basis"] = round(invested / float(total_coins), 2) if total_coins > 0 else 0
    return metrics


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="P6/B4 Buy & Hold and DCA benchmarks.")
    parser.add_argument(
        "--fees",
        choices=(*FEE_MODEL_NAMES, "none"),
        required=True,
        help="Fee model (bybit | binance | kraken) or 'none' (historical fee-free benchmarks).",
    )
    parser.add_argument(
        "--pair-costs-file",
        type=Path,
        default=None,
        help="Per-pair spread/slippage JSON applied to the Buy & Hold market entry.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path(__file__).resolve().parent.parent / "results" / "P6_benchmarks.json",
        help="Output JSON (default: results/P6_benchmarks.json).",
    )
    args = parser.parse_args(argv)
    args.pair_costs = None
    if args.pair_costs_file is not None:
        try:
            args.pair_costs = load_pair_costs(args.pair_costs_file)
        except (OSError, ValueError) as exc:
            parser.error(f"--pair-costs-file: {exc}")
    return args


async def run(args: argparse.Namespace) -> None:
    settings = Settings()
    db_manager = DatabaseManager()
    await db_manager.init_db(settings)
    fees = NO_FEES if args.fees == "none" else ExchangeFees.from_name(args.fees)

    results: dict = {
        "period": {
            "start": P6_START.strftime("%Y-%m-%d"),
            "end": P6_END.strftime("%Y-%m-%d"),
        },
        "fees": args.fees,
        "pair_costs": (
            {
                p: {"spread": str(c.spread), "slippage": str(c.slippage)}
                for p, c in args.pair_costs.items()
            }
            if args.pair_costs
            else None
        ),
        "buy_and_hold": {},
        "dca_fixed_15usd_weekly": {},
    }

    for pair in PAIRS:
        print(f"\n{'=' * 60}")
        print(f"  {pair}")
        print(f"{'=' * 60}")

        candles = await load_daily_candles(db_manager, pair)
        print(f"  Daily candles loaded: {len(candles)}")

        if not candles:
            print(f"  WARNING: No daily candles for {pair}")
            results["buy_and_hold"][pair] = {"error": "no data"}
            results["dca_fixed_15usd_weekly"][pair] = {"error": "no data"}
            continue

        print(f"  Period: {candles[0].timestamp.date()} → {candles[-1].timestamp.date()}")

        # Buy & Hold
        bh = buy_and_hold(candles, fees=fees, pair_costs=args.pair_costs)
        results["buy_and_hold"][pair] = bh
        print("\n  Buy & Hold:")
        print(f"    Return: {bh.get('total_return_pct', 0):+.1f}%")
        print(f"    Sharpe: {bh.get('sharpe_ratio', 0):.2f}")
        print(f"    Max DD: {bh.get('max_drawdown_pct', 0):.1f}%")
        print(f"    Calmar: {bh.get('calmar_ratio', 0):.2f}")

        # DCA
        dca = dca_fixed_weekly(candles, fees=fees)
        results["dca_fixed_15usd_weekly"][pair] = dca
        print("\n  DCA $15/week:")
        print(f"    Return: {dca.get('total_return_pct', 0):+.1f}%")
        print(f"    Invested: ${dca.get('total_invested', 0):.0f}")
        print(f"    Final: ${dca.get('ending_balance', 0):.0f}")
        print(f"    Buys: {dca.get('num_buys', 0)}")
        print(f"    Sharpe: {dca.get('sharpe_ratio', 0):.2f}")
        print(f"    Max DD: {dca.get('max_drawdown_pct', 0):.1f}%")

    await db_manager.close_db()

    # Save JSON
    output_path: Path = args.output
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(results, indent=2, default=str), encoding="utf-8")
    print(f"\n\nBenchmarks saved to: {output_path}")


def main(argv: list[str] | None = None) -> int:
    # Load .env here, not at import time (see run_p6_backtests.main).
    load_dotenv(Path(__file__).parent.parent / ".env")
    asyncio.run(run(parse_args(argv)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
