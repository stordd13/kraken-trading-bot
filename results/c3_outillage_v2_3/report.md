Aucune donnée de la fenêtre de campagne 2021-03-01 → 2026-06-29 n'a été lue par le producteur ni par la chaîne, sur aucun run de ce chantier ; aucune issue de chaîne n'a été lue.

# C3 — outillage v2.3 : rapport final du chantier (lots 1 et 2)

**Fenêtre d'instrument, aucune portée économique.** Ce chantier livre le code qui applique le protocole C3 v2.3
(sha256 `d030ab239de317f6cba89877d682338fa2001d2a63d231f1a86c519fe87a79e6`) — AM-01, l'évaluation différée : clé
`deferred_evaluation.date`, descripteur `D`, non-divulgation —, puis rétablit sous v2.3 la conformité du producteur C3b
et de la chaîne sur le serveur. Celle du 30/09, prouvée sous v2.2, n'avait plus de valeur probante : sous v2.3,
`c3_anchor` refuse son manifeste. Le chantier ne dit rien de la famille grid : aucune métrique de candidat n'a été lue,
commentée ni reportée.

La phrase de la première ligne a une portée ; deux exceptions sont dites au § 8 : les 24 tests `_full` de la porte
§ L.5, et les 13 tests base de la suite, lancés par le tunnel au lot 1. Les deux lisent des données de la période de
campagne ; ce ne sont pas des runs du producteur, et aucune métrique n'en a été lue.

- **Brief** : `agent/AGENT_C3_OUTILLAGE_V2_3.md` (commité tel que reçu). **Paquet** : `docs/amendements_c3_v2.3.md`,
  section « Adoption » (réserves X1-X8).
- **Plans**, un par lot, chacun approuvé avant sa première écriture : `plans/lot1.md` (D1-D13 ; D13 tranchée par Bruno à
  la question du plan) et `plans/lot2.md` (K1-K9, D1-D10).
- **Branche** `feat/c3-outillage-v2.3`, partie de `dev = b50f2d1`. Deux lots, un GO par lot, poussée à chaque lot.
  **Aucun merge : il est fait par Bruno après relecture de ce rapport (STOP 2).**
- **Journal** : `docs/RESEARCH_LOG.md`, entrée 21, avec son issue.

## 1. Ce qui est livré

### Lot 1 — lever X1-X8 (`lot1/README.md`)

| Commit | Objet | Marqueurs levés |
|---|---|---|
| `f73727c` | brief tel que reçu, plan du lot 1 (GO), scripts de preuve, mesures de base | — |
| `318e51b` | **D9** : renommage du test au nom périmé (`…_sous_v21` → `…_sous_le_protocole_courant`), nom seul | — |
| `d7362f0` | **la clé** : `load_manifest` exige `deferred_evaluation.date` (forme, code 2 dans tout module) ; `c3_anchor.assert_deferred_date` à l'étape 1, ≥ 365 j après `window.end`, sinon `R0_INVALID_RUN` ; fixtures D8 | X1, X2, X8 |
| `382bea0` | **le verdict** : descripteur `D` dans `c3_common` ; `cv.opens_deferred_way` (§ 10.1, conjonctif par conjonctif) ; inscription `deferred_evaluation {date, variant_key}` en mode `chain`, code 0, une fois par famille, écrite une fois, jamais imprimée ; **D13** : la ligne du registre écrit sans digest ; tests neufs N1, N3, N4 | X3, X4, X5 |
| `18a3212` | **l'ancrage** : `cc.deferred_descriptor_at_run`, `stop_criterion` compare `sig(canon(D))` re-dérivé du manifeste entrant, refus sans empreinte ; test neuf N2 | X6 (témoin R-17), X7 |
| `a30d62a` | rapport du lot, preuves, 39 mutants | — |

Code touché : `scripts/audit/c3_common.py`, `c3_anchor.py`, `c3_verdict.py`, et rien d'autre sous `scripts/` ni `src/`.
Interface retenue (les appels des X, figés par leurs corps) : `Manifest.deferred_evaluation_date`,
`cc.MissingEvidenceError`, `cv.deferred_descriptor(campagne, bloc_retenu)`, bloc de registre `deferred_evaluation
{date, variant_key}` ; ajouts : `cc.DEFERRED_MIN_DAYS` (hors `THRESHOLDS`), `cc.deferred_descriptor_at_verdict`,
`cc.deferred_descriptor_at_run`, `cv.opens_deferred_way`, `cv.deferred_evaluation_block`,
`c3_anchor.assert_deferred_date`, `Decision.delta_hat` (jamais publié).

### Lot 2 — conformité serveur sous v2.3 et porte § L.5 (ce rapport)

| Commit | Objet |
|---|---|
| `dcef301` (C0) | plan du lot 2 (GO inclus) ; `interdits_lot2.sh` ; tunnel constaté fermé |
| `15e4cb9` (S1) | **SHA du run de conformité** : entrée 21, attendu, manifeste v2.3, deux pilotes, `verify_attendu.py`, scripts de procédure repris du lot 3 v2.2 (`reprise_lot2.out`), `manifest_check`, `events`, `pilot_dryrun`, `verify_adverse`, `interdits_lot2_adverse`, `lint_lot2`. **Aucun code** |
| S2 | preuves de la conformité (codes et booléens) ; **SHA de la porte § L.5** |
| S3 | preuves de la porte, ce rapport, issue de l'entrée 21 |
| S4 | statut CI de S3 |

**Le lot 2 n'écrit aucun code** : diff vide contre `a30d62a` sur `scripts/ tests/ src/ config/ pyproject.toml
poetry.lock .github/ agent/ skills/` et les docs gelées, à chaque commit (`tests/interdits_lot2_*.out`).

## 2. Tests

| Étape | Passés | Ignorés | Désélectionnés (`_full`) | xfail | Échecs / XPASS |
|---|---|---|---|---|---|
| base (`b50f2d1`) | 3 309 | 19 | 24 | 9 | 0 |
| C1 renommage | 3 309 | 19 | 24 | 9 | 0 |
| C2 la clé | 3 312 | 19 | 24 | 6 | 0 |
| C3 le verdict | 3 318 | 19 | 24 | 3 | 0 |
| fin du lot 1 (`18a3212`) | **3 321** | 19 | 24 | **1** (le caduc) | 0 |
| lot 2 | inchangé : aucun code, aucun test | | | | |

- **Décompte** : 3 309 + 8 levés + 4 neufs = 3 321 (`tests/comptes_C4.out`, par diff d'identifiants contre `b50f2d1`).
  Aucun test retiré ; un renommé (D9). Le seul xfail restant est le caduc déclaré au chantier v2.2
  (`test_hors_R_a_comparator_cagr_overflow_is_a_control_error_3`).
- **Corps des huit X identiques** au gel, décorateurs = base moins le seul `xfail` (`tests/diff_tests_C4.out`, AST).
- **Tests neufs** (D10), nés rouges à `b50f2d1` (`tests/rouge_avant_C3.out`, `rouge_avant_C4.out`) : N1 prédicat du
  § 10.1 conjonctif par conjonctif ; N2 descripteur au run différé (provenance déclarée, unique candidat), non-divulgation
  à l'ancrage ; N3 réinscription différée discordante, ni empreinte ni digest du registre imprimés ; N4 tout champ hors
  table hors engagement.
- **Les 13 tests base** passent tunnel ouvert (`tests/base_db_C4.out`), tunnel fermé ensuite, vérifié.
- **CI verte en tentative 1, sans aucune relance**, à chaque SHA poussé :

  | SHA | Run |
  |---|---|
  | `18a3212` (fin du code, lot 1) | 36746018801 |
  | `a30d62a` (lot 1) | 36747302318 |
  | `15e4cb9` (S1) | 36773583447 |
  | `c62acb4` (S2) | 36776398179 |

  S3 : `tests/ci_status_S3.out`, au commit S4.

## 3. Mutants (`mutants.log`)

- **Lot 1** : **39 mutants**, un par règle levée et plus — validation de la date (M1-M4), prédicat d'ouverture, chaque
  conjonctif (M5-M8), chacun des dix champs de `D` omis (M9.1-10), restrictions et sources (M10a-g), re-dérivation au run
  différé (M11a-d), comparaison à l'ancrage (M12a-b), garde « une fois par famille » (M13), réinscription (M14),
  non-divulgation (M15a-d). **Tous rouges sous le mutant, restaurés, verts ensuite**, chacun tué par un test nommé
  (`lot1/README.md` § 3). `non_divulgation.sh` mord sur M15d et mordait à la base (le digest du registre, retiré par D13).
- **Lot 2** : pas de mutant de code (aucun code). Les vérificateurs sont prouvés par cas déviés (§ 7.1).

## 4. Écarts au brief (déclarés, jamais arbitrés)

| Lot | Critère du brief | Constat |
|---|---|---|
| 1 | « 3 317 passés (3 309 + 8 levés) » | **3 321** : quatre tests neufs (D10), sans lesquels des mutants exigés survivaient |
| 1 | Renommage « `test_c3_entry.py:709` » | la définition est à la ligne **706** |
| 1 | Non-divulgation | tenue, **et** le digest du registre n'est plus imprimé du tout (D13, décision de Bruno) |
| 2 | « le lot n'écrit aucun code hors la mise à jour du manifeste et des scripts de preuve » | tenu ; scripts de procédure repris du lot 3 v2.2 par substitutions comptées (`reprise_lot2.out`) ; `postflight.sh` étendu (NRestarts comparé au preflight, alembic head), `manifest_check.sh` réécrit |
| 2 | « aucun sha d'artefact du chemin sélection versionné » | tenu ; la règle 64 hex du lot 1 est étendue pour ce lot aux sha sûrs (fichiers du chantier, manifeste v2.2 comparé, archives) — D3, valable pour ce lot seulement, re-décidée au chantier de campagne |
| 2 | Fichiers étrangers à la racine | `gel_v2_3.patch` absent dès G0 ; `lot2_s1.patch` apparu au preflight de la conformité : ni touché ni suivi, ajouté après S1 à la liste des étrangers d'`interdits_lot2.sh` (sha256_16 relevé), déclaré |

## 5. Décisions, limites déclarées, candidats v2.4

**Candidats v2.4** (rien d'implémenté « en convention ») :
- du chantier v2.2 : D3, D6, D14 (lot 1) et D6, D7 (lot 2), renvoyés à une v2.4 par la décision du 30/09 ;
- **D12 (lot 1) — « une fois » pour le run différé lui-même** : après le verdict de la variante différée, la famille
  porte deux verdicts comptés et l'empreinte inscrite reste acceptée ; un second manifeste de même `D` passerait. Le
  texte renvoie la mécanique du run différé à un amendement ultérieur (AM-01, « Limites dites ») ;
- **D13 (lot 1) — `anchor.json.registry.sha256`** (et, par transitivité, le digest imprimé d'`anchor.json`) : digest
  d'un fichier qui porte l'empreinte, gardé parce qu'il fait partie du contrat de chaîne. Fermeture structurelle
  proposée par Bruno : un **sel aléatoire à la racine du registre de campagne**, qui rend tout digest non inversible sans
  lire le registre ; elle relève de la conversation manifeste et exigera son propre item d'outillage (`load_registry`
  jette aujourd'hui toute clé de racine inconnue, `c3_anchor.py:218`) ;
- **D13 (lot 1) — taille du registre** : elle diffère quand un bloc différé est inscrit ; couverte par la règle de
  non-lecture (aucun listing de tailles, tenu par les vérificateurs du lot 2).

**Limite de test** : la normalisation UTC des deux instants de `D` (D2 du lot 1) n'est discriminée par aucun test ni
mutant (toutes les fixtures écrivent déjà `+00:00`) ; candidat de test.

## 6. Défauts du chantier, dits comme tels

### 6.1 Lot 1 (repris de `lot1/README.md` § 6)

- `non_divulgation.sh`, première version (avant tout commit) : motif trop large, doublons ; resserré.
- Le même contrôle n'a pas été lancé au C2 : il a signalé au C3 une constante publique écrite au C2.
- N3, première version : une empreinte altérée de 16 zéros, faux positif dans les NAV décimales ; remplacée avant commit.
- `rouge_avant.sh` : chemin mal retiré (cosmétique), corrigé.
- N1 et N4 naissent rouges sur l'interface absente, pas sur la règle ; leur morsure est prouvée par les mutants.
- `interdits_adverse.sh` n'a pas de cas pour le fichier étranger (jamais touché).
- **K5 du lot 2 — une obligation fausse transmise au lot 2** : `lot1/README.md` § 5 écrit « la porte § L.5 cite le test
  par son nom neuf (D9) ». C'est faux : la porte § L.5 option 1 est faite des 24 `test_determinism_parallel_vs_serial_full`
  seuls, et le test renommé n'y figure pas. L'obligation venait du D9 du lot 1 ; le message de lancement du lot 2 l'a
  propagée sans vérifier quelle porte le brief visait. **Défaut imputé au lot 1 et au message de lancement**, constaté
  à la lecture du plan du lot 2 ; le README clos n'est pas corrigé (décision de Bruno au GO du lot 2).

### 6.2 Lot 2

- **`interdits.sh` (lot 1) traitait l'absence du fichier étranger comme un écart** (`etranger_inchange=1` si
  `gel_v2_3.patch` manque) : un fichier qui n'est pas au chantier peut disparaître sans que rien ne soit touché.
  Constaté à G0 (le fichier avait été retiré hors de cette session) ; `interdits_lot2.sh` en fait un constat
  (`etranger=absent`). Le script du lot 1, clos, n'est ni corrigé ni relancé.
- **`interdits_lot2.sh` modifié après S1** : un second fichier étranger, `lot2_s1.patch`, est apparu à la racine au
  preflight de la conformité. Il n'a été ni ouvert ni touché ; le script l'exclut par son nom et le contrôle inchangé
  (préfixe de 16 hex relevé au premier constat), comme `gel_v2_3.patch`. Le vérificateur modifié a été re-prouvé avant
  S2 (`interdits_lot2_adverse.out`). Le run de conformité, lui, s'est fait au S1, non concerné.
- **K5** : l'obligation fausse sur la porte § L.5, imputée au lot 1 et au message de lancement (§ 6.1).

## 7. Preuves serveur

Les deux phases ont tourné en lecture seule. `alembic` était à `c3bd1e7a0001 (head)` avant et après, le service à
`662c104` sans ligne sale, et le collector actif avec `NRestarts=0`, tous inchangés. Environnement : l'interpréteur du
venv du service (Python 3.12.3, pytest 9.0.2), `env PYTHONPATH="$REPO/src"` sur chaque invocation, `bash -lc` sous
tmux ; pas de `set -e`, pas de `kill`, pas de relance.

### 7.1 Conformité sous v2.3 (`conformite/`)

- **Attendu** : `conformite/attendu.md`, committé à S1 avec l'entrée 21. Bruno l'a relu avec le manifeste et le pilote
  au SHA S1 complet (STOP 1) ; son GO de lancement nomme S1.
- **Préalables à S1**, tous à `rc=0` :
  - `manifest_check.out` : chemins changés contre le manifeste v2.2 = exactement `deferred_evaluation.date` ajouté,
    `protocol_sha256`, `research_log_entry`, `run_scope`, `variant_id` réécrits ; écart de la date 365,000000 j ;
    `c3_anchor` local 0, `T` attendu ;
  - `events.out` : liste close = code, 54 noms ;
  - `reprise_lot2.out` : pilotes et scripts repris du lot 3 v2.2, lignes changées = chemins, branche, constantes,
    en-têtes ;
  - `pilot_dryrun.out` : 6 simulations au code attendu ;
  - `verify_adverse.out` : 2 témoins à 0 ; 22 + 15 cas déviés à 1, chacun avec un seul item en écart ;
  - `interdits_lot2_adverse.out`, `lint_lot2.out`.
- **Run** : un seul, au SHA **`15e4cb9a3a9215caa7ecb5ca2e2bab6b63bf5458`**, le 2026-09-30 de **20:53:16 à
  20:57:22Z**. Pilote `1f4b9fd4…be16` exécuté depuis le clone. Code du pilote : **0**.
- **`verify_attendu.out`** : **10 items vérifiables sur 10 tenus**, `rc=0`.

  | Item | Mesuré |
  |---|---|
  | Gardes | `guard=0` au SHA S1, `krakenbot` du clone, protocole v2.3, manifeste `24bde67d…565a`, `CAMPAIGN_UNLOCK` absent |
  | Trois exécutions (workers 4 / 1 / 4) | préfixe 0 ; `c3_anchor` (la date à 365 j exactement admise), `c3_entry`, `c3_benchmark`, `c3_select` en 0 ; `c3b_evaluate` **`0 event=evaluated`** ; `chain` 0 avec **`anchor:0,entry:0,benchmark:0,select:0,continuity:0`** ; **`chain.verified` vrai, violations vides, zéro violation au rejeu** ; interpréteur du clone |
  | Déterminisme | **23 artefacts identiques au bit sur les trois exécutions** (`compared=23 differing=0 absent=0`), liste attendue exacte |
  | Base, service | inchangés ; arbre du clone propre |

- **Durées** (bornes `start_<K>` / `end_<K>`) : 52 s et 53 s à 4 workers (exécutions 1 et 3), 2 min 18 s à 1 worker
  (exécution 2).
- **Archive** : `~/archive/c3_outillage_v2_3_conf_20260930/c3_outillage_v2_3_conf_server_20260930.tgz`, 139 fichiers,
  sha256 `94a6e9e87ec1cf35e71496a8ff3886477d78178ff11fed41e2392eec21e7000b`. Vérifiée par codes seulement : liste, 0 entrée
  `repo/` ou `.env`, `sha256sum -c`, extraction et `diff -rq`, `cmp` du pilote, `sha256sum -c` de l'extraction.
  **`rm -rf` à 20:57:54Z.**
- **Issue non lue.** Par construction, `validé` et `réfuté` sont inatteignables (provenance `unknown`, `P_PROVENANCE` au
  rang 2 du § H.1), la voie du § 10.1 ne s'ouvre pas et aucune évaluation différée n'est inscrite (dérivé du code et des
  tests X4, N1 ; non vérifié par lecture du registre). L'inscription est non comptée, dans des registres jetés avec
  l'archive. Rien du chemin sélection n'a été ouvert, listé ni mesuré ; seul le sha de l'archive a été imprimé.

### 7.2 Porte § L.5, option 1 (`gate_L5/`)

- **SHA testé** : **`c62acb4c351de177d30b9b7f4c75b8d5c3306ba9`** (S2, D5), CI verte (run 36776398179). Pilote
  `gate_L5/run_gate.sh` (`b5d2018f…2c93`), repris de la porte v2.2 (chemins et en-tête seuls, `reprise_lot2.out`).
- **Fenêtre** : **21:08:00 → 22:18:21Z le 2026-09-30 (70 min 21 s)**. Code du pilote : **0**.
- **Résultat** : `full=0`, les **24 combos en `rc=0` avec un JUnit `1/0/0/0`**, agrégat
  `junit_total=tests:24,failures:0,errors:0,skipped:0,missing:0`.
  - `verify_gate.out` : **6 items sur 6 tenus** (le vérificateur prouvé avant, le faux vert « module skippé » y est un
    cas dévié).
  - Durées `call` (s) : 234,60 · 235,61 · 188,07 · 54,23 · 52,99 · 42,86 · 56,75 · 56,41 · 45,56 · 49,07 · 49,28 ·
    38,76 · 52,33 · 51,43 · 40,87 · 330,86 · 335,71 · 252,17 · 309,77 · 308,04 · 234,36 · 407,96 · 421,63 · 315,26 —
    le profil des portes précédentes (v2.2 le 30/09 : 71 min 40 s).
- **Non-lecture** : journaux et JUnit (`--showlocals`) en fichiers seulement, archivés ; n'ont été rapatriés que
  `status.txt`, `pytest_summary.txt` (ligne `call` et ligne de résumé), `pilot_exit.txt` et les deux `alembic`.
- **Archive** : `~/archive/c3_outillage_v2_3_gate_20260930/c3_outillage_v2_3_gate_server_20260930.tgz`, 56 fichiers,
  sha256 `f8a853fa3c09535bbe4ea0ee01d1cf74c7e6a5b02920d7f1fbf6a7224ad88b73`. Vérifiée par codes. **`rm -rf` à 22:18:58Z.**
- **`postflight.out`** (`rc=0`) : `~/runs/c3_outillage_v2_3` absent, aucune session tmux du chantier ; les deux archives
  passent `sha256sum -c` ; collector actif, `NRestarts=0` (égal au preflight) ; service `662c104`, 0 ligne sale ;
  alembic `c3bd1e7a0001 (head)` ; `CAMPAIGN_UNLOCK` absent de l'arbre du service.
- **Invariance jusqu'au tip.** Après S2, seuls changent `results/c3_outillage_v2_3/` et `docs/RESEARCH_LOG.md` ; le code
  est identique à `a30d62a` (`interdits_lot2_S3.out`, diff vide et liste blanche). La porte jouée à S2 vaut pour le tip,
  sans rejeu (précédent C2 / C3b / v2.2).

## 8. Tunnel, base, lint, interdits, limites

- **Tunnel** (`tests/tunnel.out`) : au lot 1, ouvert pour les 13 tests base (lecture seule), fermé et vérifié fermé en
  fin de lot ; au lot 2, **jamais ouvert**, constaté fermé à G0 et avant STOP 2.
- **Aucune migration.**
- **Lint et typage** : lot 1, ruff (liste CI et dépôt) vert, `mypy src/` = 65, mypy strict des trois modules égal à la
  base ; lot 2, `lint_lot2.out`, en vérification seulement (aucun formatage).
- **Interdits** : lot 1, `tests/interdits_C0.out` à `interdits_C5.out` (diff vide contre `b50f2d1` sur les chemins
  gelés, protocole au sha consigné, liste blanche, aucun artefact du chemin, empreintes de 64 hex ⊆ table d'Adoption,
  `CAMPAIGN_UNLOCK` absent) ; lot 2, `tests/interdits_lot2_*.out` (en plus : diff vide contre `a30d62a` sur le code, les
  tests, les docs gelées et le livrable du lot 1 ; règle 64 hex du lot 2). Mordant prouvé : `interdits_adverse.out`,
  `interdits_lot2_adverse.out`.

**Limites**
- **Les 24 `_full`** sont des backtests P6 (USDC, défauts de classe, 2023-04 → 2026-04) comparés par hash. Ce ne sont
  pas des runs du producteur ; ils lisent la période de campagne sur d'autres séries ; aucune métrique n'est lue.
- **Les 13 tests base du lot 1** ont lu la base par le tunnel, en lecture seule ; aucune métrique de candidat n'en a
  été lue.
- **La phrase de la première ligne repose sur trois appuis** (le code, les tests, les codes de la chaîne ; attendu
  § 8), pas sur un journal de requêtes Postgres.
- **L'évaluation différée n'est exercée que par les tests** (X3-X7, N1-N4) : le run de conformité, sous provenance
  `unknown`, ne peut pas ouvrir la voie, et aucun run serveur ne l'a traversée.
- **Le registre de campagne unique et persistant n'existe pas encore** ; les runs de conformité utilisent des registres
  jetés.

## 9. Ce qui attend

- **Merge par Bruno**, après relecture de ce rapport. Puis `docs/CODE_MAP.md` régénéré au merge (le lot 1 a changé
  `c3_common`, `c3_anchor`, `c3_verdict`), et `git pull --ff-only` du serveur : le service est à `662c104`.
- **Lignes périmées hors du chantier**, pour le `docs(merge)` (plan du lot 2, D6 : non touchées ici) :
  - `CLAUDE.md` l.19 : « suite : outillage v2.3 (8 `xfail` strict X1-X8), puis manifeste » ;
  - `CLAUDE.md` l.43 : « squelette `xfail` X1-X8, outillage à écrire » ;
  - `CLAUDE.md` l.59-60 : « v2.3 n'est pas outillée : 8 `xfail` strict X1-X8 » ;
  - `skills/backtest.md` l.545-547 : « v2.3 n'est pas outillée … portée par huit tests `xfail` strict » ;
  - `skills/backtest.md` l.659 : décompte « 932 » des tests C3 (déjà périmé avant ce chantier) ;
  - `PROJECT_CONTEXT.md` : aucune mention de v2.3 ni de son outillage.
- **Conversation manifeste**, avant la première campagne comptée : le manifeste sous v2.3, avec sa
  `deferred_evaluation.date` ; le registre de campagne persistant et son **sel à la racine** (D13, item d'outillage) ;
  `CAMPAIGN_UNLOCK`, créé par Bruno ; la famille réelle ; la règle 64 hex du chantier de campagne (re-décidée, D3 du
  lot 2) ; D12 (« une fois » du run différé) ; les dettes 21 (`--campaign`) et 24 (spread et slippage).
- **Candidat de test** : la normalisation UTC des instants de `D` (§ 5).
