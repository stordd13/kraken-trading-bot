# Plan — Seconde campagne C3 comptée, famille `grid-atr-v4` : relance unique après correction d'instrument (plan court — GO du 2026-10-02)

Brief `agent/AGENT_C3_CAMPAGNE_GRID_V2.md` (non suivi, brief § 3). Branche `feat/c3-campagne-grid-v2` depuis `dev` @
`cce566d82f40166d9ff95c972e346b26831ed304`. Modèle direct : le chantier v1 `results/c3_campagne_grid/` (mergé). Ce
chantier exécute la cérémonie du run compté — un lancement, aucun retry, aucun écart arbitré — et ne décide rien du
fond. **GO de Bruno le 2026-10-02 sur ce texte, avec les amendements A1' et A2' (§ 10), intégrés : dérouler C0 → S1,
puis STOP 1.**

## Contexte

Le run compté v1 (S1 `cd4b177`) s'est arrêté à `c3_entry` en code 1 : 64/96 violations `warmup_series` (manifeste v1 :
liste pleine `{1d,1w,4h}` pour les 96 candidats ; classmethod : `{1d,4h}` pour `none`/`1d_only`). Correction = le
manifeste v2, gelé le 01/10, sans changement de code. Le registre porte la variante v1 sans verdict ; le v2 est une
**nouvelle inscription** dont elle est le parent. Attendu inchangé : `inconclusif (P_PROVENANCE)`, non compté,
`SÉLECTION_DESCRIPTIVE`.

## 0. Constats de lecture (lecture seule, avant tout geste)

- **Gel** : `agent/manifest_campagne_v2_draft.json` sha256 `b757c45b…4f11`, 38 507 octets — **conforme**. HEAD = `cce566d`
  (complet) = tip de `dev` ; arbre propre hors brief et brouillon v2 (non suivis ; ils le restent, brief § 3).
- **Code** : diff vide `235461e..cce566d` sur `src scripts tests config pyproject.toml poetry.lock .github skills
  CLAUDE.md`, protocole et contraintes. Le code du run v2 est celui du run v1 et de la conformité R-4.
- **Manifeste v2 − v1** (diff structurel) : `parent` (`is_root: false`, `variant_key 3159a907…fcb5`), `variant_id`
  (`…-v2`), `research_log_entry` (entrée 24), `run_scope`, **96 surcharges `decision_timeframes`** (32 × `{1d,1w,4h}`
  pour `1w_only`, 64 × `{1d,4h}`). Le reste à l'identique. Empreintes 64 hex du fichier : protocole et clé du parent.
- **Parenté** (calcul local) : `sig(canon(v1 commité)) == parent.variant_key` ; clé v2 `16d6a8f552c8cc19…`. Parent
  absent du registre → `R0_INVALID_RUN`, code 2. L'enregistrement v1 sans verdict n'entre pas dans `stop_criterion`.
- **Critère a06** (`c3_entry.py:496`, en ensemble, contre l'export du producteur) : **v1 → 64 désaccords (= le
  diagnostic), v2 → 0**.
- **Serveur, attendu** (constaté au premier pas du run) : `~/runs/c3_campagne_grid/campagne/` en place (clone `cd4b177`,
  `.env`, copie de `CAMPAIGN_UNLOCK`, `out/` avec `pilot_exit.txt`) ; aucune archive v1. Aucun composant de chemin nommé
  `out` dans les arbres suivis (`cd4b177`, `cce566d`) ni dans les 24 refs distantes : la garde A3 tient sur le clone.
- **Durée** : préfixe v1 mesuré 43 min 40 s → central ≈ 55 min ; sonde 120 s × 120, plafond 4 h, inchangés.
- **`--now`** : littéral **identique** au v1, `2026-10-01T00:00:00+00:00` (gel v2 du même jour, même règle que la graine
  `20261001`) ; il entre dans `first_registered_at` de la variante v2.

## 1. D-pilote — `results/c3_campagne_grid_v2/server/run_campagne.sh`

Repris du pilote v1 par substitutions comptées (`reprise.out`). Changent : **trois lignes de code** — `SELF`, `MANIFEST`
(chemins `results/c3_campagne_grid_v2/…`), `MANIFEST_SHA` (`b757c45b…4f11`) — et les commentaires qui nomment le
chantier, le plan, le chemin de la commande ou la « première inscription » (→ inscription de la variante v2, parent déjà
au registre). Le SHA S1 n'est pas un littéral : c'est l'argument du pilote, de `launch.sh` et de `verify.sh`.

Inchangés au caractère : **les deux lignes `--registry /home/bruno/c3/registry/variants.json`** (les deux seules),
`--campaign GRID_ATR_V4_2026` (ancre `^C3_GRID_ATR_V4_2026`), `WORKERS=3`, `NOW`, `EVENTS` (54, re-prouvé), `STEPS_OK`,
**`RUN=/home/bruno/runs/c3_campagne_grid/campagne`** (le run v2 réutilise le chemin du v1, § 2), gardes, arrêt au
premier écart, contrôles « après » inconditionnels, extraction. `nice -n 10`, tmux `c3-campagne-grid-<AAAAMMJJ>`.
`launch.sh` : la branche (`feat/c3-campagne-grid-v2`, deux lignes) et les chemins du dépôt ; `wait`, `fetch` : les
chemins du dépôt seulement.

## 2. D-archive-préalable (nouveau) — `tests/archive_prealable.sh`

- **Copie de `results/c3_campagne_grid/tests/archive.sh`, corps distant (heredoc `REMOTE`) identique à l'octet**
  (`cmp` des corps extraits : `archive_dryrun.out`, `reprise.out`). Une copie, parce que le script v1 écrirait sa
  sortie dans l'arbre gelé du v1. Gardes A3 inchangées : préalables (`out/pilot_exit.txt` présent, aucune session
  `^c3-campagne-grid-`, archive absente) → `mkdir -m 700` → même système de fichiers → `mv campagne/out` → noms avant =
  après → `chmod -R a-w` → aucun inscriptible → ni `repo/` ni `.env` → témoins → aucun composant `out` résiduel → la
  seule suppression, `rm -rf /home/bruno/runs/c3_campagne_grid` en littéral absolu → absence vérifiée.
- **Date figée au jour du run v1 : archive `~/archive/c3_campagne_grid_20261001/out`** (littéral dans le wrapper, pas
  d'argument). Elle est libre (le v1 n'a jamais archivé) ; un second appel est refusé par la garde du corps
  (`archive_absente_avant`) ; l'archive du run v2 (jour ≥ 20261002) ne la heurte pas, si bien que **le corps de
  l'archive v2 reste celui du v1** (§ 4). Le preflight ne change que son chemin de sortie et le contrôle
  `jour_lancement` d'A1' (§ 10) ; son contrôle `archive_du_jour` porte sur le jour du lancement.
- **Sonde en lecture seule avant le corps** (wrapper, corps intouché) : même périphérique pour `campagne/out` et
  `~/archive` (`stat -c %d`, forme GNU jamais exercée au serveur), forme GNU de `find -perm /222` acceptée ; écart →
  refus, rien touché.
- Le clone v1, sa copie du `.env` et sa copie de `CAMPAIGN_UNLOCK` disparaissent là ; `out/` v1 archivé tel quel,
  jamais ouvert (ni taille, ni compte, ni sha).
- **Premier pas du run, après le GO de lancement. Conditionne le lancement** : `launch.sh` (`mkdir $RUN`) refuse un
  répertoire existant, le preflight refuse `run_dir=PRESENT`.
- **Échecs, dits exactement** : sonde ou préalables en écart → rien touché, STOP ; écart au contrôle de système de
  fichiers → un répertoire d'archive vide reste, et un nouvel essai serait refusé par sa propre garde ; écart après le
  `mv` → `out/` déplacé, `repo/` en place, script non rejouable (`pilote_termine`), preflight et lancement bloqués —
  STOP, seul un geste de Bruno débloque. Aucun de ces cas n'écrit au registre ni ne lance le run compté.

## 3. D-lecture du verdict — inchangée mot pour mot (plan v1 § 2)

Canal sanctionné : la chaîne § L.2 de `c3_verdict chain` sur stdout (`logs/chain.log`, jamais affiché), heredoc ancré
`^C3_GRID_ATR_V4_2026 | verdict=` (une ligne exactement), liste close : `issue` (3), `raison` (13 + `-`),
`selection_descriptive` (comparé, jamais imprimé), `issue_inscrite` (forme fixe). Booléens mécaniques de
`chain/verdict.json` et des deux `anchor.json` (`registry_new_entry_pre` vrai, `registry_new_entry_chain` faux).
**`compté` dérivé, non lu**, par la table du § 10.1 recopiée et épinglée à `c3_verdict.COUNTED` /
`UNCOUNTED_IF_REMOVED_BY` (`table_10_1.sh`). Jamais un champ d'issue, d'identité, de métrique hors canal.

## 4. D-archive — inchangée (plan v1 § 3)

`tests/archive.sh` : corps distant **identique à l'octet** à celui du v1 (`~/archive/c3_campagne_grid_<AAAAMMJJ du jour>/out`,
`rm -rf /home/bruno/runs/c3_campagne_grid` sur le clone v2). Une seule addition, locale : **refus avant tout `ssh` si
`server/verify_attendu.out` ne porte pas 11/11 et `rc=0`** — la règle « seulement après verify » devient mécanique ;
prouvé par un faux `ssh` en tête de `PATH` qui consigne tout appel (aucun appel réel possible). Écart à l'attendu =
STOP : ni archive ni suppression.

## 5. D-postflight — inchangé (plan v1 § 4), plus l'archive v1

`postflight.sh <date archive v2> <HEAD service du preflight> <NRestarts du preflight>` : lecture seule ;
`~/runs/c3_campagne_grid` absent ; aucune session `^c3-campagne-grid-` ; **les deux archives** (`…_<date v2>` et
`…_20261001`, littéral) présentes, en lecture seule, sans `repo/` ni `.env` ; collector actif, `NRestarts` = preflight ;
HEAD du service = preflight, 0 ligne sale ; `alembic` `c3bd1e7a0001 (head)` ; `CAMPAIGN_UNLOCK` du service présent.
**Jamais `~/c3/`.** Cérémonie de Bruno, listée au rapport : clés de racine (runbook § 1 étendu, A2'), sauvegarde (§ 2),
merge, clôture § K.2 effective au journal, suppression de `CAMPAIGN_UNLOCK` après le merge.

## 6. S1 — le gel entre au dépôt (contenu)

- `manifest.json` = le brouillon à l'octet (`cmp`), `sha256sum` = `b757c45b…4f11`.
- `tests/manifest_check.sh` : contrôles de forme v1 (96 distincts, 365,000000 j, `contaminated`, graine, 8 estampilles,
  protocole v2.3) avec `parent` non racine ; titre cité par le manifeste présent **une fois**, en chaîne fixe
  `### <titre> (entrée 24,`, entre l'issue de l'entrée 23 et « Essais à venir ». **Plus** : (a) surcharge =
  `GrokGridATRAdaptiveV4.decision_timeframes(params)` triée, 96/96, et critère a06 en ensemble contre l'export du
  producteur : v2 → 0 ; **adverse : le même contrôle sur le manifeste v1 commité → 64** ; (b) `parent.variant_key ==
  sig(canon(v1 commité))` ; (c) ancrage local, registre temporaire hors dépôt, sel factice écrit au fichier
  (`secrets.token_hex(32)`, jamais imprimé), **v1 inscrite par `c3_anchor` lui-même** sur le manifeste v1 commité, même
  `--now`, puis trois cas, un journal par cas : registre vide (sel seul) → **2**, refus de parenté, registre inchangé ;
  avec v1 → **0**, nouvelle au registre, `T = 2024-11-22T04:48:00+00:00`, préfixe 1 362,2 j, 96 candidats, racine et
  enregistrement v1 inchangés (booléens) ; re-run → **0**, idempotent, registre inchangé. N'imprime de `anchor.json`
  que T, préfixe, évaluation, n, `new_entry` (jamais `variant_key`, `registry.sha256`, `manifest_sha256`,
  `inputs_sha256`) ; journaux filtrés par liste blanche (`ancrage T =`, `variante … — …`, `provenance …`, `ENTREE
  REFUSEE … absent du registre`), jamais `written … sha256`. Temporaires supprimés.
- `attendu.md` : modèle v1, 11 items (brief § 2.2 : variante neuve à l'item 5 ; cinq codes d'étape, renvoi
  `c3_verdict.CHAIN_FILES`, `c3_verdict.py:2016` ; triplet `inconclusif` / `P_PROVENANCE` / non compté, tout autre =
  STOP). **Réécrits pour v2** : § 3 « Limites » — avec un parent, un registre absent ou une faute de frappe dans un
  littéral `--registry` ne crée plus rien en silence : refus R0 à `pre_anchor` (ou à l'étape 1 de la chaîne), donc un
  nouvel arrêt qui ferme la voie ; parades : relecture A2 au caractère, contrôle mécanique d'`interdits.sh`, clause
  étendue du § 1 du runbook (A2') ; § 7 (d) relance unique ; §§ 9, 11, 12 (archive-préalable, `archive_dryrun`,
  chemins) ; la ligne d'A1' ; le one-liner d'A2' entre ses marqueurs. Les empreintes v1 citées sont tronquées.
- `server/verify_attendu.py` : `MANIFEST_SHA`, libellé de l'item 5 (« inscription de la variante v2, nouvelle au
  registre ») et chemin d'usage ; `KRAKENBOT_SUFFIX` inchangé.
- `docs/RESEARCH_LOG.md`, **entrée 24**, après l'issue de l'entrée 23, avant « Essais à venir », titre exact du
  manifeste, colonnes du journal : périmètre (96 candidats avec surcharges par candidat, fenêtre, `T`) ; données (8
  estampilles, renvoi 13) ; code (S1, protocole `d030ab23…`, manifeste `b757c45b…`, parent `3159a907…` renvoi 23) ;
  coûts inchangés ; attendu déclaré ; **§ 10.1 : relance unique après correction d'instrument, décision de Bruno —
  aucune relance ensuite, quel que soit le résultat** (P1) ; décision consécutive : clôture § K.2 de
  `docs/rejeu_grid_prespec.md`, travail de mécanisme pour les familles suivantes. Issue dans une section suivante.
- Scripts repris de `results/c3_campagne_grid/tests/` par substitutions comptées (`reprise.out`, chaque diff recopié,
  64 hex tronqués) : preflight, launch, wait, fetch, verify, archive, archive_prealable, postflight, verify_adverse,
  pilot_dryrun, mutants_pilote, events, table_10_1, archive_dryrun, manifest_check, interdits (+ adverse), lint, tunnel,
  ci_status, reprise ; neuf, sans source : `stop1_registre.sh` (A2'). Non repris : les trois scripts du diagnostic v1.
  Re-prouvés avant de servir : `pilot_dryrun` (8 simulations du v1, six lignes substituées), `mutants_pilote` (3),
  `verify_adverse` (témoin + 31), `table_10_1`, `archive_dryrun` (`cmp` des trois corps ; 5 cas, dont l'archive
  `…_20261001` préexistante restée intacte ; la sonde et le refus local du wrapper v2 sous faux `ssh` ; aucun fichier
  nommé `CAMPAIGN_UNLOCK`, un marqueur à la place), `stop1_registre` (A2'), `events` (54 = 54), `lint`.
- `interdits.sh` : base `cce566d…` ; diff vide sur tout, **y compris `results/c3_campagne_grid/**`** ; liste blanche
  `results/c3_campagne_grid_v2/**` ∪ `docs/RESEARCH_LOG.md` (ajouts seuls) ; règle 64 hex : table d'Adoption ∪
  fichiers du chantier ∪ {`b757c45b…4f11`, `3159a907…fcb5`} ; registre nommé sur les deux seules lignes `--registry`
  du pilote ; `CAMPAIGN_UNLOCK` absent en local ; brief et brouillon v2 non suivis. Adverse : cas v1 + chantier v1
  touché (fichier suivi modifié ; fichier non suivi ajouté) → rc≠0 ; témoin positif : la clé du parent admise.

## 7. Commits et gates (branche assertée et `interdits.sh` avant chaque commit)

| Pas | Contenu | Poussé |
|---|---|---|
| G0 | `git switch -c feat/c3-campagne-grid-v2 cce566d82f40166d9ff95c972e346b26831ed304` ; HEAD complet vérifié ; `tunnel.sh state` (fermé attendu, aucun besoin du tunnel) | — |
| C0 `docs(results)` | `plans/plan.md` (ce plan, GO), `interdits.sh` + adverse et sorties, `tunnel.sh` et sa sortie | non |
| **S1** `docs(research)` — **SHA du run** | § 6 entier, entrée 24 | oui, CI lue |
| **STOP 1** | Bruno relit au SHA S1 complet : attendu (dont le one-liner d'A2'), entrée 24, pilote (**les deux littéraux `--registry` au caractère près**), `manifest_check`, archive-préalable ; **crée `CAMPAIGN_UNLOCK`**, exécute le § 1 étendu livré (sortie `True`) ; GO de lancement nommant S1, **à partir du 2026-10-02 UTC** (A1') | |
| Run | archive-préalable → preflight (lecture seule ; rc≠0 → STOP) → launch → wait (arrière-plan) → fetch (4 fichiers) → balayage 64 hex → verify (11/11) → archive → postflight | |
| S2 `docs(results)` | preuves du run, `report.md`, issue de l'entrée 24 + jalon § 10.2 daté, `ci_status_S1.out` | oui, CI lue |
| S3 | `ci_status_S2.out` | oui |
| **STOP 2** | merge par Bruno | |

Règle d'arrêt (brief § 4) : tout code ou triplet hors attendu, `chain.verified` faux, une violation, un refus, une
garde en échec, tout besoin de toucher manifeste, code ou texte → STOP, constat versionné, répertoire serveur en place,
rien relancé, rien lu en diagnostic sans l'accord de Bruno. Relance unique : un nouvel arrêt ferme la voie.

## 8. Vérification

Avant S1, tout à `rc=0` : `manifest_check` (3 cas, parent, 96/96, adverse v1 = 64, titre), `events`, `reprise`,
`pilot_dryrun` (8/8), `mutants_pilote`, `verify_adverse`, `table_10_1`, `archive_dryrun`, `stop1_registre`, `lint`,
`interdits` + adverse ; `pytest` : code inchangé (diff vide prouvé), rejoué par la CI sur S1. Après le run :
`verify_attendu.out` 11/11, balayage 64 hex des 4 fichiers, postflight `rc=0`, `interdits` au tip.

## 9. Points soumis à Bruno avec le plan

- **P1 — § 10.1 au-delà du brief.** Le texte : « un second verdict non compté sur la même famille la déclare *non
  testable sous cet instrument* ; elle est alors comptée dans le budget du § 10.2 ». Que le v1 (sortie code 1, aucun
  verdict) soit le premier « non compté » est une lecture ; le registre ne le compte pas, et après le verdict v2
  `stop_criterion` accepterait une troisième variante (1 < 2) : la fermeture tient à la décision écrite de Bruno, pas
  au code. Proposition : l'entrée 24 n'écrit que sa décision telle que le brief la cite ; la conséquence § 10.2 reste
  à sa clôture § K.2.
- **P2 — avant le GO de lancement, deux gestes de Bruno, hors brief.** (i) Au § 1 du runbook rejoué, une clause
  booléenne de plus, même forme, sortie `True` seule : la clé du parent `3159a907…fcb5` présente, sans `verdict`, seule
  variante. Motif : avec un parent, un registre absent ou altéré ferait refuser l'ancrage (R0, code 2) et consumerait
  la relance unique — sa vérification est la seule parade côté registre réel, l'agent ne peut pas la faire. (ii) Une
  sauvegarde datée (runbook § 2) avant le lancement si aucune n'a été faite depuis la première inscription.

## 10. Décisions de Bruno au GO (2026-10-02), intégrées

- **A1'** — une ligne à `attendu.md` et un contrôle au preflight : **GO de lancement à partir du 2026-10-02 UTC** ; un
  lancement le 01/10 est refusé mécaniquement (l'archive du run v2 de ce jour porterait le nom de l'archive v1,
  `c3_campagne_grid_20261001`). Preflight : `jour_lancement` (jour UTC ≥ `20261002`, sinon `remote_ok=1`), en plus
  du contrôle `archive_du_jour`, inchangé.
- **A2'** — le one-liner du § 1 étendu (P2 i) est **livré dans les fichiers S1** (`attendu.md`, bloc entre deux
  marqueurs) et relu au STOP 1, jamais improvisé. Une seule expression booléenne, sortie `True` seule : les clauses du
  runbook § 1 sans `variants == {}` (racine exactement `salt`, `variants` ; sel de 64 hex), plus le mode `600` en
  booléen (au lieu de `stat`, qui imprimerait la taille), plus la clé du parent `3159a907…fcb5` seule variante, sans
  `verdict` ni `deferred_evaluation`. **Prouvé avant de servir** par `tests/stop1_registre.sh` : le bloc est extrait
  d'`attendu.md` lui-même, le chemin du registre (construit dans le script, jamais écrit) remplacé par celui d'un
  registre fabriqué hors dépôt — exactement une substitution, sinon rien n'est exécuté ; témoin (sel factice, mode
  600, enregistrement v1 écrit par `c3_anchor` sur le manifeste v1 commité) → `True` ; chaque déviation → `False` ou
  code ≠ 0, jamais `True` : mode 644, parent absent, parent avec `verdict`, avec `deferred_evaluation`, variante en
  trop, clé de racine en trop, sel court ou non hexadécimal, fichier absent, JSON illisible. Sortie committée :
  `True` / `False` / codes seulement.
- **P1** accepté : l'entrée 24 porte la décision de Bruno telle que le brief la cite ; la conséquence § 10.2 reste à
  sa clôture § K.2.
- **P2 (i)** accepté avec A2'. **P2 (ii)** satisfait : sauvegarde datée du 01/10, postérieure à la première
  inscription, déjà faite (consigné à `attendu.md`, cérémonie du registre).
