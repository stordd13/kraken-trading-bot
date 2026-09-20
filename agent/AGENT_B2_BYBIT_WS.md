# AGENT B2 — BybitWebSocketClient (Bybit EU, WS public spot)

> Mode : **Plan mode**. Propose le plan (structure du client, insertion dans
> `BaseWebSocketClient`, stratégie watchdog, ordre des commits), attends validation
> humaine, puis exécute.
> Branche : `feat/b2-bybit-ws` depuis `dev` (tag de départ `v2.3.0-b1-bybit-rest`).
> Ne JAMAIS toucher : `MultiStrategyRouter`, `GeminiGlobalRiskManager`, `ExecutionEngine`.

---

## 0. Lecture obligatoire avant le plan

1. **`skills/bybit.md`**, section WebSocket — source de vérité : endpoint
   `wss://stream.bybit.eu/v5/public/spot`, topics `kline.{interval}.{SYMBOL}` /
   `tickers.{SYMBOL}`, max 10 args par requête subscribe, ping applicatif
   `{"op":"ping"}` / 20 s, mapping intervalles, format kline (`end` inclusif,
   `confirm`, volume/turnover, pas de trades_count).
2. `src/krakenbot/connectors/binance/ws.py` — le modèle : structure, `_save_ohlc`
   optionnel via `db_manager`, `_data_flow_watchdog`, `_preventive_reconnect_timer`
   (23 h), alertes Telegram.
3. `src/krakenbot/connectors/base_ws.py` — l'ABC à implémenter.
4. `src/krakenbot/connectors/exchange.py` — remplacer le NotImplementedError de la
   branche WS bybit.
5. `src/krakenbot/collector.py` + `CODE_MAP.md` (sections connectors/, collector).

## 1. Objectif

Un `BybitWebSocketClient` public spot complet, sélectionnable via la factory, qui
alimente `market_data_ohlc` avec `exchange='bybit'` pour 3 paires × 7 timeframes,
robuste aux zombies et aux reconnexions. Rien d'autre : pas d'import historique ni
de backfill (B3), pas de TaskScheduler (B3), pas de WS privé.

## 2. Spec technique

### 2.1 `connectors/bybit/ws.py` — clone structurel de `binance/ws.py`
- Connexion unique : 21 klines + 3 tickers = 24 topics → **3 requêtes subscribe**
  (max 10 args chacune). Symbole = `pair.replace("/", "")`.
- Mapping intervalles projet → Bybit : `1,5,15,60,240 → "1","5","15","60","240"` ;
  `1440 → "D"` ; `10080 → "W"`.
- Parsing kline : `data[0]`, `start`/`end` en ms, **`end` inclusif** → règle DB
  inchangée : `timestamp = end + 1 ms` (= `start + interval`), aligné Binance.
  `confirm: true` = candle clôturée (équivalent `k.x` Binance). `volume` en base,
  `turnover` en quote → `vwap = turnover / volume` (Decimal, division protégée si
  volume nul), `trades_count = None`.
- Candles `volume=0` : **valides** (candles plates, fréquentes sur EU) — les
  écrire, pas les filtrer.
- Écriture DB : même mécanique `_save_ohlc` optionnel via `db_manager` que Binance,
  `exchange="bybit"` hardcodé dans le connecteur (normal, cf. binance/ws.py:450).
- Ping applicatif `{"op":"ping"}` toutes les 20 s. Le pong arrive avec `op:"ping"`,
  `ret_msg:"pong"`. Absence de pong ~10 s → force disconnect + reconnect. Ignorer
  dans le parseur : les acks de subscribe (pas de champ `topic`) et les pongs.
- Reconnexion préventive 23 h conservée (pattern Binance).
- structlog partout, Decimal partout, imports absolus.

### 2.2 Watchdog — LE piège de la phase, à traiter dans le plan
Les klines Bybit ne sont poussées **que lorsqu'un trade a lieu** (~31 msgs / 5 min
observés sur EU, toutes paires confondues — nuit et weekend ce sera moins). Le
watchdog Binance calibré sur un flux dense déclencherait des reconnexions en boucle
sur un marché calme. Exigences :
- Le watchdog surveille le flux **agrégé** (tous topics confondus), pas un topic seul.
- Le ping/pong (20 s) est le signal de vie de la CONNEXION ; l'absence de klines est
  un signal de MARCHÉ calme, pas de zombie. Le watchdog data ne doit déclencher
  qu'avec un seuil large (proposer une valeur, ordre de grandeur ≥ 10 min sans AUCUN
  message topic, pong exclus) et logger la distinction.
- Proposer le comportement dans le plan avec justification chiffrée.

### 2.3 `connectors/exchange.py`
Remplacer le `NotImplementedError` de `build_exchange_ws_client` par la branche
bybit. Signature identique aux autres branches.

### 2.4 Collector
`collector.py` doit fonctionner avec `EXCHANGE_NAME=bybit` : WS via la factory
(déjà le cas), vérifier qu'aucun littéral binance/kraken ne bloque le chemin
(config des paires/TF, filtres). NE PAS toucher au `TaskScheduler` (hardcode Kraken
connu, dette B3) — si le collector l'instancie de façon bloquante pour Bybit, le
neutraliser proprement derrière un flag/try avec log explicite, et le noter au
rapport pour B3.

### 2.5 Tests
- Unitaires, WS mocké : parsing kline (clôturée / non clôturée / volume 0), ticker,
  ack subscribe ignoré, pong ignoré et détecté comme signal de vie, mapping
  intervalles, découpage en 3 requêtes subscribe, règle `end + 1 ms`, vwap Decimal.
- Un test d'intégration opt-in (`BYBIT_INTEGRATION=1`) : connexion réelle à
  stream.bybit.eu, réception d'au moins un message kline et un pong, sans DB.

## 3. Validation en deux temps

### Temps 1 — code fini (conditionne le merge)
1. `poetry run pytest -q` vert, ruff propre, mypy sans nouvelle erreur.
2. Test d'intégration opt-in vert.
3. **Collecte locale d'1 h** (collector en local, `EXCHANGE_NAME=bybit`, DB via
   tunnel ou locale) : candles `exchange='bybit'` présentes pour les paires/TF
   actifs, timestamps alignés sur la grille (`% interval == 0` après la règle
   +1 ms), pas de doublons, log du watchdog sans faux positif. Requête SQL de
   contrôle collée au rapport.

### Temps 2 — observation serveur 24 h (conditionne le tag et la clôture, HUMAIN)
Déploiement sur Hetzner par l'humain (checklist §5). Après 24 h :
`SELECT interval, COUNT(*), MIN(timestamp), MAX(timestamp) FROM market_data_ohlc
WHERE exchange='bybit' GROUP BY interval` cohérent, zéro gap > 2× interval sur les
TF courts (hors nuit sans trades — comparer aux tickers), aucune reconnexion en
boucle dans les logs, la reconnexion préventive 23 h a eu lieu proprement.

## 4. Commits attendus

1. `feat(connectors): BybitWebSocketClient (public spot, kline+ticker, ping 20s)`
2. `feat(connectors): bybit branch in build_exchange_ws_client`
3. `feat(collector): bybit support (config, no binance literals on the path)`
4. `test(bybit-ws): unit tests + opt-in integration test`
5. `docs(bybit): WS learnings in skill (watchdog calibration, observed msg rates)`

## 5. Clôture de phase — checklist HUMAINE

1. Review du plan (watchdog !) puis du diff. Merge dans dev, push,
   vérifier `git log --oneline -1 origin/dev`.
2. Serveur : `.env` → `EXCHANGE_NAME=bybit` + les 4 variables `BYBIT_*`
   (l'action reportée depuis B1). `git pull`, `poetry install`.
3. `sudo systemctl enable --now krakenbot-collector` — le service se réactive
   ICI, pour la première fois depuis juillet. NE PAS réactiver `krakenbot.service`
   (le trader attend B4/B5).
4. Lancer l'observation 24 h (temps 2). Vérifier les requêtes SQL le lendemain.
5. Si 24 h propres : tag `v2.4.0-b2-bybit-ws`, push du tag, nouveau zip pour le
   copilote. Sinon : rapport des anomalies, retour agent.
