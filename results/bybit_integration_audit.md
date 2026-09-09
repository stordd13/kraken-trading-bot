# Bybit EU — Audit d'intégration (2026-09-07)

> Agent B0 — lecture seule. Aucun ordre placé, aucune modification du code de production.
> Scripts d'exploration : `scripts/audit/bybit_q1_endpoints.py` … `bybit_q8_price_diff.py` (+ `bybit_common.py`).
> Outputs bruts complets : `$BYBIT_AUDIT_OUT/q*_run.log` / `q*.json` (hors repo). Les extraits ci-dessous sont tronqués.
> ccxt 4.5.34, websockets 16.0, Python 3.12 (poetry env).

## Résumé exécutif

- **Faisabilité : GO avec réserves.**
- **Bybit EU est une instance séparée**, pas un simple front réglementaire : `api.bybit.eu` / `stream.bybit.eu`, 133 symbols spot (vs 538 sur `api.bybit.com`), `symbolId` différents, filtres de lot différents, carnet d'ordres propre, historique kline **uniquement depuis le 2025-06-11** (~15 mois). Tout le code B1-B3 doit cibler `hostname="bybit.eu"`.
- **Les données Binance restent la base de backtest** : sur 90 jours BTC/USDC 1h, close Bybit global vs Binance corrélé à 0.999999 (|écart| médian 0.7 bps, max 7 bps) ; Bybit EU vs Binance 0.99999 (|écart| médian 1.3 bps, p99 18 bps, max 38 bps, 0 candle sans volume). Backtester sur Binance avec fees Bybit est justifié ; l'écart EU est du bruit de microstructure (volume 1h médian 2.8 BTC sur EU vs 10 BTC sur global).
- **Les 3 points qui conditionnent B1-B3** :
  1. **Clés API absentes du `.env`** (`BYBIT_API_KEY`/`BYBIT_API_SECRET` non définies) → la partie authentifiée (Q1 `query-api`, `wallet-balance`, permissions, type de compte UTA, headers `X-Bapi-Limit`) **n'a pas pu être vérifiée**. À faire en tout premier dans B1.
  2. **Fees 0.10 % maker / 0.25 % taker** (vs 0.075 % Binance BNB) : un aller-retour taker coûte 0.50 % contre 0.15 % aujourd'hui. Les stratégies à rotation rapide (grid ATR, scalping) doivent être re-backtestées avec `ExchangeFees.bybit_defaults()` avant tout go live ; les sorties MARKET (stop-loss/trailing) sont le poste de coût principal.
  3. **Market BUY via ccxt** : `create_order(sym, "market", "buy", amount)` envoie `marketUnit=baseCoin` + `qty` en base (OK pour le code actuel), **mais** si un `price` est passé, ccxt convertit en coût quote sans `marketUnit` → piège à documenter dans le connecteur. Le stop-loss serveur (`triggerPrice` + `orderFilter=StopOrder`) existe mais n'est pas nécessaire (on garde le MARKET client-side comme sur Binance).

---

## Q1 — Endpoints Bybit EU

**Réponse.** Bybit EU GmbH utilise un **domaine dédié** : `https://api.bybit.eu` (REST) et `wss://stream.bybit.eu` (WS). Les deux sont des distributions CloudFront distinctes de `api.bybit.com` / `stream.bybit.com`. L'API est la même v5 (mêmes chemins, même format de réponse), mais l'univers d'instruments et les filtres diffèrent (voir Q2). ccxt supporte cela nativement via l'option `hostname="bybit.eu"` (les URLs sont `https://api.{hostname}`). Écart d'horloge mesuré : +66 ms (global) / +97 ms (EU), RTT ~150-210 ms depuis le Mac — très loin du `recv_window` par défaut de 5000 ms.

**Preuve.**
```
$ dig +short api.bybit.eu      → d2kgrdix5zze9r.cloudfront.net.
$ dig +short stream.bybit.eu   → dk6nkjr60fw8y.cloudfront.net.
$ dig +short api.bybit.com     → d3d4ij29qlbhtu.cloudfront.net.
(api.bybit-eu.com, api.eu.bybit.com, api-eu.bybit.com : ne résolvent pas)

Q1.a — Server time / clock offset / RTT per host
global  https://api.bybit.com   offset(median)=+66 ms  rtt(median)=152 ms  raw={"retCode": 0, "retMsg": "OK", "result": {"timeSecond": "1788791200", "timeNano": "1788791200401574337"}, ...}
eu      https://api.bybit.eu    offset(median)=+97 ms  rtt(median)=210 ms  raw={"retCode": 0, "retMsg": "OK", "result": {"timeSecond": "1788791202", ...}

Q1.b — Spot instrument universe: global vs EU host
global : 538 spot symbols (538 Trading), 85 *USDC
eu     : 133 spot symbols (133 Trading), 112 *USDC
only on global (463): ["0GUSDT", "1INCHUSDT", ... "ADAUSDT", ... "APEXUSDC", ...]
only on EU     (58): ["AEROUSDC", "ANIMEUSDC", ... "CCEUR", ... "EURCEUR", "EURCUSDC", ... "HYPEEUR", ...]
BTCUSDC: global=yes eu=yes identical_filters=False   (symbolId 117 vs 838, minOrderAmt 5 vs 1, maxOrderQty 48 vs 273.92)
ETHUSDC: global=yes eu=yes identical_filters=False   (symbolId 116 vs 934, basePrecision 0.00001 vs 0.0001)
SOLUSDC: global=yes eu=yes identical_filters=False   (symbolId 133 vs 933, basePrecision 0.0001 vs 0.001)

Q1.c — Private endpoints exist on both hosts? (unauthenticated probe)
eu      GET /v5/user/query-api          HTTP 200 -> {"retCode": 10001, "retMsg": "Request parameter error: apiKey is missing", ...}
eu      GET /v5/account/wallet-balance  HTTP 401 -> null

Q1.d — ccxt.bybit hostname handling
ccxt.bybit(hostname='bybit.com') -> https://api.bybit.com  fetch_time=1788791205088  recvWindow=5000  adjustForTimeDifference=False
ccxt.bybit(hostname='bybit.eu')  -> https://api.bybit.eu   fetch_time=1788791205543  recvWindow=5000  adjustForTimeDifference=False

Q1.e — Authenticated calls (read-only) with .env keys
BYBIT_API_KEY / BYBIT_API_SECRET NOT FOUND in .env -> authenticated part SKIPPED.
```

**Non tranché (explicitement).** `GET /v5/user/query-api` et `GET /v5/account/wallet-balance` **n'ont pas été appelés avec les clés du compte** : le `.env` ne contient aucune variable `BYBIT_*` (vérifié par `grep -E "^BYBIT" .env`). On ne peut donc pas prouver ici (a) que les clés créées sur bybit.eu sont refusées sur api.bybit.com (attendu d'après la séparation des instances), (b) le type de compte (UTA obligatoire pour `accountType=UNIFIED` — le champ `marginTrading=utaOnly` des instruments EU suggère que oui), (c) les permissions/IP whitelist. Le script `bybit_q1_endpoints.py` exécute ces appels automatiquement dès que les clés sont dans `.env`.

**Impact code.** `BybitSettings(api_url="https://api.bybit.eu", ws_url="wss://stream.bybit.eu/v5/public/spot", recv_window_ms=5000)` ; ccxt initialisé avec `{"hostname": "bybit.eu", "options": {"defaultType": "spot", "recvWindow": ..., "adjustForTimeDifference": True}}`. Le `recv_window` Bybit se passe en header `X-BAPI-RECV-WINDOW` (ccxt le gère) ; erreur `retCode 10002` si dérive > 5 s. Activer `adjustForTimeDifference=True` comme sur Binance (ccxt bybit ne le fait pas par défaut).

---

## Q2 — Paires USDC

**Réponse.** `BTCUSDC`, `ETHUSDC`, `SOLUSDC` existent en spot sur l'entité EU, statut `Trading`, `marginTrading=utaOnly`. Sur EU, BTC n'est coté qu'en **USDC, EUR, PLN** (pas de USDT). Les filtres EU sont **plus grossiers que ceux du global** pour ETH/SOL et **identiques aux constantes Binance actuelles** pour ETH et SOL ; BTC est 10× plus fin (`0.000001`). Min notional : 5 USDC (ETH, SOL) et **1 USDC pour BTC** sur EU (5 sur global) — garder 5 partout par sécurité.

| Pair | symbol | minOrderQty | qtyStep (basePrecision) | minOrderAmt | tickSize | maxMarketOrderQty | Binance (rest.py) minQty / minNotional |
|---|---|---|---|---|---|---|---|
| BTC/USDC | `BTCUSDC` | 0.000001 | 0.000001 | **1** | 0.1 | 91.30695 | 0.00001 / 5 |
| ETH/USDC | `ETHUSDC` | 0.0001 | 0.0001 | 5 | 0.01 | 1201.96 | 0.0001 / 5 |
| SOL/USDC | `SOLUSDC` | 0.001 | 0.001 | 5 | 0.01 | 7892.84 | 0.001 / 5 |

**Preuve** (`GET /v5/market/instruments-info?category=spot&symbol=…` sur `api.bybit.eu`).
```
BTCUSDC: status=Trading marginTrading=utaOnly innovation=0 stTag=0
   tickSize=0.1  minOrderQty=0.000001  basePrecision=0.000001  quotePrecision=0.0000001  minOrderAmt=1  maxOrderQty=273.92085  maxMarketOrderQty=91.30694999  maxLimitOrderQty=273.92085  maxOrderAmt=1200000  postOnlyMaxLimitOrderSize=1369.60425
   raw: {"symbolId": 838, "symbol": "BTCUSDC", "baseCoin": "BTC", "quoteCoin": "USDC", ... "priceFilter": {"tickSize": "0.1"}, "riskParameters": {"priceLimitRatioX": "0.005", "priceLimitRatioY": "0.01"} ...}
ETHUSDC: status=Trading ...
   tickSize=0.01  minOrderQty=0.0001  basePrecision=0.0001  quotePrecision=0.000001  minOrderAmt=5  maxOrderQty=3605.879219  maxMarketOrderQty=1201.95974 ...
SOLUSDC: status=Trading ...
   tickSize=0.01  minOrderQty=0.001  basePrecision=0.001  quotePrecision=0.00001  minOrderAmt=5  maxOrderQty=23678.51762  maxMarketOrderQty=7892.839208 ...

Q2 — ccxt.bybit load_markets() on hostname=bybit.eu
BTC/USDC: id=BTCUSDC spot=True active=True precision={'amount': 1e-06, 'price': 0.1} limits={'amount': {'min': 1e-06, 'max': 273.92085}, 'cost': {'min': 1.0, 'max': 1200000.0}} taker=0.001 maker=0.001
ETH/USDC: id=ETHUSDC ... precision={'amount': 0.0001, 'price': 0.01} limits={'amount': {'min': 0.0001, 'max': 3605.879219}, 'cost': {'min': 5.0, ...}}
SOL/USDC: id=SOLUSDC ... precision={'amount': 0.001, 'price': 0.01}  limits={'amount': {'min': 0.001, 'max': 23678.51762}, 'cost': {'min': 5.0, ...}}
BTC spot quotes in ccxt markets: ['EUR', 'PLN', 'USDC']

Q2 — Effective minimum order per pair (USDC), tickers on EU host
BTC/USDC: last=79120.7 minOrderQty*last=0.0791 USDC  minOrderAmt=1 USDC -> effective min = 1.0000 USDC; turnover24h=3081498.19 USDC
ETH/USDC: last=2485.9  minOrderQty*last=0.2486 USDC  minOrderAmt=5 USDC -> effective min = 5.0000 USDC; turnover24h=1084682.48 USDC
SOL/USDC: last=104.48  minOrderQty*last=0.1045 USDC  minOrderAmt=5 USDC -> effective min = 5.0000 USDC; turnover24h=1192985.03 USDC
```
Note : ccxt affiche `taker=maker=0.001` (valeur générique de `describe()`), **pas** les fees réelles du compte (0.10/0.25 % constatées par Bruno). Ne pas lire les fees depuis ccxt.

**Impact code.** Les constantes `MIN_ORDER_SIZE` de `binance/rest.py` peuvent être reprises telles quelles pour ETH/SOL ; BTC passe à `0.000001` (ou reste à `0.00001`, conservateur). Arrondir `qty` à `basePrecision` et `price` à `tickSize` (Bybit rejette `retCode 10001` "qty invalid" sinon) — ccxt `amount_to_precision`/`price_to_precision` le fait si `load_markets()` a été appelé sur le bon hostname. `riskParameters.priceLimitRatioX=0.5 %` : un LIMIT trop loin du marché est rejeté (à prendre en compte pour les grilles larges du grid ATR).

---

## Q3 — Liquidité et spread

**Réponse (3 mesures EU à 14:26, 16:28 et 18:28 UTC + 1 mesure global de comparaison).** Le carnet EU est **étroit et profond au niveau des murs de market-makers** : spread médian BTC 0.0013 %, ETH 0.005 %, SOL 0.019 % ; profondeur cumulée à ±0.1 % du mid de 2.6-4 M USDC (BTC), 0.8 M (ETH), 0.14-0.16 M (SOL). Un market BUY de 1 000 USDC est absorbé par le premier niveau sur les 3 paires (slippage 0 bps). En revanche, le **volume réellement traité** sur EU est faible : turnover24h ≈ 3.1 M USDC (BTC), 1.1 M (ETH), 1.2 M (SOL) contre 51.5 M USDC pour BTCUSDC global. Les hypothèses backtest actuelles (spread 0.02 %, slippage 0.01 %) sont **conservatrices** par rapport au spread observé ; on les garde (voire slippage 0.02 % pour couvrir les heures creuses, cf. écarts EU/global jusqu'à 38 bps en Q8).

Mesure 1 — 2026-09-07 14:26 UTC, `api.bybit.eu`, `limit=50` :

| Pair | best bid | best ask | spread % | depth bid ±0.1 % (USDC) | depth ask ±0.1 % (USDC) | levels bid/ask dans la bande | slip. market buy 1k USDC |
|---|---|---|---|---|---|---|---|
| BTC/USDC | 79107.7 | 79108.7 | 0.0013 | 3 020 662 | 4 008 395 | 14 / 13 | 0.0 bps |
| ETH/USDC | 2485.81 | 2486.00 | 0.0076 | 692 633 | 820 475 | 8 / 6 | 0.0 bps |
| SOL/USDC | 104.39 | 104.41 | 0.0192 | 160 542 | 142 065 | 7 / 8 | 0.0 bps |

Comparaison même instant (14:34 UTC) sur `api.bybit.com` (global), `limit=50` :

| Pair | best bid | best ask | spread % | depth bid ±0.1 % | depth ask ±0.1 % | levels | slip. 1k |
|---|---|---|---|---|---|---|---|
| BTC/USDC | 79010.0 | 79010.1 | 0.0001 | 113 262 (tronqué à 50 niveaux) | 90 503 (tronqué) | 50 / 50 | 0.0 bps |
| ETH/USDC | 2480.02 | 2480.03 | 0.0004 | 22 117 | 35 998 | 39 / 29 | 0.8 bps |
| SOL/USDC | 104.11 | 104.12 | 0.0096 | 5 129 | 3 706 | 10 / 10 | 1.7 bps |

Lecture : le global a un spread plus serré mais un carnet plus granulaire ; l'EU a peu de niveaux mais de gros blocs (ex. 25.28 BTC à 79 162.7). Les deux carnets ne sont **pas** identiques (prix mid différents de ~100 USDC à 8 min d'écart, structure différente) → confirmation que l'EU a son propre matching engine.

**Preuve (mesure 1, tronquée).**
```
Q3 measurement 1/3 at 2026-09-07T14:26:13 host=eu
-- limit=50
BTC/USDC  bid=79107.7 ask=79108.7 spread=0.0013% depth±0.1%: bid=3,020,662 ask=4,008,395 USDC (levels 14/13, covered True/True) slip(1k buy)=-0.000 bps
          raw: {"s": "BTCUSDC", "a": [["79108.7", "0.036351"], ["79111.7", "0.00422"], ["79124.7", "0.246485"], ["79125.5", "2.704493"], ["79125.6", "0.004674"], ["79141.3", "0.004907"], ["79150.1", "2.806132"], ["79150.4", "6.775498"], ["79157.1", "0.005151"], ["79162.7", "25.283393"] ...
ETH/USDC  bid=2485.81 ask=2486 spread=0.0076% depth±0.1%: bid=692,633 ask=820,475 USDC (levels 8/6, covered True/True) slip(1k buy)=0.000 bps
          raw: {"s": "ETHUSDC", "a": [["2486", "0.6035"], ["2486.9", "58.5227"], ["2486.91", "17.9036"], ["2487.31", "62.5414"], ["2487.34", "65.5789"], ["2487.85", "124.6993"], ...
SOL/USDC  bid=104.39 ask=104.41 spread=0.0192% depth±0.1%: bid=160,542 ask=142,065 USDC (levels 7/8, covered True/True) slip(1k buy)=0.000 bps
          raw: {"s": "SOLUSDC", "a": [["104.41", "116.256"], ["104.42", "27.027"], ["104.44", "28.373"], ["104.45", "387.765"], ["104.46", "278.886"], ...
```

Mesure 2 — 2026-09-07 16:28 UTC, `api.bybit.eu`, `limit=50` :

| Pair | best bid | best ask | spread % | depth bid ±0.1 % (USDC) | depth ask ±0.1 % (USDC) |
|---|---|---|---|---|---|
| BTC/USDC | 78827.4 | 78828.4 | 0.0013 | 919 031 | 3 963 430 |
| ETH/USDC | 2471.86 | 2471.91 | 0.0020 | 809 506 | 890 425 |
| SOL/USDC | 103.50 | 103.52 | 0.0193 | 159 647 | 179 318 |

Mesure 3 — 2026-09-07 18:28 UTC, `api.bybit.eu`, `limit=50` :

| Pair | best bid | best ask | spread % | depth bid ±0.1 % (USDC) | depth ask ±0.1 % (USDC) |
|---|---|---|---|---|---|
| BTC/USDC | 79138.2 | 79147.5 | 0.0118 | 2 593 310 | 3 947 573 |
| ETH/USDC | 2489.44 | 2489.57 | 0.0052 | 804 493 | 841 701 |
| SOL/USDC | 103.70 | 103.71 | 0.0096 | 304 859 | 144 558 |

Synthèse des 3 mesures EU (`bybit_q3_orderbook.py --summary`, `limit=50`) :
```
host    pair      limit  n  spread% med  spread% max  bid depth med  ask depth med  slip1k bps med
eu      BTC/USDC     50  3       0.0013       0.0118      2,593,310      3,963,430           0.000
eu      ETH/USDC     50  3       0.0052       0.0076        804,493        841,701           0.000
eu      SOL/USDC     50  3       0.0192       0.0193        160,542        144,558           0.000
global  BTC/USDC     50  1       0.0001       0.0001        113,262         90,503          -0.000
global  ETH/USDC     50  1       0.0004       0.0004         22,117         35,998           0.814
global  SOL/USDC     50  1       0.0096       0.0096          5,129          3,706           1.706
```
Spread médian EU : BTC 0.0013 % (max 0.012 %), ETH 0.005 %, SOL 0.019 % ; profondeur ±0.1 % médiane : BTC 2.6 M / 4.0 M USDC, ETH 0.80 M / 0.84 M, SOL 0.16 M / 0.14 M ; slippage d'un market buy de 1 000 USDC = 0 bps sur les 3 paires aux 3 mesures. La bande ±0.1 % a toujours été couverte avec moins de 15 niveaux. La profondeur bid BTC a varié de 0.9 M à 3.0 M entre les mesures (murs de market-makers mobiles) — c'est le point à surveiller pour des ordres > 50 k USDC, hors périmètre du bot (capital ≈ 1 k).

**Impact code.** `ExchangeFees.bybit_defaults(maker=0.0010, taker=0.0025, spread=0.0002, slippage=0.0002)` (voir section Constantes). Le format du carnet v5 est `{"s","b":[[price,qty],…],"a":[[price,qty],…],"ts","u","seq"}` (clés courtes, tri bid desc / ask asc) ; `limit` max 200 en spot.

---

## Q4 — Profondeur des données historiques

**Réponse.** Sur `api.bybit.eu`, l'historique kline commence le **2025-06-11** pour les 3 paires et les 7 intervalles (≈ 15 mois, ≈ 2.5 M candles au total, 0 gap sur le 1h). Sur `api.bybit.com` (global), BTC/ETH commencent le **2021-12-09** et SOL le **2021-12-23** (≈ 4.7 ans, ≈ 9.6 M candles, 0 gap 1h) — mais ce n'est **pas** le même carnet que l'EU. Bybit ne publie **aucun dump kline spot** : `public.bybit.com/spot/{SYMBOL}/` contient des dumps de **trades** (tick) mensuels (2022-11 → 2024) puis quotidiens, et `kline_for_metatrader4/` ne couvre que 23 perp USDT. Import complet EU via REST : 2 532 appels de 1 000 → ~15 min séquentiel (≈ 51 s au `rateLimit` ccxt de 20 ms, en pratique ~350 ms/appel).

`api.bybit.eu` — première candle (UTC) et nombre estimé :

| Pair | 1 | 5 | 15 | 60 | 240 | D | W |
|---|---|---|---|---|---|---|---|
| BTC/USDC | 2025-06-11 09:20 (652 628) | 2025-06-11 09:20 (130 526) | 2025-06-11 09:15 (43 509) | 2025-06-11 09:00 (10 878) | 2025-06-11 08:00 (2 720) | 2025-06-11 (454) | 2025-06-09 (66) |
| ETH/USDC | 2025-06-11 09:55 (652 593) | 2025-06-11 09:55 (130 519) | 2025-06-11 09:45 (43 507) | 2025-06-11 09:00 (10 878) | 2025-06-11 08:00 (2 720) | 2025-06-11 (454) | 2025-06-09 (66) |
| SOL/USDC | 2025-06-11 10:30 (652 558) | 2025-06-11 10:30 (130 512) | 2025-06-11 10:30 (43 504) | 2025-06-11 10:00 (10 877) | 2025-06-11 08:00 (2 720) | 2025-06-11 (454) | 2025-06-09 (66) |

`api.bybit.com` — première candle :

| Pair | 1 | 5 | 15 | 60 | 240 | D | W |
|---|---|---|---|---|---|---|---|
| BTC/USDC | 2021-12-09 09:56 (2 495 792) | 2021-12-09 09:55 (499 159) | 2021-12-09 09:45 (166 387) | 2021-12-09 09:00 (41 598) | 2021-12-09 08:00 (10 400) | 2021-12-09 (1 734) | 2021-12-06 (249) |
| ETH/USDC | 2021-12-09 10:04 (2 495 784) | 2021-12-09 10:00 (499 158) | 2021-12-09 10:00 (166 386) | 2021-12-09 10:00 (41 597) | 2021-12-09 08:00 (10 400) | 2021-12-09 (1 734) | 2021-12-06 (249) |
| SOL/USDC | 2021-12-23 03:53 (2 475 995) | 2021-12-23 03:50 (495 200) | 2021-12-23 03:45 (165 067) | 2021-12-23 03:00 (41 268) | 2021-12-23 00:00 (10 318) | 2021-12-23 (1 720) | 2021-12-20 (247) |

**Preuve.**
```
Q4.a — kline query semantics (proof)
start=2017-01-01, limit=3 → {"retCode": 0, "result": {"category": "spot", "symbol": "BTCUSDC", "list": [["1749639600000", "109720.1", "109720.1", "109298", "109298", "0.00002", "2.18596"], ["1749636000000", "109720.1", "109720.1", "109720.1", "109720.1", "0", "0"], ["1749632400000", "109720.1", ... "0", "0"]]}}
→ list is DESCENDING; with start only, Bybit returns candles from `start` onward.
→ row format: [startTime(ms), open, high, low, close, volume(base), turnover(quote)]

TOTAL eu:     ≈2,522,209 candles, 2532 API calls of 1000 → ≥51s at ccxt rateLimit 20 ms; realistic sequential ≈ 14.8 min at ~350 ms/call
TOTAL global: ≈9,620,442 candles, 9632 API calls of 1000 → ≥193s at ccxt rateLimit 20 ms; realistic sequential ≈ 56.2 min

Q4.c — gap check, interval 60, full history on https://api.bybit.eu
BTC/USDC  candles=10,878 expected=10,878 missing=0 n_gaps=0 calls=11 first=2025-06-11T09:00:00+00:00 last=2026-09-07T14:00:00+00:00
ETH/USDC  candles=10,878 expected=10,878 missing=0 n_gaps=0 calls=11
SOL/USDC  candles=10,877 expected=10,877 missing=0 n_gaps=0 calls=11
(global : 41,598 / 41,597 / 41,268 candles, 0 gap)

Q4.d — public.bybit.com downloadable dumps
root dirs: ['kline_for_metatrader4/', 'premium_index/', 'spot_index/', 'trading/', 'spot/']
spot/ has 1055 symbol dirs; our pairs present: ['BTCUSDC', 'ETHUSDC', 'SOLUSDC']
  BTCUSDC: 1443 files, first=['BTCUSDC-2022-11.csv.gz', 'BTCUSDC-2022-12.csv.gz'], last=['BTCUSDC_2026-09-05.csv.gz', 'BTCUSDC_2026-09-06.csv.gz']
  sample BTCUSDC_2026-09-06.csv.gz: ['id,timestamp,price,volume,side,rpi', '1,1788652801145,79845.8,0.00027,sell,0', ...]
  → these are TRADE (tick) dumps, not klines. kline_for_metatrader4/: 23 dirs, USDC dirs: []
```
Remarque : les toutes premières candles EU (2025-06-11) ont `volume=0` (marché ouvert sans trade) — le REST renvoie donc des candles "plates" plutôt que des trous ; le script d'import doit les accepter. Les dumps trades de `public.bybit.com/spot/` sont ceux du global (commencent 2022-11), pas de l'EU.

**Impact code.** Nouveau script `scripts/bybit_kline_import.py` sur le modèle de `binance_vision_import.py` mais **REST paginé** (`start` + `limit=1000`, avancer de `last_start + interval`), batch d'insert 1000 rows, `exchange='bybit'`, timestamp DB = `startTime + interval` (période-fin, cf. Q5). La pagination `--days` du collector existant est compatible. Le DB check de `CLAUDE.md` (`SELECT exchange, COUNT(*)`) affichera une 3e ligne `bybit: ~2,500,000`.

---

## Q5 — WebSocket v5 public

**Réponse.** URL EU : `wss://stream.bybit.eu/v5/public/spot` (même protocole que `stream.bybit.com`). Subscribe dynamique par message JSON, **max 10 `args` par requête** (erreur `"args size >10"` sinon) — les 24 topics du projet (21 klines + 3 tickers) passent en 3 requêtes sur **une seule connexion**. Kline : `data[0]` avec `start`/`end` en ms, `end = start + interval − 1 ms` → **`end` est inclusif**, exactement comme le `T` de Binance : la règle DB reste `timestamp = end + 1 ms` (= `start + interval`), les données Bybit s'alignent donc sans conversion sur les timestamps Binance existants. `confirm: true` marque la clôture (équivalent `k.x`). Ping : `{"op":"ping"}` toutes les 20 s, réponse `{"success":true,"ret_msg":"pong","op":"ping","conn_id":…,"req_id":…}`. Pas de coupure documentée à 24 h (Binance) ; non mesurable en 1 jour — garder le reconnect préventif à 23 h par sécurité.

Mapping intervalles :

| projet (min) | 1 | 5 | 15 | 60 | 240 | 1440 | 10080 |
|---|---|---|---|---|---|---|---|
| Bybit | `1` | `5` | `15` | `60` | `240` | `D` | `W` |

Topics : `kline.{interval}.{SYMBOL}` (ex. `kline.60.BTCUSDC`, `kline.D.ETHUSDC`), `tickers.{SYMBOL}`. Symbole = `pair.replace("/", "")` comme sur Binance.

**Preuve — subscribe / limites / ping (`bybit_q5_ws_capture.py --mode limits`, stream.bybit.eu).**
```
subscribe with 12 args → [{"success": false, "ret_msg": "args size >10", "conn_id": "d97jphrgig3od7574usg-6a3m1", "req_id": "many", "op": "subscribe"}]
subscribe invalid symbol → [{"success": false, "ret_msg": "Invalid symbol :[kline.1.NOPEUSDC]", ...}]
subscribe invalid interval → [{"success": false, "ret_msg": "Invalid kline type :[kline.7.BTCUSDC]", ...}]
24 project topics in chunks of 10 → acks: [{"success": true, "ret_msg": "subscribe", "req_id": "chunk0", "op": "subscribe"}, {... "req_id": "chunk10" ...}, {... "req_id": "chunk20" ...}]
unsubscribe → [{"success": true, "ret_msg": "unsubscribe", "req_id": "unsub", "op": "unsubscribe"}]
ping → [{"success": true, "ret_msg": "pong", "conn_id": "d97jphrgig3od7574usg-6a3m1", "req_id": "p1", "op": "ping"}]
duplicate subscribe → []   (aucun ack, aucun doublon de flux)
```

Payloads exacts :
```json
{"req_id": "audit-1", "op": "subscribe", "args": ["kline.1.BTCUSDC", "tickers.BTCUSDC"]}
{"req_id": "ping-1788791699", "op": "ping"}
```

**Preuve — capture de 5 min sur `wss://stream.bybit.eu/v5/public/spot`, `kline.1.BTCUSDC` + `tickers.BTCUSDC` (14:31 → 14:36 UTC).**
```
messages by topic/op: {'op:subscribe': 1, 'kline.1.BTCUSDC': 31, 'tickers.BTCUSDC': 22, 'op:ping': 14}
kline msgs: 31 (confirm=true: 5, confirm=false: 26)
kline fields: ['close', 'confirm', 'end', 'high', 'interval', 'low', 'open', 'start', 'timestamp', 'turnover', 'volume']
  start=1788791460000 (14:31:00) end=1788791519999 (14:31:59.999) end-start=59999 ms confirm=False timestamp=1788791461155
  start=1788791460000 (14:31:00) end=1788791519999 (14:31:59.999) end-start=59999 ms confirm=True  timestamp=1788791520154
  start=1788791520000 (14:32:00) end=1788791579999 (14:32:59.999) end-start=59999 ms confirm=True  timestamp=1788791580155
→ end - start = interval - 1 ms ⇒ `end` is INCLUSIVE (last ms), same convention as Binance `T`.
  confirm=true received at 14:32:00.184 = 185 ms after candle end   (global : ~1 020 ms)
  confirm=true received at 14:33:00.186 = 187 ms after candle end
  next kline msg after confirm: start=14:32:00 confirm=False
ticker msgs: 22; types: ['snapshot']   (global sur 90 s : 133 tickers, 38 klines)
```

3 messages bruts (EU) :
```json
{"success": true, "ret_msg": "subscribe", "conn_id": "d97jp8pe6qldg79a2p9g-5k9p5", "req_id": "audit-1", "op": "subscribe"}

{"type": "snapshot", "topic": "kline.1.BTCUSDC", "data": [{"start": 1788791460000, "end": 1788791519999, "interval": "1", "open": "79050", "close": "79050.1", "high": "79050.1", "low": "79050", "volume": "0.000012", "turnover": "0.9486012", "confirm": false, "timestamp": 1788791461155}], "ts": 1788791461155}

{"type": "snapshot", "topic": "kline.1.BTCUSDC", "data": [{"start": 1788791460000, "end": 1788791519999, "interval": "1", "open": "79050", "close": "79036.9", "high": "79061.3", "low": "79036.9", "volume": "0.773761", "turnover": "61165.4975707", "confirm": true, "timestamp": 1788791520154}], "ts": 1788791520154}
```
Ticker et pong (EU) :
```json
{"topic": "tickers.BTCUSDC", "ts": 1788791461070, "type": "snapshot", "cs": 18248946678, "data": {"symbol": "BTCUSDC", "lastPrice": "79050.1", "highPrice24h": "80535", "lowPrice24h": "79023.3", "prevPrice24h": "79626.9", "volume24h": "38.764377", "turnover24h": "3087626.5845112", "price24hPcnt": "-0.0072", "usdIndexPrice": ""}}
{"success": true, "ret_msg": "pong", "conn_id": "d97jphrgig3od7574usg-6a3m1", "req_id": "p1", "op": "ping"}
```
Observations : (a) le pong arrive avec `op: "ping"` et `ret_msg: "pong"` (pas `op: "pong"`) ; (b) les messages kline ne sont poussés **qu'en cas de trade** (31 messages en 5 min sur EU, dont 26 mises à jour intra-candle — sur global 38 en 90 s) : le watchdog de flux de `binance/ws.py` doit être calibré sur l'ensemble des topics, pas sur un seul symbole 1m ; (c) la candle confirmée arrive ~185 ms après `end` sur EU ; (d) `usdIndexPrice` est vide sur EU ; (e) `volume` en base, `turnover` en quote, pas de `trades_count`.

**Ping/pong — comportement si absent (test de 15 min sans ping, `--mode noping`).**
```
Q5 no-ping test on wss://stream.bybit.eu/v5/public/spot: subscribe, never send ping, wait up to 900s
connection still alive after 900s without client ping (84 msgs) — closed by us. close_code=1000 close_reason=''
```
Le serveur **n'a pas coupé** la connexion en 15 min sans ping applicatif (la doc recommande 20 s, sans préciser de délai de coupure). Le ping reste obligatoire dans le connecteur : c'est le seul moyen de détecter une connexion zombie (le bug déjà rencontré sur Binance), et l'absence de pong sous ~10 s doit déclencher le `_force_disconnect_and_reconnect` existant.

**Limites (doc Bybit v5, non contredites par les tests)** : 10 args par requête `subscribe` (vérifié), pas de limite documentée de topics par connexion (24 topics acceptés), 500 connexions / 5 min par IP, `args` cumulés ≤ 21 000 caractères par connexion. Durée de vie : aucune coupure à 24 h documentée (contrairement à Binance) — non mesurable dans le cadre de l'audit ; conserver `_PREVENTIVE_RECONNECT_SECONDS = 23 h`.

**Impact code.** `BybitWebSocketClient` clone de `BinanceWebSocketClient` : (1) URL + subscribe `{"op":"subscribe","args":[…]}` par lots de 10 ; (2) parse `topic.startswith("kline.")` → `data[0]`, `is_complete = confirm`, `timestamp = end + 1 ms`, `volume` en base, `turnover` en quote (VWAP calculable = turnover/volume, contrairement à Binance), pas de `trades_count` ; (3) ping applicatif `{"op":"ping"}` toutes les 20 s (les frames ping WebSocket natifs ne suffisent pas d'après la doc) + watchdog existant ; (4) le message `subscribe` ack (`op` sans `topic`) et le pong doivent être ignorés par le parseur ; (5) `tickers.*` : `type=snapshot` puis `delta` en dérivés, **snapshot à chaque message en spot** (observé), champ `lastPrice`.

---

## Q6 — Ordres (lecture seule, documentation pour B1)

**Réponse.** Spot v5 supporte `orderType` Limit / Market, `timeInForce` GTC (défaut) / IOC / FOK / **PostOnly** (PostOnly est un `timeInForce`, pas un flag), stop via `triggerPrice` + `orderFilter=StopOrder`, `orderLinkId` (client id, ≤ 36 chars, unique) via le param ccxt `clientOrderId`. `orderId` Bybit = chaîne numérique (~19 chiffres). Statut : `GET /v5/order/realtime` (ordres ouverts ; ccxt `fetch_order` retombe sur `/v5/order/history` pour les ordres clos), annulation : `POST /v5/order/cancel` (`orderId` **ou** `orderLinkId`). Les statuts Bybit (`New`, `PartiallyFilled`, `Filled`, `Cancelled`, `Rejected`, `PartiallyFilledCanceled`) sont mappés par ccxt sur `open/closed/canceled/rejected`.

**Market BUY : `qty` en base ou en quote ?** Bybit spot accepte les deux, le champ `marketUnit` (`baseCoin` | `quoteCoin`) le précise ; **sans `marketUnit`, un Market BUY spot interprète `qty` en quote (USDC)** (comportement historique de Bybit, équivalent `quoteOrderQty` Binance). ccxt 4.5.34 avec `createMarketBuyOrderRequiresPrice=False` (défaut bybit) :
- `create_order("BTC/USDC","market","buy", 0.001)` → `{"marketUnit":"baseCoin","qty":"0.001"}` ✅ base, comme le code Binance actuel.
- `create_order("BTC/USDC","market","buy", 0.001, 79000)` → `{"qty":"79"}` **sans `marketUnit`** → 79 USDC de quote ! ⚠️ Ne jamais passer `price` à un market order Bybit (le connecteur Binance ne le fait pas, à conserver).
- `params={"cost": 100}` → `{"qty":"100"}` (quote) — équivalent explicite de `quoteOrderQty`.
- Market SELL → toujours `marketUnit=baseCoin`.

**Preuve (`ccxt.bybit.create_order_request`, aucun envoi).**
```
has.createOrder=True createMarketBuyOrderWithCost=True createPostOnlyOrder=True createStopOrder=True editOrder=True cancelOrder=True fetchOrder=True fetchOpenOrders=True fetchMyTrades=True
options: {'createMarketBuyOrderRequiresPrice': False, 'defaultType': 'spot', 'recvWindow': 5000, 'adjustForTimeDifference': False, 'brokerId': 'CCXT'}
private.GET  v5/order/realtime  cost=5 | private.POST v5/order/create cost=2.5 | private.POST v5/order/cancel cost=2.5 | private.POST v5/order/cancel-all cost=50

market BUY, amount in BASE (0.001 BTC)
   → {"symbol": "BTCUSDC", "side": "Buy", "orderType": "Market", "category": "spot", "marketUnit": "baseCoin", "qty": "0.001"}
market BUY, amount + price → ccxt computes cost
   → {"symbol": "BTCUSDC", "side": "Buy", "orderType": "Market", "category": "spot", "qty": "79"}
market BUY with explicit cost=100 USDC
   → {"symbol": "BTCUSDC", "side": "Buy", "orderType": "Market", "category": "spot", "qty": "100"}
market SELL 0.001 BTC
   → {"symbol": "BTCUSDC", "side": "Sell", "orderType": "Market", "category": "spot", "marketUnit": "baseCoin", "qty": "0.001"}
limit BUY 0.001 @ 79000 (GTC default)
   → {"symbol": "BTCUSDC", "side": "Buy", "orderType": "Limit", "price": "79000", "category": "spot", "qty": "0.001"}
limit BUY postOnly
   → {"symbol": "BTCUSDC", "side": "Buy", "orderType": "Limit", "timeInForce": "PostOnly", "price": "79000", "category": "spot", "qty": "0.001"}
limit SELL IOC → {... "timeInForce": "IOC" ...}      limit SELL FOK → {... "timeInForce": "FOK" ...}
limit BUY with clientOrderId (→ orderLinkId)
   → {"symbol": "BTCUSDC", "side": "Buy", "orderType": "Limit", "orderLinkId": "krakenbot-grid-btc-000123", "price": "79000", "category": "spot", "qty": "0.001"}
market SELL with stop trigger (stop-loss style)
   → {"symbol": "BTCUSDC", "side": "Sell", "orderType": "Market", "orderFilter": "StopOrder", "category": "spot", "marketUnit": "baseCoin", "qty": "0.001", "triggerPrice": "75000"}

Q6.e — unauthenticated probes proving the endpoints exist on api.bybit.eu
  GET /v5/order/realtime  HTTP 200 → {"retCode": 10001, "retMsg": "Request parameter error: apiKey is missing", ...}
  GET /v5/order/history   HTTP 200 → {"retCode": 10001, ...}
  GET /v5/execution/list  HTTP 200 → {"retCode": 10001, ...}
  POST /v5/order/cancel   HTTP 200 → {"retCode":10001,"retMsg":"Request parameter error: apiKey is missing", ...}
```
Note : Bybit renvoie **HTTP 200 avec `retCode != 0`** pour la plupart des erreurs métier (ccxt lève `ExchangeError`/`InvalidOrder` en fonction du `retCode`). Le mapping d'exceptions du connecteur (`InsufficientBalanceError` ← `retCode 170131`, `OrderCancelError` ← `170213` "order not exists"…) est à écrire dans B1.

**Impact code.** `BybitRestClient.place_market_order` : appeler `create_order(pair, "market", side, amount)` **sans price**. `place_limit_order` : `params={"timeInForce": "PostOnly"}` recommandé pour garantir le maker 0.10 % (rejet si le prix croise — comportement à gérer : re-coter plutôt que taker). `expires_in_seconds` : pas de GTD en spot Bybit → conserver l'expiration client-side de `order_manager`. Fee asset : pas d'équivalent BNB ; les fees sont prélevées dans la monnaie reçue (`execFee` dans `/v5/execution/list`). Type de compte : `accountType=UNIFIED` (UTA) — à confirmer avec les clés.

---

## Q7 — Rate limits

**Réponse.** Les headers `X-Bapi-Limit`, `X-Bapi-Limit-Status`, `X-Bapi-Limit-Reset-Timestamp` ne sont renvoyés que sur les endpoints **privés** (non capturables sans clés — voir Q1) ; aucun header de limite sur les endpoints publics. Un burst de **120 appels `kline` concurrents en 1.4 s** sur `api.bybit.eu` est passé sans aucun `10006`/`403` (doc : ~600 req / 5 s par IP sur les endpoints marché). ccxt applique un token-bucket global `rateLimit=20 ms` × coût par endpoint (kline/orderbook/tickers = 5 → 10 req/s ; `order/create`/`cancel` = 2.5 → 20 req/s ; `wallet-balance` = 1). Doc privés : 10 req/s par UID par défaut (20/s sur `order/create` spot, 50/s VIP).

Charge KrakenBot : le collector consomme **0 REST en régime** (21 klines + 3 tickers sur une connexion WS) et ~25-100 appels au démarrage/backfill ; le trader place quelques ordres/minute au pire + polling `order_manager` (< 1 req/s). Marge > 95 % sur toutes les limites. Un import historique complet EU (2 532 appels) reste sous la limite publique même en parallèle ×8.

**Preuve.**
```
Q7.a — rate-limit headers on public endpoints (api.bybit.eu)
  /v5/market/time         HTTP 200 retCode=0 headers=(no X-Bapi-Limit headers)
  /v5/market/kline        HTTP 200 retCode=0 headers=(no X-Bapi-Limit headers)
  /v5/market/orderbook    HTTP 200 retCode=0 headers=(no X-Bapi-Limit headers)
  /v5/market/tickers ... /v5/market/instruments-info ... /v5/market/recent-trade : idem

Q7.b — burst test: 120 concurrent GET /v5/market/kline (limit=1000) on api.bybit.eu
  120 requests in 1.43s → outcomes {(200, 0): 120}

Q7.d — ccxt.bybit rate limiting model
  ex.rateLimit = 20 ms between weighted units → 50 units/s
  cost public.GET  v5/market/kline = 5 | v5/market/orderbook = 5 | v5/market/tickers = 5 | v5/market/instruments-info = 5
  cost private.GET v5/account/wallet-balance = 1 | v5/order/realtime = 5 | v5/execution/list = 5
  cost private.POST v5/order/create = 2.5 | v5/order/cancel = 2.5
```
**Non tranché.** Valeurs réelles de `X-Bapi-Limit` par endpoint privé pour le compte de Bruno (dépend du niveau VIP) : le script `bybit_q7_ratelimits.py` les capture (Q7.c) dès que les clés sont dans `.env`.

**Impact code.** `enableRateLimit=True` suffit (comme Binance). Garder le retry/backoff existant sur `RateLimitError` et mapper `retCode 10006` (+ HTTP 403 en cas de ban IP temporaire) dessus.

---

## Q8 — Écart de prix Binance vs Bybit

**Réponse.** Sur 90 jours (2026-06-09 → 2026-09-07), 2 161 closes 1h BTC/USDC alignés (timestamp d'ouverture) :

| Comparaison | n | corr. close | corr. rendements 1h | écart moyen (bps) | \|écart\| moyen | \|écart\| médian | p95 | p99 | max (bps) | > 10 bps | > 25 bps |
|---|---|---|---|---|---|---|---|---|---|---|---|
| Bybit **global** vs Binance | 2161 | 0.999999 | 0.9992 | −0.02 | 0.89 | 0.68 | 2.54 | 3.67 | 7.11 | 0.0 % | 0.0 % |
| Bybit **EU** vs Binance | 2161 | 0.999989 | 0.9921 | −0.03 | 2.28 | 1.29 | 7.26 | 18.09 | 38.33 | 2.7 % | 0.6 % |
| Bybit EU vs Bybit global | 2161 | 0.999989 | 0.9923 | −0.01 | 2.30 | 1.32 | 7.38 | 18.37 | 37.96 | 2.7 % | 0.6 % |

Aucun biais systématique (écart moyen ≈ 0). Le bruit EU (jusqu'à 38 bps, la nuit UTC : 01:00-02:00) vient de la faible activité EU (volume 1h médian 2.8 BTC vs 10 BTC global), pas d'un prix structurellement différent — les écarts se résorbent à la candle suivante. **Décision confirmée : backtester sur les données Binance (8.7 M rows, 9 ans) avec les fees Bybit.** L'historique EU (15 mois) sert de contrôle out-of-sample et de source pour le live, pas de base de backtest.

⚠️ **Source Binance = API publique `api.binance.com/api/v3/klines`, pas la DB** : le tunnel SSH vers Hetzner était injoignable pendant tout l'audit (`ssh: connect to host 77.42.90.102 port 41922: Operation timed out`, avec et sans sandbox ; `autossh` relancé sans succès). Ce sont les mêmes candles que celles importées depuis Binance Vision (même source de marché), donc la conclusion tient ; le script `bybit_q8_price_diff.py` utilise automatiquement la DB (`exchange='binance'`, timestamps période-fin convertis) dès que `localhost:5433` répond.

**Preuve.**
```
Q8 — BTC/USDC 1h closes, 90 days: 2026-06-09T13:00:00+00:00 → 2026-09-07T13:00:00+00:00
  bybit[global] 2161 candles in 3 calls
  bybit[eu] 2161 candles in 3 calls
  DB unavailable: OSError: Multiple exceptions: [Errno 61] Connect call failed ('127.0.0.1', 5433) ...
  binance[API] 2162 candles, 2026-06-09T13:00:00+00:00 → 2026-09-07T14:00:00+00:00
  [bybit GLOBAL vs binance] n=2161 close_corr=0.999999 ret_corr(1h)=0.9992 mean=-0.02 bps |mean|=0.89 median=0.68 p95=2.54 p99=3.67 max=7.11 bps at 2026-08-24T14:00:00+00:00 (binance 79495.14 vs bybit 79438.6) >10bps: 0.0% >25bps: 0.0%
  [bybit EU vs binance]     n=2161 close_corr=0.999989 ret_corr(1h)=0.9921 mean=-0.03 bps |mean|=2.28 median=1.29 p95=7.26 p99=18.09 max=38.33 bps at 2026-08-21T01:00:00+00:00 (binance 75108.54 vs bybit 75396.4) >10bps: 2.7% >25bps: 0.6%
     2026-08-21T01:00:00+00:00 +38.33 bps  binance=75108.54 bybit=75396.4
     2026-09-02T01:00:00+00:00 -35.96 bps  binance=76988.54 bybit=76711.7
     2026-09-02T02:00:00+00:00 -33.10 bps  binance=77298.29 bybit=77042.4
  zero-volume 1h candles: EU=0/2161  global=0/2161
  median 1h base volume: EU=2.778 BTC  global=10.005 BTC
```

**Impact code.** Aucun sur le backtest engine. Pour le live, ajouter `slippage=0.0002` dans les hypothèses Bybit EU pour couvrir les fills nocturnes ; les stops MARKET peuvent se déclencher sur des mèches EU absentes de Binance (≤ 40 bps) — le crash protector du risk manager doit tolérer ce bruit.

---

## Constantes proposées pour B1

```python
# connectors/bybit/rest.py — filtres api.bybit.eu (instruments-info, 2026-09-07)
MIN_ORDER_SIZE: dict[str, Decimal] = {          # = minOrderQty = basePrecision (qtyStep)
    "BTC/USDC": Decimal("0.000001"),
    "ETH/USDC": Decimal("0.0001"),
    "SOL/USDC": Decimal("0.001"),
}
LOT_SIZES = MIN_ORDER_SIZE                       # qtyStep identique au min sur les 3 paires
TICK_SIZES: dict[str, Decimal] = {
    "BTC/USDC": Decimal("0.1"),
    "ETH/USDC": Decimal("0.01"),
    "SOL/USDC": Decimal("0.01"),
}
MIN_NOTIONAL = Decimal("5")                      # minOrderAmt : 1 (BTC), 5 (ETH, SOL) → 5 partout
MAX_MARKET_ORDER_QTY = {"BTC/USDC": Decimal("91.30"), "ETH/USDC": Decimal("1201"), "SOL/USDC": Decimal("7892")}

# config/settings.py
class ExchangeFees(BaseModel):
    @classmethod
    def bybit_defaults(cls) -> ExchangeFees:
        """Bybit EU spot (compte vérifié, VIP0) : maker 0.10 %, taker 0.25 %.
        spread 0.02 % : conservateur vs 0.001-0.02 % observé (Q3).
        slippage 0.02 % : couvre les écarts EU/global nocturnes (Q8 p95 = 7 bps)."""
        return cls(maker=Decimal("0.0010"), taker=Decimal("0.0025"),
                   spread=Decimal("0.0002"), slippage=Decimal("0.0002"))

class BybitSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="BYBIT_")
    api_key: SecretStr
    api_secret: SecretStr
    hostname: str = "bybit.eu"                                   # ccxt option
    api_url: str = "https://api.bybit.eu"
    ws_url: str = "wss://stream.bybit.eu/v5/public/spot"
    recv_window_ms: int = 5000
    account_type: str = "UNIFIED"

# WS
BYBIT_INTERVAL_MAP = {"1": 1, "5": 5, "15": 15, "60": 60, "240": 240, "D": 1440, "W": 10080}
WS_MAX_ARGS_PER_SUBSCRIBE = 10
WS_PING_INTERVAL_SECONDS = 20
```

---

## Différences Binance → Bybit qui touchent le code existant

| Composant | Ce qui change | Effort |
|---|---|---|
| `config/settings.py` | `BybitSettings` (hostname, urls, recv_window, account_type), `ExchangeFees.bybit_defaults()`, `exchange_name` accepte `"bybit"`, `.env.example` | 0.5 j |
| `connectors/exchange.py` | branche `bybit` dans `build_exchange_rest_client` / `build_exchange_ws_client` | 0.1 j |
| `connectors/bybit/rest.py` (clone de `binance/rest.py`) | `ccxt.bybit({"hostname": "bybit.eu", "options": {"defaultType": "spot", "adjustForTimeDifference": True}})` ; `params={"category": "spot"}` implicite via `defaultType` ; market BUY **sans price** ; LIMIT avec `timeInForce=PostOnly` optionnel ; `clientOrderId` → `orderLinkId` ; mapping `retCode` → exceptions ; `fetch_balance` sur `accountType=UNIFIED` ; pas de BNB ; fees dans `execFee` ; `fetch_ohlcv` identique (ccxt normalise en `[ts, o, h, l, c, v]`) | 2 j |
| `connectors/bybit/ws.py` (clone de `binance/ws.py`) | URL, `{"op":"subscribe","args":[...]}` par lots de 10, parse `kline.*` (`data[0]`, `confirm`, `end+1 ms`), `tickers.*` (`lastPrice`), ping applicatif 20 s, ignorer les acks `op`, reconnect préventif 23 h conservé | 1.5 j |
| `execution/order_manager.py` | statuts Bybit via ccxt (`open/closed/canceled/rejected`), `PartiallyFilledCanceled` ; expiration GTD reste client-side | 0.5 j |
| `scripts/bybit_kline_import.py` (nouveau) | import REST paginé `start`+`limit=1000`, `exchange='bybit'`, timestamp période-fin, batch 1000 ; pas de dumps CSV | 1 j |
| `scripts/backtest.py`, `run_p6/p7` | `--exchange binance --fees bybit` : les données restent Binance, seules les fees changent (`ExchangeFees.bybit_defaults()`) ; re-run des survivants P6/P7 | 0.5 j + temps machine |
| `strategies.yaml`, `main.py` | `exchange: bybit` ; aucune stratégie ne dépend de Binance (vérifier `use_bnb_for_fees`) | 0.2 j |
| `scripts/dashboard.py`, `collector` | filtre `exchange='bybit'` ; la DB garde `binance` pour l'historique | 0.3 j |
| Tests | fixtures kline/orderbook/ticker Bybit, tests de mapping `marketUnit`, `end+1 ms`, lots de 10 | 1 j |
| Déploiement (`skills/deployment.md`) | `.env` serveur : `EXCHANGE_NAME=bybit`, clés, IP whitelist Bybit = IP Hetzner | 0.2 j |

Total estimé B1-B3 : **~8 jours** hors re-backtests.

---

## Levées post-B0 (B1, 2026-09-08)

Clés `BYBIT_API_KEY` / `BYBIT_API_SECRET` ajoutées au `.env` local le 8 sept (clé « krakenbot_readonly »,
`readOnly=1`, `ips: ["*"]`, expire le 2026-12-08). Scripts Q1/Q6/Q7 relancés (`BYBIT_AUDIT_OUT=/tmp/bybit_audit_b1`,
JSON non versionnés car ils contiennent `userID`/`apiKey`).

| Question B0 | Réponse (api.bybit.eu, 2026-09-08) |
|---|---|
| Type de compte | **UTA** : `query-api` → `uta: "1"`, `unified: "0"` ; `wallet-balance?accountType=UNIFIED` → `retCode 0`, `accountType: "UNIFIED"` |
| Permissions | `Spot: ["SpotTrade"]`, `Wallet: [AccountTransfer, SubMemberTransfer]`, `Derivatives: [DerivativesTrade]`, `Exchange: [ExchangeHistory]` — mais **`readOnly: "1"`** (la clé ne peut pas écrire malgré `SpotTrade`) |
| IP whitelist | `ips: ["*"]` (aucune restriction) |
| Clé EU sur le global | **Refusée** : `api.bybit.com` → `retCode 10003` "API key is invalid" |
| Solde | `totalWalletBalance: "0"`, `coin: []` → **wallet vide** |
| Horloge | offset +93 ms, RTT 189 ms (EU) ; `adjustForTimeDifference=True` dans le client |
| Headers rate limit privés | `wallet-balance` → `X-Bapi-Limit: 50`, `X-Bapi-Limit-Status: 49`, `X-Bapi-Limit-Reset-Timestamp: <ms>` ; publics : aucun header, burst 60 klines / 1.45 s sans `10006` |
| Q6 lecture | `fetch_open_orders` / `fetch_my_trades` BTC/USDC → `[]` (compte neuf) ; bodies `create_order_request` identiques à B0 |
| `order/create` avec clé read-only | `retCode 10005` "Invalid API-key, IP, or permissions for action." → mappé `KrakenAPIError(reason=permission_denied)` |

**Non levé (bloqué par la clé read-only + wallet vide)** : rejet PostOnly réel (retCode vs statut
`Rejected`), `priceLimitRatioX` sur un LIMIT à −2 %, round-trip live PostOnly → status → cancel.
Procédure dans `skills/bybit.md` § « Levé en B1 » (`scripts/audit/bybit_b1_roundtrip.py --trade`).

### Round-trip B1 (`scripts/audit/bybit_b1_roundtrip.py --trade`, 2026-09-08 22:37 CEST)

```
1. Read-only (LIVE client)
markets loaded on bybit.eu: 133
BTC/USDC precision={'amount': 1e-06, 'price': 0.1} limits amount.min=1e-06 cost.min=1.0
balance (free): {} (wallet empty)
ticker: bid=78503.0 ask=78525.5 last=78525.5
  4h 2026-09-08T12:00:00+00:00 O=78436.4 C=78896.4 V=25.625817
  4h 2026-09-08T16:00:00+00:00 O=78896.4 C=78364.7 V=21.175206
  4h 2026-09-08T20:00:00+00:00 O=78364.7 C=78525.5 V=3.918441
open orders: []
stats: {'orders_placed': 0, 'orders_filled': 0, 'orders_failed': 0, 'api_calls': 5}

2. Paper round-trip (simulated fills, real ticker)
market BUY  0.000076 @ 78525.5 fee=0.01491984500 USDC
  balance: {'USDC': Decimal('994.01714215500'), 'BTC': Decimal('0.000076')}
limit SELL PostOnly(paper) -> pending id=paper-limit-7e3b3d82
  status: {'order_id': 'paper-limit-7e3b3d82', 'status': 'pending', 'filled': 0, 'amount': 0.000076, 'price': 82451.8}
  cancel: True
market SELL 0.000076 @ 78525.5 fee=0.01491984500 USDC
  balance: {'USDC': Decimal('999.97016031000'), 'BTC': Decimal('0.000000')}
  check: USDC == 1000 - fees -> True (expected 999.97016031000)

3. LIVE limit orders (real, cancelled/rejected — NEVER market)
3a. PostOnly BUY 0.000080 @ 74599.2 (-5 %)
    -> KrakenAPIError: Bybit refused the action (retCode 10005): the API key is read-only ...
3b. GTC BUY 0.000077 @ 76954.9 (-2 %, priceLimitRatioX probe)
    -> KrakenAPIError: ... retCode 10005 ...
3c. PostOnly BUY 0.000076 @ 78604.1 (above ask 78525.5)
    -> KrakenAPIError: ... retCode 10005 ...
open orders after run: []
stats: {'orders_placed': 3, 'orders_filled': 0, 'orders_failed': 3, 'api_calls': 6}
```

`BYBIT_INTEGRATION=1 pytest tests/test_connectors/test_bybit_rest_integration.py` : 4 passed
(filtres EU = skill, balance réelle, OHLCV 4h, paper round-trip), 1 skipped (`trade`).

### Protocole trade (`bybit_b1_roundtrip.py --trade --notional 6`, 2026-09-09 08:58 CEST) — BLOQUÉ côté compte

Schéma à 4 clés en place (`BYBIT_*` read-only, `BYBIT_TRADE_*` trade, commit `feat(bybit): dedicated
read-only vs trade API key pairs`). Sortie brute complète (identifiants masqués) :

```
==============================================================================
1. Read-only: load_markets / balance / ticker / OHLCV (LIVE client, read-only key)
==============================================================================
2026-09-09 08:58:11 [info     ] bybit_rest_initialized         account_type=UNIFIED has_api_key=<masked> hostname=bybit.eu key_role=readonly maker_fee=0.0010 mode=live taker_fee=0.0025
2026-09-09 08:58:14 [info     ] bybit_rest_markets_loaded      hostname=bybit.eu symbols=133
markets loaded on bybit.eu: 133
BTC/USDC precision={'amount': 1e-06, 'price': 0.1, 'cost': None, 'base': None, 'quote': None} limits={'leverage': {'min': 1.0, 'max': None}, 'amount': {'min': 1e-06, 'max': 273.92085}, 'price': {'min': None, 'max': None}, 'cost': {'min': 1.0, 'max': 1200000.0}}
2026-09-09 08:58:15 [info     ] [LIVE] get_balance             currencies=[]
balance (free): {} (wallet empty)
ticker: bid=79159.1 ask=79168.6 last=79161.8
2026-09-09 08:58:15 [debug    ] fetching_ohlcv                 limit=3 pair=BTC/USDC since=None timeframe=4h
2026-09-09 08:58:15 [info     ] ohlcv_fetched                  candles=3 first_timestamp='2026-09-08 20:00:00+00:00' interval=240 last_timestamp='2026-09-09 04:00:00+00:00' pair=BTC/USDC
  4h 2026-09-08T20:00:00+00:00 O=78364.7 C=78466.1 V=5.495427
  4h 2026-09-09T00:00:00+00:00 O=78466.1 C=78673.2 V=0.883565
  4h 2026-09-09T04:00:00+00:00 O=78673.2 C=79161.8 V=12.873742
2026-09-09 08:58:16 [info     ] [LIVE] get_open_orders         count=0
open orders: []
stats: {'orders_placed': 0, 'orders_filled': 0, 'orders_failed': 0, 'api_calls': 5}
2026-09-09 08:58:16 [info     ] bybit_rest_closed

==============================================================================
2. Paper round-trip (simulated fills, real ticker)
==============================================================================
2026-09-09 08:58:16 [info     ] bybit_rest_initialized         account_type=UNIFIED has_api_key=<masked> hostname=bybit.eu key_role=readonly maker_fee=0.0010 mode=paper taker_fee=0.0025
2026-09-09 08:58:16 [info     ] [PAPER] set_balance            amount=1000 currency=USDC
2026-09-09 08:58:16 [info     ] [PAPER] set_balance            amount=0 currency=BTC
2026-09-09 08:58:16 [debug    ] event_bus_no_subscribers       event_type=trade.order_filled
2026-09-09 08:58:16 [info     ] [PAPER] market_order_filled    amount=0.000075 fee=0.01484283750 pair=BTC/USDC price=79161.8 side=buy
market BUY  0.000075 @ 79161.8 fee=0.01484283750 USDC
  balance: {'USDC': Decimal('994.04802216250'), 'BTC': Decimal('0.000075')}
2026-09-09 08:58:16 [info     ] [PAPER] limit_order_pending    amount=0.000075 expires_at=2026-09-09T07:13:16.446054+00:00 order_id=paper-limit-ac8cee33 pair=BTC/USDC price=83119.9 side=sell
limit SELL PostOnly(paper) -> pending id=paper-limit-ac8cee33
  status: {'order_id': 'paper-limit-ac8cee33', 'status': 'pending', 'filled': Decimal('0'), 'amount': Decimal('0.000075'), 'price': Decimal('83119.9')}
2026-09-09 08:58:16 [info     ] [PAPER] order_cancelled        order_id=paper-limit-ac8cee33
2026-09-09 08:58:16 [debug    ] event_bus_no_subscribers       event_type=trade.order_cancelled
  cancel: True
2026-09-09 08:58:16 [debug    ] event_bus_no_subscribers       event_type=trade.order_filled
2026-09-09 08:58:16 [info     ] [PAPER] market_order_filled    amount=0.000075 fee=0.01484283750 pair=BTC/USDC price=79161.8 side=sell
market SELL 0.000075 @ 79161.8 fee=0.01484283750 USDC
  balance: {'USDC': Decimal('999.97031432500'), 'BTC': Decimal('0.000000')}
  check: USDC == 1000 - fees -> True (expected 999.97031432500)
2026-09-09 08:58:16 [info     ] bybit_rest_closed

==============================================================================
3. LIVE limit orders (real, cancelled/rejected — NEVER market, TRADE key)
==============================================================================
2026-09-09 08:58:16 [info     ] bybit_rest_initialized         account_type=UNIFIED has_api_key=<masked> hostname=bybit.eu key_role=trade maker_fee=0.0010 mode=live taker_fee=0.0025
2026-09-09 08:58:19 [info     ] bybit_rest_markets_loaded      hostname=bybit.eu symbols=133
2026-09-09 08:58:19 [info     ] [LIVE] get_balance             currencies=[]
key_role=trade  balance (free): {}
3a. PostOnly BUY 0.000079 @ 75203.7 (-5 %)
2026-09-09 08:58:20 [error    ] bybit_rest_limit_order_error   error='bybit {"retCode":10005,"retMsg":"Invalid API-key, IP, or permissions for action.","result":{},"retExtInfo":{},"time":1788937100116}' error_type=KrakenAPIError pair=BTC/USDC side=buy
    -> KrakenAPIError: Bybit refused the action (retCode 10005): the API key is read-only, lacks the Spot Trade permission, or the caller IP is not whitelisted. Create a key with readOnly=0 + Spot Trade on bybit.eu. Raw: bybit {"retCode":10005,"retMsg":"Invalid API-key, IP, or permissions for action.","result":{},"retExtInfo":{},"time":1788937100116} | Details: {'ret_code': 10005, 'reason': 'permission_denied'}
3b. GTC BUY 0.000077 @ 77578.5 (-2 %, priceLimitRatioX probe)
2026-09-09 08:58:20 [error    ] bybit_rest_limit_order_error   error='bybit {"retCode":10005,"retMsg":"Invalid API-key, IP, or permissions for action.","result":{},"retExtInfo":{},"time":1788937100683}' error_type=KrakenAPIError pair=BTC/USDC side=buy
    -> KrakenAPIError: Bybit refused the action (retCode 10005): the API key is read-only, lacks the Spot Trade permission, or the caller IP is not whitelisted. Create a key with readOnly=0 + Spot Trade on bybit.eu. Raw: bybit {"retCode":10005,"retMsg":"Invalid API-key, IP, or permissions for action.","result":{},"retExtInfo":{},"time":1788937100683} | Details: {'ret_code': 10005, 'reason': 'permission_denied'}
3c. PostOnly BUY 0.000075 @ 79247.8 (above ask 79168.6)
2026-09-09 08:58:21 [error    ] bybit_rest_limit_order_error   error='bybit {"retCode":10005,"retMsg":"Invalid API-key, IP, or permissions for action.","result":{},"retExtInfo":{},"time":1788937101458}' error_type=KrakenAPIError pair=BTC/USDC side=buy
    -> KrakenAPIError: Bybit refused the action (retCode 10005): the API key is read-only, lacks the Spot Trade permission, or the caller IP is not whitelisted. Create a key with readOnly=0 + Spot Trade on bybit.eu. Raw: bybit {"retCode":10005,"retMsg":"Invalid API-key, IP, or permissions for action.","result":{},"retExtInfo":{},"time":1788937101458} | Details: {'ret_code': 10005, 'reason': 'permission_denied'}
2026-09-09 08:58:21 [info     ] [LIVE] get_open_orders         count=0
2026-09-09 08:58:21 [info     ] [LIVE] get_open_orders         count=0
open orders after run: []  -> OK (empty)
2026-09-09 08:58:22 [info     ] [LIVE] get_balance             currencies=[]
balance (free) after run: {}
stats: {'orders_placed': 3, 'orders_filled': 0, 'orders_failed': 3, 'api_calls': 9}
2026-09-09 08:58:22 [info     ] bybit_rest_closed
```

**Verdict : les trois ordres (a) PostOnly −5 %, (b) LIMIT −2 %, (c) PostOnly au-dessus de l'ask sont
refusés avant d'atteindre le matching engine (`retCode 10005`), aucun ordre n'a été créé, `fetch_open_orders`
vide en fin de run.** `priceLimitRatioX` et la forme du rejet PostOnly restent donc **non levés**.

Diagnostic read-only (`scripts/audit/bybit_key_diag.py`, 2026-09-09 08:59 CEST) :

```
[readonly] query-api -> note=krakenbot_readonly readOnly="1" Spot=[SpotTrade] Wallet=[AccountTransfer, SubMemberTransfer] ips=["*"] uta="1" expiredAt=2026-12-08T20:13:39Z
[readonly] wallet-balance UNIFIED -> totalEquity=0 coins=[]
[readonly] coins-balance FUND -> [('USDC', '28.433268', '28.433268')]
[trade]    query-api -> note=krakenbot_trade    readOnly="1" Spot=[SpotTrade] Wallet=[] ips=["*"] uta="1" expiredAt=2026-12-08T20:24:12Z
[trade]    wallet-balance UNIFIED -> totalEquity=0 coins=[]
[trade]    coins-balance FUND -> PermissionDenied (pas de permission Account Transfer — normal pour une clé trade)
same key id? False
```

Deux causes, toutes deux côté compte Bybit :
1. **La clé `krakenbot_trade` est `readOnly=1`** (créée en « Read-Only » malgré la case Spot Trade) →
   `order/create` refusé (`10005`). À recréer/éditer en **Read-Write**, Spot Trade uniquement, sans withdraw.
2. **Les 28.43 USDC sont dans le wallet Funding**, pas dans l'Unified Trading Account (`totalEquity=0`).
   Les ordres spot puisent dans l'UTA → transfert interne Funding → Unified Trading requis (UI Bybit).
Une fois les deux corrigés : `poetry run python scripts/audit/bybit_key_diag.py` (attendu `readOnly="0"`
sur la clé trade et USDC dans `wallet-balance UNIFIED`), puis relancer le protocole `--trade`.

### Protocole trade — VALIDÉ (`bybit_b1_roundtrip.py --trade --notional 6`, 2026-09-09 09:31 CEST)

Préalables corrigés par l'humain : clé `krakenbot_trade` recréée en Read-Write (`readOnly="0"`, Spot Trade,
sans withdraw, `ips=["*"]`, expire 2026-12-09) ; 28.43 USDC transférés dans l'Unified Trading Account.

Premier run (09:30) : les ordres (a) et (b) ont été **créés** mais le client a levé `OrderExecutionError`
sur le `fetch_order` post-création (ccxt bybit exige `params={"acknowledged": True}` pour `fetchOrder`,
sinon il lève un avertissement) ; le filet de sécurité a annulé les deux ordres résiduels. Bug corrigé
(`fix(bybit): acknowledge ccxt fetchOrder lookback`), l'historique `/v5/order/history` montre pour ce run :
`2300181859310924800` PostOnly −5 % → `Cancelled/CancelByUser`, `2300181861559071744` GTC −2 % →
`Cancelled/CancelByUser`, `2300181867775030272` PostOnly > ask → **`Rejected`, `rejectReason=EC_PostOnlyWillTakeLiquidity`**, `cumExecQty=0`.

Second run (09:31, client corrigé), sortie brute complète (identifiants masqués) :

```
==============================================================================
1. Read-only: load_markets / balance / ticker / OHLCV (LIVE client, read-only key)
==============================================================================
2026-09-09 09:31:43 [info     ] bybit_rest_initialized         account_type=UNIFIED has_api_key=<masked> hostname=bybit.eu key_role=readonly maker_fee=0.0010 mode=live taker_fee=0.0025
2026-09-09 09:31:46 [info     ] bybit_rest_markets_loaded      hostname=bybit.eu symbols=133
markets loaded on bybit.eu: 133
BTC/USDC precision={'amount': 1e-06, 'price': 0.1, 'cost': None, 'base': None, 'quote': None} limits={'leverage': {'min': 1.0, 'max': None}, 'amount': {'min': 1e-06, 'max': 273.92085}, 'price': {'min': None, 'max': None}, 'cost': {'min': 1.0, 'max': 1200000.0}}
2026-09-09 09:31:46 [info     ] [LIVE] get_balance             currencies=['USDC']
balance (free): {'USDC': Decimal('28.433268')}
ticker: bid=79254.6 ask=79260.5 last=79276.2
2026-09-09 09:31:47 [debug    ] fetching_ohlcv                 limit=3 pair=BTC/USDC since=None timeframe=4h
2026-09-09 09:31:47 [info     ] ohlcv_fetched                  candles=3 first_timestamp='2026-09-08 20:00:00+00:00' interval=240 last_timestamp='2026-09-09 04:00:00+00:00' pair=BTC/USDC
  4h 2026-09-08T20:00:00+00:00 O=78364.7 C=78466.1 V=5.495427
  4h 2026-09-09T00:00:00+00:00 O=78466.1 C=78673.2 V=0.883565
  4h 2026-09-09T04:00:00+00:00 O=78673.2 C=79276.2 V=17.200232
2026-09-09 09:31:47 [info     ] [LIVE] get_open_orders         count=0
open orders: []
stats: {'orders_placed': 0, 'orders_filled': 0, 'orders_failed': 0, 'api_calls': 5}
2026-09-09 09:31:48 [info     ] bybit_rest_closed

==============================================================================
2. Paper round-trip (simulated fills, real ticker)
==============================================================================
2026-09-09 09:31:48 [info     ] bybit_rest_initialized         account_type=UNIFIED has_api_key=<masked> hostname=bybit.eu key_role=readonly maker_fee=0.0010 mode=paper taker_fee=0.0025
2026-09-09 09:31:48 [info     ] [PAPER] set_balance            amount=1000 currency=USDC
2026-09-09 09:31:48 [info     ] [PAPER] set_balance            amount=0 currency=BTC
2026-09-09 09:31:48 [info     ] [PAPER] market_order_filled    amount=0.000075 fee=0.01486428750 pair=BTC/USDC price=79276.2 side=buy
market BUY  0.000075 @ 79276.2 fee=0.01486428750 USDC
  balance: {'USDC': Decimal('994.03942071250'), 'BTC': Decimal('0.000075')}
2026-09-09 09:31:48 [info     ] [PAPER] limit_order_pending    amount=0.000075 expires_at=2026-09-09T07:46:48.185233+00:00 order_id=paper-limit-2abc71a9 pair=BTC/USDC price=83240.1 side=sell
limit SELL PostOnly(paper) -> pending id=paper-limit-2abc71a9
  status: {'order_id': 'paper-limit-2abc71a9', 'status': 'pending', 'filled': Decimal('0'), 'amount': Decimal('0.000075'), 'price': Decimal('83240.1')}
2026-09-09 09:31:48 [info     ] [PAPER] order_cancelled        order_id=paper-limit-2abc71a9
  cancel: True
2026-09-09 09:31:48 [info     ] [PAPER] market_order_filled    amount=0.000075 fee=0.01486428750 pair=BTC/USDC price=79276.2 side=sell
market SELL 0.000075 @ 79276.2 fee=0.01486428750 USDC
  balance: {'USDC': Decimal('999.97027142500'), 'BTC': Decimal('0.000000')}
  check: USDC == 1000 - fees -> True (expected 999.97027142500)
2026-09-09 09:31:48 [info     ] bybit_rest_closed

==============================================================================
3. LIVE limit orders (real, cancelled/rejected — NEVER market, TRADE key)
==============================================================================
2026-09-09 09:31:48 [info     ] bybit_rest_initialized         account_type=UNIFIED has_api_key=<masked> hostname=bybit.eu key_role=trade maker_fee=0.0010 mode=live taker_fee=0.0025
2026-09-09 09:31:50 [info     ] bybit_rest_markets_loaded      hostname=bybit.eu symbols=133
2026-09-09 09:31:51 [info     ] [LIVE] get_balance             currencies=['USDC']
key_role=trade  balance (free): {'USDC': Decimal('28.433268')}
3a. PostOnly BUY 0.000079 @ 75312.3 (-5 %)
2026-09-09 09:31:52 [info     ] [LIVE] limit_order_placed      amount=0.000079 client_order_id=kb-3e5f141e27bd495da12b1ed869b742bc order_id=2300182416633263104 pair=BTC/USDC price=75312.3 side=buy status=pending time_in_force=PostOnly
    -> status=pending id=2300182416633263104 meta={'client_order_id': 'kb-3e5f141e27bd495da12b1ed869b742bc', 'post_only': True}
    get_order_status: {'order_id': '2300182416633263104', 'client_order_id': 'kb-3e5f141e27bd495da12b1ed869b742bc', 'status': 'open', 'filled': Decimal('0'), 'amount': Decimal('0.000079'), 'price': Decimal('75312.3'), 'average': Decimal('75312.3'), 'fee': Decimal('0'), 'fee_currency': ''}
2026-09-09 09:31:52 [info     ] [LIVE] order_cancelled         order_id=2300182416633263104
    cancel_order: True
3b. GTC BUY 0.000077 @ 77690.6 (-2 %, priceLimitRatioX probe)
2026-09-09 09:31:53 [info     ] [LIVE] limit_order_placed      amount=0.000077 client_order_id=kb-8ea879c69edf4a97a105215d154b1fd8 order_id=2300182426892530688 pair=BTC/USDC price=77690.6 side=buy status=pending time_in_force=GTC
    -> ACCEPTED status=pending id=2300182426892530688 (no rejection!)
2026-09-09 09:31:53 [info     ] [LIVE] order_cancelled         order_id=2300182426892530688
    cancel_order: True
3c. PostOnly BUY 0.000075 @ 79339.8 (above ask 79260.5)
2026-09-09 09:31:54 [warning  ] [LIVE] limit_order_post_only_rejected amount=0.000075 client_order_id=kb-96a4d33f90bc4c579d1fd5b95a45404e exchange_order_id=2300182438032602112 pair=BTC/USDC price=79339.8 reason=EC_PostOnlyWillTakeLiquidity side=buy
    -> status=cancelled id=2300182438032602112 meta={'reject_reason': 'post_only_would_cross', 'exchange_order_id': '2300182438032602112', 'client_order_id': 'kb-96a4d33f90bc4c579d1fd5b95a45404e', 'raw_reason': 'EC_PostOnlyWillTakeLiquidity'}
2026-09-09 09:31:55 [info     ] [LIVE] get_open_orders         count=0
2026-09-09 09:31:55 [info     ] [LIVE] get_open_orders         count=0
open orders after run: []  -> OK (empty)
2026-09-09 09:31:55 [info     ] [LIVE] get_balance             currencies=['USDC']
balance (free) after run: {'USDC': Decimal('28.433268')}
stats: {'orders_placed': 3, 'orders_filled': 0, 'orders_failed': 0, 'api_calls': 15}
2026-09-09 09:31:55 [info     ] bybit_rest_closed
```

| Question | Verdict |
|---|---|
| (a) PostOnly loin du prix | `order/create` → `retCode 0`, statut `open` via `get_order_status`, `cancel_order → True` |
| (b) LIMIT BUY à −2 % vs `priceLimitRatioX = 0.5 %` | **Accepté** (`pending`, annulé ensuite). Le ratio ne rejette pas un ordre **passif** loin du marché ; il plafonne les prix **agressifs** (`170193` "Buy order price cannot be higher than…", `170194` côté sell). Pas d'impact sur les niveaux passifs des grilles ATR ni sur les profit targets. |
| (c) PostOnly au-dessus de l'ask | `order/create` → `retCode 0` + `orderId`, puis ordre `Rejected` (`rejectReason=EC_PostOnlyWillTakeLiquidity`, 0 exécuté) ; normalisé par le client en `Order(status=CANCELLED, signal_metadata.reject_reason="post_only_would_cross")`, `orders_failed` non incrémenté |
| Ordres résiduels | `fetch_open_orders` vide en fin de run ; balance inchangée (28.433268 USDC), aucun fill |

`BYBIT_INTEGRATION=trade pytest tests/test_connectors/test_bybit_rest_integration.py` : **5 passed**
(dont le round-trip live PostOnly → status → cancel). Notional réel engagé : ~6 USDC par ordre, 0 exécuté.

---

## Risques identifiés

1. ~~**Clés API non vérifiées**~~ **Levé en B1 (2026-09-08/09, voir section ci-dessus)** — round-trip live validé le 9 sept. Texte B0 : type de compte (UTA vs Classic — `wallet-balance` exige `accountType=UNIFIED` sur UTA), permissions Spot Trade, whitelist IP, et confirmation que les clés bybit.eu sont refusées sur api.bybit.com. Action : ajouter `BYBIT_API_KEY`/`BYBIT_API_SECRET` au `.env` et relancer `bybit_q1_endpoints.py`, `bybit_q6_orders.py`, `bybit_q7_ratelimits.py`.
2. **Fees ×3 en taker** (0.25 % vs 0.075 %) : les stratégies dont l'edge est < 0.5 %/trade (grid ATR à petits pas, scalping 5m déjà KILL) deviennent perdantes. Re-backtester P6/P7 avec `bybit_defaults()` avant tout déploiement ; privilégier PostOnly.
3. **Liquidité EU mince en volume traité** (BTC 3 M USDC/24 h) malgré un carnet profond : risque de fills partiels sur LIMIT (les murs MM peuvent disparaître), et mèches locales jusqu'à 40 bps la nuit qui déclenchent des stops absents sur Binance. Le risk manager doit utiliser des stops ATR, pas des stops serrés fixes.
4. **Historique EU de 15 mois seulement** : impossible de backtester sur Bybit EU natif ; dépendance durable aux données Binance (dont l'API publique reste accessible depuis l'UE aujourd'hui, mais sans garantie). Prévoir de continuer le collector Binance en parallèle (données only) tant que l'API publique répond.
5. **Piège `marketUnit`** : un Market BUY avec `price` ou via `params["cost"]` envoie un montant en USDC ; un `qty` base envoyé sans `marketUnit` serait interprété en quote → risque d'ordre 79 000× trop gros ou trop petit. Test unitaire obligatoire sur le body généré.
6. **Précision** : `basePrecision` BTC = 1e-6 sur EU mais `0.00001` dans le code Binance ; ETH/SOL EU **plus grossiers** que global — `load_markets()` doit impérativement être appelé sur `hostname=bybit.eu`, sinon ccxt arrondira avec les filtres du global et Bybit rejettera (`10001`).
7. ~~**`priceLimitRatioX = 0.5 %`**~~ **Levé en B1 (9 sept)** : un LIMIT passif à −2 % est accepté ; le ratio ne concerne que les prix agressifs (`170193`/`170194`). Pas d'impact grilles ATR / profit targets.
8. **WS** : max 10 args/requête (géré), ack `subscribe` non typé `topic` (à ignorer), pas de `trades_count` dans les klines (colonne nullable OK), `tickers` snapshot à chaque message (volume de messages ~2/s par symbole → fine avec le watchdog).
9. **Tunnel Hetzner indisponible pendant l'audit** : Q8 fait sur l'API Binance publique plutôt que la DB ; à re-valider sur la DB (`--binance-source db`) — attendu identique.
10. **Durée de vie de connexion WS non documentée** côté Bybit : conserver le reconnect préventif à 23 h et le watchdog de flux existants.
