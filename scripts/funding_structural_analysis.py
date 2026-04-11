"""Structural analysis of Kraken Futures PF_XBTUSD funding rates + 3 hedge scenarios.

Describes the distribution, run structure, and compares passive-hold simulations
for Spot+Perp, Perp+Quarterly, and Leveraged Perp Long.

Usage:
    poetry run python scripts/funding_structural_analysis.py --months 12
"""

from __future__ import annotations

import argparse
import asyncio
from collections import defaultdict
from datetime import UTC, datetime
from decimal import Decimal
import json
from pathlib import Path
import statistics
import sys

from dotenv import load_dotenv

# Load .env.local first (override), then .env as fallback — must run before
# krakenbot imports so env vars are visible to Settings().
_env_local = Path(__file__).parent.parent / ".env.local"
_env_file = Path(__file__).parent.parent / ".env"
if _env_local.exists():
    load_dotenv(_env_local, override=True)
load_dotenv(_env_file)

# Add scripts dir to path so we can import from first script
sys.path.insert(0, str(Path(__file__).parent))

from analyze_funding_arb_kraken import fetch_funding_history  # noqa: E402
import ccxt.async_support as ccxt_async  # noqa: E402
import structlog  # noqa: E402

from krakenbot.config.settings import Settings  # noqa: E402
from krakenbot.connectors.kraken_futures_rest import KrakenFuturesClient  # noqa: E402

log = structlog.get_logger()

# --- Fee constants ---
SPOT_MAKER_FEE = Decimal("0.0016")
PERP_MAKER_FEE = Decimal("0.0002")
QUARTERLY_MAKER_FEE = Decimal("0.0002")

# Scenario A: Spot + Perp
FEES_OPEN_A = SPOT_MAKER_FEE + PERP_MAKER_FEE  # 0.18%
FEES_CLOSE_A = SPOT_MAKER_FEE + PERP_MAKER_FEE  # 0.18%
TOTAL_FEES_A = FEES_OPEN_A + FEES_CLOSE_A  # 0.36%

# Scenario B: Perp + Quarterly
FEES_OPEN_B = PERP_MAKER_FEE + QUARTERLY_MAKER_FEE  # 0.04%
FEES_CLOSE_B = PERP_MAKER_FEE + QUARTERLY_MAKER_FEE  # 0.04%
TOTAL_FEES_B = FEES_OPEN_B + FEES_CLOSE_B  # 0.08%

# Scenario C: Pure leveraged perp long
FEES_OPEN_C = PERP_MAKER_FEE  # 0.02%
FEES_CLOSE_C = PERP_MAKER_FEE  # 0.02%
TOTAL_FEES_C = FEES_OPEN_C + FEES_CLOSE_C  # 0.04%


# ---------------------------------------------------------------------------
# Q1 — Distribution
# ---------------------------------------------------------------------------


def describe_distribution(values: list[float], label: str) -> dict:
    """Compute detailed statistics on a list of float values."""
    if not values:
        return {"label": label, "count": 0}

    sorted_vals = sorted(values)
    n = len(sorted_vals)

    def percentile(p: float) -> float:
        k = (n - 1) * p / 100
        f = int(k)
        c = f + 1
        if c >= n:
            return sorted_vals[-1]
        return sorted_vals[f] + (k - f) * (sorted_vals[c] - sorted_vals[f])

    pos = sum(1 for v in values if v > 0)
    neg = sum(1 for v in values if v < 0)

    return {
        "label": label,
        "count": n,
        "mean": statistics.mean(values),
        "median": statistics.median(values),
        "stdev": statistics.stdev(values) if n > 1 else 0.0,
        "min": min(values),
        "max": max(values),
        "p5": percentile(5),
        "p25": percentile(25),
        "p75": percentile(75),
        "p95": percentile(95),
        "positive_pct": pos / n * 100,
        "negative_pct": neg / n * 100,
    }


# ---------------------------------------------------------------------------
# Q2 — Run analysis
# ---------------------------------------------------------------------------

_RUN_BUCKETS = [
    ("< 1h", 0, 1),
    ("1-6h", 1, 6),
    ("6-24h", 6, 24),
    ("1-3d", 24, 72),
    ("3-7d", 72, 168),
    ("7-30d", 168, 720),
    ("30d+", 720, float("inf")),
]


def _bucket_label(hours: int) -> str:
    for label, lo, hi in _RUN_BUCKETS:
        if lo <= hours < hi:
            return label
    return "30d+"


def _run_stats(durations: list[int]) -> dict:
    if not durations:
        return {
            "count": 0,
            "mean_hours": 0.0,
            "median_hours": 0.0,
            "max_hours": 0,
            "min_hours": 0,
            "total_hours": 0,
            "histogram": {label: 0 for label, _, _ in _RUN_BUCKETS},
        }
    hist: dict[str, int] = {label: 0 for label, _, _ in _RUN_BUCKETS}
    for d in durations:
        hist[_bucket_label(d)] += 1
    return {
        "count": len(durations),
        "mean_hours": statistics.mean(durations),
        "median_hours": statistics.median(durations),
        "max_hours": max(durations),
        "min_hours": min(durations),
        "total_hours": sum(durations),
        "histogram": hist,
    }


def compute_runs(rates: list[dict]) -> dict:
    """Compute consecutive same-sign run statistics."""
    if not rates:
        return {"positive": _run_stats([]), "negative": _run_stats([])}

    sorted_rates = sorted(rates, key=lambda r: r["timestamp"])
    positive_runs: list[int] = []
    negative_runs: list[int] = []

    current_sign: int | None = None
    current_length = 0

    for r in sorted_rates:
        rate = float(r["rate"])
        sign = 1 if rate > 0 else (-1 if rate < 0 else 0)

        if sign == 0:
            # Zero rates extend the current run (not a sign change)
            current_length += 1
            continue

        if sign == current_sign:
            current_length += 1
        else:
            # Save previous run
            if current_sign == 1 and current_length > 0:
                positive_runs.append(current_length)
            elif current_sign == -1 and current_length > 0:
                negative_runs.append(current_length)
            current_sign = sign
            current_length = 1

    # Final run
    if current_sign == 1 and current_length > 0:
        positive_runs.append(current_length)
    elif current_sign == -1 and current_length > 0:
        negative_runs.append(current_length)

    return {
        "positive": _run_stats(positive_runs),
        "negative": _run_stats(negative_runs),
    }


# ---------------------------------------------------------------------------
# Q3 — 3 Scenario simulations (passive hold)
# ---------------------------------------------------------------------------


def simulate_scenario_a(
    rates: list[dict],
    initial_capital: Decimal = Decimal("1000"),
    alloc_pct: Decimal = Decimal("0.5"),
) -> dict:
    """Scenario A: Spot + Perp hedge (passive hold).

    Open long spot + short perp at t=0, hold, close at t=final.
    Collect all funding. Fees = 0.36% round-trip.
    """
    if not rates:
        return {}

    sorted_rates = sorted(rates, key=lambda r: r["timestamp"])
    position_size = initial_capital * alloc_pct

    total_fees = position_size * TOTAL_FEES_A
    cumulative_funding = Decimal("0")
    peak = Decimal("0")
    max_drawdown = Decimal("0")

    for r in sorted_rates:
        rate = Decimal(str(r["rate"]))
        cumulative_funding += position_size * rate
        # Track drawdown on cumulative funding (net of nothing yet, just funding)
        if cumulative_funding > peak:
            peak = cumulative_funding
        dd = peak - cumulative_funding
        if dd > max_drawdown:
            max_drawdown = dd

    net_pnl = cumulative_funding - total_fees
    net_pnl_pct = (net_pnl / initial_capital) * 100

    total_hours = len(sorted_rates)
    total_days = total_hours / 24
    total_years = total_days / 365
    apr = (net_pnl_pct / Decimal(str(total_years))) if total_years > 0 else Decimal("0")

    return {
        "scenario": "A",
        "description": "Spot + Perp Hedge",
        "position_size": float(position_size),
        "gross_funding": float(cumulative_funding),
        "total_fees": float(total_fees),
        "net_pnl": float(net_pnl),
        "net_pnl_pct": float(net_pnl_pct),
        "annualized_apr": float(apr),
        "max_drawdown": float(max_drawdown),
    }


def simulate_scenario_b(
    rates: list[dict],
    initial_capital: Decimal = Decimal("1000"),
    alloc_pct: Decimal = Decimal("0.5"),
) -> dict:
    """Scenario B: Perp + Quarterly calendar spread (passive hold).

    Long perp + short quarterly at t=0, hold, close at t=final.
    Funding collected on perp leg only. Fees = 0.08% round-trip.
    Assumes zero basis drift between perp and quarterly.
    """
    if not rates:
        return {}

    sorted_rates = sorted(rates, key=lambda r: r["timestamp"])
    position_size = initial_capital * alloc_pct

    total_fees = position_size * TOTAL_FEES_B
    cumulative_funding = Decimal("0")

    for r in sorted_rates:
        rate = Decimal(str(r["rate"]))
        cumulative_funding += position_size * rate

    net_pnl = cumulative_funding - total_fees
    net_pnl_pct = (net_pnl / initial_capital) * 100

    total_hours = len(sorted_rates)
    total_days = total_hours / 24
    total_years = total_days / 365
    apr = (net_pnl_pct / Decimal(str(total_years))) if total_years > 0 else Decimal("0")

    return {
        "scenario": "B",
        "description": "Perp + Quarterly Calendar Spread",
        "position_size": float(position_size),
        "gross_funding": float(cumulative_funding),
        "total_fees": float(total_fees),
        "net_pnl": float(net_pnl),
        "net_pnl_pct": float(net_pnl_pct),
        "annualized_apr": float(apr),
    }


def simulate_scenario_c(
    rates: list[dict],
    initial_capital: Decimal = Decimal("1000"),
    alloc_pct: Decimal = Decimal("0.5"),
    price_start: Decimal = Decimal("0"),
    price_end: Decimal = Decimal("0"),
    leverage: Decimal = Decimal("3"),
) -> dict:
    """Scenario C: Pure leveraged perp long (NOT market-neutral).

    Long perp with leverage on collateral. Collect/pay funding on notional.
    Directional exposure to BTC price.
    """
    if not rates:
        return {}

    sorted_rates = sorted(rates, key=lambda r: r["timestamp"])
    collateral = initial_capital * alloc_pct
    notional = collateral * leverage  # e.g. 500 * 3 = 1500 USDC

    total_fees = notional * TOTAL_FEES_C

    # Funding PnL on notional
    funding_pnl = Decimal("0")
    for r in sorted_rates:
        rate = Decimal(str(r["rate"]))
        funding_pnl += notional * rate

    # Directional PnL
    directional_pnl = Decimal("0")
    if price_start > 0:
        price_change_pct = (price_end - price_start) / price_start
        directional_pnl = notional * price_change_pct

    total_pnl = funding_pnl + directional_pnl - total_fees
    total_pnl_pct = (total_pnl / initial_capital) * 100

    total_hours = len(sorted_rates)
    total_days = total_hours / 24
    total_years = total_days / 365
    apr = (total_pnl_pct / Decimal(str(total_years))) if total_years > 0 else Decimal("0")

    return {
        "scenario": "C",
        "description": "Leveraged Perp Long (3x)",
        "collateral": float(collateral),
        "notional": float(notional),
        "leverage": float(leverage),
        "funding_pnl": float(funding_pnl),
        "directional_pnl": float(directional_pnl),
        "total_fees": float(total_fees),
        "total_pnl": float(total_pnl),
        "total_pnl_pct": float(total_pnl_pct),
        "annualized_apr": float(apr),
        "price_start": float(price_start),
        "price_end": float(price_end),
    }


# ---------------------------------------------------------------------------
# Q4 — Monthly breakdown
# ---------------------------------------------------------------------------


def monthly_breakdown(rates: list[dict], position_size: Decimal) -> list[dict]:
    """Group rates by calendar month and compute per-month stats."""
    if not rates:
        return []

    sorted_rates = sorted(rates, key=lambda r: r["timestamp"])

    # Group by YYYY-MM
    months: dict[str, list[dict]] = defaultdict(list)
    for r in sorted_rates:
        dt = datetime.fromtimestamp(r["timestamp"] / 1000, tz=UTC)
        key = dt.strftime("%Y-%m")
        months[key] = months.get(key, [])
        months[key].append(r)

    results: list[dict] = []
    for month_key in sorted(months):
        month_rates = months[month_key]
        values = [float(r["rate"]) for r in month_rates]
        positive_hours = sum(1 for v in values if v > 0)
        total_hours = len(values)
        funding = sum(position_size * Decimal(str(r["rate"])) for r in month_rates)

        # Compute runs within this month
        runs = compute_runs(month_rates)

        results.append(
            {
                "month": month_key,
                "hours": total_hours,
                "funding_collected": float(funding),
                "positive_hours_pct": positive_hours / total_hours * 100 if total_hours else 0,
                "num_positive_runs": runs["positive"]["count"],
                "num_negative_runs": runs["negative"]["count"],
                "best_run_hours": runs["positive"]["max_hours"],
                "worst_run_hours": runs["negative"]["max_hours"],
            }
        )

    return results


# ---------------------------------------------------------------------------
# Q5 — Top N worst negative runs
# ---------------------------------------------------------------------------


def top_negative_runs(rates: list[dict], position_size: Decimal, n: int = 10) -> list[dict]:
    """Find the N longest negative funding runs with cumulative loss."""
    if not rates:
        return []

    sorted_rates = sorted(rates, key=lambda r: r["timestamp"])

    runs: list[dict] = []
    current_run_start: int | None = None
    current_run_loss = Decimal("0")
    current_run_length = 0

    for r in sorted_rates:
        rate = float(r["rate"])
        if rate < 0:
            if current_run_start is None:
                current_run_start = r["timestamp"]
                current_run_loss = Decimal("0")
                current_run_length = 0
            current_run_loss += position_size * Decimal(str(r["rate"]))
            current_run_length += 1
        else:
            if current_run_start is not None:
                runs.append(
                    {
                        "start_timestamp": current_run_start,
                        "end_timestamp": r["timestamp"],
                        "duration_hours": current_run_length,
                        "cumulative_loss": float(current_run_loss),
                    }
                )
                current_run_start = None

    # Final run
    if current_run_start is not None:
        runs.append(
            {
                "start_timestamp": current_run_start,
                "end_timestamp": sorted_rates[-1]["timestamp"],
                "duration_hours": current_run_length,
                "cumulative_loss": float(current_run_loss),
            }
        )

    # Sort by duration descending
    runs.sort(key=lambda r: r["duration_hours"], reverse=True)
    return runs[:n]


# ---------------------------------------------------------------------------
# BTC price fetch
# ---------------------------------------------------------------------------


async def fetch_btc_prices(start_ms: int, end_ms: int) -> tuple[Decimal, Decimal, str, str]:
    """Fetch BTC/USD start and end prices via ccxt kraken (public, no auth)."""
    exchange = ccxt_async.kraken({"enableRateLimit": True})
    try:
        start_candles = await exchange.fetch_ohlcv("BTC/USD", "1d", since=start_ms, limit=1)
        end_candles = await exchange.fetch_ohlcv("BTC/USD", "1d", since=end_ms - 86400000, limit=1)

        price_start = Decimal(str(start_candles[0][1]))  # open
        price_end = Decimal(str(end_candles[0][4]))  # close
        date_start = datetime.fromtimestamp(start_candles[0][0] / 1000, tz=UTC).strftime("%Y-%m-%d")
        date_end = datetime.fromtimestamp(end_candles[0][0] / 1000, tz=UTC).strftime("%Y-%m-%d")

        return price_start, price_end, date_start, date_end
    finally:
        await exchange.close()


# ---------------------------------------------------------------------------
# Report generation
# ---------------------------------------------------------------------------


def _fmt_ts(ms: int) -> str:
    return datetime.fromtimestamp(ms / 1000, tz=UTC).strftime("%Y-%m-%d %H:%M")


def generate_report(
    *,
    distributions: dict[str, dict],
    runs: dict,
    scenario_a: dict,
    scenario_b: dict,
    scenario_c: dict,
    monthly: list[dict],
    worst_runs: list[dict],
    pair: str,
    months: int,
    start_ts: int,
    end_ts: int,
    total_hours: int,
    output_path: Path,
) -> None:
    """Generate the structural analysis markdown report."""
    total_days = total_hours / 24
    start_str = _fmt_ts(start_ts)
    end_str = _fmt_ts(end_ts)

    lines = [
        "# Kraken PF_XBTUSD — Structural Analysis",
        f"Generated: {datetime.now(UTC).isoformat()}",
        f"Period analyzed: {start_str} -> {end_str} ({total_hours} hours, {total_days:.1f} days)",
        "",
    ]

    # --- Section 1: Distributions ---
    lines.append("## 1. Distribution of Funding Rates")
    lines.append("")

    for key in ["global", "positive_only", "negative_only"]:
        dist = distributions.get(key, {})
        label = dist.get("label", key)
        lines.append(f"### {label}")
        lines.append("")
        if dist.get("count", 0) == 0:
            lines.append("No data.")
            lines.append("")
            continue
        lines.append(f"- **Count**: {dist['count']}")
        lines.append(f"- **Mean**: {dist['mean']:.8f} ({dist['mean'] * 100:.6f}%)")
        lines.append(f"- **Median**: {dist['median']:.8f} ({dist['median'] * 100:.6f}%)")
        lines.append(f"- **Stdev**: {dist['stdev']:.8f}")
        lines.append(f"- **Min**: {dist['min']:.8f} ({dist['min'] * 100:.6f}%)")
        lines.append(f"- **Max**: {dist['max']:.8f} ({dist['max'] * 100:.6f}%)")
        lines.append(f"- **P5**: {dist['p5']:.8f} ({dist['p5'] * 100:.6f}%)")
        lines.append(f"- **P25**: {dist['p25']:.8f}")
        lines.append(f"- **P75**: {dist['p75']:.8f}")
        lines.append(f"- **P95**: {dist['p95']:.8f} ({dist['p95'] * 100:.6f}%)")
        lines.append(f"- **Positive %**: {dist['positive_pct']:.1f}%")
        lines.append(f"- **Negative %**: {dist['negative_pct']:.1f}%")
        lines.append("")

    # --- Section 2: Runs ---
    lines.append("## 2. Run Analysis")
    lines.append("")

    for sign_key, sign_label in [("positive", "Positive Runs"), ("negative", "Negative Runs")]:
        rs = runs.get(sign_key, {})
        lines.append(f"### {sign_label}")
        lines.append("")
        lines.append(f"- **Count**: {rs.get('count', 0)}")
        lines.append(f"- **Mean duration**: {rs.get('mean_hours', 0):.1f} hours")
        lines.append(f"- **Median duration**: {rs.get('median_hours', 0):.1f} hours")
        lines.append(f"- **Max**: {rs.get('max_hours', 0)} hours")
        lines.append(f"- **Min**: {rs.get('min_hours', 0)} hours")
        lines.append(f"- **Total hours**: {rs.get('total_hours', 0)}")
        lines.append("")
        lines.append("**Histogram:**")
        lines.append("")
        lines.append("| Bucket | Count |")
        lines.append("|--------|-------|")
        hist = rs.get("histogram", {})
        for label, _, _ in _RUN_BUCKETS:
            lines.append(f"| {label} | {hist.get(label, 0)} |")
        lines.append("")

    # --- Section 3: 3 Scenarios ---
    lines.append("## 3. Three Hedge Scenarios — Passive Hold Simulation")
    lines.append("")

    # Scenario A
    lines.append("### Scenario A: Spot + Perp Hedge")
    lines.append("")
    lines.append(f"- Fees round-trip: {float(TOTAL_FEES_A) * 100:.2f}%")
    lines.append("- Basis risk: None (perfect hedge)")
    lines.append(f"- Position: {scenario_a.get('position_size', 0):.0f} USDC delta-neutral")
    lines.append("")
    lines.append("**Results:**")
    lines.append("")
    lines.append(f"- Gross funding collected: {scenario_a.get('gross_funding', 0):.4f} USDC")
    lines.append(f"- Total fees: {scenario_a.get('total_fees', 0):.4f} USDC")
    lines.append(
        f"- Net P&L: {scenario_a.get('net_pnl', 0):.4f} USDC ({scenario_a.get('net_pnl_pct', 0):.2f}%)"
    )
    lines.append(f"- Annualized APR: {scenario_a.get('annualized_apr', 0):.2f}%")
    lines.append(f"- Max drawdown (funding): {scenario_a.get('max_drawdown', 0):.4f} USDC")
    lines.append("")

    # Scenario B
    lines.append("### Scenario B: Perp + Quarterly Calendar Spread")
    lines.append("")
    lines.append(
        f"- Fees round-trip: {float(TOTAL_FEES_B) * 100:.2f}% (4.5x lower than Scenario A)"
    )
    lines.append("- Basis risk: ASSUMED ZERO (unrealistic - see warning)")
    lines.append(f"- Position: {scenario_b.get('position_size', 0):.0f} USDC notional")
    lines.append("")
    lines.append(
        "> **WARNING**: This scenario assumes zero basis drift between perp and quarterly."
        " In reality, basis can add +/-2-5% PnL deviation. Real results may be significantly different."
    )
    lines.append("")
    lines.append("**Results:**")
    lines.append("")
    lines.append(f"- Gross funding collected: {scenario_b.get('gross_funding', 0):.4f} USDC")
    lines.append(f"- Total fees: {scenario_b.get('total_fees', 0):.4f} USDC")
    lines.append(
        f"- Net P&L: {scenario_b.get('net_pnl', 0):.4f} USDC ({scenario_b.get('net_pnl_pct', 0):.2f}%)"
    )
    lines.append(f"- Annualized APR: {scenario_b.get('annualized_apr', 0):.2f}%")
    lines.append("")

    # Scenario C
    lines.append("### Scenario C: Leveraged Perp Long (3x)")
    lines.append("")
    lines.append(f"- Fees round-trip: {float(TOTAL_FEES_C) * 100:.2f}%")
    lines.append("- NOT market-neutral — directional exposure")
    lines.append(
        f"- Position: {scenario_c.get('collateral', 0):.0f} USDC collateral,"
        f" {scenario_c.get('notional', 0):.0f} USDC notional"
    )
    lines.append("")
    lines.append(
        "> **WARNING**: This is directional speculation, not arbitrage."
        " A BTC drop of 10% causes -30% loss on position."
    )
    lines.append("")
    lines.append("**BTC price evolution on period:**")
    lines.append("")
    lines.append(f"- Start: ${scenario_c.get('price_start', 0):,.0f}")
    lines.append(f"- End: ${scenario_c.get('price_end', 0):,.0f}")
    price_s = scenario_c.get("price_start", 0)
    price_e = scenario_c.get("price_end", 0)
    price_chg = ((price_e - price_s) / price_s * 100) if price_s > 0 else 0
    lines.append(f"- Change: {price_chg:+.2f}%")
    lines.append("")
    lines.append("**Results breakdown:**")
    lines.append("")
    lines.append(f"- Funding PnL: {scenario_c.get('funding_pnl', 0):.4f} USDC")
    lines.append(f"- Directional PnL: {scenario_c.get('directional_pnl', 0):.4f} USDC")
    lines.append(f"- Fees: {scenario_c.get('total_fees', 0):.4f} USDC")
    lines.append(
        f"- Total Net P&L: {scenario_c.get('total_pnl', 0):.4f} USDC"
        f" ({scenario_c.get('total_pnl_pct', 0):.2f}%)"
    )
    lines.append(f"- Annualized APR: {scenario_c.get('annualized_apr', 0):.2f}%")
    lines.append("")

    # --- Section 4: Monthly breakdown ---
    lines.append("## 4. Monthly Breakdown")
    lines.append("")
    lines.append("| Month | Funding Collected | Positive % | Best Run | Worst Run |")
    lines.append("|-------|-------------------|------------|----------|-----------|")
    for m in monthly:
        lines.append(
            f"| {m['month']} | {m['funding_collected']:.4f} USDC"
            f" | {m['positive_hours_pct']:.1f}%"
            f" | {m['best_run_hours']}h"
            f" | {m['worst_run_hours']}h |"
        )
    lines.append("")

    pos_months = sum(1 for m in monthly if m["funding_collected"] > 0)
    neg_months = len(monthly) - pos_months
    lines.append(f"Months positive: {pos_months} / {len(monthly)}")
    lines.append(f"Months negative: {neg_months} / {len(monthly)}")
    if monthly:
        best = max(monthly, key=lambda m: m["funding_collected"])
        worst = min(monthly, key=lambda m: m["funding_collected"])
        lines.append(f"Best month: {best['month']} ({best['funding_collected']:.4f} USDC)")
        lines.append(f"Worst month: {worst['month']} ({worst['funding_collected']:.4f} USDC)")
    lines.append("")

    # --- Section 5: Top 10 worst negative runs ---
    lines.append("## 5. Top 10 Worst Negative Runs")
    lines.append("")
    lines.append("| # | Start | End | Duration (h) | Cumulative Loss (USDC) |")
    lines.append("|---|-------|-----|--------------|------------------------|")
    for i, wr in enumerate(worst_runs, 1):
        lines.append(
            f"| {i}"
            f" | {_fmt_ts(wr['start_timestamp'])}"
            f" | {_fmt_ts(wr['end_timestamp'])}"
            f" | {wr['duration_hours']}"
            f" | {wr['cumulative_loss']:.4f} |"
        )
    lines.append("")

    # --- Section 6: Key Observations ---
    lines.append("## 6. Key Observations")
    lines.append("")
    apr_a = scenario_a.get("annualized_apr", 0)
    apr_b = scenario_b.get("annualized_apr", 0)
    apr_c = scenario_c.get("annualized_apr", 0)
    lines.append(
        f"- **Is Scenario A profitable?** {'YES' if apr_a > 0 else 'NO'} — APR: {apr_a:.2f}%"
    )
    lines.append(
        f"- **Is Scenario B profitable?** {'YES' if apr_b > 0 else 'NO'}"
        f" — APR: {apr_b:.2f}% (but with basis risk caveat)"
    )
    lines.append(
        f"- **Is Scenario C profitable?** {'YES' if apr_c > 0 else 'NO'}"
        f" — APR: {apr_c:.2f}% (but non-neutral)"
    )

    if worst_runs:
        longest_neg = worst_runs[0]
        lines.append(
            f"- **What is the longest negative run?** {longest_neg['duration_hours']} hours"
            f" on {_fmt_ts(longest_neg['start_timestamp'])}"
        )
    else:
        lines.append("- **What is the longest negative run?** None")

    # Trend analysis: first half vs second half
    if len(monthly) >= 4:
        half = len(monthly) // 2
        first_half_avg = statistics.mean(m["funding_collected"] for m in monthly[:half])
        second_half_avg = statistics.mean(m["funding_collected"] for m in monthly[half:])
        if second_half_avg > first_half_avg * 1.1:
            trend = "IMPROVING"
        elif second_half_avg < first_half_avg * 0.9:
            trend = "WORSENING"
        else:
            trend = "STABLE"
        lines.append(
            f"- **Is the monthly trend improving, worsening, or stable?** {trend}"
            f" (first half avg: {first_half_avg:.4f}, second half avg: {second_half_avg:.4f})"
        )

    # Short negative runs analysis
    if worst_runs:
        all_neg_runs = runs.get("negative", {})
        total_neg = all_neg_runs.get("count", 0)
        hist = all_neg_runs.get("histogram", {})
        short_neg = hist.get("< 1h", 0) + hist.get("1-6h", 0) + hist.get("6-24h", 0)
        if total_neg > 0:
            lines.append(
                f"- **What % of negative runs are < 24h?** {short_neg}/{total_neg}"
                f" ({short_neg / total_neg * 100:.1f}%)"
                " — these could be held through without closing"
            )

    lines.append("")

    # --- Section 7: Recommendations ---
    lines.append("## 7. Recommendations for Phase 4A Design")
    lines.append("")

    if apr_a > 5:
        lines.append(
            "**Option 1 — Passive Hold Spot+Perp**: Scenario A is clearly profitable"
            f" (APR {apr_a:.2f}% > 5%). Proceed with implementation."
        )
    elif apr_b > 5:
        lines.append(
            "**Option 2 — Calendar Spread Perp+Quarterly**: Scenario B shows"
            f" {apr_b:.2f}% APR with much lower fees. HIGHER PRIORITY if viable."
            " BUT we need historical basis data to validate the zero-drift assumption."
        )
    elif apr_b > 0 and apr_a <= 0:
        lines.append(
            f"**Option 5 — Need more data**: Scenario B ({apr_b:.2f}% APR) is the only"
            " hedged approach showing positive returns, but the zero-basis-drift"
            " assumption is unrealistic. Need to pull quarterly contract data"
            " separately to confirm."
        )
    elif apr_a > 0 or apr_b > 0:
        lines.append(
            "**Option 3 — Hold with smart exit**: Scenarios A/B are marginal."
            " Consider holding through short negative runs (<24h) and only"
            " exiting on prolonged negative runs (>72h)."
        )
    else:
        lines.append(
            "**Option 4 — Not viable**: All hedged scenarios show negative APR."
            " Funding arb is not viable on Kraken in current conditions."
        )

    lines.append("")

    output_path.write_text("\n".join(lines))
    log.info("report_generated", path=str(output_path))


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


async def main() -> None:
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Structural analysis of Kraken Futures funding rates"
    )
    parser.add_argument("--months", type=int, default=12, help="Months of history to analyze")
    parser.add_argument("--pair", type=str, default="XBT/USD", help="Internal pair name")
    args = parser.parse_args()

    settings = Settings()

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
        # Fetch funding rates
        rates = await fetch_funding_history(client, args.pair, args.months)
        if not rates:
            log.error("no_funding_data_fetched")
            return

        sorted_rates = sorted(rates, key=lambda r: r["timestamp"])
        total_hours = len(sorted_rates)
        start_ts = sorted_rates[0]["timestamp"]
        end_ts = sorted_rates[-1]["timestamp"]

        log.info(
            "data_loaded",
            total_hours=total_hours,
            start=_fmt_ts(start_ts),
            end=_fmt_ts(end_ts),
        )

        # Save raw data
        results_dir = Path("results")
        results_dir.mkdir(exist_ok=True)

        raw_path = results_dir / "funding_history_structural_raw.json"
        raw_path.write_text(
            json.dumps(
                [{"timestamp": r["timestamp"], "rate": str(r["rate"])} for r in rates],
                indent=2,
            )
        )

        # Q1 — Distributions
        all_values = [float(r["rate"]) for r in sorted_rates]
        pos_values = [v for v in all_values if v > 0]
        neg_values = [v for v in all_values if v < 0]

        distributions = {
            "global": describe_distribution(all_values, "Global"),
            "positive_only": describe_distribution(pos_values, "Positive Only"),
            "negative_only": describe_distribution(neg_values, "Negative Only"),
        }

        # Q2 — Runs
        runs = compute_runs(sorted_rates)

        # Q3 — 3 Scenarios
        position_size = Decimal("500")
        scenario_a = simulate_scenario_a(sorted_rates)
        scenario_b = simulate_scenario_b(sorted_rates)

        # Fetch BTC prices for scenario C
        log.info("fetching_btc_prices")
        price_start, price_end, date_start, date_end = await fetch_btc_prices(start_ts, end_ts)
        log.info(
            "btc_prices_fetched",
            start=f"${price_start:,.0f} ({date_start})",
            end=f"${price_end:,.0f} ({date_end})",
        )

        scenario_c = simulate_scenario_c(
            sorted_rates,
            price_start=price_start,
            price_end=price_end,
        )

        # Q4 — Monthly breakdown
        monthly = monthly_breakdown(sorted_rates, position_size)

        # Q5 — Worst runs
        worst = top_negative_runs(sorted_rates, position_size)

        # Generate report
        report_path = results_dir / "funding_structural_analysis.md"
        generate_report(
            distributions=distributions,
            runs=runs,
            scenario_a=scenario_a,
            scenario_b=scenario_b,
            scenario_c=scenario_c,
            monthly=monthly,
            worst_runs=worst,
            pair=args.pair,
            months=args.months,
            start_ts=start_ts,
            end_ts=end_ts,
            total_hours=total_hours,
            output_path=report_path,
        )

        # Print summary
        print("\n" + "=" * 60)
        print(f"STRUCTURAL ANALYSIS — {args.pair} — {args.months} months")
        print("=" * 60)
        print(f"Period: {_fmt_ts(start_ts)} -> {_fmt_ts(end_ts)} ({total_hours}h)")
        print(f"Positive rate: {distributions['global'].get('positive_pct', 0):.1f}%")
        print(f"Mean rate: {distributions['global'].get('mean', 0):.8f}/h")
        print()
        print("--- 3 Scenarios (passive hold) ---")
        print(f"A) Spot+Perp:     APR {scenario_a.get('annualized_apr', 0):+.2f}%")
        print(f"B) Perp+Quarterly: APR {scenario_b.get('annualized_apr', 0):+.2f}%")
        print(f"C) Leveraged 3x:  APR {scenario_c.get('annualized_apr', 0):+.2f}%")
        print()
        print(f"Full report: {report_path}")
        print("=" * 60)

    finally:
        await client.close()


if __name__ == "__main__":
    asyncio.run(main())
