# C3 — Outillage v2.3, lot 1 : lever X1-X8 — rapport de lot

Brief : `agent/AGENT_C3_OUTILLAGE_V2_3.md` (commité tel que reçu, sha256_16 `844ca5377609bc7c`). Plan approuvé :
`results/c3_outillage_v2_3/plans/lot1.md` (GO de Bruno le 30/09 ; décisions D1-D13, D13 tranchée par Bruno à la
question du plan). Branche `feat/c3-outillage-v2.3` depuis `dev` @ `b50f2d15150f90a6d6ceb7ab2d41f8b1f495ecf9`, poussée,
**non mergée**. Protocole v2.3, sha256 `d030ab239de317f6cba89877d682338fa2001d2a63d231f1a86c519fe87a79e6`, recalculé à
chaque commit par `interdits.sh` : inchangé.

## 1. Livré, commit par commit

| Commit | Objet | Marqueurs levés |
|---|---|---|
| `f73727c3b5e35586a443bde918a8bcf8fb985848` | brief tel que reçu, plan du lot 1 (GO), scripts de preuve, mesures de base | — |
| `318e51be343f330f025041a1fe2e5651b581b638` | **D9** : renommage du test au nom périmé (`…_sous_v21` → `…_sous_le_protocole_courant`), nom seul | — |
| `d7362f05638479cd6e1f5cf34899736233ed5327` | **la clé** : `load_manifest` exige `deferred_evaluation.date` (forme, code 2 dans tout module) ; `c3_anchor.assert_deferred_date` à l'étape 1, ≥ 365 j après `window.end`, sinon `R0_INVALID_RUN` (D3) ; `cc.DEFERRED_MIN_DAYS` hors `THRESHOLDS` ; fixtures D8 | X1, X2, X8 |
| `382bea050e1a7d5323e93e5d213ffafc0db0c7ef` | **le verdict** : descripteur `D` dans `c3_common` (D1, D2) ; `cv.deferred_descriptor`, `Decision.delta_hat`, `cv.opens_deferred_way` (D4) ; inscription `deferred_evaluation {date, variant_key}` en mode `chain`, code 0, une fois par famille, écrite une fois, jamais imprimée (D5) ; **D13** : la ligne du registre écrit sans digest ; tests neufs N1, N3, N4 | X3, X4, X5 |
| `18a321250f72a935f5f8517c6b1f5e17370bd5a4` | **l'ancrage** : `cc.deferred_descriptor_at_run`, `stop_criterion` compare `sig(canon(D))` re-dérivé du manifeste entrant, refus sans empreinte (D6) ; test neuf N2 | X6 (témoin R-17), X7 |
| C5 (ce fichier) | `lot1/README.md`, `tests/*.sh` et `.out`, `mutants.log` | — |

Chaque marqueur a été levé au commit où son test sortait en XPASS strict, constaté avant le retrait, et à aucun autre
(ordre D11 : verdict avant ancrage, pour que X7 ne passe qu'une fois sa règle entière en place — un verdict qui
n'inscrit rien « n'inscrit jamais »). Code touché : `scripts/audit/c3_common.py`, `c3_anchor.py`, `c3_verdict.py`, et
rien d'autre sous `scripts/` ni `src/`.

**Interface retenue** (les appels des X, figés par leurs corps) : `Manifest.deferred_evaluation_date` (datetime UTC),
`cc.MissingEvidenceError` pour toute forme invalide, `cv.deferred_descriptor(campagne, bloc_retenu)`, bloc de registre
`deferred_evaluation {date, variant_key}` à côté de `verdict`. Ajouts : `cc.DEFERRED_MIN_DAYS`,
`cc.deferred_descriptor_at_verdict`, `cc.deferred_descriptor_at_run`, `cv.opens_deferred_way`,
`cv.deferred_evaluation_block`, `c3_anchor.assert_deferred_date` ; `stop_criterion`, `register` et
`registry_inscription` reçoivent un argument de plus (aucun test ne les appelle directement, constaté).

## 2. Tests

- **Suites** (`tests/suite_*.out`, sans tunnel, greffon `gate_sans_tunnel`, sans les 24 `_full`, chacune sur l'arbre
  committé ensuite sans modification entre les deux) :

  | Étape | Passés | Ignorés | Désélectionnés | xfail | Échecs / XPASS |
  |---|---|---|---|---|---|
  | base (`b50f2d1`, mesurée au C0) | 3 309 | 19 | 24 | 9 | 0 |
  | C1 renommage | 3 309 | 19 | 24 | 9 | 0 |
  | C2 la clé | 3 312 | 19 | 24 | 6 | 0 |
  | C3 le verdict | 3 318 | 19 | 24 | 3 | 0 |
  | C4 l'ancrage | **3 321** | 19 | 24 | **1** (le caduc) | 0 |

- **Comptes** (`tests/comptes_C4.out`, rc=0) : collectes à `b50f2d1` (worktree détaché) et au tip ; retiré = l'ancien
  nom du test renommé, seul ; ajoutés = son nom neuf + les quatre tests neufs (`tests/declares_lot1.txt`) ; levés =
  exactement les huit déclarés ; xfail du tip = xfail de la base moins les levés ; équation 3 309 + 8 + 4 = 3 321 ; le
  `-k` écarte exactement les 24 `test_determinism_parallel_vs_serial_full`.
- **Diff des tests** (`tests/diff_tests_C4.out`, rc=0, AST contre `b50f2d1`, onze fichiers C3) : les huit X levés,
  **corps identiques**, décorateurs = ceux de la base moins le seul `xfail` ; le renommé, nœud identique sous son nom
  neuf ; corps modifiés = les deux déclarés (`fx.manifest`, `_campaign_v21_manifest`, D8) ; fonctions neuves = les
  quatre déclarées ; aucune fonction retirée, aucun autre xfail touché (le caduc intact). Hors AST : une ligne
  `import copy` ajoutée à `test_c3_verdict.py` (N4).
- **Rouge avant** (`tests/rouge_avant_C3.out`, `rouge_avant_C4.out`, rc=0) : les quatre tests neufs lancés dans un
  worktree à `b50f2d1` avec les fichiers de test courants — tous rouges. N3 échoue sur son témoin (aucune inscription),
  N2 sur la règle (le témoin est refusé : `(2, True)` au lieu de `(0, False)`) ; **N1 et N4 échouent sur l'interface
  absente** (`Decision` sans `delta_hat`, `cv.deferred_descriptor` absent), comme X5 au gel : leur morsure sur la règle
  est prouvée par les mutants (§ 3 : M5-M8 pour N1, M10e-g pour N4).
- **Fin** (`tests/xfail_fin.out`, rc=0) : seul `test_hors_R_a_comparator_cagr_overflow_is_a_control_error_3` (le caduc
  déclaré au chantier v2.2) reste xfail.

Tests neufs (D10, écart déclaré au § 4) :

| # | Test | Ce qu'il porte |
|---|---|---|
| N1 | `test_c3_verdict.py::test_A6_v23_le_predicat_d_ouverture_suit_le_10_1_conjonctif_par_conjonctif` | table du § 10.1 recopiée : témoin, chaque porte Q seule en échec, `Δ̂_σ = 0`, `Δ̂_dd < 0`, `validé`, `réfuté`, `F_NOT_ESTIMABLE` |
| N2 | `test_c3_anchor.py::test_A6_v23_sur_une_famille_close_le_descripteur_entrant_suit_la_regle_du_run_differe` | colonne « Recoupement au run différé » : témoin accepté ; provenance `unknown`, deux candidats → refusés ; aucune empreinte (inscrite, dérivée) dans stdout, stderr, sorties |
| N3 | `test_c3_verdict.py::test_A6_v23_une_evaluation_differee_inscrite_differente_est_une_violation_sans_empreinte_imprimee` | inscription écrite une fois : bloc différé altéré → code 1, registre intact ; ni empreinte ni digest du registre (D13) imprimés |
| N4 | `test_c3_verdict.py::test_A6_v23_tout_champ_hors_de_la_table_est_hors_engagement` | « tout champ hors de cette liste est hors engagement » : `research_log_entry`, `run_scope`, `variant_id`, `protocol_sha256`, paramètres de procédure, provenance, clés en trop, autre paire, autre stratégie → `D` inchangé hors `deferred_evaluation_of` |

## 3. Mutants (`../mutants.log`, `tests/mutants_lot1.sh`, `tests/mutant.sh`)

39 mutants, un à la fois, après C4 (HEAD `18a321250f72a935f5f8517c6b1f5e17370bd5a4`) : substitution littérale unique
dans l'un des trois modules, tueurs lancés, fichier restauré par `git checkout`, diff vide vérifié, tueurs relancés.
**Tous : rouges sous le mutant, restaurés (diff vide), verts ensuite** (`mutants_lot1 rc=0`). Chaque tueur est un test
nommé ; les identifiants complets sont au journal. Les tests d'une même ligne sont lancés **ensemble** contre le
mutant (`mutant.sh`) : pour une ligne à plusieurs tueurs, le constat est l'échec de ce lancement commun — au moins l'un
d'eux rougit —, pas l'échec de chacun.

| # | Mutant (règle) | Tué par |
|---|---|---|
| M1 | `load_manifest` lit le bloc en optionnel (absent → date par défaut) | X1, X8 |
| M2 | borne `≥ 365 j` devenue `> 365 j` | X2 (témoin 365 j) |
| M3 | 365 → 364 | X2 (`364_jours`) |
| M4 | contrôle de la date retiré de l'étape 1 | X2 |
| M5 | prédicat : conjonctif issue/raison retiré | X4 (`valide`), N1 |
| M6a-c | prédicat : Q1, puis Q2, puis Q3 ignoré | N1 |
| M7 | prédicat : `Δ̂` ignoré | N1 |
| M8 | prédicat : `Δ̂ > 0` devenu `Δ̂ ≥ 0` | N1 (`Δ̂_σ = 0`) |
| M9.1-10 | `D` : chacun des dix champs omis, un par un | X5 |
| M10a | `D` : `engines` non restreint | X5 |
| M10b | `D` : `pair_costs` non restreint | X5, X6 |
| M10c | `D` : `decision_timeframes` non trié | X5, X6 |
| M10d | `D` : surcharge par candidat ignorée | X5 |
| M10e | `D` au verdict : provenance de la campagne au lieu de `clean` | N4 |
| M10f | `D` : `data` entier (clés hors table comprises) | N4 |
| M10g | `D` : `research_log_entry` ajouté | X5, N4 |
| M11a | run différé : `deferred_evaluation_of = sig(entrant)` | X6 |
| M11b | run différé : fenêtre prise de la date différée de l'entrant | X6 |
| M11c | run différé : provenance constante `clean` | N2 |
| M11d | run différé : premier candidat au lieu de l'unique | N2 |
| M12a | ancrage : empreinte brute du manifeste (état v2.2) | X6 |
| M12b | ancrage : tout accepté sur famille close | adverse R-17 (`test_R17_sur_une_famille_close_une_autre_empreinte_que_la_differee_est_refusee`) |
| M13 | garde « une fois par famille » retirée | X7 |
| M14 | bloc différé ignoré à la réinscription | N3 |
| M15a | ancrage : empreinte dérivée imprimée dans le refus (préfixe 16) | N2 |
| M15b | verdict : bloc différé interpolé dans la violation de discordance | N3 |
| M15c | verdict : bloc différé imprimé sur la ligne d'inscription | X3 |
| M15d | verdict : digest du registre rétabli sur la ligne d'inscription (D13) | N3 ; et `non_divulgation.sh` (rc=1 sous le mutant, 0 après) |

Le contrôle statique `non_divulgation.sh` a aussi mordu **à la base** (`non_divulgation_base.out`, rc=1 : le seul site
était la ligne du digest du registre, `c3_verdict.py:1882`, que D13 retire) ; 0 site à C3 et C4.

## 4. Écarts à la porte du brief

| Critère du brief | Constat | Ce qui le couvre |
|---|---|---|
| « 3 317 passés (3 309 + 8 levés) » | **3 321** : quatre tests neufs (D10), sans lesquels des mutants exigés par le brief survivaient (conjonctif Q, `Δ̂`, provenance au run différé, unique candidat, champs hors table, réinscription) | plan D10 ; `comptes_C4.out` |
| « Corps des huit tests X identiques hors levée des marqueurs » | tenu ; tests verts modifiés : `fx.manifest` et `_campaign_v21_manifest` (D8) | `diff_tests_C4.out` |
| Renommage « `test_c3_entry.py:709` » | la définition est à la ligne **706** (709 est dans la docstring) ; nom seul | D9 ; `diff_tests_C4.out` |
| Rien d'imprimé qui porte l'empreinte | tenu, **et** le digest du registre ne l'est plus du tout (D13, décision de Bruno) : changement de la ligne `written <registre> …` du verdict | D13 ; N3 ; `non_divulgation_C4.out` |

## 5. Décisions, limites déclarées, obligations au lot 2

Décisions appliquées : D1-D13 du plan, sans écart. En particulier :
- **D2** : les valeurs de `D` sont celles que le manifeste déclare, sauf les deux instants de `window`, normalisés en
  UTC (un instant est engagé, pas sa graphie). **Limite dite** : aucun test ne discrimine cette normalisation (toutes
  les fixtures écrivent déjà `+00:00`) et aucun mutant ne la vise ; candidat de test pour un lot ultérieur.
- **D4** : dans `decide()`, `F_CANNOT_SEPARATE` n'est atteint qu'après `Q1 ∧ Q2 ∧ Q3` ; le conjonctif Q du prédicat est
  gardé parce que le texte le nomme, et seul N1 (test pur) le fait tomber.

Limites déclarées (non implémentées, candidates v2.4) :
- **D12 — « une fois » pour le run différé lui-même** : après le verdict de la variante différée, la famille porte deux
  verdicts comptés et l'empreinte inscrite reste acceptée ; un second manifeste de même `D` passerait. Le texte renvoie
  la mécanique du run différé à un amendement ultérieur (AM-01, « Limites dites »).
- **D13 — `anchor.json.registry.sha256`** (et, par transitivité, le digest imprimé d'`anchor.json` qui le contient) :
  digest d'un fichier qui porte l'empreinte, inchangé parce qu'il fait partie du contrat de chaîne. Fermeture
  structurelle proposée par Bruno : un **sel aléatoire à la racine du registre**, écrit à la création du registre de
  campagne, qui rend tout digest non inversible sans lire le registre ; elle relève de la conversation manifeste et
  exigera son propre item d'outillage — `load_registry` rend aujourd'hui `{"variants"}` seul et jette toute autre clé
  de racine à la réécriture (`c3_anchor.py:218`).
- **D13 — taille du registre** : elle diffère quand un bloc différé est inscrit ; couverte par la règle de non-lecture
  (aucun listing de tailles).

Obligations transmises au lot 2 :
- le manifeste de conformité v2.3 déclare `deferred_evaluation.date` ≥ 365 j après `window.end` (2020-12-28) — une
  déclaration, jamais une fenêtre lue ; garde-fou 6 inchangé (il ne lit que `window`) ;
- la porte § L.5 cite le test par son nom neuf (D9) ;
- les vérificateurs ne listent jamais la taille du registre (D13) ; la ligne `written <registre> (issue inscrite, § A.6)`
  ne porte plus de digest (constaté : `verify_attendu.py` v2.2 ne la lisait pas).

## 6. Défauts du lot, dits comme tels

- **`non_divulgation.sh`, première version** (avant C0, non committée) : le motif `derived|inscri` prenait une
  dizaine de noms existants sans rapport (`derived_identity`, `derived_status`, le triplet `inscription` du verdict
  v2.2) et doublait chaque signalement. Resserré à `deferred|descriptor` (convention de nommage du lot : tout objet qui
  porte l'empreinte ou le descripteur a l'un de ces mots dans son nom), dédoublonné, avant tout commit.
- **Le même contrôle, au C3** : il a signalé `cc.DEFERRED_MIN_DAYS` dans le message de refus de la date, écrit au C2.
  Je ne l'avais pas lancé au C2 (il était rouge par construction sur le digest du registre, que C3 retire) : le signal
  est donc arrivé un commit plus tard qu'il aurait pu. Constante publique, exceptée par son nom avec la date déclarée
  (`deferred_evaluation_date`) ; aucune ligne de code changée pour cela.
- **N3, première version** : l'empreinte altérée était `"0" * 64` ; sa préfixe de 16 zéros vit dans les NAV décimales
  de `benchmark.json`, et le test échouait sur un faux positif. Remplacée par une empreinte calculée, avant le commit.
- **`rouge_avant.sh`, premier lancement** : le chemin du worktree était mal retiré des lignes d'échec (préfixe
  `/private` de macOS) ; cosmétique, corrigé, relancé.
- **N1 et N4 naissent rouges sur l'interface absente**, pas sur la règle (§ 2) : leur morsure sur la règle n'est prouvée
  que par les mutants.
- **`interdits_adverse.sh` n'a pas de cas pour `gel_v2_3.patch`** : ce fichier non suivi n'est pas à ce chantier et n'est
  jamais touché, même temporairement ; son contrôle (sha256_16 inchangé) n'est donc pas prouvé par un cas dévié.

## 7. Tunnel, base, lint, interdits, CI

- **Tunnel** (`tests/tunnel.out`) : fermé au départ ; ouvert à 16:45:25Z ; les six fichiers qui portent les tests
  base lancés sans le greffon, sans les 24 `_full` (`tests/base_db_C4.out`) : 92 passés, **plus aucun test ignoré pour
  base injoignable** (13 l'étaient dans la suite sans tunnel, `suite_C4.out`) ; fermé à 16:50:34Z, **`nc -z` échoue**
  (vérifié par le script et à la main). Base en lecture seule ; rien d'écrit.
- **Lint** (`tests/lint_C2.out`, `lint_C3.out`, `lint_C4.out`, base `lint_base.out`) : ruff check et `format --check`
  (liste CI) verts, `ruff check .` vert, `mypy src/` = **65**, mypy strict `c3_common` 4 / `c3_anchor` 0 /
  `c3_verdict` 0, égal à la base. Formatter lancé sur les fichiers nommés seulement ; hunks vérifiés par
  `git diff -U0` : tous dans les zones du lot.
- **Interdits** (`tests/interdits_C0.out` à `interdits_C4.out`, rc=0 à chaque commit, fichiers indexés) : chemins gelés
  intacts contre `b50f2d1` (dont `src/`, `scripts/backtest.py`, runners, `rejeu_common.py`, `c3b_*.py`, protocole et
  paquets v2.1-v2.3, répertoires des chantiers clos) ; sha256 recalculé du protocole = dernière ligne consignée du
  paquet v2.3 ; liste blanche du lot ; `gel_v2_3.patch` non suivi et inchangé ; aucun artefact du chemin, aucune
  empreinte de 64 hex hors table d'Adoption ; `CAMPAIGN_UNLOCK` absent ; aucun script qui nomme le répertoire de la
  dette 23. Mordant prouvé : `tests/interdits_adverse.out` (témoin 0, dix cas déviés ≠ 0, tout restauré).
- **CI** (`tests/ci_status_C4.out`) : run `36746018801` sur `18a321250f72a935f5f8517c6b1f5e17370bd5a4`, **succès en
  tentative 1**, aucune relance. La CI de ce commit (C5) est donnée au message de fin de lot.
- **Aucun** serveur, migration, artefact du chemin sélection, sha d'artefact versionné ; `CAMPAIGN_UNLOCK` jamais créé.
