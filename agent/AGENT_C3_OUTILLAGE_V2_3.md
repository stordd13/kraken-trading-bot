# Brief agent — Outillage C3 v2.3 (lever X1-X8, conformité serveur sous v2.3, porte § L.5)

**Nouvel agent. Plan mode : chaque lot commence par un plan écrit (décisions numérotées), soumis à Bruno, GO
avant la première écriture du lot. Gates : plan → GO → (lot 2) STOP avant tout lancement serveur → STOP au
rapport final. Le merge est fait par Bruno, jamais par l'agent.**

## 0. À lire avant tout geste

1. `CLAUDE.md`, `skills/backtest.md` (§ Validation C3, § Producteur C3b), `skills/database.md` (tunnel),
   `skills/deployment.md` (serveur) ;
2. `docs/protocole_c3.md` **v2.3**, sha256
   `d030ab239de317f6cba89877d682338fa2001d2a63d231f1a86c519fe87a79e6` — § A.6 (clé, descripteur `D`,
   dérivation à l'ancrage, non-divulgation), § A.5, § I.1 (ligne 10 ter), § H.1 ;
3. `docs/amendements_c3_v2.3.md` — section Adoption entière : décisions G-1 à G-11, réserves d'application
   (table X1-X8 avec leurs fichiers), « ≥ 365 jours », note de portée ;
4. les huit tests `xfail(strict=True)` X1-X8 dans `tests/test_scripts/test_c3_{anchor,common,verdict}.py`,
   et le témoin R-17 converti (G-10). **Leur attendu est normatif, leur interface d'appel est indicative**
   (`fx.deferred_descriptor`, `cv.deferred_descriptor`, noms de fonctions : à toi de proposer l'emplacement
   final au plan) ;
5. `results/c3_v2_3_gel/report.md` (le gel, ses écarts déclarés) ;
6. modèles du chantier précédent : `agent/AGENT_C3_OUTILLAGE_V2_2.md`, `results/c3_outillage_v2_2/report.md`,
   `lot1_chaine/README.md`, `lot2_producteur/README.md`, `conformite/` (attendu, manifeste, pilotes,
   `verify_attendu.py`), `gate_L5/`.

## 1. Contexte

Le protocole v2.3 est gelé et mergé (`dev` @ `b50f2d15150f90a6d6ceb7ab2d41f8b1f495ecf9`). Ses règles nouvelles
(AM-01, évaluation différée) sont portées par huit tests `xfail` strict posés au gel par un autre agent, depuis
le texte seul. Ce chantier les lève, puis rétablit la conformité serveur : **celle du 30/09, prouvée sous v2.2,
n'a plus de valeur probante** — l'ancrage v2.3 refuse tout manifeste v2.2 (précédent : la conformité v2.1 du
28/09, invalidée par v2.2). AM-02 (ligne 10 ter) est du texte-suit-le-code : rien à outiller.

## 2. Objectif

Deux lots, une session et un GO par lot, poussée à chaque lot, branche `feat/c3-outillage-v2.3` depuis
`dev` @ `b50f2d15150f90a6d6ceb7ab2d41f8b1f495ecf9`. À la fin : chaîne et producteur conformes sous v2.3 au
serveur, porte § L.5 tenue, 0 xfail hors le caduc déclaré, prêt pour le manifeste de la première campagne.

## 3. Lot 1 — code et tests : lever X1-X8

### 3.1 Périmètre

| Réserve | Ce qui est attendu (le test xfail fait foi) | Site probable |
|---|---|---|
| X1, X2 | `deferred_evaluation.date` lue et validée à l'étape 1 : présente, date lisible, **≥ 365 jours** après `window.end` (365 exactement : accepté) ; sinon `R0_INVALID_RUN`, code 2 | `c3_anchor`, `c3_common.load_manifest` (X8) |
| X3, X4 | quand l'issue ouvre la voie prospective du § 10.1 (`F_CANNOT_SEPARATE` ∧ `Q1∧Q2∧Q3` ∧ `Δ̂ > 0` aux six combinaisons), le verdict inscrit `deferred_evaluation {date, variant_key}` — `date` copiée du manifeste, `variant_key = sig(canon(D))` — **en mode `chain` seul, jamais hors code 0** ; sinon, aucune inscription | `c3_verdict.registry_inscription` |
| X5 | `D` dérivé champ par champ selon le tableau du § A.6 — liste close épinglée par le test, `engines` et `pair_costs` restreints à la retenue, `decision_timeframes` effectifs **triés par étiquette**, `universe_provenance` constante `clean` | dérivation partagée : verdict **et** ancrage la calculent — propose l'emplacement (`c3_common` ?) au plan |
| X6 | ancrage, famille au verdict compté portant une inscription : le manifeste entrant dont le descripteur dérivé a l'empreinte inscrite est accepté ; toute autre empreinte → `R0_INVALID_RUN`, code 2 | `c3_anchor.stop_criterion` |
| X7 | le verdict d'une variante différée acceptée n'inscrit jamais de `deferred_evaluation` (une fois par famille) | `c3_verdict` |

Plus : renommage du test au nom périmé `…_n_est_pas_rejouable_sous_v21` (`test_c3_entry.py:709`) — nom seul,
corps intact (Application v2.3, point 2) ; `fx.manifest()` et tout manifeste synthétique de la suite dotés de
la date (le gros du volume — recense-les au plan) ; fixtures de conformité locales si elles existent.

### 3.2 Règles du lot (chantier v2.2, reconduites)

- **Un XPASS force la suppression du marqueur, rien d'autre.** Un test caduc se déclare, ne se répare pas.
- Corps des huit tests X : **identiques hors levée des marqueurs**, prouvé par diff AST contre le tip du gel ;
  tout autre changement de test est déclaré. Aucun test retiré.
- **Non-divulgation (§ A.6)** : l'empreinte différée n'est **jamais imprimée** hors registre — aucune ligne de
  log, aucun stdout, aucun artefact hors registre ne la porte ; propose au plan un contrôle mécanique
  (grep des sites d'impression ou test dédié).
- Mutants : au moins un par règle levée — validation de date (borne 365), prédicat d'ouverture de la voie
  (chaque conjonctif), **chaque champ de la dérivation de `D`** (un champ omis ou non restreint doit rougir),
  comparaison à l'ancrage, garde « une fois par famille ». Liste au plan, chacun tué par un test nommé,
  tous restaurés et verts ensuite.
- Argument moteur `min_order_usdc=` intact ; `COUNTED[(inconclusif, P_PROVENANCE)] = False` inchangé ;
  inscription au registre en mode `chain` seul.
- Tunnel : ouvert pour les 13 tests base (lecture seule), fermé et **vérifié fermé** en fin de lot.
- `mypy src/` = 65 ; ruff (liste CI et dépôt) vert ; **formatter scopé aux fichiers nommés, jamais un
  répertoire** ; `interdits.sh` avant chaque commit ; SHA complet partout ; journaux en fichiers seulement ;
  shell zsh → toute vérification par scripts `results/c3_outillage_v2_3/tests/*.sh` lancés en `bash`,
  sorties committées.

### 3.3 Sortie du lot 1

Suite sans tunnel : **3 317 passés** (3 309 + 8 levés — recompte par diff d'identifiants contre le tip du
gel), **1 xfail** (le caduc), 0 échec, 0 XPASS. CI verte en tentative 1. `lot1/README.md` : commits, marqueurs
levés, écarts déclarés jamais arbitrés, défauts dits comme tels.

## 4. Lot 2 — conformité serveur sous v2.3 et porte § L.5

Modèle : lot 3 du chantier v2.2 (`results/c3_outillage_v2_2/conformite/`, `gate_L5/`). **C'est un rejeu de
l'outillage de conformité existant, pas une reconstruction. Le lot n'écrit aucun code** hors la mise à jour du
manifeste de conformité et des scripts de preuve du chantier.

- **Manifeste de conformité v2.3** : celui du 30/09 (`conformite/manifest.json`, forme) avec `protocol_sha256`
  v2.3 et `deferred_evaluation.date` ajoutée. Fenêtre inchangée 2020-01-06 → 2020-12-28 ; la date différée est
  une **déclaration du manifeste, pas une fenêtre lue** — aucune donnée postérieure au 2021-03-01 n'est lue,
  garde-fou 6 intact, `CAMPAIGN_UNLOCK` absent et jamais créé.
- Provenance `unknown` (validé/réfuté inatteignables par construction) ; famille de test, **jamais** une
  famille de campagne ; **registre neuf sous la sortie de chaque exécution**, jeté avec l'archive.
- Attendu déclaré et committé **avant** le run (entrée `RESEARCH_LOG` n° suivant, avec son issue, avant tout
  lancement — règle du journal) ; vérificateurs **prouvés avant de servir** : dry-run des pilotes en monde
  simulé, cas déviés pour tout vérificateur modifié ; `--now` fixe, même chemin absolu + `mv` pour tout run à
  égalité au bit.
- **Trois exécutions** (workers 4 / 1 / 4), quatre temps rejoués, artefacts identiques au bit (liste attendue
  exacte), codes à 0, `chain.verified` vrai, zéro violation, **issue non lue** — codes et booléens sur liste
  close seulement. Aucun sha d'artefact du chemin sélection versionné ni imprimé.
- **Porte § L.5, option 1** : 24/24 en `rc=0`, JUnit agrégé, au SHA testé ; invariance jusqu'au tip prouvée par
  interdits si des commits suivent.
- Archives `~/archive/c3_outillage_v2_3_{conf,gate}_<date>/`, vérifiées par codes (`sha256sum -c`, extraction,
  `diff -rq`), puis `rm -rf` horodaté ; postflight (collector actif `NRestarts=0`, aucune session tmux, base et
  service inchangés, alembic head inchangé, 0 ligne sale). Tunnel **jamais ouvert** au lot 2.
- **STOP avant le lancement serveur** : plan du lot approuvé, GO de Bruno nommant le SHA du run.

## 5. Critère de fin du chantier

1. 0 xfail hors le caduc déclaré ; 3 317 passés ; 0 échec ; 0 XPASS ; 0 test retiré ; CI verte tentative 1 à
   chaque SHA poussé (relance autorisée pour `test_rejeu_effect` seul).
2. Mutants tous rouges puis restaurés et verts, chacun tué par un test nommé au README.
3. Conformité v2.3 : items de l'attendu tous tenus, `rc=0` partout, trois exécutions identiques au bit, issue
   non lue, archives vérifiées puis supprimées.
4. Porte § L.5 : 24/24, agrégat JUnit sans échec ni manquant.
5. `mypy src/` = 65 ; base, service, protocole intacts.
6. Rapport final `results/c3_outillage_v2_3/report.md` (modèle : rapport v2.2) — STOP, relecture Bruno, merge
   par Bruno.

## 6. Interdits

- `src/`, `scripts/backtest.py`, les runners, `rejeu_common.py` : diff vide contre `b50f2d1`.
- **`docs/protocole_c3.md` et `docs/amendements_c3_v2.{1,2,3}.md` : intouchés — le protocole est gelé** ; son
  sha256 recalculé doit rester `d030ab23…79e6` à chaque commit (ajoute ce contrôle à `interdits.sh`).
- `results/c3_v2_2/`, `results/c3b_producteur/`, `results/c3_outillage_v2_2/`, `results/c3_v2_3_gel/` : clos.
- `CAMPAIGN_UNLOCK` jamais créé ; aucune donnée de la fenêtre de campagne lue par le producteur ou la chaîne ;
  le répertoire de la dette 23 (`~/docker/`) jamais nommé dans un script.
- Base en lecture seule ; Decimal partout ; structlog ; aucun changement de `MultiStrategyRouter`,
  `GeminiGlobalRiskManager`, `ExecutionEngine`.

## 7. Règle d'arrêt

Un attendu X qui semble intestable tel quel, un conflit entre le texte v2.3 et un comportement existant, une
interface indicative qui force un choix structurant non prévu au plan : **STOP et question à Bruno.** Les tests
X font foi sur l'attendu ; le texte fait foi sur la règle ; aucun des deux ne se « répare » en chemin.
