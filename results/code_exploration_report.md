# Code Exploration Report — KrakenBot

**Date**: 2026-04-11
**Branch**: `main`
**Scope**: Read-only codebase analysis covering architecture, strategies, indicators, execution, DB, and extension points.

---

## Résumé Exécutif

1. **Architecture single-process multi-stratégie** : un `MultiStrategyRouter` (seul `BaseStrategy` dans l'EventBus) dispatche les candles vers 7 stratégies internes et applique un `GeminiGlobalRiskManager` (1% rule, ATR SL, crash protector) sur chaque signal BUY avant publication.
2. **Risk à 2 niveaux** : le `GeminiGlobalRiskManager` filtre les signaux dans le router, puis le `GlobalRiskManager` (dans `execution/risk.py`) valide chaque ordre avant exécution — global (balance, max positions, daily loss, exposure) + par stratégie (budget, position size, trade interval).
3. **MultiTimeframeAnalyzer partagé** : instance unique, 7 timeframes (1m→1w), indicateurs lazy (EMA, SuperTrend, Ichimoku, Donchian, VWAP) + pré-enregistrés (MACD, RSI, ATR, BB, ADX). Régime calculé via EMA spread sur tout TF.
4. **DB TimescaleDB** : 5 tables (`market_data_ohlc` hypertable, `trades_history`, `open_positions`, `bot_state`, `orders`). Collector 24/7 séparé, bot charge warmup au démarrage puis live via WebSocket.
5. **Extension facile** : ajouter une stratégie = 1 fichier Python + 1 entrée dans `_INNER_STRATEGY_CLASSES` + 1 bloc YAML dans `strategies.yaml`. Le régime detector existe déjà dans l'analyzer — une couche centralisée dans le router serait une extension naturelle.

---

## Section 1 — Architecture générale

### 1.1 — Structure du projet

```
src/krakenbot/
├── __init__.py
├── __main__.py          # Entry point: python -m krakenbot
├── main.py              # KrakenBot orchestrator, STRATEGY_REGISTRY
├── collector.py         # DataCollector: service 24/7 séparé pour collecte OHLC
├── config/              # Settings Pydantic, chargement .env / .env.local
├── connectors/          # Kraken REST, WebSocket, Futures REST clients
├── core/                # EventBus (pub/sub), DatabaseManager, Logger
├── execution/           # ExecutionEngine, OrderManager, GlobalRiskManager
├── indicators/          # MultiTimeframeAnalyzer + indicateurs individuels (EMA, RSI, ATR, MACD, BB, ADX, SuperTrend, Ichimoku, Donchian, VWAP)
├── ml/                  # Pipeline ML (disabled, placeholder pour futur XGBoost/LSTM)
├── models/              # SQLAlchemy models: OHLCData, Trade, BotState, OpenPosition, Order
├── notifications/       # Telegram notifier
├── scheduler/           # TaskScheduler pour backfill REST périodique
├── strategies/          # 21 stratégies (base.py, router, risk manager, 7 actives, legacy)
└── utils/               # Helpers divers
```

### 1.2 — Point d'entrée

**Fichier** : `src/krakenbot/main.py`

```python
class KrakenBot:
    """Main bot orchestrator."""

    async def setup(self) -> None:
        # 1. Event Bus
        # 2. Database Manager
        # 3. REST Client (ccxt Kraken)
        # 4. MultiTimeframeAnalyzer (instance partagée)
        # 5. WebSocket Client
        # 6. GlobalRiskManager (execution-level)
        # 7. OrderManager
        # 8. ExecutionEngine
        # 9. Strategy (via STRATEGY_REGISTRY lookup)
        # 10. Telegram notifier

    async def start(self) -> None:
        # 1. Connect DB
        # 2. Initialize REST client + paper balance
        # 3. Warm up MultiTimeframeAnalyzer (historical candles from DB)
        # 4. Start strategy (subscribes to EventBus)
        # 5. Start ExecutionEngine
        # 6. Subscribe WebSocket OHLC for all required intervals
        # 7. Reconcile positions with exchange (DB vs Kraken balance)

    async def run(self) -> None:
        # Main loop: keep alive until shutdown signal

    async def stop(self) -> None:
        # Reverse order: strategy → execution → WS → REST → DB
```

Le `STRATEGY_REGISTRY` (ligne 68-78) mappe les noms de stratégies aux classes :

```python
STRATEGY_REGISTRY: dict[str, type[BaseStrategy]] = {
    "threshold_rolling": ThresholdRollingStrategy,
    "adaptive": AdaptiveStrategy,
    "capitulation": CapitulationStrategy,
    "bear_short": BearShortStrategy,
    "grid_spot": GridSpotStrategy,
    "grid_adaptive": GridAdaptiveStrategy,
    "trend_following": TrendFollowingStrategy,
    "multi_strategy_router": MultiStrategyRouter,  # ← Mode multi-stratégie
}
```

En mode multi-stratégie (`strategies.yaml` → `enabled: true`), seul `MultiStrategyRouter` est instancié et enregistré dans l'EventBus. Les 7 stratégies internes sont gérées directement par le router sans jamais toucher l'EventBus.

### 1.3 — EventBus

**Fichier** : `src/krakenbot/core/event_bus.py`

Architecture pub/sub async simple. Les événements principaux :

```python
class EventType(str, Enum):
    # Market data
    MARKET_TICK = "market.tick"           # Tick individuel
    MARKET_OHLC = "market.ohlc"           # Candle OHLC (tous intervalles)
    MARKET_ORDERBOOK = "market.orderbook"  # Order book (non utilisé actuellement)

    # Trading
    TRADE_SIGNAL = "trade.signal"          # Signal BUY/SELL/HOLD
    TRADE_ORDER_PLACED = "trade.order_placed"
    TRADE_ORDER_FILLED = "trade.order_filled"
    TRADE_ORDER_FAILED = "trade.order_failed"
    TRADE_ORDER_CANCELLED = "trade.order_cancelled"

    # System
    SYSTEM_ERROR = "system.error"
    BOT_STARTED = "bot.started"
    BOT_STOPPED = "bot.stopped"
    BOT_PAUSED = "bot.paused"
```

Les callbacks sont des coroutines async, stockées dans un `defaultdict(list)`.

### 1.4 — Flux d'exécution principaux

#### Flux 1 : Candle → Signal → Ordre (cas nominal BUY)

```
Kraken WS API
  └→ KrakenWebSocketClient._handle_ohlc_update()
       └→ EventBus.publish(MARKET_OHLC, candle_data)
            └→ MultiStrategyRouter._handle_ohlc(data)
                 ├→ risk_manager.update_price(price, ts)   [crash protector]
                 ├→ risk_manager.check_crash_protector(ts)
                 └→ for strategy in _inner_strategies:
                      └→ _dispatch_to_strategy(strategy, data)
                           ├→ [custom _handle_ohlc override]:
                           │    strategy._handle_ohlc(data)  [via _RiskOverlayEventBusProxy]
                           │      └→ event_bus.publish(TRADE_SIGNAL)
                           │           └→ proxy intercepts → _apply_risk_overlay(signal)
                           │                └→ GeminiGlobalRiskManager.process_signal()
                           │                     ├→ crash protector check
                           │                     ├→ ATR-based stop-loss
                           │                     └→ 1% position sizing
                           │                └→ _publish_processed_signal() → real EventBus
                           └→ [standard flow]:
                                strategy.on_ohlc(data)
                                signal = strategy.generate_signal()
                                → _apply_risk_overlay(signal) → publish
```

#### Flux 2 : Signal → Exécution → Fill

```
EventBus(TRADE_SIGNAL)
  └→ ExecutionEngine._handle_signal(data)
       ├→ Extract signal, validate (not HOLD)
       └→ _execute_signal(signal)
            ├→ GlobalRiskManager.check_order()    [2-level: global + per-strategy]
            │    ├→ Level 1: balance, max positions, daily loss, exposure
            │    └→ Level 2: per-strategy budget (position size, trade interval)
            ├→ If REJECTED → log + publish rejection event
            └→ If APPROVED:
                 ├→ [limit order] → OrderManager.place_and_track()
                 │    └→ KrakenRestClient.place_limit_order()
                 └→ [market order] → KrakenRestClient.place_market_order()
                      └→ On fill → _update_bot_state() → create OpenPosition
                           └→ EventBus.publish(TRADE_ORDER_FILLED)
```

#### Flux 3 : Fill → Callback stratégie

```
EventBus(TRADE_ORDER_FILLED)
  └→ MultiStrategyRouter._handle_trade_filled(data)
       ├→ Extract trade_strategy from data
       ├→ Lookup in _strategy_by_bot_id[trade_strategy]
       └→ target.on_trade_filled(trade_id, pair, side, amount, price, fee, ...)
            └→ Strategy updates internal position tracking
```

#### Flux 4 : Limit order pending → Poll → Fill

```
OrderManager.check_pending_orders()     [appelé toutes les 30s]
  └→ for order in _pending_orders:
       ├→ Check expiry → _handle_expired_order() → cancel on exchange
       ├→ [paper mode] → _check_paper_fill(order)
       │    └→ if candle_low <= limit_price → fill
       └→ [live mode] → _check_live_fill(order)
            └→ REST API get_order_status()
                 └→ if "closed" → update status → publish TRADE_ORDER_FILLED
```

#### Flux 5 : Crash protector → Force close

```
MultiStrategyRouter._handle_ohlc()
  └→ risk_manager.update_price(price, ts)
       └→ If price drop ≥ 7% in 30 min window:
            └→ _handle_crash(price)
                 └→ For each inner strategy with open position:
                      └→ Emit SELL signal (market order, close 50% of position)
```

---

## Section 2 — MultiStrategyRouter

### 2.1 — Signature complète

**Fichier** : `src/krakenbot/strategies/multi_strategy_router.py`

```python
class MultiStrategyRouter(BaseStrategy):
    """Orchestrator that dispatches OHLC to inner strategies and applies risk overlay.

    This is the single entry point registered in the EventBus.
    Inner strategies are managed entirely by the router — they never
    subscribe to the EventBus directly.
    """

    def __init__(
        self,
        settings: Settings,
        event_bus: EventBus,
        db_manager: DatabaseManager,
        bot_id: str | None = None,
        strategy_params: dict[str, Any] | None = None,
        analyzer: Any | None = None,
    ) -> None:
```

**Attributs principaux** :
- `self.capital_usdc: Decimal` — Capital total pour risk calculations
- `self.risk_manager: GeminiGlobalRiskManager` — Risk overlay
- `self._inner_strategies: list[BaseStrategy]` — Stratégies actives
- `self._strategy_by_bot_id: dict[str, BaseStrategy]` — Lookup rapide par bot_id

**Méthodes publiques** :

| Méthode | Ligne | Description |
|---------|-------|-------------|
| `_handle_ohlc(data)` | 248-316 | Override principal : dispatch candles + crash protector |
| `_dispatch_to_strategy(strategy, data)` | 318-358 | Dispatch individuel avec proxy risk |
| `_apply_risk_overlay(signal)` | 360-376 | Appel au GeminiGlobalRiskManager |
| `_handle_trade_filled(data)` | 547-603 | Routing des fills par bot_id |
| `start()` / `stop()` | 609-630 | Lifecycle |
| `get_name()` | 636 | Retourne `"multi_strategy_router"` |
| `on_ohlc()` / `generate_signal()` | 237-240 | No-op (logique dans `_handle_ohlc`) |

### 2.2 — Dispatch des candles

**`_handle_ohlc(data)`** (lignes 248-316) :

1. **Update crash protector** sur les candles 1m :
   - `risk_manager.update_price(price, timestamp)`
   - `risk_manager.check_crash_protector(timestamp)` → si crash → `_handle_crash(price)`

2. **Dispatch à chaque inner strategy** (lignes 298-308) :
   - Boucle sur `self._inner_strategies`
   - Appel `_dispatch_to_strategy(strategy, data)` pour chacune

**`_dispatch_to_strategy(strategy, ohlc_data)`** (lignes 318-358) :

```python
# Détecte si la stratégie a un override custom de _handle_ohlc
has_custom_handle = type(strategy)._handle_ohlc is not BaseStrategy._handle_ohlc
```

- **Si custom override** (grid, supertrend, ema_cross, etc.) :
  - Remplace temporairement `strategy.event_bus` par `_RiskOverlayEventBusProxy`
  - Ce proxy intercepte les publications `TRADE_SIGNAL` et applique le risk overlay
  - Appelle `strategy._handle_ohlc(ohlc_data)`
  - Restaure l'event_bus original

- **Si flow standard** :
  - Appelle `strategy.on_ohlc(ohlc_data)` puis `strategy.generate_signal()`
  - Si signal actionable → `_apply_risk_overlay(signal)` → publish

**Pas de filtrage** — toutes les candles vont à toutes les stratégies actives. Le filtrage par timeframe se fait dans chaque stratégie individuellement.

### 2.3 — Activation/Désactivation des stratégies

**`_init_inner_strategies()`** (lignes 156-218) :

- Lit `strategy_params["strategies"]` depuis `strategies.yaml`
- Pour chaque entrée :
  - Vérifie `active: true/false` (ligne 174) — **config statique uniquement**
  - Si inactive → skip avec log
  - Lookup dans `_INNER_STRATEGY_CLASSES` registry (ligne 178)
  - Instancie avec `bot_id`, `params`, analyzer partagé
  - Marque `strategy._running = True` manuellement (ne s'abonne pas à l'EventBus)

**Activation dynamique : NON SUPPORTÉE.** Le router construit la liste au init et ne la modifie jamais. Pour ajouter/supprimer → éditer `strategies.yaml` + redémarrer le bot.

### 2.4 — GeminiGlobalRiskManager dans le router

**Init** (lignes 138-139) :
```python
risk_config = params.get("risk", {})
self.risk_manager = GeminiGlobalRiskManager(config=risk_config)
```

**Interception** dans `_apply_risk_overlay()` (lignes 360-376) :
```python
def _apply_risk_overlay(self, signal: TradingSignal) -> TradingSignal | None:
    if self.analyzer is None:
        return signal
    return self.risk_manager.process_signal(
        signal=signal,
        capital=self.capital_usdc,
        analyzer=self.analyzer,
    )
```

**Appliqué UNIQUEMENT sur les signaux BUY** (les SELL passent toujours). Le pipeline :

1. **Crash protector** — si actif, rejette les BUY
2. **ATR-based stop-loss** — SL = entry - 3×ATR(14, "4h")
3. **1% rule** — position size telle que max_loss_at_SL ≤ 1% capital
4. **Injection metadata** : `risk_stop_loss`, `risk_atr`, `risk_position_size_btc`, `position_size_multiplier`

### 2.5 — Routing par bot_id

**`_handle_trade_filled(data)`** (lignes 547-603) :

```python
trade_strategy = data.get("strategy", "")
target = self._strategy_by_bot_id.get(trade_strategy)
# Fallback: loop sur _inner_strategies et match par get_name()
if target:
    await target.on_trade_filled(trade_id, pair, side, amount, price, fee, ...)
```

Chaque inner strategy a un `bot_id` unique (ex: `"supertrend_4h_prod"`). L'ExecutionEngine set `trade.strategy = signal.strategy` sur chaque fill, permettant le routing exact.

### 2.6 — Extension points

Le router est un **dispatcher + risk filter**, pas un meta-decision maker.

Points d'extension potentiels :

1. **Pre-dispatch filter** (avant `_dispatch_to_strategy()`) : activer/désactiver des stratégies dynamiquement selon le régime
2. **Signal aggregation** : collecter tous les signaux avant publication, appliquer une logique meta ("3+ stratégies d'accord → amplifier")
3. **Portfolio rebalancing** : ajuster `max_allocation_pct` dynamiquement entre stratégies
4. **ML signal filter** : dans `_apply_risk_overlay`, interroger un modèle avant d'émettre

L'approche la plus simple : créer un `MetaDecisionLayer` instancié par le router, consulté avant chaque publication de signal.

---

## Section 3 — BaseStrategy et interface stratégies

### 3.1 — Définition complète de BaseStrategy

**Fichier** : `src/krakenbot/strategies/base.py`

```python
class BaseStrategy(ABC):

    def __init__(
        self,
        settings: Settings,
        event_bus: EventBus,
        db_manager: DatabaseManager,
        bot_id: str | None = None,
        strategy_params: dict[str, Any] | None = None,
        analyzer: Any | None = None,
    ) -> None:
        self.settings = settings
        self.event_bus = event_bus
        self.db_manager = db_manager
        self.bot_id = bot_id or self.get_name()
        self.analyzer = analyzer
        self._running = False
        self._current_price: Decimal | None = None
        self._current_timestamp: datetime | None = None
        # ... logging, pair, etc.

    # --- Abstract methods (MUST implement) ---
    @abstractmethod
    async def on_tick(self, tick_data: dict[str, Any]) -> None: ...
    @abstractmethod
    async def on_ohlc(self, ohlc_data: dict[str, Any]) -> None: ...
    @abstractmethod
    async def generate_signal(self) -> TradingSignal | None: ...
    @abstractmethod
    def get_name(self) -> str: ...
    @abstractmethod
    def get_config(self) -> dict[str, Any]: ...

    # --- Lifecycle ---
    async def start(self) -> None:
        self._running = True
        # Subscribe to MARKET_TICK, MARKET_OHLC, TRADE_ORDER_FILLED

    async def stop(self) -> None:
        self._running = False
        # Unsubscribe from all events

    # --- Event handlers (internal) ---
    async def _handle_tick(self, data) -> None: ...      # → on_tick()
    async def _handle_ohlc(self, data) -> None: ...      # → on_ohlc() + generate_signal() + publish
    async def _handle_trade_filled(self, data) -> None:  # → on_trade_filled() [filtered by bot_id]

    # --- Overridable hook ---
    async def on_trade_filled(
        self, trade_id, pair, side, amount, price, fee, reference_price, position_id,
    ) -> None:
        """Default no-op. Override to track positions."""
        pass
```

### 3.2 — TradingSignal

```python
@dataclass
class TradingSignal:
    signal_type: SignalType          # BUY / SELL / HOLD
    pair: str                        # "XBT/USDC"
    price: Decimal                   # Prix courant au moment du signal
    confidence: float                # 0.0 à 1.0
    reason: str                      # Explication humaine
    strategy: str                    # bot_id de la stratégie
    timestamp: datetime              # UTC, timezone-aware
    metadata: dict[str, Any] = field(default_factory=dict)
```

**Champs metadata importants** :
- `order_type: str` — `"limit"` ou `"market"`
- `limit_price: Decimal` — Pour limit orders
- `position_id: int` — Pour SELL (quelle position fermer)
- `amount_btc: Decimal` — Montant exact pour SELL
- `order_size_usdc: Decimal` — Taille explicite
- `position_size_multiplier: float` — Multiplicateur (0.5 = moitié)
- `risk_stop_loss: float` — SL injecté par GeminiGlobalRiskManager
- `risk_atr: float` — ATR utilisé pour le SL
- `risk_position_size_btc: float` — Position size calculée par 1% rule

**Propriétés** :
- `should_trade: bool` — True si BUY ou SELL
- `is_buy: bool` / `is_sell: bool`
- `to_dict()` — Sérialisation

### 3.3 — Logging des signaux

Chaque stratégie log via `structlog` avec des champs structurés. Le pattern standard :

```python
# BaseStrategy._handle_ohlc() (lignes 308-316)
self.logger.info(
    "signal_generated",
    signal_type=signal.signal_type.value,
    pair=signal.pair,
    price=float(signal.price),
    confidence=signal.confidence,
    reason=signal.reason,
    strategy=self.get_name(),
)

# Stratégie-specific tick (ex: GrokSuperTrend4hRegime)
self.logger.info(
    "strategy_tick",
    bot_id=self.bot_id,
    price=float(close),
    st=float(st_value),
    st_dir=st_dir,
    regime_1d=regime_1d,
    position=self._position is not None,
    reason=reason,
)
```

### 3.4 — Persistence des positions

**Les deux** : in-memory ET database.

**In-Memory** :
- Stratégies trackent en dataclass (ex: `_position: SuperTrendPosition`)
- Grid utilise dicts : `_active_positions: dict[int, GridATRPosition]`

**Database** (`open_positions` table) :
- Créée par `ExecutionEngine._handle_buy_trade()` (lignes 554-620 dans `engine.py`)
- Mise à jour via callback `on_trade_filled()`
- Fermée par `ExecutionEngine._handle_sell_trade()` (lignes 706-821)

**Réconciliation au démarrage** : `KrakenBot._reconcile_positions_with_exchange()` (lignes 825-933 dans `main.py`) compare le solde BTC Kraken avec la somme des `open_positions.amount_btc`. Si déficit → marque les positions les plus anciennes comme CLOSED.

### 3.5 — Toutes les stratégies implémentées

| # | Fichier | Classe | Statut | Timeframes | Description |
|---|---------|--------|--------|------------|-------------|
| 1 | `base.py` | `BaseStrategy` | ABC | — | Classe abstraite de base |
| 2 | `multi_strategy_router.py` | `MultiStrategyRouter` | **Active** | Tous | Orchestrateur + risk overlay |
| 3 | `gemini_global_risk_manager.py` | `GeminiGlobalRiskManager` | **Active** | 1m, 4h | Risk overlay : 1% rule, ATR SL, crash protector |
| 4 | `grok_supertrend_4h.py` | `GrokSuperTrend4hRegime` | **Active** | 4h, 1d | Trend-following via SuperTrend + régime daily |
| 5 | `grok_grid_atr_adaptive_v4.py` | `GrokGridATRAdaptiveV4` | **Active** | 4h, 1d, 1w | Grid ATR-adaptive avec bias directionnel |
| 6 | `grok_ema_adx_atr.py` | `GrokEMA27_125_ADX_ATR` | **Active** | 4h, 1d | EMA 27/125 crossover + ADX + stop 3-stage |
| 7 | `grok_adaptive_dca_weekly.py` | `GrokAdaptiveDCAWeekly` | **Active** | 1d, 1w | DCA hebdomadaire BTC adaptatif |
| 8 | `grok_donchian_breakout_4h.py` | `GrokDonchianBreakout4h` | **Watch** | 4h, 1d | Donchian breakout + filtre régime |
| 9 | `grok_ichimoku_cloud_4h.py` | `GrokIchimokuCloud4h` | **Kill** | 4h, 1d | Ichimoku cloud (Sharpe 0.16 — trop bas) |
| 10 | `grok_vwap_trend_4h.py` | `GrokVWAPTrend4h` | **Kill** | 4h | VWAP trend (P&L net négatif) |
| 11 | `gemini_scalping_volatilite.py` | `GeminiScalpingVolatilite` | **Kill** | 5m, 15m, 1h | Bollinger + RSI scalping |
| 12 | `gemini_suivi_tendance_momentum.py` | `GeminiSuiviTendanceMomentum` | **Kill** | 4h, 1d | EMA + MACD momentum (bug pullback) |
| 13 | `gemini_retour_moyenne.py` | `GeminiRetourMoyenne` | **Kill** | 15m, 1h | Mean reversion |
| 14 | `grok_supertrend_short_4h.py` | `GrokSuperTrendShort4h` | Margin | 4h, 1d | Short-only margin (expérimental) |
| 15 | `threshold_rolling.py` | `ThresholdRollingStrategy` | Legacy | 5m | Bot single-strategy original |
| 16 | `adaptive.py` | `AdaptiveStrategy` | Legacy | 5m, 15m, 1h | Multi-timeframe adaptive (remplacé) |
| 17 | `capitulation.py` | `CapitulationStrategy` | Legacy | 5m | Détecteur de capitulation extrême |
| 18 | `bear_short.py` | `BearShortStrategy` | Legacy | 15m, 1h | Short bear market (margin) |
| 19 | `grid_adaptive.py` | `GridAdaptiveStrategy` | Legacy | 15m | Grid adaptive (remplacé par v4) |
| 20 | `grid_spot.py` | `GridSpotStrategy` | Legacy | 15m | Grid basique (remplacé par v4) |
| 21 | `trend_following.py` | `TrendFollowingStrategy` | Legacy | 1h | EMA trend basique (remplacé par supertrend) |

---

## Section 4 — MultiTimeframeAnalyzer et indicateurs

### 4.1 — Signature complète

**Fichier** : `src/krakenbot/indicators/multi_timeframe.py`

```python
class MultiTimeframeAnalyzer:
    def __init__(
        self,
        ema_fast_period: int = 20,
        ema_slow_period: int = 50,
        atr_period: int = 14,
        rsi_period: int = 14,
        bb_period: int = 20,
        regime_neutral_threshold: float = 0.5,
        warmup_candles_1h: int = 50,
    ) -> None:
```

**Toutes les méthodes `get_xxx()`** :

```python
# MACD — params dynamiques par TF
def get_macd(self, tf: str) -> dict[str, Decimal] | None
    # Returns: {"macd": Decimal, "signal": Decimal, "hist": Decimal}
    # TF 1m/5m/15m: (5,13,8), TF 1h/4h: (8,17,9), TF 1d/1w: (12,26,9)

# RSI — lazy creation
def get_rsi(self, period: int, tf: str) -> Decimal | None
    # Returns: 0-100

# ATR — lazy creation
def get_atr(self, period: int, tf: str) -> Decimal | None
    # Returns: ATR en unités de prix

# ADX — period fixe 14
def get_adx(self, tf: str) -> Decimal | None
    # Returns: 0-100 (0-25 faible, 25-50 fort, 50+ très fort)

# Bollinger Bands
def get_bollinger(self, tf: str) -> dict[str, Decimal] | None
    # Returns: {"upper", "middle", "lower", "width"}

# SuperTrend — lazy creation
def get_supertrend(self, tf: str, atr_period: int = 10, multiplier: float = 3.0) -> dict[str, Any] | None
    # Returns: {"supertrend": Decimal, "direction": 1 ou -1}

# EMA — lazy creation, période arbitraire
def get_ema(self, period: int, tf: str) -> Decimal | None
    # Returns: valeur EMA

# Ichimoku Cloud — lazy creation
def get_ichimoku(self, tf: str) -> dict[str, Decimal] | None
    # Returns: {"tenkan", "kijun", "senkou_a", "senkou_b", "chikou", "cloud_top", "cloud_bottom"}

# Donchian Channel — lazy creation
def get_donchian(self, tf: str, period_upper: int = 20, period_lower: int = 10) -> dict[str, Decimal] | None
    # Returns: {"upper", "lower", "middle", "width"}

# VWAP — lazy creation
def get_vwap(self, period: int, tf: str) -> Decimal | None
    # Returns: VWAP rolling

# Market Regime — tout timeframe
def get_regime(self, tf: str) -> str | None
    # Returns: "strong_bear" | "bear" | "neutral" | "bull" | "strong_bull"

# ML Features — extraction complète
def get_features_dict(self, tf: str) -> dict[str, float | str | None]
    # Returns: {"ema_spread", "rsi_14", "atr_ratio", "adx", "macd_hist_norm",
    #           "bb_width", "bb_pctb", "supertrend_dist", "supertrend_dir",
    #           "regime", "volume_ratio", "vwap_deviation"}
```

### 4.2 — Timeframes abonnés

**7 timeframes hardcodés** dans `ALL_TF_KEYS` :

```python
TF_TO_INTERVAL = {
    "1m": 1, "5m": 5, "15m": 15, "1h": 60,
    "4h": 240, "1d": 1440, "1w": 10080,
}
```

Tous sont pré-initialisés dans `__init__()` avec des dictionnaires d'indicateurs par TF.

**Souscriptions WebSocket** (depuis `main.py`) :
- `trigger_timeframe` (5m), `zone_timeframe` (15m), `trend_timeframe` (60m)
- Plus : 240 (4h), 1440 (1d), 10080 (1w)
- Optionnel : 1 (1m) si crash protector activé

**Non configurable** sans modifier `ALL_TF_KEYS`.

### 4.3 — Création lazy des indicateurs

**Exemple** : `get_ema(period=37, tf="4h")`

```python
def get_ema(self, period: int, tf: str) -> Decimal | None:
    tf_ind = self._indicators.get(tf)
    if tf_ind is None:
        return None

    ema_dict = tf_ind.setdefault("ema", {})
    if period not in ema_dict:
        # Premier appel → crée l'indicateur
        ema_dict[period] = EMAIndicator(period=period)
        logger.info("lazy_ema_created", tf=tf, period=period)
        return None  # Pas prêt (aucune donnée)

    indicator = ema_dict[period]
    if not indicator.is_ready:
        return None  # Pas assez de candles (besoin de 37)

    return indicator.value  # Decimal
```

**Processus** :
1. **Premier appel** : crée `EMAIndicator(period=37)`, stocke dans `ema_dict[37]`, log `"lazy_ema_created"`, retourne `None`
2. **Appels suivants** : l'indicateur reçoit des updates via `update()` à chaque candle. Après 37 candles, `is_ready` → True, retourne la valeur.

**Piège connu** : les indicateurs lazy (EMA, SuperTrend, Ichimoku, Donchian, VWAP) doivent être pré-enregistrés AVANT que le warmup ne commence, sinon ils ne recevront pas les données historiques.

### 4.4 — Tous les indicateurs

| # | Indicateur | Méthode | Type retour | Lazy ? |
|---|-----------|---------|-------------|--------|
| 1 | MACD | `get_macd(tf)` | `dict[str, Decimal] \| None` | Non (pré-enregistré) |
| 2 | RSI | `get_rsi(period, tf)` | `Decimal \| None` | Oui |
| 3 | ATR | `get_atr(period, tf)` | `Decimal \| None` | Oui |
| 4 | ADX | `get_adx(tf)` | `Decimal \| None` | Non (pré-enregistré) |
| 5 | Bollinger | `get_bollinger(tf)` | `dict[str, Decimal] \| None` | Non (pré-enregistré) |
| 6 | SuperTrend | `get_supertrend(tf, atr_period, mult)` | `dict[str, Any] \| None` | Oui |
| 7 | EMA | `get_ema(period, tf)` | `Decimal \| None` | Oui |
| 8 | Ichimoku | `get_ichimoku(tf)` | `dict[str, Decimal] \| None` | Oui |
| 9 | Donchian | `get_donchian(tf, period_upper, period_lower)` | `dict[str, Decimal] \| None` | Oui |
| 10 | VWAP | `get_vwap(period, tf)` | `Decimal \| None` | Oui |
| 11 | Régime | `get_regime(tf)` | `str \| None` | Non (utilise EMA fast/slow pré-enregistrées) |
| 12 | ML Features | `get_features_dict(tf)` | `dict[str, float \| str \| None]` | Non (agrégation) |

### 4.5 — Calcul du MarketRegime

**Méthode** : `_classify_regime(ema_spread_pct: float)` (lignes 871-891)

```python
ema_spread_pct = (EMA_fast - EMA_slow) / EMA_slow * 100
threshold = 0.5  # regime_neutral_threshold (défaut)

if ema_spread_pct > threshold * 2:      # > 1.0%  → STRONG_BULL
elif ema_spread_pct > threshold:        # > 0.5%  → BULL
elif ema_spread_pct < -threshold * 2:   # < -1.0% → STRONG_BEAR
elif ema_spread_pct < -threshold:       # < -0.5% → BEAR
else:                                   # -0.5% à +0.5% → NEUTRAL
```

**Exemple** : EMA(20)=50000, EMA(50)=49000 → spread = +2.04% → **STRONG_BULL**

### 4.6 — Timeframes du régime

Le régime est calculé sur **tous les timeframes** (1m, 5m, 15m, 1h, 4h, 1d, 1w). Chaque TF a ses propres EMA fast/slow :

```python
regime_1d = self.analyzer.get_regime("1d")  # EMA(20)/EMA(50) sur candles daily
regime_4h = self.analyzer.get_regime("4h")  # EMA(20)/EMA(50) sur candles 4h
regime_1w = self.analyzer.get_regime("1w")  # EMA(20)/EMA(50) sur candles weekly
```

**Valeurs possibles** (enum `MarketRegime`) :
```python
class MarketRegime(str, Enum):
    STRONG_BEAR = "strong_bear"
    BEAR = "bear"
    NEUTRAL = "neutral"
    BULL = "bull"
    STRONG_BULL = "strong_bull"
```

---

## Section 5 — Stratégies actives en détail

### 5.1 — GrokGridATRAdaptiveV4

**Fichier** : `src/krakenbot/strategies/grok_grid_atr_adaptive_v4.py`

#### `_handle_ohlc` (lignes 300-419)

```python
async def _handle_ohlc(self, data: dict[str, Any]) -> None:
    """Override base _handle_ohlc for grid multi-order management.

    Steps:
    1. Update price (all candles)
    2. Check regime_1w → pause if STRONG_BEAR
    3. Get ATR(14, "4h") → calculate spacing
    4. Initialize or recalculate grid
    5. Emit limit order signals for new levels
    """
    await self.on_ohlc(data)

    # Grid logic only on 4h candles
    tf = data.get("timeframe", data.get("interval"))
    if tf not in ("4h", 240, "240"):
        return

    # ... crash protector, price validation
```

#### Calcul des niveaux de grille

**Spacing** (ligne 161-172) :
```python
def _calculate_spacing(self, atr: Decimal, price: Decimal) -> Decimal:
    """spacing = clamp(atr × atr_multiplier / price, min_spacing, max_spacing)"""
    atr_spacing = atr * self.atr_multiplier / price
    return max(self.min_spacing_pct, min(self.max_spacing_pct, atr_spacing))
```

**Bias directionnel** (lignes 174-199) :
```python
def _get_directional_bias(self, regime_1d: str | None) -> tuple[int, int]:
    """BULL → plus de BUY en dessous (buy the dips)
       BEAR → plus de SELL au dessus (exit rallies)
       NEUTRAL → répartition égale"""
    total = self.grid_levels  # ex: 12
    half = total // 2
    if regime_1d in ("bull", "strong_bull"):
        buy_extra = int(float(self.bias_1d) * half)  # bias_1d=0.2 → extra=1
        n_buy = half + buy_extra
        n_sell = total - n_buy
    elif regime_1d in ("bear", "strong_bear"):
        # Inverse
    else:
        n_buy = half; n_sell = total - n_buy
    return max(1, n_buy), max(1, n_sell)
```

**Construction** (`_build_grid`, lignes 201-250) :
- BUY levels en dessous du prix courant : `price × (1 - spacing × i)` pour i=1..n_buy
- SELL levels au dessus : `price × (1 + spacing × i)` pour i=1..n_sell
- Chaque level émet un `TRADE_SIGNAL` avec `order_type: "limit"` et `limit_price`

#### Détection du weekly STRONG_BEAR

```python
regime_1w = self.analyzer.get_regime("1w")
if self.pause_1w_strong_bear and regime_1w == "strong_bear":
    if not self._paused:
        self.logger.info("grid_paused_strong_bear_1w", regime_1w=regime_1w)
        self._paused = True
    return  # Early exit — aucune opération de grille
if self._paused:
    self._paused = False
    self.logger.info("grid_resumed", regime_1w=regime_1w)
```

#### Recalculation périodique

Toutes les `recalc_hours` (défaut 6h), la grille est recentrée autour du prix courant. Les positions ouvertes conservent leurs sell targets. Seuls les ordres pending sont annulés et reconstruits.

### 5.2 — GrokSuperTrend4hRegime

**Fichier** : `src/krakenbot/strategies/grok_supertrend_4h.py`

#### `_handle_ohlc` (lignes 405-470)

```python
async def _handle_ohlc(self, data: dict[str, Any]) -> None:
    tf = data.get("timeframe", data.get("interval"))
    self._is_4h = tf in ("4h", 240, "240")
    await self.on_ohlc(data)

    if not self._is_4h:
        return  # Signaux uniquement sur les candles 4h

    signal = await self.generate_signal()
    # Log strategy_tick sur chaque candle 4h
    # Publish signal if actionable
```

#### Logique d'entrée (`_check_entry`, lignes 302-399)

**Conditions BUY** :
1. `close > SuperTrend` ET `st_direction == 1` (UP)
2. `regime_1d in ("bull", "strong_bull")`
3. Pas de position ouverte
4. Confidence 0.85 si fresh crossover (direction vient de flipper -1→1), sinon 0.7

```python
# ATR pour le stop-loss initial
atr = self.analyzer.get_atr(14, "4h")
stop_loss = price - self.sl_atr_mult * atr  # sl_atr_mult = 3.5

# Limit order légèrement sous le prix courant (maker fee)
limit_price = price * Decimal("0.999")
```

#### Logique de sortie (`_check_exit`, lignes 208-265)

**Conditions SELL** (toutes en market order pour exécution garantie) :
1. **SuperTrend flip** : `st_direction == -1` OU `price < st_value`
2. **Changement de régime** : `regime_1d in ("bear", "strong_bear")`
3. **Stop-loss** : `price <= pos.stop_loss`

#### Trailing stop (lignes 176-193)

```python
# Le SuperTrend lui-même sert de trailing stop
if st_direction == 1 and st_value > self._position.stop_loss:
    self._position.stop_loss = st_value  # SL monte avec le SuperTrend
```

**SL initial** : `entry_price - 3.5 × ATR(14, "4h")`
**Trailing** : la ligne SuperTrend elle-même. Quand elle monte (uptrend), le SL est mis à jour au niveau du SuperTrend si celui-ci est supérieur au SL courant.

### 5.3 — Interaction avec GeminiGlobalRiskManager

**OUI, les signaux des deux stratégies passent par le risk manager.**

Le flow :
1. Stratégie émet signal via `event_bus.publish(TRADE_SIGNAL, ...)`
2. Le `_RiskOverlayEventBusProxy` intercepte
3. `_apply_risk_overlay(signal)` appelle `GeminiGlobalRiskManager.process_signal()`
4. **SELL** → passe directement (les sorties ne doivent jamais être bloquées)
5. **BUY** → pipeline complet :
   - Crash protector check
   - Calcul ATR-based SL : `entry - 3 × ATR(14, "4h")`
   - Position sizing 1% rule : `max_loss_at_SL ≤ 1% of capital`
   - Injection metadata dans le signal
   - Override `position_size_multiplier` si le 1% rule donne un size plus petit
6. Signal modifié → publication sur le vrai EventBus → ExecutionEngine

---

## Section 6 — Exécution et risk management

### 6.1 — ExecutionEngine

**Fichier** : `src/krakenbot/execution/engine.py`

**Responsabilités** :
- Subscribe aux `TRADE_SIGNAL` events
- Valide les ordres via `GlobalRiskManager` (2 niveaux)
- Exécute via `KrakenRestClient` (market) ou `OrderManager` (limit)
- Met à jour `BotState` et `OpenPosition` après chaque trade
- Log toutes les décisions

**Méthode principale** : `_handle_signal(data)` (lignes 155-219)

```python
async def _handle_signal(self, data: dict[str, Any]) -> None:
    signal: TradingSignal = data.get("signal")
    if not signal.should_trade:
        return  # Ignore HOLD
    await self._execute_signal(signal)
```

### 6.2 — GlobalRiskManager (execution/risk.py)

**Fichier** : `src/krakenbot/execution/risk.py`

#### Niveau 1 — Checks globaux (toutes stratégies)

```python
# Balance check (solde réel exchange)
await self._check_balance(result, pair, side, amount, price, balance)

if side == TradeSide.BUY:
    # Max positions globales
    if global_positions >= self._global_max_positions:
        result.add_reason("Global max positions reached")

    # Daily loss limit globale
    if global_daily_pnl <= -self._global_daily_loss:
        result.add_reason("Global daily loss limit reached")

    # Exposure portfolio globale
    await self._check_global_exposure(result, pair, amount, price, balance)
```

#### Niveau 2 — Checks par stratégie (filtré par bot_id)

```python
if bot_id and bot_id in self._strategy_risk_managers:
    strategy_rm = self._strategy_risk_managers[bot_id]
    strategy_result = await strategy_rm.check_order(pair, side, amount, price, balance)
    # Checks: balance, position size, daily loss, max positions, trade interval
```

**Position size check** : `order_value / portfolio_value * 100 > max_position_pct` → rejet.

### 6.3 — Flow complet d'un signal BUY → ordre Kraken

```
1. Strategy → event_bus.publish(TRADE_SIGNAL, signal)
2. Router → _RiskOverlayEventBusProxy intercepts
3. → GeminiGlobalRiskManager.process_signal()
   → crash protector, ATR SL, 1% sizing
4. Router → publish to real EventBus
5. ExecutionEngine._handle_signal()
6. → balance = await rest_client.get_balance()
7. → risk_result = await risk_manager.check_order(pair, side, amount, price, balance, bot_id)
   → Level 1: global checks (balance, positions, daily loss, exposure)
   → Level 2: per-strategy checks (budget, position size, interval)
8. → If REJECTED: log + publish rejection event
9. → If APPROVED + order_type == "limit":
     → OrderManager.place_and_track()
       → KrakenRestClient.place_limit_order()
       → If immediately filled → publish TRADE_ORDER_FILLED
       → Else → add to _pending_orders (polled every 30s)
10. → If APPROVED + order_type == "market":
     → KrakenRestClient.place_market_order()
     → On fill → _update_bot_state() → create OpenPosition
     → EventBus.publish(TRADE_ORDER_FILLED)
```

### 6.4 — Gestion des ordres pending

**OrderManager** (`execution/order_manager.py`) :

- **Polling** : `check_pending_orders()` appelé toutes les 30 secondes
- **Paper mode** : simule les fills — BUY limit fill si `candle_low <= limit_price`, SELL limit fill si `candle_high >= limit_price`
- **Live mode** : query Kraken API `get_order_status()` → si `"closed"` → fill, si `"canceled"` → cancel
- **Expiry** : `limit_order_expiry_minutes` (config) pour les ordres normaux, 24h (86400s) pour les profit targets
- **Expired** : cancel sur exchange + `OrderStatus.EXPIRED` + remove from tracking

### 6.5 — Paper trading vs Live

| Aspect | Paper | Live |
|--------|-------|------|
| Balance | `_paper_balance` dict en mémoire | `exchange.fetch_balance()` via ccxt |
| Market orders | Update `_paper_balance` immédiatement | `exchange.create_order()` via ccxt |
| Limit orders | Stockés dans `_paper_orders`, fills simulés par candles | `exchange.create_limit_order()`, status polled |
| Fees | Calculés mais fictifs | Réels (maker 0.16%, taker 0.26%) |
| Persistence | `persist_paper_balance()` en DB | — |
| Activation | `TRADING_MODE=paper` (défaut) | `TRADING_MODE=live` + `TRADING_CONFIRM_LIVE=yes` |

---

## Section 7 — Données et DB

### 7.1 — Tables de la base de données

**5 tables principales** :

#### 1. `market_data_ohlc` (hypertable TimescaleDB)

```
PK: (timestamp, pair, interval)  — composite
Colonnes:
  timestamp     TIMESTAMP(tz)    Candle open time (UTC)
  pair          VARCHAR(20)      "XBT/USDC"
  interval      INTEGER          Minutes (1, 5, 15, 60, 240, 1440, 10080)
  open          DECIMAL(18,8)
  high          DECIMAL(18,8)
  low           DECIMAL(18,8)
  close         DECIMAL(18,8)
  volume        DECIMAL(18,8)
  vwap          DECIMAL(18,8)    Nullable
  trades_count  INTEGER          Nullable
Indexes:
  ix_ohlc_pair_timestamp (pair, timestamp)
  ix_ohlc_timestamp_desc (timestamp DESC)
```

#### 2. `trades_history`

```
PK: id (UUID)
Colonnes:
  timestamp     TIMESTAMP(tz)    Execution time
  pair          VARCHAR(20)
  side          ENUM(buy/sell)
  amount        DECIMAL(18,8)    Base currency
  price         DECIMAL(18,8)
  fee           DECIMAL(18,8)
  fee_currency  VARCHAR(10)      Default "EUR"
  trading_mode  VARCHAR(10)      "spot" or "margin"
  strategy      VARCHAR(50)      bot_id
  pnl           DECIMAL(18,8)    Nullable (calculated on sell)
  status        ENUM(pending/filled/cancelled/failed)
  order_id      VARCHAR(100)     Exchange order ID
  notes         TEXT             Nullable
  created_at    TIMESTAMP(tz)
Indexes:
  ix_trades_pair_timestamp, ix_trades_strategy_timestamp, ix_trades_status_timestamp
```

#### 3. `open_positions`

```
PK: id (UUID)
Colonnes:
  bot_id         VARCHAR(100)    Strategy instance identifier
  strategy       VARCHAR(50)
  position_id    INTEGER         Strategy-assigned position ID
  pair           VARCHAR(20)
  trading_mode   VARCHAR(10)     "spot" or "margin"
  entry_price    DECIMAL(18,8)
  amount_btc     DECIMAL(18,8)
  reference_price DECIMAL(18,8)  Price that triggered entry
  entry_time     TIMESTAMP(tz)
  entry_trade_id UUID            FK → trades_history
  exit_trade_id  UUID            Nullable, FK → trades_history
  status         ENUM(open/closed/cancelled)
  closed_at      TIMESTAMP(tz)   Nullable
  pnl            DECIMAL(18,8)   Nullable (calculated on close)
  created_at     TIMESTAMP(tz)
  updated_at     TIMESTAMP(tz)
Indexes:
  ix_open_positions_bot_id, ix_open_positions_strategy, ix_open_positions_status
```

#### 4. `bot_state`

```
PK: bot_id (VARCHAR(50))
Colonnes:
  strategy          VARCHAR(50)
  status            ENUM(initializing/running/stopped/error/paused)
  position_size     DECIMAL(18,8)    Current size in base currency
  entry_price       DECIMAL(18,8)    Nullable
  daily_pnl         DECIMAL(18,8)    Resets at midnight UTC
  total_pnl         DECIMAL(18,8)
  daily_trades_count INTEGER
  last_signal_at    TIMESTAMP(tz)    Nullable
  last_trade_at     TIMESTAMP(tz)    Nullable
  error_message     TEXT             Nullable
  updated_at        TIMESTAMP(tz)    Auto-updated
  created_at        TIMESTAMP(tz)
```

#### 5. `orders`

```
PK: id (UUID)
Colonnes:
  order_id        VARCHAR(100)    Exchange order ID (unique)
  bot_id          VARCHAR(100)
  pair            VARCHAR(20)
  side            ENUM(buy/sell)
  order_type      ENUM(market/limit)
  amount          DECIMAL(18,8)    Requested amount
  price           DECIMAL(18,8)    Limit price (nullable for market)
  filled_amount   DECIMAL(18,8)    Nullable
  filled_price    DECIMAL(18,8)    Nullable (average fill price)
  fee             DECIMAL(18,8)    Nullable
  status          ENUM(pending/filled/cancelled/expired)
  strategy        VARCHAR(50)
  signal_metadata JSON             Metadata from TradingSignal
  expires_at      TIMESTAMP(tz)    Nullable (auto-cancel time)
  created_at      TIMESTAMP(tz)
  updated_at      TIMESTAMP(tz)
```

### 7.2 — Collector et alimentation DB

**Fichier** : `src/krakenbot/collector.py`

Le `DataCollector` est un **service séparé** (`python -m krakenbot.collector`) qui tourne 24/7. Il utilise :

1. **WebSocket** pour les candles temps-réel (dernière candle en cours)
2. **REST API scheduler** pour le backfill historique multi-interval

```python
class DataCollector:
    """Standalone data collector service.
    1. Real-time OHLC data collection via WebSocket
    2. Scheduled historical data backfill via REST API
    """
```

La persistence utilise `session.merge(ohlc)` qui assure l'idempotence via la clé composite `(timestamp, pair, interval)`. Si la même candle arrive deux fois (WebSocket + REST backfill), la row existante est mise à jour plutôt que dupliquée.

Les deux services (collector et bot) communiquent **uniquement via la DB**.

### 7.3 — Warmup au démarrage

**Fichier** : `src/krakenbot/indicators/multi_timeframe.py` (lignes 236-292)

```python
async def initialize(self, db_manager: DatabaseManager, pair: str = "XBT/USDC") -> None:
    """Load historical candles from database for warmup."""
    for interval, count in [
        (60, 100),    # 1h: 100 candles
        (15, 100),    # 15m: 100 candles
        (5, 100),     # 5m: 100 candles
        (240, 100),   # 4h: 100 candles
        (1440, 100),  # 1d: 100 candles
        (10080, 60),  # 1w: 60 candles
    ]:
        candles = await session.execute(
            select(OHLCData)
            .where(OHLCData.pair == pair, OHLCData.interval == interval)
            .order_by(OHLCData.timestamp.asc())
            .limit(count)
        )
        for candle in candles:
            self.update(candle_dict, interval)
```

Appelé dans `KrakenBot.start()` :
```python
if self._multi_strategy_mode and self.analyzer:
    await self.analyzer.initialize(self.db_manager)
```

### 7.4 — Séparation données live vs historiques

**Complètement claire** :

- **Historique** (DB) : source unique = `market_data_ohlc` hypertable. Utilisé une seule fois au démarrage pour le warmup.
- **Live** (WebSocket) : après le warmup, toutes les données passent par `WebSocket → EventBus(MARKET_OHLC) → Strategies`. Les stratégies ne font jamais de requête DB pendant le trading.
- **Collector** : écrit continuellement dans la DB en arrière-plan, mais le bot de trading ne lit pas la DB après le warmup.

---

## Section 8 — Points d'extension et difficultés anticipées

### 8.1 — Ajout d'un Regime Detector

#### Existe-t-il déjà un embryon ?

**OUI.** La détection de régime est déjà intégrée dans `MultiTimeframeAnalyzer` :

- **`MarketRegime` enum** (lignes 76-84) : `STRONG_BEAR`, `BEAR`, `NEUTRAL`, `BULL`, `STRONG_BULL`
- **`_classify_regime(ema_spread_pct)`** (lignes 871-891) : classification par EMA spread
- **`get_regime(tf)`** (lignes 741-768) : API publique, tout timeframe

Les stratégies l'utilisent déjà individuellement :
```python
regime_1d = self.analyzer.get_regime("1d")
if regime_1d not in ("bull", "strong_bull"):
    return None  # Block BUY
```

#### Où insérer un composant centralisé ?

**Point d'insertion** : `MultiStrategyRouter._handle_ohlc()` (ligne 298), **AVANT** le dispatch aux inner strategies.

```python
async def _handle_ohlc(self, data: dict[str, Any]) -> None:
    # ... crash protector ...

    # NEW: Régime centralisé
    current_regime = self.regime_detector.evaluate(self.analyzer)

    # Dispatch avec contexte régime
    for strategy in self._inner_strategies:
        if self.regime_detector.is_eligible(strategy, current_regime):
            await self._dispatch_to_strategy(strategy, data)
```

#### Fichiers à créer/modifier

1. **Créer** : `src/krakenbot/strategies/regime_detector.py`
   ```python
   class RegimeDetector:
       def evaluate(self, analyzer: MultiTimeframeAnalyzer) -> dict:
           """Returns multi-TF regime assessment."""
       def is_eligible(self, strategy: BaseStrategy, regime: dict) -> bool:
           """Should this strategy receive candles in current regime?"""
   ```

2. **Modifier** : `multi_strategy_router.py`
   - Instancier `RegimeDetector` dans `__init__()`
   - Appeler avant le dispatch dans `_handle_ohlc()`

3. **Modifier** : `strategies.yaml`
   ```yaml
   params:
     regime_detector:
       enabled: true
       timeframe: "4h"
       block_strategies_in_bear: ["grok_supertrend_4h"]
   ```

**Attention** : les stratégies ont déjà leurs propres filtres de régime internes. Un filtre centralisé serait **redondant** sauf pour imposer un gate global (ex: "aucun BUY en weekly STRONG_BEAR, tous stratégies confondues").

### 8.2 — Ajout d'une stratégie Donchian breakout

#### L'embryon existe déjà !

**Fichier** : `src/krakenbot/strategies/grok_donchian_breakout_4h.py` (déjà implémenté mais `active: false`)

**Config** dans `strategies.yaml` (lignes 172-181) :
```yaml
grok_donchian_breakout_4h:
  active: false
  bot_id: donchian_breakout_4h
  params:
    period_upper: 20
    period_lower: 10
    sl_atr_mult: 3.5
    adx_threshold: 18
    max_allocation_pct: 15.0
  pairs: ["SOL/USDC"]
```

#### Étapes pour activer

1. **YAML** : Changer `active: false` → `active: true` dans `strategies.yaml`
2. **Registry** : Vérifier que `"grok_donchian_breakout_4h": GrokDonchianBreakout4h` est dans `_INNER_STRATEGY_CLASSES` (dans `multi_strategy_router.py`)
3. **Registry top-level** : Ajouter dans `STRATEGY_REGISTRY` (dans `main.py`) si on veut aussi le supporter en mode single-strategy
4. **Aucun nouveau fichier** : tout existe déjà

#### Indicateurs existants utilisables

- `get_donchian("4h", period_upper=20, period_lower=10)` → `{"upper", "lower", "middle", "width"}`
- `get_atr(14, "4h")` → pour stop-loss
- `get_adx("4h")` → pour filtre force de trend
- `get_regime("1d")` → pour filtre régime

**Aucun nouvel indicateur nécessaire.**

#### Pièges à éviter

1. **Lazy indicator warmup** : le Donchian est lazy — s'il n'est pas pré-enregistré dans `MultiTimeframeAnalyzer.__init__()`, il ne recevra pas les données historiques du warmup. **Fix** : ajouter l'init explicite dans `__init__()`.

2. **Breakout vs current candle** : le Donchian upper/lower inclut la candle courante. Pour détecter un breakout, il faut comparer au `prev_donchian_upper` (la valeur avant la candle courante), pas au upper actuel.

3. **Multi-pair** : la config spécifie `pairs: ["SOL/USDC"]` mais le router actuel ne supporte qu'un seul pair (XBT/USDC). Il faudrait soit restreindre au BTC, soit étendre le router pour le multi-pair.

4. **Timeframe 4h** : déjà subscrit dans le WebSocket (hardcodé dans `main.py`), donc pas de problème.

### 8.3 — Dettes techniques

**TODO/FIXME trouvés** :

1. **`threshold_rolling.py`** (lignes 627-629) :
   ```python
   # TODO: Implement DB loading of multiple positions
   # For now, rely on in-memory state
   pass
   ```
   Impact : **faible** — stratégie legacy, désactivée en multi-strategy.

**Pas de `FIXME`, `HACK`, ou `XXX`** dans le codebase.

**Dettes techniques implicites** (documentées dans MEMORY.md) :

1. **Bug pullback `gemini_suivi_tendance_momentum`** : `_update_pullback_state()` écrase `_prev_close_4h` avant `generate_signal()`, rendant la détection de pullback impossible. Bug présent en live aussi. **Impact** : stratégie désactivée.

2. **Bug DCA Weekly multi-pair** : 0 trades sur ETH/SOL (fonctionne sur BTC). **Impact** : stratégie désactivée pour ces pairs.

3. **Lazy indicator warmup** : les indicateurs lazy ne reçoivent pas le warmup historique s'ils ne sont pas pré-enregistrés. **Impact** : tout nouvel indicateur lazy utilisé par une stratégie doit être explicitement pré-enregistré.

### 8.4 — Tests unitaires

**14 fichiers de test** dans `tests/test_strategies/` :

| Fichier | Tests | Couverture |
|---------|-------|------------|
| `test_multi_strategy_router.py` | 2 tests | Risk processing path + rejection path |
| `test_grid_atr_debug.py` | 7 tests | Spacing, grid centering, recalc, config |
| `test_supertrend_debug.py` | 8 tests | Regime filter (bear/neutral/strong_bear), bull entry, diagnostic logging |
| `test_gemini_risk_manager.py` | — | GeminiGlobalRiskManager tests |
| `test_base.py` | — | BaseStrategy tests |
| `test_strategies_basic.py` | — | Tests basiques sur toutes les stratégies |
| `test_dca_weekly.py` | — | DCA Weekly tests |
| Autres (legacy) | — | capitulation, bear_short, trend_following, grid_spot, grid_adaptive, adaptive |

**Évaluation** :

- **Router** : **2 tests seulement** — couvre le chemin critique (risk processing) mais manque le dispatch multi-stratégie, l'agrégation de signaux, le handling d'erreurs.
- **Grid ATR V4** : **7 tests** — bonne couverture de la logique core (spacing, centering, recalc). Manque : exécution d'ordres, tracking de positions, calcul P&L.
- **SuperTrend 4h** : **8 tests** — bonne couverture du regime filtering et de la génération de signaux. Manque : logique de sortie (trailing stop, stop-loss), trade fill handling.

**Verdict** : couverture **adéquate pour les tests unitaires**, mais **minimale pour l'intégration**. Un agent qui modifie le router ne devrait casser que 2 tests (faciles à fixer), mais les effets de bord sur les stratégies internes ne sont pas couverts.

### 8.5 — Extensibilité de strategies.yaml

**Fichier** : `strategies.yaml` (327 lignes)

**Structure hiérarchique** :

```yaml
enabled: true                          # Mode multi-stratégie
deployment_profile: { ... }            # Metadata deployment
global_max_open_positions: 8           # Limites globales
common_indicators: { ... }            # Config shared analyzer
ml: { enabled: false, ... }           # Pipeline ML (disabled)
strategies:
  - name: multi_strategy_router
    enabled: true
    bot_id: multi_router
    budget: { ... }                    # Risk budget
    params:
      capital_usdc: 1000
      risk: { ... }                   # GeminiGlobalRiskManager config
      strategies:                     # ← Inner strategies nested here
        grok_grid_atr_adaptive_v4:
          active: true
          bot_id: grid_atr_v4
          params: { ... }
        grok_supertrend_4h:
          active: true
          bot_id: supertrend_4h_prod
          params: { ... }
        # ... 5 other strategies
```

**Extensibilité** :

| Action | Effort |
|--------|--------|
| Ajouter une stratégie | 1 bloc YAML sous `strategies:` |
| Activer/désactiver | Toggle `active: true/false` |
| Tuner les paramètres | Modifier `params:` sans toucher au code |
| Ajouter un paramètre | Ajouter la clé dans `params:` + lire dans le constructeur |

**Forces** : déclaratif, hiérarchique, bien commenté.
**Faiblesses** : pas de validation schema YAML (dépend de Pydantic au runtime), structure profondément imbriquée, pas d'héritage entre stratégies.

---

## Conclusion et Recommandations

### 1. Le Regime Detector centralisé est optionnel

Le régime est déjà calculé par le `MultiTimeframeAnalyzer` et utilisé individuellement par chaque stratégie. Un détecteur centralisé dans le router n'est utile que si on veut un **gate global** ("zéro trading en weekly STRONG_BEAR") sans dupliquer la logique dans chaque stratégie. L'implémentation serait simple : ~100 lignes dans un nouveau fichier + quelques lignes dans `_handle_ohlc()`.

### 2. Donchian breakout est prêt à activer

La stratégie existe, la config YAML existe, les indicateurs existent. Il suffit de : (a) s'assurer que la classe est dans `_INNER_STRATEGY_CLASSES`, (b) pré-enregistrer le Donchian dans le warmup, (c) comparer au `prev_donchian_upper` pour le breakout, (d) mettre `active: true`.

### 3. Le router a besoin de plus de tests

2 tests pour le composant le plus critique du système est insuffisant. Priorité : tester le dispatch multi-stratégie, le crash protector flow, et le routing des fills par bot_id.

### 4. L'architecture est saine et extensible

L'EventBus pub/sub, le pattern proxy pour le risk overlay, et la config YAML déclarative rendent l'ajout de nouvelles stratégies très simple. Le seul point d'attention est le piège des indicateurs lazy qui ne sont pas warmup.

### 5. Résoudre le piège lazy indicator warmup

Le bug le plus impactant pour le futur développement : tout nouvel indicateur lazy (SuperTrend, Donchian, VWAP, etc.) utilisé par une stratégie ne reçoit pas les données historiques du warmup. Solution recommandée : faire un "pre-registration pass" dans `MultiTimeframeAnalyzer.initialize()` qui scanne les stratégies actives pour leurs indicateurs requis avant de charger les candles.
