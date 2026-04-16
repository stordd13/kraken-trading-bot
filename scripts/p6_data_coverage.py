"""Phase A — Analyse de couverture des données Binance pour P6.

Vérifie la disponibilité et la qualité des données historiques Binance
pour les 3 paires (BTC/USDC, ETH/USDC, SOL/USDC) sur les 7 timeframes.

Usage:
    poetry run python scripts/p6_data_coverage.py
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from pathlib import Path
import sys

from dotenv import load_dotenv
from sqlalchemy import func, select

load_dotenv()

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from krakenbot.config.settings import Settings
from krakenbot.core.database import DatabaseManager
from krakenbot.models.market_data import OHLCData

# Expected candle intervals in minutes
INTERVALS = [5, 15, 60, 240, 1440, 10080]
INTERVAL_LABELS = {5: "5m", 15: "15m", 60: "1h", 240: "4h", 1440: "1d", 10080: "1w"}
PAIRS = ["BTC/USDC", "ETH/USDC", "SOL/USDC"]
EXCHANGE = "binance"

# P6 backtest period
P6_START = datetime(2023, 4, 1, tzinfo=UTC)
P6_END = datetime(2026, 4, 1, tzinfo=UTC)


def expected_candles(interval_min: int, start: datetime, end: datetime) -> int:
    """Calculate expected number of candles for a given interval and period."""
    total_minutes = (end - start).total_seconds() / 60
    return int(total_minutes / interval_min)


async def run() -> None:
    settings = Settings()
    db_manager = DatabaseManager()
    await db_manager.init_db(settings)

    lines: list[str] = []
    lines.append("# P6 — Data Coverage Analysis (Binance)")
    lines.append("")
    lines.append(f"Generated: {datetime.now(UTC).strftime('%Y-%m-%d %H:%M UTC')}")
    lines.append("")

    # --- Section 1: Full coverage table ---
    lines.append("## 1. Full Data Coverage")
    lines.append("")
    lines.append("| Pair | TF | Rows | Min Date | Max Date | Span (days) |")
    lines.append("|------|-----|------|----------|----------|-------------|")

    coverage: dict[tuple[str, int], dict] = {}

    async with db_manager.read_session() as session:
        stmt = (
            select(
                OHLCData.pair,
                OHLCData.interval,
                func.count().label("cnt"),
                func.min(OHLCData.timestamp).label("min_ts"),
                func.max(OHLCData.timestamp).label("max_ts"),
            )
            .where(OHLCData.exchange == EXCHANGE)
            .group_by(OHLCData.pair, OHLCData.interval)
            .order_by(OHLCData.pair, OHLCData.interval)
        )
        result = await session.execute(stmt)
        for row in result:
            pair, interval, cnt, min_ts, max_ts = row
            span_days = (max_ts - min_ts).days
            tf_label = INTERVAL_LABELS.get(interval, f"{interval}m")
            lines.append(
                f"| {pair} | {tf_label} | {cnt:,} | "
                f"{min_ts.strftime('%Y-%m-%d')} | {max_ts.strftime('%Y-%m-%d')} | "
                f"{span_days:,} |"
            )
            coverage[(pair, interval)] = {
                "count": cnt,
                "min_ts": min_ts,
                "max_ts": max_ts,
            }

    lines.append("")

    # --- Section 2: P6 period coverage (2023-04 → 2026-04) ---
    lines.append("## 2. P6 Period Coverage (2023-04-01 → 2026-04-01)")
    lines.append("")
    lines.append("| Pair | TF | Expected | Actual | Coverage % | Gap % | Status |")
    lines.append("|------|-----|----------|--------|------------|-------|--------|")

    gap_issues: list[str] = []

    async with db_manager.read_session() as session:
        for pair in PAIRS:
            for interval in INTERVALS:
                tf_label = INTERVAL_LABELS[interval]
                exp = expected_candles(interval, P6_START, P6_END)

                stmt = (
                    select(func.count())
                    .where(OHLCData.pair == pair)
                    .where(OHLCData.interval == interval)
                    .where(OHLCData.exchange == EXCHANGE)
                    .where(OHLCData.timestamp >= P6_START)
                    .where(OHLCData.timestamp < P6_END)
                )
                result = await session.execute(stmt)
                actual = result.scalar() or 0

                coverage_pct = (actual / exp * 100) if exp > 0 else 0
                gap_pct = 100 - coverage_pct
                status = "OK" if gap_pct < 1 else ("WARN" if gap_pct < 5 else "FAIL")

                lines.append(
                    f"| {pair} | {tf_label} | {exp:,} | {actual:,} | "
                    f"{coverage_pct:.1f}% | {gap_pct:.1f}% | {status} |"
                )

                if gap_pct >= 1:
                    gap_issues.append(
                        f"{pair}/{tf_label}: {gap_pct:.1f}% gap ({exp - actual} missing)"
                    )

    lines.append("")

    # --- Section 3: Common period ---
    lines.append("## 3. Common Period Across Pairs")
    lines.append("")

    # Find the latest min_ts and earliest max_ts across all pairs for 4h TF
    pair_ranges: dict[str, tuple[datetime, datetime]] = {}
    for pair in PAIRS:
        key = (pair, 240)  # 4h
        if key in coverage:
            pair_ranges[pair] = (coverage[key]["min_ts"], coverage[key]["max_ts"])

    if pair_ranges:
        common_start = max(r[0] for r in pair_ranges.values())
        common_end = min(r[1] for r in pair_ranges.values())

        for pair, (start, end) in pair_ranges.items():
            lines.append(
                f"- **{pair}** (4h): {start.strftime('%Y-%m-%d')} → {end.strftime('%Y-%m-%d')}"
            )
        lines.append("")
        lines.append(
            f"**Common period (4h):** {common_start.strftime('%Y-%m-%d')} → "
            f"{common_end.strftime('%Y-%m-%d')} "
            f"({(common_end - common_start).days} days)"
        )
    else:
        lines.append("No 4h data found for any pair.")

    lines.append("")

    # --- Section 4: Gap issues ---
    lines.append("## 4. Gap Issues (>1% missing)")
    lines.append("")
    if gap_issues:
        for issue in gap_issues:
            lines.append(f"- {issue}")
    else:
        lines.append(
            "No significant gaps detected. All pair/TF combinations have <1% missing candles."
        )

    lines.append("")

    # --- Section 5: Summary ---
    lines.append("## 5. Summary")
    lines.append("")

    total_combos = len(PAIRS) * len(INTERVALS)
    ok_combos = sum(1 for pair in PAIRS for interval in INTERVALS if (pair, interval) in coverage)
    lines.append(f"- Total pair/TF combinations: {total_combos}")
    lines.append(f"- Combinations with data: {ok_combos}")
    lines.append(f"- Gap issues (>1%): {len(gap_issues)}")
    lines.append("- P6 backtest period: 2023-04-01 → 2026-04-01 (3 years)")

    await db_manager.close_db()

    # Write report
    report_path = Path(__file__).resolve().parent.parent / "results" / "P6_data_coverage.md"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"Report written to: {report_path}")
    print()
    print("\n".join(lines))


if __name__ == "__main__":
    asyncio.run(run())
