# C3b lot 4a — producteur d'évaluation : rapport et preuves de conformité

**Fenêtre d'instrument, aucune portée économique.** Ce lot montre que le producteur d'évaluation fabrique un artefact
que la chaîne C3 admet, avec ses trois preuves du § B. Il ne dit rien de la famille grid. Aucune métrique n'est lue,
commentée ou reportée ici. Pour le chemin sélection, le seul fait rapporté est son code de sortie.

- **Brief** : `agent/AGENT_C3B_PRODUCTEUR.md` § « Lot 4a ».
- **Plan** : validé le 2026-09-28, avec le GO de Bruno et trois amendements (§ 2). Pour E10, Bruno a choisi l'option 2.
- **GO de lancement** du 2026-09-28. Il était donné sous deux conditions : la CI verte sur `85c8db7` et l'arbre
  expliqué.
- **Branche** `feat/c3b-producteur`, partie de `4d5eb46` (fin du lot 3).

| Commit | Sujet |
|---|---|
| `57b498e` | `refactor(audit): passed_params_problems extrait d'entry_controls (E10 partagé lots 3-4)` |
| `527e5ae` | `feat(audit): c3b_evaluate — run unique, flat_start_proof, first_fill_at (C3b lot 4a)` |
| `85c8db7` | `docs(research): entrée conformité évaluation` — entrée 16 et `ATTENDU.md` ; c'est le **SHA du run** |
| celui-ci | `docs(results): C3b lot 4a — conformité évaluation` |

## 1. Ce qui est livré

### `scripts/audit/c3b_evaluate.py` : le temps 3, partie 1

Pour le candidat retenu par `selection.json` (`--selection`), ou pour un candidat désigné mécaniquement (`--candidate`,
refusé au-delà du 2021-03-01), le script fait **un seul** `engine.run(pair, T, fin)`. Il produit les trois porteurs
d'une évaluation réelle (§ L.1 v2.1).

**`flat_start_proof = {"at": T, "cash": str(C), "qty": "0", "pending": 0}`**
- Elle est lue sur le moteur **après sa construction et avant `run`**.
- Les deux lectures probantes sont `usdc_balance` (`backtest.py:2250`) et `btc_held` (`:2251`).
- `pending` est vide **par construction** : sur le chemin grok, les ordres vivent dans la stratégie interne, créée dans
  `run` (`:2893-2895`). Le producteur exige quand même, en préconditions, des carnets vides (`:2268-2269`), une
  stratégie absente (`:2257`) et aucun trade (`:2291`).
- **Cette preuve vaut DÉCLARÉ**, jamais plus (§ B.2 l.889-891) : elle est produite par le programme dont elle décrit
  l'état.
- **Ce que le moteur stocke pour `C`.** La fabrique passe `float(C)` (`c3b_common.py:302`), et le moteur stocke
  `Decimal(str(float(C)))` : `Decimal("1000.0")` pour `C = 1000`.
  - L'égalité avec `C` se fait en `Decimal` **numérique**, après contrôle du type. Une comparaison de chaînes casserait
    dès `1000`.
  - Le cas `1000.50` passe (le moteur stocke `1000.5`). Un `C` à 20 chiffres significatifs est refusé (code 3). Les
    deux cas sont testés sur le vrai moteur.
  - `cash` exporte le `C` du manifeste.

**`invocation = {"single_call": true}`** — écrit par le seul chemin qui appelle `run` une fois (`run_once`).

**`first_fill_at`**
- C'est la plus petite estampille de `metrics.trades`, **strictement** après `T`. Sinon, code 3.
- Il vaut `null` sans trade : l'admission de la chaîne le refuse alors en R0 (§ 7).

**Contrôles internes (code 3, rien d'écrit)**
- `|net_pnl − (ending − starting)| ≤ 1e-6` (§ B.2 l.870), nécessaire mais pas suffisant.
- `equity_daily` sur la grille `[T, fin]`.
- Estampille de liquidation dans la cellule quotidienne finale (`c3_continuity.stamp_cell_block`), sauf si
  `trades == 0`.
- E10.

**Sorties**
- `evaluation_run.json`, intermédiaire : ses clés sont celles de la fixture `evaluation` moins celles du § F.2, et
  `metrics = {net_pnl}`.
- `evaluation_run_provenance.json`, à part.
- En succès, les événements du script ne portent ni identité, ni paire, ni métrique.

**Ordre des contrôles** : voir la docstring. Tout ce qui précède la base est pur. Un refus n'écrit rien. Une sélection
vide donne un code 2 avec l'événement `nothing_to_evaluate`.

### `scripts/audit/c3b_common.py`

- **Commit A, extraction pure.** `passed_params_problems` est sorti d'`entry_controls`, qui l'appelle, avec des
  messages identiques.
- **Commit B, ajout seul.** `designation_window_forbidden(end)` : `end > CAMPAIGN_START`, **sans** la porte
  `CAMPAIGN_UNLOCK`.

### Tests

- `tests/test_scripts/test_c3b_evaluate.py` : 55 tests, **aucun test base**. Un bouchon de moteur qui mute son état
  dans `run`, et le vrai `GridBacktester` à chargeurs bouchonnés.
- Cinq ajouts dans `test_c3b_common.py`.
- `test_c3b_prefix.py` est intouché.

## 2. Décisions et écarts, à reporter à la clôture du chantier

| # | Décision ou écart | Origine |
|---|---|---|
| D1 | **E10, option 2** : extraction de `passed_params_problems` dans le code du lot 3. La liste close est amendée pour cette seule extraction, qui s'écarte de « ajouts seulement, rien de retiré ». Preuves : sonde d'`entry_controls` identique au bit avant (`4d5eb46`, worktree) et après ; 118 tests du lot 3 intouchés et verts avant et après ; M01 rouge aux lots 3 **et** 4a | Bruno, plan |
| D2 | Garde de désignation : `--candidate` est refusé dès que la fenêtre dépasse le 2021-03-01, que `CAMPAIGN_UNLOCK` existe ou non. **Elle est reconduite au lot 4b** : refus sur la campagne, admission hors campagne | plan ; amendement 2 |
| D3 | Preuve à plat : les lectures probantes sont `cash` et `qty`, et `pending` est vide par construction (§ 1) | amendement 1 |
| D4 | **Note pour le manifeste de campagne** : le capital doit être représentable en `float`. Sinon, le moteur ne démarre pas avec `C` et la preuve est refusée (code 3). Ce n'est pas traité dans ce lot | amendement 3 |
| D5 | Flag `--selection` (et non le `--select` du brief), comme `c3_verdict.py:1498` | plan |
| D6 | `daily_grid` est importé de `krakenbot.backtest_metrics`, la fonction même que `c3_common` réexporte (`:50`) : mypy strict refuse une réexportation implicite. Ce n'est pas une copie | exécution |
| D7 | Chemin sélection : sorties et journaux **archivés seulement**, jamais versionnés ni lus. `status.txt` ne porte que les codes, l'événement et l'égalité des sha | plan, point 1 |
| D8 | Deux chemins **toujours** exécutés, sans branchement sur le code de la sélection. Le lot se clôt sur le chemin désigné | plan, point 1 |

## 3. Tests, rouge-avant, mutants, suites

### Rouge-avant (`tests/red_before_*.out`)

- **Garde de désignation**, lancée contre `57b498e`, où la fonction est absente : 5 échecs sur 5.
- **`test_c3b_evaluate.py`**, lancé contre un squelette AST de `c3b_evaluate.py` (générateur du lot 3, jamais
  committé) : **52 échecs, 3 verts**. Les 3 verts-avant sont attendus, car ils gardent des propriétés que le squelette
  conserve : pureté à l'import, discipline de source, tolérance épinglée au texte. Chacun a son mutant (M34, M35, M36).

### Mutants (`tests/mutants.py`, `tests/mutants.log`)

- **36 mutants, tous rouges, aucun survivant.** Chacun est appliqué, testé sur les trois fichiers des lots 3 et 4a,
  restauré, et son sha vérifié. La durée est d'environ 8,5 s par mutant, sans signal d'herméticité.
- **M01** (divergence E10 non vue, dans la fonction extraite) rougit dans les deux lots :
  - lot 3 : `test_c3b_common::test_a_router_entry_under_the_class_name_breaks_passed_params` et
    `test_c3b_prefix::test_a_passed_params_divergence_is_3` ;
  - lot 4a : `test_c3b_evaluate::test_a_passed_params_divergence_is_3`.

### Suites complètes locales

- **Commit A, avec deux défauts de ma part** (`tests/suite_commitA.out`, **3 184 passés**, 6 ignorés) :
  - **Lancée sans le `-k` des `_full`.** C'était pourtant une condition du GO pour tous les lots. Les 24 tests de
    déterminisme P6 (`test_determinism_parallel_vs_serial_full`, fenêtre 2023-04 → 2026-04, via le tunnel) ont donc
    tourné en local. Ils ont pris 3 h 27 et sont tous verts.
    - Ces tests ne comparent que la sortie parallèle et la sortie série ; aucune métrique n'est lue.
    - Ce ne sont pas des runs du producteur. Leur fenêtre recoupe pourtant celle de la campagne : c'est signalé à
      Bruno, qui en juge.
  - **`rc=` vide.** J'ai lu `PIPESTATUS` sous zsh, sans `pipefail`. Le code de pytest n'a donc pas été capturé ; le
    résumé ne porte aucun échec.
- **Commit B, correcte** (`tests/suite_commitB.out`, bash explicite) : **3 220 passés**, 6 ignorés, 24 désélectionnés,
  `rc=0`.
- **Clone propre de `85c8db7` sans `.env`** : 3 220 passés.
- **Conteneur Linux `python:3.12`**, avec la commande exacte de la CI : **3 207 passés, 43 ignorés** en arm64, en amd64
  émulé, et sur un clone superficiel.

### Ruff, mypy

- **ruff** : vert sur les fichiers de la CI et sur ce répertoire.
- **mypy strict**, un fichier par appel : vert sur `c3b_evaluate.py`, `c3b_common.py` et `_common.py`
  (`tests/mypy_audit.out`).
- **`mypy src/`** : 65, la base (`tests/mypy_src.out`).

### CI

Sur `85c8db7`, [run 36417095417](https://github.com/stordd13/kraken-trading-bot/actions/runs/36417095417) :

- **Tentative 1 rouge** : 1 échec sur 3 207. Le test en cause est
  `test_rejeu_effect.py::test_calibration_writes_no_extrapolation_of_the_fwe_quantile`, qui est instable :
  - il fait une assertion par sous-chaîne (`'1.645' not in` le texte d'un fichier qui porte des chronomètres) ;
  - la tentative 1 a rencontré `time_decimal_sec = 1.6453…`.

  Bruno l'a diagnostiqué ; il est sans rapport avec le lot.
- **Tentative 2 verte** : 3 207 passés, 43 ignorés, relancée par `gh run rerun --failed`.

### Diff de contrôle

- Il est vide depuis `4d5eb46` sur tout ce que le brief nomme : `src/`, `scripts/backtest.py`, les runners,
  `scripts/audit/c3_*.py`, `c3b_prefix.py`, `_common.py`, `_db.py`, `rejeu_*`, `tests/test_scripts/test_c3_*.py`,
  `test_c3b_prefix.py`, `config/`, `alembic/`, `.github/`, `pyproject.toml`, `poetry.lock`, `docs/protocole_c3.md`
  et `agent/`.
- `test_c3b_common.py` : 35 lignes ajoutées, 0 retirée.

## 4. Run serveur de conformité

### Mise en place

- **Pilote** : `server/run_c3b_evaluate.sh`, sha256 `7bdc1bd2…`. Ce sha est consigné dans `status.txt` par le pilote
  lui-même, et `cmp` est identique entre la copie versionnée, celle qui a tourné et celle de l'archive.
- **Clone isolé** `~/runs/c3b_eval4a/repo` :
  - clone GitHub, `git fetch origin feat/c3b-producteur`, `git checkout --detach 85c8db7` ;
  - `.env` copié du service ;
  - arbre suivi propre ;
  - les trois entrées ont le même sha qu'en local.
- **Environnement** : l'interpréteur du venv du service, le même que dans les gardes du lot 3 (`poetry.lock` et
  `pyproject.toml` identiques, `krakenbot` résolu vers le clone). Python 3.12.3, glibc 2.39.
- **Lancement** : `tmux new -d -s c3b-eval4a-20260928 "bash -lc …"`, qui écrit le code du pilote dans
  `pilot_exit.txt`.

### Déroulé, le 2026-09-28

| Étape | Heure (UTC) |
|---|---|
| Lancement | 12:34:12 |
| Chemin sélection, 2 exécutions | 12:34:21 et 12:34:28 |
| Chemin désigné, 2 exécutions (≈ 5,7 s chacune) | 12:34:35 et 12:34:42 |
| Fin | 12:34:44 |

Aucune coupure, aucun `kill`.

`server/status.txt`, tous les codes :

```
guard=0 … pilot_sha256=7bdc1bd2…  alembic_before=0  designation=0 identity=145867637b7f9bac…
eval_select_run1=0 event=evaluated  eval_select_run2=0 event=evaluated  select_sha_equal=0
eval_designated_run1=0  eval_designated_run2=0  designated_sha_equal=0 (a2042a02…)  alembic_after=0
admission=0  benchmark_eval_synth=0  c3_continuity=0  continuity_declared=0  interpreter_check=0  pilot_exit=0
```

### Attendu déclaré (`ATTENDU.md`, committé avant le run) et mesure

`server/verify_attendu.py` ne lit que les champs déclarés ; sa sortie est `server/verify_attendu.out`, **8 items tenus
sur 8**.

| # | Attendu | Mesuré |
|---|---|---|
| 1 | Désignation recalculée égale à `145867637b…` | **tenu** |
| 2 | Chemin sélection : deux codes égaux dans {0, 2} ; rien d'autre de lu | **tenu** : **code 0 aux deux exécutions** (événement `evaluated`), sha égaux. C'est le seul fait rapporté |
| 3 | Chemin désigné : code 0 ×2, artefact identique au bit, clés exactes, `synthetic: false`, observé et preuve déclarés, `single_call` vrai, `period = [T, fin]` | **tenu**. `evaluation_run.json` `a2042a02…` identique ; observé `{usdc_balance: "1000.0", btc_held: "0", 0/0, pas de stratégie, 0 trade}` ; preuve `{at: T, cash: "1000", qty: "0", pending: 0}` — **DÉCLARÉ** |
| 4 | `first_fill_at` non nul et `> T` ; `equity_daily` de 109 points sur `[T, fin]` ; contrôles internes verts | **tenu** : `first_fill_at = 2020-09-13T12:05Z` ; 109 points |
| 5 | Admission : réelle et admise | **tenu** : `evaluation_admission → False` sur le serveur, et recalculé en local |
| 6 | `c3_continuity` code 0 ; c1, c2, c5 `DECLARED` ; c3, c4 `VERIFIED` ; comparateur `VERIFIED` synthétique ; agrégat `DECLARED` | **tenu** |
| 7 | `alembic` inchangé | **tenu** : `c3bd1e7a0001 (head)` des deux côtés ; `transaction_read_only = on` |
| 8 | Lectures bornées à `≤ fin`, amorçage `≥ T − 400 j`, aucune donnée de campagne | **tenu** : amorçage `[2019-08-12, 2020-09-11T20:00Z]`, fenêtre `[T, fin]` |

**Fait constaté, non déclaré à l'attendu.** La sortie désignée ne liquide rien : `trades == 0` et estampille nulle,
car l'inventaire est nul à `fin`. Il en découle trois choses :
- `stamp_cell` vaut `NOT_VERIFIABLE`, ce qui est satisfait à vide (§ B.4) ;
- c3 vaut `VERIFIED` (identités exactes, `lots == []`), comme l'attendu le prévoyait pour ce cas ;
- l'exemption `trades == 0` du contrôle interne est donc exercée sur données réelles.

**Défaut de ma part, sur la non-lecture du chemin sélection.**
- En listant les tailles des fichiers de sortie sur le serveur avant l'archivage, j'ai vu que le
  `evaluation_run.json` du chemin sélection fait 5 222 octets, contre 4 886 pour l'artefact désigné. Cela révèle en
  partie que **le candidat retenu n'est pas le candidat désigné**. Ni l'identité du retenu ni aucune métrique ne sont
  lues.
- Ce fait n'est utilisé nulle part. Aucune liste de sha versionnée ne porte un fichier `select/`, précisément pour
  qu'aucune comparaison de sha ne soit possible depuis le dépôt.

**Aucune donnée de la fenêtre de campagne n'a été lue par le producteur.** Cette phrase repose sur trois appuis :
- **les bornes du code** : `run(pair, T, fin)`, avec `fin = 2020-12-28` et un amorçage lu avant `T` ; et la garde de
  désignation ;
- **les tests** : `run` appelé une fois sur `(T, fin)` exactement ;
- **les artefacts** : amorçage `≥ 2019-08-12`, fenêtre `[T, fin]`, tout avant le 2021-03-01.

Ce n'est pas un journal de requêtes Postgres. **Les 24 tests `_full` lancés en local au commit A** (§ 3) ne sont pas
des runs du producteur. Ils sont signalés à part.

### Archive et nettoyage

- **Archive** `~/archive/c3b_lot4a_20260928/c3b_lot4a_server_20260928.tgz`, sha256 `1e401ab2…`, 183 Ko. Elle contient
  22 fichiers : toute la sortie des deux chemins et le pilote, ni le `.env` ni le clone.
- **Listes de sha.** `files_all.sha256`, qui couvre les 22 fichiers, reste **sur le serveur seulement**.
  `files_versioned.sha256`, qui exclut le chemin sélection, est versionnée ici.
- **Vérifiée sur le serveur** : `sha256sum -c`, `tar -tzf` (22 fichiers), extraction avec `diff -r` vide, `cmp` du
  pilote et sha des fichiers extraits.
- **Rapatriement, hors `select/`** : 16 fichiers sur 16, mêmes sha qu'au serveur. `select/` est absent en local.
- **`rm -rf ~/runs/c3b_eval4a` le 2026-09-28 à 12:36:11Z**, après ces vérifications ; le `.env` copié est parti avec.
  Le service reste à `e9c8faf`, le collector actif.

## 5. Preuves de ce répertoire

| Fichier | Contenu |
|---|---|
| `ATTENDU.md` | attendu, committé avant le run (`85c8db7`) |
| `server/run_c3b_evaluate.sh`, `server/status.txt`, `server/pilot_exit.txt` | le pilote qui a tourné, ses codes |
| `server/designated/run1/evaluation_run.json`, `…/evaluation_run_provenance.json`, `server/designated/run2/evaluation_run_provenance.json` | sorties du chemin désigné. L'artefact de run2 est identique au bit à celui de run1, il n'est pas dupliqué |
| `server/chain/` | `admission.log`, `benchmark_eval_synth.json` (comparateur **synthétique**, sans valeur), `continuity.json`, `continuity.log` |
| `server/run.extract.log`, `server/designated_run{1,2}.extract.log`, `server/extract_logs.py` | extraits des journaux (pilote, orchestration, avertissements et erreurs), sha du brut en tête. Les bruts sont archivés |
| `server/alembic_before.txt`, `server/alembic_after.txt` | `alembic current` avant et après |
| `server/files_versioned.sha256`, `server/c3b_lot4a_server_20260928.tgz.sha256` | sha des fichiers versionnables et de l'archive |
| `server/verify_attendu.py`, `server/verify_attendu.out` | vérification de l'attendu, sur les champs déclarés seulement |
| archive seulement | les sorties et journaux du chemin sélection ; les journaux bruts |
| `tests/` | rouges-avant, `mutants.py` et `.log`, suites des commits A et B, mypy, et `refactor_e10/` (sonde d'identité, sorties avant et après, suites du lot 3 avant et après) |

## 6. Pour la suite

- **Lot 4b**
  - La garde de désignation vaut en 4b (amendement 2).
  - La violation d'identité que `c3_verdict` (`:625`) lève sur un artefact désigné est un **constat attendu**. La
    formulation finale se fera à l'ouverture du 4b, avec le code du chemin sélection, qui vaut **0**.
- **Candidat v2.2.** Une évaluation réelle sans trade n'a pas de `first_fill_at`. L'admission (§ L.1,
  `c3_common.py:1167`) la refuse alors en R0, alors que le § B.8 admet c5 `NON VÉRIFIABLE`. Un test épingle le
  comportement actuel. Le cas ne s'est pas présenté ici.
- **Conversation manifeste** : le capital doit être représentable en `float` (D4).
- **Liste de clôture, hors C3b** : corriger `test_rejeu_effect.py::test_calibration_writes_no_extrapolation_of_the_fwe_quantile`
  en assertant sur les champs parsés, pas sur le texte.
- **Rapport final du chantier, section défauts** :
  - la suite du commit A lancée sans le `-k` des `_full`, avec son `rc` non capturé ;
  - la lecture partielle par la taille des fichiers.
