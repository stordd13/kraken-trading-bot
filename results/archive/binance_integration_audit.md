# Binance Integration Audit — P0 Exploration Report

Generated: 2026-04-12T15:00:00+00:00
Scope: Technical feasibility study for pivoting krakenbot from Kraken to Binance

---

## Executive Summary

**The pivot from Kraken to Binance is technically feasible and architecturally well-prepared.** The codebase already has an `ExchangeRestClient` Protocol (`src/krakenbot/connectors/exchange.py`) and a `BaseExchangePerps` abstract class (`src/krakenbot/connectors/base_perps.py`), meaning the abstraction layer is half-built. The main work is implementing `BinanceRestClient` and `BinanceWebSocketClient`, then updating ~30 files with hardcoded Kraken references.

**Key findings:**
1. **Fees drop significantly**: Binance 0.10%/0.10% vs Kraken 0.16%/0.26% (37-62% cheaper). With BNB discount: 0.075%/0.075%.
2. **Data access is far superior**: Binance Vision provides free bulk CSV downloads (no pagination needed for backfill). REST klines support 1000 candles/request vs Kraken's 720.
3. **WebSocket is cleaner**: Binance sends `"x": true` on candle close (no endtime-tracking hack needed). Combined streams URL supports all timeframes in one connection.
4. **Existing abstraction**: `ExchangeRestClient` Protocol already defines the interface. `build_exchange_rest_client()` is the single point to swap.
5. **Main risks**: 47 test files reference Kraken directly; XBT/BTC normalization code must be refactored; Binance's 5 USDC minimum notional is higher than Kraken's.

**Estimated refactor: 3-4 weeks of focused work.** No red flags that should stop the migration.

---

## Section 1 — Paires et symbols

### 1.1 — Comment Binance nomme ses paires

| Aspect | Kraken | Binance | ccxt (unifié) |
|--------|--------|---------|---------------|
| Format natif | `XXBTZUSD` (legacy) ou `XBT/USDC` | `BTCUSDC` (concaténé) | `BTC/USDC` |
| Séparateur | `/` | Aucun | `/` |
| Bitcoin symbol | `XBT` | `BTC` | `BTC` |
| Format REST API | Dépend de l'endpoint | `BTCUSDC` partout | `BTC/USDC` partout |
| Format WebSocket | `XBT/USDC` | `btcusdc` (lowercase) | N/A (pas unifié WS) |

**Exemple concret** :
```python
# Kraken REST via ccxt
exchange = ccxt.kraken()
exchange.fetch_ohlcv("BTC/USDC", "1h")  # ccxt traduit en format Kraken interne

# Binance REST via ccxt
exchange = ccxt.binance()
exchange.fetch_ohlcv("BTC/USDC", "1h")  # ccxt traduit en "BTCUSDC" pour l'API

# Binance REST natif
# GET /api/v3/klines?symbol=BTCUSDC&interval=1h&limit=1000
```

**Point critique** : Kraken utilise `XBT` pour Bitcoin, Binance utilise `BTC`. Le code krakenbot a un mapping bidirectionnel dans `PAIR_TO_KRAKEN` (`kraken_rest.py:62-75`) et `PAIR_MAPPING` (`kraken_ws.py:68-77`). Avec Binance, ce mapping n'est plus nécessaire car ccxt normalise déjà en `BTC/USDC`.

### 1.2 — Paires USDC disponibles sur Binance spot

Confirmé via API live le 2026-04-12 (`GET /api/v3/exchangeInfo`) :

| Paire | Symbol Binance | Status | Min Qty | Step Size | Tick Size | Min Notional |
|-------|---------------|--------|---------|-----------|-----------|-------------|
| BTC/USDC | `BTCUSDC` | TRADING | 0.00001 | 0.00001 | 0.01 | 5.00 USDC |
| ETH/USDC | `ETHUSDC` | TRADING | 0.0001 | 0.0001 | 0.01 | 5.00 USDC |
| SOL/USDC | `SOLUSDC` | TRADING | 0.001 | 0.001 | 0.01 | 5.00 USDC |

**Total paires /USDC sur Binance** : 364 paires (confirmé via ccxt `load_markets()`).

**Alternatives** :
- **USDT** : Liquidité beaucoup plus élevée. `BTCUSDT` est la paire la plus tradée au monde.
- **FDUSD** : Zero-fee sur certaines paires BTC, mais instabilité du peg et avenir incertain.
- **USDC** : Recommandé pour la cohérence avec le setup actuel. Liquidité suffisante pour le volume du bot.

### 1.3 — Conventions ccxt

ccxt normalise toutes les paires au format `BASE/QUOTE` avec `/` séparateur :
- Binance natif `BTCUSDC` → ccxt `BTC/USDC`
- Binance natif `ETHUSDC` → ccxt `ETH/USDC`
- Binance natif `SOLUSDC` → ccxt `SOL/USDC`

C'est identique au format ccxt de Kraken. **Le code utilisant les paires ccxt ne changera pas.**

### 1.4 — Hardcoding de `XBT/USDC` dans le code

Fichiers avec des paires hardcodées (confirmé par grep exhaustif) :

| Fichier | Ligne | Contenu |
|---------|-------|---------|
| `src/krakenbot/config/settings.py` | 150 | `default="XBT/USDC"` — pair par défaut |
| `src/krakenbot/config/settings.py` | 308 | `default=["XBT/USDC", "XBT/EUR"]` — scheduler pairs |
| `src/krakenbot/connectors/kraken_rest.py` | 62-75 | `PAIR_TO_KRAKEN` mapping dict |
| `src/krakenbot/connectors/kraken_rest.py` | 78-83 | `MIN_ORDER_SIZE` dict avec `XBT/EUR`, `XBT/USD` etc. |
| `src/krakenbot/connectors/kraken_ws.py` | 68-77 | `PAIR_MAPPING` dict `XBT/USDC → XBT/USDC` etc. |
| `src/krakenbot/connectors/kraken_rest.py` | 86-88 | `normalize_asset_symbol()` — `"BTC" if asset in ("BTC", "XBT")` |
| `src/krakenbot/main.py` | 845-846 | `btc_balance = balances.get("BTC") or balances.get("XBT")` |
| `strategies.yaml` | (multiple) | Pair references dans les configs de stratégies |
| `scripts/backtest.py` | (multiple) | Default pair dans le parser argparse |

### 1.5 — Recommandation : quelles paires utiliser sur Binance

**Recommandation : `BTC/USDC` sur Binance spot.**

Raisons :
1. Continuité avec le setup actuel (`XBT/USDC` = `BTC/USDC` sémantiquement)
2. USDC est un stablecoin audité, fiable
3. Liquidité suffisante sur Binance (volume 24h confirmé)
4. Les backtests existants utilisent déjà des données Binance converties USDT→USDC
5. Pas besoin de refactorer la logique quote-currency

**Alternative USDT** : Si la liquidité USDC pose problème à grande échelle (>100k USDC/jour), considérer un switch vers USDT. Mais pour le volume actuel du bot (100-1000 USDC/trade), USDC est largement suffisant.

---

## Section 2 — Authentification et API keys

### 2.1 — Différences d'auth Kraken vs Binance

| Aspect | Kraken | Binance |
|--------|--------|---------|
| Algorithme | HMAC-SHA512 | HMAC-SHA256 |
| Nonce | Incrémental (nonce obligatoire) | Timestamp millisecond (`timestamp` param) |
| Header | `API-Key` + `API-Sign` | `X-MBX-APIKEY` |
| Signature location | Body (POST) | Query string (`&signature=...`) |
| Replay protection | Nonce ordering | `recvWindow` (default 5000ms, max 60000ms) |
| API version | `/0/private/...` | `/api/v3/...` |

**Exemple Binance signature** :
```python
import hmac, hashlib, time

api_key = "your_api_key"
api_secret = "your_api_secret"

timestamp = int(time.time() * 1000)  # milliseconds
query = f"symbol=BTCUSDC&side=BUY&type=LIMIT&timeInForce=GTC&quantity=0.001&price=60000&timestamp={timestamp}"
signature = hmac.new(api_secret.encode(), query.encode(), hashlib.sha256).hexdigest()

# Request:
# POST /api/v3/order?{query}&signature={signature}
# Header: X-MBX-APIKEY: {api_key}
```

### 2.2 — Restrictions Binance

**IP Whitelist** :
- Optionnel mais fortement recommandé
- **Obligatoire** pour les permissions de retrait
- API keys sans whitelist IP expirent automatiquement après **90 jours**
- Avec whitelist : durée illimitée

**Permission levels** (UI Binance) :
- Read (lecture balance, historique)
- Spot & Margin Trading
- Futures Trading
- Withdrawals (nécessite IP whitelist)
- Internal Transfer (entre wallets)

**`recvWindow`** :
- Paramètre optionnel sur chaque requête signée
- Si `serverTime - requestTimestamp > recvWindow` → requête rejetée
- Default: 5000ms. Recommandation: garder le default.
- Gotcha: si le clock du serveur du bot drift >5s, les requêtes échouent. Solution: `adjustForTimeDifference: True` dans ccxt.

### 2.3 — Abstraction par ccxt

**ccxt gère toutes les différences d'auth automatiquement.** Le code krakenbot utilise déjà :

```python
# Kraken actuel (kraken_rest.py:139-146)
self._exchange = ccxt.kraken({
    "apiKey": settings.kraken.api_key.get_secret_value(),
    "secret": settings.kraken.api_secret.get_secret_value(),
    "enableRateLimit": True,
    "rateLimit": 1000,
})

# Binance équivalent :
self._exchange = ccxt.binance({
    "apiKey": settings.binance.api_key.get_secret_value(),
    "secret": settings.binance.api_secret.get_secret_value(),
    "enableRateLimit": True,
    "options": {
        "defaultType": "spot",
        "recvWindow": 5000,
        "adjustForTimeDifference": True,
    },
})
```

**Aucune logique de signature manuelle n'est nécessaire** — ccxt gère HMAC-SHA256 + timestamp + recvWindow internement.

### 2.4 — Permissions à cocher

| Use case | Permissions Binance |
|----------|-------------------|
| (a) Read-only exploration | Enable Reading ✓ |
| (b) Spot trading | Enable Reading ✓ + Enable Spot & Margin Trading ✓ |
| (c) Futures trading | Enable Reading ✓ + Enable Futures ✓ |
| (d) Full bot (spot + futures) | Enable Reading ✓ + Enable Spot & Margin Trading ✓ + Enable Futures ✓ |

**Recommandation** : Ne PAS cocher "Enable Withdrawals". IP whitelist obligatoire pour le serveur Hetzner.

### 2.5 — Types d'API keys Binance

Binance n'a qu'un seul type d'API key : **HMAC-SHA256** (pas de choix comme "standard" vs "HMAC").

Certaines fonctionnalités avancées utilisent Ed25519 ou RSA pour la signature, mais HMAC-SHA256 est le standard et ce que ccxt utilise. **Pas de décision à prendre ici.**

---

## Section 3 — Rate limits

### 3.1 — Binance vs Kraken rate limits

| Aspect | Kraken | Binance |
|--------|--------|---------|
| Modèle | Compteur par seconde (décroissant) | Poids par minute (weight-based) |
| Limite globale | 15 appels/s (REST), decay ~3/s | 6000 weight/min (IP), + 6000/min (UID) |
| Limite ordres | Non explicite | 100 ordres/10s, 200,000/jour |
| Pénalité | Erreur 429 + ban temporaire | Erreur 429 + ban IP 2-5 min |
| Headers de tracking | Aucun standard | `X-MBX-USED-WEIGHT-1m` dans chaque réponse |

**Budget weight Binance pour le bot** :

Opérations typiques du bot par minute :
- 1x `fetch_balance` = 20 weight
- 1x `fetch_ticker` = 2 weight
- 2x `fetch_ohlcv` (2 timeframes) = 4 weight
- 1x `create_order` = 1 weight
- 1x `fetch_order` (polling) = 4 weight
- **Total ~31 weight/min** sur un budget de 6000 → **utilisation <1%**

### 3.2 — ccxt et rate limiting automatique

**Oui, ccxt gère le rate limiting automatiquement pour Binance.** Le mécanisme est basé sur les "costs" (weight normalisé) :

```python
# ccxt binance interne :
# Weight IP 1 → cost 0.1
# Weight IP 10 → cost 1.0
# enableRateLimit: True fait que ccxt attend entre les appels

exchange = ccxt.binance({"enableRateLimit": True})
# Pas besoin de gérer manuellement
```

Confirmé dans le source ccxt : Binance a un mapping endpoint → cost dans sa classe, et le throttler de ccxt applique un sleep proportionnel au cost.

### 3.3 — Retry/backoff dans krakenbot

Le code krakenbot actuel a :

| Fichier | Mécanisme | Adaptation Binance |
|---------|-----------|-------------------|
| `kraken_rest.py:614-622` | Catch `ccxt.RateLimitExceeded` → raise `RateLimitError` | **Identique** — ccxt lève la même exception |
| `kraken_ws.py:292-351` | Reconnection exponential backoff (delay × 2^n, max 300s) | **Réutilisable tel quel** |
| `settings.py:69-73` | `api_rate_limit_calls: 15` | Remplacer par un weight budget (ou supprimer, ccxt gère) |

**Pas de retry custom Kraken-spécifique** dans le code. Le bot utilise les exceptions ccxt qui sont identiques pour Binance.

### 3.4 — Weights par endpoint Binance

| Endpoint | Weight | Appels/min possibles |
|----------|--------|---------------------|
| `GET /api/v3/klines` (limit ≤ 100) | 2 | 3000 |
| `GET /api/v3/klines` (limit ≤ 500) | 5 | 1200 |
| `GET /api/v3/klines` (limit ≤ 1000) | 10 | 600 |
| `GET /api/v3/ticker/price` | 2 | 3000 |
| `GET /api/v3/account` (balance) | 20 | 300 |
| `POST /api/v3/order` | 1 | 6000 |
| `DELETE /api/v3/order` | 1 | 6000 |
| `GET /api/v3/order` | 4 | 1500 |
| `GET /api/v3/openOrders` (avec symbol) | 6 | 1000 |
| `GET /api/v3/openOrders` (TOUS) | 80 | 75 |
| `GET /api/v3/myTrades` | 20 | 300 |
| `GET /api/v3/exchangeInfo` | 20 | 300 |

### 3.5 — Gotchas connus

1. **`GET /api/v3/openOrders` sans symbol** coûte 80 weight (vs 6 avec symbol). Toujours passer le symbol.
   - ccxt affiche un warning si tu appelles `fetch_open_orders()` sans symbol (`warnOnFetchOpenOrdersWithoutSymbol: True`)
2. **`GET /api/v3/exchangeInfo`** coûte 20 weight — le mettre en cache au startup, ne pas l'appeler à chaque trade.
3. **Backfill intensif** : 600 appels klines/min (limit 1000) = 600,000 candles/min. Suffisant pour backfill rapide.
4. **Ordres algo** : Max 5 ordres algo (stop-loss, take-profit, trailing) par symbol. Le bot actuel peut dépasser si beaucoup de positions ouvertes simultanément.

---

## Section 4 — Fetch OHLC (candles historiques)

### 4.1 — fetch_ohlcv : Binance vs Kraken via ccxt

```python
# Kraken (actuel dans kraken_rest.py:1670-1675)
ohlcv_data = await self._exchange.fetch_ohlcv(
    symbol="BTC/USDC",
    timeframe="1h",
    since=since_ms,
    limit=720,  # Max Kraken
)

# Binance (identique !)
ohlcv_data = await self._exchange.fetch_ohlcv(
    symbol="BTC/USDC",
    timeframe="1h",
    since=since_ms,
    limit=1000,  # Max Binance (vs 720 Kraken)
)
```

**Le format de retour est identique** (ccxt unifié) :
```python
# [[timestamp_ms, open, high, low, close, volume], ...]
[
    [1772406000000, 65265.47, 66100.00, 65122.00, 65774.94, 266.99],
    ...
]
```

**Différence clé** : Kraken plafonne à 720 candles, Binance à 1000. Le code `time_utils.py:79` a `limit: int = 720` en default.

### 4.2 — Limites de batch

| Exchange | Max candles/request | Pagination interne ccxt |
|----------|--------------------|-----------------------|
| Kraken | 720 | `fetch_paginated_call_deterministic(..., 720)` |
| Binance | 1000 | Standard pagination |

Le code `time_utils.py:69` (`calculate_pagination_steps`) utilise `limit=720` comme default. Il faudra le rendre configurable ou le changer à 1000 pour Binance.

### 4.3 — Intervalles supportés

| Intervalle | Kraken | Binance | Bot utilise ? |
|-----------|--------|---------|--------------|
| 1s | Non | Oui | Non |
| 1m | Oui | Oui | Oui |
| 3m | Non | Oui | Non |
| 5m | Oui | Oui | Oui |
| 15m | Oui | Oui | Oui |
| 30m | Oui | Oui | Non |
| 1h | Oui | Oui | Oui |
| 2h | Non | Oui | Non |
| 4h | Oui (240min) | Oui | Oui |
| 6h | Non | Oui | Non |
| 8h | Non | Oui | Non |
| 12h | Non | Oui | Non |
| 1d | Oui (1440min) | Oui | Oui |
| 3d | Non | Oui | Non |
| 1w | Oui (10080min) | Oui | Oui |
| 15d/21600min | Oui (Kraken) | Non | Non |
| 1M | Non | Oui | Non |

**Tous les 7 timeframes du bot (1m, 5m, 15m, 1h, 4h, 1d, 1w) sont supportés par Binance.**

Le seul gap est `21600` (15 jours) que Kraken supporte mais pas Binance. Le bot ne l'utilise pas activement.

### 4.4 — Pull 2-3 ans de candles 1m

**Via REST API** :
- 3 ans = 1,576,800 candles 1m
- 1000 candles/request = 1577 requests
- 2 weight/request = 3154 weight total
- À 6000 weight/min = **~30 secondes** pour 3 ans de données 1m
- (En réalité ~2-3 minutes avec le rate limiter de ccxt)

**Via Binance Vision** (recommandé pour gros volumes) :
```
https://data.binance.vision/data/spot/monthly/klines/BTCUSDC/1m/BTCUSDC-1m-2023-01.zip
https://data.binance.vision/data/spot/daily/klines/BTCUSDC/1m/BTCUSDC-1m-2026-04-11.zip
```
- Téléchargement de fichiers ZIP contenant des CSV
- Pas de rate limit, pas d'authentification
- **36 fichiers mensuels** pour 3 ans, ~50-100 MB total
- Temps estimé : **< 1 minute** de download

### 4.5 — Endpoints plus efficaces pour gros volumes

**Binance Vision** (`https://data.binance.vision/`) :
- Données historiques gratuites en CSV/ZIP
- Granularité : daily ou monthly files
- Tous les intervalles supportés
- Pas de limite de rate
- Format : `data/spot/{daily|monthly}/klines/{SYMBOL}/{INTERVAL}/{SYMBOL}-{INTERVAL}-{DATE}.zip`

**Recommandation** : Pour le backfill initial (import de 3+ ans de données), utiliser Binance Vision au lieu de REST pagination. Écrire un script `scripts/binance_vision_import.py` qui :
1. Télécharge les ZIPs mensuels
2. Parse les CSV
3. Insert en batch dans `market_data_ohlc`

Cela remplace le scheduler de backfill REST qui pagine lentement avec 720 candles/appel.

---

## Section 5 — WebSocket streams

### 5.1 — Différences Kraken WS vs Binance WS

| Aspect | Kraken WS v1 | Binance WS |
|--------|-------------|------------|
| URL publique | `wss://ws.kraken.com` | `wss://stream.binance.com:9443/ws/<stream>` |
| URL combinée | N/A (un subscribe par canal) | `wss://stream.binance.com:9443/stream?streams=a/b/c` |
| Subscribe format | JSON `{"event":"subscribe","pair":["XBT/USDC"],...}` | JSON `{"method":"SUBSCRIBE","params":["btcusdc@kline_5m"],"id":1}` ou via URL |
| Candle complete | Détecter changement de `endtime` | Champ `"x": true` dans le payload |
| Message format | Array `[channelID, data, channelName, pair]` | Object `{"e":"kline","s":"BTCUSDC","k":{...}}` |
| Heartbeat | Kraken envoie `heartbeat` events | Binance envoie `ping` frames |
| Reconnection | Pas de limite de durée | **24h max** puis déconnexion forcée |
| Max streams | Pas de limite documentée | **1024 streams** par connexion |
| User data | N/A (pas utilisé) | Listen key required (`POST /api/v3/userDataStream`) |
| Pair format | `XBT/USDC` (avec slash) | `btcusdc` (lowercase, concaténé) |

### 5.2 — Combined streams vs single streams

**Recommandation : Combined streams.**

Pour le bot avec 7 timeframes sur BTCUSDC :
```
wss://stream.binance.com:9443/stream?streams=btcusdc@kline_1m/btcusdc@kline_5m/btcusdc@kline_15m/btcusdc@kline_1h/btcusdc@kline_4h/btcusdc@kline_1d/btcusdc@kline_1w
```

Un seul WebSocket, tous les timeframes. Le bot actuel utilise déjà un seul WS avec plusieurs subscriptions (`kraken_ws.py:158-167` dans le collector), donc le pattern est identique.

**Multi-pair** : Ajouter ETH et SOL dans le même stream :
```
?streams=btcusdc@kline_5m/ethusdc@kline_5m/solusdc@kline_5m/btcusdc@kline_4h/ethusdc@kline_4h/solusdc@kline_4h/...
```

Avec 3 paires × 7 timeframes = 21 streams (bien sous la limite de 1024).

### 5.3 — Listen key pour user data streams

**Différence critique avec Kraken** : Binance nécessite un "listen key" pour recevoir les fills et mises à jour de balance en temps réel.

```python
# 1. Obtenir un listen key
response = await exchange.request("POST", "/api/v3/userDataStream")
listen_key = response["listenKey"]

# 2. Ajouter au stream combiné
url = f"wss://stream.binance.com:9443/stream?streams=btcusdc@kline_5m/{listen_key}"

# 3. Keepalive toutes les 30 minutes (expire après 60 min)
await exchange.request("PUT", "/api/v3/userDataStream", {"listenKey": listen_key})
```

Le bot actuel n'utilise PAS de user data stream Kraken (il poll les ordres via REST dans `order_manager.py`). L'ajout du user data stream Binance serait une **amélioration** (détection de fills instantanée au lieu de polling toutes les 30s), mais n'est pas obligatoire au départ.

### 5.4 — Ping/pong et reconnexions

**Code actuel** (`kraken_ws.py`) :
- `_heartbeat_monitor()` : vérifie que des messages arrivent toutes les 30s
- `_data_flow_watchdog()` : vérifie toutes les 5 min que le compteur de messages augmente
- `_reconnect()` : exponential backoff (delay × 2^n, max 300s)
- Max 10 tentatives de reconnexion

**Adaptation pour Binance** :
- Le ping/pong Binance est au niveau WebSocket frame (géré par aiohttp/websockets automatiquement)
- **Ajout obligatoire** : reconnexion automatique toutes les **23h** (Binance coupe après 24h)
- Le `_data_flow_watchdog` peut être conservé tel quel
- La logique de reconnexion est **réutilisable** — il suffit de changer l'URL et le format de subscription

**Recommandation** : ne PAS réécrire le WS client from scratch. Refactorer `KrakenWebSocketClient` en une base class, puis créer `BinanceWebSocketClient` qui override seulement :
- URL de connexion
- Format de subscription
- Parsing des messages (array Kraken → object Binance)
- Timer de reconnexion forcée 23h

### 5.5 — Subscription multi-timeframe

**Kraken actuel** (`collector.py:157-167`) :
```python
for pair in self.settings.scheduler.pairs:
    await self.ws_client.subscribe_ohlc(pair, self.settings.trading.candle_interval_min)
    for interval in [240, 1440, 10080]:
        await self.ws_client.subscribe_ohlc(pair, interval)
    await self.ws_client.subscribe_ticker(pair)
```

**Binance équivalent** :
```python
# Option 1 : Via URL combinée (préféré)
streams = []
for pair in ["btcusdc", "ethusdc", "solusdc"]:
    for tf in ["1m", "5m", "15m", "1h", "4h", "1d", "1w"]:
        streams.append(f"{pair}@kline_{tf}")
url = f"wss://stream.binance.com:9443/stream?streams={'/'.join(streams)}"

# Option 2 : Via message SUBSCRIBE (dynamique)
await ws.send_json({
    "method": "SUBSCRIBE",
    "params": ["btcusdc@kline_5m", "btcusdc@kline_4h", ...],
    "id": 1
})
```

### 5.6 — Bug zombie WebSocket et heartbeat Binance

Le bot a un bug connu où le WebSocket Kraken reste silencieusement mort pendant 24h.

**Binance est mieux protégé** :
1. **Déconnexion forcée à 24h** : Binance coupe la connexion, forçant une reconnexion
2. **Ping frame** : Binance envoie un ping toutes les ~3 minutes. Si pas de pong en 10 minutes → déconnexion
3. Le `_data_flow_watchdog` existant (5 min check) est toujours pertinent comme couche supplémentaire

**Recommandation** :
- Conserver le watchdog existant
- Ajouter un timer de reconnexion préventive à 23h
- Logger le listen key keepalive pour détecter les échecs

---

## Section 6 — Order placement et lifecycle

### 6.1 — Types d'ordres supportés

| Type | Kraken | Binance | Utilisation bot |
|------|--------|---------|----------------|
| LIMIT | Oui | Oui | BUY (maker fee) |
| MARKET | Oui | Oui | SELL stop-loss/trailing |
| STOP_LOSS | Non natif (émulé) | Oui (market trigger) | Stop-loss |
| STOP_LOSS_LIMIT | Non natif | Oui (limit trigger) | Possible |
| TAKE_PROFIT | Non natif | Oui (market trigger) | Profit target |
| TAKE_PROFIT_LIMIT | Non natif | Oui (limit trigger) | Profit target |
| LIMIT_MAKER (post-only) | Oui (`oflags=post`) | Oui | Garantir maker fee |
| TRAILING_STOP | Non natif | Oui (`allowTrailingStop: true`) | Trailing stop |
| OCO | Non natif | Oui | TP + SL simultanés |
| OTO | Non | Oui | Entry → TP/SL automatique |

**Amélioration majeure** : Binance supporte nativement les `STOP_LOSS`, `TAKE_PROFIT` et `TRAILING_STOP` comme ordres server-side. Le bot actuel émule ces fonctionnalités côté client (polling dans `order_manager.py`). Migrer vers des ordres natifs Binance améliorerait la fiabilité (pas de risque de rate miss pendant un crash du bot).

**Limite importante** : Max **5 ordres algo** (stop-loss, take-profit, trailing) par symbol simultanément.

### 6.2 — Format des ordres ccxt

```python
# Kraken (actuel dans kraken_rest.py:1362-1367)
ccxt_order = await self._exchange.create_limit_order(
    "BTC/USDC",  # pair
    "buy",        # side
    float(amount),
    float(price),
)

# Binance (identique !)
ccxt_order = await self._exchange.create_limit_order(
    "BTC/USDC",  # pair — ccxt traduit en BTCUSDC
    "buy",
    float(amount),
    float(price),
)
```

**Le format de retour ccxt est identique** :
```python
{
    "id": "order_id_string",
    "status": "open" | "closed" | "canceled",
    "filled": 0.001,
    "average": 65000.0,
    "amount": 0.001,
    "price": 65000.0,
    "fee": {"cost": 0.065, "currency": "USDC"},
    ...
}
```

**Différence notable** : Binance retourne un `"fills"` array dans la réponse de `create_order` (quand `newOrderRespType: "FULL"`), donnant le détail de chaque fill. Kraken ne le fait pas.

### 6.3 — Fees dans l'API

**Kraken** : Les fees ne sont pas toujours retournées directement dans la réponse d'ordre. Il faut parfois les calculer ou les récupérer via `fetch_my_trades`.

**Binance** : Chaque fill dans la réponse contient `commission` et `commissionAsset` :
```json
{
    "fills": [
        {
            "price": "65000.00",
            "qty": "0.001",
            "commission": "0.00000010",
            "commissionAsset": "BTC"
        }
    ]
}
```

**Gotcha BNB fees** : Si "Use BNB for fees" est activé, `commissionAsset` sera `"BNB"` au lieu de `"BTC"` ou `"USDC"`. Le code doit gérer ce cas.

### 6.4 — Precision rules (LOT_SIZE, PRICE_FILTER, MIN_NOTIONAL)

**Binance est STRICT** sur la précision. Un ordre avec un amount non arrondi au `stepSize` sera rejeté.

| Filtre | BTCUSDC | ETHUSDC | SOLUSDC |
|--------|---------|---------|---------|
| LOT_SIZE minQty | 0.00001 | 0.0001 | 0.001 |
| LOT_SIZE stepSize | 0.00001 | 0.0001 | 0.001 |
| PRICE_FILTER tickSize | 0.01 | 0.01 | 0.01 |
| MIN_NOTIONAL | 5.00 USDC | 5.00 USDC | 5.00 USDC |

**ccxt gère automatiquement** l'arrondi au stepSize/tickSize quand on utilise `create_order()` — confirmé par `decimal_to_precision()` dans ccxt source.

**Le code krakenbot** arrondit déjà à 8 décimales (`Decimal("0.00000001")`) dans `engine.py:445`. Cela est compatible avec le stepSize Binance de 0.00001 pour BTCUSDC.

**Attention MIN_NOTIONAL** : Binance exige amount × price >= 5 USDC. Avec BTC à 65000, le minimum amount est ~0.00008 BTC. Le default order amount du bot est 100 USDC (~0.0015 BTC), donc pas de problème.

### 6.5 — Polling de limit orders

**Kraken** : `fetch_order(order_id, symbol)` — renvoie le statut actuel.
**Binance** : `fetch_order(order_id, symbol)` — identique via ccxt. Weight: 4.

Le code actuel (`order_manager.py:449-494`) utilise `get_order_status()` qui appelle `fetch_order()`. **Aucun changement nécessaire.**

Alternative Binance : Utiliser le User Data Stream WebSocket pour recevoir les fills en temps réel au lieu de poll. Mais le polling fonctionne aussi.

### 6.6 — Post-only orders

**Kraken** : `oflags=post` dans les paramètres de l'ordre.
**Binance** : Type d'ordre `LIMIT_MAKER` ou `params={"postOnly": True}` via ccxt.

```python
# Via ccxt (fonctionne pour les deux exchanges)
order = await exchange.create_order(
    "BTC/USDC", "limit", "buy", amount, price,
    params={"postOnly": True}
)
# ccxt traduit en LIMIT_MAKER pour Binance
```

Le code krakenbot actuel **n'utilise PAS explicitement post-only**. Les limit orders sont placés avec `create_limit_order()` standard. Mais le pattern maker-fee est garanti car les limit orders sont toujours en dessous du prix courant (pour BUY) grâce au `limit_buy_offset_pct` de 0.05%.

### 6.7 — Paper trading fill simulation

Le code actuel (`order_manager.py:327-357`) simule les fills :
```python
# BUY limit: candle.low <= limit_price → fill
# SELL limit: candle.high >= limit_price → fill
```

**Cette logique est exchange-agnostic.** Elle utilise les données OHLC (low/high) qui sont formatées identiquement par ccxt. **Aucun changement nécessaire pour Binance.**

---

## Section 7 — Balance et positions

### 7.1 — fetch_balance() différences

**Kraken** via ccxt :
```python
{
    "free": {"BTC": 0.5, "USDC": 5000.0, "XBT": 0.0, ...},
    "used": {"BTC": 0.1, "USDC": 1000.0, ...},
    "total": {"BTC": 0.6, "USDC": 6000.0, ...},
}
```
Note : Kraken peut retourner à la fois `BTC` et `XBT` — d'où `normalize_asset_symbol()` dans le code.

**Binance** via ccxt :
```python
{
    "free": {"BTC": 0.5, "USDC": 5000.0, "BNB": 1.5, ...},
    "used": {"BTC": 0.1, "USDC": 1000.0, ...},
    "total": {"BTC": 0.6, "USDC": 6000.0, ...},
}
```

**Différences** :
1. Binance ne retourne JAMAIS `XBT` — toujours `BTC`. La logique `normalize_asset_symbol()` (`kraken_rest.py:86-88`) ne sera plus nécessaire mais ne causera pas de bug.
2. Binance peut retourner `BNB` dans la balance (pour les fees). Le code doit l'ignorer ou le gérer.
3. Le format `free`/`used`/`total` est identique via ccxt.

### 7.2 — Wallet unique

**Kraken Spot** : Un seul wallet. Tout est dans `fetch_balance()`.
**Binance Spot** : Un seul wallet pour le spot aussi. `fetch_balance()` retourne uniquement le spot wallet.

Pas de différence pour le spot trading. Les wallets margin/futures sont séparés et nécessitent des appels différents.

### 7.3 — Paper balance

Le code actuel stocke le paper balance dans un dict en mémoire (`_paper_balance`) et en DB (`paper_balance` table). **Aucun changement nécessaire pour Binance** — c'est entièrement simulé côté client.

### 7.4 — Wallets séparés Binance

| Wallet | API | Usage |
|--------|-----|-------|
| Spot | `GET /api/v3/account` | Trading spot (notre usage) |
| Margin | `GET /sapi/v1/margin/account` | Margin trading |
| Futures USD-M | `GET /fapi/v2/account` | Perpetual futures |
| Funding | `GET /sapi/v1/asset/get-funding-asset` | Wallet de holding |
| Earn | `GET /sapi/v1/simple-earn/account` | Staking/savings |

**Impact pour le bot** :
- Pour le spot trading : aucun impact (un seul wallet)
- Pour le funding arb (spot + futures) : il faudra gérer les transfers entre wallets spot ↔ futures via `POST /sapi/v1/asset/transfer`

---

## Section 8 — Fees et maker/taker

### 8.1 — Fees Binance 2026 (nouvel utilisateur)

| Tier | Volume 30j | Maker | Taker |
|------|-----------|-------|-------|
| Regular | < 1M USDT | **0.1000%** | **0.1000%** |
| VIP 1 | ≥ 1M | 0.0900% | 0.1000% |
| VIP 2 | ≥ 5M | 0.0800% | 0.1000% |

**Avec BNB discount (25%)** :

| Tier | Maker | Taker |
|------|-------|-------|
| Regular + BNB | **0.0750%** | **0.0750%** |

**Comparaison directe** :

| | Kraken | Binance | Binance + BNB | Économie |
|---|--------|---------|-------------|----------|
| Maker | 0.16% | 0.10% | 0.075% | 37-53% |
| Taker | 0.26% | 0.10% | 0.075% | 62-71% |
| Round-trip (limit→market) | 0.42% | 0.20% | 0.15% | 52-64% |

### 8.2 — BNB discount

**Mécanisme** :
1. Posséder du BNB sur son compte Binance
2. Activer "Use BNB to pay for fees" dans les settings du compte (pas l'API — c'est un toggle UI)
3. Les fees sont automatiquement déduites en BNB au lieu de l'asset tradé
4. **25% de réduction** sur les fees spot
5. Pas besoin de flag dans l'API — c'est un setting global du compte

**Impact sur le code** :
- La `commissionAsset` dans les fills sera `"BNB"` au lieu de `"BTC"` ou `"USDC"`
- Le calcul de P&L doit gérer ce cas (fee en BNB ≠ fee en quote currency)
- Option 1 : Convertir la fee BNB en USDC pour le tracking
- Option 2 : Ignorer et considérer que le BNB fee est "gratuit" (approximation acceptable)

**Recommandation** : Activer le BNB discount. Acheter ~10 USDC de BNB, ça durera des mois à notre volume de trading.

### 8.3 — Fees hardcodées dans le code

| Fichier | Ligne | Valeur | Usage |
|---------|-------|--------|-------|
| `src/krakenbot/connectors/kraken_rest.py` | 407 | `Decimal("0.0026")` | Taker fee paper market orders |
| `src/krakenbot/connectors/kraken_rest.py` | 729 | `Decimal("0.0026")` | Taker fee paper margin orders |
| `src/krakenbot/connectors/kraken_rest.py` | 1221 | `Decimal("0.0016")` | Maker fee paper limit orders |
| `src/krakenbot/execution/order_manager.py` | 369 | `Decimal("0.0016")` | Maker fee paper limit fills |
| `scripts/backtest.py` | 487 | `Decimal("0.0016")` | Maker fee backtest |
| `scripts/backtest.py` | 491 | `Decimal("0.0026")` | Taker fee backtest |
| `scripts/backtest.py` | 492 | `Decimal("0.0002")` | Spread backtest |
| `scripts/backtest.py` | 493 | `Decimal("0.0001")` | Slippage backtest |
| `src/krakenbot/strategies/grid_adaptive.py` | 37 | `Decimal("0.64")` | MIN_PROFITABLE_SPACING (dérivé des fees) |
| `tests/test_execution/test_order_manager.py` | 1114, 1154 | `Decimal("0.0016")` | Test assertions |
| `tests/test_connectors/test_margin_orders.py` | 202, 204 | `Decimal("0.0026")` | Test assertions |

**Total : 11+ occurrences dans 6+ fichiers.**

### 8.4 — Utilisation des fees dans les stratégies

Les stratégies utilisent les fees dans :
1. **Break-even calculation** : `grid_adaptive.py:37` — `MIN_PROFITABLE_SPACING = Decimal("0.64")` (2 × 0.16% maker + spread). Avec Binance 0.075%, ce seuil baisse à ~0.35%.
2. **Backtest engine** : `backtest.py:487-493` — fees appliquées à chaque trade simulé
3. **Paper trading** : `kraken_rest.py:407,729,1221` et `order_manager.py:369` — fees simulées

### 8.5 — Recommandation : fees configurables

**Architecture recommandée** :

```python
# Dans settings.py ou exchange_config.yaml
class ExchangeFees(BaseModel):
    maker: Decimal = Decimal("0.0010")    # 0.10% default Binance
    taker: Decimal = Decimal("0.0010")    # 0.10%
    spread: Decimal = Decimal("0.0001")   # 0.01%
    slippage: Decimal = Decimal("0.0001") # 0.01%

# Utilisation
fee = self._settings.exchange_fees.maker  # au lieu de Decimal("0.0016") hardcodé
```

**Fichiers à modifier** :
1. `settings.py` : Ajouter `ExchangeFees` config
2. `kraken_rest.py` : Remplacer les 3 hardcodes par `self._settings.exchange_fees.taker/maker`
3. `order_manager.py` : Remplacer le hardcode par config
4. `backtest.py` : Remplacer par config ou CLI args (déjà partiellement fait)
5. `grid_adaptive.py` : Recalculer `MIN_PROFITABLE_SPACING` depuis config
6. Tests : Mettre à jour les assertions

---

## Section 9 — Binance Futures (pour plus tard)

### 9.1 — Binance Futures USD-M perps

| Aspect | Valeur |
|--------|--------|
| Symbol | `BTCUSDT` (USD-M) |
| Fees maker | 0.0200% (régulier) |
| Fees taker | 0.0500% (régulier) |
| Fees maker + BNB | 0.0180% |
| Fees taker + BNB | 0.0450% |
| Funding rate | Toutes les **8 heures** (00:00, 08:00, 16:00 UTC) |
| Max leverage | 125x (configurable) |
| Position modes | One-Way ou Hedge Mode |
| Collateral | USDT ou USDC selon le contrat |

**Comparaison avec Kraken Futures** :

| Aspect | Kraken Futures | Binance Futures |
|--------|---------------|----------------|
| Maker fee | 0.02% | 0.02% |
| Taker fee | 0.05% | 0.05% |
| Funding frequency | **1 heure** | **8 heures** |
| Symbol format | `PF_XBTUSD` | `BTCUSDT` |
| Max leverage | 50x | 125x |
| API séparée | Oui (ccxt.krakenfutures) | Oui (ccxt.binanceusdm) |
| API keys | Séparées du spot | **Partagées** (même clé, permission distincte) |

### 9.2 — ccxt classes

```python
import ccxt.async_support as ccxt

# Spot
spot = ccxt.binance({...})

# Futures USD-M
futures = ccxt.binanceusdm({...})

# Futures Coin-M (margé en crypto, pas recommandé)
coin_futures = ccxt.binancecoinm({...})
```

Ce sont des **classes séparées** dans ccxt, comme `ccxt.kraken` vs `ccxt.krakenfutures`. Le pattern existant dans `kraken_futures_rest.py` se transpose directement.

### 9.3 — API keys spot vs futures

**Chez Kraken** : API keys spot et futures sont **complètement séparées** (services différents). D'où la config `KrakenFuturesSettings` avec ses propres `api_key` et `api_secret`.

**Chez Binance** : **Même API key** pour spot et futures, à condition que la permission "Enable Futures" soit cochée. Les deux ccxt instances partagent les mêmes credentials.

```python
# Binance: même credentials pour les deux
api_key = settings.binance.api_key.get_secret_value()
api_secret = settings.binance.api_secret.get_secret_value()

spot = ccxt.binance({"apiKey": api_key, "secret": api_secret})
futures = ccxt.binanceusdm({"apiKey": api_key, "secret": api_secret})
```

**Simplification** : Plus besoin de `BinanceFuturesSettings` séparé pour les credentials. Un seul set de clés suffit.

### 9.4 — Funding rate arbitrage sur Binance

**Comparaison avec Kraken (d'après `results/funding_structural_analysis.md`)** :

| Aspect | Kraken PF_XBTUSD | Binance BTCUSDT |
|--------|------------------|-----------------|
| Settlement | 1h (24 fois/jour) | 8h (3 fois/jour) |
| Mean funding rate | ~0.0007%/h | ~0.0055%/8h (soit ~0.00069%/h) |
| Spot fee round-trip | 0.42% (maker+taker) | 0.20% (maker+taker) |
| Perp fee round-trip | 0.07% (maker+taker) | 0.07% (maker+taker) |
| Total entry cost | ~0.36% | ~0.20% |
| APR net (rapport Kraken) | 2.87% | À vérifier : estimé ~4-6% |

**Avantage Binance** :
1. Fees spot 50% moins cher → coût d'entrée réduit → breakeven plus rapide
2. Liquidité futures bien supérieure → moins de slippage
3. Mêmes API keys → pas de transfert complexe entre comptes

**Désavantage** :
1. Settlement 8h au lieu de 1h → capture moins granulaire
2. Le rapport Kraken montre que les 3 derniers mois (fév-avr 2026) ont des funding négatifs → le marché a changé

### 9.5 — Re-tester sur Binance ?

**Oui, cela vaudrait le coup**, pour deux raisons :
1. Le coût d'entrée est ~45% plus bas (0.20% vs 0.36% round-trip)
2. La liquidité Binance futures est ~10x celle de Kraken Futures
3. Le rapport Kraken montre APR 2.87% net avec 0.36% de fees. Avec 0.20% de fees, l'APR monterait à ~3.5-4%

**Cependant**, les 3 derniers mois ont des funding négatifs. Le test devrait inclure ces mois récents et vérifier si c'est un changement structurel ou temporaire.

---

## Section 10 — Différences critiques qui peuvent casser le code existant

### 10.1 — Liste exhaustive des hardcodes "kraken"

**Fichiers source (`src/krakenbot/`)** :

| Fichier | Type | Détail |
|---------|------|--------|
| `connectors/kraken_rest.py` | Entier fichier | Classe `KrakenRestClient`, 1931 lignes |
| `connectors/kraken_ws.py` | Entier fichier | Classe `KrakenWebSocketClient`, 1124 lignes |
| `connectors/kraken_futures_rest.py` | Entier fichier | Classe `KrakenFuturesClient`, 252 lignes |
| `connectors/exchange.py:104` | Import | `from krakenbot.connectors.kraken_rest import KrakenRestClient` |
| `connectors/__init__.py:22-23` | Exports | `KrakenRestClient`, `KrakenWebSocketClient` |
| `collector.py:28-29` | Imports | `KrakenRestClient`, `KrakenWebSocketClient` |
| `config/settings.py:42-75` | Class | `KrakenSettings` (api_key, api_secret, api_url, ws_url) |
| `config/settings.py:448-479` | Class | `KrakenFuturesSettings` |
| `config/settings.py:616` | Field | `kraken: KrakenSettings` |
| `config/settings.py:631` | Field | `kraken_futures: KrakenFuturesSettings` |
| `main.py:845` | Comment | `# Normalize XBT to BTC (Kraken uses XBT internally)` |
| `execution/engine.py:36` | TYPE_CHECKING | `from krakenbot.connectors.kraken_rest import KrakenRestClient` |

**Log messages** contenant "kraken" (grep `kraken_` dans les logger calls) :

| Pattern | Occurrences |
|---------|------------|
| `kraken_rest_*` | 18 (balance, orders, fees, rate limit errors) |
| `kraken_ws_*` | 25 (connect, disconnect, heartbeat, data) |
| `kraken_futures_*` | 3 (demo mode, errors) |

**Tests** :

| Fichier | Contenu |
|---------|---------|
| `tests/test_connectors/test_kraken_rest.py` | Tests KrakenRestClient |
| `tests/test_connectors/test_kraken_ws.py` | Tests KrakenWebSocketClient |
| `tests/test_connectors/test_kraken_futures_rest.py` | Tests KrakenFuturesClient |
| `tests/test_connectors/test_margin_orders.py` | Tests margin via KrakenRestClient |
| `tests/test_connectors/test_exchange.py` | Tests ExchangeRestClient Protocol |
| `tests/test_connectors/test_base_perps.py` | Tests BaseExchangePerps |
| `tests/test_execution/test_engine.py` | Utilise KrakenRestClient mock |
| `tests/test_execution/test_order_manager.py` | Utilise client mock |
| `tests/conftest.py` | Fixtures avec Kraken config |

**Total : ~47 fichiers de test** dont beaucoup référencent Kraken directement.

### 10.2 — Types de données : Decimal, float, str

| Donnée | Kraken (via ccxt) | Binance (via ccxt) | Impact |
|--------|-------------------|-------------------|--------|
| Prix | `float` | `float` | Aucun |
| Amount | `float` | `float` | Aucun |
| Fee | `float` dans `fee.cost` | `float` dans `fee.cost` | Aucun |
| Balance | `float` dans `free[currency]` | `float` dans `free[currency]` | Aucun |
| Order ID | `str` | `str` | Aucun |
| Timestamp OHLCV | `int` (ms) | `int` (ms) | Aucun |

**ccxt normalise les types pour les deux exchanges.** Le code krakenbot convertit déjà en `Decimal(str(value))` partout (`kraken_rest.py:260,301-313` etc.), ce qui est correct pour les deux.

**Confirmé via ccxt** :
```python
# Binance BTC/USDC precision
{'amount': 1e-05, 'price': 0.01, 'cost': None, 'base': 1e-08, 'quote': 1e-08}
```

### 10.3 — Timestamps

| Aspect | Kraken natif | Binance natif | ccxt (unifié) |
|--------|-------------|--------------|---------------|
| OHLCV | Secondes (float) | Millisecondes (int) | **Millisecondes (int)** |
| Order timestamp | Secondes | Millisecondes | **Millisecondes** |
| WS candle time | Secondes (float) | Millisecondes (int) | N/A (raw) |
| Server time | Secondes | Millisecondes | N/A |

**Via ccxt** : Les deux exchanges retournent des timestamps en **millisecondes** — ccxt normalise les timestamps Kraken. Le code krakenbot convertit déjà correctement :

```python
# kraken_rest.py:1683
timestamp = datetime.fromtimestamp(timestamp_ms / 1000, tz=UTC)
```

**Attention WS** : Le WebSocket Kraken envoie les timestamps en secondes floats (`1638747660.123`), le WS Binance en millisecondes entiers (`1638747660000`). Le code WS devra être adapté.

### 10.4 — Error codes et rejection reasons

**Kraken** : Erreurs sous forme de messages texte (ex: `"EOrder:Insufficient funds"`).
**Binance** : Codes d'erreur numériques + messages :

| Code Binance | Signification | Équivalent ccxt |
|-------------|---------------|-----------------|
| -1013 | Invalid quantity (LOT_SIZE) | `InvalidOrder` |
| -2010 | Insufficient balance | `InsufficientFunds` |
| -1021 | Timestamp outside recvWindow | `InvalidNonce` |
| -1015 | Too many orders | `RateLimitExceeded` |
| -2011 | Unknown order | `OrderNotFound` |
| -1010 | Not found | `OrderNotFound` |

**ccxt mappe ces codes vers les mêmes exceptions** (`ccxt.InsufficientFunds`, `ccxt.RateLimitExceeded`, `ccxt.OrderNotFound`, etc.). Le code krakenbot catche ces exceptions ccxt, donc **aucun changement nécessaire**.

### 10.5 — Précision des prix et amounts

| Paire | Kraken min amount | Binance min amount | Binance min notional |
|-------|------------------|--------------------|---------------------|
| BTC/USDC | 0.0001 BTC | 0.00001 BTC (10x smaller) | 5.00 USDC |
| ETH/USDC | 0.001 ETH | 0.0001 ETH (10x smaller) | 5.00 USDC |
| SOL/USDC | N/A | 0.001 SOL | 5.00 USDC |

**Risque principal** : Le `MIN_NOTIONAL` de Binance (5 USDC) est plus élevé que le minimum de Kraken pour les petits ordres. Si le bot calcule un ordre de 3 USDC, Binance le rejettera.

Le `MIN_ORDER_SIZE` dict dans `kraken_rest.py:78-83` devra être mis à jour avec les minimums Binance, ou mieux, supprimé en faveur de `exchange.markets[symbol].limits` fourni par ccxt.

---

## Section 11 — Architecture recommandée pour le refactor

### 11.1 — Interface `BaseExchangeClient`

Le code a déjà un `ExchangeRestClient` Protocol dans `exchange.py:23-90`. C'est la bonne base. Voici l'interface complète nécessaire :

```python
@runtime_checkable
class ExchangeRestClient(Protocol):
    """Interface REST pour tous les exchanges."""

    @property
    def exchange_name(self) -> str: ...

    @property
    def is_paper_mode(self) -> bool: ...

    @property
    def stats(self) -> dict[str, int]: ...

    @property
    def paper_balance(self) -> dict[str, Decimal]: ...

    # Lifecycle
    async def close(self) -> None: ...

    # Market data
    def update_last_price(self, pair: str, price: Decimal) -> None: ...
    async def get_ticker(self, pair: str) -> dict[str, Any]: ...
    async def fetch_ohlcv(
        self, pair: str, interval: int,
        since: datetime | None = None, limit: int = 1000,
    ) -> list[dict[str, Any]]: ...

    # Balance
    async def get_balance(self) -> dict[str, Decimal]: ...
    async def get_margin_balance(self) -> dict[str, Decimal]: ...

    # Orders
    async def place_market_order(
        self, pair: str, side: TradeSide, amount: Decimal,
        strategy: str, signal_price: Decimal | None = None,
    ) -> Trade: ...

    async def place_limit_order(
        self, pair: str, side: TradeSide, amount: Decimal,
        price: Decimal, strategy: str,
        expires_in_seconds: int = 900,
    ) -> Order: ...

    async def place_margin_order(
        self, pair: str, side: TradeSide, amount: Decimal,
        strategy: str, signal_price: Decimal | None = None,
        leverage: int = 2,
    ) -> Trade: ...

    async def get_order_status(self, order_id: str, pair: str | None = None) -> dict[str, Any]: ...
    async def cancel_order(self, order_id: str, pair: str | None = None) -> bool: ...
    async def get_open_orders(self, pair: str | None = None) -> list[dict[str, Any]]: ...

    # Paper trading
    async def initialize_paper_balance(self, force_reset: bool = False) -> None: ...
    async def persist_paper_balance(self) -> None: ...
    def remove_paper_order(self, order_id: str) -> None: ...
    async def set_paper_balance(self, currency: str, amount: Decimal) -> None: ...
    def get_paper_balance(self) -> dict[str, Decimal]: ...
```

**Méthodes à ajouter** (pas dans le Protocol actuel) :
- `fetch_ohlcv()` — actuellement dans `KrakenRestClient` mais pas dans le Protocol
- `get_open_orders()` — idem
- `set_paper_balance()` / `get_paper_balance()` — idem

### 11.2 — Interface `BaseWebSocketClient`

**Oui, il faut abstraire le WebSocket.** Le collector et le bot main utilisent le WS client directement.

```python
class BaseWebSocketClient(ABC):
    """Interface WebSocket pour tous les exchanges."""

    @abstractmethod
    async def connect(self) -> None: ...

    @abstractmethod
    async def close(self) -> None: ...

    @abstractmethod
    async def subscribe_ohlc(self, pair: str, interval: int) -> None: ...

    @abstractmethod
    async def subscribe_ticker(self, pair: str) -> None: ...

    @abstractmethod
    async def subscribe_trades(self, pair: str) -> None: ...

    @abstractmethod
    async def unsubscribe_ohlc(self, pair: str, interval: int) -> None: ...

    @property
    @abstractmethod
    def is_connected(self) -> bool: ...

    @property
    @abstractmethod
    def stats(self) -> dict[str, int]: ...
```

La logique de reconnexion, heartbeat monitoring, et data flow watchdog peut rester dans une **base class concrète** (pas abstraite), héritée par `KrakenWebSocketClient` et `BinanceWebSocketClient`.

### 11.3 — Logique spécifique par exchange

**Recommandation : Config YAML + Subclass.**

```
src/krakenbot/connectors/
├── base_exchange.py          # ExchangeRestClient Protocol (existe déjà)
├── base_ws.py                # BaseWebSocketClient ABC (nouveau)
├── base_perps.py             # BaseExchangePerps ABC (existe déjà)
├── exchange.py               # build_exchange_rest_client() factory (existe)
├── kraken/
│   ├── __init__.py
│   ├── rest.py               # KrakenRestClient
│   ├── ws.py                 # KrakenWebSocketClient
│   └── futures.py            # KrakenFuturesClient
├── binance/
│   ├── __init__.py
│   ├── rest.py               # BinanceRestClient
│   ├── ws.py                 # BinanceWebSocketClient
│   └── futures.py            # BinanceFuturesClient
└── config/
    └── exchange_config.yaml  # Fees, min sizes, pair mappings par exchange
```

La config spécifique (fees, precision rules) va dans **strategies.yaml** ou un nouveau **exchange_config.yaml** :

```yaml
exchanges:
  binance:
    maker_fee: 0.0010
    taker_fee: 0.0010
    spread: 0.0001
    slippage: 0.0001
    default_ohlcv_limit: 1000
    ws_url: "wss://stream.binance.com:9443"
    ws_reconnect_hours: 23
  kraken:
    maker_fee: 0.0016
    taker_fee: 0.0026
    spread: 0.0002
    slippage: 0.0001
    default_ohlcv_limit: 720
    ws_url: "wss://ws.kraken.com"
```

### 11.4 — Ordre des fichiers à créer pour le refactor

**Phase 1 — Abstraction (1 semaine)** :
1. `connectors/base_ws.py` — ABC WebSocket
2. Refactorer `connectors/exchange.py` — enrichir le Protocol avec les méthodes manquantes
3. Déplacer `kraken_rest.py` → `connectors/kraken/rest.py` (pur renommage)
4. Déplacer `kraken_ws.py` → `connectors/kraken/ws.py`
5. Déplacer `kraken_futures_rest.py` → `connectors/kraken/futures.py`
6. Extraire les fees hardcodées → config

**Phase 2 — Binance REST (1 semaine)** :
7. `connectors/binance/rest.py` — BinanceRestClient implements ExchangeRestClient
8. Update `exchange.py:build_exchange_rest_client()` pour supporter Binance
9. Update `settings.py` — ajouter `BinanceSettings` (même structure que `KrakenSettings`)
10. Tests pour BinanceRestClient

**Phase 3 — Binance WebSocket (1 semaine)** :
11. `connectors/binance/ws.py` — BinanceWebSocketClient extends BaseWebSocketClient
12. Update `collector.py` pour accepter le WS client via factory
13. Tests pour BinanceWebSocketClient

**Phase 4 — Binance Futures (optionnel, 3-5 jours)** :
14. `connectors/binance/futures.py` — BinanceFuturesClient extends BaseExchangePerps
15. Tests

**Phase 5 — Data migration (3-5 jours)** :
16. `scripts/binance_vision_import.py` — Import historique via Binance Vision
17. Tester toutes les stratégies avec les données Binance

**Phase 6 — Integration tests (3-5 jours)** :
18. Tests end-to-end paper trading Binance
19. Backtest validation avec les fees Binance
20. Fix des regressions

### 11.5 — Impact sur MultiTimeframeAnalyzer, MultiStrategyRouter, GlobalRiskManager

| Composant | Impact | Changements |
|-----------|--------|-------------|
| `MultiTimeframeAnalyzer` | **Aucun** | Exchange-agnostic. Reçoit des candles via EventBus. |
| `MultiStrategyRouter` | **Aucun** | Exchange-agnostic. Génère des signaux, ne touche pas l'exchange. |
| `GlobalRiskManager` | **Minimal** | Les fees dans les calculs de risk check doivent être configurables. |
| `ExecutionEngine` | **Minimal** | Utilise déjà le Protocol `ExchangeRestClient`. Juste le type hint à relaxer. |
| `OrderManager` | **Minimal** | Utilise déjà le Protocol `ExchangeRestClient`. |
| `BacktestEngine` | **Moyen** | Fees hardcodées à extraire. `time_utils.py` limit 720→1000. |
| Stratégies | **Aucun** | Toutes exchange-agnostic. |

**L'architecture du bot est bien séparée.** Seule la layer `connectors/` et les fees hardcodées doivent changer. Le core (strategies, indicators, analyzer, risk) n'est pas impacté.

---

## Section 12 — Estimation de complexité et risques

### 12.1 — Estimation totale

| Phase | Description | Durée estimée |
|-------|-------------|---------------|
| P1 | Abstraction (base classes, renommage) | 3-4 jours |
| P2 | BinanceRestClient | 4-5 jours |
| P3 | BinanceWebSocketClient | 3-4 jours |
| P4 | Binance Futures (optionnel) | 3-5 jours |
| P5 | Data migration + backfill | 2-3 jours |
| P6 | Integration tests + fix regressions | 3-5 jours |
| P7 | Paper trading validation | 5-7 jours (en parallèle) |
| **Total** | | **18-28 jours-agent** |

En pratique, avec un travail concentré : **3-4 semaines**.

### 12.2 — Top 5 risques

| # | Risque | Probabilité | Impact | Mitigation |
|---|--------|------------|--------|------------|
| 1 | **Tests cassés en masse** — 47 test files référencent Kraken | Certaine | Moyen | Refactorer les tests en parallèle. La plupart mockent le client. |
| 2 | **XBT/BTC confusion** — `normalize_asset_symbol()` et le mapping bidirectionnel | Moyenne | Élevé | Supprimer la normalisation XBT→BTC (Binance n'a pas ce problème). Tester exhaustivement. |
| 3 | **MIN_NOTIONAL 5 USDC** — Ordres trop petits rejetés par Binance | Moyenne | Moyen | Ajouter une validation MIN_NOTIONAL avant placement. Le default 100 USDC est ok. |
| 4 | **BNB fee asset** — P&L tracking cassé si la fee est en BNB au lieu de USDC | Moyenne | Faible | Convertir fee BNB → USDC dans le tracking, ou ignorer (montant négligeable). |
| 5 | **WebSocket 24h disconnect** — Non géré dans le code actuel | Certaine | Élevé | Ajouter un timer de reconnexion préventive à 23h. Critique pour le collector 24/7. |

### 12.3 — Tests unitaires qui vont casser

| Fichier test | Raison | Correction |
|-------------|--------|------------|
| `test_kraken_rest.py` | Import direct de `KrakenRestClient` | Garder tel quel (tests Kraken), ajouter `test_binance_rest.py` |
| `test_kraken_ws.py` | Import direct de `KrakenWebSocketClient` | Idem |
| `test_kraken_futures_rest.py` | Import direct | Idem |
| `test_margin_orders.py` | Fees hardcodées 0.0026 | Mettre à jour les fees dans les assertions |
| `test_order_manager.py` | Fees hardcodées 0.0016 | Idem |
| `test_engine.py` | Type hint `KrakenRestClient` | Changer en `ExchangeRestClient` |
| `test_exchange.py` | Test du Protocol | Probablement ok, mais vérifier |
| `test_settings.py` | Test de `KrakenSettings` | Ajouter tests `BinanceSettings` |
| `conftest.py` | Fixtures Kraken | Ajouter fixtures Binance |

**Estimation : 10-15 fichiers test à modifier, 5-8 nouveaux fichiers test à créer.**

Les tests des stratégies (`test_capitulation.py`, `test_grid_adaptive.py`, etc.) ne devraient **PAS casser** car ils sont exchange-agnostic.

### 12.4 — Refactor progressif ou big bang ?

**Refactor progressif recommandé** (Kraken et Binance en parallèle).

Raisons :
1. L'`ExchangeRestClient` Protocol existe déjà — les deux implémentations peuvent coexister
2. `build_exchange_rest_client()` dans `exchange.py` est le seul point de décision — un simple `if settings.exchange == "binance"` suffit
3. Le collector peut continuer à tourner sur Kraken pendant le développement Binance
4. Le paper trading peut être testé sur Binance sans couper le live Kraken
5. Rollback facile : changer une config, pas un codebase

**Plan de coexistence** :
```python
# exchange.py
def build_exchange_rest_client(settings, event_bus, db_manager):
    exchange = getattr(settings, "exchange_name", "kraken")
    if exchange == "binance":
        from krakenbot.connectors.binance.rest import BinanceRestClient
        return BinanceRestClient(settings, event_bus, db_manager)
    else:
        from krakenbot.connectors.kraken.rest import KrakenRestClient
        return KrakenRestClient(settings, event_bus, db_manager)
```

### 12.5 — Recommandation finale

**Oui, le pivot Binance est techniquement faisable en 4-6 semaines.**

**Pas de red flags majeurs.** Les avantages sont significatifs :
- Fees 50-60% plus basses
- Data historique bien meilleure (Binance Vision)
- API plus moderne (WebSocket combiné, ordres natifs stop/trailing/OCO)
- Liquidité supérieure (surtout pour le scaling futur)
- Future-proof pour les features avancées (funding arb, multi-pair à grande échelle)

**La seule raison de ne PAS migrer** serait si le volume de trading est trop faible pour justifier 3-4 semaines de travail. Mais vu que le bot est en développement actif avec des ambitions de scaling (1k→10k→20k USDC), le pivot est un investissement rentable.

**Next step recommandé** : Commencer par Phase 1 (abstraction) qui peut se faire sans toucher au code Kraken live. Cela posera les bases et permettra de valider l'architecture avant d'écrire le code Binance.

---

## Conclusion and Recommendations

1. **Commencer par l'abstraction** : Créer `BaseWebSocketClient`, enrichir `ExchangeRestClient`, déplacer les fichiers Kraken dans un sous-package `connectors/kraken/`. Aucun risque pour le bot live.

2. **Extraire les fees hardcodées** : 11+ occurrences dans 6 fichiers. En faire une config YAML/settings. Cela bénéficie même sans migration Binance.

3. **Implémenter `BinanceRestClient`** : Le gros du travail. Suivre le pattern de `KrakenRestClient` mais sans le mapping XBT/BTC ni les pair translations.

4. **Implémenter `BinanceWebSocketClient`** : Reprendre la base de reconnexion/heartbeat de Kraken, adapter le parsing des messages et ajouter le timer 23h.

5. **Écrire `scripts/binance_vision_import.py`** : Pour le backfill initial, Binance Vision est 100x plus rapide que la pagination REST.

6. **Mettre à jour les backtests** : Changer les fees par défaut de 0.16%/0.26% à 0.10%/0.10%. Les résultats de stratégie vont améliorer significativement.

7. **Tester en paper** : Minimum 2 semaines de paper trading Binance avant de passer live.

8. **Ne pas toucher aux stratégies** : Elles sont exchange-agnostic. Le refactor ne doit impacter QUE la couche connectors + settings.

9. **Garder Kraken en parallèle** : Ne pas supprimer le code Kraken. Garder la possibilité de revenir en changeant une config.

10. **Budget BNB** : Acheter ~10-20 USDC de BNB pour le discount de fees (25% de réduction). ROI immédiat.
