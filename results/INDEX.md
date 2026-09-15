# results/ — Index

> Une ligne par fichier conservé : date, phase, verdict, pourquoi il est encore là.
> Tout ce qui n'est plus une référence courante est dans `results/archive/` (rien n'est supprimé).
> Dernière mise à jour : 2026-09-15 (B4.3 campagne P6/P7 — rapport B4, en review).

## Fichiers de référence (à la racine de `results/`)

| Fichier | Date | Phase | Verdict / contenu | Pourquoi il reste |
|---|---|---|---|---|
| `B4_bybit_backtest_report.md` | 2026-09-15 | **B4 — livrable** | Verdict B4 : **0 / 24** en P6, **0 / 35** configs P7 sous fees Bybit, données end-stampées, grid honnête → **sélection paper vide, argumentée** ; encadré « non comparable », couverture SOL chiffrée par fenêtre (train 64.6 % / w1-w3 26-76 %), P6 et P7 avec le nombre de trades à côté de chaque métrique, benchmarks avec règle de lecture (Sharpe → B&H, return/MaxDD → DCA), flags et inéligibilité (dette 14), risk révisé pour B5, annexes | **Livrable B4** (ROADMAP § B4) ; entrée de B5 |
| `B4_P7_phase1_cross_validate.json` · `B4_P7_phase2_walk_forward.json` · `B4_P7_optimization_report.md` · `B4_P7_final_selection.json` · `B4_P7_checkpoint.md` | 2026-09-15 | B4.3 campagne P7 | 212 configs (SuperTrend 60, Grid 96, DCA 48, Donchian 8) cross-validées 70/30 puis 280 fenêtres walk-forward (top-5 × 8) sous fees Bybit : **0 / 35** configs agrégées passent les 7 critères ; `selected_for_paper = []`, 7 combos abandonnés, **5 configs inéligibles** (grid × SOL flaggé, règle GO P7 n° 1), 204 runs flaggés ; checkpoints phase 1 / phase 2 avec anomalies expliquées | Résultats bruts et sélection machine (`effective_params` par entrée) ; contrat de lecture B5 |
| `B4_P6_phase_d_results.json` · `B4_P6_phase_e_filtering.md` · `B4_P6_phase_e_survivors.json` · `B4_P6_phase_f_walkforward.json` · `B4_P6_backtest_report.md` · `B4_P6_checkpoint.md` | 2026-09-15 | B4.3 campagne P6 | 24 combos (8 × 3) sous **fees Bybit** (maker/taker par site de fill), coûts par paire, plancher 5 USDC, moteur grid honnête : **0 / 24** passent les 5 critères stricts (meilleur Sharpe test `grok_supertrend_4h` ETH 0.29, 13 trades) ; survivants `{}` et walk-forward `{}` (normal, voir note) ; **3 runs flaggés** grid × SOL (mauvais pop, dette 14) ; checkpoint validé par Bruno (GO P7) | Résultats bruts et verdict P6 de la campagne B4 ; `effective_params` et blocs `liquidation` par entrée |
| `B4_benchmarks.json` | 2026-09-15 | B4.3 campagne | B&H et DCA fixe 15 USDC/semaine sous `--fees bybit` + coûts par paire : B&H Sharpe 0.84 / 0.38 / 0.30, return +137.5 / +12.5 / −20.4 % ; DCA return +20.9 / −18.3 / −42.9 % (Sharpe DCA 2.1-2.4 **non comparable**, MaxDD 100 % artefact — rapport B4 § 5) | Benchmarks du critère P7 n° 7 et du rapport B4 |
| `B4_3_chantier0_gate_a.md` | 2026-09-14 | B4.3 chantier 0 | **Moteur grid honnête** : liquidation terminale atteignable (MARKET au dernier close, taker + spread + slippage, soldes réglés), `net_pnl` compte chaque fee une fois dans les deux moteurs ; garde signal bit-exacte sauf `net_pnl` (delta = Σ fees vente prouvé), run grid P6 réconcilié 37/37 contre le baseline B4.2 (revue adversariale du diff : 4 défauts corrigés avant soumission) (33 lots liquidés −227 USDC, PF inf → 1.66, `net_pnl` 336 → 129 = `ending − 1000`), gold hashes H1/H2, preuve D4 | Livrable GATE A ; contrat de la campagne B4.3 |
| `b4_3_step0_baselines.txt` · `b4_3_validation_outputs.txt` · `b4_3_guard_signal_outputs.txt` · `b4_3_net_pnl_identity_outputs.txt` | 2026-09-14 | B4.3 chantier 0 | Baselines HEAD (mypy 64, 1 300 passés) + sha256 des logs P6 ; validation 7.4 (3 ordres, ruff, mypy, déterminisme) ; sorties brutes de la garde d) amendée (diff de logs = 2 lignes `net_pnl`, `compare --ignore`, `verify-fees`, identités) ; évidence formule vs cash ≤ 1.6e-23 sur les 6 dumps (GO GATE A point 2) | Preuves GATE A |
| `b4_3_ref_signal_A_post.txt` · `b4_3_ref_signal_A_post_trades.json` · `b4_3_bybit_signal_A_post.json` | 2026-09-14 | B4.3 chantier 0 | Rejeu signal A post-chantier 0 (log normalisé, dumps `--trades-out` binance et bybit) : identiques aux références B4.2 sauf `metrics.net_pnl` (+1.7445 / +5.8128 = Σ fees vente) | Nouvelles références signal (`net_pnl` unifié) |
| `b4_3_ref_grid_A_post.json` · `b4_3_ref_grid_A_post_trades.json` · `b4_3_ref_grid_A_post.report.txt` · `b4_3_bybit_grid_A_post.json` | 2026-09-14 | B4.3 chantier 0 | Grid ATR v4 BTC période P6 avec liquidation terminale : 2 097 trades B4.2 bit-identiques + 33 liquidations taker (binance : PF 1.6555, `net_pnl` 128.87, ending 1 128.87 ; bybit : PF 1.617, `net_pnl` 114.21) ; log brut 130 Mo non versionné (sha256 dans `b4_3_step0_baselines.txt`) ; deux captures identiques | **Nouvelles références grid** (supersèdent `b4_2_ref_grid_A_head.*`) ; baseline de la campagne |
| `b4_3_ref_grid_quick_post.json` · `b4_3_ref_grid_quick_post_trades.json` · `b4_3_bybit_grid_quick_post.json` | 2026-09-14 | B4.3 chantier 0 | Fenêtre gold hash (2025-03-01 → 03-15) avec liquidation : 45 BUY / 37 SELL maker / 8 liquidations, PF 1.2125 (binance) / 1.1552 (bybit) | Cibles rapides des hashes H1/H2 |
| `B4_3_gate_b_configs.md` · `q3_orderbook.jsonl` | 2026-09-15 | B4.3 GATE B | Configs de campagne validées (GO B) : coûts par paire dérivés des 126 mesures de carnet Bybit EU (`q3_orderbook.jsonl`, 14-15/09) → `config/pair_costs_b4.json` (BTC 2/2 bps, ETH 3/2, SOL 11/2), risk mapping (défauts de classe conservés, dette 13), `--min-order-usdc 5`, grilles P7 (plancher 2.0 %), serveur, sorties `B4_*` | Contrat de la campagne ; source des coûts |
| `B4_2_fees_engine_report.md` | 2026-09-14 | B4.2 | **Modèle de fees maker/taker découplé de la source de données** (`--fees` obligatoire) : table de classification des sites de fill, chemins morts prouvés, cause racine dotenv + `ResourceWarning`, régression iso-fees bit-exacte, validations | Source de la résolution des dettes 2 et 9 ; prérequis de B4.3 |
| `b4_2_ref_signal_A_head.txt` · `b4_2_ref_signal_A_head.json` | 2026-09-14 | B4.2 étape 0 | Run A (`grok_supertrend_4h` BTC, période P6, 5m) sur le moteur HEAD intact : log complet + capture JSON pleine précision (92 fills, +2.42 %) ; log normalisé identique à `b4_reference_backtest_A_p6period.txt` (serveur) | Cible bit-exacte du rejeu `--fees binance` |
| `b4_2_ref_grid_quick_head.txt` · `b4_2_ref_grid_quick_head.json` | 2026-09-14 | B4.2 étape 0 | Grid ATR v4 BTC sur la fenêtre du gold hash (2025-03-01 → 03-15) : 45 BUY / 37 SELL, 0 liquidation forcée (moteur biaisé) | **Supersédée par B4.3** (`b4_3_ref_grid_quick_post.*`) ; baseline de la réconciliation GATE A |
| `b4_2_ref_grid_A_head.json` · `b4_2_ref_grid_A_head.report.txt` | 2026-09-14 | B4.2 étape 0 | Grid ATR v4 BTC période P6 (2 097 fills, 1 032 paires, +12.95 %, 0 liquidation forcée = biais de survie, 33 positions ouvertes non liquidées) : capture JSON + bloc rapport ; log brut (130 Mo) non versionné | **Supersédée par B4.3** (`b4_3_ref_grid_A_post.*`) ; baseline de la réconciliation GATE A (préfixe bit-identique des 2 097 trades) |
| `b4_2_validation_outputs.txt` | 2026-09-14 | B4.2 | Sorties brutes des validations 7.1 (diffs vides des 3 rejeux `--fees binance` + rejeux par commit), 7.3 (exit 2 sans `--fees`), 7.4 (3 ordres : 1 300 passés / 0 échec / 0 error + déterminisme), 7.5 (ruff, mypy 64), 7.6 (grep), caractérisation du `ResourceWarning` | Preuves du rapport B4.2 |
| `b4_2_bybit_signal_A.json` · `b4_2_bybit_grid_quick.json` · `b4_2_bybit_grid_A.json` | 2026-09-14 | B4.2 | Dumps `--trades-out` sous `--fees bybit` (moteur final) : chaque trade avec liquidité, taux, base, prix de référence, spread/slippage ; `verify-fees --fees bybit` OK | Preuve trade par trade (validation 7.2) ; premiers chiffres Bybit bruts pour B4.3 |
| `b4_2_step0_baselines.txt` | 2026-09-14 | B4.2 étape 0 | Baselines qualité (mypy 64, ruff format, suite pré-fix 4 failed + 1 error, texte du `ResourceWarning`, sha256 grid) | Référence des validations 7.4-7.5 |
| `B4_1_timestamp_restamp_report.md` | 2026-09-13 | B4.1 | **Re-stamp des 8 712 718 rows Binance en fin de période** (open time → `open + interval`) : audit, 3 gates, exécution serveur (2 550 fenêtres, 0 collision), invariants, audit v2 (vote OHLC, règles A/B, vue virtuelle), backtest de référence différent du baseline P6 | Source de la résolution de la dette 11 ; prérequis de validité de B4.2/B4.3 |
| `b4_binance_stamp_boundaries.json` | 2026-09-13 | B4.1 | Manifeste des frontières (21 séries, `last_open_stamped_ts`, counts, trous, rows à revérifier), sha256 `eb62eab6…` | Source de vérité du périmètre migré ; entrée des rejeux d'audit |
| `b4_timestamp_audit_pre_migration.txt` · `b4_restamp_dryrun_tunnel.txt` · `b4_restamp_dryrun_server.txt` · `b4_restamp_execute_server.txt` · `b4_restamp_ledger_server.jsonl` | 2026-09-13 | B4.1 | Sorties brutes : audit pré-migration, dry-runs (tunnel + serveur), exécution, ledger des 2 550 fenêtres | Preuves GATE 1/2 |
| `b4_timestamp_audit_post_migration.txt` (v1 strict, exit 1) · `b4_timestamp_audit_post_migration_v2.txt` · `b4_timestamp_audit_premigration_view_v2.txt` (+ `_v21` portée spec/all) | 2026-09-13 | B4.1 | Rejeux post-migration : v1 strict (6 résidus, evidence conservée), v2 (règles A/B, sensibilité) dans les deux sens | Invariant 1 et décision GATE 3 |
| `b4_reference_backtest_A_p6period.txt` · `b4_reference_backtest_B_brief.txt` | 2026-09-13 | B4.1 | Backtest de référence `grok_supertrend_4h` BTC après re-stamp (A : période/pas P6 ; B : commande littérale du brief) | Invariant 6 ; delta brut pour B4.3 |
| `B3_bybit_data_report.md` | 2026-09-11 | B3 | **Historique Bybit EU en DB** (3 paires × 7 TF depuis 2025-06-11), backfill de gaps démontré avant l'import, scheduler actif ; cohérences 1d/1w (décalage d'un intervalle attendu), prix 1h, WS/REST ; **constat** convention Binance open-stamped → dette B4 | Preuve des données live Bybit, sorties SQL brutes, décisions de convention (source de la dette 11) |
| `bybit_integration_audit.md` | 2026-09-07 | B0 | **GO avec réserves** : instance EU séparée (`api.bybit.eu`), fees 0.10/0.25, historique EU depuis 2025-06-11, corrélation prix Binance/Bybit 0.999999, clés API non vérifiées | Source des constantes B1–B3 (`skills/bybit.md`) et de la décision « données Binance + fees Bybit » |
| `P7_phase1_cross_validate.json` | 2026-05-30 | P7 phase 1 | 212 jobs de grid search cross-validés 70/30 (grid ATR v4, SuperTrend, DCA, Donchian), **fees Binance 0.075 % flat**, données open-stampées, grid biaisé — **supersédé par `B4_P7_phase1_cross_validate.json`** | Contexte historique du rapport B4 (§ 1 « non comparable ») ; jamais réécrit (`--force` interdit) |
| `P6_backtest_report_v2.md` | 2026-04-19 | P6 | 24 combos (8 stratégies × 3 paires, 2023-04 → 2026-04, cross-validate) : **0/24 passent les 5 critères stricts** ; recommandations par stratégie | Rapport P6 de référence (v1 archivée) |
| `P6_phase_d_results.json` | 2026-04-19 | P6 phase D | Résultats bruts des 24 backtests (train / test / all, fees Binance, open-stampés) — **supersédé par `B4_P6_phase_d_results.json`** | Contexte historique du rapport B4 § 3.3 (deltas signés) ; jamais réécrit |
| `P6_benchmarks.json` | 2026-04-19 | P6 | Buy & Hold et DCA fixe 15 USDC/semaine par paire (Sharpe, return), sans fee, open-stampé — **supersédé par `B4_benchmarks.json`** | Référence Binance historique |
| `P6_data_coverage.md` | 2026-04-16 | P6 | Couverture des 8.7M rows Binance par paire × TF (min/max date, gaps) | Preuve de la base de données de backtest |
| `P6_7_multiprocessing_benchmark.md` | 2026-05-20 | P6.7 | Timings 24 combos série vs parallèle (8 workers), déterminisme validé | Tuning du runner pour B4 (workers, RAM, temps attendu) |
| `P6_phase_e_survivors.json` | 2026-04-19 | P6 phase E | `{}` | Voir note ci-dessous |
| `P6_phase_f_walkforward.json` | 2026-04-19 | P6 phase F | `{}` | Voir note ci-dessous |

**Note obligatoire — `P6_phase_e_survivors.json` / `P6_phase_f_walkforward.json` et leurs jumeaux
`B4_P6_phase_e_survivors.json` / `B4_P6_phase_f_walkforward.json` contiennent `{}`.** C'est **normal** : 0 combinaison
sur 24 a passé les critères P6, en avril (fees Binance) comme en B4 (fees Bybit), donc zéro survivant en phase E et
pas de walk-forward en phase F. Ce ne sont pas des fichiers corrompus.

### Fichiers locaux non versionnés (gitignorés)

- `bench_parallel.json`, `bench_serial.json` : sorties du benchmark P6.7 (déterminisme) ; recette de
  régénération dans `P6_7_multiprocessing_benchmark.md`.
- `funding_history_*.json` : dumps bruts Kraken Futures (obsolètes).

### À venir

- `P7_phase2_walk_forward.json`, `P7_final_selection.json`, `P7_optimization_report.md` (fees Binance) : jamais
  produits — la phase 2 et le rapport P7 n'existent que sous fees Bybit (`B4_P7_*`, campagne B4.3).

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
