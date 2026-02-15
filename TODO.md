# TODO

> Tâches restantes, par priorité. L'historique est dans git log, pas ici.

---

## Urgent — Debug & Stabilisation

- [x] Valider le multi-strategy en paper mode (les 2 stratégies tournent sans crash)
- [x] Vérifier que le mode legacy fonctionne toujours (`strategies.yaml` absent)
- [ ] Tester le cycle complet limit orders : place → fill → profit target auto → cancel on stop
- [ ] Vérifier la réconciliation au démarrage avec positions ouvertes existantes
- [x] Backtest AdaptiveStrategy sur 30 jours, comparer vs ThresholdRolling
- [x] Backtest CapitulationStrategy (détecte les capitulations avec MTF actif)

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
- [ ] Logging : alerter si le collector a un gap > 30min

---

## Moyen terme — Optimisation

- [ ] Grid search pour AdaptiveStrategy (regime multipliers, trailing stop %, volume threshold)
- [ ] Optimiser les seuils de CapitulationStrategy (RSI thresholds, cooldown, trailing %)
- [ ] Analyser les fees réels limit vs market en production (vérifier qu'on est bien maker)
- [ ] Multi-pair : ETH/USDC, SOL/USDC (le collector supporte déjà plusieurs paires)
- [ ] Trailing stop amélioré : trailing par paliers (ex: -2% si profit < 5%, -1.5% si profit > 5%)
- [ ] Backtest comparatif automatisé : lancer les 3 stratégies sur les mêmes données, tableau comparatif

---

## Long terme — ML/RL

**Prérequis : 3-6 mois de données OHLC collectées (on accumule depuis ~janvier 2026)**

- [ ] Feature engineering : indicateurs techniques, volume profiles, volatilité, features calendaires
- [ ] Baseline ML : XGBoost/Random Forest sur features techniques
- [ ] Deep Learning : LSTM ou Transformer pour séries temporelles
- [ ] Reinforcement Learning : DQN/PPO avec reward = Sharpe ratio
- [ ] Pipeline ML : feature store, model versioning (MLflow), A/B test paper trading
