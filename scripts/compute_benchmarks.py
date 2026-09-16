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

Metrics (C1, ``metrics_version`` 2): both benchmarks go through ``krakenbot.backtest_metrics``
— the same daily resampling, Sharpe / Sortino / Calmar and running-peak drawdown as the
engines. The fixed DCA keeps a cash account and books each weekly deposit as an **external
flow** (end-of-period convention, exact for a buy at the close): its ratios are computed on the
flow-adjusted returns and on the performance index, so the deposits are no longer counted as
returns (defect D6 of the B4 red-team audit) and its drawdown is no longer the 100 % artefact.
"""

from __future__ import annotations

import argparse
import asyncio
from datetime import UTC, datetime, timedelta
from decimal import Decimal
import json
from pathlib import Path
import sys

from dotenv import load_dotenv
from sqlalchemy import select

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from backtest import PairCosts, load_pair_costs  # noqa: E402

from krakenbot.backtest_metrics import (
    METRICS_VERSION,
    EquityPoint,
    ExternalFlow,
    compute_metrics,
    fmt,
)
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


def _round(value: float | None, ndigits: int) -> float | None:
    return None if value is None else round(value, ndigits)


def compute_risk_metrics(
    points: list[EquityPoint],
    *,
    start: datetime,
    end: datetime,
    starting_balance: Decimal,
    flows: list[ExternalFlow] | None = None,
) -> dict[str, float | int | None]:
    """Sharpe, Sortino, MaxDD (daily, running peak), CAGR and Calmar through the shared C1
    module (``None`` = undefined, never a fake 0). The anchor ``(start, starting_balance)`` is
    the capital before the first candle; ``flows`` are the external deposits (fixed DCA)."""
    result = compute_metrics(
        points, [], start=start, end=end, starting_balance=starting_balance, flows=flows or []
    )
    return {
        "metrics_version": METRICS_VERSION,
        "sharpe_ratio": _round(result.sharpe_ratio, 4),
        "sortino_ratio": _round(result.sortino_ratio, 4),
        "max_drawdown_pct_daily": round(result.max_drawdown_pct_daily, 2),
        "cagr_pct": _round(result.cagr_pct, 4),
        "calmar_ratio": _round(result.calmar_ratio, 4),
        "n_daily_returns": result.n_daily_returns,
    }


def _anchor_time(candles: list[OHLCData]) -> datetime:
    """Instant the capital is deployed: the open of the first (period-end stamped) candle."""
    return candles[0].timestamp - timedelta(minutes=candles[0].interval)


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

    coins = Decimal(str(amount))
    points = [EquityPoint(timestamp=c.timestamp, equity=coins * c.close) for c in candles]

    final = float(points[-1].equity)
    total_return_pct = (final - capital) / capital * 100

    metrics: dict = compute_risk_metrics(
        points,
        start=_anchor_time(candles),
        end=candles[-1].timestamp,
        starting_balance=Decimal(str(capital)),
    )
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
    """Simulate DCA: buy $15 every Monday at close price (resting limit: maker fee).

    C1: cash account + external flows. Each weekly deposit is booked as an ``ExternalFlow`` at
    the candle's stamp and converted at that close (cash stays 0 afterwards), the equity is
    ``cash + coins × close``; the ratios come from the flow-adjusted returns and the
    performance index (starting balance 0, anchor before the first candle), so a deposit is
    neither a return nor a way to hide a drawdown. ``total_return_pct`` stays money-weighted
    (final equity vs invested), as before.
    """
    if not candles:
        return {"error": "no data"}

    cash = Decimal("0")
    total_invested = Decimal("0")
    total_coins = Decimal("0")
    points: list[EquityPoint] = []
    flows: list[ExternalFlow] = []
    buys = 0

    last_buy_week: int | None = None

    for c in candles:
        # Buy every Monday (weekday 0)
        iso_week = c.timestamp.isocalendar()[1]
        iso_year = c.timestamp.isocalendar()[0]
        week_key = iso_year * 100 + iso_week

        if c.timestamp.weekday() == 0 and week_key != last_buy_week:
            # Deposit (external flow) then buy at close price, maker fee taken from the notional
            flows.append(ExternalFlow(timestamp=c.timestamp, amount=weekly_amount))
            cash += weekly_amount
            coins = weekly_amount * (Decimal("1") - fees.maker) / c.close
            cash -= weekly_amount
            total_coins += coins
            total_invested += weekly_amount
            buys += 1
            last_buy_week = week_key

        # Equity = cash + coins held × current close
        points.append(EquityPoint(timestamp=c.timestamp, equity=cash + total_coins * c.close))

    if not points or total_invested == 0:
        return {"error": "no trades"}

    final = float(points[-1].equity)
    invested = float(total_invested)
    total_return_pct = (final - invested) / invested * 100

    metrics: dict = compute_risk_metrics(
        points,
        start=_anchor_time(candles),
        end=candles[-1].timestamp,
        starting_balance=Decimal("0"),
        flows=flows,
    )
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
        "metrics_version": METRICS_VERSION,
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
        print(f"    Sharpe: {fmt(bh.get('sharpe_ratio'))}")
        print(f"    Max DD: {fmt(bh.get('max_drawdown_pct_daily'), 1, suffix='%')}")
        print(f"    Calmar: {fmt(bh.get('calmar_ratio'))}")

        # DCA
        dca = dca_fixed_weekly(candles, fees=fees)
        results["dca_fixed_15usd_weekly"][pair] = dca
        print("\n  DCA $15/week:")
        print(f"    Return: {dca.get('total_return_pct', 0):+.1f}%")
        print(f"    Invested: ${dca.get('total_invested', 0):.0f}")
        print(f"    Final: ${dca.get('ending_balance', 0):.0f}")
        print(f"    Buys: {dca.get('num_buys', 0)}")
        print(f"    Sharpe: {fmt(dca.get('sharpe_ratio'))}")
        print(f"    Max DD: {fmt(dca.get('max_drawdown_pct_daily'), 1, suffix='%')}")

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
