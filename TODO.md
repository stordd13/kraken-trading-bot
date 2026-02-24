# TODO

> Tâches restantes, par priorité. L'historique est dans git log, pas ici.

---

## Fait (Feb 2026)

- [x] Valider le multi-strategy en paper mode (les 2 stratégies tournent sans crash)
- [x] Vérifier que le mode legacy fonctionne toujours (`strategies.yaml` absent)
- [x] Backtest AdaptiveStrategy sur 30 jours, comparer vs ThresholdRolling
- [x] Backtest CapitulationStrategy (détecte les capitulations avec MTF actif)
- [x] Backtest TrendFollowing V1+V2 → désactivée (-0.21% sur 3 ans)
- [x] Backtest BearShort → abandonné (-4.79%, oscillation régime)
- [x] GridSpot optimisé (±15%, min_spacing 1.5%)
- [x] GridAdaptive optimisé (spacing clamp, profitability floor, directional pause)
- [x] MultiTimeframeAnalyzer étendu (get_ema lazy, get_supertrend, get_adx, 6 TF)
- [x] 7 nouvelles stratégies implémentées (gemini_scalping, gemini_tendance, gemini_retour, grok_grid_v4, grok_supertrend, grok_ema_cross, grok_dca)
- [x] GeminiGlobalRiskManager (1% rule, ATR SL, crash protector)
- [x] MultiStrategyRouter (orchestrateur 7 strats + risk overlay)
- [x] strategies.yaml complet (7 inner + risk config + legacy disabled)
- [x] Smoke test imports OK (`from krakenbot.strategies import *`)

---

## Urgent — Validation des nouvelles stratégies

- [ ] Backtest individuel des 7 nouvelles stratégies sur 3 ans (quand serveur up)
- [ ] Paper trading du multi_strategy_router complet (minimum 2 semaines)
- [ ] `ruff check . --fix && ruff format .` + `poetry run pytest` — full project
- [ ] Tester le cycle complet limit orders : place → fill → profit target auto → cancel on stop
- [ ] Vérifier la réconciliation au démarrage avec positions ouvertes existantes
- [ ] Désactiver les stratégies non-rentables après analyse backtest
- [ ] Backfill max historique via Binance (9 ans, s'arrête automatiquement quand plus de data) :
  - `poetry run python scripts/import_external_ohlc.py --intervals 1440 10080 --days 3285 -y` (1d + 1w)
  - `poetry run python scripts/import_external_ohlc.py --intervals 60 240 --days 3285 -y` (1h + 4h)
  - `poetry run python scripts/import_external_ohlc.py --intervals 5 15 --days 1095 -y` (5m + 15m, ~3 ans dispo)
- [ ] Vérifier les périodes de données en DB : `SELECT interval, COUNT(*), MIN(timestamp), MAX(timestamp) FROM market_data_ohlc WHERE pair = 'XBT/USDC' GROUP BY interval ORDER BY interval;`

---

## Court terme — Monitoring

- [ ] Alertes Telegram ou Discord
  - Notification sur trade exécuté (BUY/SELL, P&L)
  - Alerte erreur critique / bot stoppé
  - Alerte daily loss limit atteinte
  - Rapport quotidien P&L (optionnel)
  - Fichiers : `src/krakenbot/notifications/`, config `TELEGRAM_BOT_TOKEN`
- [ ] Dashboard : ajouter visualisation du MarketRegime en cours (quel régime, depuis quand)
- [ ] Dashboard : afficher les ordres limit PENDING dans le tab Positions
- [ ] Dashboard : afficher P&L par stratégie (7 stratégies du router)
- [ ] Logging : alerter si le collector a un gap > 30min

---

## Moyen terme — Optimisation

- [ ] Grid search paramètres des 7 nouvelles stratégies (RSI thresholds, ATR mult, spacing, etc.)
- [ ] Analyser les fees réels limit vs market en production (vérifier qu'on est bien maker)
- [ ] Multi-pair : ETH/USDC, SOL/USDC (le collector supporte déjà plusieurs paires)
- [ ] Trailing stop amélioré : trailing par paliers (ex: -2% si profit < 5%, -1.5% si profit > 5%)
- [ ] Backtest comparatif automatisé : lancer les 7 stratégies sur les mêmes données, tableau comparatif

---

## Long terme — ML/RL

**Prérequis : 3 ans de données OHLC collectées (disponibles depuis ~février 2023)**

- [ ] Feature engineering : indicateurs techniques, volume profiles, volatilité, features calendaires
- [ ] Baseline ML : XGBoost/Random Forest sur features techniques
- [ ] Deep Learning : LSTM ou Transformer pour séries temporelles
- [ ] Reinforcement Learning : DQN/PPO avec reward = Sharpe ratio
- [ ] Pipeline ML : feature store, model versioning (MLflow), A/B test paper trading
