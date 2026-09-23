# Amendements au protocole C3 — v2.0 (gel `d931293`) → v2.1

> **Statut : ADOPTÉ le 2026-09-23** (Bruno), sous les décisions de gate et les réserves d'application de la
> section « Adoption » ci-dessous, qui porte aussi l'empreinte de v2.1. Ce paquet est un texte : il s'est lu
> comme le protocole s'est lu au gate 2, sans code ; son application est décrite à la section « Adoption ».
>
> **Rappel de la règle qui autorise ce document — § 0.7 et en-tête du protocole.** Une fois gelé, « *rien des
> § 0 à M ne peut être relu, repondéré, réinterprété ou élargi* ». Toute modification postérieure au GO est un
> **amendement daté**, qui décrit ce qui a changé et pourquoi, et qui **crée une nouvelle variante** au sens du
> § A.6 : un manifeste qui porte le sha256 de v2.1 n'a pas la même empreinte qu'un manifeste qui porte celui de
> v2.0, et le registre les distingue sans qu'on ait à le lui dire.
>
> Base amendée : `docs/protocole_c3.md`, sha256
> `9b62915069e59e9b0f35120c60a77f48a72b278aa9102b3096dfcb8dc25e23c2` (commit `d931293`, C3a taguée
> `v2.11.0-c3a-protocole`). Sources des décisions : brief de reprise du 23/09 (blocs A, B, C), rapport de session
> C3a du 22/09 (§ 7, § 8, § 14), inventaire USDT `results/data_inventory_usdt_2019_20260923/inventory.md`.
> Faits lus dans le code de l'archive `krakenbot-src-v2_11_0-c3a-protocole-13-gf321ddd` sont tagués **[v]** avec
> leur `fichier:ligne`.

## Adoption — 2026-09-23

**Adopté par Bruno le 2026-09-23**, au gate d'amendement, sous les décisions et les réserves ci-dessous.
Application : branche `feat/c3-amendements-v2.1` depuis `dev` @ `f321ddd` — texte du protocole, outillage
`scripts/audit/c3_*.py`, tests `tests/test_scripts/test_c3_*.py`, `docs/CONTRAINTES_POST_B4.md` § 10 —, un seul
STOP intermédiaire, après l'application de AM-15 (commit 8b), suivi d'un commit 8c décidé à ce STOP. Le reste de
ce document est le paquet tel qu'il a été proposé et revu ; là où l'application s'en écarte, cette section le
dit, et c'est elle qui fait foi avec le texte du protocole.

### Empreinte du protocole

| Révision | sha256 de `docs/protocole_c3.md` | Commit |
|---|---|---|
| v2.0 (gel du 2026-09-21) | `9b62915069e59e9b0f35120c60a77f48a72b278aa9102b3096dfcb8dc25e23c2` | `d931293` |
| v2.1 (ce paquet) | `9300f4e53bfd36633df6524c2d7ad168a732739ca3dd1765c024cc8a3ccd4129` | le commit qui porte cette section |

**sha256 v2.1 :** `9300f4e53bfd36633df6524c2d7ad168a732739ca3dd1765c024cc8a3ccd4129`

Un fichier ne peut pas porter sa propre empreinte (R-01) : le sha v2.1 est consigné ici, dans
`docs/RESEARCH_LOG.md`, `skills/backtest.md` et `CLAUDE.md` ; `c3_common.protocol_descriptor` le recalcule
dans chaque artefact, et `tests/test_scripts/test_c3_common.py` épingle la ligne ci-dessus au fichier. Toute
retouche du protocole sans amendement daté la fait diverger.

### Décisions de gate (Bruno, 2026-09-23)

| Point | Décision |
|---|---|
| AM-11 : `stamp_cell` NON VÉRIFIABLE | satisfaction à vide ; seul ÉCHEC produit `E_STAMP_MISMATCH` |
| AM-06 : portée | les quatre clés `_base` |
| Livrable réel C3a (`results/c3a_entry_validation/`) | **intact, historique v2.0** ; les deux tests qui le rejouent sont réécrits (l'ancrage v2.1 refuse le manifeste v2.0) |
| Fenêtre / SOL | **2021-03-01 conservée**. Au 2021-03-01, SOL porte 29 bougies 1 w (depuis le 2020-08-17), la 50ᵉ tombe le 2021-07-26 : D2 retire les candidats SOL dont une porte lit le 1 w — SOL est partiel dans la première campagne, ou absent. Le texte n'invoque aucun motif pour la borne |
| D1 1 w sur la fenêtre v2.1 | appliquer, conséquence **écrite** (AM-05) : six estampilles 1 w manquent en 2022, dans le préfixe, sur les trois paires — 188/194 = 96,9 % < 97 % ; sans reconstruction, l'ensemble admissible est vide ; la décision de reconstruction précède le manifeste |
| Annexe A § 10.1 | `A_NO_ADMISSIBLE_CANDIDATE` **non compté** dès qu'un candidat a été retiré par D1, D2 ou D6 |
| § B.8 : c3 NON VÉRIFIABLE | → `R1_NOT_NORMALISED` ; c1/c5 NON VÉRIFIABLE tolérés en exercice synthétique seulement |
| Bloc de liquidation contradictoire (`trades > 0` sans estampille ou sans l'un des champs de prix) | **violation, ligne 15, code 1**, jamais `R1_NOT_NORMALISED` (précédence violation → issue) ; la règle vit dans la fonction partagée, donc aussi à D6 au préfixe |
| AM-15 : frontière de confiance sur les bornes | **rejeu complet du tirage** par la chaîne |
| Environnement du rejeu | `{python, numpy, machine, libc}` : `platform.python_version()`, `numpy.__version__`, `platform.machine()`, `platform.libc_ver()` ; jamais la chaîne du noyau |
| Convention de somme | un seul chemin `numpy` ; Δ̂ et le CAGR de Q2 par les indices identité |
| AM-07 : porteurs | `decision_timeframes` exporté par **toute** observation, recoupé à l'entrée |
| AM-10 : noms | le code suit le texte : `{at, cash, qty, pending}` et contrôle `at == T` |
| AM-24 : § L.1, ligne 0 | six entrées énumérées, dont `candles.json` |
| Porte humaine intermédiaire | un seul STOP, après le commit 8b |
| STOP — ordre des opérations du CAGR (§ F.2 c) | **le code suit le texte** : `(Σ log1p(r) × 365) / n_jours`, l'ordre de `cc.cagr_pct`, une seule division en dernier ; expression `numpy` écrite en entier au texte |
| STOP — critère d'écartement (§ F.2 e) | **le texte suit le code** (R-14) : seul un `Δ*` non fini est écarté |
| STOP — suite, sérialisation, contrats, environnement | suite `Δ*` dans l'ordre `b = 1 … B` ; valeurs sérialisées par le `repr` le plus court qui se relit à l'identique (convention de `canon`, § A.1 bis) ; comparateur exactement `{dd, σ}` et environnement exact au contrat ; au § J item 12, la limite macOS est sans effet tant que producteur et chaîne tournent sur le serveur (recette C2) — c'est cette règle d'exploitation qui tient lieu de garantie, pas le champ `libc` |
| `--campaign` (paramètre libre du label de chaîne, contraire à la lettre du § L.2) | dette numérotée dans `PROJECT_CONTEXT.md` |

### Réserves d'application

- **R-01 (AM-00).** Un fichier ne peut pas porter sa propre empreinte : l'en-tête dit « nouveau sha256 : consigné
  hors du fichier », et le sha v2.1 est inscrit ci-dessus, dans `docs/RESEARCH_LOG.md`, `skills/backtest.md` et
  `CLAUDE.md`.
- **R-02, R-03.** Devenues des décisions de gate : fenêtre / SOL, D1 1 w (table ci-dessus).
- **R-04 (AM-07).** Les observations ne portent aucun drapeau `synthetic` : la règle vaut pour **toute**
  observation. Le manifeste garde sa déclaration par stratégie et sa surcharge par candidat. Forme : liste non
  vide d'étiquettes distinctes de `data.timeframes`, sinon I-A.1, R0 ; comparaison en ensemble avec la liste
  effective du candidat apparié, sinon I-A.6, violation.
- **R-05 (AM-10).** Le paquet annonçait « aucun impact » ; les noms et le contrôle `at == T` différaient du
  code : amendement à comportement changé.
- **R-06 (AM-11).** « `positions == 0` » devient « bloc présent qui ne liquide rien : `trades == 0`, estampille
  nulle ».
- **R-07 (AM-12, AM-18, AM-19).** Ligne 10 bis, raison du § H.1 et § B.3 : « clause 3 en échec **ou non
  vérifiable** » ; § B.8 : c3 NON VÉRIFIABLE → R1, `liquidation_normalised` à `null` (« non établi »), c1/c5
  `DÉCLARÉ` sur une évaluation réelle et NON VÉRIFIABLE tolérés en exercice synthétique ; ligne ajoutée au
  § 0.7 ; renvoi du § H.1 au § B.8.
- **R-08 (AM-09, AM-14, AM-20).** Format `replications[c] = {delta_stars, discarded, bound}`, `bound` nul si et
  seulement si la suite est vide (`bound` entre dans `NULLABLE_FIELDS`) ; contrat d'instrument en tête, avant
  toute lecture et avant `verify_chain`.
- **R-09 (AM-15, § J item 12).** Rejeu complet : l'évaluation exporte `returns_bench {dd, sigma}` et
  `environment` ; le § F.2 fixe le tirage, l'index de paire, `n_jours = (fin − T)` en secondes / 86 400, un seul
  chemin de calcul ; la chaîne rejoue et recoupe suites, écartées, bornes, `metrics.cagr_pct` et
  `metrics.delta_dd` ; Q2, Q3 et les bornes décident sur les valeurs rejouées ; restent déclaratifs les séries
  et `net_pnl` ; le § J item 12 est réécrit en conséquence (le paquet disait « la chaîne lit la borne »).
- **R-10 (AM-24).** Ligne 0 à six entrées, dont `candles.json` (le paquet le sortait de l'énumération, à tort :
  `c3_benchmark` le lit) ; « sans entrée réelle en C3a » retiré de la ligne 5 ; `c3_continuity` applique la
  même règle d'admission ; diagnostic et vue de continuité tirent `synthetic` de l'évaluation.
- **R-11 (annexe A § 10.1).** La ligne `A_NO_ADMISSIBLE_CANDIDATE` est scindée : l'abstention compte, sauf si un
  candidat a été retiré par D1, D2 ou D6 — elle ne compte pas alors, et l'unique relance s'applique.
- **R-12 (AM-18).** Aucun test existant n'épinglait l'ordre des raisons : un test neuf le fait, et relit la
  liste dans le bloc du § H.1.
- **R-13 (AM-02).** Le témoin « I-A.6 recalcul » cité par le paquet n'existait pas ; les témoins réels sont
  ceux de `test_c3_entry.py` et `test_c3_verdict.py` sur le livrable C3a, et les tests d'ancrage v2.1.
- **R-14 (§ F.2 c, e — décidée au STOP).** Modification du texte v2.0 hors paquet : le critère d'écartement est
  « `Δ*` non fini » et rien d'autre ; la clause « ou un rendement rééchantillonné conduit la trajectoire à zéro »
  est retirée (elle décrivait un produit cumulé qui n'est pas le calcul du (c) ; `r > −1` est imposé à
  l'entrée) ; un CAGR de −100 exactement est fini et retenu ; « reconstruite par produit cumulé » devient
  « rendement géométrique par somme des `log1p` ». Le noyau appliquait déjà ce critère depuis C3a.

### Écarts de rédaction au texte du paquet

- AM-02 (§ A.3) :
  - prémisse « amorçage de toutes les portes couvert » remplacée par les faits (gate fenêtre/SOL) ;
  - « évite que D1 lise une absence de publication » → « évite qu'une absence de publication soit lue comme une
    absence de données » (D1 ne lit que le préfixe ; la queue de fenêtre est dans l'évaluation) ;
  - « (annexe A, § 10.1) » → « (critère d'arrêt, docs/CONTRAINTES_POST_B4.md § 10.1) » (l'annexe A est le nom
    interne au paquet ; son site adopté est CONTRAINTES § 10).
- AM-04 : porteur `universe.deployment_pairs` {paire de validation: paire de déploiement} (le paquet disait
  « deployment_pair par paire de l'univers » ; le manifeste n'a pas de bloc par paire d'univers). Contrôles :
  clé ∈ univers, forme BASE/COTATION, même base, cotation différente. Le texte du protocole ne nomme pas la clé
  (documentée dans skills/backtest.md).
- AM-07 : texte adapté à R-04 (« toute observation », comparaison en ensembles au candidat apparié, recoupement à
  l'entrée, π_T non élargie) ; « Le manifeste peut la redire » → « Le manifeste la redit » (déclaration exigée par
  le code, inchangée).
- AM-08 : « Le drawdown du moteur (`max_drawdown_pct_engine`) est rapporté » → « que porte le bloc de métriques,
  n'est lu par aucune règle de la chaîne » (la chaîne ne le rapporte pas ; vérifié par grep, aucun site).
- AM-14 (§ F.2 b) : « avant toute lecture des séries » → « avant toute lecture, séries comprises » (harmonisé
  avec AM-20 : « le refus de contrat évalué avant toute lecture […] vient en premier par construction » ; R-08).
- AM-16 (§ F.2 e) : « B_effectif publié par combinaison ; un rapport qui cite une borne sans le B_effectif de sa
  combinaison est incomplet » intégré à la phrase existante qui publiait B_effectif (§ 0.7 : une règle, un site),
  au lieu d'une seconde phrase dans le paragraphe du plafond ; ajout (R-08) : borne nulle ⟺ suite retenue vide.
- AM-15 (§ F.2 b, c, d) : précisions R-09 écrites au 8a/8b (tirage, index de paire, n_jours, un seul chemin, qui
  calcule / ce que la chaîne rejoue), puis complétées au **8c après le STOP du 23/09** (décision Bruno) :
  - (c) **ordre des opérations** : `(Σ log1p(r) × 365) / n_jours`, expression numpy écrite en entier ; le
    **noyau suit le texte** (il calculait `Σ × (365 / n_jours)` : ~1 réplication sur 20 différait au bit) ;
  - (b) environnement en **quatre champs nommés avec leurs sources**, `libc` vide sur macOS (→ § J item 12) ;
    `returns_bench` = exactement {dd, σ} et environnement exact (champ en trop compris) entrent au **contrat**
    (R0) ; bloc absent = erreur de forme ;
  - (d) suite Δ* publiée dans l'ordre `b = 1 … B`, écartées retirées ; sérialisation par le `repr` le plus
    court qui se relit à l'identique (convention de `canon`, § A.1 bis) ; séries de longueurs différentes →
    rejeu inexécutable, § I.1 ligne 2, code 2 ;
  - (e) plafond : « aucune borne n'est publiée » → « aucune borne n'est citée par le verdict » ; l'évaluation
    porte la borne de toute suite retenue non vide.
- AM-10 (§ B.2) : texte du paquet appliqué tel quel ; R-05 (noms et contrôle `at == T` dans le code).
- AM-11 (§ B.4) : « `positions == 0` » → « bloc présent qui ne liquide rien (`trades == 0`, estampille nulle) »
  (R-06).
- AM-12 (§ B.8) : R-07 — c3 NON VÉRIFIABLE → R1 dans la table des actions ; `liquidation_normalised` `null`
  « non établi » ; « Ce qu'exige validé » : c1, c5 DÉCLARÉ sur une évaluation réelle, NON VÉRIFIABLE toléré en
  exercice synthétique ; `stamp_cell` NON VÉRIFIABLE satisfait à vide ajouté à la ligne d'action ; « un refus
  précède toute raison » ajouté à la phrase de coexistence.
- AM-18 (§ H.1) : libellé R1 étendu « clause 3 en échec ou non vérifiable » (R-07), sur deux lignes du bloc.
- AM-19 (§ I.1 ligne 10 bis, § B.3) : « ou non vérifiable » (R-07) ; phrase de gate sur le bloc contradictoire
  ajoutée au § B.3 ; l'abrogation de la convention du 21/09 est écrite dans le § B.3 (le paquet la disait
  hors citation).
- AM-20 (§ I.1) : la phrase du paquet « les conventions du 21/09 […] et du 22/09 sont ratifiées » se
  contredisait (une convention abrogée n'est pas ratifiée) : le texte ratifie celle du 22/09 et dit celle du
  21/09 abrogée. Frontière lignes 2 / 15 complétée par renvoi : bloc contradictoire (§ B.3) et valeur que le
  rejeu ne retrouve pas (§ F.2 d) → ligne 15 ; contrat d'instrument rompu et rejeu inexécutable (§ F.2 b, d)
  → ligne 2.
- AM-13, AM-17, AM-21 : textes du paquet appliqués tels quels (§ C.5 : « Quatre tests » → « Cinq tests »).
- AM-22 (§ J) : items 1, 10, 11 tels quels ; item 12 réécrit selon R-09 (rejeu complet) — le paquet disait
  « la chaîne lit la borne » ; précision de Bruno au GO : limite macOS sans effet tant que producteur et
  chaîne tournent sur le serveur (recette C2), règle d'exploitation = garantie, pas le champ libc.
- AM-23 (§ K.1) : tel quel.
- Annexe A (CONTRAINTES § 10) : date d'adoption 2026-09-23 ; R-11 (scission de la ligne
  A_NO_ADMISSIBLE_CANDIDATE) ; phrase d'auteur complétée « adopté le 2026-09-23 avec la révision v2.1 » ;
  renvoi au § 10 ajouté dans l'en-tête de CONTRAINTES.
- AM-24 (§ L.1) : R-10 — ligne 0 à six entrées ; le paquet sortait `candles.json` de l'énumération en le
  disant « entrée du producteur de couverture, pas de la chaîne » : faux, `c3_benchmark` le lit (`--candles`) ;
  la phrase sur le producteur de couverture n'est pas reprise (non vérifiée). « La règle est appliquée en tête
  de c3_continuity comme de c3_verdict » ajouté. Outillage : ajout dérivé du § B.8 (c1/c5 NON VÉRIFIABLE sur
  une évaluation réelle → violation), hors plan, signalé au commit.
- AM-25 (§ L.2) : tel quel. AM-26 (§ L.3, § L.4) : le paragraphe « Portée : C3a » est écrit une fois, en tête du § L.3 (il couvre les deux listes) ; le § L.4 y renvoie en une ligne — le paquet l'ajoutait « en tête des deux sections », ce qui l'écrivait deux fois (§ 0.7).
- AM-27 (§ M) : index régénéré par un script hors dépôt, depuis le texte (sections hors historique d'amendements et hors § M) : 12 lignes changent. Prémisse du paquet fausse : « E2 gagne § F.2 (e) » — ni le texte d'AM-16 du paquet ni le texte appliqué ne citent E2 au § F.2 (e) ; E2 garde § A.8, § H.0. Seuils : capital en unités de cotation, fenêtre de la première campagne ajoutée, E2 et écartées « par combinaison ».
- § K.1 (AM-23) : après l'insertion, « Elle peut être prise » renvoyait au critère ; devient « La décision peut être prise » (clarté, sens inchangé). § F.2 (d) : « rejeu inexécutable, erreur de forme (ligne 2) » — vocabulaire de la frontière du § I.1 v2.1 (le (e) emploie « erreur d'entrée » pour la ligne 15, texte v2.0).

### La porte intermédiaire du 23/09, et le commit 8c

Au STOP qui suivait AM-15, le § F.2 relu contre le noyau du rejeu ne suffisait pas comme spécification du
producteur : un producteur fidèle au texte pouvait être déclaré en violation. Six points ont été remis et
tranchés (table ci-dessus). Le premier est un défaut que la règle 3 existe pour attraper : la procédure de test
« écrite depuis le texte » avait recopié l'ordre des opérations du noyau, `Σ × (365 / n_jours)`, alors que le
texte écrivait `Σ × 365 / n_jours` — environ une réplication sur vingt différait au dernier bit, et l'égalité
« rejeu = procédure du texte » était verte pour une mauvaise raison. Il a été vu à la relecture du STOP, pas
par un test. Au commit 8c, les fixtures suivent l'expression du texte, et le noyau non corrigé fait échouer 64
tests de la suite C3 ; les témoins de 8c sont vérifiés par mutation (six mutants, six détectés), comme les deux
tests de chaîne réécrits au commit 8a (deux mutants, détectés).

---

## Table de correspondance brief → amendements

| Brief | Objet | Amendement |
|---|---|---|
| A | Conventions d'outillage datées 21/09 et 22/09 ; rapport § 7 items 1, 2, 4, 5, 7, 10, 13, 14 ; état `NOT_VERIFIABLE` de `stamp_cell` | AM-11, AM-13, AM-15, AM-17, AM-19, AM-20, AM-21, AM-22, AM-25 ; item 7 : déjà couvert (§ « Vérifié, sans amendement ») |
| B1 | Ligne run `R1_NOT_NORMALISED` à I.1 | AM-19 (origine), renvois § B.3 et § H.1 |
| B2 | E2 conjonctive sur les six distributions | AM-09, AM-16 |
| B3 | MDD journalier des deux côtés, aucune tolérance | AM-08 |
| B4 | `candles.json` hors énumération § L.1 | AM-24 |
| B5 | Clés `_btc` → `_base` dans l'export | AM-06 |
| B6 | Levée du confinement `synthetic` | AM-24 |
| B7 | Preuve de départ à plat déclarative | AM-10, AM-22 |
| B8 | `decision_timeframes` dérivés | AM-07 |
| B9 | Critère d'arrêt méta | AM-23 + annexe A |
| C1 | Profondeur 2019 de la base USDT | AM-05 (fait de données, pas de clause propre) |
| C2 | Transposition BTC/USDT → BTC/USDC Bybit | AM-01, AM-04, AM-22 |
| C3 | Aucune reconstruction des 8 semaines 1w | aucun amendement (§ « Vérifié, sans amendement ») |
| C4 | Dette 19 hors première campagne | aucun amendement |
| C5 | Fenêtre 2021-03-01 → 2026-06-29, ancrage 70 % | AM-02, AM-03, AM-05 |

**Convention de ce paquet.** Chaque amendement porte : la clause visée, le texte avant (cité), le texte après,
le motif en une phrase, l'impact outillage (fichier, comportement changé ou « aucun »), le test attendu
(rouge-avant si un comportement change). « Aucun » en impact veut dire : le texte rejoint le code, et le test
existant qui encode ce comportement est cité comme témoin. Les numéros de ligne de la table § I.1 ne sont
**jamais renumérotés** : une ligne nouvelle est « 10 bis », parce que « ligne 15 » est cité au § F.2 (e),
§ F.7 et § H.1.

---

## AM-00 — En-tête : bloc d'amendements v2.1

**Clause.** En-tête du document (encart « Statut : GELÉ ») et section « Amendements — révision de gel ».

**Avant.** L'en-tête décrit la révision de gel du 21/09 et le chantier C3a ; la section « Amendements » liste les
trois corrections A, B, C de la révision de gel.

**Après.** L'encart de statut garde son texte et reçoit, en tête, un paragraphe :

> **Révision v2.1 — amendée le <date d'adoption>.** Vingt-huit amendements datés (AM-00 à AM-27), `docs/amendements_c3_v2.1.md`,
> adoptés au gate d'amendement (Bruno, Astra, Claude). Nouveau sha256 : `<calculé à l'application, jamais avant>`.
> Le sha256 de v2.0, `9b62915069e59e9b0f35120c60a77f48a72b278aa9102b3096dfcb8dc25e23c2`, reste celui que porte
> tout manifeste C3a ; un manifeste v2.1 est une nouvelle variante (§ A.6).

La section « Amendements — révision de gel » est renommée « Amendements — révision de gel (v2.0) » et une
section « Amendements — v2.1 » la précède, qui contient la table de correspondance ci-dessus et renvoie au
paquet pour les textes.

**Motif.** Le protocole exige qu'un amendement soit daté et lisible depuis le document lui-même.

**Impact outillage.** `scripts/audit/c3_common.py:protocol_descriptor` **[v]** `:824-829` épingle le sha256 du
fichier dans chaque artefact : aucun changement de code, le nouveau sha entre seul dans les artefacts produits
après application. Les fixtures et tests qui comparent un sha attendu de v2.0 (s'il en existe) sont à
régénérer, non à tolérer.

**Test attendu.** `test_c3_common.py` : le descripteur recalculé égale le sha256 du fichier livré ; aucun sha en
dur dans les tests (un `rg` sur `9b6291…` doit rendre zéro occurrence hors documentation).

**Statut proposé.** À adopter, dernier appliqué (le sha se calcule après tous les autres).

---

## AM-01 — § 0.5 : le capital `C` en unité de cotation, pas en USDC

**Clause.** § 0.5, table « Trois nombres décisionnels », ligne « Capital de référence `C` ».

**Avant.**

> | Capital de référence `C` des simulations et du comparateur | **1000 USDC** | contrat (`starting_balance` des runners) |

**Après.**

> | Capital de référence `C` des simulations et du comparateur | **1000 unités de la monnaie de cotation de la paire du manifeste** (USDC à la cible Bybit ; USDT sur la base de validation Binance, transposition déclarée § A.6) | contrat (`starting_balance` des runners) |

**Motif.** La première campagne tourne sur `BTC/USDT` (C2, C5) ; écrire « USDC » ferait échouer D5
(« capital égal à celui du manifeste ») ou, pire, laisserait passer une lecture où 1000 USDC et 1000 USDT sont
silencieusement confondus.

**Impact outillage.** Aucun : `c3_common` lit le capital comme un `Decimal` sans unité **[v]**
`c3_common.py` (`manifest.capital`, utilisé par `c3_continuity.py:365`).

**Test attendu.** Aucun nouveau ; témoin existant : D5 sur le capital (`test_c3_entry.py`, capital du manifeste ≠
capital de l'observation → `R0_INVALID_RUN`).

**Statut proposé.** À adopter.

---

## AM-02 — § A.3 : la fenêtre déclarée de la première campagne

**Clause.** § A.3, bloc de calcul de l'ancrage et paragraphe « La fenêtre n'est pas élargie ».

**Avant.**

```
ancrage T = début + F × (fin − début)
F = 0,70
fenêtre déclarée : 2023-04-01T00:00:00Z → 2026-04-01T00:00:00Z
⇒ T = 2025-05-07T04:48:00Z          (préfixe 767,2 j · période évaluée 328,8 j · fenêtre 1096 j)
```

> **La fenêtre n'est pas élargie.** Des données existent depuis 2021-01 **[v]** `docs/CONTRAINTES_POST_B4.md` § 7,
> mais élargir la fenêtre maintenant changerait le cas de référence pendant la construction du protocole. Le
> protocole note que **le choix de fenêtre est un second levier de shopping**, au même titre que l'ancrage, et que
> la règle « bornes du manifeste, déclarées avant évaluation » le ferme.

**Après.**

```
ancrage T = début + F × (fin − début)
F = 0,70
fenêtre déclarée (v2.1, première campagne) : 2021-03-01T00:00:00Z → 2026-06-29T00:00:00Z
⇒ T = 2024-11-22T04:48:00Z          (préfixe 1362,2 j · période évaluée 583,8 j · fenêtre 1946 j)
```

> **Historique.** La fenêtre de v2.0, `2023-04-01Z → 2026-04-01Z` (`T = 2025-05-07T04:48Z`), était la fenêtre
> de référence de la construction du protocole, et elle n'a servi qu'à cela : aucune sélection n'a été produite
> sous elle (§ L.1, § D.3). Elle reste citée aux § 0.2, § A.8 et § D.3 comme fait historique.
>
> **La fenêtre de la première campagne est déclarée ici, et elle ne bouge plus.** Borne basse au 2021-03-01,
> première date où l'amorçage de toutes les portes — 1 w avec 50 semaines de profondeur comprise — est
> couvert par la base USDT importée depuis le 2019-01-01 (SOL depuis le 2020-08-11) **[v]**
> `results/data_inventory_usdt_2019_20260923/inventory.md`. Borne haute au 2026-06-29, dernière semaine
> hebdomadaire publiée : la série 1 w s'arrête au 2026-07-06 et Vision n'a pas publié 2026-07/08 ; finir la fenêtre
> **avant** le trou de queue évite que D1 lise une absence de publication comme une absence de données. Ces
> deux bornes sont écrites dans `docs/RESEARCH_LOG.md` et dans le manifeste gelé **avant tout run** ; changer de
> fenêtre est **une nouvelle campagne** et non une variante de celle-ci (annexe A, § 10.1).
>
> **Le choix de fenêtre est un second levier de shopping**, au même titre que l'ancrage, et la règle
> « bornes du manifeste, déclarées avant évaluation » le ferme. Il est interdit de déplacer une borne après
> avoir constaté quoi que ce soit de la période évaluée.

Le paragraphe « **Il est interdit de déplacer `F` après avoir constaté la longueur de la période évaluée.** »
est conservé tel quel. La divulgation de provenance de `F` est conservée telle quelle.

**Motif.** C5 : la fenêtre est un levier de shopping, donc elle s'écrit dans le protocole amendé avant tout run,
pas dans un fichier de campagne où on pourrait la retoucher.

**Impact outillage.** Aucun changement de code : `c3_anchor` recalcule `T` depuis les bornes du manifeste
**[v]** `c3_anchor.py` (règle § A.3, « jamais accepté comme paramètre libre »). Les fixtures synthétiques qui
portent la fenêtre v2.0 restent valides comme fixtures : le protocole ne fixe pas la fenêtre des fixtures, il
fixe celle de la campagne. Une fixture de campagne v2.1 est ajoutée.

**Test attendu.** `test_c3_anchor.py` : pour le manifeste `2021-03-01Z → 2026-06-29Z`, `F = 0,70`,
`T = 2024-11-22T04:48:00Z` exactement, préfixe 1362,2 j, aucun arrondi ; un manifeste qui déclare `T` en dur
est ignoré ou refusé selon la règle existante (témoin : test I-A.6 recalcul).

**Statut proposé.** À adopter (décision C5 prise, ne pas rouvrir).

---

## AM-03 — § A.4 : les quatre estampilles admissibles, recalculées pour l'ancrage v2.1

**Clause.** § A.4, table « Dernière observation admissible ».

**Avant.**

> | TF | Dernière observation admissible à `T = 2025-05-07T04:48Z` |
> |---|---|
> | 5 min | `2025-05-07T04:45Z` |
> | 4 h | `2025-05-07T04:00Z` |
> | 1 j | `2025-05-07T00:00Z` |
> | 1 w | `2025-05-05T00:00Z` (le lundi 5 mai) |

**Après.**

> | TF | Dernière observation admissible à `T = 2024-11-22T04:48Z` |
> |---|---|
> | 5 min | `2024-11-22T04:45Z` |
> | 4 h | `2024-11-22T04:00Z` |
> | 1 j | `2024-11-22T00:00Z` |
> | 1 w | `2024-11-18T00:00Z` (le lundi 18 novembre) |

Le reste de la section est inchangé : la règle vaut, pas les quatre valeurs, et l'arithmétique « aucune bougie
ne clôture à 04:48 » tient pour ce `T` comme pour le précédent — `0,7 × 1946 j = 1362,2 j`, et `0,2 j` font
encore 04:48.

**Motif.** Les valeurs sont « ce que la règle donne à l'ancrage déclaré » ; l'ancrage change, elles changent.

**Impact outillage.** Aucun : calculées par `c3_anchor` depuis `T` **[v]** (règle « jamais écrites en dur »).

**Test attendu.** `test_c3_anchor.py` : les quatre estampilles ci-dessus pour `T = 2024-11-22T04:48Z`, dérivées,
non codées en dur ; le cas limite « `T` coïncide avec une estampille » reste couvert par son test existant.

**Statut proposé.** À adopter.

---

## AM-04 — § A.6 : la transposition déclarée entre paire de validation et paire de déploiement

**Clause.** § A.6, liste des clauses du registre de variantes (après le point « S'y ajoutent un identifiant… »).

**Avant.** Le § A.6 ne connaît qu'une paire par candidat, celle de l'identité canonique (§ A.2).

**Après.** Ajout d'un point :

> - **Transposition déclarée.** Un manifeste peut déclarer, par paire de l'univers, une **paire de
>   déploiement** distincte de la **paire de validation** quand, et seulement quand, l'actif de base est le
>   même et seule la monnaie de cotation diffère (première campagne : validation `BTC/USDT`, `ETH/USDT`,
>   `SOL/USDT` sur la base Binance ; déploiement `*/USDC` sur Bybit EU). La transposition est **écrite une fois,
>   ici, comme déclaration** : elle repose sur le même argument que la transposition de site Binance → Bybit
>   déjà admise par le projet — même actif de base, fees, spread et slippage de la cible mesurés sur la paire
>   de déploiement (`CONTRAINTES` § 2) et déclarés au manifeste. **L'écart de peg entre les deux stablecoins
>   n'est pas modélisé** : c'est un non-mesurable déclaré (§ J, item 11). L'identité du candidat (§ A.2) garde
>   `pair = paire de validation` ; la paire de déploiement entre dans le manifeste, donc dans l'empreinte de la
>   variante, et **n'entre pas** dans l'identité du candidat.

**Motif.** C2 : la transposition doit être lisible dans le protocole, sinon un `validé` sur USDT serait lu comme
un `validé` sur USDC sans que personne n'ait écrit le pont.

**Impact outillage.** `c3_common.load_manifest` : champ optionnel `deployment_pair` par paire de l'univers
(liste blanche `OPTIONAL_FIELDS` **[v]** `c3_common.py:225-237`, à étendre), validé de forme (même actif de
base : préfixe avant `/` identique) ; il entre dans `sig(canon(manifeste))` par construction puisque le manifeste
entier est haché. Aucune autre lecture.

**Test attendu.** `test_c3_common.py` (rouge-avant) : un manifeste avec `deployment_pair: "BTC/USDC"` pour
`BTC/USDT` est accepté et change l'empreinte de variante ; `deployment_pair: "ETH/USDC"` pour `BTC/USDT`
(actif de base différent) → erreur d'entrée, code 2.

**Statut proposé.** À adopter (décision C2 prise).

---

## AM-05 — § A.8 D2 : la note « Conséquence de D2 sur la fenêtre déclarée », réécrite pour la base USDT

**Clause.** § A.8, encart « Conséquence de D2 sur la fenêtre déclarée, écrite plutôt que découverte ».

**Avant.**

> **Conséquence de D2 sur la fenêtre déclarée, écrite plutôt que découverte.** La fenêtre du § A.3 commence au
> 2023-04-01, et l'amorçage 1 d / 1 w remonte alors dans les trous 2022-23 des données (`CONTRAINTES` § 7). […]
> **La borne basse de la fenêtre est donc un levier sur D2 autant que sur l'ancrage**, et c'est une raison de
> plus de la déclarer au manifeste avant toute évaluation.

**Après.** L'encart est conservé en entier sous le titre « **Conséquence de D2 sur la fenêtre de v2.0 (historique)** »,
et un second encart le suit :

> **Conséquence de D2 sur la fenêtre de v2.1, écrite plutôt que découverte.** La fenêtre de la première
> campagne commence au 2021-03-01 sur la base USDT Binance, importée du 2019-01-01 (BTC, ETH) et du 2020-08-11
> (SOL) au 2026-09-01, six timeframes (5 m, 15 m, 1 h, 4 h, 1 j, 1 w), contiguë hors maintenances Binance
> inférieures à un jour, un trou 4 h de deux bougies le 2019-05-15 hors de toute fenêtre, huit estampilles 1 w
> isolées **[v]** `results/data_inventory_usdt_2019_20260923/inventory.md`. L'amorçage 1 w à 50 semaines est
> donc couvert au début du préfixe pour BTC et ETH par construction ; pour SOL, 2020-08-11 + 50 semaines tombe
> avant le 2021-03-01 de justesse, et **c'est D2 qui le dit, pas cette note** : la note déclare ce que la lecture
> des données laisse attendre, l'outil mesure. Une paire dont un timeframe de décision n'est pas amorcé au
> 2021-03-01 sort par D2 sur ses candidats, et la clause de promotion du § I.1 s'applique telle quelle.
> **Aucune reconstruction des estampilles 1 w manquantes n'est faite tant que D1 passe** (décision C3 du
> 23/09) ; si D1 échoue sur le 1 w, la reconstruction depuis le 1 d est une décision séparée, chiffrée, en rows
> marquées dérivées, jamais silencieuse.

**Motif.** C5 et C1 : la note de v2.0 décrivait une conséquence qui n'existe plus sur la nouvelle base ; la laisser
seule ferait lire le § F.6 comme une prophétie sur une fenêtre qui n'est plus celle de la campagne.

**Impact outillage.** Aucun.

**Test attendu.** Aucun nouveau ; témoin : D2 sur fixtures (`test_c3_select.py`, `test_c3_entry.py`).

**Statut proposé.** À adopter.

---

## AM-06 — § A.7 : les clés de quantité en unité de base sont suffixées `_base` (B5)

**Clause.** § A.7, table de liste blanche, ligne « Comptabilité », et § A.8 D6.

**Avant.**

> | Comptabilité | `liquidation[<préfixe>]`, entier |

**Après.**

> | Comptabilité | `liquidation[<préfixe>]`, entier. **Contrat de forme des quantités en actif de base** : les clés `amount_base`, `residual_trade_base`, `dust_written_off_base`, `inventory_divergence_base`, dans le bloc et dans chaque lot, **quelle que soit la paire** ; un bloc qui porte une clé suffixée par le nom d'un actif (`_btc`, `_eth`, …) est une erreur de forme (§ I.1, ligne 2). Le renommage vit dans la couche d'export du runner ; le moteur `scripts/backtest.py` est intouché |

**Motif.** B5 : le moteur écrit `_btc` pour toutes les paires par convention littérale (rapport § 7 item 6) ; un
protocole multi-paires ne peut pas lire `amount_btc` sur `SOL/USDT` sans faire mentir un nom.

**Impact outillage.** `scripts/audit/c3_common.py` : lecture des clés `residual_trade_btc`,
`dust_written_off_btc`, `inventory_divergence_btc` **[v]** `:1656-1676` et `amount_btc` par lot **[v]** `:1747`
→ `_base`. Fixtures synthétiques renommées. Côté producteur (C3b, hors ce paquet) : renommage dans la couche
d'export de `run_p7_grid_search.py` ou du runner conforme, pas dans `backtest.py`.

> Le brief B5 nomme `amount_base` seul. Ce paquet étend le suffixe aux trois autres clés du bloc, pour qu'il n'y
> ait qu'une règle ; si le gate préfère limiter le renommage à `amount_base`, l'amendement se réduit à cette clé
> et les trois autres gardent `_btc` avec une note de convention littérale.

**Test attendu.** `test_c3_common.py` (rouge-avant) : un bloc de liquidation avec `amount_btc` est refusé code 2
avec le nom de la clé attendue dans le message ; un bloc `_base` passe les identités et la preuve par lot.

**Statut proposé.** À adopter (portée des quatre clés à confirmer au gate).

---

## AM-07 — § A.8 D2 : les timeframes de décision sont dérivés des paramètres effectifs (B8)

**Clause.** § A.8, clause D2 et sa justification.

**Avant.**

> | **D2** | Amorçage au **début du préfixe** | `sufficient == True` sur **chaque timeframe qui alimente une porte de décision** de la stratégie du candidat | candidat | qualité des données |

**Après.** Ligne inchangée. Ajout, sous « **D2 — justification** », d'un paragraphe :

> **La liste des timeframes de décision est dérivée, jamais déclarée.** Pour un candidat, « chaque timeframe
> qui alimente une porte de décision » est la liste que **la stratégie elle-même** dérive de ses paramètres
> effectifs (pour la famille grid : `bear_protection_mode` et `bias_1d` décident si `regime_1d` et la porte 1 w
> vivent), par une méthode de classe pure, testée, **sans changement de comportement du moteur**. Le producteur
> exporte cette liste **par candidat** dans l'observation (`decision_timeframes`). Le manifeste peut la redire
> par stratégie ; **un désaccord entre la liste exportée et la liste déclarée est une violation** (§ I.1,
> ligne 15), jamais un arbitrage. Une observation réelle sans `decision_timeframes` est une erreur d'entrée
> (§ I.1, ligne 2) : D2 ne peut pas être mesurée sur une liste absente.

**Motif.** B8 : aujourd'hui le manifeste déclare les timeframes par stratégie et le candidat peut les
surcharger **[v]** `c3_common.py:1121-1154` ; une liste déclarée à la main est exactement le genre de champ
qu'on ajuste pour faire passer D2.

**Impact outillage.** `c3_common.load_manifest` : la déclaration par stratégie devient une déclaration
recoupée, la surcharge par candidat devient **obligatoire pour une observation réelle** (`synthetic: false`)
et reste optionnelle pour les fixtures ; `c3_select` : désaccord exporté / déclaré → violation ligne 15. Côté
stratégie (C3b, `src/`, hors ce paquet) : classmethod `decision_timeframes(effective_params) -> tuple[str, ...]`.

**Test attendu.** `test_c3_select.py` (rouge-avant) : observation qui exporte `("4h",)` sous un manifeste qui
déclare `("4h", "1d", "1w")` → code 1, violation nommée ; `test_c3_entry.py` : observation réelle sans
`decision_timeframes` → code 2.

**Statut proposé.** À adopter.

---

## AM-08 — § A.9 : toute quantité de risque décisionnelle est recalculée sur `equity_daily` (B3)

**Clause.** § A.9, après la liste de départage ; renvoi ajouté au § J item 4.

**Avant.** Le § A.9 nomme `max_drawdown_pct_daily` du préfixe sans dire d'où la chaîne le tient ; le § J item 4
dit que le drawdown intrabar « reste diagnostic ».

**Après.** Ajout au § A.9 :

> **D'où viennent les quantités de risque.** Le drawdown quotidien du candidat, son écart-type quotidien, et
> les mêmes grandeurs du comparateur et de tout blend apparié (§ C.4) sont **recalculés par l'outillage sur
> `equity_daily` du préfixe**, avec la même fonction et le même échantillonnage des deux côtés. La valeur
> `max_drawdown_pct_daily` enregistrée dans le bloc de métriques est **rapportée** à côté du recalcul, avec
> l'écart ; **cet écart n'est ni classé ni borné** — la NAV exportée est un `float`, l'écart est un résidu de
> représentation, et lui donner un seuil serait inventer une classe (§ 0.5) pour un nombre qui ne décide de
> rien. Le drawdown du moteur (`max_drawdown_pct_engine`, intra-bougie) est rapporté et **n'entre dans aucune
> comparaison** (§ J, item 4).

**Motif.** B3 : le brief demandait une tolérance ; il n'en faut pas, parce que les décisions lisent le recalculé et
que le MDD moteur mesure autre chose.

**Impact outillage.** Aucun : `c3_select` lit le recalculé et publie `mdd_report{recorded, recomputed, abs_diff,
note}` **[v]** `c3_select.py:285-299` ; `c3_benchmark` apparie sur `rec.mdd_daily` **[v]** `c3_benchmark.py:488`.

**Test attendu.** Aucun nouveau ; témoins : `test_c3_select.py:193` (`abs_diff == 0.0` sur fixtures exactes) et
`:705` (écart float rapporté « non classé »).

**Statut proposé.** À adopter.

---

## AM-09 — § A.13 E2 : conjonctive sur les six distributions rééchantillonnées (B2)

**Clause.** § A.13, table des conditions, ligne E2, et paragraphe « E2 — ce qu'il attrape ».

**Avant.**

> | **E2** | La distribution rééchantillonnée de `Δ*` porte **au moins deux valeurs distinctes** sur les réplications retenues | garde-fou méthodologique |

**Après.**

> | **E2** | **Chacune des six** distributions rééchantillonnées de `Δ*` — une par combinaison `L × appariement` du § F.2 (h) — porte **au moins deux valeurs distinctes** sur ses réplications retenues. Une seule distribution constante suffit à faire échouer E2 | garde-fou méthodologique |

Ajout à « E2 — ce qu'il attrape » :

> **Pourquoi conjonctive.** `validé` exige une borne strictement positive dans les six combinaisons (§ H.1).
> Une distribution constante ne porte pas de borne estimable : sur cette combinaison-là, le test « borne > 0 »
> n'est ni vrai ni faux, il est **inévaluable**. Une conjonction de six tests dont un est inévaluable n'est pas
> « partiellement vraie » ; elle est inévaluable, et l'issue est `inconclusif (F_NOT_ESTIMABLE)`. E1, elle, ne
> porte que sur la trajectoire évaluée, unique, et reste une seule condition.

**Motif.** B2 : l'outillage évalue aujourd'hui E2 sur **une** suite `delta_stars` **[v]**
`c3_verdict.py:234-243`, alors que les bornes sont lues sur six combinaisons **[v]** `:177-193`.

**Impact outillage.** Comportement changé. Format de l'artefact d'évaluation : `delta_stars`, `discarded` et
`B_effectif` deviennent **par combinaison** (`replications: {"10:dd": {delta_stars, discarded}, …}`, six
clés exactement, les mêmes que `bounds`) ; `B` reste unique (contrat § F.2 b). `c3_verdict._estimability_of`
itère sur les six, applique `cc.estimability` par combinaison (fonction inchangée), E2 = conjonction, le
plafond de réplications écartées (AM-16) par combinaison ; le résumé imprime six `distincts` et six
`B_effectif`. `c3_continuity` ne lit pas ces champs. Fixtures régénérées.

**Test attendu.** `test_c3_verdict.py` (rouge-avant) : évaluation dont cinq distributions varient et une est
constante, portes Q passées, six bornes positives → **aujourd'hui** `validé` est constructible si la suite unique
varie ; **après** : `inconclusif (F_NOT_ESTIMABLE)`, code 0. Cas miroir : six distributions variables → E2 vrai.
Forme : `replications` avec cinq clés, ou une clé hors des six → code 2.

**Statut proposé.** À adopter.

---

## AM-10 — § B.2 : la preuve de départ à plat, spécifiée (B7)

**Clause.** § B.2, ligne d'état et paragraphe « C3b doit donc spécifier une preuve… ».

**Avant.**

> *État : **NON VÉRIFIABLE** sous les artefacts actuels.*

> **C3b doit donc spécifier une preuve de départ à plat, pas déplacer des colonnes.** Ce que cette preuve doit
> établir, sans quoi la clause reste non vérifiable : qu'à l'instant `T`, **avant** tout traitement, le cash vaut
> le capital déclaré, la quantité détenue est nulle, et aucun ordre n'est en attente. **Tant que cette preuve
> n'est pas spécifiée, C3b n'est pas un « simple changement de runner »**, et ce document ne le présente pas comme
> tel. Le travail reste sous gate humain et sous invariant de confinement `compare-ab --strict`.

**Après.**

> *État : **DÉCLARÉ**, sous la preuve spécifiée ci-dessous ; **NON VÉRIFIABLE** quand elle est absente.*

> **La preuve de départ à plat — spécifiée ici, produite par C3b.** Le runner capture, **avant le traitement de
> la première bougie du run d'évaluation**, l'objet `flat_start_proof = {at: T, cash: C, qty: 0, pending: 0}`,
> et exporte `first_fill_at`, l'estampille du premier remplissage du run, qui doit être **strictement postérieure
> à `T`** (§ C.3). L'outillage contrôle la cohérence de l'objet (`at == T`, `cash == C` du manifeste,
> `qty == 0`, `pending == 0`) et `first_fill_at > T`. **Cette preuve vaut `DÉCLARÉ`, jamais `VÉRIFIÉ`** : elle
> est produite par le programme dont elle décrit l'état, et l'outillage n'a aucun moyen indépendant de la
> recalculer. `validé` n'exige pas mieux que `DÉCLARÉ` sur cette clause (§ B.8), et le rapport le dit avec ce
> mot. Un objet absent laisse la clause `NON VÉRIFIABLE` ; un objet incohérent la met en échec, et l'artefact
> déclare alors lui-même une rupture du contrat § B — refus `R0_INVALID_RUN` (§ B.8). Le travail de C3b reste
> sous gate humain et sous invariant `compare-ab --strict`.

Les deux paragraphes « *`equity_daily[...].values[0] == capital` ne prouve rien* » et « *L'identité … ne prouve
pas l'inventaire nul* » sont conservés : ils disent pourquoi la preuve déclarative est la seule disponible.

**Motif.** B7 : le protocole exigeait de C3b une preuve spécifiée ; la spécifier dans le protocole est ce qui
empêche C3b de la spécifier dans le code.

**Impact outillage.** Aucun sur la lecture : `c3_continuity.clause_1_flat_start` **[v]** `c3_continuity.py:95-…`
et `clause_5` **[v]** `:242-…` implémentent déjà cette sémantique (absent → `NOT_VERIFIABLE`, cohérent →
`DECLARED`, incohérent → `FAILED`). Côté producteur (C3b) : capture et export.

**Test attendu.** Aucun nouveau ; témoins : tests c1/c5 de `test_c3_continuity.py` (trois états).

**Statut proposé.** À adopter.

---

## AM-11 — § B.4 : une évaluation sans liquidation terminale ne rompt pas l'assertion de cellule

**Clause.** § B.4, dernier paragraphe (« *Deux limites mesurées, à porter au contrat* »).

**Avant.**

> […] Le protocole **asserte**, sans jamais le supposer, que cette estampille et la borne finale tombent dans la
> **même cellule de la grille quotidienne** ; sinon `E_STAMP_MISMATCH`.

**Après.**

> […] Le protocole **asserte**, sans jamais le supposer, que cette estampille et la borne finale tombent dans la
> **même cellule de la grille quotidienne** ; sinon `E_STAMP_MISMATCH`. **Quand il n'y a pas d'estampille** —
> le bloc de liquidation est présent, `positions == 0`, l'inventaire est nul à la borne par le jeu de la
> stratégie elle-même — l'assertion est **satisfaite à vide** : il n'y a rien à situer, et rien n'a été
> liquidé hors cellule. Cet état est rapporté `NON VÉRIFIABLE` (aucune estampille), **il ne produit pas
> `E_STAMP_MISMATCH`**, et il ne bloque pas `validé`. Un bloc de liquidation **absent** est un autre cas : c'est
> D6 et la clause 3 (§ B.3), pas celle-ci.

**Motif.** L'outillage traite aujourd'hui tout état de `stamp_cell` autre que `VERIFIED` — donc aussi
`NOT_VERIFIABLE` — comme `E_STAMP_MISMATCH` **[v]** `c3_verdict.py:476-477` ; une configuration qui finit à
plat d'elle-même rendrait `inconclusif` pour une assertion qu'elle ne peut pas violer.

**Impact outillage.** Comportement changé : `c3_verdict._continuity_actions`, `stamp_state == "FAILED"` au lieu
de `!= "VERIFIED"` ; `c3_continuity.stamp_cell_block` **[v]** `c3_continuity.py:187-200` inchangé (il produit
déjà `NOT_VERIFIABLE` pour `positions == 0`). Le résumé `stamp_same_daily_cell` reste dérivé (`VERIFIED` seul),
et il ne branche aucune action.

**Test attendu.** `test_c3_verdict.py` (rouge-avant) : le cas paramétré `stamp_NOT_VERIFIABLE` **[v]**
`test_c3_verdict.py:2336-2342` attend aujourd'hui `E_STAMP_MISMATCH` ; il attend après une issue économique
(`validé` si le reste passe). Le cas `stamp_FAILED` est inchangé.

**Statut proposé.** **À trancher au gate.** Le brief classe `NOT_VERIFIABLE` de `stamp_cell` en ratification ; ce
paquet dit qu'il y a une décision, et propose la satisfaction à vide. L'alternative — garder `E_STAMP_MISMATCH`
— se défend seulement si l'on tient qu'une évaluation sans inventaire terminal n'a pas exercé la liquidation et
qu'on ne veut rien conclure d'elle ; mais c'est alors une clause d'activité post-ancrage, que le § A.8 D3 refuse
par principe.

---

## AM-12 — § B.8 (nouvelle) : états des clauses de continuité et lecture par le consommateur

**Clause.** § B, nouvelle section B.8, placée après B.7 ; le § H.1 y renvoie pour « l'état de la continuité ».

**Avant.** Le § B définit cinq clauses et leur état de vérifiabilité « sous les artefacts actuels » ; les états
admissibles par clause, l'agrégat, les résumés et les actions de verdict vivent dans un plan hors dépôt (§ 6.4)
et dans les docstrings de `c3_continuity` et `c3_verdict` **[v]** `c3_continuity.py:10-32`, `c3_verdict.py:52-57`.

**Après.** Nouvelle section :

> ### B.8 États des clauses, agrégat, et ce que le verdict en fait
>
> **C'est la section d'origine des états de continuité et des actions qu'ils commandent (§ 0.7).**
>
> Quatre états, et quatre seulement : `VÉRIFIÉ` (recalculé par l'outillage depuis les données), `DÉCLARÉ`
> (affirmé par le producteur, contrôlé cohérent, non recalculable), `NON VÉRIFIABLE` (l'artefact ne porte pas
> de quoi statuer), `ÉCHEC`. **Liste close par clause**, des deux côtés — producteur `c3_continuity` et
> consommateur `c3_verdict` — et un état hors de la liste de sa clause est une valeur hors liste close (§ I.1,
> ligne 2) :
>
> | Clause | États admissibles | Pourquoi pas les autres |
> |---|---|---|
> | c1 départ à plat (§ B.2) | `NON VÉRIFIABLE`, `DÉCLARÉ`, `ÉCHEC` | jamais `VÉRIFIÉ` : preuve déclarative |
> | c2 aucune réinitialisation (§ B.4) | `DÉCLARÉ`, `ÉCHEC` | le bloc `invocation` est obligatoire, donc jamais « non vérifiable » ; `single_call` n'est pas recalculable |
> | c3 liquidation costée (§ B.3) | `VÉRIFIÉ`, `NON VÉRIFIABLE`, `ÉCHEC` | jamais `DÉCLARÉ` : seule la preuve par lot la vérifie ; identités exactes sans lots → `NON VÉRIFIABLE` |
> | c4 amorçage à `T` (§ B.5) | `VÉRIFIÉ`, `ÉCHEC` | recalculée (`sufficient`), rien d'autre n'est possible |
> | c5 première exécution (§ C.3) | `NON VÉRIFIABLE`, `DÉCLARÉ`, `ÉCHEC` | `first_fill_at` est déclaratif |
> | bloc `stamp_cell` (§ B.4) | `VÉRIFIÉ`, `ÉCHEC`, `NON VÉRIFIABLE` | aucune estampille → satisfaite à vide (§ B.4) |
> | bloc `comparator` (§ C.5) | `VÉRIFIÉ`, `ÉCHEC` | cinq tests booléens et la fenêtre recoupée ; tout vrai ou non |
>
> **Agrégat.** L'état agrégé des clauses est la **pire** clause, par la précédence
> `ÉCHEC > NON VÉRIFIABLE > DÉCLARÉ > VÉRIFIÉ`. Il est **imprimé**, et il ne commande **aucune action** : les
> actions se branchent sur les clauses.
>
> **Résumés dérivés, jamais recopiés.** Les résumés lisibles (`warmup_anchor_ok`, `benchmark_comparable`,
> `stamp_same_daily_cell`, `liquidation_normalised`) et l'agrégat sont **recalculés par le consommateur depuis
> les états des clauses**, puis recoupés au déclaré ; une contradiction déclaré / dérivé est une violation
> (§ I.1, ligne 15). Le verdict **lit tout** — les cinq clauses, les deux blocs, les portes, les six bornes —
> **avant** de prendre un chemin ; il ne conjoint qu'après avoir tout lu et typé.
>
> **Actions, par clause.**
>
> | Constat | Action |
> |---|---|
> | l'évaluation ne porte pas la configuration retenue (§ H.1) | refus `R0_INVALID_RUN` |
> | c1, c2 ou c5 en `ÉCHEC` | l'artefact déclare lui-même une rupture du contrat § B → refus `R0_INVALID_RUN` (§ I.1, ligne 2) |
> | c3 en `ÉCHEC` | issue `inconclusif (R1_NOT_NORMALISED)`, portée run (§ I.1, ligne 10 bis) |
> | c4 en `ÉCHEC` | `D_WARMUP_ANCHOR` (§ I.1, ligne 12) |
> | `comparator` en `ÉCHEC` | `E_NO_BENCHMARK` (§ I.1, ligne 10) |
> | `stamp_cell` en `ÉCHEC` | `E_STAMP_MISMATCH` (§ I.1, ligne 11) |
>
> Quand plusieurs constats coexistent, la raison portée est celle de la liste de priorité du § H.1.
>
> **Ce qu'exige `validé`** sur la continuité : c1 `DÉCLARÉ`, c2 `DÉCLARÉ`, c3 `VÉRIFIÉ`, c4 `VÉRIFIÉ`, c5
> `DÉCLARÉ`, `comparator` `VÉRIFIÉ`, `stamp_cell` `VÉRIFIÉ` ou `NON VÉRIFIABLE`. Ni c1 ni c5 en
> `NON VÉRIFIABLE` : une évaluation réelle qui ne porte pas sa preuve de départ à plat ou son premier
> remplissage n'est pas admise (§ L.1). En exercice synthétique (§ L.1), l'agrégat `VÉRIFIÉ` est
> inconstructible par la table ci-dessus, et c'est voulu.

**Motif.** Rapport § 7 items 12, 13, 14 : ces règles existent dans le code et dans un plan hors dépôt ; le
§ 0.7 veut qu'elles aient une section d'origine dans le protocole.

**Impact outillage.** Aucun hormis AM-11 (stamp `NON VÉRIFIABLE`) et AM-19 (c3 `ÉCHEC` → `R1`) : la table
recopie `cc.CLAUSE_ADMISSIBLE_STATES`, `STAMP_CELL_ADMISSIBLE_STATES`, `COMPARATOR_ADMISSIBLE_STATES`,
`CONTINUITY_SEVERITY` **[v]** `c3_common.py:943-964` et `_continuity_actions` **[v]** `c3_verdict.py:449-478`.

**Test attendu.** Témoins existants : `TABLE_6_4` de `test_c3_verdict.py` (20 lignes, attendu et appui par
ligne) — **l'appui de chaque ligne est réécrit vers § B.8** au lieu du plan hors dépôt ; le test « agrégat
`VERIFIED` inconstructible sur 108 combinaisons » reste.

**Statut proposé.** À adopter.

---

## AM-13 — § C.5 : la fenêtre du comparateur d'évaluation est recoupée par la chaîne

**Clause.** § C.5, table des quatre tests.

**Avant.** Quatre tests : jours forward-fillés, observation admissible aux deux bornes, compte de rendements,
finitude. Aucun ne dit **sur quelle fenêtre** le comparateur d'évaluation a été construit.

**Après.** Une cinquième ligne et un paragraphe :

> | Fenêtre du comparateur d'évaluation | `[T, fin]` exactement, `T` recalculé par `c3_anchor` | un comparateur construit par le producteur sur une autre fenêtre — le producteur ne connaît pas `T`, il ne fait que déclarer ses bornes |

> **Le producteur déclare, la chaîne recoupe.** Le comparateur d'évaluation est construit hors chaîne (§ L.1,
> pas 0) par un producteur qui ne connaît pas `T` ; il déclare ses bornes, et `c3_verdict` les compare à
> `[T, fin]`. Une discordance rend le comparateur **non comparable** (`E_NO_BENCHMARK`), **sans violation** :
> le producteur n'a pas menti, il a construit autre chose que ce que ce manifeste demande. Un `window_ok`
> déclaré qui contredit le recoupement est, lui, une violation (§ B.8, résumés dérivés).

**Motif.** Rapport § 7 item 13 : règle en vigueur **[v]** `c3_verdict.py:366-414`, absente du texte.

**Impact outillage.** Aucun.

**Test attendu.** Témoin : tests `window_ok` de `test_c3_verdict.py` (discordante → `E_NO_BENCHMARK` ; déclaré ≠
dérivé → violation).

**Statut proposé.** À adopter.

---

## AM-14 — § F.2 (b) : un paramètre de la procédure hors contrat est un contrat rompu, évalué avant toute lecture

**Clause.** § F.2 (b), fin du paragraphe.

**Avant.** « […] Classe de `L` et de `B` : qualité des données ; classe de la graine : contrat. »

**Après.** Ajout :

> **Les valeurs de `L`, `B` et le niveau de la borne sont des contrats d'instrument au sens de D5** : un
> artefact d'évaluation qui déclare `B ≠ 10 000`, une longueur de bloc hors `{10, 21, 42}` ou une combinaison
> manquante ou surnuméraire est un **contrat rompu** — `R0_INVALID_RUN`, code 2, rien n'est publié (§ I.1,
> ligne 2) — et ce contrôle est fait **avant toute lecture des séries** : un `B` hors contrat accompagné d'un
> compteur contradictoire ou d'un non-fini dans une suite rééchantillonnée sort en refus de contrat, jamais en
> violation par accident d'ordre de lecture. Précédent : `rejeu_validate_analysis.b02_frozen_parameters`.

**Motif.** Rapport § 7 item 2 : règle en vigueur **[v]** `c3_verdict.py:228-233`, absente du texte.

**Impact outillage.** Aucun ; AM-09 étend le contrôle de forme aux six clés de `replications`.

**Test attendu.** Témoin : `test_c3_verdict.py`, `B ≠ BOOTSTRAP_B` → code 2 avant tout parsing (deux cas :
compteur contradictoire, non-fini).

**Statut proposé.** À adopter.

---

## AM-15 — § F.2 (d) : la chaîne reçoit les bornes, elle ne les recalcule pas — dit une fois

**Clause.** § F.2 (d), après la formule.

**Avant.** Le § F.2 fixe la procédure et la formule ; il ne dit pas **qui** la calcule.

**Après.** Ajout :

> **Qui calcule.** La procédure est **exécutée par le producteur d'évaluation** (C3b), qui exporte, par
> combinaison, la suite `Δ*` retenue, le compteur de réplications écartées et la borne. La chaîne (§ L.1)
> **recalcule ce qu'elle peut** — `B_effectif` depuis la longueur de la suite, E1 et E2 depuis les séries — et
> **lit** la borne, qu'elle ne peut pas recalculer sans rejouer le tirage. Une borne déclarée qui ne serait pas
> celle de la suite fournie n'est donc pas détectable par la chaîne ; c'est un non-mesurable déclaré (§ J,
> item 12), et la reproductibilité bit à bit du producteur (§ I.2 I-C, graine du manifeste) est ce qui en tient
> lieu.

**Motif.** L'outillage lit `bounds` et recalcule l'estimabilité **[v]** `c3_verdict.py:177-246` ; le texte
laissait croire que la chaîne exécutait le bootstrap.

**Impact outillage.** Aucun.

**Test attendu.** Aucun nouveau ; témoin : `_bounds_all_positive` (six clés, finitude avant comparaison).

**Statut proposé.** À adopter.

---

## AM-16 — § F.2 (e) : le plafond de réplications écartées s'applique par combinaison

**Clause.** § F.2 (e), paragraphe « Le plafond, et ce qu'il vaut ».

**Avant.**

> **Le plafond, et ce qu'il vaut.** Au-delà de **10 réplications écartées sur 10 000** — soit un `B_effectif`
> inférieur à 9 990 — l'inférence est déclarée **inutilisable** : issue `inconclusif (F_NOT_ESTIMABLE)`, et
> **aucune borne n'est publiée**. […]

**Après.**

> **Le plafond, et ce qu'il vaut.** Au-delà de **10 réplications écartées sur 10 000** — soit un `B_effectif`
> inférieur à 9 990 — **sur l'une quelconque des six combinaisons** `L × appariement`, l'inférence est déclarée
> **inutilisable** : issue `inconclusif (F_NOT_ESTIMABLE)`, et **aucune borne n'est publiée**. `B_effectif` est
> publié **par combinaison** ; un rapport qui cite une borne sans le `B_effectif` de sa combinaison est incomplet.
> […]

**Motif.** Conséquence de AM-09 : six distributions, six compteurs.

**Impact outillage.** Couvert par AM-09.

**Test attendu.** Couvert par AM-09 (cas : cinq combinaisons à 0 écartée, une à 11 → `F_NOT_ESTIMABLE`).

**Statut proposé.** À adopter.

---

## AM-17 — § H.1 : statuts de sélection, table provenance × retenue

**Clause.** § H.1, paragraphe « Le vocabulaire des statuts est lui aussi clos ».

**Avant.** Le paragraphe liste les statuts possibles de sélection (`SÉLECTION_VALIDE`, `SÉLECTION_DESCRIPTIVE`,
`ABSTENTION`) sans dire comment ils se calculent.

**Après.** Ajout :

> **Comment le statut de sélection se calcule**, par `c3_select`, et se recoupe par `c3_verdict` :
>
> | Configuration retenue ? | Provenance | Statut | Raison de chaîne |
> |---|---|---|---|
> | oui | `clean` | `SÉLECTION_VALIDE` | — |
> | oui | `contaminated` ou `unknown` | `SÉLECTION_DESCRIPTIVE` | `P_PROVENANCE` |
> | non | quelconque | `ABSTENTION` | `A_NO_ADMISSIBLE_CANDIDATE` ou `A_BELOW_FLOOR` ; sous contamination, `P_PROVENANCE` la précède par priorité |
>
> Un statut déclaré par `c3_select` que `c3_verdict` ne redérive pas de la sélection et de la provenance est une
> violation (§ I.1, ligne 15).

**Motif.** Rapport § 7 item 4.

**Impact outillage.** Aucun.

**Test attendu.** Témoin : tests de statut de `test_c3_select.py` et recoupement de `test_c3_verdict.py`.

**Statut proposé.** À adopter.

---

## AM-18 — § H.1 : la liste des raisons, `R1_NOT_NORMALISED` à sa place de raison run

**Clause.** § H.1, liste fermée des raisons par ordre de priorité.

**Avant.**

```
…
D_WARMUP_ANCHOR             amorçage défaillant à l'ancrage d'évaluation
E_NO_BENCHMARK              benchmark non constructible ou non comparable
E_STAMP_MISMATCH            estampille de liquidation et borne finale en cellules distinctes
F_NOT_ESTIMABLE             estimabilité post-ancrage en défaut, ou aucun candidat estimable
F_CANNOT_SEPARATE           la borne ne sépare pas l'effet de zéro dans les six combinaisons
R1_NOT_NORMALISED           D6 : liquidation terminale non normalisée
D_NOT_ADMISSIBLE            D1 ou D5
C_COVERAGE                  D3 échoue, ou D3 est inapplicable
```

**Après.**

```
…
D_WARMUP_ANCHOR             amorçage défaillant à l'ancrage d'évaluation
R1_NOT_NORMALISED           liquidation terminale non normalisée : D6 sur un candidat ; clause 3 en échec sur l'évaluation
E_NO_BENCHMARK              benchmark non constructible ou non comparable
E_STAMP_MISMATCH            estampille de liquidation et borne finale en cellules distinctes
F_NOT_ESTIMABLE             estimabilité post-ancrage en défaut, ou aucun candidat estimable
F_CANNOT_SEPARATE           la borne ne sépare pas l'effet de zéro dans les six combinaisons
D_NOT_ADMISSIBLE            D1 ou D5
C_COVERAGE                  D3 échoue, ou D3 est inapplicable
```

Ajout, après « Lecture de la liste » :

> `R1_NOT_NORMALISED` précède `E_NO_BENCHMARK` parce que le comparateur est apparié sur le risque réalisé du
> candidat (§ C.4), que la liquidation terminale déplace ce risque (§ B.3), et qu'un comparateur construit
> contre une NAV non normalisée n'est pas le comparateur du protocole : le défaut d'instrument se lit avant le
> défaut du comparateur qu'il a contaminé.

**Motif.** B1 : en queue de liste, `R1_NOT_NORMALISED` n'était atteignable que comme raison candidat, donc jamais
comme raison de chaîne ; la ligne run (AM-19) lui donne une position.

**Impact outillage.** `c3_common.REASON_PRIORITY` **[v]** `c3_common.py:529-543` réordonnée.

**Test attendu.** `test_c3_common.py` (rouge-avant) : la liste égale celle du § H.1 v2.1, ordre compris (le test
existant qui recopie l'ordre v2.0 passe au rouge).

**Statut proposé.** À adopter.

---

## AM-19 — § I.1 : ligne 10 bis, `R1_NOT_NORMALISED` de portée run (B1)

**Clause.** § I.1, table unique ; renvois : § B.3 (dernier paragraphe), § H.1 (AM-18), § B.8 (AM-12).

**Avant.** La table ne porte `R1_NOT_NORMALISED` qu'en ligne 6 (portée candidat, D6 sur le préfixe). Le cas
« clause 3 de continuité en échec à l'évaluation » n'a aucune ligne, et l'outillage le sort par
`UndefinedIssueError` → code 2, rien publié — convention d'outillage datée du 21/09 **[v]**
`c3_verdict.py:470-471`, `c3_common.py:196`.

**Après.** Nouvelle ligne, entre 10 et 11 :

> | 10 bis | **Liquidation terminale de l'évaluation non normalisée** : clause 3 du § B en échec sur l'artefact évalué | **run** | `R1_NOT_NORMALISED` | **0** | non ; issue `inconclusif` — aucun verdict directionnel n'est fondé sur cet artefact (§ B.3) |

Ajout au § B.3, après la règle verbatim :

> **Ce que la chaîne en fait.** Sur le préfixe, un candidat sans liquidation costée sort par D6 (§ I.1,
> ligne 6). Sur l'évaluation, une clause 3 en échec est de **portée run** : l'issue est
> `inconclusif (R1_NOT_NORMALISED)`, publiée, code 0 (§ I.1, ligne 10 bis) — un résultat, pas un refus, parce
> que l'artefact est bien formé et dit vrai ; il est seulement hors d'usage décisionnel.

La convention d'outillage du 21/09 (« `UndefinedIssueError` → code 2 ») est **abrogée** par cette ligne.

**Motif.** B1 : une assignation de code hors table n'est pas un état du protocole ; § 0.7 veut que tout code de
sortie vienne de la table.

**Impact outillage.** Comportement changé : `c3_verdict._continuity_actions`, c3 `FAILED` → `reasons.append(
"R1_NOT_NORMALISED")` au lieu de `raise UndefinedIssueError` ; la classe `UndefinedIssueError` reste (garde
générique d'issue non définie), plus aucun site ne la lève pour c3 ; `decide()` porte la raison par priorité
(AM-18). La précédence « contradiction déclaré / dérivé → diagnostic code 1 même avec c3 en échec » (AM-20)
reste vraie et devient triviale : c3 en échec n'est plus un refus.

**Test attendu.** `test_c3_verdict.py` (rouge-avant) : évaluation cohérente avec c3 `FAILED`, tout le reste sain
→ **aujourd'hui** code 2, rien publié ; **après** code 0, `verdict.json` publié, `verdict=inconclusif`,
`raison=R1_NOT_NORMALISED`, `verified: true`. Cas de priorité : c3 `FAILED` et c4 `FAILED` → attendu
`D_WARMUP_ANCHOR`, parce que la liste du § H.1 le place avant `R1_NOT_NORMALISED` ; le test encode l'attendu
depuis la liste, pas depuis le code.

**Statut proposé.** À adopter.

---

## AM-20 — § I.1 : forme du diagnostic, partage des lignes 2 et 15, ordre de constat

**Clause.** § I.1, après le paragraphe « Non-recevabilité et abstention ne sont pas la même chose ».

**Avant.** La table donne les codes ; ni la forme d'un artefact code 1, ni la frontière entre « fourni mais
invalide » (ligne 15) et « absent ou mal formé » (ligne 2), ni l'ordre quand plusieurs constats se succèdent ne
sont écrits.

**Après.** Ajout :

> **Forme d'un diagnostic (ligne 15).** Un artefact de diagnostic est écrit, code 1, et porte `invalide: true`
> et la liste des violations ; il ne porte **ni verdict, ni raison, ni chaîne citable** : une violation n'est pas
> un résultat, et rien de ce qu'un diagnostic contient ne se cite dans un rapport comme une issue.
>
> **Ligne 2 ou ligne 15, la frontière.** Une valeur **fournie** mais non finie ou hors domaine (un `NaN`, un
> infini, un rendement `≤ −1`, un `λ` hors `[0, 1]`) est une violation : ligne 15, code 1. Une valeur **absente,
> nulle, mal typée ou hors liste close** (une chaîne là où un booléen est attendu, un état hors de la liste de
> sa clause, une clé manquante) est une erreur de forme : ligne 2, code 2, **rien n'est écrit** — à l'exception
> de `c3_entry`, qui écrit toujours sa validation, refus compris (§ D.3).
>
> **Ordre de constat.** Après une violation, la violation prime : un refus ou une issue constatés ensuite
> n'effacent pas le diagnostic (code 1). **Sauf lecture inachevable** : une preuve obligatoire absente, nulle,
> mal typée ou hors liste close constatée **après** une violation sort en code 2, rien publié, et les violations
> déjà constatées sont dites sur la sortie d'erreur — un diagnostic se bâtit sur une lecture complète, et une
> lecture inachevable n'en permet aucun. Le refus de contrat évalué **avant toute lecture** (§ F.2 b) n'est pas
> concerné par cet ordre : il vient en premier par construction.

Les conventions d'outillage datées du 21/09 (`UndefinedIssueError`, abrogée par AM-19) et du 22/09 (preuve
absente après violation → code 2) sont **ratifiées** par ce paragraphe, qui en devient la section d'origine.

**Motif.** Rapport § 7 items 1, 10, 14 : trois règles en vigueur, sans site.

**Impact outillage.** Aucun **[v]** `c3_verdict.py:41-50` (docstring « précédence »), `c3_entry` (écrit toujours).

**Test attendu.** Témoins : `test_c3_verdict.py` — diagnostic sans verdict ni chaîne ; violation puis preuve absente
→ code 2, violations sur stderr ; non-fini fourni → code 1 ; absent → code 2.

**Statut proposé.** À adopter.

---

## AM-21 — § I.2 I-A : une assertion sans porteur n'est jamais verte

**Clause.** § I.2, paragraphe « I-A. Validité d'entrée ».

**Avant.** « […] Les assertions sont exécutées **dans un ordre gelé** et tout ce qui suit le premier échec est
marqué **sauté, jamais vert**. Codes : § I.1. »

**Après.** Ajout :

> Une assertion dont l'artefact ne porte **aucun porteur** — un champ que l'export réel ne produit pas, par
> exemple l'intervalle d'exécution ou l'artefact de couverture — est consignée **non assertable**. Elle n'est
> **jamais verte**, elle ne bloque pas les assertions suivantes, et **en fin de I-A toute clause non assertable
> est un refus** `R0_INVALID_RUN` (§ I.1, ligne 2) : une entrée n'est validée pour sélection que si chaque
> clause est assertable et verte. « Non assertable » n'est pas un état intermédiaire tolérable ; c'est le nom
> exact de ce qui manque au producteur.

**Motif.** Rapport § 7 item 5 ; règle en vigueur **[v]** `c3_entry.py:674-690`.

**Impact outillage.** Aucun.

**Test attendu.** Témoin : `test_c3_entry.py`, artefact sans `exec_interval` → I-A refuse en fin, `not_assertable`
listé, jamais `ok: true`.

**Statut proposé.** À adopter.

---

## AM-22 — § J : items 1 et 10 mis à jour, items 11 et 12 ajoutés

**Clause.** § J, items 1, 10 (modifiés), 11, 12 (nouveaux).

**Avant.**

> 1. **Le départ à plat à l'ancrage** (§ B.2). → Déclaré **non vérifiable** ; les champs qui le rendraient
>    vérifiable sont nommés et routés en C3b. **Aucune preuve de substitution n'est proposée.**
>
> 10. **L'état du portefeuille à l'instant `T` lui-même.** […] → Le départ à plat est déclaré **non vérifiable**
>     (§ B.2) ; **aucune preuve de substitution n'est proposée**, et C3b doit **spécifier** une preuve, pas
>     déplacer des colonnes.

**Après.**

> 1. **Le départ à plat à l'ancrage** (§ B.2). → **Déclaré, jamais vérifié** : la preuve `flat_start_proof` est
>    produite par le programme qu'elle décrit et contrôlée cohérente, non recalculée. Ce qui reste non mesurable
>    est l'écart entre l'état déclaré et l'état réel du moteur à `T` ; aucun substitut.
>
> 10. **L'état du portefeuille à l'instant `T` lui-même.** […] → La preuve spécifiée au § B.2 est capturée
>     **avant la première bougie**, donc avant qu'un point d'equity existe ; elle décrit l'état initial et non un
>     état postérieur, et vaut `DÉCLARÉ`.
>
> 11. **L'écart de peg entre la monnaie de cotation de validation et celle de déploiement** (§ A.6,
>     transposition déclarée : USDT Binance → USDC Bybit). → Non modélisé ; la transposition est déclarée avec
>     son argument, les coûts de la cible sont ceux de la paire de déploiement, et aucun facteur de correction
>     n'est appliqué.
>
> 12. **L'exactitude de la borne déclarée par le producteur** (§ F.2 d). → La chaîne recalcule `B_effectif`,
>     E1 et E2, et lit la borne ; ce qu'elle ne peut pas rejouer est couvert par la reproductibilité bit à bit du
>     producteur sous la graine du manifeste (§ I.2 I-C), et par rien d'autre.

**Motif.** B7, C2, AM-15 : trois non-mesurables changent de nature ou apparaissent.

**Impact outillage.** Aucun.

**Test attendu.** Aucun.

**Statut proposé.** À adopter.

---

## AM-23 — § K.1 : renvoi au critère d'arrêt pré-enregistré (B9)

**Clause.** § K.1, paragraphe « Une clôture plus large est possible, mais elle change de nature ».

**Avant.**

> **Une clôture plus large est possible, mais elle change de nature.** Décider d'arrêter une famille entière est
> une **décision de gestion de la recherche** — budget, priorités, cap de deux familles par cycle. Elle peut être
> prise, et elle passe alors par le § 5 et le ticket § 6 de `docs/CONTRAINTES_POST_B4.md`. **Elle est annoncée
> comme telle, avec son auteur et son motif, et n'est jamais déduite d'un verdict de ce protocole.** […]

**Après.** Même paragraphe, avec une phrase ajoutée après « … cap de deux familles par cycle » :

> **Cette décision est pré-enregistrée** : le § 10 de `docs/CONTRAINTES_POST_B4.md` (critère d'arrêt, adopté
> avec la révision v2.1 de ce protocole) dit d'avance quels verdicts de cette chaîne closent une famille, combien
> de familles et combien de temps le projet s'accorde avant de s'arrêter, et ce qui doit exister avant tout ordre
> live. Ce protocole **produit les événements** que ce critère lit — les issues et leurs raisons — et **ne le
> contient pas** : le critère reste une règle de gestion, avec son auteur, hors des § 0 à M.

**Motif.** B9 : le protocole exclut la gestion de recherche de son périmètre (§ 0.3, § K.1) ; le critère vit
donc à côté, et le protocole y renvoie. Le texte du critère est en annexe A de ce paquet.

**Impact outillage.** Aucun en v2.1. Exigence C3b consignée, hors paquet : le registre de variantes (§ A.6)
pourrait refuser l'enregistrement d'une seconde campagne comptée sur une famille close — enforcement mécanique
du § 10.1, à cadrer avec le producteur, pas ici.

**Test attendu.** Aucun.

**Statut proposé.** À adopter, avec l'annexe A.

---

## AM-24 — § L.1 : `candles.json` hors énumération (B4), et la levée du confinement synthétique (B6)

**Clause.** § L.1, ligne 0 de la table et paragraphe « Ce qui est réellement atteignable en C3a ».

**Avant.**

> | 0 | **hors chaîne** | le **manifeste** (§ A.6), les **observations**, et l'**artefact de couverture** (§ A.7) — trois entrées, produites avant, jamais par l'outillage de ce protocole |

> **Ce qui est réellement atteignable en C3a.** L'exécution continue post-ancrage et la procédure d'incertitude
> relèvent de **C3b** (§ B.4, § F.2), et tout artefact réel existant est refusé à l'entrée (§ D.3). En C3a, les
> étapes 5 et 6 ne sont donc exerçables que sur des **fixtures synthétiques**, et les seules issues qu'elles
> peuvent produire sur données réelles sont la **non-recevabilité** et l'**abstention**. `validé` et `réfuté` sont
> **structurellement inatteignables tant que C3b n'a pas livré l'exécution continue** — […]

**Après.**

> | 0 | **hors chaîne** | le **manifeste** (§ A.6), les **observations**, l'**artefact de couverture** (§ A.7) et l'**artefact d'évaluation** (§ F.2, C3b) — quatre entrées, produites avant, jamais par l'outillage de ce protocole. L'artefact de couverture est lui-même produit par un **producteur de couverture** hors chaîne, depuis un export de bougies (`candles.json`, lecture seule de la base) : cet export est une entrée **du producteur de couverture**, pas de la chaîne, et il n'apparaît pas dans cette énumération |

> **Ce qui était atteignable en C3a, et ce qui l'est depuis v2.1.** En C3a, les étapes 5 et 6 n'étaient
> exerçables que sur des fixtures synthétiques, et l'outillage refusait toute évaluation déclarée réelle
> (`evaluation.synthetic: false` → refus). **Ce confinement est levé par cette révision, sous deux conditions
> cumulatives** : le paquet v2.1 adopté (ce texte) **et** un producteur conforme livré par C3b. Une évaluation
> déclarée réelle (`synthetic: false`) est admise **si et seulement si** elle porte `flat_start_proof`,
> `invocation.single_call` et `first_fill_at` (§ B.2, § B.4, § C.3 — les trois clauses déclaratives, en état
> `DÉCLARÉ`) ; il lui en manque une → refus `R0_INVALID_RUN`, code 2, rien publié, avec le nom de ce qui
> manque. Une évaluation synthétique reste admise, préfixe `C3_SYNTH_` et ligne de portée en tête (§ L.2).
> `validé` et `réfuté` deviennent atteignables sur données réelles **par ce chemin et par aucun autre**.

**Motif.** B4 et B6.

**Impact outillage.** Comportement changé : `c3_verdict.require_synthetic` **[v]** `c3_verdict.py:130-141` →
`synthetic: false` admis si les trois porteurs sont présents et bien typés dans l'évaluation, sinon refus avec
la liste des manquants ; ordre inchangé (premier contrôle de `decide()` et de `run_verdict()`). `c3_continuity`
: sa propre lecture de `synthetic` **[v]** `c3_continuity.py:338` suit la même règle. Ligne 0 : aucun impact.

**Test attendu.** `test_c3_verdict.py` (rouge-avant) : `synthetic: false` avec les trois porteurs → chaîne
`C3_<campagne>`, sans ligne de portée synthétique ; `synthetic: false` sans `first_fill_at` → code 2, message
nommant `first_fill_at` ; `synthetic: true` inchangé (préfixe `C3_SYNTH_`). Le test « confinement en tête de
tout chemin de publication » reste et couvre le nouveau refus.

**Statut proposé.** À adopter (B6 : décision prise).

---

## AM-25 — § L.2 : la chaîne, son préfixe, `chain.verified`, la cohérence des enveloppes amont

**Clause.** § L.2.

**Avant.** « Aucun paramètre libre, aucune entrée humaine […] Le rapport cite la chaîne, il ne la paraphrase pas. »

**Après.** Ajout :

> **Préfixe et portée.** Une chaîne d'exercice synthétique est préfixée `C3_SYNTH_` et son artefact porte, en
> première ligne, une portée qui dit qu'elle n'a aucune portée économique ; une chaîne réelle est préfixée `C3_`
> et ne porte pas cette ligne. Le préfixe est dérivé de `evaluation.synthetic`, jamais d'un choix.
>
> **`chain.verified`** signifie **l'intégrité mécanique de la chaîne** : codes de succès enregistrés des étapes
> amont, cohérence interne de chaque enveloppe amont (`ok ⟺ code 0`, `invalide ⟺ code 1`, refus ⟺ code 2 pour
> l'entrée) assertée **avant** d'en lire le succès, empreintes concordantes. Il ne dit rien de la qualité
> économique de l'issue, qui se lit dans `verdict` et `raison` : `verified: true` avec un `inconclusif` est
> cohérent ; `verified: false` accompagne toute violation ; un refus sans violation ne publie rien, donc ne porte
> pas de `verified`.
>
> **Les enveloppes amont disent ce qu'elles ont fait, pas ce qui a réussi.** Une étape enregistre son code de
> sortie dans son artefact ; la sous-commande `chain` invoque chaque étape en processus et **contrôle le code de
> retour effectif** avant de lire l'artefact. Une enveloppe qui se dit `ok` avec un code non nul est une
> violation.

**Motif.** Rapport § 7 items 11, 13, 14 ; règles en vigueur **[v]** `c3_verdict.py:30-40`, `:110-111`, `:702`.

**Impact outillage.** Aucun.

**Test attendu.** Témoins : tests `chain` de `test_c3_verdict.py` (cohérence des enveloppes, `verified`, préfixe).

**Statut proposé.** À adopter.

---

## AM-26 — § L.3, § L.4 : listes de C3a ; C3b déclare les siennes

**Clause.** § L.3 et § L.4, en-tête.

**Avant.** « Hors de cette liste, **aucun fichier n'est créé, modifié ou supprimé** par C3a. La liste est close
par ce document : l'allonger est un amendement au protocole, pas une décision d'implémentation. »

**Après.** Ajout en tête des deux sections :

> **Portée : C3a.** Les listes ci-dessous sont celles du chantier C3a, closes et vérifiées à sa porte pré-merge
> (§ L.5, passée le 2026-09-22). C3b ouvre la zone que C3a gelait — runner, exports, amorçage, `src/` pour la
> méthode de classe du § A.8 D2 — et **déclare sa propre liste close dans son brief**, sous ses propres gates,
> avec son propre diff de contrôle sur tout ce que le brief ne nomme pas. Ce protocole n'énumère pas les fichiers
> de C3b ; il exige qu'ils soient énumérés avant la première ligne, et que `scripts/backtest.py` reste hors
> liste tant que la dette 19 n'est pas ouverte par une décision séparée (C4 du 23/09).

**Motif.** Sans cette portée, le premier commit de C3b viole le § L.4 à la lettre.

**Impact outillage.** Aucun.

**Test attendu.** Aucun.

**Statut proposé.** À adopter.

---

## AM-27 — § M : index régénéré

**Clause.** § M, les deux tables.

**Avant.** Index à la révision v2.0.

**Après.** Régénéré par `rg` à l'application : `R1_NOT_NORMALISED` gagne les sites § B.3, § B.8, § I.1 (ligne 10
bis) ; `E2` gagne § F.2 (e) ; `E_STAMP_MISMATCH` cite § B.8 ; la table des seuils gagne les bornes de la fenêtre
(§ A.3, préférence économique, choix déclaré) et perd rien. **Règle de lecture inchangée** : une colonne de
références vide est une porte que rien n'applique — vérifiée à l'application, avant le calcul du sha.

**Motif.** § M : « régénéré à chaque révision et recollé ici ».

**Impact outillage.** Aucun.

**Test attendu.** Aucun ; contrôle manuel à l'application : aucun symbole sans site de référence.

**Statut proposé.** À adopter, avant AM-00.

---

## Vérifié, sans amendement

| Point | Constat |
|---|---|
| Rapport § 7 item 7 (`C_COVERAGE` raison de D3 ; ordre D3 puis D6) | Déjà écrit : § H.1 (« `C_COVERAGE` D3 échoue, ou D3 est inapplicable »), § A.8 (« dans l'ordre D1 → D6 ») |
| C3 (aucune reconstruction des 8 semaines 1 w) | Fait de données, cité dans AM-05 ; D1 tranche, aucune clause à écrire |
| C4 (dette 19 hors première campagne) | Rien ne change : § B.3 et § J item 2 restent ; AM-26 tient `backtest.py` hors liste |
| « Frontière de confiance » (rapport § 8, à côté d'E2) | **Non traité** : le brief du 23/09 (B2) ne la reprend pas. Si elle désigne autre chose que la conjonction des six bornes, elle doit être nommée au gate ; sinon elle est couverte par AM-09 |

## Ordre d'application proposé

AM-01 → AM-26 dans l'ordre des sections ; puis AM-27 (index) ; puis AM-00 (en-tête et sha). Les amendements à
comportement changé — AM-04, AM-06, AM-07, AM-09/AM-16, AM-11, AM-18, AM-19, AM-24 — portent chacun un test
rouge-avant, observé rouge **avant** la modification du code, dans le même commit que le texte qu'il encode.
Aucune ligne de `scripts/backtest.py`, `run_p6_backtests.py`, `run_p7_grid_search.py`, `p7_grids.py`,
`compute_benchmarks.py` n'est touchée par l'application de ce paquet ; les impacts producteur nommés ici (export
`_base`, `decision_timeframes`, `flat_start_proof`, `replications` par combinaison) sont des **exigences du brief
C3b**, pas des actions de ce paquet.

**Nouveau sha256 attendu : calculé à l'application, jamais avant.** Le protocole amendé est gelé au commit qui
porte les vingt-huit amendements et l'index régénéré ; ce sha est celui que tout manifeste v2.1 porte.

---

## Annexe A — Texte du critère d'arrêt (à insérer en § 10 de `docs/CONTRAINTES_POST_B4.md`)

> ## 10. Critère d'arrêt — pré-enregistré le <date d'adoption v2.1>
>
> Ce paragraphe dit d'avance ce qui fait s'arrêter une famille, ce qui fait s'arrêter la recherche d'alpha du
> projet, et ce qui doit exister avant tout ordre live. Il lit les événements que produit la chaîne C3
> (`docs/protocole_c3.md`, § H, § I.1) et **ne les réinterprète pas**. Il est appliqué par les deux revues
> (Astra, Claude) et par Bruno ; il ne se renégocie pas au vu d'un résultat. Auteur : Bruno, sur proposition
> Claude du 22/09 et 23/09.
>
> ### 10.1 Clôture de famille — un verdict compté, zéro retry
>
> **Une famille est un mécanisme** (§ 6.1). Un autre paramétrage, une autre fenêtre, une autre paire, une
> recombinaison d'indicateurs sont la même famille.
>
> **Un verdict compte** quand la chaîne est allée jusqu'à l'économie :
>
> | Issue C3 | Compte pour la famille |
> |---|---|
> | `validé`, `réfuté` | oui |
> | `inconclusif` — `A_NO_ADMISSIBLE_CANDIDATE`, `A_BELOW_FLOOR`, `F_NOT_ESTIMABLE`, `F_CANNOT_SEPARATE` | **oui** : le périmètre ou l'effet est le résultat (protocole § A.11) |
> | `inconclusif` — `R0_INVALID_RUN`, `P_PROVENANCE`, `D_WARMUP_PREFIX`, `D_WARMUP_ANCHOR`, `R1_NOT_NORMALISED`, `E_NO_BENCHMARK`, `E_STAMP_MISMATCH` ; sorties code 1 et 2 | **non** : défaut d'instrument, de données ou de manifeste |
>
> **Une seule relance** après correction d'instrument, par famille. Un second verdict non compté sur la même
> famille la déclare *non testable sous cet instrument* ; elle est alors **comptée dans le budget du § 10.2**,
> parce que ne pas savoir tester une famille est une information sur le projet.
>
> **Zéro retry-tuning.** Aucune seconde campagne comptée sur la même famille avec d'autres paramètres, une autre
> fenêtre ou un autre univers. Réouverture uniquement sur **hypothèse de mécanisme nouvelle**, documentée, passée
> au ticket § 6 — ce qui en fait, par définition, une autre famille.
>
> **Une seule voie de sortie, prospective.** Si l'issue est `inconclusif (F_CANNOT_SEPARATE)` **et** `Q1 ∧ Q2 ∧ Q3`
> passent **et** `Δ̂ > 0` dans les six combinaisons — seule la borne manque —, la configuration retenue, et elle
> seule, est inscrite à une **évaluation différée** au sens du protocole § D.1 (échantillon jamais consulté) :
> fenêtre `[fin du manifeste, date déclarée]`, sur données gelées après le verdict, **au moins 12 mois de
> données neuves**, mêmes paramètres, même procédure § F.2, une fois. La date et le manifeste sont écrits au
> moment du verdict, pas après. Elle ne consomme pas de budget de familles ; elle est la seule chose qui survit
> au cap temporel du § 10.2, parce que c'est une date à attendre, pas un chantier.
>
> ### 10.2 Alpha-stop projet — trois familles ou le 2027-09-30
>
> - **Budget familles : trois**, à mécanisme distinct — grid (cycle en cours) + un cycle complet du cap § 7. Au
>   delà, la multiplicité que le protocole déclare ne pas corriger (§ F.3) cesse d'être négligeable.
> - **Budget temps : 12 mois à compter du gel de v2.1**, échéance **2027-09-30**. Le compteur démarre au gel et
>   non au premier verdict, pour que la construction d'instrument entre dans le budget qu'elle a déjà consommé.
> - **Jalon : premier verdict réel (grid) avant le 2027-01-31.** Manqué → **gel de l'instrument en l'état** :
>   plus aucun amendement, plus aucune exigence producteur, la campagne grid part dans les 30 jours avec ce qui
>   existe, et son verdict compte.
> - **Déclencheur** : trois familles comptées sans `validé`, **ou** le 2027-09-30 — le premier atteint.
>   Conséquence : le trader reste éteint définitivement sous ce dispositif ; le projet est requalifié
>   (plateforme de données, instrument de recherche, pièce de portfolio). Réouverture uniquement par décision
>   écrite, avec son auteur et son motif — jamais déduite d'un verdict.
> - **`validé`** suspend le compteur temps pendant le paper (règles B5, `ROADMAP.md`) et la décision qui le suit.
>   Un paper qui échoue à ses critères pré-enregistrés vaut verdict de la famille : comptée, close, compteur
>   relancé. Un `validé` ne rouvre pas le budget familles.
>
> ### 10.3 Kill-switch live — structure exigée, chiffres dérivés
>
> Avant le premier ordre live, le ticket de déploiement fixe trois seuils, **dérivés de l'artefact de la campagne
> validée et d'aucune autre source** : (i) drawdown live rapporté au `max_drawdown_pct_daily` de la fenêtre
> d'évaluation ; (ii) rendement réalisé annualisé rapporté à la borne basse `LB` du § F.2 ; (iii) durée maximale
> sans cycle achevé rapportée à la cadence observée sur le préfixe. Les multiplicateurs et horizons sont écrits,
> gelés, et ne se renégocient pas. Aucun nombre n'est fixé ici : chacun sort des chiffres que la chaîne aura
> publiés.

**Entrée `docs/RESEARCH_LOG.md` (datée du jour de l'adoption)** : « Critère d'arrêt pré-enregistré, § 10 de
`CONTRAINTES_POST_B4.md`, adopté avec v2.1 du protocole C3. Première campagne : famille grid, fenêtre
2021-03-01 → 2026-06-29, ancrage 70 %, BTC/ETH/SOL sur USDT Binance, manifeste à geler avant tout run. »
