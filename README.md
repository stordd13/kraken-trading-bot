# KrakenBot - Automated BTC/EUR Trading Bot

> **⚠️ WARNING**: This is an automated trading system. Use at your own risk. Always start in paper trading mode.

## Overview

KrakenBot is an automated trading system for the Kraken cryptocurrency exchange, designed for BTC/EUR trading with:

- **High-frequency relative trading** (10-15 minute intervals)
- **Multiple concurrent strategies** support
- **Long-term data accumulation** via TimescaleDB
- **Paper trading mode** for safe testing
- **Risk management** built-in from day one

## Quick Start

### Prerequisites

- Python 3.11+
- PostgreSQL 15+ with TimescaleDB extension
- Kraken account with API credentials (for live trading)

### Installation

1. Clone the repository:
```bash
git clone <repository-url>
cd kraken-trading-bot
```

2. Create and activate a virtual environment:
```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

3. Install dependencies:
```bash
pip install -e ".[dev]"
```

4. Set up your environment:
```bash
cp .env.example .env
# Edit .env with your configuration
```

5. Set up the database:
```bash
# Start PostgreSQL with TimescaleDB (using Docker):
docker compose up -d db

# Run migrations:
alembic upgrade head
```

### Running the Bot

**Paper Trading (Recommended to start):**
```bash
python -m krakenbot
```

**Live Trading (⚠️ Use with caution):**
```bash
# Edit .env and set:
# TRADING_MODE=live
# TRADING_CONFIRM_LIVE=yes

python -m krakenbot
```

## Architecture

```
src/krakenbot/
├── config/          # Pydantic-based configuration
├── core/            # Database, EventBus, Logging
├── connectors/      # Kraken WebSocket & REST clients
├── models/          # SQLAlchemy ORM models
├── strategies/      # Trading strategies
├── execution/       # Order execution & risk management
└── utils/           # Helper utilities
```

## Configuration

All configuration is done via environment variables (loaded from `.env`):

- See [.env.example](.env.example) for all available options
- See [CLAUDE.md](CLAUDE.md) for detailed documentation

### Key Settings

| Variable | Default | Description |
|----------|---------|-------------|
| `TRADING_MODE` | `paper` | Trading mode (`paper` or `live`) |
| `TRADING_PAIR` | `XBT/EUR` | Trading pair |
| `RISK_DAILY_LOSS_LIMIT_EUR` | `50.0` | Daily loss limit |
| `STRATEGY_NAME` | `threshold` | Active strategy |

## Strategies

### Threshold Strategy (Default)

Simple mean-reversion strategy:
- **Buy** when price drops by X% (default: -1%)
- **Sell** when price rises by Y% from entry (default: +2%)

Configure via:
- `STRATEGY_BUY_THRESHOLD_PCT`
- `STRATEGY_SELL_THRESHOLD_PCT`

## Development

### Code Quality

```bash
# Format code
ruff format .

# Lint
ruff check . --fix

# Type check
mypy src/

# Run tests
pytest

# With coverage
pytest --cov=krakenbot --cov-report=html
```

### Pre-commit Hooks

```bash
pre-commit install
```

## Safety Features

1. **Paper Trading Default**: Never trades real money unless explicitly configured
2. **Live Mode Confirmation**: Requires `TRADING_CONFIRM_LIVE=yes` flag
3. **Daily Loss Limits**: Automatic trading halt on excessive losses
4. **Position Size Limits**: Maximum exposure controls
5. **Rate Limiting**: Respects Kraken API limits
6. **Comprehensive Logging**: Every decision is logged

## Project Status

- [x] Project structure
- [x] Configuration system
- [ ] Database models
- [ ] Kraken WebSocket connector
- [ ] Kraken REST connector
- [ ] Threshold strategy implementation
- [ ] Execution engine
- [ ] Risk management system
- [ ] Paper trading mode
- [ ] Live trading mode
- [ ] Backtesting framework
- [ ] Monitoring dashboard

## Resources

- [Kraken API Documentation](https://docs.kraken.com/)
- [TimescaleDB Documentation](https://docs.timescale.com/)
- [Project Documentation](./CLAUDE.md)

## License

MIT

## Disclaimer

This software is for educational purposes only. Cryptocurrency trading carries significant risk. The authors are not responsible for any financial losses incurred through the use of this software.

**USE AT YOUR OWN RISK.**
