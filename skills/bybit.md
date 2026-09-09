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
`BybitRestClient` ; `build_exchange_ws_client` lève `NotImplementedError` jusqu'à B2.

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

## Données historiques (B3)

- Pas de dumps kline spot sur `public.bybit.com` (trades tick uniquement, et du global). Import REST
  paginé : `GET /v5/market/kline?category=spot&symbol=…&interval=…&start=…&limit=1000`, liste
  **descendante**, avancer de `last_start + interval`. ~2 532 appels pour tout l'historique EU (≈ 15 min).
- Format ligne : `[startTime(ms), open, high, low, close, volume(base), turnover(quote)]`.
- Les premières candles EU (2025-06-11) ont `volume=0` : candles plates, pas des trous — l'import doit
  les accepter. Insertion `exchange='bybit'`, batch 1000, `ON CONFLICT DO NOTHING`.
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
| `connectors/exchange.py` | ✅ B1 : branche `bybit` dans `build_exchange_rest_client` ; WS → `NotImplementedError` jusqu'à B2 |
| `connectors/bybit/rest.py` | ✅ B1 : clone de `binance/rest.py` (ccxt hostname, market BUY sans price, PostOnly normalisé, `orderLinkId`, mapping `retCode`, UTA) — 67 tests unitaires + intégration opt-in |
| `connectors/bybit/ws.py` | clone de `binance/ws.py` (subscribe par lots de 10, parse `kline.*`/`tickers.*`, ping 20 s) |
| `execution/order_manager.py` | statuts via ccxt (`open/closed/canceled/rejected`), `PartiallyFilledCanceled` |
| `scripts/bybit_kline_import.py` | nouveau, import REST paginé |
| `scripts/backtest.py`, `run_p6/p7` | fees maker/taker distincts (dette B4), `--fees bybit` sur données Binance |
| `scheduler/task_scheduler.py` | passer par la factory (hardcode `KrakenRestClient` aujourd'hui) |
| `strategies.yaml`, `main.py`, `dashboard.py`, `collector` | `exchange: bybit`, filtre `settings.exchange_name` |
