# § F.2 du protocole C3 v2.1 — pièce jointe du brief C3b

> **Source** : `docs/protocole_c3.md` **v2.1**, § F.2 = **lignes 1384–1541** du fichier.
> **sha256 du protocole v2.1** : `9300f4e53bfd36633df6524c2d7ad168a732739ca3dd1765c024cc8a3ccd4129` — `shasum -a 256 docs/protocole_c3.md` doit rendre cette valeur ; sinon cette
> copie n'est plus celle du texte gelé. Protocole gelé le 2026-09-23 au commit `818b925` (branche
> `feat/c3-amendements-v2.1`, mergée dans `dev` sous le tag `v2.12.0-c3-v2.1`) ; amendements, décisions de gate et
> réserves : `docs/amendements_c3_v2.1.md`, section « Adoption ».
> **C'est la spécification du producteur d'évaluation C3b.** Ce fichier est une copie de travail, non suivie par
> git : **en cas d'écart, le protocole fait foi** (§ 0.7).

Contenu : (1) le § F.2 v2.1 en entier, recopié octet pour octet depuis le protocole ; (2) le diff du § F.2 entre
v2.0 (`d931293`, identique à `f321ddd`) et v2.1.

---

## 1. Le § F.2 v2.1, en entier

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
impossibles (§ F.2 a) : le rejeu est **inexécutable**, erreur de forme (§ I.1, ligne 2), code 2. **Ce qui
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

---

## 2. Diff du § F.2, v2.0 → v2.1

````diff
--- docs/protocole_c3.md v2.0 (d931293, § F.2, lignes 1181–1262)
+++ docs/protocole_c3.md v2.1 (§ F.2, lignes 1384–1541)
@@ -15,10 +15,58 @@
 évaluation et entre dans l'empreinte (§ A.6). Classe de `L` et de `B` : qualité des données ; classe de la
 graine : contrat.
 
-**(c) La reconstruction et l'annualisation.** Pour chaque réplication, la trajectoire est reconstruite par
-**produit cumulé** depuis le capital `C` (§ 0.5), puis le rendement géométrique annualisé est
-`CAGR = (exp(Σ log1p(r) × 365 / n_jours) − 1) × 100`, en %/an. `n_jours` est la durée de la fenêtre
-d'évaluation, pas le nombre de rendements. `Δ* = CAGR(config) − CAGR(comparateur)` sur la **même** réplication.
+**Le tirage, écrit pour être rejoué.** L'**index de paire** est la position de la paire de la configuration
+évaluée dans la liste **triée** des paires de l'univers (celle que porte l'artefact d'ancrage). Pour chaque `L`,
+les départs de blocs sont tirés **en un seul appel**, `rng.integers(0, n, size=(B, ⌈n / L⌉))`, `n` étant le
+nombre de rendements quotidiens de la fenêtre d'évaluation ; les indices d'une réplication sont
+`(départ + k) mod n` pour `k = 0 … L − 1`, concaténés bloc après bloc et tronqués aux `n` premiers.
+**Les mêmes indices** servent à la configuration et au comparateur, et **aux deux appariements** d'un même
+`L` : seul le comparateur change entre `dd` et `σ`. Ce tirage, et le calcul du § F.2 (c), ne sont exacts que
+dans l'environnement qui les a produits, que l'artefact d'évaluation déclare (§ I.2 I-C) en **quatre champs,
+et quatre seulement** :
+
+```
+python    platform.python_version()
+numpy     numpy.__version__
+machine   platform.machine()
+libc      platform.libc_ver() : la bibliothèque et sa version, séparées par une espace, espaces de bord retirées
+```
+
+Jamais la version du noyau du système d'exploitation, qui ne change pas le calcul. Sur macOS,
+`platform.libc_ver()` est vide, et `libc` aussi : ce que ce champ ne distingue pas est déclaré au § J, item 12.
+
+**Les valeurs de `L`, `B` et le niveau de la borne sont des contrats d'instrument au sens de D5, comme
+l'environnement du tirage et les deux appariements du comparateur** : un artefact d'évaluation qui déclare
+`B ≠ 10 000`, une longueur de bloc hors `{10, 21, 42}`, une combinaison manquante ou surnuméraire, un comparateur
+qui ne porte pas **exactement** les deux appariements `dd` et `σ`, ou un environnement qui n'est pas
+**exactement** celui où la chaîne rejoue — un champ en trop compris — est un **contrat rompu** :
+`R0_INVALID_RUN`, code 2, rien n'est publié (§ I.1, ligne 2). Ce contrôle est fait **avant toute lecture**,
+séries comprises : un `B` hors contrat accompagné d'un compteur contradictoire ou d'un non-fini dans une suite
+rééchantillonnée sort en refus de contrat, jamais en violation par accident d'ordre de lecture. Précédent :
+`rejeu_validate_analysis.b02_frozen_parameters`.
+
+**(c) Le rendement géométrique et l'annualisation.** Pour chaque réplication, le rendement géométrique
+annualisé est calculé **par somme des `log1p`** ; aucune trajectoire n'est reconstruite pas à pas depuis le
+capital `C` (§ 0.5) :
+
+```
+CAGR = (exp((Σ log1p(r) × 365) / n_jours) − 1) × 100          en %/an
+     = (numpy.exp((numpy.log1p(r)[indices].sum(axis=1) * 365) / n_jours) - 1) * 100
+```
+
+`r` est le vecteur des rendements quotidiens, `indices` la matrice `(B, n)` des indices des réplications
+(§ F.2 b). `n_jours` est la durée de la fenêtre d'évaluation, pas le nombre de rendements : `(fin − T)` en
+secondes, divisé par 86 400, en double précision. **L'ordre des opérations fait partie de la définition** : la
+somme est multipliée par 365, **puis** divisée par `n_jours` — une seule division, faite en dernier.
+`somme × (365 / n_jours)` donne un autre nombre au dernier bit sur une part des réplications — environ une sur
+vingt pour la série témoin des tests, mesuré le 2026-09-23 —, et le rejeu est une égalité au bit (§ F.2 d).
+`Δ* = CAGR(config) − CAGR(comparateur)` sur la **même** réplication.
+
+**Un seul chemin de calcul.** Ce chemin est **le seul** : appliqué aux indices identité `[[0 … n − 1]]`, il
+donne le `CAGR` observé de la configuration (porte `Q2`, § F.8) et celui de chaque comparateur, donc `Δ̂` par
+appariement — `Δ̂` en drawdown est la valeur de la porte `Q3` et le centre des trois bornes `dd` ; `Δ̂` en
+écart-type, le centre des trois bornes `σ`. Une seule fonction, une seule convention : aucune divergence
+d'arrondi entre l'estimation et ses réplications.
 
 **(d) La borne, sa formule, son niveau, sa convention de quantile.** Borne inférieure **unilatérale à 95 %**,
 de forme **pivotale (« basic »)**, recentrée sur l'estimation :
@@ -35,6 +83,22 @@
 qu'employait le précédent (`LB_j = Δ̂_j − q`). **Le choix est déclaré ici parce qu'il est décisionnel**, pas
 parce qu'il est neutre. Classe : préférence méthodologique déclarée.
 
+**Qui calcule, et ce que la chaîne rejoue.** La procédure est **exécutée par le producteur d'évaluation**
+(C3b), qui exporte les séries quotidiennes de la configuration et du comparateur de chaque appariement —
+**toutes de même longueur `n`** —, et, par combinaison, la suite `Δ*` retenue **dans l'ordre des réplications
+`b = 1 … B`, écartées retirées**, le compte de réplications écartées et la borne. Toute valeur est publiée en
+double précision, **sérialisée par le `repr` le plus court qui se relit à l'identique** — la convention de
+`canon` (§ A.1 bis) —, jamais « avec assez de décimales ». La chaîne (§ L.1) **rejoue le tirage** — graine
+du manifeste, index de paire, `n_jours`, tirage et chemin de calcul des § F.2 (b) et (c) — et **recalcule**
+les six suites, les comptes d'écartées, `Δ̂` par appariement, le `CAGR` de la configuration et les six bornes.
+**Toute différence avec ce que l'artefact déclare est une violation** (§ I.1, ligne 15) — la comparaison est une
+égalité au bit, ordre des suites compris —, et les portes `Q2`, `Q3` et les bornes décident sur les valeurs
+**rejouées**. Le rejeu n'est exécuté que dans l'environnement que l'artefact déclare : sinon, contrat rompu
+(§ F.2 b), jamais une comparaison tolérante. Des séries de longueurs différentes rendent les indices appariés
+impossibles (§ F.2 a) : le rejeu est **inexécutable**, erreur de forme (§ I.1, ligne 2), code 2. **Ce qui
+reste déclaratif** : les séries quotidiennes elles-mêmes et `net_pnl` (porte `Q1`), qu'aucune série de
+l'artefact ne permet de recalculer (§ J, item 12).
+
 **(e) Entrées invalides et échecs numériques — deux choses distinctes, une seule règle.**
 
 **C'est la section d'origine du traitement des non-finitudes pendant le bootstrap (§ 0.7) ; le § F.7 traite les
@@ -42,20 +106,32 @@
 
 | | Ce que c'est | Quand | Traitement |
 |---|---|---|---|
-| **Entrée invalide** | un `NaN`, un infini, un `λ` non fini ou un rendement `≤ −1` **dans les données fournies** à la procédure | **avant** tout tirage | **erreur d'entrée** : § I.1, ligne 15. Aucun bootstrap n'est lancé |
-| **Échec numérique** | une **réplication** produit un `Δ*` non fini, ou un rendement rééchantillonné conduit la trajectoire à zéro | **pendant** le tirage | la réplication est **écartée et comptée** |
+| **Entrée invalide** | un `NaN`, un infini, un `λ` non fini ou un rendement `≤ −1` **dans les données fournies** à la procédure, ou une série dont le `CAGR` **observé** — chemin du § F.2 (c), indices identité — n'est pas fini : l'estimation elle-même n'existe pas, il n'y a rien à écarter | **avant** tout tirage | **erreur d'entrée** : § I.1, ligne 15. Aucun bootstrap n'est lancé |
+| **Échec numérique** | une **réplication** produit un `Δ*` non fini : l'exponentielle du § F.2 (c) déborde vers l'infini (d'un côté, `Δ*` est infini ; des deux, `∞ − ∞` n'est pas défini) | **pendant** le tirage | la réplication est **écartée et comptée** |
+
+**Rien d'autre n'est écarté.** Un rendement `≤ −1` étant une entrée invalide (ligne du dessus), `log1p` est
+défini partout et la somme du § F.2 (c) ne « va à zéro » nulle part. v2.0 écartait aussi la réplication dont
+« un rendement rééchantillonné conduit la trajectoire à zéro » : la phrase décrivait un produit cumulé, qui
+n'est pas le calcul du (c). Un `CAGR` de **−100 %/an exactement** — l'exponentielle sous-déborde vers 0 — est
+une valeur **finie et légitime**, celle du pire chemin : la réplication est **retenue**. L'écarter biaiserait
+la distribution vers les chemins qui finissent bien, ce que le paragraphe suivant interdit déjà pour le
+retirage.
 
 **Comment le quantile est calculé quand des réplications sont écartées.** Elles sont **exclues, comptées, et
 non remplacées** : pas de retirage, qui biaiserait la distribution vers les chemins qui se terminent bien. Le
-quantile du § F.2 (d) est calculé sur les **réplications retenues**, et l'artefact publie **`B_effectif`**, le
-nombre effectivement utilisé, à côté de `B`. Un rapport qui cite une borne sans citer `B_effectif` est
-incomplet.
+quantile du § F.2 (d) est calculé sur les **réplications retenues**, et l'artefact publie, **par
+combinaison** `L × appariement`, **`B_effectif`**, le nombre effectivement utilisé, à côté de `B`. Un rapport
+qui cite une borne sans le `B_effectif` de sa combinaison est incomplet. Une combinaison dont aucune
+réplication n'est retenue ne porte pas de borne : la borne déclarée est nulle **si et seulement si** sa suite
+retenue est vide, et l'écart, dans un sens ou dans l'autre, contredit l'artefact (§ I.1, ligne 15).
 
 **Le plafond, et ce qu'il vaut.** Au-delà de **10 réplications écartées sur 10 000** — soit un `B_effectif`
-inférieur à 9 990 — l'inférence est déclarée **inutilisable** : issue `inconclusif (F_NOT_ESTIMABLE)`, et
-**aucune borne n'est publiée**. Classe : qualité des données, **convention déclarée**. Le nombre est repris du
-précédent et **n'est pas dérivé** : il exprime qu'une poignée de chemins dégénérés est tolérable, et qu'au-delà
-la distribution n'est plus celle qu'on croit échantillonner.
+inférieur à 9 990 — **sur l'une quelconque des six combinaisons** `L × appariement`, l'inférence est déclarée
+**inutilisable** : issue `inconclusif (F_NOT_ESTIMABLE)`, et **aucune borne n'est citée par le verdict**.
+L'artefact d'évaluation, lui, porte la borne de toute combinaison dont la suite retenue n'est pas vide
+(ci-dessus), et la chaîne la recoupe au rejeu comme les autres. Classe : qualité des données, **convention
+déclarée**. Le nombre est repris du précédent et **n'est pas dérivé** : il exprime qu'une poignée de chemins
+dégénérés est tolérable, et qu'au-delà la distribution n'est plus celle qu'on croit échantillonner.
 
 **(f) `λ` reste celui du préfixe pendant toute la procédure décisionnelle.** Le **mode** de `λ` est tranché au
 **§ C.4, section d'origine** ; ce paragraphe n'en énonce que la conséquence procédurale : `λ` est estimé une
````
