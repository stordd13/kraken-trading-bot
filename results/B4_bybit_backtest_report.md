# B4 — Rapport de backtest Bybit (fees maker/taker, données saines, moteur grid honnête) et sélection paper

## ⚠️ Addendum du 16 septembre 2026 — portée des conclusions après audit de l'instrument

Un audit adversarial externe (`results/red_team_b4_20260916/RAPPORT_RED_TEAM_B4.md`), dont les
constats principaux ont été vérifiés indépendamment sur le code du tag `v2.8.0-b4-3-campaign` et
reproduits depuis les JSON de cette campagne, a établi que l'instrument de mesure utilisé par ce
rapport comporte des défauts matériels : annualisation des Sharpe/Sortino sur des pas de temps
hétérogènes (√365 appliqué à des rendements 5 m / 4 h / 1 j selon la famille), MaxDD rapporté au pic
global final au lieu du pic courant, profit factor sans imputation de la fee d'achat, agrégation P7
transformant les PF infinis en 0 puis moyennant des ratios, walk-forward dont les candidats sont
sélectionnés sur une période chevauchant les fenêtres dites OOS, benchmark DCA comptant les dépôts
comme des rendements. Le replay grid a par ailleurs alimenté les indicateurs 4 h avec des bougies
5 m. La branche de renforcement « oversold » du DCA était inactive pendant les tests trimestriels,
faute d'EMA200 prête ; par ailleurs, les configurations retenues (`bull_reduction=0.3`) réduisent
l'achat de 15 USDC à 4,50 USDC en régime strong_bull, provoquant son rejet sous le minimum de
5 USDC — la contribution exacte de ces rejets aux fenêtres sans achat n'est pas établie par les
résultats archivés.

**Ce qui reste établi** : les fees Bybit mesurées sur le compte ; les coûts par paire du GATE B en
tant que calibration ; les comptes d'exécutions enregistrées par le simulateur, avec leurs anomalies
documentées (dette 14 : doubles ventes de lots grid × SOL) ; l'identité comptable
`net_pnl == ending − capital` sur les rejeux de référence terminant sans inventaire et sans flux
externes ; la reproductibilité de la sélection vide sous les critères codés (P6 0/24, P7 0/35).

**Ce qui doit être recalculé ou requalifié avant toute utilisation comme preuve de validation
économique** : les mesures affectées par les défauts identifiés (Sharpe/Sortino, MaxDD %, PF) et
toute comparaison les utilisant — dont l'application du seuil 0,4 et les comparaisons aux
benchmarks, la règle de décision elle-même n'étant pas en cause, ni le Sharpe B&H calculé
quotidiennement — ainsi que l'expression « dix fois sous le seuil » (§4.2-4.3) ; le statut de
validation chronologique indépendante du walk-forward ; les interprétations causales par régime ou
par les seuls frais (« les fees Bybit ont tué les stratégies »). Les observations descriptives
(comptes d'exécutions, rendements comptables, lectures trimestrielles) restent citables comme
telles, en tant que sorties du simulateur.

**Corroboration C1** : les comparaisons A/B du chantier C1 sur les rejeux de référence corroborent
les défauts de mesure sans modification des exécutions, soldes ou trajectoires d'equity — le PF du
signal A passe notamment de 1,4420 à 1,3832 après imputation des frais d'achat
(`results/C1_metrics_report.md`). Ces vérifications ne constituent pas un nouveau verdict de
campagne ni une validation après correction du replay et du protocole de sélection.

**Formulation qui remplace le verdict** : zéro configuration sélectionnée sous ce protocole avec cet
instrument. Cela justifie le non-déploiement — aucune stratégie n'est validée pour le déploiement
par cette campagne. Cela n'établit ni que les 212 configurations échoueraient sous un instrument
correct (35 seulement ont vu le walk-forward), ni l'absence d'edge économique des familles testées.

**Suites** : réparation de l'instrument de mesure (chantier C1, mergé, tag `v2.9.0-c1-metrics`),
fidélité du replay (C2), rejeu diagnostic du grid (96 configs BTC/SOL, périmètre pré-spécifié,
verdict « inconclusif » possible), validation chronologique (C3) avant toute sélection. Les runs de
nouvelles familles sont gelés jusqu'au merge de C2 ; les tickets d'entrée sur papier continuent
(`docs/CONTRAINTES_POST_B4.md`).

Le corps du rapport ci-dessous est conservé tel quel comme pièce historique.

> Livrable B4 (brief `agent/AGENT_B4_3_CAMPAIGN.md` § 6.3, `ROADMAP.md` § B4). Campagne exécutée sur le serveur
> `krakenbot` (branche `feat/b4-3-campaign`, P6 @ `874fb62`, P7 @ `eb13800` / rapport @ `a59226f` ; mergée dans `dev`
> le 2026-09-15 = `4c98b6b`, tag `v2.8.0-b4-3-campaign` @ `64ca827`), sur les
> 8 712 718 rows Binance **end-stampées** (B4.1) avec le modèle de fees **Bybit** (maker 0.10 % / taker 0.25 %, B4.2),
> les coûts par paire du GATE B (`config/pair_costs_b4.json`), un plancher d'ordre de 5 USDC et le `GridBacktester`
> corrigé au chantier 0 (liquidation terminale atteignable, `net_pnl` compté une fois — GATE A). Contrats :
> `results/B4_3_chantier0_gate_a.md`, `results/B4_3_gate_b_configs.md` (§ 7 : règles GO P7). Chaque chiffre de ce
> rapport est lisible dans un fichier `results/B4_*` ; les fichiers P6/P7 historiques ne sont cités qu'en contexte.

## 0. Verdict

**Aucune stratégie × paire × config ne survit aux fees Bybit sur données saines ; la sélection paper est vide.**

- **P6** : 0 / 24 combinaisons passent les 5 critères stricts (+ cohérence + benchmark). Seule `grok_supertrend_4h` est
  positive et cohérente sur les trois paires (PF test 1.53-1.59, MaxDD ≤ 1.8 %), mais sur 9-13 trades par segment test,
  pour +1.1 à +1.9 % en 3 ans.
- **P7** (212 configs, 280 fenêtres walk-forward sur les 4 stratégies historiques) : **0 / 35 configs agrégées** passent les
  7 critères, appliqués tels quels. Aucune config ne sauve une stratégie que son défaut condamne : la seule famille qui
  bat son défaut en phase 1 (SuperTrend ETH multiplicateur 2.0 : test 0.78 / PF 3.01 / +3.0 % sur 18 trades) tombe à
  −0.10 de Sharpe OOS moyen en walk-forward (2 fenêtres sur 8 positives, 4 trades par fenêtre) ; le grid BTC, meilleur
  Sharpe OOS de la campagne (0.04, PF 2.26, MaxDD 3.5 %, 6/8 fenêtres positives), reste 10× sous le seuil et sous le
  B&H (0.84) ; le grid SOL est **inéligible** (48 / 48 configs flaggées, § 6).
- **Sélection paper : vide, argumentée** (§ 7). Règle GO P7 n° 3 : zéro config passante = zéro sélection, aucun
  assouplissement. Ce que B5 hérite : la config paper révisée du risk (§ 8), les deux dettes (13, 14) et les données Bybit
  live pour P12.
- Résultats aberrants : aucun accepté sans explication (§ 4.2 : PF infinis et liquidations positives des fenêtres grid
  vérifiés arithmétiquement ; § 3.1 : MaxDD DCA = drawdown de l'actif).

## 1. Pourquoi les classements P6/P7 historiques ne sont pas comparables

| Différence | P6/P7 historiques (avril–mai 2026) | Campagne B4 (15 sept. 2026) | Effet attendu |
|---|---|---|---|
| Fees | 0.075 % flat (Binance BNB) sur chaque fill | **maker 0.10 % / taker 0.25 %** selon le site du fill (entrées limit maker ; SL, trailing, timeout, flips, liquidation grid en taker) | toutes les stratégies paient plus ; les sorties market 3.3× plus cher |
| Coûts par paire | spread 0.02 % / slippage 0.01 % globaux | **BTC 2/2 bps, ETH 3/2, SOL 11/2** (mesures q3 `api.bybit.eu`, 126 carnets) sur les fills market | SOL pénalisé sur chaque sortie market et à la liquidation |
| Timestamps | open-stampés → **look-ahead multi-TF** (dette 11) | **end-stampés** (B4.1, 2 550 fenêtres re-stampées, 0 collision) | signaux 4h/1d/1w vus au bon moment ; baseline signal +2.42 % vs P6 historique |
| Moteur grid | liquidation de fin de run inatteignable → inventaire terminal jamais valorisé (biais de survie), fee de vente comptée deux fois dans `net_pnl` | liquidation MARKET au dernier close (taker + spread + slippage), `net_pnl` = cash réalisé (`ending − capital`) | PF grid `inf` → fini ; returns grid en baisse (33 lots BTC liquidés −228 USDC sur le run de référence) |
| Plancher d'ordre | 1 USDC | **5 USDC** (Bybit `minOrderAmt`) | un ordre résiduel < 5 USDC est sauté |
| Grille P7 spacing | `[0.010, 0.015, 0.020, 0.025]` | `[0.015, 0.020, 0.025, 0.030]` (plancher 2.0 % = 10× le round-trip maker/maker 0.20 %) | la config 1.0 % n'existe plus |
| Benchmarks | `P6_benchmarks.json` (sans fee, données open-stampées) | `B4_benchmarks.json` (`--fees bybit`, coûts par paire) | B&H Sharpe 0.85/0.40/0.31 → 0.84/0.38/0.30 (écart = re-stamp, vérifié `--fees none`) |

Conséquence : les chiffres historiques sont cités **en contexte** (§ 3.3, § 4.1), jamais comme référence de régression.
La chaîne de production B4 est validée par le run grid BTC de P6 : identique au run de référence bybit du GATE A
(1 064 trades, PF 1.617, `net_pnl` 114.21, 33 lots liquidés −228.12).

## 2. Couverture des données par paire et par fenêtre

Trou de marché Binance (retrait des paires USDC, conversion BUSD, sept. 2022 — `B4_1_timestamp_restamp_report.md`) :
**BTC/ETH 164 j** (`2022-09-29 → 2023-03-12`), **SOL 455 j** (`2022-09-29 → 2023-12-28`). Le trou SOL mord dans la
fenêtre de campagne (première bougie 5 m SOL après le 1er avril 2023 : **2023-12-28 08:05 UTC**). Comptage 5 m en DB
(exchange `binance`, bougies end-stampées, attendu = minutes / 5) :

| Fenêtre | Train | Test | BTC train / test | ETH train / test | SOL train / test |
|---|---|---|---|---|---|
| P6 / P7 phase 1 (70/30) | 2023-04-01 → 2025-05-07 04:48 | 2025-05-07 → 2026-04-01 | 100.0 % / 100.0 % | 100.0 % / 100.0 % | **64.6 %** (142 809 / 220 953) / 100.0 % |
| w1 | 2023-04-01 → 2024-04-01 | 2024-04-01 → 2024-07-01 | 100.0 % / 100.0 % | 100.0 % / 100.0 % | **25.9 %** / 100.0 % |
| w2 | 2023-07-01 → 2024-07-01 | 2024-07-01 → 2024-10-01 | 100.0 % / 100.0 % | 100.0 % / 100.0 % | **50.7 %** / 100.0 % |
| w3 | 2023-10-01 → 2024-10-01 | 2024-10-01 → 2025-01-01 | 100.0 % / 100.0 % | 100.0 % / 100.0 % | **75.9 %** / 100.0 % |
| w4 | 2024-01-01 → 2025-01-01 | 2025-01-01 → 2025-04-01 | 100.0 % / 100.0 % | 100.0 % / 100.0 % | 100.0 % / 100.0 % |
| w5 | 2024-04-01 → 2025-04-01 | 2025-04-01 → 2025-07-01 | 100.0 % / 100.0 % | 100.0 % / 100.0 % | 100.0 % / 100.0 % |
| w6 | 2024-07-01 → 2025-07-01 | 2025-07-01 → 2025-10-01 | 100.0 % / 100.0 % | 100.0 % / 100.0 % | 100.0 % / 100.0 % |
| w7 | 2024-10-01 → 2025-10-01 | 2025-10-01 → 2026-01-01 | 100.0 % / 100.0 % | 100.0 % / 100.0 % | 100.0 % / 100.0 % |
| w8 | 2025-01-01 → 2026-01-01 | 2026-01-01 → 2026-04-01 | 100.0 % / 100.0 % | 100.0 % / 100.0 % | 100.0 % / 100.0 % |

Lecture : « 3 ans de backtest » est vrai pour BTC et ETH (1 096 jours), **faux pour SOL** : 2 ans et 3 mois de données
(2023-12-28 → 2026-04-01, 825 jours, 75.2 % de la fenêtre), tout le train SOL de P6/phase 1 tient sur 17 mois, et les
trains walk-forward w1–w3 de SOL sont amputés de 74 % / 49 % / 24 %. Tous les **segments test** sont complets à 100 %
(BTC, ETH, SOL) : les métriques out-of-sample ne sont pas affectées, mais les entraînements SOL des trois premières
fenêtres reposent sur 3 à 9 mois de données, et la cohérence 5/8 exigée par le critère P7 n° 5 est donc plus dure à
atteindre pour SOL que pour BTC/ETH. Recouvrement Bybit EU en DB (pour B5, pas pour les backtests) : BTC dès
2025-06-11, ETH/SOL dès 2025-06-27.

## 3. P6 — 24 combinaisons (8 stratégies × 3 paires), critères stricts

Fichiers : `B4_P6_phase_d_results.json` (24 entrées, signature `('bybit', 'config/pair_costs_b4.json', 5.0)` × 24),
`B4_P6_phase_e_filtering.md`, `B4_P6_backtest_report.md`, `B4_P6_checkpoint.md`. Critères (test set) : Sharpe > 1.0,
Sortino > 1.5, MaxDD < 25 %, PF > 1.5, Calmar > 0.5, ≥ 30 trades (DCA exempté), cohérence test/train > 0.5, bat B&H
ou DCA fixe en Sharpe. **Résultat : 0 / 24.** Verdict par combinaison (chaque métrique avec son nombre de trades) :

| Stratégie | Paire | Train Sharpe (n) | Test Sharpe (n) | Test Sortino | Test PF | Test MaxDD | Test Calmar | Test return | ratio test/train | All return (n) | All MaxDD |
|---|---|---|---|---|---|---|---|---|---|---|---|
| gemini_retour_moyenne | BTC | -0.18 (n=46) | -0.20 (n=21) | -0.25 | 0.19 | 0.2 % | -1.02 | -0.2 % | n/a | -0.5 % (n=67) | 0.5 % |
| gemini_retour_moyenne | ETH | -0.15 (n=44) | -0.20 (n=23) | -0.25 | 0.11 | 0.3 % | -1.04 | -0.3 % | n/a | -0.6 % (n=67) | 0.6 % |
| gemini_retour_moyenne | SOL | -0.15 (n=22) | -0.13 (n=21) | -0.16 | 0.37 | 0.2 % | -0.99 | -0.2 % | n/a | -0.4 % (n=43) | 0.5 % |
| gemini_scalping_volatilite | BTC | -0.54 (n=475) | -0.70 (n=217) | -0.81 | 0.15 | 2.0 % | -1.11 | -2.0 % | n/a | -6.1 % (n=692) | 6.1 % |
| gemini_scalping_volatilite | ETH | -0.59 (n=546) | -0.59 (n=298) | -0.73 | 0.28 | 2.7 % | -1.09 | -2.6 % | n/a | -8.1 % (n=844) | 8.2 % |
| gemini_scalping_volatilite | SOL | -0.61 (n=515) | -0.71 (n=370) | -0.86 | 0.23 | 4.1 % | -1.10 | -4.1 % | n/a | -10.0 % (n=885) | 10.0 % |
| gemini_suivi_tendance_momentum | BTC | -0.03 (n=120) | -0.14 (n=12) | -0.19 | 0.16 | 0.6 % | -0.91 | -0.5 % | n/a | -2.3 % (n=161) | 3.0 % |
| gemini_suivi_tendance_momentum | ETH | -0.03 (n=94) | -0.04 (n=15) | -0.06 | 0.66 | 1.0 % | -0.52 | -0.5 % | n/a | -0.1 % (n=133) | 3.2 % |
| gemini_suivi_tendance_momentum | SOL | -0.04 (n=49) | -0.10 (n=21) | -0.14 | 0.39 | 2.1 % | -0.83 | -1.6 % | n/a | -4.3 % (n=91) | 4.5 % |
| grok_adaptive_dca_weekly | BTC | 1.31 (n=101) | -1.20 (n=45) | -1.59 | 0.00 | 13.5 % | -0.83 | -10.1 % | -0.91 | +71.7 % (n=101) | 49.6 % |
| grok_adaptive_dca_weekly | ETH | 0.08 (n=88) | -0.56 (n=47) | -0.78 | 0.00 | 27.7 % | -0.49 | -12.2 % | -7.05 | -3.5 % (n=88) | 62.2 % |
| grok_adaptive_dca_weekly | SOL | 0.25 (n=70) | -1.14 (n=46) | -1.51 | 0.00 | 32.4 % | -0.77 | -22.5 % | -4.49 | -43.5 % (n=104) | 66.6 % |
| grok_donchian_breakout_4h | BTC | 0.17 (n=36) | -0.22 (n=8) | -0.32 | 0.60 | 0.7 % | -0.43 | -0.3 % | -1.32 | +0.9 % (n=44) | 1.6 % |
| grok_donchian_breakout_4h | ETH | -0.13 (n=26) | 0.06 (n=12) | 0.09 | 1.10 | 1.6 % | 0.12 | +0.2 % | n/a | -0.6 % (n=38) | 4.0 % |
| grok_donchian_breakout_4h | SOL | -0.36 (n=20) | -0.23 (n=14) | -0.31 | 0.69 | 1.4 % | -0.57 | -0.7 % | n/a | -3.1 % (n=34) | 4.5 % |
| grok_ema_adx_atr | BTC | 0.30 (n=8) | -0.07 (n=1) | -0.09 | 0.00 | 0.1 % | -0.21 | -0.0 % | -0.22 | +1.0 % (n=9) | 1.0 % |
| grok_ema_adx_atr | ETH | -0.18 (n=4) | 0.11 (n=2) | 0.18 | 4.00 | 0.3 % | 0.25 | +0.1 % | n/a | -0.2 % (n=6) | 0.7 % |
| grok_ema_adx_atr | SOL | 0.35 (n=2) | -0.15 (n=2) | -0.21 | 0.32 | 0.8 % | -0.29 | -0.2 % | -0.41 | +1.2 % (n=4) | 0.8 % |
| grok_grid_atr_adaptive_v4 | BTC | 0.07 (n=845) | -0.03 (n=293) | -0.05 | 0.46 | 24.0 % | -0.54 | -11.6 % | -0.44 | +11.4 % (n=1064) | 20.0 % |
| grok_grid_atr_adaptive_v4 | ETH | 0.01 (n=1253) | -0.05 (n=404) | -0.07 | 0.30 | 44.7 % | -0.79 | -31.7 % | -5.14 | +21.1 % (n=2055) | 34.5 % |
| grok_grid_atr_adaptive_v4 | SOL ⚑ | 0.07 (n=1681) | -0.06 (n=580) | -0.08 | 0.31 | 58.5 % | -0.84 | -44.4 % | -0.83 | +31.0 % (n=2310) | 32.1 % |
| grok_supertrend_4h | BTC | 0.22 (n=37) | 0.16 (n=9) | 0.23 | 1.57 | 0.6 % | 0.48 | +0.3 % | 0.72 | +1.9 % (n=46) | 2.3 % |
| grok_supertrend_4h | ETH | 0.00 (n=27) | 0.29 (n=13) | 0.42 | 1.53 | 1.8 % | 0.70 | +1.2 % | 120.38 | +1.1 % (n=40) | 3.3 % |
| grok_supertrend_4h | SOL | 0.11 (n=16) | 0.21 (n=10) | 0.31 | 1.59 | 1.1 % | 0.78 | +0.8 % | 1.89 | +1.7 % (n=26) | 2.9 % |

`ratio test/train` = Sharpe test / Sharpe train, `n/a` quand le Sharpe train ≤ 0 (la valeur 120.38 d'ETH SuperTrend
vient d'un Sharpe train de 0.0026 : sans signification). ⚑ = run flaggé (§ 6). Raisons d'échec (24 combos) : Sharpe ×24,
Sortino ×24, benchmark ×24, Calmar ×22, PF ×20, trades ×15, cohérence ×9, MaxDD ×4.

### 3.1 Lecture par stratégie (jamais le Sharpe seul)

- **`grok_supertrend_4h`** — la seule stratégie **positive et cohérente sur les trois paires** : PF test 1.57 / 1.53 /
  1.59, returns test +0.3 / +1.2 / +0.8 %, MaxDD ≤ 1.8 %, mais sur **9 / 13 / 10 trades** en test (37 / 27 / 16 en
  train) : trop peu pour le critère « 30 trades » et pour que le Sharpe (0.16 / 0.29 / 0.21) soit autre chose qu'un
  bruit de faible amplitude. Sur 3 ans, +1.9 / +1.1 / +1.7 % (46 / 40 / 26 trades) : très loin du B&H BTC (+137 %),
  mais avec un MaxDD de 2-3 % contre 50-70 %. C'est la candidate P7 (§ 4).
- **`grok_grid_atr_adaptive_v4`** — moteur honnête oblige : PF test **0.46 / 0.30 / 0.31** (contre `inf` en P6
  historique où l'inventaire terminal n'était jamais liquidé), returns test −11.6 / −31.7 / −44.4 % sur des tests qui
  finissent en marché baissier (liquidation de 33 / 44 / 47 lots sous l'eau : −202 / −440 / −625 USDC), MaxDD test
  24 / 45 / 58 %. Sur 3 ans le grid reste positif (+11.4 / +21.1 / +31.0 %, 1 064 / 2 055 / 2 310 trades) grâce aux
  phases haussières, mais avec des drawdowns de 20-35 % et un inventaire terminal toujours en perte (33 / 56 / 45 lots).
  SOL est **flaggé** (§ 6). Candidate P7 (grilles spacing / ATR / protection bear).
- **`grok_adaptive_dca_weekly`** — accumulation sans vente : le Sharpe test (−1.20 / −0.56 / −1.14) et le PF 0.00
  sont ceux d'une courbe majoritairement cash qui ne réalise jamais (§ 5, note DCA) ; à lire en return / MaxDD :
  +71.7 % / −3.5 % / −43.5 % sur 3 ans avec MaxDD **49.6 / 62.2 / 66.6 %** = le drawdown de l'actif (B&H : 49.7 / 63.8 /
  70.2 %). Les « anomalies MaxDD > 60 % » du checkpoint sont attendues, pas un bug. Candidate P7 (BTC seulement).
- **`grok_donchian_breakout_4h`** — négatif ou nul partout (PF 0.60 / 1.10 / 0.69 sur 8 / 12 / 14 trades) ; l'ETH
  positif (+0.2 %) ne survit pas aux fees sur 3 ans (−0.6 %). Candidate P7 (SOL, 8 configs) par continuité
  historique seulement.
- **`grok_ema_adx_atr`** — 1 à 2 trades en test : **inexploitable** (le PF 4.00 d'ETH repose sur 2 trades). Abandon.
- **`gemini_*`** (3) — négatifs sur les trois paires, PF ≤ 0.66, Sharpe test −0.04 à −0.71 ; le scalping perd 6-10 %
  sur 3 ans en 700-900 trades (les fees maker/taker le condamnent structurellement). Abandon confirmé (déjà KILL
  en P1A/P6).

### 3.2 Cohérence entre paires

Les trois stratégies dont le signe est le même sur BTC / ETH / SOL (SuperTrend +, scalping −, retour à la moyenne −)
sont celles dont le verdict est robuste ; DCA et grid dépendent du régime terminal (BTC haussier sur la fenêtre
`all`, ETH/SOL baissiers), ce qui est exactement ce que le walk-forward P7 doit départager.

### 3.3 Contexte historique (P6 fees Binance, non comparable — § 1)

Même verdict qu'en avril (0 / 24) ; les deltas vont dans le sens attendu et sont **tous signés** : SuperTrend test
Sharpe 0.25 → 0.16 (BTC), 0.53 → 0.29 (ETH), 0.29 → 0.21 (SOL) et PF 1.90 / 2.39 / 1.96 → 1.57 / 1.53 / 1.59 (fees
plus élevées, mêmes 9-13 trades) ; grid PF `inf` → 0.3-0.5 (liquidation terminale) avec un return 3 ans +14.4 / +24.1 /
+34.8 % → +11.4 / +21.1 / +31.0 % ; DCA quasi identique (+68.4 → +71.7 % BTC : effet du re-stamp sur les prix
d'exécution) ; Donchian 1.02 / 1.26 / 0.99 → 0.60 / 1.10 / 0.69. Aucun delta positif inexpliqué.

## 4. P7 — grid search sur les 4 stratégies historiques

Comme aucune combinaison ne survit à P6, P7 tourne sur les **4 stratégies historiques du grid search** (brief § 6.2)
avec la question : *une config sauve-t-elle une stratégie que sa config par défaut condamne ?* Grilles GATE B
(spacing `[0.015, 0.020, 0.025, 0.030]`, plancher 2.0 % ; le reste identique à P7 historique) : SuperTrend 20 configs ×
3 paires, Grid ATR 48 × BTC/SOL, DCA 48 × BTC, Donchian 8 × SOL = **212 jobs** phase 1 (cross-validation 70/30 sur
2023-04-01 → 2026-04-01, split 2025-05-07), puis **280 fenêtres** phase 2 (top-5 par combo × 8 fenêtres walk-forward
12 m / 3 m). Fichiers : `B4_P7_phase1_cross_validate.json` (212 entrées), `B4_P7_phase2_walk_forward.json`
(280 entrées), `B4_P7_optimization_report.md`, `B4_P7_final_selection.json`. Les 7 critères P7 (mean Sharpe OOS
> 0.4, PF OOS > 1.3, MaxDD < 30 %, ≥ 20 trades/fenêtre (DCA ≥ 5), cohérence ≥ 5/8, ratio OOS/train > 0.5, bat B&H ou
DCA fixe en Sharpe) sont appliqués **tels quels** (règle GO P7 n° 3).

### 4.1 Phase 1 — 212/212, 0 crash, 0 anomalie, 144 runs flaggés (les 48 configs grid × SOL)

Checkpoint (`scripts/audit/b4_p7_checkpoint.py`) : signature uniforme, aucun run « trop beau » (PF > 10 sur < 10
trades, Sharpe > 3, return > 200 %, liquidation en profit), 288 segments grid liquidés (2 à 72 lots, P&L −2.61 à
−764.95 USDC, aucun inventaire terminal vide), **144 non réconciliés = les 48 configs SOL × 3 segments** (§ 6) ; les
144 segments BTC réconcilient tous. Meilleure config par combo, avec la config par défaut (P6) en regard (test
Sharpe / PF / return, n trades ; train Sharpe, n ; 3 ans) :

| Combo | Config par défaut (P6) | Meilleure config phase 1 (test Sharpe) | Configs test > 0 | Verdict phase 1 |
|---|---|---|---|---|
| SuperTrend × BTC | 10 / 3.0 : **0.16 / 1.57 / +0.3 % (n=9)** ; train 0.22 (n=37) ; 3 ans +1.9 % | = défaut (10 / 3.0) ; 2ᵉ : 7 / 3.0 −0.05 / 0.95 / −0.1 % (n=9) | 1 / 20 | aucune config ne fait mieux que le défaut ; 9 trades en test |
| SuperTrend × ETH | 10 / 3.0 : 0.29 / 1.53 / +1.2 % (n=13) ; train 0.00 (n=27) ; 3 ans +1.1 % | **20 / 2.0 : 0.78 / 3.01 / +3.0 % (n=18)** ; train **−0.07** (n=48) ; 3 ans +2.5 % (MaxDD 2.9 %) — toute la famille mult 2.0 : Sharpe moyen 0.72, PF 2.74, +2.8 % (n=19) | 20 / 20 | la seule famille de configs qui « sauve » son défaut en phase 1 — mais le train est négatif (le test 2025-05 → 2026-04 favorise ETH) : verdict au walk-forward |
| SuperTrend × SOL | 10 / 3.0 : **0.21 / 1.59 / +0.8 % (n=10)** ; train 0.11 (n=16) ; 3 ans +1.7 % | = défaut ; 2ᵉ : 14 / 2.0 0.11 / 1.25 / +0.4 % (n=18), train −0.22, 3 ans −1.0 % | 8 / 20 | le défaut reste le meilleur ; mult 4.0 détruit (−0.31 / 0.45) |
| Grid ATR × BTC | 1.5 % / 1.5 / 1w : −0.03 / 0.46 / −11.6 % (n=293) ; 3 ans +11.4 % (MaxDD 20 %, 33 lots −228) | 3.0 % / 1.5 / 1w : −0.01 / 0.79 / −1.4 % (n=71) ; train 0.09 (n=185) ; 3 ans +11.0 % (MaxDD 5.8 %, 10 lots −51) | **0 / 48** | aucune config positive en test ; l'espacement 3 % divise la perte test par 8 et l'inventaire par 3 pour le même return 3 ans ; `atr_multiplier` sans effet (≤ 0.2 pt) ; `1d_only` le pire (PF 0.19) |
| Grid ATR × SOL ⚑ | 1.5 % / 1.5 / 1w : −0.06 / 0.31 / −44.4 % (n=580) ; 3 ans +31.0 % (MaxDD 32 %) | 3.0 % / 3.0 / none : −0.02 / 0.67 / −7.8 % (n=224) ; train 0.08 (n=576) ; 3 ans +22.3 % (MaxDD 25 %, 29 lots −326) | **0 / 48** | aucune config positive en test ; spacing 3 % −15.9 % contre −38.3 % à 1.5 % ; **48 / 48 configs flaggées** (mauvais pop) → toutes inéligibles |
| DCA × BTC | 1.5 / 0.5 / 30 : −1.20 / 0.00 / −10.1 % (n=45) ; 3 ans **+71.7 %** (MaxDD 49.6 %) | 3.0 / 0.3 / 35 : −0.42 / 0.00 / −1.3 % (n=11) ; train 1.35 (n=35) ; 3 ans +65.6 % (MaxDD 41.9 %) | **0 / 48** | aucune config ne réalise : PF 0.00 partout (le DCA n'a pas de sortie) ; `bull_reduction` 0.3 achète 4× moins en test (11 trades vs 45) et perd moins (−1.1 % vs −10 à −19 %) au prix de −6 à −16 pts sur 3 ans ; `oversold_multiplier` et `rsi_oversold` sans effet |
| Donchian × SOL | 20 / close : −0.23 / 0.69 / −0.7 % (n=14) ; 3 ans −3.1 % | 30 / close : 0.13 / 1.48 / +0.3 % (n=9) ; train **−0.44** (n=16) ; 3 ans −2.5 % | 1 / 8 | bruit : +0.3 % sur 9 trades avec un train négatif ; 0 / 8 configs positives sur 3 ans |

Distribution des Sharpe test (min / médiane / max) : SuperTrend −0.52 / −0.01 / 0.78 (60 jobs), Grid −0.07 / −0.05 /
−0.01 (96), DCA −1.24 / −1.21 / −0.42 (48), Donchian −0.43 / −0.23 / 0.13 (8). Une seule config phase 1 franchit les
critères 1-2-4 sur le seul split 70/30 (`grok_supertrend_4h` ETH 7 / 2.0, informatif). Contexte historique (P7 phase 1
fees Binance, non comparable) : mêmes têtes de classement — SuperTrend ETH 10 / 2.0 à 0.98 / 4.34 (n=18) devient 0.75 /
2.83 (n=19) sous fees Bybit ; grid PF `inf` → < 1 ; Donchian SOL 30 / close 0.21 / 1.78 → 0.13 / 1.48.

### 4.2 Phase 2 — walk-forward 8 fenêtres sur le top-5 de chaque combo

280 / 280 fenêtres, 0 crash ; 60 runs flaggés = les 5 configs grid × SOL du top-5 (inéligibles). Le checkpoint a levé
108 « anomalies », toutes expliquées avant acceptation (`B4_P7_checkpoint.md`) : 27 PF infinis = fenêtres grid sans
paire perdante (13 finissent inventaire vide, 14 avec 1-2 lots liquidés 1.2-2.5 % **au-dessus** du coût — ex. `9d3bf21b`
w1 train : 2 lots de 24.98 USDC liquidés à 71 279.48 = 71 308 × (1 − 0.0004), P&L +0.58 = +1.16 %, arithmétique
vérifiée ; l'agrégateur compte un PF `inf` comme 0 dans la moyenne, conservateur) ; 66 segments à 0 trade = fenêtres
test de 3 mois des stratégies lentes (DCA 35/40, SuperTrend 17/120, Donchian 6/40). Meilleure config par combo au
walk-forward (top-5 par Sharpe OOS moyen dans `B4_P7_optimization_report.md`) :

| Combo | Meilleure config (walk-forward) | Sharpe OOS moyen ± std (trades/fenêtre moy. / min) | PF OOS | Cohérence | MaxDD | Train Sharpe (n) | Ratio OOS/train | Critères en échec (sur 7) |
|---|---|---|---|---|---|---|---|---|
| Grid ATR × BTC | 3.0 % / 3.0 / 1w (4 configs spacing 3 % ex æquo) | **0.04 ± 0.08** (n=18 / 1) | 2.26 | **6/8** | 3.5 % | 0.08 (n=86) | 0.49 | Sharpe (0.04 < 0.4), trades (17.9 < 20), ratio (0.49 < 0.5), benchmark (0.04 < B&H 0.84) |
| Grid ATR × SOL ⚑ | 3.0 % / 3.0 / none | 0.04 ± 0.10 (n=77 / 39) | 3.71 | 5/8 | 16.3 % | 0.09 (n=318) | 0.44 | **inéligible** (14-16 flags par config) ; Sharpe, ratio, benchmark |
| SuperTrend × BTC | 7 / 3.0 (défaut 10 / 3.0 : −0.16) | −0.12 ± 0.73 (n=4 / 0) | 0.83 | 3/8 | 1.1 % | 0.29 (n=18) | < 0 | Sharpe, PF, trades (3.5), cohérence, ratio, benchmark |
| SuperTrend × ETH | 7 / 2.0 (star phase 1 20 / 2.0 : −0.20) | −0.10 ± 0.95 (n=4 / 0) | 0.91 | 2/8 | 1.5 % | 0.14 (n=23) | < 0 | idem |
| SuperTrend × SOL | 10 / 3.0 (= défaut) | −0.16 ± 0.58 (n=3 / 0) | 0.89 | 2/8 | 1.1 % | 0.14 (n=10) | < 0 | idem |
| DCA × BTC | 3.0 / 0.3 / 35 | −0.13 ± 0.38 (n=2 / 0) | 0.00 | 0/8 | 2.0 % | 0.98 (n=10) | < 0 | Sharpe, PF, trades (1.5 < 5), cohérence, ratio, benchmark |
| Donchian × SOL | 20 / close (= défaut) | −0.29 ± 0.52 (n=3 / 0) | 0.24 | 2/8 | 1.4 % | −0.55 (n=13) | n/a | Sharpe, PF, trades (3.3), cohérence, ratio, benchmark |

Lecture fenêtre par fenêtre des deux têtes de phase 1 (test Sharpe / PF / return, n trades) :
- **SuperTrend ETH 20 / 2.0** : w1 −1.57 / 0.08 / −1.2 % (8) ; w2 0 trade ; w3 −0.13 / 0.85 / −0.1 % (7) ; w4 −1.19 / 0 /
  −0.4 % (1) ; w5 +0.05 / 0.56 / +0.1 % (6) ; **w6 +1.89 / 5.15 / +2.9 % (8)** ; w7 −0.62 / 0 / −0.3 % (2) ; w8 0 trade.
  Tout le score phase 1 vient de la fenêtre w6 (test 2025-07 → 2025-10, incluse dans le segment test 70/30) ; hors
  d'elle la config perd ou ne trade pas. La config par défaut 10 / 3.0 fait de même sur BTC (w3 +1.02 sur 7 trades,
  w1 −1.96, deux fenêtres à ≤ 1 trade) et SOL (w3 +0.49, w6 +0.71, w1 −1.08).
- **Grid BTC 3.0 % / 1w** : w1 +0.05 / 3.01 / +0.8 % (20) ; w2 +0.09 / 10.2 / +1.9 % (33) ; w3 +0.10 / 2.79 / +0.7 % (21) ;
  w4 +0.03 / 1.55 / +0.6 % (31) ; w5 +0.15 / inf / +0.6 % (9, inventaire vide) ; w6 +0.05 / inf / +0.1 % (1) ; w7 −0.04 /
  0.55 / −1.0 % (22, 6 lots liquidés −21) ; w8 −0.09 / 0.03 / −2.1 % (6, 5 lots −22). Régulier mais minuscule : +0.1 à
  +1.9 % par trimestre haussier, −1 à −2 % dès que le trimestre finit sous les niveaux d'achat — un Sharpe de 0.04 pour
  un B&H à 0.84 sur la même période.

### 4.3 Réponse à la question P7

**Non.** Sur les 4 stratégies × 7 combos × 212 configs, aucune configuration ne transforme un verdict négatif en
verdict positif au walk-forward :
- le grid (BTC) gagne en régularité avec un espacement de 3 % (6/8 fenêtres positives, MaxDD 3.5 %) mais son rendement
  reste de l'ordre de +0.5 % par trimestre pour un Sharpe de 0.04 — il ne bat ni le seuil (0.4) ni le B&H (0.84) et
  n'atteint pas 20 trades par fenêtre ; sur SOL toutes les configs sont inéligibles (tolérance de fermeture, dette 14) ;
- SuperTrend ne produit que 2-5 trades par trimestre : ses Sharpe de fenêtre sont du bruit (±0.7-1.0 d'écart-type entre
  fenêtres), la cohérence plafonne à 3/8 et la meilleure config phase 1 doit tout à une seule fenêtre ;
- DCA n'a pas de sortie (PF 0.00, 0/8), Donchian est négatif sur les deux segments.
Les grilles elles-mêmes sont peu sensibles : `atr_multiplier` est sans effet sur le grid (4 configs ex æquo au bit près
sur BTC), `oversold_multiplier` / `rsi_oversold` sans effet sur le DCA, `st_atr_period` marginal sur SuperTrend. Les
seuls leviers réels sont `min_spacing_pct` (grid : 3 % > 2.5 % > 2 % > 1.5 % en test, l'inverse sur 3 ans), `bull_reduction`
(DCA : achète moins en bull) et `st_multiplier` (SuperTrend : 2.0 sur ETH, 3.0 ailleurs) — aucun ne franchit un critère.


## 5. Benchmarks sous fees Bybit et règle de lecture

`B4_benchmarks.json` (`--fees bybit --pair-costs-file config/pair_costs_b4.json`, 2023-04-01 → 2026-04-01, bougies 1d) :

| Paire | B&H return | B&H Sharpe | B&H Sortino | B&H MaxDD | DCA fixe 15 USDC/lundi : investi → final | DCA return / investi | DCA pire P&L vs investi | DCA Sharpe (script) |
|---|---|---|---|---|---|---|---|---|
| BTC/USDC | +137.5 % | 0.84 | 1.27 | 49.6 % | 2 355 → 2 847 (157 achats) | +20.9 % | −10.6 % | 2.35 (non comparable) |
| ETH/USDC | +12.5 % | 0.38 | 0.57 | 63.8 % | 2 355 → 1 925 (157 achats) | −18.3 % | −37.6 % | 2.09 (non comparable) |
| SOL/USDC | −20.4 % | 0.30 | 0.45 | 70.2 % | 1 770 → 1 010 (118 achats, dès 2023-12-29) | −42.9 % | −48.7 % | 2.08 (non comparable) |

**Règle de lecture (GO P7, règle 2).** Le Sharpe d'une stratégie se compare **au B&H seulement** ; la comparaison
**au DCA se fait en return et en MaxDD**. Le Sharpe du DCA fixe produit par `compute_benchmarks.py` (2.1-2.4) n'est
**pas comparable** : sa courbe d'equity est « coins seulement » et part de 0, chaque dépôt hebdomadaire est compté
comme un rendement (un Sharpe de 2 à côté d'un return négatif est impossible pour une vraie courbe), son MaxDD de
100 % est un artefact de la même construction, et ses achats ignorent les coûts par paire. La colonne « pire P&L vs
investi » (recalcul lecture seule, même série 1d, même fee maker) est le drawdown honnête d'un DCA : le pire
moment où l'on aurait vendu tout l'inventaire sous le capital investi jusque-là. De même, la stratégie
`grok_adaptive_dca_weekly` garde l'essentiel de ses 1 000 USDC en cash : son Sharpe n'est pas comparable à celui
d'une stratégie investie ; on la lit en return / MaxDD (§ 3.1). Le critère P7 n° 7 (« bat B&H ou DCA fixe en
Sharpe », un OR) n'est pas affecté : la borne effective est le B&H (BTC 0.84 ; ETH/SOL sous le seuil 0.4 du
critère n° 1). Note : le B&H paie l'entrée en taker + coûts par paire (2.5 USDC BTC), le DCA fixe paie le maker.

## 6. Runs flaggés et inéligibilité (règle GO GATE A + règle GO P7 n° 1)

Règle : tout run grid dont le bloc `liquidation` montre une divergence d'inventaire ou un résidu au-delà de la
dérive Decimal (1e-12), ou un `net_pnl` (cash) ≠ `net_pnl_lot_basis`, est **nommé** ; depuis le GO P7, sa config est
**inéligible à la sélection paper quel que soit son score**.

**P6 : 3 flags, tous `grok_grid_atr_adaptive_v4 × SOL/USDC`** (train / test / all) : divergence d'inventaire −0.0256 /
−0.0058 / −0.0335 SOL, `net_pnl` cash ≠ lot-basis de −3.76 / −0.74 / −3.86 USDC. Diagnostic (dump local du run `all`,
4 620 trades) : **40 lots vendus deux fois** — la stratégie protégée ferme une position par proximité de prix
(`|sell_level − prix| < 1` USD, tolérance **absolue**, `grok_grid_atr_adaptive_v4.py`) alors que le moteur débite par
`position_id` ; à ~180 USD le SOL, des cibles à moins de 1 USD sont fréquentes, jamais sur BTC (divergence 1e-30) et
quasi jamais sur ETH (1e-28). Le `net_pnl` cash publié est exact (identité `usdc − capital`) ; le lot-basis, le PF et
le win-rate SOL grid sont légèrement optimistes (+1.2 % de P&L lot-basis sur `all`). BTC et ETH grid réconcilient
(divergence ≤ 7e-28, résidu 0) sur les 6 segments.

**Condition de candidature grid × SOL** : fix de la tolérance de fermeture (absolue → **relative**, en % du prix ou
en fraction du spacing) dans la stratégie protégée, avec review humaine, puis re-run — **dette 14**
(`PROJECT_CONTEXT.md`). Aucune config grid SOL ne peut être retenue avant.

**P7 : 204 flags.** Phase 1 : **les 48 configs grid × SOL, sur leurs 3 segments** (144 runs) — le mauvais pop est
systématique sur SOL quels que soient l'espacement (1.5-3 %), le multiplicateur ATR et la protection bear ; les 48 configs
BTC réconcilient toutes (divergence ≤ 1e-28, résidu 0). Phase 2 : les 5 configs SOL du top-5 sont flaggées sur 60 de
leurs 80 segments (11-16 flags par config). **Inéligibles (règle GO P7 n° 1) : 5 configs**, listées avec leur verdict sur
les 7 critères dans `B4_P7_optimization_report.md` § « Ineligible configurations » et `B4_P7_final_selection.json`
(`ineligible_flagged`) — aucune ne passait de toute façon (Sharpe OOS 0.04, ratio OOS/train 0.44). Le combo grid × SOL
est abandonné avec la raison « all 5 configurations are flagged ». Aucun autre run de la campagne n'est flaggé (les
stratégies signal n'ont pas de bloc `liquidation`).

## 7. Sélection paper

**Sélection vide.** `B4_P7_final_selection.json` : `selected_for_paper = []`, `abandoned` = 7 combos (raison par combo),
`ineligible_flagged` = 5, `flagged_runs` = 204, `all_verdicts` = 35 configs avec leurs 7 critères. Constat d'échec,
argumenté :

1. **Aucune config ne passe les critères P7** (règle n° 3 : pas d'assouplissement). Le critère le plus proche d'être
   atteint est la cohérence du grid BTC (6/8) ; les critères Sharpe OOS > 0.4 et « bat le B&H » ne sont approchés par
   personne (max 0.04 contre 0.84), et le plancher de 20 trades par fenêtre n'est atteint que par le grid SOL,
   inéligible.
2. **Le bruit domine** : SuperTrend, Donchian et DCA ont 2-5 trades par fenêtre de 3 mois ; à ce rythme un Sharpe de
   fenêtre n'a pas de sens et une sélection reviendrait à choisir la config qui a eu de la chance sur w6 (ETH) ou w3
   (BTC / SOL).
3. **Les stratégies « positives sur 3 ans » le sont trop peu** : SuperTrend +1.1 à +1.9 % (26-46 trades), grid BTC +11 %
   avec 20 % de drawdown et un inventaire terminal de 33 lots à −228 USDC, DCA BTC +72 % avec le drawdown de l'actif
   (50 %) — contre un B&H BTC à +137 % ; ETH et SOL sont négatifs ou nuls partout sauf SuperTrend (+1 %).
4. **La grille de coûts Bybit condamne le scalping et le retour à la moyenne** (PF ≤ 0.37, 700-900 trades à −6 / −10 %)
   et ampute SuperTrend (PF 1.90 / 2.39 / 1.96 → 1.57 / 1.53 / 1.59 à trades identiques) : c'est le résultat attendu de
   B4, pas un artefact.

Ce que la campagne **retient** pour la suite (sans sélection) : (a) `grok_supertrend_4h` défaut 10 / 3.0 est la seule
stratégie cohérente sur les trois paires — candidate naturelle d'un **paper d'observation à budget nul** (P12,
données Bybit live), pas d'une sélection B4 ; (b) le grid n'a de sens qu'avec un espacement ≥ 3 % sous fees Bybit et
seulement sur BTC, après le fix de la dette 14 s'il doit revenir sur SOL ; (c) aucune stratégie ne justifie de capital
en B5 sur la base de ces backtests. Les `effective_params` capturés au runtime (défauts de classe, B.2a) restent
disponibles par entrée pour aligner `strategies.yaml` (dette 13) le jour où une sélection existe.

## 8. Risk management révisé — valeurs retenues pour la config paper B5

Cartographie GATE B (§ 2, validée GO B) : ce que les moteurs ont **simulé** dans cette campagne et ce qui reste du
runtime pur, documenté pour B5 mais non testé ici.

| Paramètre | Runtime actuel | Cible B5 (PROJECT_CONTEXT § 4) | Backtest B4 |
|---|---|---|---|
| Max positions global | 25 (`global_max_open_positions` 10 en settings, 25 YAML) | ~100 (safeguard) | non simulé (1 position signal / N lots grid) |
| Daily loss limit | 50 EUR fixe | 5 % du capital, sur P&L **net réalisé** | non simulé |
| Exposition max | 90 % | 90 % | non simulé |
| Sizing GRM | `capital × risk_pct 1 % × confidence / \|entry − SL\|`, SL ATR 3.0 × ATR(14, 4h) | risk 2 % si capital < 5k | non simulé : les stratégies posent leurs propres SL (`sl_atr_mult` 3.5) et tailles fixes |
| Crash protector | −7 % / 30 min → ferme 50 % + suspend 2 h | idem | non simulé |
| Budgets `max_allocation_pct` / `StrategyBudget` | 10-25 % de 1 000 par instance | à revoir | non simulé : chaque combo a 1 000 USDC entiers → **returns non transposables** tels quels au paper multi-stratégies (diviser par le budget) |
| Limites par paire | aucune | à envisager | non simulé |
| Sorties MARKET | coût = taker 0.25 % + coûts par paire | doctrine des stops à revalider sur les résultats | **simulé** (fees + `pair_costs`) |
| Plancher d'ordre | aucun | 5 USDC (Bybit `minOrderAmt`), viser 10 | **simulé** (`--min-order-usdc 5`, sans effet mesurable sur les ordres nominaux 25-50 USDC) |
| Params des stratégies grok | `strategies.yaml` par instance (`grid_atr_btc` : lots 10) | à aligner sur le dump `effective_params` | **défauts de classe** (dette 13 : lots grid 25 USDC, SuperTrend 50 USDC…) — B.2a |

Décisions pour B5 issues de cette campagne : (1) la sélection est lue avec les `effective_params` capturés au
runtime (`B4_P7_final_selection.json`), qui alignent `strategies.yaml` **avant** le fix de la résolution par nom de
classe (dette 13, prérequis : test one-off du chemin live/router) ; (2) la doctrine des sorties market reste à
valider en paper : les stops et flips ont coûté taker + spread + slippage dans tous les runs signal ; (3) les budgets
par instance (10-25 %) divisent mécaniquement les returns ci-dessus.

## 9. Exécution

| Étape | Commit serveur | Début → fin (UTC) | Durée | Sortie |
|---|---|---|---|---|
| P6 calibration `--limit 3` (grids) | `874fb62` | 2026-09-15 08:01:26 → 08:05:18 | 3 min 52 | 3 entrées |
| P6 24 combos (reprise) | `874fb62` | 08:07:27 → 08:17:21 | 10 min | `B4_P6_phase_d_results.json` (24/24, 0 crash) |
| P7 phase 1 calibration `--limit 3` | `eb13800` | 10:41:06 → 10:44:43 | 3 min 36 | 3 entrées grid (dont la config par défaut P6 : 33 lots, −228.12, identique au GATE A) |
| P7 phase 1 (209 jobs restants) | `eb13800` | 10:45:43 → 12:36:32 | 1 h 51 (110.8 min) | `B4_P7_phase1_cross_validate.json` (212/212) |
| P7 phase 2 (280 fenêtres) | `a59226f` | 12:38:44 → 13:03:34 | 24 min 50 | `B4_P7_phase2_walk_forward.json` (280/280) |
| P7 rapport | `a59226f` | 13:12:25 → 13:12:27 | secondes | `B4_P7_optimization_report.md`, `B4_P7_final_selection.json` |

Serveur `krakenbot` (4 vCPU, 7.6 Gi), 3 workers `nice -n 10`, `--timeout 5400`, tmux `b4` ; tmux `spread` et
`krakenbot-collector` intouchés (collector `active` sur toute la campagne : 155 / 155 bougies 1 m Bybit par paire entre 10:40 et 13:15 UTC, 0 manquante ; compteurs cumulés du journal inchangés, 1 erreur / 7 reconnexions depuis le 13/09). Disque 58 G libres
avant / après. Incidents consignés : (1) `~/.bashrc` exporte le `.env` sans guillemets → `unset SCHEDULER_PAIRS
SCHEDULER_INTERVALS` dans les wrappers ; (2) `LOG_LEVEL` non honoré par les scripts → filtre `grep --line-buffered`
avant `tee` (le filtre P6 non ancré avait perdu les lignes `job_done` des jobs supertrend/donchian/ema/dca du log
persisté ; corrigé en P7 par un motif ancré sur l'événement structlog) ; (3) aucun incident P7 : calibration, phase 1, phase 2 et rapport au premier lancement, aucune reprise, aucun `--force` ; le rapport rejoué en local sur les mêmes JSON est identique au bit près (hors horodatage).

## 10. Annexes consignées (non faites)

- **Dette 13** — résolution des params par nom de classe dans les moteurs (les grok tournent sur les défauts) ; fix
  post-B4 après alignement YAML ; test one-off du chemin live/router = prérequis B5.
- **Dette 14** — tolérance de fermeture absolue (`|sell_level − prix| < 1` USD) de `grok_grid_atr_adaptive_v4` →
  relative ; prérequis à toute candidature grid × SOL ; stratégie protégée, review humaine.
- Benchmark DCA fixe (`compute_benchmarks.py`) : courbe coins-only partant de 0 (Sharpe gonflé, MaxDD 100 %),
  `starting_balance` = 15, pas de `pair_costs` ; à reconstruire (cash + coins, dépôts hors rendement) si le critère
  n° 7 doit un jour reposer sur le DCA.
- `LOG_LEVEL` ignoré par tous les scripts (`get_logger()` ne configure rien ; seuls `collector.py` / `main.py`
  appellent `configure_logging`) — un `configure_logging()` optionnel dans les runners éviterait le filtre.
- `~/.bashrc:119` du serveur (`set -a; source .env`) casse les variables JSON pour tout `poetry run` interactif.
- Libellés de flag « … BTC » codés en dur dans `b4_flags.py` (les divergences SOL sont en SOL).
- `scripts/generate_p6_report.py` garde le titre « Binance » et duplique le titre de couverture (cosmétique).
- `results/INDEX.md` : rangs P6/P7 historiques marqués « supersédés par B4 » ; fichiers `B4_*` référencés.
- Le « mauvais pop » (lot fantôme / re-liquidation clampée) reste instrumenté, pas corrigé (fichier protégé).
