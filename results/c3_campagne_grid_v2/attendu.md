# Seconde campagne C3 comptée — famille `grid-atr-v4`, relance unique après correction d'instrument : attendu déclaré avant le lancement

**Run compté, un seul lancement, aucun retry, aucun écart arbitré — et relance unique du § 10.1**
(`docs/CONTRAINTES_POST_B4.md`) : **après ce run, plus aucune relance pour la famille grid, quel que soit le résultat**
(décision de Bruno, entrée 24). Ce run fait traverser la fenêtre de campagne à la chaîne C3, sous le protocole v2.3 et le
manifeste v2 gelé par Bruno le 2026-10-01. Le manifeste v2 corrige la déclaration du v1 (surcharges `decision_timeframes`
par candidat, sorties de la classmethod) ; le code est inchangé. L'issue est **déclarée ici avant le run** et **ne
remonte que par la liste close** du § 6 : l'issue et la raison telles que la chaîne § L.2 les écrit, le statut compté
dérivé de ces deux valeurs, des codes et des booléens. Rien d'autre du chemin sélection n'est lu, commenté ou reporté :
ni identité retenue, ni métrique, ni λ, ni porte, ni motif.

Cet attendu est committé avant le lancement, avec l'entrée 24 de `docs/RESEARCH_LOG.md`, au commit **S1**, qui est le
SHA du run. **Bruno le relit au SHA S1 complet (STOP 1)** : cet attendu, dont le contrôle du § 4, l'entrée 24, le pilote
(les deux littéraux `--registry`, comparés au caractère près, § 3), `tests/manifest_check.out` et l'archive-préalable
(§ 5). Puis **Bruno crée `CAMPAIGN_UNLOCK`** et exécute le contrôle du registre livré au § 4. Son GO de lancement nomme
S1, **à partir du 2026-10-02 UTC** (A1', § 1). **Rien ne tourne sur le serveur avant ce GO.**

- **Brief** : `agent/AGENT_C3_CAMPAGNE_GRID_V2.md` (non suivi par décision, brief § 3). **Plan** : `plans/plan.md` (GO du
  2026-10-02 : amendements A1' et A2', points P1 et P2 tranchés, § 10).
- **Modèle** : l'attendu du run v1 (`results/c3_campagne_grid/attendu.md`), réécrit pour la relance.
- **Protocole** v2.3, sha256 `d030ab239de317f6cba89877d682338fa2001d2a63d231f1a86c519fe87a79e6`, inchangé.
- **Code** identique à `dev` @ `cce566d82f40166d9ff95c972e346b26831ed304`. Le diff est vide sur `src/ scripts/ tests/
  config/ pyproject.toml poetry.lock .github skills/ agent/` (brief et brouillon v2 non suivis, exceptés), sur le
  protocole, les amendements, les contraintes et le chantier v1 (`tests/interdits_S1.out`). C'est le code du run v1
  (`235461e`) et de la conformité R-4 tenue au serveur le 01/10 (entrée 22, 10/10).

## 1. Fenêtre

- **Période** : `2021-03-01T00:00Z → 2026-06-29T00:00Z` (1 946 j), `F = 0,70`.
- **Ancrage** : `T = 2024-11-22T04:48:00Z` (0,70 × 1 946 j = 1 362,2 j de préfixe ; 583,8 j d'évaluation). `T` est
  recalculé par `c3_anchor`, jamais passé en paramètre ; il est vérifié en local sur le manifeste
  (`tests/manifest_check.out`). Il est inchangé depuis le v1.
- **Provenance** : `contaminated` — qualification du rapport gelé du rejeu (`results/rejeu_grid_report.md` § 10.3 :
  planchers du balayage re-choisis à la lumière de la campagne Binance, renoncement non corrigé).
- **Date de l'évaluation différée** : `2027-06-29T00:00:00+00:00`, 365,000000 j après la fin. Elle est déclarée parce
  que v2.3 l'exige et reste **inerte ici** : la voie du § 10.1 ne s'ouvre que sur `inconclusif (F_CANNOT_SEPARATE)`,
  inatteignable sous `P_PROVENANCE` (§ 7). Aucun module ne lit de donnée à cette date.
- **Garde-fou 6** : levé par `CAMPAIGN_UNLOCK`, créé par Bruno (§ 4).
- **Lancement à partir du 2026-10-02 UTC (A1').** L'archive du run v1, faite par l'archive-préalable (§ 5), porte la
  date du run v1, `c3_campagne_grid_20261001`. Un lancement le 01/10 donnerait le même nom à l'archive du run v2. Il est
  refusé mécaniquement : le preflight exige un jour UTC ≥ `20261002` (`jour_lancement`), en plus de son contrôle
  `archive_du_jour`.

## 2. Manifeste

**Fichier** : `results/c3_campagne_grid_v2/manifest.json`, sha256
`b757c45bbed2b0913ac4ec781c9c6928fa935b7c71639e66f26fb5d2468f4f11`. C'est la **copie à l'octet** du brouillon gelé
(`cmp`, `tests/manifest_check.out`), assertée par la garde du pilote.

**Contenu**, vérifié par `tests/manifest_check.sh` (`rc=0`) sans aucune lecture de données :
- protocole v2.3 ; famille `grid-atr-v4` ;
- **96 candidats distincts** = `grok_grid_atr_adaptive_v4` × {`BTC/USDT`, `SOL/USDT`} × `min_spacing_pct` {0,015 ; 0,02 ;
  0,025 ; 0,03} × `atr_multiplier` {1,5 ; 2,0 ; 2,5 ; 3,0} × `bear_protection_mode` {none, 1w_only, 1d_only} ;
- **une surcharge `decision_timeframes` par candidat**, égale à la sortie triée de la classmethod pure
  `GrokGridATRAdaptiveV4.decision_timeframes(params)` (96/96) : `{1d,1w,4h}` pour les 32 `1w_only`, `{1d,4h}` pour les 64
  autres. Le critère de `c3_entry` qui a arrêté le v1 (`a06_warmup`, l.496 : liste effective du manifeste contre
  l'export du producteur, en ensemble) donne 0 désaccord sur v2 ; sur le manifeste v1 commité, le même contrôle en
  donne **64**, la cause constatée de l'arrêt ;
- **parent** : `is_root` faux, `variant_key` = `sig(canon(manifeste v1 commité))` = `3159a907…fcb5`, recalculé ;
- paires de déploiement `*/USDC` (transposition déclarée, § A.6) ;
- fees `bybit`, taker 0,25 %, coûts par paire du GATE B (`config/pair_costs_b4.json`) ; `min_order_quote 5.0` ;
  capital `"1000"` ;
- graine 20261001, `B = 10000`, blocs {10, 21, 42}, niveau 0,95 ; `lambda_mode: prefix` ; seuils avec leur classe ;
- les 8 estampilles 1 w dérivées citées par `run_scope` ;
- le titre de l'entrée 24, présent une fois au journal.

Le reste est identique au manifeste v1 (`d422076b…5041`).

**`c3_anchor` en local**, pur et sans base. Registres et sorties sont dans un répertoire temporaire hors du dépôt,
supprimé ensuite, avec un sel factice. C'est un **contrôle du manifeste, pas le run** (A4 du chantier v1). La variante
v1 y est inscrite par `c3_anchor` lui-même, sur le manifeste v1 commité. Trois cas :
- **registre au sel seul** : code **2**, refus de parenté (« déclare le parent 3159a90780ebbf8a, absent du registre »),
  registre inchangé ;
- **registre portant v1** : code **0**. La variante `16d6a8f552c8cc19` (`grid-atr-v4-campagne-2021-2026-v2`) est
  « nouvelle au registre », avec `T = 2024-11-22T04:48:00+00:00`, un préfixe de 1 362,2 j et 96 candidats. La racine
  (le sel) et l'enregistrement v1 restent inchangés ;
- **rejeu** : code **0**, « déjà au registre, idempotent », registre inchangé.

## 3. Registre de campagne

C'est le registre persistant de la campagne (runbook `skills/registry.md` : un seul registre pour toutes les familles,
sel à la racine, créé par Bruno), utilisé en mode `chain`. **Il porte la variante v1**, `3159a90780ebbf8a`, inscrite le
2026-10-01 par l'ancrage autonome du run v1, **sans verdict** : c'est le parent que déclare le manifeste v2. Il est
nommé **sur les deux seules lignes `--registry` du pilote** et nulle part ailleurs ; **ni l'agent ni le pilote ne le
lisent, ne le copient, ne le listent ni ne le testent** (aucun stat, aucun sha, aucune taille).

- **Ancrage autonome** (étape préalable à l'évaluation) : **inscription de la variante v2**, nouvelle au registre
  (`registry.new_entry` vrai dans `pre/anchor.json`, § 6 item 5). Le parent étant présent et sans verdict, le critère
  d'arrêt de l'ancrage (§ A.6 v2.2) ne refuse pas.
- **`c3_verdict.py chain`, étape 1** : la variante v2 y est déjà, enregistrement recalculé égal : **idempotent**,
  `registry.new_entry` faux dans `chain/anchor.json` (§ 6 item 7).
- **Étape 6** : l'issue, la raison et le statut compté sont inscrits une fois dans l'enregistrement de la variante v2 ;
  la sortie de la chaîne porte alors la ligne de forme fixe `written … (issue inscrite, § A.6)` (D13 : ni valeur ni
  digest), constatée par un booléen.
- **Déclarés, jamais vérifiés** (non-lecture) :
  - la racine préservée à chaque réécriture (R-4 ; prouvé sur registre temporaire, § 2) ;
  - `compte: false` inscrit ;
  - **aucune évaluation différée inscrite** (la voie ne s'ouvre pas : code et tests X4, N1).
- **Limites, dites — réécrites pour un manifeste qui déclare un parent.**
  - Avec un parent, un registre **absent** au chemin donné, ou une **faute de frappe** dans un littéral `--registry`, ne
    crée plus rien en silence. `c3_anchor` lit un registre vide, ne trouve pas le parent, et refuse en
    `R0_INVALID_RUN`, code 2, sans rien écrire. Ce refus tombe à `pre_anchor` (premier littéral) ou à l'étape 1 de la
    chaîne (second littéral, après une inscription faite par le premier).
  - **C'est un nouvel arrêt, qui ferme la voie pour la famille** (brief § 4).
  - Parades :
    - la **relecture au caractère près** des deux littéraux au STOP 1 ;
    - le contrôle mécanique de `tests/interdits.sh` (chaque ligne égale au chemin construit, qui ne remplace pas la
      relecture) ;
    - le **contrôle du registre réel par Bruno**, avant le GO (§ 4) — l'agent ne peut pas le faire.
  - Un registre **altéré** (parent absent, verdict déjà inscrit) aurait le même effet ; même parade.
  - `anchor.json` sur registre persistant n'est pas bit-stable entre exécutions : un seul run, aucune comparaison.

## 4. `CAMPAIGN_UNLOCK` et contrôle du registre — gestes de Bruno avant le GO

**`CAMPAIGN_UNLOCK`** : créé par **Bruno**, à la main, entre STOP 1 et le GO, dans l'arbre du service :
`~/apps/kraken-trading-bot/results/c3b_producteur/CAMPAIGN_UNLOCK` (non suivi ; la garde d'arbre du producteur ignore les
non-suivis). Le producteur le cherche sous la racine du code exécuté, donc dans le clone créé au lancement.
- `tests/preflight.sh` constate sa **présence** dans l'arbre du service (existence seule, contenu jamais lu).
- `tests/launch.sh` le **copie** dans le clone juste après le `.env` et vérifie l'égalité par `cmp` (aucun sha, rien
  affiché) : un transport par script, jamais une création.
- La garde du pilote constate sa présence dans le clone (`campaign_unlock=present`) ; après le run, il est toujours
  présent (`campaign_unlock_after=present`).
- Le postflight le constate présent, non touché, dans l'arbre du service. **Bruno le supprime après le merge**
  (re-verrouillage).

L'agent ne le crée jamais, même temporairement : ses dry-runs locaux emploient un **marqueur de simulation** d'un autre
nom.

**Contrôle du registre réel (A2', décision de Bruno au GO du plan).** C'est le § 1 du runbook, étendu. Il est livré
ici et relu au STOP 1, jamais improvisé. Bruno l'exécute **au serveur**, où vit le registre, au moment où il crée
`CAMPAIGN_UNLOCK`. C'est une seule expression booléenne ; **la seule sortie admise est `True`**. Elle contient :
- les clauses du runbook § 1 sans `variants == {}` : racine exactement `salt` et `variants`, sel de 64 hex ;
- le mode `600`, testé en booléen plutôt que par `stat`, qui imprimerait la taille ;
- la clé du parent, seule variante, sans `verdict` ni `deferred_evaluation`.

Il ne s'affiche rien d'autre. `False`, une trace ou une absence de sortie : pas de GO.

<!-- stop1-registre:debut -->
```bash
python3 -c 'import json, pathlib; p = pathlib.Path.home() / "c3/registry/variants.json"; K = "3159a90780ebbf8a4ae4a271a7f3685be4a63309485554466790297fb057fcb5"; d = json.load(open(p)); print((p.stat().st_mode & 0o777) == 0o600 and isinstance(d, dict) and sorted(d) == ["salt", "variants"] and isinstance(d["salt"], str) and len(d["salt"]) == 64 and set(d["salt"]) <= set("0123456789abcdef") and isinstance(d["variants"], dict) and list(d["variants"]) == [K] and isinstance(d["variants"][K], dict) and not ({"verdict", "deferred_evaluation"} & set(d["variants"][K])))'
```
<!-- stop1-registre:fin -->

Ce bloc est **prouvé avant de servir** par `tests/stop1_registre.sh` (`tests/stop1_registre.out`).
- La commande est extraite d'ici même. Le chemin du registre (construit dans le script, jamais écrit) y est remplacé
  par celui d'un registre fabriqué hors dépôt : exactement une substitution, sinon rien n'est exécuté.
- **Témoin** : sel factice, mode 600, enregistrement v1 écrit par `c3_anchor` sur le manifeste v1 commité → `True`.
- **Chaque déviation** → `False` ou un code non nul, jamais `True` : mode 644 ; parent absent ; parent avec `verdict` ;
  parent avec `deferred_evaluation` ; variante en trop ; clé de racine en trop ; sel court ; sel non hexadécimal ;
  fichier absent ; JSON illisible.

**Sauvegarde du registre** (runbook § 2) : une copie datée du 01/10, postérieure à la première inscription, est **déjà
faite** (P2 ii, constaté par Bruno au GO du plan). La sauvegarde suivante relève de la cérémonie après le run (§ 12).

## 5. Ce qui tourne

**Archive-préalable du run v1, premier pas du run** (plan § 2) : `tests/archive_prealable.sh`.
- C'est une copie de l'`archive.sh` du chantier v1 ; son **corps distant est identique à l'octet**, gardes A3 inchangées
  (`tests/archive_dryrun.out`).
- Elle déplace `~/runs/c3_campagne_grid/campagne/out` vers **`~/archive/c3_campagne_grid_20261001/out`** (date figée au
  jour du run v1). L'archive est en lecture seule, vérifiée par codes, sans sha.
- Puis la seule suppression qui la concerne : `rm -rf /home/bruno/runs/c3_campagne_grid`, en littéral absolu, sous
  gardes. Le clone v1, sa copie du `.env` et sa copie de `CAMPAIGN_UNLOCK` disparaissent ; `out/` v1 n'est jamais
  ouvert.
- Elle est précédée d'une sonde en lecture seule (même périphérique, formes GNU de `stat` et `find`).
- Elle **conditionne le lancement** : le run v2 réutilise `~/runs/c3_campagne_grid/campagne`, que `launch.sh` (`mkdir`)
  et le preflight (`run_dir`) refusent tant qu'il existe.

**Pilote** : `results/c3_campagne_grid_v2/server/run_campagne.sh`, versionné à S1 et **exécuté depuis le clone** à ce
SHA. Il consigne lui-même son sha256 (`pilot_sha256`), que la relecture recalcule au blob S1. C'est le pilote v1 avec
**trois lignes de code changées** — `SELF`, `MANIFEST`, `MANIFEST_SHA` — et les commentaires datés du v1
(`tests/reprise.out`). Les deux littéraux `--registry`, `--campaign`, `NOW`, `RUN`, `EVENTS`, l'arrêt au premier écart
et l'extraction sont inchangés au caractère.
- **Une seule exécution**, `--workers 3`, sous `nice -n 10` (posé par `launch.sh`).
- `--now 2026-10-01T00:00:00+00:00`, la date du gel v2 (même règle que la graine 20261001, même littéral qu'au v1) ; elle
  entre aussi dans `first_registered_at` de la variante v2.
- `--campaign GRID_ATR_V4_2026` (étiquette d'instrument, dette 21).
- **Arrêt au premier écart** : une étape ne tourne que si toutes les précédentes ont rendu leur attendu ; sinon
  `<clé>=NOT_RUN`, et `halted_at` nomme le premier écart. Aucune écriture au registre ne suit un écart. Les contrôles
  « après » sont inconditionnels.

```
c3b_prefix.py   --manifest M --output-dir out/prefix --workers 3 --now N
c3_anchor.py    --manifest M --registry <registre de campagne> --output out/pre/anchor.json --now N
c3_entry.py     … --output out/pre/entry.json --markdown out/pre/entry.md --now N
c3_benchmark.py … --output out/pre/benchmark.json --now N
c3_select.py    … --output out/pre/selection.json --markdown out/pre/selection.md --now N
c3b_evaluate.py --manifest M --anchor out/pre/anchor.json --selection out/pre/selection.json \
    --benchmark out/pre/benchmark.json --output-dir out/eval --now N
c3_verdict.py chain --manifest M --observations out/prefix/observations.json --coverage out/prefix/coverage.json \
    --candles out/prefix/candles.json --evaluation out/eval/evaluation.json \
    --benchmark-eval out/eval/benchmark_eval.json --candles-eval out/eval/candles_eval.json \
    --registry <registre de campagne> --out-dir out/chain --campaign GRID_ATR_V4_2026 --now N
```

**Environnement unique** : l'interpréteur du venv du service, `env PYTHONPATH="$REPO/src"` sur chaque invocation
Python ; `alembic current` sans `PYTHONPATH`, depuis l'arbre du service, avant et après.

**Durée** : préfixe mesuré au run v1, 43 min 40 s pour 96 × 1 362,2 j à 3 workers (le travail du préfixe ne dépend pas
des surcharges) ; après le préfixe ≤ 11 min ; central ≈ 55 min. Attente : sonde toutes les 120 s, 120 sondes (plafond
4 h). La sonde n'imprime que `exit=`, le nombre de lignes de `status.txt` et la clé de sa dernière ligne.

## 6. Attendu, item par item — la liste close de ce qui remonte

Tout ce qui n'est pas dans cette table reste au serveur, archivé, **jamais versionné ni ouvert**. Les items sont
vérifiés par `server/verify_attendu.py` sur les seuls `status.txt`, `alembic_before.txt`, `alembic_after.txt` et
`pilot_exit.txt`.

| # | Clés de `status.txt` | Attendu |
|---|---|---|
| 1 | `guard`, `pilot_sha256`, `pilot_copy` | `guard=0` au SHA S1 (complet) ; `krakenbot` du clone ; `protocol=d030ab23…79e6` ; `manifest=b757c45b…4f11` ; **`campaign_unlock=present`** ; `pilot_sha256` = sha du blob à S1 ; copie du pilote 0. Les gardes exigent aussi un arbre suivi propre, `poetry.lock` et `pyproject.toml` égaux à ceux du service, un `.env`, et aucune sortie déjà présente |
| 2 | `alembic_before`, `alembic_after`, `alembic_same_head` | `0`, `0`, `0` ; deux fichiers identiques portant `c3bd1e7a0001 (head)` |
| 3 | `service_before`, `service_after`, `tree_after`, `campaign_unlock_after` | service inchangé (HEAD, `dirty=0`, `collector=active`, même `NRestarts`) ; arbre du clone propre ; `present` |
| 4 | `workers`, `prefix` | `3` ; `0 event=-`. **Code 0 ⟹ base en lecture seule assertée par Postgres** (`probe_database`, `SHOW transaction_read_only = on`), sinon `database_read_failed` et 2 ; de même pour l'item 6 |
| 5 | `pre_anchor`, `registry_new_entry_pre`, `pre_entry`, `pre_benchmark`, `pre_select` | `0` ; **`true`** (inscription de la **variante v2**, nouvelle au registre ; son parent v1 y est déjà) ; `0` ; `0` ; `0` |
| 6 | `eval` | `0 event=evaluated`, **jamais** `refusal_form_written` |
| 7 | `chain`, `chain_steps`, `chain_verified`, `violations_empty`, `replay_violations_empty`, `registry_new_entry_chain`, `issue_inscrite`, `extract` | `0` ; `anchor:0,entry:0,benchmark:0,select:0,continuity:0` ; `true` ; `true` ; `true` ; `false` (étape 1 idempotente) ; `true` ; `0`. **Cinq codes d'étape, pas six** (correction A1 du chantier v1) : `run_chain` invoque exactement les cinq étapes de `c3_verdict.CHAIN_FILES` (`scripts/audit/c3_verdict.py:2016`) ; le code du verdict est celui de la chaîne elle-même (`chain=0`), pas un sixième pas |
| 8 | `issue`, `raison`, `selection_descriptive` | **`inconclusif`**, **`P_PROVENANCE`**, et **compté : non**, dérivé de `(issue, raison)` par la table du § 10.1 (décision Q1 du chantier v1, reconduite ; `verify_attendu.out`) ; `selection_descriptive=true` (le statut `SÉLECTION_DESCRIPTIVE` comparé par le pilote, jamais imprimé). **Tout autre triplet, y compris un triplet « meilleur », est un écart, donc un STOP — jamais une bonne surprise** |
| 9 | `interpreter` | `0` : les deux provenances nomment le `krakenbot` du clone |
| 10 | `halted_at`, toute clé | `-` ; aucune étape `NOT_RUN` |
| 11 | `pilot_exit.txt` | `0` |

**L'issue et la raison viennent du canal sanctionné** : la chaîne § L.2 que `c3_verdict chain` publie sur stdout (dix
champs ; inventaire du plan v1, K2).
- Le pilote n'en retient que la ligne au label exact `C3_GRID_ATR_V4_2026` ; une évaluation synthétique porterait
  `C3_SYNTH_` et ne correspondrait pas.
- Il contrôle sa forme : neuf champs nommés, dans l'ordre du code.
- Il n'imprime que `verdict` et `raison`, chacun validé contre sa liste close du § H.1 (sinon `hors_liste`).
- Il compare `statut_selection` à `SÉLECTION_DESCRIPTIVE` sans l'imprimer.

`verdict.json` n'est **pas** ouvert pour l'issue. Il l'est, en machine, pour quatre contrôles comme aux conformités
(`chain.verified`, violations, violations de rejeu, codes d'étape). Les deux `anchor.json` le sont pour
`registry.new_entry`. La lecture est inchangée mot pour mot depuis le chantier v1 (plan § 3).

**`compté` n'a aucun canal** hors du registre : `c3_verdict` l'inscrit avec l'issue et la raison, mais ne l'écrit ni sur
stdout ni dans `verdict.json`. Il est donc **dérivé, non lu**.
- La table du § 10.1 est recopiée du texte dans `verify_attendu.py` et épinglée aux constantes `COUNTED` et
  `UNCOUNTED_IF_REMOVED_BY` du code (`tests/table_10_1.out`).
- La ligne conditionnelle (`A_NO_ADMISSIBLE_CANDIDATE`) n'est pas dérivable sans lecture et rend `indéterminé` : un
  écart.

**Le rapport cite `verdict=` et `raison=` tels que la chaîne les écrit.** La chaîne complète (identité retenue,
continuité, variante, empreintes) reste archivée, jamais lue : limite déclarée au regard du § L.2 (« le rapport cite la
chaîne »), voulue par le brief.

## 7. Constats hérités, écrits en le sachant

- **(a) Le triplet est connu d'avance.** Provenance `contaminated` : `P_PROVENANCE` (rang 2 du § H.1) précède toute autre
  raison, et `R0_INVALID_RUN` sort en code 2 sans publication. **Toute chaîne en code 0 sur ce manifeste publie donc
  `inconclusif (P_PROVENANCE)`.**
  - Le triplet ne porte aucune information économique ; `validé` et `réfuté` sont inatteignables ; la voie du § 10.1 ne
    s'ouvre pas.
  - Un autre triplet signalerait un défaut d'instrument.
- **(b) La sélection est descriptive.** Elle est calculée et publiée sous `SÉLECTION_DESCRIPTIVE` (§ A.5 : un calcul
  descriptif reste autorisé ; table de statut du § H.1). L'évaluation porte sur la configuration retenue, chemin
  sélection seul.
- **(c) Non compté.** `P_PROVENANCE` n'est pas compté (`CONTRAINTES_POST_B4.md` § 10.1). Le registre portera, pour la
  variante v2 de la famille `grid-atr-v4`, un verdict non compté ; l'enregistrement v1 reste sans verdict.
- **(d) Relance unique (§ 10.1).** Ce run est la relance unique après correction d'instrument, **décision de Bruno** :
  après lui, plus aucune relance pour la famille grid, quel que soit le résultat. Un écart au préfixe ou à l'ancrage
  laisse le registre comme avant le run ; un écart après l'ancrage autonome y laisse l'enregistrement v2 sans verdict.
  **Dans tous les cas, un nouvel arrêt ferme la voie pour la famille ; la suite appartient à Bruno** (brief § 4).
  - Mécaniquement, après un verdict v2 non compté, le critère d'arrêt de l'ancrage accepterait encore une variante
    (deux verdicts non comptés requis). La fermeture tient à la décision écrite, pas au code (plan § 9, P1).
  - La conséquence au regard du § 10.2 relève de la clôture § K.2 de Bruno.
- **(e) Clôture de la famille, décidée avant le run.** La décision consécutive — clôture de la famille grid par la clause
  de clôture § K.2 de `docs/rejeu_grid_prespec.md` — est une décision de gestion de Bruno. Elle est inscrite à l'entrée
  24 **avant** le run, avec son auteur ; elle n'est jamais déduite du verdict (protocole § K.1).

## 8. Bornes des lectures

Ces données sont déjà explorées au sens du § D.1 (P6, P7, B4, rejeu grid, run v1 jusqu'au préfixe) : la portée reste
**rétrospective** (§ D.2). Lectures du producteur bornées :
- au préfixe : `≤ T`, amorçage `≥ début − 400 j` ;
- à l'évaluation : `≤ fin = 2026-06-29T00:00Z`, amorçage `≥ T − 400 j`.

**La date différée (2027-06-29) n'est lue par aucun module comme une fenêtre.** Appuis, sans lecture d'artefact :
- le code : `candles_artefact` refuse toute estampille `> fin`, et les lectures du préfixe sont bornées à `T` ;
- les tests ;
- les codes de chaîne : `continuity = 0` impose `period = [T, fin]` ; la règle d'entrée de `candles_eval.json` refuse,
  en code 2, toute estampille postérieure à la fin.

Ce n'est pas un journal de requêtes.

## 9. Non-lecture

- **Jamais à l'écran** : les sorties des producteurs et de la chaîne (`.json`, `.md`), le registre, les journaux,
  `extract.err` ; aucun listing, aucune taille, aucun sha d'artefact ; **aucun sha d'archive**. Il en va de même de
  `out/` du run v1, archivé par l'archive-préalable sans être ouvert.
- **Remonte au dépôt** :
  - `status.txt` : codes, noms d'événements de la liste close, booléens, `issue` et `raison` ;
  - `pilot_exit.txt` et les deux `alembic current` ;
  - `verify_attendu.out` : items, triplet constaté, compté dérivé ;
  - les sorties des scripts du run : `tests/archive_prealable.out`, `preflight.out`, `launch.out`, `wait.out`,
    `fetch.out`, `archive.out`, `postflight.out`.

  Avant S2, la règle 64 hex d'`interdits.sh` est balayée sur les quatre fichiers rapatriés (A4 du chantier v1).

## 10. Règle d'échec

- **Ce qui déclenche un STOP** : tout code différent de l'attendu, un triplet différent (« meilleur » compris),
  `chain.verified` faux, une violation, un refus d'entrée, une garde en échec, un item de `verify_attendu.out` en
  écart, tout besoin de toucher au manifeste, au code ou au texte.
- **Ce que le STOP impose** : constat versionné (`status.txt` et les extraits), **répertoire serveur laissé en place, ni
  archive ni suppression**, rien de relancé, **aucune lecture de diagnostic sans l'accord de Bruno**. Un run compté ne
  se réessaie pas — **et celui-ci est la relance unique : un nouvel arrêt ferme la voie pour la famille**.
- **Échecs qui ne sont pas une relance** : aucun n'écrit au registre ni ne lance le run compté.
  - Un **refus de preflight** (rien lancé, rien écrit) se re-tente après l'accord de Bruno (A5 du chantier v1).
  - Un **échec de l'archive-préalable**, selon le moment :
    - sonde ou préalables en écart : rien touché ;
    - contrôle de système de fichiers en écart : un répertoire d'archive vide reste, qu'un nouvel essai refuserait ;
    - écart après le `mv` : `out/` déplacé, `repo/` en place, script non rejouable, preflight et lancement bloqués,
      et seul un geste de Bruno débloque.

## 11. Les vérificateurs, prouvés avant de servir

- **`tests/manifest_check.out`** (`rc=0`) : § 2. **`tests/manifest_check_rouge_avant_entree24.out`** : la même vérification
  lancée avant l'écriture de l'entrée 24 — tout tient, sauf le titre au journal, rouge (`rc=1`) : le contrôle mord.
- **`tests/events.out`** (`rc=0`) : la liste close `EVENTS` du pilote égale celle du code (54 = 54).
- **`tests/pilot_dryrun.out`** (`rc=0`) : le pilote tourne dans un monde simulé, avec six lignes substituées et comptées.
  - Le monde : clone, faux interpréteur, faux `systemctl`, registre simulé, marqueur de simulation au lieu de
    `CAMPAIGN_UNLOCK`.
  - Les huit simulations du v1 : conforme → 0 ; triplet « meilleur » → 1 ; forme de refus → 1 (chaîne `NOT_RUN`,
    registre simulé sans verdict) ; échec du préfixe → 1 (registre simulé jamais créé) ; violation de chaîne → 1 ;
    `new_entry` faux → 1 ; SHA faux → 2 ; sans marqueur → 2.
  - Limites dites : `bash` local 3.2, serveur 5 ; le registre simulé part absent alors que le registre réel porte v1.
    Le pilote ne lit jamais le registre ; la parenté est prouvée par `manifest_check`.
- **`tests/mutants_pilote.out`** (`rc=0`, détail d'exécution) : trois mutants temporaires du pilote font chacun échouer
  le dry-run — contrôle du triplet retiré, arrêt au premier écart désactivé, garde `CAMPAIGN_UNLOCK` inversée. Le pilote
  est ensuite restauré, `cmp` à 0.
- **`tests/verify_adverse.out`** (`rc=0`) : `verify_attendu.py` rend 0 sur le témoin (le `status.txt` de la simulation
  conforme) et 1 sur chacun des **31 cas déviés**, avec exactement un item en écart.
- **`tests/table_10_1.out`** (`rc=0`) : la recopie du § 10.1 égale les constantes du code ; deux mutants de la recopie
  mordent ; `(inconclusif, P_PROVENANCE)` dérive « non compté ».
- **`tests/archive_dryrun.out`** (`rc=0`, détail d'exécution) :
  - les corps distants des deux scripts d'archive sont égaux à l'octet à celui du v1 ;
  - les cinq cas du v1 (date 20261001), plus `conforme_v2` (date 20261002, l'archive v1 préexistante restée intacte) ;
  - la sonde de l'archive-préalable, cinq cas ;
  - les enveloppes sous faux `ssh` : refus local d'`archive.sh` sans « 11/11 » (0 appel), passage avec (1 appel) ;
    sonde en écart (corps non lancé) ; date figée 20261001 portée par l'appel du corps ; argument refusé ;
  - la ligne `jour_lancement` du preflight (A1') : 20261001 refusé, 20261002 admis.
- **`tests/mutants_archive.out`** (`rc=0`, détail d'exécution) : quatre mutants temporaires font chacun échouer
  `archive_dryrun` — précondition 11/11 d'`archive.sh` retirée, contrôle de la sonde d'`archive_prealable.sh` neutralisé,
  date figée de l'archive-préalable changée, seuil A1' du preflight abaissé à 20261001. Les scripts sont ensuite
  restaurés, `cmp` à 0.
- **`tests/stop1_registre.out`** (`rc=0`) : le contrôle du registre du § 4, extrait d'ici, témoin `True`, dix
  déviations jamais `True`.
- **`tests/interdits_*.out`** et **`tests/interdits_adverse.out`** (`rc=0`) : § 3 du brief ; les deux cas du pilote
  (faute de frappe dans un littéral `--registry`, troisième ligne `--registry`) et le chantier v1 touché mordent.
- **`tests/lint.out`**, **`tests/reprise.out`** (`rc=0`).

## 12. Après le run

1. `fetch` (quatre fichiers).
2. Règle 64 hex balayée (A4).
3. `verify` (11/11 exigé ; `archive.sh` le refuse localement sinon).
4. **Seulement alors** `archive` : `~/archive/c3_campagne_grid_<AAAAMMJJ du jour, ≥ 20261002>/out`, déplacé, en lecture
   seule, jamais supprimé. La seule suppression est celle du clone v2, sous gardes (A3).
5. `postflight` : les deux archives, `~/runs/c3_campagne_grid` absent.
6. Rapport `report.md`, issue de l'entrée 24 et jalon § 10.2 daté.
7. **STOP 2.**

**Cérémonie de Bruno, après STOP 2** (listée au rapport, jamais exécutée par l'agent) :
- vérification des clés de racine du registre (le contrôle du § 4 ne vaut plus après l'inscription de v2 : runbook § 1
  sans `variants == {}`) ;
- sauvegarde du registre (runbook § 2) ;
- merge ;
- clôture § K.2 effective au journal ;
- suppression de `CAMPAIGN_UNLOCK`.
