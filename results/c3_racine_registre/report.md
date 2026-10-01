Aucune donnée de la fenêtre de campagne 2021-03-01 → 2026-06-29 n'a été lue par le producteur ni par la chaîne, sur aucun run de ce chantier ; aucune issue de chaîne n'a été lue.

# C3 — Racine du registre (R-4) : rapport final du chantier (lots 1 et 2)

**Fenêtre d'instrument, aucune portée économique.** Le registre de campagne unique portera à sa racine un sel aléatoire
(`skills/registry.md` § 1), qui rend tout digest du registre non inversible sans le lire — fermeture structurelle du
canal D13. Ce chantier fait que l'ancrage **préserve les clés de racine** à la réécriture (il les jetait), prouve que le
verdict les préservait déjà, défend par un test la normalisation UTC des instants du descripteur `D`, commite le
runbook, puis rejoue au serveur la conformité du producteur et de la chaîne au SHA du chantier. C'est, sauf découverte,
le dernier changement de code de chaîne avant la campagne : cette conformité sert de preuve d'instrument au manifeste.

La phrase de la première ligne a une portée ; une exception est dite au § 8 : les 13 tests base, lancés par le tunnel au
lot 1, lisent des données de la période de campagne. Ce ne sont pas des runs du producteur, et aucune métrique n'en a
été lue. La porte § L.5 n'a pas été rejouée (§ 7.2).

- **Brief** : `agent/AGENT_C3_RACINE_REGISTRE.md` (commité tel que reçu). **Runbook** : `skills/registry.md` (le fichier
  joint `RUNBOOK_REGISTRE_CAMPAGNE.md`, tel que reçu, `cmp` identique).
- **Plan** : `plans/plan.md` (D1-D10, GO du lot 1 le 01/10 ; § 7 = L1-L7 du lot 2) ; exécution du lot 2 :
  `plans/lot2.md` (GO du lot 2 le 01/10 ; ses ajouts approuvés au GO de lancement).
- **Branche** `feat/c3-racine-registre`, partie de `dev = 313eb00`, poussée à chaque lot. **Aucun merge : il est fait par
  Bruno après relecture de ce rapport (STOP 2).**
- **Journal** : `docs/RESEARCH_LOG.md`, entrée 22, avec son issue.

## 1. Ce qui est livré

### Lot 1 — code, tests, runbook (`lot1/README.md`)

| Commit | Objet |
|---|---|
| `71061ed36d165a0447b8b941139ed521d2873050` (C0) | brief, plan (GO), inventaire-filet et sa preuve, `interdits.sh` et sa preuve, mesures de base |
| `8915807b9acafcfce3404c8cf5e01f8b80f11d18` (C1) | `skills/registry.md`, le runbook tel que reçu |
| `b8ed4b019fdc9cc0a1f9bf05a9074d643b8ccfb8` (C2) | **le passthrough** : `c3_anchor.load_registry` rend la racine lue, contrôlée par le critère du writer strict (jamais par `canon`) ; `register` la rend telle quelle ; tests T1, T2-chaîne, T2-verdict, T4 |
| `9b72662ccf4ce49717571fffde91ea31e47e9930` (C3) | test T3 : la normalisation UTC des instants de `D` |
| `56c65aaf8d14e6c70a4dcc66f321a83bb785d817` (C4) | rapport du lot, preuves, mutants |

Code touché : `scripts/audit/c3_anchor.py` seul. `c3_verdict.py`, `c3_common.py` et le reste de la chaîne et du
producteur : diff vide contre `313eb00`.

### Lot 2 — conformité rejouée, porte par invariance (ce rapport)

| Commit | Objet |
|---|---|
| `c3f0ac6a22251a48b34227083c9aaad6de174ee4` (C0) | `plans/lot2.md` (GO) ; `interdits_lot2.sh` et sa preuve ; tunnel constaté fermé |
| `84fff64385b8da267668f69d038f09d58fa522a3` (S1) | **SHA du run** : manifeste, attendu, pilote, vérificateur, scripts et leurs preuves d'avant lancement, invariance de la porte, entrée 22. **Aucun code** |
| S2 (ce commit) | preuves de la conformité, archive, postflight, invariance au tip, ce rapport, issue de l'entrée 22 |
| S3 | statut CI de S2 |

**Le lot 2 n'écrit aucun code** : diff vide contre `56c65aa` sur `scripts/ tests/ src/ config/ pyproject.toml
poetry.lock .github/ agent/ skills/` et les docs gelées, à chaque commit (`tests/interdits_lot2_*.out`).

## 2. Tests

| Étape | Passés | Ignorés | Désélectionnés (`_full`) | xfail | Échecs / XPASS |
|---|---|---|---|---|---|
| base (`313eb00`) | 3 321 | 19 | 24 | 1 (le caduc) | 0 |
| C2 le passthrough | 3 325 | 19 | 24 | 1 | 0 |
| C3 le test UTC (fin du code) | **3 326** | 19 | 24 | **1** (le caduc) | 0 |
| lot 2 | inchangé : aucun code, aucun test | | | | |

- **Décompte** : 3 321 + 5 neufs = 3 326, 0 retiré, 0 renommé (`tests/comptes_C3.out`, par diff d'identifiants contre
  `313eb00`). Le seul xfail est le caduc déclaré au chantier v2.2.
- **Corps des tests existants intacts** (`tests/diff_tests_C3.out`, AST) ; seule ligne retirée des tests : un import
  élargi.
- **Tests neufs** (plan § 3) : T1 (racine à l'ancrage : enregistrement, idempotence, enfant), T2-chaîne (l'adverse du
  brief : ancrage **et** inscription du verdict dans un même `chain`), T2-verdict (`registry_inscription` seul), T3
  (UTC de `D` : `+00:00`, `Z`, `+02:00`, neuf couples verdict × run différé), T4 (flottant non fini à la racine → code 1,
  diagnostic). T1, T2-chaîne et T4 rouges à `313eb00` sur la règle ; T2-verdict et T3 verts à `313eb00` (propriétés déjà
  tenues), leur mordant prouvé par mutants.
- **Les 13 tests base** passent tunnel ouvert (`tests/base_db_C3.out`), tunnel fermé ensuite, vérifié.
- **CI verte en tentative 1, sans aucune relance**, à chaque SHA poussé :

  | SHA | Run |
  |---|---|
  | `9b72662` (C3, fin du code) | 36838326935 |
  | `56c65aa` (C4, lot 1) | 36839482107 |
  | `84fff64` (S1) | 36842190288 |

  S2 : `tests/ci_status_S2.out`, au commit S3.

## 3. Mutants (`mutants.log`)

Neuf mutants, chaque tueur nommé lancé **seul** contre son mutant ; tous rouges sous le mutant, restaurés (diff vide),
verts ensuite ; la seconde passe du journal porte la ligne d'échec de chaque tueur, toutes sur la règle : passthrough
retiré à la lecture (M1a) ou à l'écriture (M1b) ; racine perdue (M2a) ou réécrite (M2b, M2c) à l'inscription du verdict ;
graphie engagée dans `D` (M3a) ; `astimezone` retiré (M3b) ; contrôle de racine retiré (M4 : la trace nue du writer) ;
racine imprimée (M5, que `non_divulgation.sh` voit aussi). Détail : `lot1/README.md` § 4.

## 4. Écarts au brief et au plan (déclarés, jamais arbitrés)

| Lot | Critère | Constat |
|---|---|---|
| 1 | Brief § 0.2 : le runbook « joint » | absent à l'ouverture ; demandé à Bruno à la question du plan, déposé, lu avant la soumission du plan |
| 1 | Plan D6 | graphie `+02:00` ajoutée au test UTC (extension, approuvée au GO) |
| 1 | Plan § 6 / § 4 | `vert_avant` réalisé comme mode de `rouge_avant.sh` ; chaque tueur lancé seul (v2.3 les lançait ensemble) |
| 1 | Brief § 6 : `~/docker/` jamais nommé | le runbook tel que reçu nomme `~/docker/` et `~/c3/` ; aucun script du chantier ne les nomme |
| 2 | Plan L5 | contrôle (d) ajouté (modules chargés à la collecte du `_full`) ; règle d'imports des fichiers de test élargie à `tests/` après constat (§ 6) — approuvés au GO de lancement |
| 2 | Reprise du lot 2 v2.3 | phase « porte » retirée des scripts repris (porte non rejouée) ; `manifest_check.sh` réécrit pour le delta du lot — approuvés au GO de lancement |

## 5. Décisions, limites déclarées, candidats v2.4

Décisions appliquées : D1-D10 (lot 1), L1-L7 (lot 2), sans écart hors § 4. Limites :
- **D1 — mise en page** : la racine est préservée en valeurs, pas en octets du fichier ; le writer réécrit avec
  `indent=2` et clés triées — mise en page qui coïncide avec celle du fichier du runbook § 1.
- **D2 — côté verdict** : `registry_inscription` ne contrôle pas la racine ; un non-fini de racine y est inatteignable en
  `chain` (l'étape 1 le refuse avant) et le verdict seul n'écrit pas de registre.
- **K4 du plan** : `canon` lirait comme un décimal toute chaîne qui en a la forme ; la racine ne lui est jamais passée,
  mais la même lecture vaut toujours pour les chaînes des **enregistrements** (classe préexistante, hors chantier).
- **Inventaire-filet** : fait de motifs, sur l'état de la base ; un épinglage écrit hors motifs lui échapperait.
- **Le passthrough n'a été exercé au serveur sur aucun registre porteur d'un sel** : les registres de la conformité sont
  neufs, leur racine ne porte que `variants` (dit et assumé, attendu § 3). Il ne l'est que par les tests (T1, T2-chaîne,
  T2-verdict, T4).

Candidats v2.4 et suites, rien d'implémenté « en convention » : ceux du rapport v2.3 (D3, D6, D14 et D6, D7 du chantier
v2.2 ; D12 « une fois » du run différé) restent ouverts ; **D13 `anchor.json.registry.sha256`** est désormais fermé
structurellement **dès que le registre de campagne porte son sel** (runbook § 1, geste de Bruno après le merge) ; la
**taille** du registre reste couverte par la non-lecture (runbook § 4).

## 6. Défauts du chantier, dits comme tels

### 6.1 Lot 1 (repris de `lot1/README.md` § 6)

- `inventaire_filet.sh`, première version : deux lectures de `variants` seul non classées, témoin de la preuve rouge ;
  table complétée avant commit.
- `interdits_adverse.sh`, première version : constatait le code, pas l'item qui mordait ; complété avant commit.
- `mutant.sh`, première passe : ligne d'échec non consignée ; complété, mutants rejoués.
- T2-verdict sous M2a échoue par `KeyError: 'salt'` sur sa propre lecture, avant son assertion (même cause, diagnostic
  moins net) ; laissé tel quel.
- Aucun cas dévié pour `CAMPAIGN_UNLOCK` ni pour le répertoire du registre de campagne : jamais créés, même
  temporairement.

### 6.2 Lot 2

- **`invariance_porte.sh`, premier essai** (avant S1) : ma règle d'imports pour les trois fichiers de test touchés
  (« importés seulement par des tests C3 ») était trop étroite — `test_c3_common.py` est aussi importé par
  `tests/test_scripts/test_audit_common.py`, hors du chemin de la porte. Règle élargie à `tests/` et déclarée dans le
  script ; le contrôle (c) du plan (`c3_anchor`) tenait. Approuvé au GO de lancement.
- **Le même script, au premier passage de sa preuve** : le contrôle (c) ne lisait que les fichiers suivis ; le cas
  « un module de `src/` importe `c3_anchor` » (fichier non suivi) n'était vu que par (a) et (b). Étendu aux non-suivis
  avant S1 ; (c) mord désormais seul aussi (`invariance_adverse.out`).
- **`interdits_lot2_adverse.sh`, premier passage** : la liste des items en écart portait une ligne de comptage
  (`empreintes_64_ajoutees=…`) qui n'est pas un écart ; filtrée avant commit.
- **Reprise** : le faux interpréteur de `pilot_dryrun.sh` garde sa branche `-m pytest` (porte), inerte ; et des
  commentaires des scripts repris renvoient encore à des décisions du plan v2.3 (D1, D4, K3…) — renvois au modèle, pas
  aux décisions de ce chantier.

## 7. Preuves serveur

Le run a tourné en lecture seule. `alembic` était à `c3bd1e7a0001 (head)` avant et après, le service à `313eb00` sans
ligne sale, le collector actif avec `NRestarts=0`, tous inchangés. Environnement : l'interpréteur du venv du service
(Python 3.12.3), `env PYTHONPATH="$REPO/src"` sur chaque invocation, `bash -lc` sous tmux ; pas de `set -e`, pas de
`kill`, pas de relance.

### 7.1 Conformité au SHA du chantier (`conformite/`)

- **Attendu** : `conformite/attendu.md`, committé à S1 avec l'entrée 22. Bruno l'a relu avec le manifeste et le pilote au
  SHA S1 complet, les a recalculés, et a approuvé les ajouts au plan (STOP 1) ; son GO de lancement nomme S1.
- **Préalables à S1**, tous à `rc=0` : `manifest_check.out` (ajouté ∅, retiré ∅, réécrit exactement `research_log_entry`,
  `run_scope`, `variant_id` ; trois lignes de texte ; écart de la date 365,000000 j ; `c3_anchor` local 0, `T` attendu) ;
  `events.out` (54 = 54) ; `reprise_lot2.out` ; `pilot_dryrun.out` (4 simulations au code attendu) ;
  `verify_adverse.out` (témoin 0, 22 cas déviés à un item chacun) ; `interdits_lot2_adverse.out` ; `lint_lot2.out`.
- **Run** : un seul, au SHA **`84fff64385b8da267668f69d038f09d58fa522a3`**, le 2026-10-01 de **10:16:15 à 10:20:27Z**
  (preflight `rc=0` à 10:15:58Z). Pilote `ddf85bb8…66ff`, exécuté depuis le clone. Code du pilote : **0**.
- **`verify_attendu.out`** : **10 items vérifiables sur 10 tenus**, `rc=0`.

  | Item | Mesuré |
  |---|---|
  | Gardes | `guard=0` au SHA S1, `krakenbot` du clone, protocole v2.3, manifeste `9966efad…a24b`, `CAMPAIGN_UNLOCK` absent |
  | Trois exécutions (workers 4 / 1 / 4) | préfixe 0 ; `c3_anchor`, `c3_entry`, `c3_benchmark`, `c3_select` en 0 ; `c3b_evaluate` **`0 event=evaluated`** ; `chain` 0 avec **`anchor:0,entry:0,benchmark:0,select:0,continuity:0`** ; **`chain.verified` vrai, violations vides, zéro violation au rejeu** ; interpréteur du clone |
  | Déterminisme | **23 artefacts identiques au bit sur les trois exécutions** (`compared=23 differing=0 absent=0`), liste attendue exacte |
  | Base, service | inchangés ; arbre du clone propre |

- **Durées** (bornes `start_<K>` / `end_<K>`) : 54 s et 54 s à 4 workers (exécutions 1 et 3), 2 min 21 s à 1 worker.
- **Archive** : `~/archive/c3_racine_registre_conf_20261001/c3_racine_registre_conf_server_20261001.tgz`, 139 fichiers,
  sha256 `04e00089d0eb11129c410ef79bb094ed14e7808a75374f7541941320fdd8512d`. Vérifiée par codes seulement : liste, 0 entrée
  `repo/` ou `.env`, `sha256sum -c`, extraction et `diff -rq`, `cmp` du pilote, `sha256sum -c` de l'extraction.
  **`rm -rf` à 10:21:13Z.**
- **Issue non lue.** Par construction, `validé` et `réfuté` sont inatteignables (provenance `unknown`, `P_PROVENANCE` au
  rang 2 du § H.1), la voie du § 10.1 ne s'ouvre pas et aucune évaluation différée n'est inscrite (dérivé du code et des
  tests X4, N1 ; non vérifié par lecture du registre). Rien du chemin sélection n'a été ouvert, listé ni mesuré ; seul
  le sha de l'archive a été imprimé.
- **`postflight.out`** (`rc=0`) : `~/runs/c3_racine_registre` absent, aucune session tmux du chantier ; l'archive passe
  `sha256sum -c` ; collector actif, `NRestarts=0` (égal au preflight) ; service `313eb00`, 0 ligne sale ; alembic
  `c3bd1e7a0001 (head)` ; `CAMPAIGN_UNLOCK` absent de l'arbre du service.

### 7.2 Porte § L.5 : non rejouée, invariance prouvée

- **Dernière porte jouée** : option 1, les 24 `test_determinism_parallel_vs_serial_full` en `rc=0`, au
  `c62acb4c351de177d30b9b7f4c75b8d5c3306ba9`, le 30/09 (`results/c3_outillage_v2_3/gate_L5/`).
- **Chaîne d'invariance** : `c62acb4` → `313eb00` (merge de l'outillage v2.3 dans `dev`) ne change que
  `results/c3_outillage_v2_3/` et `docs/RESEARCH_LOG.md` ; `313eb00` → tip ne change que `c3_anchor.py`, trois fichiers de
  test C3, le runbook, le brief, `docs/RESEARCH_LOG.md` et `results/c3_racine_registre/`.
- **`tests/invariance_porte_S1.out` et `invariance_porte_S2.out`** (`rc=0`, au SHA du run et au tip) : (a) fichiers
  changés depuis `c62acb4` dans cette liste ; (b) diff vide contre `313eb00` et contre `c62acb4` sur `src/ config/
  pyproject.toml poetry.lock .github/`, `scripts/` hors `c3_anchor.py`, `tests/` hors les trois fichiers touchés ; (c)
  `c3_anchor` importé seulement par `c3_verdict` et des tests C3, aucun module touché importé sous `src/` ni `scripts/`
  hors `c3_verdict` ; (d) 23 modules du dépôt chargés à la collecte du module `_full`, aucun `c3_*` ni `test_c3*`.
  Mordant prouvé : `tests/invariance_adverse.out` (témoin 0, quatre cas déviés ≠ 0).
- **La porte jouée au `c62acb4` vaut pour le tip**, sans rejeu (précédents C2, C3b, v2.2, v2.3).

## 8. Tunnel, base, lint, interdits, limites

- **Tunnel** (`tests/tunnel.out`) : au lot 1, ouvert pour les 13 tests base (lecture seule), fermé et vérifié fermé ; au
  lot 2, **jamais ouvert**, constaté fermé à G0 et avant STOP 2.
- **Aucune migration.** Aucun registre persistant, aucun sel réel ; `~/c3/` ni touché ni créé ; `CAMPAIGN_UNLOCK` jamais
  créé.
- **Lint et typage** : lot 1, ruff vert, `mypy src/` = 65, mypy strict égal à la base ; lot 2, `lint_lot2.out`, en
  vérification seulement.
- **Interdits** : lot 1, `tests/interdits_C0.out` à `interdits_C4.out` ; lot 2, `tests/interdits_lot2_*.out`. Mordant
  prouvé : `interdits_adverse.out`, `interdits_lot2_adverse.out` (chaque cas dévié par son item).

**Limites**
- **Les 13 tests base du lot 1** ont lu la base par le tunnel, en lecture seule ; aucune métrique n'en a été lue.
- **La phrase de la première ligne repose sur trois appuis** (le code, les tests, les codes de la chaîne ; attendu § 8),
  pas sur un journal de requêtes Postgres.
- **La porte § L.5 n'a pas tourné à ce chantier** : sa validité au tip repose sur l'invariance prouvée (§ 7.2).

## 9. Ce qui attend

- **Merge par Bruno**, après relecture de ce rapport. Puis `docs/CODE_MAP.md` régénéré au merge (le lot 1 a changé
  `c3_anchor`), et `git pull --ff-only` du serveur : le service est à `313eb00`.
- **Lignes périmées hors du chantier**, pour le `docs(merge)` (non touchées ici) :
  - `CLAUDE.md` l.19 et l.59-60 : « outillage v2.3 (8 `xfail` strict X1-X8) » / « v2.3 n'est pas outillée » (périmées
    depuis le chantier v2.3) ; l.43 « outillage à écrire » ; et la ligne de routage du runbook `skills/registry.md`
    (« registre de campagne : création, sauvegarde, non-lecture ») à ajouter à la table ;
  - `skills/backtest.md` l.545 (« v2.3 n'est pas outillée ») et l.567 (ligne `c3_anchor.py` : la racine du registre
    traverse l'ancrage, R-4) ; l.659 (décompte « 932 », déjà périmé) ;
  - `PROJECT_CONTEXT.md` : ni v2.3 outillée, ni R-4, ni le runbook.
- **Avant la première campagne comptée** (conversation manifeste) : la création du registre de campagne par Bruno
  (runbook § 1, sel à la racine), le manifeste gelé sous v2.3, `CAMPAIGN_UNLOCK` créé par Bruno ; et, du runbook
  (« Renvois ») : sur registre persistant, `anchor.json` n'est pas identique au bit entre exécutions (`registry.new_entry`,
  `registry.sha256`) — la liste des artefacts comparés du manifeste de campagne devra en tenir compte.
