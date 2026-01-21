# CLAUDE.md - KrakenBot

## Projet
Bot de trading automatisé BTC/USDC sur Kraken avec collecte de données 24/7.

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

## Structure

```
src/krakenbot/
├── collector.py      # Service standalone collecte données
├── main.py           # Trading bot
├── config/           # Settings Pydantic
├── core/             # Database, EventBus, Logger
├── connectors/       # KrakenWS, KrakenREST
├── models/           # SQLAlchemy ORM
├── strategies/       # ThresholdStrategy
├── execution/        # ExecutionEngine, RiskManager
└── scheduler/        # TaskScheduler (backfill)

scripts/dashboard.py  # Dashboard Dash temps réel

deploy/
├── krakenbot.service           # Systemd trading bot
└── krakenbot-collector.service # Systemd data collector
```

## Conventions

- **Python 3.11+**, type hints obligatoires
- **Async/await** partout
- **Imports absolus**: `from krakenbot.core import ...`
- **Linting**: `ruff check . --fix && ruff format .`
- **Decimal** pour les montants (jamais float)
- **UTC** pour tous les timestamps

## Commandes

```bash
# Dev local
poetry install
poetry run python -m krakenbot.collector
poetry run python -m krakenbot
poetry run python scripts/dashboard.py  # avec tunnel SSH

# Lint
poetry run ruff check . --fix && poetry run ruff format .

# Tests
poetry run pytest
```

## Déploiement (Hetzner)

**CI/CD**: Push `main` → GitHub Actions → Deploy auto

```bash
# Sur le serveur
sudo systemctl status krakenbot-collector
sudo systemctl status krakenbot
sudo journalctl -u krakenbot-collector -f
sudo journalctl -u krakenbot -f
```

**Dashboard (depuis Mac):**
```bash
ssh -L 5432:localhost:5432 bruno@<IP> -N &
poetry run python scripts/dashboard.py
# http://localhost:8050
```

## Base de Données

- **PostgreSQL 15 + TimescaleDB**
- **Tables**: `market_data_ohlc`, `trades_history`, `bot_state`, `task_execution_logs`
- **Déduplication**: Clé `(timestamp, pair, interval)` + `session.merge()`

## Stratégie: ThresholdStrategy

```python
buy_threshold_pct: float = -1.0   # Acheter si -1%
sell_threshold_pct: float = 2.0   # Vendre si +2%
rolling_window: int = 20
trade_amount: float = 5.0         # USDC par trade
```

## Risk Management

- `max_position_pct`: 5% portfolio max/trade
- `daily_loss_limit`: 50 USDC/jour
- `min_trade_interval_sec`: 60s entre trades
- Mode paper par défaut, live requiert `TRADING_MODE=live`

## Secrets (.env)

```bash
KRAKEN_API_KEY=xxx
KRAKEN_API_SECRET=xxx
DATABASE_URL=postgresql+asyncpg://user:pass@localhost:5432/krakenbot
TRADING_MODE=paper  # paper | live
```
