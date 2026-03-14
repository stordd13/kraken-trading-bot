# KrakenBot - Automated BTC Trading Bot

> **WARNING**: Automated trading system. Use at your own risk. Always start in paper trading mode.

## Overview

KrakenBot is an automated trading system for Kraken exchange (BTC/USDC) with:
- **Two independent services**: Data collector (24/7) + Trading bot
- **Paper trading mode** for safe testing
- **Real-time dashboard** (Dash)
- **Risk management** built-in

## Architecture

```
┌─────────────────────────────┐    ┌──────────────────────────────────────┐
│   krakenbot-collector       │    │      krakenbot                       │
│   (Always running 24/7)     │    │   (Start/Stop as needed)             │
│                             │    │                                      │
│  - WebSocket real-time      │    │  - MultiStrategyRouter (7 strategies)│
│  - REST API backfill        │    │  - GeminiGlobalRiskManager           │
│  - TaskScheduler            │    │  - ExecutionEngine                   │
│                             │    │  - Paper/Live trading                │
└──────────────┬──────────────┘    └──────────────┬───────────────────────┘
               └────────────┬──────────────────────┘
                            ▼
               ┌─────────────────────────┐
               │  PostgreSQL/TimescaleDB │
               └─────────────────────────┘
```

## Quick Start

### Prerequisites
- Python 3.11+
- PostgreSQL 15+ with TimescaleDB
- Poetry

### Installation

```bash
git clone https://github.com/stordd13/kraken-trading-bot.git
cd kraken-trading-bot
poetry install
cp .env.example .env  # Edit with your config
```

### Database Setup

```bash
# Using Docker
docker compose up -d db

# Run migrations
poetry run alembic upgrade head
```

### Running

```bash
# Data collector (run 24/7)
poetry run python -m krakenbot.collector

# Trading bot (paper mode by default)
poetry run python -m krakenbot

# Dashboard (requires SSH tunnel to DB)
# Make the local forwarded port match DATABASE_URL.
# Example if DATABASE_URL uses localhost:5433:
# autossh -M 0 -f -N -L 5433:localhost:5432 bruno@<server-ip> -p <ssh-port>
poetry run python scripts/dashboard.py
# Open http://localhost:8050
```

## Configuration

Base config via `.env` file, strategy config via `strategies.yaml`:

```bash
# .env — base settings
KRAKEN_API_KEY=xxx
KRAKEN_API_SECRET=xxx
DATABASE_URL=postgresql+asyncpg://user:pass@localhost:5433/krakenbot
TRADING_MODE=paper          # paper | live
TRADING_PAIR=XBT/USDC
TRADING_DEFAULT_ORDER_AMOUNT_EUR=15.0
RISK_MAX_POSITION_PCT=5.0
RISK_DAILY_LOSS_LIMIT_EUR=50.0
```

Strategy configuration lives in `strategies.yaml` (multi-strategy mode with 7 strategies + risk manager). See [CLAUDE.md](./CLAUDE.md) and [krakenbot-etat-complet-feb2026.md](./krakenbot-etat-complet-feb2026.md) for details.

## Deployment (Hetzner VPS)

CI/CD: Push to `main` → GitHub Actions → Auto deploy

```bash
# Check services on server
sudo systemctl status krakenbot-collector
sudo systemctl status krakenbot
sudo journalctl -u krakenbot-collector -f
```

## Development

```bash
# Lint & format
poetry run ruff check . --fix
poetry run ruff format .

# Tests
poetry run pytest

# Type check
poetry run mypy src/
```

## Project Structure

```
src/krakenbot/
├── collector.py          # Data collector service
├── main.py               # Trading bot + STRATEGY_REGISTRY
├── config/               # Pydantic settings
├── core/                 # Database, EventBus, Logger
├── connectors/           # KrakenWS, KrakenREST
├── models/               # SQLAlchemy ORM
├── indicators/           # MultiTimeframeAnalyzer, EMA, RSI, MACD, BB, ATR, ADX, SuperTrend
├── strategies/           # 7 active strategies + router + risk manager + legacy
│   ├── multi_strategy_router.py
│   ├── gemini_global_risk_manager.py
│   ├── gemini_scalping_volatilite.py
│   ├── gemini_suivi_tendance_momentum.py
│   ├── gemini_retour_moyenne.py
│   ├── grok_grid_atr_adaptive_v4.py
│   ├── grok_supertrend_4h.py
│   ├── grok_ema_adx_atr.py
│   └── grok_adaptive_dca_weekly.py
├── execution/            # ExecutionEngine, RiskManager
└── scheduler/            # TaskScheduler

scripts/
├── dashboard.py          # Dash dashboard
├── backtest.py           # BacktestEngine (signal + grid)
└── backtest_grid.py      # Grid search parameters

strategies.yaml           # Multi-strategy configuration
deploy/
├── krakenbot.service
└── krakenbot-collector.service
```

## Safety Features

1. **Paper trading default** - Never trades real money unless explicitly configured
2. **Live mode confirmation** - Requires `TRADING_MODE=live` + `TRADING_CONFIRM_LIVE=yes`
3. **Daily loss limits** - Auto-stops if daily loss exceeds limit
4. **Position size limits** - Max % of portfolio per trade
5. **Minimum trade interval** - Prevents rapid-fire trading
6. **Global risk manager** - 1% max capital risk per trade, ATR-based stop-losses, crash protector (7% drop in 30min)

## Resources

- [Kraken API Docs](https://docs.kraken.com/)
- [TimescaleDB Docs](https://docs.timescale.com/)
- [Project Docs](./CLAUDE.md)
- [TODO](./TODO.md)

## License

MIT

## Disclaimer

This software is for educational purposes only. Cryptocurrency trading carries significant risk. **USE AT YOUR OWN RISK.**
