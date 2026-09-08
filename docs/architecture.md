# Architecture — flux d'un trade, multi-pair, conventions

> Pour localiser un module ou une fonction précise : `docs/CODE_MAP.md`. Pour l'état du projet :
> `PROJECT_CONTEXT.md`.

## Deux services indépendants

- **Collector** (`python -m krakenbot.collector`) : tourne 24/7, reçoit les candles OHLC par WebSocket
  (3 paires × 7 timeframes = 21 streams + 3 tickers), écrit dans `market_data_ohlc` avec
  `exchange = settings.exchange_name`.
- **Trader** (`python -m krakenbot`) : start/stop, lit les candles via son propre WebSocket, orchestre
  les stratégies via le `MultiStrategyRouter`, émet les ordres via l'`ExecutionEngine` → REST de
  l'exchange (paper : simulation en mémoire).

Les deux communiquent uniquement via la DB. L'exchange est choisi par `settings.exchange_name` et la
factory `connectors/exchange.py` (`build_exchange_rest_client` / `build_exchange_ws_client`).
Cible : **Bybit EU** (connecteur B1–B3). Binance = données historiques ; Kraken = legacy / paper.

## Flux d'un trade

```
Candle WebSocket → EventBus (MARKET_OHLC)
  → MultiStrategyRouter (seule BaseStrategy sur l'EventBus ; filtre par pair)
    → Stratégie interne (on_ohlc + generate_signal)
    → GeminiGlobalRiskManager (règle 1 %, SL ATR, crash protector, confidence)
    → EventBus (TRADE_SIGNAL)
  → ExecutionEngine (+ GlobalRiskManager, OrderManager) → REST exchange
  → EventBus (TRADE_ORDER_FILLED)
    → route vers la stratégie source via bot_id
```

Les backtests (`scripts/backtest.py`) rejouent les candles DB dans une instance de stratégie **sans**
passer par le router, l'ExecutionEngine ni l'OrderManager.

## Multi-pair

- `MultiPairAnalyzerRegistry` : un `MultiTimeframeAnalyzer` par pair, création lazy, accès
  `registry.get(pair)`. Indicateurs sur 6 TF (5m → 1w) : `get_ema()`, `get_rsi()`, `get_atr()`,
  `get_macd()`, `get_bollinger()`, `get_adx()`, `get_supertrend()`, `get_donchian()`, `get_regime()`.
- Le router filtre les candles : une candle ETH ne va qu'aux stratégies ETH.
- Toutes les stratégies héritent de `BaseStrategy(pair=...)` ; une même classe peut être instanciée N
  fois avec des paires différentes. Chaque instance a son `bot_id`, ses positions et ses logs.
- Le `GeminiGlobalRiskManager` calcule le SL sur l'ATR **du pair du signal**.

## Types d'ordres (fees Bybit EU maker 0.10 % / taker 0.25 %)

- BUY → toujours LIMIT (PostOnly côté connecteur)
- SELL profit target → LIMIT
- SELL stop-loss / trailing / timeout → MARKET (exécution garantie, 0.25 %)

Détail et conséquences : `skills/risk_management.md`.

## Conventions de code (obligatoires)

- **Python 3.12+**, async/await partout, imports absolus `from krakenbot.core import ...`
- **Decimal** pour tous les montants et prix, via string : `Decimal("65000.50")`, jamais `Decimal(65000.50)`
- **UTC** pour tous les timestamps
- **structlog** : `logger = structlog.get_logger(__name__)` ;
  `logger.info("event_name", pair=self.pair, strategy=self.bot_id, key=value)` — jamais `print`
- **Pairs** : `normalize_pair()` (`krakenbot.utils.pair`, XBT → BTC) ; jamais de paire ni d'exchange en dur
- **Analyzer** : `analyzer = self._analyzer_registry.get(self.pair)` puis `analyzer.get_rsi(14, "4h")`
- Naming : classes `PascalCase`, fonctions/variables `snake_case`, constantes `UPPER_SNAKE_CASE`
- DB : filtre `settings.exchange_name` en prod, inserts par batch de 1000

## Fichiers protégés

`strategies/multi_strategy_router.py`, `strategies/gemini_global_risk_manager.py`,
`execution/engine.py` : pas de modification sans raison explicite et review humain. Le
`GlobalRiskManager` (`execution/risk.py`) ne se bypasse jamais.
