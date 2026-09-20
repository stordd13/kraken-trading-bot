# AGENT B1 — BybitRestClient (Bybit EU, spot)

> Mode : **Plan mode**. Propose le plan (fichiers créés/modifiés, signatures, ordre des
> commits), attends validation humaine, puis exécute.
> Branche : `feat/b1-bybit-rest` depuis `dev` (tag de départ `v2.2.0-b05-cleanup`).
> Ne JAMAIS toucher : `MultiStrategyRouter`, `GeminiGlobalRiskManager`, `ExecutionEngine`.

---

## 0. Lecture obligatoire avant le plan

1. **`skills/bybit.md`** — la source de vérité de cette phase : endpoints `.eu`, filtres de
   lot, pièges ccxt (market BUY, PostOnly, `orderLinkId`), mapping `retCode`, fees. Ne rien
   re-découvrir, ne rien contredire sans le signaler.
2. `CODE_MAP.md` — sections connectors/ et config/.
3. `src/krakenbot/connectors/binance/rest.py` — le modèle à cloner (structure, paper mode,
   normalisation des retours). `src/krakenbot/connectors/exchange.py` — Protocol + factory.
4. `src/krakenbot/config/settings.py` — `BinanceSettings` (pattern à imiter), `ExchangeFees`.
5. `scripts/audit/bybit_common.py`, `bybit_q1_endpoints.py`, `bybit_q6_orders.py`,
   `bybit_q7_ratelimits.py` — à relancer avec les clés (section 2).

## 1. Objectif

Un `BybitRestClient` complet et testé, sélectionnable via la factory, validé par un
round-trip d'ordre paper avec les vraies clés API sur `api.bybit.eu`. Rien d'autre :
pas de WebSocket (B2), pas d'import historique (B3), pas de fees backtest (B4).

## 2. Préalable — clés API (bloquant, humain dans la boucle)

Le `.env` doit contenir `BYBIT_API_KEY` / `BYBIT_API_SECRET` (clés read-only créées sur
bybit.eu). Si absentes au démarrage : STOP, demander à l'humain.

Première action une fois les clés en place, AVANT d'écrire le client — relancer les audits
non conclus de B0 et consigner les réponses dans `results/bybit_integration_audit.md`
(section « Levées post-B0 ») :
- `bybit_q1_endpoints.py` : type de compte (UTA/`UNIFIED` ?), permissions, endpoints privés
- `bybit_q6_orders.py` : comportement ordres réels (test avec des montants minimaux si
  écriture nécessaire → demander à l'humain de passer les clés en trade AVANT, jamais de
  clés withdraw)
- `bybit_q7_ratelimits.py` : headers `X-Bapi-Limit*` réels
- Lever `priceLimitRatioX = 0.5 %` : confirmer le comportement sur un LIMIT loin du prix
  (rejet ? code ?) — impact grilles ATR larges, à documenter dans le skill.

Si une réponse contredit une hypothèse du skill (ex : pas UTA, permissions manquantes) :
STOP, rapporter avant de coder.

## 3. Spec technique

### 3.1 `config/settings.py`
- `BybitSettings(BaseSettings)` : `env_prefix="BYBIT_"`, même pattern que `BinanceSettings`.
  Champs : `api_key`, `api_secret` (SecretStr), `hostname` (default `"bybit.eu"`),
  `recv_window` (default 5000), `account_type` (default `"UNIFIED"`).
- `ExchangeFees.bybit_defaults()` : maker `Decimal("0.0010")`, taker `Decimal("0.0025")`,
  spread `Decimal("0.0002")`, slippage `Decimal("0.0002")` (valeurs du skill).
- `exchange_name` : accepter `"bybit"`. **Décision à trancher dans le plan** (dette
  documentée n°1, incident serveur du 7 sept) : remplacer le default `"kraken"` par une
  erreur explicite au setup si la variable n'est pas définie, OU default `"bybit"`.
  Proposer, avec l'impact sur les tests existants ; l'humain tranche.
- `.env.example` mis à jour.

### 3.2 `connectors/bybit/rest.py`
Clone structurel de `binance/rest.py`, adapté selon `skills/bybit.md` :
- ccxt : `ccxt.bybit({"hostname": settings.hostname, "options": {"defaultType": "spot",
  "adjustForTimeDifference": True}})`, `enableRateLimit=True`, `load_markets()` obligatoire
  à l'init (les filtres EU diffèrent du global).
- Fees : JAMAIS lues depuis ccxt (`describe()` renvoie du générique) — via `ExchangeFees`.
- `place_limit_order` : support `timeInForce="PostOnly"` (c'est un timeInForce, pas un
  flag) ; rejet PostOnly (prix croisé) = retour normalisé permettant au caller de re-coter,
  pas une exception fatale.
- `place_market_order` BUY : ne JAMAIS passer `price` à ccxt (piège 79 000×, cf. skill).
  Montant en quote → `params={"cost": ...}`.
- `clientOrderId` → `orderLinkId` (≤ 36 chars).
- Mapping `retCode` → exceptions projet existantes (`core/exceptions.py`) : `170131` →
  InsufficientBalanceError, `170213` → order not exists, `10006`/403 → RateLimitError,
  `10002` → erreur horloge (message actionnable). HTTP 200 avec `retCode != 0` = erreur.
- Arrondis : `amount_to_precision` / `price_to_precision` post-`load_markets()`.
  `MIN_NOTIONAL = Decimal("5")` (skill).
- Paper mode : même mécanique que le client Binance (balance simulée, fills en mémoire).
- Decimal partout, structlog partout, imports absolus.

### 3.3 `connectors/exchange.py`
Branche `"bybit"` dans `build_exchange_rest_client`. Ne pas toucher la branche WS
(B2) — si la factory WS exige une entrée, lever NotImplementedError explicite.

### 3.4 Tests
- Unitaires avec ccxt mocké : mapping retCode, PostOnly, market BUY sans price,
  arrondis lot/tick, MIN_NOTIONAL, paper mode. Pattern des tests binance existants.
- Un test d'intégration marqué (skip par défaut, opt-in via env) qui exige les vraies
  clés : `get_balance`, `fetch_ohlcv`, et le round-trip paper.

## 4. Validation — critères de fin

1. `poetry run pytest -q` vert (tests unitaires nouveaux inclus).
2. `poetry run ruff check .` propre ; mypy sans nouvelle erreur.
3. Scripts audit Q1/Q6/Q7 relancés, résultats consignés, aucune contradiction bloquante
   avec le skill (ou contradictions documentées et arbitrées).
4. **Round-trip paper avec vraies clés sur api.bybit.eu** : place limit (PostOnly) →
   status → cancel ; place market simulé paper → fill → balance cohérente. Sortie de
   la démonstration collée dans le rapport final.
5. `skills/bybit.md` mis à jour avec ce qui a été appris (priceLimitRatioX, UTA, headers
   rate limit) — le skill reste la source de vérité pour B2/B3.

## 5. Commits attendus

1. `feat(config): BybitSettings + ExchangeFees.bybit_defaults + exchange_name bybit`
2. `feat(connectors): BybitRestClient (spot, paper mode, retCode mapping)`
3. `feat(connectors): bybit branch in build_exchange_rest_client`
4. `test(bybit): unit tests + opt-in integration test`
5. `docs(bybit): audit follow-ups (Q1/Q6/Q7, priceLimitRatioX) in skill + audit report`

## 6. Clôture de phase — checklist HUMAINE (pas l'agent)

Dans cet ordre, en vérifiant chaque sortie :
1. Review du plan, puis review du diff (surtout settings.py et la factory).
2. Merge dans `dev` (local ou PR) — vérifier : `git log --oneline -1 origin/dev` montre
   le merge APRÈS push.
3. Tag `v2.3.0-b1-bybit-rest`, push du tag.
4. Serveur : `git checkout dev && git pull` + vérification d'un fichier témoin.
5. Nouveau zip de référence pour le copilote.
