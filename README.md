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
┌─────────────────────────────┐    ┌─────────────────────────────┐
│   krakenbot-collector       │    │      krakenbot              │
│   (Always running 24/7)     │    │   (Start/Stop as needed)    │
│                             │    │                             │
│  - WebSocket real-time      │    │  - ThresholdStrategy        │
│  - REST API backfill        │    │  - ExecutionEngine          │
│  - TaskScheduler            │    │  - Paper/Live trading       │
└──────────────┬──────────────┘    └──────────────┬──────────────┘
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
ssh -L 5432:localhost:5432 bruno@<server-ip> -N &
poetry run python scripts/dashboard.py
# Open http://localhost:8050
```

## Configuration

All config via `.env` file:

```bash
# Kraken API
KRAKEN_API_KEY=xxx
KRAKEN_API_SECRET=xxx

# Database
DATABASE_URL=postgresql+asyncpg://user:pass@localhost:5432/krakenbot

# Trading
TRADING_MODE=paper          # paper | live
TRADING_PAIR=XBT/USDC
TRADING_DEFAULT_ORDER_AMOUNT_EUR=15.0

# Risk Management
RISK_MAX_POSITION_PCT=5.0         # Max 5% portfolio per trade
RISK_DAILY_LOSS_LIMIT_EUR=50.0    # Stop if daily loss > 50€
RISK_MIN_TRADE_INTERVAL_SEC=60    # Min 60s between trades

# Strategy (Threshold)
STRATEGY_BUY_THRESHOLD_PCT=-1.0   # Buy on -1% dip
STRATEGY_SELL_THRESHOLD_PCT=2.0   # Sell on +2% profit
```

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
├── collector.py      # Data collector service
├── main.py           # Trading bot
├── config/           # Pydantic settings
├── core/             # Database, EventBus, Logger
├── connectors/       # KrakenWS, KrakenREST
├── models/           # SQLAlchemy ORM
├── strategies/       # ThresholdStrategy
├── execution/        # ExecutionEngine, RiskManager
└── scheduler/        # TaskScheduler

scripts/
├── dashboard.py      # Dash dashboard
└── backtest.py       # Backtesting

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

## Resources

- [Kraken API Docs](https://docs.kraken.com/)
- [TimescaleDB Docs](https://docs.timescale.com/)
- [Project Docs](./CLAUDE.md)
- [TODO](./TODO.md)

## License

MIT

## Disclaimer

This software is for educational purposes only. Cryptocurrency trading carries significant risk. **USE AT YOUR OWN RISK.**
