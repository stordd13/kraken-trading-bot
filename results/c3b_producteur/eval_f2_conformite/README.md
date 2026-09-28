# C3b lot 4b — comparateur d'évaluation et procédure § F.2 : rapport et preuves de conformité

**Fenêtre d'instrument, aucune portée économique.** Ce lot montre deux choses sur la sortie du producteur d'évaluation
complet :
- elle traverse la chaîne C3 **complète**, soit six étapes, avec `chain.verified` vrai ;
- la chaîne rejoue le tirage du § F.2 **au bit près** : aucune violation au rejeu.

Il ne dit rien de la famille grid. **L'issue publiée par `c3_verdict` n'a pas été lue** (décision de Bruno du 28/09).
Aucune métrique, aucun λ, aucune identité ni paire du retenu n'est lu, commenté ou reporté ici.

- **Brief** : `agent/AGENT_C3B_PRODUCTEUR.md` § « Lot 4b », amendé par les décisions de clôture du 4a :
  1. conformité sur le chemin sélection seul ;
  2. issue non lue ;
  3. attendu déclaré sans l'issue.
- **Plan** : validé le 2026-09-28 (`~/.claude/plans/pasted-content-id-864e-c3b-wondrous-clarke.md`).
  - Réponses de Bruno au plan : `evaluation.json` **remplace** `evaluation_run.json`, les assertions 4a de fond restent
    intouchées et le diff du fichier de tests est nommé ; la liste close de ce qui remonte reçoit **deux booléens**.
  - GO : A1 à A4 (§ 2).
- **GO de lancement** du 2026-09-28, au `459190a`. Consignes :
  - l'`OverflowError` va à la liste des sorties code 1 de la chaîne ;
  - deux limites vont au rapport (§ 6) ;
  - en cas de code non nul : `status.txt` seul, puis STOP.
- **Branche** `feat/c3b-producteur`, partie de `a0d452d` (fin du lot 4a).

| Commit | Sujet |
|---|---|
| `3740c40` | `feat(audit): c3b_evaluate — comparateur § C.5, procédure § F.2 rejouable (C3b lot 4b)` |
| `459190a` | `docs(research): entrée conformité § F.2` — entrée 17 et `ATTENDU.md` ; c'est le **SHA du run** |
| celui-ci | `docs(results): C3b lot 4b — conformité § F.2` |

## 1. Ce qui est livré

### `scripts/audit/c3b_evaluate.py`, partie 2 : primitives de la chaîne seules (décision 3)

**Comparateur d'évaluation (§ C.3-C.5)**
- Les closes `[T, fin]` de **la seule paire évaluée** (exécution et quotidienne) sont lues par `c3bc.fetch_closes`.
  Elles forment `candles_eval.json` (`c3bc.candles_artefact`, qui refuse toute estampille `> fin`).
- Ce payload est **relu par `cb.load_candles`**, puis passé à `cb.build_pair(pair, …, start=T, end=fin)`. La convention
  est celle de la fonction, citée sans être réécrite :
  - entrée à la clôture de la première bougie d'exécution strictement après `T` ;
  - sortie à la dernière `≤ fin` ;
  - taker + spread + slippage sur les deux jambes.
- **Non constructible** : refus 2 `comparator_not_buildable`, **avant le moteur** (E5).
- `benchmark_eval.json` porte exactement `{pair, window, comparable, comparability}` :
  - les cinq tests de `cc.COMPARABILITY_TESTS` ;
  - `comparable` **recalculé** comme leur conjonction, et recoupé à `build_pair` (code 3 sinon).

**λ du préfixe, tenus fixes (§ F.2 f)**
- Nouveau flag `--benchmark`. Le producteur n'y lit que `pair`, `estimable` et les deux λ de l'identité évaluée.
  - Il vérifie les empreintes du manifeste et de l'ancrage.
  - Sur le chemin sélection, `selection.inputs_sha256.benchmark` doit être l'empreinte du fichier fourni.
- `NOT_ESTIMABLE` donne 2. Une paire du bloc discordante ou un λ hors `[0, 1]` donne 3.
- La conversion est `Decimal(str(λ))`, celle de `c3_benchmark.py:500`.

**Séries appariées (§ F.2 a)**
- `returns_config = cc.recompute_daily(equity_daily.values, n_jours).returns`.
- `returns_bench[m] = cc.recompute_daily(cb.blend_nav(nav_bh, λ_m, C), n_jours).returns`.
- `n_jours = (fin − T) / 86 400`, jamais `duration_days` ni `evaluation_days` (E8).
- **Avant tout tirage** :
  - longueurs inégales : 3 `series_length` ;
  - rendement non fini ou `≤ −1`, ou CAGR observé non fini : 3 `f2_invalid_input`.

**Procédure § F.2**
- `cc.replay_bootstrap` avec la graine de `anchor.uncertainty.seed` (recoupée au manifeste, code 3 sinon), l'index de
  la paire dans les paires **triées** de l'ancrage, et `n_jours`.
- Ce sont les trois paramètres que `c3_verdict._replay` relit (`c3_verdict.py:259-277`).

**Sorties**
- `evaluation.json` : **exactement** les clés de la fixture `evaluation` de `test_c3_common.py`. C'est le payload du 4a
  plus les clés § F.2 ; `metrics = {net_pnl, cagr_pct, delta_dd}`.
- `benchmark_eval.json`, `candles_eval.json`.
- `evaluation_sensitivity.json` : λ ré-estimé sur `[T, fin]` par `cb.match_lambda` ; mode `reestimated`, `DESCRIPTIF`,
  hors chaîne.
- `evaluation_run_provenance.json` (schéma `c3b_evaluate_run/2`, avec `benchmark` et `replay`).
- Le journal reste sans identité, paire, métrique ni λ : `evaluated`, puis `written` ×5.

**Ordre des contrôles** : voir la docstring (étapes 1 à 11, dont 6b, 6c et 10b). Tout ce qui précède la base est pur, et
un refus n'écrit rien.

### `c3b_common.py`, `test_c3b_common.py`

Intouchés (E13).

## 2. Décisions et écarts, à reporter à la clôture du chantier

| # | Décision ou écart | Origine |
|---|---|---|
| E1 | `evaluation.json` remplace `evaluation_run.json` ; la provenance garde son nom | Bruno, plan |
| E2 | `--benchmark` obligatoire ; empreintes recoupées, et celle de la sélection sur le chemin sélection | plan |
| E3 | `candles_eval.json` porte la seule paire évaluée | plan |
| E4 | Comparateur construit depuis l'artefact relu par `cb.load_candles` (manifeste restreint au candidat) | plan |
| E5 | Comparateur non constructible : 2 avant le moteur. **Candidat v2.2** : `E_NO_BENCHMARK` est inatteignable par la chaîne dans ce cas, qui exige `returns_bench` | plan ; A1 |
| E6 | Constructible mais non comparable : tout est écrit, la chaîne rend `E_NO_BENCHMARK` | plan |
| E7 | Bougies et comparateur passent avant le moteur (comme X1 au lot 3) | plan |
| E8 | `n_jours` vient des bornes. Le mutant `duration_days` est équivalent sur le vrai moteur (`backtest.py:2869`, même expression) : son rouge s'obtient avec un bouchon qui déclare une autre durée. Le mutant `evaluation_days` rougit au dernier bit (`14 − fl(9,8) = 4,199999999999999 ≠ fl(4,2)`, mesuré) | plan |
| E9 | Graine lue dans l'ancrage, recoupée au manifeste | plan |
| E10 | λ en `Decimal(str(λ))` ; estimabilité ; domaine `[0, 1]` | plan |
| E11 | **Candidat v2.2** : la chaîne ne recoupe ni λ ni `returns_bench`, puisque `evaluation.json` ne porte ni λ ni bougies. « λ du préfixe tenu fixe » n'est garanti que par construction côté producteur, comme S-3 | plan ; A1 |
| E12 | Diff de la partie 4a du fichier de tests limité à T1-T10 (`tests/test_diff_4a.txt`, 41 lignes, toutes rattachées). Seule T9 change le contenu d'une assertion : la forme, parce que le 4b ajoute ces clés | plan ; consigne de Bruno |
| E13 | Aucun changement à `c3b_common.py` ni à `test_c3b_common.py` | plan |
| A2 | `--campaign C3B_LOT4B` : **étiquette d'instrument**. La dette 21 (`--campaign`) reste intacte | GO |
| X1 | **Écart d'exécution** : `cc.recompute_daily` lève `OverflowError` sur un CAGR observé non fini, parce que `cc.cagr_pct` passe par `math.exp`, là où la somme de numpy du § F.2 rend `inf`. Le producteur la route en 3 `f2_invalid_input` (§ F.2 e), avec un test et son mutant (M33). Voir § 6 | exécution |
| X2 | **Au-delà du plan** : un test (paire du bloc `benchmark.json`, 3 `benchmark_inconsistent`), un refus du mode de λ non décisionnel (§ C.4), et les mutants M32 à M35 | exécution |

## 3. Tests, rouge-avant, mutants, suites

### Tests

`tests/test_scripts/test_c3b_evaluate.py` compte **99 tests** : 55 du 4a et 44 nouveaux. **Aucun test base** :
herméticité du 4a, bougies servies par `tp.install_database`, et `benchmark.json` **simulé conforme** (`write_benchmark`,
les quinze clés de `candidate_block`).

Attendus :
- **§ F.2** : égalité au bit avec `fx.f2_procedure`, la procédure écrite depuis le texte dans `test_c3_common.py` (suites,
  écartées, bornes, `cagr_pct`, `delta_dd`, et texte JSON du writer strict). Deux séries de configuration × trois
  comparateurs × deux index de paire.
- **Comparateur** : NAV dérivée à la main depuis la convention (§ C.3).
- **Rejeu** en processus par `c3_verdict._evaluation_contract`, `_read_replications`, `_read_series`, `_replay` et
  `_cross_check_replay` : **zéro violation**.
- **Chaîne complète** `c3_verdict.py chain` en processus : code 0, `chain.verified` vrai (limite au § 6).

### Rouge-avant

- **Contre `a0d452d`** : `tests/red_before_a0d452d.out`, 91 échecs et 8 verts. Les 8 verts sont des tests 4a qui
  n'atteignent pas le producteur complet.
- **Contre un squelette 4b** : les huit fonctions nouvelles lèvent `NotImplementedError` (`tests/make_skeleton_4b.py`,
  jamais committé comme code), `tests/red_before_skeleton.out`. Résultat : 74 échecs et 25 verts, tous des tests 4a qui
  refusent avant l'étape 6b ou qui sont purs.
- **Les 44 tests 4b sont rouges-avant dans les deux cas.**

### Mutants 4b

`tests/mutants.py` ; harnais du 4a, étendu aux mutants à plusieurs sites.

- **Premier passage** (`tests/mutants_pass1.log`) : 31 rouges et **4 survivants**, tous du côté des tests :
  - **M01** (index de paire dans l'ordre du manifeste) — **défaut de mon test**. Le monde de test n'avait que 5
    rendements pour des blocs de 10 à 42 : chaque réplication est une rotation de la série entière, le tirage ne se
    voit pas. Le rejeu tourne désormais sur un monde long de 47 rendements (`long_world`).
  - **M11** (λ du premier bloc) — **défaut de mon test** : le candidat évalué était le premier bloc de `benchmark.json`.
    C'est maintenant la seconde identité BTC.
  - **M10** (`Decimal(λ)`) — données non discriminantes. La conversion ne se voit au bit que pour 11 valeurs de λ sur
    999 (pas de 0,001), mesuré. Les λ du test passent de 0,123 / 0,456 à 0,168 / 0,336.
  - **M12** (CAGR par `math.fsum`) — données non discriminantes. Sur le témoin, `fsum` et la somme de numpy coïncident ;
    une série `varying_returns(9)`, où elles diffèrent, est ajoutée.
- **Second passage** (`tests/mutants.log`) : **35 mutants, 35 rouges, aucun survivant**, fichier restauré et sha vérifié
  à chaque fois, environ 19 s par mutant.
- **Rejeu des 36 mutants du 4a au tip 4b** (`tests/mutants_4a_replay.log`, amendement A3) : **tous appliqués, tous
  rouges**. Les aides modifiées n'ont désarmé aucun test du 4a.

### Suites, lint, types, CI

- **Suite complète locale** (`tests/suite.out`, script bash, `pipefail`, sans les 24 `_full`) : **3 264 passés**, soit
  3 220 + 44, 6 ignorés, 24 désélectionnés, `rc=0`.
- **ruff** : vert sur les globs de la CI, sur `src/` et sur ce répertoire.
- **mypy strict**, un fichier par appel : vert sur `c3b_evaluate.py`, `c3b_common.py` et `_common.py`
  (`tests/mypy_audit.out`). `mypy src/` = **65**, la base (`tests/mypy_src.out`).
- **CI** : verte **dès la tentative 1** sur `459190a`, avec 3 251 passés
  ([run 36436609751](https://github.com/stordd13/kraken-trading-bot/actions/runs/36436609751)).
- **Diff de contrôle** (`tests/controle_diff.txt`) :
  - depuis `a0d452d`, seuls `c3b_evaluate.py`, `test_c3b_evaluate.py`, `docs/RESEARCH_LOG.md` et ce répertoire bougent ;
  - depuis `ec7ffb8`, `test_c3_common.py` et `test_c3_verdict.py` ne bougent que par `6953fbc` (lot 2), et leur diff
    est vide depuis `a0d452d` ;
  - `src/`, `config/`, `scripts/backtest.py`, `c3_*.py` et `.github/` ont un diff vide sur ce lot.

## 4. Run serveur de conformité

### Mise en place

- **Clone isolé** `~/runs/c3b_eval4b/repo` : clone GitHub, `git checkout --detach 459190a`, `.env` copié du service.
  L'arbre suivi est propre, et les entrées du lot 3 ont le même sha qu'en local.
- **Pilote** : `server/run_c3b_eval4b.sh`, sha256 `9b401797…9cc8`.
  - Ce sha est consigné par le pilote lui-même.
  - `cmp` est identique entre la copie versionnée, celle qui a tourné et celle de l'archive.
- **Environnement** : l'interpréteur du venv du service, avec `env PYTHONPATH="$REPO/src"` sur chaque invocation
  Python. `krakenbot` résolu vers le clone, par la garde puis par `interpreter_check`. Python 3.12.3.
- **Entrée archivée** : `candles.json` du lot 3 est extrait de `~/archive/c3b_lot3_20260928/` (archive `80b5f2b9…`,
  fichier `20c0d1fb…`). Le registre des variantes du lot 3 est copié (`7c5b8065…`).
- **Défaut du pilote, vu avant le lancement.** Une vérification en lecture seule sur le serveur, faite au STOP 1, a
  montré que le fichier s'appelle `out/run1/candles.json` dans l'archive, et non `./run1/candles.json`. La garde aurait
  refusé. Correction : `--strip-components=1`, qui garde le chemin écrit dans l'attendu.
- **Lancement** : `tmux new -d -s c3b-eval4b-20260928 "bash -lc …"`. Le code du pilote va dans `pilot_exit.txt`.

### Déroulé, le 2026-09-28

| Étape | Heure (UTC) |
|---|---|
| Lancement | 14:48:51 |
| Producteur, run1 | fin 14:49:00 |
| Producteur, run2 | fin 14:49:09 |
| Chaîne complète, fin du pilote | 14:49:13 |

Aucune coupure, aucun `kill`. Code du pilote : **0**.

`server/status.txt`, tous les codes :

```
guard=0 sha=459190a2… lot3_candles=0 registry=0   pilot_sha256=9b401797…   alembic_before=0
eval_run1=0 event=evaluated   eval_run2=0 event=evaluated   eval_bit_equal=0   outputs_bit_equal=0
alembic_after=0   chain_exit=0   chain_verified=true   verdict_violations=0   replay_violations=0
chain_steps=anchor:0,entry:0,benchmark:0,select:0,continuity:0   extract=0   interpreter_check=0
```

### Attendu déclaré (`ATTENDU.md`, committé avant le run) et mesure

`server/verify_attendu.py` ne lit que `status.txt`, les deux `alembic current` et `pilot_exit.txt`. Sa sortie est
`server/verify_attendu.out` : **5 items vérifiables sur 5 tenus**, `rc=0`.

| # | Attendu | Mesuré |
|---|---|---|
| 1 | Gardes : SHA, arbre, environnement, entrées du lot 3, registre | **tenu** |
| 2 | Producteur : 0/0 `evaluated` ; `evaluation.json` au bit ; trois autres artefacts au bit ; interpréteur du clone | **tenu** |
| 3 | Chaîne complète : six étapes en 0 ; `chain.verified` vrai ; 0 violation ; 0 violation au rejeu | **tenu** |
| 4 | `alembic` identique avant et après | **tenu** : `c3bd1e7a0001 (head)` des deux côtés |
| 5 | Lectures bornées à `≤ fin`, aucune donnée de campagne | appuis déclarés ci-dessous, sans lecture d'artefact |

**Aucune donnée de la fenêtre de campagne n'a été lue par le producteur.** La phrase repose sur trois appuis :
- **le code** :
  - bougies lues sur `[T, fin]` pour la seule paire évaluée (`read_evaluation_closes`) ;
  - `candles_artefact` refuse toute estampille `> fin` ;
  - un seul `run(pair, T, fin)`, avec `fin = 2020-12-28` et un amorçage `≥ T − 400 j` ;
- **les tests** : les lectures relevées valent exactement `(pair, 5, T, fin)` et `(pair, 1440, T, fin)` ;
  `run(pair, T, fin)` est appelé une fois ;
- **les codes de la chaîne** :
  - `continuity = 0` impose `period = [T, fin]` (`c3_continuity.py:384-388`) ;
  - `verdict = 0` avec un retenu impose que c2 n'est pas en échec, donc une grille quotidienne `[T, fin]`.

La fenêtre du comparateur **n'est pas** un appui. Une fenêtre discordante donnerait `E_NO_BENCHMARK`, une issue publiée
en code 0 ; or l'issue n'est pas lue.

Ce n'est pas un journal de requêtes Postgres. **Aucun artefact du chemin sélection n'a été ouvert** pour l'établir.

**Non-lecture.** Rien ne s'est affiché, hors de la liste close et des deux booléens autorisés :
- aucune sortie du producteur ni de la chaîne ;
- aucun journal ;
- aucun listing, taille ou sha d'artefact.

L'archive a été vérifiée par codes seulement. Le seul sha imprimé est celui de l'archive elle-même.

### Archive et nettoyage

- **Archive** `~/archive/c3b_lot4b_20260928/c3b_lot4b_server_20260928.tgz`, sha256 `6c02f438…815d`. Elle contient 30
  fichiers : toutes les sorties, les journaux, la chaîne, le `candles.json` extrait du lot 3 et le pilote. Ni le `.env`
  ni le clone n'y sont (compte vérifié : 0).
- **Vérifiée sur le serveur, par codes seulement** :
  - liste de l'archive comparée par `diff -q` à la liste des fichiers : 0 ;
  - `sha256sum -c --status` : 0 ;
  - extraction et `diff -rq` : 0 ;
  - `cmp` du pilote : 0 ;
  - `sha256sum -c` sur l'extraction : 0.
- `files_all.sha256` et `files_expected.txt` restent **sur le serveur seulement**.
- **`rm -rf ~/runs/c3b_eval4b` le 2026-09-28 à 14:50:01Z**, après ces vérifications ; le `.env` copié est parti avec.
  Le service reste à `e9c8faf`, le collector actif.

## 5. Preuves de ce répertoire

| Fichier | Contenu |
|---|---|
| `ATTENDU.md` | attendu, committé avant le run (`459190a`) |
| `server/run_c3b_eval4b.sh`, `server/status.txt`, `server/pilot_exit.txt` | le pilote qui a tourné, ses codes |
| `server/alembic_before.txt`, `server/alembic_after.txt` | `alembic current` avant et après |
| `server/verify_attendu.py`, `server/verify_attendu.out` | vérification de l'attendu, sur `status.txt` seulement |
| `server/c3b_lot4b_server_20260928.tgz.sha256` | sha de l'archive |
| archive seulement | toutes les sorties du producteur et de la chaîne, et leurs journaux ; jamais ouverts |
| `tests/` | `red_before_{a0d452d,skeleton}.out`, `make_skeleton_4b.py`, `mutants.py`, `mutants_pass1.log`, `mutants.log`, `mutants_4a_replay.log`, `suite.out`, `mypy_audit.out`, `mypy_src.out`, `test_diff_4a.txt`, `controle_diff.txt` |

## 6. Limites, candidats et listes pour la clôture

### Limites (consigne du GO de lancement)

- **Le chemin sélection ne traverse `c3_verdict` qu'au serveur.** Le monde synthétique des tests n'a aucun candidat
  estimable au préfixe (D3 : trop peu de cycles en 9,8 jours) : `c3_select` s'y abstient.
  - En processus, la chaîne complète tourne donc sur une évaluation **désignée**, avec des λ simulés, et décide
    l'abstention **après** avoir lu, rejoué et recoupé tout l'artefact.
  - Le chemin sélection lui-même n'est exercé, jusqu'au verdict, que par le run de ce lot.
- **Candidat de clôture** : un monde synthétique où un candidat est estimable et retenu, pour que le chemin sélection
  traverse `c3_verdict` en test.

### Candidats v2.2 (liste, jamais implémentés ici)

- **E5** : comparateur d'évaluation non constructible. `E_NO_BENCHMARK` est inatteignable, parce que la chaîne exige
  `returns_bench`.
- **E11** : la chaîne ne recoupe ni λ ni `returns_bench` ; la garantie ne tient que côté producteur.
- **Rappel du 4a** : une évaluation réelle sans trade n'a pas de `first_fill_at`. Elle est refusée en R0 par
  l'admission, alors que le § B.8 admet c5 `NON VÉRIFIABLE`.
- **Rappel du lot 3, E3** : jours couverts indéfinis quand `covered_units == 0`.

### Sorties en code 1 de la chaîne, hors table § I.1 (liste du lot 2, complétée)

- Les quatre chemins `NaN` du lot 2 : `c3_anchor.py:335`, `c3_benchmark.py:166-168`, `c3_select.py:294-297`,
  `c3_verdict.py:413`.
- **X1, ajout de ce lot** : `cc.recompute_daily`, via `cc.cagr_pct` et `math.exp`, lève `OverflowError` sur une
  trajectoire dont le CAGR déborde. Sur une telle série, `c3_benchmark` (`candidate_block`) sortirait par une exception
  non rattrapée. Le producteur, lui, la route en 3.

### Écarts au brief, à corriger à la clôture (liste complète au 4b)

| Écart | Où |
|---|---|
| Noms : `select.json` → `selection.json` ; `stamp_cell` = `c3_continuity.stamp_cell_block` ; `evaluation_run.json` n'est plus un artefact (E1), le fichier de provenance garde le nom `evaluation_run_provenance.json` | lots 3, 4a, 4b |
| `ReadOnlyDatabaseManager` vit dans `scripts/audit/_db.py`, pas dans `_common.py` (décision du lot 2) | lot 2 |
| Flag `--selection`, et non `--select` | 4a, D5 |
| `--benchmark`, nommé dans l'architecture du brief mais absent de la spécification § Lot 4b | 4b, E2 |
| Décision 2 : la phrase « l'issue publiée est citée dans le rapport » est **rayée** ; l'issue n'est pas lue | clôture 4a |
| Capital représentable en `float` : sinon, le moteur ne démarre pas avec `C` (note pour le manifeste de campagne) | 4a, D4 |
| `first_fill_at` nul contre c5 `NON VÉRIFIABLE` (candidat v2.2 ci-dessus) | 4a |
| Chemins en code 1 hors § I.1 de la chaîne (liste ci-dessus, plus X1) | lot 2, 4b |
| `test_rejeu_effect.py::test_calibration_writes_no_extrapolation_of_the_fwe_quantile` instable : assertion par sous-chaîne sur un texte qui porte des chronomètres ; corriger en assertant sur les champs parsés | 4a |
| `candles_eval.json` : la paire évaluée seule (E3) ; comparateur non constructible → 2 (E5) ; comparateur avant le moteur (E7) | 4b |

### Défauts de ma part, pour la section défauts du rapport final

- **Tests 4b qui ne mordaient pas au premier passage de mutants (M01, M11).** Le monde de test était trop court pour
  que le tirage se voie, et le candidat évalué était le premier bloc de `benchmark.json`. Corrigé, puis second passage
  entièrement rouge.
- **Pilote** : mauvais chemin dans l'archive du lot 3 (`./run1/…` au lieu de `out/run1/…`), vu **avant** le lancement
  par une vérification en lecture seule.
- **`rc=` vide à la première vérification de l'attendu** : j'ai relu `PIPESTATUS` sous zsh, le défaut déjà noté au 4a.
  Refait sous bash, `rc=0`.
- **Faux verts-avant dans mon analyse du rouge-avant.** Ma regex `\S+` coupait les identifiants de test contenant une
  espace. Les deux tests étaient bien rouges ; leurs identifiants sont passés en ASCII sans espace, et l'analyse a été
  refaite.

## 7. Pour la suite

- **Porte § L.5, option 1**, au SHA livré (les 24 `_full` sur le serveur), puis **STOP avant merge** du chantier, en
  session à part.
- **Rapport final du chantier** (`results/c3b_producteur/report.md`) :
  - la phrase de non-lecture ;
  - les listes du § 6 ;
  - les défauts ci-dessus ;
  - la fuite de 336 octets du 4a ;
  - l'exemption `trades == 0` exercée au 4a.
- **Docs de clôture**, hors de ce lot : `PROJECT_CONTEXT`, `ROADMAP`, `skills/backtest.md` (§ « Producteur C3b »),
  correction du brief.
