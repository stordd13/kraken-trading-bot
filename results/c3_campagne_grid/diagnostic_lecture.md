# Campagne grid — lecture de diagnostic du STOP au run : script et preuves, soumis à relecture (non exécuté)

**Décision de Bruno** (après le constat `constat.md`) : une lecture de diagnostic, **décidée avant toute lecture**, sur
liste close, de la seule clé `violations` de `out/pre/entry.json`. Ce document accompagne le script pour la relecture ;
**rien n'a tourné au serveur.** Le script ne tourne qu'après la relecture et le GO de Bruno.

- **Script** : `tests/diagnostic_entry.sh` — un heredoc au serveur, lecture seule, même mécanique que l'extraction du
  pilote ; un seul fichier ouvert (`entry.json`), une seule clé lue (`violations`) ; `entry.md` et `entry.log` jamais
  ouverts ; la sortie d'erreur de l'interpréteur jetée au serveur, seul son code remonte (`lecture_exit`).
- **Sortie, forme fixe** (trois lignes, quelle que soit l'issue — aucune forme conditionnelle) :
  `violations_total=<n>` ; `violations_par_classe=anchor_inputs_sha256:<n>,anchor_T:<n>,provenance:<n>,non_fini_ou_invalide:<n>,hors_classe:<n>` ;
  `champs=<champ:n,…>` (ou `-`). `violations_total=illisible` si la clé manque ou n'est pas une liste.
- **Preuves** : `tests/schema_observations.out`, `tests/diagnostic_preuve.out` (§ 3).

## 1. Cadrage, et ce que le code de S1 y ajoute

Le cadrage de Bruno tient : `exit_code = 1 if violations else (2 if refusal else 0)` (`c3_entry.py:978`) ; un échec
I-A produit un refus (code 2), et la cause d'un code 1 est dans `violations`.

**Inventaire des formes de violation atteignables depuis `c3_entry` au code de S1** (`235461e`), fait avant d'écrire :

| # | Forme | Site | Classe (classification décidée) |
|---|---|---|---|
| 1 | `anchor.inputs_sha256.manifest: enregistré …, fichier …` | `c3_common.check_inputs_match` l.1101-1106, appelé `c3_entry.py:938` | `anchor_inputs_sha256` |
| 2 | `anchor.anchor déclaré …, recalculé … — le recalcul fait foi` | `c3_entry.py:944-946` | `anchor_T` |
| 3 | `anchor.universe_provenance '…' != manifeste '…'` | `c3_entry.py:951-953` | `provenance` |
| 4 | `InvalidValueError` (valeur non finie, `< minimum`, suite non finie) et `NonFiniteValueError` (`canon`), levées aussi depuis l'intérieur des assertions | `c3_common` l.348, 358, 385, 472, 484, 554 ; `rejeu_common` l.180, 186 ; inscrites `c3_entry.py:974-976` (revue R3 d) | `non_fini_ou_invalide` |
| **5** | `observations.<identité>.decision_timeframes exportée … ≠ liste effective du manifeste …` | **`c3_entry.py:497-501`** (`a06_warmup`, `ctx.violations`, la liste de `main`) | **`hors_classe`** |
| **6** | `observations.<identité>.warmup.<préfixe>.<série>.sufficient déclaré …, recalculé …` | **`c3_entry.py:516-519`** (`a06_warmup`) | **`hors_classe`** |
| **7** | `coverage.pairs.<paire>.<série>.first_day/last_day …` (deux sous-formes, AM-09) | **`c3_common.coverage_recompute` l.2089-2104**, versées par `c3_entry.py:597` (`a07_coverage`) | **`hors_classe`** |

**Les formes 5 à 7 ne figurent pas dans le cadrage.** Sous la classification décidée, elles tombent en `hors_classe` —
le témoin `hors_classe` le prouve sur les trois, produites par le code de S1. Si l'une d'elles est la cause, la sortie
dira `hors_classe:<n>` sans dire laquelle : un point de décision. **Non élargi ici** : ajouter une classe par forme (par
exemple `series_decision`, `amorcage_sufficient`, `couverture_dates`) reste ta décision, à prendre avant le GO, puisque
la classification se décide avant toute lecture.

Les autres `InvalidValueError` de `c3_common` (l.556 « hors domaine », l.915 « rejeu : CAGR », l.2295 « bloc
contradictoire ») ne sont **pas** atteignables depuis `c3_entry` à S1 ; leurs motifs sont gardés dans la classe
`non_fini_ou_invalide` parce qu'ils sont des `InvalidValueError` (définition de la classe), déclaré.

## 2. Le champ, et sa validation

Pour `non_fini_ou_invalide`, le champ est la dernière composante du chemin (`<chemin>.<champ>[i]?: …`). Il n'est rendu
que si (a) le chemin part de **`observations.`** et (b) le champ est une clé du **schéma des observations** ; sinon
`hors_liste`. La condition (a) est un **choix d'implémentation, à approuver** : sans elle, une valeur non finie du
manifeste ou de la couverture sur une clé homonyme (`spread`, `slippage` existent aussi dans `fees.pair_costs` du
manifeste) serait rendue comme un champ des observations. `NonFiniteValueError` (`canon`) ne porte aucun chemin :
`hors_liste`. Un champ de la couverture (`longest_gap_days`, …) : `hors_liste`.

**Le schéma des observations, tiré du code de S1** (`tests/schema_observations.sh`) : les clés que lisent les accesseurs
`cc.require_*`, `cc.nullable_*` et `cc.optional_*`. Le relevé couvre les méthodes de `Context`, `_liquidation_form`,
`_segment_form`, `a01_form`, `a02_d5`, `a03_bounds`, `a04_identities`, `a06_warmup` et `a08_d2`, ainsi que
`c3_common.warmup_sufficient`. Il en sort **63 clés**, extraites par l'AST, égales à la copie `SCHEMA` du script et triées
sans doublon. Deux mutants de la copie mordent : une clé retirée, une clé étrangère ajoutée. Les clés dynamiques
(identité, segment, série, préfixe, `<segment>_start`) sont listées à part et ne sont jamais des champs.

## 3. Preuves (locales, sans serveur ni base)

- **Témoins produits par le code de S1** (`tests/diagnostic_preuve.out`) :
  - `anchor` et `nan` sont les `entry.json` qu'écrit `c3_entry.main` sur des entrées fabriquées : les formes 1-3, puis
    un `net_pnl` NaN levé dans l'assertion I-A.1 ;
  - `non_fini` vient des accesseurs réels ; `hors_classe` vient de `a06_warmup` et `coverage_recompute`, plus une forme
    inconnue ;
  - `mixte` réunit les quatre précédents, avec des champs sentinelles hors de `violations` ; viennent ensuite `vide`,
    `illisible` et `non_liste`.
  - Les huit rendent l'attendu, **dérivé de la classification (texte), jamais de la sortie**.
- **Non-divulgation** :
  - chaque violation plantée porte l'identité réelle d'un candidat (la clé d'observation, 64 hex) et des valeurs
    (`-987654`, NaN, inf, la paire, la stratégie) ;
  - `entry.md` et `entry.log` sont présents, porteurs de sentinelles, et **illisibles** (chmod 000).
  - Sur les huit cas, la sortie respecte la grammaire fermée et ne contient aucune chaîne plantée.
- **Cinq mutants du corps, tous vus** : violation brute imprimée ; chemin au lieu du champ ; champ non validé ;
  `entry.md` ouvert (échoue, illisible) ; un autre champ d'`entry.json` lu.

## 4. À trancher avant le GO

1. Les formes 5 à 7 restent-elles en `hors_classe`, ou reçoivent-elles leurs classes (§ 1) ?
2. La condition de racine `observations.` (§ 2) est-elle approuvée ?
3. GO d'exécution : `bash results/c3_campagne_grid/tests/diagnostic_entry.sh` → `tests/diagnostic_entry.out`, versionné tel
   quel (trois lignes de la liste close, des codes).
