"""Analyze Kraken Futures PF_XBTUSD funding rate history and simulate a simple
delta-neutral cash-and-carry strategy.

Usage:
    poetry run python scripts/analyze_funding_arb_kraken.py --months 12
"""

from __future__ import annotations

import argparse
import asyncio
from datetime import UTC, datetime, timedelta
from decimal import Decimal
import json
from pathlib import Path
import statistics

from dotenv import load_dotenv

# Load .env.local first (override), then .env as fallback — must run before
# krakenbot imports so env vars are visible to Settings().
_env_local = Path(__file__).parent.parent / ".env.local"
_env_file = Path(__file__).parent.parent / ".env"
if _env_local.exists():
    load_dotenv(_env_local, override=True)
load_dotenv(_env_file)

import structlog  # noqa: E402

from krakenbot.config.settings import Settings  # noqa: E402
from krakenbot.connectors.kraken_futures_rest import KrakenFuturesClient  # noqa: E402

log = structlog.get_logger()

# Constants
TOTAL_FEES_ROUND_TRIP = Decimal("0.0036")  # 0.36% all maker
FUNDING_THRESHOLD_BUY_BPS = Decimal("0.0000005") # 0.00005% / hour — very permissive
FUNDING_THRESHOLD_SELL_BPS = Decimal("-0.00001")  # Close only when clearly negative (-0.001%/h) to avoid noise flapping


async def fetch_funding_history(
    client: KrakenFuturesClient,
    pair: str,
    months: int,
) -> list[dict]:
    """Fetch the full funding rate history for the last N months."""
    now = datetime.now(UTC)
    since = now - timedelta(days=months * 30)
    since_ms = int(since.timestamp() * 1000)

    log.info("fetching_funding_history", pair=pair, since=since.isoformat())

    all_rates: list[dict] = []
    current_since = since_ms
    batch_limit = 100

    while True:
        batch = await client.get_funding_history(
            pair=pair, since_ms=current_since, limit=batch_limit
        )
        if not batch:
            break
        all_rates.extend(batch)
        last_ts = batch[-1]["timestamp"]
        if last_ts <= current_since:
            break
        current_since = last_ts + 1
        await asyncio.sleep(0.1)

    log.info("funding_history_fetched", count=len(all_rates))
    return all_rates


def analyze_distribution(rates: list[dict]) -> dict:
    """Compute statistics on the funding rate distribution."""
    if not rates:
        return {}

    values = [float(r["rate"]) for r in rates]

    return {
        "count": len(values),
        "mean": statistics.mean(values),
        "median": statistics.median(values),
        "stdev": statistics.stdev(values) if len(values) > 1 else 0,
        "min": min(values),
        "max": max(values),
        "positive_count": sum(1 for v in values if v > 0),
        "negative_count": sum(1 for v in values if v < 0),
        "zero_count": sum(1 for v in values if v == 0),
        "positive_pct": sum(1 for v in values if v > 0) / len(values) * 100,
        "above_threshold_count": sum(1 for v in values if v > float(FUNDING_THRESHOLD_BUY_BPS)),
        "above_threshold_pct": sum(1 for v in values if v > float(FUNDING_THRESHOLD_BUY_BPS))
        / len(values)
        * 100,
    }


def simulate_strategy(rates: list[dict], initial_capital: Decimal = Decimal("1000")) -> dict:
    """Simulate a simple asymmetric funding arb strategy.

    - Enter (long spot + short perp) when funding > FUNDING_THRESHOLD_BUY_BPS
    - Exit when funding <= FUNDING_THRESHOLD_SELL_BPS
    - Fees are applied at each entry and exit
    - Position size: 50% of capital (500 USDC spot long + 500 USDC perp short)

    Returns a dict with trade count, gross funding collected, net P&L, etc.
    """
    if not rates:
        return {}

    # Sort by timestamp ascending
    sorted_rates = sorted(rates, key=lambda r: r["timestamp"])

    position_size = initial_capital / Decimal("2")  # 500 USDC

    in_position = False
    entry_idx: int | None = None

    trades: list[dict] = []
    cumulative_funding = Decimal("0")
    cumulative_fees = Decimal("0")

    for idx, rate_data in enumerate(sorted_rates):
        rate = Decimal(str(rate_data["rate"]))

        if not in_position:
            if rate > FUNDING_THRESHOLD_BUY_BPS:
                # Open position
                in_position = True
                entry_idx = idx
                # Fee for entry (spot maker + perp maker)
                entry_fees = position_size * (Decimal("0.0016") + Decimal("0.0002"))  # 0.18%
                cumulative_fees += entry_fees
                trades.append(
                    {
                        "action": "OPEN",
                        "timestamp": rate_data["timestamp"],
                        "funding_rate": float(rate),
                        "position_size": float(position_size),
                        "entry_fees": float(entry_fees),
                    }
                )
        else:
            # Collect funding (positive means we receive)
            funding_collected = position_size * rate
            cumulative_funding += funding_collected

            if rate <= FUNDING_THRESHOLD_SELL_BPS:
                # Close position
                in_position = False
                exit_fees = position_size * (Decimal("0.0016") + Decimal("0.0002"))  # 0.18%
                cumulative_fees += exit_fees
                assert entry_idx is not None
                trades.append(
                    {
                        "action": "CLOSE",
                        "timestamp": rate_data["timestamp"],
                        "funding_rate": float(rate),
                        "position_size": float(position_size),
                        "exit_fees": float(exit_fees),
                        "duration_hours": idx - entry_idx,
                    }
                )

    # If still in position at the end, close it
    if in_position:
        exit_fees = position_size * (Decimal("0.0016") + Decimal("0.0002"))
        cumulative_fees += exit_fees
        assert entry_idx is not None
        trades.append(
            {
                "action": "CLOSE_EOD",
                "timestamp": sorted_rates[-1]["timestamp"],
                "exit_fees": float(exit_fees),
                "duration_hours": len(sorted_rates) - entry_idx,
            }
        )

    net_pnl = cumulative_funding - cumulative_fees
    net_pnl_pct = (net_pnl / initial_capital) * 100

    # Annualize
    total_hours = len(sorted_rates)
    total_days = total_hours / 24
    total_years = total_days / 365
    apr = (net_pnl_pct / Decimal(str(total_years))) if total_years > 0 else Decimal("0")

    open_trades = [t for t in trades if t["action"] == "OPEN"]
    close_trades = [t for t in trades if t["action"].startswith("CLOSE")]

    return {
        "initial_capital": float(initial_capital),
        "position_size": float(position_size),
        "total_hours_analyzed": total_hours,
        "total_days_analyzed": round(total_days, 1),
        "num_open_trades": len(open_trades),
        "num_close_trades": len(close_trades),
        "avg_duration_hours": (
            sum(t.get("duration_hours", 0) for t in close_trades) / len(close_trades)
            if close_trades
            else 0
        ),
        "cumulative_funding_collected": float(cumulative_funding),
        "cumulative_fees": float(cumulative_fees),
        "net_pnl": float(net_pnl),
        "net_pnl_pct": float(net_pnl_pct),
        "annualized_apr": float(apr),
    }


def generate_report(
    distribution: dict,
    simulation: dict,
    pair: str,
    months: int,
    output_path: Path,
) -> None:
    """Generate a markdown report."""
    lines = [
        f"# Funding Rate Arb Backtest — {pair} — {months} months",
        "",
        f"Generated: {datetime.now(UTC).isoformat()}",
        "",
        "## Distribution of Hourly Funding Rates",
        "",
        f"- **Total observations**: {distribution.get('count', 0)}",
        f"- **Mean rate**: {distribution.get('mean', 0):.6f} ({distribution.get('mean', 0) * 100:.4f}%)",
        f"- **Median rate**: {distribution.get('median', 0):.6f} ({distribution.get('median', 0) * 100:.4f}%)",
        f"- **Std dev**: {distribution.get('stdev', 0):.6f}",
        f"- **Min**: {distribution.get('min', 0):.6f} ({distribution.get('min', 0) * 100:.4f}%)",
        f"- **Max**: {distribution.get('max', 0):.6f} ({distribution.get('max', 0) * 100:.4f}%)",
        "",
        "## Positive vs Negative Frequency",
        "",
        f"- **Positive rate hours**: {distribution.get('positive_count', 0)} ({distribution.get('positive_pct', 0):.1f}%)",
        f"- **Negative rate hours**: {distribution.get('negative_count', 0)}",
        f"- **Zero rate hours**: {distribution.get('zero_count', 0)}",
        f"- **Hours above entry threshold (0.005%)**: {distribution.get('above_threshold_count', 0)} ({distribution.get('above_threshold_pct', 0):.1f}%)",
        "",
        "## Strategy Simulation (Asymmetric Funding Arb)",
        "",
        "**Rules:**",
        "- Open long spot + short perp when funding rate > 0.005% / hour",
        "- Close when funding rate <= 0",
        "- Position size: 500 USDC (50% of 1000 USDC capital)",
        "- Fees: 0.16% maker spot + 0.02% maker perp on each leg (both entry and exit) = 0.36% round-trip",
        "",
        "**Results:**",
        "",
        f"- **Initial capital**: {simulation.get('initial_capital', 0):.2f} USDC",
        f"- **Position size**: {simulation.get('position_size', 0):.2f} USDC",
        f"- **Period analyzed**: {simulation.get('total_days_analyzed', 0)} days ({simulation.get('total_hours_analyzed', 0)} hours)",
        f"- **Number of trades opened**: {simulation.get('num_open_trades', 0)}",
        f"- **Number of trades closed**: {simulation.get('num_close_trades', 0)}",
        f"- **Avg duration per trade**: {simulation.get('avg_duration_hours', 0):.1f} hours",
        f"- **Cumulative funding collected**: {simulation.get('cumulative_funding_collected', 0):.4f} USDC",
        f"- **Cumulative fees paid**: {simulation.get('cumulative_fees', 0):.4f} USDC",
        f"- **Net P&L**: {simulation.get('net_pnl', 0):.4f} USDC ({simulation.get('net_pnl_pct', 0):.2f}%)",
        f"- **Annualized APR**: {simulation.get('annualized_apr', 0):.2f}%",
        "",
        "## Verdict",
        "",
    ]

    apr = simulation.get("annualized_apr", 0)
    if apr > 5:
        lines.append(f"**PROFITABLE** — Annualized APR of {apr:.2f}% exceeds 5% threshold.")
        lines.append("")
        lines.append("Recommendation: Proceed with Phase 4A (live strategy implementation).")
    elif apr > 0:
        lines.append(f"**MARGINAL** — Annualized APR of {apr:.2f}% is positive but below 5%.")
        lines.append("")
        lines.append(
            "Recommendation: Review conditions before Phase 4A."
            " Maybe adjust thresholds or wait for better market regime."
        )
    else:
        lines.append(f"**NOT PROFITABLE** — Annualized APR of {apr:.2f}% is negative or zero.")
        lines.append("")
        lines.append(
            "Recommendation: Do NOT proceed with Phase 4A."
            " Funding arb is not viable on Kraken in current conditions."
        )

    lines.append("")
    lines.append("## Raw Data")
    lines.append("")
    lines.append("See `results/funding_history_raw.json` for the raw funding history used.")

    output_path.write_text("\n".join(lines))
    log.info("report_generated", path=str(output_path))


async def main() -> None:
    """Main entry point."""
    parser = argparse.ArgumentParser(description="Analyze Kraken Futures funding rate history")
    parser.add_argument("--months", type=int, default=12, help="Months of history to analyze")
    parser.add_argument("--pair", type=str, default="XBT/USD", help="Internal pair name")
    args = parser.parse_args()

    settings = Settings()

    # Check Kraken Futures credentials
    if not settings.kraken_futures.api_key.get_secret_value():
        log.error(
            "kraken_futures_api_key_missing",
            hint="Set KRAKEN_FUTURES_API_KEY in .env.local",
        )
        return
    if not settings.kraken_futures.api_secret.get_secret_value():
        log.error(
            "kraken_futures_api_secret_missing",
            hint="Set KRAKEN_FUTURES_API_SECRET in .env.local",
        )
        return

    client = KrakenFuturesClient(settings)

    try:
        # Fetch history
        rates = await fetch_funding_history(client, args.pair, args.months)

        if not rates:
            log.error("no_funding_data_fetched")
            return

        # Save raw data
        results_dir = Path("results")
        results_dir.mkdir(exist_ok=True)

        raw_path = results_dir / "funding_history_raw.json"
        raw_path.write_text(
            json.dumps(
                [{"timestamp": r["timestamp"], "rate": str(r["rate"])} for r in rates],
                indent=2,
            )
        )

        # Analyze
        distribution = analyze_distribution(rates)
        simulation = simulate_strategy(rates)

        # Generate report
        report_path = results_dir / "funding_arb_backtest_results.md"
        generate_report(distribution, simulation, args.pair, args.months, report_path)

        # Print summary to console
        print("\n" + "=" * 60)
        print(f"FUNDING ARB BACKTEST — {args.pair} — {args.months} months")
        print("=" * 60)
        print(f"Observations: {distribution.get('count', 0)}")
        print(f"Mean rate: {distribution.get('mean', 0):.6f} / hour")
        print(f"% positive: {distribution.get('positive_pct', 0):.1f}%")
        print(f"% above threshold: {distribution.get('above_threshold_pct', 0):.1f}%")
        print(f"Trades: {simulation.get('num_open_trades', 0)}")
        print(
            f"Net P&L: {simulation.get('net_pnl', 0):.4f} USDC"
            f" ({simulation.get('net_pnl_pct', 0):.2f}%)"
        )
        print(f"Annualized APR: {simulation.get('annualized_apr', 0):.2f}%")
        print("=" * 60)
        print(f"Full report: {report_path}")
        print()

    finally:
        await client.close()


if __name__ == "__main__":
    asyncio.run(main())
