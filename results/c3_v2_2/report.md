# C3 — Amendement v2.2 du protocole : rapport de fin de chantier

> **Chantier documentaire, aucun run.** Brief `agent/AGENT_C3_AMENDEMENT_V2_2.md` (Bruno, 29/09). Branche
> `feat/c3-amendements-v2.2`, depuis `dev` @ `8689636`. Le SHA livré est le commit qui porte ce rapport et la sortie
> de `tests/gate.sh`. **État : poussé au `1189470` après le GO du STOP 2, CI verte ; non mergé.** Le merge est une
> décision humaine.
>
> **Protocole v2.2 adopté le 2026-09-29** : `docs/protocole_c3.md`, sha256
> `1bed7696c0b0002b702f34fd549a59fc648968ff2e3056a98d33168bd643292a` ; paquet `docs/amendements_c3_v2.2.md`
> (section « Adoption »). **Aucune ligne de `scripts/audit/*.py` ni de `src/`** : les règles nouvelles de v2.2 sont
> portées par 46 tests `xfail` strict, et leur outillage est la liste close `outillage_v2_2.md`.

## 1. Ce qui est livré

| Livrable | Où |
|---|---|
| Phase 1 : classification des sorties code 1, inventaire des tests-miroirs, conformité C3b, décisions | `results/c3_v2_2/phase1.md` |
| Paquet v2.2 : douze amendements, constats de rédaction, « Vérifié, sans amendement », ordre, **Adoption** (empreintes, décisions de gate, lecture adverse, ligne Astra, réserves R-15 à R-22, écarts) | `docs/amendements_c3_v2.2.md` |
| Protocole v2.2 | `docs/protocole_c3.md` |
| Tests : jumeaux `xfail` des miroirs contredits, adverses neufs, pont levé, tests du sha généralisés | `tests/test_scripts/test_c3*.py`, `test_c3b*.py` |
| Propagation | `CLAUDE.md`, `skills/backtest.md`, `docs/RESEARCH_LOG.md` (entrée 18), `PROJECT_CONTEXT.md`, `ROADMAP.md`, `docs/CODE_MAP.md`, `results/INDEX.md` |
| Liste close du chantier outillage | `results/c3_v2_2/outillage_v2_2.md` |
| Scripts de contrôle et leurs sorties | `results/c3_v2_2/tests/` : `suite_c3.sh`, `pkg_check.sh`, `xfail_rouge.sh`, `mutant.sh`, `f8_ecart.sh`, `index_m.sh`/`.py`, `texte_conforme.py`, `apres.py`, `gate.sh`, `gate_sans_tunnel.py`, `greffon_portee.sh`, `comptes.sh`, `ci_status.sh` |

## 2. Par amendement

| AM | Section(s) | Commit | Tests | Réserve |
|---|---|---|---|---|
| — | brief suivi ; phase 1 | `3bd3365`, `cf56900` | — | — |
| paquet | PROPOSÉ ; retouches du STOP 1 (C-1 à C-6) | `82fb522`, `b8b2390` | — | — |
| AM-05 | § A.6, § L.1 l. 6, § K.1 | `451a148` | pont `xfail` du test du sha ; 5 adverses | R-17 (bloquant campagne) |
| AM-04 | § A.7 (Contrats, Comptabilité) | `608ea37` | 10 jumeaux et adverses ; (i) « lot sans amount » ; témoin « hors positions » vérifié par mutation | R-16 (bloquant manifeste) |
| AM-09 | § A.7 (couverture) | `b5aecd8` | 4 (jumeau producteur, 3 adverses d'entrée) | R-20 (non bloquant) |
| AM-10 | § A.8 D4 | `f9023ba` | 2 (`raises=OverflowError`) | R-21 (non bloquant manifeste, bloquant campagne) |
| AM-01 | § A.8 (`grid_levels`) | `302996c` | aucun (témoin : `test_grid_v4_decision_timeframes.py`) | — |
| AM-02 | § A.8 (note SOL) | `4f310ef` | aucun (témoin : `test_warmup_at.py`) | — |
| AM-06 | § C.5, § L.1, § L.2, § J 13 | `303e21d` | 5 (jumeau producteur, 4 adverses de chaîne) ; (i) témoin d'abstention `continuite=-` | R-18 (bloquant manifeste) |
| AM-11 | § F.8 | `6bbb262` | aucun ; mesure `f8_ecart.sh` | — |
| AM-08 | § L.1, § B.8 (« Ce qu'exige `validé` ») | `8509d9e` | 6 (2 jumeaux producteur, 1 continuité, 3 verdict) ; (i) 2 docstrings | R-19 (bloquant manifeste) |
| AM-03 | § L.2, § L.1 l. 0, § F.2 d, § J 12, § 0.7 | `269a1ce` | 9 (7 adverses de chaîne sur un monde v2.2 cohérent, jumeau du parseur, jumeau producteur) | R-15 (bloquant manifeste) |
| — | cas 1 à 4 (aucun texte) ; item producteur hors réserve | `5600eaf` | 4 + 1 | R-22 ; hors réserve |
| AM-12 | § M | `5d98a2e` | `index_m.sh` (méthode validée sur l'index v2.1) | — |
| AM-00 | en-tête, « Amendements — v2.2 » | `ac7710f` | — (texte figé ; sha v2.2) | — |
| Adoption | section « Adoption » du paquet | `ff77c60` | — | — |
| tests du sha | généralisés, pont levé | `db8dd65` | 2 tests, vérifiés par 3 mutants | — |
| propagation | sept fichiers | `e47963e` | — | — |
| outillage | liste close | `d9c4aa3` | — | — |

Le texte appliqué est le texte du paquet, figé au STOP 1 (`b8b2390`). Les blocs « Après » sont copiés depuis le
paquet par extraction (`tests/apres.py`, cité au commit d'AM-06). `tests/texte_conforme.py` retrouve dans le
protocole les 23 blocs « Après » du paquet, à la mise en page près. Ce contrôle mord : un mutant d'un mot sort en
ABSENT (défaut 6 du § 7).

## 3. Tests

- **Livré** (`tests/suite_c3.out`, suites C3 et C3b) : 1 149 passés, 46 `xfail` strict. Le détail, par
  identifiant, est au § 4.2.
  - Cinq cas paramétrés `min_order_usdc` sont retirés : `MANDATORY` de l'ancrage ×2, `MANDATORY` de l'entrée ×2,
    D5 ×1. Leur attendu v2.2 vit dans les jumeaux R-16.
  - L'ancien refus « aucune unité couverte » du producteur est remplacé par son jumeau R-20.
  - Trois tests sont renommés à la scission ou à la généralisation : le test du sha v2.1 devient « le dernier
    sha », et les deux tests verts du producteur scindés (comparateur non constructible, zéro trade) sont renommés.
  - Un témoin vert est ajouté : le suffixe de monnaie hors des positions nommées (AM-04).
  - Le pont est levé.
- **Décompte des `xfail`** : R-15 9, R-16 10, R-17 5, R-18 5, R-19 6, R-20 4, R-21 2, R-22 4, hors réserve 1.
- **Rouges pour la bonne raison.** `tests/xfail_rouge.out` relance chaque lot en `--runxfail` et consigne l'exception
  et la ligne d'échec. `raises=` est fixé sur l'exception constatée :
  - `AssertionError` là où le code rend le mauvais résultat ;
  - `ValueError` pour trois cas R-22 (écriture ou lecture JSON stricte d'un non-fini) ;
  - `OverflowError` là où `math.exp` déborde (R-21 ×2, hors réserve ×1).
- **Scission plutôt que perte de couverture.** Seules les assertions que v2.2 contredit passent dans un jumeau
  `xfail` ; le reste du test d'origine reste vert.
- **Vérifications par mutation** (`tests/mutants.log`), toutes avec rouge sous mutant, restauration et diff vide :
  - le témoin AM-04 « suffixe hors positions ni lu ni refusé », contre une garde non bornée ;
  - le test du sha, contre un octet ajouté au protocole ;
  - les deux tests du sha, contre une empreinte v2.2 altérée dans la table (ensemble, puis le second seul).
- **Monde v2.2 cohérent (R-15).** `_v22_world` tire `returns_config` de `equity_daily` par la formule du texte,
  écrite côté test. Sa base ne porte aucune violation aujourd'hui (`inconclusif (F_CANNOT_SEPARATE)`, contrôle
  consigné au commit) : chaque adverse échoue donc pour sa seule raison.

## 4. La porte (`tests/gate.sh`)

Sortie : `tests/gate.out`, second passage, 2026-09-29T10:00:01Z, `rc=0`. Le premier passage est au défaut 9 du § 7.

- **Portée.** La porte a tourné à `d9c4aa3`, avec pour seuls fichiers hors commit ses propres fichiers et ce rapport.
  Le commit qui les porte ajoute en plus une retouche ruff de trois scripts de contrôle (défaut 10 du § 7). Il n'y a
  ni code, ni test, ni texte du protocole.
- **L'en-tête « 1 fichier suivi modifié ».** C'est `tests/index_m.out` : la porte relance `index_m.sh`, qui réécrit
  son en-tête (horodatage, HEAD). Son contenu est inchangé, et il est committé avec la porte.

| Critère du brief | Clé de `gate.out` | Résultat |
|---|---|---|
| sha à trois voies (fichier = dernière ligne d'Adoption = `cc.protocol_descriptor`) | `sha_trois_voies` | 0 : `1bed7696…292a` |
| suite complète verte au sens CI | `suite_verte`, `zero_echec_zero_xpass` | 0 : 3 246 passés, 46 `xfailed`, 19 ignorés, 24 désélectionnés (`_full`) ; 0 FAILED, 0 ERROR, 0 XPASS. **Écart 2** (§ 4.1) : 13 tests base ignorés |
| `xfail` strict comptés et listés avec leur R | `xfail_egaux_a_la_liste` | 0 : 46 = 46 de `outillage_v2_2.md`, chaque `xfail` listé avec sa raison |
| ruff propre | `ruff` | 0 (`src/` et liste C3 de la CI) |
| `mypy src/` = 65 | `mypy_src_65` | 0 : 65 erreurs dans 18 fichiers |
| hashes gold intacts | `gold_fichier_et_moteur_inchanges_depuis_8689636` | **Écart 1** (§ 4.1) : gold non rejoué ; 0 au sens de la clé (test gold, `src/`, `scripts/backtest.py` inchangés depuis `8689636`) |
| diff de contrôle vide (moteur, runners, `c3*.py`, config, livrables C3a/C3b, CONTRAINTES) | `diff_vide_chemins_geles` | 0 |
| `git diff --stat 8689636 HEAD -- src scripts/audit/*.py` vide | `diff_src_scripts_audit` | 0 ligne |
| tout fichier changé est dans la liste close | `fichiers_dans_liste_close` | 0 (37 fichiers) |
| manifeste historique C3a intact et toujours refusé | `livrable_c3a_refuse_sous_v22` | 0 : 2 passés, fichiers inchangés |
| § B.8 inchangé (précision 2) | `miroir_B8_identique_et_vert` | 0 : la fonction est identique à `8689636` et verte |
| paquet complet | `paquet_complet` | 0 |
| `phase1.md` et `outillage_v2_2.md` committés | `livrables_suivis` | 0 |
| texte appliqué = paquet | `texte_applique_egal_paquet` | 0 : 23 blocs, 0 absent |
| index § M régénéré | `index_M_regenere` | 0 |
| branche poussée, CI lue avec `gh`, verte | `tests/ci_status.out` | 0 : run 36559243970 sur `1189470`, `success` à la première tentative, aucune relance. Résumé pytest de la CI (`gh run view 36559243970 --log`) : 3 246 passés, 43 ignorés (les 19 de la porte, plus les 24 `_full`, que la CI ne désélectionne pas et qui s'y ignorent sans base), 46 `xfailed` |

### 4.1 Écarts à la porte

La porte passe avec deux critères qui ne sont pas tenus dans la forme du brief et du plan. Ils sont acceptés par
Bruno au STOP 2, et consignés ici comme écarts.

**Le fait qui couvre les deux** : `git diff 8689636 HEAD -- src scripts/audit/*.py` est **vide** (`gate.out`,
`diff_src_scripts_audit=0`). `scripts/backtest.py`, les runners et `config` le sont aussi
(`diff_vide_chemins_geles=0`). Entre la clôture C3b (`fe82fe5`) et `8689636`, `tests`, `src` et `scripts` n'ont pas
changé. Aucun test lié à la base n'a donc pu changer de comportement depuis la dernière suite qui les a exécutés.
Ce chantier n'a rien écrit dans la base.

| # | Écart | Ce que disent le brief et le plan | Ce qui est livré | Ce qui le couvre |
|---|---|---|---|---|
| 1 | gold non rejoué | brief : « hashes gold intacts » ; plan, critère 4 : « gold inchangé depuis `8689636`, 2 passés » | le test gold est lié à la base et s'ignore sans tunnel. La clé de la porte ne vérifie que l'absence de diff sur le test, `src/` et `scripts/backtest.py` depuis `8689636` | le fait ci-dessus, plus le gold 2/2 à la clôture C3b (`results/c3b_producteur/closure/tests/mypy_gold.out`, `gold_2_passed=0`) |
| 2 | 13 tests base ignorés | brief : « suite verte au sens CI » ; plan, critère 2 : « suite complète », « sans ouvrir de tunnel » | le tunnel 5433 était **ouvert** au lancement, et pas par ce chantier. Le greffon `gate_sans_tunnel.py`, un moyen hors plan, refuse à pytest les ports 5432 et 5433. Résultat : 13 tests base ignorés, en plus des 6 d'intégration Bybit que la CI ignore aussi | le fait ci-dessus, plus la clôture C3b, où ces 13 tests passaient (`suite_locale.out`, tunnel ouvert). La réconciliation du § 4.2 montre que ce sont exactement eux qui manquent |

Les ignorés, lus dans `gate.out` :

| Raison | Nombre |
|---|---|
| base injoignable : gold, déterminisme P6, fidélité C2, rejeu (couverture, benchmark, clamp) | 13 |
| intégration Bybit (`BYBIT_INTEGRATION`), ignorés à la clôture C3b et en CI aussi | 6 |

### 4.2 Réconciliation des comptes

Script `tests/comptes.sh`, sortie `tests/comptes.out`, `rc=0`.
- **Méthode.** Collecte seule des identifiants de tests, à `8689636` (worktree temporaire hors du dépôt, retiré) et à
  HEAD, avec la commande de la porte et le greffon des deux côtés.
- **Collectes cohérentes.** Celle de la base vaut 3 270, soit les 3 264 passés et 6 ignorés de la clôture. Celle de
  HEAD vaut 3 311, soit les 3 246 passés, 19 ignorés et 46 `xfail` de la porte.

**3 264** (clôture C3b) **− 13** (tests base, ignorés sans tunnel) **− 9** (identifiants retirés) **+ 4** (verts
neufs) **= 3 246** ; la porte en compte 3 246. Les 46 `xfail` sont tous des identifiants neufs.

- **Les 9 retirés :**
  - 5 cas paramétrés `min_order_usdc` (ancrage ×2, entrée ×2, D5 ×1), dont l'attendu v2.2 est dans des jumeaux
    R-16 ;
  - l'ancien refus R-20 du producteur, dont l'attendu est dans son jumeau ;
  - 3 tests renommés : `test_le_sha_v21_…`, `test_a_non_buildable_comparator_is_2_before_the_engine`,
    `test_no_trade_writes_a_null_first_fill_at_that_the_chain_refuses`.
- **Les 4 verts neufs :**
  - ces 3 renommés (`test_le_dernier_sha_…`, `…_stops_before_the_engine`, `…_null_first_fill_at`) ;
  - le témoin d'AM-04.
- Aucun test n'a disparu en route. Le seul changement net est −6 + 1 : les six attendus v2.1 passés dans des
  jumeaux `xfail`, et le témoin neuf.

### 4.3 Portée du greffon

Script `tests/greffon_portee.sh`, sortie `tests/greffon_portee.out`, `rc=0`. Le greffon vit en
`results/c3_v2_2/tests/gate_sans_tunnel.py`. Il est chargé **seulement** par `gate.sh`, qui passe `-p gate_sans_tunnel`
et ajoute son répertoire au `PYTHONPATH`.
- Aucun fichier suivi hors de `results/c3_v2_2/` ne le nomme. Il est absent de `pyproject.toml`
  (`[tool.pytest.ini_options]`), de `tests/conftest.py` et de `.github/`.
- Une invocation pytest ordinaire ne l'enregistre pas (`--trace-config`). Le témoin l'enregistre sous `-p` et le
  `PYTHONPATH` de `gate.sh`, ce qui prouve que l'observation le verrait.
- Il n'est pas importable depuis la racine du dépôt sans ce `PYTHONPATH`.
- pytest ne le collecte pas, même lancé sur son répertoire (`python_files = ["test_*.py"]`, `testpaths = ["tests"]`).

Les tests base locaux de tout autre usage s'exécutent donc comme avant, tunnel ouvert.

## 5. Conformité des artefacts C3b sous v2.2

Tous sont historiques v2.1 : sous v2.2, l'ancrage refuse le manifeste du lot 3, comme il refuse le livrable C3a
(v2.0). Par réserve, les artefacts rendus non conformes sont dans la section « Adoption » du paquet.

**C-2, la remarque de Bruno au STOP 1.** Elle demandait si c3 rend `NON VÉRIFIABLE` sur un bloc vide. Réponse
lue dans le code **[v]** : non. `cc.liquidation_identities` ne met `lots_present` à faux que si la clé `lots` est
**absente** (`c3_common.py:2014-2016`). La branche `NOT_VERIFIABLE` de c3 n'est prise que dans ce cas
(`c3_continuity.py:201`). Une liste exportée et vide (`lots: []`, `trades == 0`, état sans trade exact) sort donc
`VERIFIED`. L'item R-19 reste donc « admettre `first_fill_at` nul avec son porteur » ; il
n'y a pas d'item « c3 à vide ». Ce constat est écrit dans l'Adoption (table de gate, C-2) et dans
`outillage_v2_2.md` (R-19).

Une correction à `phase1.md` § 4. AM-08 ne cassait rien tant qu'il n'était qu'un élargissement. Mais le porteur
`metrics.executions`, exigé depuis la décision 8 et la retouche C-6, manque à toutes les évaluations existantes. Il
en va de même des λ déclarés (AM-03).

## 6. Limites

- **Interface des `xfail`.** Les noms de clés, l'option `--candles-eval` et les entrées du dictionnaire d'artefacts
  du verdict sont indicatifs ; l'attendu ne l'est pas. Les quatre adverses de chaîne R-18 rougissent aujourd'hui sur
  l'option inconnue, avant d'atteindre leur attendu.
- **AM-10 est testé au niveau des fonctions**, avec une durée de préfixe réduite. Le débordement du CAGR sur des
  rendements finis n'existe pas sur le préfixe des fixtures (767 j) : il exige moins de ~361 j. Aucun monde à
  fenêtre courte n'a été construit.
- **Pas de tunnel.** Voir les écarts 1 et 2 du § 4.1.
- **Les 24 `_full`** sont désélectionnés, comme à chaque chantier ; § L.5 ne s'applique pas à un chantier sans code.

## 7. Défauts et constats (hors table)

**Constats à porter plus loin**
- **CONTRAINTES § 10 contre la ligne Astra** (précision 3 du GO de phase 2). `docs/CONTRAINTES_POST_B4.md` § 10 dit que
  le critère d'arrêt « est appliqué par les deux revues (Astra, Claude) et par Bruno ». La ligne Astra de la section
  « Adoption » de v2.2 dit : « Re-passe Astra non faite (Astra non à jour depuis v2.0 ; réservée aux familles de
  stratégies) ». Pour une révision du protocole, une des deux revues nommées par CONTRAINTES est donc hors circuit.
  L'incohérence n'est pas corrigée ici, puisque CONTRAINTES n'est pas dans la liste close ; elle est consignée pour
  ne pas être redécouverte au manifeste.
- **Producteur** : `cb.build_pair` hors du `try` à `c3b_evaluate.py:544`. C'est un item d'outillage hors réserve,
  avec un `xfail`.
- **Candidats v2.3** (constats de rédaction 7 et 8 du paquet) :
  - « Cette liste est exactement ce que D5 asserte » (§ A.6) est inexact ;
  - le § A.7 énonce les contrats de forme `_base` et `_quote` pour la projection du préfixe ; l'outillage les
    applique aussi au bloc de liquidation de l'évaluation, mais le texte ne le dit pas.
- **Nom de test périmé**, laissé inchangé comme le veut le brief :
  `test_le_livrable_reel_de_C3a_reste_l_historique_v20_et_n_est_pas_rejouable_sous_v21`.

**Défauts du chantier**, dits comme tels :
1. **Rôles inversés dans mon plan de phase 2.** J'ai d'abord écrit que la lecture adverse était celle de Bruno ;
   elle est celle du relecteur (Claude), et Bruno adopte. Corrigé au plan avant toute écriture, sur la remarque de
   Bruno.
2. **Trois phrases de gate impossibles à appliquer mot pour mot** :
   - C-2 : « sans lot » contredisait la ligne c3 du § B.8 ;
   - C-4 : « blend » est faux pour λ < 1 ;
   - C-5 : la phrase disait qu'aucune clause n'est évaluée, alors que l'abstention en évalue.
    Je les ai soumises par question plutôt que de les réécrire
   seul ; les trois rédactions ont été décidées au STOP.
3. **Prévision fausse de l'index dans le paquet (AM-12).** Voici l'index réel :
   - `E_NO_BENCHMARK` ne gagne que § J, parce que la retouche C-3 l'a retiré du § L.2 ;
   - `D4` ne change pas ;
   - `P2` gagne § F.8 ;
   - `R1_NOT_NORMALISED` gagne § L.1.

   L'écart est consigné dans l'Adoption, et c'est la sortie du script qui fait foi.
4. **`phase1.md` § 4 disait qu'AM-08 ne cassait rien.** Ce n'est plus vrai depuis que le porteur est exigé (§ 5
   ci-dessus).
5. **Citations `fichier:ligne` décalées** d'une à trois lignes :
   - `c3_benchmark.py` 88-93 → 91-95 ;
   - 1089-1119 → 1089-1118 ;
   - 3325 → 3326 ;
   - 1880 → 1881 ;
   - 645-646 → 646-647.

   Je les ai vues et corrigées moi-même, en relisant le code, avant les commits.
6. **Shell zsh, encore.** La vérification par mutant de `texte_conforme.py` a lu `PIPESTATUS` sous zsh, qui ne le
   remplit pas : le code de sortie sous mutant n'a pas été capturé (valeur vide). La ligne ABSENT imprimée prouve le
   rouge, mais le code manque. C'est la classe d'incident que la règle « vérification par script bash » du brief
   devait exclure : cette vérification-là a été faite en ligne de commande. La porte et tous les scripts committés
   tournent sous bash.
7. **Expression `-k` trop large dans un relevé.** `R22 or hors_R` a aussi attrapé deux tests R-15 déjà consignés
   (« hors_regle »). C'est sans effet, et c'est dit au commit `5600eaf`.
8. **Tunnel trouvé ouvert à la porte**, ouvert hors de ce chantier. Je ne l'ai pas fermé : il n'est pas à moi. Je l'ai
   neutralisé pour le seul processus pytest par un greffon qui refuse les connexions à 5432 et 5433. C'est un moyen
   neuf, qui n'était pas au plan ; il est dit ici, dans `gate.out`, et consigné comme écart 2 (§ 4.1). Sa portée
   est vérifiée au § 4.3.
9. **Premier passage de la porte rouge sur son propre parseur** (09:56Z, `rc=1`). Tous les autres critères valaient
   0, pytest compris (0 échec, 0 XPASS, 46 `xfailed`). Seule la comparaison des `xfail` avec la liste de l'outillage
   échouait. La cause est la regex de `gate.sh` : `\S+` coupait l'id paramétré à son espace (`[estampille …]`),
   le crochet fermant manquait, et l'id n'était pas ramené au nom du test. Les deux cas R-15 paramétrés sortaient
   donc hors liste, et leur nom de base manquant.
   - Correctif : le parseur coupe au premier crochet ; une branche morte est retirée au passage.
   - La porte est relancée entière. Le `gate.out` committé est le second passage.
10. **Lint de mes scripts de contrôle.** `ruff check .` sur le dépôt entier trouvait deux `I001` (imports), dans
    `tests/index_m.py` et `tests/texte_conforme.py`, et `ruff format` reformatait `tests/apres.py`. La liste ruff de
    la CI ne lit pas `results/`, mais la règle d'or 10 (ruff vert) vaut pour tout commit. Les deux `I001` étaient
    les seules erreurs de `ruff check .` sur tout le dépôt.
    - Correctif, dans le commit de la porte : tri des imports et une ligne reformatée, sans effet sur le
      comportement.
    - Vérification : `texte_conforme.py` (code 0) et `index_m.sh` (code 0, sortie identique hors en-tête) ont été
      relancés après la retouche, et `ruff check .` passe.
    - Après la retouche, `ruff format --check .` reformaterait encore 12 fichiers. Aucun n'est touché par un commit
      de ce chantier depuis `8689636`.

## 8. Pour la suite

- **Push fait** (GO de Bruno au STOP 2) : `feat/c3-amendements-v2.2` poussée au `1189470`, CI verte sans relance
  (`tests/ci_status.out`). La règle de relance (le seul flaky `test_rejeu_effect`, tout autre rouge est un STOP) est
  écrite dans `tests/ci_status.sh`. Pas de merge.
- **Serveur** : rien à tirer. Aucun code n'a changé, et le collector ne verra pas la différence.
- **Merge sur `dev`** : décision humaine. `docs/CODE_MAP.md` se régénère au merge.
- **Chantier outillage v2.2** : `outillage_v2_2.md`. D'abord les bloquants manifeste (R-15, R-16, R-18, R-19) ; puis
  R-17, R-21 et R-22 avant la première campagne comptée.
- **Manifeste de la première campagne** : au sha256 v2.2, après l'outillage.
