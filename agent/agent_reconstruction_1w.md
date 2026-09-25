# Tâche agent — reconstruction des 8 estampilles 1 w manquantes (USDT Binance)

**Mode : plan mode. Nouvel agent. Deux étapes séparées par un gate humain : étape 1 lecture seule → rapport → validation Bruno → étape 2 écriture.** Ne rien écrire en base, ne rien committer avant le gate.

## 0. À lire avant tout (dans cet ordre)

1. `CLAUDE.md`, `PROJECT_CONTEXT.md` (état au 24/09, v2.12.0-c3-v2.1, origin/dev = f2ca821).
2. `skills/database.md` — connexion (tunnel 5433 vs serveur), filtre `exchange='binance'`, batch ≤ 1000, pièges hypertable. **Serveur : `git pull` vers f2ca821 avant tout accès base.**
3. `skills/binance_import.md` et `scripts/binance_vision_import.py` — convention end-stamped, `ON CONFLICT DO NOTHING`, parse des klines (quelles colonnes Vision alimentent `vwap` et `trades_count`).
4. `docs/protocole_c3.md` § A.8 (bloc « Ce que la lecture des données laisse attendre », clause reconstruction) et § L.1 (manifeste).
5. `results/data_inventory_usdt_2019_20260923/inventory.md` § 1.2/1.3 — les 8 estampilles 1 w isolées.
6. `scripts/audit/c3_common.py` : `weekly_stamps_in`, `first_stamp_strictly_after`, `longest_missing_run`, `WEEK_MINUTES`, et la fonction qui calcule D1 sur un artefact de couverture.
7. `src/krakenbot/models/market_data.py` (`OHLCData`, PK `timestamp, pair, interval, exchange`), `docs/RESEARCH_LOG.md` (format d'entrée).

## 1. Contexte

Sur `exchange='binance'`, paires `BTC/USDT`, `ETH/USDT`, `SOL/USDT`, `interval=10080`, huit estampilles hebdomadaires manquent, identiques sur les trois paires (convention end-stamped, stamp = lundi 00:00 UTC de fin de période) :

```
2022-06-06  2022-07-04  2022-09-05  2022-10-03  2022-11-07  2022-12-05  2025-02-03  2025-03-03
```

Les six de 2022 sont dans le préfixe de la première campagne (`(2021-03-01, T=2024-11-22T04:48Z]`) : D1 1 w = 188/194 = 96,9 % < 97 %, ensemble admissible vide. Les deux de 2025 sont dans la période évaluée. Le protocole v2.1 § A.8 déclenche la clause : reconstruction depuis le 1 d, décision séparée, chiffrée, rows marquées dérivées, jamais silencieuse, prérequis du manifeste.

**Décisions déjà prises (Bruno, 24/09, ne pas rouvrir) :**
- Scope = les 8 estampilles × 3 paires = 24 rows. Même mécanisme, une seule procédure.
- Marquage = table de provenance à côté (`ohlc_derived`), pas de colonne sur `market_data_ohlc`, pas de valeur `exchange` spéciale. Les rows OHLC vont dans `market_data_ohlc` avec `exchange='binance'`.
- D1 compte les rows dérivées comme observées ; le manifeste de la campagne listera les 8 estampilles dérivées (lues dans `ohlc_derived`).
- Entrée RESEARCH_LOG datée **avant** le commit d'écriture.

## 2. Étape 1 — lecture seule (aucune écriture, aucun commit)

Script `scripts/audit/reconstruct_1w.py`, sous-commande `check` (ou flag `--dry-run` par défaut). Sortie : `results/reconstruction_1w_2022_2025/check_report.md` + `check_report.json`. Le script est le même que celui de l'étape 2 : l'étape 1 est son mode sans écriture.

Méthode de reconstruction (à coder une seule fois, fonction pure sur 7 rows 1 d, `Decimal` partout) :

- sélection : pour la semaine de stamp `S` (lundi 00:00), les rows 1 d (`interval=1440`) de stamps `S − 6 j, S − 5 j, …, S` (end-stamped : le row stampé mardi 00:00 est le lundi). Exactement 7 rows, sinon la semaine est **non reconstructible**.
- `open` = open du premier jour ; `close` = close du dernier ; `high` = max ; `low` = min ; `volume` = Σ ; `trades_count` = Σ (si les 7 sont non NULL, sinon NULL) ; `vwap` : voir contrôle (c).

Mesures à produire, chiffrées, par paire :

**(a) Diagnostic.** Confirmer que les 8 stamps manquent et qu'aucune autre ne manque sur `(2021-03-01, 2026-06-29]` ; `weekly_stamps_in` sur le préfixe et sur la période évaluée ; D1 1 w actuel recalculé par la fonction de `c3_common` (attendu 188/194).

**(b) Disponibilité 1 d.** Pour chacune des 8 semaines × 3 paires : 7/7 rows 1 d présentes, prix et volume non NULL. Un seul 6/7 → la semaine est signalée non reconstructible et **on s'arrête au rapport**.

**(c) Contrôle d'exactitude — le cœur de l'étape.** Appliquer la méthode à **toutes** les semaines 1 w présentes dans `(2021-03-01, 2026-06-29]` (≈ 270 par paire, 1 w de SOL comprise) et comparer à la row Vision stockée :
- `open, high, low, close, volume` : égalité `Decimal` stricte, attendu **0 mismatch**. Tout mismatch est listé (stamp, colonne, valeur Vision, valeur reconstruite). Un seul mismatch sur ces cinq colonnes → pas d'écriture, rapport et retour à Bruno.
- `trades_count` : idem, chiffré à part.
- `vwap` : mesurer d'abord s'il est peuplé sur les rows Binance 1 w et 1 d, et s'il est lu quelque part sur le chemin backtest/C3 (`grep vwap` sur `scripts/`, `src/krakenbot/backtesting`, `strategies`, `indicators` ; l'indicateur VWAP de `multi_timeframe.py` recalcule-t-il depuis OHLCV ou lit-il la colonne ?). Si peuplé : comparer Σ(vwap_d·vol_d)/Σvol_d à la valeur stockée et chiffrer l'écart max. **Proposer** (pas décider) : NULL si rien ne lit la colonne, sinon la formule avec écart documenté.

**(d) Cause, boîte de temps 20 min.** Les 8 semaines sont toutes à cheval sur une frontière de mois, mais d'autres semaines à cheval sont présentes (2022-05-02, 2023, 2024). Regarder comment `binance_vision_import.py` / le fichier mensuel Vision 1 w rangent une semaine à cheval ; noter l'hypothèse, sans chercher plus loin. Ça ne change pas le remède.

**(e) Idempotence future.** Confirmer que `ON CONFLICT DO NOTHING` de l'import Vision protège les rows dérivées d'un écrasement lors d'une reprise (idempotent, hors fenêtre — reprise 2026-07/08 prévue) ; documenter la conséquence : une vraie row Vision n'écrasera jamais une row dérivée sans action explicite.

**Fin de l'étape 1 :** rapport présenté à Bruno avec les chiffres (a)–(e) et la proposition vwap. **Stop.**

## 3. Étape 2 — écriture (après validation explicite de Bruno)

### 3.1 Table de provenance `ohlc_derived`

Migration alembic (nouvelle table uniquement, aucun ALTER sur `market_data_ohlc`) + modèle SQLAlchemy `OHLCDerived` dans `src/krakenbot/models/market_data.py` :

| colonne | type | note |
|---|---|---|
| `timestamp, pair, interval, exchange` | PK, mêmes types que `OHLCData` | FK logique vers la row dérivée |
| `method` | String | `"agg_1d_v1"` |
| `source_interval` | Integer | 1440 |
| `source_stamps` | JSONB | les 7 stamps 1 d, ISO |
| `source_sha256` | String(64) | sha des 7 rows 1 d sérialisées (repr `Decimal`, ordre fixé) — preuve rejouable |
| `vwap_policy` | String | `"null"` ou `"weighted"` |
| `script_sha256` | String(64) | sha du script |
| `git_sha` | String(40) | |
| `created_at` | TIMESTAMPTZ | |
| `note` | Text | référence RESEARCH_LOG |

Commentaire de table : « Rows de `market_data_ohlc` non observées, dérivées par agrégation. Une row ici ⟺ la row OHLC correspondante n'est pas une donnée d'exchange. »

### 3.2 Écriture

`reconstruct_1w.py write` : rejoue le contrôle (c) **avant** d'écrire (0 mismatch OHLCV ou abort), insère les 24 rows OHLC (`pg_insert … on_conflict_do_nothing`, un seul batch) puis les 24 rows de provenance, dans une transaction. Toute row déjà présente en OHLC = abort, pas de DO NOTHING silencieux sur le périmètre demandé. Puis relit et imprime : D1 1 w recalculé sur le préfixe (attendu **194/194**), couverture sur la période évaluée, `SELECT count(*) FROM ohlc_derived`.

Environnement d'exécution : celui que Bruno indique (tunnel depuis le Mac suffit pour 24 rows ; si serveur, `git pull` d'abord). `DATABASE_URL` via `load_dotenv()`, jamais `Settings()` (piège 5432, cf. `skills/database.md`). `structlog`, `Decimal`, `exchange='binance'` littéral (script de données, pas prod).

### 3.3 Rapport final

`results/reconstruction_1w_2022_2025/report.md` : commande exacte, git sha, chiffres (a)–(e), 24 rows écrites (stamp, paire, OHLCV), D1 avant/après, décision vwap, hypothèse cause. Ce dossier sera référencé par le manifeste.

### 3.4 RESEARCH_LOG

Entrée « Reconstruction des 8 estampilles 1 w USDT (inscrite le JJ/09/2026, avant l'écriture) », format du fichier : périmètre, méthode, résultat du contrôle (c), décision D1 « comptées comme observées, listées au manifeste », renvoi au rapport. Le commit de cette entrée **précède** le commit qui contient l'écriture effective / le rapport final.

## 4. Tests

`tests/test_scripts/test_reconstruct_1w.py`, hermétiques (pas de base) :
- fonction d'agrégation sur 7 rows synthétiques : OHLCV, `trades_count`, NULL propagation, refus si ≠ 7 rows, refus si un stamp ne tombe pas sur la grille `S − k j` ;
- sélection des stamps sources pour un `S` donné (test de l'off-by-one end-stamped) ;
- sérialisation `source_sha256` stable (même input → même sha, ordre indépendant de l'ordre d'entrée) ;
- `write` refuse si le contrôle renvoie un mismatch (mock).

`poetry run pytest tests/test_scripts/test_reconstruct_1w.py` vert, suite complète verte, `ruff` propre sur les fichiers touchés.

## 5. Hors scope — ne pas toucher

Mesure SOL / D2, inventaire des modes bear lisant le 1 w, dettes 21/22, `binance_vision_import.py`, `c3_common.py` et toute la chaîne C3, `MultiStrategyRouter` / `GeminiGlobalRiskManager` / `ExecutionEngine`, tout amendement du protocole. Si un problème hors scope apparaît, le noter dans le rapport, ne pas le traiter.

## 6. Critère de fin

1. Contrôle (c) : 0 mismatch OHLCV sur toutes les semaines présentes × 3 paires, chiffré dans le rapport.
2. D1 1 w sur le préfixe v2.1 = 194/194 par les fonctions de `c3_common`.
3. 24 rows dans `market_data_ohlc`, 24 rows dans `ohlc_derived`, relues et listées.
4. Tests + suite complète verts.
5. RESEARCH_LOG écrit avant le commit d'écriture.
6. Commits atomiques, dans l'ordre :
   - `feat(data): ohlc_derived provenance table + reconstruct_1w check`
   - `test(data): reconstruct_1w aggregation and guards`
   - `docs(research): RESEARCH_LOG — reconstruction 8 estampilles 1w USDT`
   - `feat(data): reconstruct_1w write — 24 rows + report`
   - `docs: CODE_MAP / skills/database.md (table ohlc_derived)`
