# Brief agent — Seconde campagne C3 comptée : famille grid-atr-v4, relance après correction d'instrument

**Nouvel agent. Plan mode, plan court. Gates : plan → GO → S1 → STOP 1 (relecture au SHA) →
`CAMPAIGN_UNLOCK` créé par Bruno, jamais par l'agent → GO de lancement nommant S1 → run → STOP 2 au rapport.
Le merge est fait par Bruno. C'est le run compté, et c'est la relance unique du § 10.1 : un seul lancement,
aucun retry, aucun écart arbitré.**

## 0. À lire avant tout geste

1. `CLAUDE.md` ; `skills/backtest.md` ; `skills/deployment.md` ; **`skills/registry.md` en entier** — les
   règles de non-lecture du registre sont absolues ;
2. le fichier joint `manifest_campagne_v2_draft.json` — **le manifeste v2, gelé le 2026-10-01, sha256
   `b757c45bbed2b0913ac4ec781c9c6928fa935b7c71639e66f26fb5d2468f4f11`, 38 507 octets** : il se commite à
   l'octet, toute divergence est un STOP, toute retouche exigerait un nouveau gel par Bruno ;
3. **le chantier v1 entier, `results/c3_campagne_grid/`** (mergé) : c'est le modèle direct — `plans/plan.md`,
   `attendu.md`, le pilote, les scripts de `tests/`, `constat.md`, `diagnostic_lecture.md` (la cause de
   l'arrêt), `manifest.json` (le manifeste v1, parent de celui-ci) ;
4. `docs/protocole_c3.md` v2.3 (sha `d030ab23…79e6`, gelé) : § A.5-A.6, § H.1, § I.1, § D.2 ;
   `docs/CONTRAINTES_POST_B4.md` § 10 (dont § 10.1 : « une seule relance après correction d'instrument ») ;
5. `docs/RESEARCH_LOG.md` entrées 13, 14, 23 (la 23 porte le constat du run v1 arrêté).

## 1. Contexte

Le run compté v1 (01/10, SHA S1 `cd4b177`) s'est arrêté à `c3_entry` en code 1 : 64/96 violations
`warmup_series` — le manifeste v1 déclarait la liste pleine `{1d,1w,4h}` pour les 96 candidats alors que la
classmethod pure `GrokGridATRAdaptiveV4.decision_timeframes(params)` dérive `{1d,4h}` pour
`bear_protection_mode ∈ {none, 1d_only}`. L'export du producteur est juste ; la déclaration était fausse.
**Correction : le manifeste v2** — surcharges `decision_timeframes` par candidat (sorties de la classmethod),
`parent = {is_root: false, variant_key: 3159a907…fcb5}` (la variante v1, inscrite au registre **sans
verdict** — orpheline documentée). Aucun changement de code.

Conséquences pour ce chantier : le registre contient déjà la variante v1 → l'ancrage du v2 est une **nouvelle
inscription** (`new_entry` vrai au pré, faux à la chaîne, comme au chantier v1 — mais pour une variante
neuve, pas une idempotence du v1). **§ 10.1, décision de Bruno à écrire à l'entrée 24 : ce run est la relance
unique après correction d'instrument ; après lui, plus aucune relance pour la famille grid, quel que soit le
résultat.** L'attendu de fond est inchangé : provenance `contaminated`, **issue `inconclusif (P_PROVENANCE)`,
non compté**, sélection `SÉLECTION_DESCRIPTIVE`, décision consécutive : clôture de la famille par la clause
§ K.2 de `docs/rejeu_grid_prespec.md`. Ce chantier exécute la cérémonie ; il ne décide rien du fond.

## 2. Chantier

Un lot. Branche `feat/c3-campagne-grid-v2` depuis `dev` @ `cce566d82f40166d9ff95c972e346b26831ed304` (le tip post-merge du
chantier v1 — SHA complet, vérifié avant G0).

### 2.1 Décisions attendues au plan (propositions argumentées, GO avant écriture)

- **D-pilote** : reprise de `results/c3_campagne_grid/server/run_campagne.sh` par substitutions comptées.
  Inchangés : les **deux lignes `--registry /home/bruno/c3/registry/variants.json`** en littéral (les deux
  seules), `--campaign GRID_ATR_V4_2026` (étiquette d'instrument, dette 21 — l'ancre d'extraction
  `^C3_GRID_ATR_V4_2026` reste valable), `--workers 3`, `nice -n 10`, arrêt au premier écart, contrôles
  « après » inconditionnels, dimensionnement (~45 min central, plafond 4 h, sonde 120 s). Changent : le SHA
  S1 attendu, le sha du manifeste (`b757c45b…4f11`), `--now 2026-10-01T00:00:00+00:00` (date du gel v2,
  même règle que la graine `20261001`).
- **D-archive-préalable (nouveau)** : le répertoire du run v1 arrêté, `~/runs/c3_campagne_grid`, est encore
  en place (règle d'arrêt). Avant tout lancement : archivage par `archive.sh` du chantier v1 et **ses gardes
  A3 inchangées** (mv de `campagne/out` vers `~/archive/c3_campagne_grid_<date>/out`, lecture seule,
  vérification par codes, puis — seule suppression — `rm` du répertoire en littéral absolu, refus si un
  composant `out` subsiste). Le clone v1 et sa copie du `.env` disparaissent là. `launch.sh` refuse un
  répertoire existant : ce pas conditionne le lancement. Il s'exécute après le GO de lancement, en premier
  pas du run.
- **D-lecture du verdict** : inchangée mot pour mot (chantier v1, § 2 du plan) : canal sanctionné = chaîne
  § L.2 sur stdout, heredoc ancré, liste close ; booléens mécaniques de `verdict.json`/`anchor.json` comme
  aux conformités ; `compté` **dérivé, non lu** du couple constaté, table § 10.1 épinglée à
  `c3_verdict.COUNTED` ; jamais un champ d'issue, d'identité, de métrique hors canal.
- **D-archive** et **D-postflight** : inchangés (chantier v1, § 3-4 du plan). L'agent ne touche jamais
  `~/c3/`.

### 2.2 S1 — le gel entre au dépôt (puis STOP 1)

- `results/c3_campagne_grid_v2/manifest.json` : le fichier joint, **à l'octet** (`cmp`), `sha256sum` committé
  = `b757c45b…4f11`.
- `manifest_check` v2 : mêmes contrôles de forme que v1 (96 candidats distincts, différée à 365,000000 j,
  `contaminated`, graine) **plus** : chaque surcharge `decision_timeframes` égale la sortie de la classmethod
  sur les params du candidat (96/96) ; `parent.variant_key` égal à `sig(canon(manifeste v1))` recalculé
  depuis `results/c3_campagne_grid/manifest.json` commité. **Ancrage local sur registre temporaire
  pré-contenant la variante v1** (record reconstruit depuis le manifeste v1 commité, sel factice — jamais le
  vrai registre) : trois cas — registre vide → code 2 (contrôle négatif : le contrôle de parent mord) ;
  registre avec v1 → code 0, « nouvelle au registre », T = `2024-11-22T04:48Z`, préfixe 1 362,2 j
  (inchangés) ; re-run → « déjà au registre, idempotent ». Sortie committée filtrée par liste blanche —
  jamais une ligne `written … sha256 …`.
- `attendu.md` (modèle v1, 11 items) : gardes (manifeste `b757c45b…`, `CAMPAIGN_UNLOCK` présent) ; base ;
  service ; préfixe 0 ; chaîne 1-4 en 0 et `registry_new_entry_pre=true` (**variante neuve**) ; `evaluated` ;
  chaîne en 0, **cinq** codes d'étape en 0 (correction A1 du chantier v1, renvoi `c3_verdict.CHAIN_FILES`),
  `chain.verified` vrai, violations vides, `registry_new_entry_chain=false`, `issue_inscrite=true` ;
  **triplet `inconclusif`, `P_PROVENANCE`, `compté` faux** (tout autre, « meilleur » compris, = écart =
  STOP) et `selection_descriptive=true` ; interpréteur du clone ; aucun `NOT_RUN` ; `pilot_exit` 0.
  Déclarés, jamais vérifiés : aucune évaluation différée inscrite, contenu du registre, bornes des lectures.
- `docs/RESEARCH_LOG.md`, **entrée 24, avant tout lancement**, titre exact cité par le manifeste, colonnes
  du journal : périmètre (96 candidats **avec surcharges par candidat**, fenêtre, T), données (les 8
  estampilles listées, renvoi 13), code (S1, protocole `d030ab23…`, manifeste `b757c45b…`, parent
  `3159a907…` renvoi entrée 23), coûts (inchangés), attendu déclaré, **§ 10.1 : relance unique après
  correction d'instrument, décision de Bruno — aucune relance ensuite**, décision consécutive : clôture
  § K.2, travail de mécanisme pour les familles suivantes. L'issue s'inscrira dans une section suivante.
- Scripts repris de `results/c3_campagne_grid/tests/` par substitutions comptées (`reprise.out`) ; dry-run du
  pilote (8 simulations du chantier v1), mutants, `verify_adverse`, `table_10_1`, `archive_dryrun`
  re-prouvés avant de servir. `interdits.sh` : diff vide contre le SHA de base sur tout — **y compris
  `results/c3_campagne_grid/**` (chantier v1, historique clos)** ; liste blanche
  `results/c3_campagne_grid_v2/**` ∪ `docs/RESEARCH_LOG.md` (ajouts seuls) ; règle 64 hex : table d'Adoption
  ∪ fichiers du chantier ∪ **{`b757c45b…4f11`, `3159a907…fcb5`}** (le sha du gel v2 et la clé du parent,
  présente dans le manifeste commité) ; registre nommé seulement sur les deux lignes `--registry` du pilote,
  chacune égale au chemin construit ; `CAMPAIGN_UNLOCK` absent en local.

**STOP 1** : Bruno relit au SHA S1 complet — attendu, entrée 24, pilote (**les deux littéraux `--registry`
au caractère près**), `manifest_check`, le pas d'archive-préalable. Puis **Bruno crée `CAMPAIGN_UNLOCK`**
dans l'arbre du service et rejoue le § 1 du runbook (sans la clause `variants == {}`, sortie `True`). Puis
GO de lancement nommant S1.

### 2.3 Le run, puis STOP 2

Archive-préalable du run v1 (gardes A3 ; refus → STOP) → preflight (lecture seule ; mémoire,
`CAMPAIGN_UNLOCK` présent ; `rc≠0` → STOP, re-tenter le preflight après accord n'est pas une relance) →
lancement → attente → remontée **par la liste close seulement** → balayage 64 hex des fichiers rapatriés →
vérification de l'attendu (11/11) → archive conservée → postflight → rapport
`results/c3_campagne_grid_v2/report.md` (ce qui a été fait, l'issue par le canal sanctionné, les écarts — il
ne doit y en avoir aucun —, ce qui attend : sauvegarde du registre par Bruno, merge, clôture § K.2 effective
au journal, suppression de `CAMPAIGN_UNLOCK` après merge) → issue inscrite à l'entrée 24 → **STOP 2**.
Jalon § 10.2 : premier verdict réel de la famille grid (échéance 2027-01-31), à consigner avec sa date.

## 3. Interdits

Le registre : jamais lu, jamais copié, jamais nommé dans un script autrement que les deux lignes `--registry`
du pilote. `CAMPAIGN_UNLOCK` : constaté, jamais créé. Aucun sha d'artefact du chemin sélection versionné ni
imprimé ; aucune métrique, aucun classement, aucune issue lue hors du canal sanctionné. `src/`, `scripts/`,
`tests/`, `config/`, le protocole et les amendements, **et `results/c3_campagne_grid/**` (chantier v1)** :
diff vide contre le SHA de base — ce chantier n'écrit que `results/c3_campagne_grid_v2/**` et l'entrée 24.
Tunnel : selon besoin du pilote seulement. Base en lecture seule.

## 4. Règle d'arrêt

Tout code hors attendu, tout triplet différent de l'attendu déclaré, `chain.verified` faux, une violation, un
refus, une garde en échec, tout besoin de toucher au manifeste, au code ou au texte : **STOP, constat
versionné, répertoire serveur en place, rien de relancé, rien de lu en diagnostic sans l'accord de Bruno.**
Un run compté ne se « réessaie » pas — et celui-ci est la relance unique du § 10.1 : un nouvel arrêt ferme
la voie pour la famille, la suite appartient à Bruno.
