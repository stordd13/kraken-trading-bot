# Brief agent — Racine du registre (R-4) : passthrough des clés de racine, test UTC, runbook, conformité rejouée

**Nouvel agent. Plan mode, plan court : décisions numérotées, GO de Bruno avant la première écriture de chaque
lot. Gates : plan → GO → (lot 2) STOP avant tout lancement serveur, GO nommant le SHA → STOP au rapport. Le
merge est fait par Bruno, jamais par l'agent.**

## 0. À lire avant tout geste

1. `CLAUDE.md` ; `skills/backtest.md` ; `skills/deployment.md` ;
2. le fichier joint `RUNBOOK_REGISTRE_CAMPAGNE.md` — les décisions R-1 à R-7 et D13 qui motivent ce chantier ;
   il est **commité tel que reçu** au lot 1, à l'emplacement proposé au plan ;
3. `docs/protocole_c3.md` v2.3 (sha256 `d030ab23…79e6`, **gelé, intouché**) : § A.6 (le registre, les
   enregistrements, la non-divulgation) — constat attendu : il spécifie les enregistrements et l'inscription,
   **pas le schéma de racine du fichier** ;
4. `scripts/audit/c3_anchor.py` : `load_registry` (la racine rendue `{"variants"}` seul — le défaut à corriger),
   `register`, la canonicalisation R-22 ; `scripts/audit/c3_verdict.py` : `registry_inscription` (le plan du
   lot 1 outillage v2.3 affirme qu'il préserve les clés de racine — **à prouver, pas à croire**) ;
5. `results/c3_outillage_v2_3/report.md` § 5 (D13 : le sel, sa motivation), § 9 ; `conformite/` et ses pilotes
   (modèles du lot 2, troisième rejeu) ; `docs/RESEARCH_LOG.md` entrée 21 (modèle de l'entrée 22).

## 1. Contexte

Le registre de campagne unique et persistant sera créé **par Bruno, à la main, après le merge de ce chantier**
(runbook § 1). Sa racine portera un sel aléatoire (`{"salt": "<64 hex>", "variants": {}}`) qui rend tout digest
du registre non inversible sans le lire — fermeture structurelle du canal D13. Or `load_registry` jette
aujourd'hui toute clé de racine inconnue : **la première réécriture par l'ancrage perdrait le sel,
silencieusement.** Ce chantier corrige cela, ajoute le test manquant de la normalisation UTC du descripteur
(limite déclarée du rapport v2.3), commite le runbook, puis rejoue la conformité serveur : le chantier touche
`c3_anchor`, donc la conformité du 30/09 ne couvre plus le tip — on prouve, on n'argumente pas. Ce chantier
est, sauf découverte, **le dernier changement de code de chaîne avant la campagne** : sa conformité servira de
preuve d'instrument au manifeste.

**Aucun sel réel n'est créé ni manipulé dans ce chantier.** Les tests utilisent des valeurs de racine
synthétiques, nommées comme telles. Aucun registre persistant n'est créé, ni en local ni au serveur.

## 2. Objectif

À la fin : l'ancrage réécrit un registre **sans perdre aucune clé de racine** ; un adverse le prouve pour les
deux écrivains (ancrage et verdict) ; la normalisation UTC des instants de `D` est défendue par un test ; le
runbook est dans l'arbre ; la conformité v2.3 est re-prouvée au SHA du chantier ; la porte § L.5 vaut par
invariance déclarée et prouvée. Branche `feat/c3-racine-registre` depuis
`dev` @ `313eb00c2019b98cf20fb81ac8327f7b9d1e920a`.

## 3. Lot 1 — code, tests, runbook

### 3.1 Inventaire-filet (premier livrable du plan, avant toute écriture)

Recenser tout test, fixture ou vérificateur qui épingle la **racine exacte** du registre (`{"variants"}` seul,
égalité de clés de racine, schéma fermé) — grep sur les tests, `verify_attendu.py`, les scripts des chantiers
clos ne comptant pas (ils ne retournent pas). **Si un épinglage normatif existe : STOP** — la levée passe par
trois lignes de v2.4 avant l'outillage (décision Bruno). Constat attendu d'après nos lectures : aucun, la
canonicalisation R-22 portant sur `variants` seul — mais c'est l'inventaire qui fait foi.

### 3.2 Périmètre

- **Passthrough** : `load_registry` (et tout chemin de réécriture de l'ancrage) préserve les clés de racine
  inconnues, à l'octet près de leur valeur ; `{"variants"}` reste obligatoire et validé comme aujourd'hui.
  L'emplacement exact (lecture, écriture, les deux) est une décision du plan.
- **Côté verdict** : prouver que `registry_inscription` préserve déjà les clés de racine — par test, pas par
  lecture seule. S'il ne les préserve pas : même correction, déclarée.
- **Adverse** : un registre synthétique portant une clé de racine en plus (valeur synthétique explicite, p. ex.
  `"salt": "racine-de-test"`) traverse un enregistrement par l'ancrage **et** une inscription par le verdict ;
  la clé et sa valeur survivent à l'octet près. Né rouge à `313eb00` sur le chemin ancrage.
- **Idempotence et bit-égalité conservées** : l'étape 1 reste idempotente sur un registre déjà porteur de la
  variante ; trois exécutions d'un même run restent identiques au bit (la conformité du lot 2 le re-prouve).
- **Normalisation UTC de `D`** (limite du rapport v2.3 § 5) : un manifeste dont les instants sont écrits en
  `…Z` produit la **même empreinte de descripteur** qu'en `+00:00`, côté verdict et côté run différé.
- **Mutants**, chacun tué par un test nommé, tous restaurés : passthrough retiré (retour à `{"variants"}`
  seul) ; clé de racine réécrite ou perdue à l'inscription du verdict ; normalisation UTC retirée (`isoformat`
  contourné).
- **Runbook** : commité tel que reçu ; emplacement proposé au plan (recommandation : `skills/registry.md`,
  cohérent avec `deployment.md` et `database.md`). Tout besoin d'adaptation (chemin, renvoi) : déclaré, jamais
  silencieux.
- **Non-divulgation reconduite** : aucun digest du registre imprimé, aucune clé de racine imprimée hors des
  mondes de test ; `non_divulgation.sh` du lot 1 v2.3 adapté aux lignes ajoutées.

### 3.3 Règles et sortie du lot

Règles des chantiers précédents, inchangées : protocole et amendements **gelés** (sha v2.3 recalculé à chaque
commit dans `interdits.sh`) ; `src/`, `scripts/backtest.py`, runners, `rejeu_common.py`, `c3b_*.py` : diff vide
contre `313eb00` ; formatter scopé aux fichiers nommés ; SHA complet partout ; corps des tests existants
intacts hors liste déclarée (diff AST) ; comptes par diff d'identifiants ; tunnel ouvert pour les 13 tests base
seulement, refermé et vérifié ; CI verte tentative 1 (relance pour `test_rejeu_effect` seul) ; `mypy src/` = 65 ;
journaux en fichiers ; vérifications par `results/c3_racine_registre/tests/*.sh` lancés en `bash`, sorties
committées ; messages par `-F`.

Sortie : suite sans tunnel **3 321 + les tests neufs du plan** (recompte par identifiants, 0 retiré), 1 xfail
(le caduc), 0 échec, 0 XPASS ; mutants tous rouges puis verts ; `lot1/README.md`.

## 4. Lot 2 — conformité rejouée au SHA du chantier ; porte par invariance

Modèle : le lot 2 du chantier v2.3 (troisième rejeu — c'est une routine outillée). **Aucun code.**

- **Manifeste** : celui de la conformité v2.3 (`24bde67d…565a`) avec **seuls** `research_log_entry`
  (entrée 22), `run_scope` et `variant_id` réécrits — le protocole n'a pas changé, la date différée non plus.
  `manifest_check.sh` prouve ce delta exact.
- **Attendu** : items et codes du 30/09 repris ; un § « Ce que ce chantier change » : le passthrough (sans
  effet sur ce run : les registres de conformité, neufs, ne portent aucune clé en plus — dit et assumé), le
  test UTC, rien d'autre.
- Entrée 22 au journal avant lancement ; pilotes repris par substitutions comptées (`reprise_*.out`) ;
  dry-run et vérificateurs re-prouvés (cas déviés) ; **STOP avant lancement, GO nommant le SHA** ; trois
  exécutions 4/1/4, même `--now`, même chemin absolu + `mv`, registre **neuf et jeté** par exécution ;
  23 artefacts identiques au bit ; issue non lue ; archives vérifiées par codes puis supprimées ; postflight.
- **Porte § L.5 : non rejouée.** Invariance déclarée et prouvée : diff vide sur `src/` et les dépendances des
  24 `_full` contre `313eb00`, chaîne d'invariance jusqu'à la dernière porte jouée (`c62acb4`, 24/24) écrite au
  rapport. Si l'inventaire du § 3.1 ou le plan fait toucher quoi que ce soit que la porte couvre : elle se
  rejoue, décision au plan.
- `CAMPAIGN_UNLOCK` absent et jamais créé ; tunnel jamais ouvert au lot 2 ; aucune donnée de la fenêtre de
  campagne lue (portée dite comme au rapport v2.3).

## 5. Critère de fin du chantier

1. Inventaire-filet versionné, vide ou tranché.
2. Adverse de racine vert pour les deux écrivains ; mutants tués ; test UTC vert ; suite complète 0 échec,
   0 XPASS, 1 xfail (le caduc), 0 retiré ; CI verte tentative 1 à chaque SHA poussé.
3. Runbook dans l'arbre, tel que reçu.
4. Conformité : 10 items tenus, trois exécutions au bit, archives vérifiées puis supprimées, postflight `rc=0`.
5. Invariance de la porte prouvée et écrite.
6. Rapport final `results/c3_racine_registre/report.md` (lignes périmées pour le `docs(merge)` listées) —
   STOP 2, relecture Bruno, merge par Bruno.

## 6. Interdits

`src/`, `scripts/backtest.py`, runners, `rejeu_common.py`, `scripts/audit/c3b_*.py`, `docs/protocole_c3.md`,
`docs/amendements_c3_v2.{1,2,3}.md`, `docs/CONTRAINTES_POST_B4.md`, `results/` clos (`c3_v2_2`,
`c3b_producteur`, `c3_outillage_v2_2`, `c3_v2_3_gel`, `c3_outillage_v2_3`) : intouchés. Aucun registre
persistant créé, aucun sel réel généré, `~/c3/` jamais touché ni créé, `CAMPAIGN_UNLOCK` jamais créé,
`~/docker/` jamais nommé. Base en lecture seule ; Decimal partout ; structlog.

## 7. Règle d'arrêt

Un épinglage normatif de la racine (§ 3.1), un test vert à `313eb00` qui rougit hors inventaire, un XPASS,
tout besoin de toucher au texte gelé, tout doute sur la portée de la porte § L.5 : **STOP et question à
Bruno.** Ce chantier ferme un canal de fuite ; il ne décide rien du registre réel, qui appartient à Bruno.
