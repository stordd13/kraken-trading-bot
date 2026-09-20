# Rejeu diagnostic grid — pré-spécification gelée

> **Statut : GELÉE.** Rédigée et committée le 2026-09-20, **avant toute simulation**, sur la branche
> `feat/rejeu-grid-diag` créée depuis le tag `v2.10.0-c2-replay` (sha épinglé
> **`9897803f48a6537a248f5a41c53a1ea5522d46a0`**). Plan validé au gate 1 (deux gates, brief
> `agent/rejeu_diagnostic_grid_v2.md`).
>
> **Rien dans les § A–L ne peut être relu, repondéré, réinterprété ou élargi une fois qu'une sortie de simulation
> existe.** Un seuil qui se révèle mal choisi est consigné comme tel dans le rapport de gate 2 ; le verdict reste
> celui que la règle gelée produit. Un périmètre qui se révèle mal choisi est un **résultat**, pas une invitation à
> l'ajuster.
>
> Les faits marqués **[v]** ont été lus dans le code ou dans `results/c2_replay/P6_grid_rerun.json` /
> `results/B4_P7_phase1_cross_validate.json` pendant la rédaction.

---

## § 0. Périmètre gelé, commande de record, garde-fous d'exécution

### 0.1 La question

Une seule : **la famille grid, dans ce périmètre gelé, mérite-t-elle un travail supplémentaire (`candidat`),
est-elle `dépriorisée`, ou le rejeu est-il `inconclusif` ?** Le rejeu **ne sélectionne rien** : toute sélection
relève du protocole C3, qui n'existe pas. `candidat` ne signifie jamais « déployable ».

Contexte de portée, à rappeler dans le rapport : C1 a réparé la mesure (`metrics_version` 2), C2 ce qui est simulé
(`replay_version` 2). Sur la fenêtre gold le grid passe de **45 à 2 trades**, l'espacement tape le **plafond 5 %**
au lieu du plancher 1,5 %, et le régime hebdomadaire n'était pas amorcé sur les 19-21 premières clôtures de
`train`/`all` **[v]**. **Le grid que ce rejeu exécute n'est pas celui qui a produit le 0/48 de B4.** Les classements
B4 ne sont ni un point de comparaison ni une attente.

### 0.2 La commande unique

```
poetry run python scripts/run_p7_grid_search.py --phase 1 --fees bybit \
  --strategy grok_grid_atr_adaptive_v4 \
  --pair-costs-file config/pair_costs_b4.json --min-order-usdc 5 \
  --workers 3 --timeout 10800 \
  --output results/rejeu_grid_20260919/P7_phase1_grid.json
```

`--strategy grok_grid_atr_adaptive_v4` seul donne `GRID_ATR_PAIRS = (BTC/USDC, SOL/USDC)` ×
`expand_grid(GRID_ATR_GRID)` = **96 jobs** **[v]**. Interdits sans exception : `--pair`, `--phase 2`,
`--phase report`, `--report`, `--selection`, `--benchmarks`, `--limit`, `--force`, `--serial`.

`run_p7_grid_search.py` n'a **ni `--exchange` ni `--start`/`--end`** : `EXCHANGE = "binance"`,
`P7_START = 2023-04-01`, `P7_END = 2026-04-01`, `CANDLE_INTERVAL = 5`, `CAPITAL = 1000.0`, `TRAIN_RATIO = 0.7` sont
des constantes de module **[v]**. Le périmètre de données et la période sont donc fixés **par le code**, pas par un
drapeau.

`--workers 3` : précédent B4.3 explicitement justifié (~1 Go par worker, **le collector garde son vCPU**). Le
déterminisme 24/24 de C2 prouve la reproductibilité run-à-run, **pas** l'invariance au nombre de workers : le nombre
est gelé à une valeur, pas déclaré sans importance.

### 0.3 Le `--timeout` ne protège de rien, une limite murale externe le remplace

Vérifié dans le code : sur `mp.TimeoutError` le runner écrit une entrée portant `"error"` mais **ne tue pas le
worker**, et `pool.join()` l'attend quand même **[v]**. `--timeout 10800` est donc gardé **haut, uniquement pour ne
pas marquer en erreur un job légitimement lent**.

**Limite murale externe, déclarée avant le run : 6 h** pour les 96 jobs (contre ≈ 2 h estimées à partir des mesures
serveur post-C2 : ~119 s/job BTC, ~94 s/job SOL, 3 segments chacun **[v]**), surveillée depuis tmux. Dépassement ⇒
**arrêt manuel et verdict `R0_INVALID_RUN`**, sans relance « pour voir ».

### 0.4 Règle de reprise

Une relance n'est autorisée que pour une **erreur technique identifiée comme transitoire**. **L'erreur est classée
avant toute relance** : `error` et `traceback` de chaque entrée fautive sont lus, consignés et archivés sous
`results/rejeu_grid_20260919/attempts/`. Une **exception d'invariant comptable** (`RuntimeError` de replay,
divergence d'inventaire) n'est **jamais** transitoire : elle donne `R0_INVALID_RUN` immédiatement et ne doit pas
disparaître derrière une relance réussie. Au maximum **deux passes** de reprise pour des erreurs transitoires
classées ; au-delà, `R0_INVALID_RUN`. La reprise est la reprise par défaut du runner (`filter_pending_jobs` re-file
toute clé portant `"error"` sans `--force` **[v]**) ; `--force` reste interdit.

### 0.5 Interdits d'office

Élargir la grille, ajouter une paire, changer la période, toucher `max_spacing_pct`, fixer la dette 13, modifier
moteurs / stratégies / runners / configs / dépendances, relancer avec un périmètre modifié après avoir vu les
résultats.

**Autorisé** : scripts de post-traitement sous `scripts/audit/` et leurs tests (liste close, § I-A.14), qui ne
modifient aucune simulation.

### 0.6 Défauts de classe en vigueur (dette 13 non fixée) — liste complète

`grid_levels 12`, `max_spacing_pct 0.05` (**non balayé**), `atr_period 14`, `recalc_hours 6` (cadence effective
8 h), `bias_1d 0.2`, `order_size_usdc 25`, `max_allocation_pct 20.0` (**jamais lu par le moteur de backtest**
**[v]**), capital 1000 USDC, `candle_interval 5` **[v]**.

**Exposition maximale — énoncé correct.** Lots de **25 USDC**, `max_allocation_pct` **non appliqué**, achats limités
par le **cash disponible** ; les lots ouverts **survivent aux reconstructions de grille** et de nouveaux achats
peuvent être créés. **L'exposition maximale n'est pas démontrée** : aucun plafond de type « 12 × 25 = 300 USDC »
n'est écrit dans ce document, et aucun raisonnement ne s'appuie sur un tel plafond.

### 0.7 La grille balayée

`GRID_ATR_GRID` **[v]** : `min_spacing_pct` ∈ [0.015, 0.020, 0.025, 0.030] × `atr_multiplier` ∈ [1.5, 2.0, 2.5, 3.0]
× `bear_protection_mode` ∈ ["none", "1w_only", "1d_only"] = 48 par paire, **96 configs**.

---

## § 1. Segments

`all` = 2023-04-01T00:00:00+00:00 → 2026-04-01T00:00:00+00:00, 1096 jours :
`equity_daily.all.values` = **1097 points → 1096 rendements** (`n_daily_returns` 1096) **[v]**.
`train` = **769 points → 768 rendements** ; `test` = **330 points → 329 rendements** **[v]**, séparés au split
recalculé `P7_START + (P7_END − P7_START) × 0.7` = 2025-05-07T04:48:00+00:00 **[v]**.

**`all` est le seul segment qu'un seuil lit.** `train` et `test` servent aux assertions de validité et à une note de
stabilité descriptive. Ils ne sont **jamais** concaténés (ils partagent l'instant de split et chacun paie sa
liquidation terminale que `all` ne paie pas — témoin numérique : 768 + 329 = 1097 ≠ 1096 rendements), **jamais**
comptés comme preuves indépendantes de `all`, **jamais** une borne d'incertitude. 96 configs × 3 segments = **288
simulations, qui ne sont pas 288 observations** : la famille d'hypothèses est de 48 par paire, sur `all`.

---

## § A. Classes d'indiscernabilité — descriptif, n'entre dans aucune branche de verdict

### A.1 Canonicalisation

Le bloc `liquidation` est exporté en **Decimal sérialisés en chaînes** **[v]** (`scripts/backtest.py`, `_dec(v) =
str(v)`) : le fichier contient réellement `"residual_net_proceeds": "0"`, `"inventory_divergence_btc": "0E-30"`,
`"dust_written_off_btc": "-6E-31"` **[v]**. Arrondir « tous les floats » n'appliquerait donc aucune tolérance là où
le bruit de poussière vit, et `Decimal("0")` contre `Decimal("0E-30")` scinderait deux runs identiques.

```
canon(x) :  float                     -> repr(float(x))                          # aller-retour le plus court
            int / bool                -> repr(x)                                 # 0, 0.0 et "0" ne collisionnent jamais
            None                      -> "null"
            str parsable en Decimal   -> format(Decimal(x).normalize(), "f")     # "0E-30" -> "0"
            autre str                 -> la chaîne verbatim

sig = sha256(json.dumps(obj, sort_keys=True, separators=(",", ":"),
                        ensure_ascii=False, allow_nan=False).encode("utf-8")).hexdigest()
```

`allow_nan=False` : tout NaN/Inf lève → échec de validité (§ I-A.9), jamais une scission de classe silencieuse.

Deux tiers, tous deux rapportés, **l'exact étant le nombre de record** :
- `sig_exact` — comme ci-dessus ;
- `sig_tol` — floats via `float(f"{x:.9e}")`, Decimal quantifiés à `1e-12`.

### A.2 Champs de la signature

**Inclus** : les trois dicts de métriques `train` / `test` / `all` ; `equity_daily[seg].values` **complet** ;
`liquidation[seg]` **hors** `timestamp` et `reference_price` ; `rejections[seg].by_cause`.
**Exclus** (et pourquoi) : `params` et `effective_params` (ce sont les étiquettes de la config, pas sa sortie),
`period` (identique par construction), `warmup` (identique par paire, cf. § I-A.8).

### A.3 Rendu

« 96 configs → N classes », **par paire**, sur `sig_exact` et sur `sig_tol`, avec pour chaque classe la liste des
configs membres et, entre deux classes voisines, la **première différence** (chemin JSON) produite par
`first_difference` (`scripts/audit/b4_2_reference_capture.py` **[v]**).

**Lecture rétroactive B4** : sur `results/B4_P7_phase1_cross_validate.json` — le fichier **B4**, pas
`results/P7_phase1_cross_validate.json` qui est la campagne pré-B4 sans `fees` ni `liquidation` **[v]** — limitée
aux champs que ce fichier a conservés (`strategy`, `pair`, `params`, `liquidation`, `train`, `test`, `all`).
Référence pré-enregistrée, segment `all` : **BTC 48 → 45 classes, SOL 48 → 48** **[v]**.

### A.4 Légende obligatoire, verbatim

> « L'égalité de signature est une **indiscernabilité sur les sorties exportées**. Le journal des transactions n'est
> pas exporté : ce n'est jamais une preuve d'identité des ordres, ni une preuve que le clamp a saturé. »

---

## § B. Mesure directe du clamp — hors simulation, ne déplace aucun verdict

### B.1 Procédure

Depuis la DB (`exchange='binance'`, `interval=240`, les deux paires, `2023-02-01 < ts <= 2026-04-01` dont une
amorce exclue des comptes), `ATRIndicator(14)` **importé** (`krakenbot.indicators.atr` — Wilder amorcé par moyenne
simple des 14 premiers TR **[v]**), recalcul pour chacun des 16 couples (plancher, multiplicateur) de

```
spacing_t = max(plancher, min(0.05, ATR(14,4h)_t × multiplicateur / close_t))
```

### B.2 Rendu

Fraction des clôtures 4 h **au plancher** / **strictement à l'intérieur** / **au plafond**, par paire, sur la fenêtre
entière puis par **trimestre calendaire** (12 trimestres 2023Q2 → 2026Q1). Bornes de liaison, écrites d'avance : le
plafond mord ssi `ATR/close ≥ 0.05 / m`, soit **3,33 % / 2,50 % / 2,00 % / 1,67 %** pour m = 1,5 / 2,0 / 2,5 / 3,0 ;
le plancher mord ssi `ATR/close ≤ plancher / m` (16 cellules, 0,50 % … 2,00 %).

Mesure annexe SOL, descriptive : fraction des clôtures où le pas de quantification des niveaux
(`Decimal("0.1")` USD **[v]**) représente au moins 10 % de `spacing_t × close_t`.

### B.3 Étiquette obligatoire

Cette mesure est **distributionnelle, ce n'est pas un rejeu**. L'amorçage diffère de celui du moteur — sur SOL
`warmup.all["4h"].loaded == 0` **[v]** — et **aucune des deux paires ne reproduit l'état ATR réalisé du moteur**.
Si la mesure ne peut pas être produite, l'hypothèse « axe ATR mort sous l'instrument v1, plafond saturé sous
l'instrument réparé » est **étiquetée explicitement comme non mesurée** dans le rapport, et rien d'autre ne change :
**le clamp ne déplace aucun verdict, dans aucune direction.**

---

## § C. Couverture — 25 cycles grid achevés

### C.1 La quantité comptée

```
cycles = all.total_trades − liquidation.all.positions
```

Exact par construction : `total_trades = pairs_completed + liquidated_positions` **[v]**
(`scripts/backtest.py:3326`), identité épinglée par les tests de GATE A **[v]**. Référence post-C2 BTC :
`57 − 4 = 53` cycles sur trois ans **[v]**.

### C.2 Seuil : `cycles ≥ 25`, par config, sur `all`

Le § 8 de `docs/CONTRAINTES_POST_B4.md` nomme la bande du projet — « ~25-30 round-trips sur l'ensemble de la
période » — et dit dans la même phrase que la franchir **ne valide rien** : c'est un filtre de couverture, pas un
seuil statistique. Le bas de la bande est retenu, pour une raison propre à ce balayage :

> Le filtre est **corrélé à un axe balayé**. `spacing = clamp(ATR·m/close, plancher, 0.05)` : à faible `ATR/close`
> une config à plancher 3,0 % est **plus large** que la référence (0.015, 4.0) et produit **moins** de cycles ; à
> `ATR/close` élevé elle est plus serrée. L'affirmation « les configs balayées tradent au moins autant que la
> référence à 53 cycles » est donc **fausse comme énoncé général** et n'est pas faite. Un seuil plus haut tronque le
> plan d'expérience **de façon non aléatoire**, le long du paramètre testé. C'est un argument sur la **structure de
> l'expérience**, pas sur ses résultats.

**Limite, inscrite avec le seuil** : 25 cycles est un **filtre d'admissibilité minimal, pas une taille
d'échantillon**. Les cycles d'une grille à l'intérieur d'une même tendance sont **fortement corrélés** — ce ne sont
pas 25 observations indépendantes. Si la méthode d'incertitude exige davantage d'information, l'insuffisance donne
**`inconclusif` même au-dessus de 25**. La sévérité vit dans les gates économiques (§ F), pas dans le filtre.

**Conséquences gelées** : `cycles` est imprimé en table **4 × 4 × 3** pour rendre la troncature visible, et le
paragraphe de verdict dit combien de configs chaque cellule (plancher, multiplicateur) a perdues au filtre.
**Falsification acceptée par écrit** : si des configs à 20-24 cycles montrent une économie qui serait autrement
passée, le rapport consigne que le seuil a mordu et les a exclues ; **le nombre ne bouge pas.**

### C.3 Liquidations

`liquidation.all.{positions, trades, pnl, fees, buy_fees, sell_fees, gross_usdc, avg_holding_minutes}` en **colonne
séparée** par config, **jamais** repliées dans `cycles`, et **entièrement conservées dans l'économique** : `net_pnl`
est le cash réalisé après la vente MARKET terminale **[v]**, et cette vente est dans le chemin de NAV, donc dans
chaque rendement et chaque drawdown. **Aucun chiffre du rapport n'est restitué « hors liquidation ».**

### C.4 La voie « ~3 ans d'equity à exposition non triviale » est ÉCARTÉE

Deux raisons d'artefact, écrites avant tout résultat :
1. **Aucune exposition n'est exportée.** L'entrée ne porte que la NAV ; pas de cash, pas d'inventaire, pas de
   notionnel. Retrouver `q_t` depuis `NAV_t = cash_t + q_t·P_t` exige les jours qui ont porté un trade, donc le
   journal des transactions, qui n'existe pas. Rejeté comme estimation dérivée ; non calculé.
2. **La NAV est forward-fillée à travers les trous, sans marqueur.** `n_daily_returns` compte les rendements
   *définis* et vaut **1096 sur SOL malgré le trou de 455 jours** **[v]** : 1097 points ne prouvent pas 1096 jours
   d'exposition.

**Conséquence : seul le repère en cycles admet.** Une config sous 25 cycles ne peut pas être rattrapée par « mais
elle a porté pendant trois ans ». Deux indicateurs sont rapportés et **ne décident rien** :
`nnz = #{t : |r_t| > 1e-12}` et `β̂ = Σ s_t·b_t / Σ b_t²` (pente OLS sans constante des rendements de la config sur
ceux du benchmark plein notionnel). `nnz` est décrit pour ce qu'il est — **des jours où la NAV a bougé**, pas des
jours d'exposition : un jour à plat en cash et un jour de trou forward-fillé donnent tous deux 0.0, mais un jour
portant de l'inventaire à mark inchangé aussi, et un jour à plat en cash où une vente appariée se règle, non.

---

## § D. Admissibilité par paire — tranchée avant le run

### D.1 Mesure (`data_coverage.json`, produit et committé AVANT la campagne)

Par paire, sur les 1096 jours UTC de `[2023-04-01, 2026-04-01)`, `exchange='binance'`, convention end-stamped (une
bougie stampée `t` couvre `(t − intervalle, t]`) :

- `days_5m` — jours portant ≥ 1 bougie `interval=5` stampée dans `(J 00:00, J+1 00:00]` ;
- `days_5m_complete` — jours portant ≥ **144** des 288 bougies 5 m attendues ;
- `max_gap_days` — plus longue suite contiguë de jours sans aucune bougie 5 m ;
- `days_4h`, `first_covered_day`, `last_covered_day`, comptes par intervalle (5 / 240 / 1440 / 10080), complétude
  quotidienne médiane, nombre de jours sous 90 % et sous 50 % de complétude, et la **liste explicite des stamps 1 w
  manquants dans la fenêtre** (attendus : 2025-01-27 et 2025-02-24, **sur les deux paires** **[v]**).

### D.2 Règle (gelée, les cinq clauses)

```
admissible(paire) ⇔ days_5m           >= 1065        # = 1096 − 31
                 ET days_5m_complete  >= 1065
                 ET days_4h           >= 1065
                 ET max_gap_days      <= 31
                 ET first_covered_day <= 2023-04-02   ET   last_covered_day >= 2026-03-31
```

`1065 = 1096 − 31` : le § 7 pose « 3+ ans de backtest » comme non négociable et la fenêtre fait exactement trois
ans, donc la lecture stricte est 1096 ; une tolérance d'un mois cumulé garde l'énoncé « trois ans » vrai à 2,8 % et
absorbe les maintenances d'exchange. Elle est argumentée comme **tolérance de qualité de données**, jamais comme
« trois ans moins un mois ». `max_gap_days ≤ 31` empêche de dépenser cette tolérance en un seul trou structurel.
`days_5m_complete` existe parce que « ≥ 1 bougie dans la journée » n'est pas un test de qualité : une paire à 1
bougie sur 288 par jour scorerait 1096/1096 — c'est la clause de complétude qui fait de l'admissibilité de BTC une
**preuve** et non une hypothèse.

### D.3 Attendu pré-enregistré et conséquence gelée

**BTC/USDC** : 1096 jours couverts, trou 0, première journée 2023-04-01 → **admissible**.
**SOL/USDC** : le trou de 455 jours (2022-09-29 → 2023-12-28) tombe **à l'intérieur** de la fenêtre ; première
bougie 5 m en fenêtre le 2023-12-28 08:05 UTC **[v]** → ≈ 825 jours (75,2 %, 27,1 mois), trou ≈ 271 jours, première
journée couverte avec neuf mois de retard → **inadmissible sur quatre clauses sur cinq**.

**Gelé : aucun résultat SOL ne peut produire un verdict `candidat` — ni un verdict `dépriorisation`.**

> Argument décisif : si SOL pouvait fonder une dépriorisation sans pouvoir fonder un candidat, des données déclarées
> inadmissibles pourraient **tuer une famille sans pouvoir la soutenir** — un cliquet à sens unique. Et la « seconde
> mise à mort » du § 5 (retour seulement avec un mécanisme nouveau) est trop lourde pour reposer sur une paire que
> la règle vient de déclarer non testable.

C'est une **extension du texte littéral du brief** (qui n'interdit que `candidat`), signalée comme telle dans le
rapport.

**SOL reste pleinement dans le diagnostic technique** : mutisme de `b4_flags` après la dette 14, mesure du clamp,
classes d'indiscernabilité, blocs de warmup, métriques brutes. Il est exclu du **seul verdict économique**, et
chaque ligne SOL porte le tag `DESCRIPTIF`.

**L'inadmissibilité se mesure sur la couverture réelle dans la période simulée.** Si `data_coverage.json` contredit
l'estimation de ~27 mois, la règle est **réévaluée avant le run**, avec re-soumission humaine — **jamais après**.
Si la mesure rend BTC inadmissible, BTC devient descriptif et le verdict de famille est
`inconclusif (D_NO_ADMISSIBLE_PAIR)`. Si `data_coverage.json` ne peut pas être produit, aucune paire n'est
admissible : `inconclusif (D_UNMEASURABLE)` — une règle qui supposerait silencieusement la couverture complète
serait un défaut.

### D.4 Warmup — transcription et classification exhaustive

Les neuf champs de `warmup[seg][tf]` pour `tf ∈ {4h, 1d, 1w}` sont transcrits par paire et par segment
(`interval`, `required`, `loaded`, `extended_by`, `stale_by_candles`, `largest_gap_candles`, `sufficient`, `first`,
`last` **[v]**). Le bloc ne décrit que le préfixe d'amorçage stampé `<= start`, **jamais** la série en fenêtre —
c'est précisément pourquoi le § D.1 mesure la couverture indépendamment.

Classification du segment `all`, **exhaustive** :

- **W0** — les trois blocs à `sufficient == True`.
- **W1** — `4h` **suffisant** (`loaded ≥ required`, `stale_by_candles == 0`, `largest_gap_candles ≤ 1`) **et** la
  seule cause d'insuffisance de `1d` / `1w` est une **lacune interne** (`largest_gap_candles > 1`), aucun
  timeframe périmé.
- **W2** — **tout autre cas** : `4h loaded == 0`, ou tout `stale_by_candles > 0` ou `None`, ou tout
  `loaded < required`. Les résultats de la paire sont `DESCRIPTIF` ; **aucune config de cette paire ne peut
  produire un verdict, positif ou négatif.**

**Attendu** : SOL → **W2** (mesuré sur la référence : `4h loaded 0, stale None` ; `1d stale 183` ; `1w stale 25`
**[v]**). BTC → **W1** (`4h loaded 91, sufficient true` ; `1d loaded 88 ≥ 50, stale 0, largest_gap 163` ;
`1w loaded 50 = 50, stale 0, largest_gap 23, extended_by 19` **[v]**).

W1 n'est pas bloquant, pour une raison **mécanique** et non orientée vers un résultat : `largest_gap_candles` sur
1 d / 1 w signifie que les EMA20/50 ont été amorcées **à travers** le trou pré-fenêtre de 164 jours, ce qui affecte
les entrées de **régime** ; l'ATR qui fixe l'espacement est un objet 4 h et il est amorcé (`loaded 91`, gap 0).
La statistique « nombre de clôtures de décision avec `get_regime(tf) is None` » **n'est pas spécifiée** : elle n'est
pas calculable depuis l'artefact (la borne naïve `required − loaded + stale` vaut −38 sur BTC 1 d et lève sur SOL
4 h où `stale` est `None` **[v]**).

**Comme `bias_1d = 0.2` fait vivre `regime_1d` dans TOUS les modes — y compris `none` — le qualificatif W1 porte sur
les 48 configs de la paire, pas seulement sur `1w_only` / `1d_only`** **[v]**. Qualificatif obligatoire, à imprimer
à côté de **chaque** chiffre de la paire concernée :

> « Le warmup 1d/1w de BTC est `sufficient=False` par `largest_gap_candles` 163 / 23 : les EMA20/50 qui alimentent
> `get_regime` ont été amorcées à travers le trou de 164 jours. `bias_1d` faisant vivre `regime_1d` dans tous les
> modes, **tout** résultat de cette paire — quel que soit `bear_protection_mode` — repose sur une porte dont
> l'amorçage n'est pas propre ; le réexaminer est une entrée obligatoire de C3. »

Le bloc `warmup` ne dépendant que de (paire, segment) et non des paramètres balayés, la classe W s'applique à la
paire entière ; le § I-A.8 asserte que le bloc est identique sur les 48 configs, et toute différence est **rapportée
et résolue en retenant la classe la plus stricte**.

---

## § E. Benchmark d'exposition — construit, pas cité

### E.1 Pourquoi les chiffres existants sont bannis de tout seuil

`scripts/compute_benchmarks.py` **[v]** : charge `timestamp >= P6_START AND timestamp < P6_END` là où les moteurs
chargent `<= end` (dette 15(c)) ; ancre la fenêtre de métriques à `candles[0].timestamp − intervalle`, soit
**2023-03-31**, un jour avant l'ancre du grid ; entre à l'**open** de la première bougie quotidienne ; facture une
entrée MARKET et **aucune sortie**, alors que le grid paie une liquidation terminale ; n'exporte que des
**scalaires** (pas de vecteur d'equity, pas de chemin de drawdown) ; et son CLI n'a que `--fees`,
`--pair-costs-file`, `--output` — **ni date, ni paire, ni capital**, donc il ne peut pas être re-visé.

Ses sorties (BTC B&H Sharpe 0.8470, MaxDD_daily 49.65 %, return +137,51 %, 1096 rendements ; SOL Sharpe 0.2954,
return −20,43 %, **824 rendements** — le trou SOL est visible dans le benchmark lui-même) **[v]** sont imprimées
dans le rapport comme **descripteurs historiques**, à côté des chiffres reconstruits, avec le delta. **Seul le
benchmark reconstruit est décisionnel.** `compute_benchmarks.py` n'est pas modifié.

### E.2 Le benchmark plein notionnel reconstruit (par paire)

Données : `exchange='binance'`, `interval=1440`,
`timestamp >= 2023-04-01T00:00Z AND timestamp <= 2026-04-01T00:00Z` — la convention de bornes des moteurs, ce qui
**répare** la dette 15(c) du côté de ce rejeu.

- **Ancre** `start`, `starting_balance = Decimal("1000")`, cash avant l'entrée, cash oisif à 0 %.
- **Constructibilité, avec le stamp nommé.** En end-stamping, la bougie quotidienne stampée exactement
  `2023-04-01T00:00:00+00:00` **clôture à l'instant d'ancre** : son close est le prix à `start`. Le benchmark est
  constructible pour une paire ssi cette bougie existe, ou si la première bougie stampée `> start` est à moins de
  24 h de `start`. **BTC : constructible. SOL : non constructible** — la première bougie en fenêtre a 271 jours de
  retard, et ré-ancrer à une date ultérieure est interdit (dates communes, sans exception).
- **Entrée** à ce close : `exec_in = close × (1 + spread + slippage)`,
  `qty = 1000 × (1 − taker) / exec_in`, avec `taker` de `ExchangeFees.from_name("bybit")` et `(spread, slippage)` de
  `config/pair_costs_b4.json` (BTC 0.0002 / 0.0002, SOL 0.0011 / 0.0002 **[v]**) — **les mêmes objets et le même
  fichier que la campagne**, assertés égaux (§ I-A.15).
- **Marks intérieurs** : `EquityPoint(c.timestamp, qty × c.close)` pour chaque bougie stampée `> start`, mark to
  market sans coût, exactement la convention du grid.
- **Liquidation terminale** : un point d'equity supplémentaire stampé à `end`, ajouté **après** le mark de même
  stamp, `equity = qty × close_last × (1 − spread − slippage) × (1 − taker)`. **Le grid en paie une, le benchmark
  aussi.**
- **Métriques** par `krakenbot.backtest_metrics.compute_metrics(points, [], start=…, end=…,
  starting_balance=Decimal("1000"), flows=[])` — signature réelle : `start`, `end`, `starting_balance` et `flows`
  sont **keyword-only** **[v]**. `MetricsResult` ne porte **pas** `total_return_pct` **[v]** : il est dérivé de
  `daily.nav[-1]` dans le script, qui le dit.
- **Exporté** : les 1097 NAV, les 1096 rendements quotidiens, `sharpe_ratio`, `sortino_ratio`,
  `max_drawdown_pct_daily`, `cagr_pct`, `calmar_ratio`, `n_daily_returns`, `total_return_pct` dérivé, `entry_price`,
  `exit_price`, les coûts facturés sur les deux jambes, et les diagnostics du § E.4.

### E.3 Les comparateurs à budget de risque

Le § 8 nomme explicitement le comparateur — « B&H/cash à budget de risque **et coûts comparables** » — donc il est
**construit**, pas déclaré impossible.

**Blend statique : allocation initiale, jamais rééquilibrée.** `λ × 1000` USDC dans l'actif à l'ancre avec
exactement les coûts du § E.2, `(1 − λ) × 1000` en cash à 0 %, une liquidation terminale sur la jambe actif. Tous
les coûts étant proportionnels au notionnel, la NAV est exacte et fermée :

```
NAV_λ(t) = (1 − λ) × 1000 + λ × NAV_bh(t)         pour chacun des 1097 instants de la grille
```

Un blend **rééquilibré** (une série de rendements `λ·b_t`) serait une exposition remise à λ chaque jour à coût nul :
irréalisable au spot, ne payant aucun des round-trips du § 2, et non composé — donc systématiquement **biaisé en
faveur de la stratégie**. On prend le statique.

**Les deux appariements se font par RECHERCHE sur les NAV statiques réellement construites.**
`λ_σ = σ_config / σ_bh` serait **faux** : dans un blend statique, le poids de l'actif **dérive avec le prix**, les
rendements du portefeuille ne sont donc pas `λ·r_bh` et le rapport des volatilités n'est pas λ.

```
Grille λ : {0.000, 0.001, …, 1.000}. Pour chaque λ on construit NAV_λ puis ses 1096 rendements quotidiens.

λ_dd = min{ λ : MDD_daily(indice de NAV_λ) >= MDD_daily(indice de la config) }     sinon 1
λ_σ  = min{ λ : σ_daily(NAV_λ)             >= σ_daily(config)             }        sinon 1
```

- **Monotonie** : *prouvée* pour `λ_dd`. `NAV_λ` est une transformée affine croissante de `NAV_bh`, donc le pic
  courant est la transformée du pic, et `dd_λ(t) = λ(P_V(t) − V(t)) / ((1−λ)·1000 + λ·P_V(t))` a une dérivée en λ
  strictement positive ; un maximum de fonctions croissantes point par point est croissant, donc le croisement est
  **unique**. **Non prouvée** pour `λ_σ` : le script **compte les croisements sur la grille**, retient le **plus
  petit** λ, et **rapporte le nombre de croisements**.
- **Tolérance gelée** : le résidu relatif `|cible(NAV_λ) − cible(config)| / cible(config)` est rapporté pour les
  deux appariements ; au-delà de **10 %**, l'appariement est étiqueté **approximatif** dans le rapport (descriptif,
  non bloquant).
- **Cas sans appariement possible**, gelés : (i) `cible(config) > cible(NAV_1)` ⇒ **λ = 1**, étiqueté « appariement
  impossible par le haut, comparaison contre le B&H plein notionnel » — le levier est interdit par le § 7, donc une
  config plus risquée que le B&H ne réclame aucune remise de risque ; (ii) `cible(config) = 0` ⇒ **λ = 0**,
  comparateur **100 % cash**, qui est l'autre benchmark nommé par le § 8.
- `backtest_metrics.max_drawdown_pct` est une routine **Decimal** **[v]** : les NAV flottantes sont converties en
  `Decimal` avant l'appel, sinon `TypeError`.

**Énoncé obligatoire** : *l'appariement sur le drawdown (ou la volatilité) observé est une **comparaison
rétrospective**, jamais une allocation validée pour l'avenir.* Et si `λ_dd < 0.02`, verbatim :

> « Le comparateur apparié détient moins de 2 % du capital dans l'actif ; la comparaison porte sur l'efficience à
> très petit budget de risque, pas sur une allocation alternative réaliste. Ce qui empêche un effet absolu
> trivialement petit de fonder un verdict est le plancher G2, pas cette comparaison. »

### E.4 Tests de comparabilité (bloquants)

L'assertion « la grille quotidienne du benchmark égale celle de la config » est **vacuante** — `daily_grid(start,
end)` est une fonction pure des deux instants **[v]** — et n'est donc pas utilisée. À sa place :

- `ff_days` = nombre d'instants de grille `t_k` (k ≥ 1) **sans** bougie de prix stampée dans `(t_{k−1}, t_k]`,
  c'est-à-dire le nombre de marks forward-fillés. Comparable ssi `ff_days ≤ 31` (la tolérance du § D).
- Une bougie existe à `start` ou dans les 24 h qui précèdent (constructibilité E.2), et une existe à `end`.
- `n_daily_returns == 1096`, tous les rendements finis, `min_t r_t > −0.5` (domaine de `log1p`, § F).
- Recoupement de provenance : à chaque minuit intérieur, le close 5 m stampé `J 00:00` doit égaler le close 1 d
  stampé `J 00:00` (end-stamping, B4.1) ; les écarts sont comptés et listés (attendu : 0). **Rapporté, non
  bloquant** — la série 1 d fait foi pour le benchmark.

### E.5 Repli

Si le benchmark n'est pas constructible ou pas comparable pour une paire : les chiffres de cette paire restent
**descriptifs**, aucun effet n'est calculé, aucun verdict économique n'est fondé, et le verdict de paire est
`inconclusif (E_NO_BENCHMARK)` — conformément au § 8 et au brief, qui poussent ce cas vers l'inconclusif plutôt que
vers un défaut. Il n'est **jamais** remplacé par la table du § 4 ni par la sortie de `compute_benchmarks.py`.
**SOL y est attendu**, par une seconde route indépendante qui concorde avec le § D.3.

### E.6 Taux sans risque

`rf = 0` des deux côtés. C'est une **convention** : le moteur ne paie aucun intérêt sur l'USDC oisif, donc facturer
au comparateur un rendement que la stratégie ne peut pas gagner reviendrait à comparer contre un instrument que le
projet n'opère pas. Elle n'est **pas neutre** : le blend détient `(1 − λ)` en cash et la config une fraction cash
**différente, variable et non exportée**.

**Aucune ligne de sensibilité `rf = 4 %/an` n'est publiée** : faute d'historique de cash côté grid, l'écart n'est
pas calculable, et il ne sera pas présenté comme une sensibilité mesurée. Le rapport écrit seulement que la
convention est `rf = 0` et qu'un `rf > 0` déplacerait Δ d'une quantité **non quantifiée ici**.

---

## § F. Effet, borne d'incertitude, multiplicité, « échantillon trop petit »

numpy 2.4.1 + pandas 2.3.3 + stdlib uniquement. **scipy est absent** (extra `ml`) et son installation est interdite ;
rien de ce qui suit n'en a besoin.

### F.1 Le Sharpe n'est décisionnel nulle part

Motifs — les seuls à inscrire :
1. la question de ce diagnostic est une question de **magnitude** — un effet assez grand pour justifier du travail —
   **pas** une question de ratio ;
2. un ratio **ne pénalise pas le coût d'opportunité d'être hors marché**, et capturer 4,57 % d'un mouvement de
   137,51 % (~3 %) à 1 000 USDC de capital se juge en **magnitude absolue** ;
3. le nombre de jours réellement exposés est faible, donc l'**incertitude propre du ratio** est grande.

Le Sharpe de la config et celui du B&H plein notionnel restent **rapportés à titre descriptif**, pour qui applique
le § 4 littéralement.

*Ne sont écrits nulle part, parce que faux* : « une courbe majoritairement cash rend le Sharpe artefactuel » (à
poids constant avec du cash à rendement nul, moyenne et volatilité baissent proportionnellement et le ratio est
inchangé) ; « la NAV bouge 35 % des jours » comme mesure d'exposition (ce n'en est pas une, cf. § C.4).

### F.2 L'effet

Pour la config `j`, sur `all`, depuis `equity_daily["all"]["values"]` (1097 flottants) :

```
s_k = v_k / v_{k−1} − 1                                      k = 1..1096   (aucun flux externe sur ces runs)
CAGR(x) = (exp( Σ_k log1p(x_k) × 365 / 1096 ) − 1) × 100     en %/an
Δ_j^dd  = CAGR(config j) − CAGR(blend statique à λ_dd(j))    en points de % par an
Δ_j^σ   = CAGR(config j) − CAGR(blend statique à λ_σ(j))     en points de % par an
```

`Σ log1p` reproduit exactement l'indice C1 (`I_end = Π(1+r)`, pas de flux, `starting_balance = 1000` donc l'indice
est proportionnel à la NAV) ; le § I-A.10 vérifie numériquement cette reproduction avant tout calcul. Le CAGR est
**recalculé** et non lu dans l'entrée, `cagr_pct` ne faisant pas partie des 24 clés exportées **[v]**.

### F.3 Gates ponctuels décisionnels, évalués sur CHAQUE config éligible

```
G1   net_pnl(all) > 0
G2   total_return_pct(all) >= 6.0          # sur 1096 jours
G4   Δ_j^dd > 0   ET   Δ_j^σ > 0
```

Ils sont évalués sur **tout l'ensemble éligible**, jamais sur une config pré-sélectionnée : trier par une quantité
puis tester le gagnant renverrait un « non » opératoire alors qu'une autre config du même ensemble passe.

**G2 — l'effet économique minimum (§ 8 (i)). Ancrage, tel quel :**

> **6 % sur trois ans est un seuil conventionnel de poursuite de recherche**, pas une borne dérivée d'une
> quantification des frictions.
>
> L'ancrage par les frictions non modélisées du § 2 est **retiré** : il appliquait des points de base au **capital**
> alors qu'ils portent sur le **notionnel**. Arithmétique correcte : 25 cycles × 25 USDC × 8 bps = **0,50 USDC**,
> soit **0,05 %** de 1 000 USDC. *Cette arithmétique corrige la conversion des bps en pourcentage du capital ; elle
> ne quantifie pas les frictions non modélisées, dont l'amplitude reste inconnue ; le seuil de 6 % reste une
> convention de poursuite de recherche.*
>
> **Divulgation** : au moment de fixer ce plancher, la référence post-C2 BTC (+4,57 % sur 3 ans) était connue ; le
> plancher a été placé au-dessus pour préserver le pouvoir de falsification du gate.
>
> 6 % sur trois ans ≈ **1,96 %/an**, soit **~20 USDC/an à 1 000 USDC**. **Franchir ce plancher autorise davantage de
> recherche (C3), jamais un déploiement.** Un verdict « candidat » ne doit pas pouvoir se lire comme « ça
> rapporte ».

L'option d'un plancher à 13 % a été écartée : « le vrai coût d'opportunité du cash USDC » n'existe pas tant qu'une
alternative rémunérée n'est pas nommée et documentée avec son propre risque de contrepartie. Cette formulation
n'est pas reprise.

**G3 est DESCRIPTIF, ce n'est pas un gate.** `net_pnl ≥ 10 × total_fees` n'est **pas une borne démontrée** des
frictions inconnues, et les non-exécutions ne se résument pas à un multiplicateur de frais. Le ratio
`net_pnl / total_fees` reste **imprimé par config** ; si un candidat émerge avec `net_pnl < 10 × total_fees`, le
rapport le dit comme **qualification du résultat**, jamais comme échec.

### F.4 Borne d'incertitude (§ 8 (iii)) — bootstrap par blocs circulaires, correction simultanée mono-étape

Pourquoi ni bootstrap iid ni erreur-type normale : les rendements quotidiens sont **sériellement dépendants** (un
lot est marké jusqu'à sa vente appariée — détention maker moyenne mesurée ≈ 4 jours **[v]**), à **queues lourdes**
(kurtosis mesurée 98,9 sur la référence : un jour de liquidation domine **[v]**), nuls sur une large fraction des
jours, et **quasi colinéaires** entre les 48 configs (même actif, même chemin).

```
N = 1096 ; L ∈ {10, 21, 42} avec L = 21 en tête ; m = ceil(N/L) ; B = 10000
rng    = numpy.random.default_rng([20260919, pair_index, L])       # pair_index 0 = BTC, 1 = SOL
starts = rng.integers(0, N, size=(B, m))                            # tirés UNE fois par L, avant tout chunking
idx    = (starts[:, :, None] + arange(L)).reshape(B, -1)[:, :N] % N # circulaire, indices APPARIÉS config <-> benchmark
```

`L = 21` (trois semaines) : la dépendance à préserver est le portage d'inventaire plus un pas de la cadence 1 w ;
c'est ≈ 60× la cadence de reconstruction effective (8 h) et ≈ 5× la détention maker moyenne. `L = 10 ≈ N^{1/3}` est
le point bas de sensibilité, `L = 42` (deux mois) le point haut. `B = 10000` : le quantile unilatéral à 5 % tombe
sur la 500ᵉ statistique d'ordre, et l'erreur de Monte-Carlo sur une probabilité vaut ≈ 0,0022.

**λ est ré-estimé dans chaque réplication** (mêmes indices de blocs pour la config et pour le benchmark) :
rééchantillonner en gelant λ n'évalue pas la procédure complète. Implémentation gelée : par réplication, la NAV
bootstrap du benchmark est reconstruite par produit cumulé, puis la **courbe λ → cible(NAV_λ)** est calculée **une
fois par réplication** sur une grille à deux étages (grossière au pas 0.005, puis raffinement ±0.005 au pas 0.001)
et **inversée par `searchsorted` pour les 48 configs** — le coût est porté par la réplication, pas par le couple
(réplication, config).

**MDD vectorisé — à valider AVANT la campagne.** La boucle `Decimal` de `backtest_metrics.max_drawdown_pct` est un
choix d'implémentation, pas une contrainte. Une implémentation numpy (produit cumulé + maximum courant) est écrite,
son **temps et sa mémoire mesurés**, et son **équivalence numérique vérifiée contre le calcul Decimal** sur les
courbes observées (résidu relatif ≤ 1e-9). Le résultat de cette vérification est committé dans `calibration.json`.

**Repli déclaré d'avance.** Si la ré-estimation ne tient pas dans un budget mural déclaré — **2 h par combinaison
(L, appariement)** — ou si l'équivalence échoue, la borne est calculée **à λ gelé** et **étiquetée « analyse de
sensibilité, sans garantie de couverture 95 % »** ; dans ce cas **aucun verdict `candidat` ne peut s'y appuyer** et
le run ne peut plus rendre que `dépriorisation` ou `inconclusif`.

```
Pour chaque (L, appariement) :
    V*_b  = max_{j ∈ J_calc} ( Δ*_{b,j} − Δ̂_j )        # null recentré : E[Δ_j] = 0 pour tout j
    q_FWE = numpy.quantile(V*, 0.95, method="linear")
    LB_j  = Δ̂_j − q_FWE        pour CHAQUE j            # borne simultanée mono-étape, par configuration
```

**La famille de correction est l'ensemble des 48 courbes *calculables* de la paire** (`J_calc`). L'admissibilité, la
couverture et les gates s'appliquent **au stade du verdict**, pas par un remplissage `−∞` : des `−∞` pour les
configs filtrées ne démontreraient pas la neutralité statistique du filtre. `|J_calc|` est rapporté.

Max-T plutôt que Bonferroni, **pour une raison propre à ce run** : des configs byte-identiques produisent des
colonnes `Δ*` parfaitement corrélées, donc `q_FWE` s'effondre vers le quantile mono-config — la correction voit le
nombre **effectif** d'essais, exactement le comportement voulu sous la dégénérescence attendue. Max-T **non
studentisé** (studentiser avec des erreurs-types bootstrap de la même passe est une approximation non justifiée ;
l'échelle est homogène par construction — même actif, même chemin, même lot de 25 USDC). Le renoncement est
**mesuré, pas affirmé** : le rapport imprime `max_j se_j / min_j se_j` sur `J_calc` et, au-delà de 3, signale que la
correction est conservatrice pour les configs de petite échelle. **Le passage en stepdown n'est pas requis.**

`Σ log1p` étant indépendant de l'ordre, la statistique ne dépend d'une réplication que par les **comptes par date** :
`C` (B × N, int32) est construit par `bincount`, puis `TLS = C @ log1p(S)` et `TLB = C @ log1p(Bl)`. Les chunks
(2000 réplications) s'appliquent à la matrice `starts` **déjà tirée**, donc le chunking ne peut changer aucun
tirage.

**Aussi rapporté, décisionnel nulle part** : `se_j` par config ; le **jackknife de queue** — `Δ̂` recalculé après
retrait du plus grand et du plus petit log-rendement quotidien, obligatoire vu la kurtosis ; le compte de
réplications dégénérées. **Aucun intervalle de confiance par configuration n'est publié comme intervalle
d'inférence** : un IC basique/pivotal ordinaire n'est pas un intervalle d'inférence sélective et ne sera pas
étiqueté comme tel.

### F.5 Résolution pré-enregistrée (`calibration.json`, calculé et committé AVANT la campagne)

Sur la seule courbe d'equity grid post-C2 existante (`results/c2_replay/P6_grid_rerun.json`, défauts de classe,
`atr_multiplier 4.0` **[v]**) : on construit **le benchmark de la fenêtre** (§ E), on calcule **Δ** pour les deux
appariements, et on **bootstrappe Δ** → un **SE mono-config déclaré avant le run**, par `L`.

C'est la quantité pertinente : le SE du CAGR d'une courbe seule ne renseigne **ni** sur l'écart au benchmark
apparié, **ni** sur le maximum sur 48 essais. **Aucune extrapolation au quantile FWE n'est écrite** — ni bornes du
type `1.645–3.1 × SE`, ni « ce design ne peut pas détecter un effet sous ~1 pp/an », ni « G2 sera la contrainte
mordante ». `calibration.json` porte également la vérification d'équivalence du MDD vectorisé et son coût mesuré.

La référence est divulguée comme **quasi-membre** de la famille balayée : son `min_spacing_pct 0.015` est le
minimum balayé et son `bear_protection_mode` nul laisse `pause_1w_strong_bear = True`, soit le bras comportemental
`1w_only` **[v]** ; seul `atr_multiplier 4.0` est hors balayage. **Aucun seuil de ce document n'en est dérivé.**

### F.6 Éligibilité = la règle « échantillon trop petit »

Une config est **ÉLIGIBLE** ssi, toutes conditions réunies :
1. sa paire est admissible (§ D.2) et sa classe de warmup `all` est W0 ou W1 (§ D.4) ;
2. le benchmark est constructible et comparable pour cette paire (§ E.4) ;
3. `cycles ≥ 25` (§ C.2) ;
4. `nnz ≥ 110` (10 % de 1096) — **filtre conventionnel d'activité**, pas une preuve de quantité d'information : avec
   L = 21 et 53 blocs par réplication, une série comptant moins d'une centaine de jours informatifs fait dépendre la
   distribution rééchantillonnée du tirage d'un ou deux amas ;
5. `Δ_j` calculable : 1096 rendements définis des deux côtés, tous finis, `min_t r_t > −0.5`, λ fini.

Une config inéligible est imprimée avec ses métriques et son **premier gate en échec**, taguée
`NON ÉVALUÉE (gate: …)`. **Son Δ décisionnel n'est pas publié** — on ne calcule pas quand même pour commenter le
chiffre.

Si aucune config d'une paire n'est éligible, **le bootstrap n'est pas lancé pour cette paire** et le verdict de
paire est `inconclusif`, avec la raison prise du **gate modal en échec** : `C_COVERAGE` (clause 3),
`F_NOT_ESTIMABLE` (clauses 4 ou 5), `E_NO_BENCHMARK` (clause 2), `D_WARMUP_W2` / `D_NOT_ADMISSIBLE` (clause 1). Le
premier gate en échec de chaque config étant toujours imprimé, la raison n'est jamais affaire de goût.

### F.7 Valeurs indéfinies et infinies

- `sharpe_ratio`, `sortino_ratio`, `calmar_ratio`, `profit_factor` à `None` ne sont **jamais** comparés à un seuil,
  jamais coercés en 0, jamais moyennés dans une décision. **Aucune règle décisionnelle de ce document ne les lit** :
  Δ, `net_pnl`, `total_return_pct`, `cycles`, `MDD_daily` et `σ_daily` portent toute la décision, et aucun ne peut
  valoir `None` sur une entrée validée. Cela **dissout** le problème du profit factor infini au lieu de le rustiner.
- `profit_factor is None` est désambiguïsé dans le rapport par `gross_profit_net` / `gross_loss_net`
  (`> 0 / 0` → infini ; `0 / 0` → indéfini), et `pf_excluded_trades != 0` est imprimé « PF incomplet ». Purement
  descriptif.
- Tout NaN ou Inf dans une NAV, un rendement, λ, Δ ou Δ* ⇒ **échec de validité** (§ I), pas un nombre à commenter.
- Une réplication est dégénérée si elle produit un Δ* non fini ; elles sont comptées, et si une config dépasse
  **10 sur 10 000**, l'inférence est déclarée inutilisable pour la paire → `inconclusif (F_NOT_ESTIMABLE)`.

---

## § G. Agrégation config → paire → famille

### G.1 Statut de config (premier match l'emporte)

| # | Condition | Statut |
|---|---|---|
| 1 | paire non admissible (§ D.2) ou warmup `all` en W2 (§ D.4) | `DESCRIPTIF` |
| 2 | benchmark non constructible / non comparable (§ E.4) | `NO_BENCHMARK` |
| 3 | `cycles < 25` (§ C.2) | `BELOW_COVERAGE` |
| 4 | `nnz < 110` ou Δ incalculable (§ F.6.4–5) | `NOT_ESTIMABLE` |
| 5 | sinon | `ELIGIBLE`, et `PASSES_GATES` ssi **G1 ∧ G2 ∧ G4** |

Aucun statut « INVALID » par config n'existe : le § I-A est **au niveau du run et bloquant**, donc l'argument
« une entrée était mauvaise, le reste tient » n'est pas disponible.

### G.2 Porte au niveau du run, avant tout le reste

```
si une assertion de validité de campagne (§ I-A) échoue   -> FAMILLE = inconclusif (R0_INVALID_RUN) ; STOP
si b4_flags est non vide APRÈS § I-A.8 et § I-A.12        -> FAMILLE = inconclusif (R1_ACCOUNTING_FLAG) ; STOP
```

**Pas de sauvetage partiel** : le même moteur a produit les 96 entrées ; une anomalie comptable non résolue dans une
seule est une preuve que la comptabilité n'est pas réconciliée en général. « Flag investigué » ne rend pas le run
admissible (brief § 6). Une entrée portant `"error"` est un échec de **job**, traité par la règle de reprise du
§ 0.4 (classement de l'erreur avant toute relance), puis `R0`.

**Un job en échec sur une paire inadmissible tue quand même le run.** C'est délibéré et c'est le seul endroit où SOL
peut affecter le verdict de famille : un job planté signifie que l'artefact est incomplet, l'assertion de jeu de
clés (§ I-A.2) échoue, et accepter un fichier de 94 entrées serait accepter un périmètre inconnu. Ce n'est pas SOL
qui vote ; c'est le run qui n'existe pas.

### G.3 Verdict de paire

```
si non admissible ou warmup W2                   -> "descriptif"
si benchmark non comparable                      -> inconclusif (E_NO_BENCHMARK)
J = { configs ELIGIBLE } ;  si J = ∅              -> inconclusif (gate modal en échec)
C = { j ∈ J : G1(j) ET G2(j) ET G4(j)
              ET LB_j > 0 dans LES SIX combinaisons (L ∈ {10,21,42} × appariement ∈ {dd, σ}) }
si C ≠ ∅                                         -> candidat
sinon si aucun j ∈ J ne passe G1 ET G2 ET G4     -> dépriorisation (G_POINT_NEGATIVE)
sinon                                            -> inconclusif (F_CANNOT_SEPARATE)
```

**Le représentant se choisit APRÈS**, parmi `C` : `argmax Δ̂^dd` ; départages successifs `Δ̂^σ` plus grand, puis
`max_drawdown_pct_daily` plus petit, puis `params_hash(params)` lexicographiquement le plus petit — déterministe
jusqu'au dernier pas. Il est nommé comme **porteur de la preuve**, jamais comme une sélection.

### G.4 Verdict de famille

```
votantes = [ P ∈ {BTC/USDC, SOL/USDC} : verdict_paire(P) != "descriptif" ]
si run non exploitable                      -> inconclusif (R0 / R1)
sinon si votantes = ∅                       -> inconclusif (D_NO_ADMISSIBLE_PAIR)
sinon si une verdict_paire == "candidat"    -> candidat
sinon si toutes == "dépriorisation"         -> dépriorisation
sinon                                       -> inconclusif (raison de la paire votante)
```

**Cas réel attendu : BTC vote, SOL est `descriptif` ⇒ le verdict de famille est celui de BTC.**

### G.5 Non-règles explicites

- **La dégénérescence ne change jamais un verdict.** « 48 → 1 classe » et « 48 → 48 classes » se lisent à
  l'identique par les § C à H ; le compte de classes est un **constat**, pas une porte, et n'entre dans aucune
  statistique.
- La mesure du clamp (§ B) ne change jamais un verdict, dans aucune direction.
- `train` / `test` ne changent jamais un verdict : pas de concaténation, pas de « confirmé sur le test », pas de
  critère de dispersion.
- SOL ne contribue ni à `candidat` ni à `dépriorisation` (§ D.3).
- Le Sharpe ne change jamais un verdict (§ F.1). G3 non plus (§ F.3).
- `candidat` n'est ni un déploiement, ni une sélection paper, ni la sélection d'une configuration. **Le run ne
  sélectionne rien.**

### G.6 Ligne de rapport par config (colonnes obligatoires)

`params` · identifiant de classe (§ A) · `cycles` · `liquidation.positions` · `nnz` · classe de warmup · statut et
premier gate en échec · `net_pnl` · `total_return_pct` · `total_fees` · `net_pnl / total_fees` (G3 descriptif) ·
`max_drawdown_pct_daily` · `max_drawdown_pct_engine` · `sharpe_ratio` (descriptif) · `profit_factor` (descriptif,
désambiguïsé) · `λ_dd` · `λ_σ` · résidus d'appariement · `β̂` · `Δ̂^dd` · `Δ̂^σ` · `se_j` · `LB_j` sur les six
combinaisons.

---

## § H. Les trois verdicts — conditions nécessaires et suffisantes

**`candidat`** ⟺ le run est exploitable (§ I-A au vert, `b4_flags` muet **après** les assertions de présence)
**et** il existe une paire admissible de classe W0/W1 dont le benchmark est comparable **et** il existe **une même
configuration éligible** de cette paire qui satisfait **G1 ∧ G2 ∧ G4** **et** dont les **six bornes simultanées
`LB_j` sont strictement positives**. Tout cela, sur la **même** configuration, ou pas `candidat`.

Sens, verbatim au rapport :

> « Dans ce périmètre gelé, ce grid — mesuré contre un blend buy-and-hold / cash de son propre actif, à son propre
> budget de drawdown quotidien (et séparément de volatilité), sur ses propres dates et à ses propres coûts — a
> produit un effet positif qui survit aux 48 essais, sur un rendement absolu au-dessus du plancher gelé. **La
> famille mérite davantage de travail, et rien d'autre.** Ce n'est ni un déploiement, ni une sélection paper, et
> aucune configuration n'est sélectionnée : C3 (equity continue, sélection chronologique) reste un prérequis. Le § 5
> de `CONTRAINTES_POST_B4.md` s'applique au travail supplémentaire : une famille déjà listée comme morte sous
> l'instrument v1 revient avec un **mécanisme**, pas avec de nouveaux paramètres — le balayage qui a produit cette
> preuve n'est pas lui-même ce travail. »

**`dépriorisation`** ⟺ le run est exploitable, au moins une paire est votante (admissible, W0/W1, benchmark
comparable, `J ≠ ∅`) **et**, sur chaque paire votante, **aucune** config éligible ne satisfait G1 ∧ G2 ∧ G4.

C'est **mérité, pas par défaut** : les gates sont des faits ponctuels sur le chemin réalisé, évalués sur tout
l'ensemble éligible ; le maximum sur les essais y échoue déjà, et aucune correction de multiplicité ne pourrait les
rendre positifs — elle ne peut qu'abaisser la borne. Portée épistémique, verbatim : *« l'effet mesuré sur cette
fenêtre est sous le minimum gelé ; ce n'est pas une affirmation que l'effet vrai est nul. »* Portée du périmètre,
verbatim : *« `grok_grid_atr_adaptive_v4` sur `GRID_ATR_GRID`, BTC/USDC, 2023-04-01 → 2026-04-01, défauts de classe,
modèle de fees Bybit, données Binance — **pas** l'impossibilité économique du grid trading, et rien sur un autre
périmètre. Rejoint le § 5 : la famille ne revient qu'avec un mécanisme nouveau, jamais avec de nouveaux
paramètres. »*

**`inconclusif`** ⟺ tout le reste — dont le cas « des configs passent les gates ponctuels mais aucune ne tient les
six bornes ». Raison consignée dans la liste fermée, **dans cet ordre de priorité** : `R0_INVALID_RUN` ·
`R1_ACCOUNTING_FLAG` · `D_UNMEASURABLE` · `D_NO_ADMISSIBLE_PAIR` · `D_WARMUP_W2` · `E_NO_BENCHMARK` ·
`C_COVERAGE` · `F_NOT_ESTIMABLE` · `F_CANNOT_SEPARATE`.

Conséquence, verbatim : **pas de déploiement et pas de tuning supplémentaire** ; la raison est écrite, et le
périmètre **n'est pas élargi pour chercher une autre réponse**.

Placement délibéré des deux frontières : une estimation **positive** qui échoue à la borne familiale est
`inconclusif`, **jamais** `dépriorisation` — l'absence de significativité n'est pas une preuve d'absence ; une
estimation **en échec sur les gates ponctuels** est `dépriorisation`, **jamais** `inconclusif` — sinon le négatif
attendu refuit vers « non résolu, à re-tenter avec des paramètres », l'état exact que le § 5 existe pour fermer.

---

## § I. Validité — deux étapes séparées

La boucle de dépendance est cassée : la validité de campagne **ne lit aucun artefact d'analyse**, et la validité des
analyses s'exécute après elles.

**L'ordre fait partie de la spécification.** `collect_flags` saute silencieusement toute entrée portant `"error"`
**[v]** (`scripts/b4_flags.py:98`) et `flag_segment` renvoie `[]` sur un bloc `liquidation` absent **[v]**
(`b4_flags.py:33`) : « `b4_flags` est muet » est un **faux vert** tant que I-A.1 à I-A.12 n'ont pas passé.

### I-A. Validité de campagne — `scripts/audit/rejeu_validate_campaign.py` (exit 0 / 2)

| # | Assertion | Ce qu'un échec signifie |
|---|---|---|
| 1 | Le fichier existe et parse en objet JSON ; aucun `*selection*.json` ni `*report*.md` dans le répertoire de sortie ; le texte brut ne contient pas `selected_for_paper` | la phase report interdite a été exécutée |
| 2 | Exactement **96** entrées, 48 par paire, jeu de clés **égal à celui reconstruit dans le script** par `p7_grids.expand_grid(GRID_ATR_GRID)` et `run_p7_grid_search.make_key(...)` — jamais codé en dur — et suffixe 8-hex de chaque clé égal à `params_hash(entry["params"])` | dérive de périmètre, troncature, ou clé qui n'identifie plus sa config |
| 3 | **Aucune entrée ne porte de clé `"error"`** (nommées et comptées en premier) | un job a échoué ; `collect_flags` l'aurait caché. Reprise § 0.4, puis R0 |
| 4 | Conditionnelle à 3 : chaque entrée a exactement les 22 clés top-level attendues | une autre version du runner, ou un fichier édité à la main |
| 5 | `strategy` ; `pair` dans les deux ; `exchange == "binance"` ; `fees == "bybit"` ; `metrics_version == 2` ; `replay_version == 2` (aussi via `require_metrics_version`) ; basename de `pair_costs_file` = `pair_costs_b4.json` ; `pair_costs` **comparé au fichier lui-même** ; `min_order_usdc == 5.0` ; `phase == "1"` ; `window_idx is None` ; `dca_counters is None`. **`liquidation[seg].spread_pct` / `.slippage_pct` ne sont assertés que si `positions > 0` ; si `positions == 0`, ils doivent être `null`**, comme `timestamp`, `price`, `reference_price`, avec `trades == 0` **[v]** | les simulations n'ont pas été produites sous le périmètre de coûts gelé. La clause « null sur segment plat » est ce qui empêche un segment plat légitime de tuer le run |
| 6 | `period` égal aux quatre bornes, le split étant **recalculé** `P7_START + (P7_END − P7_START) × 0.7`, pas codé en dur | une autre fenêtre : rien des § C-F ne s'applique |
| 7 | `params` égal au dict attendu pour sa clé. Dans `effective_params.params` (forme réelle `{strategy_class, passed_params, params:{nom:{value, source}}}`, **Decimals exportés en chaînes** **[v]**), comparaison par `Decimal(str(value))` : `min_spacing_pct` et `atr_multiplier` contre `params` ; `max_spacing_pct == 0.05` ; `order_size_usdc == 25` ; `grid_levels == 12` ; `atr_period == 14` ; `recalc_hours == 6` ; `bias_1d == 0.2` ; `max_allocation_pct == 20.0` ; `bear_protection_mode` égal à `params` ; `pause_1w_strong_bear` True pour `1w_only`, False pour `none` et `1d_only` **[v]**. **`source` n'est jamais asserté** (il vaut `class_default` même quand l'override a posé le flag **[v]**) et **`bear_protection_1d_enabled` n'est pas asserté** (non exporté **[v]**) — consigné dans les non-mesurables, pas silencieusement sauté. Limitation consignée : `effective_params` est capturé au **dernier** segment exécuté (`all`) **[v]** | la dette 13 a bougé en silence, ou un override n'a pas atteint la stratégie |
| 8 | `liquidation`, `equity_daily`, `rejections`, `warmup` non nuls, chacun avec exactement les clés `{train, test, all}` ; `liquidation[seg]` a exactement **18** clés **[v]** ; `warmup[seg]` a `{4h, 1d, 1w}` avec les 9 champs ; `rejections[seg]` a `unit`, `by_cause`, `events` sur les 7 causes **[v]** ; le bloc `warmup` est **identique sur les 48 configs d'une paire** (différence rapportée, classe la plus stricte retenue) | **le faux vert** : un bloc `liquidation` absent fait renvoyer `[]` à `flag_segment` |
| 9 | `equity_daily["all"]` aux bornes gelées, **1097 valeurs → 1096 rendements** ; `train` **769 → 768** ; `test` **330 → 329** ; `values[0] == 1000.0` ; toutes finies et `> 0` ; aucun NaN/Inf | la grille quotidienne ou l'ancre ne sont pas celles de C1 ; le § F ne peut pas tourner |
| 10 | Chacun de `train`/`test`/`all` a exactement les **24** clés de `METRICS_VERSION 2` **[v]**. **Auto-test d'instrument** : depuis `equity_daily[seg].values` convertis en `Decimal`, recalcul des rendements, de `sharpe_ratio`, `sortino_ratio`, `max_drawdown_pct(indice)` et du compte de rendements définis, avec `\|recalculé − exporté\| <= 1e-6` pour chaque valeur définie, `None ↔ None` exactement, et `n_daily_returns == 1096` sur `all`. **`cagr_pct` n'est pas exporté : il est recalculé et comparé à aucun champ.** Le seul recoupement admis le concernant est l'identité interne `\|calmar_ratio × max_drawdown_pct_daily − CAGR_recalculé\| <= 1e-6`, **évaluée uniquement quand `calmar_ratio is not None`** ; sinon l'assertion est **sautée et le saut est consigné** | les métriques exportées ne sont pas celles de la courbe exportée, ou le post-traitement a dérivé du contrat C1 |
| 11 | Identités comptables par segment, toutes **Decimal-coercées** par `Decimal(str(x))` comme `b4_flags._dec` **[v]** : `total_trades >= liquidation.positions >= 0` ; `cycles >= 0` ; `winning_trades + losing_trades == total_trades` ; `starting_balance == 1000.0` ; `duration_days == 1096.0` sur `all` ; `pf_excluded_trades == 0` ; **`unrealized_pnl == liquidation[seg].pnl` à 1e-9** — ce champ porte le **P&L de liquidation terminale**, pas un mark ouvert (mesuré : BTC `all` −15.310009211802027 = `liquidation.pnl` exactement **[v]**), donc **aucune assertion « ≈ 0 » n'existe nulle part dans ce document** ; et, si le segment s'est terminé à plat, `\|net_pnl − (ending_balance − starting_balance)\| <= 1e-6` | une identité comptable est rompue → run inexploitable |
| 12 | Réconciliation de liquidation, explicite et non déléguée, après coercition Decimal : `residual_net_proceeds == 0` et `residual_trade_btc == 0` exactement ; `\|inventory_divergence_btc\| <= 1e-12` ; `\|dust_written_off_btc\| <= 1e-12` ; `\|net_pnl − net_pnl_lot_basis\| <= 1e-9` — les constantes `DUST_BTC` / `NET_PNL_TOL` de `b4_flags.py` **[v]**, appliquées ici **après** que la présence est prouvée | une anomalie comptable non résolue |
| 13 | **Seulement maintenant** : `b4_flags.collect_flags(results) == []`, **et** une ré-application indépendante de `flag_segment(liquidation[seg], entry[seg])` sur les 96 × 3 couples renvoie `[]` | la dette 14 étant corrigée, le silence est l'attendu et un flag est un **échec du run** (R1) |
| 14 | **Intégrité de l'instrument, contre le sha épinglé `9897803`** : `git diff --stat 9897803..HEAD -- src scripts/backtest.py scripts/run_p6_backtests.py scripts/run_p7_grid_search.py scripts/p7_grids.py config pyproject.toml poetry.lock` **vide** ; sur `tests`, `git diff --stat 9897803..HEAD -- tests` ne doit lister **que**, et en ajout pur, la liste close : `tests/test_scripts/test_rejeu_data_coverage.py`, `test_rejeu_validate_campaign.py`, `test_rejeu_signatures.py`, `test_rejeu_spacing_clamp.py`, `test_rejeu_benchmark.py`, `test_rejeu_effect.py`, `test_rejeu_verdict.py` — **aucun test existant modifié ou supprimé** ; **et** `git status --porcelain` vide sur tous ces chemins. Sha256 de chaque fichier de moteur consigné, plus `git rev-parse HEAD`, sha256 de `poetry.lock`, `numpy.__version__`, hôte, version de Python | un diff commit-à-commit ne voit pas les éditions non committées, et la campagne tourne depuis l'arbre de travail ; `dev` est une référence mouvante et l'incident du 16/09 en est le précédent |
| 15 | `data_coverage.json` et `benchmark.json` existent, ont été **produits avant la campagne**, portent leurs champs gelés, et leur `pair_costs` / modèle de fees égalent ceux de la campagne | le § D ou le § E ne peut pas être appliqué |

Un échec de I-A rend **tout le run** inexploitable, pas seulement l'entrée fautive.

### I-B. Validité des analyses — `scripts/audit/rejeu_validate_analysis.py`

Exécutée **après** `rejeu_effect.py` et **avant** `rejeu_verdict.py`. `effect.json` consigne `B`, chaque `L`, chaque
graine, `numpy.__version__`, `|J_calc|`, **le mode de λ (ré-estimé / gelé-sensibilité)**, le compte de réplications
dégénérées, et le premier gate en échec de chaque config inéligible ; un rerun sur les mêmes entrées reproduit
`LB_j` **bit à bit**. `signatures.json` et `clamp.json` sont présents, ou explicitement marqués non productibles.

Un échec ici donne `inconclusif (F_NOT_ESTIMABLE)` sans toucher au verdict de campagne.

---

## § J. Non-mesurables déclarés, chacun avec la règle qui remplace la mesure

1. **Exposition / notionnel déployé au cours du temps, et son plafond.** Non exportés ; les lots survivent aux
   reconstructions et les achats ne sont bornés que par le cash. → la voie alternative du § 8 est **écartée** ; seul
   le repère à 25 cycles admet. `β̂` et `nnz` sont rapportés et ne décident que le filtre d'activité.
2. **Quels jours en fenêtre avaient réellement des données.** `equity_daily` est forward-fillée sans marqueur et
   `n_daily_returns` vaut 1096 même à travers le trou SOL de 455 jours **[v]**. → la couverture est mesurée
   séparément depuis la DB (§ D), jamais imputée par jour, et `n_daily_returns` n'est **jamais** une statistique de
   couverture.
3. **Le flux d'ordres.** Pas de journal de transactions. → le § A est une indiscernabilité, avec légende verbatim,
   et n'alimente aucune statistique.
4. **`bear_protection_1d_enabled`.** Posé sur l'instance mais jamais exporté **[v]**. → le § I-A.7 asserte la chaîne
   de mode et `pause_1w_strong_bear` ; le rapport dit que le drapeau 1 d lui-même est inobservable dans l'artefact.
5. **L'état ATR et régime réalisé du moteur.** Le § B les recalcule hors ligne avec un autre amorçage. → étiqueté
   mesure **distributionnelle**, ne décide rien.
6. **Le drawdown intrabar.** Non reconstructible (contrat C1). → toute comparaison de drawdown est
   quotidien-contre-quotidien des deux côtés ; `max_drawdown_pct_engine` reste diagnostic et n'est jamais un critère
   inter-familles.
7. **File d'attente, non-exécutions, fills partiels, sélection adverse** (§ 2 : non modélisés, non quantifiés). →
   **aucun substitut chiffré** : G3 est descriptif, et la conditionnalité au modèle de fill est écrite dans chaque
   verdict.
8. **L'incertitude d'échantillonnage de λ.** → λ est **ré-estimé dans le bootstrap** ; à défaut, le résultat est
   étiqueté « analyse de sensibilité, sans garantie de couverture 95 % » et ne peut fonder aucun `candidat`.
9. **L'effet d'un `rf > 0`.** Non calculable faute d'historique de cash côté grid. → **aucune ligne de sensibilité
   publiée** ; la convention `rf = 0` est déclarée comme telle.
10. **L'économie de SOL sur cette fenêtre.** → inadmissible (§ D) et benchmark non constructible (§ E), deux routes
    indépendantes vers le même traitement : descriptif, ne contribue à rien.
11. **La validité hors échantillon / chronologique.** Une fenêtre ; le walk-forward de la phase 2 n'est pas
    chronologique. → `train`/`test` ne votent jamais ; `candidat` signifie explicitement « mérite du travail, doit
    encore passer C3 ». Le rapport dit en une phrase que le verdict a été atteint **sans aucune statistique hors
    échantillon**.
12. **Le fait que ce périmètre soit un parmi d'autres**, et que les planchers du balayage aient été re-choisis après
    avoir vu les résultats Binance (`p7_grids.py` le documente **[v]**). → **renoncement non corrigé**, écrit à côté
    du résultat de multiplicité.
13. **Un Sharpe dégonflé analytique.** scipy absent, installation interdite ; et il testerait le Sharpe **propre**
    de la config, une autre hypothèse que celle posée ici, où le Sharpe n'est de toute façon pas décisionnel.

---

## § K. Attendu déclaré, clause de clôture, découverte annexe

### K.1 Attendu déclaré, avant le run

> Une config post-C2 connue capture **~3 % du mouvement de l'actif**. Si c'est représentatif, **le plancher de 6 %
> ne sera pas franchi** et ce chantier produira un **négatif propre et pré-spécifié** — c'est un **bon résultat**,
> pas un échec.

Le déclarer avant interdit de le renégocier après.

### K.2 Clause de clôture

> Si le verdict est `dépriorisation`, **le cas est clos par ce rejeu**. Toute reprise de la famille grid exige un
> **mécanisme nouveau** au sens du § 5 de `CONTRAINTES_POST_B4.md`, passant par le ticket d'entrée § 6 — **pas un
> nouveau balayage, pas un périmètre élargi « pour vérifier »**.

### K.3 Découverte annexe — à signaler, pas à traiter

Le § 4 de `docs/CONTRAINTES_POST_B4.md` affirme que le Sharpe 2+ du benchmark DCA est « un artefact de courbe
majoritairement cash ». **La formulation est imprécise** et en partie traçable au défaut **D6** (dépôts comptés
comme rendements), corrigé en C1. Consigné au rapport ; la correction du document relève d'un autre passage.

---

## § L. Artefacts et ordre d'exécution

Tous sous `results/rejeu_grid_20260919/`. **Aucun pas n'est sauté ni réordonné.**

| Étape | Producteur | Artefact | Quand |
|---|---|---|---|
| 0 | — | les 9 scripts `scripts/audit/rejeu_*.py` **écrits et testés** | avant tout |
| 1 | `rejeu_data_coverage.py` | `data_coverage.json` (§ D) | avant la campagne |
| 2 | `rejeu_benchmark.py` | `benchmark.json` (§ E) | avant la campagne |
| 3 | `rejeu_effect.py --calibrate` | `calibration.json` (§ F.5 + équivalence MDD) | avant la campagne |
| 4 | — | entrée `docs/RESEARCH_LOG.md` | **avant le lancement** (décision 17) |
| 5 | `run_p7_grid_search.py` | `P7_phase1_grid.json` (96 entrées), `attempts/` | la campagne |
| 6 | `rejeu_validate_campaign.py` | `validation_campaign.json` — **exit 0 exigé** | après |
| 7 | `rejeu_signatures.py` | `signatures.json` (§ A) | après |
| 8 | `rejeu_spacing_clamp.py` | `clamp.json` (§ B) | après |
| 9 | `rejeu_effect.py` | `effect.json` (§ C, § F) | après |
| 10 | `rejeu_validate_analysis.py` | `validation_analysis.json` (§ I-B) | après |
| 11 | `rejeu_verdict.py` | `verdict.json` + **la chaîne de verdict** (§ G, § H) | après |
| 12 | — | `results/rejeu_grid_report.md` | gate 2 |

`rejeu_verdict.py` **n'a aucun paramètre libre et aucune entrée humaine** : deux personnes l'exécutant sur les mêmes
artefacts obtiennent **la même chaîne**. C'est le contrat de falsifiabilité de ce document. **Le rapport cite la
chaîne**, il ne la paraphrase pas.

Les mots `selected_for_paper`, « sélection », « déployable » et « production » ne sont pas des issues de ce run.
Les découvertes annexes sont **signalées, jamais traitées**.
