# results/ — Index

> Une ligne par fichier conservé : date, phase, verdict, pourquoi il est encore là.
> Tout ce qui n'est plus une référence courante est dans `results/archive/` (rien n'est supprimé).
> Dernière mise à jour : 2026-09-08 (B0.5).

## Fichiers de référence (à la racine de `results/`)

| Fichier | Date | Phase | Verdict / contenu | Pourquoi il reste |
|---|---|---|---|---|
| `bybit_integration_audit.md` | 2026-09-07 | B0 | **GO avec réserves** : instance EU séparée (`api.bybit.eu`), fees 0.10/0.25, historique EU depuis 2025-06-11, corrélation prix Binance/Bybit 0.999999, clés API non vérifiées | Source des constantes B1–B3 (`skills/bybit.md`) et de la décision « données Binance + fees Bybit » |
| `P7_phase1_cross_validate.json` | 2026-05-30 | P7 phase 1 | 212 jobs de grid search cross-validés 70/30 (grid ATR v4, SuperTrend, DCA, Donchian), **fees Binance 0.075 % flat** | Machinerie et grilles réutilisées en B4 ; classements non transposables aux fees Bybit |
| `P6_backtest_report_v2.md` | 2026-04-19 | P6 | 24 combos (8 stratégies × 3 paires, 2023-04 → 2026-04, cross-validate) : **0/24 passent les 5 critères stricts** ; recommandations par stratégie | Rapport P6 de référence (v1 archivée) |
| `P6_phase_d_results.json` | 2026-04-19 | P6 phase D | Résultats bruts des 24 backtests (train / test / all, fees Binance) | Baseline de comparaison fees Binance vs Bybit en B4 |
| `P6_benchmarks.json` | 2026-04-19 | P6 | Buy & Hold et DCA fixe 15 USDC/semaine par paire (Sharpe, return) | Benchmarks des critères P7/B4 (« bat B&H ou DCA ») |
| `P6_data_coverage.md` | 2026-04-16 | P6 | Couverture des 8.7M rows Binance par paire × TF (min/max date, gaps) | Preuve de la base de données de backtest |
| `P6_7_multiprocessing_benchmark.md` | 2026-05-20 | P6.7 | Timings 24 combos série vs parallèle (8 workers), déterminisme validé | Tuning du runner pour B4 (workers, RAM, temps attendu) |
| `P6_phase_e_survivors.json` | 2026-04-19 | P6 phase E | `{}` | Voir note ci-dessous |
| `P6_phase_f_walkforward.json` | 2026-04-19 | P6 phase F | `{}` | Voir note ci-dessous |

**Note obligatoire — `P6_phase_e_survivors.json` et `P6_phase_f_walkforward.json` contiennent `{}`.**
C'est **normal** : 0 combinaison sur 24 a passé les critères P6 (cf. rapport v2), donc zéro survivant en
phase E et pas de walk-forward en phase F. Ce ne sont pas des fichiers corrompus. Ils seront régénérés
en B4 avec les fees Bybit.

### Fichiers locaux non versionnés (gitignorés)

- `bench_parallel.json`, `bench_serial.json` : sorties du benchmark P6.7 (déterminisme) ; recette de
  régénération dans `P6_7_multiprocessing_benchmark.md`.
- `funding_history_*.json` : dumps bruts Kraken Futures (obsolètes).

### À venir

- `P7_phase2_walk_forward.json`, `P7_final_selection.json`, `P7_optimization_report.md` : produits par
  `scripts/run_p7_grid_search.py --phase 2` / `--phase report` — non lancés (rejoués en B4).
- `B4_bybit_backtest_report.md` : livrable de B4.

### Scripts qui écrivent encore dans `results/`

`scripts/p6_5_diagnose_dca.py`, `p6_5_diagnose_filters.py`, `filter_p6_survivors.py` et
`generate_p6_report.py` écrivent aux anciens chemins (`results/P6_5_diagnostic_*.md`,
`results/P6_phase_e_filtering.md`, `results/P6_backtest_report.md`). Non modifiés en B0.5 (gel du code) :
relancer l'un d'eux recrée un fichier à la racine, à déplacer ou à renommer (B4 les fera pointer vers
des noms `B4_*`).

## `results/archive/` (23 fichiers, contexte historique)

| Fichier | Date | Contexte |
|---|---|---|
| `binance_integration_audit.md` | 2026-04 | Audit P0 du pivot Kraken → Binance. Obsolète depuis la suspension UE (2026-07-01), mais documente l'origine des 8.7M rows |
| `P6_backtest_report.md` | 2026-04 | Rapport P6 v1, remplacé par `P6_backtest_report_v2.md` |
| `P6_phase_d_results_v1.json` | 2026-04 | Résultats P6 v1 (avant fix grid) |
| `P6_5_diagnostic_dca.md` | 2026-04 | P6.5 : diagnostic 0 trade DCA sur ETH/SOL |
| `P6_5_diagnostic_gemini.md` | 2026-04 | P6.5 : diagnostic stratégies Gemini (KILL 1A) |
| `P6_5_diagnostic_grok_trend.md` | 2026-04 | P6.5 : diagnostic filtres trend Grok |
| `P6_5_grid_fix_verification.md` | 2026-04 | P6.5 : vérification du fix grid ATR v4 |
| `P6_phase_e_filtering.md` | 2026-04 | P6 phase E : application des critères (0 survivant) |
| `backtest_phase1a_results.md` | 2026-03 | Phase 1A (Kraken) : KEEP grid_atr_v4 / dca / supertrend, KILL retour_moyenne / scalping / suivi_tendance |
| `backtest_new_strategies_results.md` | 2026-03 | Phase 1B (Kraken) : donchian WATCH, ichimoku / vwap KILL |
| `backtest_multipair_results.md` | 2026-04 | Premiers backtests ETH/SOL (SuperTrend universel, DCA bug) |
| `audit_p0_results.md` | 2026-04 | Audit P0 code (pré-abstraction) |
| `kraken_futures_audit.md` | 2026-04 | Audit Kraken Futures (connecteur supprimé en B0.5) |
| `kraken_futures_integration_results.md` | 2026-04 | Intégration Kraken Futures (supprimée en B0.5) |
| `paper_trading_debug.md` | 2026-04 | Debug paper trading Binance |
| `telegram_alerts_results.md` | 2026-04 | Validation alertes Telegram (v1.2.0) |
| `cicd_fix_results.md` | 2026-04 | Fix CI/CD (v1.4.0) |
| `dca_fix_results.md` | 2026-04 | Fix DCA weekly |
| `fix_dca_cleanup_results.md` | 2026-03 | Cleanup DCA |
| `consolidation_results.md` | 2026-03 | Consolidation des stratégies |
| `cleanup_report.md` | 2026-03 | Cleanup repo (époque Kraken) |
| `lint_report.md` | 2026-03 | Rapport lint (époque Kraken) |
| `test_report.md` | 2026-03 | Rapport tests (époque Kraken) |
