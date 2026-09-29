# Amendements au protocole C3 — v2.1 → v2.2

> **Statut : ADOPTÉ le 2026-09-29** (Bruno), sous les décisions de gate et les réserves d'application de la
> section « Adoption » ci-dessous, qui porte aussi l'empreinte de v2.2. Historique : proposé le 2026-09-29,
> retouché au STOP de lecture adverse le même jour (C-1 à C-6), dont le GO a figé le texte pour application ;
> appliqué au protocole, un commit par amendement ; adopté au commit qui porte cette section. Les rôles : la
> lecture adverse est faite par Claude (relecteur), sur l'Avant / Après d'AM-03, AM-06 et AM-08 ; Bruno adopte.
> Ce paquet est un texte, et il se relit comme un texte.
>
> **La règle qui autorise ce document** est celle du § 0.7 et de l'en-tête du protocole : toute modification
> postérieure au gel est un **amendement daté**, qui dit ce qui a changé et pourquoi. Un amendement **crée une
> nouvelle variante** au sens du § A.6 : un manifeste qui porte le sha256 de v2.2 n'a pas l'empreinte d'un
> manifeste qui porte celui de v2.1.
>
> **Base amendée** : `docs/protocole_c3.md` v2.1, sha256
> `9300f4e53bfd36633df6524c2d7ad168a732739ca3dd1765c024cc8a3ccd4129` (merge `b3524ac`, tag `v2.12.0-c3-v2.1`).
>
> **Sources**
> - le brief `agent/AGENT_C3_AMENDEMENT_V2_2.md` (29/09) ;
> - `PROJECT_CONTEXT.md` § 9, « Candidats amendement v2.2 » (les neuf) ;
> - `results/sol_d2_1w_modes/report.md` § 8.1 ;
> - `results/c3b_producteur/report.md` et les écarts 11, 14 et 15 de `agent/AGENT_C3B_PRODUCTEUR.md` ;
> - `results/c3_v2_2/phase1.md` : classification, inventaire, conformité C3b, et décisions de Bruno au § 10 ;
> - le GO de phase 2 du 29/09 et ses quatre corrections.
>
> Les faits lus dans le code au SHA `8689636` sont tagués **[v]**, avec leur `fichier:ligne`. Le texte du protocole
> ne nomme aucune ligne de code comme règle : il nomme des sections.

## Adoption — 2026-09-29

**Adopté par Bruno le 2026-09-29**, au gate d'amendement, sous les décisions et les réserves ci-dessous.
Application : branche `feat/c3-amendements-v2.2` depuis `dev` @ `8689636` — texte du protocole et tests
`tests/test_scripts/test_c3_*.py`, `test_c3b_*.py` ; **aucune ligne de `scripts/audit/*.py` ni de `src/`**. Deux
STOP : la lecture adverse (après le paquet, avant toute application), puis l'arrêt avant push. Le reste de ce
document est le paquet tel qu'il a été proposé, retouché et appliqué ; là où l'application s'en écarte, cette
section le dit, et c'est elle qui fait foi avec le texte du protocole.

### Empreinte du protocole

| Révision | sha256 de `docs/protocole_c3.md` | Commit |
|---|---|---|
| v2.0 (gel du 2026-09-21) | `9b62915069e59e9b0f35120c60a77f48a72b278aa9102b3096dfcb8dc25e23c2` | `d931293` |
| v2.1 (amendée le 2026-09-23) | `9300f4e53bfd36633df6524c2d7ad168a732739ca3dd1765c024cc8a3ccd4129` | `b3524ac` |
| v2.2 (ce paquet) | `1bed7696c0b0002b702f34fd549a59fc648968ff2e3056a98d33168bd643292a` | `ac7710f` (AM-00, dernier commit de texte) |

**sha256 v2.2 :** `1bed7696c0b0002b702f34fd549a59fc648968ff2e3056a98d33168bd643292a`

Un fichier ne peut pas porter sa propre empreinte (R-01 de v2.1) : le sha v2.2 est consigné ici, dans
`docs/RESEARCH_LOG.md`, `skills/backtest.md` et `CLAUDE.md` ; `c3_common.protocol_descriptor` le recalcule dans
chaque artefact, et `tests/test_scripts/test_c3_common.py` épingle la **dernière** ligne `**sha256 vX.Y :**` de cette
section au fichier. Toute retouche du protocole sans amendement daté la fait diverger. Sous v2.2, `c3_anchor` refuse
tout manifeste qui déclare v2.1 ou v2.0 : le livrable C3a (v2.0) et les artefacts de C3b (v2.1) sont historiques.

### Décisions de gate (Bruno, 2026-09-29)

**Avant rédaction** — `results/c3_v2_2/phase1.md` § 10 (treize décisions, remarque d'ordre), plus les quatre
corrections du GO de phase 2. Rappel, sans les redire : classification (C) — cas 1 à 4 en (c), cas 5 en (b) →
AM-10 ; AM-06 forme A ; motif (i) / (ii) et jumeaux ; pont `xfail` du test du sha ; numérotation (AM-01 à AM-09 sur
les candidats, AM-07 renvoi, AM-10 et suivants, R-15 et suivantes) ; clé `min_order_quote` au manifeste ; AM-05
(famille au manifeste, statut compté écrit à l'étape 6, renvoi au § 10.1) ; porteur « zéro exécution » recoupé ;
ligne § 0.7 d'AM-03 ; un adverse par réserve ; `results/INDEX.md` ; note du § F.8 dans v2.2 (AM-11) ; table
confirmée ; AM-08 en implication seule ; AM-04 borné aux positions nommées ; évaluation différée comme état du
registre ; item 13 du § J avec vecteur et borne.

**STOP de lecture adverse** — lecture adverse faite par Claude (relecteur) sur l'Avant / Après d'AM-03, AM-06 et
AM-08 rendu au STOP (paquet `82fb522`). Bruno a accepté les six constats ; ils sont appliqués au paquet par le
commit `b8b2390`, avant toute application au protocole.

| # | Objet de la retouche | Constat / réponse |
|---|---|---|
| C-1 | AM-06, § L.1 : l'identité portée par un refus est recoupée à la configuration retenue avant toute lecture du bloc `refused` ; c1-c5, `stamp_cell`, `comparator` non évalués, contrôle d'identité maintenu | accepté, retouche C-1 |
| C-2 | AM-08, § L.1 : la clause 3 d'une évaluation sans exécution est vérifiée à vide, jamais `R1_NOT_NORMALISED` | accepté, retouche C-2. Constat lu dans le code : c3 sort déjà `VERIFIED` sur `lots: []` (aucun adverse de plus en R-19). **Rédaction décidée au STOP** : « liste de lots exportée et vide » ; le mot à mot « sans lot » contredisait la ligne c3 du § B.8 (identités exactes sans lots → `NON VÉRIFIABLE`) |
| C-3 | AM-03 / AM-06 : sur une évaluation non refusée, un recalcul impossible sur l'export est une violation ; deux motifs, `comparator_not_buildable` et `comparator_not_comparable` | accepté, retouche C-3. Le § 10.1 ne compte ni code 1 ni `E_NO_BENCHMARK` : la retouche change ce que le rapport dit du producteur, pas le budget de relance |
| C-4 | AM-03, § L.2 : le comparateur d'évaluation (entrée à part) est recoupé sur le même recalcul | accepté, retouche C-4. **Rédaction décidée au STOP** : NAV du « B&H plein notionnel recalculé, dont le blend est tiré » ; le mot à mot « blend recalculé » était faux dès que λ < 1 |
| C-5 | AM-06, § L.2 : `-` est la valeur du champ « état de la continuité » en abstention aussi | accepté, retouche C-5 ; le constat de rédaction 6 est réglé. **Rédaction décidée au STOP** : « chaque fois qu'aucun état de clause n'entre dans l'issue » ; en abstention l'étape 5 évalue les clauses sans qu'elles soient rapportées |
| C-6 | AM-08 : la clé est `metrics.executions`, pas `metrics.total_trades` (homonyme d'une métrique du moteur à sens différent) | accepté, retouche C-6 |
| — | Formule de `returns_config` ; égalité des λ ; règle d'entrée de `candles_eval.json` ; § J, item 13 ; implication seule d'AM-08 ; paragraphe « Ce qu'exige `validé` » | **rien trouvé** |

Ligne Astra (brief, au mot près) :

> Re-passe Astra non faite (Astra non à jour depuis v2.0 ; réservée aux familles de stratégies). AM-3+7, AM-6 et AM-8 changent ce que la chaîne vérifie — ce sont les amendements où une lecture adverse aurait servi. À défaut, lecture adverse écrite par Claude avant adoption, consignée à la table de gate ; adoption par Bruno.

### Réserves d'application (2026-09-29)

L'outillage que v2.2 impose n'est pas écrit dans ce chantier. Chaque réserve est portée par des tests
`xfail(strict=True, raises=…)`, rouges aujourd'hui pour la raison consignée dans
`results/c3_v2_2/tests/xfail_rouge.out` ; leur levée est l'entrée du chantier outillage
(`results/c3_v2_2/outillage_v2_2.md`). L'attendu de ces tests est normatif ; leur interface d'appel est indicative.

- **R-15 (AM-03) — § L.2, § L.1 ligne 0 — bloquant manifeste.** La chaîne recalcule `returns_config` sur
  `equity_daily`, recoupe les λ déclarés à `benchmark.json`, recalcule `returns_bench` et la NAV du comparateur
  d'évaluation sur `candles_eval.json` (septième entrée) ; recalcul impossible sur une évaluation non refusée →
  violation ; le producteur déclare ses λ.
  - `xfail` (9) : `test_c3_verdict.py` — `test_R15_returns_config_ecarte_d_un_ulp…`, `test_R15_des_lambdas_declares…`,
    `test_R15_returns_bench_different…`, `test_R15_la_nav_du_comparateur…`, `test_R15_une_evaluation_non_refusee…`,
    `test_R15_un_export_d_evaluation_hors_regle_d_entree_est_refuse` (×2), `test_R15_le_parseur_chain_expose…` ;
    `test_c3b_evaluate.py` — `test_R15_evaluation_json_declares_the_prefix_lambdas_it_used`.
  - Artefacts C3b non conformes : toute évaluation (4a `evaluation_run.json` versionné, 4b `evaluation.json`
    archivé non lu) ne déclare aucun λ ; `benchmark_eval.json` ne porte pas de NAV ; `candles_eval.json` n'est pas
    une entrée de chaîne.
- **R-16 (AM-04) — § A.7 — bloquant manifeste.** Clés `min_order_quote` et `gross_quote` à l'export, à la
  lecture et au manifeste ; garde de forme sur les deux seules positions nommées.
  - `xfail` (10) : `test_c3_chronology.py` (contrats de π_T) ; `test_c3_entry.py` (`min_order_quote` absente ou
    nulle ×2, D5, `min_order_usdc` à la position, `gross_usdc` dans le bloc) ; `test_c3_anchor.py` (clé du manifeste
    ×2) ; `test_c3b_common.py` (lots et bloc `gross_quote`, observation `min_order_quote`).
  - Artefacts C3b non conformes : `prefix_conformite/server/run1/observations.json` (12 `min_order_usdc`,
    66 `gross_usdc`), `eval_conformite/server/designated/run1/evaluation_run.json` (1 `gross_usdc`), manifeste du
    lot 3 ; les 12 empreintes de projection de `selection.json` ne sont plus recalculables à l'identique (les
    identités de candidat ne changent pas).
- **R-17 (AM-05) — § A.6 — bloquant campagne.** Famille au manifeste ; statut compté écrit par `c3_verdict` à
  l'étape 6 ; refus par `c3_anchor` des variantes que le § 10.1 exclut, évaluation différée comme état du registre ;
  registre de campagne unique et persistant (conséquence d'AM-05).
  - `xfail` (5) : `test_c3_anchor.py` (manifeste sans famille, seconde campagne sur famille au verdict compté,
    relance au-delà de l'unique, empreinte autre que la différée) ; `test_c3_verdict.py` (inscription de l'issue).
  - Artefacts C3b non conformes : `prefix_conformite/manifest.json` (pas de famille), `server/chain/variants.json`
    (ni famille ni issue).
- **R-18 (AM-06) — § C.5, § L.1, § L.2 — bloquant manifeste.** Le producteur écrit la forme de refus et
  l'export ; l'admission reconnaît la forme de refus (identité d'abord) ; la continuité route sans contrat § B ; le
  verdict publie `E_NO_BENCHMARK` avec le motif, rejoue la non-constructibilité, porte `continuite=-`.
  - `xfail` (5) : `test_c3_verdict.py` (issue et motif, refus avec séries, refus démenti, identité ≠ retenue) ;
    `test_c3b_evaluate.py` (forme de refus et export écrits).
  - Artefacts C3b non conformes : aucun (aucune évaluation refusée n'a été produite).
- **R-19 (AM-08) — § L.1, § B.8 — bloquant manifeste.** Porteur `metrics.executions` exporté et exigé ;
  `first_fill_at` nul ⟺ `executions == 0` ; `executions == 0` ⟹ equity constante `= C` ; c5 non vérifiable admis
  sans exécution.
  - `xfail` (6) : `test_c3b_evaluate.py` (admission sans exécution, `metrics` avec `executions`) ;
    `test_c3_continuity.py` (réelle sans exécution → c5 non vérifiable, c3 vérifiée à vide) ; `test_c3_verdict.py`
    (aucune violation et jamais `validé`, deux contradictions).
  - Artefacts C3b non conformes : toute évaluation, qui ne porte pas `metrics.executions` (correction de
    `phase1.md` § 4, qui disait qu'AM-08 ne cassait rien : vrai de l'élargissement, faux depuis que le porteur est
    exigé).
- **R-20 (AM-09) — § A.7 — non bloquant.** Dates de couverture nulles si et seulement si aucune unité couverte.
  - `xfail` (4) : `test_c3b_common.py` (série écrite à dates nulles) ; `test_c3_entry.py` (trois combinaisons).
  - Artefacts C3b non conformes : aucun.
- **R-21 (AM-10) — § A.8 D4 — non bloquant manifeste, bloquant campagne.** Le CAGR qui déborde retire le
  candidat par D4, sans exception ; impossible sur le préfixe de 1 362 jours, possible sur une fenêtre courte.
  - `xfail` (2) : `test_c3_benchmark.py`, `test_c3_select.py` (`raises=OverflowError`).
  - Artefacts C3b non conformes : aucun.
- **R-22 (cas 1 à 4 de `phase1.md` § 1, aucun texte) — § I.1 (forme du diagnostic), § C.5, § C.6, § A.8 D4 —
  non bloquant manifeste, bloquant campagne.** Le texte prescrit déjà la forme ; l'outillage produit une trace.
  - `xfail` (4) : `test_c3_anchor.py` (cas 1), `test_c3_benchmark.py` (cas 2), `test_c3_select.py` (cas 3),
    `test_c3_verdict.py` (cas 4).
  - Artefacts C3b non conformes : aucun.

**Hors réserve** (contrat du producteur C3b, 0/2/3 — pas le protocole) : `cb.build_pair` hors du `try` à
`c3b_evaluate.py:544` ; un `xfail` (`test_c3b_evaluate.py`, `raises=OverflowError`).

**Pont** : `test_c3_common.py`, test du sha v2.1 ↔ protocole, `xfail(strict=True, raises=AssertionError)` du
premier commit de texte (`451a148`) au commit des tests du sha ; ce n'est pas une réserve.

### Écarts de rédaction et d'application

- **Texte.** Chaque bloc « Après » est appliqué tel quel, vérifié par `results/c3_v2_2/tests/texte_conforme.py`
  (espaces normalisés). Seule la mise en page diffère : AM-08 met la phrase d'admission du § L.1 et sa suite dans
  leurs propres paragraphes ; AM-02 et AM-03 (§ J, item 12) recoupent des lignes. AM-00 : la date d'adoption est
  le 2026-09-29.
- **AM-12.** L'index réel diffère de la prévision du paquet : `E_NO_BENCHMARK` ne gagne que § J (la retouche C-3
  l'a retiré du § L.2), `D4` ne change pas, `P2` gagne § F.8 (AM-11) et `R1_NOT_NORMALISED` gagne § L.1 (C-2).
  C'est la sortie du script, validé sur l'index v2.1, qui fait foi (`index_m.sh`).
- **Tests.**
  - Scission des miroirs en jumeaux `xfail` : les assertions que v2.2 contredit passent dans un jumeau, le reste
    reste vert.
  - Miroirs non relevés par `phase1.md` § 2, trouvés à l'application : jeux de clés de `evaluation.json`
    (`test_c3b_evaluate.py`, triplet exact de `metrics` et interdit « aucune clé `lambda` ») ; jeu de clés de
    l'observation contre le résultat P7 (`test_c3b_common.py`) ; lots `gross_usdc` du même fichier.
  - Le cas de forme `test_c3_entry.py` « lot sans amount » reste vert en (i), comme prévu.
  - Les adverses de chaîne R-18 rougissent aujourd'hui sur l'option `--candles-eval` que la chaîne ne connaît pas
    encore (septième entrée) ; leur attendu porte la règle.
  - AM-10 (R-21) est testé au niveau des fonctions, à durée de préfixe réduite : le débordement n'existe pas sur
    le préfixe des fixtures.
  - R-22 et l'item hors réserve sont dans un commit `test` à part (`5600eaf`), sans texte.
  - Le pont est levé au commit des tests du sha, et non au commit AM-00 : à AM-00, le test lit encore le paquet
    v2.1 et la ligne de sha v2.2 n'existe pas.
- **Vérification par mutation.** Le témoin « suffixe hors positions ni lu ni refusé » (AM-04) rougit sous un
  mutant de garde non bornée et reverdit après restauration (`mutants.log`).

## Décisions qui fondent ce paquet (Bruno, 29/09)

Leur détail est au § 10 de `results/c3_v2_2/phase1.md`, et le paquet ne les redit pas. Les quatre corrections
du GO de phase 2 s'y ajoutent :

- **AM-08 énonce une implication, pas une équivalence.**
- **AM-04 borne le contrat de forme aux positions qu'il nomme.**
- **AM-05 fait de l'évaluation différée un état du registre.**
- **AM-06 nomme le vecteur de relance par omission et ce qui le borne.**

## Table de correspondance candidat → amendement

| # | Candidat (`PROJECT_CONTEXT.md` § 9, `phase1.md`) | Amendement |
|---|---|---|
| 1 | § A.8 l.515 : `grid_levels`, axe de `decision_timeframes` | AM-01 |
| 2 | § A.8 l.605-606 : « lisent le 1 w » → « alimente une porte de décision » | AM-02 |
| 3 | Recoupement `returns_config ← equity_daily` côté chaîne (ex-S-3) | AM-03 |
| 4 | S-1 : `min_order_usdc`, `gross_usdc` | AM-04 |
| 5 | Application du § 10.1 au registre de variantes | AM-05 |
| 6 | E5 : `E_NO_BENCHMARK` inatteignable sur un comparateur non constructible | AM-06 |
| 7 | E11 : la chaîne ne recoupe ni λ ni `returns_bench` | AM-03 (AM-07 : renvoi) |
| 8 | `first_fill_at` nul refusé en R0 | AM-08 |
| 9 | Dates de couverture indéfinies quand `covered_units == 0` | AM-09 |
| C | Cinq sorties code 1 hors table § I.1 (`phase1.md` § 1) | Cas 1 à 4 : aucun texte, l'outillage seul est en défaut (R-22). Cas 5 : AM-10 |
| — | Note postérieure au gel de v2.1 (§ F.8, `fsum` contre `numpy`) | AM-11 |
| — | Index des symboles | AM-12 |
| — | En-tête et empreinte | AM-00 |

## Convention de ce paquet

Chaque amendement porte six rubriques :
- la clause visée ;
- le texte **avant**, cité ;
- le texte **après** ;
- le **motif** ;
- l'**impact outillage** : fichiers, comportement à changer, et la réserve qui le porte ;
- le **test attendu**.

Aucun amendement ne change de comportement dans ce chantier : `scripts/audit/*.py` et `src/` sont intouchés.
L'outillage que le texte impose est porté par les réserves R-15 à R-22 et par des tests
`xfail(strict=True, raises=…, reason="R-xx …")`. L'attendu de ces tests est normatif et se dérive du texte ;
leur interface d'appel est indicative, et le chantier outillage peut la compléter sans toucher à l'attendu.

Les numéros de ligne de la table du § I.1 ne sont jamais renumérotés, et **ce paquet n'y ajoute aucune ligne**.
Les réserves continuent la numérotation de v2.1 (R-01 à R-14), pour qu'aucun `xfail` ne soit ambigu.

---

## AM-00 — En-tête : bloc d'amendements v2.2

**Clause.** L'en-tête du document (encart « Révision v2.1 » et « Statut : GELÉ ») et les sections
« Amendements ».

**Avant.** L'encart s'ouvre sur « **Révision v2.1 — amendée le 2026-09-23.** […] » ; la première section est
« Amendements — v2.1 ».

**Après.** L'encart reçoit en tête un paragraphe ; celui de v2.1 est conservé tel quel à sa suite :

> **Révision v2.2 — amendée le <date d'adoption>.** Douze amendements datés (AM-00 à AM-12 ; AM-07 est fusionné
> dans AM-03), `docs/amendements_c3_v2.2.md`, adoptés par Bruno au gate d'amendement après lecture adverse
> (Claude). Les décisions de gate et les réserves d'application (R-15 à R-22) sont consignées dans la section
> « Adoption » de ce paquet. **Nouveau sha256 : consigné hors du fichier.** Le sha256 de v2.1,
> `9300f4e53bfd36633df6524c2d7ad168a732739ca3dd1765c024cc8a3ccd4129`, reste celui que portent les artefacts
> de C3b ; un manifeste v2.2 est une nouvelle variante (§ A.6).

Une section « **Amendements — v2.2** » précède celle de v2.1. Elle contient la table de correspondance
ci-dessus et renvoie à ce paquet pour les textes (§ 0.7).

**Motif.** Un amendement doit être daté et lisible depuis le document lui-même (précédent : AM-00 de v2.1).

**Impact outillage.** Aucun. `cc.protocol_descriptor` **[v]** `scripts/audit/c3_common.py:999-1004` recalcule le
sha du fichier dans chaque artefact. `c3_anchor` **[v]** `scripts/audit/c3_anchor.py:103-108` refusera sous v2.2
tout manifeste qui déclare v2.1, donc le manifeste du lot 3 de C3b, comme il refuse sous v2.1 le livrable C3a.

**Test attendu.**
- `test_c3_common.py:552` rougit dès le premier commit de texte. Il est tenu par un **pont**
  `xfail(strict=True, raises=AssertionError, reason="en attente de l'empreinte v2.2 (AM-00, section Adoption)")`,
  levé après la section « Adoption ».
- Ce test, puis `:562`, sont ensuite **généralisés** :
  - `ADOPTED_PACKAGE` pointe sur ce paquet ;
  - la lecture porte sur la **dernière** ligne `**sha256 vX.Y :**` ;
  - le compte des empreintes de la table passe à trois ;
  - l'épinglage de la ligne au fichier reste celui d'avant.
- Témoins inchangés : `test_c3_entry.py:709` et `test_c3_verdict.py:2501`. Le livrable C3a reste refusé.

**Statut proposé.** À adopter, en dernier : le sha se calcule après tous les autres amendements.

---

## AM-01 — § A.8, D2 : `grid_levels` est un axe de la liste de décision

**Clause.** § A.8, paragraphe « La liste des timeframes de décision est dérivée, jamais déclarée », parenthèse
illustrative.

**Avant.**

> (pour la famille grid : `bear_protection_mode` et `bias_1d` décident si `regime_1d` et la porte 1 w
> vivent)

**Après.**

> (pour la famille grid : `bear_protection_mode`, `grid_levels` et `bias_1d` décident si `regime_1d` et la
> porte 1 w vivent)

**Motif.** `regime_1d` décide si et seulement si `_get_directional_bias` n'est pas constante sur le domaine de
`get_regime`. Cela dépend de `(grid_levels, bias_1d)`, et `bias_1d ≠ 0` n'est ni suffisant ni nécessaire
(`results/sol_d2_1w_modes/report.md` § 3.2, § 8.1-1). La règle normative que la parenthèse illustre tient ; seule
l'illustration était incomplète.

**Impact outillage.** Aucun. La classmethod prend déjà `grid_levels` **[v]**
`src/krakenbot/strategies/grok_grid_atr_adaptive_v4.py:226` (C3b, lot 1).

**Test attendu.** Aucun nouveau. Témoin : `tests/test_strategies/test_grid_v4_decision_timeframes.py` (60 tests,
dont les témoins G = 1 et G = 13).

**Statut proposé.** À adopter.

---

## AM-02 — § A.8 : « alimente une porte de décision », dans la note SOL de la fenêtre v2.1

**Clause.** § A.8, encart « Conséquences de D2 et de D1 sur la fenêtre de v2.1 », puce « D2 sur SOL ».

**Avant.**

> D2 retire donc tout candidat SOL dont une porte de décision lit le 1 w : **SOL est partiel dans la première
> campagne, ou absent** si tous les modes de la famille lisent le 1 w.

**Après.**

> D2 retire donc tout candidat SOL dont le 1 w alimente une porte de décision : **SOL est partiel dans la
> première campagne, ou absent** si le 1 w alimente une porte de décision dans tous les modes de la famille.

**Motif.** Le code lit le 1 w dans **tous** les modes **[v]** `scripts/backtest.py:383`, sans condition, mais ne le
fait décider que là où la porte de pause vit **[v]** `:384` (`results/sol_d2_1w_modes/report.md` § 8.1-2). Le
critère de D2 est « alimente une porte de décision » (§ A.8, table, ligne D2) : la note doit porter le même
critère, pas un autre.

**Impact outillage.** Aucun.

**Test attendu.** Aucun nouveau. Témoin : `tests/test_scripts/test_warmup_at.py` (classes C1-C6).

**Statut proposé.** À adopter.

---

## AM-03 — § L.2 : ce que le producteur garantit, la chaîne le recalcule (candidats 3 et 7)

**Clause.**
- § L.2 : un nouveau paragraphe et une table, section d'origine.
- Renvois : § L.1 (ligne 0) ; § F.2 (d), alinéa « Qui calcule » ; § J, item 12 ; § 0.7, table de renvoi.

**Avant (§ L.2).** La section définit la chaîne, son préfixe, `chain.verified` et les enveloppes amont. Elle ne dit
rien des valeurs que le producteur garantit par construction.

**Après (§ L.2)** — un paragraphe ajouté après « Les enveloppes amont disent ce qu'elles ont fait […] » :

> **Ce que le producteur garantit, la chaîne le recalcule.** *C'est la section d'origine de ces recoupements
> (§ 0.7).* Trois valeurs de l'artefact d'évaluation sont garanties par construction chez le producteur
> (§ F.2 d). La chaîne ne les tient pas pour acquises : à l'étape de verdict (§ L.1, pas 6), elle recalcule
> chacune depuis un **lieu de lecture** nommé, et **toute discordance est une violation** (§ I.1, ligne 15 : une
> valeur que le rejeu ne retrouve pas). La comparaison est une égalité au bit, dans l'ordre de la grille
> quotidienne.
>
> | Valeur que l'évaluation déclare | Lieu de lecture | Recalcul |
> |---|---|---|
> | `returns_config`, les rendements quotidiens de la configuration | `equity_daily`, dans l'artefact d'évaluation lui-même | `r_t = E_t / E_{t−1} − 1`, en double précision, sur les valeurs exportées, dans l'ordre de la grille ; un point précédé d'une valeur `≤ 0` ne porte pas de rendement |
> | les deux `λ` que l'évaluation déclare avoir utilisés | `benchmark.json`, produit à l'étape 3 de la même chaîne pour la configuration évaluée | égalité exacte avec les `λ_dd` et `λ_σ` que l'étape 3 a publiés (§ C.4, § F.2 f) |
> | `returns_bench`, les rendements du comparateur, par appariement | l'**export de bougies d'évaluation** `candles_eval.json`, entrée hors chaîne (§ L.1, ligne 0) | B&H plein notionnel sur `[T, fin]` sous la convention du § C.3 ; blend statique du § C.4 aux `λ` publiés par l'étape 3 ; NAV du blend calculée en décimal, marquée sur la grille quotidienne, passée en double précision ; rendements par la formule de la première ligne |
>
> Le comparateur d'évaluation (§ C.5, entrée à part) est recoupé sur ce même recalcul : sa NAV sur la grille
> quotidienne, passée en double, est égale au bit à celle du B&H plein notionnel recalculé, dont le blend est
> tiré ; une discordance est une violation. Les cinq tests du § C.5 portent donc sur l'objet même dont
> `returns_bench` est tiré.
>
> **L'export de bougies d'évaluation** porte une seule paire, celle de la configuration évaluée, et aucune
> estampille postérieure à la fin de la fenêtre d'évaluation. Sinon c'est une erreur d'entrée (§ I.1, ligne 2),
> jamais tronquée, pour la raison qu'en donne le § A.7, règle 2.
>
> Sur une évaluation **non refusée**, un recalcul impossible sur l'export est une **violation** (§ I.1,
> ligne 15) : le producteur a déclaré un comparateur que l'entrée ne permet pas de retrouver. Le seul
> comparateur non constructible légitime est celui de la forme de refus (§ C.5).
>
> **Ce que ces recoupements ne prouvent pas.** Ils établissent que les séries déclarées sont celles
> qu'impliquent `equity_daily`, l'export de bougies et les `λ` de l'étape 3. Ils ne prouvent pas que
> `equity_daily` soit la trajectoire du moteur, ni que l'export soit fidèle à la base : ces deux entrées restent
> déclaratives (§ J, items 12 et 13).

**Avant (§ L.1, ligne 0).**

> | 0 | **hors chaîne** | six entrées, produites avant, jamais par l'outillage de ce protocole : le **manifeste** (§ A.6), les **observations**, l'**artefact de couverture** (§ A.7), l'**export de bougies** `candles.json` (lecture seule de la base), que `c3_benchmark` lit pour construire le comparateur du préfixe (§ C), l'**artefact d'évaluation** (§ F.2, produit par C3b) et le **comparateur d'évaluation** (§ C.5) |

**Après (§ L.1, ligne 0).**

> | 0 | **hors chaîne** | sept entrées, produites avant, jamais par l'outillage de ce protocole : le **manifeste** (§ A.6), les **observations**, l'**artefact de couverture** (§ A.7), l'**export de bougies** `candles.json` (lecture seule de la base), que `c3_benchmark` lit pour construire le comparateur du préfixe (§ C), l'**artefact d'évaluation** (§ F.2, produit par C3b), le **comparateur d'évaluation** (§ C.5) et l'**export de bougies d'évaluation** `candles_eval.json` (lecture seule de la base), sur lequel la chaîne recoupe le comparateur d'évaluation (§ L.2) |

**Avant (§ F.2 d, fin de l'alinéa « Qui calcule »).**

> **Ce qui reste déclaratif** : les séries quotidiennes elles-mêmes et `net_pnl` (porte `Q1`), qu'aucune série de
> l'artefact ne permet de recalculer (§ J, item 12).

**Après (§ F.2 d).**

> **Ce qui reste déclaratif** : `equity_daily`, l'export de bougies d'évaluation et `net_pnl` (porte `Q1`), qu'aucune
> série de l'artefact ne permet de recalculer (§ J, item 12). Les séries de rendements, elles, sont recoupées sur
> ces entrées (§ L.2).

**Avant (§ J, item 12, première phrase).**

> 12. **Ce que le rejeu du § F.2 ne couvre pas** (§ F.2 b, d). → La chaîne rejoue le tirage et **recalcule** les
> suites, les écartées, `Δ̂`, le `CAGR` et les bornes ; ce qu'elle ne peut pas recalculer reste **déclaratif** :
> les séries quotidiennes elles-mêmes, et `net_pnl` (porte `Q1`), qu'aucune série de l'artefact ne permet de
> reconstruire.

**Après (§ J, item 12, première phrase ; la suite de l'item est inchangée).**

> 12. **Ce que le rejeu du § F.2 ne couvre pas** (§ F.2 b, d). → La chaîne rejoue le tirage et **recalcule** les
> suites, les écartées, `Δ̂`, le `CAGR` et les bornes, et elle recoupe les séries de rendements sur leurs lieux
> de lecture (§ L.2). Ce qu'elle ne peut pas recalculer reste **déclaratif** : `equity_daily` et l'export de
> bougies d'évaluation, sur lesquels ces recoupements s'appuient, et `net_pnl` (porte `Q1`), qu'aucune série de
> l'artefact ne permet de reconstruire.

**Après (§ 0.7, table de renvoi : une ligne ajoutée à la fin).**

> | Recoupements, par la chaîne, de ce que le producteur garantit | **§ L.2** | renvoi |

**Motif.**
- **Candidat 3 (ex-S-3).** `returns_config = cc.recompute_daily(equity_daily.values, days).returns` **[v]**
  `scripts/audit/c3b_evaluate.py:614-615`. L'égalité n'est garantie que par construction côté producteur.
- **Candidat 7 (E11).**
  - `evaluation.json` ne porte aucun `λ`. Seul `evaluation_sensitivity.json` les porte **[v]**
    `c3b_evaluate.py:748`, et la chaîne ne le lit pas.
  - `c3_verdict` ne lit pas `benchmark.json` **[v]** `c3_verdict.py:111` (`INPUT_NAMES`).
  - Aucun module `c3_*` ne lit `candles_eval.json`.
  - « λ du préfixe tenu fixe » (§ F.2 f) n'est donc garanti que côté producteur.
- **Conséquence.** Les recoupements du § F.2 (d) partent de séries que personne ne recoupe. Un producteur fautif
  sur l'une des trois valeurs passerait le rejeu au bit.

**Impact outillage — R-15, bloquant manifeste.**
- **`c3_verdict`.**
  - Recalculer `returns_config` sur `evaluation.equity_daily`, par la formule du texte. C'est celle de
    `cc.recompute_daily` **[v]** `c3_common.py:1612-1623`, et le producteur l'emploie.
  - Lire `benchmark.json` (entrée nouvelle du verdict ; `verify_chain` **[v]** `c3_verdict.py:940` doit en
    recouper l'empreinte).
  - Lire `candles_eval.json`, sur la seule paire évaluée, comme le producteur **[v]** `c3b_evaluate.py:540`
    (`cb.load_candles` sur un manifeste réduit au candidat, qui refuse déjà une estampille postérieure à `fin`,
    **[v]** `c3_benchmark.py:91-95`).
  - Reconstruire le comparateur par `cb.build_pair` **[v]** `c3_benchmark.py:173` et `cb.blend_nav` **[v]**
    `:289`, puis comparer au bit. Le parseur `chain` expose `--candles-eval`.
- **Frontière (retouche C-3).** Sur une évaluation non refusée, un recalcul impossible est une violation ; la liste
  close des motifs du § C.5 n'en a que deux.
- **Comparateur d'évaluation (retouche C-4).** `benchmark_eval.json` porte aujourd'hui les seuls tests et la fenêtre
  **[v]** `c3b_evaluate.py:576-581` : il doit exporter la NAV du B&H sur la grille quotidienne, et la chaîne la
  compare au bit au B&H recalculé.
- **Producteur (`c3b_evaluate`).**
  - Déclarer les `λ` utilisés dans `evaluation.json`. La règle du brief C3b « λ … jamais dans
    `evaluation.json` » **[v]** `agent/AGENT_C3B_PRODUCTEUR.md:427` est levée pour les `λ` du préfixe ; la
    sensibilité à `λ` ré-estimé reste hors de l'artefact.
  - `candles_eval.json` est déjà écrit.
- **Fixtures** : `fx.evaluation` porte les `λ` déclarés.

**Test attendu — R-15** (`xfail` strict, attendu tiré de ce texte).
- **Chaîne.** Chacune de ces entrées donne une violation, code 1 :
  - `returns_config` écarté d'un ulp du recalcul sur `equity_daily` ;
  - `λ` déclarés différents de ceux de `benchmark.json` ;
  - `returns_bench` différent du recalcul sur `candles_eval.json`.
- **Entrée.** `candles_eval.json` portant une estampille postérieure à `fin`, ou une seconde paire → refus,
  code 2.
- **Comparateur (C-4).** NAV du comparateur d'évaluation ≠ NAV du B&H recalculé → violation.
- **Frontière (C-3).** Évaluation non refusée dont l'export n'a pas l'estampille d'entrée → violation, et non
  `E_NO_BENCHMARK`.
- **Parseur.** Le parseur `chain` expose `candles_eval` : jumeau de `test_c3_verdict.py:2551`.
- **Producteur.** `evaluation.json` déclare les `λ` du préfixe, et aucune clé de sensibilité : jumeaux de
  `test_c3b_evaluate.py:1023-1036` et `:1827-1848`, dont l'interdit « aucune clé `lambda` » est contredit par ce
  texte.

**Statut proposé.** À adopter.

---

## AM-04 — § A.7 : les montants en monnaie de cotation sont suffixés `_quote`, aux positions nommées (S-1)

**Clause.** § A.7, table de la liste blanche : lignes « Contrats » et « Comptabilité ».

**Avant.**

> | Contrats | `metrics_version`, `replay_version`, `exchange`, `fees`, `pair_costs`, `pair_costs_file`, `min_order_usdc` |

> | Comptabilité | `liquidation[<préfixe>]`, entier. **Contrat de forme des quantités en actif de base** : les clés `amount_base`, `residual_trade_base`, `dust_written_off_base`, `inventory_divergence_base`, dans le bloc et dans chaque lot, **quelle que soit la paire** ; un bloc qui porte une clé suffixée par le nom d'un actif (`_btc`, `_eth`, …) est une erreur de forme (§ I.1, ligne 2). Le renommage vit dans la couche d'export du runner ; le moteur `scripts/backtest.py` est intouché |

**Après.**

> | Contrats | `metrics_version`, `replay_version`, `exchange`, `fees`, `pair_costs`, `pair_costs_file`, `min_order_quote`. **Contrat de forme du plancher d'ordre** : il s'exprime en unités de la monnaie de cotation de la paire (§ 0.5), et sa clé est `min_order_quote` **quelle que soit la paire** ; à cette position, une clé `min_order_` suffixée par le nom d'une monnaie (`min_order_usdc`, `min_order_usdt`, …) est une erreur de forme (§ I.1, ligne 2) |

> | Comptabilité | `liquidation[<préfixe>]`, entier. **Contrat de forme des quantités en actif de base** : les clés `amount_base`, `residual_trade_base`, `dust_written_off_base`, `inventory_divergence_base`, dans le bloc et dans chaque lot, **quelle que soit la paire** ; un bloc qui porte une clé suffixée par le nom d'un actif (`_btc`, `_eth`, …) est une erreur de forme (§ I.1, ligne 2). **Contrat de forme des montants en monnaie de cotation** : la clé `gross_quote`, dans le bloc et dans chaque lot, **quelle que soit la paire** ; un bloc ou un lot qui porte une clé `gross_` suffixée par le nom d'une monnaie (`gross_usdc`, `gross_usdt`, …) est une erreur de forme (§ I.1, ligne 2). **Ces contrats de forme ne valent qu'aux positions qu'ils nomment** : ailleurs, un suffixe d'actif ou de monnaie n'est ni lu ni refusé (règle 1 ci-dessous). Le renommage vit dans la couche d'export du runner ; le moteur `scripts/backtest.py`, et son argument `min_order_usdc`, sont intouchés |

**Motif.**
- S-1 (revue du 23/09) : `min_order_usdc` et `gross_usdc` nomment l'USDC, alors que les paires de validation
  de la première campagne sont en USDT (§ A.6, transposition déclarée). C'est la même classe de défaut que les
  clés `_btc` (AM-06 de v2.1) : un nom qui ment sur la paire qu'il décrit.
- Le contrat est **borné aux positions nommées**, comme AM-06 de v2.1 l'a fait pour `_base`. Un contrat non
  borné refuserait tout artefact de runner qui porte un suffixe de monnaie hors liste blanche, que la règle 1
  écarte pourtant sans le lire.

**Impact outillage — R-16, bloquant manifeste.**
- **Export du producteur** :
  - `c3b_common.lots_from_trades` **[v]** `c3b_common.py:345`, qui écrit `gross_usdc` ;
  - `liquidation_block` **[v]** `:354-382`, avec la table de renommage **[v]** `:69-73` (qui ne porte que les
    trois `_btc`) et la garde des restes **[v]** `:368` (qui ne voit que `_btc`) ;
  - `observation_entry` **[v]** `:415`.
- **Lecture de la chaîne** :
  - `PREFIX_WHITELIST_CONTRACTS` **[v]** `c3_common.py:1525` ;
  - `liquidation_identities` **[v]** `:1943`, `:2038`, `:2078` ;
  - `c3_entry` **[v]** `:155`, `:175`, `:264`, `:318-320` ;
  - `c3_select` **[v]** `:231-233`.
- **Garde** : une garde de forme symétrique de `check_base_quantity_keys` **[v]** `c3_common.py:1881-1891`, sur
  les deux seules positions nommées.
- **Manifeste** : la clé du manifeste devient `min_order_quote` (décision du 29/09) ; lecture **[v]**
  `c3_common.py:1316`.
- **Moteur** : l'argument du moteur ne bouge pas **[v]** `c3b_common.py:314`.
- **Fixtures** : renommées avec le code.

**Test attendu — R-16.**
- Jumeaux `xfail` de :
  - `test_c3_chronology.py:287`, contrats de π_T ;
  - `test_c3_entry.py:244`, chemin obligatoire, en élément marqué de `MANDATORY` ;
  - `test_c3_entry.py:446`, D5 ;
  - `test_c3_anchor.py:273`, clé du manifeste ;
  - `test_c3b_common.py:751`, clé du lot.
- Neuf : un bloc de liquidation qui porte `gross_usdc` est refusé (code 2), et le message nomme `gross_quote`.
- Le classement (i) / (ii) de chaque miroir est **vérifié à l'exécution**. Par exemple, le cas de forme
  `test_c3_entry.py:310` reste vert : un lot sans clé `gross_*` est refusé dans les deux versions.

**Statut proposé.** À adopter.

---

## AM-05 — § A.6 : le registre tient l'état du critère d'arrêt, l'ancrage l'applique

**Clause.**
- § A.6 : la liste minimale du manifeste, et un point ajouté en fin de liste.
- Renvois : § L.1, ligne 6 ; § K.1.

**Avant (§ A.6, liste minimale).**

> - Le manifeste porte donc, **au minimum et sans exception** : la fenêtre et `F` ; l'univers et sa provenance ;
>   **la source de données et l'intervalle de bougies** ; […]

**Après (§ A.6, liste minimale).**

> - Le manifeste porte donc, **au minimum et sans exception** : la fenêtre et `F` ; l'univers et sa provenance ;
>   **la famille** du mécanisme évalué, au sens du critère d'arrêt (`docs/CONTRAINTES_POST_B4.md` § 10.1) ;
>   **la source de données et l'intervalle de bougies** ; […] *(la suite est inchangée)*

**Après (§ A.6)** — un point ajouté après « Le registre est le pendant machine de `docs/RESEARCH_LOG.md` […] » :

> - **Le registre tient l'état du critère d'arrêt, et l'ancrage l'applique.** Le critère d'arrêt a sa section
>   d'origine hors de ce document (`docs/CONTRAINTES_POST_B4.md` § 10.1), où il n'est pas redit ; ce point en
>   donne l'application mécanique.
>   - **À l'étape 6** (§ L.1), le verdict inscrit dans l'enregistrement de sa variante l'issue, la raison, et le
>     statut *compté* ou *non compté* que le § 10.1 leur attribue.
>   - Quand l'issue ouvre la voie de sortie prospective du § 10.1, il y inscrit aussi, au moment du verdict, la
>     **date déclarée** et l'**empreinte attendue** `sig(canon(manifeste))` du manifeste de l'évaluation
>     différée.
>   - **À l'étape 1**, l'ancrage lit les enregistrements de la famille que le manifeste déclare. Il refuse
>     (`R0_INVALID_RUN`, code 2, § I.1, ligne 2) toute variante que le § 10.1 exclut : une seconde campagne sur
>     une famille qui porte déjà un verdict compté, ou une relance au-delà de l'unique.
>   - Sur une telle famille, **seule est acceptée** la variante dont l'empreinte est l'empreinte attendue inscrite
>     au verdict. L'évaluation différée est un état du registre, pas une exception de lecture.
>   - L'issue publiée et le statut compté ne sont tenus qu'à un endroit.

**Avant (§ L.1, ligne 6).**

> | 6 | `c3_verdict` | l'issue et **la chaîne de verdict** |

**Après (§ L.1, ligne 6).**

> | 6 | `c3_verdict` | l'issue et **la chaîne de verdict** ; l'issue et son statut au critère d'arrêt, inscrits à l'enregistrement de la variante (§ A.6) |

**Avant (§ K.1).**

> […] et **ne le contient pas** : le critère reste une règle de gestion, avec son auteur, hors des § 0 à M.

**Après (§ K.1).**

> […] et **ne le contient pas** : le critère reste une règle de gestion, avec son auteur, hors des § 0 à M ; son
> application mécanique au registre de variantes est au § A.6.

**Motif.**
- Le § 10.1 est une règle normative, sans texte au protocole. AM-23 de v2.1 l'avait consigné : « le registre de
  variantes (§ A.6) pourrait refuser l'enregistrement d'une seconde campagne comptée sur une famille close ».
- Aujourd'hui le registre ne connaît ni la famille ni l'issue **[v]** `c3_anchor.py:57-68` (`RECORD_KEYS`), et il
  n'est écrit qu'à l'étape 1 **[v]** `:334-335`. L'issue publiée et le compteur de famille seraient donc tenus à
  deux endroits, dont un à la main.
- L'évaluation différée doit être un état du registre (correction 3 du GO du 29/09). Sans cela, « elle n'est pas
  une seconde campagne » est une phrase que le code ne peut pas appliquer.
- Le § K.1 reste exact : le protocole ne contient pas le critère, il y renvoie (même forme qu'AM-23).

**Impact outillage — R-17, bloquant campagne.** L'outillage doit exister avant la première campagne comptée.
- **Manifeste** : un champ de famille, obligatoire, ajouté à `load_manifest` **[v]** `c3_common.py:1276`.
- **Enregistrement** : il gagne l'issue, la raison, le statut compté et, le cas échéant, la date et l'empreinte
  attendue.
  - Ces champs sont hors `RECORD_KEYS`, pour que l'idempotence de l'ancrage **[v]** `c3_anchor.py:161-172`
    tienne.
  - Ils sont écrits une fois. Une réécriture différente est une violation.
- **`c3_verdict`** écrit le registre à l'étape 6. Le parseur `chain` porte déjà `--registry`.
- **`c3_anchor`** refuse une variante exclue.
- **La table du § 10.1**, attribution des statuts compté et non compté, est recopiée par un test et épinglée à la
  constante du code (règle 3).
- **Le registre de campagne est unique et persistant.**
  - Aujourd'hui, `c3_anchor` refuse une seconde racine dans un registre non vide **[v]** `c3_anchor.py:174-180`,
    et C3b a tenu un registre neuf par run (écart 12).
  - Une première campagne d'une autre famille déclarera donc un parent (§ A.6 : « toute empreinte différente
    […] doit déclarer son parent ») : c'est dit ici, sans changement de texte.

**Test attendu — R-17.**
- **Ancrage.** Chacun de ces cas est refusé en code 2 :
  - manifeste sans famille ;
  - famille qui porte un verdict compté : une variante enfant de même famille est refusée, R0 ;
  - relance déjà consommée (deux verdicts non comptés) : une nouvelle variante est refusée ;
  - famille close avec évaluation différée inscrite : une variante d'une **autre** empreinte est refusée.
- **Chaîne.** Après `chain`, l'enregistrement de la variante porte l'issue, la raison et le statut.
- Le témoin « empreinte attendue acceptée » n'est écrit que vérifié par mutation.

**Statut proposé.** À adopter.

---

## AM-06 — § C.5 : le refus amont d'un comparateur non constructible est ratifié, lu et recoupé par la chaîne

**Clause.**
- § C.5 : deux paragraphes ajoutés, section d'origine de cette route.
- § L.1 : un paragraphe ajouté, route d'admission.
- § L.2 : un paragraphe ajouté, champ « état de la continuité ».
- § J : item 13 ajouté.

**Avant (§ C.5).** La section se termine par le paragraphe « **Le producteur déclare, la chaîne recoupe.** […] Un
`window_ok` déclaré qui contredit le recoupement est, lui, une violation (§ B.8, résumés dérivés). » Elle ne dit pas
ce qui arrive quand le producteur ne peut pas **construire** le comparateur d'évaluation.

**Après (§ C.5)** — deux paragraphes ajoutés à la fin de la section :

> **Comparateur d'évaluation non constructible : le refus amont est ratifié, et lu par la chaîne.** *C'est la
> section d'origine de cette route (§ 0.7).*
> - **Le producteur.** Quand il ne peut pas construire le comparateur d'évaluation — estampille d'exécution
>   d'entrée ou de sortie absente, et aucune bougie de substitution (§ C.3) —, le producteur n'exécute pas
>   l'évaluation. Il écrit l'artefact d'évaluation sous sa **forme de refus** : l'identité de la configuration,
>   la fenêtre `[T, fin]`, et un bloc `refused` qui porte la raison `comparator_not_buildable` et un motif,
>   **sans aucune série**.
> - **La chaîne.** Elle lit cette forme (§ L.1) et publie `inconclusif (E_NO_BENCHMARK)`, code 0 (§ I.1,
>   ligne 10).
> - **Le refus est recoupé.** La chaîne ne le croit pas : elle **rejoue la non-constructibilité** sur l'export de
>   bougies d'évaluation (§ L.2), et un refus que l'export dément est une violation (§ I.1, ligne 15).
> - **Deux formes interdites.** Un artefact d'évaluation qui porte à la fois un bloc `refused` et des séries se
>   contredit : c'est une violation. Un artefact qui ne porte ni l'un ni les autres est une erreur de forme
>   (§ I.1, ligne 2).
>
> **Le motif est un champ de l'issue, pas une raison.** `E_NO_BENCHMARK` couvre plusieurs constats, et l'artefact
> de verdict porte, à côté de la raison, un motif pris dans une liste close :
> - `comparator_not_buildable` : le refus amont ci-dessus ;
> - `comparator_not_comparable` : un test du tableau ci-dessus en échec, nommé à côté.
>
> La liste des raisons du § H.1 ne change pas.

**Avant (§ L.1)** — le paragraphe d'admission se termine par : « […] Une évaluation synthétique reste admise, préfixe
`C3_SYNTH_` et ligne de portée en tête (§ L.2). `validé` et `réfuté` deviennent atteignables sur données réelles
**par ce chemin et par aucun autre**. »

**Après (§ L.1)** — un paragraphe ajouté à la suite :

> **Forme de refus de l'artefact d'évaluation (§ C.5).**
> - **Admission.** Un artefact d'évaluation sous forme de refus (bloc `refused`, aucune série) est admis sans les
>   porteurs ci-dessus, qu'il soit déclaré réel ou synthétique. Aucune exécution n'a eu lieu : il n'y a rien à
>   prouver de son départ ni de son premier remplissage.
> - **Identité d'abord.** L'identité de la configuration portée par le refus est recoupée à la configuration
>   retenue **avant** toute lecture du bloc `refused` ; une discordance est un refus `R0_INVALID_RUN` (§ B.8,
>   table des actions, première ligne).
> - **Sa route.** L'étape 5 n'évalue aucune clause du § B, et les clauses c1-c5 et les blocs `stamp_cell` et
>   `comparator` ne sont pas évalués sur cette route ; le contrôle d'identité, lui, s'applique. Le comparateur
>   d'évaluation n'est pas exigé ; l'export de bougies d'évaluation l'est (§ L.2).
> - **Son issue.** L'étape 6 publie l'issue du § C.5, et la raison portée est la première que la liste du § H.1
>   donne parmi les constats de la chaîne.

**Avant (§ L.2).** « Elle porte au minimum l'issue, la raison, l'identité canonique retenue ou `-`, le statut de
sélection, l'état de la continuité, l'identité de variante, la provenance de l'univers, le sha256 de ce document,
et celui des observations. »

**Après (§ L.2)** — un paragraphe ajouté après le premier :

> **L'état de la continuité** est l'agrégat des clauses du § B.8. Sur la route du refus amont (§ C.5, § L.1),
> aucune clause n'est évaluée : ce champ est **sans objet**, et la chaîne porte `-`. C'est une valeur du champ
> de chaîne, pas un état de clause : la liste close du § B.8 ne change pas. `-` est la valeur de ce champ chaque
> fois qu'aucun état de clause n'entre dans l'issue : refus amont, où aucune clause n'est évaluée, et
> abstention (§ A.11), où elles sont lues et recoupées sans être rapportées.

**Après (§ J)** — item ajouté après l'item 12 :

> 13. **L'omission d'une bougie dans l'export d'évaluation** (§ C.5, § L.2).
>     - **Le vecteur.** Un export qui omet la bougie d'exécution d'entrée ou de sortie rend le comparateur non
>       constructible. Le producteur refuse, et la chaîne, qui rejoue le refus sur ce même export, le confirme.
>       L'issue `E_NO_BENCHMARK` n'est pas comptée pour la famille et ouvre la relance
>       (`docs/CONTRAINTES_POST_B4.md` § 10.1). C'est une relance obtenue par omission. La chaîne ne peut pas la
>       distinguer d'une absence réelle, puisqu'elle ne lit pas la base (§ L.4).
>     - **La borne.** Ce n'est pas la chaîne qui borne ce vecteur, c'est la relance unique du critère d'arrêt
>       (`docs/CONTRAINTES_POST_B4.md` § 10.1, section d'origine, non redite ici) : une omission n'achète qu'une
>       relance par famille, et la suite est tranchée par ce critère. Aucun substitut de mesure n'est proposé.

**Motif.**
- Candidat 6 (E5, lot 4b). Aujourd'hui, sur un comparateur non constructible, le producteur refuse en code 2
  **avant le moteur**, et rien n'est écrit **[v]** `c3b_evaluate.py:555-558`, `:912-914`. La chaîne n'a rien à
  lire, et `E_NO_BENCHMARK` est inatteignable.
- Une campagne sans issue du § I.1 n'est pas une campagne : le § 10.1 ne sait pas la compter.
- Pourquoi la forme retenue (décision 29/09) : forme de refus du **même** artefact, plutôt qu'une huitième
  entrée. Avec l'export de bougies d'évaluation (AM-03), la chaîne rejoue la non-constructibilité, et le refus
  devient recoupé.
- L'item 13 nomme le vecteur et sa borne (correction 4 du GO) : sans cela, on aurait consigné un non-mesurable
  sans dire pourquoi il est tolérable.
- **Deux motifs, pas trois (retouche C-3 du STOP 1).** Sur une évaluation non refusée, un recalcul impossible est
  une violation (AM-03), pas un `E_NO_BENCHMARK` : le seul comparateur non constructible légitime est celui de la
  forme de refus. Le § 10.1 ne compte ni un code 1 ni un `E_NO_BENCHMARK` : la retouche change ce que le rapport
  dit du producteur, pas le budget de relance.

**Impact outillage — R-18, bloquant manifeste.**
- **Producteur.** Sur `comparator_not_buildable`, écrire la forme de refus et `candles_eval.json`, au lieu du
  refus 2 sans artefact **[v]** `c3b_evaluate.py:555-558`.
- **`cc.evaluation_admission`** **[v]** `c3_common.py:1150-1176` reconnaît la forme de refus.
- **`c3_continuity`** route sans contrat § B. Aujourd'hui `comparator_block` exige `benchmark_eval` **[v]**
  `c3_continuity.py:287-333`, et l'admission se fait en tête **[v]** `:361`.
- **`c3_verdict`** publie `E_NO_BENCHMARK` avec le motif. Aujourd'hui il ne le tire que du comparateur `FAILED`
  **[v]** `c3_verdict.py:581`, `:646-647`. Il porte `continuite=-` sur cette route **[v]** `:897` et rejoue
  `cb.build_pair` sur l'export (R-15).
- **Aucune modification du § B.8.** `test_c3_verdict.py:3167` reste inchangé et vert.

**Test attendu — R-18.**
- **Producteur** (jumeau de `test_c3b_evaluate.py:1401`) : comparateur non constructible → `evaluation.json` sous
  forme de refus, et `candles_eval.json` écrit.
- **Chaîne** :
  - évaluation refusée → `inconclusif (E_NO_BENCHMARK)`, motif `comparator_not_buildable`, code 0,
    `continuite=-` ;
  - `refused` accompagné de séries → violation ;
  - refus démenti par un export qui porte les deux estampilles → violation ;
  - refus portant une identité ≠ configuration retenue → `R0_INVALID_RUN`, code 2, rien publié (C-1).
- **Abstention → `continuite=-`** (C-5) : déjà vrai et déjà testé, `test_c3_verdict.py:3758`
  (`test_revue_Fin2_1_l_abstention_recoupe_la_continuite_et_porte_continuite_tiret`). C'est un témoin
  (i), dont le docstring est recité sur le § L.2 v2.2 ; ce n'est pas un `xfail`.
- Le cas « ni l'un ni les autres → code 2 » est vrai aujourd'hui : il n'est donc pas un adverse.

**Statut proposé.** À adopter.

---

## AM-07 — renvoi

Le candidat 7 (E11 : λ et `returns_bench`) est traité par **AM-03**, qui porte les trois recoupements dans un seul
amendement (décision du 29/09).

---

## AM-08 — § L.1 et § B.8 : une évaluation réelle sans exécution est admise

**Clause.** § L.1, phrase d'admission d'une évaluation réelle ; § B.8, paragraphe « Ce qu'exige `validé` ». La
table et la phrase de précédence du § B.8 ne changent pas.

**Avant (§ L.1).**

> Une évaluation déclarée réelle (`synthetic: false`) est admise **si et seulement si** elle porte `flat_start_proof`,
> `invocation.single_call` et `first_fill_at` (§ B.2, § B.4, § C.3 — les trois clauses déclaratives, en état
> `DÉCLARÉ`) ; il lui en manque une → refus `R0_INVALID_RUN`, code 2, rien publié, avec le nom de ce qui manque.

**Après (§ L.1).**

> Une évaluation déclarée réelle (`synthetic: false`) est admise **si et seulement si** elle porte
> `flat_start_proof`, `invocation.single_call`, `first_fill_at` et `metrics.executions` (§ B.2, § B.4, § C.3
> — les trois clauses déclaratives). `metrics.executions` est le nombre d'exécutions (remplissages) du run
> d'évaluation. S'il lui en manque un, c'est un refus `R0_INVALID_RUN`, code 2, rien publié, avec le nom de ce
> qui manque.
>
> **`first_fill_at` peut être nul, et dans un seul cas : l'évaluation n'a rien exécuté.**
> - `first_fill_at` est nul **si et seulement si** `executions == 0` ; ces deux déclarations se recoupent.
> - `executions == 0` **implique** `equity_daily` constante, égale au capital `C` ; l'outillage le recalcule.
> - Une contradiction entre ces faits est une violation (§ I.1, ligne 15).
> - **Rien n'est exigé dans l'autre sens** : une equity constante ne prouve pas l'absence d'exécution.
>
> Une évaluation réelle sans exécution est admise, et sa clause 5 est `NON VÉRIFIABLE` (§ B.8). Avec
> `executions == 0`, une position nulle à `fin` et un bloc de liquidation dont la liste de lots est exportée et
> vide, la clause 3 est `VÉRIFIÉE` à vide : il n'y avait rien à liquider, et le contrat le dit (§ B.3, titre) —
> comme `stamp_cell` sans estampille (§ B.4). Une évaluation sans exécution qui exporte sa liste de lots reçoit
> donc l'issue économique du § H, jamais `R1_NOT_NORMALISED` ; sans liste de lots, la clause 3 reste
> `NON VÉRIFIABLE` (§ B.8).

**Avant (§ B.8, « Ce qu'exige `validé` »).**

> **Ce qu'exige `validé`** sur la continuité : c2 `DÉCLARÉ`, c3 `VÉRIFIÉ`, c4 `VÉRIFIÉ`, `comparator` `VÉRIFIÉ`,
> `stamp_cell` `VÉRIFIÉ` ou `NON VÉRIFIABLE`, et **c1, c5 `DÉCLARÉ` sur une évaluation réelle** — une
> évaluation réelle qui ne porte pas sa preuve de départ à plat ou son premier remplissage n'est pas admise
> (§ L.1). **En exercice synthétique** (§ L.1), c1 et c5 `NON VÉRIFIABLE` sont tolérés : l'exercice éprouve
> l'outillage, pas une évaluation. L'agrégat `VÉRIFIÉ` est inconstructible par la table ci-dessus, et c'est
> voulu.

**Après (§ B.8, « Ce qu'exige `validé` »).**

> **Ce qu'exige `validé`** sur la continuité : c2 `DÉCLARÉ`, c3 `VÉRIFIÉ`, c4 `VÉRIFIÉ`, `comparator` `VÉRIFIÉ`,
> `stamp_cell` `VÉRIFIÉ` ou `NON VÉRIFIABLE`, et **c1, c5 `DÉCLARÉ` sur une évaluation réelle** — une
> évaluation réelle qui ne porte pas sa preuve de départ à plat n'est pas admise (§ L.1). Une évaluation réelle
> **sans exécution** est admise avec un premier remplissage nul (§ L.1). Sa clause 5 est alors
> `NON VÉRIFIABLE`, `validé` lui est inatteignable, et son issue est celle que le § H lui donne. **En exercice
> synthétique** (§ L.1), c1 et c5 `NON VÉRIFIABLE` sont tolérés : l'exercice éprouve l'outillage, pas une
> évaluation. L'agrégat `VÉRIFIÉ` est inconstructible par la table ci-dessus, et c'est voulu.

**Motif.**
- **Candidat 8 (lot 4a).** Sans exécution, le producteur écrit `first_fill_at: null` **[v]**
  `c3b_evaluate.py:394-398`. L'admission le refuse en R0 **[v]** `c3_common.py:1167-1175`, alors que le § B.8
  admet c5 `NON VÉRIFIABLE`. Une cellule sans exécution produit ainsi un **faux R0** : un refus d'instrument là
  où le protocole attend une issue.
- **Pourquoi une implication, et pas une équivalence** (correction 1 du GO du 29/09).
  - L'absence d'exécution rend l'equity constante égale à `C` : ni frais, ni variation d'inventaire.
  - La réciproque suppose que chaque exécution paie des frais strictement positifs. Sous un modèle de frais
    nuls, deux exécutions au même prix laissent l'equity plate avec `executions > 0` ; exiger la réciproque
    ferait crier violation à tort.
- **Pourquoi `executions`, et pas `total_trades` (retouche C-6 du STOP 1).** `total_trades` existe dans le moteur
  avec le sens `pairs_completed + liquidated_positions` **[v]** `scripts/backtest.py:3326` ; une clé homonyme à
  sens différent serait copiée un jour telle quelle par la couche d'export. `executions` est le nombre
  d'exécutions (remplissages) du run d'évaluation.
- **La clause 3 d'une évaluation sans exécution (retouche C-2 du STOP 1), lue dans le code.** Le producteur exporte
  toujours la liste des lots, vide quand rien n'est liquidé **[v]** `c3b_common.py:375`. Sur un bloc à
  `trades == 0`, sans position et à `lots: []`, la clause 3 sort aujourd'hui `VERIFIED` **[v]**
  `c3_common.py:2008-2012`, `c3_continuity.py:196-211`, ce que le lot 4a a exercé sur données réelles. Un bloc
  **sans** liste de lots rend `NOT_VERIFIABLE` **[v]** `c3_continuity.py:201-210`, conformément au § B.8. D'où la
  rédaction « liste de lots exportée et vide », décidée au STOP 1 ; aucun adverse de plus en R-19.
- **Pourquoi un porteur déclaré et recoupé.** `executions` est déclaratif, comme `first_fill_at`. Les deux se
  recoupent l'un l'autre, et l'implication vers `equity_daily` se recalcule : la clause ne repose pas sur une
  seule déclaration.

**Impact outillage — R-19, bloquant manifeste.**
- **`cc.evaluation_admission`** **[v]** `c3_common.py:1150-1176` :
  - `metrics.executions` devient obligatoire ;
  - `first_fill_at` devient présent et nullable, sous condition.
- **Recoupements** : `first_fill_at` nul ⟺ `executions == 0`, et `executions == 0` ⟹ equity constante `= C`
  (continuité ou verdict).
- **`c3_verdict`** : la règle « c1 ou c5 `NON VÉRIFIABLE` sur une évaluation réelle → violation » **[v]**
  `c3_verdict.py:556-564` admet c5 `NON VÉRIFIABLE` quand `first_fill_at` est nul.
- **Producteur** : il exporte `metrics.executions`, le nombre d'exécutions, c'est-à-dire les remplissages dont
  `first_fill_at` est le premier. Aujourd'hui `metrics` n'a que trois clés **[v]** `c3b_evaluate.py:686-690`, et
  les exécutions sont `engine.metrics.trades` **[v]** `:812-814`.
- **Fixtures** : `fx.evaluation` porte `metrics.executions`.

**Test attendu — R-19.**
- **Producteur**, jumeaux de `test_c3b_evaluate.py:924`, `:1023-1036` et `:1827-1848` :
  - sans exécution, `metrics.executions == 0` et l'admission ne refuse pas ;
  - le jeu de clés de `metrics` comprend `executions`.
- **Continuité** : évaluation réelle, `first_fill_at` nul, `executions` 0, equity constante `= C` → code 0,
  c5 `NOT_VERIFIABLE`.
- **Verdict** :
  - le même monde → aucune violation, issue ≠ `validé` ;
  - `first_fill_at` nul avec `executions > 0` → violation ;
  - `executions == 0` avec une equity non constante → violation.
- Rien n'est testé dans le sens abandonné.
- Témoins (i) dont seul le docstring est recité sur v2.2 : `test_c3_continuity.py:201`,
  `test_c3_verdict.py:1864` et `:1898`, `:1949`. Leurs fixtures portent un remplissage, et l'attendu reste le
  même.

**Statut proposé.** À adopter.

---

## AM-09 — § A.7 : dates de couverture nulles si et seulement si aucune unité n'est couverte

**Clause.** § A.7, paragraphe « L'artefact de couverture est une entrée du protocole », liste de ce qu'il porte.

**Avant.**

> Il porte, par paire et par timeframe : le **compte de bougies observées**, le **compte attendu** sur `[début, T]`,
> la liste des **estampilles manquantes**, le **plus long trou en jours**, et les premier et dernier jours
> couverts.

**Après.**

> Il porte, par paire et par timeframe : le **compte de bougies observées**, le **compte attendu** sur
> `[début, T]`, la liste des **estampilles manquantes**, le **plus long trou en jours**, et les premier et
> dernier jours couverts. Ces deux dates sont **nulles si et seulement si** la série n'a aucune unité couverte au
> sens de D1 (§ A.8). Une date nulle sur une série qui a des unités couvertes, ou une date présente sur une
> série qui n'en a aucune, contredit l'artefact (§ I.1, ligne 15).

**Motif.**
- Écart 11 de C3b (lot 3, E3). Une série sans unité couverte n'a pas de premier ni de dernier jour couvert.
- Aujourd'hui, le producteur la refuse en code 2 **[v]** `c3b_common.py:625-632`, `c3b_prefix.py:395-406`, et la
  chaîne lit les dates par `require_str` **[v]** `c3_entry.py:568-569`, `c3_common.py:1812-1813`.
- Une paire sans données doit sortir par D1 et devenir descriptive (§ I.1, ligne 3). Elle ne doit pas faire
  refuser tout le run.

**Impact outillage — R-20, non bloquant.**
- Le producteur écrit des dates nulles au lieu de refuser.
- `c3_entry` I-A.7 et `cc.coverage_recompute` lisent ces dates en nullable, avec la condition du texte ;
  `NULLABLE_FIELDS` **[v]** `c3_common.py:261-280`.

**Test attendu — R-20.**
- **Producteur** (jumeau de `test_c3b_common.py:1119`) : aucune unité couverte → série écrite, dates nulles.
- **Entrée** :
  - `covered_units == 0` avec des dates nulles → I-A.7 passe, et D1 retire la paire ;
  - dates nulles avec `covered_units > 0` → violation ;
  - dates présentes avec `covered_units == 0` → violation, si ce cas est rouge aujourd'hui (sinon ce n'est pas un
    adverse, et c'est consigné).
- Témoin inchangé : `test_c3_entry.py:801`.

**Statut proposé.** À adopter.

---

## AM-10 — § A.8, D4 : le CAGR qui en découle doit être fini

**Clause.** § A.8 : table des clauses, ligne D4 ; paragraphe « D4 — la seule contrainte mathématique ».

**Avant (table).**

> | **D4** | Estimabilité | rendements quotidiens définis et **tous finis**, dénominateurs non nuls | candidat | contrainte mathématique |

**Après (table).**

> | **D4** | Estimabilité | rendements quotidiens définis et **tous finis**, dénominateurs non nuls, **et le CAGR annualisé qui en découle, fini** | candidat | contrainte mathématique |

**Après (paragraphe D4)** — ajouté à la fin du paragraphe :

> **Le CAGR qui déborde.** Des rendements tous finis peuvent donner un CAGR que l'annualisation fait déborder de
> la double précision dans laquelle le protocole calcule (§ F.2 c). Ce CAGR n'est alors pas défini, et le
> candidat sort par D4 (§ I.1, ligne 6). Ce n'est pas une violation (ligne 15) : le CAGR est une valeur
> **calculée** par l'outillage, pas une valeur **fournie**.

**Motif.**
- **Cas 5 de la classification** (`phase1.md` § 1 et § 10). `cc.cagr_pct` passe par `math.exp`, qui lève
  `OverflowError` **[v]** `c3_common.py:732`. Sur le chemin chaîne (`c3_benchmark` **[v]** `:266`, `:310`,
  `:433` ; `c3_select` **[v]** `:280`), l'exception n'est pas rattrapée, et l'outil sort en code 1 avec une
  trace. D4 passe sur des rendements finis, et aucun texte ne couvrait ce cas.
- **Pourquoi la ligne 6 et pas la ligne 15** (décision du 29/09). Une valeur calculée n'est pas une valeur
  fournie. Au préfixe il y a un candidat à retirer, alors qu'à l'évaluation il n'y en a pas : là, le § F.2 (e)
  envoie un CAGR observé non fini en ligne 15. La symétrie tient.
- **Le trou est étroit, et c'est ce qui justifie le statut « bloquant campagne » sans l'exagérer.**
  - `Σ log1p(r) = ln(E_fin / E_0)`, avec `E_0 = C = 1000` imposé à l'ancre (§ B.2).
  - En double précision, la somme ne dépasse pas `ln(1,8·10³⁰⁸ / 1000) ≈ 702,9`, et l'exponentielle ne déborde
    qu'au-delà de 709,78.
  - Il faut donc un préfixe de moins de 702,9 × 365 / 709,78 ≈ **361 jours**.
  - C'est impossible sur le préfixe de 1 362,2 jours de la première campagne. C'est possible sur une fenêtre
    courte, comme la fenêtre d'instrument 2020 (préfixe d'environ 250 j) ou une relance à fenêtre courte.

**Impact outillage — R-21, non bloquant manifeste, bloquant campagne.**
- **`c3_select`** : D4 vaut aujourd'hui `rec.domain_ok` **[v]** `c3_select.py:342`. Il retient aussi « CAGR
  fini ». La finitude des rendements est le cas 3 (R-22).
- **`c3_benchmark`** : `candidate_block` **[v]** `c3_benchmark.py:433` consigne `estimable: false` au lieu de
  lever.
- **`cc.recompute_daily`** **[v]** `c3_common.py:1625` rend un CAGR non défini, sans exception.

**Test attendu — R-21.** Monde à fenêtre courte, préfixe de moins de 361 jours ; rendements finis, CAGR qui
déborde.
- `c3_benchmark` → code 0, candidat `estimable: false`.
- `c3_select` → candidat retiré par D4, code 0.
- `xfail(raises=OverflowError)` : c'est l'exception observée aujourd'hui.

**Statut proposé.** À adopter.

---

## AM-11 — § F.8 : les deux chemins de sommation du rendement géométrique

**Clause.** § F.8, paragraphe « Leurs valeurs et leurs classes sont celles du § A.10 ».

**Avant.**

> **Leurs valeurs et leurs classes sont celles du § A.10**, section d'origine des seuils ; les répéter ici les
> ferait diverger. Seuls les domaines de mesure changent.

**Après.**

> **Leurs valeurs et leurs classes sont celles du § A.10**, section d'origine des seuils ; les répéter ici les
> ferait diverger. Seuls les domaines de mesure changent, et le chemin de sommation du rendement géométrique.
> - **Les deux chemins.** Au préfixe (`P2`), la somme des `log1p` est une somme correctement arrondie. À
>   l'évaluation (`Q2`), c'est le chemin du § F.2 (c), le seul que la chaîne rejoue au bit.
> - **L'écart est borné.** Sur une même série de `n` rendements, les deux sommes diffèrent au plus de
>   `1,01 · n · u · Σ|log1p r|`, avec `u = 2⁻⁵³` : c'est la borne de toute sommation en double précision, quel
>   qu'en soit l'ordre, à laquelle s'ajoute l'arrondi final. Le CAGR diffère d'autant, multiplié par
>   `(100 + CAGR) · 365 / n_jours`, à quelques ulps près.
> - **Il est sans effet décisionnel.** Cet écart ne reçoit ni seuil ni classe (§ 0.5). `P2` et `Q2` portent sur
>   des fenêtres disjointes et ne se comparent jamais entre elles.

**Motif.**
- La « note postérieure au gel » de v2.1 (`docs/amendements_c3_v2.1.md`, section « Adoption ») promettait ce
  point à v2.2. Le reporter une seconde fois en ferait une dette (décision du 29/09).
- **[v]** La sélection calcule par `cc.cagr_pct`, avec `math.fsum` **[v]** `c3_common.py:731-732`. L'évaluation
  calcule par `cc.cagr_rows`, avec `numpy` **[v]** `:769-777`.
- **Mesure** `results/c3_v2_2/tests/f8_ecart.sh` sur les 27 séries des tests existants (témoin d'évaluation,
  20 séries variables, 6 trajectoires de préfixe) :
  - écart maximal **2,1·10⁻¹⁴ point de %/an** ;
  - au plus **0,08 %** de la majoration ci-dessus ;
  - `numpy` 2.4.1, Python 3.12.11.

**Impact outillage.** Aucun.

**Test attendu.** Aucun nouveau. La mesure est committée avec sa sortie.

**Statut proposé.** À adopter.

---

## AM-12 — § M : index régénéré

**Clause.** § M, les deux tables.

**Avant.** L'index est à la révision v2.1.

**Après.** L'index est régénéré à l'application, depuis le texte v2.2 (sections hors historique d'amendements et
hors § M), par un script versionné sous `results/c3_v2_2/tests/`. Changements attendus, à vérifier sur la sortie
du script :
- `E_NO_BENCHMARK` gagne § L.1, § L.2 et § J ;
- `R0_INVALID_RUN` gagne § A.6 ;
- `D4` gagne son site de référence au § A.8.

**Règle de lecture inchangée** : une colonne de références vide est une porte que rien n'applique. Elle se
vérifie avant le calcul du sha.

**Motif.** § M : « régénéré à chaque révision et recollé ici ».

**Impact outillage.** Aucun.

**Test attendu.** Aucun. Le contrôle est fait par le script, dont la sortie est committée.

**Statut proposé.** À adopter, avant AM-00.

---

## Constats de rédaction (agent rédacteur)

Ce sont les points vus en rédigeant. Ce n'est pas la lecture adverse : celle-ci est faite par le relecteur, au
STOP, sur l'Avant / Après d'AM-03, AM-06 et AM-08. Les quatre premiers ont été tranchés par le GO du 29/09 ; les
suivants sont consignés, et ne sont pas corrigés dans ce paquet.

1. **AM-08, réciproque.** « Des exécutions ⟹ equity non constante » ne tient que sous des frais strictement
   positifs. Tranché : implication seule.
2. **AM-06, fidélité de l'export.** Le rejeu de la non-constructibilité prouve la cohérence avec l'export, pas
   avec la base. Tranché : item 13 du § J, avec le vecteur et sa borne.
3. **AM-03, `equity_daily`.** Le recoupement prouve une cohérence interne, pas la vérité de la trajectoire.
   Tranché : `equity_daily` et l'export restent déclaratifs (§ J, item 12).
4. **AM-05, évaluation différée.** Elle ne doit pas être refusée comme une seconde campagne. Tranché : c'est un
   état du registre (date et empreinte attendue).
5. **`total_trades` : même nom, deux sens. Réglé au STOP 1 (C-6) : la clé est `metrics.executions`.**
   - Le moteur porte une métrique `total_trades` dont le sens n'est pas celui d'AM-08 : `pairs_completed +
     liquidated_positions` sur le grid **[v]** `scripts/backtest.py:3326`, et le nombre de ventes sur le moteur
     signal (§ A.8, D3).
   - AM-08 définissait `metrics.total_trades` comme le **nombre d'exécutions** ; le producteur devait exporter ce
     compte-là **[v]** `c3b_evaluate.py:812-814`.
   - Les deux valent zéro ensemble sur les deux moteurs, sauf peut-être un lot soldé en poussière, à vérifier à
     l'outillage (R-19).
6. **`continuite=-` en abstention. Réglé au STOP 1 (C-5), dans AM-06 ; ce n'est plus un candidat v2.3.**
   - L'outillage porte `continuite=-` quand aucune configuration n'est retenue **[v]** `c3_verdict.py:724-727`,
     `:897`. Le § L.2 ne définit `-` que pour l'identité retenue.
   - C'est une convention d'outillage non écrite. AM-06 emploie le même `-` pour « sans objet » sur la route du
     refus amont ; C-5 étend la phrase à l'abstention.
7. **§ A.6, « Cette liste est exactement ce que la clause D5 asserte ».** C'est inexact avant ce paquet : les
   seuils, le mode de `λ` et la graine ne sont pas assertés par D5, et la famille d'AM-05 non plus. Candidat
   v2.3, non corrigé.
8. **Portée des contrats de forme `_base` et `_quote` sur le bloc de liquidation de l'évaluation.**
   - Le § A.7 les énonce pour la projection du préfixe.
   - L'outillage les applique partout où le bloc est lu, par la fonction partagée **[v]**
     `c3_common.py:1893` (D6 au préfixe, clause 3 à l'évaluation). Le texte ne le dit pas pour l'évaluation.
   - Candidat v2.3, non corrigé.
9. **Registre unique et persistant.**
   - AM-05 suppose un registre de campagne unique ; C3b en a tenu un neuf par run (écart 12).
   - Aujourd'hui, une seconde racine est refusée **[v]** `c3_anchor.py:174-180` : la première campagne d'une
     autre famille devra déclarer un parent (§ A.6).
   - C'est dit dans l'impact d'AM-05, sans changement de texte.

---

## Vérifié, sans amendement

| Point | Constat |
|---|---|
| Cas 1 à 4 de la classification (`phase1.md` § 1) | Le texte prescrit déjà la forme : ligne 15 et diagnostic pour les cas 1 et 4 ; § C.5 et § C.6 (code 0) pour le cas 2 ; D4, ligne 6, pour le cas 3. L'outillage seul est en défaut : R-22, aucun texte |
| § H.1 et § I.1 | Aucune raison nouvelle, aucune ligne nouvelle. Le refus amont passe par `E_NO_BENCHMARK` (ligne 10) et AM-10 par D4 (ligne 6). Le motif est un champ |
| § B.8 | Ni état nouveau, ni ligne nouvelle. « Sans objet » est une valeur du champ de chaîne (§ L.2). `test_c3_verdict.py:3167` est inchangé |
| `docs/CONTRAINTES_POST_B4.md` § 10 | Non touché : AM-05 et AM-06 y renvoient sans le reformuler |
| Livrable C3a, artefacts C3b | Historiques, respectivement v2.0 et v2.1. Aucun n'est régénéré. Sous v2.2, l'ancrage refuse leurs manifestes (`phase1.md` § 4) |

---

## Ordre d'application

1. **Au GO du STOP de lecture adverse**, un commit par amendement, dans l'ordre des sections :
   - AM-05 (§ A.6 ; il pose le pont `xfail` du test du sha) ;
   - AM-04, puis AM-09 (§ A.7) ;
   - AM-10, AM-01, puis AM-02 (§ A.8) ;
   - AM-06 (§ C.5, § L.1, § L.2, § J) ;
   - AM-11 (§ F.8) ;
   - AM-08 (§ L.1, § B.8) ;
   - AM-03 (§ L.2, § L.1, § F.2 d, § J, § 0.7).

   Chaque commit porte le texte, identique à ce paquet, avec ses miroirs (i), ses jumeaux (ii) et ses adverses
   neufs. Tout écart au texte est consigné ; sur AM-03, AM-06 ou AM-08, un écart est un STOP.
2. **AM-12** (index), puis **AM-00** (en-tête). Le sha256 de v2.2 est calculé une fois, jamais avant.
3. **Commit « Adoption »** de ce paquet : empreintes v2.0, v2.1 et v2.2 ; décisions de gate, avec les constats de
   la lecture adverse et les réponses de Bruno ; réserves R-15 à R-22 ; ligne Astra ; écarts de rédaction.
4. Tests du sha généralisés, et levée du pont.

Aucune ligne de `scripts/audit/*.py`, de `src/`, de `scripts/backtest.py` ni des runners n'est touchée.
L'outillage est la liste close `results/c3_v2_2/outillage_v2_2.md`.
