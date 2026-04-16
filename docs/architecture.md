Kraken WS/REST
   ↓
Collector
   ↓
PostgreSQL / TimescaleDB

Kraken WS/REST
   ↓
Trading Bot
   ↓
strategies.yaml
   ↓
top-level strategy
   ↓
current config: MultiStrategyRouter
   ↓
7 supported inner strategies
   ↓
ExecutionEngine
   ↓
GlobalRiskManager / RiskManager
   ↓
OrderManager
   ↓
paper fills or live Kraken orders

Backtests:
scripts/backtest.py
   ↓
DB candle replay
   ↓
single strategy instance

Backtests do not execute through MultiStrategyRouter / ExecutionEngine / OrderManager.
