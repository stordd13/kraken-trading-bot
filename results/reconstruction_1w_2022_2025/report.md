# Reconstruction des 8 estampilles 1 w USDT — rapport final

> **Écrit et vérifié le 2026-09-24.** 24 rows `market_data_ohlc` (`exchange='binance'`, `interval = 10080`) +
> 24 rows de provenance `ohlc_derived`. **D1 1 w sur le préfixe de la première campagne : 188/194 → 194/194** sur
> BTC/USDT, ETH/USDT et SOL/USDT ; période évaluée 82/84 → 84/84. Contrôle d'exactitude : la méthode redonne les
> **810** semaines Vision présentes de la fenêtre au `Decimal` près (0 mismatch OHLCV, 0 mismatch `trades_count`).
> Opération de données : **aucune simulation, aucune sélection**. Ce dossier est celui que le manifeste de la première
> campagne référence pour les 8 estampilles dérivées.

Brief : `agent/agent_reconstruction_1w.md` (plan amendé le 24/09 : quatre amendements et deux mineurs de Bruno).
Protocole : `docs/protocole_c3.md` v2.1 § A.8 (clause de reconstruction). Journal : `docs/RESEARCH_LOG.md`, entrée 13,
committée **avant** l'écriture (`4866c7d`).

## 1. Chronologie, commits, commandes exactes

Branche `feat/c3b-reconstruction-1w`, depuis `dev` @ `b43515a` ; **mergée dans `dev` le 2026-09-24 (`00ad09a`, merge
commit, arbre identique au `5cb8a24` testé)** après la porte serveur (§ 6).

| Étape | Commit / instant (UTC) | Objet |
|---|---|---|
| 1 | `2bee227` | `feat(data): reconstruct_1w check` — script, sous-commande `check` (lecture seule) |
| 1 | `35b06ce` | `test(data): reconstruct_1w pure layer` — 37 tests |
| 1 | 2026-09-24 15:12:01 | `check` sur tree propre au `35b06ce` → `check_report.{json,md}` (JSON sha256 `f41b45f16ad880c5e641fc586ec4b479d37cc595a1e94b21f1029d5ddd310108`) |
| gate | 24/09 | GO Bruno : `--vwap-policy null`, option A confirmée, migration et `write` par le tunnel |
| 2 | `9b59c26` | `feat(data): ohlc_derived model + migration + reconstruct_1w write` |
| 2 | `9a4e1f7` | `test(data): reconstruct_1w write guards` — 56 tests au total |
| 2 | `4866c7d` | `docs(research): RESEARCH_LOG — reconstruction 8 estampilles 1w USDT` (entrée 13) |
| 2 | 15:47:07 → 15:47:12 | `alembic upgrade head` par le tunnel : `c1ae7a1c0001 → c3bd1e7a0001` |
| 2 | 15:47:19 → 15:47:26 | `write` au `4866c7d` → 24 + 24 rows, relecture verte, `write_report.{json,md}` (JSON sha256 `b0f1acecda841091790af0a81b90b2a054812dd01cab27c00a893903fb04e743`) |

Environnement : Mac, tunnel `localhost:5433 → serveur:5432`, `DATABASE_URL` du `.env` (lu par `load_dotenv`, jamais
`Settings()`). Serveur : checkout avancé en `--ff-only` de `f321ddd` à `origin/dev` = `b43515a` avant tout accès base
(`src/` inchangé entre les deux, aucun restart, collector actif) ; **aucune commande alembic sur le serveur**.

```bash
poetry run python scripts/audit/reconstruct_1w.py check \
    --output results/reconstruction_1w_2022_2025/check_report.json \
    --markdown results/reconstruction_1w_2022_2025/check_report.md
poetry run alembic upgrade head
poetry run python scripts/audit/reconstruct_1w.py write --vwap-policy null \
    --note "docs/RESEARCH_LOG.md — entrée 13 (reconstruction des 8 estampilles 1 w USDT, inscrite le 24/09/2026 avant l'écriture, commit 4866c7d)" \
    --output results/reconstruction_1w_2022_2025/write_report.json \
    --markdown results/reconstruction_1w_2022_2025/write_report.md
```

Empreintes du script : `35b06ce` (check) sha256 `1a96b958…a24b` ; `4866c7d` (write, identique à `9b59c26`) sha256
`d25e230c…966c`. Entre les deux, seuls la docstring, les imports et la CLI perdent des lignes : la couche pure qui porte
le contrôle (`aggregate_week`, `compare_week`, `control`, `d1_week`) est inchangée (`git diff 35b06ce 9b59c26`).

## 2. Méthode `agg_1d_v1`

Pour la semaine d'estampille `S` (lundi 00:00 UTC, fin de période) : les 7 rows 1 d d'estampilles `S − 6 j … S` (la row
stampée mardi 00:00 est le lundi). `open` du premier jour, `close` du dernier, `high` max, `low` min, `volume` Σ,
`trades_count` Σ si les 7 sont non NULL. Toute autre entrée — ≠ 7 rows, doublon, estampille hors de la grille,
prix ou volume NULL — rend la semaine **non reconstructible**. `Decimal` partout, sommes sous un contexte qui lève sur
toute inexactitude, valeur refusée si elle ne tient pas dans `DECIMAL(18, 8)` sans arrondi.

## 3. Mesures de l'étape 1 (`check_report.md`)

**(a) Diagnostic.** Sur `(2021-03-01, 2026-06-29]` : 270 estampilles présentes sur 278 par paire, les 8 manquantes
**exactement celles du brief**, identiques sur les trois paires, aucune hors grille. `cc.weekly_stamps_in` : 194 périodes
sur le préfixe `(2021-03-01, T = 2024-11-22T04:48Z]`, 84 sur la période évaluée. D1 1 w recalculé par
`cc.coverage_recompute` sous la règle de `c3_select.d1_for_pair` (égalité épinglée par test) : **188/194 = 96,9 %,
échoue**, trou maximal 7 j (≤ 31) ; période évaluée 82/84.

**(b) Disponibilité 1 d.** 24/24 cibles : 7/7 rows 1 d, prix et volume non NULL ; `source_sha256` par cible.

**(c) Contrôle d'exactitude.** Méthode appliquée aux **270 × 3 = 810** semaines 1 w Vision présentes de la fenêtre :
**0 mismatch OHLCV** (égalité `Decimal` stricte), `trades_count` comparé à part : **0 mismatch** sur 810. `write` a
rejoué ce contrôle dans sa transaction, avant les INSERT : 810 semaines, 0 mismatch.

**vwap.** Colonne **NULL sur toutes les rows `binance` 1 d et 1 w, USDC comme USDT** (0 non NULL sur les 12 séries,
tout l'historique). **Aucun lecteur** sur le chemin backtest / C3 : le balayage du jeton `vwap` (`scripts/backtest.py`,
runners P6/P7, `compute_benchmarks.py`, `scripts/audit/c3_*.py`, `backtest_metrics`, `replay_contract`, `strategies/`,
`indicators/` ; `src/krakenbot/backtesting` n'existe pas) ne trouve que le registre de l'indicateur VWAP de
`indicators/multi_timeframe.py`, **recalculé depuis `close` et `volume`** (`:378-379`, feature `get_vwap` `:868`). La
formule pondérée n'a aucune entrée. **Décision Bruno (24/09) : `vwap_policy = null`** — les 24 rows portent `vwap`
NULL, comme toutes les rows Binance.

**(d) Cause — probe Vision, entrée de décision.** Les deux fichiers mensuels 1 w (mois d'ouverture, mois de clôture) de
chaque cible, pour les trois symboles : 33 fichiers, tous HTTP 200. **Aucune des 24 bougies n'est servie** (24/24
absentes des deux fichiers) : il n'existait pas de row réelle à importer. Les fichiers de 2022 (Last-Modified du
02/06/2022 au 04/01/2023) et de 2025-01 / 2025-02 (04/03/2025) omettent la semaine à cheval qui finit le 2 du mois suivant
ou plus tard (le fichier 2022-12 sert encore `2023-01-02`, semaine finie le 01/01) ; le fichier **2025-03, régénéré le
08/10/2025**, sert la semaine à cheval `2025-04-07`. **Hypothèse : la règle de génération de Vision a changé, et les
fichiers de 2022 n'ont pas été régénérés.** L'import n'y est pour rien : il insère tout ce que le fichier sert.
**Conséquence** : la reprise 1 w 2026-07/08 ne devrait pas exiger de reconstruction — à vérifier au moment de la reprise
(voir § 8).

**(e) Idempotence.** `binance_vision_import.py:200-201` : `on_conflict_do_nothing(index_elements=["timestamp", "pair",
"interval", "exchange"])` (fichier sha256 `63575e0f…0514`). Une vraie row Vision servie plus tard pour une des 8
estampilles **n'écraserait jamais** la row dérivée ; la remplacer exige une action explicite (`DELETE` de la row OHLC
**et** de sa provenance, puis réimport).

**TimescaleDB.** Compression désactivée sur `market_data_ohlc` ; les 8 chunks des cibles non compressés : INSERT direct.

## 4. Écriture (étape 2, `write_report.md`)

Table de provenance `ohlc_derived` (migration `c3bd1e7a0001`, `create_table` seul, aucun ALTER sur `market_data_ohlc`),
modèle `OHLCDerived` : PK `(timestamp, pair, interval, exchange)` aux types d'`OHLCData`, `method`, `source_interval`,
`source_stamps` (JSONB), `source_sha256`, `vwap_policy`, `script_sha256`, `git_sha`, `created_at`, `note` ; commentaire
de table « Rows de market_data_ohlc non observées, dérivées par agrégation. Une row ici ⟺ la row OHLC correspondante
n'est pas une donnée d'exchange. » ; FK logique seulement (la cible est une hypertable).

`write`, dans une transaction : lecture des séries et des clés déjà dérivées ; `plan_write` rejoue le contrôle (c) et
vérifie chaque cible (absente d'OHLC et de la provenance, reconstructible, dans `DECIMAL(18, 8)`) — un seul défaut et
**aucun INSERT** ; puis deux INSERT **simples** (gate du 24/09 : un conflit lève et annule), 24 OHLC puis 24 provenance.
Relecture sur une connexion neuve, en lecture seule :

| Paire | D1 1 w préfixe avant | après | période évaluée avant | après | manquantes après | semaines contrôlées après | mismatches OHLCV après |
|---|---|---|---|---|---|---|---|
| BTC/USDT | 188/194 (échoue) | **194/194 (passe)** | 82/84 | 84/84 | 0 | 278 | 0 |
| ETH/USDT | 188/194 (échoue) | **194/194 (passe)** | 82/84 | 84/84 | 0 | 278 | 0 |
| SOL/USDT | 188/194 (échoue) | **194/194 (passe)** | 82/84 | 84/84 | 0 | 278 | 0 |

`SELECT count(*) FROM ohlc_derived` = **24** ; pour chacune des 24 rows, `source_sha256` **rejoué** depuis les 7 rows 1 d
= la valeur stockée, et la row OHLC = l'agrégat rejoué. Provenance commune : `method = agg_1d_v1`, `source_interval =
1440`, `vwap_policy = null`, `git_sha = 4866c7d39ed4c6d7f279aa2a6ef4cf8e5bd8e8f7`, `script_sha256 = d25e230c…966c`,
`created_at = 2026-09-24T15:47:20.274794Z`.

**Contrôle indépendant du script** (SQL brut, lecture seule, `evidence/independent_counts.txt`) : `binance` total
**11 952 996** = 11 952 972 + 24 ; 1 w USDT 391 / 391 / 308 (= grilles de l'inventaire) ; `ohlc_derived` 24 rows, un seul
`git_sha`, 0 provenance sans row OHLC ; `alembic_version` = `c3bd1e7a0001`.

### Les 24 rows écrites (relues)

| Paire | Semaine | open | high | low | close | volume | trades_count |
|---|---|---|---|---|---|---|---|
| BTC/USDT | 2022-06-06 | 29468.10000000 | 32399.00000000 | 29282.36000000 | 29919.21000000 | 422401.40352000 | 7249030 |
| BTC/USDT | 2022-07-04 | 21038.08000000 | 21539.85000000 | 18626.00000000 | 19315.83000000 | 508544.13970000 | 8098167 |
| BTC/USDT | 2022-09-05 | 19555.61000000 | 20576.25000000 | 19540.00000000 | 20000.30000000 | 1527594.84529000 | 38080138 |
| BTC/USDT | 2022-10-03 | 18809.13000000 | 20385.86000000 | 18471.28000000 | 19056.80000000 | 2777070.91238000 | 39023576 |
| BTC/USDT | 2022-11-07 | 20627.48000000 | 21480.65000000 | 20031.24000000 | 20905.58000000 | 2205754.83045000 | 47012044 |
| BTC/USDT | 2022-12-05 | 16428.77000000 | 17324.00000000 | 15995.27000000 | 17105.70000000 | 1572173.55626000 | 33957294 |
| BTC/USDT | 2025-02-03 | 102620.01000000 | 106457.44000000 | 96150.00000000 | 97700.59000000 | 184203.26328000 | 38100357 |
| BTC/USDT | 2025-03-03 | 96258.00000000 | 96500.00000000 | 78258.52000000 | 94270.00000000 | 373604.39736000 | 52557578 |
| ETH/USDT | 2022-06-06 | 1813.64000000 | 2016.45000000 | 1737.00000000 | 1806.23000000 | 4894188.42940000 | 5019674 |
| ETH/USDT | 2022-07-04 | 1197.79000000 | 1238.93000000 | 998.00000000 | 1074.26000000 | 7610801.14680000 | 6463507 |
| ETH/USDT | 2022-09-05 | 1426.76000000 | 1650.00000000 | 1422.08000000 | 1579.28000000 | 5044263.25510000 | 7303513 |
| ETH/USDT | 2022-10-03 | 1294.62000000 | 1400.00000000 | 1253.20000000 | 1276.72000000 | 4714233.48760000 | 5752095 |
| ETH/USDT | 2022-11-07 | 1590.45000000 | 1680.00000000 | 1502.32000000 | 1568.29000000 | 4581252.75080000 | 5675381 |
| ETH/USDT | 2022-12-05 | 1193.88000000 | 1309.77000000 | 1151.02000000 | 1279.41000000 | 3279474.59660000 | 4710731 |
| ETH/USDT | 2025-02-03 | 3232.61000000 | 3437.31000000 | 2750.71000000 | 2869.68000000 | 3917894.04870000 | 26191788 |
| ETH/USDT | 2025-03-03 | 2819.70000000 | 2839.95000000 | 2076.26000000 | 2518.11000000 | 6704218.92400000 | 34415210 |
| SOL/USDT | 2022-06-06 | 44.98000000 | 48.39000000 | 35.71000000 | 38.52000000 | 31680429.89000000 | 2209771 |
| SOL/USDT | 2022-07-04 | 39.39000000 | 41.25000000 | 30.92000000 | 33.39000000 | 32137486.49000000 | 2064570 |
| SOL/USDT | 2022-09-05 | 30.43000000 | 33.16000000 | 30.00000000 | 32.16000000 | 16639278.09000000 | 1074135 |
| SOL/USDT | 2022-10-03 | 32.33000000 | 35.41000000 | 31.65000000 | 32.06000000 | 20717720.17000000 | 1237324 |
| SOL/USDT | 2022-11-07 | 32.93000000 | 38.79000000 | 30.24000000 | 32.62000000 | 27119839.35000000 | 1806932 |
| SOL/USDT | 2022-12-05 | 14.11000000 | 14.32000000 | 12.78000000 | 13.71000000 | 20094104.49000000 | 775159 |
| SOL/USDT | 2025-02-03 | 240.49000000 | 244.70000000 | 192.31000000 | 203.51000000 | 32632945.29000000 | 25323947 |
| SOL/USDT | 2025-03-03 | 167.94000000 | 179.85000000 | 125.55000000 | 178.71000000 | 57102095.79500000 | 28665318 |

`vwap` NULL sur les 24. Valeurs identiques, chiffre pour chiffre, à celles que `check` avait reconstruites au `35b06ce`.
`source_sha256` complets et `source_stamps` : `write_report.json` (`verification.rows`).

## 5. Tests — rouges d'abord, puis mutants

`tests/test_scripts/test_reconstruct_1w.py`, hermétiques (sans base, sans réseau), **56 tests**. Attendus dérivés du
brief (§ 1, § 2, § 3.1, § 3.2) et du protocole (§ A.8 v2.1), jamais de l'implémentation ; D1 1 w épinglé à
`c3_select.d1_for_pair` sur une couverture synthétique à quatre séries dont les trois autres sont complètes (témoin
conforme). Preuves dans `evidence/` :

- **Étape 1** : 35 rouges / 1 vert contre un squelette `NotImplementedError` (`red_first_skeleton.txt`) ; le test de
  semaines à cheval, ajouté ensuite, rouge avant son helper (`red_first_straddling.txt`) ; **7 mutants** ciblés, tous
  attrapés, fichier restauré à l'identique (`mutants.txt` : off-by-one `S − 7 j`, sha dépendant de l'ordre, NULL de
  `trades_count` compté 0, nombre de rows non contrôlé, `open` pris dans l'ordre d'entrée, `load_dotenv` à l'import —
  le test vert à la naissance —, seuil D1 recopié).
- **Étape 2** : 15 rouges avant l'implémentation, 4 verts à la naissance (cas CLI : `write` n'était pas une commande —
  vert pour une mauvaise raison) (`red_first_step2.txt`) ; **10 mutants**, tous attrapés, fichiers restaurés
  (`mutants_step2.txt` : la première passe s'est arrêtée sur une ancre de mutant ambiguë — W7 trouvée deux fois — après
  W1 à W6 ; W7 à W10 relancés avec une ancre unique ; les trois cas CLI verts à la naissance mordent sous W1-W3).

**Suite complète** (`pytest -m "not slow"`, tunnel ; les 25 désélectionnés = les 24 `_full` + `test_rejeu_data_coverage::test_measured_coverage_still_matches_the_pre_registration`) :

| Avant | Résultat | Suite |
|---|---|---|
| commits `2bee227` / `35b06ce` | 1re passe : 2824 passés, **1 échec** `test_c2_replay_fidelity_db` (`Connection reset by peer` dans le tunnel) ; test seul : passe | **relance complète : 2825 passés, 6 skippés** |
| commits `9b59c26` / `9a4e1f7` / `4866c7d` | 1re passe : 2842 passés, **2 échecs** `test_grid_atr_v4_backward_compat_hash[binance, bybit]` — **cause non établie** : seule la fin du journal a été conservée ; relancés seuls : 2/2 passent (77 s), aucune donnée écrite à ce moment | **relance complète, journal complet gardé : 2844 passés, 6 skippés** |

Les commits `35b06ce`, `9a4e1f7` et `4866c7d` n'ont pas eu de passe complète propre : leur tree de code est
**identique octet à octet** à celui de la passe verte qui les précède (le commit ne fait qu'entrer dans git un fichier
déjà présent au moment du run ; `4866c7d` ne touche que `docs/RESEARCH_LOG.md`, qu'aucun test ne lit). `ruff check` et
`ruff format --check` propres sur les fichiers touchés ; `mypy src/` = 65 (baseline).

## 6. Porte serveur

**Diff de contrôle § L.3 non vide** — option A confirmée par Bruno : `src/krakenbot/models/market_data.py` (nouveau
modèle `OHLCDerived`, +95 / −1 lignes), `src/krakenbot/models/__init__.py` (export), et hors liste § L.3 `alembic/env.py`
(import) et `alembic/versions/20260924_c3bd1e7a0001_ohlc_derived_provenance.py`. Aucun comportement de backtest n'est
touché (ajout d'une table ; aucun moteur ne la lit), mais la condition 2 du § L.5 ne peut plus s'appuyer sur un SHA
antérieur pour `src/`. **Les 24 tests `_full` (`test_determinism_parallel_vs_serial_full`) sont VERTS sur le serveur au
`5cb8a24e7e594d9dbd93d4f39af8654a9891e3a4`** : `tests=24 failures=0 errors=0 skipped=0`, 2026-09-24 20:36:25Z →
21:47:17Z (70 min 52 s), lancés sur signal de Bruno après les commits et avant le merge. Recette de C2 / C3a : checkout
isolé `~/r1w-determinism/repo` à HEAD détaché, alimenté par `git bundle b43515a..feat/c3b-reconstruction-1w` (sha256
`8541b0a74c061adb319470fcd97ad81a2984db3fa3261abedbcd7d6946ea0d36` des deux côtés — la branche n'était pas poussée),
`.venv` propre au répertoire (Python 3.12.3, pytest 9.0.2), `.env` copié de l'arbre du service, base en accès local,
`nice -n 5`, tmux ; une invocation `pytest` par combo, arrêt au premier échec (non servi). Preuves :
`determinism_server/` (pilote versionné `run24.sh`, `run24.log`, 24 × `comboN.xml` / `comboN.log`, `README.md`). Ils
lisent les paires USDC (`runner.PAIRS`) : les 24 rows dérivées (USDT) ne peuvent pas les affecter ; la porte vérifie le
seul changement de `src/`. Collector actif, `NRestarts=0`, arbre du service intact pendant le run.

**Base et checkout serveur.** La migration `c3bd1e7a0001` a été appliquée sur la base de production par le tunnel, le
2026-09-24 à 15:47Z ; aucune commande alembic n'a tourné sur le serveur avant le merge (consigne de Bruno). Après le
merge (`00ad09a`) et le push de `dev` : `git pull --ff-only` sur le serveur → `00ad09a`, puis `poetry run alembic
current` → **`c3bd1e7a0001 (head)`**, sans upgrade ; pas de restart, collector actif, `NRestarts=0`.

## 7. Retour arrière (non exécuté)

```sql
BEGIN;
DELETE FROM market_data_ohlc o USING ohlc_derived d
 WHERE o.timestamp = d.timestamp AND o.pair = d.pair AND o.interval = d.interval
   AND o.exchange = d.exchange AND d.method = 'agg_1d_v1';
DELETE FROM ohlc_derived WHERE method = 'agg_1d_v1';
COMMIT;
-- puis, si la table doit disparaître : alembic downgrade c1ae7a1c0001
```

## 8. Hors scope, noté sans être traité

- **`check` n'est pas conscient des rows dérivées** : relancé aujourd'hui, il signalerait les 8 estampilles comme « déjà
  présentes » (violation). C'est un outil d'avant écriture ; la vérification d'après écriture est la relecture de `write`.
- **Reprise 1 w 2026-07/08** : l'absence de reconstruction attendue est à vérifier au moment de la reprise ; `check` est
  borné à la fenêtre de la campagne et aux 8 cibles, la vérification portera sur les estampilles 1 w reprises (par
  exemple `data_inventory.py` sur les séries USDT).
- **`skills/binance_import.md:194`** donnait `10-10`, `11-14`, `12-12` au lieu de `10-03`, `11-07`, `12-05` (les
  estampilles présentes qui suivent les trous) : corrigé dans le commit docs final (accord de Bruno).
- **`PROJECT_CONTEXT.md`** et `ROADMAP.md` : mis à jour après le merge, dans un commit docs séparé sur `dev`.
- Une autre session `kraken-trading-bot` était ouverte, inactive, pendant tout le chantier ; branche assertée avant
  chaque commit.

## 9. Fichiers de ce dossier

| Fichier | Contenu |
|---|---|
| `check_report.json` · `check_report.md` | Étape 1, au `35b06ce` : (a)–(e), vwap, probe Vision, chunks |
| `write_report.json` · `write_report.md` | Étape 2, au `4866c7d` : contrôle rejoué, rows planifiées, relecture, provenance rejouée, retour arrière |
| `evidence/` | Tests rouges d'abord, mutants, passes de la suite, sortie d'`alembic upgrade`, sortie de `write`, contrôle indépendant |
| `determinism_server/` | Porte serveur : les 24 `_full` au `5cb8a24` — pilote `run24.sh`, `run24.log`, JUnit et journaux par combo, `README.md` |
| `report.md` | Ce rapport |
