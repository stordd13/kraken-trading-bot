# AGENT B0 — Audit d'intégration Bybit EU

> Mode : lecture seule. Aucune modification du code de production.
> Durée : 1 jour. Livrable unique : `results/bybit_integration_audit.md`.

---

## Contexte

Binance a suspendu ses services aux résidents UE le 1er juillet 2026 (pas d'agrément MiCA).
KrakenBot doit pivoter vers **Bybit EU** (Bybit EU GmbH, agréé MiCA via FMA Autriche).
Le compte de Bruno est vérifié sur Bybit EU. Fees spot constatées : maker 0.10 %, taker 0.25 %.

Lire avant de commencer :
- `PROJECT_CONTEXT.md`, `CLAUDE.md`
- `skills/database.md`, `skills/troubleshooting.md`
- `src/krakenbot/connectors/exchange.py` (Protocol + factory)
- `src/krakenbot/connectors/binance/rest.py` et `ws.py` (le connecteur à cloner)
- `scripts/binance_vision_import.py` (le pattern d'import à reproduire)
- `results/binance_integration_audit.md` (l'audit P0 équivalent, à prendre comme modèle de rapport)

Tu as des clés API Bybit **read-only** dans `.env` : `BYBIT_API_KEY`, `BYBIT_API_SECRET`.
Ne place aucun ordre. Ne touche pas aux fonds.

## Branche

`feat/b0-bybit-audit` depuis `dev`. Seuls fichiers autorisés :
- `results/bybit_integration_audit.md`
- `scripts/audit/bybit_*.py` (scripts d'exploration jetables, pas de tests requis)

---

## Les 8 questions auxquelles le rapport doit répondre, avec preuve

Pour chaque question : la réponse, puis l'output brut (tronqué) de l'appel qui la prouve.

### Q1 — Endpoints Bybit EU
Bybit EU GmbH utilise-t-il les endpoints globaux (`api.bybit.com`, `stream.bybit.com`) ou un
domaine dédié ? Vérifier avec les clés du compte : `GET /v5/user/query-api` et `GET /v5/account/wallet-balance`
via ccxt (`ccxt.bybit`). Si un `hostname` ccxt spécifique est nécessaire, le documenter.
Vérifier aussi le `recv_window` et l'écart d'horloge (Bybit rejette au-delà de 5 s par défaut).

### Q2 — Paires USDC
Confirmer que `BTC/USDC`, `ETH/USDC`, `SOL/USDC` existent en spot pour l'entité EU, avec pour chacune :
symbol exact, `minOrderQty`, `qtyStep` (lot size), `minOrderAmt` (min notional), `tickSize`.
Source : `GET /v5/market/instruments-info?category=spot`. Comparer avec les constantes de
`connectors/binance/rest.py` (`LOT_SIZES`, `MIN_NOTIONAL`).

### Q3 — Liquidité et spread
Pour les 3 paires, 3 mesures espacées d'au moins 2 h : best bid, best ask, spread en %,
profondeur cumulée à ±0.1 % du mid (en USDC). Source : `GET /v5/market/orderbook?category=spot&limit=50`.
Comparer avec les hypothèses backtest actuelles (spread 0.02 %, slippage 0.01 %) et proposer des
valeurs Bybit pour `ExchangeFees`.

### Q4 — Profondeur des données historiques
Pour les 3 paires × intervals `1, 5, 15, 60, 240, D, W` : date de la première candle disponible via
`GET /v5/market/kline?category=spot` (paginer en arrière depuis maintenant, `limit=1000`).
Tableau pair × interval → première date, nb de candles estimé.
Chercher aussi si Bybit publie des dumps spot kline téléchargeables (public.bybit.com ou équivalent) ;
si non, estimer le nombre d'appels API pour tout importer et le temps à `enableRateLimit=True`.

### Q5 — WebSocket v5 public
Documenter précisément pour `wss://stream.bybit.com/v5/public/spot` (ou l'URL EU si différente) :
- payload de subscribe pour `kline.{interval}.{symbol}` et `tickers.{symbol}`
- mapping intervals Bybit (`1,5,15,60,240,D,W`) ↔ minutes du projet (`1,5,15,60,240,1440,10080`)
- format exact d'un message kline (champs `start`, `end`, `confirm`, `open/high/low/close/volume`, `turnover`)
- sémantique du timestamp : `end` est-il inclusif ou exclusif ? (Binance `T` = dernière ms → on ajoute 1 ms ;
  il faut la règle équivalente pour que les timestamps DB soient alignés avec les données Binance existantes)
- ping/pong : intervalle attendu, format, comportement si absent
- limite de topics par connexion et limite de connexions
- durée de vie d'une connexion (Binance coupait à 24 h → reconnexion préventive à 23 h ; Bybit ?)
Capturer 5 minutes de messages réels sur `kline.1.BTCUSDC` et joindre 3 messages bruts au rapport.

### Q6 — Ordres (lecture seule, mais documenter pour B1)
Via la doc et `ccxt.bybit.describe()` : types d'ordres supportés en spot (Limit, Market, PostOnly,
`timeInForce` GTC/IOC/FOK), format du `orderId` et `orderLinkId`, `GET /v5/order/realtime` pour le statut,
`POST /v5/order/cancel`. Comportement d'un Market BUY spot : `qty` en quote (USDC) ou en base ?
(Binance accepte les deux via `quoteOrderQty`, ccxt bybit a `createMarketBuyOrderRequiresPrice`.)
Vérifier ce que ccxt fait pour `create_order(symbol, 'market', 'buy', amount)` sur bybit spot.

### Q7 — Rate limits
Limites REST par endpoint (`X-Bapi-Limit`, `X-Bapi-Limit-Status` headers), et ce que ccxt fait avec
`enableRateLimit`. Estimer si le collector (3 paires × 7 TF) + le trader tiennent largement sous la limite.

### Q8 — Écart de prix Binance vs Bybit
Sur les 90 derniers jours disponibles, 1h, BTC/USDC : comparer close Bybit (API) vs close Binance (DB,
`exchange='binance'`, mêmes timestamps). Reporter : corrélation, écart moyen en bps, écart max.
But : justifier (ou infirmer) la décision de backtester sur les données Binance avec les fees Bybit.

---

## Format du rapport

```
# Bybit EU — Audit d'intégration (date)

## Résumé exécutif (10 lignes max)
- Faisabilité : GO / GO avec réserves / NO-GO
- Les 3 points qui conditionnent B1-B3

## Q1 … Q8 (une section chacune : réponse, preuve, impact sur le code)

## Constantes proposées pour B1
LOT_SIZES, MIN_NOTIONAL, ExchangeFees.bybit_defaults(maker, taker, spread, slippage)

## Différences Binance → Bybit qui touchent le code existant
Tableau : composant | ce qui change | effort estimé

## Risques identifiés
```

---

## Règles

1. Lecture seule. Aucun ordre, même paper. Aucune modification hors `results/` et `scripts/audit/`.
2. Chaque réponse est prouvée par un output réel, pas par la doc seule.
3. Si une question ne peut pas être tranchée (endpoint EU inaccessible, paire absente), le dire
   explicitement avec ce qui a été tenté. Ne pas supposer.
4. Commit unique : `docs(bybit): add Bybit EU integration audit (B0)`.
