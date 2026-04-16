"""P6.5 Phase 3 — diagnose adaptive DCA vs fixed DCA on equal footing.

The benchmark fixed DCA (scripts/compute_benchmarks.py) and the adaptive DCA
(SignalBacktester via grok_adaptive_dca_weekly) use different denominators
and capital constraints, which makes "fixed +23.3% vs adaptive -11%"
misleading. This script simulates fixed DCA with:

  (a) starting_balance = $1000 (same as adaptive)
  (b) buy skipped when usdc_balance < weekly amount (same as adaptive)
  (c) measured on the TEST window only (30% of P6 period, same as backtester)

Also reports the original benchmark number for sanity / contrast.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from decimal import Decimal
import json
from pathlib import Path
import sys

from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / ".env")

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from backtest import _load_candles_chunked

from krakenbot.config.settings import get_settings
from krakenbot.core.database import DatabaseManager

P6_START = datetime(2023, 4, 1, tzinfo=UTC)
P6_END = datetime(2026, 4, 1, tzinfo=UTC)
TRAIN_RATIO = 0.7
EXCHANGE = "binance"
PAIRS = ["BTC/USDC", "ETH/USDC", "SOL/USDC"]
CAPITAL = Decimal("1000")
WEEKLY_AMOUNT = Decimal("15")

RESULTS_PATH = Path(__file__).resolve().parent.parent / "results" / "P6_phase_d_results.json"
OUTPUT_PATH = (
    Path(__file__).resolve().parent.parent / "results" / "P6_5_diagnostic_dca.md"
)


def test_window() -> tuple[datetime, datetime]:
    """Return (test_start, test_end) for the 30% tail of P6."""
    span = P6_END - P6_START
    split = P6_START + timedelta(seconds=int(span.total_seconds() * TRAIN_RATIO))
    return split, P6_END


def simulate_fixed_dca(
    candles,
    weekly_amount: Decimal,
    starting_capital: Decimal | None,
) -> dict:
    """Simulate fixed DCA with optional capital constraint.

    If `starting_capital` is None, unlimited (reference/benchmark behaviour).
    Otherwise, skip buys when running balance < weekly_amount (matches backtester).
    """
    if not candles:
        return {"error": "no candles"}

    total_coins = Decimal("0")
    total_invested = Decimal("0")
    usdc_balance = starting_capital if starting_capital is not None else None
    buys_done = 0
    buys_skipped = 0
    last_week_key: int | None = None
    equity_curve: list[tuple[datetime, float]] = []

    for c in candles:
        iso_year, iso_week, _ = c.timestamp.isocalendar()
        week_key = iso_year * 100 + iso_week
        # Buy on the first Monday candle of a new ISO week.
        is_monday_new_week = c.timestamp.weekday() == 0 and week_key != last_week_key
        if is_monday_new_week:
            if usdc_balance is not None and usdc_balance < weekly_amount:
                buys_skipped += 1
            else:
                coins = weekly_amount / c.close
                total_coins += coins
                total_invested += weekly_amount
                if usdc_balance is not None:
                    usdc_balance -= weekly_amount
                buys_done += 1
            last_week_key = week_key

        # Equity = USDC left (if any) + coins × current close
        crypto_equity = total_coins * c.close
        if usdc_balance is not None:
            equity = usdc_balance + crypto_equity
        else:
            # Reference mode: total invested vs current value of coins
            equity = crypto_equity
        equity_curve.append((c.timestamp, float(equity)))

    final_coins_value = total_coins * candles[-1].close
    if starting_capital is None:
        # Benchmark-style return: (final - invested) / invested
        if total_invested == 0:
            return {"error": "no buys"}
        total_return_pct = float(
            (final_coins_value - total_invested) / total_invested * 100
        )
        ending_balance = float(final_coins_value)
    else:
        # Backtester-style return: (ending - starting) / starting
        ending_balance = float(
            (usdc_balance or Decimal("0")) + final_coins_value
        )
        total_return_pct = float(
            (Decimal(str(ending_balance)) - starting_capital) / starting_capital * 100
        )

    return {
        "total_return_pct": round(total_return_pct, 2),
        "starting_capital": float(starting_capital) if starting_capital else None,
        "total_invested": float(total_invested),
        "ending_balance": round(ending_balance, 2),
        "coins_accumulated": float(total_coins),
        "buys_done": buys_done,
        "buys_skipped": buys_skipped,
        "final_close": float(candles[-1].close),
    }


def load_adaptive_dca_test_results() -> dict:
    """Extract adaptive DCA test-set metrics from Phase D results JSON."""
    if not RESULTS_PATH.exists():
        return {}
    data = json.loads(RESULTS_PATH.read_text())
    out: dict[str, dict] = {}
    for pair in PAIRS:
        key = f"grok_adaptive_dca_weekly_{pair.replace('/', '_')}"
        entry = data.get(key)
        if entry and "test" in entry:
            out[pair] = entry["test"]
    return out


def build_report(
    per_pair: dict[str, dict],
    adaptive_test: dict[str, dict],
) -> str:
    lines: list[str] = [
        "# P6.5 — Diagnostic DCA Adaptive vs Fixed (apples-to-apples)",
        "",
        "## Pourquoi ce diagnostic",
        "",
        "Dans P6, le benchmark DCA fixe (`results/P6_benchmarks.json`) calcule :",
        "",
        "    total_return = (final_value - total_invested) / total_invested * 100",
        "",
        "alors que le DCA adaptatif (`grok_adaptive_dca_weekly` dans SignalBacktester) calcule :",
        "",
        "    total_return = (ending_balance - starting_balance) / starting_balance * 100",
        "",
        "De plus :",
        "- Benchmark fixe : capital **illimité** (on ajoute $15/semaine indéfiniment)",
        "- Adaptatif : capital **plafonné à $1000** → épuise l'USDC après ~66 semaines",
        "- Benchmark fixe : mesuré sur **3 ans** ; adaptatif test : **~11 mois** (30% tail)",
        "",
        "La comparaison directe 'fixed +23.3% vs adaptive -11%' compare des pommes et des oranges.",
        "",
        "## Simulation fixed DCA avec les mêmes contraintes que l'adaptatif",
        "",
        "Pour chaque paire, on simule le DCA fixe avec :",
        "- starting capital = $1000 (plafond)",
        "- buys skippés quand `usdc_balance < $15`",
        "- sur la fenêtre **test** seulement (30% queue de P6, ~11 mois)",
        "",
        "| Pair | Fixed DCA uncapped (3 ans) | Fixed DCA capped test | Adaptive DCA test | Verdict |",
        "|---|---|---|---|---|",
    ]

    verdict_lines: list[str] = []
    for pair in PAIRS:
        pair_data = per_pair.get(pair, {})
        uncapped = pair_data.get("uncapped_full")
        capped = pair_data.get("capped_test")
        adaptive = adaptive_test.get(pair, {})
        ad_return = adaptive.get("total_return_pct", 0.0)
        ad_trades = adaptive.get("total_trades", 0)

        un_str = (
            f"{uncapped['total_return_pct']:+.1f}% ({uncapped['buys_done']} buys)"
            if uncapped
            else "—"
        )
        cap_str = (
            f"{capped['total_return_pct']:+.1f}% ({capped['buys_done']} buys, "
            f"{capped['buys_skipped']} skipped)"
            if capped
            else "—"
        )
        ad_str = f"{ad_return:+.1f}% ({ad_trades} trades)"

        if capped and uncapped:
            cap_return = capped["total_return_pct"]
            delta = ad_return - cap_return
            if delta > 1.0:
                verdict = f"Adaptive better by {delta:+.1f}pp"
            elif delta < -1.0:
                verdict = f"Adaptive WORSE by {delta:.1f}pp"
            else:
                verdict = "~Similar"
        else:
            verdict = "n/a"

        lines.append(f"| {pair} | {un_str} | {cap_str} | {ad_str} | {verdict} |")
        verdict_lines.append(f"- {pair}: {verdict}")

    lines += [
        "",
        "## Interprétation",
        "",
        "La bonne comparaison est **fixed capped test vs adaptive test** — même capital,",
        "même contrainte, même fenêtre. Le benchmark uncapped sert uniquement de sanity",
        "check (doit matcher `results/P6_benchmarks.json`).",
        "",
        "### Verdict par paire",
        "",
        *verdict_lines,
        "",
        "### Quel est le bug (s'il y en a un) ?",
        "",
        "Si adaptive ~= fixed capped : **pas de bug**. Le mismatch apparent avec le",
        "benchmark uncapped est un artefact de méthodologie, pas de logique.",
        "",
        "Si adaptive << fixed capped : la logique adaptive (boost RSI<30, reduction",
        "strong_bull) dégrade la performance. À investiguer stratégie par stratégie.",
        "",
        "## Recommandation",
        "",
        "Si le verdict est 'similar', accepter le DCA adaptatif et **utiliser la méthodologie",
        "fixed capped comme benchmark officiel pour P7** au lieu de l'uncapped.",
        "",
        "Ajouter une clé `dca_fixed_capped` à `results/P6_benchmarks.json` pour",
        "comparaisons futures (travail optionnel en P7).",
        "",
        "**Aucun fix code en P6.5** pour le DCA — c'est un problème de méthodologie",
        "de benchmark, pas d'un bug dans la stratégie ou le backtester.",
    ]
    return "\n".join(lines) + "\n"


async def main() -> None:
    settings = get_settings()
    db = DatabaseManager()
    await db.init_db(settings)
    try:
        test_start, test_end = test_window()
        print(f"Test window: {test_start.date()} → {test_end.date()}")

        per_pair: dict[str, dict] = {}
        for pair in PAIRS:
            print(f"Loading daily candles for {pair}…")
            candles_full = await _load_candles_chunked(
                db, pair, 1440, P6_START, P6_END, exchange=EXCHANGE
            )
            candles_test = [c for c in candles_full if c.timestamp >= test_start]

            uncapped_full = simulate_fixed_dca(candles_full, WEEKLY_AMOUNT, None)
            capped_test = simulate_fixed_dca(candles_test, WEEKLY_AMOUNT, CAPITAL)
            per_pair[pair] = {
                "uncapped_full": uncapped_full,
                "capped_test": capped_test,
            }

        adaptive_test = load_adaptive_dca_test_results()

        report = build_report(per_pair, adaptive_test)
        OUTPUT_PATH.write_text(report)
        print(f"Report: {OUTPUT_PATH}")
    finally:
        await db.close_db()


if __name__ == "__main__":
    asyncio.run(main())
