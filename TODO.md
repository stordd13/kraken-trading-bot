# KrakenBot - TODO & Progress Tracker

> Dernière mise à jour: 2026-01-15

## 📊 Résumé Global

**Statut actuel:** Infrastructure core + Connecteurs Kraken ✅
**Prochaine étape:** Stratégies de trading + Execution engine

---

## ✅ Complété Aujourd'hui (2026-01-15)

### 1. Infrastructure de Base
- [x] Structure complète du projet créée
- [x] `pyproject.toml` avec toutes les dépendances (Python 3.11+)
- [x] `.env.example` avec configuration complète
- [x] `.gitignore` pour protéger les secrets
- [x] `README.md` avec documentation

### 2. Configuration (Pydantic)
- [x] `config/settings.py` - Configuration complète avec validation
  - KrakenSettings (API keys, rate limits)
  - DatabaseSettings (PostgreSQL + TimescaleDB)
  - RiskManagementSettings (limites de risque)
  - TradingSettings (mode paper/live, confirmation explicite)
  - StrategySettings (paramètres de stratégie)
- [x] Validation au démarrage
- [x] Protection mode live (requiert `CONFIRM_LIVE=yes`)

### 3. Core Modules
- [x] `core/logger.py` - Logging structuré avec structlog
  - Format JSON pour production
  - Masquage automatique des secrets
  - Context binding pour traçabilité
- [x] `core/database.py` - Base de données async
  - SQLAlchemy 2.0 async
  - Support TimescaleDB
  - Connection pooling
  - Context managers pour sessions
- [x] `core/event_bus.py` - Système pub/sub asynchrone
  - Subscribe/unsubscribe
  - Wildcard subscriptions
  - Event history tracking
  - Statistics
- [x] `core/exceptions.py` - Exceptions custom
  - KrakenAPIError, WebSocketError
  - TradingError, RiskLimitExceededError
  - DataError, ConfigurationError

### 4. Models ORM
- [x] `models/base.py` - Types et enums communs
  - TradeSide, TradeStatus, BotStatus
  - Custom types: DecimalMoney, TimestampUTC
- [x] `models/market_data.py` - Données de marché
  - OHLCData (hypertable TimescaleDB)
  - TickData
  - Propriétés calculées (price_change, etc.)
- [x] `models/trades.py` - Trading
  - Trade (historique des ordres)
  - BotState (état persistant du bot)

### 5. Database Migrations
- [x] Alembic configuré (async)
- [x] Migration initiale (`20240115_000000_001_initial_schema.py`)
  - Création extension TimescaleDB
  - Création tables avec indexes
  - Conversion OHLC en hypertable

### 6. Connecteurs Kraken
- [x] `connectors/kraken_ws.py` - WebSocket client
  - Connexion auto-reconnect
  - Subscriptions OHLC, ticker, trades
  - Sauvegarde en DB automatique
  - Publication sur EventBus
  - Heartbeat monitoring
- [x] `connectors/kraken_rest.py` - REST client (ccxt)
  - Mode paper trading complet (simulation)
  - Mode live trading (avec ccxt)
  - Balance queries
  - Market orders (buy/sell)
  - Gestion des erreurs et rate limits

### 7. Tests
- [x] 11 fichiers de tests créés
- [x] Fixtures partagées (`conftest.py`)
- [x] Tests pour tous les modules core
- [x] Tests pour les connecteurs (mocked)
- [x] Coverage configuré dans `pyproject.toml`

---

## 🚧 En Cours / À Valider

**Rien** - En attente de validation pour la prochaine étape.

---

## 📋 Reste À Faire (selon PRD)

### Phase 1 - MVP (Priorité Haute)

#### 3. Stratégies de Trading
- [ ] `strategies/base.py` - Classe abstraite BaseStrategy
  - [ ] Interface on_tick() / on_ohlc()
  - [ ] Méthode generate_signal()
  - [ ] TradingSignal dataclass (BUY/SELL/HOLD)
- [ ] `strategies/threshold.py` - ThresholdStrategy
  - [ ] Logique mean reversion simple
  - [ ] Buy si prix baisse de X%
  - [ ] Sell si profit de Y%
  - [ ] État persistant (position, entry price)

#### 4. Execution & Risk Management
- [ ] `execution/risk.py` - RiskManager
  - [ ] Vérification solde disponible
  - [ ] Limite de position (% portfolio)
  - [ ] Limite de perte journalière
  - [ ] Max positions ouvertes
  - [ ] Intervalle minimum entre trades
  - [ ] RiskCheckResult (approved/rejected + raisons)
- [ ] `execution/engine.py` - ExecutionEngine
  - [ ] Écoute EventBus pour signaux
  - [ ] Validation via RiskManager
  - [ ] Exécution ordres via REST client
  - [ ] Mise à jour BotState
  - [ ] Logging complet

#### 5. Point d'Entrée
- [ ] `src/krakenbot/main.py` - Entry point
  - [ ] Initialisation tous les composants
  - [ ] Démarrage WebSocket + Strategy + Execution
  - [ ] Loop principal
  - [ ] Graceful shutdown
  - [ ] Stats périodiques

#### 6. Tests & Validation
- [ ] Tests stratégies
  - [ ] test_strategies/test_base.py
  - [ ] test_strategies/test_threshold.py
- [ ] Tests execution
  - [ ] test_execution/test_risk.py
  - [ ] test_execution/test_engine.py
- [ ] Tests d'intégration end-to-end
- [ ] Validation coverage > 80%

#### 7. Documentation
- [ ] Guides d'utilisation dans `docs/`
  - [ ] Installation et setup
  - [ ] Configuration des stratégies
  - [ ] Paper trading → Live trading
- [ ] Exemples de .env pour différents cas d'usage

### Phase 2 - Production Ready (Priorité Moyenne)

#### 1. Monitoring & Observabilité
- [ ] Dashboard Streamlit simple
  - [ ] Vue temps réel (positions, PnL)
  - [ ] Graphique BTC/EUR avec signaux
  - [ ] Derniers trades
  - [ ] Stats de performance
- [ ] Export métriques pour Grafana (futur)
- [ ] Alertes Discord/Telegram (optionnel)

#### 2. Backtesting Framework
- [ ] `scripts/backtest.py`
  - [ ] Replay historique depuis DB
  - [ ] Simulation stratégie
  - [ ] Calcul métriques (Sharpe, drawdown, etc.)
  - [ ] Export résultats

#### 3. Multi-Stratégies
- [ ] Registre de stratégies
- [ ] Déploiement parallèle de plusieurs bots
- [ ] Isolation des états par stratégie
- [ ] Agrégation des limites de risque

#### 4. Robustesse Production
- [ ] Health checks (DB, API, WS)
- [ ] Graceful degradation si WS déconnecté
- [ ] Retry logic configurable
- [ ] Circuit breakers pour API
- [ ] Sauvegarde état avant shutdown

### Phase 3 - ML/AI (Priorité Basse)

#### 1. Data Pipeline ML
- [ ] Export historique → Parquet/CSV
- [ ] Feature engineering
- [ ] Pipeline d'entraînement
- [ ] Versioning des modèles

#### 2. Stratégies Avancées
- [ ] `strategies/ml_transformer.py` - Placeholder
- [ ] `strategies/rl_ppo.py` - Placeholder
- [ ] Intégration modèles PyTorch
- [ ] A/B testing stratégies

---

## 🎯 Prochaine Session

**Objectif:** Compléter la Phase 1 - MVP

**Tâches prioritaires (dans l'ordre):**
1. ✅ Valider l'architecture actuelle
2. Implémenter `strategies/` (base + threshold)
3. Implémenter `execution/` (risk + engine)
4. Créer `main.py` entry point
5. Tester le bot en mode paper trading end-to-end
6. Fixer les bugs découverts
7. Documentation utilisateur

**Critères de succès MVP:**
- Bot démarre sans erreur
- Reçoit les données Kraken via WebSocket
- Sauvegarde OHLC/ticks en DB
- Génère des signaux BUY/SELL basés sur seuils
- Exécute des ordres en mode paper
- Respecte toutes les limites de risque
- Logs clairs et structurés
- Tests passent avec >80% coverage

---

## 📝 Notes & Décisions

### Paramètres Recommandés (validés)
- **Paper mode:** 15€ par trade, 50€ perte max/jour
- **Live mode:** 10€ par trade, 20€ perte max/jour (pour 1000€ capital)

### Architecture Validée
- ✅ TimescaleDB pour données time-series (pas SQLite)
- ✅ ccxt pour REST API (simplifie auth Kraken)
- ✅ Structlog pour logging JSON
- ✅ Pydantic Settings pour config
- ✅ EventBus interne (pas Redis/RabbitMQ pour MVP)

### Conventions de Code
- Python 3.11+, type hints obligatoires
- Async/await partout
- Decimal pour montants (jamais float!)
- UTC timestamps timezone-aware
- Google-style docstrings
- Ruff pour linting/formatting
- Mypy en mode strict

---

## 🐛 Bugs Connus

**Aucun pour le moment** - En attente de tests end-to-end.

---

## 💡 Idées Futures

- [ ] Support multi-paires (ETH/EUR, etc.)
- [ ] Interface web complète (React/Vue)
- [ ] Mobile app pour monitoring
- [ ] Stratégies basées sur sentiment Twitter
- [ ] Intégration TradingView pour signaux
- [ ] Auto-tuning des paramètres via optimisation bayésienne
