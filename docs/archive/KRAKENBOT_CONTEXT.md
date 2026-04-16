# KrakenBot — Contexte Projet pour Claude Code (Mars 2026)

> **Ce document donne le contexte minimum nécessaire pour travailler sur KrakenBot.**
> Lire ce fichier EN ENTIER avant de toucher au code.

---

## Qu'est-ce que KrakenBot ?

Bot de trading automatisé BTC/USDC sur Kraken. Deux services indépendants :

- **Collector** (24/7) : collecte candles OHLC via WebSocket Kraken + backfill REST quotidien → PostgreSQL/TimescaleDB
- **Trading Bot** : multi-stratégie via `MultiStrategyRouter`, 7 stratégies internes, `GeminiGlobalRiskManager` filtre chaque BUY

## Situation actuelle (Mars 2026)

- **Serveur Hetzner DOWN** (hack, retour ~fin mars). Pas de backup DB.
- **Données perdues ?** NON — récupérables via API Kraken (backfill REST).
- **Code intact** sur GitHub.
- **7 nouvelles stratégies implémentées** mais **JAMAIS backtestées**. C'est le travail prioritaire.

## Stack & Conventions (OBLIGATOIRES)

- Python 3.11+, 100% async/await
- **Decimal** obligatoire pour prix/montants (jamais float)
- **structlog** pour le logging
- **ccxt** pour REST Kraken, **websockets** pour données live
- **SQLAlchemy 2.0 async** + asyncpg + TimescaleDB (en production)
- **Ruff** pour lint + format, **mypy** pour types
- **Poetry** pour les dépendances

## Fees Kraken (CRITIQUE — à simuler dans TOUT backtest)

| Type | Fee |
|------|-----|
| BUY limit (maker) | 0.16% |
| SELL limit (maker) | 0.16% |
| SELL market (taker) | 0.26% |
| Spread simulé (backtest) | 0.02% |
| Slippage simulé (backtest) | 0.01% |

Round-trip minimum : 0.32% (limit/limit) à 0.42% (limit/market).
**Tout signal doit espérer > 0.5% de move net pour être rentable.**

## Les 7 stratégies à backtester

| # | Classe | bot_id | TF principal | Type | Budget/trade |
|---|--------|--------|-------------|------|-------------|
| 1 | GeminiScalpingVolatilite | scalping_vol | 5m + filtre 1h | Scalping RSI+MACD intraday | 25 USDC |
| 2 | GeminiRetourMoyenne | retour_moy | 15m + filtre 1h | Mean reversion BB + DCA | 20 USDC |
| 3 | GeminiSuiviTendanceMomentum | tendance_mom | 4h + filtre 1d | Trend pullback EMA | 50 USDC |
| 4 | GrokGridATRAdaptiveV4 | grid_atr_v4 | multi-TF | Grid ATR adaptive | 25 USDC |
| 5 | GrokSuperTrend4hRegime | supertrend_4h | 4h + filtre 1d | SuperTrend trend | 50 USDC |
| 6 | GrokEMA27_125_ADX_ATR | ema_cross_4h | 4h + filtre 1d | EMA cross + 3-stage stops | 40 USDC |
| 7 | GrokAdaptiveDCAWeekly | dca_weekly | 1d (lundi) | DCA hebdo adaptatif | 15 USDC/sem |

**Backtester existant** : `SignalBacktester` (strats 1-3, 5-7) + `GridBacktester` (strat 4).

## Données OHLC disponibles via API Kraken

| Intervalle | Profondeur récupérable | Nb candles approx |
|-----------|----------------------|-------------------|
| 1m | ~6-12 mois | variable |
| 5m | ~1-2 ans | ~315k/an |
| 15m | ~3 ans | ~105k |
| 1h | **~9 ans (depuis 2017)** | ~78k |
| 4h | **~9 ans** | ~19.5k |
| 1d | **~9 ans** | ~3.3k |
| 1w | **~9 ans** | ~470 |

## Leçons historiques (context important pour interpréter les résultats)

- **Grid trading = seule approche historiquement profitable** (+45% à +180% sur 3 ans)
- **Mean reversion 5m = toujours perdant** (3 strats testées, 3 échecs)
- **6/6 anciennes stratégies signal-based = zéro profitable**
- **min_spacing grid ≥ 1.5% CRITIQUE** pour couvrir les fees
- **Buy-and-hold BTC fév 2023 → fév 2026 = +180%**, max drawdown -51%

## Structure des fichiers clés

```
src/krakenbot/
├── strategies/
│   ├── base.py                              # BaseStrategy ABC + TradingSignal dataclass
│   ├── multi_strategy_router.py             # Router unique (dispatch 7 strats)
│   ├── gemini_global_risk_manager.py        # Risk overlay (1% rule, ATR SL, crash protector)
│   ├── gemini_scalping_volatilite.py        # Strat 1
│   ├── gemini_retour_moyenne.py             # Strat 2
│   ├── gemini_suivi_tendance_momentum.py    # Strat 3
│   ├── grok_grid_atr_adaptive_v4.py         # Strat 4 (grid)
│   ├── grok_supertrend_4h.py                # Strat 5
│   ├── grok_ema_adx_atr.py                  # Strat 6
│   └── grok_adaptive_dca_weekly.py          # Strat 7
├── indicators/
│   └── multi_timeframe.py                   # MultiTimeframeAnalyzer (EMA, RSI, ATR, MACD, BB, ADX, SuperTrend)
├── execution/
│   ├── engine.py                            # ExecutionEngine
│   └── risk.py                              # GlobalRiskManager
├── connectors/
│   ├── kraken_rest.py                       # REST via ccxt (référence pour l'API)
│   └── kraken_ws.py                         # WebSocket
scripts/
├── backtest.py                              # BacktestEngine (SignalBacktester + GridBacktester)
strategies.yaml                              # Config complète des 7 stratégies
```

## Règles d'or pour tout agent

1. **Ne PAS modifier** MultiStrategyRouter, GeminiGlobalRiskManager, ExecutionEngine, ni aucune stratégie
2. **Ne PAS commencer le ML** — on est en Phase -1A (backtests purs)
3. **Decimal** pour tout prix/montant, **structlog** pour tout log
4. **Fees réalistes** dans tout backtest : maker 0.16%, taker 0.26%, spread 0.02%, slippage 0.01%
5. **Lire le code existant AVANT d'écrire** — réutiliser ce qui existe (ccxt, indicateurs, etc.)
