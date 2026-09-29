# Outillage v2.2 — liste close du chantier suivant

> **Entrée du chantier outillage** qui suit l'amendement v2.2 du protocole C3 (`docs/amendements_c3_v2.2.md`,
> adopté le 2026-09-29, sha256 `1bed7696c0b0002b702f34fd549a59fc648968ff2e3056a98d33168bd643292a`). Rien de ce
> qui suit n'est implémenté : `scripts/audit/*.py` et `src/` sont inchangés depuis `8689636`.
>
> **Un item par réserve**, avec le § qui l'impose, les fichiers à toucher, le statut et les tests `xfail` à lever.
> Les tests sont `xfail(strict=True, raises=…)` : quand l'outillage d'une réserve est livré, ils passent en XPASS,
> la suite rougit, et le marqueur **doit** être retiré. Tout test de cette liste qui reste `xfail` après le chantier
> est une réserve non levée.
>
> **Règle de lecture des tests.** L'**attendu** (code, issue, raison, motif, clé exigée) se dérive du texte v2.2 : il
> est normatif et ne se change pas. L'**interface d'appel** (noms de clés `lambdas`, `family`, `verdict`,
> `deferred_evaluation`, `refused`, option `--candles-eval`, entrées `benchmark`, `candles_eval`, `benchmark_eval` du
> dictionnaire d'artefacts du verdict) est **indicative** : le chantier outillage peut la compléter ou la renommer,
> en le disant. Les mondes de ces tests sont conformes à v2.2 sur tout ce que l'interface de v2.1 permet de porter ;
> le chantier les complète (entrées nouvelles, fixtures), sans toucher à l'attendu.
>
> **Ordre imposé par les statuts.** Bloquants manifeste d'abord (R-15, R-16, R-18, R-19), puis bloquants campagne
> (R-17, R-21, R-22) avant la première campagne comptée ; R-20 et l'item hors réserve quand on veut.

## R-15 — la chaîne recalcule ce que le producteur garantit (AM-03) — bloquant manifeste

- **Imposé par** : § L.2 v2.2 (section d'origine des recoupements, avec la NAV du comparateur — retouche C-4 — et
  la frontière — C-3), § L.1 v2.2 ligne 0 (septième entrée), § F.2 (d) et § J item 12 (ce qui reste déclaratif).
- **Fichiers** :
  - `scripts/audit/c3_verdict.py` : recalculer `returns_config` sur `evaluation.equity_daily` par
    `r_t = E_t / E_{t−1} − 1` (celle de `cc.recompute_daily`, `c3_common.py:1612-1623`) ; lire `benchmark.json`
    (absent d'`INPUT_NAMES`, `:111`) et recouper les λ déclarés ; lire `candles_eval.json` sur la seule paire
    évaluée (`cb.load_candles` sur manifeste réduit, comme `c3b_evaluate.py:540`), reconstruire le B&H
    (`cb.build_pair`) et le blend (`cb.blend_nav`), recouper `returns_bench` et la NAV du comparateur
    d'évaluation au bit ; recalcul impossible sur une évaluation non refusée → violation ; `verify_chain` (`:940`)
    hache `benchmark.json` et `candles_eval.json` ; option `--candles-eval` au parseur `chain`.
  - `scripts/audit/c3b_evaluate.py` : déclarer les λ du préfixe dans `evaluation.json` (aujourd'hui seulement dans
    `evaluation_sensitivity.json`, `:748`) ; exporter la NAV du B&H dans `benchmark_eval.json` (`:576-581`).
  - Fixtures : `fx.evaluation` (λ déclarés, `equity_daily` cohérent), `_chain_world` (export d'évaluation).
- **`xfail` à lever (9)** :
  - `test_c3_verdict.py::test_R15_returns_config_ecarte_d_un_ulp_du_recalcul_sur_equity_daily_est_une_violation`
  - `test_c3_verdict.py::test_R15_des_lambdas_declares_differents_de_ceux_de_l_etape_3_sont_une_violation`
  - `test_c3_verdict.py::test_R15_returns_bench_different_du_recalcul_sur_l_export_est_une_violation`
  - `test_c3_verdict.py::test_R15_la_nav_du_comparateur_d_evaluation_differente_du_bh_recalcule_est_une_violation`
  - `test_c3_verdict.py::test_R15_une_evaluation_non_refusee_sans_estampille_d_entree_dans_l_export_est_une_violation`
  - `test_c3_verdict.py::test_R15_un_export_d_evaluation_hors_regle_d_entree_est_refuse` (2 cas)
  - `test_c3_verdict.py::test_R15_le_parseur_chain_expose_la_septieme_entree`
  - `test_c3b_evaluate.py::test_R15_evaluation_json_declares_the_prefix_lambdas_it_used`
- **Artefacts C3b non conformes** : toute évaluation (aucun λ déclaré), `benchmark_eval.json` (pas de NAV) ;
  `candles_eval.json` n'était pas une entrée de chaîne.

## R-16 — clés `_quote` aux positions nommées (AM-04) — bloquant manifeste

- **Imposé par** : § A.7 v2.2, lignes Contrats et Comptabilité (contrats de forme bornés aux positions nommées).
- **Fichiers** :
  - `scripts/audit/c3b_common.py` : `lots_from_trades` (`:345`), `liquidation_block` (`:354-382`, table de
    renommage `:69-73`, garde des restes `:368`), `observation_entry` (`:415`) → `gross_quote`, `min_order_quote`.
    L'argument du moteur `min_order_usdc=` (`:314`) **ne bouge pas**.
  - `scripts/audit/c3_common.py` : `PREFIX_WHITELIST_CONTRACTS` (`:1525`), `liquidation_identities` (`:1943`,
    `:2038`, `:2078`), clé du manifeste (`:1316` → `min_order_quote`), garde de forme symétrique de
    `check_base_quantity_keys` (`:1881-1891`) sur les **deux seules** positions nommées.
  - `scripts/audit/c3_entry.py` (`:155`, `:175`, `:264`, `:318-320`) ; `scripts/audit/c3_select.py` (`:231-233`).
  - Fixtures : `test_c3_common.py:893`, `:1067`, `:1086`, `:1169` (artefacts simulés, renommés avec le code).
- **`xfail` à lever (10)** :
  - `test_c3_chronology.py::test_R16_les_contrats_de_la_projection_sont_ceux_du_A7_v22`
  - `test_c3_entry.py::test_R16_le_plancher_d_ordre_min_order_quote_absent_ou_nul_refuse_l_entree` (2 cas)
  - `test_c3_entry.py::test_R16_un_plancher_d_ordre_different_du_manifeste_refuse_l_entree_D5`
  - `test_c3_entry.py::test_R16_un_plancher_d_ordre_suffixe_par_une_monnaie_refuse_l_entree_a_la_forme`
  - `test_c3_entry.py::test_R16_un_bloc_de_liquidation_qui_porte_gross_usdc_refuse_l_entree_a_la_forme`
  - `test_c3_anchor.py::test_R16_le_plancher_d_ordre_min_order_quote_du_manifeste_absent_ou_nul_refuse_l_entree` (2 cas)
  - `test_c3b_common.py::test_R16_les_lots_et_le_bloc_de_liquidation_portent_gross_quote`
  - `test_c3b_common.py::test_R16_l_observation_exportee_porte_min_order_quote`
- **Garde-fou** : le témoin vert `test_c3_entry.py::test_un_suffixe_de_monnaie_hors_des_positions_nommees_n_est_ni_lu_ni_refuse`
  doit rester vert (vérifié par mutation : une garde non bornée le rougit).
- **Artefacts C3b non conformes** : `observations.json`, `evaluation_run.json` désigné, manifeste du lot 3 ; les
  empreintes de projection de `selection.json` changent (pas les identités de candidat).

## R-17 — le registre tient l'état du critère d'arrêt (AM-05) — bloquant campagne

- **Imposé par** : § A.6 v2.2 (famille au manifeste ; statut compté écrit à l'étape 6 ; évaluation différée comme
  état du registre ; refus des variantes que le § 10.1 exclut), § L.1 v2.2 ligne 6, § K.1 (renvoi) ; règle
  d'origine : `docs/CONTRAINTES_POST_B4.md` § 10.1.
- **Fichiers** :
  - `scripts/audit/c3_common.py` : `load_manifest` (`:1276`), champ de famille obligatoire.
  - `scripts/audit/c3_anchor.py` : lecture des enregistrements de la famille ; refus R0 (seconde campagne sur
    famille au verdict compté ; relance au-delà de l'unique) ; seule l'empreinte différée attendue passe ; champs
    d'issue hors `RECORD_KEYS` (`:57-68`) pour que l'idempotence (`:161-172`) tienne. Registre de campagne unique
    et persistant : une première campagne d'une autre famille déclare un parent (seconde racine refusée,
    `:174-180`).
  - `scripts/audit/c3_verdict.py` : écriture, à l'étape 6, de l'issue, de la raison, du statut compté (table du
    § 10.1 recopiée dans un test et épinglée à la constante du code), et de la date et de l'empreinte attendue de
    l'évaluation différée quand l'issue ouvre la voie de sortie prospective ; écrits une fois (une réécriture
    différente est une violation).
  - Fixtures : `fx.manifest` (famille).
- **`xfail` à lever (5)** :
  - `test_c3_anchor.py::test_R17_un_manifeste_sans_famille_est_refuse`
  - `test_c3_anchor.py::test_R17_une_seconde_campagne_sur_une_famille_au_verdict_compte_est_refusee`
  - `test_c3_anchor.py::test_R17_une_relance_au_dela_de_l_unique_est_refusee`
  - `test_c3_anchor.py::test_R17_sur_une_famille_close_une_autre_empreinte_que_la_differee_est_refusee`
  - `test_c3_verdict.py::test_R17_la_chaine_inscrit_l_issue_et_son_statut_a_l_enregistrement_de_la_variante`
- **Témoin à écrire à ce chantier** (vérifié par mutation) : sur une famille close, la variante de l'empreinte
  différée attendue est acceptée.
- **Artefacts C3b non conformes** : manifeste du lot 3 (pas de famille), `variants.json` (ni famille ni issue).

## R-18 — refus amont d'un comparateur non constructible (AM-06) — bloquant manifeste

- **Imposé par** : § C.5 v2.2 (forme de refus, rejeu de la non-constructibilité, deux formes interdites, motif en
  liste close de deux), § L.1 v2.2 (route du refus : identité d'abord — C-1 —, aucune clause évaluée), § L.2 v2.2
  (`continuite=-`, refus amont et abstention — C-5), § J item 13.
- **Fichiers** :
  - `scripts/audit/c3b_evaluate.py` : sur `comparator_not_buildable` (`:555-558`), écrire la forme de refus
    (identité, fenêtre `[T, fin]`, bloc `refused {reason, window, motif}`, aucune série) et `candles_eval.json`, au
    lieu du refus 2 sans artefact (`:912-914`).
  - `scripts/audit/c3_common.py` : `evaluation_admission` (`:1150-1176`) reconnaît la forme de refus, et recoupe
    l'identité avant toute lecture du bloc `refused`.
  - `scripts/audit/c3_continuity.py` : route sans contrat § B (aujourd'hui `comparator_block` exige
    `benchmark_eval`, `:287-333` ; admission `:361`).
  - `scripts/audit/c3_verdict.py` : `E_NO_BENCHMARK` avec son motif (aujourd'hui tiré du seul comparateur
    `FAILED`, `:581`, `:646-647`), rejeu de la non-constructibilité sur l'export (R-15), `continuite=-` (`:897`).
  - **Le § B.8 et `test_c3_verdict.py:3167` ne changent pas.**
- **`xfail` à lever (5)** :
  - `test_c3_verdict.py::test_R18_une_evaluation_sous_forme_de_refus_rend_E_NO_BENCHMARK_avec_son_motif`
  - `test_c3_verdict.py::test_R18_un_refus_qui_porte_des_series_se_contredit`
  - `test_c3_verdict.py::test_R18_un_refus_que_l_export_dement_est_une_violation`
  - `test_c3_verdict.py::test_R18_un_refus_d_une_autre_configuration_que_la_retenue_est_un_refus_R0`
  - `test_c3b_evaluate.py::test_R18_a_non_buildable_comparator_writes_the_refusal_form_and_the_export`
- **Note** : les quatre tests de chaîne rougissent aujourd'hui sur l'option `--candles-eval` inconnue ; une fois
  l'option livrée (R-15), ils doivent rougir sur leur attendu tant que R-18 n'est pas livré.
- **Artefacts C3b non conformes** : aucun.

## R-19 — évaluation réelle sans exécution (AM-08) — bloquant manifeste

- **Imposé par** : § L.1 v2.2 (porteur `metrics.executions` — C-6 ; `first_fill_at` nul ⟺ `executions == 0` ;
  `executions == 0` ⟹ `equity_daily` constante `= C` ; rien dans l'autre sens ; clause 3 vérifiée à vide sur une
  liste de lots exportée et vide — C-2), § B.8 v2.2 (« Ce qu'exige `validé` »).
- **Fichiers** :
  - `scripts/audit/c3_common.py` : `evaluation_admission` (`:1150-1176`) exige `metrics.executions`, admet
    `first_fill_at` nul si et seulement si zéro exécution ; `OPTIONAL_FIELDS` / `NULLABLE_FIELDS` en conséquence.
  - `scripts/audit/c3_continuity.py` / `c3_verdict.py` : les deux recoupements ; la règle
    `c3_verdict.py:556-564` (c1 ou c5 `NOT_VERIFIABLE` sur une évaluation réelle → violation) admet c5
    `NOT_VERIFIABLE` quand `first_fill_at` est nul.
  - `scripts/audit/c3b_evaluate.py` : exporter `metrics.executions`, le **nombre d'exécutions** (les remplissages de
    `engine.metrics.trades`, `:812-814`), **pas** la métrique `total_trades` du moteur (`pairs_completed +
    liquidated_positions` sur le grid, `scripts/backtest.py:3326`). À vérifier : un lot soldé en poussière.
  - Fixtures : `fx.evaluation` (`metrics.executions`) ; les témoins (i) `test_c3_continuity.py:201`,
    `test_c3_verdict.py:1864`/`:1898`/`:1949` reçoivent le porteur.
  - Aucun outillage pour la clause 3 à vide : c3 sort déjà `VERIFIED` sur `lots: []` (constat C-2).
- **`xfail` à lever (6)** :
  - `test_c3b_evaluate.py::test_R19_no_trade_is_admitted_with_zero_executions`
  - `test_c3b_evaluate.py::test_R19_evaluation_json_metrics_carry_executions`
  - `test_c3_continuity.py::test_R19_une_evaluation_reelle_sans_execution_est_admise_c5_non_verifiable`
  - `test_c3_verdict.py::test_R19_une_evaluation_reelle_sans_execution_ne_porte_aucune_violation_et_jamais_valide`
  - `test_c3_verdict.py::test_R19_first_fill_at_nul_avec_des_executions_est_une_violation`
  - `test_c3_verdict.py::test_R19_zero_execution_avec_une_equity_non_constante_est_une_violation`
- **Artefacts C3b non conformes** : toute évaluation (pas de `metrics.executions`).

## R-20 — dates de couverture nullables (AM-09) — non bloquant

- **Imposé par** : § A.7 v2.2 (dates nulles si et seulement si aucune unité couverte ; sinon ligne 15).
- **Fichiers** : `scripts/audit/c3b_common.py` (`covered_bounds` `:611-635`, refus `coverage_no_covered_unit`
  `:625-632` → dates nulles) ; `scripts/audit/c3_entry.py` (`:568-569`) et `cc.coverage_recompute`
  (`c3_common.py:1812-1813`) en nullable conditionnel ; `NULLABLE_FIELDS` (`:261-280`).
- **`xfail` à lever (4)** :
  - `test_c3b_common.py::test_R20_a_series_without_covered_unit_is_written_with_null_dates`
  - `test_c3_entry.py::test_R20_une_serie_sans_unite_couverte_a_dates_nulles_passe_l_entree`
  - `test_c3_entry.py::test_R20_des_dates_nulles_sur_une_serie_couverte_sont_une_violation`
  - `test_c3_entry.py::test_R20_des_dates_presentes_sur_une_serie_sans_unite_couverte_sont_une_violation`
- **Artefacts C3b non conformes** : aucun.

## R-21 — D4 exige un CAGR fini (AM-10) — non bloquant manifeste, bloquant campagne

- **Imposé par** : § A.8 D4 v2.2 (ligne de la table et paragraphe « Le CAGR qui déborde » : ligne 6, jamais 15).
- **Fichiers** : `scripts/audit/c3_common.py` (`recompute_daily` `:1625`, `cagr_pct` `:732` : un CAGR non défini,
  sans exception) ; `scripts/audit/c3_select.py` (D4 `:342`) ; `scripts/audit/c3_benchmark.py` (`candidate_block`
  `:433` : `estimable: false`, `first_failed: D4`).
- **`xfail` à lever (2)** (`raises=OverflowError`) :
  - `test_c3_benchmark.py::test_R21_un_cagr_qui_deborde_sur_des_rendements_finis_rend_le_candidat_non_estimable`
  - `test_c3_select.py::test_R21_un_cagr_qui_deborde_sur_des_rendements_finis_retire_le_candidat_par_D4`
- **Portée** : impossible sur un préfixe de plus de ~361 jours (`E_0 = C`), donc sur la première campagne (1 362 j) ;
  possible sur une fenêtre courte.

## R-22 — sorties code 1 hors table § I.1, cas 1 à 4 (aucun texte) — non bloquant manifeste, bloquant campagne

- **Imposé par** : § I.1 (forme d'un diagnostic ; frontière ligne 2 / ligne 15), § C.5 et § C.6 (cas 2), § A.8 D4
  « tous finis » (cas 3). Classification (c) du 29/09 : le texte prescrit la forme, le code en produit une autre.
- **Fichiers et formes dues** :
  - cas 1, `scripts/audit/c3_anchor.py:335` : valider la finitude des enregistrements du registre à la lecture →
    diagnostic `invalide: true`, code 1 ;
  - cas 2, `scripts/audit/c3_benchmark.py:166-168` (et `:436-438`, `:504-506`) : un artefact écrivable (NAV en
    décimal, rendements non finis non écrits) → paire non comparable, code 0 ;
  - cas 3, `scripts/audit/c3_select.py:342` (D4 = « définis et tous finis »), `:294-297`, `:368-371` → candidat
    retiré par D4, code 0 ;
  - cas 4, `scripts/audit/c3_verdict.py:413` : ne pas recopier un non-fini fourni → diagnostic, code 1.
- **`xfail` à lever (4)** :
  - `test_c3_anchor.py::test_R22_un_non_fini_dans_un_autre_enregistrement_du_registre_est_un_diagnostic`
  - `test_c3_benchmark.py::test_R22_un_bh_a_rendement_non_fini_sur_des_bougies_finies_rend_la_paire_non_comparable`
  - `test_c3_select.py::test_R22_une_nav_extreme_a_rendement_non_fini_retire_le_candidat_par_D4`
  - `test_c3_verdict.py::test_R22_un_non_fini_fourni_dans_l_estimabilite_declaree_est_un_diagnostic`

## Hors réserve — contrat du producteur (0/2/3)

- **Imposé par** : le contrat de codes du producteur C3b (brief `agent/AGENT_C3B_PRODUCTEUR.md`), pas le protocole.
- **Fichier** : `scripts/audit/c3b_evaluate.py:544` — `cb.build_pair` appelé hors du `try` de l'étape 10b
  (`:1089-1118`) ; une `OverflowError` y sort en trace, code 1.
- **`xfail` à lever (1)** : `test_c3b_evaluate.py::test_hors_R_a_comparator_cagr_overflow_is_a_control_error_3`.

## Décompte

46 tests `xfail` strict : R-15 9, R-16 10, R-17 5, R-18 5, R-19 6, R-20 4, R-21 2, R-22 4, hors réserve 1.
`results/c3_v2_2/tests/gate.sh` vérifie que l'ensemble des `xfailed` de la suite est exactement cette liste.
