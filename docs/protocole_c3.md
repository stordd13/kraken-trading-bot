# Protocole de validation chronologique — C3, version 2

> **Statut : GELÉ.** GO humain donné le **2026-09-21**, sur cette révision, après les deux corrections
> documentaires qui la constituent. **À partir d'ici, l'outillage suit ce document ; le document ne suit pas
> l'outillage.** Si une fixture révèle une incohérence du protocole, **on s'arrête et on la signale** — on ne
> corrige pas le document en silence pour faire passer un test. Une fois gelé,
> **rien des § 0 à M ne peut être relu, repondéré, réinterprété ou élargi** — ni pendant l'écriture de
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

## Amendements — révision de gel

Ce qui a **réellement** changé dans cette révision, celle sur laquelle le GO a été donné. Aucun code n'existait
au moment de la soumission.

**Deux corrections, toutes deux issues d'une lecture de l'index que je n'avais pas faite.** Mon index affichait
`E1` et `E2` avec **zéro site de référence**, et j'ai écrit « aucune anomalie ». Une colonne de références vide
signifie qu'**aucune règle n'applique la porte** — et c'était précisément la cause du premier défaut.

| # | Section | Ce qui a changé |
|---|---|---|
| A | **§ H.0, nouvelle ; § F.8 et § A.8 corrigés** | Le § F.8 affirmait encore qu'une configuration plate donne **légitimement** `réfuté` et que le § A.13 ne couvrait pas ce cas, alors qu'`E1` l'écarte. **La préséance de l'estimabilité sur le verdict économique est énoncée une seule fois, au § H.0** : tant qu'`E1` et `E2` ne sont pas satisfaites, ni `validé` ni `réfuté` ne peuvent être prononcés, et l'issue est `inconclusif (F_NOT_ESTIMABLE)`. Le § H.1 rend cette exigence explicite **pour `validé` aussi**, et le renvoi des portes `Q` pointe désormais sur le **§ F.8**, leur site de définition, et non sur le § F.2 |
| B | **§ A.13, E2** | L'explication d'E2 transformait une condition **suffisante** en condition **nécessaire**. Contre-exemple : deux trajectoires **variables et identiques** sous rééchantillonnage apparié donnent des `CAGR` qui bougent et une **différence toujours nulle**. La condition opérationnelle d'E2 est **inchangée** ; seule son explication est corrigée, ici et dans ses occurrences du § A.8 et de l'en-tête |
| C | **§ M** | Index régénéré — `E1` et `E2` portent maintenant des sites de référence — et **la règle de lecture ajoutée** : un symbole sans site de référence est une porte que rien n'applique |

**Aucun seuil introduit, aucun seuil modifié.** `E1` et `E2` gardent leurs valeurs ; seule leur articulation avec
les issues est écrite.

**Révisions antérieures, pour mémoire.** Troisième soumission : convention d'exécution du benchmark séparée de
celle des moteurs, instant du prix distingué de l'estampille ; `E1` exemptant le comparateur ; `Q1`-`Q3`
restaurés au § F.8 ; entrées invalides séparées des échecs numériques avec `B_effectif` publié ; seuil 144/288
déclaré ; arithmétique hebdomadaire corrigée ; § M créé. Deuxième soumission : § 0.7 ; table unique des codes de
sortie ; procédure numérique figée et borne pivotale ; séquence filtrer-puis-classer ; artefact de couverture ;
portée du `réfuté` bornée au triplet ; preuve initiale exigée de C3b ; porte pré-merge du § L.5.

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
| Capital de référence `C` des simulations et du comparateur | **1000 unités de la monnaie de cotation de la paire du manifeste** (USDC à la cible Bybit ; USDT sur la base de validation Binance, transposition déclarée § A.6) | contrat (`starting_balance` des runners) |
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

### 0.7 Une règle normative, une seule section d'origine

**Toute règle normative de ce document est énoncée dans exactement une section. Partout ailleurs elle est
citée par renvoi, jamais reformulée.**

*Pourquoi cette règle existe.* La première soumission de ce document portait quatre contradictions internes, et
les quatre avaient la même cause : une règle écrite à deux endroits, dont les deux énoncés avaient divergé à la
réécriture. Codes de sortie, multiplicité, candidat retenu, portée de `réfuté`. Aucune n'était une erreur de
raisonnement ; toutes étaient des erreurs de rédaction, et un protocole gelé qui se contredit n'est pas
applicable mécaniquement — le § 0.6 exige que deux personnes obtiennent la même chaîne.

**Sections d'origine, table de renvoi.** Quand deux passages semblent parler de la même règle, **celui-ci
tranche** :

| Règle | Section d'origine | Tout le reste |
|---|---|---|
| Codes de sortie et portée d'un refus | **§ I.1** | renvoi |
| Séquence sélection : admissibilité → plancher → classement | **§ A.10** | renvoi |
| Multiplicité et ce qu'on en corrige ou non | **§ F.3** | renvoi |
| Procédure d'incertitude et formule de la borne | **§ F.2** | renvoi |
| Portée d'un `réfuté` et d'une clôture | **§ K.1** | renvoi |
| Définition d'une issue | **§ H** | renvoi |
| Convention d'exécution des deux côtés | **§ C.3** | renvoi |
| Classe d'un nombre décisionnel | **§ 0.5** | renvoi |

**Une reformulation, même fidèle, est un défaut de rédaction** : elle survivra à la prochaine correction de la
section d'origine et la contredira.

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
erreur d'entrée, jamais un tirage au sort** — portée et code au § I.1.

### A.3 La règle d'ancrage, fixée avant toute application

```
ancrage T = début + F × (fin − début)
F = 0,70
fenêtre déclarée (v2.1, première campagne) : 2021-03-01T00:00:00Z → 2026-06-29T00:00:00Z
⇒ T = 2024-11-22T04:48:00Z          (préfixe 1362,2 j · période évaluée 583,8 j · fenêtre 1946 j)
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

> **Historique.** La fenêtre de v2.0, `2023-04-01Z → 2026-04-01Z` (`T = 2025-05-07T04:48Z`), était la fenêtre
> de référence de la construction du protocole, et elle n'a servi qu'à cela : aucune sélection n'a été produite
> sous elle (§ L.1, § D.3). Elle reste citée aux § 0.2, § A.8 et § D.3 comme fait historique.
>
> **La fenêtre de la première campagne est déclarée ici, et elle ne bouge plus.** Borne basse au 2021-03-01,
> déclarée le 2026-09-23 et maintenue au gate du même jour. Sur la base USDT importée depuis le 2019-01-01 (SOL
> depuis le 2020-08-11) **[v]** `results/data_inventory_usdt_2019_20260923/inventory.md`, l'amorçage des séries
> 4 h et 1 d (jusqu'à 200 bougies) est couvert à cette date sur les trois paires, et celui du 1 w — régime 1 w, 50 bougies **[v]**
> `scripts/backtest.py:305`, `:420-425` — sur BTC et ETH ; pour SOL, la 50ᵉ estampille 1 w tombe le 2021-07-26.
> La conséquence sur D2 est écrite au § A.8, pas découverte. Borne haute au 2026-06-29, dernière semaine
> hebdomadaire publiée : la série 1 w s'arrête au 2026-07-06 et Vision n'a pas publié 2026-07/08 ; finir la
> fenêtre **avant** le trou de queue évite qu'une absence de publication soit lue comme une absence de données.
> Ces deux bornes sont écrites dans `docs/RESEARCH_LOG.md` et dans le manifeste gelé **avant tout run** ; changer
> de fenêtre est **une nouvelle campagne** et non une variante de celle-ci (critère d'arrêt,
> `docs/CONTRAINTES_POST_B4.md` § 10.1).
>
> **Le choix de fenêtre est un second levier de shopping**, au même titre que l'ancrage, et la règle
> « bornes du manifeste, déclarées avant évaluation » le ferme. Il est interdit de déplacer une borne après
> avoir constaté quoi que ce soit de la période évaluée.

**Il est interdit de déplacer `F` après avoir constaté la longueur de la période évaluée.**

### A.4 Les estampilles admissibles à l'ancrage

**Aucune bougie ne clôture à `04:48`** : 288 minutes après minuit n'est un multiple ni de 5, ni de 240, ni de
1440, ni de 10080 **[v]** (arithmétique, vérifiable à la main). **Le protocole ne demande donc jamais une
bougie estampillée exactement à la borne.**

Les données étant estampillées en fin de période (B4.1), la bougie estampillée `t` est close à `t` et
**appartient au passé de `t`**. La dernière observation admissible à l'ancrage est donc, par timeframe, la
dernière bougie estampillée `≤ T` :

| TF | Dernière observation admissible à `T = 2024-11-22T04:48Z` |
|---|---|
| 5 min | `2024-11-22T04:45Z` |
| 4 h | `2024-11-22T04:00Z` |
| 1 j | `2024-11-22T00:00Z` |
| 1 w | `2024-11-18T00:00Z` (le lundi 18 novembre) |

**Règle, et non les quatre valeurs** : pour chaque timeframe, l'observation admissible est **la dernière
estampille `≤ T`** de ce timeframe. Les quatre valeurs du tableau sont ce que cette règle donne à l'ancrage
déclaré ; **elles sont calculées par l'outil depuis `T`, jamais écrites en dur**. Le cas limite est couvert par
la règle et non par une formulation en prose : si `T` coïncide avec une estampille, **c'est celle-là**, pas la
précédente.

**Le prix de référence à une borne non alignée** est le **close de la dernière bougie estampillée `≤ T`** du
timeframe considéré. **Jamais une bougie postérieure** — ce serait une information indisponible à la décision.
Cette règle vaut des deux côtés : pour la stratégie comme pour le benchmark (§ C.3).

**Première exécution autorisée.** La décision à `T` s'appuie sur les observations ci-dessus. **Aucun
remplissage ne peut survenir à `T` ni avant** — la convention complète, des deux côtés, est au **§ C.3,
section d'origine**. Le premier remplissage possible est la bougie d'exécution
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
- **Transposition déclarée.** Un manifeste peut déclarer, par paire de l'univers, une **paire de
  déploiement** distincte de la **paire de validation** quand, et seulement quand, l'actif de base est le
  même et seule la monnaie de cotation diffère (première campagne : validation `BTC/USDT`, `ETH/USDT`,
  `SOL/USDT` sur la base Binance ; déploiement `*/USDC` sur Bybit EU). La transposition est **écrite une fois,
  ici, comme déclaration** : elle repose sur le même argument que la transposition de site Binance → Bybit
  déjà admise par le projet — même actif de base, fees, spread et slippage de la cible mesurés sur la paire
  de déploiement (`CONTRAINTES` § 2) et déclarés au manifeste. **L'écart de peg entre les deux stablecoins
  n'est pas modélisé** : c'est un non-mesurable déclaré (§ J, item 11). L'identité du candidat (§ A.2) garde
  `pair = paire de validation` ; la paire de déploiement entre dans le manifeste, donc dans l'empreinte de la
  variante, et **n'entre pas** dans l'identité du candidat.
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
| Comptabilité | `liquidation[<préfixe>]`, entier. **Contrat de forme des quantités en actif de base** : les clés `amount_base`, `residual_trade_base`, `dust_written_off_base`, `inventory_divergence_base`, dans le bloc et dans chaque lot, **quelle que soit la paire** ; un bloc qui porte une clé suffixée par le nom d'un actif (`_btc`, `_eth`, …) est une erreur de forme (§ I.1, ligne 2). Le renommage vit dans la couche d'export du runner ; le moteur `scripts/backtest.py` est intouché |
| Amorçage | `warmup[<préfixe>]`, entier, **et** le bloc d'amorçage mesuré au début du préfixe |
| Exécution | `rejections[<préfixe>]`, `dca_counters[<préfixe>]` |
| **Couverture** | l'**artefact de couverture** décrit ci-dessous, pour la paire du candidat, sur `[début, T]` |

**L'artefact de couverture est une entrée à part entière, et il manquait.** Un bloc `warmup` décrit
**l'amorçage** — combien de bougies ont été chargées avant un instant, et si un trou les traverse. Il ne dit
**rien** de la couverture **sur toute la longueur du préfixe**, qui est ce que D1 mesure. Les deux ne se
substituent pas l'un à l'autre.

L'artefact de couverture est une **entrée du protocole, pas une sortie de son outillage** : il est produit
**avant** la sélection, et sa production n'appartient pas à la chaîne du § L.1 — c'est ce qui permet à
l'outillage de rester **pur et sans accès base**. Il porte, par paire et par timeframe : le **compte de bougies
observées**, le **compte attendu** sur `[début, T]`, la liste des **estampilles manquantes**, le **plus long
trou en jours**, et les premier et dernier jours couverts. Son empreinte entre dans celle du manifeste (§ A.6),
et la validité d'entrée (§ I-A) vérifie qu'il couvre exactement `[début, T]` et les paires de l'univers.

En C3a, il est **synthétique**, produit par les fixtures. Une application réelle le produit depuis la base,
en lecture seule, hors de cette chaîne.

**Écartés sans être lus** — et c'est la liste qui compte pour le § A.12 : tout bloc de segment autre que le
préfixe (les métriques, la trajectoire, la comptabilité, l'amorçage et les rejets postérieurs à l'ancrage), les
bornes postérieures à l'ancrage de `period`, et **toute clé de premier niveau non énumérée ci-dessus**, connue ou
inconnue. Un champ écarté n'est ni lu, ni haché, ni rapporté.

**Deux règles qui ne se confondent pas.**

1. Un champ **hors liste blanche** est **écarté silencieusement**, quel que soit son contenu. C'est là, et
   uniquement là, que peut vivre un futur différent — c'est ce qui rend le test du § A.12 exécutable au lieu de
   vide de contenu.
2. Un champ **dans la liste blanche** qui déclare une borne **postérieure à `T`** est une **erreur d'entrée
   (§ I.1)**, **jamais tronquée**. La troncature serait le re-découpage de courbe que le § D interdit, et elle
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

**Le dénominateur, par timeframe, écrit plutôt que supposé.** « 97 % des jours » n'a de sens que si le compte
attendu est défini. Sur `[début, T]` :

| Timeframe | Attendu | Unité comptée |
|---|---|---|
| 5 min | **288 par jour** | jours dont le compte observé atteint **au moins 144** |
| 4 h | **6 par jour** | jours dont les 6 estampilles sont présentes |
| 1 j | **1 par jour** | jours présents |
| **1 w** | **une estampille par période hebdomadaire**, ancrée au lundi, estampillée en **fin** de période | **périodes hebdomadaires** présentes, jamais des jours |

La dernière ligne est la subtilité : l'hebdomadaire ne se compte pas en jours. Sur un préfixe de 767,2 jours,
le dénominateur quotidien vaut ≈ 767 et le dénominateur hebdomadaire ≈ **110 périodes**. Une estampille
hebdomadaire manquante pèse donc `1/110 ≈ 0,91 %`, contre `1/767 ≈ 0,13 %` pour un jour manquant : **environ
sept fois plus, pas cent fois**. *(La version précédente écrivait « cent fois ». C'était faux, et l'ordre de
grandeur comptait puisqu'il justifiait la ligne.)* C'est pourquoi le seuil de 97 % s'applique **au dénominateur
propre de chaque timeframe**, et non à un compte de jours commun.

**Le seuil de 144 sur 288 est un choix, et il a une limite qu'il faut écrire.** Il est **repris du précédent**,
où une journée 5 min était comptée couverte dès la moitié de ses bougies. Classe : **qualité des données,
convention déclarée** — il n'est pas dérivé. Sa limite est réelle : un motif régulier d'**une bougie manquante
sur deux** affiche **100 % de jours couverts** alors que **50 % des bougies sont absentes**. D1 ne voit donc pas
ce motif-là. Le complément qui le verrait — un taux de complétude agrégé sur toute la fenêtre, et non un compte
de jours — **n'est pas imposé par cette version**, et l'absence est déclarée plutôt que comblée à la hâte.

**Pourquoi 1 w est couvert.** Le rejeu a mesuré deux estampilles hebdomadaires manquantes sur BTC **à
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

**La liste des timeframes de décision est dérivée, jamais déclarée.** Pour un candidat, « chaque timeframe
qui alimente une porte de décision » est la liste que **la stratégie elle-même** dérive de ses paramètres
effectifs (pour la famille grid : `bear_protection_mode` et `bias_1d` décident si `regime_1d` et la porte 1 w
vivent), par une méthode de classe pure, testée, **sans changement de comportement du moteur**. Le producteur
exporte cette liste **par candidat** dans **toute** observation (`decision_timeframes`) — une observation ne
porte aucun drapeau qui la distinguerait d'une fixture. Le manifeste la redit, par stratégie ou par candidat
(surcharge) ; **un désaccord entre la liste exportée et la liste effective du manifeste pour ce candidat est
une violation** (§ I.1, ligne 15), jamais un arbitrage, et les deux listes se comparent en ensembles. Une
observation sans `decision_timeframes`, ou qui en porte une liste vide, dupliquée ou hors des séries déclarées,
est une erreur d'entrée (§ I.1, ligne 2) : D2 ne peut pas être mesurée sur une liste absente. Le recoupement
est fait à la validité d'entrée (§ I.2 I-A), qui lit l'observation entière ; la projection du § A.7 n'est pas
élargie.

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

**Ce que D3 ne couvre pas.** Aucune clause d'admissibilité ne porte sur la **fenêtre d'évaluation** : un
candidat admissible sur son préfixe peut n'y produire presque rien. Ce protocole **n'impose volontairement aucun
plancher d'activité post-ancrage**, pour une raison de principe — un tel plancher serait une condition **sur le
résultat** de la période qu'on prétend ne pas avoir regardée, et il rouvrirait la porte que le § 0.2 (a) ferme.

> **Ce qui était écrit ici et qui était faux.** La version précédente concluait : « l'incertitude post-ancrage
> d'un candidat peu actif sera large, et l'issue sera `inconclusif` ». **C'est faux** : rien ne garantit qu'une
> faible activité produise une borne large, et l'issue n'est pas automatique.
>
> **La correction de la correction.** La révision suivante avançait qu'une trajectoire constante rend `Δ*`
> constant. **C'est faux aussi** : si la configuration est plate pendant que le comparateur varie, `Δ*`
> **varie**. La révision d'après ajoutait qu'une largeur nulle « exige que les deux côtés soient
> déterministes » — **faux également**, et dans l'autre sens : c'est une condition **suffisante**, pas
> **nécessaire**. Deux trajectoires **variables et identiques** sous rééchantillonnage apparié donnent aussi un
> `Δ*` constamment nul. L'énoncé exact est au **§ A.13, E2**.
>
> Elle ajoutait qu'un candidat inactif pourrait franchir `Q1` et `Q2` grâce à la baisse de son comparateur.
> **Faux également** : `Q1` et `Q2` portent sur **son propre résultat** — `net_pnl` et rendement géométrique de
> la configuration — et ne lisent pas le comparateur (§ F.8). Un candidat plat échoue `Q1` et `Q2`, et la
> conclusion `réfuté` qui en découle est **légitime** : il n'a produit aucun effet économique sur la fenêtre.
> Seul `Q3` dépend du comparateur.

Ce qui reste réellement à couvrir est donc plus étroit que ce que j'ai écrit deux fois : un **bootstrap
dégénéré**, quand la distribution rééchantillonnée ne porte pas d'information. C'est l'objet du **§ A.13**.

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

> **Conséquence de D2 sur la fenêtre de v2.0 (historique).** La fenêtre du § A.3 commence au
> 2023-04-01, et l'amorçage 1 d / 1 w remonte alors dans les trous 2022-23 des données (`CONTRAINTES` § 7).
> Mesuré sur l'unique artefact réel, `sufficient` est **`False`** en 1 d et 1 w sur BTC et sur SOL au début du
> préfixe. **D2 écarte donc aujourd'hui, de façon déterministe, tout candidat dont une porte de décision lit le
> 1 d ou le 1 w, sur ces deux paires, pour cette fenêtre.** Ce n'est pas une prédiction : c'est une conséquence
> des deux choix — la fenêtre et D2 — et elle est déclarée ici pour que le § F.6 ne se lise pas comme une
> prophétie. **La borne basse de la fenêtre est donc un levier sur D2 autant que sur l'ancrage**, et c'est une
> raison de plus de la déclarer au manifeste avant toute évaluation.

> **Conséquences de D2 et de D1 sur la fenêtre de v2.1, écrites plutôt que découvertes.** La fenêtre de la
> première campagne commence au 2021-03-01 sur la base USDT Binance, importée du 2019-01-01 (BTC, ETH) et du
> 2020-08-11 (SOL) au 2026-09-01, six timeframes (5 m, 15 m, 1 h, 4 h, 1 j, 1 w), contiguë hors maintenances
> Binance inférieures à un jour, un trou 4 h de deux bougies le 2019-05-15 hors de toute fenêtre, huit
> estampilles 1 w isolées **[v]** `results/data_inventory_usdt_2019_20260923/inventory.md`. Deux conséquences
> s'en déduisent, calculées par les fonctions de l'outillage sur les bornes déclarées :
>
> - **D2 sur SOL.** Le régime 1 w exige 50 bougies **[v]** `scripts/backtest.py:305`, `:420-425`. Au 2021-03-01,
>   SOL en porte **29** (première estampille 1 w le 2020-08-17) ; la 50ᵉ tombe le **2021-07-26**. D2 retire donc
>   tout candidat SOL dont une porte de décision lit le 1 w : **SOL est partiel dans la première campagne, ou
>   absent** si tous les modes de la famille lisent le 1 w. BTC et ETH sont amorcés sur toutes leurs séries au
>   début du préfixe. Une paire dont un timeframe de décision n'est pas amorcé au 2021-03-01 sort par D2 sur ses
>   candidats, et la clause de promotion du § I.1 s'applique telle quelle.
> - **D1 sur le 1 w.** Six des huit estampilles 1 w isolées tombent **dans le préfixe** — 2022-06-06,
>   2022-07-04, 2022-09-05, 2022-10-03, 2022-11-07, 2022-12-05, les mêmes sur les trois paires ; les deux autres
>   (2025-02-03, 2025-03-03) tombent dans la période évaluée. Sur les 194 périodes hebdomadaires de
>   `(2021-03-01, T]`, **188 sont présentes, soit 96,9 %, sous les 97 % de D1**, sur BTC, ETH et SOL ; le trou
>   maximal, 7 jours, reste sous la borne de 31 jours. Sans reconstruction, D1 retire les trois paires et
>   l'ensemble admissible est vide : `A_NO_ADMISSIBLE_CANDIDATE` (§ I.1, ligne 8).
>
> **Aucune reconstruction des estampilles 1 w manquantes n'est faite tant que D1 passe** (décision C3 du
> 23/09). D1 ne passe pas sur cette fenêtre : **la reconstruction depuis le 1 d est une décision séparée,
> chiffrée, en rows marquées dérivées, jamais silencieuse, et elle est un prérequis du manifeste de la première
> campagne.** Cette note déclare ce que la lecture des données laisse attendre ; l'outil, lui, mesure sur
> l'artefact de couverture.

### A.9 Score, classement, égalités

**L'ordre défini ici ne s'applique qu'à l'ensemble survivant du § A.10, jamais à l'ensemble admissible.**

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
  identité sont une erreur d'entrée** (§ I.1).
- **L'ordre d'entrée n'influence rien** : permuter les candidats dans le fichier ne déplace ni un score, ni un
  rang, ni le choix.

**D'où viennent les quantités de risque.** Le drawdown quotidien du candidat, son écart-type quotidien, et les
mêmes grandeurs du comparateur et de tout blend apparié (§ C.4) sont **recalculés par l'outillage sur
`equity_daily` du préfixe**, avec la même fonction et le même échantillonnage des deux côtés. La valeur
`max_drawdown_pct_daily` enregistrée dans le bloc de métriques est **rapportée** à côté du recalcul, avec
l'écart ; **cet écart n'est ni classé ni borné** — la NAV exportée est un `float`, l'écart est un résidu de
représentation, et lui donner un seuil serait inventer une classe (§ 0.5) pour un nombre qui ne décide de
rien. Le drawdown du moteur (`max_drawdown_pct_engine`, intra-bougie), que porte le bloc de métriques, n'est lu
par aucune règle de la chaîne et **n'entre dans aucune comparaison** (§ J, item 4).

### A.10 Le plancher, et **la séquence de sélection**

**C'est la section d'origine de la séquence de sélection (§ 0.7). Aucun autre passage ne la redit ; tous y
renvoient.**

**La séquence, en trois pas, dans cet ordre et sans exception :**

```
1.  FILTRER   — D1 à D6 (§ A.8) sur chaque candidat.            -> ensemble ADMISSIBLE
2.  FILTRER   — P1 ∧ P2 ∧ P3 sur chaque candidat admissible.    -> ensemble SURVIVANT
3.  CLASSER   — l'ordre total du § A.9 sur le seul ensemble SURVIVANT.
                La configuration retenue est son PREMIER.
```

**On filtre avant de classer, et c'est une correction.** La version précédente classait l'ensemble
**admissible** puis appliquait le plancher à côté ; les deux passages désignaient alors des configurations
différentes. Contre-exemple minimal, à couvrir par une fixture :

| Candidat | CAGR préfixe | `Δ^dd` | P2 | Classé par `Δ^dd` |
|---|---|---|---|---|
| **A** | 1,5 %/an | **+3** | **échoue** | 1ᵉʳ |
| **B** | 3,0 %/an | +1 | passe | 2ᵉ |

Classer puis filtrer désigne **A**, qui ne franchit pas le plancher. Filtrer puis classer désigne **B**. **La
séquence ci-dessus impose B.**

**Les portes sont évaluées sur tout l'ensemble admissible, jamais sur un gagnant pré-trié** — trier par une
quantité puis tester le premier renverrait un « non » opératoire alors qu'un autre candidat du même ensemble
passe. C'est une correction déjà acquise au gate du rejeu, reprise telle quelle.

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

**C'est la section d'origine de l'interdiction de repêcher (§ 0.7).** Les § A.13 et § K.1 y renvoient.

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

### A.13 Estimabilité post-ancrage — un garde-fou méthodologique, pas une contrainte universelle

**Ce que ce contrôle est.** Un **garde-fou méthodologique déclaré d'avance** : il refuse de publier une borne
que la procédure du § F.2 n'a pas pu estimer. Ce n'est **pas** une contrainte mathématique universelle, et il
est présenté comme un choix, avec ses limites.

Deux conditions, mesurées **sur la fenêtre d'évaluation**, avant qu'une issue `validé` ou `réfuté` puisse être
prononcée :

| # | Condition | Classe |
|---|---|---|
| **E1** | La trajectoire **évaluée** compte au moins **10 % de jours à rendement non nul** sur la fenêtre. **Le comparateur n'est pas soumis à E1** | qualité des données, **convention déclarée** |
| **E2** | **Chacune des six** distributions rééchantillonnées de `Δ*` — une par combinaison `L × appariement` du § F.2 (h) — porte **au moins deux valeurs distinctes** sur ses réplications retenues. Une seule distribution constante suffit à faire échouer E2 | garde-fou méthodologique |

Un échec donne **`inconclusif (F_NOT_ESTIMABLE)`**, de portée run (§ I.1). **Ni `validé`, ni `réfuté`.**

**E1 — pourquoi le comparateur en est exempté.** Le comparateur peut être **du cash pur** : c'est exactement ce
que donne `λ = 0`, prévu et traité au § F.2 (g) quand la cible de risque du candidat est nulle. Un comparateur
cash est **déterministe** — tous ses rendements sont nuls par construction, non par manque de données. Lui
imposer 10 % de rendements non nuls rendrait **systématiquement inconclusive** toute comparaison à `λ = 0`,
y compris avec une stratégie parfaitement active et une distribution de `Δ*` parfaitement calculable, puisque
`Δ*` varierait alors avec le seul rééchantillonnage de la stratégie. E1 ne porte donc que sur la trajectoire
évaluée.

**E1 — le seuil de 10 %, et ce qu'il vaut.** Il est **repris du précédent**, où il valait `nnz ≥ 110` sur 1096
jours, et où la pré-spécification le qualifiait elle-même de « **filtre conventionnel d'activité, pas une preuve
de quantité d'information** ». **Je ne peux pas le dériver pour C3**, et ce document ne prétend pas l'avoir
fait : c'est une **convention** reconduite, déclarée comme telle, dont la seule justification est qu'une série
comptant moins d'une dizaine de pour cent de jours informatifs fait dépendre la distribution rééchantillonnée
du tirage d'un ou deux amas. Le gate peut le retenir, l'ajuster ou le supprimer ; il ne doit pas le lire comme
un résultat.

**E2 — ce qu'il attrape.** `Δ* = CAGR(config) − CAGR(comparateur)`. **E2 détecte une distribution
rééchantillonnée de `Δ*` constante, quelle qu'en soit la cause.** Deux causes au moins la produisent :

- **deux trajectoires déterministes** — par exemple une configuration plate comparée à du cash ;
- **deux trajectoires variables identiques** sous rééchantillonnage **apparié** : leurs `CAGR` changent d'une
  réplication à l'autre, mais leur **différence vaut toujours zéro**, puisque les mêmes indices de blocs sont
  appliqués aux deux séries (§ F.2 a).

E2 ne présume donc **aucune** cause, et il n'exige pas que les deux côtés soient déterministes. *(La rédaction
précédente l'affirmait : elle transformait une condition **suffisante** en condition **nécessaire**. La
condition opérationnelle d'E2 n'a pas changé ; seule son explication était fausse.)* E2 est un garde-fou étroit,
et **c'est délibéré** : il refuse une borne sans information, il
ne juge pas l'activité.

**Pourquoi conjonctive.** `validé` exige une borne strictement positive dans les six combinaisons (§ H.1).
Une distribution constante ne porte pas de borne estimable : sur cette combinaison-là, le test « borne > 0 »
n'est ni vrai ni faux, il est **inévaluable**. Une conjonction de six tests dont un est inévaluable n'est pas
« partiellement vraie » ; elle est inévaluable, et l'issue est `inconclusif (F_NOT_ESTIMABLE)`. E1, elle, ne
porte que sur la trajectoire évaluée, unique, et reste une seule condition.

**Ce contrôle n'est pas un repêchage** (§ A.11, section d'origine de cette interdiction). Un repêchage
**remplace** un candidat écarté ou **relâche** une clause. E1 et E2 ne font ni l'un ni l'autre : ils
**retirent une issue**, ils n'en fabriquent aucune, et **aucun candidat de substitution n'est jamais
sélectionné**. La configuration retenue reste celle du § A.10 ; si son évaluation n'est pas estimable, le
protocole le dit et s'arrête. On peut perdre une conclusion, on n'en gagne jamais une par un second tour.

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
l'ancrage. Les runners n'exportent aucun des trois.

*Et transporter des champs existants ne suffirait pas.* Le dump `--equity-out` produit bien `cash`,
`inventory_qty` et `mark_price` **[v]** `scripts/backtest.py:3722-3743`, mais **chaque point est écrit après le
traitement d'une bougie** **[v]** `:1959-1960` pour le moteur signal et `:2333-2334` pour le grid. Un tel point
décrit un **état postérieur**, pas l'état initial. Et à l'ancrage déclaré, la situation est plus nette encore :
**aucune bougie n'est estampillée à `T = 04:48`** (§ A.4), donc **aucun point n'existe à `T`** — le premier
point disponible est postérieur à l'instant dont on voudrait prouver l'état.

**C3b doit donc spécifier une preuve de départ à plat, pas déplacer des colonnes.** Ce que cette preuve doit
établir, sans quoi la clause reste non vérifiable : qu'à l'instant `T`, **avant** tout traitement, le cash vaut
le capital déclaré, la quantité détenue est nulle, et aucun ordre n'est en attente. **Tant que cette preuve
n'est pas spécifiée, C3b n'est pas un « simple changement de runner »**, et ce document ne le présente pas comme
tel. Le travail reste sous gate humain et sous invariant de confinement `compare-ab --strict`.

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
| **W-ancrage** | `T` | l'amorçage du **portefeuille évalué** — échec : **`D_WARMUP_ANCHOR`**, dont la portée et le code sont au § I.1 |

Les deux sont chronologiquement propres : le rapport de warmup est construit sur
`history = [c for c in candles if c.timestamp <= start]` **[v]** `scripts/backtest.py:502`, fonction pure de
(paire, timeframe, instant, base `≤` instant). **Il ne lit aucune donnée postérieure à son instant.**

Piège à ne pas reproduire : la série **fournie** aux indicateurs court jusqu'à la borne finale — correct pour un
run continu — mais **seul le rapport est pur**. Un implémenteur ne doit pas confondre la série nourrie et
l'objet de warmup.

### B.6 Clause 5 — la première exécution

**Section d'origine : § C.3.** Rappel sans reformulation : aucun remplissage à `T` ni avant ; le premier
remplissage possible est la bougie d'exécution
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

### C.3 Décider et exécuter — deux instants, jamais un seul

**C'est la section d'origine de la convention d'exécution des deux côtés (§ 0.7).**

**Le défaut que cette section corrige.** La version précédente faisait entrer le benchmark au *close connu à
`T`*. Un prix **connu** n'est pas un prix **exécutable** : le close de minuit est connu à 04:48, il n'est pas
un prix d'achat à 04:48. Contre-exemple : l'actif vaut 100 à minuit, 110 à l'instant d'exécution, puis reste
constant. Le benchmark s'attribuait **≈ +10 %** d'un mouvement **antérieur à son investissement**, sans avoir
jamais pu acheter à 100. Déclarer l'écart « non mesurable » ne réparait rien.

**La distinction, posée une fois.**

| | Ce que c'est | Ce qui l'alimente |
|---|---|---|
| **Instant de décision** | l'ancrage `T`, ou la borne considérée | les **observations disponibles** : dernière estampille `≤ T` par timeframe (§ A.4) |
| **Instant d'exécution** | la **première bougie d'exécution estampillée strictement après `T`** | son propre prix, et les coûts déclarés |

**Une exécution future prévue d'avance n'est pas une fuite de sélection** : la décision n'a lu que le passé de
`T`, seul le remplissage est postérieur. C'est exactement la séparation décision / exécution que C2 a posée pour
le grid — décision aux clôtures de la série de décision, exécution sur la série d'exécution, ordre tranché à
timestamp égal **[v]** `scripts/backtest.py:586` et `:2450`.

**Ce qui est synchronisé est la contrainte, pas l'événement.** La version précédente écrivait que les deux
côtés « exécutent à la même bougie, au même prix de marché ». **C'est faux, et cela réécrivait les moteurs par
mégarde** : le moteur signal remplit un ordre au marché à l'**open** de la bougie N+1, et un ordre limite **à
son prix limite** si la bougie le touche, sinon pas du tout **[v]** `scripts/backtest.py:1205-1231` ; le moteur
grid, lui, attend ses propres décisions et ses franchissements de niveaux. Aucun des deux n'exécute « au close
de la bougie suivante ».

**Ce que les deux côtés partagent, et c'est tout :**

| Contrainte commune | Énoncé |
|---|---|
| Information | **les mêmes observations disponibles à `T`** : dernière estampille `≤ T` par timeframe (§ A.4) |
| Résolution | **le même intervalle d'exécution**, déclaré au manifeste |
| Antériorité | **aucun remplissage à `T` ni avant**, des deux côtés |

**La stratégie garde ses signaux et ses règles de remplissage**, inchangés. **Le benchmark a sa propre
convention d'achat, pré-spécifiée ici** — il n'a ni signal ni ordre limite, donc il lui en faut une :

> **Convention d'achat du benchmark.** Le benchmark achète **une fois**, au **prix constaté à l'instant de
> clôture de la première bougie d'exécution dont l'estampille est strictement postérieure à `T`**. La
> liquidation terminale est symétrique, au prix constaté à l'instant de clôture de la dernière bougie
> d'exécution estampillée `≤ borne haute`. Les deux jambes paient taker, spread et slippage.
>
> *Justification.* Le benchmark ne décide rien : il n'a pas besoin d'un prix d'ouverture, qui ne servirait
> qu'à un ordre déclenché par un signal. Ce qu'il lui faut est un prix **postérieur à la décision** et
> **effectivement constaté**. La clôture de la première bougie postérieure est le premier instant qui satisfait
> les deux.

**Instant du prix et estampille de la bougie sont deux choses, et à un ancrage hors grille elles divergent.**
Les bougies sont estampillées en **fin** de période. À `T = 04:48`, la première bougie 5 min estampillée
strictement après `T` porte l'estampille `04:50` — mais elle **ouvre à `04:45`**, soit **avant `T`**. Son
**open n'est donc pas un prix postérieur à `T`** ; sa **clôture, à l'instant `04:50`, l'est**.

| Grandeur | Valeur à `T = 04:48` | Postérieure à `T` ? |
|---|---|---|
| Estampille de la bougie retenue | `04:50` | oui |
| Instant de son **open** | `04:45` | **non** |
| Instant de sa **clôture** | `04:50` | **oui** |

**Exigence, donc** : l'**instant du prix utilisé** est strictement postérieur à `T`. L'estampille seule ne
suffit pas à le garantir. C'est aussi pourquoi la convention « open de la bougie suivante » du moteur signal
**ne se transpose pas** : elle vaut pour une décision prise **sur une clôture de bougie**, où l'open suivant est
bien postérieur à la décision. L'ancrage étant hors grille par construction (§ A.3, aucun arrondi de `04:48`),
cette condition n'est pas remplie et la convention ne peut pas être recopiée.

| | Stratégie | Benchmark |
|---|---|---|
| Série de décision | le ou les timeframes de ses portes | sans objet : aucune porte, aucun indicateur |
| Série d'exécution | l'intervalle d'exécution déclaré au manifeste | **le même** |
| Bornes de chargement | `>= borne basse` et `<= borne haute` | idem, sur les séries qu'il utilise |
| Instant de disponibilité | estampillage fin de période : la bougie estampillée `t` est close à `t` | idem |
| Déclenchement d'un remplissage | **ses signaux** : marché à l'open de N+1, limite au prix limite si touché, sinon pas de fill **[v]** `scripts/backtest.py:1216-1231` ; le grid, ses franchissements de niveaux | **sa convention pré-spécifiée ci-dessus**, un achat unique |
| Antériorité | aucun remplissage à `T` ni avant | idem |
| Quantité détenue | selon la stratégie | `C × (1 − taker) / prix d'exécution d'entrée`, spread et slippage inclus dans ce prix |
| Marquage entre les bornes | equity du moteur, rééchantillonnée quotidiennement (contrat C1) | `quantité × close quotidien`, même grille quotidienne |
| Warmup | bloc `warmup`, deux contrôles (§ B.5) | sans objet |
| Frais | modèle `--fees` et coûts par paire, maker/taker par site de remplissage | taker + spread + slippage sur **les deux** jambes |
| Valorisation finale | § B.3 | une liquidation terminale, à la convention ci-dessus |

**Ce que cette section ne fait pas.** Elle **ne modifie aucun moteur**, et elle ne prétend plus à une égalité
d'exécution qui n'existe pas. Les deux courbes ne sont pas comparables parce qu'elles feraient la même chose au
même instant — elles ne le font pas — mais parce qu'elles sont **soumises à la même contrainte
d'information et d'antériorité**, et qu'aucune des deux n'utilise un prix que sa décision ne pouvait pas
attendre.

**Conséquence sur le rééchantillonnage.** La trajectoire du benchmark est construite à la résolution
d'exécution pour ses **deux** remplissages, puis **marquée quotidiennement** comme celle de la stratégie. Les
deux courbes vivent donc sur la **même grille quotidienne** (contrat C1) et le § C.5 les compare point à point.

**Les fonctions du rejeu sont réutilisables après vérification de leur contrat, jamais telles quelles.** Cas
concret et bloquant : `select_entry_candle` **[v]** `scripts/audit/rejeu_benchmark.py:166-186` prend la bougie
estampillée exactement à la borne, **sinon la première bougie suivante dans les 24 h**. Aucune des deux branches
n'est la convention ci-dessus : la première entre à un prix connu mais non exécutable, la seconde entre jusqu'à
19 h plus tard à la résolution quotidienne. **C3 écrit sa propre sélection d'entrée**, qui applique la règle
« décider à `T`, exécuter à la bougie d'exécution suivante ». `build_full_notional` et `benchmark_metrics` sont
paramétrés par leurs bornes mais **appellent** la sélection d'entrée : l'adaptation se fait **par injection,
pas par copie**, et **sans modifier le diagnostic gelé**. `comparability_block` est inutilisable en l'état : il
code en dur le compte de rendements de la fenêtre du rejeu **[v]** `scripts/audit/rejeu_benchmark.py:322`.

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
| Jours forward-fillés du benchmark | **la règle de D1** (§ A.8, section d'origine des seuils de couverture), appliquée à la fenêtre considérée | un comparateur marké sur des prix périmés |
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

### F.2 La procédure d'incertitude — figée avant tout code

**C'est la section d'origine de la procédure et de la formule de la borne (§ 0.7).** Elle est écrite ici,
**appliquée en C3b**. Rien de ce qui suit n'est laissé au moment de l'implémentation : une borne percentile et
une borne pivotale diffèrent, et sous les queues lourdes mesurées au rejeu **elles peuvent inverser une
décision**.

**(a) L'objet rééchantillonné.** Les **rendements quotidiens** de la configuration évaluée et de son
comparateur, sur la grille quotidienne commune du § C.3, **indices appariés** — la même suite de blocs est
appliquée aux deux séries, sans quoi l'écart ne serait pas celui d'une comparaison.

**(b) Le rééchantillonnage.** Blocs **circulaires**, longueurs `L ∈ {10, 21, 42}` jours avec `L = 21` en tête,
`B = 10 000` réplications. Les indices de départ sont tirés **une fois par `L`, avant tout découpage en lots**,
par `numpy.random.default_rng([graine, index de paire, L])` ; la graine est **déclarée au manifeste** avant
évaluation et entre dans l'empreinte (§ A.6). Classe de `L` et de `B` : qualité des données ; classe de la
graine : contrat.

**Le tirage, écrit pour être rejoué.** L'**index de paire** est la position de la paire de la configuration
évaluée dans la liste **triée** des paires de l'univers (celle que porte l'artefact d'ancrage). Pour chaque `L`,
les départs de blocs sont tirés **en un seul appel**, `rng.integers(0, n, size=(B, ⌈n / L⌉))`, `n` étant le
nombre de rendements quotidiens de la fenêtre d'évaluation ; les indices d'une réplication sont
`(départ + k) mod n` pour `k = 0 … L − 1`, concaténés bloc après bloc et tronqués aux `n` premiers.
**Les mêmes indices** servent à la configuration et au comparateur, et **aux deux appariements** d'un même
`L` : seul le comparateur change entre `dd` et `σ`. Ce tirage, et le calcul du § F.2 (c), ne sont exacts que
dans l'environnement qui les a produits, que l'artefact d'évaluation déclare (§ I.2 I-C) en **quatre champs,
et quatre seulement** :

```
python    platform.python_version()
numpy     numpy.__version__
machine   platform.machine()
libc      platform.libc_ver() : la bibliothèque et sa version, séparées par une espace, espaces de bord retirées
```

Jamais la version du noyau du système d'exploitation, qui ne change pas le calcul. Sur macOS,
`platform.libc_ver()` est vide, et `libc` aussi : ce que ce champ ne distingue pas est déclaré au § J, item 12.

**Les valeurs de `L`, `B` et le niveau de la borne sont des contrats d'instrument au sens de D5, comme
l'environnement du tirage et les deux appariements du comparateur** : un artefact d'évaluation qui déclare
`B ≠ 10 000`, une longueur de bloc hors `{10, 21, 42}`, une combinaison manquante ou surnuméraire, un comparateur
qui ne porte pas **exactement** les deux appariements `dd` et `σ`, ou un environnement qui n'est pas
**exactement** celui où la chaîne rejoue — un champ en trop compris — est un **contrat rompu** :
`R0_INVALID_RUN`, code 2, rien n'est publié (§ I.1, ligne 2). Ce contrôle est fait **avant toute lecture**,
séries comprises : un `B` hors contrat accompagné d'un compteur contradictoire ou d'un non-fini dans une suite
rééchantillonnée sort en refus de contrat, jamais en violation par accident d'ordre de lecture. Précédent :
`rejeu_validate_analysis.b02_frozen_parameters`.

**(c) Le rendement géométrique et l'annualisation.** Pour chaque réplication, le rendement géométrique
annualisé est calculé **par somme des `log1p`** ; aucune trajectoire n'est reconstruite pas à pas depuis le
capital `C` (§ 0.5) :

```
CAGR = (exp((Σ log1p(r) × 365) / n_jours) − 1) × 100          en %/an
     = (numpy.exp((numpy.log1p(r)[indices].sum(axis=1) * 365) / n_jours) - 1) * 100
```

`r` est le vecteur des rendements quotidiens, `indices` la matrice `(B, n)` des indices des réplications
(§ F.2 b). `n_jours` est la durée de la fenêtre d'évaluation, pas le nombre de rendements : `(fin − T)` en
secondes, divisé par 86 400, en double précision. **L'ordre des opérations fait partie de la définition** : la
somme est multipliée par 365, **puis** divisée par `n_jours` — une seule division, faite en dernier.
`somme × (365 / n_jours)` donne un autre nombre au dernier bit sur une part des réplications — environ une sur
vingt pour la série témoin des tests, mesuré le 2026-09-23 —, et le rejeu est une égalité au bit (§ F.2 d).
`Δ* = CAGR(config) − CAGR(comparateur)` sur la **même** réplication.

**Un seul chemin de calcul.** Ce chemin est **le seul** : appliqué aux indices identité `[[0 … n − 1]]`, il
donne le `CAGR` observé de la configuration (porte `Q2`, § F.8) et celui de chaque comparateur, donc `Δ̂` par
appariement — `Δ̂` en drawdown est la valeur de la porte `Q3` et le centre des trois bornes `dd` ; `Δ̂` en
écart-type, le centre des trois bornes `σ`. Une seule fonction, une seule convention : aucune divergence
d'arrondi entre l'estimation et ses réplications.

**(d) La borne, sa formule, son niveau, sa convention de quantile.** Borne inférieure **unilatérale à 95 %**,
de forme **pivotale (« basic »)**, recentrée sur l'estimation :

```
LB = Δ̂ − quantile_{0,95}( Δ*_b − Δ̂ )        b = 1..B
quantile : numpy.quantile(..., method="linear")
```

*Pourquoi pivotale et pas percentile.* La forme pivotale corrige le déplacement de la distribution
rééchantillonnée par rapport à l'estimation, là où la forme percentile le reporte tel quel dans la borne. Sous
une distribution asymétrique à queues lourdes — la kurtosis mesurée au rejeu était dominée par une journée de
liquidation — les deux bornes diffèrent, et la différence peut changer le signe de `LB`. C'est aussi la forme
qu'employait le précédent (`LB_j = Δ̂_j − q`). **Le choix est déclaré ici parce qu'il est décisionnel**, pas
parce qu'il est neutre. Classe : préférence méthodologique déclarée.

**Qui calcule, et ce que la chaîne rejoue.** La procédure est **exécutée par le producteur d'évaluation**
(C3b), qui exporte les séries quotidiennes de la configuration et du comparateur de chaque appariement —
**toutes de même longueur `n`** —, et, par combinaison, la suite `Δ*` retenue **dans l'ordre des réplications
`b = 1 … B`, écartées retirées**, le compte de réplications écartées et la borne. Toute valeur est publiée en
double précision, **sérialisée par le `repr` le plus court qui se relit à l'identique** — la convention de
`canon` (§ A.1 bis) —, jamais « avec assez de décimales ». La chaîne (§ L.1) **rejoue le tirage** — graine
du manifeste, index de paire, `n_jours`, tirage et chemin de calcul des § F.2 (b) et (c) — et **recalcule**
les six suites, les comptes d'écartées, `Δ̂` par appariement, le `CAGR` de la configuration et les six bornes.
**Toute différence avec ce que l'artefact déclare est une violation** (§ I.1, ligne 15) — la comparaison est une
égalité au bit, ordre des suites compris —, et les portes `Q2`, `Q3` et les bornes décident sur les valeurs
**rejouées**. Le rejeu n'est exécuté que dans l'environnement que l'artefact déclare : sinon, contrat rompu
(§ F.2 b), jamais une comparaison tolérante. Des séries de longueurs différentes rendent les indices appariés
impossibles (§ F.2 a) : le rejeu est **inexécutable**, erreur d'entrée (§ I.1, ligne 2), code 2. **Ce qui
reste déclaratif** : les séries quotidiennes elles-mêmes et `net_pnl` (porte `Q1`), qu'aucune série de
l'artefact ne permet de recalculer (§ J, item 12).

**(e) Entrées invalides et échecs numériques — deux choses distinctes, une seule règle.**

**C'est la section d'origine du traitement des non-finitudes pendant le bootstrap (§ 0.7) ; le § F.7 traite les
non-finitudes dans les *entrées*, et les deux ne se recouvrent pas.**

| | Ce que c'est | Quand | Traitement |
|---|---|---|---|
| **Entrée invalide** | un `NaN`, un infini, un `λ` non fini ou un rendement `≤ −1` **dans les données fournies** à la procédure, ou une série dont le `CAGR` **observé** — chemin du § F.2 (c), indices identité — n'est pas fini : l'estimation elle-même n'existe pas, il n'y a rien à écarter | **avant** tout tirage | **erreur d'entrée** : § I.1, ligne 15. Aucun bootstrap n'est lancé |
| **Échec numérique** | une **réplication** produit un `Δ*` non fini : l'exponentielle du § F.2 (c) déborde vers l'infini (d'un côté, `Δ*` est infini ; des deux, `∞ − ∞` n'est pas défini) | **pendant** le tirage | la réplication est **écartée et comptée** |

**Rien d'autre n'est écarté.** Un rendement `≤ −1` étant une entrée invalide (ligne du dessus), `log1p` est
défini partout et la somme du § F.2 (c) ne « va à zéro » nulle part. v2.0 écartait aussi la réplication dont
« un rendement rééchantillonné conduit la trajectoire à zéro » : la phrase décrivait un produit cumulé, qui
n'est pas le calcul du (c). Un `CAGR` de **−100 %/an exactement** — l'exponentielle sous-déborde vers 0 — est
une valeur **finie et légitime**, celle du pire chemin : la réplication est **retenue**. L'écarter biaiserait
la distribution vers les chemins qui finissent bien, ce que le paragraphe suivant interdit déjà pour le
retirage.

**Comment le quantile est calculé quand des réplications sont écartées.** Elles sont **exclues, comptées, et
non remplacées** : pas de retirage, qui biaiserait la distribution vers les chemins qui se terminent bien. Le
quantile du § F.2 (d) est calculé sur les **réplications retenues**, et l'artefact publie, **par
combinaison** `L × appariement`, **`B_effectif`**, le nombre effectivement utilisé, à côté de `B`. Un rapport
qui cite une borne sans le `B_effectif` de sa combinaison est incomplet. Une combinaison dont aucune
réplication n'est retenue ne porte pas de borne : la borne déclarée est nulle **si et seulement si** sa suite
retenue est vide, et l'écart, dans un sens ou dans l'autre, contredit l'artefact (§ I.1, ligne 15).

**Le plafond, et ce qu'il vaut.** Au-delà de **10 réplications écartées sur 10 000** — soit un `B_effectif`
inférieur à 9 990 — **sur l'une quelconque des six combinaisons** `L × appariement`, l'inférence est déclarée
**inutilisable** : issue `inconclusif (F_NOT_ESTIMABLE)`, et **aucune borne n'est citée par le verdict**.
L'artefact d'évaluation, lui, porte la borne de toute combinaison dont la suite retenue n'est pas vide
(ci-dessus), et la chaîne la recoupe au rejeu comme les autres. Classe : qualité des données, **convention
déclarée**. Le nombre est repris du précédent et **n'est pas dérivé** : il exprime qu'une poignée de chemins
dégénérés est tolérable, et qu'au-delà la distribution n'est plus celle qu'on croit échantillonner.

**(f) `λ` reste celui du préfixe pendant toute la procédure décisionnelle.** Le **mode** de `λ` est tranché au
**§ C.4, section d'origine** ; ce paragraphe n'en énonce que la conséquence procédurale : `λ` est estimé une
fois, sur le préfixe, puis **tenu fixe dans chaque réplication**. Le précédent, lui, ré-estimait `λ` dans chaque
réplication — et c'était correct **chez lui**, parce que son `λ` était apparié sur la fenêtre même qu'il
rééchantillonnait. Ici `λ` est une quantité **du passé**, décidée à l'ancrage : la ré-estimer après l'ancrage
changerait l'objet estimé. La ré-estimation post-ancrage est calculée et **rapportée comme sensibilité
descriptive**, elle ne fonde aucune issue.

**(g) Le domaine, le pas et la règle de choix de `λ`.** `λ ∈ [0, 1]`, recherche à deux étages : grille
grossière au pas **0,005**, puis raffinement **±0,005 au pas 0,001**. La cible est le risque réalisé du candidat
sur le préfixe — `max_drawdown_pct_daily` pour `λ_dd`, écart-type quotidien pour `λ_σ`. Trois cas, tranchés :

| Cas | Règle |
|---|---|
| **Cible nulle** (candidat sans drawdown, ou de volatilité nulle) | `λ = 0`. Le comparateur est **tout en cash**, ce qui est l'allocation de même risque. Le fait est **imprimé**, parce qu'un `Δ` contre du cash se lit autrement |
| **Croisements multiples** sur la grille | le **plus petit `λ`** qui atteint la cible est retenu, et **le nombre de croisements est imprimé** |
| **Aucun croisement** dans `[0, 1]`, ou résidu d'appariement au-delà de 10 % (§ 0.5) | le candidat est **`NOT_ESTIMABLE`** : son `Δ` décisionnel **n'est pas publié** (§ C.6) |

**(h) Les six combinaisons `L × appariement`.** La borne doit être strictement positive dans **les six**. C'est
une exigence de **robustesse au choix d'un paramètre de nuisance**. Ce que cette exigence n'est pas, et la
raison en est au **§ F.3, section d'origine** : ce n'est pas une correction de multiplicité, et ce document n'en
applique aucune.

### F.3 Multiplicité — l'énoncé restreint, et pourquoi il ne couvre pas notre cas

**C'est la section d'origine de tout ce que ce document dit de la multiplicité (§ 0.7).**

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

L'issue **`inconclusif` est prévue explicitement et n'est pas un échec du protocole**. Deux frontières, et
elles ne se confondent pas :

- une estimation **positive qui échoue à la borne** — une seule des six combinaisons suffit — est
  **`inconclusif (F_CANNOT_SEPARATE)`**, **jamais `réfuté`** : l'absence de séparation n'est pas une preuve
  d'absence ;
- une estimation qui **échoue aux portes ponctuelles** `Q1`, `Q2` ou `Q3` est **`réfuté`**, **jamais
  `inconclusif`** : sinon le négatif attendu s'échappe en « à re-tenter avec d'autres paramètres ».

La définition complète des issues est au **§ H, section d'origine** ; la portée d'un `réfuté` est au **§ K.1**.

### F.7 Valeurs indéfinies et infinies

Reprise du précédent, et manquante dans la première soumission.

- Un ratio à `None` — Sharpe, Sortino, Calmar, facteur de profit — n'est **jamais** comparé à un seuil, **jamais
  coercé en 0**, **jamais moyenné dans une décision**. **Aucune règle décisionnelle de ce document ne les lit** :
  `Δ`, `net_pnl`, le rendement géométrique, les cycles, le drawdown quotidien et l'écart-type quotidien portent
  toute la décision, et aucun d'eux ne peut valoir `None` sur une entrée valide. Cela **dissout** le problème du
  facteur de profit infini au lieu de le rustiner.
- Un `None` reste **imprimé** comme `None`, désambiguïsé par les sommes qui le produisent quand elles existent.
  Purement descriptif.
- Tout `NaN` ou infini **dans les entrées** — une NAV, un rendement, un `λ`, un `Δ` fournis à la procédure —
  est un **échec de validité** (§ I.1, ligne 15), pas un nombre à commenter. `canon` lève sur une valeur non
  finie (§ A.1 bis), donc une empreinte ne peut pas en masquer une.
- Une non-finitude **produite par une réplication pendant le bootstrap** n'est **pas** traitée ici : c'est un
  échec numérique, et sa règle unique est au **§ F.2 (e), section d'origine**. La version précédente de ce
  paragraphe la traitait comme une violation, ce qui contredisait le plafond de tolérance du § F.2. **Cet
  énoncé est supprimé.**
- Un candidat filtré **n'est jamais rempli par `−∞`** pour rester dans un calcul : il en **sort**. Remplir
  ne démontrerait pas la neutralité du filtre, cela la supposerait.

### F.6 L'attendu déclaré

> **Attendu déclaré avant toute application : `inconclusif`.**

Le déclarer d'avance **interdit de le renégocier après**. C'est un **attendu déclaré, jamais une conclusion
imposée** : il ne préjuge d'aucun résultat, et un résultat différent est consigné comme falsifiant l'attendu,
sans être renégocié.

### F.8 `Q1`, `Q2`, `Q3` — les portes ponctuelles post-ancrage

**C'est la section d'origine de ces trois portes (§ 0.7).** La version précédente les utilisait au § H sans les
définir nulle part : leur définition avait disparu à la réécriture du § F.2 et personne ne la portait plus.

Elles sont les portes du plancher du § A.10, **réévaluées sur la fenêtre d'évaluation** et contre le
**benchmark d'évaluation** du § C.4. Elles portent un nom distinct pour qu'on ne les confonde jamais avec les
portes de sélection, qui vivent sur le préfixe.

```
Q1   net_pnl(fenêtre d'évaluation) > 0
Q2   rendement géométrique de la fenêtre d'évaluation >= 2,0 %/an
Q3   Δ^dd post-ancrage > 0
```

**Leurs valeurs et leurs classes sont celles du § A.10**, section d'origine des seuils ; les répéter ici les
ferait diverger. Seuls les domaines de mesure changent.

**Ce que chacune lit, parce que la distinction a déjà induit une erreur dans ce document :**

| Porte | Lit | Ne lit pas |
|---|---|---|
| `Q1` | le **résultat propre** de la configuration : son `net_pnl` sur la fenêtre | le comparateur |
| `Q2` | le **résultat propre** de la configuration : son rendement géométrique | le comparateur |
| `Q3` | l'**écart** au comparateur apparié | — |

Conséquence directe : une configuration restée **plate** après l'ancrage échoue `Q1` et `Q2` **par son propre
résultat**, quelle que soit la trajectoire du comparateur.

**Mais l'échec de ces portes ne suffit pas à produire `réfuté`.** Une telle configuration échoue **aussi** E1
(§ A.13) : moins de 10 % de jours à rendement non nul. **L'estimabilité est préalable au verdict économique**,
et la préséance est énoncée **une seule fois, au § H** (§ 0.7). L'issue d'une configuration inactive est donc
**`inconclusif (F_NOT_ESTIMABLE)`**, jamais `réfuté`.

*(La rédaction précédente affirmait ici l'inverse — « la conclusion `réfuté` est légitime », « le § A.13 ne
couvre pas ce cas ». Elle contredisait E1, qu'aucune règle de verdict ne citait alors. C'est cette absence de
citation qui rendait la contradiction invisible : un symbole normatif sans site de référence est une porte que
rien n'applique.)*

---

## § G. Agrégation et non-règles

### G.1 Agrégation — une seule configuration, et la règle qui l'impose

**Il y a un seul classement et une seule configuration retenue, sur tout l'univers.** La séquence est celle du
**§ A.10, section d'origine** : filtrer par D1-D6, filtrer par P1-P3, puis classer les **survivants** par
l'ordre total du § A.9, **toutes paires confondues**. La configuration retenue est le **premier de ce
classement**, et il n'y en a qu'une.

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

### H.0 La préséance de l'estimabilité sur le verdict économique

**C'est la section d'origine de cette préséance (§ 0.7). Aucun autre passage ne la redit ; tous y renvoient.**

> **Les conditions d'estimabilité du § A.13 sont préalables à tout verdict économique.** Tant que `E1` et `E2`
> ne sont pas satisfaites, **ni `validé` ni `réfuté` ne peuvent être prononcés**, quel que soit le résultat des
> portes `Q1`, `Q2`, `Q3`. L'issue est alors **`inconclusif (F_NOT_ESTIMABLE)`**.
>
> **L'échec des portes ponctuelles ne produit `réfuté` qu'après satisfaction des conditions d'estimabilité.**

*Pourquoi cette préséance existe.* Une porte économique compare un résultat à un seuil. Si la fenêtre ne porte
pas de quoi estimer ce résultat, la comparaison a lieu mais **ne signifie rien** : on conclurait sur une absence
d'observation. Le cas concret est celui d'une configuration restée **inactive** après l'ancrage — elle échoue
`Q1` et `Q2` par son propre résultat (§ F.8), **et** elle échoue `E1`. La préséance tranche : l'issue est
`inconclusif`, pas `réfuté`.

*Ce que cette préséance n'est pas.* Ce n'est pas un repêchage (§ A.11) : elle **retire** une issue, elle n'en
fabrique aucune, et aucun candidat de substitution n'est sélectionné.

### H.1 Les trois issues

**`validé`** ⟺ le run est exploitable au sens du § I **et** l'univers est de provenance `clean` **et**
**les conditions d'estimabilité du § A.13 sont satisfaites** (§ H.0) **et** **la configuration retenue au sens
du § A.10** — pas « une configuration », **celle-là** — franchit P1 ∧ P2 ∧ P3 sur le préfixe, franchit
`Q1 ∧ Q2 ∧ Q3` sur la fenêtre d'évaluation (**§ F.8**), **et** sa borne d'incertitude post-ancrage est
strictement positive dans **les six** combinaisons `L × appariement` (§ F.2).

> **Pourquoi « celle-là » et pas « une ».** Un énoncé existentiel autoriserait à évaluer tous les candidats
> après l'ancrage et à déclarer `validé` si l'un survit : c'est **exactement** la fuite du § 0.2 (a), sous un
> autre nom. **Une seule configuration est évaluée après l'ancrage : celle que la sélection a retenue.**

**`réfuté`** ⟺ le run est exploitable, **l'univers est de provenance `clean`**, une configuration a été retenue,
**les conditions d'estimabilité du § A.13 sont satisfaites** (§ H.0), et son évaluation post-ancrage échoue à
`Q1`, `Q2` ou `Q3` (**§ F.8**).
Portée : *l'effet mesuré sur cette fenêtre est sous le minimum déclaré ; ce n'est pas une affirmation que
l'effet vrai est nul.* **Ce qu'un `réfuté` clôt exactement est au § K.1, section d'origine** — et ce n'est
jamais une famille.

> **Pourquoi `réfuté` exige aussi `clean`.** Sans cette condition, un univers que le protocole déclare inapte à
> soutenir un résultat positif pourrait tout de même **tuer une famille** — et le § K clôt le cas sur un
> `réfuté`. Ce cliquet à sens unique est précisément ce que le précédent avait refusé (`docs/rejeu_grid_prespec.md`
> § D.3 : « des données déclarées inadmissibles pourraient tuer une famille sans pouvoir la soutenir »). Un
> univers `contaminated` ou `unknown` rend donc `inconclusif (P_PROVENANCE)`, jamais `réfuté`.

**`inconclusif`** ⟺ tout le reste. Liste fermée des raisons, par ordre de priorité :

```
R0_INVALID_RUN              une assertion de validité d'entrée a échoué
P_PROVENANCE                univers `contaminated` ou `unknown`
D_WARMUP_PREFIX             D2 échoue sur la totalité des candidats de l'artefact
A_NO_ADMISSIBLE_CANDIDATE   l'ensemble admissible est vide
A_BELOW_FLOOR               ensemble non vide, aucun candidat ne franchit le plancher
D_WARMUP_ANCHOR             amorçage défaillant à l'ancrage d'évaluation
E_NO_BENCHMARK              benchmark non constructible ou non comparable
E_STAMP_MISMATCH            estampille de liquidation et borne finale en cellules distinctes
F_NOT_ESTIMABLE             estimabilité post-ancrage en défaut, ou aucun candidat estimable
F_CANNOT_SEPARATE           la borne ne sépare pas l'effet de zéro dans les six combinaisons
R1_NOT_NORMALISED           D6 : liquidation terminale non normalisée
D_NOT_ADMISSIBLE            D1 ou D5
C_COVERAGE                  D3 échoue, ou D3 est inapplicable
```

**Le vocabulaire des statuts est lui aussi clos**, et il ne se confond pas avec celui des raisons. Statuts
possibles d'un **candidat** : `ADMISSIBLE`, `NOT_ESTIMABLE`, `NON_ADMISSIBLE`, `HORS_USAGE_DÉCISIONNEL`.
Statuts possibles d'une **paire** : `VOTANTE`, `DESCRIPTIF`. Statuts possibles d'une **sélection** :
`SÉLECTION_VALIDE`, `SÉLECTION_DESCRIPTIVE`, `ABSTENTION`. Un statut décrit un objet ; une raison explique une
issue. `NOT_ESTIMABLE` (statut de candidat) et `F_NOT_ESTIMABLE` (raison) portent volontairement des noms
voisins et **ne sont pas la même chose** : le premier retire un candidat, le second n'apparaît que si le retrait
de tous les candidats se fait par cette voie.

**Lecture de la liste.** L'ordre ci-dessus est **l'ordre de priorité**, sans exception et sans départage à
inventer : la chaîne porte **la première raison qui s'applique**.

**La portée d'une raison — candidat, artefact ou run — n'est pas redite ici.** Elle est donnée par la **table
du § I.1, seule source** (§ 0.7). Une raison de portée candidat est imprimée à côté du candidat qu'elle a
retiré et ne porte pas la chaîne ; une raison de portée artefact ou run la porte. La version précédente de ce
paragraphe classait les raisons elle-même, et son classement avait divergé de la table : `D_WARMUP_ANCHOR`,
`E_NO_BENCHMARK`, `E_STAMP_MISMATCH` et `F_NOT_ESTIMABLE` y étaient interdits de chaîne alors que la table les
donne de niveau run. **Cet ancien classement est supprimé.**

`A_NO_ADMISSIBLE_CANDIDATE` reste atteignable parce qu'il est prioritaire sur les raisons de clause : l'ensemble
vide est le fait décisionnel, la clause qui l'a vidé est un diagnostic imprimé à côté.

**Un échec de niveau run court-circuite tout** : `R0_INVALID_RUN` est évalué avant toute autre chose, et
`D_NOT_ADMISSIBLE` déclenché par D5 est un échec de § I-A, donc il remonte en `R0_INVALID_RUN`.

---

## § I. Validité — étapes séparées

La boucle de dépendance est cassée : chaque étape ne lit que des artefacts produits avant elle.

### I.1 Portée, raison, code de sortie, poursuite — **la table unique**

**C'est la section d'origine de cette règle (§ 0.7). Aucun autre passage du document ne redit un code de
sortie ; tous renvoient ici.**

Trois portées, et trois seulement :

- **candidat** — le défaut concerne une simulation. Le candidat sort de l'ensemble, la chaîne continue.
- **artefact** — le défaut concerne un fichier d'observations entier. Cet artefact est refusé, la chaîne
  s'arrête pour lui.
- **run** — le défaut prouve que l'exécution n'est pas ce qu'elle prétend être. Tout s'arrête.

| # | Situation | Portée | Raison | Code | Poursuite autorisée |
|---|---|---|---|---|---|
| 1 | Entrée conforme | — | — | **0** | oui, étape suivante |
| 2 | Contrat d'instrument rompu : D5, unicité des identités, forme des blocs | **run** | `R0_INVALID_RUN` | **2** | **non** |
| 3 | Couverture insuffisante : D1 | **candidat** de la paire concernée, **tous** | `D_NOT_ADMISSIBLE` | **0** | oui ; la paire devient `DESCRIPTIF` |
| 4 | Amorçage du préfixe : D2, **sur une partie** des candidats | **candidat** | `D_WARMUP_PREFIX` | **0** | oui ; les autres candidats restent |
| 5 | Amorçage du préfixe : D2, **sur la totalité** des candidats de l'artefact | **artefact** | `D_WARMUP_PREFIX` | **2** | **non** ; aucun classement n'est produit |
| 6 | D1, D3, D4, D6 sur un candidat — **non promouvables** | **candidat** | `D_NOT_ADMISSIBLE`, `C_COVERAGE`, `F_NOT_ESTIMABLE`, `R1_NOT_NORMALISED` | **0** | oui ; si elles vident l'ensemble, ligne 8 |
| 7 | Provenance `contaminated` ou `unknown` | **run** | `P_PROVENANCE` | **0** | oui, mais la sélection est `SÉLECTION_DESCRIPTIVE` et `validé` est inatteignable |
| 8 | Ensemble admissible vide après D1-D6 | **run** | `A_NO_ADMISSIBLE_CANDIDATE` | **0** | non ; c'est une **abstention**, donc un résultat publié |
| 9 | Aucun survivant du plancher P1-P3 | **run** | `A_BELOW_FLOOR` | **0** | non ; abstention, résultat publié |
| 10 | Benchmark non constructible ou non comparable | **run** | `E_NO_BENCHMARK` | **0** | non ; issue `inconclusif` |
| 11 | Estampille de liquidation et borne finale en cellules distinctes | **run** | `E_STAMP_MISMATCH` | **0** | non ; issue `inconclusif` |
| 12 | **Amorçage défaillant à l'ancrage d'évaluation** | **run** | `D_WARMUP_ANCHOR` | **0** | non ; issue `inconclusif` |
| 13 | Estimabilité post-ancrage en défaut (§ A.13) | **run** | `F_NOT_ESTIMABLE` | **0** | non ; issue `inconclusif` |
| 14 | La borne ne sépare pas l'effet de zéro | **run** | `F_CANNOT_SEPARATE` | **0** | non ; issue `inconclusif` |
| 15 | Auto-contrôle d'instrument en défaut : statut recalculé ≠ statut enregistré, non-finitude, ordre non total | **run** | — | **1** | **non** ; c'est une violation, pas un résultat |

**La règle de promotion, lignes 4 et 5 — et la liste close des clauses promouvables.**

> **Une seule clause est promouvable dans cette version : D2.** Quand D2 échoue sur **la totalité** des
> candidats que porte l'artefact, l'échec est **promu en refus d'artefact** et **garde sa raison**
> (`D_WARMUP_PREFIX`, code 2, aucun classement). Quand D2 ne touche qu'une partie des candidats, il les retire
> et la chaîne continue.
>
> **D1, D3, D4 et D6 ne sont pas promouvables.** Si elles vident l'ensemble sur une entrée par ailleurs valide,
> l'issue est l'**abstention** `A_NO_ADMISSIBLE_CANDIDATE` (ligne 8, code 0, résultat publié), pas un refus
> d'artefact. D5 est déjà de portée run et n'a rien à promouvoir.

**C'est une convention de ce protocole, et elle est assumée comme telle.** Elle **ne se déduit pas** d'une
opposition entre « défauts de données » et « défauts de candidats », qui ne tiendrait pas : **D2 dépend aussi
des paramètres** du candidat — les timeframes qu'il fait vivre dépendent de sa configuration — et **D6 décrit un
défaut de l'instrument**, pas du candidat. Le motif retenu est plus étroit et plus honnête : un artefact dont
**aucun** candidat n'a de porte de régime correctement amorcée ne permet **aucune lecture**, pas même
descriptive, et le dire au refus d'entrée est plus clair que de produire un classement vide. Les autres clauses,
elles, laissent une lecture possible du reste, et l'abstention la publie.

Cette convention rend le cas du § D.3 mécanique : l'amorçage du préfixe y échoue sur les deux paires, donc sur
la totalité, donc l'artefact est refusé sous `D_WARMUP_PREFIX`.

**`D_WARMUP_ANCHOR` est de niveau run** (ligne 12), et pas de diagnostic : il concerne l'**unique** exécution
évaluée, donc il n'a pas de candidat à retirer. Le classer en diagnostic, comme le faisait la version
précédente, produisait une issue dont la raison était interdite dans la chaîne — un état inatteignable par
construction.

**Non-recevabilité et abstention ne sont pas la même chose.** L'abstention est un **résultat** du protocole sur
des données recevables : code 0, publiée. La non-recevabilité est un **refus d'entrée** : code 2, rien n'est
publié au-delà de la validation. Les confondre laisserait tourner la sélection sur un artefact que le protocole
vient de déclarer inapte.

### I.2 Les trois étapes

**I-A. Validité d'entrée** — forme de l'artefact, contrats de version (D5), bornes finissant exactement à
l'ancrage, présence et forme des blocs d'amorçage **et de couverture**, provenance de l'univers, unicité des
identités canoniques. Les assertions sont exécutées **dans un ordre gelé** et tout ce qui suit le premier échec
est marqué **sauté, jamais vert**. Codes : § I.1.

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
   critère inter-familles. L'origine des quantités de risque décisionnelles, recalculées sur `equity_daily`,
   est au § A.9.
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
9. **Le nombre de fins non plates.** L'identité de fin à plat étant nécessaire mais non suffisante (§ B.2), son
   compte de ruptures est une **borne inférieure**. → Il est rapporté comme tel, jamais comme un dénombrement.
10. **L'état du portefeuille à l'instant `T` lui-même.** Aucun point d'equity n'est écrit avant qu'une bougie
    n'ait été traitée **[v]** `scripts/backtest.py:1959-1960`, `:2333-2334` ; et à l'ancrage déclaré, **aucune
    bougie n'est estampillée à `T`** (§ A.4), donc **aucun point n'existe à `T`**. → Le départ à plat est
    déclaré **non vérifiable** (§ B.2) ; **aucune preuve de substitution n'est proposée**, et C3b doit
    **spécifier** une preuve, pas déplacer des colonnes.

---

## § K. Portée d'une clôture, et découverte annexe

### K.1 Ce qu'un `réfuté` clôt, et ce qu'il ne clôt pas

**C'est la section d'origine de la portée d'un `réfuté` et d'une clôture (§ 0.7).**

**Ce que `réfuté` établit** est défini au § H : la **configuration retenue**, sous **ce manifeste**, sur **cette
fenêtre d'évaluation**, échoue aux portes déclarées. Rien de plus.

**Le cas clos est donc le triplet** `(configuration retenue, empreinte du manifeste, fenêtre d'évaluation)`, et
il est nommé ainsi dans le rapport. Concrètement : cette configuration-là n'est pas reprise sous ce manifeste et
sur cette fenêtre, et **l'interdiction de repêcher du § A.11 reste entière** — aucun candidat de
substitution n'est sélectionné, aucune clause n'est relâchée, aucune borne n'est déplacée.

> **Ce que la version précédente déduisait à tort.** Elle écrivait que `réfuté` closait **le cas**, puis
> renvoyait au § 5 de `docs/CONTRAINTES_POST_B4.md`, qui parle de **familles**. **L'échec d'une configuration ne
> démontre pas celui de sa famille** : une famille contient d'autres configurations, que ce run n'a pas
> évaluées, et l'évaluation post-ancrage n'en a vu qu'une par construction (§ H). Le précédent avait déjà borné
> exactement cela pour sa propre issue négative ; l'extension était une inférence, pas une règle.

**Une clôture plus large est possible, mais elle change de nature.** Décider d'arrêter une famille entière est
une **décision de gestion de la recherche** — budget, priorités, cap de deux familles par cycle. Elle peut être
prise, et elle passe alors par le § 5 et le ticket § 6 de `docs/CONTRAINTES_POST_B4.md`. **Elle est annoncée
comme telle, avec son auteur et son motif, et n'est jamais déduite d'un verdict de ce protocole.** Un rapport
qui écrirait « la famille est close parce que le protocole a rendu `réfuté` » commettrait l'inférence que ce
paragraphe interdit.

### K.2 Découverte annexe

Une découverte faite en chemin est **signalée, jamais traitée**. Deux sont déjà consignées par ce document :
la liquidation terminale absente du moteur signal (§ B.3), portée en dette du projet et prérequis C3b ; et
l'impossibilité de vérifier le départ à plat sous les artefacts actuels (§ B.2), qui demande à C3b une **preuve
spécifiée** et non un transport de champs.

---

## § L. Artefacts, ordre d'exécution, diff de contrôle

### L.1 Ordre d'exécution

Aucun pas n'est sauté ni réordonné.

| # | Producteur | Artefact |
|---|---|---|
| 0 | **hors chaîne** | le **manifeste** (§ A.6), les **observations**, et l'**artefact de couverture** (§ A.7) — trois entrées, produites avant, jamais par l'outillage de ce protocole |
| 1 | `c3_anchor` | ancrage recalculé, estampilles admissibles, enregistrement au registre de variantes |
| 2 | `c3_entry` | validité d'entrée (§ I-A) → `results/c3a_entry_validation/` — poursuite selon la table du § I.1 |
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
base de données**, et `--now` injectable pour une sortie reproductible octet à octet. **Les codes de sortie sont
ceux de la table du § I.1, et de nulle part ailleurs** (§ 0.7).

### L.5 La porte pré-merge, et ce que le tunnel ne dispense pas

Les **24 tests de déterminisme full-range** (`tests/test_scripts/test_run_p6_determinism.py`, variantes `_full`)
ne s'exécutent pas via le tunnel local : ils s'y bloquent sur l'entrée-sortie, ce que le rapport C2 a déjà
constaté et résolu en les exécutant **sur le serveur**. Le reste de la suite passe en trois minutes en local,
et les six tests de déterminisme courts en trois minutes et demie.

**Le blocage du tunnel n'est pas une dispense permanente.** À la porte pré-merge de C3a, **l'une des deux
conditions suivantes est remplie et écrite dans le rapport** :

1. les 24 tests **tournent sur le serveur**, au SHA livré, avec leurs rapports archivés — la recette de C2 ; ou
2. le **diff de contrôle est documenté vide sur tous les chemins que ces tests exercent** — `src/`,
   `scripts/backtest.py`, `scripts/run_p6_backtests.py`, `scripts/run_p7_grid_search.py`,
   `scripts/p7_grids.py`, `config/`, `pyproject.toml`, `poetry.lock` — auquel cas les rejeux du dernier SHA où
   ils ont tourné valent pour celui-ci, **et le rapport le dit explicitement, avec ce SHA**.

Pour un chantier qui n'ajoute que des fichiers d'audit et de tests, c'est la seconde condition qui s'applique ;
elle doit être **écrite**, pas sous-entendue.

---

## § M. Index des symboles normatifs

Produit par `rg` sur ce fichier, à la révision soumise. **Chaque symbole a exactement un site de définition.**
L'index sert à repérer une définition **absente** ou **multiple**, et **un symbole que rien n'applique**. Il est
régénéré à chaque révision et recollé ici.

> **Règle de lecture, et elle a déjà servi.** **Un symbole normatif dont la colonne « sites de référence » est
> vide est une porte que rien n'applique.** Ce n'est pas un détail de présentation, c'est un défaut : la
> révision précédente affichait `E1` et `E2` sans aucun site de référence, et cette colonne vide **était** la
> contradiction qui laissait le § F.8 conclure `réfuté` sur une configuration qu'`E1` écartait. J'ai lu cet
> index et écrit « aucune anomalie ». **La colonne vide est une anomalie.**

| Symbole | Site de définition | Sites de référence |
|---|---|---|
| `Q1` | § F.8 | § A.8, § F.5, § H.0, § H.1 |
| `Q2` | § F.8 | § A.8, § F.5, § H.0, § H.1 |
| `Q3` | § F.8 | § A.8, § F.5, § H.0, § H.1 |
| `P1` | § A.10 | § A.11, § G.1, § H.1, § I.1 |
| `P2` | § A.10 | § A.11, § H.1 |
| `P3` | § A.10 | § A.11, § G.1, § H.1, § I.1 |
| `D1` | § A.8 | § A.7, § A.10, § A.11, § C.5, § G.1, § H.1, § I.1, § J |
| `D2` | § A.8 | § 0.5, § B.5, § D.3, § H.1, § I.1 |
| `D3` | § A.8 | § D.3, § H.1, § I.1, § J |
| `D4` | § A.8 | § I.1 |
| `D5` | § A.8 | § A.6, § D.3, § H.1, § I.1, § I.2 |
| `D6` | § A.8 | § A.10, § A.11, § G.1, § H.1, § I.1 |
| `E1` | § A.13 | § F.8, § H.0 |
| `E2` | § A.13 | § A.8, § H.0 |
| `R0_INVALID_RUN` | § I.1 | § H.1 |
| `P_PROVENANCE` | § I.1 | § H.1 |
| `D_WARMUP_PREFIX` | § I.1 | § B.5, § D.3, § H.1 |
| `A_NO_ADMISSIBLE_CANDIDATE` | § I.1 | § A.11, § H.1 |
| `A_BELOW_FLOOR` | § I.1 | § A.11, § H.1 |
| `D_WARMUP_ANCHOR` | § I.1 | § B.5, § H.1 |
| `E_NO_BENCHMARK` | § I.1 | § C.5, § H.1 |
| `E_STAMP_MISMATCH` | § I.1 | § B.4, § H.1 |
| `F_NOT_ESTIMABLE` | § I.1 | § A.13, § F.2, § F.8, § H.0, § H.1 |
| `F_CANNOT_SEPARATE` | § I.1 | § F.5, § H.1 |
| `R1_NOT_NORMALISED` | § I.1 | § A.8, § H.1 |
| `D_NOT_ADMISSIBLE` | § I.1 | § H.1 |
| `C_COVERAGE` | § I.1 | § A.8, § H.1 |

**Seuils, et leur site unique.** Chaque valeur est définie une fois, avec sa classe (§ 0.5) :

| Seuil | Valeur | Site | Classe |
|---|---|---|---|
| Fraction d'ancrage `F` | 0,70 | § A.3 | préférence économique |
| Couverture minimale du préfixe | 97 % du dénominateur propre à chaque timeframe | § A.8 D1 | qualité des données |
| Trou maximal | min(31 j, 3 % des jours) | § A.8 D1 | qualité des données |
| Jour 5 min compté couvert | ≥ 144 bougies sur 288 | § A.8 D1 | qualité des données, convention |
| Cycles achevés au préfixe | ≥ 25 | § A.8 D3 | préférence économique |
| Plancher de rendement | 2,0 %/an | § A.10 P2 | préférence économique |
| Capital de référence `C` | 1000 USDC | § 0.5 | contrat |
| Taux sans risque | 0 | § 0.5 | préférence économique, convention |
| Résidu d'appariement de `λ` | ≤ 10 % de la cible | § 0.5 | qualité des données |
| Longueurs de bloc `L` | {10, 21, 42} | § F.2 (b) | qualité des données |
| Réplications `B` | 10 000 | § F.2 (b) | qualité des données |
| Niveau de la borne | 95 %, unilatéral | § F.2 (d) | préférence méthodologique déclarée |
| Pas de recherche de `λ` | 0,005 puis 0,001 | § F.2 (g) | qualité des données |
| Réplications écartées tolérées | ≤ 10 sur 10 000 | § F.2 (e) | qualité des données, convention |
| Jours à rendement non nul | ≥ 10 % de la fenêtre d'évaluation | § A.13 E1 | qualité des données, convention |
| Valeurs distinctes de `Δ*` | ≥ 2 | § A.13 E2 | garde-fou méthodologique |

### Ce que l'index ne prouve pas

Il compte des symboles ; **il ne lit pas des règles**. Il ne détecterait pas deux règles **incompatibles
formulées avec des symboles différents** — par exemple une condition d'estimabilité exigeant une activité que la
construction du comparateur rend impossible, ou une portée de refus contredisant une issue prévue ailleurs. Ces
deux cas se sont produits dans ce document et **aucun n'aurait été trouvé par cet index** : ils l'ont été en
relisant les conditions et leurs conséquences. **L'index est un filet, pas une preuve**, et **le nombre de
lignes de ce document n'est un critère d'acceptation de rien.**
