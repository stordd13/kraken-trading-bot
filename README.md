# KrakenBot - Automated Crypto Trading Bot

> **WARNING**: Automated trading system. Use at your own risk. Always start in paper trading mode.

## Overview

KrakenBot is an automated multi-pair trading system for **Binance** (BTC/USDC, ETH/USDC, SOL/USDC) with:
- **Two independent services**: Data collector (24/7) + Trading bot
- **8 strategies** running in parallel via MultiStrategyRouter
- **Multi-timeframe analysis** (5m, 15m, 1h, 4h, 1d, 1w)
- **Centralized risk management** (1% rule, ATR stop-losses, crash protector)
- **Paper trading mode** for safe testing
- **Real-time dashboard** (Dash)

> Note: Despite its name, the bot has been fully migrated from Kraken to Binance for lower fees (0.075% vs 0.16-0.26%) and better API support.

## Architecture

```
┌────────────────────────────────┐    ┌──────────────────────────────────────┐
│   krakenbot-collector          │    │      krakenbot (trader)               │
│   (Always running 24/7)        │    │   (Start/Stop as needed)             │
│                                │    │                                      │
│  - Binance WebSocket           │    │  - MultiStrategyRouter               │
│    (3 pairs × 7 TF = 21 streams│    │    (8 strategies, pair-aware)        │
│  - REST backfill               │    │  - GeminiGlobalRiskManager           │
│                                │    │  - ExecutionEngine → Binance REST    │
└──────────────┬─────────────────┘    └──────────────┬───────────────────────┘
               └────────────┬──────────────────────────┘
                            ▼
               ┌──────────────────────────┐
               │  PostgreSQL / TimescaleDB │
               │  (~10M rows, 5 yrs data) │
               └──────────────────────────┘
```

## Quick Start

### Prerequisites
- Python 3.12+
- PostgreSQL 16+ with TimescaleDB
- Poetry
- Binance account with API keys

### Installation

```bash
git clone https://github.com/stordd13/kraken-trading-bot.git
cd kraken-trading-bot
poetry install
cp .env.example .env  # Edit with your config
```

### Database Setup

```bash
docker compose up -d db
poetry run alembic upgrade head
```

### Running

```bash
# Data collector (run 24/7)
poetry run python -m krakenbot.collector

# Trading bot (paper mode by default)
poetry run python -m krakenbot

# Dashboard
poetry run python scripts/dashboard.py  # http://localhost:8050
```

## Configuration

Base config via `.env`, strategy config via `strategies.yaml`:

```bash
# .env
EXCHANGE_NAME=binance
BINANCE_API_KEY=xxx
BINANCE_API_SECRET=xxx
DATABASE_URL=postgresql+asyncpg://user:pass@localhost:5432/krakenbot
TRADING_MODE=paper
```

Strategy configuration in `strategies.yaml` — multi-strategy router with per-pair strategy instances. See [CLAUDE.md](./CLAUDE.md) for conventions and [PROJECT_CONTEXT.md](./PROJECT_CONTEXT.md) for full project state.

## Development

```bash
poetry run pytest                              # Tests (~1091)
poetry run ruff check . --fix && ruff format . # Lint
poetry run mypy src/                           # Type check

# Backtest
poetry run python scripts/backtest.py \
    --strategy grok_supertrend_4h \
    --pair BTC/USDC \
    --exchange binance \
    --days 1095 --capital 1000
```

## Project Structure

```
src/krakenbot/
├── strategies/           # 8 strategies + router + risk manager
├── indicators/           # MultiTimeframeAnalyzer + per-pair registry
├── execution/            # ExecutionEngine, RiskManager, OrderManager
├── connectors/
│   ├── binance/          # REST + WebSocket (active)
│   └── kraken/           # REST + WebSocket + Futures (legacy)
├── config/               # Pydantic settings, ExchangeFees
├── core/                 # Database, EventBus, Logger
└── models/               # SQLAlchemy ORM

scripts/
├── backtest.py           # BacktestEngine (signal + grid)
├── binance_vision_import.py  # Historical data import
└── dashboard.py          # Dash dashboard
```

## Safety Features

1. **Paper trading default** — never trades real money unless explicitly configured
2. **Live mode confirmation** — requires `TRADING_MODE=live` + `TRADING_CONFIRM_LIVE=yes`
3. **Daily loss limits** — auto-stops if daily loss exceeds threshold
4. **Position sizing** — max risk per trade (1-2% of capital)
5. **ATR stop-losses** — volatility-adapted stops on every position
6. **Crash protector** — detects 7%+ drop in 30min, closes 50% of longs, suspends 2h
7. **Confidence modulation** — strategy conviction level adjusts position size

## Documentation

- [PROJECT_CONTEXT.md](./PROJECT_CONTEXT.md) — Full project state and architecture
- [CLAUDE.md](./CLAUDE.md) — Guide for AI agents working on the project
- [ROADMAP.md](./ROADMAP.md) — Development roadmap (P0–P14)

## License

MIT

## Disclaimer

This software is for educational purposes only. Cryptocurrency trading carries significant risk. **USE AT YOUR OWN RISK.**
