# C3 — Outillage v2.2, lot 1 (chaîne pure : R-15, R-21, R-22, R-17) — plan soumis au GO

## Contexte

v2.2 est adoptée « texte et tests seulement » (46 `xfail` strict, `scripts/audit/*.py` inchangés depuis `8689636`).
Le brief `agent/AGENT_C3_OUTILLAGE_V2_2.md` découpe l'outillage en trois lots, une session par lot, plan d'abord.
Cette session = **lot 1**. Liste close : `results/c3_v2_2/outillage_v2_2.md`. Branche `feat/c3-outillage-v2.2`
depuis `dev = 8c114fe` (arbre propre ; seul le brief est non suivi). Rien n'est écrit avant le GO.

La lecture du code et des tests (tout `c3_verdict.py`, `c3_anchor.py`, `c3_benchmark.py`, fixtures de
`test_c3_common.py` / `test_c3_verdict.py`, tests producteur) fait apparaître **des contraintes que le brief ne
voit pas** : elles fixent plusieurs choix, et d'autres sont des trous de texte. Elles sont au § 1, avant le détail.

## 0. GO reçu (29/09, texte du relecteur relayé par Bruno) — conditions intégrées ci-dessous

D1, D2, D4, D8, D9, D10, D11, D13 accordés tels que recommandés. D5 accordé **sous condition** (réponse au § 1,
ligne D5). D12 accordé **avec obligations au lot 2** (ligne D12). D3, D6, D14 consignés candidats v2.3. D7 consigné
avec la mention **« prérequis probable v2.3 avant campagne »** (mini-amendement à trancher en conversation manifeste,
pas après : si l'issue `inconclusif` attendue de la première campagne ouvre la voie de sortie du § 10.1, D7 ferme
exactement ce chemin — à vérifier au texte là-bas). Ce texte s'adressait à Bruno ; l'approbation de ce plan vaut son
GO avant toute écriture git.

## 1. Décisions (recommandations ; statut au § 0)

| # | Nature | Question | Recommandation et motif |
|---|---|---|---|
| D1 | écart au brief (découpage) | Où va **R-15 côté producteur** (λ dans `evaluation.json`, NAV dans `benchmark_eval.json`) ? | **Au lot 1.** Sans lui, R-15 chaîne casse trois tests verts : `test_the_full_chain_verifies_a_produced_evaluation` (producteur → `chain`, exige λ et NAV), et les jeux de clés `fx.evaluation` / `fx.benchmark_eval` épinglés au producteur (`test_c3b_evaluate.py:1021`, `:1825`, `:1358`), que la chaîne oblige à compléter. Le brief se contredit : texte 19/27, décompte « 20 / 26 » — celui-ci suppose déjà R-15 entier au lot 1. |
| D2 | architecture imposée | R-15 dans `decide()` : inconditionnel ou conditionné ? | **Conditionné à la présence des entrées v2.2** dans le dictionnaire d'artefacts (`manifest`, `benchmark`, `candles_eval`, `benchmark_eval` : toutes ou aucune, présence partielle = erreur d'entrée) ; la couche fichier (`run_verdict`, modes verdict et chain) les **exige toujours** (fichier absent → code 2). C'est la seule forme qui ne touche aucun attendu : le test R-15 « un ulp » exige que `_reseries` laisse `equity_daily` intact, alors que ~15 tests `decide` sur `_sound()` passent des séries arbitraires qu'aucune `equity` ne reproduit au bit (granularité de `E_t/E_{t−1}−1` : 2⁻⁵²). Même forme que le « contrat de couche » déjà écrit dans la docstring de `decide`. Trou résiduel → D8. |
| D3 | **trou de texte** (STOP) | Abstention où l'étape 3 n'a publié **aucun λ** pour la configuration évaluée (non estimable au préfixe) : que font les recoupements λ et `returns_bench` ? | **Sans objet dans ce seul cas** (lu sur `benchmark.candidates[id].estimable`) ; avec une configuration retenue, λ non publié = violation. `returns_config ← equity_daily`, NAV et règle d'entrée de l'export restent recalculés. Imposé par deux tests verts : `test_revue_Fin_1_confinement_au_niveau_chain[abstention]` (`_all_d3`, λ nuls) et le test producteur ci-dessus (abstention, λ simulés). Candidat v2.3. |
| D4 | interface | Le verdict seul (étape 6 hors `chain`) lit-il les quatre entrées ? | **Oui**, `--manifest --benchmark --candles-eval --benchmark-eval` obligatoires ; `test_le_parseur_n_expose_que_des_chemins_et_un_horodatage` (`test_c3_verdict.py:418`, ensemble exact) complété de ces quatre chemins (§ 0.6 tenu : que des chemins). Sinon l'étape 6 publierait sans recoupement. |
| D5 | forme | Les nouveaux liens d'empreinte entrent-ils dans `chain.checks` ? | **Non : violations par `cc.check_inputs_match`** (forme de tous les autres modules) — `anchor.manifest`, `selection.benchmark`, `continuity.benchmark_eval` ; `candles_eval` haché dans `verdict.inputs_sha256`. `len(checks) == 17` (`:1824`, `:2090`) intact ; `chain.verified` passe à faux sur toute violation, comme aujourd'hui. **Condition du GO, réponse : les fichiers sont re-hachés, pas seulement des liens déclarés.** `cc.check_inputs_match` calcule `file_sha256(path)` du fichier effectivement fourni au verdict (`c3_common.py:1061`) et le compare à l'empreinte que l'amont a enregistrée : `benchmark.json` contre `selection.inputs_sha256.benchmark`, `benchmark_eval.json` contre `continuity`, le manifeste contre `anchor`. `candles_eval.json` n'a aucun amont qui l'enregistre (entrée hors chaîne) : il est re-haché dans `verdict.inputs_sha256` (enveloppe), et son contenu est rejoué (R-15). **Écart de lettre déclaré** : ces liens vivent dans une fonction sœur appelée par `run_verdict` juste après `verify_chain`, pas dans `verify_chain` même — y entrer en `checks` changerait le compte de 17. |
| D6 | trou de texte | L'inscription R-17 (étape 6) en mode verdict seul ? | **Mode `chain` seul** (seul à porter `--registry`, comme le dit l'impact d'AM-05). Le verdict seul n'inscrit pas : consigné, candidat v2.3. |
| D7 | **trou de texte** (STOP), écart à la liste close | Inscription de l'**évaluation différée** (date déclarée, empreinte attendue) : d'où `c3_verdict` tire-t-il la date et le manifeste de l'évaluation différée ? | **Le texte ne le dit pas → non implémentée** (jamais « en convention »). La lecture côté ancrage est livrée (bloc différé inscrit → seule son empreinte passe ; testée + témoin). Conséquence dite : une famille close par un `F_CANNOT_SEPARATE` ouvrant la sortie refusera tout, évaluation différée comprise, tant que le texte ne dit pas la source. Candidat v2.3, bloquant campagne à trancher en conversation manifeste. |
| D8 | tests neufs hors brief | Deux adverses de plus ? | **Oui** : (A1) R-15 **par la CLI** (monde ulp écrit sur disque → code 1) — sans lui, le mutant « `run_verdict` ne transmet pas les entrées v2.2 » survit à toute la suite (règle agent 1) ; (A2) R-17 **réinscription discordante** → violation, registre inchangé (règle écrite par AM-05, sans test). |
| D9 | effet de bord R-17 | La famille obligatoire fait échouer `load_manifest` **avant** l'assertion du sha : les deux tests du livrable v2.0 (`test_c3_entry.py:706`, `test_c3_verdict.py:2526`, « `protocol_sha256` in err ») rougiraient. | **`c3_anchor` asserte le sha déclaré avant `load_manifest`** (refus R0 nommant `protocol_sha256`) : un manifeste d'un autre protocole n'est pas relu sous le schéma v2.2. Même besoin au lot 2 (`min_order_quote`). |
| D10 | épinglage | `OPTIONAL_FIELDS` += `verdict`, `deferred_evaluation` (enregistrement du registre) ; `NULLABLE_FIELDS` += `raison` (`null` pour `validé`/`réfuté`). | **Oui**, avec leur raison en commentaire ; `test_les_listes_…_closes_et_nommees` (`test_c3_common.py:145`) suit — la liste close impose déjà ces listes « en conséquence » au lot 2. |
| D11 | interface producteur | `test_the_full_chain_verifies_a_produced_evaluation` construit son argv `chain` à la main. | **Ajouter `--candles-eval eval_out/candles_eval.json`** (le producteur l'écrit déjà). |
| D12 | XPASS prévus | (a) `test_R18_un_refus_qui_porte_des_series_se_contredit` passera au lot 1 : son export omet l'estampille d'entrée, la chaîne (sans R-18) voit une évaluation non refusée au comparateur irreconstructible → violation C-3 → code 1 ; (b) l'item hors réserve (`raises=OverflowError`) : R-21 supprime l'exception de `cc.cagr_pct`, le CAGR non fini du comparateur est alors pris par `replay_bootstrap` → `f2_invalid_input`, code 3. | **Règle du brief : XPASS → marqueur retiré dans le commit qui le produit, rien d'autre**, déclaré. Le critère « 4 R-18 restent xfail » devient 3 (écart à la porte). (a) reste discriminant pour R-18 au lot 2 (route du refus : sans la règle, il rendrait `E_NO_BENCHMARK`, code 0). Si (b) échoue autrement qu'en XPASS → STOP. **Obligations transmises au lot 2 (au README du lot 1)** : (b) ne clôt pas l'item hors réserve sur le fond — le lot 2 applique le fix prescrit (`build_pair` dans le `try` de l'étape 10b) ou prouve qu'aucune autre exception ne sort de `:544` en code 1, écart déclaré dans les deux cas ; (a) est nommé au plan du lot 2 comme test vert que la route R-18 fera passer par l'admission du refus — s'il rougit, règle d'arrêt. |
| D13 | lecture | § 10.1 : « au moins un candidat retiré par D1, D2 ou D6 ». | **`selection.candidates[*].first_failed_gate ∈ {D1, D2, D6}`** (le gate qui l'a retiré, § A.11). |
| D14 | candidat v2.3 | Les sorties code 1 et 2 (non comptées au § 10.1) n'ont pas d'issue : rien n'est inscrit, l'ancrage ne peut pas les compter dans « la relance unique ». | Consigné, non implémenté. |

Noms d'interface **gardés tels que les tests les proposent** (aucun renommage) : `family`, `verdict {issue, raison,
compte}`, `deferred_evaluation {date, variant_key}`, `lambdas {dd, sigma}`, `--candles-eval`, entrées
`benchmark` / `candles_eval` / `benchmark_eval`. **Ajout déclaré** : entrée `manifest` du dictionnaire (coûts, `C`,
intervalle d'exécution du § C.3, lus comme le producteur, `c3b_evaluate.py:540`).

## 2. Ce qui est livré, par réserve (ordre des commits)

Commit 0 — `docs(agent)` : le brief tel que reçu + `results/c3_outillage_v2_2/plans/lot1.md` (ce plan, GO inclus).

### C1 — R-15 producteur (1 xfail) — `c3b_evaluate.py`, fixtures
- `evaluation.json` porte `lambdas = {dd, sigma}` : les flottants lus dans `benchmark.json` (`prefix_lambdas`,
  `:270-323`), exactement ; `benchmark_eval.json` porte `nav = [float(v) for v in bench.nav]` (`:576-581`).
- `fx.evaluation` : `lambdas` (défaut `{0.0, 0.0}`, cohérent avec le comparateur cash par défaut) ; `equity_daily`
  tirée de la série de config (`E_0 = C`, cumul en double) et `returns_config` = `r_t = E_t/E_{t−1}−1` sur elle
  (écrit depuis le texte, helpers `fx.equity_of` / `fx.returns_of`) ; `returns_bench` passé tel quel.
- `fx.benchmark_eval` : `nav` par défaut = B&H plein notionnel de l'export par défaut sur `[T, fin]` (`cb.build_pair`,
  comme `_v22_world`).
- Marqueur levé : `test_R15_evaluation_json_declares_the_prefix_lambdas_it_used`.

### C2 — R-15 chaîne (8 xfail + XPASS D12a) — `c3_verdict.py`
- `INPUT_NAMES` += `manifest`, `benchmark`, `candles_eval`, `benchmark_eval` ; parseurs (D4) ; `chain` :
  `--candles-eval` facultatif au parseur (le test du livrable v2.0 construit son argv sans lui) ; absent → la chaîne
  s'arrête avant le verdict, code 2, message nommé. `run_chain` passe manifeste, `benchmark.json` de l'étape 3,
  export et comparateur.
- `run_verdict` : liens d'empreinte (D5).
- `decide` (D2), après `_replay`/`_cross_check_replay`, lecture stricte puis recoupements au bit :
  1. `returns_config` = `cc.recompute_daily(equity_daily.values, days).returns` (la fonction du producteur) ;
  2. règle d'entrée de l'export : une seule paire = paire évaluée (sinon `EntryRefusedError` R0), `cb.load_candles`
     sur le manifeste réduit à cette paire (refuse `t > fin`) ;
  3. B&H `cb.build_pair(pair, …, start=T, end=fin, coûts/C/intervalle du manifeste)` ; non constructible sur une
     évaluation non refusée → violation (C-3) ; sinon `benchmark_eval.nav` == NAV recalculée au bit (C-4) ;
  4. si l'étape 3 a publié λ (`estimable`) : `evaluation.lambdas` == `λ_dd, λ_σ` exacts, puis `returns_bench[m]` ==
     `recompute_daily([float(v) for v in cb.blend_nav(nav, Decimal(str(λ_m)), C)]).returns` au bit ; sinon D3.
- Fixtures (déclarées) : `_artifacts` (séries passées par `equity_of`/`returns_of`, comparateur aussi — les tests
  « trajectoires identiques » restent identiques au bit ; `equity_daily`, `lambdas {0,0}`) ; `_reseries` (même
  arrondi, **sauf** dans un monde R-15 — clé `candles_eval` présente — où il ne remplace que les séries : test
  ulp) ; `_write_cli_inputs` (écrit les quatre entrées par défaut : `fx.manifest()`, λ = 0 cash, export `[T, fin]`
  réduit, comparateur avec NAV ; empreintes réelles du manifeste, `selection.benchmark`, `continuity.benchmark_eval` ;
  argv) ; `_chain_world` (λ lus dans le `benchmark.json` de la chaîne sonde, export écrit, `returns_bench` = blend
  recalculé, `lambdas` passés) ; `_chain_argv` (`--candles-eval`) ; `_v22_world` (entrée `manifest`, `estimable`,
  et les entrées posées **avant** son `_reseries`).
- Tests : D4, D11 ; A1 (D8) ; marqueurs levés : les 8 R-15 chaîne ; D12a si XPASS constaté.
- **Aucune entrée de test CLI n'a un comparateur non cash** (inventaire fait) : λ = 0 suffit à tous les mondes CLI.

### C3 — R-21 (2 xfail + XPASS D12b) — `c3_common.py`, `c3_select.py`
- `cc.cagr_pct` → `float | None` : `None` si un rendement est non fini ou `≤ −1`, ou si l'exponentielle déborde ;
  jamais d'exception. `recompute_daily` : champ `returns_finite`, σ `None` sur rendements non finis, rien d'autre
  ne change (`.returns` intact : le test producteur « ruine » attend toujours son `−1` avant tirage).
- D4 (`c3_select.py:342`) = `domain_ok ∧ returns_finite ∧ cagr_pct is not None`, détail par cause.
  `c3_benchmark.candidate_block` : déjà `first_failed: D4` dès que `cagr_pct` est nul (vérifié, aucune ligne).
- Branche `except OverflowError` de `c3b_evaluate.evaluation_series` devenue morte : constatée, laissée à l'item
  hors réserve (lot 2).

### C4 — R-22 cas 1 à 4 (4 xfail)
- cas 1 `c3_anchor.load_registry` : `cc.canon` sur tout le registre lu → `NonFiniteValueError` → diagnostic, code 1.
- cas 2 `c3_benchmark.PairBenchmark.to_dict` : `nav` en décimal (chaînes), `returns` `null` s'il n'est pas tout fini
  (personne ne relit ces deux champs : vérifié) ; `:436-438`, `:504-506` finis ou nuls par C3.
- cas 3 `c3_select` : couvert par D4 (C3) ; `mdd_report`/`recomputed` écrivables.
- cas 4 `c3_verdict._estimability_of` : `declared` ne recopie que `E1`, `E2`, `ok` ; un non-fini dans le bloc déclaré
  est une violation (ligne 15).

### C5 — R-17 (5 xfail + témoin + épinglage § 10.1) — `c3_common.py`, `c3_anchor.py`, `c3_verdict.py`
- `load_manifest` : `family` obligatoire (chaîne non vide) ; `Manifest.family`. D9. `fx.manifest` et
  `producer_manifest` (`test_c3b_common.py:88`) portent `family: "grid"`.
- `c3_anchor` : `RECORD_KEYS` += `family` (champs d'issue hors `RECORD_KEYS` : l'idempotence tient) ; pour une clé
  **nouvelle** seulement, sur les enregistrements de la famille : verdict compté → seule l'empreinte
  `deferred_evaluation.variant_key` inscrite passe, tout autre refus R0 ; sinon ≥ 2 verdicts non comptés → refus R0
  (relance au-delà de l'unique). D10.
- `c3_verdict` : constante `COUNTED` = table du § 10.1 (+ la ligne conditionnelle D13) ; en mode `chain`, avant
  toute écriture : variante absente du registre → violation ; verdict déjà inscrit identique → rien ; différent →
  violation (diagnostic, code 1, registre intact) ; sinon, après `verdict.json`, inscription `verdict {issue, raison,
  compte}`. Rien n'est inscrit hors code 0 (D14). Pas de différée (D7).
- Tests neufs : témoin « empreinte différée attendue acceptée » (`test_c3_anchor.py`) ; épinglage de la table du
  § 10.1 recopiée du texte (`test_c3_verdict.py`, rouge-avant : constante absente) ; A2 (D8).

### C6 — `docs(results)` : `lot1_chaine/README.md`, `tests/*.sh` + `.out`, `mutants.log`

## 3. Vérifications (toutes par `bash results/c3_outillage_v2_2/tests/*.sh`, `.out` committés, `pipefail`)

- `tunnel.sh` : tunnel ouvert au début (13 tests base exécutés), **fermé et vérifié fermé** (`nc -z` échoue) à la fin.
- `suite.sh` à chaque commit : suite entière `-k "not test_determinism_parallel_vs_serial_full"`, `-rxX` ; 0 échec,
  0 XPASS non retiré. Mutants lancés après la suite, jamais pendant.
- `comptes.sh` : ids collectés à `8c114fe` (worktree) et au tip ; supprimés = ∅ ; levés = la liste du lot (20 + D12) ;
  neufs = témoin, épinglage, A1, A2 ; et preuve que `-k "not test_determinism_parallel_vs_serial_full"` désélectionne
  **exactement** les 24 `_full` de la convention CI (collecte avec et sans `-k`, différence = ces 24 ids, rien d'autre).
- `xfail_reste.sh` : les R-18 de chaîne restés `xfail` rejoués en `--runxfail` — échec sur l'attendu, plus sur
  `--candles-eval` inconnue (comparé à `results/c3_v2_2/tests/xfail_rouge.out`).
- `diff_tests.sh` (AST contre `8c114fe`) : corps des tests levés identiques hors décorateur ; toute autre fonction
  modifiée ∈ liste déclarée (fixtures § 2, D4, D10, D11) ; aucune assertion d'attendu touchée.
- `mutant.sh` → `mutants.log` : témoin R-17 (refuser l'empreinte attendue → rouge), épinglage (une ligne de la
  constante inversée), A1 (`run_verdict` sans entrées v2.2), A2 (réinscription écrasée), D3 (λ jamais recoupés →
  le test R-15 λ rougit), D9 (pré-contrôle retiré → tests v2.0 rouges).
- `lint.sh` : ruff (liste CI + `ruff check .`), `mypy src/` = 65, mypy strict des `scripts/audit/` modifiés
  (`MYPYPATH=src:scripts:scripts/audit --follow-imports=silent --strict`) : base mesurée à `8c114fe`, aucun écart neuf.
- `interdits.sh` : `git diff 8c114fe` vide sur `src/`, `scripts/backtest.py`, runners P6/P7, `rejeu_common.py`,
  `docs/protocole_c3.md`, `docs/amendements_c3_v2.*`, `results/c3_v2_2/`, `results/c3b_producteur/`.
- Fin de lot : README (livré, tests, mutants, écarts au brief et à la liste close, candidats v2.3 D3/D6/D7/D14,
  défauts), assert de branche avant chaque commit, messages par `-F`, `git push -u origin feat/c3-outillage-v2.2`,
  CI lue par `gh` (relance pour `test_rejeu_effect` seul). Aucun merge.

**Écarts à la porte du brief** (table au README, comme la table d'écarts C3b) : décompte lot 1 = 20 + D12 (le « 19 »
du texte du brief était faux, son « 20 / 26 » juste) ; « 4 R-18 restent xfail » devient 3 ; `candidate_block` sans
ligne changée pour R-21 (constaté) ; tests verts modifiés : D4, D10, D11, `fx.manifest` / `producer_manifest`
(famille), fixtures du § 2 ; liens D5 hors `verify_chain` ; D7 non implémenté.

**Règle d'arrêt** : tout test vert à `8c114fe` qui rougit et que ce plan n'a pas nommé, tout attendu qu'il faudrait
toucher, tout besoin dans `src/` ou le moteur → STOP, rien d'arbitré.
