# 📋 PRD - KrakenBot Trading System
## Product Requirement Document v1.0

---

## 1. Executive Summary

### 1.1 Vision
Développer un système de trading automatisé robuste et évolutif pour le trading BTC/EUR sur Kraken, capable de passer de stratégies simples basées sur des règles à des stratégies avancées utilisant le Machine Learning.

### 1.2 Objectifs Clés
- **Automatisation complète**: Trading 24/7 sans intervention humaine
- **Scalabilité**: Support de multiples bots/stratégies en parallèle
- **Évolutivité**: Architecture permettant l'intégration future de ML/RL
- **Robustesse**: Gestion des erreurs, reconnexion automatique, garde-fous

### 1.3 Métriques de Succès
| Métrique | Objectif MVP | Objectif v2 |
|----------|--------------|-------------|
| Uptime | 95% | 99.5% |
| Latence exécution | < 5s | < 1s |
| Data loss | 0% | 0% |
| Order execution success (technique) | > 95% | > 99% |

---

## 2. Contexte & Analyse

### 2.1 Problème à Résoudre
- Les données historiques minute-par-minute sont limitées à 1 mois sur Kraken
- Le trading manuel est inefficace pour les stratégies haute fréquence
- L'évolution vers le ML nécessite des mois de données accumulées

### 2.2 Solution Proposée
Un système modulaire qui:
1. Accumule les données en temps réel pour constituer un dataset long terme
2. Exécute des stratégies de trading automatiquement
3. Permet l'ajout facile de nouvelles stratégies (y compris ML)

### 2.3 Contraintes
- **Budget**: Utilisation de technologies open-source
- **Réglementation**: Respect des limites API Kraken
- **Capital**: Trades de petits montants (5-20€ par trade)

---

## 3. User Stories

### 3.1 Data Collection
```
EN TANT QUE système,
JE VEUX collecter les données OHLC et ticks en temps réel,
AFIN DE constituer un historique exploitable pour le backtesting et le ML.
```

**Critères d'acceptation:**
- [ ] Connexion WebSocket stable à Kraken
- [ ] Stockage dans TimescaleDB sans perte de données
- [ ] Reconnexion automatique en cas de déconnexion
- [ ] Logs structurés pour chaque événement

### 3.2 Paper Trading
```
EN TANT QUE trader,
JE VEUX tester mes stratégies en mode simulation,
AFIN DE valider leur comportement sans risquer de capital.
```

**Critères d'acceptation:**
- [ ] Mode paper trading par défaut
- [ ] Simulation réaliste (slippage, fees)
- [ ] Logs identiques au mode live
- [ ] Calcul du P&L simulé

### 3.3 Live Trading
```
EN TANT QUE trader,
JE VEUX que le bot exécute des ordres réels sur Kraken,
AFIN DE générer des profits automatiquement.
```

**Critères d'acceptation:**
- [ ] Activation explicite requise (flag + confirmation)
- [ ] Toutes les protections de risque actives
- [ ] Notifications en cas d'événement important
- [ ] Possibilité d'arrêt d'urgence

### 3.4 Multi-Stratégies
```
EN TANT QUE trader,
JE VEUX déployer plusieurs stratégies en parallèle,
AFIN DE diversifier mes approches de trading.
```

**Critères d'acceptation:**
- [ ] Chaque stratégie a son propre état isolé
- [ ] Allocation de capital par stratégie
- [ ] Logs taggués par stratégie
- [ ] Métriques séparées par stratégie

---

## 4. Spécifications Fonctionnelles

### 4.1 Module: Data Ingestor

**Responsabilités:**
- Maintenir une connexion WebSocket avec Kraken
- Recevoir et parser les données OHLC et ticks
- Publier les données sur l'Event Bus interne
- Persister les données dans TimescaleDB

**API Kraken utilisées:**
```
WebSocket Public:
- ohlc (candles 1min, 5min, 15min)
- ticker (prix temps réel)
- trade (transactions)

REST Public:
- OHLC historique (pour seed initial)
- Server Time (synchronisation)
```

**Schéma de données:**
```python
@dataclass
class OHLCData:
    timestamp: datetime
    pair: str
    interval: int  # minutes
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: Decimal
    vwap: Decimal  # Volume Weighted Average Price
    count: int     # Number of trades

@dataclass
class TickData:
    timestamp: datetime
    pair: str
    price: Decimal
    volume: Decimal
    side: Literal["buy", "sell"]
```

### 4.2 Module: Strategy Engine

**Responsabilités:**
- Gérer le cycle de vie des stratégies
- Dispatcher les événements de marché aux stratégies
- Collecter les signaux générés
- Maintenir l'état de chaque stratégie

**Interface Strategy:**
```python
class BaseStrategy(ABC):
    # Lifecycle
    async def initialize(self) -> None: ...
    async def shutdown(self) -> None: ...
    
    # Events
    async def on_ohlc(self, candle: OHLCData) -> None: ...
    async def on_tick(self, tick: TickData) -> None: ...
    
    # Signal generation
    async def generate_signal(self) -> Signal | None: ...
    
    # State management
    def get_state(self) -> StrategyState: ...
    def set_state(self, state: StrategyState) -> None: ...
```

**Stratégie v1 - ThresholdReversion:**
```
PARAMÈTRES:
- buy_threshold_pct: -1.0%  (acheter si baisse de 1%)
- sell_threshold_pct: +2.0% (vendre si gain de 2%)
- trade_amount_eur: 5€
- lookback_minutes: 15

LOGIQUE:
1. Calculer la variation de prix sur les N dernières minutes
2. Si variation < buy_threshold ET pas de position ouverte:
   → Générer signal BUY
3. Si position ouverte ET gain > sell_threshold:
   → Générer signal SELL
4. Sinon: HOLD
```

### 4.3 Module: Execution Engine

**Responsabilités:**
- Recevoir les signaux du Strategy Engine
- Valider les ordres (risk checks)
- Exécuter les ordres via l'API Kraken
- Gérer les confirmations et erreurs

**Flow d'exécution:**
```
Signal → Risk Check → Order Creation → API Call → Confirmation → State Update
                ↓              ↓            ↓            ↓
             Reject         Log         Retry        Log + Event
```

**Risk Checks:**
```python
class RiskManager:
    async def validate_order(self, order: Order) -> ValidationResult:
        checks = [
            self._check_balance(),           # Solde suffisant?
            self._check_position_limit(),    # Limite position?
            self._check_daily_loss(),        # Perte journalière?
            self._check_rate_limit(),        # Rate limit API?
            self._check_market_hours(),      # Marché ouvert?
        ]
        return await self._run_checks(checks)
```

### 4.4 Module: Database

**Tables:**

```sql
-- Market data (TimescaleDB hypertable)
CREATE TABLE market_data_ohlc (
    time TIMESTAMPTZ NOT NULL,
    pair VARCHAR(20) NOT NULL,
    interval_minutes INT NOT NULL,
    open DECIMAL(18,8) NOT NULL,
    high DECIMAL(18,8) NOT NULL,
    low DECIMAL(18,8) NOT NULL,
    close DECIMAL(18,8) NOT NULL,
    volume DECIMAL(18,8) NOT NULL,
    vwap DECIMAL(18,8),
    trade_count INT,
    PRIMARY KEY (time, pair, interval_minutes)
);
SELECT create_hypertable('market_data_ohlc', 'time');

-- Trades executed by bot
CREATE TABLE trades (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    created_at TIMESTAMPTZ DEFAULT NOW(),
    pair VARCHAR(20) NOT NULL,
    side VARCHAR(4) NOT NULL,  -- 'buy' or 'sell'
    amount DECIMAL(18,8) NOT NULL,
    price DECIMAL(18,8) NOT NULL,
    fee DECIMAL(18,8),
    order_id VARCHAR(50),  -- Kraken order ID
    strategy VARCHAR(50) NOT NULL,
    bot_id VARCHAR(50) NOT NULL,
    mode VARCHAR(10) NOT NULL,  -- 'paper' or 'live'
    pnl DECIMAL(18,8)
);

-- Bot state persistence
CREATE TABLE bot_state (
    bot_id VARCHAR(50) PRIMARY KEY,
    strategy VARCHAR(50) NOT NULL,
    status VARCHAR(20) NOT NULL,  -- 'running', 'paused', 'stopped'
    config JSONB NOT NULL,
    state JSONB NOT NULL,
    last_updated TIMESTAMPTZ DEFAULT NOW()
);

-- Risk tracking
CREATE TABLE daily_pnl (
    date DATE PRIMARY KEY,
    realized_pnl DECIMAL(18,8) DEFAULT 0,
    trades_count INT DEFAULT 0,
    max_drawdown DECIMAL(18,8) DEFAULT 0
);
```

---

## 5. Spécifications Non-Fonctionnelles

### 5.1 Performance
| Critère | Exigence |
|---------|----------|
| Latence WebSocket → Signal | < 100ms |
| Latence Signal → Order | < 1s |
| Throughput data ingestion | > 100 msg/s |
| DB write latency | < 50ms |

### 5.2 Disponibilité
- **Uptime cible**: 99.5%
- **Recovery time**: < 5 minutes
- **Data durability**: Aucune perte acceptable

### 5.3 Sécurité
- Secrets stockés dans variables d'environnement
- Pas de secrets dans les logs
- API keys avec permissions minimales (trade only)
- Connexions chiffrées (TLS)

### 5.4 Observabilité
- Logs structurés JSON (structlog)
- Métriques Prometheus-compatible
- Alerting Discord/Telegram pour événements critiques
- Dashboard Grafana (optionnel)

---

## 6. Architecture Technique

### 6.1 Diagramme Haut Niveau

```
┌─────────────────────────────────────────────────────────────────┐
│                         KrakenBot System                         │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  ┌──────────────┐    ┌──────────────┐    ┌──────────────┐       │
│  │   Kraken     │    │   Event      │    │   Strategy   │       │
│  │  WebSocket   │───▶│    Bus       │───▶│   Engine     │       │
│  │  Connector   │    │  (Internal)  │    │              │       │
│  └──────────────┘    └──────────────┘    └──────┬───────┘       │
│         │                   │                    │               │
│         │                   │                    ▼               │
│         │                   │           ┌──────────────┐         │
│         │                   │           │  Execution   │         │
│         │                   │           │   Engine     │         │
│         │                   │           └──────┬───────┘         │
│         │                   │                  │                 │
│         ▼                   ▼                  ▼                 │
│  ┌─────────────────────────────────────────────────────────┐    │
│  │                    TimescaleDB                           │    │
│  │  ┌─────────┐  ┌─────────┐  ┌─────────┐  ┌─────────┐     │    │
│  │  │  OHLC   │  │  Ticks  │  │ Trades  │  │  State  │     │    │
│  │  └─────────┘  └─────────┘  └─────────┘  └─────────┘     │    │
│  └─────────────────────────────────────────────────────────┘    │
│                                                                  │
│  ┌──────────────┐    ┌──────────────┐                           │
│  │   Kraken     │    │  Monitoring  │                           │
│  │  REST API    │    │  & Alerting  │                           │
│  │  Connector   │    │              │                           │
│  └──────────────┘    └──────────────┘                           │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

### 6.2 Stack Technique

| Composant | Technologie | Justification |
|-----------|-------------|---------------|
| Language | Python 3.11+ | Écosystème ML, async natif |
| Runtime | asyncio | Non-bloquant, performant |
| Database | PostgreSQL + TimescaleDB | Time-series optimisé |
| ORM | SQLAlchemy 2.0 | Async support, migrations |
| Config | Pydantic Settings | Validation, type safety |
| Logging | structlog | JSON structuré |
| Exchange | ccxt | Abstraction multi-exchange |
| Container | Docker | Portabilité, isolation |

### 6.3 Dépendances Python

```toml
[project]
dependencies = [
    # Core
    "python-dotenv>=1.0.0",
    "pydantic>=2.5.0",
    "pydantic-settings>=2.1.0",
    
    # Async
    "asyncio>=3.4.3",
    "websockets>=12.0",
    "aiohttp>=3.9.0",
    
    # Exchange
    "ccxt>=4.0.0",
    
    # Database
    "sqlalchemy[asyncio]>=2.0.0",
    "asyncpg>=0.29.0",
    "alembic>=1.13.0",
    
    # Data processing
    "pandas>=2.1.0",
    "numpy>=1.26.0",
    
    # Logging
    "structlog>=23.2.0",
    
    # Utils
    "click>=8.1.0",  # CLI
    "rich>=13.7.0",  # Pretty output
]

[project.optional-dependencies]
dev = [
    "pytest>=7.4.0",
    "pytest-asyncio>=0.23.0",
    "pytest-cov>=4.1.0",
    "mypy>=1.7.0",
    "ruff>=0.1.6",
]
ml = [
    "torch>=2.1.0",
    "transformers>=4.35.0",
    "stable-baselines3>=2.2.0",  # RL
]
```

---

## 7. Roadmap

### Phase 1: MVP (Semaines 1-3)
- [ ] Setup projet (structure, config, Docker)
- [ ] Data Ingestor (WebSocket Kraken)
- [ ] Database (TimescaleDB setup, migrations)
- [ ] Stratégie ThresholdReversion
- [ ] Paper Trading mode
- [ ] Logging structuré

### Phase 2: Production Ready (Semaines 4-6)
- [ ] Live Trading mode (avec protections)
- [ ] Risk Management complet
- [ ] Monitoring & Alerting
- [ ] Backtesting framework basique
- [ ] Documentation complète

### Phase 3: Multi-Stratégies (Semaines 7-9)
- [ ] Multi-bot support
- [ ] Dashboard monitoring (Grafana)
- [ ] API REST pour contrôle
- [ ] Stratégies additionnelles (MACD, RSI, etc.)

### Phase 4: ML Integration (Semaines 10+)
- [ ] Feature engineering pipeline
- [ ] Transformer-based prediction model
- [ ] Reinforcement Learning (PPO)
- [ ] A/B testing framework

---

## 8. Risques & Mitigations

| Risque | Probabilité | Impact | Mitigation |
|--------|-------------|--------|------------|
| Perte de connexion WebSocket | Haute | Moyen | Reconnexion auto + buffer |
| Rate limit Kraken | Moyenne | Moyen | Backoff exponentiel |
| Perte de données | Basse | Haut | WAL PostgreSQL + backups |
| Bug stratégie | Moyenne | Haut | Paper trading + tests |
| API Kraken down | Basse | Haut | Mode pause automatique |

---

## 9. Critères de Validation

### Definition of Done - MVP
- [ ] Tests passent avec coverage > 80%
- [ ] Documentation à jour
- [ ] Docker build successful
- [ ] Paper trading fonctionne 24h sans crash
- [ ] Données stockées correctement dans DB

### Definition of Done - Production
- [ ] Live trading testé avec petit capital
- [ ] Monitoring alertes fonctionnelles
- [ ] Recovery automatique testé
- [ ] Backup DB en place
- [ ] Runbook opérationnel documenté

---

## 10. Annexes

### A. Glossaire
- **OHLC**: Open, High, Low, Close - format de données de prix
- **Tick**: Transaction individuelle sur le marché
- **Signal**: Instruction générée par une stratégie (BUY/SELL/HOLD)
- **Paper Trading**: Simulation de trading sans argent réel
- **Slippage**: Différence entre prix attendu et prix exécuté
- **PnL**: Profit and Loss (gains et pertes)

### B. Références API Kraken
- WebSocket API: https://docs.kraken.com/websockets/
- REST API: https://docs.kraken.com/rest/
- Rate Limits: https://support.kraken.com/hc/en-us/articles/206548367

### C. Configuration Exemple
```env
# .env.example
KRAKEN_API_KEY=your_api_key_here
KRAKEN_API_SECRET=your_api_secret_here
DATABASE_URL=postgresql+asyncpg://user:pass@localhost:5432/krakenbot
TRADING_MODE=paper
LOG_LEVEL=INFO
```
