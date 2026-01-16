
# CLAUDE.md - Instructions pour Claude Code

> Ce fichier est automatiquement lu par Claude Code au démarrage. Il définit le contexte, les conventions et les règles du projet.

## 🎯 PROJET: KrakenBot - Trading Automatisé BTC

### Objectif
Système de trading automatisé sur Kraken pour BTC/EUR avec:
- Trading haute fréquence relative (intervalles 10-15 min)
- Multiple stratégies déployables en parallèle
- Pipeline de données pour accumulation d'historique long terme
- Évolution future vers ML/RL



### Vision Produit
1. **Court terme**: Bot fonctionnel avec stratégie simple (seuils)
2. **Moyen terme**: Backtesting + monitoring + multi-stratégies
3. **Long terme**: Intégration ML (Transformers + RL)

---

## 📁 STRUCTURE DU PROJET

```
src/krakenbot/
├── config/          # Configuration Pydantic
├── core/            # Database, EventBus, Logger
├── connectors/      # Kraken WS & REST
├── models/          # SQLAlchemy ORM
├── strategies/      # Logique de trading
├── execution/       # Orders + Risk Management
└── utils/           # Helpers
```

---

## 🔧 CONVENTIONS DE CODE

### Python
- **Version**: Python 3.11+
- **Type hints**: OBLIGATOIRES sur toutes les fonctions
- **Async**: Utiliser `async/await` partout, jamais de code bloquant
- **Imports**: Utiliser imports absolus (`from krakenbot.core import ...`)

### Style
```python
# ✅ BON
async def fetch_ohlc(pair: str, interval: int = 15) -> list[OHLCData]:
    """Fetch OHLC data from Kraken WebSocket.
    
    Args:
        pair: Trading pair (e.g., "XBT/EUR")
        interval: Candle interval in minutes
        
    Returns:
        List of OHLC candles
    """
    ...

# ❌ MAUVAIS
def fetch_ohlc(pair, interval=15):
    ...
```

### Naming
- **Classes**: PascalCase (`ThresholdStrategy`)
- **Fonctions/Variables**: snake_case (`calculate_signal`)
- **Constantes**: UPPER_SNAKE_CASE (`MAX_POSITION_SIZE`)
- **Fichiers**: snake_case (`kraken_ws.py`)

### Error Handling
```python
# Utiliser des exceptions custom
class KrakenAPIError(Exception):
    """Erreur de l'API Kraken."""
    pass

class InsufficientBalanceError(Exception):
    """Solde insuffisant pour le trade."""
    pass

# Logger toutes les erreurs avec contexte
logger.error("Failed to place order", extra={
    "pair": pair,
    "side": side,
    "amount": amount,
    "error": str(e)
})
```

---

## 🗄️ DATABASE

### Tech Stack
- **PostgreSQL 15+** avec **TimescaleDB** extension
- **SQLAlchemy 2.0** avec async support
- **Alembic** pour migrations

### Tables Principales
```sql
-- Données OHLC (hypertable TimescaleDB)
market_data_ohlc (timestamp, pair, open, high, low, close, volume)

-- Ticks temps réel
market_data_ticks (timestamp, pair, price, volume, side)

-- Historique des trades du bot
trades_history (id, timestamp, pair, side, amount, price, strategy, pnl)

-- État des bots
bot_state (bot_id, strategy, status, last_signal, position)
```

### Règles
- TOUJOURS utiliser des transactions
- TOUJOURS utiliser des index sur les colonnes de recherche
- Les timestamps sont TOUJOURS en UTC

---

## 🔐 SÉCURITÉ & SECRETS

### Variables d'Environnement (via .env)
```bash
# Kraken API
KRAKEN_API_KEY=xxx
KRAKEN_API_SECRET=xxx

# Database
DATABASE_URL=postgresql+asyncpg://user:pass@localhost:5432/krakenbot

# Trading Config
TRADING_MODE=paper  # paper | live
MAX_POSITION_EUR=100
DAILY_LOSS_LIMIT_EUR=50
```

### Règles Absolues
1. **JAMAIS** de secrets dans le code
2. **JAMAIS** de commit de `.env`
3. **TOUJOURS** utiliser `.env.example` comme template
4. **TOUJOURS** valider les secrets au démarrage

---

## ⚠️ GESTION DES RISQUES

### Paramètres par Défaut
```python
DEFAULT_RISK_CONFIG = {
    "max_position_pct": 5.0,        # Max 5% du portfolio par trade
    "daily_loss_limit_eur": 50,     # Stop si perte > 50€/jour
    "max_open_positions": 3,        # Max 3 positions simultanées
    "min_trade_interval_sec": 60,   # Min 1 min entre trades
}
```

### Checks Obligatoires Avant Chaque Trade
1. ✅ Vérifier le solde disponible
2. ✅ Vérifier la limite de position
3. ✅ Vérifier la perte journalière
4. ✅ Vérifier le rate limit API
5. ✅ Logger la décision avec contexte complet

---

## 🧪 TESTS

### Structure
```
tests/
├── conftest.py          # Fixtures partagées
├── test_strategies/
│   └── test_threshold.py
├── test_connectors/
│   └── test_kraken_ws.py
└── test_execution/
    └── test_risk.py
```

### Règles
- Coverage minimum: **80%**
- Utiliser `pytest-asyncio` pour les tests async
- Mocker les appels API Kraken (JAMAIS d'appels réels en test)
- Fixtures pour les données de marché simulées

### Commandes
```bash
# Run tous les tests
pytest

# Avec coverage
pytest --cov=krakenbot --cov-report=html

# Tests spécifiques
pytest tests/test_strategies/ -v
```

---

## 🐳 DOCKER

### Stack Complète (docker-compose.yml)
```yaml
services:
  app:
    build: .
    env_file: .env
    depends_on: [db]
    
  db:
    image: timescale/timescaledb:latest-pg15
    volumes:
      - pgdata:/var/lib/postgresql/data
      
  # Optionnel: monitoring
  grafana:
    image: grafana/grafana
```

### Commandes Utiles
```bash
# Démarrer la stack
docker compose up -d

# Voir les logs
docker compose logs -f app

# Rebuild après changements
docker compose build --no-cache app
```

---

## 📊 STRATÉGIES DE TRADING

### Interface de Base
```python
from abc import ABC, abstractmethod
from krakenbot.models import Signal, MarketData

class BaseStrategy(ABC):
    """Classe de base pour toutes les stratégies."""
    
    @abstractmethod
    async def on_tick(self, data: MarketData) -> None:
        """Appelé à chaque nouveau tick."""
        pass
    
    @abstractmethod
    async def generate_signal(self) -> Signal | None:
        """Génère un signal de trading (BUY/SELL/HOLD)."""
        pass
    
    @abstractmethod
    def get_config(self) -> dict:
        """Retourne la config de la stratégie."""
        pass
```

### Stratégie v1: ThresholdReversion
```python
class ThresholdStrategy(BaseStrategy):
    """
    Stratégie simple basée sur des seuils.
    - Achète si le prix baisse de X%
    - Vend si le prix monte de Y% depuis l'achat
    """
    
    def __init__(
        self,
        buy_threshold_pct: float = -1.0,   # Acheter si -1%
        sell_threshold_pct: float = 2.0,   # Vendre si +2%
        trade_amount_eur: float = 5.0,     # 5€ par trade
    ):
        ...
```

---

## 🔄 WORKFLOW DE DÉVELOPPEMENT

### Branches
- `main`: Production stable
- `develop`: Intégration
- `feature/*`: Nouvelles fonctionnalités
- `fix/*`: Corrections de bugs

### Avant Chaque Commit
```bash
# 1. Formatter le code
ruff format .

# 2. Linter
ruff check . --fix

# 3. Type checking
mypy src/

# 4. Tests
pytest
```

### Pre-commit Hook (optionnel)
```yaml
# .pre-commit-config.yaml
repos:
  - repo: https://github.com/astral-sh/ruff-pre-commit
    rev: v0.1.6
    hooks:
      - id: ruff
      - id: ruff-format
```

---

## 📝 LOGS

### Format
Utiliser du JSON structuré pour faciliter l'analyse:
```python
import structlog

logger = structlog.get_logger()

logger.info("trade_executed", 
    pair="XBT/EUR",
    side="buy",
    amount=5.0,
    price=42000.0,
    strategy="threshold_v1"
)
```

### Niveaux
- `DEBUG`: Données de marché, calculs intermédiaires
- `INFO`: Trades exécutés, signaux générés
- `WARNING`: Rate limits approchés, latence élevée
- `ERROR`: Échecs d'ordres, erreurs API
- `CRITICAL`: Limites de risque atteintes, arrêt du bot

---

## 🚀 DÉPLOIEMENT

### Mode Paper Trading (Défaut)
```bash
TRADING_MODE=paper python -m krakenbot
```

### Mode Live (⚠️ ATTENTION)
```bash
# Requiert confirmation explicite
TRADING_MODE=live CONFIRM_LIVE=yes python -m krakenbot
```

---

## 📚 RESSOURCES

- [Kraken WebSocket API](https://docs.kraken.com/websockets/)
- [Kraken REST API](https://docs.kraken.com/rest/)
- [ccxt Documentation](https://docs.ccxt.com/)
- [TimescaleDB Docs](https://docs.timescale.com/)

---

## ❓ QUESTIONS FRÉQUENTES

**Q: Pourquoi TimescaleDB plutôt que PostgreSQL seul?**
A: TimescaleDB est optimisé pour les données time-series avec compression automatique et requêtes temporelles optimisées.

**Q: Pourquoi pas SQLite pour le MVP?**
A: Le passage à PostgreSQL plus tard causerait trop de refactoring. Autant partir sur la bonne stack dès le départ.

**Q: Comment ajouter une nouvelle stratégie?**
A: 
1. Créer une classe dans `src/krakenbot/strategies/`
2. Hériter de `BaseStrategy`
3. Implémenter `on_tick()` et `generate_signal()`
4. Enregistrer dans le registry des stratégies

---

## 🎯 PROCHAINES ÉTAPES

Quand tu travailles sur ce projet, suis cet ordre:
1. **Setup infrastructure** (DB, config, logging)
2. **Data pipeline** (WebSocket Kraken → DB)
3. **Stratégie simple** (ThresholdReversion)
4. **Execution engine** (Paper trading d'abord)
5. **Tests & validation**
6. **Monitoring basique**
7. **Mode live** (avec toutes les protections)
