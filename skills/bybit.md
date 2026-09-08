# Skill: Bybit EU

> Constantes et pièges de l'instance Bybit EU, pour le connecteur (B1 REST, B2 WS, B3 data).
> Source : audit B0 du 2026-09-07, `results/bybit_integration_audit.md` (verdict GO avec réserves),
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

ccxt : `ccxt.bybit({"hostname": "bybit.eu", "options": {"defaultType": "spot", "adjustForTimeDifference": True}})`.
`load_markets()` **doit** être appelé sur ce hostname : les filtres de lot EU diffèrent du global,
sinon ccxt arrondit avec les mauvais pas et Bybit rejette (`retCode 10001`). Les clés API créées sur
bybit.eu ne sont pas attendues fonctionner sur api.bybit.com (non prouvé : clés absentes du `.env`).

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
À implémenter en B1 : `ExchangeFees.bybit_defaults(maker=0.0010, taker=0.0025, spread=0.0002, slippage=0.0002)`.

## Filtres de lot (api.bybit.eu, instruments-info du 2026-09-07)

| Pair | symbol | minOrderQty = qtyStep | tickSize | minOrderAmt | maxMarketOrderQty |
|---|---|---|---|---|---|
| BTC/USDC | `BTCUSDC` | 0.000001 | 0.1 | 1 USDC | 91.3 |
| ETH/USDC | `ETHUSDC` | 0.0001 | 0.01 | 5 USDC | 1201 |
| SOL/USDC | `SOLUSDC` | 0.001 | 0.01 | 5 USDC | 7892 |

- `MIN_NOTIONAL = 5 USDC` partout (BTC accepte 1, garder 5 par sécurité).
- Arrondir `qty` à `basePrecision` et `price` à `tickSize` (`amount_to_precision` / `price_to_precision`
  après `load_markets()`).
- **`riskParameters.priceLimitRatioX = 0.5 %`** : un LIMIT trop loin du dernier prix est rejeté.
  Impacte les grilles ATR larges et les profit targets éloignés — à lever/valider en B1 et en paper.
- `marginTrading=utaOnly` → compte **UTA** (`accountType=UNIFIED`) attendu, à confirmer avec les clés.

## Ordres (spot v5)

- `orderType` Limit / Market ; `timeInForce` GTC (défaut) / IOC / FOK / **PostOnly** (c'est un
  `timeInForce`, pas un flag). PostOnly recommandé en entrée pour garantir le maker ; si le prix croise,
  l'ordre est rejeté → re-coter plutôt que devenir taker.
- **Piège market BUY** : ccxt envoie `marketUnit=baseCoin` + `qty` en base si on appelle
  `create_order(sym, "market", "buy", amount)` **sans `price`**. Avec un `price`, ccxt convertit en coût
  quote **sans `marketUnit`** → `qty` interprété en USDC (ordre 79 000× faux). Ne jamais passer `price`
  à un market order Bybit. `params={"cost": 100}` = équivalent explicite de `quoteOrderQty`.
- `clientOrderId` ccxt → `orderLinkId` (≤ 36 chars, unique). `orderId` Bybit = chaîne numérique.
- Pas de GTD en spot → l'expiration des limits reste client-side (`order_manager`).
- Stop serveur (`triggerPrice` + `orderFilter=StopOrder`) existe mais on garde le MARKET client-side.
- Erreurs métier : HTTP 200 avec `retCode != 0`. Mapping à écrire en B1 : `170131` → insufficient
  balance, `170213` → order not exists, `10006` / HTTP 403 → rate limit, `10002` → dérive d'horloge
  (> 5 s ; `recv_window` 5000 ms, RTT mesuré ~200 ms).

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
- Endpoints privés : headers `X-Bapi-Limit*` (non capturés sans clés), 10 req/s par UID par défaut.
- Charge KrakenBot : 0 REST en régime (tout en WS), < 1 req/s pour le polling `order_manager`.

## Non tranché (bloquant B1) — clés API

Au 7 sept 2026, `.env` ne contient ni `BYBIT_API_KEY` ni `BYBIT_API_SECRET`. Non vérifiés : type de
compte (UTA), permissions Spot Trade, whitelist IP, headers de rate limit, refus des clés EU sur le
global. Première action de B1 : ajouter les clés (read-only d'abord) et relancer
`scripts/audit/bybit_q1_endpoints.py`, `bybit_q6_orders.py`, `bybit_q7_ratelimits.py`.

## Ce qui change dans le code (estimation B0 : ~8 j hors re-backtests)

| Composant | Changement |
|---|---|
| `config/settings.py` | `BybitSettings` (hostname, urls, recv_window, account_type), `ExchangeFees.bybit_defaults()`, `exchange_name` accepte `"bybit"`, `.env.example` |
| `connectors/exchange.py` | branche `bybit` dans `build_exchange_rest_client` / `build_exchange_ws_client` |
| `connectors/bybit/rest.py` | clone de `binance/rest.py` (ccxt hostname, market BUY sans price, PostOnly, `orderLinkId`, mapping `retCode`, `accountType=UNIFIED`) |
| `connectors/bybit/ws.py` | clone de `binance/ws.py` (subscribe par lots de 10, parse `kline.*`/`tickers.*`, ping 20 s) |
| `execution/order_manager.py` | statuts via ccxt (`open/closed/canceled/rejected`), `PartiallyFilledCanceled` |
| `scripts/bybit_kline_import.py` | nouveau, import REST paginé |
| `scripts/backtest.py`, `run_p6/p7` | fees maker/taker distincts (dette B4), `--fees bybit` sur données Binance |
| `scheduler/task_scheduler.py` | passer par la factory (hardcode `KrakenRestClient` aujourd'hui) |
| `strategies.yaml`, `main.py`, `dashboard.py`, `collector` | `exchange: bybit`, filtre `settings.exchange_name` |
