# KrakenBot - TODO

> Dernière mise à jour: 2026-01-21

## Statut Actuel

- **Data Collector**: En production sur Hetzner (24/7)
- **Trading Bot**: Paper trading en cours
- **Dashboard**: Dash disponible (localhost:8050)

---

## Phase 1: Validation Stratégie Actuelle (EN COURS)

### Analyse Paper Trading
- [ ] Laisser tourner paper trading quelques jours/semaines
- [ ] Analyser les trades exécutés (win rate, P&L, drawdown)
- [ ] Identifier les patterns de trades perdants

### Backtest sur Vraies Données
- [ ] Script backtest avec données collectées
- [ ] Comparer résultats backtest vs paper trading
- [ ] Ajuster paramètres si nécessaire (buy_threshold, sell_threshold, rolling_window)

### Décision Go/No-Go Live
- [ ] Si stratégie rentable ou neutre → Phase 2
- [ ] Si stratégie perdante → itérer sur paramètres

---

## Phase 2: Live Trading + Alertes

### Passage en Live
- [ ] Petit capital initial (50-100€)
- [ ] Surveillance active premiers jours
- [ ] Vérifier exécution réelle des ordres

### Alerting (setup avec bot live pour debug facile)
- [ ] Notifications Telegram/Discord sur trades exécutés
- [ ] Alertes sur erreurs critiques
- [ ] Alertes limites de risque atteintes
- [ ] Rapport quotidien P&L

---

## Phase 3: Stratégies Avancées

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

---

## Phase 4: Machine Learning

### Prérequis
- [ ] Minimum 3-6 mois de données OHLC collectées
- [ ] Features engineering (indicateurs techniques, volume, volatilité)
- [ ] Train/validation/test split temporel

### Modèles à Explorer
- [ ] Baseline: Random Forest / XGBoost sur features techniques
- [ ] LSTM pour séries temporelles
- [ ] Transformer-based (si assez de données)
- [ ] Reinforcement Learning (DQN, PPO)

### Pipeline ML
- [ ] Feature store
- [ ] Backtesting framework ML-compatible
- [ ] Model versioning (MLflow?)
- [ ] A/B testing paper trading

---

## Améliorations Continues (en parallèle)

### Robustesse
- [ ] Gestion reconnexions WebSocket/DB
- [ ] Health checks endpoint (`/health`)
- [ ] Tests unitaires composants critiques

### Monitoring
- [ ] Métriques Prometheus (optionnel)
- [ ] Dashboard Grafana (optionnel)

---

## Complété

- [x] Architecture 2 services (collector + trading bot)
- [x] CI/CD GitHub Actions → Hetzner
- [x] Dashboard Dash temps réel
- [x] Systemd services
- [x] Data collection 24/7
- [x] Paper trading fonctionnel
- [x] Risk management (5 checks)
- [x] 284 tests (100% pass)
