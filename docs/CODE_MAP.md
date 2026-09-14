# CODE_MAP — où est quoi dans KrakenBot

> Régénéré le 2026-09-14 après le merge B4.2 (`dev` @ `3406a6c`, tag `v2.7.0-b4-2-fees-engine` sur le commit de régénération). Génération précédente : 2026-09-13 (post-B4.1, `dev` @ `c67daeb`, tag `v2.6.0-b4-1-binance-restamp` @ `d3d3423`).
> **B4.2 (mergé le 2026-09-14, `3406a6c`)** : `config/settings.py` (+`FEE_MODEL_NAMES`, `ExchangeFees.from_name`, docstrings) est le seul changement de `src/` ; `scripts/backtest.py` (−255 lignes de chemins morts, `--fees` obligatoire, `fee_model` requis, champs d'audit de `BacktestTrade`, `PairCosts`, `--trades-out`, parser module), `run_p6_backtests.py`, `run_p7_grid_search.py`, `run_p6_walkforward.py` (nouvelle CLI), `binance_vision_import.py` (`.env` dans `main()`), `dashboard.py` (`DASHBOARD_FEE_MODEL`), nouveau `scripts/audit/b4_2_reference_capture.py` (hors comptage) ; `tests/conftest.py` (purge credentials + boucle d'événements de session). Lignes des 7 modules touchés régénérées ci-dessous, les autres modules sont inchangés.
> **B4.1 (mergé le 2026-09-13, `c67daeb`)** : `src/` ne change que par des docstrings (`models/market_data.py` commentaire `timestamp` = fin de période, `data/backfill.py`, `connectors/exchange.py`) ; révision Alembic `b4c0ffee0001` (`COMMENT ON COLUMN` seul, appliquée sur le serveur) ; `scripts/binance_vision_import.py:parse_klines_csv` écrit `open_time + interval` ; nouveaux `scripts/audit/b4_stamp_lib.py`, `b4_timestamp_audit.py`, `b4_restamp_binance.py` (hors comptage, voir `results/B4_1_timestamp_restamp_report.md`). Lignes des 4 fichiers touchés régénérées ci-dessous, les autres modules sont inchangés.
> Depuis la génération post-B2 ont changé : `data/backfill.py` (nouveau), `scheduler/task_scheduler.py`, `collector.py`, `connectors/exchange.py`, `connectors/bybit/rest.py`, `core/event_bus.py`, `config/settings.py`, `indicators/multi_timeframe.py`, `multi_pair_registry.py`, `utils/time_utils.py`, `connectors/{bybit,binance}/ws.py` (1 kwarg de log), scripts `bybit_kline_import.py` + `backfill_gap.py` (nouveaux), `fetch_ohlc.py` + `backfill_binance_gap.py` (supprimés)
> (`git diff --stat v2.4.0-b2-bybit-ws..HEAD -- src scripts`) : leurs lignes sont à jour, les autres modules sont inchangés.
> Commande : `wc -l` + `grep -n -E "^(class |def |async def )|^    (async )?def [a-z]"` + `grep -n "^from krakenbot"` sur `src/krakenbot/**/*.py` et `scripts/*.py`.
> À régénérer à chaque merge sur `dev`. Numéros de ligne = `symbole:ligne`. Hors tests, hors `scripts/audit/`.
> Total : src 28 884 lignes (ml inclus ; 28 853 post-B4.1, +31 en B4.2 = registre `from_name` + docstrings), scripts 13 603 lignes (P7 inclus ; 13 358 post-B4.1, +245 en B4.2 : CLI `--fees`/`--trades-out`/`--pair-costs-file`, reprise `FeeModelMismatchError`, walk-forward CLI ; chemins morts −255).

## Flux runtime en 5 lignes

`__main__.py` → `main.KrakenBot` (setup:156, start:480, run:914) instancie settings, DB, EventBus, REST/WS via `connectors/exchange.py`
(dispatch sur `settings.exchange_name`, **obligatoire** depuis B1 : `bybit` / `binance` / Kraken ; WS Bybit en B2), `MultiStrategyRouter` (seule stratégie top-level
depuis B0.5), `ExecutionEngine`, `OrderManager`, `GlobalRiskManager`, `MultiPairAnalyzerRegistry`.
WS publie `MARKET_OHLC` → router `_handle_ohlc:275` → stratégie interne `on_ohlc`/`generate_signal` → `GeminiGlobalRiskManager.process_signal:321`
→ `TRADE_SIGNAL` → `ExecutionEngine._handle_signal:155` → REST (`place_limit_order`/`place_market_order`) → `TRADE_ORDER_FILLED`
→ router `_handle_trade_filled:612` → stratégie source via `bot_id`. Le collector (`collector.py`) est le même WS sans trading.

## config/

| Module | Lignes | Rôle | Symboles clés | Attention |
|---|---|---|---|---|
| `settings.py` | 979 | Pydantic settings (env + `strategies.yaml`) | `KrakenSettings:43`, `BinanceSettings:84`, `BybitSettings:126` (`credentials:229` — `readonly` = `BYBIT_*`, `trade` = `BYBIT_TRADE_*` ; `ws_url:66`, `ws_ping_interval_seconds`, `ws_pong_timeout_seconds`, `ws_watchdog_warn/zombie_seconds`, `ws_watchdog_resubscribe_alert_count`, `_validate_watchdog_thresholds:214`), `DatabaseSettings:252`, `RiskManagementSettings:279`, `TradingSettings:315`, `ScheduledTasksSettings:455`, `MultiStrategySettings:525` (`enabled` default False, forcé True par `strategies.yaml`), `FEE_MODEL_NAMES:580`, `ExchangeFees:583` (`kraken_defaults:600`, `binance_defaults:605`, `bybit_defaults:611`, **`from_name:621` = registre `--fees` (B4.2)**), `OrderSettings:675`, `_validate_router_runtime_alignment:734`, `Settings:783` (`exchange_fees:835` = fees live/paper des connecteurs, jamais lu par le backtest), `get_settings:951`, `reload_settings:969` | **`exchange_name` obligatoire** (`Literal[kraken\|binance\|bybit]`, sans default — dette B1 réglée) ; `validate_all` exige `BYBIT_TRADE_*` en live Bybit ; `trading.pair` default `"XBT/USDC"` (:324) ; `ScheduledTasksSettings.pairs` default `["BTC/USDC","ETH/USDC","SOL/USDC"]` (B2), `intervals` default 7 TF ; importe `strategies.multi_strategy_router` (couplage config→stratégies) ; `ScheduledTasksSettings` : cron défaut `30 3 * * *`, `backfill_days` = fenêtre de scan des gaps (défaut 3) (B3) |

## core/

| Module | Lignes | Rôle | Symboles clés | Dépendances |
|---|---|---|---|---|
| `event_bus.py` | 514 | Pub/sub async central | `EventType:55` (+ `SCHEDULER_TASK_SUCCESS/FAILED`, B3), `Event:83`, `EventBus:109` (`subscribe:155`, `publish:236`, `publish_and_wait:321`, `get_history:444`), `get_event_bus:489` | appelé par tout le runtime |
| `database.py` | 373 | Engine SQLAlchemy async + TimescaleDB | `Base:34`, `DatabaseManager:44` (`init_db:98`, `session:179`, `read_session:204`, `create_hypertable:231`), `get_db_manager:298`, `init_db:310`, `get_session:334` | `config.settings` |
| `exceptions.py` | 516 | Hiérarchie d'erreurs | `KrakenBotError:33`, `KrakenAPIError:78`, `RateLimitError:113`, `WebSocketError:147`, `InsufficientBalanceError:255`, `RiskLimitExceededError:291`, `OrderExecutionError:327`, `OrderCancelError:368` | noms « Kraken » réutilisés par Binance |
| `logger.py` | 297 | structlog + masquage secrets | `mask_secrets:50`, `configure_logging:156`, `get_logger:237`, `bind_context:254` | `config.settings` |

## models/

| Module | Lignes | Rôle | Symboles clés | Attention |
|---|---|---|---|---|
| `base.py` | 172 | Enums partagés | `TradeSide:55`, `TradeStatus:67`, `BotStatus:87`, `SignalType:105`, `PositionStatus:119`, `OrderType:133`, `OrderStatus:145`, `TradingMode:163` | `TradingMode` dupliqué dans `config/settings.py:26` |
| `market_data.py` | 255 | Hypertables OHLC/ticks | `OHLCData:20`, `TickData:169` | colonne `exchange` default/server_default `"kraken"` (:67-68) ; PK (timestamp, pair, interval, exchange) ; `timestamp` = **fin de période** (`open_time + interval`, commentaire B4.1) |
| `trades.py` | 819 | Tables trading | `Trade:31`, `BotState:208`, `OpenPosition:387`, `BacktestRun:567`, `PaperBalance:764`, `utc_now:22` | |
| `orders.py` | 216 | Ordres LIMIT suivis | `Order:26` | |
| `scheduled_tasks.py` | 107 | Log du scheduler | `TaskExecutionLog:17` | |

## connectors/

| Module | Lignes | Rôle | Symboles clés | Dépendances / attention |
|---|---|---|---|---|
| `exchange.py` | 218 | Protocol + factories | `ExchangeRestClient:26` (Protocol), `build_exchange_rest_client:145` (kwarg `read_only` → Bybit `key_role="readonly"`), `build_exchange_ws_client:183` | dispatch sur `settings.exchange_name` (`binance`, `bybit`:144, sinon Kraken) ; WS `bybit` → `BybitWebSocketClient` (:168, B2) ; appelé par `main.py`, `collector.py`, `order_manager.py` ; le Protocol ne reflète pas les signatures réelles (`signal_price` vs `reference_price`) — dette n°7 ; docstring `fetch_ohlcv:95` = contrat de timestamp (end-stamped **Bybit seulement**, B3) |
| `base_ws.py` | 107 | ABC WebSocket | `BaseWebSocketClient:25` (`connect:90`, `subscribe_ohlc:98`, `subscribe_ticker:102`) | |
| `binance/rest.py` | 1486 | REST Binance via ccxt + paper | `MIN_ORDER_SIZE:58`, `MIN_NOTIONAL:65`, `BinanceRestClient:68` (`get_balance:182`, `fetch_ohlcv:269`, `place_market_order:521`, `place_limit_order:824`, `get_order_status:1096`, `cancel_order:1166`, `initialize_paper_balance:1265`) | LOT_SIZE hardcodés BTC/ETH/SOL ; `place_margin_order:1237` = stub |
| `binance/ws.py` | 844 | WS Binance (kline/ticker) | `INTERVAL_MAP`/`BINANCE_INTERVAL_MAP:63`, `_pair_to_symbol:73`, `BinanceWebSocketClient:93` (`connect:148`, `subscribe_ohlc:217`, `_handle_kline:399`, `_data_flow_watchdog:560`, `_preventive_reconnect_timer:606`) | timestamp DB = `T + 1 ms` (:423) ; `exchange="binance"` hardcodé (:450) ; reconnect 23 h ; log `candle_timestamp` (B3) |
| `kraken/rest.py` | 1930 | REST Kraken (legacy, référence paper) | `normalize_asset_symbol:86`, `normalize_asset_balances:91`, `KrakenRestClient:100` (`place_market_order:327`, `place_margin_order:654`, `place_limit_order:1130`, `get_order_status:1433`, `fetch_ohlcv:1605`) | `normalize_asset_*` importés par `execution/order_manager.py:28` et `execution/risk.py:35` |
| `kraken/ws.py` | 1131 | WS Kraken v1 | `KrakenWebSocketClient:81` (`subscribe_ohlc:931`, `subscribe_trades:1011`, `ping:1124`) | map `BTC/USDC→XBT/USDC` (:74-75) ; `exchange="kraken"` (:645,669) |
| `bybit/rest.py` | 1628 | REST Bybit EU via ccxt + paper (B1) | `MIN_ORDER_SIZE:67`, `TICK_SIZE:73`, `MIN_NOTIONAL:82`, `BybitRestClient:105` (`load_markets:257`, `_round_amount:308`, `_round_price:313`, `_translate_error:341`, `get_balance:446`, `fetch_ohlcv:517`, `place_market_order:674`, `_live_market_order:828`, `place_limit_order:944`, `_rejected_post_only_order:1108`, `_live_limit_order:1154`, `get_order_status:1293`, `cancel_order:1342`) | `hostname="bybit.eu"`, `key_role` readonly/trade, `load_markets()` lazy, market BUY sans `price` (`quote_amount` → `cost`), PostOnly par défaut + rejet normalisé (`signal_metadata.reject_reason`), `fetch_order(params.acknowledged=True)`, mapping `retCode` ; validé en live le 9 sept (`skills/bybit.md`) ; **B3 : `fetch_ohlcv` via l'endpoint brut `publicGetV5MarketKline` — `timestamp = start + interval`, `vwap = turnover/volume`, candle en cours exclue** |
| `bybit/ws.py` | 1014 | WS Bybit EU public spot v5 (B2) | `INTERVAL_MAP`/`BYBIT_INTERVAL_MAP`, `MAX_ARGS_PER_REQUEST`, `_pair_to_symbol:97`, `_symbol_to_pair:102`, `BybitWebSocketClient:126` (`connect:202`, `subscribe_ohlc:264`, `_resubscribe_all:319`, `_handle_message:395`, `_handle_control_message:435`, `_handle_kline:460`, `_handle_ticker:546`, `_save_ohlc:581`, `_ping_loop:605`, `_data_flow_watchdog:662`, `_handle_stale_flow:731`, `_preventive_reconnect_timer:766`, `_reconnect:787`, `_cleanup:965`) | timestamp DB = `end + 1 ms` ; log `candle_timestamp` (B3) ; `exchange="bybit"` hardcodé ; `vwap = turnover/volume` ; ping applicatif 20 s / pong 10 s = zombie connexion ; watchdog flux agrégé 2 paliers (`BybitSettings.ws_watchdog_*`) + escalade Telegram ; subscribe par lots de 10 ; reconnect 23 h ; `MARKET_TICK` avec `price` (clé lue par les stratégies) et `bid`/`ask` None |

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
| `multi_timeframe.py` | 1083 | Analyzer multi-TF par pair (lazy indicators) | `MarketRegime:76`, `MultiTimeframeAnalysis:95`, `MultiTimeframeAnalyzer:139` (`initialize:236`, `update:300`, `analyze:379`, `get_rsi:484`, `get_atr:510`, `get_adx:536`, `get_supertrend:584`, `get_ema:628`, `get_donchian:682`, `get_vwap:723`, `get_regime:748`, `get_features_dict:781`) | `pair="BTC/USDC"`, `exchange="binance"` en defaults (:239-240) ; indicateurs lazy à pré-enregistrer avant warmup ; `initialize:236` : `pair` et `exchange` **obligatoires** (B3, plus de default `binance`) |
| `multi_pair_registry.py` | 117 | Un analyzer par pair | `normalize_pair:34`, `MultiPairAnalyzerRegistry:43` (`get_or_create:60`, `get:75`, `update:79`, `initialize_all:91`) | `initialize_all` exchange default `"binance"` (:94) ; ne pas créer d'analyzer à la main ; `initialize_all:91` : `exchange` obligatoire (B3) |
| `atr.py` 115 · `adx.py` 229 · `ema.py` 105 · `rsi.py` 105 · `macd.py` 143 · `bollinger.py` 121 · `supertrend.py` 205 (dépend `atr`) · `donchian.py` 108 · `ichimoku.py` 136 · `vwap.py` 88 | | Indicateurs purs Decimal (`*Indicator` classes, ligne 10-31) | sans dépendance krakenbot | `Donchian` inclut la candle courante |

## data/ · scheduler/ · notifications/ · utils/ · racine

| Module | Lignes | Rôle | Symboles clés | Attention |
|---|---|---|---|---|
| `data/backfill.py` | 505 | Détection + comblement de gaps OHLC, exchange-agnostic (B3) | `Gap:98`, `GapResult:117`, `BackfillSummary`, `floor_to_grid:172` (1w ancré lundi), `is_grid_aligned:183`, `last_closed_timestamp:189`, `internal_gaps_from_rows:194`, `tail_gap:206`, `candle_to_row:231`, `fetch_timestamp_bounds:253`, `fetch_max_timestamps:275`, `detect_gaps:286`, `insert_candles:333`, `fill_gap:360`, `backfill_gaps:445` | convention DB = fin de période ; query LAG + `MAX(timestamp)` ; `ON CONFLICT DO NOTHING` batch 1000 ; **garanti pour Bybit seulement** (voir docstring) ; aucun littéral exchange |
| `scheduler/task_scheduler.py` | 250 | APScheduler : backfill de gaps périodique (B3) | `JOB_ID`, `TaskScheduler:43` (`start:85`, `stop:113`, `run_backfill:120`, `_write_logs`) | client REST **injecté** par le collector (read-only), job unique `gap_backfill` (`SCHEDULER_DAILY_BACKFILL_CRON`, défaut 03:30 UTC), `backfill_gaps` sur `settings.exchange_name` avec `lookback=backfill_days` ; 1 row `TaskExecutionLog` par gap + 1 row de run (`pair='*'`) ; events `SCHEDULER_TASK_*` ; aucun import de `scripts/` |
| `notifications/telegram.py` | 204 | Alertes Telegram | `get_notifier:27`, `TelegramNotifier:38` (`send_trade_fill:93`, `send_crash_protector:160`, `send_daily_summary:141`) | singleton module |
| `utils/time_utils.py` | 201 | Pagination ccxt | `minutes_to_ccxt_timeframe:10`, `calculate_pagination_steps:64`, `get_max_days_for_interval:134`, `ms_to_datetime:199` (B3) | |
| `main.py` | 1260 | Orchestrateur trader | `STRATEGY_REGISTRY:71` (router uniquement), `KrakenBot:76` (`setup:156`, `_setup_strategies:259`, `_collect_strategy_pairs:335`, `_register_strategy_budgets:362`, `_get_multi_strategy_ohlc_intervals:459`, `start:480`, `stop:585`, `_reconcile_positions_with_exchange:804`, `run:914`, `_periodic_order_check:977`, `_log_stats:999`), `main:1179` | mode legacy mono-stratégie supprimé : `multi_strategy.enabled=false` → `ValueError` dans `_setup_strategies` |
| `collector.py` | 417 | Collecteur WS + scheduler (service systemd) | `DataCollector:45` (`setup:85`, `start:154`, `run:262`), `main:357` | WS via factory ; TF depuis `settings.scheduler.intervals` (B2) ; REST client via factory **`read_only=True`**, prêté au `TaskScheduler` instancié pour tout exchange si `SCHEDULER_ENABLED` (B3, garde kraken-only supprimée) ; ferme le client au stop |
| `__main__.py` | 14 | `python -m krakenbot` → `main.main` | | |

## ml/ (désactivé, `ml.enabled: false`)

`config.py` 65 (`MLSettings:30`) · `db_models.py` 324 (`MLFeatureRow:21`, `MLExternalData:282`) · `features/feature_store.py` 664 (`FeatureStore:48`, exchange default `"kraken"` :472) ·
`features/external_data.py` 185 (`ExternalDataFetcher:28`) · `inference/enhancer.py` 95 (`MLSignalEnhancer:40`) · `models/lightgbm/` (`RegimePredictor:20`, `SignalFilter:25`, `VolForecaster:20`) · `monitoring/drift.py` 71.

## scripts/

| Script | Lignes | Rôle | Symboles clés | Attention |
|---|---|---|---|---|
| `backtest.py` | 2878 | Moteur backtest signal + grid | `_override_pair_in_params:90`, `PairCosts:108`, `load_pair_costs:119`, `resolve_fee_model:141`, `BacktestTrade:160` (champs d'audit `liquidity`/`fee_rate`/`fee_base_usdc`/`reference_price`/`spread_pct`/`slippage_pct`), `BacktestMetrics:181`, `BacktestEngine:246` (`__init__:253`, `_apply_params_override:314`, `_build_replay_sequence:418`, `load_historical_data:525`, `_resolve_fill:567`, `_costs_for_pair:596`, `execute_signal:603`, `calculate_final_metrics:845`, `run:981`, `print_report:1327`, `save_to_database:1406`), `GridBacktester:1502` (`GRID_STRATEGIES:1509`, `__init__:1511`, `_create_grok_grid_strategy:1666`, `_force_close_open_positions:2161`, `run:1999`, `print_report:2360`, `save_to_database:2413`), `build_parser:2451`, `parse_args:2556`, `dump_trades_json:2580`, `main:2672` | **`--fees {bybit,binance,kraken}` obligatoire (B4.2)**, `fee_model` keyword-only requis dans les 2 constructeurs (`resolve_fee_model`), indépendant de `exchange` = source de données (default `"kraken"` :53, :261, :1519, :2509 → toujours passer `--exchange binance`) ; maker sur les fills limit/grille, taker + spread + slippage sur les fills market, taker sans spread aux liquidations forcées (`_force_close_open_positions`, **no-op sur le chemin grok** : `_last_close` jamais posé — B4.3) ; `--trades-out`, `--pair-costs-file` (moteur signal) ; `.env` chargé dans `main()` seulement ; doit appeler `analyzer.update()` dans la boucle |
| `run_p6_backtests.py` | 685 | 24 backtests P6 en multiprocessing + reprise | `Job:84` (champ `fees`), `build_job_list:123`, `FeeModelMismatchError:175`, `filter_pending_jobs:188`, `run_single_backtest_job:311`, `detect_n_workers:407`, `run_parallel:488`, `parse_args:568`, `main:605` | `--fees` obligatoire (B4.2), enregistré dans chaque résultat ; la reprise refuse un fichier d'un autre modèle ou sans clé `fees` (pré-B4.2) → exit 2, `--force` seule échappatoire ; statut `logs/p6_status.json` |
| `run_p6_walkforward.py` | 291 | Walk-forward fenêtres | `generate_windows:49`, `run_single_backtest:80`, `parse_args:116`, `main:132` | `--fees` obligatoire (B4.2), survivants vérifiés (`fees`), `--survivors`/`--output` |
| `filter_p6_survivors.py` 250 · `generate_p6_report.py` 322 · `p6_data_coverage.py` 202 · `p6_5_diagnose_dca.py` 287 · `p6_5_diagnose_filters.py` 300 · `compute_benchmarks.py` 254 | | Pipeline P6 (critères, rapport, couverture, diagnostics, buy&hold/DCA) | `check_criteria:39`, `compute_risk_metrics:39`, `buy_and_hold:123` | sans dépendance runtime (JSON in/out) |
| `run_p7_grid_search.py` | 1004 | Grid search P7 (phase 1 cross-validate, phase 2 walk-forward, report) | `P7Job:107` (champ `fees`), `WalkForwardWindow:212`, `select_top_k_per_combo:272`, `build_phase2_jobs:316`, `FeeModelMismatchError:362`, `filter_pending_jobs:387`, `_assert_results_fee_model:418`, `StatusState:462`, `run_parallel:693`, `parse_args:798`, `_run_report_phase:854`, `main:894` | sorties `results/P7_phase1_cross_validate.json` / `P7_phase2_walk_forward.json` (les fichiers P6/P7 historiques n'ont pas de clé `fees` → B4.3 écrit ailleurs), statut `logs/p7_status.json` ; `--fees` requis pour toutes les phases, validé contre les fichiers d'entrée en phase 2 et report |
| `p7_grids.py` 120 · `p7_report.py` 607 | | Grilles P7 (4 stratégies, noms réels des kwargs) · agrégation walk-forward + 7 critères + markdown | `expand_grid:90` · `WalkForwardAggregate:65`, `aggregate_walk_forward:125`, `ConfigVerdict:225`, `generate_report:440` | rapport `results/P7_optimization_report.md` (non généré) |
| `binance_vision_import.py` | 346 | Import CSV Binance Vision → `market_data_ohlc` | `pair_to_binance_symbol:71`, `parse_klines_csv:109`, `import_month:164`, `main:231` | batch 1000 rows ; ms/µs auto ; **timestamp = `open_time + interval` (fin de période) depuis B4.1** ; `.env` chargé dans `main()` (B4.2) |
| `bybit_kline_import.py` | 346 | Import historique Bybit EU (B3, one-shot) | `ImportStats:74`, `resolve_since:118`, `import_pair_interval:163`, `format_table:258`, `main:341` | REST brut v5 via `fetch_ohlcv` (`vwap`, end-stamped), reprise `MAX(timestamp)` sauf trou de tête (`MIN` trop récent → scan complet), `--force-full`, `--dry-run`, batch 1000 `ON CONFLICT DO NOTHING`, condition d'arrêt loggée (`last_responses`) ; garde `EXCHANGE_NAME=bybit` |
| `backfill_gap.py` | 148 | Backfill de gaps, exchange courant (B3) | `parse_args:49`, `format_summary:76`, `main:143` | wrapper mince de `krakenbot.data.backfill` ; `--dry-run`, `--lookback-days`, `--pairs`, `--intervals` ; client read-only via factory ; warning si exchange ≠ bybit |
| `download_multipair_ohlc.py` | 378 | Download ccxt Binance multi-pair | `download_pair_interval_sync:160` | `exchange="binance"` defaults (:94,112) ; ccxt sync |
| `import_external_ohlc.py` | 403 | Fusion candles Binance sans écraser | `fetch_candles_from_binance:66`, `save_candles_preserve_existing:156` | |
| `dashboard.py` | 3684 | Dash UI (trades, positions, backtests) | `fetch_ohlc_data:409`, `fetch_stats:495`, `run_backtest_in_thread:880`, `create_candlestick_chart:1005`, callbacks `update_*:1914-3392` | `"XBT/USDC"` ×7 (`fetch_ohlc_data:409`, `fetch_current_price:652`) ; SQL brut via `_read_sql:169` ; dropdown backtest construit depuis `strategies.yaml` ; `DASHBOARD_FEE_MODEL:58` = `"bybit"` passé au `BacktestEngine` (B4.2) — la source de données reste le default `kraken` et les stratégies grid sont routées vers le moteur signal (annexes B4.2) |
| `status.py` | 232 | État bot/DB en CLI | `get_status:59` | |
| `build_ml_features.py` 196 · `fetch_external_data.py` 82 | | Pipeline ML (off) | | |
| `seed_test_data.py` 143 · `test_all.py` 233 · `test_binance_connection.py` 105 · `test_binance_ws.py` 106 | | Smoke tests manuels | | `seed_test_data` insère `exchange="kraken"` (:74) |
| `audit/bybit_common.py` · `audit/bybit_q1_endpoints.py` … `bybit_q8_price_diff.py` · `audit/bybit_key_diag.py` · `audit/bybit_b1_roundtrip.py` | | Audit B0/B1 Bybit EU (hors comptage) | | `bybit_b1_roundtrip.py --trade` place 3 LIMIT réels annulés/rejetés (jamais MARKET) ; `bybit_key_diag.py` : clés + wallet UNIFIED/FUND (read-only) |
| `audit/b4_stamp_lib.py` · `audit/b4_timestamp_audit.py` · `audit/b4_restamp_binance.py` | | B4.1 : helpers purs (votes, frontières, manifeste, fenêtres, ledger, règles A/B), audit read-only (modes pré / `--post-migration` / `--pre-migration-view`), migration re-stamp (`--dry-run --explain` / `--execute`, table de progression transactionnelle) — hors comptage | | tests `tests/test_scripts/test_b4_*.py` (48) |
| `audit/b4_2_reference_capture.py` | | B4.2 : harnais de régression iso-fees — `capture` (run → JSON schéma 1, Decimal exact), `compare` (projection byte-exacte), `verify-fees --fees` (maker/taker/spread/slippage trade par trade), `normalise-log` — hors comptage | | tests `tests/test_scripts/test_b4_2_reference_capture.py` ; captures et rejeux dans `results/b4_2_*` |
| `backup_db.sh` · `restore_db.sh` | | Dump/restore Postgres (serveur) | | |

## Points d'attention transverses

1. **Defaults `"kraken"`** encore présents : `OHLCData.exchange:65`, `backtest.py` (4×), `feature_store.py:472`. `settings.exchange_name` est **obligatoire** depuis B1 (`EXCHANGE_NAME` absent → erreur explicite au démarrage) ; reste `deploy.yml` / `.env` serveur (B2).
2. **Kraken en dur hors connecteur** : `execution/order_manager.py:28` et `execution/risk.py:35` (`normalize_asset_*`), `engine.py:82` (type hint). ✅ B3 : `scheduler/task_scheduler.py` passe par le client de la factory et n'importe plus `scripts/` ; `fetch_ohlc.py` supprimé.
3. **`XBT/USDC`** : `settings.trading.pair:196`, `ScheduledTasksSettings:355`, `dashboard.py` (7), `kraken/ws.py:74-75` ; les stratégies utilisent `self.pair`.
4. **Registres statiques** : `main.STRATEGY_REGISTRY:71` (router seul) et `multi_strategy_router._INNER_STRATEGY_CLASSES:54` — une stratégie non listée est ignorée même si présente dans `strategies.yaml`.
5. ✅ B4.2 : **fees de backtest découplées de la source de données** — `--fees {bybit,binance,kraken}` obligatoire (`backtest.py`, runners P6/P7, walk-forward), `ExchangeFees.from_name()`, maker/taker par site de fill, taker aux liquidations forcées du `GridBacktester` (`skills/backtest.md`, `results/B4_2_fees_engine_report.md`). Reste B4.3 : `_force_close_open_positions` inopérant sur le chemin grok (`_last_close` jamais posé), double comptage de la fee de vente dans `net_pnl` (2 moteurs), sorties limit marketables facturées maker.
6. ✅ B3 : `exchange` obligatoire dans `multi_timeframe.py:236` et `multi_pair_registry.py:91` (plus de default `"binance"`). ✅ B4.1 : convention de timestamp unifiée en fin de période (rows `binance` re-stampées le 2026-09-13, `results/B4_1_timestamp_restamp_report.md`) ; les clients REST Binance/Kraken renvoient toujours l'open time ccxt (dette 12).
7. **Fichiers > 1 000 lignes** à ne pas toucher sans review : `kraken/rest.py`, `binance/rest.py`, `bybit/rest.py`, `kraken/ws.py`, `main.py`, `multi_timeframe.py`, `backtest.py`, `dashboard.py`.
