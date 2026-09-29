# C3 — Outillage v2.2, lot 2 (producteur et réserves mixtes : R-16, R-18, R-19, R-20, hors réserve) — plan soumis au GO

> Plan rédigé en plan mode, approuvé le 2026-09-29 (GO en § 0), recopié tel quel par le commit 0. Rien n'a été écrit
> en git avant le GO.

## Contexte

Lot 2 du chantier `agent/AGENT_C3_OUTILLAGE_V2_2.md`, sur `feat/c3-outillage-v2.2` au tip `8d2ef60` (arbre propre, lot 1
livré, aucun merge). Liste close : `results/c3_v2_2/outillage_v2_2.md`. Décisions et obligations héritées :
`plans/lot1.md` (D1-D14) et `lot1_chaine/README.md` § 5. État de départ mesuré au lot 1 : 3 284 passés, 25 xfail
(R-16 10, R-18 4, R-19 6, R-20 4, hors réserve 1 caduc), 0 échec. **Tunnel vérifié fermé à l'ouverture de cette session**
(aucun écouteur sur 5433, aucun `ssh … 5433`) ; consigné par `tunnel.sh state` au premier geste après le GO.

La lecture du code et des 24 tests montre **trois conflits entre tests verts, xfail et texte** et **deux trous de texte**.
Ils fixent le plan ; ils sont en tête (§ 1), décision demandée pour chacun.

## 0. GO reçu (29/09, Bruno) — conditions intégrées ci-dessous

D1, D2, D4, D5, D8, D9, D10, D11, D12 accordés tels que recommandés. **D3 accordé avec consignation en candidat v2.3** :
la table des codes du § I.1 est du texte normatif et le code de sortie de la forme de refus n'y figure pas ; le choix
(0) est forcé et minimal, le texte doit finir par le dire. **D6 et D7 consignés candidats v2.3** (lectures à la lettre de
C-1 / C-3, rien d'arbitré), **et leurs deux conséquences reportées au dossier d'attendu du lot 3** (§ 6). Rien d'autre
ne change au plan. D1 : miroir non relevé consigné comme défaut du chantier v2.2 (le deuxième, après `phase1.md` § 4).
L'approbation de ce plan vaut GO avant toute écriture git.

## 1. Décisions demandées au GO

| # | Nature | Question | Recommandation et motif |
|---|---|---|---|
| D1 | **conflit test vert / xfail (STOP)** | `test_c3b_evaluate.py::test_a_non_buildable_comparator_stops_before_the_engine` (vert) finit par `assert not (tmp_path / "out").exists()` ; son jumeau R-18, **même monde** (bougie d'entrée retirée), exige `out/evaluation.json` sous forme de refus. Les deux ne peuvent pas être verts. | **Retirer cette seule ligne** : c'est l'attendu v2.1 (« rien d'écrit ») que § C.5 v2.2 abolit (« il écrit l'artefact d'évaluation sous sa forme de refus ») ; son docstring renvoie déjà la forme de refus au jumeau. `built == []` (le moteur n'est pas construit) reste. Défaut du chantier v2.2 (miroir non relevé), consigné. Sans GO : STOP au commit R-18. |
| D2 | **écart à la liste close** (hors réserve) | « `cb.build_pair` déplacé dans le `try` de l'étape 10b » : 10b tourne **après** le moteur. | **Garde à son site** (étape 10, avant le moteur), même contrat que 10b : toute exception non typée de la construction du comparateur (`load_candles`, `build_pair`, tests § C.5) → trace sur stderr, `ProducerControlError("comparator_failed")`, code 3, rien d'écrit. Le déplacer ferait tourner le moteur avant de savoir le comparateur constructible, contre § C.5 v2.2 (« le producteur n'exécute pas l'évaluation ») et le test R-18 producteur (`built == []`). Adverse neuf (T15) ; le test caduc garde son marqueur. |
| D3 | contrat du producteur ; **candidat v2.3 (GO)** | Code de sortie du producteur quand il écrit la forme de refus. | **0**, événement `refusal_form_written` (niveau info) : il a produit l'artefact que § C.5 prescrit ; « 2 = refus, rien d'écrit » reste vrai. Écrits : `evaluation.json` (forme de refus), `candles_eval.json`, `evaluation_run_provenance.json` (`outputs` = ces deux fichiers ; `flat_start_observed` et `duration_s` nuls) ; ni `benchmark_eval.json` ni sensibilité. Forme : `{synthetic: false, strategy, pair, params, period, refused: {reason: "comparator_not_buildable", window: [T, fin], motif: "comparateur d'évaluation <raison de build_pair>"}}` (les clés du monde `_refusal_world`). |
| D4 | interface (complétée, déclarée) | § L.1 v2.2 : sur la route du refus, « le comparateur d'évaluation n'est pas exigé » ; aujourd'hui `--benchmark-eval` est `required` dans `c3_continuity`, le verdict et `chain`. | **Facultatif au parseur** (ensembles de `dest` inchangés, tests de parseur verts) ; **exigé sur la route exécutée** (absent → code 2, nommé) ; sur la route du refus, **ni lu ni haché** s'il est fourni (les tests de chaîne R-18 le passent). `verify_producer_inputs` saute alors le lien `continuity.benchmark_eval` ; `verdict.inputs_sha256` ne le porte pas. |
| D5 | lecture (C-1) | Qu'est-ce qui choisit la route, et quand le bloc `refused` est-il lu ? | La route se choisit sur la **présence** d'un bloc `refused` (typé bloc, contenu non lu). `c3_continuity` ne lit **jamais** son contenu : admission, « refus + séries » (clé parmi `equity_daily`, `returns_config`, `returns_bench`, `replications`) → violation, identité dans l'univers et `period == [T, fin]` (R0, règles d'aujourd'hui), puis `continuity.json` sans clause : `{synthetic, strategy, pair, identity, evaluation_window, refused_route: true, note}`. Le verdict lit `refused` **après** le recoupement de l'identité à la retenue : `reason` ∈ {`comparator_not_buildable`} (sinon code 2), `window == [T, fin]` (sinon R0, comme `period`), `motif` chaîne. |
| D6 | **trou de texte (STOP)** | Forme de refus **en abstention** (aucune configuration retenue) : à quoi recouper l'identité (C-1) ? | **Lettre de C-1 : R0, code 2, rien publié** (l'identité ne peut pas égaler une retenue absente). Asymétrie dite : sur la route exécutée, l'abstention admet l'évaluation de toute configuration de l'univers (famille de D3, lot 1). Conséquence : un run de conformité par désignation, en abstention, à comparateur non constructible, s'arrête en 2. Candidat v2.3. Alternative : issue d'abstention, refus rejoué mais non rapporté. |
| D7 | lecture + trou | Quand le verdict porte-t-il `motif` ? | **Non nul si et seulement si la raison publiée est `E_NO_BENCHMARK`** : `comparator_not_buildable` (route du refus) ou `comparator_not_comparable` (comparateur `FAILED`, route exécutée), et `motif_detail` (clé neuve déclarée) : la raison du rejeu, ou les tests § C.5 en échec « nommés à côté ». `E_NO_BENCHMARK` constaté sous une raison prioritaire (ex. `P_PROVENANCE`, provenance `unknown` de la fenêtre du lot 3) : `motif` nul — candidat v2.3. `motif` et `motif_detail` aussi au diagnostic (nuls). La chaîne à neuf champs ne change pas. |
| D8 | **conflit témoin vert / texte (écart à la liste close)** | La liste close veut que le témoin `test_c3_continuity.py::test_une_evaluation_reelle_sans_porteur_est_refusee_en_tete` « reçoive le porteur ». Cas `[sans first_fill_at]` : réelle, `first_fill_at` nul, attendu **R0, code 2**. Avec `executions > 0`, § L.1 v2.2 dit **violation, code 1** (« une contradiction entre ces faits »), et le test R-19 du verdict l'exige (`executions=3` → 1). | **La fixture ne porte `metrics.executions` que si `first_fill_at` est non nul** (`fx.evaluation`, défaut dérivé = `liquidation_positions + 1`) : un monde sans premier remplissage ne déclare pas son compte. **Admission réelle** : clé `first_fill_at` présente (nulle admise), `metrics.executions` entier ≥ 0 ; un `first_fill_at` nul **sans** `metrics.executions` est refusé R0 **en nommant les deux** (sa recevabilité — nul ⟺ zéro exécution — n'est pas décidable). Le témoin reste vert par cette route, dite ; son cas `[sans flat_start_proof]` reçoit le porteur. Côté verdict, les témoins le reçoivent : `REAL_CARRIERS_L1` += `"metrics.executions"`, `_carry` le pose (3). |
| D9 | architecture R-19 | Où vivent les recoupements, et quel `C` ? | **Au verdict seul** (AM-08 : « continuité ou verdict ») : `first_fill_at` nul ⟺ `executions == 0`, et `executions == 0` ⟹ toutes les valeurs d'`equity_daily` `== C`, appliqués dès que `metrics.executions` est porté (toujours sur une réelle). `C` = capital du manifeste quand l'entrée est au dictionnaire, sinon `cc.CAPITAL` (classe contrat, § 0.5, que `c3_anchor` asserte gelé). c5 `NON VÉRIFIABLE` admis sur une réelle **ssi `first_fill_at` nul**. `validé` inatteignable par construction (zéro exécution ⟹ equity constante ⟹ E1 faux) : aucune garde morte ajoutée. Listes : `first_fill_at` **reste** dans `OPTIONAL_FIELDS` (un synthétique peut l'omettre ; « optionnel ou nullable, pas les deux », `test_c3_common.py:184`), présence réelle contrôlée à l'admission ; `OPTIONAL_FIELDS` += `executions`. |
| D10 | architecture R-20 | La contradiction dates / unités (ligne 15) passe par où ? | `cc.coverage_recompute` lit les dates en nullable et rend la contradiction sous une clé **à part** (`violations`), jamais dans `problems` (qui est un refus I-A.7) : `c3_entry` I-A.7 → `ctx.violations`, code 1 (attendu des tests) ; `c3_select` D1 et `reconstruct_1w.py` ne lisent que `problems`, inchangés ; le producteur l'exige vide (contrôle 3). Référence : `covered_recomputed` (« au sens de D1 »). `c3b_prefix.py` intouché (il rattrape `ProducerRefusal` en bloc, `:403`). `NULLABLE_FIELDS` += `first_day`, `last_day`. |
| D11 | forme R-16 | Garde, renommages, identifiants. | `cc.check_quote_amount_keys(bloc, stem, where)`, symétrique de `check_base_quantity_keys`, **aux deux positions nommées seules** : premier niveau d'une observation (`min_order_*` ≠ `min_order_quote`) ; bloc de liquidation et chaque lot (`gross_*` ≠ `gross_quote`). Appelée par `c3_entry` (I-A.1), `cc.liquidation_identities` (D6 et clause 3) et `c3b_common.liquidation_block` (contrôle 3). Table de renommage += `gross_usdc → gross_quote` (clé du moteur, `backtest.py:3296`). `Manifest.min_order_usdc` → `min_order_quote` ; l'argument moteur `min_order_usdc=` ne bouge pas (`c3b_common.py:314`). L'id paramétré `Σ gross ≠ gross_usdc` (`test_c3_select.py`) est **gardé** (identifiant stable pour `comptes.sh`), sa lambda renommée. |
| D12 | obligation c | Branche morte `except OverflowError` d'`evaluation_series`. | **Retirée**, docstring corrigée : depuis R-21 (`a538d22`) `cc.cagr_pct` rend `None` ; un CAGR non fini sort par `cc.replay_bootstrap` → `f2_invalid_input`, code 3 (cas `explosion` de `test_an_invalid_input_is_3_before_any_draw`, vert), et toute exception résiduelle par le `except Exception` de 10b (3). Commit `refactor` à part. |

Noms d'interface **gardés tels que les tests les proposent** : `refused {reason, window, motif}`, `motif`,
`metrics.executions`, `gross_quote`, `min_order_quote`. **Ajouts déclarés** : `motif_detail` (verdict),
`refused_route` (continuité, route du refus), `--benchmark-eval` facultatif (D4), `Manifest.min_order_quote`.

## 2. Livré, par commit (assert de branche avant chaque commit, message par `-F`, `suite.sh` après chacun)

**C0** `docs(results)` : ce plan (GO inclus) → `plans/lot2.md` ; scripts de vérification adaptés (§ 3).

**C1 `feat(c3)` — R-16 (10 xfail)**
- `c3b_common.py` : `LIQUIDATION_RENAME` (`:69-73`) += `gross_usdc` ; garde des restes (`:368`) étendue aux `gross_*` ;
  `lots_from_trades` (`:345`) → `gross_quote` ; `liquidation_block` appelle la garde sur bloc et lots ;
  `observation_entry` (`:415`) → `min_order_quote` ; `build_engine` lit `manifest.min_order_quote`.
- `c3_common.py` : `load_manifest` (`:1339`) exige `min_order_quote` ; `PREFIX_WHITELIST_CONTRACTS` (`:1553`) ;
  `liquidation_identities` (`:1981`, `:2040`, `:2076-2116`) → `gross_quote` + garde ; `check_quote_amount_keys` neuve.
- `c3_entry.py` : `_liquidation_form` (`:155`, `:175`) + garde bloc et lots ; `a01_form` (`:264`) + garde premier niveau ;
  `a02_d5` (`:318-320`). `c3_select.py` (`:231-233`).
- Fixtures renommées **avec** le code : `fx.manifest`, `fx.observation`, `fx.liquidation_segment` ; `test_c3_select.py` :
  lambda du paramètre `Σ gross ≠ gross_usdc` et corps de `test_revue_R3_gross_different_de_amount_x_price_ne_passe_pas_D6`.
- Neufs : T1-T3 (§ 4). Garde-fou : témoin `test_un_suffixe_de_monnaie_hors_des_positions_nommees_n_est_ni_lu_ni_refuse`
  vert, mutant L2M1.

**C2 `feat(c3)` — R-18 (4 xfail) + D1**
- `c3_common.py` : `evaluation_admission` admet la forme de refus sans porteurs (présence de `refused`) ;
  `REFUSAL_REASONS`, `BENCHMARK_MOTIFS`, `EVALUATION_SERIES`, lecture/contradiction de la forme ; `OPTIONAL_FIELDS` += `refused`.
- `c3_continuity.py` : route du refus (D5), `--benchmark-eval` facultatif (D4), lecture de l'évaluation avant le
  comparateur ; l'identité et la fenêtre extraites en aide commune aux deux routes (comportement inchangé).
- `c3_verdict.py` : `run_verdict` route avant `_evaluation_contract` ; `decide` → `_decide_refused` (identité d'abord,
  puis bloc, rejeu sur l'export, `E_NO_BENCHMARK`, `continuite=-`) ; rejeu tiré de `_producer_recoupements`
  (étapes 2-3 extraites en `_rebuild_comparator`, comportement inchangé) ; `motif` / `motif_detail` (D7) ;
  `verify_producer_inputs` (D4) ; parseurs et `run_chain` (D4). La ligne `decision = decide(artifacts, …)` ne bouge pas
  (ancre de M3).
- `c3b_evaluate.py` : `evaluation_comparator` rend le comparateur ou le refus ; `evaluate` s'arrête **avant le moteur** ;
  `main` écrit la forme de refus (D3) ; docstring d'ordre des contrôles.
- **Route nouvelle de `test_R18_un_refus_qui_porte_des_series_se_contredit`** (obligation b) : admission du refus, puis
  violation « refus + séries » **à la continuité** → étape 5 en code 1, chaîne en 1 ; plus par C-3 au verdict. Constat
  par `route_r18.sh`. S'il rougit : règle d'arrêt.
- Test vert modifié : D1. Neufs : T4-T9.

**C3 `feat(c3)` — R-19 (6 xfail)**
- `c3b_evaluate.py` : `metrics.executions = len(engine.metrics.trades)` (les remplissages dont `first_fill_at` est le
  premier — nul ⟺ 0 par construction), fusionné dans `metrics` par `evaluation_artefact`. Réponse au « lot soldé en
  poussière » : le résidu `≤ 1e-12` passé en perte (`backtest.py:3234`) n'est pas un trade, donc pas une exécution ; il ne
  naît qu'après des remplissages : l'implication ne peut pas en souffrir.
- `c3_common.py` : admission (D8), `execution_recoupements` (D9), `OPTIONAL_FIELDS` += `executions`.
- `c3_verdict.py` : recoupements au verdict, exemption c5 (`:764-770`). `c3_continuity.py` : détail de c5 quand
  `first_fill_at` est nul (libellé seul, état inchangé).
- Fixtures : `fx.evaluation` (D8), `REAL_CARRIERS_L1`, `_carry`. Neufs : T10-T13.

**C4 `feat(c3)` — R-20 (4 xfail)** — `c3b_common.covered_bounds` (`:611-635`) : dates nulles au lieu du refus
`coverage_no_covered_unit` ; `coverage_series` exige `violations` vide ; `cc.coverage_recompute` (`:1850-1863`) et
`c3_entry` (`:568-569`) selon D10. Neuf : T14.

**C5 `fix(c3b)` — hors réserve** (D2) + T15. **C6 `refactor(c3b)`** — branche morte (D12).

**C7 `docs(results)`** — `lot2_producteur/README.md` (format du lot 1 : livré, tests, mutants, table d'écarts, candidats
v2.3, défauts), `tests/*.sh` + `.out`, `mutants.log`. Push `git push -u origin feat/c3-outillage-v2.2`, sans merge.
**C8 `docs(results)`** — `ci_status_lot2.out` (relance pour `test_rejeu_effect` seul, tout autre rouge = STOP).

## 3. Vérifications (toutes par `bash results/c3_outillage_v2_2/tests/*.sh`, `pipefail`, `.out` committés)

- `tunnel.sh` : `state` (fermé) à l'ouverture, `open` pour le lot (13 tests base), `close` + vérifié fermé en fin.
- `suite.sh L2C1` … `L2C6` : 0 échec, 0 XPASS ; tout XPASS → marqueur retiré dans le commit qui le produit, rien d'autre.
- `comptes.sh lot2 L2C6` + `declares_lot2.txt` **cumulatif contre `8c114fe`** : retirés ∅ ; levés = 21 (lot 1) + 24 ;
  neufs = 4 (lot 1) + 15 ; équation 3 259 + 45 + 19 = **3 323 passés** ; `-k` = les 24 `_full`.
- `xfail_fin.sh` (neuf) : l'ensemble des XFAIL de la suite finale est **exactement** le test caduc.
- `diff_tests.sh lot2` : listes déclarées étendues (fixtures et tests verts du § 5, décorateur de la lambda
  `test_chaque_identite_exacte_de_D6_fausse_retire_le_candidat`, affectation `REAL_CARRIERS_L1`) ; corps des 46 xfail de la base identiques.
- `route_r18.sh` (neuf) : obligation b, la chaîne s'arrête à `continuity` en code 1.
- `mutants_lot2.sh` → `mutants.log` : L2M1-L2M13 (§ 4) ; **M1-M6 du lot 1 rejoués au tip** (ancres réappliquées si
  besoin, déclaré), **M3 en tête : tué par A1**, liste complète de ses tueurs consignée (M3b refait : le test « refus avec
  séries » n'en est plus) ; si A1 ne le tue pas → couverture complétée avant la porte.
- `lint.sh lot2` : `AUDIT` += `c3_entry`, `c3_continuity`, `c3b_common`, bases mesurées à `8c114fe` (worktree) dans
  `lint_base_lot2.out` ; ruff (liste CI + dépôt), `mypy src/` = 65, mypy strict sans écart neuf.
- `interdits.sh lot2` : diff vide contre `8c114fe` sur `src/`, `scripts/backtest.py`, runners P6/P7, `rejeu_common.py`,
  protocole, paquets d'amendements, `results/c3_v2_2/`, `results/c3b_producteur/`.

## 4. Tests neufs (liste close, 15) et mutants

| # | Test | Ce qu'il mord (mutant) |
|---|---|---|
| T1 | `test_c3_entry.py::test_R16_un_lot_qui_porte_gross_usdc_refuse_l_entree_a_la_forme` | garde des lots retirée (L2M2) |
| T2 | `test_c3_continuity.py::test_R16_un_bloc_de_liquidation_d_evaluation_qui_porte_gross_usdc_est_une_erreur_de_forme` | garde retirée de `liquidation_identities` (L2M3) |
| T3 | `test_c3b_common.py::test_R16_un_montant_gross_hors_table_de_renommage_est_un_controle_en_echec` | garde des restes limitée à `_btc` |
| T4 | `test_c3_verdict.py::test_R18_les_motifs_et_la_raison_du_refus_sont_ceux_du_texte` (épinglage § C.5 recopié) | une entrée des constantes changée |
| T5 | `test_c3_verdict.py::test_R18_un_comparateur_non_comparable_porte_le_motif_comparator_not_comparable` | motif de la route exécutée retiré (L2M6) |
| T6 | `test_c3_verdict.py::test_R18_l_identite_du_refus_est_recoupee_avant_toute_lecture_du_bloc_refused` (bloc malformé + autre configuration → R0) | bloc lu avant l'identité (L2M4) |
| T7 | `test_c3_verdict.py::test_R18_la_chaine_sur_une_forme_de_refus_n_exige_pas_le_comparateur_d_evaluation` | D4 |
| T8 | `test_c3_continuity.py::test_R18_une_evaluation_executee_sans_comparateur_d_evaluation_est_refusee` | `--benchmark-eval` non exigé sur la route exécutée (L2M13) |
| T9 | `test_c3b_evaluate.py::test_R18_the_refusal_form_exits_0_and_writes_only_its_artefacts` | D3 |
| T10 | `test_c3_verdict.py::test_R19_un_premier_remplissage_avec_zero_execution_est_une_violation` | ⟺ réduit à un sens (L2M7) |
| T11 | `test_c3_verdict.py::test_R19_zero_execution_et_equity_constante_differente_de_C_est_une_violation` | « = C » retiré, implication retirée (L2M8) |
| T12 | `test_c3_verdict.py::test_R19_zero_execution_equity_non_constante_rendements_coherents_est_une_violation` | implication retirée — le test xfail homologue est tué par R-15 d'abord (constat au README) |
| T13 | `test_c3b_evaluate.py::test_R19_executions_is_the_number_of_fills` | `executions` = trades de liquidation (L2M9) |
| T14 | `test_c3_select.py::test_R20_une_serie_sans_unite_couverte_retire_la_paire_par_D1` | bout en bout : dates nulles → D1, pas un refus |
| T15 | `test_c3b_evaluate.py::test_hors_R_an_exception_in_build_pair_is_a_control_error_3` | garde du comparateur retirée (L2M12) |

Autres mutants : L2M1 garde R-16 **non bornée** (toute clé de premier niveau finissant par `_usdc`/`_usdt`) → témoin
rouge ; L2M5 rejeu du refus retiré → `test_R18_un_refus_que_l_export_dement_est_une_violation` rouge ; L2M10 exemption c5
élargie → `test_c1_ou_c5_non_verifiable_sur_une_evaluation_reelle_est_une_violation[c5]` rouge ; L2M11 contradiction de
dates réduite à un sens → `test_R20_des_dates_presentes_sur_une_serie_sans_unite_couverte_sont_une_violation` rouge.
Chaque neuf est constaté rouge au tip du lot 1 (ou sous son mutant quand l'état de base ne l'exerce pas), règle agent 1.

## 5. Tests verts et fixtures modifiés (liste close, déclarée)

`test_c3_common.py` : `manifest`, `observation`, `liquidation_segment` (R-16) ; `evaluation` (R-19, D8) ;
`test_les_listes_de_champs_optionnels_et_nullables_sont_closes_et_nommees` (obligation d : `refused`, `executions` ;
`first_day`, `last_day`). `test_c3_select.py` : les deux tests de D11. `test_c3_verdict.py` : `REAL_CARRIERS_L1`, `_carry`.
`test_c3b_evaluate.py` : `test_a_non_buildable_comparator_stops_before_the_engine` (D1, une ligne retirée). Rien d'autre ;
aucun attendu d'un des 24 xfail touché.

## 6. Règle d'arrêt, écarts à la porte

Tout test vert qui rougit et que ce plan ne nomme pas, tout attendu qu'il faudrait toucher, tout besoin dans `src/`,
`scripts/backtest.py`, `rejeu_common` ou le texte → STOP, rien d'arbitré. **Écarts à la porte du brief déjà visibles** :
un test vert modifié (D1) ; l'item hors réserve livré à son site et non dans 10b (D2) ; le témoin continuité
`[sans first_fill_at]` ne reçoit pas le porteur (D8) ; la porte « 0 xfail » se lit « 0 xfail hors le caduc déclaré ».
**Candidats v2.3 (GO)** : D3 (code de sortie de la forme de refus, absent de la table du § I.1), D6 (forme de refus en
abstention), D7 (motif sous une raison prioritaire). **Report au dossier d'attendu du lot 3** (écrit avant le run,
STOP 1), consigné au README du lot 2 :
- D7 : la fenêtre 2020 est en provenance `unknown` ; `P_PROVENANCE` précède `E_NO_BENCHMARK`, donc si le comparateur
  était non comparable, le verdict de conformité porterait `P_PROVENANCE` et un `motif` nul — l'attendu (codes et
  booléens seuls, issue non lue) s'écrit en le sachant ;
- D6 : le coin « désignation + abstention + comparateur non constructible → code 2 » n'est pas sur le chemin de
  conformité tant que le comparateur 2020 se construit (prouvé par C3b le 28/09) — à vérifier une fois à l'attendu.

Fin de lot : README, push, CI verte, tunnel fermé et vérifié.
