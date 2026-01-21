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
- `python -m krakenbot.collector` → Data collector
- `python -m krakenbot` → Trading bot
- `python scripts/dashboard.py` → Dashboard Dash (localhost:8050)

## Structure

```
src/krakenbot/
├── collector.py      # Service standalone collecte données (24/7)
├── main.py           # Trading bot (paper/live)
├── config/           # Settings Pydantic
├── core/             # Database, EventBus, Logger
├── connectors/       # KrakenWS, KrakenREST
├── models/           # SQLAlchemy ORM (market_data_ohlc, trades_history, bot_state)
├── strategies/       # ThresholdStrategy (seule stratégie active)
├── execution/        # ExecutionEngine, RiskManager
└── scheduler/        # TaskScheduler pour backfill historique

scripts/
└── dashboard.py      # Dashboard Dash temps réel

deploy/
├── krakenbot.service           # Systemd trading bot
└── krakenbot-collector.service # Systemd data collector
```

## Conventions de Code

- **Python 3.11+**, type hints obligatoires
- **Async/await** partout, jamais de code bloquant
- **Imports absolus**: `from krakenbot.core import ...`
- **Linting**: `ruff check . --fix && ruff format .`
- **Naming**: PascalCase (classes), snake_case (fonctions/variables)

## Commandes Utiles

```bash
# Dev local
poetry install
poetry run python -m krakenbot.collector  # Collecteur
poetry run python -m krakenbot            # Trading bot
poetry run python scripts/dashboard.py    # Dashboard (avec tunnel SSH)

# Lint/Format
poetry run ruff check . --fix
poetry run ruff format .

# Tests
poetry run pytest
```

## Déploiement (Hetzner VPS)

**CI/CD**: Push sur `main` → GitHub Actions → Deploy automatique

**Services systemd:**
```bash
sudo systemctl status krakenbot-collector  # Doit toujours tourner
sudo systemctl status krakenbot            # Paper/live trading
sudo journalctl -u krakenbot-collector -f  # Logs collector
sudo journalctl -u krakenbot -f            # Logs trading
```

**Dashboard local (avec tunnel SSH):**
```bash
ssh -L 5432:localhost:5432 bruno@<IP> -N &
poetry run python scripts/dashboard.py
# Ouvrir http://localhost:8050
```

## Base de Données

- **PostgreSQL 15 + TimescaleDB** sur Hetzner
- **Tables**: `market_data_ohlc`, `trades_history`, `bot_state`, `task_execution_logs`
- **Déduplication**: Clé composite `(timestamp, pair, interval)` + `session.merge()`

## Stratégie Active: ThresholdStrategy

```python
# Paramètres dans config/settings.py
buy_threshold_pct: float = -1.0   # Acheter si prix baisse de 1%
sell_threshold_pct: float = 2.0   # Vendre si prix monte de 2%
rolling_window: int = 20          # Fenêtre pour calcul
trade_amount: float = 5.0         # Montant USDC par trade
```

## Gestion des Risques

- `max_position_pct`: 5% du portfolio max par trade
- `daily_loss_limit`: Stop si perte > 50 USDC/jour
- `min_trade_interval_sec`: 60s minimum entre trades
- Mode paper par défaut, live requiert `TRADING_MODE=live`

## Secrets (.env)

```bash
KRAKEN_API_KEY=xxx
KRAKEN_API_SECRET=xxx
DATABASE_URL=postgresql+asyncpg://user:pass@localhost:5432/krakenbot
TRADING_MODE=paper  # paper | live
```

## TODO (Prochaines étapes)

### Priorité haute
- [ ] Alerting Telegram/Discord sur trades et erreurs
- [ ] Backtest sur les vraies données collectées
- [ ] Analyse des trades paper trading

### Priorité moyenne
- [ ] Tests unitaires composants critiques
- [ ] Health checks endpoint
- [ ] Métriques Prometheus

### Long terme
- [ ] Passage en live (petit capital 50-100€)
- [ ] Multi-stratégies en parallèle
- [ ] ML/RL avec données accumulées
