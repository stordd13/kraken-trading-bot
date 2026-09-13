# Skill: Bybit EU

> Constantes et pièges de l'instance Bybit EU, pour le connecteur (B1 REST, B2 WS, B3 data).
> Source : audit B0 du 2026-09-07 + levées B1 du 2026-09-08, `results/bybit_integration_audit.md`,
> scripts d'exploration `scripts/audit/bybit_q1_endpoints.py` … `bybit_q8_price_diff.py`.

## Pourquoi Bybit EU

Binance a retiré sa demande MiCA (24 juin 2026) et suspendu ses services aux résidents UE le
1er juillet 2026. Bybit EU GmbH (agréé MiCA via la FMA Autriche) est retenu : maker 0.10 % / taker
0.25 % vérifiés sur le compte, API v5 identique au global, USDC coté. Alternatives écartées : Kraken
Pro (0.40/0.80), Coinbase (0.40–0.60), Bitvavo (API limitée). OKX Europe (0.08/0.10 avec X-Perps)
reste une option au palier 20k. Détail : `docs/archive/PIVOT_BYBIT_PLAN.md`.

## Instance séparée — tout doit cibler `bybit.eu`

| | Global | **EU** |
|---|---|---|
| REST | `https://api.bybit.com` | **`https://api.bybit.eu`** |
| WS public spot | `wss://stream.bybit.com/v5/public/spot` | **`wss://stream.bybit.eu/v5/public/spot`** |
| Symbols spot | 538 | 133 (112 en USDC ; BTC coté en USDC, EUR, PLN — pas de USDT) |
| Historique kline BTC/ETH/SOL-USDC | depuis 2021-12 | **depuis 2025-06-11** (~15 mois, ~2.5M candles sur 7 TF) |
| Carnet / matching engine | propre | propre (mid différent, murs de MM mobiles) |

ccxt : `ccxt.bybit({"hostname": "bybit.eu", "options": {"defaultType": "spot", "adjustForTimeDifference": True,
"enableUnifiedAccount": True}})` — c'est ce que fait `BybitRestClient` (`connectors/bybit/rest.py`, B1).
`load_markets()` **doit** être appelé sur ce hostname : les filtres de lot EU diffèrent du global,
sinon ccxt arrondit avec les mauvais pas et Bybit rejette (`retCode 10001`). Le client le charge
paresseusement (une fois, avant le premier appel exchange) ; échec → `KrakenAPIError`.
**Prouvé le 2026-09-08** : une clé créée sur bybit.eu est refusée sur api.bybit.com (`retCode 10003`
"API key is invalid").

`EXCHANGE_NAME=bybit` est **obligatoire** dans le `.env` (local et serveur) : `Settings.exchange_name`
n'a plus de default depuis B1 (incident du 7 sept). La factory `build_exchange_rest_client` renvoie
`BybitRestClient` ; `build_exchange_ws_client` renvoie `BybitWebSocketClient` (B2). Le template `.env` de
`deploy.yml` fixe `EXCHANGE_NAME=bybit` et attend les secrets GitHub `BYBIT_API_KEY/SECRET` et
`BYBIT_TRADE_API_KEY/SECRET` (B2).

## Clés API — schéma à 4 variables

| Variable | Rôle | Utilisée par |
|---|---|---|
| `BYBIT_API_KEY` / `BYBIT_API_SECRET` | clé **read-only** | paper mode (balance réelle au premier démarrage), audits, tests d'intégration en lecture |
| `BYBIT_TRADE_API_KEY` / `BYBIT_TRADE_API_SECRET` | clé **Trade** (Spot Trade uniquement, **jamais withdraw**) | `TRADING_MODE=live`, `bybit_b1_roundtrip.py --trade`, `BYBIT_INTEGRATION=trade` |

`BybitSettings.credentials(role)` renvoie la paire selon `role ∈ {"readonly", "trade"}` et lève
`ValueError` si la clé Trade est demandée mais absente. `BybitRestClient` choisit `trade` en LIVE
et `readonly` en PAPER ; `BybitRestClient(..., key_role="readonly")` force la clé read-only sur un
client LIVE (lectures réelles sans droit d'écriture). `validate_all()` exige `BYBIT_TRADE_*` en live.

## Fees (ne PAS lire depuis ccxt)

| | Valeur | Note |
|---|---|---|
| Maker (limit, PostOnly) | **0.10 %** | vérifié sur le compte (VIP0) |
| Taker (market) | **0.25 %** | sorties SL / trailing / timeout = MARKET → poste de coût principal |
| Round-trip limit/limit | 0.20 % | vs 0.15 % Binance BNB |
| Round-trip limit/market | 0.35 % | vs 0.15 % Binance BNB |
| Spread simulé | 0.02 % | conservateur vs 0.001–0.02 % observé (Q3) |
| Slippage simulé | 0.02 % | couvre les écarts EU/global nocturnes (Q8 p99 = 18 bps, max 38 bps) |

ccxt affiche `taker=maker=0.001` (valeur générique de `describe()`), pas les fees du compte. Les fees
sont prélevées dans la monnaie reçue (`execFee` dans `/v5/execution/list`), pas d'équivalent BNB.
Implémenté en B1 : `ExchangeFees.bybit_defaults()` (maker 0.0010, taker 0.0025, spread 0.0002, slippage
0.0002). `BybitRestClient` utilise `settings.exchange_fees` s'il est fixé explicitement, sinon ces defaults
(propriété `client.fees`). Les fees backtest (`scripts/backtest.py`) restent la dette B4.

## Filtres de lot (api.bybit.eu, instruments-info du 2026-09-07)

| Pair | symbol | minOrderQty = qtyStep | tickSize | minOrderAmt | maxMarketOrderQty |
|---|---|---|---|---|---|
| BTC/USDC | `BTCUSDC` | 0.000001 | 0.1 | 1 USDC | 91.3 |
| ETH/USDC | `ETHUSDC` | 0.0001 | 0.01 | 5 USDC | 1201 |
| SOL/USDC | `SOLUSDC` | 0.001 | 0.01 | 5 USDC | 7892 |

- `MIN_NOTIONAL = 5 USDC` partout (BTC accepte 1, garder 5 par sécurité).
- Arrondir `qty` à `basePrecision` et `price` à `tickSize` (`amount_to_precision` / `price_to_precision`
  après `load_markets()`).
- **`riskParameters.priceLimitRatioX = 0.5 %` — levé le 2026-09-09** : un LIMIT BUY **passif** à −2 % du
  dernier prix est **accepté** (ordre réel, annulé ensuite). Le ratio plafonne uniquement les prix
  **agressifs** (BUY au-dessus de last × (1 + X) → `170193`, SELL en dessous → `170194`). Aucun impact sur
  les niveaux passifs des grilles ATR ni sur les profit targets. Le client mappe `170193`/`170194` →
  `OrderExecutionError(details.reason="price_limit_ratio")` par précaution.
- Compte **UTA confirmé** le 2026-09-08 (`query-api` → `uta: "1"`, `wallet-balance?accountType=UNIFIED`
  répond). `options.enableUnifiedAccount=True` force la branche UTA de ccxt (market BUY en `qty` base
  avec `marketUnit=baseCoin`, pas d'appel privé de détection).

## Ordres (spot v5)

- `orderType` Limit / Market ; `timeInForce` GTC (défaut) / IOC / FOK / **PostOnly** (c'est un
  `timeInForce`, pas un flag). PostOnly recommandé en entrée pour garantir le maker ; si le prix croise,
  l'ordre est rejeté → re-coter plutôt que devenir taker. **Forme réelle du rejet (2026-09-09)** :
  `order/create` répond `retCode 0` avec un `orderId`, puis l'ordre passe `orderStatus=Rejected`,
  `rejectReason=EC_PostOnlyWillTakeLiquidity`, `cumExecQty=0` — pas d'exception ccxt. D'où le
  `fetch_order` post-création du client (voir API ci-dessous).
- **ccxt `fetch_order` sur Bybit exige `params={"acknowledged": True}`** (limitation « 500 derniers
  ordres »), sinon ccxt lève un avertissement en exception *après* que l'ordre a été créé. Le client
  le passe partout (`_FETCH_ORDER_PARAMS`).
- **Piège market BUY** : ccxt envoie `marketUnit=baseCoin` + `qty` en base si on appelle
  `create_order(sym, "market", "buy", amount)` **sans `price`**. Avec un `price`, ccxt convertit en coût
  quote **sans `marketUnit`** → `qty` interprété en USDC (ordre 79 000× faux). Ne jamais passer `price`
  à un market order Bybit. `params={"cost": 100}` = équivalent explicite de `quoteOrderQty`.
- `clientOrderId` ccxt → `orderLinkId` (≤ 36 chars, unique). `orderId` Bybit = chaîne numérique.
- Pas de GTD en spot → l'expiration des limits reste client-side (`order_manager`).
- Stop serveur (`triggerPrice` + `orderFilter=StopOrder`) existe mais on garde le MARKET client-side.
- Erreurs métier : HTTP 200 avec `retCode != 0`. Mapping B1 (`BybitRestClient._translate_error`, qui
  lit l'exception typée ccxt **et** le `retCode` brut du message) : `170131` → `InsufficientBalanceError`,
  `170213` → `status="not_found"` / `cancel_order → False`, `10006` / HTTP 403 → `RateLimitError`,
  `10002` → `KrakenAPIError` (message NTP actionnable ; `recv_window` 5000 ms, RTT ~200 ms),
  `10005` → `KrakenAPIError(details.reason="permission_denied")` (clé read-only, Spot Trade absent ou
  IP non whitelistée — observé sur `order/create` avec la clé `readOnly=1`), `170193`/`170194`
  ("buy price cannot be higher / sell price cannot be lower") → `OrderExecutionError(details.reason=
  "price_limit_ratio")`, `10001` → `OrderExecutionError` (filtre de lot / paramètre).

### API `BybitRestClient` (B1)

- `place_market_order(pair, side, amount, strategy, signal_price, *, quote_amount=None)` : `amount`
  arrondi vers le bas au `qtyStep`, `price` jamais transmis à ccxt ; `quote_amount` (BUY uniquement)
  → `params={"cost": ...}`, `amount=None`. Fee dans la monnaie reçue (`order["fee"]`).
- `place_limit_order(pair, side, amount, price, strategy, expires_in_seconds, *, post_only=True)` :
  prix arrondi au `tickSize` **à l'écart du marché** (BUY vers le bas, SELL vers le haut) ;
  `timeInForce=PostOnly` par défaut (`post_only=False` → GTC). La réponse `order/create` n'a pas de
  statut → un `fetch_order(..., params={"acknowledged": True})` suit (coût 5). **Rejet PostOnly** (ccxt `OrderImmediatelyFillable`, message
  "post only", ou ordre `rejected`/`canceled` avec `filled=0`) → retour **normalisé** : `Order(status=
  CANCELLED, filled_amount=0, signal_metadata={"reject_reason": "post_only_would_cross", ...})`, pas
  d'exception, `orders_failed` non incrémenté → le caller re-cote.
- `clientOrderId` = `kb-<uuid hex>` (≤ 36 chars) → `orderLinkId`, repris dans `signal_metadata` et
  `get_order_status()["client_order_id"]`.
- `MIN_NOTIONAL = 5` validé après arrondi ; `MIN_ORDER_SIZE` = filtres EU ci-dessus.
- Paper mode : mêmes mécaniques que le client Binance (balance mémoire + `paper_balance` DB, fees maker
  sur limit / taker sur market).

## WebSocket v5 public

- Une seule connexion suffit : 21 klines + 3 tickers. **Max 10 `args` par requête `subscribe`**
  (`"args size >10"` sinon) → 3 requêtes.
- Topics : `kline.{interval}.{SYMBOL}`, `tickers.{SYMBOL}`. Mapping intervalles projet → Bybit :
  `1 5 15 60 240 → "1" "5" "15" "60" "240"`, `1440 → "D"`, `10080 → "W"`. Symbole = `pair.replace("/", "")`.
- Kline : `data[0]` avec `start`/`end` en ms, **`end` inclusif** (`end = start + interval − 1 ms`) →
  règle DB inchangée : `timestamp = end + 1 ms` (= `start + interval`), aligné sur Binance.
  `confirm: true` = clôture (équivalent `k.x`). `volume` en base, `turnover` en quote (VWAP =
  turnover/volume), **pas de `trades_count`**.
- Messages kline poussés uniquement en cas de trade (31 msgs / 5 min sur EU) : calibrer le watchdog sur
  l'ensemble des topics, pas sur un seul symbole 1m.
- Ping applicatif `{"op":"ping"}` toutes les 20 s ; le pong arrive avec `op: "ping"`,
  `ret_msg: "pong"`. Le serveur n'a pas coupé en 15 min sans ping, mais le ping reste obligatoire pour
  détecter les zombies (absence de pong ~10 s → `_force_disconnect_and_reconnect`). Ignorer les acks
  `subscribe` (pas de `topic`) et les pongs dans le parseur. Garder le reconnect préventif à 23 h.
- Ticker spot : `type=snapshot` à chaque message, champ `lastPrice`, `usdIndexPrice` vide sur EU.

### Implémenté en B2 — `connectors/bybit/ws.py` (`BybitWebSocketClient`)

- Clone structurel de `binance/ws.py` (aiohttp, `heartbeat=None` : le ping applicatif est le seul
  mécanisme de vie, `receive_timeout=60`). Sélection via `build_exchange_ws_client` (`EXCHANGE_NAME=bybit`).
- Settings (`BybitSettings`, env `BYBIT_*`) : `ws_url` (`wss://stream.bybit.eu/v5/public/spot`),
  `ws_ping_interval_seconds` (20), `ws_pong_timeout_seconds` (10, validé < ping), `ws_watchdog_warn_seconds` (600), `ws_watchdog_zombie_seconds` (1800, validé > warn),
  `ws_watchdog_resubscribe_alert_count` (3). **Seuils en `.env`, pas en code** : à ajuster après
  l'observation 24 h / le paper sans commit.
- Souscription : `subscribe_ohlc` / `subscribe_ticker` envoient 1 topic ; `_resubscribe_all()` renvoie tous
  les topics par lots de 10 (`MAX_ARGS_PER_REQUEST`), utilisé après chaque reconnect et par le watchdog.
  Un subscribe dupliqué est idempotent côté Bybit (pas d'ack, pas de doublon).
- **Deux détecteurs distincts** :
  1. `_ping_loop` = vie de la CONNEXION : ping 20 s, pas de pong sous 10 s → `bybit_ws_pong_timeout`,
     Telegram (1 fois par épisode) + `_reconnect` (backoff 5 s × 2ⁿ, max 300 s, 10 essais).
  2. `_data_flow_watchdog` = vie des SOUSCRIPTIONS, sur le flux **agrégé** (klines + tickers, pongs et
     acks exclus), check toutes les 60 s après 60 s de grâce :
     - ≥ `warn` (10 min) sans aucun message topic → `bybit_ws_data_flow_stale`
       (`reason=quiet_market_or_lost_subscriptions`, `pong_alive`), re-subscribe silencieux, 1 fois par
       épisode (flag remis par le premier message topic). Pas de Telegram… sauf **escalade** : ≥ 3
       re-subscribes en 24 h glissantes → `bybit_ws_resubscribe_storm_telegram_sent`.
     - ≥ `zombie` (30 min) → `bybit_ws_data_flow_zombie` (connexion vivante, flux mort), Telegram +
       `_reconnect`.
     - `bybit_ws_data_flow_ok` toutes les 5 min : `topic_messages_delta`, `pongs_delta` — c'est la métrique
       pour recalibrer les seuils.
  Justification : ~10 msgs/min observés sur UNE paire l'après-midi ; avec 24 topics, 10 min de silence =
  zéro trade sur BTC+ETH+SOL/USDC. Le seuil Binance (5 min → reconnect) bouclerait la nuit.
- Kline → `MARKET_OHLC` (même dict que Binance/Kraken) + `OHLCData(exchange="bybit", vwap=turnover/volume
  quantisé 1e-8 ou None si volume 0, trades_count=None)` via `session.merge` (collector seulement :
  `db_manager` injecté). Candles `volume=0` écrites.
- Ticker → `MARKET_TICK` `{pair, timestamp, price, last, bid: None, ask: None, volume}` : le ticker spot v5
  n'a pas de best bid/ask. Vérifié le 2026-09-09 : seul `BaseStrategy._handle_tick` consomme l'événement
  et les 8 stratégies ne lisent que `price` ; les lecteurs de bid/ask passent par le REST `get_ticker`
  (`bid1Price`/`ask1Price` mappés par ccxt). Si B5 veut le best bid/ask en push : topic `orderbook.1.{SYMBOL}`.
- Stats supplémentaires : `topic_messages`, `pongs_received`, `resubscribes` (loggées par le collector
  toutes les 5 min dans `collector_periodic_stats`).
- Tests : `tests/test_connectors/test_bybit_ws.py` (46, WS mocké) ;
  `BYBIT_INTEGRATION=1 poetry run pytest tests/test_connectors/test_bybit_ws_integration.py` (connexion
  réelle, ≥ 1 pong + ≥ 1 kline/ticker en ≤ 90 s, sans DB ni clé).
- Collector (`EXCHANGE_NAME=bybit`) : 3 paires × 7 TF (`SCHEDULER_INTERVALS`, 1m inclus) + 3 tickers = 24
  topics en 3 requêtes. Depuis B3 le `TaskScheduler` (backfill de gaps REST, § « Données historiques »)
  est instancié pour tout exchange, contrôlé par `SCHEDULER_ENABLED`, avec le client REST **read-only**
  du collector (`build_exchange_rest_client(..., read_only=True)`).

**Observé — collecte locale 1 h du 2026-09-09 (13:07 → 14:07 UTC, Wi-Fi local, tunnel SSH saturé en
parallèle par les tests P6) :**
- Flux agrégé 24 topics : **272 à 573 messages topic / 5 min** (≈ 1–2 msg/s), 15 pongs / 5 min,
  4 550 frames reçues, 225 candles clôturées écrites (58 × 1m, 12 × 5m, 4 × 15m, 1 × 1h par paire),
  59 candles plates (`volume=0`, `vwap NULL`), 0 erreur de parsing / d'écriture, 0 `data_flow_stale`.
  Un silence de 10 min en journée représenterait donc ~600 messages manquants : le palier warn est large.
- **3 décrochages réseau** (13:27, 13:38, 13:57) : silence total du socket (klines, tickers ET pong) pendant
  28–47 s, détecté par `pong_timeout` (10 s) → reconnect en 16 s (5 s backoff + ~11 s de connexion, signe de
  dégradation réseau) → 24 topics resouscrits, flux repris. Un timeout de pong plus long n'aurait rien changé.
- **Conséquence data** : la candle dont la clôture tombe pendant la coupure n'est jamais confirmée
  (Bybit ne rejoue pas) → 2 trous de 1 candle 1m par paire (13:39, 13:57), aucun sur 5m/15m/1h. À couvrir
  par le backfill REST de gaps (B3), pas par le WS.
**Observation serveur 24 h (2026-09-09 18:12 → 2026-09-10 18:41 UTC, DB locale, `dev@ad296c8`) — PROPRE :**
- 101 349 frames, 96 918 messages topic, 4 401 pongs, 5 667 candles clôturées, 0 erreur, 0 `data_flow_stale`,
  0 zombie, 0 `pong_timeout`, 0 Telegram. Flux agrégé par 5 min : **min 164 (nuit), max 1 290, moy. 330**
  → un silence de 10 min reste ≥ 3× hors norme même la nuit ; seuils 600/1800 s conservés.
- 1m : 1 469 candles par paire = **complet** (0 trou), 35 % de candles plates la nuit (`volume=0`), 0 désalignement,
  5m/15m/1h/4h/1d cohérents.
- 2 fermetures côté serveur Bybit (`close_code 1006` à 01:37 et 02:31 UTC) → reconnect en 5 s + 24 topics
  resouscrits, **aucune candle perdue** (aucune clôture dans la fenêtre). À surveiller sur la durée ; le
  reconnect préventif 23 h n'a pas encore eu lieu car chaque reconnexion réarme le timer (prochain ≈ 01:31 UTC).
- **Nuit 2 (10→11 sept)** : Bybit EU ferme la connexion avec `close_code 1006` chaque nuit entre ~01:00 et
  02:40 UTC (4 fermetures en 2 nuits : 01:37, 02:31, 01:04, 01:58), reconnect en ~6 s + 24 topics à chaque
  fois. Le reconnect préventif 23 h ne s'est **jamais déclenché** : chaque fermeture réarme le timer (il est
  de fait remplacé par les coupures Bybit). **Première perte réelle** : la fermeture de 01:04:54 a chevauché la
  clôture 01:05:00 → candle 1m 01:05 absente pour BTC et SOL (ETH l'a reçue). Confirme le besoin du backfill
  de gaps REST en **B3** (~1 candle 1m perdue par nuit et par paire au pire, jamais sur les TF ≥ 5m à ce jour).
- Contrôles SQL utilisés (à réutiliser pour l'observation 24 h) :
  ```sql
  SELECT pair, interval, COUNT(*), MIN(timestamp), MAX(timestamp) FROM market_data_ohlc
   WHERE exchange='bybit' GROUP BY pair, interval ORDER BY pair, interval;
  -- 1w : la grille est ancrée le LUNDI 00:00 UTC (epoch 0 = jeudi) → offset 4 jours
  SELECT interval, COUNT(*) FILTER (WHERE (EXTRACT(EPOCH FROM timestamp)::bigint
           - CASE WHEN interval = 10080 THEN 4*86400 ELSE 0 END) % (interval*60) <> 0) AS misaligned
    FROM market_data_ohlc WHERE exchange='bybit' GROUP BY interval;            -- 0 attendu partout
  WITH t AS (SELECT pair, timestamp, LAG(timestamp) OVER (PARTITION BY pair ORDER BY timestamp) prev
             FROM market_data_ohlc WHERE exchange='bybit' AND interval=1)
  SELECT pair, prev, timestamp FROM t WHERE timestamp - prev > interval '1 minute';  -- = reconnexions
  ```

## Données historiques (B3) — ✅ fait le 2026-09-11 (`results/B3_bybit_data_report.md`)

- Pas de dumps kline spot sur `public.bybit.com` (trades tick uniquement, et du global). Import REST
  paginé : `GET /v5/market/kline?category=spot&symbol=…&interval=…&start=…&limit=1000`, liste
  **descendante**, avancer de `last_start + interval`. Format ligne :
  `[startTime(ms), open, high, low, close, volume(base), turnover(quote)]`.
- **`BybitRestClient.fetch_ohlcv` (B3)** passe par l'endpoint brut via l'API implicite ccxt
  (`publicGetV5MarketKline`, même hostname EU, même token-bucket, coût 5) et **non** par `fetch_ohlcv`
  ccxt (qui perd `turnover`). Contrat : `timestamp = start + interval` (fin de période, = rows WS),
  `vwap = turnover / volume` quantisé 1e-8 (`None` si volume 0), candle en cours exclue, liste
  ascendante, `since` = open time de la première candle voulue (= `MAX(timestamp)` DB pour reprendre).
  **Ce contrat n'existe que pour Bybit** : Binance/Kraken renvoient l'open time ccxt → le backfill générique
  n'est correct que pour `EXCHANGE_NAME=bybit` (docstring du Protocol `connectors/exchange.py`).
- Première candle EU : **2025-06-11 09:00 UTC** (1h, DB ts `10:00`) ; 1w : première clôture `2025-06-16`
  (lundi). Les premières candles sont plates (`volume=0`, `vwap NULL`) : ce sont des candles, pas des trous.
- Convention 1d/1w vs Binance : décalage d'**exactement un intervalle** (Binance Vision = open time),
  documenté dans `skills/database.md`, remédiation B4.

### Runbook import historique — `scripts/bybit_kline_import.py`

```bash
tmux new -s b3-import && cd ~/apps/kraken-trading-bot        # serveur, DB locale, collector actif
poetry run python scripts/bybit_kline_import.py --dry-run     # curseurs + nb d'appels estimés
poetry run python scripts/bybit_kline_import.py               # 3 paires × 7 TF, ~2 550 appels, ~15 min
poetry run python scripts/bybit_kline_import.py --pairs BTC/USDC --intervals 60 --force-full
```
Reprise par `MAX(timestamp)` par (pair, interval) **sauf** trou de tête (`MIN(timestamp)` trop récent :
rows WS présentes mais historique jamais importé → scan complet depuis `--since`, défaut `2025-06-01`).
Insert `ON CONFLICT DO NOTHING` batch 1000 : les candles du collector font foi. Condition d'arrêt loggée
(`last_responses` : page courte puis réponse vide = fin d'historique, ou `reached_now`).

### Runbook backfill de gaps — `scripts/backfill_gap.py` / `TaskScheduler`

```bash
poetry run python scripts/backfill_gap.py --dry-run                 # table des gaps, aucune écriture
poetry run python scripts/backfill_gap.py                           # comble tout (trous internes + fin)
poetry run python scripts/backfill_gap.py --lookback-days 3 --intervals 1 5
```
Module `krakenbot.data.backfill` : trous internes (query LAG) + gap de fin (`MAX(timestamp)` → dernière
candle clôturée, marge 15 s), `fetch_ohlcv` + `ON CONFLICT DO NOTHING`. Le même code tourne dans le collector
via `TaskScheduler` : job unique `gap_backfill`, cron `SCHEDULER_DAILY_BACKFILL_CRON` (défaut **`30 3 * * *`**,
après la fenêtre des fermetures 1006 de 01:00–02:40 UTC), fenêtre de scan `SCHEDULER_BACKFILL_DAYS`
(défaut 3). Chaque run écrit `task_execution_logs` (1 row par gap + 1 row de run `pair='*'`, `interval=0`)
et logge `scheduled_backfill_completed` (gaps_found / gaps_filled / candles_inserted).
- Décision B0 confirmée : **les backtests restent sur les données Binance** (corrélation close 1h BTC
  Bybit global vs Binance 0.999999, EU vs Binance 0.99999, écart moyen ≈ 0, pas de biais). L'historique
  EU sert de contrôle out-of-sample et de warmup live.

## Rate limits

- Endpoints publics : pas de headers de limite ; burst de 120 appels kline en 1.4 s passé sans erreur
  (doc ≈ 600 req / 5 s par IP). ccxt : token-bucket `rateLimit=20 ms` × coût (kline/orderbook/tickers = 5,
  order/create = 2.5). `enableRateLimit=True` suffit.
- Endpoints privés (capturé le 2026-09-08 sur `wallet-balance`) : `X-Bapi-Limit: 50`,
  `X-Bapi-Limit-Status: 49` (restant), `X-Bapi-Limit-Reset-Timestamp` (ms). Doc : 10–20 req/s par UID
  sur `order/*`. Le burst de 60 klines concurrents en 1.45 s est passé sans `10006`.
- Charge KrakenBot : 0 REST en régime (tout en WS), < 1 req/s pour le polling `order_manager`.

## Levé en B1 (2026-09-08) — clés API et compte

Clés `BYBIT_API_KEY` / `BYBIT_API_SECRET` dans le `.env` local (note « krakenbot_readonly », créées le
2026-09-08, **expirent le 2026-12-08**, `ips: ["*"]`). Audits Q1/Q6/Q7 relancés (`results/bybit_integration_audit.md`
§ « Levées post-B0 ») : compte **UTA**, permissions `Spot: [SpotTrade]`, clé refusée sur le global,
headers de rate limit capturés, `adjustForTimeDifference` nécessaire (offset +93 ms, `recvWindow` 5000).

**Levé le 2026-09-09 (clé `krakenbot_trade` recréée en Read-Write, 28.43 USDC transférés Funding →
Unified Trading Account)** — protocole `scripts/audit/bybit_b1_roundtrip.py --trade --notional 6` :
- (a) PostOnly BUY −5 % → créé, `get_order_status` = `open`, `cancel_order` = True ;
- (b) GTC BUY −2 % → **accepté** (verdict `priceLimitRatioX` ci-dessus), annulé ;
- (c) PostOnly BUY au-dessus de l'ask → `Rejected` / `EC_PostOnlyWillTakeLiquidity`, 0 fill, normalisé
  `reject_reason="post_only_would_cross"` ;
- `fetch_open_orders` vide en fin de run, balance inchangée, aucun MARKET.
`BYBIT_INTEGRATION=trade pytest tests/test_connectors/test_bybit_rest_integration.py` → 5 passed.
Sortie brute : `results/bybit_integration_audit.md` § « Levées post-B0 ».

Pièges rencontrés en chemin : une clé créée en « Read-Only » sur bybit.eu garde `readOnly=1` même avec
la case Spot Trade → `order/create` = `10005` ; des USDC déposés dans le wallet **Funding** sont
invisibles de `wallet-balance?accountType=UNIFIED` et inutilisables en spot → transfert interne requis.
Diagnostic : `poetry run python scripts/audit/bybit_key_diag.py` (read-only).

## Ce qui change dans le code (estimation B0 : ~8 j hors re-backtests)

| Composant | Changement |
|---|---|
| `config/settings.py` | ✅ B1 : `BybitSettings` (hostname, recv_window, account_type), `ExchangeFees.bybit_defaults()`, `exchange_name` **obligatoire** (`kraken\|binance\|bybit`), `.env.example` |
| `connectors/exchange.py` | ✅ B1 : branche `bybit` dans `build_exchange_rest_client` · ✅ B2 : branche `bybit` dans `build_exchange_ws_client` |
| `connectors/bybit/rest.py` | ✅ B1 : clone de `binance/rest.py` (ccxt hostname, market BUY sans price, PostOnly normalisé, `orderLinkId`, mapping `retCode`, UTA) — 67 tests unitaires + intégration opt-in |
| `connectors/bybit/ws.py` | ✅ B2 : clone de `binance/ws.py` (subscribe par lots de 10, parse `kline.*`/`tickers.*`, ping 20 s, watchdog 2 paliers configurable) — 46 tests + intégration opt-in |
| `execution/order_manager.py` | statuts via ccxt (`open/closed/canceled/rejected`), `PartiallyFilledCanceled` |
| `scripts/bybit_kline_import.py` | ✅ B3 : import REST paginé brut v5, reprise `MAX(timestamp)`, batch 1000, `ON CONFLICT DO NOTHING` |
| `data/backfill.py`, `scripts/backfill_gap.py` | ✅ B3 : backfill de gaps exchange-agnostic (LAG + tail), CLI `--dry-run` |
| `scripts/backtest.py`, `run_p6/p7` | fees maker/taker distincts (dette B4), `--fees bybit` sur données Binance |
| `scheduler/task_scheduler.py` | ✅ B3 : client REST read-only injecté par le collector, job unique `gap_backfill` 03:30 UTC, plus d'import `scripts/` |
| `strategies.yaml`, `main.py`, `dashboard.py`, `collector` | `exchange: bybit`, filtre `settings.exchange_name` — ✅ B2 pour le collector (intervals depuis settings, garde scheduler, `SCHEDULER_PAIRS` default BTC/ETH/SOL) |
