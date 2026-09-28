# C3b lot 2 — `_common.py`, writer strict, S-4 : rapport et preuves

Brief : `agent/AGENT_C3B_PRODUCTEUR.md` § « Lot 2 ». Branche `feat/c3b-producteur`, partie de `f4b3e33`. Exécuté le
2026-09-27, en local (tunnel 5433, `.env`). Aucun code du producteur n'existe encore : ce lot ne produit aucune
métrique de candidat. Un incident de test a toutefois lu la base, il est décrit au § 8.

| Commit | Sujet |
|---|---|
| `02360db` | `refactor(audit): _common.py partagé (git_provenance, ReadOnlyDatabaseManager)` |
| `6953fbc` | `fix(audit): write_json strict — un type non JSON est une erreur nommée (dette 22)` |
| `c61793f` | `ci: ruff sur les scripts d'audit C3` |
| `75d9a51` | `docs(results): C3b lot 2 — inventaire writer, rouge-avant, mutants` |
| celui-ci | `docs(results): C3b lot 2 — état CI constaté par l'API publique` |

## 1. Ce qui est livré

- `scripts/audit/_common.py` — module pur (bibliothèque standard seule). `write_json_strict(path, payload)` et
  `git_provenance(script_relpath, *, root)`.
- `scripts/audit/_db.py` — `ReadOnlyDatabaseManager`, déplacé tel quel depuis `warmup_at.py`.
- `scripts/audit/c3_common.py` — `import _common` et `write_json = _common.write_json_strict`. Rien d'autre.
- `scripts/audit/warmup_at.py`, `scripts/audit/reconstruct_1w.py` — plus aucune copie locale ; chacun appelle
  `git_provenance(SCRIPT_RELPATH)`.
- `.github/workflows/ci.yml` — `ruff check` et `ruff format --check` sur la liste explicite ; `"feat/**"` au push.
- `tests/test_scripts/test_audit_common.py` — 44 tests.
- `tests/test_scripts/test_c3_common.py`, `test_c3_verdict.py` — 6 lignes ajoutées, 3 retirées (§ 2, décision 1).

Contrat du writer : parcours du payload **avant** toute écriture, en types exacts — `str`, `int`, `float`, `bool`,
`None`, `dict` à clés `str`, `list`, `tuple`. Tout autre type, sous-types compris, lève `TypeError` ; un flottant non
fini lève `ValueError` ; une clé non `str` lève `TypeError`. Le message commence par le chemin de la valeur
(`a.b[3].c`). Sur refus rien n'est créé, pas même le répertoire. Sur un payload JSON pur, le texte et le sha256 sont
ceux de `rejeu_common.write_json`.

## 2. Décisions du 27/09 — écarts au brief, à reporter à la clôture

| # | Décision | Écart |
|---|---|---|
| 1 | `witness_returns` et `varying_returns` rendent des `float` natifs (`.tolist()`) ; le site adverse `test_c3_verdict._write_cli_inputs` garde `rc.write_json` | le brief disait « sans modification des tests » ; le STOP visait des sites de production, et l'inventaire est vide |
| 2 | `"feat/**"` ajouté à `push.branches` | au-delà de S-4, qui ne parlait que du lint |
| 3 | `parse_now` et `read_json` restent ceux de `c3_common` | le § Lot 2 les rangeait dans `_common.py` « déplacés depuis `warmup_at` / `reconstruct_1w` » : ils n'y étaient pas. La liste close prime. **Brief à corriger** |
| 4 | Preuves dans un 4e commit | la consigne disait trois commits |
| 5 | `ReadOnlyDatabaseManager` dans `_db.py`, `_common.py` pur | liste close amendée : un fichier neuf de plus ; le grep du critère de fin cherche la classe dans `_db.py` |
| 6 | Clé de dictionnaire non `str` refusée | au-delà du libellé du brief |
| 7 | Chemins `NaN` listés, non corrigés | § 4.3 |

`_db.py` est ajouté à la liste de la CI et au contrôle mypy, par conséquence de la décision 5.

## 3. Inventaire exigé au plan

Question : quels sites de `scripts/audit/c3_*.py` passent au writer un `Decimal`, un `datetime` ou un type numpy ?

**Aucun. La liste est vide**, aucune conversion n'a été faite, aucun `c3_{anchor,entry,benchmark,select,continuity,
verdict}.py` n'est touché.

| Site d'écriture | Écritures sous les 932 tests | Valeurs non natives |
|---|---|---|
| `c3_anchor.py:326`, `:335` (registre), `:339` | 730 | 0 |
| `c3_entry.py:986` | 278 | 0 |
| `c3_benchmark.py:691`, `:698` | 135 | 0 |
| `c3_select.py:796`, `:805` | 113 | 0 |
| `c3_continuity.py:529`, `:538` | 52 | 0 |
| `c3_verdict.py:1301`, `:1318` | 137 | 0 |

Méthode, deux voies indépendantes qui concordent :

1. **Sonde** (`probe_writer.py`) : elle enveloppe le writer, parcourt chaque payload en types exacts et laisse
   l'écriture se faire. 1 445 écritures de production, zéro constat.
2. **Lecture statique intégrale** des sept modules : chaque feuille de chaque payload, remontée à sa construction.

La convention des sites est déjà la conversion à la construction : `.isoformat()` sur les `datetime`, `str()` sur les
`Decimal`, `float()` / `int()` sur les scalaires numpy.

**Ce que cela dit des artefacts C3a existants : `default=str` n'y a jamais été appelé. Aucun n'a écrit une chaîne à
la place d'un nombre, ni l'inverse.**

## 4. Ce que l'inventaire a appris d'autre

### 4.1 L'exemple de la dette 22 est inexact pour `numpy.float64`

La dette dit qu'un `numpy.float64` « serait écrit comme texte ». Mesuré (numpy 2.4.1) : `numpy.float64` est un
sous-type de `float`, `json` l'écrit en nombre et n'appelle jamais `default`. `float32`, `int64` et `bool_` deviennent
bien des chaînes. Conséquence : un `default` qui lève ne voit jamais un `float64` ; seul le parcours en types exacts
le refuse.

### 4.2 101 tests C3 écrivaient ce que le writer strict refuse

| Site de test | Ce qui était écrit | Tests |
|---|---|---|
| `test_c3_continuity.py:_world` | `returns_config` en `numpy.float64` | 66 |
| `test_c3_verdict.py:_chain_world` | `returns_config` en `numpy.float64` | 30 |
| `test_c3_verdict.py:_write_cli_inputs` | `NaN` ou infini injecté exprès | 5 |

Les deux nombres sont recoupés par mutation : le mutant M16 (fixtures rendues en `numpy.float64`) fait échouer
exactement 96 tests, le mutant M17 (site adverse par le writer strict) exactement 5.

### 4.3 Écart de contrat : code 1 hors § I.1

Quatre chemins de production peuvent porter un flottant non fini jusqu'au writer. Aucun n'est exercé par les tests.
Ils ne s'ouvrent que sur une entrée absurde ou sur un jeton `NaN` présent dans un JSON d'entrée (`json.loads`
l'accepte).

| Site | Valeur | Origine |
|---|---|---|
| `c3_anchor.py:335` | enregistrements du registre autres que celui de la variante | recopiés depuis le fichier du registre (`load_registry` `:132-143`, `register` `:186`), jamais canonicalisés |
| `c3_benchmark.py:166-168`, `:436-438`, `:504-506` | `nav`, `returns`, `cagr_pct`, `target_dd`, `cagr_blend_*`, `delta_*` | dépassement de `float(Decimal)` ; `returns` est écrit même quand `all_finite` est faux (`:249`, `:278`) |
| `c3_select.py:294-297`, `:368-371`, `:402` | `mdd_report.recomputed`, `abs_diff`, `recomputed.*`, `scores.cagr_pct` | MDD et CAGR recalculés quand D4 échoue sur un NAV ≤ 0 |
| `c3_verdict.py:413` | `estimabilite.declared` | copie de `evaluation.estimability`, dont seuls `E1`, `E2`, `ok` sont typés |

Avant ce lot, ces chemins écrivaient un artefact portant `NaN` ou `Infinity`, qui n'est pas du JSON. Après, le writer
lève `ValueError`. Aucun `main` de la chaîne ne l'attrape : l'interpréteur sort en **code 1** avec une trace, sans
artefact ni ligne `VIOLATION`. Ce code 1 n'est pas celui de la table du § I.1, qui promet un diagnostic.

Constaté sur un cas, hors dépôt : une évaluation portant `estimability: {"note": NaN}` fait sortir `c3_verdict` en
code 1 sur `ValueError: estimabilite.declared.note: flottant non fini (nan)`, sans `verdict.json`. Les trois autres
chemins sont lus, pas exécutés.

Non corrigé : les six modules sont hors liste close. **Candidat à lister pour la suite.**

## 5. Tests, rouge-avant, mutants

44 tests dans `test_audit_common.py`. Chaque attendu cite son appui (brief § Lot 2, dette 22, docstrings des scripts,
décisions du 27/09).

**Rouge-avant.**

- Partie 1 (9 tests, provenance et définition unique) contre un export de `f4b3e33` : erreur de collecte,
  `ModuleNotFoundError: No module named '_common'` (`red_before_part1.out`). C'est un rouge de module absent, il
  ne dit rien de la finesse des tests : ce sont les mutants M9 à M14 qui prouvent qu'ils mordent.
- Partie 2 (35 tests, writer) contre l'état du commit 1 : **34 rouges, 10 verts** sur 44 (`red_before_part2.out`).
  Le seul test de la partie 2 vert à l'écriture est l'égalité de sha avec `rc.write_json`, par construction ; les
  mutants M6a à M6d le couvrent. Le test d'import de la chaîne était rouge parce que `c3_common` n'importait pas
  encore `_common` ; sa clause « `krakenbot.core.database` absent » était déjà vraie, c'est M12 qui la couvre.

**Mutants** (`mutants.py`, `mutants.log`) : 21 mutants, **tous rouges**, chaque fichier restauré et son sha256
vérifié identique.

| Mutant | Tué par |
|---|---|
| M1 sous-type de `float` accepté | 2 tests |
| M2 parcours retiré, `default=str` | 32 tests |
| M3 non fini accepté | 4 tests |
| M4 index de liste omis du chemin | 9 tests |
| M5 clé non `str` acceptée | 5 tests |
| M6a `indent=4`, M6b `sort_keys=False`, M6c sans `\n`, M6d `ensure_ascii=True` | 1 test chacun |
| M7 répertoire créé avant validation | 30 tests |
| M8 `c3_common.write_json` revient au writer du rejeu | 1 test |
| M9 chemin haché constant | 2 tests |
| M10a `tracked_tree_clean` forcé vrai | 3 tests |
| M10b `script_tracked` forcé vrai | 1 test |
| M11 manager sans lecture seule | 1 test |
| M12 `_common` importe `_db` | 2 tests |
| M13 `warmup_at` passe le chemin d'un autre script | 1 test |
| M14 copie locale réintroduite | 2 tests |
| M15 fixtures en `numpy.float64` | 1 test |
| M16 idem, sur les tests C3 | 96 tests |
| M17 site adverse par le writer strict | 5 tests |

## 6. Identité des écritures, avant et après

`probe_writer.py` relève le sha256 de chaque fichier écrit par les 932 tests C3, par les sites de test comme par
les sites de production. Clé : `test | rang de l'écriture | nom du fichier`.

| Run | État | Écritures |
|---|---|---|
| `sha_before.json` | `f4b3e33`, tree suivi propre, avant toute modification | 4 354 |
| `sha_before_twin.json` | même état, second run | 4 354 |
| `sha_after.json` | `c61793f`, tree suivi propre | 4 354 |

Entre les deux runs de référence, 0 écriture instable. Entre avant et après : **4 354 comparées (1 445 de
production, 2 909 de test), 0 absente, 0 nouvelle, 0 refusée, 0 sha256 différent** (`compare_before_after.out`).

Après le lot, plus aucun `numpy.float64` n'atteint un writer, et les seuls flottants non finis passent par le site
adverse, via `rc.write_json`.

## 7. Critère de fin

| Critère | État | Preuve |
|---|---|---|
| `test_audit_common.py` vert, rouge-avant et mutants consignés | fait | § 5 |
| 932 tests C3 verts | fait, assertions intouchées, diff limité à la décision 1 | `sha_after.out` |
| Suite locale verte, `-k "not test_determinism_parallel_vs_serial_full"` | **3 042 passés**, 6 skippés, 24 désélectionnés (base 2 998 + 44) | `suite_commit2.out` |
| grep négatif | trois définitions, chacune à sa place | `controles_fin_de_lot.out` |
| `ruff check` et `ruff format --check` sur la liste | verts, 22 fichiers | idem |
| mypy strict sur `_common.py` et `_db.py` | vert ; `warmup_at.py` reste vert | idem |
| Diff de contrôle | 9 fichiers, tous listés ; vide sur les fichiers nommés par le brief et sur `src/` | idem |
| CI verte sur la branche | **verte sur `75d9a51`**, toutes les étapes en succès, dont les deux étapes ruff « audit C3 » | [run 36326173115](https://github.com/stordd13/kraken-trading-bot/actions/runs/36326173115) |

La CI a été lue **après** le commit `75d9a51`, qui disait ici « non constaté par moi » : `gh` n'était pas authentifié
et le serveur MCP github répondait 401. Le dépôt est public ; l'état du run a été lu par l'API REST de GitHub, sans
jeton, le 2026-09-27 (run créé à 14:30:40Z, terminé à 14:37:12Z, première tentative). Bruno a constaté le même run
vert de son côté. Avant le push, les deux étapes ajoutées avaient été exécutées localement telles qu'écrites dans le
workflow, sous bash : vertes.

Ce que je n'ai pas pu vérifier :

- **`reconstruct_1w.py` sous mypy** garde son erreur antérieure au lot (`:210`, `no-any-return`). `mypy src/` :
  65 erreurs, égal à la base.
- **Les écritures de `warmup_at` et de `reconstruct_1w` par leur `main`** ne sont exercées par aucun test. Le passage
  du writer « strict au sens de `json` » au writer à types exacts n'y est couvert que par la sonde sur
  `build_payload` (0 constat) et par la lecture de `build_report`.

La suite sur l'état du commit 1 a rendu 3 006 passés et 1 échec : `test_c2_replay_fidelity_db`, sur
`[Errno 54] Connection reset by peer` (tunnel). Relancé seul sur le même arbre, il passe (`suite_commit1.out`).

## 8. Incident : un test non hermétique a lu la base

Pendant le premier run des mutants, M10a a duré 579 s. Sous ce mutant l'arbre sale est déclaré propre : le test du
refus `uncommitted_tree`, tel que je l'avais écrit, laissait alors `warmup_at.main` et `reconstruct_1w.main check`
continuer. Après le contrôle de provenance, ce chemin charge `.env`, lit la base par le tunnel et, pour `check`,
interroge Binance Vision. Je n'ai pas de trace de ce qui a été effectivement lu : je le déduis du code et de la
durée. Les deux cas du test ont échoué, donc aucun des deux `main` n'a rendu le refus attendu.

- Les deux scripts sont en lecture seule, assertée côté Postgres : rien n'a pu être écrit en base.
- Leurs sorties, s'il y en a eu, sont allées dans les répertoires temporaires de pytest. Je ne les ai pas lues.
- Ce ne sont pas des runs du producteur et ils ne calculent aucune métrique de candidat. Ils lisent en revanche
  des estampilles de la fenêtre `2021-03-01 → 2026-06-29`, comme lors de leurs chantiers d'origine.
- Aucune ligne n'a été ajoutée à `docs/RESEARCH_LOG.md` : à toi de dire s'il en faut une.

Défaut de mon test, vu par le mutant. Corrigé dans `6953fbc` : `.env` n'est plus chargé, `DATABASE_URL` est retirée,
`collect` lève. M10a est rouge en 1 s au second run. Le premier journal est conservé
(`mutants_run1_test_non_hermetique.log`).

## 9. À consigner à la clôture du chantier

- **Dette 22, fermée.** Fix dans `scripts/audit/_common.py`, pas à `rejeu_common.py:344` : `rejeu_common.write_json`
  est gelé avec le diagnostic du 20/09. Corriger l'exemple du `numpy.float64` (§ 4.1).
- **Brief** : `parse_now` et `read_json` hors `_common.py` ; `_db.py` dans la liste close ; grep du critère de fin.
- **Candidat pour la suite** : les quatre chemins du § 4.3.
- **Lots 3 et 4** : les `c3b_*` importent `cc.parse_now` et `cc.read_json`, écrivent par `_common.write_json_strict`,
  et convertissent au site d'écriture.

## 10. Fichiers de ce répertoire

| Fichier | Contenu |
|---|---|
| `probe_writer.py`, `probe.sh`, `compare_sha.py` | la sonde, son lanceur, la comparaison |
| `sha_before*.json`, `sha_after.json`, `*.state.txt`, `*.out` | les trois relevés et l'état git de chacun |
| `compare_before_after.out` | le verdict d'identité |
| `red_before_part1.out`, `red_before_part2.out` | les rouges-avant |
| `mutants.py`, `mutants.log`, `mutants_run1_test_non_hermetique.log` | les mutants, leur journal, le journal du premier run |
| `suite_commit1.out`, `suite_commit2.out` | les suites locales |
| `controles_fin_de_lot.out` | grep négatif, diff de contrôle, ruff, mypy |
