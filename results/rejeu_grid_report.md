# Rejeu diagnostic grid — rapport (gate 2)

> Brief : `agent/rejeu_diagnostic_grid_v2.md` · Plan approuvé le 2026-09-20 ·
> Branche `feat/rejeu-grid-diag` depuis `dev` @ tag `v2.10.0-c2-replay` (`9897803`).
> **Pré-spécification gelée** : `docs/rejeu_grid_prespec.md` (commit `4ecd985`, sha256 `20079aff60a55152`,
> amendée en `aa17ed0` sur deux corrections d'implémentation consignées au § A.1 — aucun seuil, aucune règle de
> décision, aucun périmètre déplacé).
> **État** : clos au gate 2 — verdict **`inconclusif (F_CANNOT_SEPARATE)`**, émis par `rejeu_verdict.py`.

---

## 0. Ce que ce rejeu peut et ne peut pas dire

Une seule question : la famille grid, **dans ce périmètre gelé**, mérite-t-elle un travail supplémentaire
(`candidat`), est-elle `dépriorisée`, ou le rejeu est-il `inconclusif` ? **Le rejeu ne sélectionne rien** : toute
sélection relève du protocole C3, qui n'existe pas. `candidat` ne signifie jamais « déployable ».

Le verdict est celui qu'émet `scripts/audit/rejeu_verdict.py`, script sans paramètre libre ni entrée humaine : deux
personnes l'exécutant sur les mêmes artefacts obtiennent la même chaîne. **Ce rapport cite la chaîne**, il ne la
paraphrase pas.

**Attendu déclaré avant le run (§ K.1 de la pré-spec)** : une config post-C2 connue capture ~3 % du mouvement de
l'actif ; si c'est représentatif, le plancher de 6 % ne sera pas franchi et ce chantier produit un **négatif propre
et pré-spécifié** — un bon résultat, pas un échec.

## 1. Périmètre et défauts de classe en vigueur

96 configs = `grok_grid_atr_adaptive_v4` × {BTC/USDC, SOL/USDC} × `GRID_ATR_GRID` inchangée
(`min_spacing_pct` [0.015, 0.020, 0.025, 0.030] × `atr_multiplier` [1.5, 2.0, 2.5, 3.0] ×
`bear_protection_mode` [none, 1w_only, 1d_only]). P7 **phase 1 uniquement** : ni phase 2 (walk-forward non
chronologique), ni `--report`, ni `--selection` (le rapport P7 émet `selected_for_paper`).

Période 2023-04-01 → 2026-04-01, données Binance end-stampées, modèle de fees **bybit**, coûts par paire
`config/pair_costs_b4.json` (BTC 2/2 bps, SOL 11/2 bps), `--min-order-usdc 5` (**inerte sur le moteur grid** : les
lots sont fixes ; valeur de provenance et de garde de reprise).

**Défauts de classe, dette 13 non fixée** : `grid_levels` 12, **`max_spacing_pct` 0.05 non balayé**, `atr_period`
14, `recalc_hours` 6 (cadence effective 8 h), `bias_1d` 0.2, `order_size_usdc` 25, `max_allocation_pct` 20.0
**jamais lu par le moteur**, capital 1000 USDC, `candle_interval` 5.

**Exposition maximale** : lots de 25 USDC, `max_allocation_pct` non appliqué, achats limités par le cash
disponible ; les lots ouverts survivent aux reconstructions de grille et de nouveaux achats peuvent être créés —
**l'exposition maximale n'est pas démontrée**, et aucun raisonnement de ce rapport ne s'appuie sur un plafond.

**Segments** : `all` (1097 points → 1096 rendements) est le **seul segment qu'un seuil lit**. `train` (769 → 768)
et `test` (330 → 329) sont descriptifs, jamais concaténés (768 + 329 = 1097 ≠ 1096), jamais comptés comme preuves
indépendantes. 96 × 3 = 288 simulations, **qui ne sont pas 288 observations**.

## 2. Mesures de pré-campagne (produites et committées avant le lancement)

### 2.1 Couverture réelle des données (§ D)

| Mesure | BTC/USDC | SOL/USDC |
|---|---|---|
| `days_5m` / `days_5m_complete` / `days_4h` | 1096 / 1096 / 1096 | 825 / 825 / 825 |
| `max_gap_days` | 0 | **271** |
| `first_covered_day` → `last_covered_day` | 2023-04-01 → 2026-03-31 | **2023-12-28** → 2026-03-31 |
| jours < 90 % / < 50 % de complétude | 0 / 0 | 272 / 271 |
| **admissible (les cinq clauses)** | **oui** | **non — les cinq échouent** |

825 jours = 75,2 % de la fenêtre = **27,1 mois**, contre les « 3+ ans » non négociables du § 7 des contraintes.
Conforme à l'attendu pré-enregistré : **la règle gelée s'applique telle quelle, sans re-soumission**.

**Deux écarts de prédiction, pas de règle**, consignés :
1. la pré-spec annonçait SOL « inadmissible sur quatre clauses sur cinq » ; la mesure en donne **cinq**
   (`first_covered_day` 2023-12-28 fait aussi échouer la clause `first_last`) ;
2. la pré-spec citait les deux bougies 1 w manquantes de BTC comme `2025-01-27` et `2025-02-24` (stamps
   **d'ouverture**) ; end-stampées, ce sont `2025-02-03` et `2025-03-03` — **les mêmes deux bougies**, exprimées
   dans l'autre convention. SOL en compte 41, dont 39 dans son trou.

### 2.2 Benchmark d'exposition reconstruit (§ E)

Bornes moteur `>= start` et `<= end` (ce qui **répare la dette 15(c)** de ce côté), entrée au close stampé à
l'ancre, **une liquidation terminale facturée comme le grid**, métriques par `krakenbot.backtest_metrics`.

| paire | constructible | comparable | `ff_days` | rendement | MaxDD quotidien | CAGR | Sharpe | σ quotidien |
|---|---|---|---|---|---|---|---|---|
| BTC/USDC | oui | oui | 0 | +138,28 % | 49,65 % | 33,5313 %/an | 0,8493 | 0,024595 |
| SOL/USDC | **non** | non | 271 | — | — | — | — | — |

SOL : première bougie quotidienne en fenêtre stampée `2023-12-29`, soit **272 jours après l'ancre** ; ré-ancrer à
une date ultérieure est interdit (dates communes, sans exception). C'est une **seconde route indépendante** vers
le même traitement que le § D : SOL est descriptif.

Descripteurs historiques (`results/C1_benchmarks_v2.json`, **descriptifs, jamais un seuil**) : BTC Sharpe 0,8470,
rendement +137,51 %, MaxDD 49,65 % sur 1096 rendements. Les écarts du reconstruit (+0,0023 de Sharpe, +0,77 pp de
rendement, MaxDD identique) sont exactement ce que produisent la borne `<= end` réparée, l'entrée au close plutôt
qu'à l'open, et la liquidation terminale que le benchmark historique ne facturait pas.

### 2.3 Résolution pré-enregistrée et équivalence du MaxDD vectorisé (§ F.5)

Sur la seule courbe d'equity grid post-C2 existante (`results/c2_replay/P6_grid_rerun.json`, BTC, défauts de
classe, `atr_multiplier` 4.0 — **quasi-membre** de la famille balayée : `min_spacing_pct` 0.015 est le minimum
balayé et `bear_protection_mode` nul laisse `pause_1w_strong_bear = True`, soit le bras `1w_only` ; seul le
multiplicateur 4.0 est hors balayage ; **aucun seuil n'en est dérivé**) :

- observé : CAGR 1,5000 %/an, σ quotidien 0,000845, `nnz` 388/1096, λ_dd 0,010, λ_σ 0,014,
  **Δ_dd +1,0416 pp/an**, **Δ_σ +0,8594 pp/an** ;
- **SE mono-config de Δ** (bootstrap par blocs, B = 10 000) : dd 0,976 / 0,979 / 1,002 et σ 0,872 / 0,886 / 0,924
  pour L = 10 / 21 / 42. *Aucune extrapolation au quantile FWE n'est écrite : le SE d'une courbe seule ne
  renseigne ni sur le maximum sur 48 essais, ni sur ce que le design pourra détecter.*
- **MaxDD vectorisé vérifié** contre la routine Decimal sur **1003 courbes** : résidu relatif maximal
  **1,57e-14** (seuil 1e-9), 181× plus rapide. La ré-estimation de λ dans le bootstrap est donc **activée**.
- **Coût mesuré de la ré-estimation** : 145,6 / 118,7 / 116,9 s par L, contre un budget déclaré de **7 200 s par
  combinaison (L, appariement)** → `lambda_mode = reestimated`, et `candidat` reste atteignable.

## 3. La campagne et sa validité (§ I-A)

96 jobs lancés le 2026-09-20 à **10:52:58 UTC** au SHA `0120ce8`, terminés à **11:50:20 UTC** :
**96 réussis, 0 échec, 57,4 min**, 3 workers, `nice -n 10`, très en deçà de la limite murale externe de 6 h
déclarée avant le run. Aucune reprise n'a été nécessaire, donc aucune erreur à classer.

Les **quinze assertions** de la validité de campagne passent, dans l'ordre gelé — et l'ordre compte :
`collect_flags` saute silencieusement toute entrée portant `"error"` et `flag_segment` renvoie `[]` sur un bloc
`liquidation` absent, donc « `b4_flags` est muet » n'est un résultat qu'**après** I-A.1 à I-A.12.

| Assertion | Résultat |
|---|---|
| I-A.1 présence, aucune sortie de sélection à côté | ok — 7 fichiers dans le répertoire, aucun `*selection*.json` ni `*report*.md` |
| I-A.2 96 entrées, jeu de clés **reconstruit en script** | ok — 96 clés rebâties par `expand_grid(GRID_ATR_GRID)` × `make_key` |
| I-A.3 aucune entrée `"error"` | ok — 96 entrées nommées et comptées **en premier** |
| I-A.4 22 clés top-level | ok |
| I-A.5 périmètre gelé (exchange, fees, coûts, versions) | ok — `spread_pct`/`slippage_pct` assertés seulement si `positions > 0`, exigés `null` sinon |
| I-A.6 période et split **recalculé** | ok — split 2025-05-07T04:48:00+00:00 |
| I-A.7 `params` et `effective_params` | ok — Decimal comparés via `Decimal(str(value))` ; `source` jamais asserté ; `bear_protection_1d_enabled` non exporté donc non asserté |
| I-A.8 blocs présents et conformes | ok — un bloc `warmup` partagé par les 48 configs de chaque paire |
| I-A.9 grilles 1097 / 769 / 330, ancrées à 1000 | ok |
| I-A.10 24 clés + **auto-test d'instrument** | ok — Sharpe / Sortino / MaxDD / rendements définis recalculés depuis l'equity exportée, tolérance 1e-6 ; `cagr_pct` **comparé à aucun champ**, son seul recoupement admis (`calmar × MaxDD`) a tourné sur **288 segments, sauté sur 0** |
| I-A.11 identités comptables par segment | ok — **aucune assertion « ≈ 0 »** : `unrealized_pnl` **est** `liquidation.pnl` |
| I-A.12 réconciliation de liquidation, explicite | ok — 288 blocs réconciliés, tolérances `b4_flags` appliquées **après** la preuve de présence |
| I-A.13 `b4_flags` muet + `flag_segment` ré-appliqué | ok — muet, et ré-application indépendante sur les **288** couples (entrée, segment) |
| I-A.14 intégrité de l'instrument | ok — diff code **vide** contre `9897803`, diff `tests` = les 7 fichiers de la liste close, arbre propre, empreintes consignées |
| I-A.15 artefacts de pré-campagne antérieurs à la campagne | ok |

**Verdict de validité : EXPLOITABLE** (exit 0, aucune assertion en échec).
Compteurs de rejets : **zéro sur les sept causes**, sur les 96 configs et les trois segments.

**Correctif du validateur, postérieur à la campagne.** `rejeu_validate_campaign.py` acceptait un sous-bloc
**présent mais `null`** (`liquidation.all = null`, et de même pour `warmup` et `rejections`) : le contrôle parent
porte sur le jeu de clés, correct sur `{"train": {...}, "test": {...}, "all": None}`, et les assertions suivantes
sautent un segment non-dict — le faux vert exact que ce contrôle existe pour attraper. Corrigé (commit `5a443da`),
avec huit tests négatifs paramétrés (quatre blocs × {null, absent}) et une ligne de doctrine dans
`skills/backtest.md`. **Les artefacts livrés ne contiennent aucun sous-bloc null** : re-validés avec le validateur
corrigé, ils redonnent **EXPLOITABLE, exit 0, aucun échec**
(`validation_campaign_revalidated.json`). Le verdict n'est pas remis en cause.

La **validité des analyses** (§ I-B) passe elle aussi : sept assertions sur sept, dont la reproductibilité
**bit à bit** des `LB_j` — `effect.json` et un second passage complet, indépendant, sont **identiques champ par
champ** hors horodatage, sur les 96 blocs `LB` comparés.

## 4. Classes d'indiscernabilité (§ A) — descriptif

| paire | configs | classes exactes | classes tolérantes |
|---|---|---|---|
| BTC/USDC | 48 | **48** | 48 |
| SOL/USDC | 48 | **23** | 23 |

La partition tolérante est **identique** à la partition exacte : aucune classe ne tient à la dernière décimale.

**Lecture rétroactive B4** (`results/B4_P7_phase1_cross_validate.json`, champs conservés) : BTC 48 → **45**,
SOL 48 → **48** — les deux **en accord** avec la référence pré-enregistrée au § A.3 avant le run.

> L'égalité de signature est une **indiscernabilité sur les sorties exportées**. Le journal des transactions n'est
> pas exporté : ce n'est jamais une preuve d'identité des ordres, ni une preuve que le clamp a saturé.

Sous l'instrument réparé, **BTC se distingue entièrement** (48/48) alors que **SOL s'effondre à 23 classes**. Les
premières différences entre classes voisines de SOL tombent presque toutes dans `$.equity_daily.all[...]` autour
des indices 277–434, c'est-à-dire **après** la fin du trou de données SOL (indice 272 ≈ 2023-12-28) : les classes
SOL se séparent là où la paire recommence à avoir des données.

## 5. Mesure directe du clamp (§ B) — distributionnelle, ne déplace aucun verdict

> Mesure **distributionnelle, pas un rejeu** : l'amorçage diffère de celui du moteur et **aucune des deux paires ne
> reproduit l'état ATR réalisé du moteur**.

Fraction des clôtures 4 h par classe de clamp (fenêtre entière ; BTC 6 576 clôtures, SOL 4 935) :

| | m = 1.5 | m = 2.0 | m = 2.5 | m = 3.0 |
|---|---|---|---|---|
| **BTC — au plafond** | 0,36 % | 4,55 % | 11,24 % | 21,61 % |
| **BTC — à l'intérieur** (plancher 1,5 %) | 78,60 % | 90,75 % | 87,53 % | 78,13 % |
| **SOL — au plafond** | 17,87 % | 48,96 % | **82,43 %** | **95,02 %** |
| **SOL — à l'intérieur** (plancher 1,5 %) | 82,13 % | 51,04 % | 17,57 % | 4,98 % |

**C'est le constat que le brief demandait**, et il transforme l'hypothèse en fait mesuré — en la **restreignant à
une paire**. Sur BTC, l'espacement reste très majoritairement **à l'intérieur** de la bande : les deux axes balayés
restent vivants, ce qui explique les 48 classes distinctes. Sur SOL, le plafond de 5 % mord sur 82 % puis 95 % des
clôtures à m = 2,5 et 3,0 et le plancher ne mord quasi jamais : au-delà de m = 2,5 l'espacement est **épinglé à
5 %** quel que soit le plancher, l'axe `min_spacing_pct` devient inerte, d'où les 23 classes.

La mesure annexe de quantification (pas de 0,1 USD ≥ 10 % de `spacing × close`) est **nulle sur les deux paires** :
la quantification n'explique aucune fusion de classes, y compris sur SOL.

## 6. Couverture en cycles achevés (§ C)

`cycles = all.total_trades − liquidation.all.positions`, sur le segment `all` :

| paire | min | médiane | max | **≥ 25 cycles** |
|---|---|---|---|---|
| BTC/USDC | 77 | 144,5 | 483 | **48 / 48** |
| SOL/USDC | 168 | 230 | 415 | **48 / 48** |

**Le filtre de couverture n'a tronqué aucune config.** La crainte écrite au § C.2 — qu'un seuil plus haut ampute
de façon non aléatoire la moitié « large » du balayage — ne s'est pas matérialisée : même le minimum (77 cycles sur
BTC) est trois fois au-dessus du seuil, et un seuil à 30 aurait produit exactement la même table. Consigné comme
tel : le choix de 25 plutôt que 30 **n'a rien changé** à ce rejeu.

Rappel inscrit avec le seuil : 25 cycles est un **filtre d'admissibilité minimal, pas une taille d'échantillon** ;
les cycles d'une grille dans une même tendance sont fortement corrélés. Toute l'inférence tourne sur les
1 096 rendements quotidiens, jamais sur le compte de cycles.

Les liquidations terminales restent **dans l'économique** (`net_pnl` est le cash réalisé après la vente MARKET) et
sont rapportées séparément ; aucun chiffre de ce rapport n'est restitué « hors liquidation ».

## 7. Admissibilité et warmup (§ D)

`warmup[all]`, identique sur les 48 configs de chaque paire (asserté par I-A.8) :

| paire | 4 h | 1 d | 1 w | classe |
|---|---|---|---|---|
| BTC/USDC | required 14, loaded 91, stale 0, gap 0 → **suffisant** | loaded 88 ≥ 50, stale 0, **gap 163** | loaded 50, `extended_by` 19, stale 0, **gap 23** | **W1** |
| SOL/USDC | **loaded 0**, stale `None` | loaded 68, **stale 183** | loaded 50, `extended_by` 21, **stale 25**, gap 1 | **W2** |

Exactement les classes pré-enregistrées. SOL est donc traité en descriptif par **trois routes indépendantes** :
inadmissible au § D.2 (cinq clauses), benchmark non constructible au § E.2, et warmup W2 ici.

> Le warmup 1 d/1 w de BTC est `sufficient=False` par `largest_gap_candles` 163 / 23 : les EMA20/50 qui alimentent
> `get_regime` ont été amorcées **à travers** le trou pré-fenêtre de 164 jours. `bias_1d` faisant vivre `regime_1d`
> dans **tous** les modes, **tout** résultat de cette paire — quel que soit `bear_protection_mode` — repose sur une
> porte dont l'amorçage n'est pas propre ; le réexaminer est une **entrée obligatoire de C3**.

## 8. Effet, gates ponctuels et borne d'incertitude (§ E.3, § F)

### 8.1 Les comparateurs appariés

Blend **statique** `NAV_λ(t) = (1 − λ)·1000 + λ·NAV_bh(t)` — allocation initiale, **jamais rééquilibrée** — avec
exactement les coûts du benchmark reconstruit et une liquidation terminale sur la jambe actif. Les deux λ sont
trouvés **par recherche** sur les NAV réellement construites, jamais par un rapport de volatilités (dans un blend
statique le poids de l'actif dérive avec le prix, donc les rendements du portefeuille ne sont pas `λ·r_bh`).

Sur les 48 configs BTC : **λ_dd de 0,015 à 0,082**, λ_σ du même ordre, **un seul croisement** sur la grille pour
chaque config (la monotonie est prouvée pour l'appariement drawdown, comptée pour l'appariement volatilité), et des
résidus d'appariement de 0,2 % à 2,6 % — tous **sous le seuil de 10 %**, donc aucun appariement n'est étiqueté
approximatif. **12 configs sur 48 ont `λ_dd < 0,02`** et portent donc le paragraphe verbatim du § E.3 :

> Le comparateur apparié détient moins de 2 % du capital dans l'actif ; la comparaison porte sur l'efficience à très
> petit budget de risque, pas sur une allocation alternative réaliste. Ce qui empêche un effet absolu trivialement
> petit de fonder un verdict est le plancher G2, pas cette comparaison.

**L'appariement sur le drawdown (ou la volatilité) observé est une comparaison rétrospective, jamais une allocation
validée pour l'avenir.**

### 8.2 Les gates ponctuels décisionnels

Sur BTC/USDC, évalués sur **chaque** config éligible (48/48 éligibles : paire admissible, warmup W1, benchmark
comparable, cycles ≥ 25, `nnz` ≥ 110, Δ calculable) :

| gate | contenu | résultat |
|---|---|---|
| G1 | `net_pnl(all) > 0` | **48 / 48** |
| G2 | `total_return_pct(all) ≥ 6,0 %` | **18 / 48** |
| G4 | `Δ_dd > 0` **et** `Δ_σ > 0` | **31 / 48** |
| **G1 ∧ G2 ∧ G4** | | **16 / 48** |

Premier gate en échec : **G2 pour 30 configs sur 48**, G4 pour 2, aucun pour les 16 restantes. Le plancher
économique est donc le gate ponctuel le plus mordant — un constat **mesuré après coup**, que la
pré-spécification interdisait explicitement d'annoncer d'avance à partir du SE de calibration. Il ne faut pas le
confondre avec ce qui décide du verdict : ce sont les six bornes simultanées, qu'aucune config ne tient.

**Recoupement indépendant.** Les 48 λ et les 48 Δ ont été recalculés hors du script, directement depuis
`P7_phase1_grid.json` et `benchmark.json` : **λ identiques sur les 48 configs** (à l'unité de grille près) et
**écart maximal de 2,2e-14 pp/an sur Δ_dd comme sur Δ_σ**. Les mêmes 16 configs passent les trois gates.

G3 (`net_pnl ≥ 10 × total_fees`) est **descriptif** : le ratio va de 1,8 à 11,2 et **8 configs sur 48** seulement le
franchissent. Il n'entre dans aucun verdict ; sa limite est imprimée avec lui — il borne une mauvaise spécification
du **coût par fill**, pas de la **probabilité de fill**.

### 8.3 La borne d'incertitude

Bootstrap par blocs circulaires, N = 1096, **B = 10 000**, L ∈ {10, 21, 42}, graines dérivées de
`[20260919, pair_index, L]`, indices **appariés** config ↔ benchmark, **λ ré-estimé dans chaque réplication**
(`lambda_mode = reestimated` — l'équivalence du MaxDD vectorisé avait été vérifiée avant la campagne à 1,57e-14 et
le coût mesuré, 117–149 s par longueur de bloc, tenait largement dans le budget déclaré de 7 200 s). Correction
simultanée mono-étape sur les **48 courbes calculables** : `V*_b = max_j (Δ*_{b,j} − Δ̂_j)`,
`q_FWE = quantile(V*, 0,95)`, `LB_j = Δ̂_j − q_FWE` pour **chaque** j.

| | L = 10 | L = 21 | L = 42 |
|---|---|---|---|
| `q_FWE` appariement drawdown | 5,924 | 6,164 | 6,247 |
| `q_FWE` appariement volatilité | 4,942 | 5,148 | 5,417 |

Les quatre meilleures configs par Δ̂_dd parmi celles qui passent les trois gates :

| plancher / m / mode | rendement | cycles | λ_dd | Δ_dd | Δ_σ | `se` (L=21) | `LB` min sur les six |
|---|---|---|---|---|---|---|---|
| 0,025 / 1,5 / none | 10,320 % | 265 | 0,031 | **+1,917** | +1,560 | 2,708 | **−4,330** |
| 0,025 / 1,5 / 1w_only | 8,598 % | 230 | 0,031 | +1,377 | +1,020 | 2,856 | −4,870 |
| 0,015 / 2,5 / none | 6,844 % | 143 | 0,019 | +1,362 | +1,181 | 1,574 | −4,885 |
| 0,020 / 2,5 / none | 6,708 % | 138 | 0,019 | +1,318 | +1,138 | 1,577 | −4,929 |

**Aucune des 48 configs ne tient `LB_j > 0`, dans aucune des six combinaisons.**

Trois lectures obligatoires, écrites ici parce qu'elles pèsent sur l'interprétation :

1. **Les erreurs-types sont élevées relativement aux effets observés.** Le meilleur Δ̂ (+1,92 pp/an) est inférieur
   à son propre `se` mono-config (2,56 à 2,79 selon L). **La procédure pré-spécifiée ne sépare aucun effet de
   zéro.** La **contribution propre de la correction de multiplicité n'a pas été isolée** : Δ̂ < `se` ne démontre
   pas qu'un test sans correction échouerait, en particulier sous une distribution asymétrique à queues lourdes
   (kurtosis mesurée 98,9 sur la courbe de référence), et aucune analyse supplémentaire n'a été conduite après les
   résultats pour l'établir.
2. **Les `q_FWE` d'environ 6 pp/an sont les seuils critiques observés de cette procédure**, sur cette fenêtre, avec
   ces 48 essais et ces courbes — **pas une limite générale de détection**. La pré-spécification interdisait
   d'écrire d'avance une borne de ce type à partir du SE mono-config de la calibration ; elle n'autorise pas
   davantage à la transformer après coup en propriété du problème.
3. **La correction est conservatrice pour les petites échelles.** `max se / min se` sur les 48 configs vaut
   **5,35 > 3** : le max-T non studentisé pénalise davantage les configs de faible volatilité que les autres. C'est
   le renoncement annoncé au § F.4, ici mesuré.

Éléments rapportés, décisionnels nulle part : `se` par config ; **jackknife de queue** — sur la meilleure config,
Δ̂_dd passe de +1,917 à **+2,068** sous suppression **conjointe** du plus grand et du plus petit log-rendement
quotidien. La valeur est rapportée telle quelle : une suppression conjointe ne permet pas de conclure sur la
dépendance à une date unique, les deux contributions pouvant se compenser, et aucune analyse leave-one-out n'a été
ajoutée après les résultats ; β̂ de 0,040 à 0,067 (faible chargement sur le benchmark) ;
**zéro réplication dégénérée** sur les 48 configs et les 10 000 réplications. Aucun intervalle de confiance par
configuration n'est publié comme intervalle d'inférence.

Les 48 configs BTC sont **ÉLIGIBLES** : aucune n'est écartée pour couverture, activité ou calculabilité.
Côté SOL, les 48 sont **DESCRIPTIF** et **aucun Δ n'est publié** — la règle « on ne calcule pas quand même
pour commenter le chiffre » est appliquée à la lettre.

### 8.4 SOL/USDC

`|J_calc| = 0`, aucune config éligible, `not_estimable = true`, raison `D_NOT_ADMISSIBLE` : le bootstrap **n'a pas
été lancé** pour cette paire. Ses métriques brutes sont dans les artefacts et rapportées comme descriptives —
elles sont d'ailleurs, en apparence, les meilleures des deux paires (48/48 au-dessus de 6 %, médiane +11,1 %). La
paire qui affiche les plus beaux chiffres est exactement celle que la règle de qualité de données, gelée **avant**
de les voir, écarte. C'est le meilleur argument en faveur de l'ordre dans lequel ce chantier a été conduit.

## 9. Verdict

Émis par `scripts/audit/rejeu_verdict.py`, qui ne consomme que les artefacts gelés, n'a **aucun paramètre libre ni
entrée humaine**, et produit la même chaîne pour quiconque l'exécute sur les mêmes fichiers. La voici, **citée, non
paraphrasée** :

```
REJEU_GRID_20260919 | famille=inconclusif | raison=F_CANNOT_SEPARATE | BTC/USDC=inconclusif | SOL/USDC=descriptif | representant=- | prespec=20079aff60a55152 | campagne=08d981e493402f37
```

### 9.1 Le chemin exact dans la règle gelée

| étape (§ G.3) | BTC/USDC | SOL/USDC |
|---|---|---|
| paire admissible ? warmup ? | admissible, **W1** | **inadmissible**, **W2** → `descriptif` |
| benchmark comparable ? | oui | **non** (non constructible) |
| `J` = configs éligibles | **48** | 0 |
| `G` = passent G1 ∧ G2 ∧ G4 | **16** | — |
| `C` = **la même** config passe les gates **et** tient les six bornes | **0** | — |
| verdict de paire | **`inconclusif (F_CANNOT_SEPARATE)`** | `descriptif` (ne vote pas) |

**Le verdict de famille est celui de BTC/USDC**, seule paire votante : `inconclusif`, raison
`F_CANNOT_SEPARATE`. Aucun représentant n'est nommé, puisque `C` est vide.

La branche empruntée est précise. Sur BTC, `J ≠ ∅` (48 configs éligibles) et **16 passent G1 ∧ G2 ∧ G4** : la
clause « aucune config éligible ne passe les gates » — celle qui mène à `dépriorisation` — **n'est pas
satisfaite**. Mais `C` est vide : aucune de ces 16 ne tient `LB_j > 0` dans les six combinaisons. Le dernier
`sinon` de la règle s'applique, et il donne `inconclusif (F_CANNOT_SEPARATE)`.

### 9.2 Ce que ce verdict n'est pas

- Ce n'est **pas** une `dépriorisation`. La règle gelée distingue explicitement les deux cas, et le placement est
  délibéré : une estimation **en échec sur les gates ponctuels** vaut `dépriorisation` ; une estimation
  **positive qui échoue à la borne** vaut `inconclusif`, jamais `dépriorisation` — *l'absence de significativité
  n'est pas une preuve d'absence*. Ici 16 configs passent les gates ponctuels : la famille n'a pas échoué sur les
  faits ponctuels du chemin réalisé, elle n'a pas été **séparée du bruit**.
- Ce n'est **pas** un `candidat`, et rien n'est sélectionné.
- Conséquence gelée, verbatim : **pas de déploiement et pas de tuning supplémentaire** ; la raison est écrite, et
  **le périmètre n'est pas élargi pour chercher une autre réponse**. En particulier, la mesure du clamp montrant
  que le plafond de 5 % sature sur SOL n'autorise **pas** à rejouer avec un `max_spacing_pct` plus haut : la
  pré-spécification a fermé cette porte d'avance, et un périmètre qui se révèle mal choisi est un **résultat**.
- La **clause de clôture** du § K.2 ne s'applique pas : elle ne vaut que pour une `dépriorisation`. La famille grid
  n'est donc ni relancée ni close par ce rejeu ; elle reste où le § 5 la laisse, et ce qui manque pour trancher est
  nommé en § 9.3.

### 9.3 Ce qu'il faudrait pour trancher

Non pas un balayage plus large — il est explicitement exclu — mais les trois choses que ce rejeu a mesurées comme
manquantes :

1. **De la précision.** Les seuils critiques observés de cette procédure valent environ **6 pp/an** (appariement
   drawdown) pour un meilleur effet de **+1,9 pp/an**, lui-même sous son propre `se` mono-config. Sur cette
   fenêtre et avec ces courbes, les erreurs-types sont élevées relativement aux effets observés ; ce constat porte
   sur la procédure pré-spécifiée, pas sur ce qu'une autre méthode pourrait ou ne pourrait pas établir.
2. **De l'equity continue et une sélection chronologique** — c'est le protocole C3, et il reste un prérequis.
3. **Un amorçage propre des portes de régime** : le warmup 1 d/1 w de BTC est `sufficient=False` par lacune interne
   (163 et 23 bougies), et `bias_1d` fait vivre `regime_1d` dans **tous** les modes, donc **tout** résultat BTC de
   ce rejeu repose sur une porte mal amorcée. C'est une entrée obligatoire de C3.

## 10. Portée, ce que la règle gelée a coûté, renoncements

### 10.1 Effet observé des choix de pré-spécification

Consigné sans jugement de valeur : ce que la règle gelée a produit, et ce qu'une autre règle aurait produit sur
**les mêmes artefacts**, toutes les autres règles inchangées.

**G3.** Son ajout comme gate obligatoire, toutes les autres règles inchangées, aurait laissé **zéro configuration
passant les gates ponctuels** et conduit à `dépriorisation`. Vérifié sur les artefacts : **aucune des 8 configs qui
franchissent `net_pnl ≥ 10 × total_fees` n'est parmi les 16 qui passent G1 ∧ G2 ∧ G4** — l'intersection est vide,
les 8 portent toutes `atr_multiplier` 3,0 et échouent toutes d'abord sur G2. Son maintien descriptif a donc
effectivement changé le verdict.

**Sharpe.** Une configuration dépasse ponctuellement le B&H, **0,855 contre 0,8493**. Cela aurait satisfait le
critère de comparaison du § 4, mais ne suffit pas à établir un verdict `candidat` : aucune configuration ne
satisfait les six bornes exigées.

**Couverture.** Choisir 25 plutôt que 30 cycles n'a eu **aucun effet** ; le minimum observé est **77**.

### 10.2 L'attendu déclaré est partiellement falsifié — consigné comme tel

Le § K.1 déclarait avant le run : « une config post-C2 connue capture ~3 % du mouvement de l'actif ; si c'est
représentatif, le plancher de 6 % ne sera pas franchi ». **Ce n'est pas représentatif** : la référence portait
`atr_multiplier` 4,0, **hors balayage**, et **18 configs BTC sur 48 franchissent le plancher de 6 %** (jusqu'à
10,32 %), de même que les 48 configs SOL. L'attendu est donc falsifié sur le franchissement du plancher. Il est
consigné ici sans être renégocié : c'est précisément pour pouvoir écrire cette phrase qu'il avait été déclaré
avant.

### 10.3 Ce que ce rejeu ne peut pas dire

- **Aucune statistique hors échantillon.** Le verdict repose entièrement sur le segment `all` ; `train` et `test`
  n'ont voté nulle part, et le walk-forward de la phase 2 n'est pas chronologique. C'est C3.
- **Le périmètre est un parmi d'autres, et il a été choisi après avoir vu des résultats.** Les planchers du balayage
  ont été re-choisis à la lumière de la campagne Binance (`p7_grids.py` le documente : « 1.0 % dropped, 1.5 % kept
  as the Binance-calibration witness, 3.0 % added »). La multiplicité réelle dépasse donc les 48 corrigés.
  **Renoncement non corrigé**, écrit ici à côté du résultat de multiplicité.
- **File d'attente, non-exécutions, fills partiels, sélection adverse** ne sont pas modélisés et leur amplitude est
  **inconnue**. Tout résultat est conditionnel au modèle de remplissage au toucher. Aucun substitut chiffré n'est
  proposé : G3 est descriptif et sa limite est imprimée avec lui.
- **`rf = 0` est une convention.** Le blend détient `(1 − λ)` en cash et la config une fraction cash différente,
  variable et **non exportée** ; aucune ligne de sensibilité `rf > 0` n'est publiée, faute d'historique de cash côté
  grid. On connaît l'allocation du **comparateur** (λ entre 0,015 et 0,082, donc très majoritairement en cash) ; on ne
  connaît **pas** celle de la configuration — le λ apparié ne mesure pas le cash du grid, qui n'est pas exporté et
  que le § J de la pré-spécification déclare non mesurable. Un `rf > 0` déplacerait donc Δ d'une quantité non
  quantifiable ici.
- **L'exposition n'est pas mesurée.** Ni cash, ni inventaire, ni notionnel ne sont exportés ; la voie « ~3 ans
  d'equity à exposition non triviale » du § 8 a été écartée d'avance pour cette raison, et la mesure le confirme :
  sur SOL, la NAV est **plate sur les 277 premiers jours** (le trou de données, forward-fillé sans marqueur) et
  `n_daily_returns` vaut quand même 1096 — 277 de ces rendements sont des zéros fabriqués.
- **Le verdict de famille repose sur une seule paire.** BTC/USDC est la seule votante ; SOL/USDC est descriptive.
  **ETH/USDC est hors du périmètre de ce diagnostic** (comme en P7) : celui-ci ne permet **aucune conclusion de
  candidature ni de dépriorisation** pour cette paire. Le rejeu de référence C2
  (`results/c2_replay/P6_grid_rerun.json`, un seul jeu de paramètres par paire) **ne remplace pas un balayage** et
  ne comble pas ce trou.
- **La dégénérescence réduit l'information sur les paramètres, pas la lisibilité du résultat.** Elle ne change
  aucun verdict (§ G.5), et elle est ici **spécifique à SOL** : 23 classes contre 48 sur BTC.

## 11. Innocuité du serveur

Campagne et analyses exécutées dans un **checkout isolé** `~/rejeu-grid/repo` (clone en HEAD détaché sur le SHA
testé, `.venv` local via `POETRY_VIRTUALENVS_IN_PROJECT=true`, `.env` **copié** depuis l'arbre du service et jamais
modifié, base en accès **local**, aucun tunnel). **Jamais l'arbre du service ni son virtualenv** : vérifié avant et
après, `~/apps/kraken-trading-bot` reste sur `dev` avec un arbre propre. Aucun merge, aucun déploiement, aucun
`systemctl`, aucune modification du `.env` serveur, aucun `workflow_dispatch`. La session tmux `spread` n'a pas été
touchée ; la campagne a tourné dans une session `rejeu` créée pour elle.

| Contrôle | Avant | Après |
|---|---|---|
| `krakenbot-collector` | actif | **actif** |
| `NRestarts` | 0 | **0** |
| RAM disponible | 5,8 Gi | 5,8 Gi |
| Disque libre | 55 G | 55 G |
| Continuité 1 m Bybit sur la fenêtre du run | — | **59 lignes par paire, 0 trou, écart max 1,00 min** |

Un seul événement de watchdog dans la fenêtre : `bybit_ws_resubscribed` à 11:49:31 (24 topics en 3 requêtes),
action normale du watchdog, **sans trou associé** — la continuité 1 m est intacte sur les trois paires.

**Migration Alembic** : `SELECT version_num FROM alembic_version` renvoie `c1ae7a1c0001` — la migration **est
appliquée** sur le serveur. C'est signalé (et non traité) parce que `PROJECT_CONTEXT.md` § 5 et la dette 15(a) la
disent « serveur en attente ». Elle ne conditionnait pas la campagne : les runners écrivent du JSON, pas la DB.
