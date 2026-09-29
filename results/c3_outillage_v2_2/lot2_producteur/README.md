# C3 — Outillage v2.2, lot 2 : producteur et réserves mixtes (R-16, R-18, R-19, R-20, hors réserve) — rapport de lot

Brief `agent/AGENT_C3_OUTILLAGE_V2_2.md` ; liste close `results/c3_v2_2/outillage_v2_2.md` ; plan du lot approuvé le
2026-09-29 avec le GO de Bruno : `results/c3_outillage_v2_2/plans/lot2.md` (décisions D1 à D12). Branche
`feat/c3-outillage-v2.2`, partie du tip du lot 1 `8d2ef60`. Protocole v2.2, sha256
`1bed7696c0b0002b702f34fd549a59fc648968ff2e3056a98d33168bd643292a`, intouché. Aucun merge.

## 1. Livré, commit par commit

| Commit | Objet | Marqueurs levés |
|---|---|---|
| `e722901` | plan du lot 2 (GO inclus) ; `lint.sh` étendu à `c3_entry`, `c3_continuity`, `c3b_common`, base mypy strict mesurée à `8c114fe` dans un worktree (`lint_base_lot2.sh` / `.out`) | — |
| `93b983e` | **R-16** : clés `_quote` aux positions nommées. Export : `gross_usdc` du moteur renommé `gross_quote` (table de renommage), lots `gross_quote`, observation `min_order_quote` ; argument moteur `min_order_usdc=` inchangé. Lecture : manifeste `min_order_quote`, liste blanche de π_T, `liquidation_identities`, `c3_entry`, `c3_select`. Garde `cc.check_quote_amount_keys`, bornée aux deux positions nommées (D11) | 10 |
| `5ea08ac` | **R-18** : forme de refus du comparateur non constructible. Le producteur écrit `evaluation.json` sous forme de refus, `candles_eval.json` et la provenance, code 0, moteur jamais construit (D3). La chaîne admet la forme sans porteurs, choisit la route sur la présence du bloc (D5), recoupe l'identité à la retenue avant de lire le bloc (C-1 ; abstention → R0, D6), n'évalue aucune clause (`refused_route`), rejoue la non-constructibilité sur l'export, publie `inconclusif`, `continuite=-`, `motif` / `motif_detail` (D7). `--benchmark-eval` facultatif (D4). Test vert modifié : D1 | 4 |
| `5d41fb2` | **R-19** : `metrics.executions` (remplissages de `engine.metrics.trades`) exporté et exigé ; `first_fill_at` présent, nul admis ; recoupements au verdict : nul ⟺ zéro exécution, zéro exécution ⟹ equity constante égale à `C` (D9) ; c5 `NON VÉRIFIABLE` admis ssi `first_fill_at` nul. Fixtures : D8 | 6 |
| `1517424` | **R-20** : dates de couverture nulles ssi aucune unité couverte ; le producteur écrit la série au lieu du refus `coverage_no_covered_unit` ; la contradiction est une violation, rendue à part des problèmes de couverture (D10) | 4 |
| `8ff96a5` | **hors réserve** : la construction du comparateur d'évaluation en échec sort en `comparator_failed`, code 3, à son site avant le moteur (D2) ; adverse neuf, le test caduc garde son marqueur | — |
| `c566b33` | branche morte `except OverflowError` d'`evaluation_series` retirée (obligation c, D12) | — |

Noms d'interface gardés tels que les tests les proposaient : `refused {reason, window, motif}`, `motif`,
`metrics.executions`, `gross_quote`, `min_order_quote`. **Ajouts déclarés** : `motif_detail` (verdict et diagnostic),
`refused_route` (continuité, route du refus), `--benchmark-eval` facultatif au parseur de `c3_continuity`, du verdict
et de `chain` (exigé sur la route exécutée), `Manifest.min_order_quote` (ex-`min_order_usdc`), constantes
`cc.REFUSAL_REASONS`, `cc.BENCHMARK_MOTIFS`, `cc.EVALUATION_SERIES`, fonctions `cc.is_refusal_form`,
`cc.refusal_series_carried`, `cc.execution_recoupements`, `cc.check_quote_amount_keys`.

## 2. Tests

- **Suites** (`tests/suite_L2C*.out`, tunnel ouvert, sans les 24 `_full`, chacune sur l'arbre committé juste après,
  sans modification entre les deux) :

  | Étape | Passés | Ignorés | Désélectionnés | xfail | Échecs / XPASS |
  |---|---|---|---|---|---|
  | tip du lot 1 (`8d2ef60`) | 3 284 | 6 | 24 | 25 | 0 |
  | C1 R-16 | 3 297 | 6 | 24 | 15 | 0 |
  | C2 R-18 | 3 307 | 6 | 24 | 11 | 0 |
  | C3 R-19 | 3 317 | 6 | 24 | 5 | 0 |
  | C4 R-20 | 3 322 | 6 | 24 | 1 | 0 |
  | C5 hors réserve | 3 323 | 6 | 24 | 1 | 0 |
  | C6 branche morte | **3 323** | 6 | 24 | **1** | 0 |

- **Comptes** (`tests/comptes_lot2.out`, rc=0, déclarations cumulées contre `8c114fe` : `tests/declares_lot2.txt`) :
  retirés ∅ ; ajoutés = les 19 neufs déclarés (4 au lot 1, 15 au lot 2) ; levés = exactement les 45 déclarés (21 + 24) ;
  xfail du tip ⊆ xfail de la base ; équation **3 259 + 45 + 19 = 3 323** ; le `-k` écarte exactement les 24 `_full`.
- **Xfail en fin de lot** (`tests/xfail_fin.out`, rc=0) : le seul XFAIL de la suite finale est le test caduc
  `test_hors_R_a_comparator_cagr_overflow_is_a_control_error_3`.
- **Diff des tests** (`tests/diff_tests_lot2.out`, rc=0, par l'AST contre `8c114fe`) : corps des 46 tests xfail de la
  base identiques ; décorateurs : marqueurs retirés, le caduc re-marqué (lot 1) ; tout autre changement déclaré (§ 4).
- **Route du test « refus avec séries »** (`tests/route_r18.out`, rc=0, obligation b) : il passe désormais par
  l'admission de la forme de refus — violation « refus + séries » à la continuité, chaîne arrêtée à l'étape 5 en code 1,
  aucune violation C-3 au verdict.

## 3. Mutants (`../mutants.log`, `tests/mutants_lot2.sh`, rc=0 ; plus L2M17, lancé seul après)

| # | Mutant | Test qui le tue |
|---|---|---|
| M1-M6 | les six mutants du lot 1, **rejoués au tip du lot 2** (ancres inchangées) | leurs témoins du lot 1 — tous rouges, restaurés, verts |
| M3 rejoué | `run_verdict` ne transmet pas les entrées v2.2 à `decide` | **A1**, et trois tests R-18 de chaîne (la route du refus exige manifeste et export) ; le test « refus avec séries » n'en est plus (obligation e) |
| L2M1 | garde R-16 non bornée (toute clé de premier niveau `_usdc` / `_usdt`) | témoin « suffixe hors positions nommées » |
| L2M2 | garde des lots retirée à l'entrée | T1 |
| L2M3 | garde retirée de `liquidation_identities` | T2 |
| L2M3b | garde retirée du bloc à l'export | T3 |
| L2M4 | bloc `refused` lu avant l'identité (C-1) | T6 |
| L2M5 | rejeu de la non-constructibilité retiré | `test_R18_un_refus_que_l_export_dement_est_une_violation` |
| L2M6 | motif `comparator_not_comparable` retiré | T5 |
| L2M7 | ⟺ réduit au sens « nul ⟹ zéro » | T10 |
| L2M8 | implication « zéro exécution ⟹ equity = C » retirée | T11 et T12 lancés ensemble, puis T12 relancé seul sous L2M8 : rouge (T11 seul est rouge sous L2M8b) — **constat** : le test xfail levé homologue reste vert sous ce mutant (le recalcul R-15 le voit d'abord) |
| L2M8b | implication réduite à la constance | T11 |
| L2M9 | `executions` = trades de liquidation | T13 |
| L2M10 | exemption c5 élargie à toute évaluation réelle | `test_c1_ou_c5_non_verifiable_sur_une_evaluation_reelle_est_une_violation[c5]` |
| L2M11 | contradiction des dates réduite à un sens | `test_R20_des_dates_presentes_sur_une_serie_sans_unite_couverte_sont_une_violation` |
| L2M12 | garde du comparateur retirée | T15 |
| L2M13 | comparateur d'évaluation non exigé sur la route exécutée | T8 |
| L2M14 | une entrée de `BENCHMARK_MOTIFS` changée | T4 (épinglage recopié du § C.5) |
| L2M15 | `--benchmark-eval` requis au parseur `chain` | T7 |
| L2M16 | forme de refus rendue en refus 2 | T9 |
| L2M17 | l'entrée exige de nouveau des dates non nulles | T14 |

Les 24 tests levés étaient rouges pour leur raison à `8c114fe` (`results/c3_v2_2/tests/xfail_rouge.out`). Chaque test neuf
est prouvé par son mutant (colonne de droite).

## 4. Écarts à la porte du brief

| Critère du brief | Constat | Ce qui le couvre |
|---|---|---|
| « 0 xfail dans toute la suite » | **0 xfail hors le caduc déclaré** : 45 levés sur 46, le test hors réserve reste xfail (caduc par AM-10, décision de gate du 29/09, lot 1) ; il est remplacé par T15 | `xfail_fin.out` ; D2 |
| Item hors réserve : « `cb.build_pair` dans le `try` de l'étape 10b » | garde **à son site**, avant le moteur, même contrat que 10b (code 3, trace sur stderr, rien d'écrit) : dans 10b, le moteur tournerait avant de savoir le comparateur constructible, contre § C.5 v2.2 et le test R-18 producteur | D2 (GO) ; L2M12 |
| Diff des tests : marqueurs, interface, fixtures, rien d'autre | tests verts et aides modifiés, déclarés : `test_a_non_buildable_comparator_stops_before_the_engine` (une ligne retirée, D1) ; `test_c3_select.py` : lambda du paramètre `Σ gross ≠ gross_usdc` (identifiant gardé) et `test_revue_R3_gross_different_de_amount_x_price_ne_passe_pas_D6` (clés, D11) ; `REAL_CARRIERS_L1` et `_carry` (le porteur, D8) ; fixtures `fx.manifest`, `fx.observation`, `fx.liquidation_segment`, `fx.evaluation` ; épinglage des listes closes (obligation d) ; tests neufs T1-T15 et l'aide `_violations_of` | `diff_tests_lot2.out` |
| Témoin R-16 vert, mutation « garde non bornée » à l'appui | vert ; L2M1 le rougit | `mutants.log` |
| `git diff 8c114fe -- scripts/backtest.py src/` vide | vide, ainsi que les autres chemins interdits | `interdits_lot2.out` |

## 5. Écarts à la liste close, candidats v2.3, report au lot 3

**Écarts à la liste close** (déclarés, décidés au GO, jamais arbitrés) :
- hors réserve : garde à son site, pas dans 10b (D2) ;
- R-19 : le témoin continuité `test_une_evaluation_reelle_sans_porteur_est_refusee_en_tete[sans first_fill_at]` ne
  « reçoit » pas le porteur. Avec `executions > 0`, § L.1 v2.2 fait de `first_fill_at` nul une violation (code 1), pas le
  refus R0 que ce témoin attend. Son monde ne déclare donc pas de compte (la fixture ne le déclare qu'avec un premier
  remplissage), et l'admission refuse en nommant `first_fill_at` et `metrics.executions` (D8). Les témoins du verdict,
  eux, le reçoivent ;
- R-19 : les recoupements vivent au verdict seul (AM-08 : « continuité ou verdict ») ; la continuité ne change que le
  libellé de c5 sans remplissage (D9) ;
- R-16 : deux tests verts de `test_c3_select.py` renommés dans leurs clés, hors de la liste des fixtures de la liste
  close (D11) ;
- R-20 : `c3b_prefix.py:395-406`, cité par le motif d'AM-09, est intouché : il rattrape `ProducerRefusal` en bloc et n'a
  rien à changer ; `reconstruct_1w.py`, autre appelant de `cc.coverage_recompute`, est intouché (il ne lit que
  `problems`), ses tests sont verts.

**Candidats v2.3** (GO du 29/09 ; consignés, rien d'implémenté « en convention ») :
- **D3** — le code de sortie du producteur qui écrit la forme de refus (0) n'est pas dans la table des codes du § I.1 :
  choix forcé et minimal, le texte doit finir par le dire ;
- **D6** — forme de refus en abstention : à la lettre de C-1, l'identité ne peut égaler une retenue absente → R0 ;
  asymétrie avec la route exécutée, dont l'abstention admet l'évaluation de toute configuration de l'univers ;
- **D7** — `E_NO_BENCHMARK` constaté sous une raison prioritaire (ex. `P_PROVENANCE`) : `motif` nul ;
- et ceux du lot 1 : D3 (abstention sans λ), D6 (inscription hors `chain`), **D7 (évaluation différée, prérequis probable
  avant campagne)**, D14.

**Report au dossier d'attendu du lot 3** (à écrire avant le run, STOP 1) :
- D7 : la fenêtre 2020 est en provenance `unknown` ; `P_PROVENANCE` précède `E_NO_BENCHMARK` au § H.1. Si le comparateur
  y était non comparable, le verdict de conformité porterait `P_PROVENANCE` et un `motif` nul : l'attendu (codes et
  booléens seuls, issue non lue) s'écrit en le sachant ;
- D6 : le coin « désignation + abstention + comparateur non constructible → code 2 » n'est pas sur le chemin de
  conformité tant que le comparateur 2020 se construit (C3b l'a prouvé le 28/09) — à vérifier une fois à l'attendu.

**Branches sans adverse dédié** (règles écrites, dites) : la contradiction « refus + séries » **au verdict** (en chaîne,
la continuité la voit d'abord ; route_r18.out) ; `refused.window ≠ [T, fin]` (R0) ; `refused.reason` hors liste
(code 2 ; T6 l'exerce, mais derrière le R0 d'identité) ; `refused_route` faux (violation) ; `metrics.executions` négatif au
recoupement (l'admission le refuse déjà sur une réelle) ; une seule des deux dates de couverture nulle.

**Obligations du lot 1** : a → D2 et T15 ; b → `route_r18.out` ; c → D12 ; d → épinglage des listes closes à chaque
commit (`refused`, `executions`, `first_day`, `last_day`) ; e → M1-M6 rejoués, M3 tué par A1.

## 6. Défauts du lot, dits comme tels

1. **Formatage hors périmètre.** Un `ruff format scripts/audit/` lancé sur tout le répertoire a reformaté, dans l'arbre de
   travail, six fichiers `rejeu_*`, dont `rejeu_common.py`, interdit. Constaté par `git status` avant tout commit ; les six
   fichiers ont été restaurés par `git checkout`, `rejeu_common.py` vérifié identique à `8c114fe`. Aucun commit ne les
   touche (`interdits_lot2.out`). Ensuite, formatage par fichiers nommés seulement.
2. **T14 sans mutant au plan.** Le tableau des tests neufs du plan ne donnait pas de mutant à T14 ; L2M17 a été ajouté
   après le premier passage de `mutants_lot2.sh` et lancé seul (consigné comme tel à `mutants.log`).
3. **Calendrier des scripts.** Le plan mettait les scripts de vérification adaptés au commit 0 ; seul `lint.sh` (et sa base)
   y est. `xfail_fin.sh`, `route_r18.sh`, `mutants_lot2.sh`, `declares_lot2.txt` et l'extension de `diff_tests.sh` sont au
   commit de ce rapport, écrits pendant les suites dans le répertoire temporaire.
4. **Numérotation des mutants.** Le plan en annonçait treize ; il y en a dix-huit (L2M3b, L2M8b et L2M14 à L2M17 ajoutés,
   un par test neuf qui n'en avait pas) ; la numérotation du plan est gardée pour les treize.
5. Une commande shell a échoué sur une variable non découpée (zsh) ; relancée avec la liste explicite, sans effet.

## 7. Tunnel, base, lint, interdits

Tunnel `127.0.0.1:5433` constaté fermé à l'ouverture de la session (19:49:18Z), ouvert à 19:50:20Z pour les 13 tests base
de la suite existante (lecture seule, aucun test base ajouté ni modifié), fermé à 21:04:55Z, vérifié fermé (`nc -z` échoue)
— `tests/tunnel.out`. Aucune migration. Lint et typage (`tests/lint_lot2.out`, rc=0) : ruff (liste CI et dépôt) vert,
`mypy src/` = 65, mypy strict sans écart neuf sur les neuf `scripts/audit/` touchés par le chantier (base :
`lint_base.out`, `lint_base_lot2.out`). Interdits (`tests/interdits_lot2.out`, rc=0) : diff vide contre `8c114fe`.

CI : voir `tests/ci_status_lot2.out` (commit suivant).
