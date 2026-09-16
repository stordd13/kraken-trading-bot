# Journal des essais de recherche (append-only)

> **Règle.** Toute campagne ou run exploratoire de backtest est inscrit ici **avant son lancement**
> (décision 17 du `ROADMAP.md`). Les modifications guidées par des résultats (nouveau paramétrage, nouveau
> filtre, nouvelle fenêtre, nouveau critère) sont de **nouveaux essais**, tracés à leur tour. **Rien n'est
> supprimé ni réécrit** : une entrée erronée est corrigée par une entrée suivante qui la cite. Le journal
> sert au contrôle des essais multiples (audit red-team B4, phase 2 priorité 5) : sans lui, aucun taux de
> faux positifs n'est estimable.
>
> Granularité : la campagne (le détail par config vit dans les JSON référencés). Le rejeu diagnostic grid
> (décision 15) est hors quota des 2 familles/cycle mais s'inscrit ici comme tout run. Tant que les runs
> R&D sont gelés (jusqu'au merge de C1-C2), seules les entrées rétroactives et les chantiers de réparation
> de l'instrument figurent ici.

## Format d'une entrée

`date | phase/campagne | famille + périmètre (configs × paires) | données + période | version code
(tag/commit) + version métriques | modèle de fees | verdict | décision consécutive | source (rapport)`

Versions métriques : **v1** = moteurs pré-C1 (défauts D1-D6 de l'audit red-team du 16/09, invalidés) ;
**v2** = `krakenbot.backtest_metrics`, `metrics_version` 2 (C1, tag `v2.9.0-c1-metrics`).

## Entrées

### Reconstruction rétroactive (16/09/2026 — dates depuis les rapports sources)

| # | Date | Phase / campagne | Famille + périmètre (configs × paires) | Données + période | Version code + métriques | Modèle de fees | Verdict | Décision consécutive | Source (rapport) |
|---|---|---|---|---|---|---|---|---|---|
| 1 | 2026-04-19 | P6 — 24 combos | 8 stratégies × 3 paires (BTC/ETH/SOL) = 24 combos, cross-validate 70/30 | Binance (open-stampées), 2023-04 → 2026-04 | `v2.0.0-p6-validated` ; métriques v1 (invalidées D1-D6) | binance 0.075 % flat | 0/24 aux 5 critères stricts | grid search P7 | `results/P6_backtest_report_v2.md`, `results/P6_phase_d_results.json` |
| 2 | 2026-05-30 | P7 phase 1 — grid search cross-validé | 212 configs (4 stratégies : grid ATR v4, SuperTrend, DCA, Donchian) | Binance (open-stampées), 2023-04 → 2026-04 | commit `f04d1fd` (branche mergée le 7 sept, pas de tag) ; métriques v1 | binance 0.075 % flat | classements non transposables aux fees Bybit | re-run B4 | `results/P7_phase1_cross_validate.json` |
| 3 | 2026-09-15 | B4 — P6 re-run | 24 combos (8 × 3) | Binance **end-stampées** (B4.1), 2023-04 → 2026-04 | `v2.8.0-b4-3-campaign` (P6 @ `874fb62`) ; métriques v1 | bybit maker 0.10 % / taker 0.25 % + coûts GATE B par paire (BTC 2/2, ETH 3/2, SOL 11/2 bps), plancher 5 USDC | 0 survivant (3 runs grid × SOL flaggés, dette 14) | GO P7 (checkpoint validé) | `results/B4_P6_backtest_report.md`, `results/B4_P6_checkpoint.md` |
| 4 | 2026-09-15 | B4 — P7 phases 1-2 | 212 configs (SuperTrend 60, Grid 96, DCA 48, Donchian 8) sur 7 combos + 35 configs × 8 fenêtres walk-forward (280) | idem 3 | `v2.8.0-b4-3-campaign` (P7 @ `eb13800`, rapport @ `a59226f`) ; métriques v1 | idem 3 | 0/35, sélection vide ; 48/48 grid × SOL flaggées (dette 14) | roadmap B5 → P10 suspendue ; audit red-team du 16/09 → instrument invalidé (addendum B4) → C1 → C2 → rejeu grid → C3 | `results/B4_bybit_backtest_report.md`, `results/B4_P7_optimization_report.md`, `results/B4_P7_checkpoint.md` |
| 5 | 2026-09-15 | B4 — benchmarks | B&H + DCA fixe 15 USDC/semaine × 3 paires | idem 3 | `v2.8.0-b4-3-campaign` ; métriques v1 (DCA contaminé D6) | idem 3 | B&H Sharpe (quotidien) 0.84 / 0.38 / 0.30 ; DCA Sharpe 2.1-2.4 non comparable (D6) | critère P7 n° 7 ; recalcul v2 en C1 (`results/C1_benchmarks_v2.json`) | `results/B4_benchmarks.json`, `results/B4_bybit_backtest_report.md` § 5 |
| 6 | ≤ 2026-03 | Campagnes kraken-era antérieures | — | — | — | — | — | — | non reconstruites au détail, voir `docs/archive/` (rapports : `results/archive/`) |

### Essais à venir (à inscrire avant lancement)

_(vide — runs R&D gelés jusqu'au merge de C1-C2 ; prochains inscrits attendus : rejeu C2, rejeu diagnostic
grid 96 configs BTC/SOL, protocole C3)_
