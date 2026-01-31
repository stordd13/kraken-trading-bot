# KrakenBot - TODO

> Dernière mise à jour: 2026-01-31

## Statut Actuel

- **Data Collector**: ✅ En production sur Hetzner (24/7)
- **Trading Bot**: ✅ LIVE (mode live activé, buy_threshold=-3%)
- **Dashboard**: ✅ Dash disponible (localhost:8050, 5 tabs)

---

## Phase 1: Bot Live Fonctionnel ✅ TERMINÉ

- [x] Architecture 2 services (collector + trading bot)
- [x] Data collection 24/7 (WebSocket + REST backfill)
- [x] ThresholdRollingStrategy fonctionnelle
- [x] Risk management (5 checks)
- [x] Paper trading validé
- [x] Live trading activé
- [x] Dashboard Dash avec tab Positions
- [x] CI/CD GitHub Actions → Hetzner
- [x] Backtest avec grid search
- [x] Fix bug timing référence prix (2026-01-31)

---

## Phase 2: Monitoring & Optimisation 🚧 EN COURS

### 2.1 Tracking Positions ✅ FAIT
- [x] Tab "Positions" dans le dashboard
- [x] P&L non réalisé en temps réel
- [x] Durée des positions
- [x] Auto-refresh 10 secondes

### 2.2 Amélioration Backtesting ✅ FAIT
- [x] Intégrer frais Kraken (0.26% taker)
- [x] Simulation slippage + spread (0.01% + 0.02%)
- [x] Métriques avancées (Profit Factor, Sharpe, Sortino, Max Drawdown)
- [x] Validation croisée temporelle (`--cross-validate` flag)

### 2.3 Alertes (Plus tard)
- [ ] Notifications Telegram/Discord sur trades
- [ ] Alertes erreurs critiques
- [ ] Rapport quotidien P&L

---

## Phase 3: Multi-Stratégies 📋 PLANIFIÉ

### Nouvelles Stratégies à Explorer
- [ ] Mean Reversion avec Bollinger Bands
- [ ] Momentum (RSI, MACD)
- [ ] VWAP strategy
- [ ] Multi-timeframe analysis (1m + 15m + 1h)

### Infrastructure Multi-Stratégies
- [ ] Registry de stratégies
- [ ] Comparaison backtest entre stratégies
- [ ] Paper trading parallèle de plusieurs stratégies
- [ ] Allocation capital par stratégie

### Multi-Pair
- [ ] Support XBT/EUR
- [ ] Support ETH/USDC
- [ ] Corrélation analysis entre pairs

---

## Phase 4: Machine Learning 🔮 LONG TERME

### Prérequis
- [ ] Minimum 3-6 mois de données OHLC collectées
- [ ] Features engineering (indicateurs techniques, volume, volatilité)
- [ ] Train/validation/test split temporel

### Modèles à Explorer
- [ ] Baseline: Random Forest / XGBoost sur features techniques
- [ ] LSTM pour séries temporelles
- [ ] Transformer-based (si assez de données)
- [ ] Reinforcement Learning (DQN, PPO)

---

## Historique Complété

- [x] Architecture 2 services (collector + trading bot)
- [x] CI/CD GitHub Actions → Hetzner
- [x] Dashboard Dash temps réel (5 tabs)
- [x] Systemd services
- [x] Data collection 24/7
- [x] Paper trading fonctionnel
- [x] Risk management (5 checks)
- [x] Live trading activé
- [x] Tab Positions avec P&L temps réel
- [x] Fix bug timing référence prix
- [x] Backtest avec frais réalistes + Sortino + cross-validation
