# C3 — Racine du registre (R-4), lot 1 : passthrough, test UTC, runbook — rapport de lot

Brief : `agent/AGENT_C3_RACINE_REGISTRE.md` (commité tel que reçu, sha256_16 `70f7069eafe74884`). Runbook :
`skills/registry.md`, le fichier joint `RUNBOOK_REGISTRE_CAMPAGNE.md` tel que reçu (sha256_16 `34686dc7c3eb2580`).
Plan approuvé : `results/c3_racine_registre/plans/plan.md` (GO de Bruno le 01/10 ; décisions D1-D10). Branche
`feat/c3-racine-registre` depuis `dev` @ `313eb00c2019b98cf20fb81ac8327f7b9d1e920a`, poussée, **non mergée**. Protocole
v2.3, sha256 `d030ab239de317f6cba89877d682338fa2001d2a63d231f1a86c519fe87a79e6`, recalculé à chaque commit par
`interdits.sh` : inchangé.

## 1. Livré, commit par commit

| Commit | Objet |
|---|---|
| `71061ed36d165a0447b8b941139ed521d2873050` (C0) | brief tel que reçu, plan (GO), inventaire-filet et sa preuve, `interdits.sh` et sa preuve, scripts repris de v2.3, mesures de base |
| `8915807b9acafcfce3404c8cf5e01f8b80f11d18` (C1) | `skills/registry.md`, le runbook tel que reçu (`cmp` identique, `tests/runbook_C1.out`) |
| `b8ed4b019fdc9cc0a1f9bf05a9074d643b8ccfb8` (C2) | **le passthrough** : `c3_anchor.load_registry` rend la racine lue (D1) et la contrôle par le critère du writer strict, jamais par `canon` (D2) ; `register` la rend telle quelle, des deux branches ; constante `fx.REGISTRY_ROOT_SYNTHETIC` (D4) ; tests T1, T2-chaîne, T2-verdict, T4 |
| `9b72662ccf4ce49717571fffde91ea31e47e9930` (C3) | test T3, la normalisation UTC des instants de `D` (D6) |
| C4 (ce fichier) | `lot1/README.md`, `tests/*.sh` et `.out`, `mutants.log` |

Code touché : `scripts/audit/c3_anchor.py` seul (`load_registry` `:233-260`, `register` `:263-307`, docstring du
module). **`c3_verdict.py` et `c3_common.py` : diff vide** (gelés pour ce chantier, D3 ; `interdits_C*.out`).

Le passthrough, tel qu'il est :
- `load_registry` : `variants` obligatoire et validé comme avant (mapping de mappings, `canon` des enregistrements,
  R-22 cas 1) ; toute autre clé de racine est rendue telle que `read_json` la donne, **jamais lue, réservée ni
  validée** ; ses valeurs passent `cc.dumps_canonical` (`allow_nan=False`) — un flottant non fini lève
  `cc.NonFiniteValueError` au message constant, sans valeur : violation, code 1, diagnostic, registre non réécrit.
- `register` : branche d'écriture `{**registre, "variants": mis_à_jour}` ; branche idempotente, le registre tel que lu
  (jamais écrit : `main` n'écrit que sur `new_entry`).

## 2. Inventaire-filet (brief § 3.1)

`tests/inventaire_filet.sh` → `inventaire_filet_C0.out` (rc=0), à la base : 50 occurrences des motifs (littéral de
racine, égalité au registre entier, clés de racine, octets ou sha du registre, lecture du fichier registre passée à
`set`/`sorted`/`list`/`len`) dans `tests/`, `scripts/audit/` et les vérificateurs et pilotes v2.3 repris au lot 2 ;
chacune classée par une table déclarée (fichier + fragment de ligne) : `defaut` 5 (le code corrigé ici), `octets_inchanges`
14, `entre_executions` 13, `simulation` 7, `hors_sujet` 4, `contrat_de_chaine` 3, `type_de_variants` 2, `variants_seul` 2.
**Aucun épinglage normatif de la racine** : aucune ligne de v2.4 nécessaire. Mordant prouvé
(`inventaire_adverse.out` : témoin 0 ; quatre épinglages fabriqués — égalité au littéral, `set(registry)`,
`registry.keys()`, `sorted(read_json(…))` — sortent en rc=1).

## 3. Tests

- **Suites** (`tests/suite_*.out`, sans tunnel, greffon `gate_sans_tunnel`, sans les 24 `_full`, chacune sur l'arbre
  committé ensuite) :

  | Étape | Passés | Ignorés | Désélectionnés | xfail | Échecs / XPASS |
  |---|---|---|---|---|---|
  | base (`313eb00`, mesurée au C0) | 3 321 | 19 | 24 | 1 (le caduc) | 0 |
  | C2 le passthrough | 3 325 | 19 | 24 | 1 | 0 |
  | C3 le test UTC | **3 326** | 19 | 24 | **1** (le caduc) | 0 |

- **Comptes** (`tests/comptes_C3.out`, rc=0) : collectes à `313eb00` (worktree détaché) et au tip ; **0 retiré** ;
  ajoutés = exactement les cinq déclarés (`tests/declares.txt`) ; équation 3 321 + 0 levé + 5 neufs = 3 326 ; ignorés
  et désélectionnés inchangés ; le `-k` écarte exactement les 24 `_full`.
- **Diff des tests** (`tests/diff_tests_C3.out`, rc=0, AST contre `313eb00`, onze fichiers C3) : aucun corps existant
  modifié, aucune fonction retirée ; neuves = les cinq déclarées ; affectation ajoutée = `REGISTRY_ROOT_SYNTHETIC`
  seule. Hors AST : l'import `from datetime import timedelta` élargi à `datetime, timedelta, timezone`
  (`test_c3_verdict.py`, T3) — seule ligne retirée des tests.
- **Rouge avant** (`tests/rouge_avant_C2.out`, rc=0) : T1, T2-chaîne, T4 lancés dans un worktree à `313eb00` avec les
  fichiers de test courants — **rouges sur la règle** : T1 « la première réécriture a jeté la racine », T2-chaîne la
  racine réduite à `['variants']`, T4 le non-fini de racine non diagnostiqué (code 0). **Vert avant**
  (`rouge_avant_C2_vert.out`, `rouge_avant_C3_vert.out`) : T2-verdict et T3 passent à `313eb00` — les propriétés étaient
  tenues (K2 du plan : le verdict préservait la racine ; D2 v2.3 normalisait déjà) ; leur mordant est prouvé par les
  mutants (§ 4).
- **Fin** (`tests/xfail_fin.out`, rc=0) : seul `test_hors_R_a_comparator_cagr_overflow_is_a_control_error_3` reste xfail.

Tests neufs (plan § 3) :

| # | Test | Ce qu'il porte |
|---|---|---|
| T1 | `test_c3_anchor.py::test_A6_la_racine_du_registre_survit_a_l_ancrage_enregistrement_idempotence_enfant` | registre écrit comme au runbook § 1 : racine intacte à l'enregistrement de la racine, octets inchangés à la relance idempotente, racine intacte à l'enregistrement d'un enfant ; valeurs synthétiques absentes de stdout, stderr, `anchor*.json` |
| T2-chaîne | `test_c3_verdict.py::test_A6_la_racine_du_registre_traverse_l_ancrage_et_l_inscription_du_verdict` | **l'adverse du brief** : un `chain` dans le monde de X3 (verdict et évaluation différée inscrits) ; racine intacte à l'octet ; rien d'imprimé |
| T2-verdict | `test_c3_verdict.py::test_A6_registry_inscription_preserve_les_cles_de_racine` | `cv.registry_inscription` seul, sans puis avec bloc différé, écrit par le writer de la chaîne : racine intacte à l'octet |
| T3 | `test_c3_verdict.py::test_A6_v23_les_instants_de_D_sont_normalises_un_instant_pas_une_graphie` | trois graphies (`+00:00`, `Z`, `+02:00`) × campagne × manifeste différé : `window` de `D` = l'instant UTC ; `D` ne dépend de la graphie de campagne que par `deferred_evaluation_of` ; l'empreinte re-dérivée à l'ancrage = celle du verdict, neuf couples |
| T4 | `test_c3_anchor.py::test_R22_un_non_fini_a_la_racine_du_registre_est_un_diagnostic` | `NaN` flottant à la racine : code 1, `invalide`, registre non réécrit ; témoin : la chaîne `"NaN"` traverse (valeur opaque) |

« À l'octet près » (D4) : pour chaque clé de racine en plus, `cc.dumps_canonical(avant) == cc.dumps_canonical(après)`
— JSON compact trié, **sans** `canon`, donc `7`, `7.0` et `"7"` sont distincts — et l'ensemble des clés de racine égal.

## 4. Mutants (`../mutants.log`, `tests/mutants.sh`, `tests/mutant.sh`)

Neuf mutants, un à la fois, au tip C3 (`9b72662`). **Chaque tueur nommé est lancé seul** contre le mutant (un mutant à
deux tueurs est appliqué deux fois) : rouge sous le mutant, fichier restauré (`git diff --quiet`), vert ensuite. Le
journal porte deux passes, toutes deux `rc=0` : la seconde ajoute la ligne d'échec de chaque tueur (`mutant.sh`
complété, § 6).

| # | Mutant | Tué par | Ligne d'échec (2e passe) |
|---|---|---|---|
| M1a | `load_registry` rend `{"variants"}` seul (état `313eb00`) | T1 ; T2-chaîne | « la première réécriture a jeté la racine » ; `['variants'] == ['racine_de_t…', 'variants']` |
| M1b | `register` (écriture) rend `{"variants": updated}` | T1 ; T2-chaîne | idem |
| M2a | `registry_inscription` : racine perdue | T2-verdict ; T2-chaîne | `KeyError: 'salt'` (§ 6) ; racine réduite à `['variants']` |
| M2b | `registry_inscription` : racine réécrite par `canon` | T2-verdict ; T2-chaîne | issues différentes ; valeur de `racine_de_test_typee` différente |
| M2c | `run_verdict` : registre canonicalisé au site d'écriture | T2-chaîne | valeur de `racine_de_test_typee` différente |
| M3a | `D` : la graphie du manifeste entre dans `window` (`isoformat` contourné, un seul site) | T3 | issues `False` sur les couples hors `+00:00` |
| M3b | `parse_datetime` sans `astimezone(UTC)` | T3 | idem (graphie `+02:00`) |
| M4 | contrôle de la racine retiré (D2) | T4 | `ValueError: salt: flottant non fini (nan)` levée par le writer strict — la trace nue que D2 interdit |
| M5 | `load_registry` imprime la racine sur stderr | T1 ; `non_divulgation.sh` | `'racine-de-test' not in …` ; `non_divulgation.sh` rc=1 sous le mutant, 0 après |

M2a-c et M3a-b portent sur `c3_verdict.py` et `c3_common.py`, gelés pour ce chantier : mutants temporaires seulement,
diff vide vérifié après chacun.

## 5. Écarts au brief et au plan (déclarés)

| Critère | Constat | Ce qui le couvre |
|---|---|---|
| Brief § 0.2 : le runbook joint | **absent du dépôt et de `~/Downloads`** à l'ouverture ; demandé à Bruno à la question du plan, déposé dans `~/Downloads/`, lu avant la soumission du plan | plan § 0 ; `runbook_C1.out` |
| Sortie : « 3 321 + les tests neufs du plan » | 3 326 = 3 321 + 5 | `comptes_C3.out` |
| Plan D6 : graphie `+02:00` | extension au brief (`Z` / `+00:00`), approuvée au GO ; seule graphie qui fait mourir M3b | T3 ; M3b |
| Plan § 6 : `vert_avant` | réalisé comme un mode de `rouge_avant.sh` (`<rouge|vert>`), pas un script séparé | `reprise_lot1_C4.out` |
| Plan § 4 : « tué par » | chaque tueur lancé **seul** contre le mutant (v2.3 les lançait ensemble) | `mutants.log` |
| Brief § 6 : `~/docker/` jamais nommé | le runbook, tel que reçu, nomme `~/docker/` et `~/c3/` ; aucun script du chantier ne les nomme (`interdits.sh`, contrôles 6 et 7) | plan K7 ; `interdits_C*.out` |

## 6. Décisions, limites, défauts du lot

Décisions appliquées : D1-D10 du plan, sans écart. Limites déclarées :
- **D1 — mise en page** : la racine est préservée en valeurs, pas en octets du fichier ; le writer réécrit avec
  `indent=2` et clés triées. Pour le fichier du runbook § 1 (`json.dumps(…, indent=2)`, clés déjà triées, ASCII), la
  mise en page coïncide : la première écriture n'ajoute que l'enregistrement.
- **D2 — côté verdict** : `registry_inscription` ne contrôle pas la racine ; un non-fini de racine y est inatteignable
  en `chain` (l'étape 1 le refuse avant, T4) et le verdict seul n'écrit pas de registre. Déclaré, aucun code.
- **K4 du plan** : `canon` aurait lu un sel hex de forme `chiffres e chiffres` comme un décimal et levé
  `decimal.Overflow` (p ≈ 5·10⁻¹³ par sel) ; c'est pourquoi la racine ne lui est jamais passée. La même lecture vaut
  toujours pour toute chaîne d'un **enregistrement** (classe préexistante, hors de ce chantier).
- **Inventaire-filet** : il est fait de motifs ; un épinglage écrit sous une forme hors motifs lui échapperait. Il
  porte sur la base (C0) : les tests neufs, eux, assertent l'ensemble des clés de racine **préservé** — l'inverse d'un
  épinglage à `{"variants"}`.

Défauts du lot, dits comme tels :
- **`inventaire_filet.sh`, première version** (avant C0) : sa table ne classait pas deux lectures de `variants` seul
  (`test_c3_anchor.py:509, :520`) que le motif élargi attrapait ; le **témoin** de `inventaire_adverse.sh` est sorti
  rouge. Table complétée, preuve rejouée, avant tout commit.
- **`interdits_adverse.sh`, première version** (avant C0) : il constatait le code de chaque cas, pas l'item qui mordait ;
  complété (`items_en_ecart`), rejoué : chaque cas dévié mord par son propre item.
- **`mutant.sh`, première passe** : la ligne d'échec du tueur n'était pas consignée ; un mutant aurait pu mourir d'un
  plantage étranger à sa règle. Complété, les neuf mutants rejoués ; les lignes d'échec sont toutes sur la règle.
- **T2-verdict sous M2a** : il échoue par `KeyError: 'salt'` sur sa propre lecture de la racine, avant son assertion —
  même cause (racine perdue), mais un diagnostic moins net qu'une assertion. Laissé tel quel, déclaré.
- **`interdits_adverse.sh` n'a pas de cas** pour `CAMPAIGN_UNLOCK` ni pour le répertoire du registre de campagne sous
  `$HOME` : ils ne sont jamais créés, même temporairement (brief § 6) ; leurs contrôles ne sont pas prouvés par un cas
  dévié.

## 7. Tunnel, base, lint, interdits, non-divulgation, CI

- **Tunnel** (`tests/tunnel.out`) : fermé au départ ; ouvert à 08:45:40Z ; les six fichiers des tests base lancés sans
  le greffon, sans les 24 `_full` (`tests/base_db_C3.out`) : 92 passés, **plus aucun test ignoré pour base
  injoignable** (13 l'étaient dans `suite_C3.out`) ; fermé à 08:51:40Z, **`nc -z` échoue**. Base en lecture seule.
- **Lint** (`tests/lint_base.out`, `lint_C2.out`, `lint_C3.out`) : ruff check et `format --check` (liste CI) verts,
  `ruff check .` vert, `mypy src/` = **65**, mypy strict `c3_common` 4 / `c3_anchor` 0 / `c3_verdict` 0, égal à la base.
  Formatter lancé sur deux fichiers de test nommés ; hunks tous dans les tests neufs (0 ligne existante retirée).
- **Interdits** (`tests/interdits_C0.out` à `interdits_C4.out`, rc=0 à chaque commit, fichiers indexés) : chemins gelés
  intacts contre `313eb00` (dont `src/`, runners, `rejeu_common.py`, `c3b_*.py`, `c3_common.py`, `c3_verdict.py` et les
  quatre autres modules de chaîne, protocole et paquets, `CONTRAINTES`, `CLAUDE.md`, résultats des chantiers clos) ;
  protocole au sha consigné ; liste blanche ; aucun artefact du chemin ; empreintes de 64 hex ⊆ table d'Adoption ∪
  fichiers du chantier (D10 : la seule est le sha du runbook) ; `CAMPAIGN_UNLOCK` absent ; dette 23 ; registre de
  campagne jamais nommé par un script, absent du `$HOME` local. Mordant : `interdits_adverse.out` (témoin et témoin
  positif D10 à 0, douze cas déviés ≠ 0, chacun par son item, tout restauré).
- **Non-divulgation** (`tests/non_divulgation_base.out`, `_C2`, `_C3`, `_apres_mutants`, rc=0 ; `_mutant_M5`, rc=1) :
  règles 1-3 du lot 1 v2.3 et règle 4 (D8) — 20 lignes ajoutées à `c3_anchor.py`, aucune n'imprime ni n'interpole.
- **CI** (`tests/ci_status_C3.out`) : run `36838326935` sur `9b72662ccf4ce49717571fffde91ea31e47e9930`, **succès en
  tentative 1**, aucune relance. La CI de ce commit (C4) est donnée au message de fin de lot.
- **Aucun** serveur, migration, artefact du chemin sélection ; aucun registre persistant ni sel réel créé ;
  `CAMPAIGN_UNLOCK` jamais créé.

## 8. Ce qui attend

- **GO du lot 2** (plan § 7) : conformité rejouée au SHA du chantier (manifeste v2.3 à trois chemins réécrits, entrée 22,
  trois exécutions 4/1/4), porte § L.5 par invariance prouvée, rapport final `results/c3_racine_registre/report.md`.
- Merge par Bruno après le lot 2 ; puis création du registre de campagne par Bruno (runbook § 1).
