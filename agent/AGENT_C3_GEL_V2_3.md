# Brief agent — Gel du protocole C3 v2.3 (application du texte + squelette normatif)

**Nouvel agent. Mode ask-for-edit / review : chaque édition est proposée et relue avant application.
Aucun serveur, aucune base, aucun tunnel. Un STOP : au rapport, avant merge. Le merge est fait par Bruno,
jamais par l'agent.**

## 0. À lire avant tout geste

Dans cet ordre :
1. `CLAUDE.md` (règles d'or du projet) ;
2. le fichier joint `amendements_c3_v2_3_draft.md` — **le texte approuvé par Bruno le 30/09, source unique de
   ce chantier** ; son corps (AM-00, AM-01, AM-02, Application, Limites) ne se réécrit pas ;
3. `docs/protocole_c3.md` (v2.2, sha256 `1bed7696c0b0002b702f34fd549a59fc648968ff2e3056a98d33168bd643292a`) —
   les passages cités en « Avant » dans le draft ;
4. `docs/amendements_c3_v2.2.md`, section « Adoption » — **modèle de forme** pour la section Adoption v2.3
   (table Empreinte, ligne `**sha256 vX.Y :**`, décisions de gate, réserves) ;
5. `docs/CONTRAINTES_POST_B4.md` § 10.1 (la phrase à remplacer) ;
6. `tests/test_scripts/test_c3_common.py:552-577` (mécanisme d'épinglage `ADOPTED_PACKAGE`) ;
7. `docs/RESEARCH_LOG.md`, entrée 18 (modèle d'entrée « aucun run »).

## 1. Contexte

Le protocole C3 v2.2 est gelé et outillé (chantier clos le 30/09, `results/c3_outillage_v2_2/report.md`).
La conversation manifeste du 30/09 a tranché et Bruno a approuvé un mini-amendement v2.3 : AM-01 (inscription
de l'évaluation différée — date déclarée au manifeste, engagement par descripteur `D`) et AM-02 (§ I.1,
ligne 10 ter). Ce chantier **applique** ce texte et pose son squelette normatif. **Il n'implémente rien** :
l'outillage v2.3 est un chantier séparé, cadré après ce gel.

## 2. Objectif

Un seul livrable : `dev` prêt à recevoir, par merge de Bruno, le protocole v2.3 gelé — texte appliqué à
l'identique, sha256 consigné, épinglage à jour, règles nouvelles portées par des `xfail` strict, suite verte,
CI verte.

## 3. Spécification

### 3.1 Branche

`feat/c3-amendements-v2.3` depuis `dev` @ `662c104ef8cb5a9b5c7fb04452f7af817cb5a87a`. SHA complet partout,
`gh` compris.

### 3.2 Commit C1 — le gel (docs seulement)

1. **`docs/protocole_c3.md`** : appliquer les blocs Avant/Après du draft, à l'identique.
   - AM-00 : ligne v2.3 au bloc des révisions de l'en-tête (date du gel : 2026-09-30).
   - AM-01 : les deux puces du § A.6 remplacées par le bloc « Après » (clé du manifeste, tableau du
     descripteur `D`, dérivation à l'ancrage, non-divulgation) ; ajout de `deferred_evaluation.date` à la
     liste des déclarations minimales du § A.5.
   - AM-02 : ligne 10 ter insérée entre 10 bis et 11 dans la table du § I.1, plus la phrase sous la table.
   - **Rien d'autre ne change dans ce fichier.** Tout passage « Avant » introuvable ou ambigu → STOP, question
     à Bruno, jamais d'arbitrage silencieux.
2. **`docs/amendements_c3_v2.3.md`** : le draft joint, posé avec ces seules transformations :
   - en-tête : statut « **ADOPTÉ le 2026-09-30** (Bruno) », mention « draft » retirée ;
   - section « **## Adoption — 2026-09-30** » insérée après l'en-tête, sur le modèle v2.2, portant :
     - la table « Empreinte du protocole » (v2.2 → v2.3), remplie avec le sha256 recalculé de
       `docs/protocole_c3.md` **après** l'édition du point 1 ;
     - la ligne exacte, en dernier dans la section : `**sha256 v2.3 :** \`<64 hex>\`` — c'est la ligne que le
       test d'épinglage attrape par la regex `\*\*sha256 v(\d+\.\d+) :\*\* \`([0-9a-f]{64})\`` ;
     - les décisions de gate consignées : D-A (date déclarée au manifeste, validée à l'ancrage), D-B
       (engagement par descripteur, liste close ; `engines` inclus, paramètres de procédure exclus), D-C
       (empreinte au registre seul, jamais versionnée ni imprimée) ; « au moins 12 mois » s'entend
       **≥ 365 jours** entre `window.end` et `deferred_evaluation.date` ; tri v2.3/v2.4 (D3 lot 2 et le
       renommage entrent ; D3, D6, D14 lot 1 et D6, D7 lot 2 attendent v2.4) ; la limite « mécanique du run
       différé reportée sous contrainte du descripteur » assumée ;
     - une note de portée : la voie prospective ne s'ouvre que sur `F_CANNOT_SEPARATE` (rang 11 du § H.1) ;
       sous provenance `contaminated` ou `unknown`, `P_PROVENANCE` (rang 2) la précède — l'amendement ne rend
       la sortie différée atteignable que pour une campagne `clean` ;
   - la section « Empreinte du protocole (à remplir au gel) » de fin de draft : supprimée (remplacée par la
     table de la section Adoption).
   - **Le corps des AM est intact au caractère près.** Tout écart nécessaire → STOP.
3. **`docs/CONTRAINTES_POST_B4.md` § 10.1** : la phrase « La date et le manifeste sont écrits au moment du
   verdict, pas après. » remplacée par la phrase compagnon du draft. Aucune autre ligne de ce fichier.
4. **Consignations du sha v2.3** (règle R-01 : un fichier ne porte pas sa propre empreinte) :
   - `docs/RESEARCH_LOG.md` : **entrée 20**, modèle de l'entrée 18 — chantier documentaire, aucun run, aucune
     donnée lue, aucune base, aucun serveur ; branche, sha v2.3, renvoi à `docs/amendements_c3_v2.3.md` ;
     suite : outillage v2.3, puis manifeste ;
   - `skills/backtest.md` : le paragraphe « Source » mis à jour (v2.3, sha, amendements v2.3 ; v2.2 rejoint
     l'historique comme v2.1 l'a fait) ;
   - `CLAUDE.md` : les mentions v2.2 « protocole courant » mises à jour vers v2.3 (sha), sur le modèle des
     lignes existantes — mentions historiques v2.1/v2.2 conservées.
5. **`tests/test_scripts/test_c3_common.py:552`** : `ADOPTED_PACKAGE` basculé sur
   `docs/amendements_c3_v2.3.md`. C'est la **seule** ligne de test de C1 ; elle y est pour que la suite reste
   verte à chaque commit.

Message : `docs(c3): gel du protocole v2.3 — AM-01 évaluation différée, AM-02 § I.1 ligne 10 ter`.

### 3.3 Commit C2 — le squelette normatif (xfail strict)

Huit tests neufs, **`xfail` strict** (`strict=True`), marqués `reason` renvoyant à AM-01. **Règle du chantier
v2.2, reconduite : l'attendu d'un xfail est normatif, son interface est indicative.** L'outillage v2.3 les
lèvera ; un XPASS force la suppression du marqueur, rien d'autre.

| # | Attendu (normatif) |
|---|---|
| X1 | Manifeste sans clé `deferred_evaluation.date` → refus à l'étape 1, `R0_INVALID_RUN`, code 2 (§ A.5, § A.6 v2.3 ; § I.1 ligne 2) |
| X2 | `deferred_evaluation.date` à moins de 365 jours après `window.end`, ou non lisible comme date → même refus |
| X3 | Verdict dont l'issue ouvre la voie prospective du § 10.1 (`F_CANNOT_SEPARATE`, `Q1∧Q2∧Q3`, `Δ̂ > 0` aux six combinaisons) : inscrit `deferred_evaluation {date, variant_key}` dans l'enregistrement de sa variante, `date` copiée du manifeste, `variant_key = sig(canon(D))`, en mode `chain` seul |
| X4 | Verdict dont l'issue n'ouvre pas la voie : aucune inscription `deferred_evaluation` |
| X5 | Le descripteur `D` est dérivé champ par champ selon le tableau d'AM-01 (manifeste + configuration retenue synthétiques → valeur attendue de chaque champ, `universe_provenance = "clean"`, `fees.pair_costs` restreint à la paire retenue) |
| X6 | Ancrage, famille au verdict compté portant une inscription : manifeste entrant dont le descripteur dérivé a l'empreinte inscrite → accepté ; toute autre empreinte de descripteur → `R0_INVALID_RUN`, code 2 (l'adverse v2.2 « famille close, autre empreinte » est mis à jour vers la comparaison par descripteur, corps déclaré au diff) |
| X7 | Verdict d'une variante différée acceptée : n'inscrit jamais de `deferred_evaluation` (une fois par famille) |
| X8 | `load_manifest` lit `deferred_evaluation.date` (datetime) ; forme invalide → erreur de forme, jamais un défaut silencieux |

- Emplacement : fichiers `tests/test_scripts/test_c3_*.py` existants au plus près du sujet (anchor, verdict,
  common), ou un fichier neuf `test_c3_deferred.py` si c'est plus lisible — au choix, dit au rapport.
- AM-02 : **zéro test** (comportement inchangé, couvert par R-18 et T1-T15).
- Aucun test existant modifié hors X6 ; toute modification est déclarée.

Message : `test(c3): xfail strict v2.3 — évaluation différée (X1-X8)`.

### 3.4 Commit C3 — preuves et rapport

`results/c3_v2_3_gel/` :
- `report.md` : ce qui a été fait, les écarts déclarés (jamais arbitrés), le décompte des tests, le sha v2.3 ;
- `tests/interdits_gel.sh` + `.out` : diff vide contre `662c104` sur `src/`, `scripts/`, `config/`,
  `pyproject.toml`, `poetry.lock`, `.github/`, `results/c3b_producteur/`, `results/c3_outillage_v2_2/`,
  `results/c3_v2_2/` ; liste blanche des fichiers changés = exactement ceux des § 3.2-3.4 ;
- `tests/sha_consigne.sh` + `.out` : recalcul `sha256sum docs/protocole_c3.md` et grep de la valeur aux
  quatre consignations + `ADOPTED_PACKAGE` ;
- `tests/comptes_gel.sh` + `.out` : décompte de la suite (attendu § 4).

Message : `docs(c3): rapport du gel v2.3, preuves`.

## 4. Validation — critère de fin

Tout doit tenir, sinon STOP :
1. Diff de `docs/protocole_c3.md` strictement égal aux blocs Avant/Après du texte approuvé.
2. Test d'épinglage vert : sha256 recalculé = ligne `**sha256 v2.3 :**` = les quatre consignations.
3. Suite complète locale, **sans tunnel** : 3 310 passés, **9 xfail** (1 caduc + X1-X8), 0 échec, 0 XPASS,
   0 test retiré. Tout écart de compte est expliqué au rapport avant STOP.
4. `interdits_gel.out` à `rc=0` ; aucun fichier hors liste blanche.
5. Lint : ruff (liste CI) vert sur les fichiers touchés ; **formatter scopé aux fichiers nommés, jamais un
   répertoire** ; `mypy src/` inchangé (= 65) — `src/` n'étant pas touché, tout écart est un signal d'alerte.
6. CI verte **en tentative 1** à chaque SHA poussé (relance autorisée pour `test_rejeu_effect` seul).
7. STOP au rapport : Bruno relit le diff complet, merge lui-même. **Aucun merge par l'agent.**

## 5. Interdits

- `src/`, `scripts/`, `config/`, `pyproject.toml`, `poetry.lock`, `.github/` : intouchés.
- Aucune connexion base, aucun tunnel, aucun geste serveur, aucune migration.
- Aucun artefact du chemin sélection, aucun sha d'artefact versionné, `CAMPAIGN_UNLOCK` jamais créé.
- Aucune implémentation des règles AM-01 « en convention » : le squelette xfail, rien de plus.
- Shell : l'agent est en zsh ; toute vérification passe par des scripts lancés en `bash`, sorties committées.
- Journaux en fichiers seulement ; `interdits_gel.sh` avant chaque commit.

## 6. Règle d'arrêt

Toute ambiguïté du texte approuvé, tout « Avant » introuvable, tout conflit avec un test existant, toute
tentation d'améliorer le texte en chemin : **STOP et question à Bruno.** Ce chantier applique, il ne décide
pas.
