# KrakenBot - Roadmap

> Dernière mise à jour: 2026-01-31

## Vue d'Ensemble

```
Phase 1               Phase 2              Phase 3              Phase 4
┌─────────────────┐    ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐
│ Bot Live        │ →  │ Monitoring &    │→ │ Multi-Stratégie │→ │ Machine         │
│ Fonctionnel     │    │ Optimisation    │  │ & Multi-Pair    │  │ Learning        │
└─────────────────┘    └─────────────────┘  └─────────────────┘  └─────────────────┘
     ✅ DONE              EN COURS             PLANIFIÉ            LONG TERME
```

---

## Phase 1: Bot Live Fonctionnel ✅ TERMINÉ

- [x] Architecture 2 services (collector + trading bot)
- [x] Data collection 24/7 (WebSocket + REST backfill)
- [x] ThresholdRollingStrategy fonctionnelle
- [x] Risk management (5 checks)
- [x] Paper trading validé
- [x] Live trading activé
- [x] Dashboard Dash
- [x] CI/CD GitHub Actions → Hetzner
- [x] Backtest avec grid search

---

## Phase 2: Monitoring & Optimisation 🚧 EN COURS

### 2.1 Tracking des Positions Ouvertes ✅ FAIT

**Objectif**: Voir les positions en cours et le P&L non réalisé

- [x] Query positions ouvertes depuis `trades_history`
- [x] Calcul P&L non réalisé en temps réel
- [x] Tab "Positions" dans le dashboard
- [x] Affichage: entry price, current price, P&L%, durée
- [x] Auto-refresh toutes les 10 secondes

### 2.2 Amélioration Backtesting (PRIORITÉ ACTUELLE)

**Objectif**: Résultats plus réalistes

- [ ] Intégrer frais Kraken (0.26% taker pour market orders)
- [ ] Simulation slippage (0.05%)
- [ ] Métriques avancées (Profit Factor, Sortino, Max Drawdown)
- [ ] Validation croisée temporelle (train 70% / test 30%)

**Fichiers à modifier**:
- `scripts/backtest.py`

### 2.3 Alertes et Notifications (Plus tard)

**Objectif**: Être informé en temps réel des événements importants

- [ ] Setup bot Telegram ou Discord webhook
- [ ] Notification sur trade exécuté (BUY/SELL)
- [ ] Alerte sur erreur critique
- [ ] Alerte limite de risque atteinte (daily loss)
- [ ] Rapport quotidien P&L (optionnel)

**Fichiers à créer**:
- `src/krakenbot/notifications/` - Module notifications
- Config: `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`

---

## Phase 3: Multi-Stratégie & Optimisation 📋 PLANIFIÉ

### 3.1 Nouvelles Stratégies

| Stratégie | Description | Complexité |
|-----------|-------------|------------|
| Bollinger Bands | Mean reversion avec bandes de volatilité | Moyenne |
| RSI Momentum | Overbought/Oversold signals | Facile |
| MACD Crossover | Trend following | Facile |
| VWAP | Volume-weighted average price | Moyenne |
| Multi-Timeframe | Combine 5m + 15m + 1h signals | Complexe |

### 3.2 Infrastructure Multi-Stratégies

- [ ] Registry de stratégies avec activation/désactivation
- [ ] Backtesting comparatif entre stratégies
- [ ] Paper trading parallèle (plusieurs stratégies simultanées)
- [ ] Allocation capital par stratégie

### 3.3 Paramètres Dynamiques

- [ ] Détection de régime (trending vs ranging)
- [ ] Ajustement seuils selon volatilité (ATR-based)
- [ ] Stop-loss dynamique (trailing stop)

### 3.4 Multi-Pair

- [ ] Support XBT/EUR
- [ ] Support ETH/USDC (optionnel)
- [ ] Corrélation analysis entre pairs
- [ ] Allocation intelligente

---

## Phase 4: Machine Learning 🔮 LONG TERME

### Prérequis
- Minimum 3-6 mois de données OHLC
- Feature engineering complet
- Infrastructure ML (MLflow, etc.)

### 4.1 Feature Engineering

- [ ] Indicateurs techniques (RSI, MACD, Bollinger, ATR, etc.)
- [ ] Features de volume et volatilité
- [ ] Features calendaires (hour, day_of_week)
- [ ] Lag features (returns t-1, t-2, etc.)

### 4.2 Modèles Baseline

- [ ] Random Forest / XGBoost sur features techniques
- [ ] Régression logistique comme baseline
- [ ] Évaluation: precision, recall, profit factor

### 4.3 Deep Learning

- [ ] LSTM pour séries temporelles
- [ ] Transformer-based (si assez de données)
- [ ] Attention mechanisms pour feature importance

### 4.4 Reinforcement Learning

- [ ] DQN (Deep Q-Network)
- [ ] PPO (Proximal Policy Optimization)
- [ ] Custom reward function (Sharpe ratio based)

### 4.5 Pipeline ML

- [ ] Feature store
- [ ] Model versioning (MLflow)
- [ ] A/B testing en paper trading
- [ ] Monitoring drift

---

## Métriques de Succès

### Phase 2
- [x] Dashboard affiche positions ouvertes
- [ ] Backtest inclut frais réalistes (0.26%)
- [ ] Notifications reçues en < 30 sec (optionnel)

### Phase 3
- [ ] Au moins 3 stratégies backtestées
- [ ] Paper trading multi-stratégie fonctionnel
- [ ] Au moins 2 pairs supportées

### Phase 4
- [ ] Modèle ML bat la stratégie simple en backtest
- [ ] Pipeline ML automatisé
- [ ] A/B test concluant en paper trading

---

## Notes Techniques

### Stack Actuelle
- Python 3.11+
- AsyncIO everywhere
- PostgreSQL + TimescaleDB
- SQLAlchemy (async)
- Pydantic settings
- Dash (dashboard)
- Poetry (deps)

### Stack Future Potentielle
- Telegram API (notifications)
- MLflow (ML tracking)
- PyTorch/TensorFlow (deep learning)
- Stable-Baselines3 (RL)

---

## Liens

- [PROJECT_STATUS.md](./PROJECT_STATUS.md) - État actuel détaillé
- [CLAUDE.md](./CLAUDE.md) - Instructions développement
- [TODO.md](./TODO.md) - Tâches détaillées (legacy)
