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

## Architecture Overview

KrakenBot uses an **event-driven architecture** where components communicate through an internal EventBus. Here's the data flow:

```
┌──────────────────────────────────────────────────────────────────┐
│                          KrakenBot Main                           │
│                    (Orchestrates everything)                      │
└───────────────────────────────┬──────────────────────────────────┘
                                │
                ┌───────────────┼───────────────┐
                │               │               │
                ▼               ▼               ▼
        ┌──────────────┐ ┌──────────┐ ┌────────────────┐
        │   EventBus   │ │ Database │ │    Logging     │
        │  (Pub/Sub)   │ │ Manager  │ │  (structlog)   │
        └──────┬───────┘ └────┬─────┘ └────────────────┘
               │              │
    ┌──────────┼──────────────┼──────────────┐
    │          │              │              │
    ▼          ▼              ▼              ▼
┌─────────┐ ┌────────┐ ┌────────────┐ ┌──────────────┐
│Kraken WS│ │Strategy│ │  Execution │ │ REST Client  │
│ Client  │ │        │ │   Engine   │ │  (ccxt)      │
└────┬────┘ └───┬────┘ └─────┬──────┘ └──────┬───────┘
     │          │            │               │
     │ Publishes│ Subscribes │ Executes      │ Places
     │ OHLC/    │ to market  │ signals after │ orders
     │ ticks    │ data       │ risk check    │
     └──────────┴────────────┴───────────────┘
```

### Component Lifecycle

1. **Startup Order** (critical for proper operation):
   ```
   Settings → EventBus → Database → REST Client → WebSocket Client
   → Execution Engine → Strategy → WS Subscribe
   ```

2. **Data Flow**:
   - WebSocket receives market data (OHLC candles, ticks)
   - Data is saved to database and published to EventBus
   - Strategy receives data, analyzes it, generates signals
   - ExecutionEngine receives signals, checks risk, executes orders
   - Results are logged and stored in database

3. **Shutdown** (graceful, reverse order):
   ```
   Strategy stop → Execution stop → WebSocket disconnect → Database close
   ```

---

## Detailed Component Documentation

### 1. Configuration Module ([config/settings.py](src/krakenbot/config/settings.py))

**Purpose**: Centralized configuration with validation using Pydantic Settings.

**Key Classes**:

- **`Settings`**: Main application settings container
  - Loads from `.env` file automatically
  - Validates all settings at startup
  - Provides convenience properties like `is_live_trading`

- **`KrakenSettings`**: Kraken API configuration
  - API keys (stored as SecretStr for security)
  - WebSocket/REST URLs
  - Rate limiting parameters

- **`TradingSettings`**: Trading behavior configuration
  - Trading mode (paper/live) with explicit confirmation required for live
  - Trading pair and default order amounts
  - Candle interval for analysis

- **`RiskManagementSettings`**: Risk limits
  - Max position size (% of portfolio)
  - Daily loss limit (EUR)
  - Max open positions
  - Emergency stop-loss percentage

- **`StrategySettings`**: Strategy parameters
  - Strategy name to use
  - Buy/sell thresholds
  - Lookback periods for analysis

- **`ScheduledTasksSettings`**: Scheduled data collection
  - Enable/disable scheduled tasks
  - Cron expressions for data collection jobs
  - Trading pairs to collect data for
  - OHLC intervals (1min, 5min, 15min, 1h)
  - Batch size for database inserts

**Usage Example**:
```python
from krakenbot.config.settings import get_settings

settings = get_settings()
if settings.is_live_trading:
    print("⚠️  LIVE TRADING MODE - Real money at risk!")
```

---

### 2. Core Modules

#### 2.1 EventBus ([core/event_bus.py](src/krakenbot/core/event_bus.py))

**Purpose**: Internal publish-subscribe system for decoupled component communication.

**Key Features**:
- **Type-safe events**: Events are strings like `"ohlc:XBT/EUR"` or `"trade:signal"`
- **Wildcard subscriptions**: Subscribe to `"ohlc:*"` to receive all OHLC events
- **Async callbacks**: All event handlers are async functions
- **Event history**: Keeps track of recent events for debugging
- **Statistics**: Tracks publish/subscribe counts

**Event Types**:
- `ohlc:{pair}`: OHLC candle data received
- `tick:{pair}`: Real-time tick data
- `trade:signal`: Trading signal generated by strategy
- `trade:executed`: Order successfully executed
- `trade:rejected`: Order rejected by risk manager

**Usage Example**:
```python
# Subscribe to events
async def on_ohlc(event_type: str, data: dict):
    print(f"Received OHLC: {data['close']}")

await event_bus.subscribe("ohlc:XBT/EUR", on_ohlc)

# Publish events
await event_bus.publish("ohlc:XBT/EUR", {
    "pair": "XBT/EUR",
    "close": 42000.0,
    "timestamp": datetime.now(UTC)
})
```

#### 2.2 Database Manager ([core/database.py](src/krakenbot/core/database.py))

**Purpose**: Async database connection management with SQLAlchemy 2.0 and TimescaleDB.

**Key Features**:
- **Async engine**: Non-blocking database operations
- **Connection pooling**: Reuses connections efficiently
- **Context managers**: Automatic transaction management
- **TimescaleDB support**: Optimized for time-series data

**Usage Example**:
```python
db_manager = DatabaseManager(settings.database.url)
await db_manager.connect()

# Use session context manager
async with db_manager.session() as session:
    ohlc = OHLCData(pair="XBT/EUR", timestamp=now, open=42000, ...)
    session.add(ohlc)
    await session.commit()
```

#### 2.3 Logger ([core/logger.py](src/krakenbot/core/logger.py))

**Purpose**: Structured JSON logging with automatic secret masking.

**Key Features**:
- **JSON output**: Machine-readable logs for analysis
- **Context binding**: Attach context to all subsequent logs
- **Secret masking**: Automatically hides API keys, secrets in logs
- **Log levels**: DEBUG, INFO, WARNING, ERROR, CRITICAL

**Usage Example**:
```python
from krakenbot.core.logger import get_logger

logger = get_logger()
logger = logger.bind(strategy="threshold", pair="XBT/EUR")
logger.info("signal_generated", signal_type="BUY", price=41500.0)
```

---

### 3. Connectors

#### 3.1 WebSocket Client ([connectors/kraken_ws.py](src/krakenbot/connectors/kraken_ws.py))

**Purpose**: Real-time market data from Kraken via WebSocket.

**Key Features**:
- **Auto-reconnect**: Automatically reconnects on connection loss
- **Multiple subscriptions**: OHLC, ticker, trades
- **Database persistence**: Saves all data to TimescaleDB
- **EventBus integration**: Publishes data for strategies
- **Heartbeat monitoring**: Detects stale connections

**Subscriptions**:
- **OHLC**: Candlestick data (configurable interval, default 15min)
- **Ticker**: Current price, volume, spread
- **Trades**: Individual trades on the exchange

**Usage Example**:
```python
ws_client = KrakenWebSocketClient(settings.kraken, db_manager, event_bus)
await ws_client.connect()
await ws_client.subscribe_ohlc("XBT/EUR", interval=15)
# Data flows automatically to database and event bus
```

#### 3.2 REST Client ([connectors/kraken_rest.py](src/krakenbot/connectors/kraken_rest.py))

**Purpose**: Order execution and balance queries via Kraken REST API.

**Key Features**:
- **Paper trading mode**: Simulates orders without touching real money
  - Simulated EUR balance (default 1000€)
  - Simulated BTC balance (default 0.01 BTC)
  - Tracks simulated positions
- **Live trading mode**: Real orders via ccxt library
- **Balance queries**: Get EUR and crypto balances
- **Market orders**: Buy/sell at current market price

**Paper Trading Behavior**:
```python
# In paper mode, orders are simulated:
result = await rest_client.place_market_order("XBT/EUR", "buy", Decimal("15.0"))
# Returns simulated order:
# {
#   "order_id": "paper_123456",
#   "pair": "XBT/EUR",
#   "side": "buy",
#   "amount_eur": 15.0,
#   "price": 42000.0,  # Simulated current price
#   "fee": 0.15  # 1% fee
# }
```

---

### 4. Models ([models/](src/krakenbot/models/))

#### 4.1 Base Types ([models/base.py](src/krakenbot/models/base.py))

**Enums**:
- `TradeSide`: BUY, SELL
- `TradeStatus`: PENDING, FILLED, CANCELLED, FAILED
- `BotStatus`: IDLE, RUNNING, STOPPED, ERROR

**Custom Types**:
- `DecimalMoney`: PostgreSQL NUMERIC(20, 8) for precise money values
- `TimestampUTC`: Timezone-aware UTC timestamps

#### 4.2 Market Data ([models/market_data.py](src/krakenbot/models/market_data.py))

**`OHLCData`**: Candlestick data (TimescaleDB hypertable)
```python
class OHLCData(Base):
    timestamp: datetime  # Indexed
    pair: str           # e.g., "XBT/EUR"
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: Decimal

    # Calculated properties:
    @property
    def price_change_pct(self) -> Decimal:
        """Price change percentage from open to close."""
```

**`TickData`**: Real-time individual trades

#### 4.3 Trades ([models/trades.py](src/krakenbot/models/trades.py))

**`Trade`**: Historical record of executed orders
```python
class Trade(Base):
    id: UUID
    timestamp: datetime
    pair: str
    side: TradeSide
    amount_crypto: Decimal
    amount_eur: Decimal
    price: Decimal
    fee: Decimal
    pnl: Decimal | None  # Profit/Loss for this trade
    strategy: str
    status: TradeStatus
```

**`BotState`**: Persistent state of the bot
```python
class BotState(Base):
    bot_id: str
    strategy: str
    status: BotStatus
    last_signal_at: datetime | None
    current_position_crypto: Decimal  # Current holdings
    entry_price: Decimal | None       # Entry price if in position
    total_pnl: Decimal                # Cumulative profit/loss
    daily_pnl: Decimal                # Today's profit/loss
    trade_count: int
    last_updated: datetime
```

---

### 5. Trading Strategies

#### 5.1 Base Strategy ([strategies/base.py](src/krakenbot/strategies/base.py))

**`TradingSignal`**: Data class representing a trading decision
```python
@dataclass
class TradingSignal:
    signal_type: SignalType  # BUY, SELL, or HOLD
    pair: str
    price: Decimal
    confidence: float        # 0.0 to 1.0
    reason: str             # Human-readable explanation
    strategy: str           # Strategy name
    timestamp: datetime
    metadata: dict[str, Any]
```

**`BaseStrategy`**: Abstract base class for all strategies
```python
class BaseStrategy(ABC):
    @abstractmethod
    async def on_tick(self, tick_data: dict[str, Any]) -> None:
        """Called on every price tick."""

    @abstractmethod
    async def on_ohlc(self, ohlc_data: dict[str, Any]) -> None:
        """Called on every completed candle."""

    @abstractmethod
    async def generate_signal(self) -> TradingSignal | None:
        """Generate trading signal based on current data."""

    async def start(self) -> None:
        """Start the strategy (subscribe to events)."""

    async def stop(self) -> None:
        """Stop the strategy (unsubscribe from events)."""
```

#### 5.2 Threshold Strategy ([strategies/threshold.py](src/krakenbot/strategies/threshold.py))

**Purpose**: Simple mean-reversion strategy using price thresholds.

**Algorithm**:
1. **Track price history**: Maintains a rolling window of closing prices
2. **Calculate reference price**: Moving average of last N candles (default: 10)
3. **Generate BUY signal** when:
   - Current price < reference price - X% (default: -1%)
   - AND bot has no position
   - Confidence based on how far below threshold
4. **Generate SELL signal** when:
   - Current price > entry price + Y% (default: +2%)
   - AND bot has an open position
   - Confidence based on profit percentage

**State Management**:
- Reads position from `BotState` in database
- Knows if currently in a position or not
- Tracks entry price for profit calculation

**Example Scenario**:
```
Price history: [42000, 41800, 41900, 41700, 41600]
Moving average: 41800
Current price: 41400
Buy threshold: 41800 * 0.99 = 41382

→ Current price (41400) < Threshold (41382)
→ Generate BUY signal with confidence 0.8
```

**Configuration**:
```bash
STRATEGY_NAME=threshold
STRATEGY_BUY_THRESHOLD_PCT=-1.0   # Buy on -1% dip
STRATEGY_SELL_THRESHOLD_PCT=2.0    # Sell on +2% profit
STRATEGY_LOOKBACK_PERIODS=10       # Use 10 candles for MA
```

---

### 6. Execution System

#### 6.1 Risk Manager ([execution/risk.py](src/krakenbot/execution/risk.py))

**Purpose**: Validate every order against risk limits before execution.

**Five Critical Checks**:

1. **Sufficient Balance**
   ```python
   # For BUY orders: Check EUR balance
   if side == TradeSide.BUY:
       eur_balance = balance.get("EUR", Decimal("0"))
       if eur_balance < amount:
           return RiskCheckResult(approved=False,
               reasons=["Insufficient EUR balance"])

   # For SELL orders: Check crypto balance
   elif side == TradeSide.SELL:
       crypto_amount = amount / price
       if crypto_balance < crypto_amount:
           return RiskCheckResult(approved=False,
               reasons=["Insufficient crypto balance"])
   ```

2. **Position Size Limit** (default: 5% of portfolio)
   ```python
   total_balance = eur_balance + (crypto_balance * price)
   max_position = total_balance * (max_position_pct / 100)
   if amount > max_position:
       return RiskCheckResult(approved=False,
           reasons=[f"Order exceeds {max_position_pct}% portfolio limit"])
   ```

3. **Daily Loss Limit** (default: 50 EUR)
   ```python
   bot_state = await get_bot_state()
   if bot_state.daily_pnl < -daily_loss_limit_eur:
       return RiskCheckResult(approved=False,
           reasons=["Daily loss limit exceeded"])
   ```

4. **Max Open Positions** (default: 3)
   ```python
   if side == TradeSide.BUY:
       open_positions = await count_open_positions()
       if open_positions >= max_open_positions:
           return RiskCheckResult(approved=False,
               reasons=[f"Already at max {max_open_positions} positions"])
   ```

5. **Minimum Trade Interval** (default: 60 seconds)
   ```python
   time_since_last = now - bot_state.last_signal_at
   if time_since_last < timedelta(seconds=min_trade_interval_sec):
       return RiskCheckResult(approved=False,
           reasons=[f"Last trade was {time_since_last.seconds}s ago"])
   ```

**Result**:
```python
@dataclass
class RiskCheckResult:
    approved: bool
    reasons: list[str]  # Empty if approved, contains rejection reasons if not
```

#### 6.2 Execution Engine ([execution/engine.py](src/krakenbot/execution/engine.py))

**Purpose**: Orchestrate order execution with risk validation.

**Workflow**:
```
1. Receive TradingSignal from EventBus (published by strategy)
2. Calculate order amount (from settings or signal)
3. Query current balance from REST client
4. Validate with RiskManager
5a. If APPROVED:
    - Execute order via REST client
    - Update BotState with new position/P&L
    - Publish "trade:executed" event
    - Log success
5b. If REJECTED:
    - Publish "trade:rejected" event
    - Log rejection with reasons
    - Do NOT place order
```

**P&L Calculation**:
```python
# When closing a position (SELL after BUY):
if side == TradeSide.SELL and bot_state.current_position_crypto > 0:
    cost_basis = bot_state.entry_price * bot_state.current_position_crypto
    proceeds = current_price * bot_state.current_position_crypto
    pnl = proceeds - cost_basis - fees
    bot_state.total_pnl += pnl
    bot_state.daily_pnl += pnl
```

**Statistics Tracking**:
- Signals received
- Signals executed
- Signals rejected (with breakdown by reason)
- Average execution time

**Usage**:
```python
engine = ExecutionEngine(
    event_bus=event_bus,
    rest_client=rest_client,
    risk_manager=risk_manager,
    db_manager=db_manager,
    settings=settings
)
await engine.start()
# Now listens for "trade:signal" events automatically
```

---

### 7. Main Entry Point

#### 7.1 KrakenBot Orchestrator ([main.py](src/krakenbot/main.py))

**Purpose**: Coordinate all components and manage their lifecycle.

**Responsibilities**:
1. **Setup Phase**: Initialize all components
   ```python
   async def setup(self):
       self.settings = get_settings()
       self.logger = get_logger()
       self.event_bus = EventBus()
       self.db_manager = DatabaseManager(self.settings.database.url)
       self.rest_client = KrakenRestClient(...)
       self.ws_client = KrakenWebSocketClient(...)
       self.risk_manager = RiskManager(...)
       self.execution_engine = ExecutionEngine(...)
       self.strategy = ThresholdStrategy(...)
   ```

2. **Start Phase**: Start components in correct order
   ```python
   async def start(self):
       await self.db_manager.connect()
       await self.ws_client.connect()
       await self.execution_engine.start()  # MUST start before strategy!
       await self.strategy.start()
       await self.ws_client.subscribe_ohlc(pair, interval)
   ```

3. **Run Phase**: Main event loop with periodic stats
   ```python
   async def run(self):
       while self._running:
           await asyncio.sleep(60)  # Log stats every 60s
           self._log_stats()
   ```

4. **Stop Phase**: Graceful shutdown in reverse order
   ```python
   async def stop(self):
       await self.strategy.stop()
       await self.execution_engine.stop()
       await self.ws_client.disconnect()
       await self.db_manager.disconnect()
   ```

**Signal Handling**:
```python
# Registers handlers for SIGINT (Ctrl+C) and SIGTERM
signal.signal(signal.SIGINT, self._handle_signal)
signal.signal(signal.SIGTERM, self._handle_signal)
```

**Periodic Statistics**:
Every 60 seconds, logs:
- WebSocket: messages received, connection status
- Execution Engine: signals received/executed/rejected
- Strategy: signals generated, current position

---

## Configuration Guide

### Environment Variables

All configuration via `.env` file. Copy `.env.example` and customize:

```bash
# Application
APP_NAME=KrakenBot
ENVIRONMENT=development  # development | production | testing
LOG_LEVEL=INFO           # DEBUG | INFO | WARNING | ERROR | CRITICAL
LOG_JSON=true

# Kraken API
KRAKEN_API_KEY=your_api_key_here          # Required for live trading
KRAKEN_API_SECRET=your_api_secret_here    # Required for live trading
KRAKEN_WS_URL=wss://ws.kraken.com
KRAKEN_API_URL=https://api.kraken.com

# Database (PostgreSQL + TimescaleDB)
DATABASE_URL=postgresql+asyncpg://krakenbot:krakenbot@localhost:5432/krakenbot
DATABASE_POOL_SIZE=5
DATABASE_MAX_OVERFLOW=10

# Trading Configuration
TRADING_MODE=paper                         # paper | live
TRADING_PAIR=XBT/EUR
TRADING_DEFAULT_ORDER_AMOUNT_EUR=15.0
TRADING_CANDLE_INTERVAL_MIN=15
TRADING_CONFIRM_LIVE=no                    # Set to "yes" for live trading

# Risk Management
RISK_MAX_POSITION_PCT=5.0                  # Max 5% of portfolio per trade
RISK_DAILY_LOSS_LIMIT_EUR=50.0             # Stop trading if daily loss > 50€
RISK_MAX_OPEN_POSITIONS=3                  # Max 3 simultaneous positions
RISK_MIN_TRADE_INTERVAL_SEC=60             # Min 60s between trades
RISK_EMERGENCY_STOP_LOSS_PCT=10.0          # Emergency stop at -10%

# Strategy (Threshold)
STRATEGY_NAME=threshold
STRATEGY_BUY_THRESHOLD_PCT=-1.0            # Buy on -1% dip
STRATEGY_SELL_THRESHOLD_PCT=2.0            # Sell on +2% profit
STRATEGY_LOOKBACK_PERIODS=10               # Moving average period
```

### Recommended Settings

**Paper Trading (Testing)**:
```bash
TRADING_MODE=paper
TRADING_DEFAULT_ORDER_AMOUNT_EUR=15.0
RISK_DAILY_LOSS_LIMIT_EUR=50.0
```

**Live Trading (Conservative)**:
```bash
TRADING_MODE=live
TRADING_CONFIRM_LIVE=yes
TRADING_DEFAULT_ORDER_AMOUNT_EUR=10.0
RISK_DAILY_LOSS_LIMIT_EUR=20.0
RISK_MAX_POSITION_PCT=2.0
```

---

## How to Run the Bot

### Step 1: Database Setup

Using Docker Compose (recommended):
```bash
# Start PostgreSQL with TimescaleDB
docker compose up -d db

# Verify it's running
docker compose ps

# Check logs
docker compose logs db
```

Manual PostgreSQL setup:
```bash
# Install TimescaleDB extension (Ubuntu/Debian)
sudo apt install postgresql-15 timescaledb-postgresql-15
sudo timescaledb-tune
sudo systemctl restart postgresql

# Create database
sudo -u postgres createdb krakenbot
sudo -u postgres createuser krakenbot -P  # Enter password when prompted
```

### Step 2: Run Migrations

```bash
# Activate virtual environment
source venv/bin/activate

# Run Alembic migrations
alembic upgrade head

# Verify tables were created
psql -h localhost -U krakenbot -d krakenbot -c "\dt"
```

You should see:
```
 market_data_ohlc
 market_data_ticks
 trades_history
 bot_state
 alembic_version
```

### Step 3: Configure Environment

```bash
# Copy example
cp .env.example .env

# Edit configuration
nano .env  # or vim, code, etc.
```

**Minimum required for paper trading**:
- `DATABASE_URL`: Set to your PostgreSQL connection string
- `TRADING_MODE=paper`: Keep as paper for testing
- All risk/strategy settings can stay at defaults

### Step 4: Run the Bot

**Paper Trading Mode**:
```bash
python -m krakenbot
```

Expected output:
```json
{"event":"bot_starting","mode":"paper","pair":"XBT/EUR","strategy":"threshold","timestamp":"2026-01-16T10:00:00Z"}
{"event":"database_connected","url":"postgresql+asyncpg://krakenbot@localhost:5432/krakenbot"}
{"event":"websocket_connected","url":"wss://ws.kraken.com"}
{"event":"execution_engine_started"}
{"event":"strategy_started","strategy":"threshold"}
{"event":"subscribed_to_ohlc","pair":"XBT/EUR","interval":15}
{"event":"bot_running"}
```

### Step 5: Monitor the Bot

**Watch logs in real-time**:
```bash
python -m krakenbot | jq .  # Pretty-print JSON logs (requires jq)
```

**Check database**:
```bash
# Connect to database
psql -h localhost -U krakenbot -d krakenbot

# View recent OHLC data
SELECT timestamp, pair, close, volume
FROM market_data_ohlc
ORDER BY timestamp DESC
LIMIT 10;

# View bot state
SELECT * FROM bot_state;

# View trade history
SELECT timestamp, side, amount_eur, price, pnl, status
FROM trades_history
ORDER BY timestamp DESC
LIMIT 10;
```

**Periodic stats** (logged every 60 seconds):
```json
{
  "event": "periodic_stats",
  "websocket": {
    "connected": true,
    "messages_received": 45,
    "subscriptions": ["ohlc:XBT/EUR"]
  },
  "execution": {
    "signals_received": 2,
    "signals_executed": 1,
    "signals_rejected": 1,
    "rejection_reasons": {"insufficient_balance": 1}
  },
  "strategy": {
    "name": "threshold",
    "signals_generated": 2,
    "current_position": "0.00035",
    "total_pnl": "1.25"
  }
}
```

### Step 6: Stop the Bot

**Graceful shutdown**:
```bash
# Press Ctrl+C
# or send SIGTERM:
kill -TERM <pid>
```

The bot will:
1. Stop generating new signals
2. Stop executing new orders
3. Disconnect WebSocket
4. Close database connections
5. Log final statistics

---

## Backtesting

KrakenBot includes a comprehensive backtesting framework to test strategies on historical data before deploying them live.

### Running a Backtest

**Basic usage**:
```bash
# Backtest the last 7 days (default)
python -m scripts.backtest --pair XBT/USDC

# Backtest specific period
python -m scripts.backtest --pair XBT/USDC --days 30

# Backtest with custom end date
python -m scripts.backtest --pair XBT/USDC --days 14 --end-date 2026-01-15

# Backtest specific strategy
python -m scripts.backtest --strategy threshold --pair XBT/USDC --days 7

# Save backtest results to database for dashboard visualization
python -m scripts.backtest --pair XBT/USDC --days 7 --save

# Save with custom name
python -m scripts.backtest --pair XBT/USDC --days 30 --save --name "Aggressive Strategy Test"
```

### Backtest Output

The backtest will display a comprehensive report:

```
================================================================================
                              BACKTEST REPORT
================================================================================

Strategy:                      threshold
Period:                        2026-01-09 to 2026-01-16
Duration:                      7.0 days

--------------------------------------------------------------------------------
PERFORMANCE SUMMARY
--------------------------------------------------------------------------------
Starting Balance:              1000.00 USDC
Ending Balance:                1025.40 USDC
Total Return:                  +2.54%
Net P&L:                       +25.40 USDC
Total Fees Paid:               4.60 USDC

--------------------------------------------------------------------------------
TRADE STATISTICS
--------------------------------------------------------------------------------
Total Trades:                  8
Winning Trades:                5
Losing Trades:                 3
Win Rate:                      62.50%
Average Win:                   +8.20 USDC
Average Loss:                  -4.10 USDC
Profit Factor:                 2.00

--------------------------------------------------------------------------------
RISK METRICS
--------------------------------------------------------------------------------
Max Drawdown:                  12.30 USDC
Max Drawdown %:                1.23%
Sharpe Ratio:                  1.85
================================================================================
```

### Performance Metrics Explained

- **Total Return %**: Overall portfolio return from start to end
- **Net P&L**: Profit/Loss after fees
- **Win Rate**: Percentage of profitable trades
- **Profit Factor**: Ratio of total wins to total losses (>1 is profitable)
- **Max Drawdown**: Largest peak-to-trough decline in portfolio value
- **Sharpe Ratio**: Risk-adjusted return (>1 is good, >2 is excellent)

### Requirements for Backtesting

1. **Historical Data**: You need OHLC data in your database for the backtest period
2. **Minimum Data**: At least 10 candles required (strategy needs history to analyze)
3. **Database Running**: PostgreSQL with TimescaleDB must be accessible

**Tip**: Let the bot run in paper mode for a few days/weeks to accumulate historical data, then backtest different strategy parameters to optimize performance!

### Strategy Optimization

You can modify strategy parameters in `.env` and re-run backtests to find optimal settings:

```bash
# Test with more aggressive buy threshold
STRATEGY_BUY_THRESHOLD_PCT=-0.5 python -m scripts.backtest --days 30

# Test with tighter sell target
STRATEGY_SELL_THRESHOLD_PCT=1.0 python -m scripts.backtest --days 30
```

---

## Monitoring Dashboard

KrakenBot includes a real-time Streamlit dashboard for monitoring bot performance, positions, and trades.

### Starting the Dashboard

**Prerequisites**:
1. Install monitoring dependencies:
   ```bash
   pip install -e ".[monitoring]"
   ```

2. Ensure database is running and populated with data:
   ```bash
   docker compose up -d db
   ```

**Run the dashboard**:
```bash
streamlit run scripts/dashboard.py
```

The dashboard will open in your browser at `http://localhost:8501`.

### Dashboard Features

#### 1. Real-Time Metrics
- **Total P&L**: Overall profit/loss across all trades
- **Daily P&L**: Today's profit/loss performance
- **Current Position**: BTC holdings and entry price
- **Trade Count**: Total number of executed trades

#### 2. Interactive Price Chart
- **Candlestick Chart**: OHLC data with Plotly interactive controls
- **Trading Signals**: Visual markers for buy (🔺 green) and sell (🔻 red) orders
- **Configurable Timeframe**: Select from 1 hour to 7 days of history
- **Latest Price**: Current BTC price and 24h change

#### 3. Recent Trades Table
- **Color-Coded Rows**: Green for buys, red for sells
- **Trade Details**: Timestamp, side, price, amounts, fees, P&L
- **Status Tracking**: See pending, executed, or failed trades

#### 4. Bot Status Monitor
- **Live Status**: 🟢 RUNNING, 🟡 IDLE, 🔴 STOPPED/ERROR
- **Strategy Info**: Active strategy name and parameters
- **Last Activity**: When the bot last updated or generated a signal
- **Bot ID**: Unique identifier for this bot instance

#### 5. Controls
- **Refresh Button**: Manually refresh all data
- **Auto-Refresh**: Enable 30-second automatic updates
- **Chart Hours Slider**: Adjust time range (1-168 hours)
- **Trading Mode Indicator**: See if running in Paper or Live mode

### Dashboard Screenshot Example

```
╔══════════════════════════════════════════════════════════════╗
║  🤖 KrakenBot Dashboard              🔄 Refresh  📝 Paper    ║
╠══════════════════════════════════════════════════════════════╣
║  Total P&L        Position         Entry Price   Trades      ║
║  +25.40 USDC     0.00123456 BTC    92,450.00      12         ║
║  +5.20 today                                                  ║
╠══════════════════════════════════════════════════════════════╣
║  📈 XBT/USDC Price Chart (Last 24h)                          ║
║  [Interactive candlestick chart with buy/sell markers]       ║
║                                                               ║
║  Latest: 93,200.00 USDC   24h Change: +1.2%   Vol: 2.4 BTC  ║
╠══════════════════════════════════════════════════════════════╣
║  Recent Trades                                                ║
║  Time            Side  Price     Amount      P&L    Status   ║
║  2026-01-16 14:30  BUY  92,450   15.00 USDC   —     executed ║
║  2026-01-16 14:45  SELL 93,200   15.20 USDC  +0.70  executed ║
╠══════════════════════════════════════════════════════════════╣
║  Bot Status: 🟢 RUNNING   Strategy: threshold                ║
║  Last Updated: 2026-01-16 14:50:23 UTC                       ║
╚══════════════════════════════════════════════════════════════╝
```

### Dashboard Requirements

- **Database Access**: Dashboard reads from the same PostgreSQL database as the bot
- **Historical Data**: Chart requires OHLC data in the database (accumulated by the bot)
- **Port 8501**: Default Streamlit port must be available

### Backtest Visualization

The dashboard includes a **Backtest Results** mode that allows you to visualize saved backtest runs:

1. **Run a backtest with --save flag**:
   ```bash
   python -m scripts.backtest --pair XBT/USDC --days 30 --save
   ```

2. **Open the dashboard**:
   ```bash
   streamlit run scripts/dashboard.py
   ```

3. **Switch to Backtest mode**:
   - In the sidebar, select "Backtest Results"
   - Choose a backtest from the dropdown
   - View comprehensive metrics: Net P&L, Win Rate, Sharpe Ratio, Max Drawdown
   - See the full backtest period chart with entry/exit points

4. **Compare multiple backtests**:
   - Run multiple backtests with different parameters
   - Switch between them in the dashboard to compare performance
   - Each backtest is saved with timestamp for easy identification

### Tips for Using the Dashboard

1. **Paper Mode Testing**: Run the bot in paper mode and monitor performance on the dashboard before going live
2. **Strategy Validation**: Use the chart to visualize if your buy/sell signals align with market movements
3. **Performance Tracking**: Check Total P&L and Win Rate to evaluate strategy effectiveness
4. **Multi-Window**: Open dashboard in one window, keep logs in terminal in another
5. **Auto-Refresh**: Enable for hands-off monitoring, disable when analyzing specific trades
6. **Backtest Analysis**: Save all your backtests to compare different strategy parameters and find optimal settings

---

## Troubleshooting

### Common Issues

#### 1. Database Connection Errors

**Error**: `could not connect to server: Connection refused`

**Solution**:
```bash
# Check if PostgreSQL is running
docker compose ps

# If not running, start it
docker compose up -d db

# Check database logs
docker compose logs db
```

#### 2. TimescaleDB Extension Missing

**Error**: `extension "timescaledb" is not available`

**Solution**:
```bash
# Connect to database
psql -h localhost -U krakenbot -d krakenbot

# Create extension
CREATE EXTENSION IF NOT EXISTS timescaledb;
```

#### 3. Migration Errors

**Error**: `Target database is not up to date`

**Solution**:
```bash
# Check current version
alembic current

# Show pending migrations
alembic history

# Apply all pending migrations
alembic upgrade head
```

#### 4. WebSocket Connection Drops

**Symptom**: Bot logs show repeated reconnection attempts

**Solution**:
- Check internet connection
- Verify Kraken API is operational: https://status.kraken.com/
- Increase reconnect delay: `KRAKEN_WS_RECONNECT_DELAY_SEC=10`

#### 5. No Signals Generated

**Symptom**: Bot runs but never generates buy/sell signals

**Solution**:
```bash
# Check if OHLC data is being received
psql -h localhost -U krakenbot -d krakenbot -c \
  "SELECT COUNT(*) FROM market_data_ohlc WHERE timestamp > NOW() - INTERVAL '1 hour';"

# If no data, check WebSocket logs for errors
# If data exists, adjust strategy thresholds:
STRATEGY_BUY_THRESHOLD_PCT=-0.5   # More aggressive
STRATEGY_SELL_THRESHOLD_PCT=1.0
```

#### 6. Paper Trading Orders Not Simulated

**Symptom**: Orders rejected with "insufficient balance" in paper mode

**Solution**:
```python
# Paper mode has default balances:
# EUR: 1000.0
# BTC: 0.01

# Reduce order size:
TRADING_DEFAULT_ORDER_AMOUNT_EUR=10.0  # Instead of 15.0
```

---

## Safety Features

### 1. Paper Trading Default
- Bot NEVER trades real money unless explicitly configured
- `TRADING_MODE` defaults to `paper`
- Simulates orders with realistic fees and slippage

### 2. Live Mode Confirmation
- Live trading requires TWO flags:
  - `TRADING_MODE=live`
  - `TRADING_CONFIRM_LIVE=yes`
- Prevents accidental live trading

### 3. Daily Loss Limits
- Trading automatically halts if daily loss exceeds limit
- Resets at midnight UTC
- Default: 50 EUR per day

### 4. Position Size Limits
- Maximum exposure per trade (default: 5% of portfolio)
- Prevents over-concentration

### 5. Rate Limiting
- Respects Kraken API limits (15 calls/min for Tier 1)
- Automatic backoff on rate limit errors

### 6. Emergency Stop-Loss
- Automatic position closure on extreme losses
- Default: -10% from entry price

### 7. Comprehensive Logging
- Every decision is logged with full context
- JSON format for easy parsing
- Automatic secret masking in logs

### 8. Minimum Trade Interval
- Prevents rapid-fire trading
- Default: 60 seconds between trades

---

## Development

### Running Tests

```bash
# Run all tests
pytest

# With verbose output
pytest -v

# With coverage report
pytest --cov=krakenbot --cov-report=html

# Open coverage report
open htmlcov/index.html

# Run specific test file
pytest tests/test_strategies/test_threshold.py

# Run tests matching pattern
pytest -k "risk"
```

**Current test coverage**: 284 tests, 100% pass rate

### Code Quality Tools

```bash
# Format code with Ruff
ruff format .

# Lint and auto-fix issues
ruff check . --fix

# Type checking with mypy
mypy src/

# All quality checks at once
ruff format . && ruff check . --fix && mypy src/ && pytest
```

### Pre-commit Hooks

Install pre-commit hooks to automatically format/lint before commits:
```bash
pre-commit install
```

Now every `git commit` will automatically:
1. Format code with Ruff
2. Lint with Ruff
3. Check types with mypy
4. Fail commit if issues found

### Project Structure

```
kraken-trading-bot/
├── src/krakenbot/           # Main source code
│   ├── __init__.py
│   ├── __main__.py         # Entry point (python -m krakenbot)
│   ├── main.py             # KrakenBot orchestrator
│   ├── config/             # Pydantic settings
│   │   ├── __init__.py
│   │   └── settings.py
│   ├── core/               # Core infrastructure
│   │   ├── __init__.py
│   │   ├── database.py     # SQLAlchemy async
│   │   ├── event_bus.py    # Pub/sub system
│   │   ├── exceptions.py   # Custom exceptions
│   │   └── logger.py       # Structured logging
│   ├── connectors/         # External API clients
│   │   ├── __init__.py
│   │   ├── kraken_rest.py  # REST API (ccxt)
│   │   └── kraken_ws.py    # WebSocket client
│   ├── models/             # SQLAlchemy ORM
│   │   ├── __init__.py
│   │   ├── base.py         # Common types/enums
│   │   ├── market_data.py  # OHLC, ticks
│   │   └── trades.py       # Trade history, bot state
│   ├── strategies/         # Trading strategies
│   │   ├── __init__.py
│   │   ├── base.py         # BaseStrategy ABC
│   │   └── threshold.py    # Mean reversion strategy
│   ├── execution/          # Order execution
│   │   ├── __init__.py
│   │   ├── engine.py       # ExecutionEngine
│   │   └── risk.py         # RiskManager
│   └── utils/              # Helper utilities
│       └── __init__.py
├── tests/                  # Test suite (284 tests)
│   ├── conftest.py         # Pytest fixtures
│   ├── test_config/
│   ├── test_core/
│   ├── test_connectors/
│   ├── test_models/
│   ├── test_strategies/
│   ├── test_execution/
│   └── test_main.py
├── alembic/                # Database migrations
│   ├── env.py
│   └── versions/
│       └── 20240115_000000_001_initial_schema.py
├── .env.example            # Environment template
├── .gitignore
├── alembic.ini             # Alembic config
├── docker-compose.yml      # PostgreSQL + TimescaleDB
├── pyproject.toml          # Dependencies & config
├── CLAUDE.md               # Project conventions
├── TODO.md                 # Progress tracker
└── README.md               # This file
```

### Adding a New Strategy

1. **Create strategy file** in `src/krakenbot/strategies/`:
   ```python
   # src/krakenbot/strategies/my_strategy.py
   from krakenbot.strategies.base import BaseStrategy, TradingSignal, SignalType
   from decimal import Decimal
   from datetime import datetime, UTC

   class MyStrategy(BaseStrategy):
       def __init__(self, event_bus, db_manager, settings, param1: float):
           super().__init__(event_bus, db_manager, settings)
           self.param1 = param1

       async def on_tick(self, tick_data: dict) -> None:
           # Handle tick data
           pass

       async def on_ohlc(self, ohlc_data: dict) -> None:
           # Handle OHLC candles
           pass

       async def generate_signal(self) -> TradingSignal | None:
           # Your strategy logic here
           return TradingSignal(
               signal_type=SignalType.BUY,
               pair=self.settings.trading.pair,
               price=Decimal("42000.0"),
               confidence=0.8,
               reason="Your reason here",
               strategy="my_strategy",
               timestamp=datetime.now(UTC),
           )
   ```

2. **Add configuration** to `config/settings.py`:
   ```python
   class StrategySettings(BaseSettings):
       # Add your parameters
       my_param1: float = Field(default=1.0, ...)
   ```

3. **Update main.py** to instantiate your strategy:
   ```python
   from krakenbot.strategies.my_strategy import MyStrategy

   # In KrakenBot.setup():
   if self.settings.strategy.name == "my_strategy":
       self.strategy = MyStrategy(...)
   ```

4. **Write tests** in `tests/test_strategies/test_my_strategy.py`

5. **Update `.env.example`** with new parameters

---

## Historical Data Collection

KrakenBot includes a comprehensive system for collecting and managing real OHLC data from Kraken API.

### Manual Data Fetch

Fetch historical OHLC data for a specific pair and interval:

```bash
# Fetch 7 days of 15min candles for XBT/EUR
python -m scripts.fetch_ohlc --pair XBT/EUR --interval 15 --days 7

# Resume from last stored timestamp
python -m scripts.fetch_ohlc --pair XBT/EUR --interval 15 --days 90 --resume

# Available intervals: 1, 5, 15, 30, 60, 240, 1440 (minutes)
```

**Features**:
- Automatic pagination (720 candles per request limit)
- Resume from last timestamp if interrupted
- Retry logic for network errors
- Rate limiting (1 req/sec)
- Progress bar with tqdm
- Deduplication via database merge

### Backfill Historical Data

One-shot backfill of all configured pairs and intervals:

```bash
# Dry-run to estimate volume
python -m scripts.backfill_historical_data --dry-run

# Execute backfill
python -m scripts.backfill_historical_data

# Custom pairs/intervals
python -m scripts.backfill_historical_data --pairs XBT/EUR --intervals 15 60
```

**Backfill Limits** (based on Kraken API retention):
- 1min: 7 days
- 5min: 30 days
- 15min: 90 days
- 1h: 365 days

### Scheduled Data Collection

The bot includes automatic scheduled tasks (via APScheduler) to continuously collect data:

**Default Schedule**:
- **1min OHLC**: Daily at 02:00 UTC
- **5min OHLC**: Daily at 02:15 UTC
- **15min OHLC**: Weekly (Mondays) at 03:00 UTC
- **1h OHLC**: Monthly (1st of month) at 04:00 UTC

**Configuration** (in `.env`):
```bash
SCHEDULER_ENABLED=true
SCHEDULER_PAIRS=XBT/USDC,XBT/EUR
SCHEDULER_INTERVALS=1,5,15,60
SCHEDULER_TIMEZONE=UTC

# Custom cron expressions
SCHEDULER_DAILY_1MIN_CRON="0 2 * * *"
SCHEDULER_WEEKLY_15MIN_CRON="0 3 * * 1"
```

**Audit Trail**: All task executions are logged in `task_execution_logs` table with:
- Task ID, pair, interval
- Start/completion timestamps
- Status (success/failed)
- Number of candles fetched
- Error messages if failed

To disable scheduled collection, set `SCHEDULER_ENABLED=false` in `.env`.

---

## Project Status

### Completed (MVP)

- [x] Project structure and configuration
- [x] Core infrastructure (Database, EventBus, Logger)
- [x] Kraken connectors (WebSocket + REST)
- [x] Data models (ORM with TimescaleDB)
- [x] Base strategy framework
- [x] Threshold mean-reversion strategy
- [x] Risk management system (5 critical checks)
- [x] Execution engine with P&L tracking
- [x] Paper trading mode (fully functional)
- [x] Live trading mode (with safety checks)
- [x] Graceful shutdown handling
- [x] Comprehensive test suite (284 tests, 100% pass)

### Recently Completed

- [x] **Historical data collection system**
  - Scripts to fetch real OHLC data from Kraken REST API
  - Automatic pagination for large time ranges
  - Resume capability from last timestamp
  - Time interval conversion utilities (1m, 5m, 15m, 1h, etc.)
- [x] **Scheduled data collection** (APScheduler)
  - Daily jobs for 1min and 5min intervals
  - Weekly jobs for 15min intervals
  - Monthly jobs for 1h intervals
  - Audit trail with TaskExecutionLog model
  - Integrated into bot lifecycle
- [x] **Backfill scripts**
  - One-shot historical data backfill for all pairs/intervals
  - Dry-run mode for estimating volume
  - Parallel or sequential execution
  - Progress bars and detailed logging

### In Progress

- [ ] End-to-end testing with real Kraken data
- [ ] User documentation and guides

### Planned (Phase 2)

- [x] Streamlit monitoring dashboard
- [x] Backtesting framework
- [ ] Multi-strategy support
- [ ] Health checks and alerts
- [ ] Discord/Telegram notifications

### Future (Phase 3)

- [ ] ML-based strategies (Transformers)
- [ ] Reinforcement learning strategies
- [ ] Feature engineering pipeline
- [ ] Model versioning and A/B testing

## Resources

- [Kraken API Documentation](https://docs.kraken.com/)
- [TimescaleDB Documentation](https://docs.timescale.com/)
- [Project Documentation](./CLAUDE.md)

## License

MIT

## Disclaimer

This software is for educational purposes only. Cryptocurrency trading carries significant risk. The authors are not responsible for any financial losses incurred through the use of this software.

**USE AT YOUR OWN RISK.**
