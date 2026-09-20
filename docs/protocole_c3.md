# Protocole de validation chronologique — C3, version 2

> **Statut : SOUMIS AU GATE 2.** Ce document est **gelé au GO humain, et à cet instant précis**. Une fois gelé,
> **rien des § 0 à L ne peut être relu, repondéré, réinterprété ou élargi** — ni pendant l'écriture de
> l'outillage, ni au contact des données. Toute modification postérieure au GO est un **amendement daté**, qui
> décrit ce qui a changé et pourquoi, et qui **crée une nouvelle variante** au sens du § A.6.
>
> Chantier **C3a** — brief `agent/c3a_protocole_chronologique_v2.md`. Branche `feat/c3a-protocole`, depuis `dev`
> @ **`57051cc2a86bf44b90958e1e7b3b58c5de819cfc`**. Aucune ligne d'outillage n'existe au moment où ce document
> est soumis : c'est la condition du gate 2, et il se review **comme un texte**, pas à travers son code.
>
> Les faits lus dans le code ou dans un artefact pendant la rédaction sont tagués **`[v]`** en ligne, avec leur
> `fichier:ligne`. Antériorité obligatoire : `docs/rejeu_grid_prespec.md`, précédent complet d'un protocole
> pré-spécifié qui a tenu. **Ce protocole n'en hérite aucun seuil par transitivité** (§ 0.5).
>
> **C3a terminé ≠ C3 terminé ; C3 terminé ≠ stratégie validée.** C3a livre ce document, l'outillage de sélection
> et ses tests. **C3b** livre l'intégration et la vérification de l'exécution continue. Aucun des deux ne
> sélectionne quoi que ce soit pour le paper.

---

## § 0. Périmètre, question, garde-fous

### 0.1 La question unique

> Une **configuration figée**, choisie à une date d'ancrage en n'ayant lu que le passé, a-t-elle produit sur la
> période postérieure un effet économique que la procédure d'incertitude déclarée sépare de son benchmark
> d'exposition ?

Trois issues, et trois seulement : **`validé`**, **`réfuté`**, **`inconclusif`**. Une quatrième étiquette,
**`descriptif`**, existe au niveau d'une paire ou d'un artefact et ne vote jamais.

### 0.2 Ce que C3 répare

L'audit red-team du 16/09 a rassemblé sous « walk-forward non chronologique » deux choses distinctes :

- **(a) Fuite de sélection.** `select_top_k_per_combo` trie par le Sharpe du segment `test` de la phase 1,
  période `2025-05-07T04:48Z → 2026-04-01Z` **[v]** `scripts/run_p7_grid_search.py:305-310` ; les huit **moitiés de test** des
  fenêtres de la phase 2 couvrent `2024-04 → 2026-04`, les fenêtres complètes couvrant `2023-04 → 2026-04`
  **[v]** `:232-264` et son docstring `:243`. Quatre fenêtres précèdent la période de
  sélection, une la chevauche, **trois y sont incluses**. Le choix est informé par ce qu'il est censé prédire.
  C'est ce défaut que ce protocole répare, **dans la logique de sélection, sans toucher à aucun moteur**.
- **(b) Réinitialisation par segment.** `_run_segment` instancie un moteur neuf par segment **[v]**
  `scripts/run_p7_grid_search.py:726-729`. Traité par le § B, vérifié en C3b.

### 0.3 Hors périmètre, nommé

- **Une procédure qui re-sélectionne périodiquement ses paramètres est hors périmètre de C3a comme de C3b.**
  Elle valide un **objet différent** — une règle, pas une configuration — et ne correspond pas à ce qui est
  déployé : en production une configuration est posée dans `strategies.yaml`, surveillée, et tuée à la main
  (décision 13 du `ROADMAP.md`). Si elle est voulue un jour, c'est une **extension nommée avec sa propre charge
  de validation**, pas une dérive de celle-ci.
- **Le mécanisme de changement de configuration** est hors périmètre, pour la même raison.
- Aucune modification de moteur, de métriques, de fees, ni des critères P6/P7.
- Aucune campagne de backtest de recherche, aucune sélection de stratégie pour le paper, aucune réouverture du
  verdict du rejeu diagnostic grid.
- **Aucun langage de validation économique dans les livrables de C3a.**

### 0.4 Ce qu'un `validé` ne signifie jamais

Ni un déploiement, ni une preuve prospective, ni une autorisation de paper. Il signifie exactement : *sous ce
protocole, sur cette fenêtre déjà explorée, une configuration choisie sans regarder l'avenir a produit un effet
que la procédure déclarée sépare de son comparateur.* La portée est bornée par le § D.

### 0.5 Statut des seuils — aucun héritage automatique

**Aucun seuil numérique de ce document n'est hérité du rejeu par transitivité.** Chacun est un **choix neuf pour
C3**, présenté avec sa justification, sa divulgation, et **sa classe** :

| Classe | Ce que cela veut dire |
|---|---|
| **contrainte mathématique** | Non négociable, dérive de la définition. Exemple : `r > −1` pour que `log1p(r)` existe |
| **qualité des données** | Choix de fiabilité, ajustable, à justifier. Exemple : couverture minimale, tolérance de trou |
| **préférence économique** | Choix du projet, à justifier et à divulguer. Exemple : plancher de rendement |
| **contrat** | Imposé par un contrat de version ou de provenance. Exemple : `metrics_version == 2` |

Le § 0.5 est une règle de lecture : **tout nombre qui entre dans une décision porte sa classe avec lui.** Un
nombre décisionnel sans classe est une erreur de rédaction, pas une convention tacite.

Trois nombres décisionnels qui échappaient à cette règle sont fixés ici, une fois :

| Nombre | Valeur | Classe |
|---|---|---|
| Capital de référence `C` des simulations et du comparateur | **1000 USDC** | contrat (`starting_balance` des runners) |
| Taux sans risque `rf` du comparateur | **0** | préférence économique, convention déclarée (§ J.8) |
| Résidu d'appariement au-delà duquel un `λ` est rejeté (§ C.6) | **10 %** de la cible appariée | qualité des données |

Les bornes de la fenêtre (§ A.3) sont un **choix déclaré**, de classe **préférence économique**, et le document
écrit lui-même qu'elles sont un levier de shopping (§ A.3, § A.8 D2).

### 0.6 Garde-fous d'exécution

- Liste fermée et nommée des fichiers nouveaux ; **diff de contrôle vide** hors cette liste (§ L.3).
- Le script de verdict n'a **aucun paramètre libre et aucune entrée humaine** : deux personnes l'exécutant sur
  les mêmes artefacts obtiennent **la même chaîne**. C'est le contrat de falsifiabilité de ce document.
- Une **découverte annexe se signale, ne se traite pas**.
- Tout rejeu technique, s'il en devenait un nécessaire, est **inscrit à `docs/RESEARCH_LOG.md` avant son
  lancement** (décision 17 du `ROADMAP.md`). **Ce protocole n'en prévoit aucun.**

---

## § A. Ce qui est sélectionné, et quand

### A.1 L'objet sélectionné

**Une configuration figée** — un triplet `(stratégie, paire, paramètres)` — choisie **une fois**, à la date
d'ancrage. La sélection n'utilise que les données antérieures à cette date. La configuration retenue est ensuite
évaluée sur la période postérieure, **en equity continue** (§ B).

### A.1 bis `canon` et `sig` — contrat adopté, et non hérité tacitement

Trois objets de ce protocole reposent sur une empreinte : l'identité d'un candidat (§ A.2), la clé d'une variante
(§ A.6) et la signature de projection (§ A.7). La fonction d'empreinte est **adoptée explicitement**, avec sa
classe **contrat** :

> `canon(x)` est l'image canonique d'une feuille JSON : un `float` devient son `repr` le plus court, un `int` ou
> un `bool` son `repr`, `None` la chaîne `"null"`, une chaîne qui parse comme `Decimal` sa forme normalisée en
> virgule fixe (`"0E-30"` → `"0"`), toute autre chaîne elle-même ; les conteneurs sont parcourus récursivement.
> **Un NaN ou un infini lève**, il ne produit jamais d'empreinte. `sig(x)` est le sha256 du texte JSON
> déterministe (`sort_keys`, séparateurs compacts, `allow_nan=False`) de `canon(x)`.

C'est la définition de `docs/rejeu_grid_prespec.md` § A.1, **adoptée ici comme contrat nommé** et non importée
par transitivité : elle est reprise parce qu'elle est correcte pour cet usage, et le § 0.5 lui donne sa classe.

### A.2 L'identité canonique d'un candidat

L'identité d'un candidat est **`sig(canon({strategy, pair, params}))`**, et **pas `params_hash` seul**.

*Pourquoi.* `params_hash` **[v]** `scripts/run_p7_grid_search.py:149-152` ne hache que le dictionnaire de
paramètres. Il ne suffit comme clé que dans un univers **explicitement limité à une stratégie et une paire** —
ce qui n'est pas le cas général et ne doit jamais être supposé. Deux candidats de stratégies différentes peuvent
partager un `params_hash` sans être le même objet. **Deux candidats partageant l'identité canonique sont une
erreur d'entrée (exit 2), jamais un tirage au sort.**

### A.3 La règle d'ancrage, fixée avant toute application

```
ancrage T = début + F × (fin − début)
F = 0,70
fenêtre déclarée : 2023-04-01T00:00:00Z → 2026-04-01T00:00:00Z
⇒ T = 2025-05-07T04:48:00Z          (préfixe 767,2 j · période évaluée 328,8 j · fenêtre 1096 j)
```

Classe de `F` : **préférence économique**, avec divulgation de provenance ci-dessous.

**Les bornes viennent du manifeste gelé, jamais de la dernière donnée disponible.** C'est la clause qui rend le
test de chronologie du § A.12 **exécutable** : si l'ancrage dépendait de la dernière donnée en base, deux futurs
différents produiraient deux ancrages, donc deux préfixes, et le test ne prouverait rien.

**`T` est recalculé par l'outil depuis la règle, jamais accepté comme paramètre libre.** Précédent : l'assertion
I-A.6 du rejeu recalcule le split au lieu de le coder en dur.

**Aucun arrondi implicite de `04:48`.** Arrondir à minuit serait un re-choix silencieux, et un re-choix
silencieux est exactement ce que ce protocole existe pour empêcher.

**Divulgation de provenance.** `F = 0,70` est hérité de P6/P7 — `TRAIN_RATIO = 0.7` **[v]**
`scripts/run_p7_grid_search.py:81`, constante committée bien avant l'audit red-team. Il est donc **antérieur à
C3 et n'a pas été choisi au vu d'un résultat C3**. C'est une **convention rétrospective, sans prétention
d'optimalité** : elle ne fixe pas une date universelle, et toute application future déclare son propre ancrage
dans son manifeste, **avant évaluation**.

**La fenêtre n'est pas élargie.** Des données existent depuis 2021-01 **[v]** `docs/CONTRAINTES_POST_B4.md` § 7,
mais élargir la fenêtre maintenant changerait le cas de référence pendant la construction du protocole. Le
protocole note que **le choix de fenêtre est un second levier de shopping**, au même titre que l'ancrage, et que
la règle « bornes du manifeste, déclarées avant évaluation » le ferme.

**Il est interdit de déplacer `F` après avoir constaté la longueur de la période évaluée.**

### A.4 Les estampilles admissibles à l'ancrage

**Aucune bougie ne clôture à `04:48`** : 288 minutes après minuit n'est un multiple ni de 5, ni de 240, ni de
1440, ni de 10080 **[v]** (arithmétique, vérifiable à la main). **Le protocole ne demande donc jamais une
bougie estampillée exactement à la borne.**

Les données étant estampillées en fin de période (B4.1), la bougie estampillée `t` est close à `t` et
**appartient au passé de `t`**. La dernière observation admissible à l'ancrage est donc, par timeframe, la
dernière bougie estampillée `≤ T` :

| TF | Dernière observation admissible à `T = 2025-05-07T04:48Z` |
|---|---|
| 5 min | `2025-05-07T04:45Z` |
| 4 h | `2025-05-07T04:00Z` |
| 1 j | `2025-05-07T00:00Z` |
| 1 w | `2025-05-05T00:00Z` (le lundi 5 mai) |

**Règle, et non les quatre valeurs** : pour chaque timeframe, l'observation admissible est **la dernière
estampille `≤ T`** de ce timeframe. Les quatre valeurs du tableau sont ce que cette règle donne à l'ancrage
déclaré ; **elles sont calculées par l'outil depuis `T`, jamais écrites en dur**. Le cas limite est couvert par
la règle et non par une formulation en prose : si `T` coïncide avec une estampille, **c'est celle-là**, pas la
précédente.

**Le prix de référence à une borne non alignée** est le **close de la dernière bougie estampillée `≤ T`** du
timeframe considéré. **Jamais une bougie postérieure** — ce serait une information indisponible à la décision.
Cette règle vaut des deux côtés : pour la stratégie comme pour le benchmark (§ C.3).

**Première exécution autorisée.** La décision à `T` s'appuie sur les observations ci-dessus. **Aucun
remplissage ne peut survenir à `T` ni avant.** Le premier remplissage possible est la bougie d'exécution
suivante. Cette propriété est aujourd'hui satisfaite par les deux moteurs, mais **par accident de construction**,
et le protocole la rend **spécifiée** :

- moteur grid : `_GRID_REPLAY_PHASE = {"exec": 0, "1w": 1, "1d": 2, "4h": 3}` **[v]** `scripts/backtest.py:586`,
  tri **[v]** `:2450`, `decides = c.timestamp >= start_time` **[v]** `:2446` — à instant égal l'exécution passe
  avant la décision ;
- moteur signal : modèle next-bar **[v]** `scripts/backtest.py:1842-1852`, `pending` initialisé à `None`
  **[v]** `:1847`.

### A.5 L'univers candidat et sa provenance

L'univers est un **manifeste fermé, haché, déclaré avant que l'ancrage soit appliqué**. Il n'est jamais codé en
dur dans l'outillage : **C3a ne lance aucune campagne**, et le protocole doit rester applicable à un univers
qu'il ne connaît pas.

Le manifeste déclare une **provenance**, en trois valeurs :

| Provenance | Définition | Conséquence |
|---|---|---|
| `clean` | La composition de l'univers ne dépend d'aucun résultat postérieur à l'ancrage | Peut porter un `validé` |
| `contaminated` | La composition dépend, en tout ou partie, de résultats postérieurs à l'ancrage | **Ne peut jamais porter un `validé`.** La sélection est calculée et publiée sous l'étiquette `SÉLECTION_DESCRIPTIVE` |
| `unknown` | La provenance n'est pas établie | **Traitée exactement comme `contaminated`.** `unknown` n'est **jamais** assimilé à `clean` |

*Pourquoi cette porte existe.* **La chronologie de l'arithmétique ne répare pas la chronologie de la
provenance.** Le projet a son propre cas documenté. Le code porte la trace d'un re-choix des planchers du
balayage P7 — « 1.0 % dropped, **1.5 % kept as the Binance-calibration witness**, 3.0 % added » **[v]**
`scripts/p7_grids.py:56-59` — mais ce même commentaire attribue le re-plancher à l'arithmétique de coûts du
GATE B de B4.3 : **seule** la mention du témoin de calibration est traçable à une campagne. **La qualification en
contamination est celle du rapport gelé**, `results/rejeu_grid_report.md` § 10.3 (« les planchers du balayage ont
été re-choisis à la lumière de la campagne Binance … **Renoncement non corrigé** »), et non une lecture inventée
ici. En faire un champ lisible par machine transforme un aveu en porte.

**La distinction est conservée telle quelle** : une provenance `contaminated` ou `unknown` **interdit une
confirmation indépendante** ; elle **n'interdit pas un calcul descriptif**, qui reste autorisé et publié comme
tel.

### A.6 Le registre de variantes

Explorer plusieurs ancrages, plusieurs fenêtres, plusieurs règles ou plusieurs seuils est une **multiplicité à
déclarer**, pas une analyse de sensibilité gratuite. Une phrase ne s'applique pas toute seule : le registre est
sa forme machine.

- **La clé d'une variante est l'empreinte du manifeste complet**, `sig(canon(manifeste))` — **et pas** le seul
  triplet `(fenêtre, univers, ancrage)`. Un changement de **règle de sélection, de seuil, de définition de
  benchmark ou de protocole** est un **nouvel essai même à fenêtre, univers et ancrage identiques**, et
  l'empreinte du manifeste complet rend cette distinction **reproductible** au lieu de déclarative.
- Le manifeste porte donc, **au minimum et sans exception** : la fenêtre et `F` ; l'univers et sa provenance ;
  **la source de données et l'intervalle de bougies** ; **le modèle de fees et les coûts par paire** ; **le
  capital `C`** ; le plancher d'ordre ; la règle de sélection ; **chaque seuil avec sa classe** (§ 0.5) ; la
  définition du benchmark et **le mode de `λ`** (§ C.4) ; **les portes ponctuelles post-ancrage et les paramètres
  de la procédure d'incertitude** (§ F.2) ; et le **sha256 de ce document**.
  Cette liste est exactement ce que la clause D5 asserte « égal à ce qui est déclaré » : deux essais qui ne
  diffèrent que par leur modèle de fees **doivent** porter deux clés de variante distinctes, sans quoi le
  registre manque précisément ce qu'il existe pour tracer.
- S'y ajoutent un **identifiant de variante déclaré par l'humain** et un **lien de parenté** vers la variante
  dont elle dérive.
- **Ré-exécuter le même manifeste est idempotent** : même empreinte, même enregistrement, aucun refus, aucun
  ordinal supplémentaire. Le registre trace des **essais de recherche**, il ne compte pas des appels de script.
- Toute empreinte différente est **une nouvelle variante**, qui doit déclarer son parent. **C'est là que le
  contrôle mord.**
- Le registre est le pendant machine de `docs/RESEARCH_LOG.md` et renvoie à son entrée.

### A.7 La projection d'ancrage, et sa liste blanche

La preuve lisible par la sélection est **le seul préfixe** `[début de fenêtre, T]`, obtenue par une **projection
sur liste blanche**, notée `π_T`. La liste blanche est **le contenu de ce paragraphe**, pas une promesse : c'est
elle qui définit `π_T`, et donc le test du § A.12.

**Le segment de préfixe.** Une entrée d'observation désigne ses segments par des clés ; le manifeste déclare
**laquelle est le segment de préfixe** (dans les artefacts produits par les runners du projet, c'est `train`).
Tout autre segment est **hors liste blanche**.

**Liste blanche, exhaustive.** `π_T(O)` retient, et rien d'autre :

| Portée | Champs retenus |
|---|---|
| Identité et provenance | `strategy`, `pair`, `params`, `effective_params` |
| Contrats | `metrics_version`, `replay_version`, `exchange`, `fees`, `pair_costs`, `pair_costs_file`, `min_order_usdc` |
| Bornes | **les seules bornes du segment de préfixe** : son début et sa fin |
| Métriques | le bloc de métriques **du segment de préfixe**, entier |
| Trajectoire | `equity_daily[<préfixe>]` : `start`, `end`, `values` |
| Comptabilité | `liquidation[<préfixe>]`, entier |
| Amorçage | `warmup[<préfixe>]`, entier, **et** le bloc d'amorçage mesuré au début du préfixe |
| Exécution | `rejections[<préfixe>]`, `dca_counters[<préfixe>]` |

**Écartés sans être lus** — et c'est la liste qui compte pour le § A.12 : tout bloc de segment autre que le
préfixe (les métriques, la trajectoire, la comptabilité, l'amorçage et les rejets postérieurs à l'ancrage), les
bornes postérieures à l'ancrage de `period`, et **toute clé de premier niveau non énumérée ci-dessus**, connue ou
inconnue. Un champ écarté n'est ni lu, ni haché, ni rapporté.

**Deux règles qui ne se confondent pas.**

1. Un champ **hors liste blanche** est **écarté silencieusement**, quel que soit son contenu. C'est là, et
   uniquement là, que peut vivre un futur différent — c'est ce qui rend le test du § A.12 exécutable au lieu de
   vide de contenu.
2. Un champ **dans la liste blanche** qui déclare une borne **postérieure à `T`** est une **erreur d'entrée
   (exit 2)**, **jamais tronquée**. La troncature serait le re-découpage de courbe que le § D interdit, et elle
   transformerait une entrée invalide en entrée silencieusement acceptée.

L'empreinte `sig(canon(π_T(O)))` est écrite dans l'artefact de sélection, et c'est elle que le § A.12 compare.

### A.8 Admissibilité d'un candidat — mesurée sur le préfixe seul

Toutes les clauses portent sur `[début de fenêtre, T]`. **Chaque clause est un choix neuf pour C3, pas une
conséquence de la chronologie.**

**Portée d'une clause — déclarée, jamais devinée.** Une clause est de portée **paire** quand elle décrit les
données et vaut identiquement pour tous les candidats de cette paire : son échec retire **la paire entière**.
Une clause est de portée **candidat** quand elle décrit une simulation : son échec retire **ce candidat**. Une
clause est de portée **run** quand son échec prouve que l'artefact n'est pas ce qu'il prétend être : son échec
rend **tout le run inexploitable** (§ I-A), sans sauvetage partiel.

| # | Clause | Règle proposée | Portée | Classe |
|---|---|---|---|---|
| **D1** | Couverture du préfixe | jours couverts ≥ **97 %** des jours du préfixe **et** trou maximal ≤ **min(31 j, 3 % des jours du préfixe)**, sur les séries 5 min, 4 h, 1 j **et 1 w** | paire | qualité des données |
| **D2** | Amorçage au **début du préfixe** | `sufficient == True` sur **chaque timeframe qui alimente une porte de décision** de la stratégie du candidat | candidat | qualité des données |
| **D3** | Couverture en allers-retours achevés | **≥ 25** cycles achevés sur le préfixe, au sens défini ci-dessous | candidat | préférence économique |
| **D4** | Estimabilité | rendements quotidiens définis et **tous finis**, dénominateurs non nuls | candidat | contrainte mathématique |
| **D5** | Provenance de l'instrument | `metrics_version == 2`, `replay_version == 2`, modèle de fees, coûts par paire, source, intervalle, capital et plancher d'ordre égaux à ceux du manifeste, bornes **exactement** `[début, T]` | **run** | contrat |
| **D6** | Comptabilité terminale normalisée | le préfixe porte une liquidation terminale costée | candidat | contrat |

**D1 — justification.** Le rééchantillonnage quotidien **forward-fille sans marqueur** **[v]**
`src/krakenbot/backtest_metrics.py:166-179`, et `n_daily_returns` compte quand même les jours fabriqués : sur
SOL, la NAV du rejeu est plate sur **277 jours** et `n_daily_returns` vaut malgré tout 1096 **[v]**
`results/rejeu_grid_report.md` § 10.3. Sans D1, un candidat peut être classé sur des rendements inventés. Les
trois nombres — **97 %**, **3 %**, **31 j** — sont des choix de fiabilité, ajustables, **pas des seuils
statistiques**.

> **Divulgation.** Ces trois nombres ne sont pas indépendants du précédent, et il faut le dire plutôt que
> l'omettre : la pré-spécification du rejeu tolérait `max_gap_days ≤ 31` sur une fenêtre de 1096 jours, et
> `1 − 31/1096 = 97,2 %`. Le plafond absolu de 31 jours est **repris** — un mois d'absence est le maximum qu'on
> accepte de forward-filler, indépendamment de la longueur de la fenêtre — tandis que le 3 % relatif est ajouté
> pour qu'une **fenêtre courte** ne devienne pas plus permissive qu'une longue. C'est un choix neuf, informé par
> le précédent, et non une conséquence de la chronologie.

**Pourquoi 1 w y est ajouté.** Le rejeu a mesuré deux estampilles hebdomadaires manquantes sur BTC **à
l'intérieur** de la fenêtre — `2025-02-03` et `2025-03-03` **[v]** `results/rejeu_grid_report.md` § 2.1 — et la
série 1 w alimente des portes de régime. Une couverture qui ne regarde que 5 min, 4 h et 1 j est aveugle
précisément là où D2 mord.

**D2 — justification, et pourquoi il est plus strict que le rejeu.** Une porte de régime amorcée **à travers**
un trou n'est pas la porte que la configuration décrit. Cas mesuré sur l'unique artefact réel : au début du
préfixe, BTC porte `1 d loaded 88, largest_gap_candles 163, sufficient False` et
`1 w loaded 50, extended_by 19, gap 23, sufficient False` ; SOL porte `4 h loaded 0` **[v]**
`results/rejeu_grid_20260919/P7_phase1_grid.json`. Et `bias_1d = 0.2` fait vivre `regime_1d` dans **les trois**
bras de `bear_protection_mode`, donc le défaut n'épargne aucune configuration. Le rapport du rejeu nomme déjà la
reprise de cet amorçage « une entrée obligatoire de C3 » (§ 9.3, point 3).

Le rejeu, lui, a toléré cette classe en imprimant une mise en garde à côté de chaque chiffre. **Ce protocole ne
le peut pas, et la raison est l'usage, pas la qualité** : une mise en garde a un lecteur, **un classement n'en a
pas** — il est consommé. D2 est donc plus strict, et cette différence est un choix, non une correction du rejeu.

**D3 — la quantité comptée, d'abord.** « Cycle achevé » n'a de sens que si le document dit quel nombre il
compte, et ce nombre est **dépendant du moteur** :

- **Moteur grid** : `cycles = total_trades − liquidation.positions` — `total_trades` y vaut
  `pairs_completed + liquidated_positions` **[v]** `scripts/backtest.py:3326`, donc la soustraction laisse les
  allers-retours réellement bouclés.
- **Moteur signal** : `cycles = total_trades`, qui vaut `len(sell_trades)` **[v]** `scripts/backtest.py:1522`,
  soit le nombre de sorties — la définition voulue.
- **Stratégie d'accumulation qui ne vend jamais** : le moteur **retombe sur le compte des achats** **[v]**
  `scripts/backtest.py:1525-1531`. Ce nombre **n'est pas un compte de cycles**, et D3 ne peut pas le lire comme
  tel. Règle : pour une stratégie dont le préfixe ne porte **aucune vente**, **D3 est déclaré inapplicable**, le
  candidat est `NOT_ESTIMABLE` avec la raison `C_COVERAGE`, et **aucun nombre de substitution n'est fabriqué**.

**Justification et limite.** `docs/CONTRAINTES_POST_B4.md` § 8 retient « ~25-30 allers-retours sur l'ensemble de
la période » comme **repère interne de couverture du projet, explicitement pas un seuil statistique universel**.
Le protocole applique ce repère **à la fenêtre réellement utilisée pour décider**, c'est-à-dire au préfixe — ce
qui est **plus exigeant** qu'une proratisation. **Franchir D3 est nécessaire, jamais suffisant.**

**Ce que D3 ne couvre pas, et c'est délibéré.** Aucune clause d'admissibilité ne porte sur la **fenêtre
d'évaluation** : un candidat admissible sur son préfixe peut n'y produire presque rien. Ce protocole **n'impose
volontairement aucun plancher d'activité post-ancrage**, pour une raison de principe — un tel plancher serait
une condition **sur le résultat** de la période qu'on prétend ne pas avoir regardée, et il rouvrirait la porte
que le § 0.2 (a) ferme. La conséquence est assumée et écrite : **l'incertitude post-ancrage d'un candidat peu
actif sera large, et l'issue sera `inconclusif`** — ce qui est le bon comportement, pas un trou.

Et la réciproque, qu'il faut écrire : **l'absence d'effet du seuil de 25 cycles sur la campagne du rejeu ne
démontre pas sa validité générale** — c'est une observation sur un balayage, pas une propriété du seuil.

**D4 — la seule contrainte mathématique, et ce qu'elle n'est pas.** `log1p(r)` est défini pour **tout `r > −1`**.
Une borne plus stricte sur les rendements quotidiens — par exemple `r > −0,5` — serait un **choix de qualité des
données**, pas une contrainte mathématique, et **ce protocole n'en adopte aucune** : une journée à −50 % est
possible sur les actifs du périmètre, et l'exclure d'office écarterait une observation réelle. Un jour porteur
de `r ≤ −0,5` déclenche une **alerte de qualité des données à investiguer**, imprimée, **qui ne retire aucun
candidat**.

**D6 — la règle, et sa raison.** Le préfixe **porte** une liquidation terminale costée. À défaut, le candidat
est écarté avec la raison `R1_NOT_NORMALISED` — **et la raison importe** : il n'est pas écarté « parce qu'il est
mauvais », il est écarté parce qu'il est **hors d'usage décisionnel** (§ B.3). Le défaut est dans l'instrument,
pas dans la stratégie, et le rapport doit le dire ainsi.

**Un candidat inadmissible est imprimé avec ses métriques et son premier gate en échec**, dans l'ordre
D1 → D6. Son score décisionnel n'est pas publié : on ne calcule pas quand même pour commenter le chiffre.

> **Conséquence de D2 sur la fenêtre déclarée, écrite plutôt que découverte.** La fenêtre du § A.3 commence au
> 2023-04-01, et l'amorçage 1 d / 1 w remonte alors dans les trous 2022-23 des données (`CONTRAINTES` § 7).
> Mesuré sur l'unique artefact réel, `sufficient` est **`False`** en 1 d et 1 w sur BTC et sur SOL au début du
> préfixe. **D2 écarte donc aujourd'hui, de façon déterministe, tout candidat dont une porte de décision lit le
> 1 d ou le 1 w, sur ces deux paires, pour cette fenêtre.** Ce n'est pas une prédiction : c'est une conséquence
> des deux choix — la fenêtre et D2 — et elle est déclarée ici pour que le § F.6 ne se lise pas comme une
> prophétie. **La borne basse de la fenêtre est donc un levier sur D2 autant que sur l'ancrage**, et c'est une
> raison de plus de la déclarer au manifeste avant toute évaluation.

### A.9 Score, classement, égalités

- **Les deux écarts, définis ici.** Pour le candidat `j`, sur le préfixe :
  `Δ_j^dd = CAGR(NAV du candidat) − CAGR(blend apparié à λ_dd(j))` et
  `Δ_j^σ = CAGR(NAV du candidat) − CAGR(blend apparié à λ_σ(j))`, tous deux en **points de % par an**, les deux
  `λ` étant ceux du § C.4. Les deux sont calculés ; **seul `Δ_j^dd` classe**, `Δ_j^σ` départage.
- **Quantité classée** : `Δ_j^dd`.
- **Départage**, ordre total déclaré d'avance et appliqué qu'il y ait égalité ou non :
  1. `Δ_j^σ` plus grand ;
  2. `max_drawdown_pct_daily` du préfixe plus petit ;
  3. **identité canonique** (§ A.2) lexicographiquement la plus petite.
- La totalité de l'ordre découle de l'unicité des identités, assertée à l'entrée. **Deux candidats de même
  identité sont une erreur d'entrée (exit 2).**
- **L'ordre d'entrée n'influence rien** : permuter les candidats dans le fichier ne déplace ni un score, ni un
  rang, ni le choix.

### A.10 Le plancher de sélection

Un candidat admissible n'est retenu que s'il franchit **les trois** portes suivantes, évaluées sur **tout**
l'ensemble admissible et jamais sur un gagnant pré-trié :

```
P1   net_pnl(préfixe) > 0
P2   rendement géométrique du préfixe >= 2,0 %/an
P3   Δ^dd > 0
```

**P1** — classe : préférence économique. Une configuration qui a perdu de l'argent sur la fenêtre même qui sert
à la choisir n'est pas choisie.

**P2** — classe : **préférence économique**, et **convention, pas dérivation**. Sa valeur n'est pas dérivable :
l'amplitude des frictions non modélisées du § 2 de `docs/CONTRAINTES_POST_B4.md` est **inconnue**, et le rejeu a
explicitement retiré l'ancrage par les frictions comme arithmétiquement faux. P2 est donc **une convention de
poursuite de recherche**, exprimée **par an** et non proratisée depuis une durée.

> **Divulgation, en trois points, au sens du précédent G2.**
>
> **(i) La coïncidence avec le précédent est réelle et se dit.** La pré-spécification du rejeu écrit elle-même
> « 6 % sur trois ans ≈ **1,96 %/an** » (§ F.3). Le 2,0 %/an retenu ici **tombe donc sur l'équivalent annuel du
> plancher du rejeu**. C'est un choix neuf — exprimer le plancher par an est précisément ce qui évite la
> proratisation — mais il aboutit au même ordre de grandeur, et omettre de le signaler serait une dissimulation.
>
> **(ii) Deux distributions étaient connues, pas une.** Sur le préfixe de 767,2 jours :
>
> | Ensemble | Instrument | Rendement annualisé du préfixe | Sous 2,0 %/an |
> |---|---|---|---|
> | 96 configs du rejeu (grid, BTC + SOL) | `metrics_version` 2 | BTC 2,61 à 7,63 %/an · SOL 4,72 à 10,40 %/an | **0 / 96** |
> | 212 configs de P7 phase 1 (4 familles, 3 paires) | **pré-C1/C2, invalidé** | min −2,33 %/an (`grok_donchian_breakout_4h` SOL) | **68 / 212** |
>
> Écrire « le seul ensemble réel que le projet connaisse » serait donc **faux** : le second existe, ce document
> le lit d'ailleurs au § B.3. Il est sous un instrument invalidé et ne peut fonder aucun seuil — mais il montre
> que **P2 n'est pas inerte en général**, seulement sur la famille grid.
>
> **(iii) Conséquence honnête.** Sur la famille grid et cette fenêtre, P2 ne discrimine rien ; la discrimination
> y est portée par **P3**. Sur d'autres familles, il mord. P2 reste un **garde-fou contre la trivialité**, et
> c'est à ce titre qu'il est retenu, pas comme porte discriminante.

**P3** — classe : préférence économique, et **choix neuf, déclaré comme tel**. C'est l'exigence de benchmark
d'exposition de `docs/CONTRAINTES_POST_B4.md` § 8, appliquée au préfixe. Le précédent exigeait les **deux**
signes (`Δ^dd > 0` **et** `Δ^σ > 0`) ; ce protocole n'exige que `Δ^dd > 0`, parce que l'appariement en drawdown
est celui qui porte le classement et que doubler la condition reviendrait à faire voter deux fois le même
comparateur. `Δ^σ` reste calculé, rapporté, et départage.

**Franchir le plancher autorise une évaluation, jamais un déploiement.**

### A.11 L'abstention

L'abstention **existe, est atteignable, et n'est pas un échec du protocole**. Deux branches distinctes :

| Raison | Condition |
|---|---|
| `A_NO_ADMISSIBLE_CANDIDATE` | Les clauses D1-D6 vident l'ensemble |
| `A_BELOW_FLOOR` | L'ensemble admissible est non vide, aucun candidat ne franchit P1 ∧ P2 ∧ P3 |

**Un seul mécanisme choisit la raison rapportée, et c'est la liste de priorité du § H.** Il n'y a **pas** de
« gate modal », parce qu'un mode n'a pas de départage déclaré et qu'il romprait le § 0.6 : deux personnes
doivent obtenir la même chaîne.

`A_NO_ADMISSIBLE_CANDIDATE` **précède** les raisons de clause dans la liste de priorité, et c'est délibéré :
quand l'ensemble est vide, le fait décisionnel est **qu'il est vide**, et la clause qui l'a vidé est un détail
de diagnostic. Elle reste imprimée — pour chaque candidat, son premier gate en échec — mais elle **ne porte pas
la raison**. Sans cette précédence, `A_NO_ADMISSIBLE_CANDIDATE` serait inatteignable, donc décoratif.

Clause verbatim, à citer dans tout rapport qui s'abstient :

> « Aucune clause n'est relâchée, aucun ancrage n'est déplacé, aucune fenêtre n'est élargie, aucun univers n'est
> étendu, aucun candidat n'est repêché. Un périmètre qui se révèle mal choisi est un **résultat**. »

### A.12 La propriété de chronologie forte

**Énoncé.** Soit `O` un fichier d'observations et `π_T` la projection du § A.7. Pour tout `O'` tel que
`π_T(O') = π_T(O)` :

```
admissibilité(O')        = admissibilité(O)        (clause par clause, pour chaque candidat)
scores(O')               = scores(O)
classement(O')           = classement(O)           (l'ORDRE COMPLET, pas sa tête)
choix_ou_abstention(O')  = choix_ou_abstention(O)  (y compris la raison de l'abstention)
```

**Égalité octet à octet après canonicalisation**, jamais « le même gagnant ». C'est ce qui distingue un
protocole chronologique d'un protocole qui se croit chronologique.

**Où vit le futur qui diffère, sans quoi l'énoncé serait vide.** `O'` se construit à partir de `O` en modifiant
**exclusivement des champs hors liste blanche** (§ A.7) : les blocs de segment postérieurs à l'ancrage — leurs
métriques, leur trajectoire quotidienne, leur comptabilité de liquidation, leurs rejets — et les bornes
postérieures à l'ancrage de `period`. Ces champs restent **présents et bien formés**, parce que la validité
d'entrée les contrôle (§ I-A) ; ils sont simplement **écartés sans être lus** par `π_T`. La règle d'erreur du
§ A.7, elle, ne concerne **que** les champs de la liste blanche : elle ne bloque donc jamais la construction de
`O'`, et les deux règles coexistent sans se contredire.

**Pourquoi la forme boîte noire ne suffit pas, et ce qui la complète.** Un sélecteur qui lit le futur mais se
trouve **insensible aux futurs testés** passe cet énoncé. Il est donc obligatoirement apparié à un **contrôle
négatif** : un scoreur volontairement fuyant est injecté, et le test doit **échouer**. Sans ce contrôle, la
propriété est **trivialement vraie et ne prouve rien**.

**Les contrôles structurels sont des indices de conception, pas des garanties.** La liste blanche, le refus de
troncature et la signature de la fonction de décision réduisent la surface d'erreur ; ils **n'excluent ni une
variable globale, ni une lecture de fichier**. La preuve est portée par l'invariance et le contrôle négatif ;
les contrôles structurels sont rapportés comme tels et **ne sont jamais présentés comme suffisants**.

---

## § B. Le contrat de continuité du portefeuille

Cinq clauses, chacune accompagnée de **l'état de sa vérifiabilité** sous les artefacts actuels. **« Non
vérifiable » est une réponse admissible de ce protocole ; une preuve fausse ne l'est pas.**

### B.1 La frontière qu'il ne faut pas confondre

**La réinitialisation dénoncée comme défaut (b) est un défaut à une frontière interne et une exigence à la
frontière sélection → évaluation.** La clause 1 ci-dessous est satisfaite **par** l'instanciation d'un moteur
neuf que la clause 2 interdit en cours de run. Confondre les deux est le plus court chemin vers la mauvaise
implémentation.

Correction d'un point du brief : le segment `all` **n'est pas** le témoin du contrat, parce qu'il démarre au
début de la fenêtre et non à l'ancrage. Le témoin est `_run_segment("test", …)` **[v]**
`scripts/run_p7_grid_search.py:726-745` : un moteur, un appel, démarrage à l'ancrage. `all` prouve seulement
qu'un appel unique de trois ans fonctionne — ce qui sert la clause 2.

### B.2 Clause 1 — le portefeuille évalué démarre à plat à l'ancrage

*Énoncé.* Les positions fictives des simulations de sélection **ne passent jamais** dans le portefeuille évalué :
celui-ci démarre plat à `T`, avec le capital déclaré et un inventaire nul.

*État : **NON VÉRIFIABLE** sous les artefacts actuels.* Deux vérifications apparemment naturelles n'en sont pas :

- **`equity_daily[...].values[0] == capital` ne prouve rien.** La valeur est **imposée** à l'ancre :
  `if k > 0: # the anchor is authoritative: points stamped <= start are ignored`, puis
  `last = starting_balance + flow_sum` **[v]** `src/krakenbot/backtest_metrics.py:169-179`. L'observer sur 96
  entrées, c'est observer une constante écrite par le code.
- **L'identité `|net_pnl − (ending_balance − starting_balance)| ≤ 1e-6` ne prouve pas l'inventaire nul.**
  Contre-exemple : un achat de 100 avec 1 de frais, prix inchangé, donne cash 900, inventaire marké 99,
  `net_pnl = −1` et `ending − starting = −1`. L'identité est satisfaite, l'inventaire ne l'est pas. Elle est
  **nécessaire, pas suffisante**.

*Ce qui la rendrait vérifiable.* Le **cash**, la **quantité détenue** et la **provenance de l'exécution** à
l'ancrage. Les runners n'exportent aucun des trois. Le dump `--equity-out` produit déjà `cash`,
`inventory_qty` et `mark_price` par point **[v]** `scripts/backtest.py:3722-3743`, et n'est refusé qu'avec
`--cross-validate` **[v]** `:3668` ; il manque que **le runner les porte jusqu'à l'artefact**. C'est un
changement de **runner**, pas de moteur. **Routé en C3b**, sous gate humain et sous invariant de confinement
`compare-ab --strict`.

### B.3 Clause 3 — toute liquidation prévue paie ses coûts, et là où il n'y en a pas, le contrat le dit

*Énoncé.* Toute liquidation prévue par le contrat — notamment la liquidation terminale — **paie ses coûts** :
fees, spread et slippage par paire, comme le reste du modèle.

*État : satisfait par le moteur grid ; **absent** du moteur signal.*

- **Grid.** `_force_close_open_positions` **[v]** `scripts/backtest.py:3149-3260`, appelé en premier dans
  `_calculate_final_metrics` **[v]** `:3320-3323` : vente au MARCHÉ sur le dernier close négociable,
  `exec_price = reference_price × (1 − spread − slippage)` **[v]** `:3183`, fee taker **[v]** `:3104-3106`, et
  **un point d'equity final est ajouté** **[v]** `:3238-3248` pour que le coût entre dans le solde final, le
  rendement, le drawdown et le Sharpe.
- **Signal.** Aucune liquidation n'existe dans le corps de `BacktestEngine` **[v]** `scripts/backtest.py:787-2186`.
  Le solde final est un pur mark : `ending_balance = equity_curve[-1][1]` **[v]** `:1555-1561`. Un inventaire
  ouvert à la borne finale est **valorisé au dernier close sans fee, sans spread, sans slippage**. Et
  `unrealized_pnl` **n'est écrit que par `GridBacktester`** **[v]** `:3267`, sa valeur par défaut étant
  `Decimal("0")` **[v]** `:636` : le moteur signal exporte toujours `0.0`, donc **le champ ne détecte rien**.

*Mesure.* Sur les artefacts B4, **166 segments sur 636** en phase 1 et **116 sur 560** en phase 2 rompent
l'identité de fin à plat **[v]** (recomptage depuis `results/B4_P7_phase1_cross_validate.json` et
`results/B4_P7_phase2_walk_forward.json`). Répartition mesurée : phase 1, `grok_adaptive_dca_weekly` 144 et
`grok_supertrend_4h` 22 ; phase 2, `grok_supertrend_4h` 67, `grok_adaptive_dca_weekly` 37 et
`grok_donchian_breakout_4h` 12 ; **`grok_grid_atr_adaptive_v4` en rompt 0 sur les deux phases**.

*Ce que ce zéro établit, et ce qu'il n'établit pas.* Le § B.2 vient de montrer que l'identité est **nécessaire,
pas suffisante** : un compte de ruptures est donc une **borne inférieure** du nombre de fins non plates, et son
absence côté grid **ne prouve rien par elle-même**. Ce zéro est **cohérent avec** la lecture du code — le grid
liquide, le moteur signal n'a pas de liquidation — et c'est **la lecture du code qui établit l'asymétrie**, pas
le comptage. Le comptage donne l'ordre de grandeur de ce qui est en jeu. Cas extrême, `grok_adaptive_dca_weekly` BTC segment `all` : 101 achats, zéro vente,
`net_pnl = −0,9975`, `ending_balance = 1716,84`, `total_return_pct = +71,68 %`.

*Règle, et ce qu'on n'en conclut surtout pas.* Il serait tentant d'écrire qu'un verdict négatif reste valide *a
fortiori* puisque le coût omis est positif. **Cette règle est fausse et n'est pas retenue**, pour deux raisons :

1. `Δ` est mesuré contre un blend dont `λ` est apparié sur le **drawdown réalisé du candidat** (§ C.4).
   Normaliser la liquidation déplace le MaxDD, donc `λ`, donc le rendement du blend — **dans le sens du
   rendement du B&H de l'actif**, positif sur certaines paires et négatif sur d'autres. **La direction de `Δ`
   n'est pas universelle.**
2. Le `net_pnl` du moteur signal **exclut les gains latents** : l'exemple DCA ci-dessus le montre
   (`net_pnl = −0,9975` pour un rendement de +71,68 %). Raisonner sur son signe ne renseigne pas sur l'économie.

**Règle retenue, verbatim :**

> *Aucun verdict économique directionnel n'est fondé sur un artefact dont la liquidation terminale n'est pas
> normalisée. La normalisation de la liquidation terminale et les métriques correspondantes sont **définies et
> vérifiées avant tout usage décisionnel**, en reproduisant exactement le modèle de coûts du moteur.*

Ce constat est **consigné comme dette du projet et prérequis C3b**, pas comme une clause de qualité d'une
configuration : le défaut est dans l'instrument, pas dans les stratégies.

### B.4 Clause 2 — aucune réinitialisation interne

*Énoncé.* L'évaluation est **un seul appel** `engine.run(pair, T, fin)`. Les statistiques périodiques se
calculent **par tranchage de la grille quotidienne continue** ; elles ne re-découpent jamais la courbe en runs.
Une moyenne de ratios trimestriels **n'est pas** le ratio de la série continue, et le maximum de huit drawdowns
de comptes réinitialisés **n'est pas** le drawdown d'un portefeuille continu.

*État : satisfait par lecture du code, sous convention d'appel.* Les moteurs n'ont **aucun** reset interne :
`BacktestEngine.run` est une boucle unique sur une séquence unique **[v]** `scripts/backtest.py:1849-1976` ;
`equity_curve` est en ajout seul ; les soldes ne sont jamais re-semés ; la liquidation terminale est idempotente
**[v]** `:3173`. Le reset vit **entièrement dans le runner** **[v]** `scripts/run_p7_grid_search.py:728`. La
clause est donc satisfaite **si et seulement si** l'évaluation est invoquée en un seul appel : c'est une
**convention d'appel**, pas une modification de moteur. **Son intégration et sa vérification relèvent de C3b.**

*Deux limites mesurées, à porter au contrat.* `load_historical_data` charge `>= start` **et** `<= end` **[v]**
`scripts/backtest.py:1193-1194` : deux runs chaînés comptent **deux fois** la bougie de frontière — un appel
unique l'évite par construction. Et la liquidation terminale du grid est estampillée au **dernier close
négociable**, pas à la borne finale **[v]** `:3175-3179`. Le protocole **asserte**, sans jamais le supposer, que
cette estampille et la borne finale tombent dans la **même cellule de la grille quotidienne** ; sinon
`E_STAMP_MISMATCH`.

### B.5 Clause 4 — l'amorçage, deux contrôles distincts

**Il y a deux contrôles de warmup, à deux instants, servant deux propriétés. Les confondre est une erreur, et
ils sont imprimés séparément :**

| Contrôle | Instant | Propriété servie |
|---|---|---|
| **W-préfixe** | début de la fenêtre | l'amorçage de la **preuve de sélection** (§ A.8, D2) — échec : `D_WARMUP_PREFIX` |
| **W-ancrage** | `T` | l'amorçage du **portefeuille évalué** — échec : **`D_WARMUP_ANCHOR`**, qui rend l'évaluation post-ancrage inexploitable et l'issue `inconclusif` |

Les deux sont chronologiquement propres : le rapport de warmup est construit sur
`history = [c for c in candles if c.timestamp <= start]` **[v]** `scripts/backtest.py:502`, fonction pure de
(paire, timeframe, instant, base `≤` instant). **Il ne lit aucune donnée postérieure à son instant.**

Piège à ne pas reproduire : la série **fournie** aux indicateurs court jusqu'à la borne finale — correct pour un
run continu — mais **seul le rapport est pur**. Un implémenteur ne doit pas confondre la série nourrie et
l'objet de warmup.

### B.6 Clause 5 — la première exécution

Voir § A.4. **Aucun remplissage à `T` ni avant** ; le premier remplissage possible est la bougie d'exécution
suivante.

### B.7 Ce que la vérification du § B ne prouve pas

Elle ne prouve ni la justesse économique d'une configuration, ni la fidélité du modèle de remplissage. Les
frictions non reproduites — file d'attente, non-exécutions, remplissages partiels, sélection adverse — restent
**non modélisées et d'amplitude inconnue** (§ J).

---

## § C. Synchronisation stratégie ↔ benchmark

### C.1 Pourquoi le benchmark est construit, et non cité

`scripts/compute_benchmarks.py` est **interdit d'usage décisionnel** sous ce protocole, et ses sorties
n'apparaissent qu'à titre de **descripteurs historiques**, à côté des chiffres reconstruits, avec le delta.
Écarts mesurés avec la convention des moteurs :

| Écart | Constat |
|---|---|
| Borne de chargement | charge `timestamp < P6_END` **[v]** `scripts/compute_benchmarks.py:107-108` là où les moteurs chargent `<= end` **[v]** `scripts/backtest.py:1193-1194` — dette 15(c) |
| Ancre | `candles[0].timestamp − interval` **[v]** `:94-96`, soit une période **avant** l'ancre des moteurs |
| Entrée | au premier **open** **[v]** `:139-140`, non au close estampillé à l'ancre |
| Sortie | **aucune** : « the signal engine's convention (no end-of-run liquidation) » **[v]** `:12` |
| Sorties | scalaires seulement, aucune trajectoire de NAV **[v]** `:154-160` |

**La dette 15(c) reste ouverte, et son traitement est défini** : `compute_benchmarks.py` **n'est pas modifié**
— il entre au diff de contrôle (§ L.3) — et C3b le corrige ou le retire sous son propre gate. **Un benchmark
encore désaligné est interdit d'usage décisionnel ; il reste descriptif.**

### C.2 Les deux comparateurs, et pourquoi il ne faut pas les empiler

Ils répondent à des questions différentes :

| Comparateur | Question à laquelle il répond | Rôle |
|---|---|---|
| **B&H plein notionnel** (`CONTRAINTES` § 4) | « l'actif, détenu entièrement, a fait quoi ? » | **Référence descriptive et base de construction** du comparateur apparié |
| **Blend B&H/cash apparié en risque** (`CONTRAINTES` § 8) | « à budget de risque et coûts comparables, une allocation passive a fait quoi ? » | **Le comparateur décisionnel** |

**Le battre en rendement brut n'est un gate ni explicite ni implicite.** Le B&H plein notionnel n'entre dans
aucune porte ; il est rapporté, et il sert à construire le blend.

### C.3 La table de synchronisation, des deux côtés

| | Stratégie | Benchmark |
|---|---|---|
| Bornes de chargement | `>= borne basse` et `<= borne haute` | **`>= dernière estampille ≤ borne basse`** et `<= borne haute`, sur la série quotidienne estampillée en fin de période |
| Instant de disponibilité | estampillage fin de période : la bougie estampillée `t` est close à `t` | idem |
| Prix à une borne **non alignée** | close de la dernière bougie estampillée `≤ borne`, **sur le timeframe de la stratégie** | close de la dernière bougie estampillée `≤ borne`, **sur la série quotidienne** — **jamais une bougie postérieure** |
| Première exécution | § A.4 : aucun remplissage à la borne ni avant ; le premier remplissage possible est la bougie d'exécution suivante | entrée **à la borne basse**, au prix de référence ci-dessus |
| Warmup | bloc `warmup`, deux contrôles (§ B.5) | sans objet : aucun indicateur |
| Frais | modèle `--fees` et coûts par paire, maker/taker par site de remplissage | taker + spread + slippage sur **les deux** jambes |
| Valorisation finale | § B.3 | **une** liquidation terminale à la borne haute |

**La borne de chargement du benchmark est élargie exprès.** À une borne non alignée, la dernière estampille
quotidienne est **strictement antérieure** à la borne ; la charger `>= borne basse` la rendrait invisible et le
comparateur n'aurait plus de prix d'entrée. La borne basse du chargement est donc **cette estampille**, et non
l'instant de l'ancrage.

**Deux asymétries subsistent, déclarées plutôt que dissimulées.**

1. **Une barre d'exécution.** La stratégie ne peut pas être remplie à la borne basse ; le benchmark y entre.
   Le benchmark est donc exposé **une bougie d'exécution plus tôt**. L'écart n'est pas quantifié et il est
   **favorable au benchmark en tendance haussière, défavorable en tendance baissière** — sa direction dépend du
   chemin, donc aucune correction n'est appliquée.
2. **La fraîcheur du prix de référence diffère.** À `T = 04:48`, le dernier close de la stratégie est
   `04:45` (3 minutes), celui du benchmark quotidien est `2025-05-07T00:00` (4 h 48). Les deux côtés respectent
   la même **règle** — la dernière estampille `≤ borne` — mais **pas sur le même timeframe**, et donc pas avec
   la même fraîcheur. C'est une conséquence de l'ancrage non aligné, elle est **consignée au § J** comme
   non-mesurable, et **aucune ligne de sensibilité n'est publiée**.

**Les fonctions du rejeu sont réutilisables après vérification de leur contrat, jamais telles quelles.** Cas
concret et bloquant : `select_entry_candle` **[v]** `scripts/audit/rejeu_benchmark.py:166-186` prend la bougie
estampillée exactement à la borne, **sinon la première bougie suivante dans les 24 h** — un regard **vers
l'avant**. Appliqué à `T = 04:48` sur une série quotidienne, il entrerait au close du **8 mai**, soit ≈ 19 h
**après** l'ancrage : une information indisponible à la décision. **C3 écrit sa propre sélection d'entrée,
regardant vers l'arrière**, conformément à la ligne « prix à une borne non alignée » ci-dessus.
`build_full_notional` et `benchmark_metrics` sont paramétrés par leurs bornes mais **appellent** la sélection
d'entrée : l'adaptation se fait **par injection, pas par copie**, et **sans modifier le diagnostic gelé**.
`comparability_block` est inutilisable en l'état : il code en dur le compte de rendements de la fenêtre du rejeu
**[v]** `scripts/audit/rejeu_benchmark.py:322`.

Chaque réutilisation est accompagnée, dans le rapport, de **l'écart constaté et de l'adaptation retenue**.

### C.4 Le comparateur apparié en budget de risque, et le mode de λ

Blend **statique** `NAV_λ(t) = (1 − λ)·C + λ·NAV_bh(t)` — allocation initiale, **jamais rééquilibrée** —
construit sur le B&H plein notionnel reconstruit, avec exactement ses coûts et sa liquidation terminale.

- `λ_dd` est trouvé **par recherche sur les NAV réellement construites**, de sorte que le
  `max_drawdown_pct_daily` réalisé du blend égale celui du candidat ; `λ_σ` de même sur l'écart-type quotidien
  des rendements. **Jamais par un rapport de volatilités** : dans un blend statique le poids de l'actif dérive
  avec le prix, donc les rendements du portefeuille ne sont pas `λ·r_bh`.
- **Étiquette obligatoire, à imprimer à côté de tout `λ`** : *un appariement sur un risque **réalisé** est une
  comparaison rétrospective, jamais une allocation validée pour l'avenir.*

**Le mode de `λ` du comparateur d'évaluation — tranché.**

| Mode | Ce qu'il dit | Statut |
|---|---|---|
| **`λ` fixé sur le préfixe** | Le comparateur est une allocation **décidable à l'ancrage avec l'information du passé seul**. Implémentable. Budget de risque *ex ante* ; il ne correspondra pas au risque réalisé après l'ancrage | **DÉCISIONNEL** |
| `λ` ré-estimé après l'ancrage | Budget de risque *ex post* exactement apparié, mais **non implémentable** et rétrospectif | **DESCRIPTIF uniquement** |

Le mode est **écrit dans l'artefact** et **entre dans l'empreinte du manifeste** (§ A.6), parce qu'il change
l'interprétation du résultat.

Pour la **sélection**, tout est calculé sur le préfixe par définition ; l'appariement y reste rétrospectif *à
l'intérieur du passé*, et l'étiquette ci-dessus s'applique aussi.

### C.5 Tests de comparabilité — bloquants

Paramétrés par la fenêtre considérée, jamais par une longueur en dur. Quatre tests, chacun avec ce qu'il
attrape :

| Test | Borne | Ce qu'il attrape |
|---|---|---|
| Jours forward-fillés du benchmark | ≤ **min(31 j, 3 % des jours de la fenêtre)** — la borne D1, reprise explicitement | un comparateur marké sur des prix périmés |
| Observation admissible aux deux bornes (§ A.4) | présence | un comparateur sans prix d'entrée ou sans prix de sortie |
| Compte de rendements = `len(grille quotidienne) − 1` | égalité | **la ruine** : `resample_daily` cesse de définir un rendement dès qu'une NAV atteint 0 ou moins **[v]** `src/krakenbot/backtest_metrics.py:184-194`. Hors ce cas le test est vrai par construction, et il est conservé **uniquement** pour ce cas, qui est nommé |
| Finitude | toutes valeurs finies | un NaN ou un infini entré dans la chaîne |

Un échec donne `E_NO_BENCHMARK`, et **aucun repli sur `compute_benchmarks.py` n'est autorisé**.

### C.6 Cas non calculables

Aucun croisement de `λ` sur la grille de recherche, **résidu d'appariement supérieur à 10 % de la cible
appariée** (§ 0.5, classe qualité des données), `λ` non fini, rendements indéfinis ou non finis, benchmark non constructible : le candidat est **`NOT_ESTIMABLE`**, son
**`Δ` décisionnel n'est pas publié**, et son premier gate en échec est imprimé. Si aucun candidat n'est
estimable, l'issue est `inconclusif`, et la raison portée par la chaîne est celle que donne la liste de
priorité du § H — jamais un « gate modal », qui n'a pas de départage déclaré.

---

## § D. Quelles données prouvent quoi

### D.1 Trois natures de données, nommées

| Nature | Définition | Usage autorisé |
|---|---|---|
| **Historique déjà exploré** | Binance 2021-2026, balayé par P6, P7, B4 et le rejeu | Développement et **évaluation rétrospective**. **Jamais** un hors-échantillon |
| **Évaluation chronologique rétrospective** | Ce que ce protocole produit : honnête sur la fuite de sélection, **menée sur des données déjà vues** | Décider sous ce protocole, avec la portée du § D.2 |
| **Échantillon réellement jamais consulté** | Données futures, **gelées avant observation** | Une confirmation prospective |

### D.2 La portée, écrite une fois pour toutes

> **Les résultats historiques restent rétrospectifs au niveau du processus de recherche ; réparer l'instrument
> ne rend pas les données vierges.**

Une confirmation prospective exige une configuration, des critères et des règles de suivi **fixés avant
observation des résultats**. B5 peut porter une telle évaluation, tout en testant le fonctionnement
opérationnel — **sans être ni l'unique dispositif prospectif possible** (une évaluation différée sur des données
futures gelées joue le même rôle), **ni une preuve indépendante automatique** : modifier les paramètres ou ne
conserver que les gagnants pendant le paper en détruirait la portée.

**Quatre semaines de paper ne constituent pas une preuve économique**, en particulier à basse rotation. Les
**conditions d'admission** au paper et les **preuves exigées pour conclure** ensuite sont deux choses
distinctes. **Les règles B5 du `ROADMAP.md` ne sont pas modifiées par ce document.**

### D.3 Recevabilité des artefacts existants

Un artefact n'est recevable en entrée que s'il satisfait D5 (§ A.8) et les conditions d'entrée du § I-A.

**Artefacts legacy B4 — irrecevables, une clause.** `results/B4_P7_phase1_cross_validate.json` et
`results/B4_P7_phase2_walk_forward.json` ne portent ni `equity_daily`, ni `metrics_version`, ni `warmup`
**[v]** (`results/B4_P7_phase1_cross_validate.json`, `results/B4_P7_phase2_walk_forward.json` : aucune des
deux clés `equity_daily`, `metrics_version`, `warmup` n'y figure). Sans trajectoire de NAV : pas de score, pas
de comparaison, pas de contrôle de continuité, pas de
classe de warmup.

**Artefact du rejeu — un motif technique de refus, puis des limitations de portée distinctes.**

D'abord ce qui **ne** le disqualifie **pas**, parce que c'est là qu'un refus paresseux se cacherait :
**l'arithmétique de la chronologie est satisfaite**. Le segment `train` couvre exactement `[début, T]`, le moteur
charge `<= end` **[v]** `scripts/backtest.py:1193-1194`, et `train_end == test_start` à la seconde. Une sélection
lue sur le seul `train` serait donc **mécaniquement chronologique**.

*Précision, parce que l'énoncé voisin serait faux* : les trades **ne se partitionnent pas** entre `train`, `test`
et `all`. Mesuré **sur le champ `total_trades`** : `train + test == all` sur **32 configurations sur 48** pour
BTC et **28 sur 48** pour SOL **[v]** (`results/rejeu_grid_20260919/P7_phase1_grid.json`). Le champ compte,
et il faut le nommer : sur la quantité `cycles` du § A.8 D3, l'égalité ne tient sur **aucune** des 96
configurations — les deux lectures racontent des histoires opposées. La réinitialisation à l'ancrage **change donc le chemin réalisé** sur une minorité substantielle de
configurations. Ce n'est pas un défaut — c'est la clause 1 du § B qui opère — mais il ne faut pas écrire que les
trades se partitionnent.

**Le motif technique de refus, seul, appliqué mécaniquement :**

- **D2 échoue au début du préfixe, sur les deux paires.** BTC : `1 d gap 163`, `1 w gap 23`, `sufficient False`.
  SOL : `4 h loaded 0`. Raison : **`D_WARMUP_PREFIX`**. Phrase portée par l'artefact de validation :
  **« cet artefact ne satisfait pas les conditions d'entrée C3 ».** *(La fenêtre d'évaluation, elle, est propre
  — c'est W-ancrage, un contrôle distinct, § B.5.)*

**Les limitations de portée, distinctes, qui ne sont pas des motifs de refus technique :**

- **Provenance `contaminated`** (§ A.5). Elle **interdit une confirmation indépendante** ; elle **n'interdit pas
  un calcul descriptif**, que ce protocole autorise sous l'étiquette `SÉLECTION_DESCRIPTIVE`.
- **SOL inadmissible** — couverture 825 jours, benchmark non constructible, warmup W2, NAV plate sur 277 jours
  forward-fillés. C'est une limitation **de périmètre par paire** : elle retire SOL, **elle n'exclut pas BTC**.
  Écrire l'inverse serait une erreur de raisonnement.
- **Le gel du rejeu** est une **contrainte de périmètre, pas un défaut des données** : le diagnostic ne se
  réécrit pas, ne se réinterprète pas, ne se rouvre pas, et sa pré-spécification dit que `train`/`test` ne
  déplacent jamais un verdict. Cela borne ce qu'on a le droit de **conclure**, pas la qualité de ce qui a été
  **mesuré**.

**Comment le refus est produit.** La règle est écrite ici, **avant** toute application. L'outillage la reproduit
mécaniquement en ne lisant que les **blocs de métadonnées** de l'artefact — `period`, `metrics_version`,
`replay_version`, `warmup`, `params`, présence de `liquidation` — et **jamais les courbes d'equity**. La sortie
est archivée sous **`results/c3a_entry_validation/`**, jamais sous `results/rejeu_*`, et porte le **sha256 du
fichier source**. Elle **ne produit ni classement, ni verdict économique** sur la famille grid : l'outil de
sélection refuse de tourner tant que la validation d'entrée n'est pas verte. **Les artefacts et le verdict du
rejeu restent inchangés**, vérifié par sha256.

### D.4 Ce qui prouve l'outillage

Le parcours complet du protocole est démontré sur des **fixtures synthétiques générées en code**, couvrant au
minimum : aucun candidat admissible, égalités au classement à chaque niveau, frontière interne, données
manquantes à l'ancrage, et la chronologie forte avec son contrôle négatif. **Les artefacts existants permettent
de tester l'orchestration ; ils ne permettent pas de reconstituer une validation chronologique en redécoupant
leurs courbes.**

---

## § E. Doctrine des critères

Chaque critère précise **ce qu'il mesure**, **sa justification**, **ses dépendances mécaniques aux paramètres**,
et **les arbitrages qu'il opère**. Une corrélation avec un paramètre balayé **ne constitue pas à elle seule un
motif d'exclusion** — un paramètre peut légitimement modifier l'économie, et un critère de risque peut
légitimement écarter une configuration au rendement supérieur. Toute calibration n'utilise que les données
autorisées avant l'évaluation.

**C'est tout. Il n'y a pas de cinquième exigence, et il n'y en aura pas.**

> **Note de discipline.** Le projet a cherché plusieurs fois une loi générale sur ce que doit être un bon
> critère, à partir du cas G3 du rejeu ; le brief de ce chantier en recense **trois formulations antérieures**
> déjà fausses, et la rédaction du présent document en a produit **deux de plus**. La dernière — « un critère
> doit ordonner dans une direction dérivable du mécanisme du balayage » — rejetterait un **critère de risque
> parfaitement légitime** : un critère pertinent n'a aucune obligation d'être monotone selon chaque paramètre
> balayé. Elle s'appuyait en outre, telle qu'elle était formulée ici, sur un raccourci — « moins de frais →
> ratio plus haut » — qui oublie que le **numérateur** de `net_pnl / total_fees` varie aussi. Ce raccourci est
> **une faute de la loi candidate, pas du rapport gelé** : `results/rejeu_grid_report.md` § 10.1 énonce la
> chaîne complète (multiplicateur large → grille espacée → peu de cycles → peu de frais → ratio élevé) et la
> mesure. **On arrête de chercher cette loi.**
>
> **Le cas G3 reste un cas documenté** — `results/rejeu_grid_report.md` § 10.1 — **pas une loi.** Symétriquement,
> **l'absence d'effet du seuil de 25 cycles sur cette campagne ne démontre pas sa validité générale** : c'est
> une observation sur un balayage, pas une propriété du seuil.

---

## § F. Plan d'évaluation de la précision

Fixé **avant toute application**.

### F.1 L'effet économiquement pertinent

`Δ^dd`, en **points de % par an**, contre le comparateur apparié du § C.4. C'est une question de **magnitude**,
pas de ratio. **Le Sharpe n'est décisionnel nulle part dans ce document** ; il est rapporté à titre descriptif.

### F.2 La procédure d'incertitude

Écrite ici, **appliquée en C3b** : bootstrap par **blocs circulaires** sur la courbe post-ancrage et sur son
benchmark synchronisé, **indices appariés** entre les deux.
`docs/CONTRAINTES_POST_B4.md` § 8 mandate nommément le bootstrap par blocs.

**Paramètres gelés par ce document** :

| Paramètre | Valeur | Classe |
|---|---|---|
| Longueurs de bloc `L` | **{10, 21, 42} jours**, `L = 21` en tête | qualité des données |
| Réplications `B` | **10 000** | qualité des données |
| Appariements | **{`dd`, `σ`}** | préférence économique |
| Graine | **déclarée au manifeste** avant évaluation, et entrant dans l'empreinte (§ A.6) ; tirage `default_rng([graine, index de paire, L])`, indices tirés **une fois par `L`, avant tout découpage** | contrat |
| Mode de `λ` | § C.4, **déclaré avec la borne** parce qu'il change l'interprétation | contrat |

`L = 21` en tête : trois semaines préservent le portage d'inventaire ; `L = 10` et `L = 42` sont les points bas
et haut de sensibilité. `B = 10 000` place le quantile unilatéral à 5 % sur la 500ᵉ statistique d'ordre.

**Les six combinaisons `L × appariement` sont une exigence de robustesse, pas une correction de multiplicité.**
Une seule configuration est évaluée ; il n'y a donc pas de famille à corriger à ce stade (§ F.3). Exiger que la
borne soit positive dans **les six** demande que la conclusion ne dépende pas du choix d'un paramètre de
nuisance. Nommer cela « correction » serait faux.

**Les portes ponctuelles post-ancrage, déclarées ici** — ce sont P1, P2 et P3 du § A.10, **réévaluées sur la
fenêtre d'évaluation** et contre le **benchmark d'évaluation** du § C.4, et notées `Q1`, `Q2`, `Q3` pour qu'on
ne les confonde jamais avec les portes de sélection. Leurs valeurs et leurs classes sont celles du § A.10 ; les
répéter ailleurs les ferait diverger.

Motifs, à inscrire : les rendements quotidiens sont **sériellement dépendants**, à **queues lourdes**, et nuls
sur une large fraction des jours. Ni un bootstrap iid ni une erreur-type normale ne conviennent.

### F.3 Multiplicité — l'énoncé restreint, et pourquoi il ne couvre pas notre cas

Il est tentant d'écrire qu'aucune correction n'est nécessaire à l'évaluation puisqu'**une seule** configuration
y est évaluée. **Cet argument n'est défendable que sous des conditions précises** : une configuration choisie
**exclusivement sur le passé**, puis évaluée **une fois**, sur une période **indépendante**.

**Ces conditions ne sont pas réunies ici.** L'argument ne couvre ni un **historique déjà exploré**, ni
**plusieurs manifestes**, ni des **choix révisés après évaluation** — et C3a travaille précisément sur un
historique déjà exploré par P6, P7, B4 et le rejeu.

**Conséquence écrite** : l'évaluation rétrospective menée sous ce protocole porte une **multiplicité déclarée et
non quantifiée**. Ce qui est déclaré : le cardinal de l'ensemble admissible, l'identité de variante et sa
parenté au registre (§ A.6), la provenance de l'univers, et le fait que la fenêtre a déjà été balayée. **La
non-quantification est un non-mesurable déclaré** (§ J), avec sa règle de remplacement, et non une note de bas
de page.

### F.4 Puissance

**Aucune estimation prévisionnelle défendable n'est disponible, et ce protocole le déclare au lieu d'inventer un
seuil de détection.**

Les seuils critiques observés par le rejeu — de l'ordre de 6 points de % par an — sont un **fait mesuré a
posteriori, sur une autre fenêtre, avec une autre famille de correction**. **Le protocole interdit de les
extrapoler**, exactement comme la pré-spécification du rejeu interdisait d'extrapoler depuis sa calibration.

**N'est écrit nulle part, parce que faux** : *« une fenêtre plus courte ne peut pas avoir des erreurs-types plus
petites »*. La variabilité et la structure de dépendance peuvent différer d'une période à l'autre, et rien n'est
affirmé sur la précision avant de l'avoir mesurée.

### F.5 Règles de conclusion, et le statut de « inconclusif »

L'issue **`inconclusif` est prévue explicitement et n'est pas un échec du protocole**. Une estimation positive
qui échoue à la borne — dans une seule des six combinaisons suffit — est **`inconclusif (F_CANNOT_SEPARATE)`**,
**jamais `réfuté`** : l'absence de séparation n'est pas une preuve d'absence. Une estimation qui échoue aux portes ponctuelles est `réfuté`, **jamais `inconclusif`** : sinon le
négatif attendu s'échappe en « à re-tenter avec d'autres paramètres ».

### F.6 L'attendu déclaré

> **Attendu déclaré avant toute application : `inconclusif`.**

Le déclarer d'avance **interdit de le renégocier après**. C'est un **attendu déclaré, jamais une conclusion
imposée** : il ne préjuge d'aucun résultat, et un résultat différent est consigné comme falsifiant l'attendu,
sans être renégocié.

---

## § G. Agrégation et non-règles

### G.1 Agrégation — une seule configuration, et la règle qui l'impose

**Il y a un seul classement et une seule configuration retenue, sur tout l'univers.** Le § A.9 définit un ordre
total sur l'ensemble des candidats admissibles, **toutes paires confondues** ; la configuration retenue est son
maximum, et il n'y en a qu'une.

**Il n'y a donc pas de vote par paire.** Une paire dont les clauses de portée « paire » échouent (§ A.8 D1) voit
tous ses candidats retirés de l'ensemble admissible : elle est **`descriptif`** — ses chiffres sont imprimés,
ils n'entrent dans aucun ordre. Ce n'est pas un vote négatif, c'est une absence.

*Pourquoi pas une retenue par paire.* Retenir une configuration par paire rendrait `validé` et `réfuté`
simultanément atteignables sur le même run, ce qui contredirait le § H, et ferait de l'agrégation inter-paires
une décision non écrite. La configuration retenue est nommée **porteuse du résultat**, jamais « la meilleure ».

### G.2 Non-règles explicites

- **Aucune donnée postérieure à l'ancrage n'entre dans la sélection, ni directement, ni par le benchmark, ni
  par l'ancrage lui-même.**
- **Le Sharpe ne change jamais une issue** (§ F.1).
- **Un artefact dont la liquidation terminale n'est pas normalisée ne porte aucun verdict directionnel**
  (§ B.3).
- **L'ordre d'entrée des candidats ne change jamais rien** (§ A.9).
- `validé` n'est ni un déploiement, ni une sélection paper (§ 0.4).

---

## § H. Les issues — conditions nécessaires et suffisantes

**`validé`** ⟺ le run est exploitable au sens du § I **et** l'univers est de provenance `clean` **et**
**la configuration retenue au sens du § A.9** — pas « une configuration », **celle-là** — franchit
P1 ∧ P2 ∧ P3 sur le préfixe, franchit `Q1 ∧ Q2 ∧ Q3` sur la fenêtre d'évaluation (§ F.2), **et** sa borne
d'incertitude post-ancrage est strictement positive dans **les six** combinaisons `L × appariement` (§ F.2).

> **Pourquoi « celle-là » et pas « une ».** Un énoncé existentiel autoriserait à évaluer tous les candidats
> après l'ancrage et à déclarer `validé` si l'un survit : c'est **exactement** la fuite du § 0.2 (a), sous un
> autre nom. **Une seule configuration est évaluée après l'ancrage : celle que la sélection a retenue.**

**`réfuté`** ⟺ le run est exploitable, **l'univers est de provenance `clean`**, une configuration a été retenue,
et son évaluation post-ancrage échoue à `Q1`, `Q2` ou `Q3`. Portée : *l'effet mesuré sur cette fenêtre est sous
le minimum déclaré ; ce n'est pas une affirmation que l'effet vrai est nul.*

> **Pourquoi `réfuté` exige aussi `clean`.** Sans cette condition, un univers que le protocole déclare inapte à
> soutenir un résultat positif pourrait tout de même **tuer une famille** — et le § K clôt le cas sur un
> `réfuté`. Ce cliquet à sens unique est précisément ce que le précédent avait refusé (`docs/rejeu_grid_prespec.md`
> § D.3 : « des données déclarées inadmissibles pourraient tuer une famille sans pouvoir la soutenir »). Un
> univers `contaminated` ou `unknown` rend donc `inconclusif (P_PROVENANCE)`, jamais `réfuté`.

**`inconclusif`** ⟺ tout le reste. Liste fermée des raisons, par ordre de priorité :

```
R0_INVALID_RUN              une assertion de validité d'entrée a échoué (§ I-A)        [run]
P_PROVENANCE                univers `contaminated` ou `unknown` : descriptif seulement [run]
A_NO_ADMISSIBLE_CANDIDATE   l'ensemble admissible est vide                             [run]
A_BELOW_FLOOR               ensemble non vide, aucun candidat ne franchit le plancher  [run]
F_CANNOT_SEPARATE           la borne ne sépare pas l'effet de zéro dans les six        [run]
--- au-dessous : raisons de diagnostic, imprimées par candidat ou par paire, jamais portées par la chaîne
R1_NOT_NORMALISED           D6 : liquidation terminale non normalisée (§ B.3)
D_WARMUP_PREFIX             D2 : amorçage défaillant au début du préfixe
D_WARMUP_ANCHOR             amorçage défaillant à l'ancrage d'évaluation
D_NOT_ADMISSIBLE            D1 (paire) ou D5 (run)
E_NO_BENCHMARK              benchmark non constructible ou non comparable (§ C.5)
E_STAMP_MISMATCH            estampille de liquidation et borne finale en cellules distinctes (§ B.4)
C_COVERAGE                  D3 échoue, ou D3 est inapplicable (aucune vente au préfixe)
F_NOT_ESTIMABLE             D4 échoue, ou § C.6
```

**Le vocabulaire des statuts est lui aussi clos**, et il ne se confond pas avec celui des raisons. Statuts
possibles d'un **candidat** : `ADMISSIBLE`, `NOT_ESTIMABLE`, `NON_ADMISSIBLE`, `HORS_USAGE_DÉCISIONNEL`.
Statuts possibles d'une **paire** : `VOTANTE`, `DESCRIPTIF`. Statuts possibles d'une **sélection** :
`SÉLECTION_VALIDE`, `SÉLECTION_DESCRIPTIVE`, `ABSTENTION`. Un statut décrit un objet ; une raison explique une
issue. `NOT_ESTIMABLE` (statut de candidat) et `F_NOT_ESTIMABLE` (raison) portent volontairement des noms
voisins et **ne sont pas la même chose** : le premier retire un candidat, le second n'apparaît que si le retrait
de tous les candidats se fait par cette voie.

**Lecture de la liste.** La chaîne de verdict porte **la première raison de la moitié haute qui s'applique** —
ce sont les seules raisons de niveau run, et l'ordre ci-dessus est leur ordre de priorité, sans exception et
sans départage à inventer. Les raisons de la moitié basse **expliquent** pourquoi un candidat ou une paire est
sorti ; elles sont imprimées à côté de lui et **ne portent jamais la chaîne**. C'est ce qui rend
`A_NO_ADMISSIBLE_CANDIDATE` atteignable : l'ensemble vide est le fait décisionnel, la clause qui l'a vidé est
un diagnostic.

**Un échec de niveau run court-circuite tout** : `R0_INVALID_RUN` est évalué avant toute autre chose, et
`D_NOT_ADMISSIBLE` déclenché par D5 est un échec de § I-A, donc il remonte en `R0_INVALID_RUN`.

---

## § I. Validité — étapes séparées

La boucle de dépendance est cassée : chaque étape ne lit que des artefacts produits avant elle.

**I-A. Validité d'entrée** — forme de l'artefact, contrats de version (D5), bornes finissant exactement à
l'ancrage, présence et forme des blocs d'amorçage, provenance de l'univers, unicité des identités canoniques.
Les assertions sont exécutées **dans un ordre gelé** et tout ce qui suit le premier échec est marqué **sauté,
jamais vert**. Un échec d'entrée rend **tout** le run inexploitable : il n'y a pas de sauvetage partiel.

**La règle des codes de sortie, une fois, sans exception :**

| Situation | Code | Suite de la chaîne |
|---|---|---|
| Entrée valide | **0** | la chaîne continue |
| **Entrée refusée — y compris la non-recevabilité d'un artefact** (§ D.3) | **2** | la chaîne **s'arrête** ; aucun classement n'est produit |
| Abstention atteinte **après** une entrée verte (§ A.11) | **0** | c'est un **résultat**, il est publié |
| Auto-contrôle d'instrument en échec | **1** | violation |

La non-recevabilité **n'est pas** une abstention : l'abstention est un résultat du protocole sur des données
recevables, la non-recevabilité est un refus d'entrée. Les confondre reviendrait à laisser tourner la sélection
sur un artefact que le protocole vient de déclarer inapte.

**I-B. Validité de chronologie** — la propriété du § A.12, vérifiée par invariance et par contrôle négatif.

**I-C. Validité des analyses** — reproductibilité **bit à bit** d'un second passage sur les mêmes entrées ;
paramètres, graines et versions consignés dans l'artefact.

---

## § J. Non-mesurables déclarés, chacun avec la règle qui remplace la mesure

1. **Le départ à plat à l'ancrage** (§ B.2). → Déclaré **non vérifiable** ; les champs qui le rendraient
   vérifiable sont nommés et routés en C3b. **Aucune preuve de substitution n'est proposée.**
2. **Le coût de liquidation terminale du moteur signal** (§ B.3). → Aucun verdict directionnel ; normalisation
   définie et vérifiée avant tout usage décisionnel.
3. **L'exposition et le notionnel déployé au cours du temps.** Ni cash, ni inventaire, ni notionnel ne sont
   exportés par les runners. → Le repère de couverture D3 est la **seule** voie d'admission sur ce point ;
   aucune voie alternative fondée sur l'exposition n'est ouverte.
4. **Le drawdown intrabar.** Non reconstructible (contrat C1). → Toute comparaison de drawdown est
   quotidien-contre-quotidien des deux côtés ; `max_drawdown_pct_engine` reste diagnostic et n'est jamais un
   critère inter-familles.
5. **File d'attente, non-exécutions, remplissages partiels, sélection adverse.** Non modélisés, amplitude
   inconnue (`CONTRAINTES` § 2). → **Aucun substitut chiffré**, et la conditionnalité au modèle de remplissage
   est écrite dans chaque issue.
6. **Quels jours en fenêtre avaient réellement des données.** `equity_daily` est forward-fillée sans marqueur
   **[v]** `src/krakenbot/backtest_metrics.py:166-179`. → La couverture est mesurée séparément (D1) ;
   `n_daily_returns` n'est **jamais** une statistique de couverture.
7. **La multiplicité de la recherche rétrospective** (§ F.3). → Déclarée et **non quantifiée** ; ce qui est
   déclaré est énuméré au § F.3, et aucun nombre n'est publié comme s'il la corrigeait.
8. **L'effet d'un taux sans risque non nul.** → La convention `rf = 0` est déclarée comme telle (§ 0.5), sans
   ligne de sensibilité.
9. **Les deux asymétries stratégie ↔ benchmark à une borne non alignée** (§ C.3) : le benchmark entre une bougie
   d'exécution plus tôt, et son prix de référence est d'une fraîcheur différente parce qu'il vit sur un autre
   timeframe. → Les deux sont **déclarées, non quantifiées** ; **aucune correction n'est appliquée** et aucune
   ligne de sensibilité n'est publiée. Leur direction dépend du chemin.
10. **Le nombre de fins non plates.** L'identité de fin à plat étant nécessaire mais non suffisante (§ B.2), son
    compte de ruptures est une **borne inférieure**. → Il est rapporté comme tel, jamais comme un dénombrement.

---

## § K. Clause de clôture et découverte annexe

**Clause de clôture.** Si l'issue est `réfuté`, le cas est clos par cette évaluation. Toute reprise exige un
**mécanisme nouveau** au sens du § 5 de `docs/CONTRAINTES_POST_B4.md`, passant par le ticket d'entrée § 6 —
**pas un nouveau balayage, pas un périmètre élargi « pour vérifier »**.

**Découverte annexe.** Une découverte faite en chemin est **signalée, jamais traitée**. Deux sont déjà
consignées par ce document : la liquidation terminale absente du moteur signal (§ B.3), portée en dette du
projet et prérequis C3b ; et l'impossibilité de vérifier le départ à plat sous les artefacts actuels (§ B.2).

---

## § L. Artefacts, ordre d'exécution, diff de contrôle

### L.1 Ordre d'exécution

Aucun pas n'est sauté ni réordonné.

| # | Producteur | Artefact |
|---|---|---|
| 1 | `c3_anchor` | ancrage recalculé, estampilles admissibles, enregistrement au registre de variantes |
| 2 | `c3_entry` | validité d'entrée (§ I-A) → `results/c3a_entry_validation/` — **exit 0 exigé pour la suite** |
| 3 | `c3_benchmark` | comparateur du préfixe, `λ` et son mode |
| 4 | `c3_select` | projection, admissibilité, scores, classement, choix ou abstention |
| 5 | `c3_continuity` | contrat du § B sur un artefact d'évaluation, avec l'état de vérifiabilité de chaque clause — **sans entrée réelle en C3a** |
| 6 | `c3_verdict` | l'issue et **la chaîne de verdict** |

**Ce qui est réellement atteignable en C3a.** L'exécution continue post-ancrage et la procédure d'incertitude
relèvent de **C3b** (§ B.4, § F.2), et tout artefact réel existant est refusé à l'entrée (§ D.3). En C3a, les
étapes 5 et 6 ne sont donc exerçables que sur des **fixtures synthétiques**, et les seules issues qu'elles
peuvent produire sur données réelles sont la **non-recevabilité** et l'**abstention**. `validé` et `réfuté` sont
**structurellement inatteignables tant que C3b n'a pas livré l'exécution continue** — ce n'est pas un défaut du
protocole, c'est le découpage en deux lots, et il est écrit pour qu'on ne le découvre pas à l'usage.

### L.2 La chaîne de verdict

Aucun paramètre libre, aucune entrée humaine : deux personnes exécutant le verdict sur les mêmes artefacts
obtiennent **la même chaîne**. Elle porte au minimum l'issue, la raison, l'identité canonique retenue ou `-`, le
statut de sélection, l'état de la continuité, l'identité de variante, la provenance de l'univers, le sha256 de
ce document, et celui des observations. **Le rapport cite la chaîne, il ne la paraphrase pas.**

### L.3 Diff de contrôle

Vide sur `src`, `scripts/backtest.py`, `scripts/run_p6_backtests.py`, `scripts/run_p7_grid_search.py`,
`scripts/p7_grids.py`, **`scripts/compute_benchmarks.py`**, `config`, `pyproject.toml`, `poetry.lock`.

`scripts/compute_benchmarks.py` est ajouté à cette liste **délibérément** : le § C touche sa doctrine, et la
tentation de « juste corriger la borne d'un jour » est exactement la dérive que le diff de contrôle existe pour
attraper.

### L.4 La liste fermée des fichiers nouveaux

Hors de cette liste, **aucun fichier n'est créé, modifié ou supprimé** par C3a. La liste est close par ce
document : l'allonger est un amendement au protocole, pas une décision d'implémentation.

**Outillage** — `scripts/audit/` (hors comptage de `docs/CODE_MAP.md`) :

```
c3_common.py   c3_anchor.py   c3_entry.py   c3_benchmark.py   c3_select.py   c3_continuity.py   c3_verdict.py
```

**Tests** — `tests/test_scripts/`, en **ajout pur**, aucun test existant modifié ou supprimé :

```
test_c3_common.py   test_c3_anchor.py   test_c3_entry.py   test_c3_benchmark.py
test_c3_select.py   test_c3_chronology.py   test_c3_continuity.py   test_c3_verdict.py
```

`test_c3_entry.py` couvre l'outil qui produit le refus du § D.3 : sans lui, la seule sortie que ce protocole
exerce réellement sur des données réelles ne serait pas testée.

**Documentation** : ce fichier, plus les mises à jour de `skills/backtest.md` (section protocole),
`results/INDEX.md`, `ROADMAP.md` (ligne C3), `PROJECT_CONTEXT.md` (note WF **non déclarée résolue**, et la dette
du § B.3) et `docs/CODE_MAP.md`.

**Artefacts** : `results/c3a_entry_validation/`.

Convention de l'outillage, sans exception : **pur, en lecture seule, JSON en entrée et en sortie, aucun accès
base de données**, `--now` injectable pour une sortie reproductible octet à octet, et **codes de sortie
0 ok · 1 violation · 2 usage ou entrée invalide**. Une abstention et une non-recevabilité sont des **résultats**,
donc **exit 0** ; un échec d'assertion de validité est **exit 2**.
