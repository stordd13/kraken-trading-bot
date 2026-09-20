# AGENT B3 — Données Bybit EU : import historique, backfill de gaps, TaskScheduler générique

> **Mode : PLAN d'abord.** Tu proposes un plan détaillé (fichiers touchés, ordre des étapes,
> points de décision), tu **STOP**, Bruno valide, puis tu exécutes. Même règle à chaque gate.
> Durée cible : 2 jours. Branche : `feat/b3-bybit-data` depuis `dev` (départ `v2.4.0-b2-bybit-ws`).
> **Interdit absolu : push sur `main`** (deploy.yml redémarre le trader, qui doit rester stoppé
> jusqu'à B4/B5). Interdit aussi : toucher à `MultiStrategyRouter`, `GeminiGlobalRiskManager`,
> `ExecutionEngine`, placer le moindre ordre, ou toucher aux rows `exchange='binance'` / `'kraken'`.
> ⚠️ Le collector Bybit tourne **EN PRODUCTION** sur Hetzner depuis le 2026-09-09 18:12 UTC et écrit
> dans `market_data_ohlc` (`exchange='bybit'`). Tout ce que fait cette phase cohabite avec lui.
> Ne jamais stopper `krakenbot-collector` sans instruction explicite de Bruno.

---

## 0. Lecture obligatoire avant le plan

- `CLAUDE.md` (règles d'or), `PROJECT_CONTEXT.md`, `docs/CODE_MAP.md`
- `skills/bybit.md` — §§ « Données historiques (B3) », « Rate limits », requêtes SQL de contrôle
- `skills/database.md` (batch 1000, ON CONFLICT, jamais réimporter sans vérifier) et
  `skills/deployment.md` (tmux pour les tâches longues, opérations DB lourdes = serveur direct, jamais via tunnel)
- La dette à rembourser : `src/krakenbot/scheduler/task_scheduler.py` (`KrakenRestClient` en dur :84,
  import `scripts.fetch_ohlc` :174) et la garde kraken-only de `src/krakenbot/collector.py` (:126-139)
- `src/krakenbot/connectors/exchange.py` (Protocol `fetch_ohlcv` + factories) et
  `src/krakenbot/connectors/bybit/rest.py::fetch_ohlcv` (B1, limit max 1000)
- Modèles de code : `scripts/binance_vision_import.py` (batch inserts idempotents `ON CONFLICT DO
  NOTHING`), `scripts/backfill_binance_gap.py` (détection par MAX(timestamp)),
  `scripts/audit/bybit_q4_history.py` (pagination kline validée en B0)
- `scripts/fetch_ohlc.py` — **lecture seule**, pour comprendre ce qu'on remplace

## 1. Objectif

Trois livrables :
1. **Historique Bybit EU complet en DB** : 3 paires × 7 TF, toute la profondeur EU
   (depuis 2025-06-11, ~2.5M candles), `exchange='bybit'`.
2. **Backfill de gaps exchange-agnostic**, démontré sur les gaps réels existants (voir §3, étape 1).
3. **TaskScheduler via la factory** : le backfill périodique tourne enfin (il n'a jamais marché
   pour Binance — dette historique), pour n'importe quel exchange.

Plus une petite dette WS (§2.5). Décisions du pivot, non re-débattables : les backtests B4 restent
sur les données **Binance** ; les données Bybit servent de contrôle out-of-sample et de warmup live.

## 2. Spec technique

### 2.1 Décision d'architecture (actée, ne pas rediscuter)

**La logique de backfill vit dans `src/krakenbot/`** (module nouveau, p.ex. `data/backfill.py` —
propose l'emplacement dans ton plan), construite sur `ExchangeRestClient.fetch_ohlcv` du Protocol.
Les scripts CLI sont des wrappers minces autour de ce module. Raison : `src/` qui importe depuis
`scripts/` est précisément la dette qu'on rembourse (`task_scheduler.py:174`) — ne pas la recréer.

### 2.2 Import historique — `scripts/bybit_kline_import.py` (one-shot)

- **Source : endpoint brut `GET /v5/market/kline?category=spot`** (via l'instance ccxt du client B1
  ou aiohttp, propose), **pas** `fetch_ohlcv` ccxt. Raison : ccxt renvoie `[ts,o,h,l,c,v]` sans le
  `turnover`, or le WS écrit `vwap = turnover/volume` — un import ccxt laisserait `vwap` NULL sur
  15 mois, incohérent avec les rows WS. Le brut renvoie
  `[startTime(ms), open, high, low, close, volume(base), turnover(quote)]`.
- Pagination : `limit=1000`, liste **descendante** (vérifié en B0), avancer par
  `last_start + interval` ; condition d'arrêt en fin d'historique à **prouver** dans le rapport,
  pas à supposer. ~2 532 appels pour tout l'historique, **~15 min** au rate limit
  (`enableRateLimit=True` suffit, kline public coût 5, burst validé en B0 ; pas de headers de
  limite sur les endpoints publics). Si la durée explose, c'est une anomalie : investiguer, pas attendre.
- Convention timestamp DB : `timestamp = start + interval` (= `end + 1 ms` Bybit), identique au WS B2.
  Alignement grille obligatoire.
- `vwap = turnover / volume` quantisé 1e-8, `None` si `volume == 0` ; `trades_count = None` ;
  **les candles `volume=0` sont des candles plates à écrire, pas des trous** (les premières candles
  EU de juin 2025 sont plates).
- `Decimal` partout. Insert : `pg_insert(OHLCData)` + `ON CONFLICT DO NOTHING`, batch 1000
  (pattern `binance_vision_import.py`). Les candles déjà écrites par le collector font foi,
  l'import n'écrase jamais.
- Idempotent et reprennable : reprise par `MAX(timestamp)` par (pair, interval), `--force-full`
  pour rescanner. CLI : `--pairs`, `--intervals`, `--since`, `--dry-run`. structlog, progression loggée.
- **Exécution : sur le serveur, dans tmux**, collector actif (c'est voulu). Jamais via le tunnel.

### 2.3 Backfill de gaps — module `src/` + CLI `scripts/backfill_gap.py`

- Client REST via `build_exchange_rest_client(settings)` (read-only), exchange courant =
  `settings.exchange_name`, **aucun littéral**.
- Détection par (pair, interval) : **trous internes** (query LAG, cf. `skills/bybit.md`) **ET gap
  de fin** (`MAX(timestamp)` → now, moins la candle en cours). Attention : sur Bybit les candles
  plates existent en DB (volume=0), donc un trou est un vrai trou.
- Comblement : `fetch_ohlcv(pair, interval, since=…)` + insert `ON CONFLICT DO NOTHING`, même
  convention timestamp. Si le vwap est reconstructible à coût nul (endpoint brut), le faire ;
  sinon `vwap=None` sur les candles backfillées est acceptable (1-2 candles/nuit) — tranche dans le plan.
- `--dry-run` imprime la table des gaps sans fetch. Log structuré par gap
  (pair, interval, bornes, candles récupérées).
- `backfill_binance_gap.py` : remplacé par le script générique — proposer suppression dans le plan.
- `scripts/fetch_ohlc.py` (Kraken legacy) : une fois le scheduler migré et `backfill_binance_gap.py`
  remplacé, il n'a plus aucun consommateur. **Proposer sa suppression dans le plan — décision humaine.**

### 2.4 TaskScheduler générique + réactivation dans le collector

- `task_scheduler.py` : client via la factory, plus de `KrakenRestClient` ni d'import `scripts.*`.
  Le job périodique devient un **backfill de gaps** (module 2.3), pas un fetch aveugle de N jours × 7 TF.
  Garder APScheduler, `TaskExecutionLog`, les events `SCHEDULER_TASK_*`.
- **Cron par défaut à revoir** : `0 2 * * *` tombe en plein dans la fenêtre des fermetures 1006
  observées (01:00–02:40 UTC) — backfiller *pendant* la casse nocturne n'a pas de sens. Propose un
  défaut décalé (p.ex. 03:30 UTC) pour passer *après*.
- `collector.py` : suppression de la garde `exchange_name == "kraken"` — le scheduler s'instancie
  pour tout exchange, contrôlé par `SCHEDULER_ENABLED`. Log explicite de chaque exécution
  (gaps trouvés / remplis). Client fermé proprement au stop.

### 2.5 Petite dette WS (au passage, zéro logique)

Renommer le kwarg `timestamp=` des appels structlog (collision avec la clé du renderer) en
`candle_timestamp` dans `connectors/bybit/ws.py` **et** `connectors/binance/ws.py`.
Rien d'autre sur les WS. Le renommage sera visible après le restart collector (§3, étape 4).

## 3. Validation et séquencement serveur (ORDRE IMPÉRATIF)

Le séquencement compte : l'import historique couvre jusqu'à maintenant, donc il comblerait aussi
les gaps existants — **la démo du backfill doit donc précéder l'import complet.**

1. **Démo backfill sur gaps réels (AVANT l'import)** : déploiement du code sur le serveur
   (git pull de la branche, `poetry install`), puis `backfill_gap.py --dry-run` — il doit lister au
   minimum les 2 gaps connus : **candles 1m de 01:05 UTC le 11/09 pour BTC/USDC et SOL/USDC**
   (timestamp DB `01:06:00`), perdues pendant la fermeture 1006 de 01:04:54 — plus tout gap des
   nuits suivantes. Run réel, preuve SQL avant/après dans le rapport. **Gate STOP** : résultat
   soumis à Bruno avant de passer à l'import.
2. **Import historique** en tmux (`tmux new -s b3-import`), collector actif. Validations SQL
   post-import (requêtes de `skills/bybit.md`, sorties brutes dans le rapport) :
   counts et MIN/MAX(timestamp) par pair × TF (MIN ≈ 2025-06-11) ; désalignement grille = 0 ;
   zéro trou interne résiduel (query LAG).
3. **Cohérences croisées** :
   - **1d/1w** : comparer les timestamps `interval IN (1440, 10080)` Bybit vs Binance sur la période
     commune — même convention d'ouverture exigée (semaine lundi 00:00 UTC, etc.), sinon le warmup
     live de l'analyzer mélangera deux grilles. Divergence → **STOP**, on tranche.
   - **Prix** (style Q8) : corrélation des closes 1h Bybit vs Binance par paire sur la période de
     chevauchement + écart médian/max. Attendu : corrélation > 0.999, écart médian ~bruit. C'est la
     re-validation empirique de « backtests sur données Binance ». Écart anormal → **STOP**, rapporter.
   - **Chevauchement WS/REST** : sur quelques candles écrites par le WS depuis le 09/09, OHLCV
     identiques entre la row DB et ce que renvoie le REST (sanity, 1 requête suffit).
4. **Restart collector** (`sudo systemctl restart krakenbot-collector`) pour activer le scheduler et
   le renommage `candle_timestamp`. Vérifier au log : service up, `task_scheduler_started` +
   `num_jobs`, plus aucun kwarg `timestamp=`. Le restart crée un mini-gap → le scheduler ou un run
   manuel de `backfill_gap.py` doit le combler (deuxième démonstration, gratuite).
5. **Observation scheduler** : au moins une exécution périodique loggée (`TaskExecutionLog` +
   gaps trouvés — 0 attendu en régime de croisière hors coupures nocturnes).

### Tests et code

- `poetry run pytest -q` vert (suite complète, 967 tests collectés post-B0.5 — zéro régression,
  46 tests WS inclus), `ruff check` / `ruff format` propres, mypy sans nouvelle erreur.
- Unitaires nouveaux : parsing kline brut (vwap, volume=0, convention timestamp), pagination et
  reprise d'import (mocks), détection de gaps sur fixtures (interne, fin, aucun, candles plates),
  scheduler via factory (dispatch kraken/binance/bybit, mocks), aucun littéral exchange sur les
  chemins touchés.

## 4. Critères de fin (tous obligatoires)

- [ ] Les 2 candles 1m du 11/09 (BTC, SOL) comblées **par le backfill, avant l'import**, preuve SQL.
- [ ] Historique Bybit complet en DB : 3 paires × 7 TF depuis 2025-06-11 (~2.5M candles), aligné,
      zéro trou interne.
- [ ] Cohérences croisées §3.3 passées (1d/1w, prix, WS/REST) ou STOP documenté.
- [ ] `TaskScheduler` sans référence Kraken en dur, sans import de `scripts/`, actif dans le
      collector quel que soit l'exchange ; garde kraken-only supprimée ; ≥ 1 exécution observée.
- [ ] `pytest` + `ruff` verts, mypy sans nouvelle erreur.
- [ ] Logs WS sans kwarg `timestamp=` (bybit + binance).
- [ ] Rapport `results/B3_bybit_data_report.md` : décisions, outputs SQL bruts, durée réelle de
      l'import, anomalies, comportement du premier run schedulé.
- [ ] Docs à jour : `skills/bybit.md` (§ B3 fait, runbook import/backfill), `PROJECT_CONTEXT.md`,
      `ROADMAP.md` (B3 ✅), `docs/CODE_MAP.md` régénéré (méthode dans son en-tête).

## 5. Commits attendus

Atomiques, sur `feat/b3-bybit-data`, PR vers `dev` uniquement :
1. `feat(data): exchange-agnostic gap backfill module + CLI`
2. `feat(scripts): bybit historical kline import (raw v5, resumable, batch 1000)`
3. `refactor(scheduler): TaskScheduler via exchange factory, gap-based periodic backfill`
4. `fix(ws): rename shadowed timestamp log kwarg to candle_timestamp`
5. `test(b3): …` séparés si volumineux
6. `docs(b3): report + skills + code map`
7. (si validé au plan) `chore: remove fetch_ohlc.py + backfill_binance_gap.py (superseded)`

## 6. Clôture de phase — checklist HUMAINE (Bruno, pas l'agent)

1. Review du plan, puis du diff (scheduler surtout : c'est du code qui tournera 24/7).
2. Merge dans `dev`, push, vérifier `git log --oneline -1 origin/dev`.
3. Serveur : séquence §3 dans l'ordre (démo backfill → import → cohérences → restart → observation).
4. Tag `v2.5.0-b3-bybit-data`, push du tag, zip pour le copilote. B4 peut s'écrire.

## 7. Hors scope (ne pas toucher)

- Fees maker/taker distincts dans `backtest.py` → ouverture de B4.
- Mesure de spread nocturne (`bybit_q3_orderbook.py`) → avant B4, hors agent.
- `deploy.yml` (découplage trader/collector) → prérequis B5.
- Suppression des données `exchange='kraken'` → après validation live.
- `execution/` (`normalize_asset_*`, type hints Kraken) → dette séparée.
- Toute stratégie, tout ordre, tout push sur `main`.

## 8. En cas de doute

STOP et question à Bruno plutôt qu'une hypothèse silencieuse. En particulier : condition d'arrêt de
la pagination, divergence de convention 1d/1w, écart de prix anormal sur la période commune,
comportement inattendu du `ON CONFLICT` sous chevauchement WS/REST, ou tout résultat SQL qui ne
colle pas aux estimations (~2.5M candles, ~15 min d'import).
