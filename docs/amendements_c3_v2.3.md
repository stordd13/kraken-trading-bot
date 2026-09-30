# Amendements au protocole C3 — v2.2 → v2.3 (mini-amendement « évaluation différée »)

> **Statut : ADOPTÉ le 2026-09-30** (Bruno). Ce paquet est un texte : il se lit sans code, son application est
> décrite à la section « Application » et se cadre après le gel (discipline « texte d'abord »).
>
> **Rappel de la règle qui autorise ce document — § 0.7 et en-tête du protocole.** Toute modification
> postérieure au gel est un **amendement daté**, qui décrit ce qui a changé et pourquoi, et qui **crée une
> nouvelle variante** au sens du § A.6 : un manifeste qui porte le sha256 de v2.3 n'a pas la même empreinte
> qu'un manifeste qui porte celui de v2.2.
>
> Base amendée : `docs/protocole_c3.md`, sha256
> `1bed7696c0b0002b702f34fd549a59fc648968ff2e3056a98d33168bd643292a` (v2.2, commit `662c104`). Sources :
> `results/c3_outillage_v2_2/report.md` § 5 (candidats D7 lot 1 et D3 lot 2), `lot1_chaine/README.md` § 5,
> `lot2_producteur/README.md` § 5, passation du 30/09 § 3, décisions D-A / D-B / D-C (Bruno, cette
> conversation). Faits lus dans le code de l'archive `krakenbot-src-v2_12_0-c3-v2_1-96-g662c104` tagués **[v]**
> avec leur `fichier:ligne`.

## Adoption — 2026-09-30

**Adopté par Bruno le 2026-09-30**, en conversation manifeste, puis au STOP du gel sous les décisions ci-dessous.
Application : branche `feat/c3-amendements-v2.3` depuis `dev` @ `662c104ef8cb5a9b5c7fb04452f7af817cb5a87a`, brief
`agent/AGENT_C3_GEL_V2_3.md` — texte du protocole, phrase compagnon de `docs/CONTRAINTES_POST_B4.md` § 10.1,
consignations du sha et épinglage du test du sha (commit de gel), puis squelette normatif en `xfail` strict (commit
suivant) ; **aucune ligne de `scripts/` ni de `src/`**. Un STOP : au rapport (`results/c3_v2_3_gel/report.md`), avant
merge ; le merge est fait par Bruno. Le reste de ce document est le paquet approuvé le 2026-09-30 ; là où
l'application s'en écarte, cette section le dit, et c'est elle qui fait foi avec le texte du protocole.

### Empreinte du protocole

| Révision | sha256 de `docs/protocole_c3.md` | Commit |
|---|---|---|
| v2.0 (gel du 2026-09-21) | `9b62915069e59e9b0f35120c60a77f48a72b278aa9102b3096dfcb8dc25e23c2` | `d931293` |
| v2.1 (amendée le 2026-09-23) | `9300f4e53bfd36633df6524c2d7ad168a732739ca3dd1765c024cc8a3ccd4129` | `b3524ac` |
| v2.2 (amendée le 2026-09-29) | `1bed7696c0b0002b702f34fd549a59fc648968ff2e3056a98d33168bd643292a` | `ac7710f` (AM-00, dernier commit de texte) |
| v2.3 (ce paquet) | `d030ab239de317f6cba89877d682338fa2001d2a63d231f1a86c519fe87a79e6` | le commit de gel du chantier, qui porte cette section |

Un fichier ne peut pas porter sa propre empreinte (R-01 de v2.1) : le sha v2.3 est consigné ici, dans
`docs/RESEARCH_LOG.md` (entrée 20), `skills/backtest.md` et `CLAUDE.md` ; `c3_common.protocol_descriptor` le
recalcule dans chaque artefact, et `tests/test_scripts/test_c3_common.py` épingle la **dernière** ligne
`**sha256 vX.Y :**` de cette section au fichier. Sous v2.3, `c3_anchor` refuse tout manifeste qui déclare v2.2 ou une
révision antérieure (AM-00, « Conséquence dite ») : les conformités du 30/09, sous v2.2, sont historiques.

### Décisions de gate — conversation manifeste (Bruno, 2026-09-30)

- **D-A** — la date de l'évaluation différée est déclarée au manifeste (`deferred_evaluation.date`) et validée à
  l'ancrage (étape 1), jamais choisie au verdict.
- **D-B** — l'engagement porte sur un descripteur `D`, liste close : `engines` inclus, paramètres de procédure
  (`anchor_fraction`, `uncertainty`) exclus.
- **D-C** — l'empreinte `sig(canon(D))` vit au registre seul : jamais versionnée ni imprimée.
- « Au moins 12 mois » (§ 10.1, AM-01) s'entend **≥ 365 jours** entre `window.end` et `deferred_evaluation.date`.
- Tri v2.3 / v2.4 : entrent en v2.3 le candidat D7 du lot 1 (AM-01), le candidat D3 du lot 2 (AM-02) et le
  renommage du test au nom périmé (« Application », point 2) ; D3, D6, D14 du lot 1 et D6, D7 du lot 2 attendent une
  v2.4.
- Limite assumée : la mécanique du run différé (forme exacte de son manifeste au-delà du descripteur, ancre effective
  sur sa fenêtre) est reportée à un amendement ultérieur, sous la contrainte du descripteur (AM-01, « Limites
  dites »).

### Portée

La voie prospective ne s'ouvre que sur `F_CANNOT_SEPARATE`, rang 11 de la liste fermée du § H.1. Sous provenance
`contaminated` ou `unknown`, `P_PROVENANCE` (rang 2) la précède : l'amendement ne rend la sortie différée atteignable
que pour une campagne `clean`.

### Décisions de gate — STOP du gel (Bruno, 2026-09-30)

| # | Objet | Décision |
|---|---|---|
| G-1 | § A.6, liste « au minimum et sans exception » : le paquet la situait au § A.5 et n'en donnait pas le texte « après » | insertion « **la date de l'évaluation différée** (`deferred_evaluation.date`, ci-dessous) ; » avant « et le **sha256 de ce document** ». Les deux renvois « § A.5 » du paquet (rubrique « Clause » d'AM-01, phrase sous l'« Après ») sont corrigés en « § A.6 » : amendement de la règle « corps intact au caractère près » du brief, décidé à ce gate, borné à ces deux occurrences |
| G-2 | Constat D5 : la phrase qui suit la liste (« Cette liste est exactement ce que la clause D5 asserte… ») couvre désormais la date, que D5 (§ A.8) ne nomme pas | consigné, sans retouche (précédent : la famille, v2.2) |
| G-3 | AM-01, placement : les deux puces « Avant » ne sont pas adjacentes, la puce « À l'étape 1 » les sépare | puces 1 à 3 de l'« Après » à la place de la première ; « À l'étape 1 » intacte ; puces 4 et 5 à la place de la seconde — la seule lecture où « Sur une telle famille » garde son antécédent |
| G-4 | AM-00, forme : le paquet donnait une ligne nue | le contenu de la ligne est coulé dans la forme établie des révisions, en tête du bloc, avant v2.2 : « **Révision v2.3 — amendée le 2026-09-30.** Trois amendements datés (AM-00 à AM-02), `docs/amendements_c3_v2.3.md`, adoptés par Bruno au gate d'amendement du 2026-09-30. **Nouveau sha256 : consigné hors du fichier.** Le sha256 de v2.2 (`1bed7696…292a`) perd son statut d'empreinte courante ; un manifeste v2.3 est une nouvelle variante (§ A.6). » |
| G-5 | Pas de section « Amendements — v2.3 » au protocole, alors que v2.1 et v2.2 en ont une | asymétrie assumée : la correspondance candidats → amendements de v2.3 vit dans ce paquet (sections « Application » et « Adoption ») |
| G-6 | Descripteur `D`, ligne `engines` : « le bloc `engines` du manifeste » — aucun manifeste ne porte ce bloc ; le moteur est déclaré par stratégie (`strategies.<nom>.engine`) | `{strategy: engine}` restreint à la stratégie de la configuration retenue, sur le modèle de `pair_costs` restreint à la paire retenue ; cellule corrigée au paquet et au protocole avant le gel |
| G-7 | Descripteur `D` : ligne `decision_timeframes` ajoutée | la liste effective de la configuration retenue, surcharge par candidat comprise — au verdict dérivée de la retenue, au run différé de l'unique candidat entrant —, **triée par étiquette** : `canon` garde l'ordre des listes et le § A.8 compare ces listes en ensembles, un autre ordre d'écriture ne fait donc pas une autre empreinte ; ligne ajoutée au paquet et au protocole avant le gel |
| G-8 | Table d'empreinte : le paquet portait `662c104` (état mergé) pour v2.2 | historique complet, v2.0 à v2.3 ; la ligne v2.2 porte `ac7710f`, le commit de texte, comme la table de v2.2 l'écrit elle-même : le paquet était inexact sur ce point |
| G-9 | Test d'épinglage `test_aucun_sha_de_protocole_n_est_ecrit_en_dur_dans_l_outillage_ni_les_tests` : il assertait les révisions v2.0 à v2.2 | la liste passe à quatre révisions, docstring à jour : deuxième ligne de test du commit de gel, déclarée ; le contrôle « aucun sha en dur » couvre les quatre empreintes |
| G-10 | Témoin R-17 `test_R17_temoin_sur_une_famille_close_l_empreinte_differee_attendue_est_acceptee`, vert, contredit par AM-01 : il inscrit l'empreinte du manifeste brut | scission en jumeaux (précédent v2.2) : le témoin inscrit le descripteur `D` et devient `xfail` strict ; l'adverse inscrit le descripteur d'une autre configuration et reste vert ; sept tests neufs ; comptes attendus 3 309 passés, 9 xfail, 0 test retiré (critère § 4.3 du brief amendé) |
| G-11 | X4 passe aujourd'hui : l'outillage n'inscrit jamais rien | témoin positif intégré : le même test exige l'inscription quand l'issue ouvre la voie, et son absence sinon ; `xfail` strict |

### Réserves d'application

L'outillage v2.3 n'est pas écrit dans ce chantier (« Application », cadrage après le gel). AM-01 est porté par huit
tests `xfail(strict=True)`, X1 à X8, posés au commit qui suit le gel ; leur attendu est normatif et se dérive du
texte, leur interface d'appel est indicative ; leur levée est l'entrée du chantier d'outillage v2.3.

| # | Attendu (AM-01) | Fichier |
|---|---|---|
| X1 | manifeste sans `deferred_evaluation.date` → refus à l'étape 1, `R0_INVALID_RUN`, code 2 (§ A.6 ; § I.1, ligne 2) | `test_c3_anchor.py` |
| X2 | date à moins de 365 jours après `window.end`, ou illisible → même refus ; 365 jours exactement : accepté | `test_c3_anchor.py` |
| X3 | issue qui ouvre la voie du § 10.1 → `deferred_evaluation {date, variant_key}` inscrit à l'enregistrement de la variante, `date` copiée du manifeste, `variant_key = sig(canon(D))`, en mode `chain` seul | `test_c3_verdict.py` |
| X4 | issue qui n'ouvre pas la voie → aucune inscription (témoin positif intégré, G-11) | `test_c3_verdict.py` |
| X5 | `D` dérivé champ par champ selon le tableau d'AM-01 | `test_c3_verdict.py` |
| X6 | famille au verdict compté portant une inscription : descripteur entrant d'empreinte inscrite → accepté ; toute autre empreinte → `R0_INVALID_RUN`, code 2 (G-10 : le témoin R-17 porte l'attendu, l'adverse R-17 reste vert) | `test_c3_anchor.py` |
| X7 | verdict d'une variante différée acceptée → jamais d'inscription (une fois par famille) | `test_c3_verdict.py` |
| X8 | `load_manifest` lit `deferred_evaluation.date` (datetime) ; forme invalide → erreur de forme, jamais un défaut silencieux | `test_c3_common.py` |

AM-02 : aucun test (comportement inchangé ; les tests R-18 et T1-T15 couvrent ce code de sortie).

### Écarts de rédaction et d'application

- **Texte.** Les blocs « Après » d'AM-01 et d'AM-02 et la phrase compagnon sont appliqués tels quels, aux décisions
  G-1, G-4, G-6 et G-7 près ; vérification : `results/c3_v2_3_gel/tests/texte_conforme.sh` (espaces normalisés).
- **Mise en page.** AM-01 est appliqué au niveau de sous-puce du § A.6, tableau indenté sous sa puce ; une ligne
  blanche sépare chaque puce neuve de sa voisine, comme dans l'« Après » (la sous-liste devient lâche), et aucune n'est
  ajoutée entre « À l'étape 6 » et la première, ni entre la dernière et « L'issue publiée ». AM-02 : la phrase, sans
  ses guillemets, en paragraphe propre sous la table. AM-00 : marques de la forme établie (gras, code).
  `CONTRAINTES` § 10.1 : phrase remplacée en place, paragraphe recoupé sur les deux lignes qui la portaient.
- **Paquet.** Seules transformations du draft (`agent/amendements_c3_v2_3_draft.md`, commité tel que reçu) : le
  statut (ADOPTÉ, mention « draft » retirée), cette section, la section « Empreinte du protocole (à remplir au gel) »
  supprimée et remplacée par la table ci-dessus, et G-1, G-6, G-7 ; hors de ces décisions, le corps est intact au
  caractère près.
- **Index § M.** Régénéré depuis le texte v2.3 par la méthode de v2.2 (`results/c3_v2_2/tests/index_m.py`) :
  identique, aucune ligne à recoller.

**sha256 v2.3 :** `d030ab239de317f6cba89877d682338fa2001d2a63d231f1a86c519fe87a79e6`

## AM-00 — En-tête : bloc d'amendements v2.3

**Clause.** En-tête du protocole, bloc des révisions.

**Après.** Le bloc des révisions ajoute la ligne v2.3 : « v2.3 (amendée le <date du gel>) —
`docs/amendements_c3_v2.3.md` : inscription de l'évaluation différée (date déclarée au manifeste, engagement
par descripteur) ; § I.1 ligne 10 ter (code de sortie du producteur, forme de refus). Nouveau sha256 : consigné
hors du fichier. »

**Motif.** R-01 (v2.1) : un fichier ne peut pas porter sa propre empreinte. Le sha v2.3 est consigné dans ce
document (section « Empreinte », au gel), `docs/RESEARCH_LOG.md`, `skills/backtest.md` et `CLAUDE.md`.

**Conséquence dite.** `assert_declared_protocol` refuse tout manifeste qui ne déclare pas le sha courant **[v]**
`scripts/audit/c3_anchor.py:142-156` : après le gel, les manifestes v2.2 sont refusés à l'entrée. Aucun
manifeste de campagne n'existe encore ; les conformités du 30/09 sont closes et archivées, on n'y retouche pas.

## AM-01 — § A.6 : l'inscription de l'évaluation différée — date déclarée au manifeste, engagement par descripteur

**Clause.** § A.6, application mécanique du critère d'arrêt : la puce « Quand l'issue ouvre la voie de
sortie prospective… » et la puce « Sur une telle famille, seule est acceptée… ». § A.6, déclarations minimales
du manifeste. Phrase compagnon de `docs/CONTRAINTES_POST_B4.md` § 10.1 (hors protocole, éditée au même paquet —
précédent : application v2.1).

**Avant.**

> - Quand l'issue ouvre la voie de sortie prospective du § 10.1, il y inscrit aussi, au moment du verdict, la
>   **date déclarée** et l'**empreinte attendue** `sig(canon(manifeste))` du manifeste de l'évaluation
>   différée.

> - Sur une telle famille, **seule est acceptée** la variante dont l'empreinte est l'empreinte attendue inscrite
>   au verdict. L'évaluation différée est un état du registre, pas une exception de lecture.

CONTRAINTES § 10.1 :

> La date et le manifeste sont écrits au moment du verdict, pas après.

**Après.**

> - Quand l'issue ouvre la voie de sortie prospective du § 10.1, il y inscrit aussi, au moment du verdict, la
>   **date déclarée** — copiée de la clé `deferred_evaluation.date` du manifeste, jamais choisie au verdict —
>   et l'**empreinte attendue** `sig(canon(D))` du **descripteur** `D` de l'évaluation différée, défini
>   ci-dessous. Le manifeste de l'évaluation différée n'est écrit nulle part au verdict : seul son engagement
>   l'est.
>
> - **La clé du manifeste.** `deferred_evaluation.date` : une date, **obligatoire sur tout manifeste**,
>   validée à l'étape 1 : **au moins 12 mois après `window.end`** (§ 10.1, « au moins 12 mois de données
>   neuves ») ; absente, non lisible ou trop proche → `R0_INVALID_RUN`, code 2 (§ I.1, ligne 2). Sur la
>   variante différée elle-même, la clé est déclarée comme sur toute autre et reste sans effet : **la voie
>   prospective ne s'ouvre qu'une fois par famille** — le verdict d'une variante différée n'inscrit jamais
>   d'évaluation différée.
>
> - **Le descripteur `D`**, liste close, sérialisé par `canon` (§ A.1 bis). Chaque champ est dérivé du
>   manifeste de campagne et de la sélection au moment du verdict, et re-dérivé du manifeste entrant au moment
>   du run différé, par la même règle :
>
>   | Champ | Valeur au verdict | Recoupement au run différé |
>   |---|---|---|
>   | `deferred_evaluation_of` | l'empreinte de la variante de campagne (`sig(canon(manifeste))`) | `parent.variant_key` du manifeste entrant |
>   | `family` | la famille du manifeste | idem |
>   | `window` | `{start: window.end de la campagne, end: date déclarée}` | `window` du manifeste entrant |
>   | `candidate` | `{strategy, pair, params}` de la **configuration retenue** (§ A.10 ; identité § A.2 recalculable) | l'unique candidat du manifeste entrant |
>   | `data` | `{exchange, exec_interval, timeframes}` du manifeste | idem |
>   | `engines` | `{strategy: engine}` restreint à la stratégie de la **configuration retenue** (`strategies.<strategy>.engine` du manifeste), sur le modèle de `pair_costs` restreint à la paire retenue | idem, pour la stratégie de l'unique candidat du manifeste entrant |
>   | `decision_timeframes` | la liste effective du manifeste pour la configuration retenue (§ A.8 : surcharge par candidat comprise), **triée par étiquette** — un ensemble, comme au § A.8 | celle de l'unique candidat du manifeste entrant, par la même règle |
>   | `fees` | `{model, taker, pair_costs` restreint à la paire retenue`, pair_costs_file}` | idem |
>   | `min_order_quote` | la valeur du manifeste | idem |
>   | `universe_provenance` | la constante `clean` — § D.1 : l'échantillon différé est postérieur au verdict et gelé après lui, jamais consulté | la provenance déclarée du manifeste entrant |
>
>   **Tout champ hors de cette liste est hors engagement**, et contrôlé au moment du run différé par les règles
>   ordinaires de la version alors en vigueur (journal, protocole courant, valeurs gelées, § F.2). En
>   particulier `research_log_entry`, `run_scope`, `variant_id` et `protocol_sha256` n'entrent pas dans `D`.
>
> - Sur une telle famille, à l'étape 1, l'ancrage **dérive le même descripteur du manifeste entrant, par la
>   même règle**, et **seule est acceptée** la variante dont `sig(canon(D))` égale l'empreinte inscrite au
>   verdict. L'évaluation différée est un état du registre, pas une exception de lecture.
>
> - **Non-divulgation.** L'empreinte différée engage la configuration retenue sur un espace d'hypothèses
>   énumérable : elle est **brute-forçable par construction**. Elle ne vit qu'au registre, inscrite en mode
>   `chain` seul ; elle n'est **jamais imprimée** hors registre, et un registre qui la porte n'est **jamais
>   versionné ni ouvert** (règle de non-lecture).

§ A.6, déclarations minimales : la liste « le manifeste porte donc, au minimum et sans exception » ajoute
`deferred_evaluation.date`.

CONTRAINTES § 10.1, phrase compagnon :

> La date et l'engagement sur le manifeste (l'empreinte du descripteur, protocole § A.6) sont écrits au moment
> du verdict, pas après ; le manifeste différé lui-même est dérivé mécaniquement au moment du run et recoupé
> contre l'engagement.

**Motif.**
- **La ligne v2.2 est inapplicable telle qu'écrite.** L'empreinte d'une variante est `sig(canon(manifeste brut
  entier))` **[v]** `c3_anchor.py:386` (`key = cc.sig(raw)`), qui contient `research_log_entry` — l'entrée
  journal du run différé sera écrite 12 mois et plus après le verdict (règle du journal), donc inconnaissable au
  moment de l'inscription — et `protocol_sha256`, que `assert_declared_protocol` exige égal au sha **courant**
  **[v]** `c3_anchor.py:142-156` : si le protocole évolue entre le verdict et le run différé, l'ancien sha est
  refusé à l'entrée et le nouveau casse l'empreinte. Contradiction interne dans les deux branches.
- **Écrire le manifeste différé en clair au verdict exposerait la configuration retenue** — une sortie du
  chemin sélection — dans un objet persistant. L'engagement par empreinte de descripteur donne le même pouvoir
  de contrainte sans divulgation ; c'est la leçon des 336 octets, appliquée avant l'accident cette fois.
- La date au manifeste (D-A) : pré-engagement maximal — la date existe avant que quiconque ait vu un chiffre —
  et validation à l'ancrage plutôt qu'au verdict, pour refuser un manifeste mal daté avant de brûler le run.
- Clé obligatoire partout plutôt que facultative : une clé facultative absente au moment où l'issue ouvre la
  voie ferait perdre la sortie prospective en silence. Une règle, aucun cas particulier ; sur la variante
  différée elle est inerte par la règle « une fois par famille ».
- L'interface livrée `deferred_evaluation {date, variant_key}` (lot 1, lecture côté ancrage) garde sa forme ;
  ce texte fixe la **valeur** de `variant_key` : `sig(canon(D))`, plus le manifeste brut entier.

**Limites dites.**
- « Mêmes paramètres » (§ 10.1) est engagé par `candidate`, `data`, `engines`, `fees`, `min_order_quote` ; les
  paramètres de procédure (`anchor_fraction`, `uncertainty`) restent hors descripteur : ils sont des **valeurs
  gelées** assertées à toute époque par l'étape 1, quelle que soit la version. La mécanique d'exécution du run
  différé (forme exacte de son manifeste au-delà du descripteur, ancre effective sur sa fenêtre) n'est pas
  spécifiée ici : elle le sera par amendement quand l'échéance approchera, sous la contrainte du descripteur.
- Les `pair_costs` engagés sont ceux de la campagne (« mêmes paramètres ») ; les coûts réels 12 mois plus tard
  peuvent différer — non-mesurable déclaré, même classe que l'écart de peg (§ J).

**Impact outillage — chantier v2.3, cadré après le gel.**
- `c3_verdict` : construction de `D`, inscription `{date, variant_key}` quand l'issue ouvre la voie ; site
  **[v]** `c3_verdict.py:1318-1330` (`registry_inscription`, docstring D7) ; la configuration retenue est déjà
  recoupée par le verdict (C-1).
- `c3_anchor` : validation de `deferred_evaluation.date` à l'entrée ; dérivation de `D` du manifeste entrant et
  comparaison dans `stop_criterion` **[v]** `c3_anchor.py:158-200` (aujourd'hui : comparaison à l'empreinte
  brute entrante).
- `c3_common.load_manifest` : lecture de la clé.
- Tests : jumeaux des règles ci-dessus ; mise à jour de l'adverse « famille close, variante d'une autre
  empreinte refusée » (amendements v2.2, adverses AM-05) ; mutants sur la dérivation de `D`.

## AM-02 — § I.1 : ligne 10 ter — le code de sortie du producteur qui écrit la forme de refus

**Clause.** § I.1, la table unique.

**Avant.** La table ne porte aucune ligne pour la sortie du **producteur** qui écrit l'artefact d'évaluation
sous sa forme de refus (§ C.5) ; la ligne 10 est celle de la chaîne.

**Après.** La table ajoute, entre 10 bis et 11 :

> | 10 ter | **Producteur** : comparateur d'évaluation non constructible — l'artefact d'évaluation est écrit sous sa **forme de refus** (§ C.5), le moteur jamais construit | — | — | **0** | oui ; la chaîne lit la forme et publie la ligne 10 |

Une phrase sous la table : « La ligne 10 ter dit le code de sortie du **producteur** ; la ligne 10 reste celle
de la chaîne. »

**Motif.** Le § I.1 se déclare table unique — « aucun autre passage du document ne redit un code de sortie ;
tous renvoient ici » — alors que le code 0 de cette sortie ne vivait que dans l'outillage **[v]**
`c3b_evaluate.py:33-34`, `:65` (docstrings des codes), comportement livré et prouvé (R-18, lot 2). **Le texte
suit le code, comportement inchangé** (précédent : décisions STOP v2.1). C'est le candidat D3 du lot 2.

**Impact outillage.** Aucun code, aucun test : les tests R-18 et T1-T15 couvrent déjà ce code de sortie.

## Application v2.3 — périmètre du chantier d'outillage (cadrage 4 questions après le gel)

1. AM-01 : verdict, ancrage, manifeste, tests, adverses, mutants (ci-dessus).
2. Renommage du test au nom périmé `…_n_est_pas_rejouable_sous_v21` **[v]** `tests/test_scripts/test_c3_entry.py:709`
   — nom seul, corps intact, déclaré au diff des tests (candidat « brief » du rapport § 5).
3. Rien d'autre : D3, D6, D14 (lot 1), D6, D7 (lot 2) attendent une v2.4 (décision Bruno, 30/09).
