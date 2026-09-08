# CODE_MAP — où est quoi dans KrakenBot

> Généré le 2026-09-08 sur `v2.1.0-p6-7-multiprocessing-19-gcb0e3d8` (branche `feat/b05-docs-cleanup`, base `dev`), post-B0.5.
> Commande : `wc -l` + `grep -n -E "^(class |def |async def )|^    (async )?def [a-z]"` + `grep -n "^from krakenbot"` sur `src/krakenbot/**/*.py` et `scripts/*.py`.
> À régénérer à chaque merge sur `dev`. Numéros de ligne = `symbole:ligne`. Hors tests, hors `scripts/audit/`.
> Total : src 25 496 lignes (ml inclus ; 31 649 avant B0.5), scripts 13 727 lignes (P7 inclus, `backtest_grid.py` / `backfill_historical_data.py` / `test_kraken_futures_demo.py` supprimés).

## Flux runtime en 5 lignes

`__main__.py` → `main.KrakenBot` (setup:156, start:480, run:914) instancie settings, DB, EventBus, REST/WS via `connectors/exchange.py`
(dispatch sur `settings.exchange_name` : `binance` / Kraken aujourd'hui, `bybit` en B1), `MultiStrategyRouter` (seule stratégie top-level
depuis B0.5), `ExecutionEngine`, `OrderManager`, `GlobalRiskManager`, `MultiPairAnalyzerRegistry`.
WS publie `MARKET_OHLC` → router `_handle_ohlc:275` → stratégie interne `on_ohlc`/`generate_signal` → `GeminiGlobalRiskManager.process_signal:321`
→ `TRADE_SIGNAL` → `ExecutionEngine._handle_signal:155` → REST (`place_limit_order`/`place_market_order`) → `TRADE_ORDER_FILLED`
→ router `_handle_trade_filled:612` → stratégie source via `bot_id`. Le collector (`collector.py`) est le même WS sans trading.

## config/

| Module | Lignes | Rôle | Symboles clés | Attention |
|---|---|---|---|---|
| `settings.py` | 792 | Pydantic settings (env + `strategies.yaml`) | `KrakenSettings:43`, `BinanceSettings:84`, `DatabaseSettings:123`, `RiskManagementSettings:150`, `TradingSettings:186`, `MultiStrategySettings:390` (`enabled` default False, forcé True par `strategies.yaml`), `ExchangeFees:444` (`kraken_defaults:455`, `binance_defaults:460` ; `bybit_defaults` à écrire en B1), `OrderSettings:502`, `_validate_router_runtime_alignment:561`, `Settings:610`, `get_settings:765`, `reload_settings:782` | **`exchange_name` default `"kraken"` (:639)** — dette B1 (incident 7 sept) ; `trading.pair` default `"XBT/USDC"` (:196) ; `ScheduledTasksSettings` pairs default `["XBT/USDC","XBT/EUR"]` (:355) ; `CapitulationSettings` / `KrakenFuturesSettings` supprimées en B0.5 ; importe `strategies.multi_strategy_router` (couplage config→stratégies) |

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
| `binance/rest.py` | 1486 | REST Binance via ccxt + paper | `MIN_ORDER_SIZE:58`, `MIN_NOTIONAL:65`, `BinanceRestClient:68` (`get_balance:182`, `fetch_ohlcv:269`, `place_market_order:521`, `place_limit_order:824`, `get_order_status:1096`, `cancel_order:1166`, `initialize_paper_balance:1265`) | LOT_SIZE hardcodés BTC/ETH/SOL ; `place_margin_order:1237` = stub |
| `binance/ws.py` | 844 | WS Binance (kline/ticker) | `INTERVAL_MAP`/`BINANCE_INTERVAL_MAP:63`, `_pair_to_symbol:73`, `BinanceWebSocketClient:93` (`connect:148`, `subscribe_ohlc:217`, `_handle_kline:399`, `_data_flow_watchdog:560`, `_preventive_reconnect_timer:606`) | timestamp DB = `T + 1 ms` (:423) ; `exchange="binance"` hardcodé (:450) ; reconnect 23 h |
| `kraken/rest.py` | 1930 | REST Kraken (legacy, référence paper) | `normalize_asset_symbol:86`, `normalize_asset_balances:91`, `KrakenRestClient:100` (`place_market_order:327`, `place_margin_order:654`, `place_limit_order:1130`, `get_order_status:1433`, `fetch_ohlcv:1605`) | `normalize_asset_*` importés par `execution/order_manager.py:28` et `execution/risk.py:35` |
| `kraken/ws.py` | 1131 | WS Kraken v1 | `KrakenWebSocketClient:81` (`subscribe_ohlc:931`, `subscribe_trades:1011`, `ping:1124`) | map `BTC/USDC→XBT/USDC` (:74-75) ; `exchange="kraken"` (:645,669) |
| `bybit/` | — | **À créer en B1/B2** (`rest.py`, `ws.py`, clones des modules Binance) | voir `skills/bybit.md` | `hostname="bybit.eu"`, `load_markets()` obligatoire, market BUY sans `price` |

`kraken/futures.py` et `base_perps.py` (Kraken Futures) ont été supprimés en B0.5.

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

Statuts « actif » ci-dessus = configuration `strategies.yaml` ; en pratique rien ne tourne (services stoppés depuis le 7 sept 2026) et tout est revalidé en B4 avec les fees Bybit.

Supprimées en B0.5 (plus aucun fichier ni entrée `strategies.yaml`) : les 7 stratégies legacy top-level Kraken-era (`threshold_rolling`,
`adaptive`, `capitulation`, `bear_short`, `trend_following`, `grid_spot`, `grid_adaptive`) et les 3 stratégies hors registre
(`grok_ichimoku_cloud_4h`, `grok_vwap_trend_4h`, `grok_supertrend_short_4h`). `indicators/ichimoku.py` et `vwap.py` sont conservés
(analyzer + ML feature store).

## indicators/

| Module | Lignes | Rôle | Symboles clés | Attention |
|---|---|---|---|---|
| `multi_timeframe.py` | 1081 | Analyzer multi-TF par pair (lazy indicators) | `MarketRegime:76`, `MultiTimeframeAnalysis:95`, `MultiTimeframeAnalyzer:139` (`initialize:236`, `update:300`, `analyze:379`, `get_rsi:484`, `get_atr:510`, `get_adx:536`, `get_supertrend:584`, `get_ema:628`, `get_donchian:682`, `get_vwap:723`, `get_regime:748`, `get_features_dict:781`) | `pair="BTC/USDC"`, `exchange="binance"` en defaults (:239-240) ; indicateurs lazy à pré-enregistrer avant warmup |
| `multi_pair_registry.py` | 116 | Un analyzer par pair | `normalize_pair:34`, `MultiPairAnalyzerRegistry:43` (`get_or_create:60`, `get:75`, `update:79`, `initialize_all:91`) | `initialize_all` exchange default `"binance"` (:94) ; ne pas créer d'analyzer à la main |
| `atr.py` 115 · `adx.py` 229 · `ema.py` 105 · `rsi.py` 105 · `macd.py` 143 · `bollinger.py` 121 · `supertrend.py` 205 (dépend `atr`) · `donchian.py` 108 · `ichimoku.py` 136 · `vwap.py` 88 | | Indicateurs purs Decimal (`*Indicator` classes, ligne 10-31) | sans dépendance krakenbot | `Donchian` inclut la candle courante |

## scheduler/ · notifications/ · utils/ · racine

| Module | Lignes | Rôle | Symboles clés | Attention |
|---|---|---|---|---|
| `scheduler/task_scheduler.py` | 300 | APScheduler : fetch OHLC périodique | `TaskScheduler:22` (`start:73`, `_register_tasks:115`, `_fetch_ohlc_task:143`) | **`KrakenRestClient` instancié en dur (:84)**, pas via `build_exchange_rest_client` ; importe `scripts.fetch_ohlc` depuis `src/` (:174) ; utilisé par `collector.py` — dette B3 |
| `notifications/telegram.py` | 204 | Alertes Telegram | `get_notifier:27`, `TelegramNotifier:38` (`send_trade_fill:93`, `send_crash_protector:160`, `send_daily_summary:141`) | singleton module |
| `utils/time_utils.py` | 196 | Pagination ccxt | `minutes_to_ccxt_timeframe:10`, `calculate_pagination_steps:64`, `get_max_days_for_interval:134` | |
| `main.py` | 1260 | Orchestrateur trader | `STRATEGY_REGISTRY:71` (router uniquement), `KrakenBot:76` (`setup:156`, `_setup_strategies:259`, `_collect_strategy_pairs:335`, `_register_strategy_budgets:362`, `_get_multi_strategy_ohlc_intervals:459`, `start:480`, `stop:585`, `_reconcile_positions_with_exchange:804`, `run:914`, `_periodic_order_check:977`, `_log_stats:999`), `main:1179` | mode legacy mono-stratégie supprimé : `multi_strategy.enabled=false` → `ValueError` dans `_setup_strategies` |
| `collector.py` | 410 | Collecteur WS seul (service systemd) | `DataCollector:44` (`setup:84`, `start:147`, `run:255`), `main:350` | WS via factory, REST via `TaskScheduler` (Kraken) |
| `__main__.py` | 14 | `python -m krakenbot` → `main.main` | | |

## ml/ (désactivé, `ml.enabled: false`)

`config.py` 65 (`MLSettings:30`) · `db_models.py` 324 (`MLFeatureRow:21`, `MLExternalData:282`) · `features/feature_store.py` 664 (`FeatureStore:48`, exchange default `"kraken"` :472) ·
`features/external_data.py` 185 (`ExternalDataFetcher:28`) · `inference/enhancer.py` 95 (`MLSignalEnhancer:40`) · `models/lightgbm/` (`RegimePredictor:20`, `SignalFilter:25`, `VolForecaster:20`) · `monitoring/drift.py` 71.

## scripts/

| Script | Lignes | Rôle | Symboles clés | Attention |
|---|---|---|---|---|
| `backtest.py` | 2793 | Moteur backtest signal + grid | `_override_pair_in_params:90`, `BacktestTrade:108`, `BacktestMetrics:122`, `BacktestEngine:187` (`__init__:194`, `_apply_params_override:250`, `_build_replay_sequence:354`, `load_historical_data:461`, `execute_signal:539`, `calculate_final_metrics:966`, `run:1102`, `print_report:1436`, `save_to_database:1515`), `GridBacktester:1611` (`GRID_STRATEGIES:1618`, `__init__:1620`, `_create_grok_grid_strategy:1784`, `run:2109`), `main:2544` | `exchange` default `"kraken"` (:53, :200, :1626, :2602) → toujours passer `--exchange binance` ; **fees flat** (`binance_defaults` :228/:1646, `ExchangeFees()` nu :230/:1648) — dette B4 ; chemin `is_multi` mort ; doit appeler `analyzer.update()` dans la boucle |
| `run_p6_backtests.py` | 637 | 24 backtests P6 en multiprocessing + reprise | `Job:85`, `build_job_list:122`, `run_single_backtest_job:285`, `detect_n_workers:379`, `run_parallel:458`, `main:566` | statut `logs/p6_status.json` |
| `run_p6_walkforward.py` | 253 | Walk-forward fenêtres | `generate_windows:50`, `run_single_backtest:81` | |
| `filter_p6_survivors.py` 250 · `generate_p6_report.py` 322 · `p6_data_coverage.py` 202 · `p6_5_diagnose_dca.py` 287 · `p6_5_diagnose_filters.py` 300 · `compute_benchmarks.py` 254 | | Pipeline P6 (critères, rapport, couverture, diagnostics, buy&hold/DCA) | `check_criteria:39`, `compute_risk_metrics:39`, `buy_and_hold:123` | sans dépendance runtime (JSON in/out) |
| `run_p7_grid_search.py` | 917 | Grid search P7 (phase 1 cross-validate, phase 2 walk-forward, report) | `P7Job:108`, `WalkForwardWindow:209`, `select_top_k_per_combo:269`, `StatusState:415`, `run_parallel:642`, `main:822` | sorties `results/P7_phase1_cross_validate.json` / `P7_phase2_walk_forward.json`, statut `logs/p7_status.json` |
| `p7_grids.py` 120 · `p7_report.py` 607 | | Grilles P7 (4 stratégies, noms réels des kwargs) · agrégation walk-forward + 7 critères + markdown | `expand_grid:90` · `WalkForwardAggregate:65`, `aggregate_walk_forward:125`, `ConfigVerdict:225`, `generate_report:440` | rapport `results/P7_optimization_report.md` (non généré) |
| `binance_vision_import.py` | 335 | Import CSV Binance Vision → `market_data_ohlc` | `pair_to_binance_symbol:66`, `parse_klines_csv:104`, `import_month:155` | batch 1000 rows ; ms/µs auto ; modèle pour un import Bybit |
| `download_multipair_ohlc.py` | 378 | Download ccxt Binance multi-pair | `download_pair_interval_sync:160` | `exchange="binance"` defaults (:94,112) ; ccxt sync |
| `import_external_ohlc.py` | 403 | Fusion candles Binance sans écraser | `fetch_candles_from_binance:66`, `save_candles_preserve_existing:156` | |
| `fetch_ohlc.py` | 639 | Fetch OHLC Kraken (legacy) | `fetch_ohlc_range:162`, `fetch_ohlc_bidirectional:363` | `KrakenRestClient` + `"XBT/USDC"` ×5, exchange `"kraken"` ; **non supprimable** : importé par `scheduler/task_scheduler.py:174` et `backfill_binance_gap.py` (dette B3) |
| `backfill_binance_gap.py` | 255 | Comble un gap Binance via l'API REST publique | `main:249` | dépend de `fetch_ohlc.py` (`get_last_timestamp`, `save_ohlc_batch`) ; usage limité tant que `api.binance.com` répond depuis l'UE |
| `dashboard.py` | 3677 | Dash UI (trades, positions, backtests) | `fetch_ohlc_data:403`, `fetch_stats:489`, `run_backtest_in_thread:874`, `create_candlestick_chart:998`, callbacks `update_*:1907-3385` | `"XBT/USDC"` ×7 (`fetch_ohlc_data:403`, `fetch_current_price:646`) ; SQL brut via `_read_sql:163` ; dropdown backtest construit depuis `strategies.yaml` |
| `status.py` | 232 | État bot/DB en CLI | `get_status:59` | |
| `build_ml_features.py` 196 · `fetch_external_data.py` 82 | | Pipeline ML (off) | | |
| `seed_test_data.py` 143 · `test_all.py` 233 · `test_binance_connection.py` 105 · `test_binance_ws.py` 106 | | Smoke tests manuels | | `seed_test_data` insère `exchange="kraken"` (:74) |
| `audit/bybit_common.py` · `audit/bybit_q1_endpoints.py` … `bybit_q8_price_diff.py` | | Audit B0 Bybit EU (lecture seule, hors comptage) | | `bybit_q1/q6/q7` à relancer avec les clés API (B1) |
| `backup_db.sh` · `restore_db.sh` | | Dump/restore Postgres (serveur) | | |

## Points d'attention transverses

1. **Defaults `"kraken"`** encore présents : `settings.exchange_name:639`, `OHLCData.exchange:65`, `backtest.py` (4×), `fetch_ohlc.py`, `feature_store.py:472`. Sans `EXCHANGE_NAME` dans le `.env`, le runtime part sur Kraken (incident du 7 sept 2026) — dette B1. Cible : `bybit`.
2. **Kraken en dur hors connecteur** : `scheduler/task_scheduler.py:84` (instancie `KrakenRestClient`) + import de `scripts.fetch_ohlc` (:174), `execution/order_manager.py:28` et `execution/risk.py:35` (`normalize_asset_*`), `engine.py:82` (type hint), script `fetch_ohlc.py`.
3. **`XBT/USDC`** : `settings.trading.pair:196`, `ScheduledTasksSettings:355`, `dashboard.py` (7), `fetch_ohlc.py` (5), `kraken/ws.py:74-75` ; les stratégies utilisent `self.pair`.
4. **Registres statiques** : `main.STRATEGY_REGISTRY:71` (router seul) et `multi_strategy_router._INNER_STRATEGY_CLASSES:54` — une stratégie non listée est ignorée même si présente dans `strategies.yaml`.
5. **Fees de backtest flat** (`backtest.py` :228/:1646) : maker = taker ; B4 exige maker 0.10 % / taker 0.25 % distincts (`skills/backtest.md`).
6. **Defaults `exchange="binance"`** dans `multi_timeframe.py:240` et `multi_pair_registry.py:94` (warmup) → `settings.exchange_name` en B3.
7. **Fichiers > 1 000 lignes** à ne pas toucher sans review : `kraken/rest.py`, `binance/rest.py`, `kraken/ws.py`, `main.py`, `multi_timeframe.py`, `backtest.py`, `dashboard.py`.
