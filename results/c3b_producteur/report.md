Aucune donnée de la fenêtre de campagne 2021-03-01 → 2026-06-29 n'a été lue par le producteur, sur aucun des trois runs serveur ; aucune issue de chaîne n'a été lue.

# C3b — producteur conforme au protocole C3 v2.1 : rapport final (paquet 1)

**Fenêtre d'instrument, aucune portée économique.** Ce chantier livre l'outillage qui permet à une campagne réelle de
traverser la chaîne C3. Il ne dit rien de la famille grid : aucune métrique de candidat n'a été lue, commentée ni
reportée. Le seul terrain réel est la fenêtre de conformité `2020-01-06 → 2020-12-28`, entièrement antérieure au
2021-03-01.

- **Brief** : `agent/AGENT_C3B_PRODUCTEUR.md`, avec en tête ses écarts constatés à la livraison.
- **Branche** `feat/c3b-producteur`, partie de `dev = ec7ffb8`. Cinq lots, une session et un plan validé par lot.
- **SHA livré** : le commit qui porte ce rapport et les autres docs de clôture. Il est cité, avec son run CI, dans
  `closure/gate_L5/README.md`.
- **Porte § L.5 option 1** : `src/` est touché par le lot 1, l'option 2 est donc indisponible. Les 24 `_full` tournent
  au serveur, au SHA livré, dans `~/runs/c3b_gate/`. Les preuves sont dans `closure/gate_L5/`, au commit suivant ; ce
  rapport n'y est pas retouché.
- **Merge** : `--no-ff` sur `dev`, avec le push de `dev`, le `pull --ff-only` du serveur et `docs/CODE_MAP.md`
  régénéré. C'est Bruno qui le fait.
- **Journal** : `docs/RESEARCH_LOG.md`, entrées 15, 16 et 17, avec leurs issues.

## 1. Ce qui est livré

**Les quatre temps** (`skills/backtest.md` § « Producteur C3b ») :

```
c3b_prefix.py  →  c3_anchor / c3_entry / c3_benchmark / c3_select  →  c3b_evaluate.py  →  c3_verdict.py chain
 (préfixe)                        (chaîne 1-4)                          (évaluation)        (chaîne complète)
```

| Fichier | Rôle | Lot |
|---|---|---|
| `src/krakenbot/strategies/base.py`, `grok_grid_atr_adaptive_v4.py` | classmethod `decision_timeframes` (pure, oracle `_get_directional_bias`) ; refus d'un `pause_1w_strong_bear` non booléen ; `NotImplementedError` sur `BaseStrategy` | 1 |
| `scripts/audit/_common.py`, `scripts/audit/_db.py` | `write_json_strict`, `git_provenance` (stdlib) ; `ReadOnlyDatabaseManager` | 2 |
| `scripts/audit/c3_common.py`, `warmup_at.py`, `reconstruct_1w.py` | writer strict et imports partagés, rien d'autre | 2 |
| `.github/workflows/ci.yml` | ruff sur les scripts d'audit C3 ; `feat/**` au push (S-4) | 2 |
| `scripts/audit/c3b_common.py` | fabrique du moteur, couche d'export, couverture, bougies, garde-fou 6, garde de désignation, `passed_params_problems` | 3, 4a |
| `scripts/audit/c3b_prefix.py` | temps 1 | 3 |
| `scripts/audit/c3b_evaluate.py` | temps 3 : run unique, preuves § B, comparateur § C.5, procédure § F.2 rejouable | 4a, 4b |
| 5 fichiers de tests neufs | 326 tests, **aucun n'accède à la base** | 1 à 4b |

Suite locale : 2 938 passés à la base, **3 264** au lot 4b (+ 326), avec 6 ignorés et les 24 `_full` désélectionnés.
`mypy src/` vaut **65**, la base, à chaque lot.

## 2. Par lot

### Lot 1 — `decision_timeframes` (`results/c3b_producteur/lot1_ab/`)

- **Commits** : `10ed8d8` (feat), `f4b3e33` (preuves), le 25/09.
- **Tests** : 60 (`test_grid_v4_decision_timeframes.py`).
  - Rouge-avant sur `src/` à `ec7ffb8` : 58 échecs.
  - 2 verts, qui épinglent des entrées et n'appellent pas la classmethod.
- **Mutants** : 7, tous rouges. Parmi eux, la forme fermée `bias_1d != 0`, `"1w"` inconditionnel et la coercition
  `bool(...)`.
- **Invariant** : `compare-ab --strict` sur les trois runs de référence (signal A, grid quick, grid A), **`STRICT
  IDENTITY OK`** partout. Seule `source_fingerprints.strategy` change, pour grid.
- **Gold hashes** : 2/2. **Suite** : 2 998.
- **Pas de run serveur.** Les gz de grid A sont gardés hors dépôt, dans `~/archive/c3b_lot1_20260925/` (Mac) :
  `ac2e85e8…` pour la référence, `12507a47…` pour C3b.
- **Pas de run CI propre** : le déclencheur `feat/**` n'est ajouté qu'au lot 2, et les runs suivants couvrent ce code.

### Lot 2 — `_common.py`, writer strict, S-4 (`results/c3b_producteur/lot2_writer/`)

- **Commits** : `02360db` (refactor), `6953fbc` (fix, dette 22), `c61793f` (ci), `75d9a51` et `0a6c33e` (preuves), le
  27/09.
- **Tests** : 44 (`test_audit_common.py`).
  - Partie 1, rouge-avant : module absent.
  - Partie 2 : 34 rouges, 10 verts.
- **Mutants** : 21, tous rouges.
- **Identité des écritures** : les 4 354 écritures des 932 tests C3 ont le même sha256 avant et après.
- **Inventaire des 12 sites d'écriture de `c3_*.py` : vide.**
- **Suite** : 3 042. **CI verte**, [run 36326173115](https://github.com/stordd13/kraken-trading-bot/actions/runs/36326173115).
- Pas de run serveur.

### Lot 3 — producteur préfixe (`results/c3b_producteur/prefix_conformite/`)

- **Commits** : `8f7d7a1`, `feb5a82` (feat) ; `6509737` (entrée 15, manifeste et attendu : **SHA du run**) ;
  `4d5eb46` (preuves).
- **Tests** : 118. Rouge-avant contre des squelettes AST : 107 échecs, 6 erreurs, 5 verts.
- **Mutants** : 44. 43 rouges, M44 équivalent (le writer trie les clés).
- **Suite** : 3 160. **CI** : [run 36338454694](https://github.com/stordd13/kraken-trading-bot/actions/runs/36338454694).
- **Run serveur** au `6509737`, le 28/09 de 06:46:17 à 06:49:15Z.
  - Pilote `ee1f5a53b07ff62242d939fab651acfb8d9cb23530553dad3b37b29ae86a111d`.
  - Tous les codes à 0.
  - Sorties identiques au bit entre 4 workers et 1.
  - `c3_entry` sans clause non assertable.
  - Attendu tenu sur 7 items sur 7.
- **Archive** `~/archive/c3b_lot3_20260928/c3b_lot3_server_20260928.tgz`, sha256
  `80b5f2b9099061cbfc4eeea83ead5c60ea8cec4d7e1403cacccab1fc0632cee8`. `rm -rf` à 06:51:56Z.

### Lot 4a — run d'évaluation et preuves § B (`results/c3b_producteur/eval_conformite/`)

- **Commits** : `57b498e` (refactor E10) ; `527e5ae` (feat) ; `85c8db7` (entrée 16 et attendu : **SHA du run**) ;
  `a0d452d` (preuves).
- **Tests** : 55, plus 5 dans `test_c3b_common.py`. Rouge-avant : 5 sur 5 pour la garde, 52 échecs et 3 verts pour
  `test_c3b_evaluate.py`.
- **Mutants** : 36, tous rouges. M01 rougit aux lots 3 **et** 4a.
- **Suite** : 3 220.
- **CI**
  - `85c8db7` : [run 36417095417](https://github.com/stordd13/kraken-trading-bot/actions/runs/36417095417). Verte en
    tentative 2 ; la tentative 1 était le flaky `test_rejeu_effect`.
  - `a0d452d` : [run 36423259134](https://github.com/stordd13/kraken-trading-bot/actions/runs/36423259134).
- **Run serveur** au `85c8db7`, le 28/09 de 12:34:12 à 12:34:44Z.
  - Pilote `7bdc1bd2c041e4144dc44bfe1f0193ec05859e5174e9483238e07d9452a1b18a`.
  - Chemin sélection : **code 0 ×2**, seul fait rapporté.
  - Chemin désigné : code 0 ×2, artefact identique au bit, admission réelle, c1 / c2 / c5 `DECLARED`.
  - Attendu tenu sur 8 items sur 8.
  - **Exemption `trades == 0` exercée sur données réelles** : rien n'est liquidé à `fin`, et `stamp_cell` vaut
    `NOT_VERIFIABLE`, satisfait à vide.
- **Archive** `~/archive/c3b_lot4a_20260928/c3b_lot4a_server_20260928.tgz`, sha256
  `1e401ab2b85d43dd491dfd458ff938618d9aa540e35bcd0ed38d29f38cfba502`. `rm -rf` à 12:36:11Z.

### Lot 4b — comparateur d'évaluation et § F.2 (`results/c3b_producteur/eval_f2_conformite/`)

- **Commits** : `3740c40` (feat) ; `459190a` (entrée 17 et attendu : **SHA du run**) ; `d351b36` (preuves).
- **Tests** : 44 nouveaux, soit 99 dans `test_c3b_evaluate.py`.
  - Rouge-avant contre `a0d452d` : 91 échecs, 8 verts.
  - Contre un squelette 4b : 74 échecs, 25 verts.
  - Les 44 tests 4b sont rouges dans les deux cas.
- **Mutants** : 35 sur 35 rouges au second passage (le premier est au § 4). Les 36 mutants 4a, rejoués au tip 4b,
  sont tous rouges.
- **Suite** : 3 264.
- **CI**
  - `459190a` : [run 36436609751](https://github.com/stordd13/kraken-trading-bot/actions/runs/36436609751), vert dès
    la tentative 1.
  - `d351b36` : [run 36439266345](https://github.com/stordd13/kraken-trading-bot/actions/runs/36439266345).
- **Run serveur** au `459190a`, le 28/09 de 14:48:51 à 14:49:13Z.
  - Pilote `9b401797639bc9b1928aa952257a67c9742f471244f9de7547d1d25f637f9cc8`.
  - Producteur : 0/0, `evaluation.json` identique au bit, trois autres artefacts identiques.
  - **Chaîne complète en six étapes, toutes en 0, `chain.verified` vrai, 0 violation, 0 violation au rejeu.**
  - `alembic` inchangé. **Issue non lue.**
- **Archive** `~/archive/c3b_lot4b_20260928/c3b_lot4b_server_20260928.tgz`, sha256
  `6c02f438733e42ede8bdeb02e5adc8e840f2ff9f0c38827f37cd13e78efe815d`. `rm -rf` à 14:50:01Z.

Tous les runs serveur ont eu lieu en lecture seule assertée par Postgres, avec `alembic` à `c3bd1e7a0001` avant et
après. Le service est resté à `e9c8faf`, et le collector actif.

## 3. Dette 22 fermée, avec son écart de site

- **Le fix** : `scripts/audit/_common.write_json_strict`, par parcours du payload en types exacts **avant**
  l'écriture. Le message commence par le chemin de la valeur. `c3_common.write_json` pointe dessus.
- **L'écart de site, déclaré** : `rejeu_common.write_json` (`rejeu_common.py:340-344`) **n'est pas touché**. Il est
  gelé avec le diagnostic du 20/09.
- **Le libellé de la dette était faux** pour `numpy.float64`. C'est un sous-type de `float`, que `json` écrit en
  nombre sans appeler `default`. Ce sont `float32`, `int64` et `bool_` qui devenaient des chaînes.
- Voir `PROJECT_CONTEXT.md` § 9, dette 22, et `lot2_writer/README.md` § 3-4.

## 4. Défauts du chantier

Consolidés et datés par lot, sans adoucissement.

**Shell zsh au lieu de bash : trois incidents, une même cause, en cinq lots.**

1. **Lot 1, captures `compare-ab`.** `$P` n'a pas été découpé en mots par zsh, et le premier lancement des captures a
   échoué. Correction : `lot1_ab/capture.sh`, en bash, avec un tableau (`P=(…)`, `"${P[@]}"`).
2. **Lot 4a, suite du commit A.** J'ai lu `PIPESTATUS` sous zsh, sans `pipefail`, et `rc=` est resté vide
   (`eval_conformite/tests/suite_commitA.out`). Le code de pytest n'a pas été capturé.
3. **Lot 4b, première vérification de l'attendu.** J'ai de nouveau lu `PIPESTATUS` sous zsh, et `rc=` était vide.
   J'ai refait la vérification sous bash, avec `rc=0`.

Les deux derniers sont des lectures de `PIPESTATUS` ; le premier est un découpage en mots. La cause est la même :
une commande de vérification écrite pour bash et exécutée par l'outil, qui tourne sous zsh. D'où la règle de cette
clôture : toute vérification qui produit un code est un script `.sh` lancé par `bash`, committé avec sa sortie
(`closure/tests/`).

**Lectures non prévues de la base ou de la fenêtre de campagne.** Aucune n'est un run du producteur.

- **Lot 2, incident du tunnel (579 s).**
  - Sous le mutant M10a, le test du refus `uncommitted_tree` n'était pas hermétique. `warmup_at.main` et
    `reconstruct_1w.main check` ont continué, ont chargé `.env` et ont lu la base par le tunnel, estampilles de la
    fenêtre de campagne comprises.
  - `check` a aussi interrogé Binance Vision.
  - Ce n'est pas un run du producteur, et aucune métrique de candidat n'a été calculée. Les sorties éventuelles sont
    allées dans les répertoires temporaires de pytest, non lues.
  - Corrigé dans `6953fbc` (`.env` coupé, `DATABASE_URL` retirée, `collect` qui lève). Règle depuis : tout `main`
    capable d'atteindre la base est testé avec `_db.ReadOnlyDatabaseManager` bouchonné.
- **Lot 4a, `_full` lancés sans `-k`.**
  - La suite du commit A a tourné sans le `-k` des `_full`, contrairement à la condition du GO. Les 24 tests de
    déterminisme P6 (fenêtre 2023-04 → 2026-04, qui recoupe la campagne) ont donc tourné en local, par le tunnel :
    **3 h 27**, tous verts.
  - Ils ne comparent que des hashes ; aucune métrique n'a été lue. Ce ne sont pas des runs du producteur. S'y
    ajoute le `rc` non capturé du point 2 ci-dessus.
- **Lot 4a, fuite de 336 octets.**
  - En listant les tailles des sorties sur le serveur, avant l'archivage, j'ai vu 5 222 octets pour
    l'`evaluation_run.json` du chemin sélection et 4 886 pour le désigné. Cela révèle en partie que **le retenu n'est
    pas le désigné**.
  - Ni l'identité ni aucune métrique n'ont été lues. Ce fait n'est utilisé nulle part.
  - Leçon appliquée au 4b : aucun listing, aucune taille, aucun sha d'artefact du chemin sélection.

**Preuves et tests.**

- **Lot 2, un README faux.** `75d9a51` disait la CI « non constatée par moi » alors qu'elle était lue. C'est corrigé
  tout de suite par `0a6c33e` : un fichier de preuves qui dit le contraire de ce qui s'est passé se corrige sans
  attendre la clôture.
- **Lot 4b, mutants survivants côté tests.** Au premier passage, 4 survivants :
  - M01 et M11 : **défauts de mes tests**. Un monde de 5 rendements pour des blocs de 10 à 42 fait de chaque
    réplication une rotation, et le candidat évalué était le premier bloc de `benchmark.json`.
  - M10 et M12 : données non discriminantes.
  - Corrigé, puis 35 rouges sur 35.
- **Lot 4b, faux verts-avant.** Ma regex `\S+` coupait les identifiants de test contenant une espace. Les tests
  étaient bien rouges ; j'ai refait l'analyse avec des identifiants ASCII sans espace.
- **Lot 3, item 5 de l'attendu mal rédigé.** « Sélection descriptive » présumait un retenu. Il a été vérifié par le
  seul booléen `status != SÉLECTION_VALIDE`, sans lire l'issue BTC/ETH.
- **Lot 3, fausse alerte `mypy`.** J'ai lu 64 au lieu de 65, faute d'avoir vu que `--ignore-missing-imports` masquait
  une erreur. Le diff des deux sorties l'a résolue.
- **Lot 4b, chemin d'archive faux dans le pilote** (`./run1/…` au lieu de `out/run1/…`). Vu **avant** le lancement,
  par une vérification en lecture seule.

## 5. Limites

- **Le chemin sélection ne traverse `c3_verdict` qu'au serveur.**
  - Le monde synthétique des tests n'a aucun candidat estimable au préfixe (D3), et `c3_select` s'y abstient.
  - En processus, la chaîne complète tourne donc sur une évaluation **désignée** avec des λ simulés.
  - Seul le run du 4b exerce le chemin sélection jusqu'au verdict. C'est un candidat de clôture (`PROJECT_CONTEXT.md`
    § 9).
- **La preuve de départ à plat vaut DÉCLARÉ, jamais plus** (§ B.2).
  - Elle est produite par le programme dont elle décrit l'état.
  - Les lectures probantes sont `usdc_balance` et `btc_held`, avant `run`.
  - `pending` est vide **par construction** : sur le chemin grok, les ordres vivent dans la stratégie interne, créée
    dans `run`.
- **« λ du préfixe tenu fixe » n'est garanti que côté producteur**, par construction et par le mutant « λ
  ré-estimé ».
  - La chaîne ne recoupe ni λ ni `returns_bench` (4b, E11).
  - De même, l'égalité `returns_config ← equity_daily` n'est garantie que par le producteur (ex-S-3).
  - Les deux sont candidats v2.2.
- **La chaîne C3a est intouchée en code, mais deux de ses fichiers de test ont changé.**
  - Depuis `ec7ffb8`, `tests/test_scripts/test_c3_common.py` et `test_c3_verdict.py` ne sont pas vides. C'est le lot 2
    (`6953fbc`, +6 / −3).
  - Deux aides rendent désormais `.tolist()`, et un site adverse passe par `rc.write_json`. Les fixtures écrivent
    ainsi ce qu'écrit un producteur conforme.
  - Les modules `c3_{anchor,entry,benchmark,select,continuity,verdict}.py` ont un diff vide. Le « vide sur
    `test_c3_*.py` » du prompt de clôture était faux ; `closure/tests/controle_diff.sh` le dit.
- **La phrase de la première ligne repose sur trois appuis** : les bornes du code (lectures `≤ T` au préfixe, `≤ fin` à
  l'évaluation, `fin = 2020-12-28`), les tests (lectures bouchonnées aux bornes exactes, `run` appelé une fois) et les
  artefacts. **Ce n'est pas un journal de requêtes Postgres.**
- **Ce que veut dire « aucune issue de chaîne lue ».** Ni l'issue de la sélection BTC/ETH (lot 3), ni le retenu
  (4a, 4b), ni le verdict (4b) n'ont été lus. Des sorties de chaîne, seule a été lue la liste close des attendus :
  - les codes ;
  - D1 et D2 en échec sur SOL, déclarés **avant** le run, par construction ;
  - `chain.verified` ;
  - les comptes de violations.
- **Les 24 `_full` de la porte § L.5 ne sont pas des runs du producteur.** Ce sont des backtests P6 (USDC, défauts
  de classe, 2023-04 → 2026-04) comparés par hash. Leurs journaux d'échec porteraient des métriques
  (`--showlocals`) : ils restent archivés, jamais affichés.

## 6. Ce qui attend

- **Amendement v2.2**, avec la re-passe Astra. Ses candidats sont listés dans `PROJECT_CONTEXT.md` § 9 : `grid_levels`
  (§ A.8 l.515), « alimente une porte » (l.605-606), recoupement `returns_config`, S-1, enforcement du § 10.1, E5,
  E11, `first_fill_at` nul, dates de couverture.
- **Manifeste de la première campagne**, dans une conversation séparée.
  - `CAMPAIGN_UNLOCK`, créé par Bruno.
  - Capital représentable en `float`.
  - Le vrai minimum Bybit pour `min_order_usdc` : `5.0` est la valeur du rejeu, inerte sur le grid.
  - Les 8 estampilles 1 w dérivées, lues dans `ohlc_derived`.
  - `decision_timeframes` par candidat.
  - Les dettes 21 (`--campaign`) et 24 (spread et slippage).
- **Dettes inchangées** : 19, 21, 23, 24.
- **Sorties en code 1 de la chaîne, hors § I.1** : quatre chemins `NaN` et l'`OverflowError` de `recompute_daily`.
- **Candidats de clôture hors C3b** : marqueur `db`, `test_rejeu_effect`, monde synthétique estimable, fabrique en
  `Decimal`, provenance étendue et scan unifié, contrainte de capital. Chacun dans sa propre session.
