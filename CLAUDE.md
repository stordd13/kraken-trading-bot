# CLAUDE.md - Instructions pour Claude Code

> Ce fichier définit le contexte, les conventions et la vision du projet. Voir TODO.md pour les tâches restantes.

## Projet: KrakenBot - Trading Automatisé BTC

**Objectif**: Système de trading automatisé sur Kraken (BTC/USDC) avec:
- Collecte de données 24/7 (WebSocket + REST backfill)
- Multiple stratégies déployables en parallèle
- Pipeline de données pour accumulation d'historique long terme
- Évolution future vers ML/RL

**Vision**:
1. **Court terme**: Bot fonctionnel avec stratégie simple (seuils) ✅
2. **Moyen terme**: Backtesting + monitoring + multi-stratégies
3. **Long terme**: Intégration ML (Transformers + RL)

---

## Architecture (2 services séparés)

```
┌─────────────────────────────┐    ┌─────────────────────────────┐
│   krakenbot-collector       │    │      krakenbot              │
│   (Toujours actif 24/7)     │    │   (Start/Stop flexible)     │
│                             │    │                             │
│  - WebSocket real-time      │    │  - ThresholdStrategy        │
│  - REST API backfill        │    │  - ExecutionEngine          │
│  - TaskScheduler            │    │  - Paper/Live trading       │
└──────────────┬──────────────┘    └──────────────┬──────────────┘
               └────────────┬──────────────────────┘
                            ▼
               ┌─────────────────────────┐
               │  PostgreSQL/TimescaleDB │
               │     (Hetzner VPS)       │
               └─────────────────────────┘
```

**Entry points:**
- `python -m krakenbot.collector` → Data collector (24/7)
- `python -m krakenbot` → Trading bot (paper/live)
- `python scripts/dashboard.py` → Dashboard Dash (localhost:8050)

---

## Structure du Projet

```
src/krakenbot/
├── collector.py      # Service standalone collecte données
├── main.py           # Trading bot
├── config/           # Settings Pydantic
├── core/             # Database, EventBus, Logger
├── connectors/       # KrakenWS, KrakenREST
├── models/           # SQLAlchemy ORM
├── strategies/       # ThresholdStrategy (+ futures stratégies)
├── execution/        # ExecutionEngine, RiskManager
└── scheduler/        # TaskScheduler (backfill)

scripts/
├── dashboard.py      # Dashboard Dash temps réel
└── backtest.py       # Backtesting

deploy/
├── krakenbot.service           # Systemd trading bot
└── krakenbot-collector.service # Systemd data collector
```

---

## Conventions de Code

### Python
- **Version**: Python 3.11+
- **Type hints**: OBLIGATOIRES sur toutes les fonctions
- **Async/await**: Partout, jamais de code bloquant
- **Imports absolus**: `from krakenbot.core import ...`
- **Decimal**: Pour les montants (jamais float)
- **UTC**: Pour tous les timestamps

### Style
```python
# ✅ BON
async def fetch_ohlc(pair: str, interval: int = 15) -> list[OHLCData]:
    """Fetch OHLC data from Kraken."""
    ...

# ❌ MAUVAIS
def fetch_ohlc(pair, interval=15):
    ...
```

### Naming
- **Classes**: PascalCase (`ThresholdStrategy`)
- **Fonctions/Variables**: snake_case (`calculate_signal`)
- **Constantes**: UPPER_SNAKE_CASE (`MAX_POSITION_SIZE`)

### Linting
```bash
ruff check . --fix && ruff format .
```

---

## Base de Données

- **PostgreSQL 15 + TimescaleDB**
- **Tables**: `market_data_ohlc`, `trades_history`, `bot_state`, `task_execution_logs`
- **Déduplication**: Clé composite `(timestamp, pair, interval)` + `session.merge()`
- **Migrations**: Alembic

---

## Stratégies de Trading

### Interface de Base
```python
class BaseStrategy(ABC):
    @abstractmethod
    async def on_tick(self, data: MarketData) -> None:
        """Appelé à chaque nouveau tick."""

    @abstractmethod
    async def generate_signal(self) -> Signal | None:
        """Génère un signal (BUY/SELL/HOLD)."""
```

### Stratégie v1: ThresholdStrategy
```python
buy_threshold_pct: float = -1.0   # Acheter si -1%
sell_threshold_pct: float = 2.0   # Vendre si +2%
rolling_window: int = 20
trade_amount: float = 5.0         # USDC par trade
```

---

## Risk Management

### Paramètres
```python
max_position_pct: 5.0        # Max 5% du portfolio par trade
daily_loss_limit: 50         # Stop si perte > 50 USDC/jour
max_open_positions: 3        # Max 3 positions simultanées
min_trade_interval_sec: 60   # Min 1 min entre trades
```

### Checks Avant Chaque Trade
1. ✅ Vérifier le solde disponible
2. ✅ Vérifier la limite de position
3. ✅ Vérifier la perte journalière
4. ✅ Vérifier le rate limit API
5. ✅ Logger la décision avec contexte complet

---

## Secrets (.env)

```bash
KRAKEN_API_KEY=xxx
KRAKEN_API_SECRET=xxx
DATABASE_URL=postgresql+asyncpg://user:pass@localhost:5432/krakenbot
TRADING_MODE=paper  # paper | live
```

**Règles**:
- JAMAIS de secrets dans le code
- JAMAIS de commit de `.env`
- Utiliser `.env.example` comme template

---

## Commandes

```bash
# Dev local
poetry install
poetry run python -m krakenbot.collector
poetry run python -m krakenbot
poetry run python scripts/dashboard.py  # avec tunnel SSH

# Lint & Tests
poetry run ruff check . --fix && poetry run ruff format .
poetry run pytest
poetry run mypy src/
```

---

## Déploiement (Hetzner)

**CI/CD**: Push `main` → GitHub Actions → Deploy auto

```bash
# Sur le serveur
sudo systemctl status krakenbot-collector
sudo systemctl status krakenbot
sudo journalctl -u krakenbot-collector -f
```

**Dashboard (depuis Mac):**
```bash
ssh -L 5432:localhost:5432 bruno@<IP> -N &
poetry run python scripts/dashboard.py
# http://localhost:8050
```

---

## Mode Live (⚠️ ATTENTION)

```bash
# Mode paper (défaut)
TRADING_MODE=paper python -m krakenbot

# Mode live (requiert confirmation)
TRADING_MODE=live TRADING_CONFIRM_LIVE=yes python -m krakenbot
```

---

## Ressources

- [Kraken WebSocket API](https://docs.kraken.com/websockets/)
- [Kraken REST API](https://docs.kraken.com/rest/)
- [TimescaleDB Docs](https://docs.timescale.com/)
- [TODO.md](./TODO.md) - Tâches restantes
