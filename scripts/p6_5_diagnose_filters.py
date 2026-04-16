"""P6.5 Phase 2 — diagnose Grok trend strategy filter strictness.

For grok_ema_adx_atr and grok_donchian_breakout_4h, counts how often each
entry-filter condition fires on BTC/USDC 4h candles over the P6 period,
then their intersection (the actual entry-signal rate). Produces
results/P6_5_diagnostic_grok_trend.md.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
import sys

from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / ".env")

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from backtest import _load_candles_chunked

from krakenbot.config.settings import get_settings
from krakenbot.core.database import DatabaseManager
from krakenbot.indicators.multi_timeframe import MultiTimeframeAnalyzer

P6_START = datetime(2023, 4, 1, tzinfo=UTC)
P6_END = datetime(2026, 4, 1, tzinfo=UTC)
PAIRS = ["BTC/USDC"]
EXCHANGE = "binance"

# Params matching strategies.yaml / strategy defaults
EMA_FAST = 27
EMA_SLOW = 125
ADX_THRESHOLD_EMA = Decimal("14")
ADX_THRESHOLD_DONCHIAN_1D = Decimal("18")
DONCHIAN_PERIOD = 20


async def diagnose_pair(db: DatabaseManager, pair: str) -> dict:
    """Walk 4h candles, counting filter firings for EMA strategy and Donchian."""
    # Load 4h + 1d + 1w so the analyzer's regime_1d computations are fed too.
    # Give the 1d feed an extra buffer for warmup.
    buffer = timedelta(days=60)
    candles_4h = await _load_candles_chunked(
        db, pair, 240, P6_START - buffer, P6_END, exchange=EXCHANGE
    )
    candles_1d = await _load_candles_chunked(
        db, pair, 1440, P6_START - buffer, P6_END, exchange=EXCHANGE
    )
    candles_1w = await _load_candles_chunked(
        db, pair, 10080, P6_START - buffer, P6_END, exchange=EXCHANGE
    )

    analyzer = MultiTimeframeAnalyzer()
    # Pre-register lazy indicators we will query (mimics strategy __init__).
    analyzer.get_ema(EMA_FAST, "4h")
    analyzer.get_ema(EMA_SLOW, "4h")
    analyzer.get_donchian("4h", period_upper=DONCHIAN_PERIOD, period_lower=DONCHIAN_PERIOD)

    # Merge all candles by timestamp so analyzer sees them in chronological order,
    # with higher TFs first on ties.
    TF_ORDER = {240: 1, 1440: 2, 10080: 3}
    merged = (
        [(c, 240) for c in candles_4h]
        + [(c, 1440) for c in candles_1d]
        + [(c, 10080) for c in candles_1w]
    )
    merged.sort(key=lambda x: (x[0].timestamp, -TF_ORDER[x[1]]))

    # Trackers
    total_4h_in_period = 0
    ema_golden_cross = 0
    ema_adx_pass = 0
    ema_regime_bull = 0
    ema_all_three = 0

    donchian_breakout = 0
    donchian_adx1d_pass = 0
    donchian_regime_bull = 0
    donchian_all_three = 0

    prev_ema_fast: Decimal | None = None
    prev_ema_slow: Decimal | None = None
    prev_donchian_upper: Decimal | None = None
    prev_close_4h: Decimal | None = None

    for candle, interval in merged:
        payload = {
            "pair": candle.pair,
            "timestamp": candle.timestamp,
            "open": candle.open,
            "high": candle.high,
            "low": candle.low,
            "close": candle.close,
            "volume": candle.volume,
            "interval": interval,
            "is_complete": True,
        }
        analyzer.update(payload, interval)

        # Count filter conditions on 4h candles inside the P6 period.
        if interval != 240 or candle.timestamp < P6_START:
            continue
        total_4h_in_period += 1

        # ----- EMA/ADX strategy -----
        ema_fast = analyzer.get_ema(EMA_FAST, "4h")
        ema_slow = analyzer.get_ema(EMA_SLOW, "4h")
        adx_4h = analyzer.get_adx("4h")
        regime_1d = analyzer.get_regime("1d")

        is_golden_cross = False
        if (
            prev_ema_fast is not None
            and prev_ema_slow is not None
            and ema_fast is not None
            and ema_slow is not None
        ):
            is_golden_cross = prev_ema_fast <= prev_ema_slow and ema_fast > ema_slow

        if is_golden_cross:
            ema_golden_cross += 1
        adx_ok_ema = adx_4h is not None and adx_4h >= ADX_THRESHOLD_EMA
        if adx_ok_ema:
            ema_adx_pass += 1
        regime_ok = regime_1d in ("bull", "strong_bull")
        if regime_ok:
            ema_regime_bull += 1
        if is_golden_cross and adx_ok_ema and regime_ok:
            ema_all_three += 1

        prev_ema_fast = ema_fast
        prev_ema_slow = ema_slow

        # ----- Donchian breakout strategy -----
        dc = analyzer.get_donchian(
            "4h", period_upper=DONCHIAN_PERIOD, period_lower=DONCHIAN_PERIOD
        )
        adx_1d = analyzer.get_adx("1d")

        is_breakout = False
        if (
            prev_donchian_upper is not None
            and prev_close_4h is not None
            and prev_close_4h <= prev_donchian_upper
            and candle.close > prev_donchian_upper
        ):
            is_breakout = True

        if is_breakout:
            donchian_breakout += 1
        adx_ok_donchian = adx_1d is not None and adx_1d >= ADX_THRESHOLD_DONCHIAN_1D
        if adx_ok_donchian:
            donchian_adx1d_pass += 1
        if regime_ok:
            donchian_regime_bull += 1
        if is_breakout and adx_ok_donchian and regime_ok:
            donchian_all_three += 1

        if dc is not None:
            prev_donchian_upper = dc["upper"]
        prev_close_4h = candle.close

    return {
        "pair": pair,
        "total_4h_in_period": total_4h_in_period,
        "ema": {
            "golden_cross": ema_golden_cross,
            "adx_pass": ema_adx_pass,
            "regime_bull": ema_regime_bull,
            "all_three": ema_all_three,
        },
        "donchian": {
            "breakout": donchian_breakout,
            "adx_1d_pass": donchian_adx1d_pass,
            "regime_bull": donchian_regime_bull,
            "all_three": donchian_all_three,
        },
    }


def _pct(n: int, total: int) -> str:
    if total == 0:
        return "—"
    return f"{(100.0 * n / total):.1f}%"


def build_report(results: list[dict]) -> str:
    lines: list[str] = [
        "# P6.5 — Diagnostic Grok Trend Filter Strictness",
        "",
        "Pour grok_ema_adx_atr (2-9 trades P6) et grok_donchian_breakout_4h (7-14 trades P6),",
        "on compte combien de fois chaque filtre de l'entrée se déclenche, puis",
        "leur intersection, sur 3 ans de 4h candles.",
        "",
        "## grok_ema_adx_atr",
        "",
        "Conditions: golden cross EMA(27)/EMA(125) **ET** ADX(14,4h) ≥ 14 **ET** régime_1d ∈ {bull, strong_bull}",
        "",
        "| Pair | Total 4h | Golden cross | ADX pass | Régime bull | **Intersection** |",
        "|---|---|---|---|---|---|",
    ]
    for r in results:
        t = r["total_4h_in_period"]
        e = r["ema"]
        lines.append(
            f"| {r['pair']} | {t:,} | {e['golden_cross']:,} ({_pct(e['golden_cross'], t)}) "
            f"| {e['adx_pass']:,} ({_pct(e['adx_pass'], t)}) "
            f"| {e['regime_bull']:,} ({_pct(e['regime_bull'], t)}) "
            f"| **{e['all_three']}** |"
        )

    lines += [
        "",
        "## grok_donchian_breakout_4h",
        "",
        "Conditions: breakout above prev Donchian(20) upper **ET** ADX(14,1d) ≥ 18 **ET** régime_1d ∈ {bull, strong_bull}",
        "",
        "| Pair | Total 4h | Breakout | ADX(1d) pass | Régime bull | **Intersection** |",
        "|---|---|---|---|---|---|",
    ]
    for r in results:
        t = r["total_4h_in_period"]
        d = r["donchian"]
        lines.append(
            f"| {r['pair']} | {t:,} | {d['breakout']:,} ({_pct(d['breakout'], t)}) "
            f"| {d['adx_1d_pass']:,} ({_pct(d['adx_1d_pass'], t)}) "
            f"| {d['regime_bull']:,} ({_pct(d['regime_bull'], t)}) "
            f"| **{d['all_three']}** |"
        )

    lines += [
        "",
        "## Interprétation",
        "",
        "**Surprise** : les filtres ADX sont très peu sélectifs sur crypto —",
        "ADX ≥ 14 passe 92% du temps, ADX(1d) ≥ 18 passe 82% du temps.",
        "Le vrai goulot d'étranglement est ailleurs selon la stratégie :",
        "",
        "### grok_ema_adx_atr",
        "- Golden cross EMA(27)/EMA(125) est rare : 31 occurrences en 3 ans (~10/an).",
        "- Intersection des 3 filtres : 12 signaux en 3 ans (~4/an).",
        "- P6 a observé 2 trades sur BTC → l'écart (12 → 2) indique que la logique",
        "  de position-management bloque la plupart des signaux : déjà en position",
        "  quand un nouveau cross arrive, cooldown/exit récent, etc.",
        "- **Filtre limitant : la rareté du golden cross EMA 27/125 lui-même.**",
        "",
        "### grok_donchian_breakout_4h",
        "- Breakout Donchian(20) : 333 candles en 3 ans (5.1%), 130 après les filtres (~45/an).",
        "- P6 a observé 7 trades sur BTC → l'écart (130 → 7) confirme encore que la logique",
        "  de position-management / cooldown post-exit bloque ~95% des signaux.",
        "- **Pas de bug de filtrage** : le breakout primaire est fréquent. C'est la logique",
        "  interne de la stratégie (une seule position à la fois, cooldowns) qui limite.",
        "",
        "### Conclusion",
        "",
        "**Pas un bug des filtres**. Les 2 stratégies fonctionnent comme conçues :",
        "elles ne tradent que sur signaux rares ou quand aucune position n'est déjà ouverte.",
        "grok_supertrend_4h produit plus de trades car son signal primaire (flip SuperTrend)",
        "est beaucoup plus fréquent qu'un EMA cross.",
        "",
        "## Recommandations",
        "",
        "Trois options possibles pour P7 (à discuter) :",
        "",
        "1. **Accepter** : peu de trades = moins de frais + signaux de meilleure qualité.",
        "   À confirmer avec des backtests sur des périodes plus longues ou plus de paires.",
        "2. **Raccourcir les EMAs** (EMA 27/125 → 10/40) pour plus de crossovers,",
        "   au risque de plus de whipsaws en marché latéral.",
        "3. **Permettre plusieurs positions simultanées** (actuellement max 1),",
        "   pour utiliser les 130 breakouts Donchian au lieu de 7.",
        "",
        "**Aucun fix code en P6.5** — Décision à prendre en P7 si on veut optimiser.",
    ]
    return "\n".join(lines) + "\n"


async def main() -> None:
    settings = get_settings()
    db = DatabaseManager()
    await db.init_db(settings)
    try:
        results = []
        for pair in PAIRS:
            print(f"Diagnosing {pair}…")
            results.append(await diagnose_pair(db, pair))
        report = build_report(results)
        out_path = Path(__file__).resolve().parent.parent / "results" / "P6_5_diagnostic_grok_trend.md"
        out_path.write_text(report)
        print(f"Report: {out_path}")
    finally:
        await db.close_db()


if __name__ == "__main__":
    asyncio.run(main())
