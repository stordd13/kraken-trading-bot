# Plan — Première campagne C3 comptée, famille `grid-atr-v4` (plan court — GO du 2026-10-01)

Brief `agent/AGENT_C3_CAMPAGNE_GRID.md`. Branche `feat/c3-campagne-grid` depuis `dev` @ `235461e8a4beac42ecb57cc75ab13e8d88dfac14`.
**GO de Bruno le 2026-10-01 sur ce texte**, après sa relecture : Q1-Q3 tranchées, amendements A1-A5 intégrés (§ 8). Ce chantier exécute la cérémonie du run compté : un lancement, aucun retry, aucun écart arbitré.

## 0. Constats de lecture (avant tout geste)

- **Manifeste** `agent/manifest_campagne_draft.json` : sha256 `d422076b09292d8aeb2a6ae3f39b9c37325f23e954c05c6c83a8979255325041`,
  30 202 octets — **conforme**. HEAD = `235461e` sur `dev`, arbre propre hors brief et brouillon (non suivis).
- **K1 — `CAMPAIGN_UNLOCK`** : `c3b_common.CAMPAIGN_UNLOCK = PROJECT_ROOT/results/c3b_producteur/CAMPAIGN_UNLOCK`, racine du
  code exécuté, donc **le clone créé au lancement**. La garde d'arbre du producteur ignore les non-suivis
  (`--untracked-files=no`). → **Q2 (Bruno) : créé dans l'arbre du service, transporté dans le clone par `launch.sh`.**
- **K2 — sortie de `c3_verdict chain`** (`c3_verdict.py:1984-2007`) : sur stdout, la chaîne § L.2 à dix champs
  (`C3_<campagne> | verdict= | raison= | selection= | statut_selection= | continuite= | variante= | provenance= | protocole=
  | observations=`), puis motif, estimabilité, portes Q, `written …/verdict.json sha256 …` et `written <registre> (issue
  inscrite, § A.6)` (forme fixe, D13). **`compte` n'est publié nulle part hors du registre** (`inscription = {issue, raison,
  compte}`, `:1916-1920`) : ni stdout, ni `verdict.json`. → STOP-question du brief posée : **Q1 (Bruno) : dérivé, non lu.**
- **K3 — registre absent** : `load_registry` rend `{"variants": {}}` si le fichier n'existe pas, et `write_json_strict` crée
  fichier et répertoire (`mkdir parents`) : un registre **sans sel** serait créé en silence, `new_entry` vrai comme dans le
  cas normal. L'agent ne peut pas le voir (aucun stat de `~/c3/`). Écriture en place : mode 600 préservé, non atomique.
- **K4 — inscriptions** : l'ancrage autonome sur le registre persistant fait la **première inscription** (`new_entry` vrai) ;
  l'étape 1 de `chain` y est idempotente (`new_entry` faux) ; l'étape 6 inscrit l'issue une fois. Manifeste racine
  (`parent.is_root`) refusé dans un registre non vide (R0, code 2).
- **K5 — triplet** : sous `contaminated`, toute chaîne en code 0 publie `inconclusif (P_PROVENANCE)` (§ H.1, rang 2 ; R0 sort
  en code 2 sans publication). Le triplet ne porte aucune économie ; tout autre triplet est un défaut d'instrument.
- **K6 — « § K.2 »** du brief = clause de clôture de `docs/rejeu_grid_prespec.md` § K.2 (le § K.2 du protocole est
  « Découverte annexe »). Clôture de famille = décision de gestion, annoncée avec auteur et motif, jamais déduite d'un
  verdict (protocole § K.1) : l'entrée 23 l'écrit comme décision de Bruno, prise avant le run.
- **K7 — temps mesurés** : conformité R-4 (12 cand. × 249,9 j) préfixe 39-40 s à 4 workers, 127 s à 1 ; chaîne 1-4 autonome
  + évaluation 11-12 s ; chaîne 3 s. Rejeu grid (96 configs, 210 432 cand.-jours) 57,4 min à 3 workers `nice -n 10`.
  Serveur : 4 CPU, 5 934 Mo disponibles au dernier preflight.

## 1. D-pilote — `results/c3_campagne_grid/server/run_campagne.sh`, repris de `run_conformite.sh` (R-4)

- **Un seul run**, exécuté depuis le clone au SHA S1 (garde : SHA, pilote du clone, arbre suivi propre, `poetry.lock` et
  `pyproject.toml` = service, `krakenbot` du clone, `.env`, protocole `d030ab23…79e6`, manifeste `d422076b…5041`,
  **`CAMPAIGN_UNLOCK` présent dans le clone** — garde inversée ; refus = 2). Ni triple exécution ni registre jeté.
- **Ordre** : `c3b_prefix` → `c3_anchor`, `c3_entry`, `c3_benchmark`, `c3_select` autonomes → `c3b_evaluate --selection` →
  `c3_verdict.py chain`. Sorties directement sous `out/{prefix,pre,eval,chain,logs}` (plus de `work/` : la contrainte du
  même chemin ne servait qu'à l'égalité au bit entre exécutions).
- **Registre** : `--registry /home/bruno/c3/registry/variants.json` en littéral sur les **deux seules** lignes qui le
  portent (ancrage autonome, `chain`) ; nommé nulle part ailleurs ; ni copié, ni testé, ni stat.
- **`--campaign GRID_ATR_V4_2026`** (étiquette d'instrument, dette 21) ; **`--now 2026-10-01T00:00:00+00:00`** (date du gel,
  même règle que la graine ; antérieure à tout lancement possible ; elle entre aussi dans `first_registered_at`).
- **Arrêt au premier écart (changement assumé par rapport aux conformités)** : chaque étape ne tourne que si toutes les
  précédentes ont rendu leur attendu ; sinon `<étape>=NOT_RUN` et `halted_at=<étape>`. Motif : sur un registre persistant
  et compté, aucune écriture (ancrage, inscription d'issue) ne doit suivre un écart constaté. Un écart au préfixe laisse le
  registre vierge ; un écart après l'ancrage laisse un enregistrement sans verdict (relance du même manifeste idempotente).
  Contrôles « après » **inconditionnels** : `alembic` après, service, arbre du clone, `CAMPAIGN_UNLOCK`.
- **`--workers 3`**, lancement sous `nice -n 10` (précédent du rejeu grid, même famille, même serveur) : 4 workers saturent
  les 4 CPU partagés avec Postgres et le collector, et le skill donne ~1 Go par worker sur 3 ans (ici 1 762 j avec
  l'amorçage, ~1,6 Go estimé). Déterminisme indépendant des workers prouvé (4 = 1 au bit, trois conformités).
  Preflight (lecture seule) : refus si mémoire disponible < 5 000 Mo ou si `CAMPAIGN_UNLOCK` est absent de l'arbre du
  service (existence seule, contenu jamais lu). **Un refus de preflight = rien lancé, rien écrit (ni serveur, ni
  registre) : re-tenter le preflight après l'accord de Bruno n'est pas une relance du run compté** (A5).
- **Durée, le calcul** : préfixe 96 × 1 362,2 j = 130 771 cand.-jours = 43,6 × la conformité. Débit du rejeu à 3 workers
  61,1 cand.-j/s → **≈ 36 min** ; par la conformité (23,6 cand.-j/s/worker, ×2,4 à 3 workers) ≈ 38 min. Après le préfixe :
  ≤ 43,6 × 12 s ≈ 9 min (majorant : l'évaluation ne croît que ×5,45) ; chaîne ≤ 43,6 × 3 s ≈ 2 min. **Central ≈ 45 min,
  majorant ≈ 50 min.** Attente : sonde toutes les **120 s**, **120 sondes (plafond 4 h)** ; au-delà rc=1, STOP, rien tué.
  La sonde n'imprime que `exit=`, le nombre de lignes de `status.txt` et la **clé** de sa dernière ligne (jamais la valeur).

## 2. D-lecture — ce qui remonte, liste close

- **Codes** : gardes, `pilot_sha256`, préfixe (+ événement de la liste close `EVENTS`, re-prouvée égale au code), les
  quatre étapes autonomes, évaluation (+ `evaluated`), `chain` — **cinq codes d'étape** (`c3_verdict.CHAIN_FILES`,
  `scripts/audit/c3_verdict.py:2016` : anchor, entry, benchmark, select, continuity) **et le code de la chaîne elle-même**,
  que rend le verdict (A1 : le « six » du brief § 2.2 comptait le verdict comme une étape) —, extractions, `alembic` ×2,
  service avant/après, arbre, `CAMPAIGN_UNLOCK` après, `halted_at`, `pilot_exit`.
- **Issue et raison — canal sanctionné : la chaîne § L.2 que `c3_verdict chain` publie sur stdout** (`logs/chain.log`,
  jamais affiché). Un heredoc ne retient que la ligne ancrée `^C3_GRID_ATR_V4_2026 \| verdict=` (exactement une ; un
  label `C3_SYNTH_` ne correspond pas) et n'imprime que : `issue=` (∈ {validé, réfuté, inconclusif}, sinon `hors_liste` /
  `absent`), `raison=` (∈ les 13 raisons du § H.1 ou `-`, sinon `hors_liste`), `selection_descriptive=true|false`
  (comparaison du champ à `SÉLECTION_DESCRIPTIVE`, jamais imprimé), `issue_inscrite=true|false` (présence de la ligne de
  forme fixe). Aucun autre champ de la ligne. `verdict.json` n'est **pas** ouvert pour l'issue.
- **Contrôles, comme aux conformités** (heredoc, booléens) : `chain/verdict.json` → `chain_verified`, `violations_empty`,
  `replay_violations_empty`, `chain_steps` ; `pre/anchor.json` → `registry_new_entry_pre` (attendu vrai) ;
  `chain/anchor.json` → `registry_new_entry_chain` (attendu faux, idempotent). Jamais un champ d'issue, d'identité, de
  métrique.
- **`compté`** : aucun canal (K2) ; **Q1 (Bruno) : dérivé, non lu** — localement, par `verify_attendu.py`, de `(issue, raison)`
  par la table du § 10.1 recopiée du texte (`CONTRAINTES_POST_B4.md`), épinglée à `c3_verdict.COUNTED` par un contrôle
  d'égalité ; ligne conditionnelle (`A_NO_ADMISSIBLE_CANDIDATE`) → `indéterminé` = écart. Dit « dérivé, non lu » ;
  l'inscription `compte` au registre est **déclarée, jamais vérifiée** (comme l'absence d'évaluation différée).
- Le rapport cite `verdict=` et `raison=` tels que la chaîne les écrit ; la chaîne complète (identité retenue,
  continuité…) reste archivée, jamais lue — limite déclarée au regard du § L.2 (« cite la chaîne »), voulue par le brief.

## 3. D-archive

- **Emplacement** : `~/archive/c3_campagne_grid_<AAAAMMJJ>/out` (700). **Déplacement** (`mv`, même système de fichiers,
  vérifié par code) de `~/runs/c3_campagne_grid/campagne/out` : aucune copie, aucun tgz, **aucun sha calculé**, aucun
  contenu lu. Puis `chmod -R a-w` (rend l'archive non supprimable par erreur).
- **Vérification par codes seulement** : liste des noms avant = après (comparée au serveur, jamais affichée) ; source
  absente ; aucun fichier inscriptible ; 0 entrée `repo/` ou `.env`. Ni taille, ni compte de fichiers, ni sha.
- **Clone `repo/`** (code au S1, copie du `.env` du service, copie de `CAMPAIGN_UNLOCK`) : pas un artefact du chemin ;
  **Q3 (Bruno) : supprimé après l'archive vérifiée** — la seule suppression du chantier, jamais `out/`. **Garde (A3)** :
  `rm -rf /home/bruno/runs/c3_campagne_grid` en **littéral absolu**, jamais une variable, et seulement si (i) tous les
  codes de l'archive valent 0, (ii) l'archive porte `out/status.txt` et `out/pilot_exit.txt`, (iii) **aucun composant de
  chemin nommé exactement `out` ne subsiste sous `/home/bruno/runs/c3_campagne_grid`** (`find … \( -name out -o -path
  '*/out/*' \)` vide). Sinon refus, rien supprimé, STOP. *Motif précisé* : le glob littéral `*/out*` correspond au
  fichier suivi `results/c3_v2_2/outillage_v2_2.md` du clone et refuserait toujours ; la forme retenue garde l'intention
  (aucun reste de `out/`), vérifiée sur l'arbre suivi (aucun composant exactement `out`).
- **Trace au rapport** : chemin, heure du déplacement, codes. Aucun `.tgz.sha256` (la règle des conformités ne se recopie pas).

## 4. D-postflight

- **Agent** (lecture seule) : `~/runs/c3_campagne_grid` absent ; aucune session tmux du chantier ; archive présente, non
  inscriptible, sans `repo/` ni `.env` (codes) ; collector actif, `NRestarts` = preflight ; HEAD du service = preflight,
  0 ligne sale ; `alembic` `c3bd1e7a0001 (head)` ; `CAMPAIGN_UNLOCK` du service présent, non touché. **Jamais `~/c3/`.**
- **Cérémonie de Bruno**, listée au rapport, non exécutée : clés de racine (runbook § 1 — sa dernière clause
  `variants == {}` ne tient plus après la première inscription), sauvegarde § 2, merge, clôture § K.2 effective au journal,
  **suppression de `CAMPAIGN_UNLOCK` après le merge** (re-verrouillage ; une campagne future = un nouveau geste — acté).
- **Avant le GO (K3, acté)** : Bruno fait la vérification § 1 du runbook (sortie `True`) au moment où il crée
  `CAMPAIGN_UNLOCK` — seule parade côté registre réel (absent ou corrompu), que l'agent ne peut pas voir. Une faute de
  frappe dans le chemin du pilote, elle, ne se voit qu'à la relecture du STOP 1 (§ 6, A2).

## 5. S1 — le gel entre au dépôt (puis STOP 1)

- `results/c3_campagne_grid/manifest.json` = le brouillon **à l'octet** (`cmp`), `tests/manifest_check.out` : `sha256sum`
  = `d422076b…5041`, protocole déclaré = courant, date différée à 365,000000 j de `window.end`, 96 candidats distincts
  (2 paires × 4 × 4 × 3), `contaminated`, `parent.is_root`, graine 20261001 ; `c3_anchor` seul, pur, registre et sortie
  hors dépôt (temporaires supprimés) : code 0, `T = 2024-11-22T04:48:00+00:00`, préfixe 1 362,2 j. **Contrôle du
  manifeste, pas le run : ce registre temporaire n'est pas le « registre jeté » qu'exclut D-pilote (acté, A4).** Sortie
  committée **filtrée par liste blanche** : lignes `ancrage T = …` (T, préfixe), `variante … — nouvelle au registre`,
  `provenance de l'univers …` ; jamais la ligne `written … sha256 …` (64 hex d'un temporaire, hors règle).
- `attendu.md` (normatif, modèle R-4) : items 1-11 — gardes (dont `CAMPAIGN_UNLOCK` **présent**) ; base ; service ;
  préfixe `0 event=-`, workers 3 ; chaîne 1-4 en 0 et `registry_new_entry_pre=true` ; `0 event=evaluated` ; chaîne en 0,
  cinq codes d'étape en 0 (**une ligne nomme la correction du « six » du brief, renvoi `c3_verdict.CHAIN_FILES`, A1**),
  `chain.verified` vrai, violations vides, `registry_new_entry_chain=false`, `issue_inscrite=true` ;
  **triplet `inconclusif`, `P_PROVENANCE`, compté faux** (tout autre, « meilleur » compris, = écart = STOP) et
  `selection_descriptive=true` ; interpréteur du clone ; aucun `NOT_RUN` ; `pilot_exit` 0. Déclarés, jamais vérifiés :
  aucune évaluation différée inscrite, contenu du registre, bornes des lectures.
- `docs/RESEARCH_LOG.md`, **entrée 23**, titre exact cité par le manifeste, insérée avant « Essais à venir », colonnes du
  journal : périmètre (famille `grid-atr-v4`, 96 candidats, fenêtre 2021-03-01 → 2026-06-29, `T`), données (binance USDT
  end-stampées, **les 8 estampilles 1 w dérivées listées**, renvoi entrée 13), code (S1, protocole `d030ab23…`, manifeste
  `d422076b…`), coûts (GATE B, sonde des 14-15/09), attendu déclaré, **décision consécutive** (clôture par la clause de
  clôture § K.2 de `docs/rejeu_grid_prespec.md`, décision de Bruno ; toute reprise exige un mécanisme nouveau ; travail de
  mécanisme pour les familles suivantes, composées avant toute évaluation). L'issue s'inscrira dans une section suivante.
- Scripts repris de `results/c3_racine_registre/tests/` par **substitutions comptées** (`reprise.out`) : `interdits.sh`
  (+ adverse), `preflight.sh`, `launch.sh` (copie de `CAMPAIGN_UNLOCK` du service au clone juste après le `.env`, `cmp`
  vérifié — Q2 ; `nice -n 10`), `wait.sh`, `fetch.sh`,
  `archive.sh` (réécrit, D-archive), `postflight.sh`, `verify.sh`, `events.sh`, `tunnel.sh`, `ci_status.sh`, `lint.sh`.
  Re-prouvés avant de servir : `pilot_dryrun.sh` (monde simulé ; 5 lignes substituées : SERVICE, PY, RUN, les deux
  `--registry` ; la ligne `UNLOCK=` pointe un **marqueur de simulation** — aucun fichier nommé `CAMPAIGN_UNLOCK` créé, même
  temporairement) avec 8 simulations : conforme → 0 ; triplet « meilleur » → 1 ; forme de refus à l'évaluation → 1 et
  `chain=NOT_RUN`, registre simulé sans verdict ; échec du préfixe → 1, registre simulé jamais créé ; violation de chaîne
  → 1 ; `new_entry` faux → 1 ; SHA faux → 2 ; marqueur absent → 2. `verify_adverse.sh` : témoin 0, chaque cas dévié à un
  item. `interdits.sh` : diff vide contre `235461e` sur `src/ scripts/ tests/ config/ pyproject.toml poetry.lock .github
  skills/ agent/ CLAUDE.md` et protocole + amendements + CONTRAINTES ; liste blanche `results/c3_campagne_grid/**` ∪
  `docs/RESEARCH_LOG.md` (ajouts seuls) ; aucun artefact du chemin, aucun `.tgz`/`.tgz.sha256` ; règle 64 hex (table
  d'Adoption ∪ fichiers du chantier ∪ `d422076b…`) — **toute sortie committée la passe ; une ligne hors règle est filtrée
  par liste blanche, la règle n'est jamais élargie** (A4) ; registre nommé seulement sur les deux lignes `--registry` du
  pilote, chacune égale au chemin construit (contrôle mécanique, qui ne remplace pas la relecture A2) ; dette 23 non
  nommée ; `CAMPAIGN_UNLOCK` absent en local.
- Le brief et le brouillon restent non suivis (§ 3 : le chantier n'écrit que `results/c3_campagne_grid/**` et l'entrée 23).

## 6. Commits et gates (branche assertée avant chaque commit, `interdits.sh` avant chacun)

| Pas | Contenu | Poussé |
|---|---|---|
| G0 | branche ; `tunnel.sh state` (fermé attendu) | — |
| C0 `docs(results)` | `plans/plan.md` (ce plan, GO), `interdits.sh` + adverse et sorties | non |
| **S1** `docs(research)` — **SHA du run** | manifeste, preuves, attendu, pilote, vérificateur, scripts et sorties d'avant lancement, entrée 23 | oui, CI lue |
| **STOP 1** | relecture de Bruno au SHA S1 complet (attendu, entrée 23, pilote) **dont les deux littéraux `--registry` comparés au caractère près à `/home/bruno/c3/registry/variants.json`** (A2) ; **Bruno crée `CAMPAIGN_UNLOCK`** et fait le § 1 du runbook ; GO nommant S1 | |
| Run | preflight (rc≠0 → STOP) → launch → wait → fetch (4 fichiers ; **règle 64 hex balayée sur eux avant S2**, A4) → verify → archive → postflight | |
| S2 `docs(results)` | preuves du run, `report.md`, issue de l'entrée 23 + jalon § 10.2 daté, ajout aux « Essais à venir » | oui, CI lue |
| S3 | `ci_status_S2.out` | oui |
| **STOP 2** | merge par Bruno | |

Règle d'arrêt (brief § 4) : tout code ou triplet hors attendu, `chain.verified` faux, une violation, un refus, une garde
en échec, tout besoin de toucher manifeste, code ou texte → STOP, constat versionné, répertoire serveur en place (ni
archive ni suppression), rien relancé, rien lu en diagnostic sans l'accord de Bruno.

## 7. Vérification

Avant S1 : `manifest_check`, `events`, `reprise`, `pilot_dryrun` (8/8), `verify_adverse`, `lint`, `interdits` (+ adverse)
à rc=0 ; CI verte sur S1. Après le run : `verify_attendu.out` 11/11, postflight rc=0, `interdits` au tip.

## 8. Décisions de Bruno au plan (01/10)

- **Q1** — `compté` : dérivé de `(issue, raison)` par la table du § 10.1, non lu ; inscription au registre déclarée.
- **Q2** — `CAMPAIGN_UNLOCK` : créé par Bruno dans l'arbre du service (non suivi), constaté au preflight, transporté
  dans le clone par `launch.sh` (`cmp`), constaté par la garde du pilote. Jamais créé par l'agent.
- **Q3** — clone `repo/` : supprimé après l'archive vérifiée ; `out/` déplacé, en lecture seule, jamais supprimé.

**Amendements de la relecture (01/10), intégrés** : A1 cinq codes d'étape + code de la chaîne, correction nommée dans
`attendu.md` (§ 2, § 5) ; A2 les deux littéraux `--registry` relus au caractère près au STOP 1 (§ 6) ; A3 garde
paranoïaque avant la seule suppression, motif `out` précisé (§ 3) ; A4 sorties committées filtrées par liste blanche
pour la règle 64 hex, balayage des quatre fichiers du fetch avant S2, contrôle local de `c3_anchor` acté comme contrôle
du manifeste (§ 5, § 6) ; A5 sémantique d'un refus de preflight (§ 1).

**Validé à la relecture** : lecture des booléens mécaniques dans `verdict.json` / `anchor.json` (`chain_verified`,
violations, `new_entry`) conforme aux « contrôles comme aux conformités » ; désambiguïsation K6 ; brief non commité
(Bruno pourra le commiter au merge).
