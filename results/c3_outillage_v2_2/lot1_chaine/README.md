# C3 — Outillage v2.2, lot 1 : chaîne pure (R-15, R-21, R-22, R-17) — rapport de lot

Brief `agent/AGENT_C3_OUTILLAGE_V2_2.md` ; liste close `results/c3_v2_2/outillage_v2_2.md` ; plan du lot approuvé le
2026-09-29 avec les conditions du relecteur relayées par Bruno : `results/c3_outillage_v2_2/plans/lot1.md` (décisions
D1 à D14). Branche `feat/c3-outillage-v2.2`, partie de `dev = 8c114fe`. Protocole v2.2, sha256
`1bed7696c0b0002b702f34fd549a59fc648968ff2e3056a98d33168bd643292a`, intouché. Aucun merge.

## 1. Livré, commit par commit

| Commit | Objet | Marqueurs levés |
|---|---|---|
| `6e9f4c0` | brief tel que reçu, plan du lot 1 | — |
| `40b1276` | **R-15 producteur** (D1) : `evaluation.json` déclare `lambdas {dd, sigma}` (les flottants mêmes de `benchmark.json`) ; `benchmark_eval.json` porte `nav`, la NAV du B&H plein notionnel passée en double | 1 |
| `1f96cde` | **R-15 chaîne** : quatre entrées de plus au verdict (manifeste, `benchmark.json`, `candles_eval.json`, comparateur d'évaluation) ; recalcul au bit de `returns_config` sur `equity_daily`, de la NAV du B&H sur l'export (C-4), des `λ` et de `returns_bench` ; règle d'entrée de l'export (code 2) ; recalcul impossible sur une évaluation non refusée → violation (C-3) ; contrat de couche (D2), abstention sans `λ` publié (D3), parseurs (D4), fichiers re-hachés hors `chain.checks` (D5), `--candles-eval` (D11) ; test neuf A1 | 8 + 1 (XPASS D12a) |
| `a538d22` | **R-21** : `cc.cagr_pct` rend `None`, jamais une exception (rendement non fini, `≤ −1`, ou débordement) ; D4 = rendements définis et tous finis, CAGR fini ; item hors réserve **caduc** (§ 4) | 2 + 1 (R-22 cas 3) |
| `ae12546` | **R-22 cas 1, 2, 4** : registre canonicalisé à la lecture (diagnostic, code 1) ; NAV du B&H du préfixe en décimal et rendements non finis non écrits (paire non comparable, code 0) ; estimabilité déclarée : non-fini → violation, seuls `E1`, `E2`, `ok` recopiés | 3 |
| `8275827` | **R-17** : famille obligatoire au manifeste ; sha du protocole asserté avant le typage (D9) ; `stop_criterion` à l'ancrage (verdict compté → seule l'empreinte différée inscrite passe ; deux non comptés → refus) ; table `COUNTED` du § 10.1 (+ ligne conditionnelle, D13) ; inscription à l'étape 6 en mode `chain`, une fois (D6) ; listes closes (D10) ; tests neufs : témoin, épinglage de la table, A2 | 5 |

Les nouvelles clés d'interface sont celles que les tests proposaient, sans renommage : `family`, `verdict {issue, raison,
compte}`, `deferred_evaluation {date, variant_key}`, `lambdas {dd, sigma}`, `--candles-eval`, entrées `benchmark`,
`candles_eval`, `benchmark_eval`. Ajout déclaré : l'entrée `manifest` du dictionnaire d'artefacts du verdict.

## 2. Tests

- **Suites** (`tests/suite_*.out`, tunnel ouvert, sans les 24 `_full`, chacune sur l'arbre committé juste après,
  sans modification entre les deux) :

  | Étape | Passés | Ignorés | Désélectionnés | xfail | Échecs / XPASS |
  |---|---|---|---|---|---|
  | base (`6e9f4c0`, code = `8c114fe`) | 3 259 | 6 | 24 | 46 | 0 |
  | C1 R-15 producteur | 3 260 | 6 | 24 | 45 | 0 |
  | C2 R-15 chaîne | 3 270 | 6 | 24 | 36 | 0 |
  | C3 R-21 | 3 273 | 6 | 24 | 33 | 0 |
  | C4 R-22 | 3 276 | 6 | 24 | 30 | 0 |
  | C5 R-17 | **3 284** | 6 | 24 | **25** | 0 |

- **Comptes** (`tests/comptes_lot1.out`, rc=0) : collectes à `8c114fe` et au tip ; retirés ∅ ; ajoutés = les quatre
  tests neufs déclarés (`tests/declares_lot1.txt`) ; levés = exactement les 21 déclarés ; xfail du tip ⊆ xfail de la
  base ; équation 3 259 + 21 + 4 = 3 284 ; le `-k` écarte exactement les 24 `test_determinism_parallel_vs_serial_full`.
- **Diff des tests** (`tests/diff_tests_lot1.out`, rc=0, par l'AST contre `8c114fe`) : corps des 43 fonctions xfail de
  la base identiques ; décorateurs : 20 fonctions démarquées (21 identifiants, un test paramétré ×2), 1 re-marquée
  (caduc) ; toute autre fonction modifiée ou neuve est dans la liste déclarée ; affectations retirées `R15` ×2, `R17`,
  `R21` ×2, ajoutée `TABLE_10_1`.
- **R-18 restés xfail** (`tests/xfail_reste.out`, rc=0) : les trois tests de chaîne échouent sur leur attendu, la chaîne
  s'arrêtant à la continuité (forme de refus pas encore admise), et plus sur l'option `--candles-eval` inconnue
  (nature constatée à `8c114fe` : `assert 2 == …`, sortie d'usage d'argparse).
- **Restent xfail (25)** : R-16 10, R-18 4 (3 de chaîne, 1 producteur), R-19 6, R-20 4, hors réserve 1 (caduc).

## 3. Mutants (`../mutants.log`, `tests/mutants_lot1.sh`, rc=0)

| # | Mutant | Témoin | Résultat |
|---|---|---|---|
| M1 | l'ancrage refuse aussi l'empreinte différée attendue | témoin R-17 | rouge, restauré, vert |
| M2 | une ligne de `COUNTED` inversée (`F_CANNOT_SEPARATE`) | épinglage § 10.1 (rouge-avant de ce test) | rouge, restauré, vert |
| M3 | `run_verdict` ne transmet pas les entrées v2.2 à `decide` | A1 | rouge, restauré, vert |
| M3b | M3, A1 exclu | fichiers du verdict et du producteur | **tué par le seul `test_R18_un_refus_qui_porte_des_series_se_contredit`** (§ 6, défaut 2) |
| M4 | la réinscription discordante n'est pas vue | A2 | rouge, restauré, vert |
| M5 | `λ` et `returns_bench` jamais recoupés (D3 généralisé) | R-15 `λ` et `returns_bench` | rouges, restauré, verts |
| M6 | sha du protocole plus asserté avant le typage (D9) | les deux tests du livrable v2.0 | rouges, restauré, verts |

Les 21 tests levés étaient rouges pour leur raison à `8c114fe` (`results/c3_v2_2/tests/xfail_rouge.out`).

## 4. Écarts à la porte du brief

| Critère du brief | Constat | Ce qui le couvre |
|---|---|---|
| « Les 20 xfail du lot levés » | **21 levés** : 20 (R-15 entier, D1 ; le « 19 » du texte du brief était faux, son « 20 / 26 » juste) + 1 XPASS | D1 ; D12a ; `comptes_lot1.out` |
| « Les 4 xfail de chaîne R-18 restent xfail » | **3** : `test_R18_un_refus_qui_porte_des_series_se_contredit` passe par la violation C-3 (export sans estampille d'entrée, évaluation vue comme non refusée) ; marqueur retiré, règle du brief | D12a ; `xfail_reste.out` pour les 3 autres |
| R-21 : `candidate_block` (`c3_benchmark.py:433`) | aucune ligne changée : `first_failed: D4` dès que `cagr_pct` est nul, déjà écrit | constaté, test R-21 vert |
| Item hors réserve | **caduc par AM-10** (décision de gate de Bruno, 29/09, option A) : sous v2.2 `cc.cagr_pct` ne lève plus ; dans le monde du test, le CAGR du B&H plein notionnel déborde (exposant 799,9 > 709,78) sans entrer dans l'évaluation, les blends aux `λ` du préfixe restent finis (644,9 et 705,2) : code 0, l'attendu code 3 est inatteignable sans convention. Le test reste xfail, re-marqué `raises=AssertionError`, raison mise à jour, assertions intactes. La porte du chantier devient **45 levés + 1 caduc déclaré**. | décision de gate ; `diff_tests_lot1.out` (re-marquage déclaré) |
| Diff des tests : marqueurs, interface, fixtures, rien d'autre | quatre tests verts modifiés, déclarés : parseur de l'étape 6 (D4), épinglage des listes closes (D10), argv de la chaîne complète du producteur (D11), et l'aide `continuity` du producteur (NAV du comparateur synthétique) ; fixtures `fx.manifest` (famille), `fx.evaluation`, `fx.benchmark_eval`, `_artifacts`, `_reseries`, `_write_cli_inputs`, `_chain_world`, `_chain_argv`, `_v22_world` ; tests neufs A1 et A2 (D8), témoin et épinglage | `diff_tests_lot1.out` |

## 5. Écarts à la liste close, candidats v2.3, obligations au lot 2

**Écarts à la liste close** (déclarés, jamais arbitrés) :
- R-15 : les liens d'empreinte vivent dans `verify_producer_inputs`, appelée par `run_verdict` juste après
  `verify_chain`, pas dans `verify_chain` même (D5) : les fichiers fournis sont **re-hachés** (`cc.check_inputs_match`)
  contre l'empreinte de leur consommateur amont — manifeste / `anchor`, `benchmark.json` / `selection`, comparateur /
  `continuity` ; `candles_eval.json`, sans amont, est haché dans `verdict.inputs_sha256` et son contenu rejoué.
- R-15 producteur livré au lot 1 et non au lot 2 (D1).
- R-17 : l'inscription de l'évaluation différée n'est pas implémentée (D7).

**Candidats v2.3** (consignés, rien d'implémenté « en convention ») :
- **D7 — prérequis probable v2.3 avant campagne** : le texte ne dit pas d'où `c3_verdict` tire la date déclarée et le
  manifeste attendu de l'évaluation différée. Conséquence : une famille close par une issue qui ouvre la voie de sortie
  prospective du § 10.1 refuse tout, évaluation différée comprise. Si l'issue `inconclusif` attendue de la première
  campagne ouvre cette voie (à vérifier au texte du § 10.1), D7 ferme exactement ce chemin : mini-amendement à trancher
  en conversation manifeste, avant la campagne.
- D3 : abstention où l'étape 3 n'a publié aucun `λ` pour la configuration évaluée — de quelle configuration est
  l'évaluation en abstention, et quels recoupements s'y appliquent.
- D6 : l'inscription au registre à l'étape 6 hors `chain` (le verdict seul ne porte pas de registre).
- D14 : les sorties code 1 et 2 ne laissent aucune trace au registre ; un run en violation n'entre pas dans la relance
  unique — trou dans l'application du « zéro retry », couvert par la discipline, pas par le registre.

**Branches sans adverse dédié** (règles écrites, dites) : présence partielle des entrées v2.2 dans `decide` (erreur
d'entrée) ; configuration retenue sans `λ` publié à l'étape 3 (violation — inatteignable par une chaîne cohérente,
`c3_select` n'admet que des estimables).

**Obligations transmises au lot 2** :
1. Item hors réserve : `cb.build_pair` dans le `try` de l'étape 10b, **et** un adverse neuf qui force une vraie
   exception dans `build_pair` → code 3, en remplacement du test caduc (décision de gate du 29/09).
2. `test_R18_un_refus_qui_porte_des_series_se_contredit` est nommé au plan du lot 2 comme test vert que la route R-18
   fera passer par l'admission du refus ; s'il rougit, règle d'arrêt. Tant qu'il passe par C-3, il garde aussi M3 (M3b).
3. Branche morte `except OverflowError` de `c3b_evaluate.evaluation_series` (plus rien ne lève depuis R-21).
4. Les listes closes et leur épinglage suivent R-19 et R-20 (`first_fill_at` nullable, dates de couverture).

## 6. Défauts du lot, dits comme tels

1. **Prédiction D12b fausse.** J'avais prédit que l'item hors réserve passerait en XPASS au commit R-21 (le CAGR non
   fini du comparateur repris par `replay_bootstrap`, code 3). Il a rendu code 0 : le CAGR qui déborde est celui du
   B&H plein notionnel, que l'évaluation n'utilise pas ; les blends restent finis. La règle d'arrêt du plan a joué :
   patch mis de côté, arbre remis à C2, décision demandée, reprise sur l'option A.
2. **Prédiction D8 partiellement fausse.** J'avais écrit que, sans A1, le mutant M3 survivrait à toute la suite. C'était
   vrai au plan ; depuis D12a, le test R-18 « refus avec séries », qui passe par C-3 en chaîne, le tue aussi (M3b). A1
   reste le garde durable : ce test changera de route au lot 2.
3. **Mes scripts de preuve, d'abord faux.** `xfail_reste.sh` a d'abord compté les occurrences de « CHAINE ARRETEE » au
   lieu des tests (5 pour 3, rc=1 sur mon script), puis manqué les en-têtes de section des noms longs (`_{5,}` au lieu
   de `_+`) ; corrigé avant de consigner. `comptes.sh` a porté un contrôle factice (`… or True`), retiré avant tout run.
   `mutants_lot1.sh` attendait la survie de M3b ; réécrit en constat vérifié (qui le tue).
4. **Patch C4 appliqué à moitié** : ancre non unique (`to_dict`, deux classes) dans `c3_benchmark.py` ; le fichier
   `c3_anchor.py` était déjà écrit. Repris en ciblant l'ancre ; aucun effet hors de l'arbre de travail.
5. **Fixture `nav` par défaut trop étroite** : `fx.benchmark_eval` ne sait construire la NAV que pour les paires du monde
   de `fx` ; l'aide `continuity` du producteur (paire USDT) a levé `KeyError`. Corrigé en lui passant la NAV que le
   producteur a exportée (déclaré).
6. **Sonde temporaire dans `tests/`** : pour établir le constat D12b, j'ai copié une sonde non suivie dans
   `tests/test_scripts/`, lancée puis retirée (état final vérifié : `git status` propre hors `results/`) ; sa première
   exécution a buté sur la garde d'arbre non propre faute de la fixture hermétique du module.

## 7. Tunnel et base

Tunnel `127.0.0.1:5433` ouvert à 15:10:39Z pour les 13 tests base de la suite existante (lecture seule, aucun test base
ajouté ni modifié par ce lot), fermé à 16:38:06Z, vérifié fermé (`nc -z` échoue) — `tests/tunnel.out`. Aucune
migration. Lint et typage (`tests/lint_lot1.out`, rc=0) : ruff (liste CI et dépôt) vert, `mypy src/` = 65, mypy strict
des `scripts/audit/` touchés sans écart neuf (base `lint_base.out` : `c3_common` 4, `c3_benchmark` 2, préexistantes).
Interdits (`tests/interdits_lot1.out`, rc=0) : diff vide contre `8c114fe` sur `src/`, `scripts/backtest.py`, runners
P6/P7, `rejeu_common.py`, le protocole, les paquets d'amendements, `results/c3_v2_2/`, `results/c3b_producteur/`.

CI : lue après le push de ce commit, consignée au suivant.
