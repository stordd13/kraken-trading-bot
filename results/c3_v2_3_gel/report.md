# C3 — gel du protocole v2.3 : rapport (STOP avant merge)

Brief : `agent/AGENT_C3_GEL_V2_3.md`. Texte approuvé : `agent/amendements_c3_v2_3_draft.md` (Bruno, 30/09). Paquet
adopté : `docs/amendements_c3_v2.3.md`, dont la section « Adoption » fait foi avec le texte du protocole. Branche
`feat/c3-amendements-v2.3` depuis `dev` @ `662c104ef8cb5a9b5c7fb04452f7af817cb5a87a`, poussée, **non mergée** : le merge
est fait par Bruno.

## 1. En bref

| | |
|---|---|
| Protocole v2.3 | `docs/protocole_c3.md`, sha256 **`d030ab239de317f6cba89877d682338fa2001d2a63d231f1a86c519fe87a79e6`** |
| Commits | C1 `2807167e2358bf3cd3a17326c818510cae8abb20` (gel), C2 `b47e4c8ec2cbfead9a0c19e711ed71ad5f321685` (xfail), C3 (ce rapport, preuves) |
| Suite sans tunnel | base `662c104` : 3 310 passés, 19 ignorés, 1 xfail ; C1 : identique ; **C2 : 3 309 passés, 19 ignorés, 9 xfail, 0 échec, 0 XPASS** |
| CI | C1 : run 36728661205 ; C2 : run 36730196567 — vertes en tentative 1, aucune relance ; C3 : au message de STOP (un commit ne peut pas porter la CI de son propre SHA) |
| Interdits | `src/`, `scripts/`, `config/`, `pyproject.toml`, `poetry.lock`, `.github/`, `results/c3b_producteur/`, `results/c3_outillage_v2_2/`, `results/c3_v2_2/` : diff vide contre `662c104` à chaque commit |
| Aucun | serveur, base, tunnel, migration, artefact du chemin sélection, sha d'artefact versionné ; `CAMPAIGN_UNLOCK` absent |

## 2. Ce qui a été fait

**C1 — le gel (docs, plus deux lignes de test).**
- `docs/protocole_c3.md` :
  - AM-00 : la révision v2.3, en tête du bloc des révisions, sous la forme établie (G-4).
  - AM-01 au § A.6 : les cinq puces de l'« Après », appliquées en deux sites autour de « À l'étape 1 » (G-3). Le
    tableau de `D` porte `engines` restreint à la stratégie retenue (G-6) et la ligne `decision_timeframes`, triée
    par étiquette (G-7). La date entre dans la liste « au minimum et sans exception » (G-1).
  - AM-02 au § I.1 : la ligne 10 ter et la phrase sous la table.
  - Rien d'autre : l'index § M se régénère à l'identique.
- `docs/amendements_c3_v2.3.md` : le draft, transformé seulement par le statut ADOPTÉ, la section « Adoption »
  (empreinte v2.0 à v2.3, décisions de la conversation manifeste et du STOP du gel, portée, réserves X1-X8, écarts),
  la section « Empreinte » du draft retirée, et G-1, G-6, G-7. La ligne `**sha256 v2.3 :**` est la dernière de la
  section.
- `docs/CONTRAINTES_POST_B4.md` § 10.1 : la phrase compagnon, en place ; aucune autre ligne.
- Consignations du sha v2.3 :
  - `docs/RESEARCH_LOG.md` : entrée 20, sur le modèle de l'entrée 18, et une puce « Essais à venir » (ajout seul) ;
  - `skills/backtest.md` : le paragraphe « Source » ;
  - `CLAUDE.md` : le résumé, le routage (une ligne v2.3 ajoutée, la ligne v2.2 conservée) et l'encart du protocole,
    mentions historiques conservées.
- `tests/test_scripts/test_c3_common.py` : `ADOPTED_PACKAGE` → paquet v2.3, et la liste des révisions de la table
  passe à quatre (G-9).
- `agent/` : le brief et le draft, commités tels que reçus (sha256 aux préfixes `430d5b83…` et `5db399e6…`,
  relevés à la réception et à chaque commit).

**C2 — le squelette normatif.** Sept tests neufs et le témoin R-17 converti, tous `xfail(strict=True)` avec une raison
qui renvoie à AM-01 ; l'adverse R-17 mis à jour reste vert.

| # | Test | Fichier | Rouge aujourd'hui sur |
|---|---|---|---|
| X1 | `test_X1_un_manifeste_sans_date_d_evaluation_differee_est_refuse_a_l_etape_1` | `test_c3_anchor.py` | code 0 (attendu 2) |
| X2 | `test_X2_une_date_trop_proche_ou_illisible_est_refusee_365_jours_exactement_passent` | `test_c3_anchor.py` | le premier cas trop proche est accepté ; le témoin des 365 jours passe |
| X3 | `test_X3_l_issue_qui_ouvre_la_voie_inscrit_la_date_du_manifeste_et_l_empreinte_du_descripteur` | `test_c3_verdict.py` | aucune inscription ; la condition du § 10.1 est vérifiée avant |
| X4 | `test_X4_une_issue_qui_n_ouvre_pas_la_voie_n_inscrit_aucune_evaluation_differee` | `test_c3_verdict.py` | son témoin positif intégré (G-11) |
| X5 | `test_X5_le_descripteur_est_derive_champ_par_champ_selon_le_tableau_du_texte` | `test_c3_verdict.py` | `AttributeError` sur `cv.deferred_descriptor`, après l'épinglage du calcul côté test |
| X6 | `test_R17_temoin_…_l_empreinte_differee_attendue_est_acceptee` (xfail) et `test_R17_sur_une_famille_close_…_est_refusee` (vert) | `test_c3_anchor.py` | refus `R0_INVALID_RUN` du critère d'arrêt : empreinte brute ≠ `sig(canon(D))` |
| X7 | `test_X7_le_verdict_d_une_variante_differee_n_inscrit_jamais_d_evaluation_differee` | `test_c3_verdict.py` | le même refus : la variante différée n'est pas encore acceptée par descripteur |
| X8 | `test_X8_load_manifest_lit_la_date_differee_et_refuse_toute_forme_invalide` | `test_c3_common.py` | le champ lu est absent |

Le descripteur est calculé côté test (`fx.deferred_descriptor`, `fx.deferred_descriptor_at_run`), à partir du tableau
du texte et jamais importé de l'outillage. X5 l'épingle à la table recopiée valeur par valeur, et c'est l'attendu de X3,
X6 et X7. Emplacement retenu : les fichiers existants au plus près du sujet ; aucun fichier de test neuf.

**C3 — preuves et rapport** : ce fichier et `tests/` (§ 6).

## 3. Décisions du STOP du gel

Consignées au paquet, section « Adoption », table G-1 à G-11 ; elles ne sont pas redites ici. En une ligne chacune :
- G-1 : § A.6 et non § A.5 ; formulation de la date dans la liste ; deux renvois du paquet corrigés.
- G-2 : constat D5, sans retouche.
- G-3 : placement d'AM-01.
- G-4 : forme d'AM-00.
- G-5 : pas de section « Amendements — v2.3 ».
- G-6 : `engines` restreint.
- G-7 : `decision_timeframes` trié par étiquette.
- G-8 : `ac7710f` pour v2.2.
- G-9 : deuxième ligne de test de C1.
- G-10 : scission du témoin R-17, comptes 3 309 / 9.
- G-11 : témoin positif intégré à X4.

## 4. Écarts déclarés (jamais arbitrés)

1. **Écarts au brief, tous décidés au gate** : G-4 (AM-00), G-1 (renvois § A.6), G-6 et G-7 (deux cellules du
   tableau), G-8 (table), G-9 (seconde ligne de test en C1), G-10 (7 neufs au lieu de 8 ; 3 309 passés au lieu de
   3 310), fichiers `agent/` commités et liste blanche étendue (GO du 30/09).
2. **Helper de test modifié** : `_chain_world` (`test_c3_verdict.py`) reçoit un paramètre facultatif
   `manifest_payload`, défaut inchangé. C'est le seul objet de test modifié hors G-9 et G-10 (`comptes_gel.out`,
   diff AST des objets de premier niveau).
3. **Construction de X7** :
   - La variante différée est le monde de chaîne des fixtures (fenêtre 2023-04-01 → 2026-04-01, candidat unique).
   - Sa campagne (fenêtre 2020-04-01 → 2023-04-01, date déclarée 2026-04-01) est enregistrée d'abord, avec un verdict
     compté ouvrant la voie et l'inscription `sig(canon(D))`.
   - Le monde est construit sur la version racine du manifeste, puis le manifeste différé est posé à sa place : la
     sonde de `_chain_world` tourne sur un registre neuf, où le parent n'existe pas (voir § 7).
4. **Choix d'interface, indicatifs** (l'outillage v2.3 peut les changer sans toucher à l'attendu) :
   - le champ `Manifest.deferred_evaluation_date` ;
   - `cv.deferred_descriptor(campaign, retained)` ;
   - la classe `cc.MissingEvidenceError` pour une forme invalide ;
   - pour X1 et X2, l'observable du refus est « code 2, rien écrit, rien enregistré » : l'ancrage n'imprime pas la
     raison `R0_INVALID_RUN` sur une erreur de forme (convention « ENTREE INVALIDE », précédent R-17 « sans
     famille ») ;
   - `raises=AssertionError` pour sept xfail, `raises=AttributeError` pour X5.
5. **Lignes laissées périmées, hors du périmètre du brief** :
   - `skills/backtest.md`, paragraphe « Tests » (« dernière empreinte (v2.2) relue dans le paquet adopté », décompte
     932) ;
   - `PROJECT_CONTEXT.md` (non listé au brief) ;
   - `docs/CODE_MAP.md` (aucun code changé).
   Ce sont des candidats pour le `docs(merge)`.

## 5. Décompte des tests

Réconciliation par identifiants contre `662c104` (`tests/comptes_gel.out`, collectes des deux côtés, même `-k`) :
- **retirés : aucun** ;
- **ajoutés : exactement les 7 déclarés** (X1, X2, X3, X4, X5, X7, X8 ; `tests/declares_gel.txt`) ;
- **xfail** : 1 (le caduc de v2.2) + 7 neufs + le témoin R-17 = **9** ;
- **passés** : 3 310 − 1 (le témoin R-17 passe en xfail) + 0 neuf vert = **3 309** ;
- ignorés 19 et désélectionnés 24 (les `_full`) : inchangés ;
- aucun XPASS, FAILED ni ERROR.

**L'écart de −1 au critère § 4.3 du brief** (3 310 attendus) est la décision G-10. Le témoin R-17 inscrivait
l'empreinte du manifeste brut, qu'AM-01 remplace par `sig(canon(D))`. Resté vert, il aurait été un verrou posé sur une
règle abrogée ; converti, il porte l'attendu d'acceptation de X6.

## 6. Preuves (`results/c3_v2_3_gel/tests/`, toutes lancées par `bash`)

| Script | Sortie(s) | Ce qu'il établit | rc |
|---|---|---|---|
| `interdits_gel.sh` | `interdits_gel_C1.out`, `_C2.out`, `_C3.out` | à chaque commit, sur les fichiers indexés : chemins gelés intacts (HEAD, index, arbre, non suivis), liste blanche, aucun artefact du chemin sélection, `CAMPAIGN_UNLOCK` absent, toute empreinte de 64 hex ajoutée ∈ table d'Adoption | 0 |
| `texte_conforme.sh` | `texte_conforme_C1.out`, `_C3.out` | protocole(662c104) + blocs « Après » + G-1, G-4 = protocole courant (espaces normalisés), changements localisés à l'en-tête, au § A.6 et au § I.1 ; CONTRAINTES : la seule phrase ; paquet contre draft : exactement quatre écarts (statut, deux renvois, cellules G-6/G-7) ; index § M régénéré égal | 0 |
| `temoins_texte.sh` | `temoins_texte.out` | `texte_conforme` mord : 4 mutants temporaires (Après d'AM-01 altéré, mot changé au § B.2, corps d'AM-02 du paquet, CONTRAINTES § 10.2), tous vus ; arbre restauré au sha près | 0 |
| `sha_consigne.sh` | `sha_consigne_C1.out`, `_C3.out` | sha recalculé = ligne `**sha256 v2.3 :**` (dernière de la section) = dernière ligne de la table = `protocol_descriptor` ; présent aux quatre consignations ; `ADOPTED_PACKAGE` sur v2.3 ; les deux tests d'épinglage verts | 0 |
| `suite_gel.sh` | `suite_base.out`, `suite_C1.out`, `suite_C2.out` | suite complète sans tunnel (greffon `gate_sans_tunnel` de v2.2) | 0 |
| `comptes_gel.sh` + `declares_gel.txt` | `comptes_gel.out` | § 5, plus le diff AST des objets de test : modifiés et ajoutés égaux aux déclarations, retirés ∅ | 0 |
| `xfail_rouge.sh` | `xfail_rouge.out` | les 8 xfail sortent XFAIL strict avec leur raison ; en `--runxfail`, la ligne et l'exception de chacun (l'assertion de la règle, jamais un préalable) | 0 |
| `mutants_gel.sh` | `mutants_gel.out` | M1 : `stop_criterion` qui accepte tout sur une famille close rougit l'adverse R-17 ; M2-M4 : un descripteur côté test sans tri, sans restriction d'`engines` ou de `pair_costs` fait sortir X5 FAILED au lieu de xfailed ; arbre restauré, `git diff scripts/` vide | 0 |
| `lint_gel.sh` | `lint_gel_C1.out`, `_C2.out` | ruff check et `format --check` (liste CI, fichiers touchés, `results/` du chantier) ; mypy `src/` = 65 | 0 |
| `ci_status.sh` | `ci_status_C1.out`, `_C2.out` | CI sur le SHA poussé, tentative 1 ; relance réservée à `test_rejeu_effect` | 0 |

## 7. Défauts de ma part, trouvés par moi avant tout commit

- **`texte_conforme.sh`, premier lancement** : deux défauts du harnais, pas du texte. Le nom de section du § I.1 était
  tronqué à 40 caractères, puis comparé à une chaîne plus longue ; le contrôle « section Empreinte retirée » cherchait
  une sous-chaîne que la section Adoption cite elle-même. Corrigés avant C1, et la preuve a ensuite été vérifiée par
  mutation (`temoins_texte.out`).
- **X7, première version** : il échouait dans la sonde de `_chain_world` (parent absent du registre neuf de la sonde),
  pas sur la règle. Sous l'outillage v2.3, il serait donc resté rouge pour toujours. Vu en `--runxfail`, corrigé
  (§ 4, point 3) ; il échoue maintenant sur le refus du critère d'arrêt.
- **`xfail_rouge.sh`, premier lancement** : le motif du résumé attendait « 8 xfailed » en début de ligne ; pytest
  écrit « 661 deselected, 8 xfailed ». En outre, la passe `--runxfail` imprimait en entier une empreinte synthétique
  de 64 hex, que le contrôle 4 d'`interdits_gel.sh` aurait refusée. Les deux sont corrigés : motif réparé, empreintes
  tronquées à 16 caractères.
- **Mes premiers tests n'étaient pas formatés.** `ruff format` a été appliqué aux trois fichiers nommés ; les hunks
  touchés sont tous dans mes zones (vérifié par `git diff -U0`). Le nom de X8 a été raccourci pour éviter une
  signature coupée.

## 8. Limites et points pour le chantier d'outillage v2.3

- **À la levée de X1**, `fx.manifest()` devra déclarer `deferred_evaluation.date`, sinon tous les manifestes des
  fixtures seront refusés. X1 et X8 retirent la clé eux-mêmes, et ne dépendent pas de ce défaut.
- **La règle « `universe_provenance` : la constante `clean` » n'est pas discriminée par X5** : la voie ne s'ouvre que
  sur une campagne `clean` (note de portée), donc constante et provenance de campagne coïncident partout où `D` est
  construit.
- **`Δ̂ > 0` aux six combinaisons** est vérifié par appariement (dd, σ) : la valeur ponctuelle ne dépend pas de `L`.
- **La non-divulgation (X3)** est vérifiée sur ce que la chaîne publie : sortie standard, erreur, fichiers du
  répertoire de sortie. Le registre porte l'empreinte par construction.
- **`Application` du paquet, point 2** (renommage du test périmé `test_c3_entry.py:709`) : non fait ici, il appartient
  à l'outillage v2.3.

## 9. Pour le merge (Bruno)

- Relire le diff complet : `git diff 662c104ef8cb5a9b5c7fb04452f7af817cb5a87a feat/c3-amendements-v2.3`.
- Après le merge, `c3_anchor` refuse tout manifeste v2.2 : les conformités du 30/09 sont historiques (AM-00).
- Aucun code n'a changé : pas de migration, pas de régénération de `CODE_MAP` imposée ; le pull serveur est une affaire
  de parité, sans redémarrage.
- **Suite** : l'outillage v2.3 (lever X1-X8), puis le manifeste de la première campagne, portant le sha v2.3 et la clé
  `deferred_evaluation.date`.
