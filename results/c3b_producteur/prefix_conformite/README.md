# C3b lot 3 — producteur préfixe : rapport et preuves de conformité

**Fenêtre d'instrument, aucune lecture économique.** Ce lot montre que le producteur fabrique des entrées que la
chaîne C3 accepte. Il ne dit rien de la famille grid. Aucun nombre de `c3_benchmark` ni de `c3_select` n'est lu,
commenté ou reporté ici. Les deux artefacts sont versionnés comme preuves de chaîne.

- **Brief** : `agent/AGENT_C3B_PRODUCTEUR.md` § « Lot 3 ».
- **Plan** : validé le 2026-09-27, avec les écarts E1-E12 et les décisions de Bruno au plan.
- **GO de lancement** du 2026-09-28, avec deux amendements au pilote.
- **Branche** `feat/c3b-producteur`, partie de `0a6c33e` (fin du lot 2).

| Commit | Sujet |
|---|---|
| `8f7d7a1` | `feat(audit): c3b_common — fabrique moteur et couche d'export (C3b lot 3)` |
| `feb5a82` | `feat(audit): c3b_prefix — observations, couverture, bougies (C3b lot 3)` |
| `6509737` | `docs(research): ligne RESEARCH_LOG conformité` — entrée 15, avec `manifest.json` et `ATTENDU.md` ; c'est le **SHA du run** |
| celui-ci | `docs(results): C3b lot 3 — conformité préfixe` |

## 1. Ce qui est livré

- **`scripts/audit/c3b_common.py`**
  - fabrique `GridBacktester` aux arguments de `run_p7_grid_search._engine`, épinglés par AST sur la source ;
  - coûts de liquidation tirés du manifeste et recoupés au fichier (§ A.6) ;
  - couche d'export :
    - entrée d'observation = dict `result` du runner à un seul segment, plus `decision_timeframes` et
      `exec_interval` ;
    - liquidation renommée `_base`, et lots reconstruits depuis les trades `forced_liquidation` ;
  - artefact de couverture (§ A.7) et export de bougies ;
  - garde-fou 6 ; validation des paramètres ; séries de décision ;
  - lectures en base, et écriture atomique par le writer strict.
- **`scripts/audit/c3b_prefix.py`** : le temps 1. Depuis le manifeste seul, il fait un run unique par candidat sur
  `[début, T]` et écrit `observations.json`, `coverage.json`, `candles.json`, plus `prefix_run.json` à part.
  - Codes : 0, 2 (refus d'entrée), 3 (contrôle interne ou job en échec).
  - Les contrôles se suivent dans un ordre gelé ; tous ceux qui précèdent la base sont purs, et un refus n'écrit
    rien (docstring du module).
- **Tests** : `tests/test_scripts/test_c3b_common.py` et `tests/test_scripts/test_c3b_prefix.py`, 118 tests, **aucun
  test base**.
- **Preuves** : ce répertoire. `tests/` contient les rouges-avant, les mutants, la suite et mypy ; `server/` contient
  le run de conformité.

Le producteur n'importe que des primitives de la chaîne (décision 3) et n'en recopie aucune règle. `covered_units`
et les jours couverts sont lus par **oracle** : on appelle `cc.coverage_recompute`, comme le fait la fixture
`degrade_coverage`.

## 2. Décisions et écarts, à reporter à la clôture du chantier

| # | Décision ou écart | Origine |
|---|---|---|
| E1 | Coûts moteur tirés du manifeste et recoupés à `config/pair_costs_b4.json` par `universe.deployment_pairs`. Le fichier ne porte que des paires `*/USDC` ; sans ce recoupement, ETH et SOL prendraient le spread par défaut du modèle, et les identités de liquidation échoueraient | plan |
| E2, E3 | `covered_units` et `first_day` / `last_day` = jours **couverts** (§ A.7 l.416), lus par oracle. Une série sans unité couverte est refusée (code 2) : **candidat v2.2**, dates nullables. Le cas ne s'est pas présenté | plan |
| E6 | Garde-fou : règle du brief, `end > 2021-03-01` refusé ; plus stricte que « touchant 2021-03-01 → 2026-06-29 » | plan, confirmé par Bruno |
| E9 | `NonFiniteValueError` levée par `cc.load_manifest` (canonisation de l'identité) → refus 2, le chemin de la clé nommé | relecture du plan |
| E10 | Contrôle interne `effective_params.passed_params == params + pair` (code 3) | relecture du plan |
| E11 | Un gestionnaire en lecture seule par job, fermé en `finally` (le brief disait : par worker) | plan |
| — | `grid_levels` exige le type exact `int` : `"12"` est refusé, alors que la classmethod le coerce. **C'est voulu** : un manifeste est un JSON typé, pas un YAML. Ce n'est pas un défaut | décision de Bruno, 27/09 |
| — | Provenance `unknown` : aucun `validé` n'est atteignable sur une fenêtre d'instrument. Univers de 4 paramétrages × 3 paires ; STOP avant le lancement | décisions de Bruno, 27/09 |
| — | Transport par **push de la branche** (le commit 3 poussé avant le run) ; un seul venv serveur ; seuil de 5 Mo **mesuré** | GO, 27/09 |
| — | Pilote : `env PYTHONPATH="$REPO/src"` sur les six invocations Python et le contrôle final ; `pilot_sha256` consigné après `guard=0` | GO de lancement, 28/09 |
| X1 | **Écart d'exécution** : couverture, dérivées et bougies sont lues et mises en forme **avant** les jobs, alors que le plan les plaçait après. Un artefact impossible à former refuse avant tout run | exécution |
| X2 | La fabrique de pool est résolue à l'appel, et non figée en valeur par défaut, pour que les tests l'interceptent | exécution |
| X3 | Le scan de discipline de source est réparti par fichier de tests, pour que chaque commit soit cohérent seul. Le commit 1 relancé seul depuis un export de son arbre donne 83 verts | exécution |

## 3. Tests, rouge-avant, mutants

- **Rouge-avant** (`tests/red_before.out`). Les tests ont été lancés contre des squelettes : mêmes signatures, et
  chaque corps lève `NotImplementedError`. Les squelettes ont été générés par AST (`tests/make_skeleton.py`) et
  jamais committés. Résultat : **107 échecs, 6 erreurs, 5 verts**. Les 5 verts :
  - les constantes du brief (mutant M22) ;
  - le scan de source des deux modules (M42) ;
  - la pureté à l'import (M43) ;
  - le `T` de la fenêtre de conformité. C'est une propriété de `c3_common` que le test documente pour l'attendu ;
    aucun mutant du producteur ne la concerne.
- **Mutants** (`tests/mutants.py`, `tests/mutants.log`) : 44 mutants, chacun appliqué, testé, restauré, puis son sha
  vérifié. **43 rougissent, aucun ne survit.**
  - M44 est **équivalent** : l'ordre d'insertion à l'assemblage ne peut pas changer le texte, car le writer trie les
    clés. L'indépendance à l'ordre d'exécution est portée par le test du pool inversé.
  - Deux passages identiques. Durée maximale : 9,3 s, aucun signal d'herméticité.
- **Herméticité construite** : une fixture autouse remplace `ReadOnlyDatabaseManager` par un bouchon qui n'ouvre
  jamais de session, coupe `.env`, fait lever les lectures en base et les chargeurs du moteur, et interdit tout vrai
  pool `spawn`.
  - Le vrai moteur tourne sur des bougies synthétiques par ses chargeurs remplacés.
  - Le chemin nominal passe `c3_anchor`, `c3_entry` (code 0, aucune clause non assertable), `c3_benchmark` et
    `c3_select` **en processus**.
- **Suite complète locale** (`tests/suite.out`) : **3 160 passés** (3 042 + 118), 6 ignorés, 24 `_full`
  désélectionnés, code 0.
- **ruff** : vert sur les fichiers de la CI (globs `c3*.py`) et sur ce répertoire.
- **mypy**
  - Strict, un fichier par appel : vert sur `c3b_common.py`, `c3b_prefix.py` et `_common.py`.
  - `mypy src/` = **65**, la base (`tests/mypy_src.out`). **Défaut de ma part, vu et corrigé** : j'avais d'abord
    mesuré 64 avec `--ignore-missing-imports`, qui masque `feature_store.py:32` (stubs pandas absents), et je l'avais
    lu comme un écart. Le diff des deux sorties l'a résolu.
- **CI** verte sur `6509737` ([run 36338454694](https://github.com/stordd13/kraken-trading-bot/actions/runs/36338454694)),
  lue par l'API publique. Toutes les étapes sont en succès, dont les deux étapes ruff « audit C3 ».
- **Diff de contrôle** vide sur tout ce que le brief nomme : `src/`, `scripts/backtest.py`, les runners,
  `scripts/audit/c3_*.py`, `rejeu_*`, `_common.py`, `_db.py`, `tests/test_scripts/test_c3_*.py`, `config/`,
  `alembic/`, `pyproject.toml`, `poetry.lock`, `docs/protocole_c3.md`, `.github/`.
- **Pool `spawn`**, jamais exercé en test : un aller-retour local sans base a été vérifié avant le push (module
  importé dans un processus neuf ; `RunContext` réel et `Candidate` intacts après pickling). Le run serveur l'a
  ensuite exercé pour de vrai (run1 à 4 workers).

## 4. Run serveur de conformité

- **Pilote** : `server/run_c3b_prefix.sh`, sha256 `ee1f5a53…`. Ce sha est consigné dans `status.txt` par le pilote
  lui-même, et `cmp` est identique entre la copie versionnée et celle qui a tourné.
- **Clone isolé** `~/runs/c3b_prefix/repo` : clone GitHub, `git fetch origin feat/c3b-producteur`, `git checkout
  --detach 6509737`, `.env` copié du service.
- **Environnement** : l'interpréteur du venv du service.
  - `poetry.lock` et `pyproject.toml` sont identiques à ceux du service.
  - `krakenbot` est résolu vers le `src/` du clone, par la garde puis par le contrôle final, sur la valeur consignée
    dans `prefix_run.json`.
  - Python 3.12.3, numpy 2.4.1, x86_64, glibc 2.39.
- **Déroulé**, le 2026-09-28 :

  | Étape | Heure (UTC) | Durée |
  |---|---|---|
  | Lancement | 06:46:17 | |
  | Fin de run1 (4 workers) | 06:47:00 | 43 s ; jobs de 2,5 à 15,1 s |
  | Fin de run2 (1 worker) | 06:49:10 | 2 min 10 s |
  | Fin de la chaîne | 06:49:15 | |

  Aucune coupure, aucun délai limite atteint.

`server/status.txt` (tous les codes) :

```
guard=0 … pilot_sha256=ee1f5a53…  alembic_before=0  producer_run1=0  producer_run2=0  alembic_after=0
sha_equal=0  c3_anchor=0  c3_entry=0  c3_benchmark=0  c3_select=0  interpreter_check=0
```

### Attendu déclaré (`ATTENDU.md`, committé avant le run) et mesure

`server/verify_attendu.py` ne lit que les champs déclarés ; sa sortie est `server/verify_attendu.out`.

| # | Attendu | Mesuré |
|---|---|---|
| 1 | Producteur en code 0 aux deux exécutions ; trois sorties identiques au bit (4 workers puis 1) ; 12 entrées ; `T = 2020-09-11T21:36Z` ; 0 estampille dérivée | **tenu** : 0 et 0 ; `observations.json` `57e48213…`, `coverage.json` `5871f74e…`, `candles.json` `20c0d1fb…` identiques ; 12 entrées (4 par paire) ; `T` exact ; 0 dérivée ; `transaction_read_only = on` |
| 2 | `c3_anchor` code 0, même `T` | **tenu** : variante `e324967c…` (`c3b-lot3-conformite-prefixe-2020`), registre neuf |
| 3 | `c3_entry` code 0, I-A.1 à I-A.8 `ok`, **aucune clause non assertable** ; D2 en échec sur les 4 candidats SOL, séries C1 `[1d, 1w, 4h]`, C2 `[1w, 4h]`, C5 `[1d, 4h]`, C6 `[4h]` ; BTC et ETH amorcés | **tenu** : I-A.1 à I-A.8 et I-A.fin `ok`, `not_assertable = []`, couverture `evaluated`, provenance `unknown` ; `D_WARMUP_PREFIX` sur exactement ces quatre candidats, avec exactement ces séries |
| 4 | `c3_benchmark` code 0 ; SOL `E_NO_BENCHMARK` (aucune bougie 5 min au `2020-01-06T00:05Z`) | **tenu** : SOL `buildable: false`, « estampille(s) d'exécution requise(s) absente(s) ['2020-01-06T00:05:00+00:00'] » |
| 5 | `c3_select` code 0, sélection descriptive (provenance `unknown`) ; SOL sort par D1, paire `DESCRIPTIF` | **tenu**, avec une réserve de rédaction (ci-dessous) : provenance `unknown`, **aucune `SÉLECTION_VALIDE`** ; SOL `DESCRIPTIF`, D1 en échec (5 min : 31 unités couvertes sur 249), les 4 candidats SOL ont D1 pour première porte (`NON_ADMISSIBLE`, `D_NOT_ADMISSIBLE`) |
| 6 | `alembic current` identique avant et après | **tenu** : `c3bd1e7a0001 (head)` des deux côtés |
| 7 | Toutes les lectures bornées à `≤ T` ; aucune donnée de la fenêtre de campagne lue | **tenu** : fenêtre de couverture `[2020-01-06, T]` ; bougies `max t ≤ T` et `min t ≥ début` sur les trois paires ; run `(début, T)` exact (test d'appel unique) ; amorçage antérieur au début |

**Réserve sur l'item 5, défaut de mon attendu, vu après coup.** « Sélection descriptive » présume qu'un candidat est
retenu, alors que l'issue de BTC et d'ETH devait n'être ni déclarée ni lue. Lire `selection.status` aurait lu cette
issue. J'ai donc vérifié la seule propriété que l'attendu visait, `status != "SÉLECTION_VALIDE"` (liste close :
valide, descriptive, abstention), qui ne distingue pas une sélection descriptive d'une abstention. L'issue BTC/ETH
reste non lue.

**Aucune donnée de la fenêtre de campagne n'a été lue par le producteur.** Cette phrase repose sur trois appuis :

- **les bornes du code** : couverture sur `(début, T]`, bougies sur `[début, T]`, run `(pair, début, T)`, et
  amorçage à `début − 400 j` au plus tôt ;
- **les tests** : les lectures bouchonnées enregistrent `end == T` ;
- **les artefacts** : `max t ≤ T = 2020-09-11T21:36Z`.

Ce n'est pas un journal de requêtes Postgres.

### Archive et nettoyage

- Archive `~/archive/c3b_lot3_20260928/c3b_lot3_server_20260928.tgz`, sha256 `80b5f2b9…`, 4,6 Mo. Elle contient les
  sorties de run1 et run2 (partiels compris), la chaîne, les journaux, `status.txt` et le pilote ; ni le `.env`, ni le
  clone.
- 50 fichiers, sha256 listés dans `server/files.sha256`.
- Vérifiée sur le serveur : `sha256sum -c`, `tar -tzf`, extraction et `diff -r` contre les sources, sha des fichiers.
  Rapatriée : mêmes sha en local (50/50).
- **`rm -rf ~/runs/c3b_prefix` le 2026-09-28 à 06:51:56Z**, après ces vérifications ; le `.env` copié est parti avec.

## 5. Preuves de ce répertoire

Règle : un fichier de moins de 5 Mo est versionné ; au-delà, il est archivé avec son sha.

| Fichier | Contenu |
|---|---|
| `manifest.json`, `ATTENDU.md` | manifeste de conformité (sha `d96ed10d…`) et attendu, committés avant le run |
| `server/run_c3b_prefix.sh`, `server/status.txt` | le pilote qui a tourné, ses codes |
| `server/run1/observations.json` (162 Ko), `server/run1/coverage.json` (2,5 Mo), `server/run1/prefix_run.json`, `server/run2/prefix_run.json` | sorties versionnées. Les fichiers de run2 ont le même sha que ceux de run1 et ne sont pas dupliqués |
| `server/chain/` | `anchor`, `entry`, `benchmark`, `selection` (`.json` / `.md`), `variants.json`, journaux de chaque étape |
| `server/*.extract.log`, `server/extract_logs.py` | extraits des journaux : événements d'orchestration, avertissements, erreurs. Les bruts sont archivés : `run1.log` `ed75192f…`, `run2.log` `657f9479…`, `run.log` `29a3c10e…` |
| `server/alembic_before.txt`, `server/alembic_after.txt` | `alembic current` avant et après |
| `server/files.sha256`, `server/c3b_lot3_server_20260928.tgz.sha256` | sha des 50 fichiers et de l'archive |
| `server/verify_attendu.py`, `server/verify_attendu.out` | la vérification de l'attendu, champs déclarés seulement |
| archivés seulement | `run1/candles.json` et `run2/candles.json` (15,2 Mo, sha `20c0d1fb…`) ; les journaux bruts ; les partiels |
| `tests/` | `red_before.out`, `make_skeleton.py`, `mutants.py`, `mutants.log`, `suite.out`, `mypy_src.out` |

## 6. Pour la suite

- **Candidat v2.2** : le § A.7 « premier et dernier jours couverts » n'est pas défini quand `covered_units == 0`
  (écart E3).
- **Lot 4a** :
  - la sortie de `c3_select` s'appelle `selection.json` (le brief dit `select.json`) ;
  - `stamp_cell` est `c3_continuity.stamp_cell_block` ;
  - le transport par push et l'environnement unique du lot 3 se reprennent tels quels.
- **Conversation manifeste**, hors C3b : `min_order_usdc 5.0` est la valeur du rejeu, inerte sur le grid ; le
  manifeste de campagne devra porter le vrai minimum Bybit.
- **Rappel du lot 2**, non traité : les quatre chemins en code 1 hors § I.1 de la chaîne.
