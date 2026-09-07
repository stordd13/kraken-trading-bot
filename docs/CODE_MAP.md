# CODE_MAP — où est quoi dans KrakenBot

> Généré le 2026-09-07 sur `v2.1.0-p6-7-multiprocessing-1-gb5b0de8` (branche `feat/b0-bybit-audit`, base `dev`).
> Commande : `wc -l` + `grep -n -E "^(class |def |async def )|^    (async )?def [a-z]"` + `grep -n "^from krakenbot"` sur `src/krakenbot/**/*.py` et `scripts/*.py`.
> À régénérer à chaque merge sur `dev`. Numéros de ligne = `symbole:ligne`. Hors tests, hors `scripts/audit/`.
> Total : src 31 649 lignes (ml inclus), scripts 12 895 lignes. Les scripts P7 (`run_p7_grid_search.py`…) n'existent que sur `feat/p7-parameter-optimization`.

## Flux runtime en 5 lignes

`__main__.py` → `main.KrakenBot` (setup:171, start:512, run:985) instancie settings, DB, EventBus, REST/WS via `connectors/exchange.py`,
`MultiStrategyRouter` (une par `strategies.yaml`), `ExecutionEngine`, `OrderManager`, `GlobalRiskManager`, `MultiPairAnalyzerRegistry`.
WS publie `MARKET_OHLC` → router `_handle_ohlc:275` → stratégie interne `on_ohlc`/`generate_signal` → `GeminiGlobalRiskManager.process_signal:321`
→ `TRADE_SIGNAL` → `ExecutionEngine._handle_signal:155` → REST (`place_limit_order`/`place_market_order`) → `TRADE_ORDER_FILLED`
→ router `_handle_trade_filled:612` → stratégie source via `bot_id`. Le collector (`collector.py`) est le même WS sans trading.

## config/

| Module | Lignes | Rôle | Symboles clés | Attention |
|---|---|---|---|---|
| `settings.py` | 852 | Pydantic settings (env + `strategies.yaml`) | `KrakenSettings:43`, `BinanceSettings:84`, `DatabaseSettings:123`, `RiskManagementSettings:150`, `TradingSettings:186`, `MultiStrategySettings:390`, `ExchangeFees:458` (`kraken_defaults:469`, `binance_defaults:474`), `OrderSettings:549`, `_validate_router_runtime_alignment:608`, `Settings:657`, `get_settings:825`, `reload_settings:842` | `exchange_name` default `"kraken"` (:687) ; `trading.pair` default `"XBT/USDC"` (:196) ; `ScheduledTasksSettings` pairs default `["XBT/USDC","XBT/EUR"]` (:355) ; importe `strategies.multi_strategy_router` (couplage config→stratégies) |

## core/

| Module | Lignes | Rôle | Symboles clés | Dépendances |
|---|---|---|---|---|
| `event_bus.py` | 510 | Pub/sub async central | `EventType:55`, `Event:83`, `EventBus:109` (`subscribe:155`, `publish:236`, `publish_and_wait:321`, `get_history:444`), `get_event_bus:489` | appelé par tout le runtime |
| `database.py` | 373 | Engine SQLAlchemy async + TimescaleDB | `Base:34`, `DatabaseManager:44` (`init_db:98`, `session:179`, `read_session:204`, `create_hypertable:231`), `get_db_manager:298`, `init_db:310`, `get_session:334` | `config.settings` |
| `exceptions.py` | 516 | Hiérarchie d'erreurs | `KrakenBotError:33`, `KrakenAPIError:78`, `RateLimitError:113`, `WebSocketError:147`, `InsufficientBalanceError:255`, `RiskLimitExceededError:291`, `OrderExecutionError:327`, `OrderCancelError:368` | noms « Kraken » réutilisés par Binance |
| `logger.py` | 297 | structlog + masquage secrets | `mask_secrets:50`, `configure_logging:156`, `get_logger:237`, `bind_context:254` | `config.settings` |

## models/

| Module | Lignes | Rôle | Symboles clés | Attention |
|---|---|---|---|---|
| `base.py` | 172 | Enums partagés | `TradeSide:55`, `TradeStatus:67`, `BotStatus:87`, `SignalType:105`, `PositionStatus:119`, `OrderType:133`, `OrderStatus:145`, `TradingMode:163` | `TradingMode` dupliqué dans `config/settings.py:26` |
| `market_data.py` | 253 | Hypertables OHLC/ticks | `OHLCData:20`, `TickData:167` | colonne `exchange` default/server_default `"kraken"` (:65-66) ; PK (timestamp, pair, interval, exchange) |
| `trades.py` | 819 | Tables trading | `Trade:31`, `BotState:208`, `OpenPosition:387`, `BacktestRun:567`, `PaperBalance:764`, `utc_now:22` | |
| `orders.py` | 216 | Ordres LIMIT suivis | `Order:26` | |
| `scheduled_tasks.py` | 107 | Log du scheduler | `TaskExecutionLog:17` | |

## connectors/

| Module | Lignes | Rôle | Symboles clés | Dépendances / attention |
|---|---|---|---|---|
| `exchange.py` | 177 | Protocol + factories | `ExchangeRestClient:26` (Protocol), `build_exchange_rest_client:128`, `build_exchange_ws_client:151` | dispatch sur `settings.exchange_name` (`binance` sinon Kraken) ; appelé par `main.py`, `collector.py`, `order_manager.py` |
| `base_ws.py` | 107 | ABC WebSocket | `BaseWebSocketClient:25` (`connect:90`, `subscribe_ohlc:98`, `subscribe_ticker:102`) | |
| `base_perps.py` | 114 | ABC perpétuels | `BaseExchangePerps:15` (`place_perp_order:43`, `get_funding_rate:82`) | seul impl : `kraken/futures.py` |
| `binance/rest.py` | 1486 | REST Binance via ccxt + paper | `MIN_ORDER_SIZE:58`, `MIN_NOTIONAL:65`, `BinanceRestClient:68` (`get_balance:182`, `fetch_ohlcv:269`, `place_market_order:521`, `place_limit_order:824`, `get_order_status:1096`, `cancel_order:1166`, `initialize_paper_balance:1265`) | LOT_SIZE hardcodés BTC/ETH/SOL ; `place_margin_order:1237` = stub |
| `binance/ws.py` | 844 | WS Binance (kline/ticker) | `INTERVAL_MAP`/`BINANCE_INTERVAL_MAP:63`, `_pair_to_symbol:73`, `BinanceWebSocketClient:93` (`connect:148`, `subscribe_ohlc:217`, `_handle_kline:399`, `_data_flow_watchdog:560`, `_preventive_reconnect_timer:606`) | timestamp DB = `T + 1 ms` (:423) ; `exchange="binance"` hardcodé (:450) ; reconnect 23 h |
| `kraken/rest.py` | 1930 | REST Kraken (legacy, référence paper) | `normalize_asset_symbol:86`, `normalize_asset_balances:91`, `KrakenRestClient:100` (`place_market_order:327`, `place_margin_order:654`, `place_limit_order:1130`, `get_order_status:1433`, `fetch_ohlcv:1605`) | `normalize_asset_*` importés par `execution/order_manager.py:28` et `execution/risk.py:35` |
| `kraken/ws.py` | 1131 | WS Kraken v1 | `KrakenWebSocketClient:81` (`subscribe_ohlc:931`, `subscribe_trades:1011`, `ping:1124`) | map `BTC/USDC→XBT/USDC` (:74-75) ; `exchange="kraken"` (:645,669) |
| `kraken/futures.py` | 251 | Kraken Futures perps | `KrakenFuturesClient:23` (`place_perp_order:94`, `get_funding_history:214`) | utilisé par `grok_supertrend_short_4h` uniquement |

## execution/

| Module | Lignes | Rôle | Symboles clés | Dépendances / attention |
|---|---|---|---|---|
| `engine.py` | 934 | Consomme `TRADE_SIGNAL`, exécute, met à jour `BotState`/`OpenPosition` | `ExecutionEngine:43` (`start:120`, `_handle_signal:155`, `_execute_signal:220`, `_calculate_order_amount:409`, `_handle_buy_trade:554`, `_handle_limit_order_fill:678`, `_handle_sell_trade:706`, `execute_manual_order:851`) | type hint `rest_client: KrakenRestClient` (:82, TYPE_CHECKING) alors que Binance est injecté ; ne pas modifier sans review |
| `order_manager.py` | 869 | Cycle de vie LIMIT (polling, timeout, profit target) | `_parse_interval_minutes:64`, `OrderManager:84` (`load_pending_from_db:156`, `place_and_track:194`, `check_pending_orders:285`, `place_profit_target:526`, `on_ohlc:620`, `cancel_all_pending:842`) | importe `normalize_asset_*` de `kraken/rest.py` ; docstring « Kraken API status polling » |
| `risk.py` | 919 | Risk legacy + global multi-stratégie | `RiskCheckResult:49`, `RiskManager:99` (`check_order:181`), `GlobalRiskManager:539` (`register_strategy:596`, `check_order:622`, `check_emergency_stop_loss:826`, `get_risk_summary:903`) | idem import kraken ; ne pas bypasser |

## strategies/

| Module | Lignes | Rôle | Symboles clés | Attention |
|---|---|---|---|---|
| `base.py` | 513 | ABC + signal | `TradingSignal:40` (`to_dict:104`), `BaseStrategy:122` (`bot_id:171`, `effective_pair:180`, `on_ohlc:203`, `generate_signal:215`, `get_name:227`, `get_config:236`, `on_trade_filled:462`) | |
| `multi_strategy_router.py` | 714 | Dispatch par pair + overlay risque | `_INNER_STRATEGY_CLASSES:54` (8 classes), `_RiskOverlayEventBusProxy:66`, `MultiStrategyRouter:96` (`_init_inner_strategies:167`, `_handle_ohlc:275`, `_dispatch_to_strategy:376`, `_apply_risk_overlay:418`, `_handle_crash:467`, `_handle_trade_filled:612`) | registre statique : nouvelle stratégie = ajouter au dict :54 ; ne pas modifier sans review |
| `gemini_global_risk_manager.py` | 497 | 1 % rule, ATR SL, crash protector | `GeminiGlobalRiskManager:48` (`calculate_position_size:110`, `calculate_stop_loss:151`, `check_crash_protector:189`, `generate_crash_sells:252`, `process_signal:321`, `check_strategy_budget:443`) | `generate_crash_sells` pair default `"BTC/USDC"` (:256) |

Les 8 stratégies internes du router (fichier `grok_*`/`gemini_*`, toutes `pair`-aware, positions persistées dans `open_positions`) :

| Classe | Fichier (lignes) | TF signal | Params clés (`strategies.yaml`) | Statut |
|---|---|---|---|---|
| `GrokGridATRAdaptiveV4:71` | `grok_grid_atr_adaptive_v4.py` (666) | 4h (biais 1d/1w) | grid_levels 12, spacing 1.5-5 %, atr 14×4.0, recalc 6 h, order 10 USDC | actif BTC |
| `GrokSuperTrend4hRegime:58` | `grok_supertrend_4h.py` (555) | 4h (régime 1d) | st_atr 10, mult 3.0, sl_atr 3.5, alloc 10 % | actif BTC ; ETH/SOL off |
| `GrokDonchianChannelBreakoutV1:59` | `grok_donchian_breakout_4h.py` (515) | 4h (régime 1d) | upper 20, lower 10, sl_atr 3.5, adx 18, order 30 USDC | actif BTC |
| `GrokEMA27_125_ADX_ATR:63` | `grok_ema_adx_atr.py` (581) | 4h (régime 1d) | ema 20/50, adx 14, atr stop 3.5, trailing 3.0 | off (J30) |
| `GrokAdaptiveDCAWeekly:71` | `grok_adaptive_dca_weekly.py` (407) | 1d/1w | base 15 USDC, oversold ×2.5, rsi 30, alloc 25 % | off ; 0 trade ETH/SOL en backtest |
| `GeminiScalpingVolatilite:50` | `gemini_scalping_volatilite.py` (488) | 5m (filtre 1h) | rsi 7/30, sl 1.5 atr, tp 1.0 atr | KILL 1A |
| `GeminiSuiviTendanceMomentum:52` | `gemini_suivi_tendance_momentum.py` (478) | 4h (régime 1d) | adx 20, sl 2.5 atr, trailing 2.0 | KILL 1A (bug pullback `_prev_close_4h`) |
| `GeminiRetourMoyenne:50` | `gemini_retour_moyenne.py` (516) | 15m (filtre 1h) | dca 3×0.5 %, sl 2.0 atr | KILL 1A |

Hors registre du router (dans `strategies.yaml` mais absents de `_INNER_STRATEGY_CLASSES:54` → rejetés au chargement si activés) :
`GrokIchimokuCloudBreakoutV1:59` `grok_ichimoku_cloud_4h.py` (523, KILL 1B) · `GrokVWAPTrendV1:62` `grok_vwap_trend_4h.py` (521, KILL 1B) ·
`GrokSuperTrendShort4hRegime:64` `grok_supertrend_short_4h.py` (569, short via `KrakenFuturesClient`, non validé).

**Legacy, candidats à suppression** (top-level via `main.py:77-83`, tous `enabled: false`, hardcodent XBT/USDC via `settings.trading.pair`) :
- `threshold_rolling.py` (809) — `ThresholdRollingStrategy:46`, rolling seuils.
- `adaptive.py` (636) — `AdaptiveStrategy:50`, trailing par régime.
- `capitulation.py` (569) — `CapitulationStrategy:55`, RSI extrême + volume.
- `bear_short.py` (545) — `BearShortStrategy:55`, short margin Kraken.
- `trend_following.py` (605) — `TrendFollowingStrategy:55`, EMA cross (importe `indicators.ema` directement).
- `grid_spot.py` (599) — `GridSpotStrategy:59`, grille fixe ; remplacé par grid ATR v4.
- `grid_adaptive.py` (328) — `GridAdaptiveStrategy:37` hérite de `GridSpotStrategy`.
- `grok_supertrend_short_4h.py` (569) — voir ci-dessus, dépend de Kraken Futures.

## indicators/

| Module | Lignes | Rôle | Symboles clés | Attention |
|---|---|---|---|---|
| `multi_timeframe.py` | 1081 | Analyzer multi-TF par pair (lazy indicators) | `MarketRegime:76`, `MultiTimeframeAnalysis:95`, `MultiTimeframeAnalyzer:139` (`initialize:236`, `update:300`, `analyze:379`, `get_rsi:484`, `get_atr:510`, `get_adx:536`, `get_supertrend:584`, `get_ema:628`, `get_donchian:682`, `get_vwap:723`, `get_regime:748`, `get_features_dict:781`) | `pair="BTC/USDC"`, `exchange="binance"` en defaults (:239-240) ; indicateurs lazy à pré-enregistrer avant warmup |
| `multi_pair_registry.py` | 116 | Un analyzer par pair | `normalize_pair:34`, `MultiPairAnalyzerRegistry:43` (`get_or_create:60`, `get:75`, `update:79`, `initialize_all:91`) | `initialize_all` exchange default `"binance"` (:94) ; ne pas créer d'analyzer à la main |
| `atr.py` 115 · `adx.py` 229 · `ema.py` 105 · `rsi.py` 105 · `macd.py` 143 · `bollinger.py` 121 · `supertrend.py` 205 (dépend `atr`) · `donchian.py` 108 · `ichimoku.py` 136 · `vwap.py` 88 | | Indicateurs purs Decimal (`*Indicator` classes, ligne 10-31) | sans dépendance krakenbot | `Donchian` inclut la candle courante |

## scheduler/ · notifications/ · utils/ · racine

| Module | Lignes | Rôle | Symboles clés | Attention |
|---|---|---|---|---|
| `scheduler/task_scheduler.py` | 300 | APScheduler : fetch OHLC périodique | `TaskScheduler:22` (`start:73`, `_register_tasks:115`, `_fetch_ohlc_task:143`) | **`KrakenRestClient` instancié en dur (:84)**, pas via `build_exchange_rest_client` ; utilisé par `collector.py` |
| `notifications/telegram.py` | 204 | Alertes Telegram | `get_notifier:27`, `TelegramNotifier:38` (`send_trade_fill:93`, `send_crash_protector:160`, `send_daily_summary:141`) | singleton module |
| `utils/time_utils.py` | 196 | Pagination ccxt | `minutes_to_ccxt_timeframe:10`, `calculate_pagination_steps:64`, `get_max_days_for_interval:134` | |
| `main.py` | 1365 | Orchestrateur trader | `STRATEGY_REGISTRY:75-85`, `KrakenBot:89` (`setup:171`, `_setup_strategies:288`, `_register_strategy_budgets:394`, `start:512`, `stop:633`, `_reconcile_positions_with_exchange:875`, `run:985`, `_periodic_order_check:1048`), `main:1284` | importe les 7 stratégies legacy |
| `collector.py` | 410 | Collecteur WS seul (service systemd) | `DataCollector:44` (`setup:84`, `start:147`, `run:255`), `main:350` | WS via factory, REST via `TaskScheduler` (Kraken) |
| `__main__.py` | 14 | `python -m krakenbot` → `main.main` | | |

## ml/ (désactivé, `ml.enabled: false`)

`config.py` 65 (`MLSettings:30`) · `db_models.py` 324 (`MLFeatureRow:21`, `MLExternalData:282`) · `features/feature_store.py` 664 (`FeatureStore:48`, exchange default `"kraken"` :472) ·
`features/external_data.py` 185 (`ExternalDataFetcher:28`) · `inference/enhancer.py` 95 (`MLSignalEnhancer:40`) · `models/lightgbm/` (`RegimePredictor:20`, `SignalFilter:25`, `VolForecaster:20`) · `monitoring/drift.py` 71.

## scripts/

| Script | Lignes | Rôle | Symboles clés | Attention |
|---|---|---|---|---|
| `backtest.py` | 3008 | Moteur backtest signal + grid | `_load_candles_chunked:47`, `_override_pair_in_params:90`, `BacktestTrade:108`, `BacktestMetrics:122`, `BacktestEngine:187` (`__init__:194`, `load_historical_data:446`, `execute_signal:524`, `calculate_final_metrics:972`, `run:1108`, `print_report:1599`, `save_to_database:1678`), `GridBacktester:1774` (`__init__:1783`, `run:2278`), `main:2759` | `exchange` default `"kraken"` (:53, :200, :1789, :2817) → toujours passer `--exchange binance` ; doit appeler `analyzer.update()` dans la boucle |
| `run_p6_backtests.py` | 637 | 24 backtests P6 en multiprocessing + reprise | `Job:85`, `build_job_list:122`, `run_single_backtest_job:285`, `detect_n_workers:379`, `run_parallel:458`, `main:566` | statut `logs/p6_status.json` |
| `run_p6_walkforward.py` | 253 | Walk-forward fenêtres | `generate_windows:50`, `run_single_backtest:81` | |
| `filter_p6_survivors.py` 250 · `generate_p6_report.py` 322 · `p6_data_coverage.py` 202 · `p6_5_diagnose_dca.py` 287 · `p6_5_diagnose_filters.py` 300 · `compute_benchmarks.py` 254 | | Pipeline P6 (critères, rapport, couverture, diagnostics, buy&hold/DCA) | `check_criteria:39`, `compute_risk_metrics:39`, `buy_and_hold:123` | sans dépendance runtime (JSON in/out) |
| `backtest_grid.py` | 270 | Grid search paramètres (ancien) | `run_backtest_with_params:51` | |
| `binance_vision_import.py` | 335 | Import CSV Binance Vision → `market_data_ohlc` | `pair_to_binance_symbol:66`, `parse_klines_csv:104`, `import_month:155` | batch 1000 rows ; ms/µs auto ; modèle pour un import Bybit |
| `download_multipair_ohlc.py` | 378 | Download ccxt Binance multi-pair | `download_pair_interval_sync:160` | `exchange="binance"` defaults (:94,112) ; ccxt sync |
| `import_external_ohlc.py` | 403 | Fusion candles Binance sans écraser | `fetch_candles_from_binance:66`, `save_candles_preserve_existing:156` | |
| `fetch_ohlc.py` | 639 | Fetch OHLC Kraken (legacy) | `fetch_ohlc_range:162`, `fetch_ohlc_bidirectional:363` | `KrakenRestClient` + `"XBT/USDC"` ×5, exchange `"kraken"` |
| `backfill_historical_data.py` | 484 | Backfill Kraken (legacy) | `backfill_all:198` | `KrakenRestClient` en dur (:222) |
| `dashboard.py` | 3682 | Dash UI (trades, positions, backtests) | `fetch_ohlc_data:408`, `fetch_stats:494`, `run_backtest_in_thread:879`, `create_candlestick_chart:1003`, callbacks `update_*:1912-3599` | `"XBT/USDC"` ×7 (`fetch_ohlc_data:408`, `fetch_current_price:651`) ; SQL brut via `_read_sql:168` |
| `status.py` | 232 | État bot/DB en CLI | `get_status:59` | |
| `build_ml_features.py` 196 · `fetch_external_data.py` 82 | | Pipeline ML (off) | | |
| `seed_test_data.py` 143 · `test_all.py` 233 · `test_binance_connection.py` 105 · `test_binance_ws.py` 106 · `test_kraken_futures_demo.py` 93 | | Smoke tests manuels | | `seed_test_data` insère `exchange="kraken"` (:74) |
| `backup_db.sh` · `restore_db.sh` | | Dump/restore Postgres (serveur) | | |

## Points d'attention transverses

1. **Defaults `"kraken"`** encore présents : `settings.exchange_name:687`, `OHLCData.exchange:65`, `backtest.py` (4×), `fetch_ohlc.py`, `feature_store.py:472`. Le runtime tourne sur Binance uniquement grâce à `EXCHANGE_NAME=binance` dans `.env`.
2. **Kraken en dur hors connecteur** : `scheduler/task_scheduler.py:84` (instancie `KrakenRestClient`), `execution/order_manager.py:28` et `execution/risk.py:35` (`normalize_asset_*`), `engine.py:82` (type hint), scripts `fetch_ohlc.py` / `backfill_historical_data.py`.
3. **`XBT/USDC`** : `settings.trading.pair:196`, `ScheduledTasksSettings:355`, `dashboard.py` (7), `fetch_ohlc.py` (5), `kraken/ws.py:74-75` ; les stratégies actives utilisent `self.pair`.
4. **Registres statiques** : `main.STRATEGY_REGISTRY:75-85` et `multi_strategy_router._INNER_STRATEGY_CLASSES:54` — une stratégie non listée est ignorée même si présente dans `strategies.yaml`.
5. **Fichiers > 1 000 lignes** à ne pas toucher sans review : `kraken/rest.py`, `binance/rest.py`, `kraken/ws.py`, `main.py`, `multi_timeframe.py`, `backtest.py`, `dashboard.py`.
