# Campagne grid — lecture de diagnostic du STOP au run : script et preuves, amendés (huit classes), soumis à relecture (non exécuté)

**Décision de Bruno** (après le constat `constat.md`) : une lecture de diagnostic, **décidée avant toute lecture**, sur
liste close, de la seule clé `violations` de `out/pre/entry.json`. **Amendement après la première relecture** : trois
classes ajoutées (§ 1), condition de racine approuvée (§ 2). Ce document accompagne le script pour la relecture ;
**rien n'a tourné au serveur.** Le script ne tourne qu'après la relecture de Claude et le GO de Bruno.

- **Script** : `tests/diagnostic_entry.sh` — un heredoc au serveur, lecture seule, même mécanique que l'extraction du
  pilote ; un seul fichier ouvert (`entry.json`), une seule clé lue (`violations`) ; `entry.md` et `entry.log` jamais
  ouverts ; la sortie d'erreur de l'interpréteur jetée au serveur, seul son code remonte (`lecture_exit`).
- **Sortie, forme fixe** (trois lignes, quelle que soit l'issue — aucune forme conditionnelle) :
  `violations_total=<n>` ; `violations_par_classe=anchor_inputs_sha256:<n>,anchor_T:<n>,provenance:<n>,non_fini_ou_invalide:<n>,warmup_series:<n>,warmup_sufficient:<n>,coverage_recoupe:<n>,hors_classe:<n>` ;
  `champs=<champ:n,…>` (ou `-`). `violations_total=illisible` si la clé manque ou n'est pas une liste.
- **Preuves** : `tests/schema_observations.out`, `tests/diagnostic_preuve.out` (§ 3).

## 1. Cadrage, inventaire, classification à huit classes

Le cadrage de Bruno tient : `exit_code = 1 if violations else (2 if refusal else 0)` (`c3_entry.py:978`) ; un échec
I-A produit un refus (code 2), et la cause d'un code 1 est dans `violations`.

**Formes de violation atteignables depuis `c3_entry` au code de S1** (`235461e`), et leur classe :

| # | Forme | Site | Classe |
|---|---|---|---|
| 1 | `anchor.inputs_sha256.manifest: enregistré …, fichier …` | `c3_common.check_inputs_match` l.1101-1106, appelé `c3_entry.py:938` | `anchor_inputs_sha256` |
| 2 | `anchor.anchor déclaré …, recalculé … — le recalcul fait foi` | `c3_entry.py:944-946` | `anchor_T` |
| 3 | `anchor.universe_provenance '…' != manifeste '…'` | `c3_entry.py:951-953` | `provenance` |
| 4 | `InvalidValueError` (valeur non finie, `< minimum`, suite non finie) et `NonFiniteValueError` (`canon`), levées aussi depuis l'intérieur des assertions | `c3_common` l.348, 358, 385, 472, 484, 554 ; `rejeu_common` l.180, 186 ; inscrites `c3_entry.py:974-976` (revue R3 d) | `non_fini_ou_invalide` |
| 5 | `observations.<identité>.decision_timeframes exportée … ≠ liste effective du manifeste …` | `c3_entry.py:497-501` (`a06_warmup`) | **`warmup_series`** |
| 6 | `observations.<identité>.warmup.<préfixe>.<série>.sufficient déclaré …, recalculé …` | `c3_entry.py:516-519` (`a06_warmup`) | **`warmup_sufficient`** |
| 7 | `coverage.pairs.<…>.first_day/last_day …` (deux sous-formes, AM-09) | `c3_common.coverage_recompute` l.2094-2104, versées par `c3_entry.py:597` (`a07_coverage`) | **`coverage_recoupe`** |
| — | toute autre forme | — | `hors_classe` (le filet) |

**Décision de Bruno (amendement)** : les formes 5 à 7, atteignables mais hors du premier cadrage, reçoivent chacune leur
classe, en **comptage seul** : motifs sur les **parties stables** des formes, **aucun groupe, jamais d'extrait** — elles
portent des identités de candidats, des séries de décision, des dates. `hors_classe` reste le filet.

Les autres `InvalidValueError` de `c3_common` (l.556 « hors domaine », l.915 « rejeu : CAGR », l.2295 « bloc
contradictoire ») ne sont **pas** atteignables depuis `c3_entry` à S1 ; leurs motifs sont gardés dans la classe
`non_fini_ou_invalide` parce qu'ils sont des `InvalidValueError` (définition de la classe), déclaré.

## 2. Le champ, et sa validation

Pour `non_fini_ou_invalide`, le champ est la dernière composante du chemin (`<chemin>.<champ>[i]?: …`). Il n'est rendu
que si (a) le chemin part de **`observations.`** et (b) le champ est une clé du **schéma des observations** ; sinon
`hors_liste`. La condition (a) est **approuvée par Bruno** : sans elle, une valeur non finie du manifeste ou de la
couverture sur une clé homonyme (`spread`, `slippage` existent aussi dans `fees.pair_costs` du manifeste) serait rendue
comme un champ des observations. `NonFiniteValueError` (`canon`) ne porte aucun chemin : `hors_liste`. Un champ de la
couverture (`longest_gap_days`, …) : `hors_liste`.

**Le schéma des observations, tiré du code de S1** (`tests/schema_observations.sh`) : les clés que lisent les accesseurs
`cc.require_*`, `cc.nullable_*` et `cc.optional_*`. Le relevé couvre les méthodes de `Context`, `_liquidation_form`,
`_segment_form`, `a01_form`, `a02_d5`, `a03_bounds`, `a04_identities`, `a06_warmup` et `a08_d2`, ainsi que
`c3_common.warmup_sufficient`. Il en sort **63 clés**, extraites par l'AST, égales à la copie `SCHEMA` du script et triées
sans doublon. Deux mutants de la copie mordent : une clé retirée, une clé étrangère ajoutée. Les clés dynamiques
(identité, segment, série, préfixe, `<segment>_start`) sont listées à part et ne sont jamais des champs.

## 3. Preuves, rejouées après l'amendement (locales, sans serveur ni base)

- **Onze témoins produits par le code de S1** (`tests/diagnostic_preuve.out`) :
  - `anchor` et `nan` : les `entry.json` qu'écrit `c3_entry.main` sur des entrées fabriquées ;
  - `non_fini` : les accesseurs réels ;
  - `warmup_series` et `warmup_sufficient` : `a06_warmup` ;
  - `coverage_recoupe` : les deux sous-formes de `coverage_recompute` ;
  - `hors_classe` : une forme inventée ;
  - `mixte` : la réunion des précédents, avec des champs sentinelles hors de `violations` ;
  - `vide`, `illisible` et `non_liste`.
  - Chacune des trois formes tombe dans sa classe. Les onze rendent l'attendu, **dérivé de la classification (texte),
    jamais de la sortie**.
- **Non-divulgation, rejouée** :
  - chaque violation plantée porte l'identité réelle d'un candidat (64 hex). Elle est **plantée au chemin de chacune des
    trois nouvelles formes**, ce que la fabrique vérifie elle-même ;
  - les violations portent aussi des valeurs (`-987654`, NaN, inf), la paire, la stratégie, des séries (`'1d'`) et des
    dates ;
  - `entry.md` et `entry.log` sont présents, porteurs de sentinelles, et **illisibles** (chmod 000).
  - Sur les onze cas, la sortie respecte la grammaire fermée et ne contient aucune chaîne plantée.
- **Huit mutants du corps, tous vus** :
  - violation brute imprimée ; chemin au lieu du champ ; champ non validé ; `entry.md` ouvert (échoue, illisible) ; un
    autre champ d'`entry.json` lu ;
  - **classe `warmup_series` retirée** ; **sous-forme AM-09 « sans unité » retirée** ; **extrait d'une forme
    `warmup_sufficient` imprimé**.

## 4. Ce qui reste avant de tourner

Relecture de Claude au SHA de ce commit, puis GO d'exécution de Bruno : `bash results/c3_campagne_grid/tests/diagnostic_entry.sh`
→ `tests/diagnostic_entry.out`, versionné tel quel (trois lignes de la liste close, des codes).
