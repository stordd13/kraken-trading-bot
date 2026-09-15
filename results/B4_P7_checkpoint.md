# B4 — CHECKPOINT P7 (phase 1 → phase 2 → rapport)

Serveur `krakenbot`, branche `feat/b4-3-campaign`, tmux `b4`, 3 workers `nice -n 10`, `--fees bybit --pair-costs-file
config/pair_costs_b4.json --min-order-usdc 5 --timeout 5400`. Résumés produits par `scripts/audit/b4_p7_checkpoint.py`
(lecture seule) sur les fichiers rapatriés (sha256 identiques au serveur).

## Phase 1 — `eb13800`, calibration `--limit 3` 10:41:06 → 10:44:43 (3 min 36), 209 jobs 10:45:43 → 12:36:32 (1 h 51)

1. Completion (phase 1): 212/212 jobs succeeded, 0 crashed, 0 missing — per strategy: grok_adaptive_dca_weekly 48, grok_donchian_breakout_4h 8, grok_grid_atr_adaptive_v4 96, grok_supertrend_4h 60
2. Campaign signature (fees, pair_costs_file, min_order_usdc): ('bybit', 'config/pair_costs_b4.json', 5.0) x212
3. Flag rule: 144 flagged run(s) → 48 ineligible config(s) (GO P7 rule 1) — the 48 grid × SOL configs, 3 segments (train/test/all) each; full list in B4_P7_optimization_report.md § Flagged runs
4. Anomalies (0 trades / PF inf / |return| > 200 % / MaxDD > 60 % / too good / liquidation in profit): 0 — none
5. Best test Sharpe per combo (Sharpe / PF / return, n trades; train Sharpe, n): grok_adaptive_dca_weekly×BTC: -0.42 / 0.00 / -1.3% (n=11; train 1.35, n=35) params {'oversold_multiplier': 3.0, 'bull_reduction': 0.3, 'rsi_oversold': 35}; grok_donchian_breakout_4h×SOL: 0.13 / 1.48 / +0.3% (n=9; train -0.44, n=16) params {'donchian_upper_period': 30, 'breakout_confirmation': 'close'}; grok_grid_atr_adaptive_v4×BTC: -0.01 / 0.79 / -1.4% (n=71; train 0.09, n=185) params {'min_spacing_pct': 0.03, 'atr_multiplier': 1.5, 'bear_protection_mode': '1w_only'}; grok_grid_atr_adaptive_v4×SOL: -0.02 / 0.67 / -7.8% (n=224; train 0.08, n=576) params {'min_spacing_pct': 0.03, 'atr_multiplier': 3.0, 'bear_protection_mode': 'none'}; grok_supertrend_4h×BTC: 0.16 / 1.57 / +0.3% (n=9; train 0.22, n=37) params {'st_atr_period': 10, 'st_multiplier': 3.0}; grok_supertrend_4h×ETH: 0.78 / 3.01 / +3.0% (n=18; train -0.07, n=48) params {'st_atr_period': 20, 'st_multiplier': 2.0}; grok_supertrend_4h×SOL: 0.21 / 1.59 / +0.8% (n=10; train 0.11, n=16) params {'st_atr_period': 10, 'st_multiplier': 3.0}
6. Phase-1 configs clearing criteria 1-2-4 on the single 70/30 test split (informational, the verdict is phase 2): 1 — grok_supertrend_4h_ETH_USDC_p1_2deb09d8
7. Grid liquidations: 288 segments, lots min/max 2/72, pnl min/max -764.95/-2.61, 0 with empty inventory, 144 not reconciled — the 144 SOL segments (all 48 configs)
8. Test Sharpe distribution per strategy (min / median / max over its jobs): grok_adaptive_dca_weekly: -1.24 / -1.21 / -0.42 (48 jobs); grok_donchian_breakout_4h: -0.43 / -0.23 / 0.13 (8 jobs); grok_grid_atr_adaptive_v4: -0.07 / -0.05 / -0.01 (96 jobs); grok_supertrend_4h: -0.52 / -0.01 / 0.78 (60 jobs)
9. Jobs per pair: BTC/USDC 116, ETH/USDC 20, SOL/USDC 76
10. Verdict: phase 1 complete → phase 2; STOP if any crash / flag / anomaly above is unexplained

## Phase 2 — `a59226f`, 280 fenêtres 12:38:44 → 13:03:34 (25 min) ; rapport 13:12:25 → 13:12:27

1. Completion (phase 2): 280/280 jobs succeeded, 0 crashed, 0 missing — per strategy: grok_adaptive_dca_weekly 40, grok_donchian_breakout_4h 40, grok_grid_atr_adaptive_v4 80, grok_supertrend_4h 120
2. Campaign signature (fees, pair_costs_file, min_order_usdc): ('bybit', 'config/pair_costs_b4.json', 5.0) x280
3. Flag rule: 60 flagged run(s) → 5 ineligible config(s) (GO P7 rule 1) — grok_grid_atr_adaptive_v4×SOL#50614027 (11 flag(s): test, train); grok_grid_atr_adaptive_v4×SOL#5958d056 (12 flag(s): test, train); grok_grid_atr_adaptive_v4×SOL#b054321f (13 flag(s): test, train); grok_grid_atr_adaptive_v4×SOL#ba542585 (12 flag(s): test, train); grok_grid_atr_adaptive_v4×SOL#df1cc242 (12 flag(s): test, train)
4. Anomalies (0 trades / PF inf / |return| > 200 % / MaxDD > 60 % / too good / liquidation in profit): 108 — 27 × PF inf (grid windows without a losing pair: 13 with an empty terminal inventory, 14 with 1-2 lots liquidated above cost), 14 × liquidation pnl positive (+0.58 to +0.73 USDC, 1-2 lots, close 1.2-2.5 % above entry, arithmetic verified), 66 × 0 trades (3-month test windows of the low-frequency strategies: DCA 35/40 tests, SuperTrend 17/120, Donchian 6/40; DCA train 8/40) — explained, not bugs (reading below)
5. Best mean OOS Sharpe per combo (Sharpe / PF / MaxDD, consistency, mean n trades; train Sharpe): grok_adaptive_dca_weekly×BTC: -0.13 / 0.00 / 2.0% (0/8, n=2; train 0.98) params {'oversold_multiplier': 3.0, 'bull_reduction': 0.3, 'rsi_oversold': 35}; grok_donchian_breakout_4h×SOL: -0.29 / 0.24 / 1.4% (2/8, n=3; train -0.55) params {'donchian_upper_period': 20, 'breakout_confirmation': 'close'}; grok_grid_atr_adaptive_v4×BTC: 0.04 / 2.26 / 3.5% (6/8, n=18; train 0.08) params {'min_spacing_pct': 0.03, 'atr_multiplier': 3.0, 'bear_protection_mode': '1w_only'}; grok_grid_atr_adaptive_v4×SOL: 0.04 / 3.71 / 16.3% (5/8, n=77; train 0.09) params {'min_spacing_pct': 0.03, 'atr_multiplier': 3.0, 'bear_protection_mode': 'none'} [flagged→ineligible]; grok_supertrend_4h×BTC: -0.12 / 0.83 / 1.1% (3/8, n=4; train 0.29) params {'st_atr_period': 7, 'st_multiplier': 3.0}; grok_supertrend_4h×ETH: -0.10 / 0.91 / 1.5% (2/8, n=4; train 0.14) params {'st_atr_period': 7, 'st_multiplier': 2.0}; grok_supertrend_4h×SOL: -0.16 / 0.89 / 1.1% (2/8, n=3; train 0.14) params {'st_atr_period': 10, 'st_multiplier': 3.0}
6. 7 criteria (unchanged, GO P7 rule 3) over 35 aggregated configs: 0 passing, 0 passing AND eligible — none
7. Grid liquidations: 160 segments, lots min/max 0/27, pnl min/max -217.34/+0.73, 13 with empty inventory, 60 not reconciled — the 60 SOL segments of the 5 SOL configs
8. Test Sharpe distribution per strategy (min / median / max over its jobs): grok_adaptive_dca_weekly: -1.06 / 0.00 / 0.00 (40 jobs); grok_donchian_breakout_4h: -1.66 / -0.31 / 0.72 (40 jobs); grok_grid_atr_adaptive_v4: -0.10 / 0.05 / 0.18 (80 jobs); grok_supertrend_4h: -2.16 / -0.19 / 1.95 (120 jobs)
9. Jobs per pair: BTC/USDC 120, ETH/USDC 40, SOL/USDC 120
10. Verdict: phase 2 complete → report; STOP if any crash / flag / anomaly above is unexplained

## Lecture

- **Complétude** : 212/212 et 280/280, 0 crash, signature de campagne uniforme, reprise jamais nécessaire, jamais de
  `--force`. Disque 58 G libres avant / après ; log filtré `logs/b4_p7.log` 1.8 Mo ; collector `active` sans
  interruption (compteurs cumulés du journal inchangés : 1 erreur, 7 reconnexions depuis le 13/09) ; tmux `spread`
  intact ; aucun process orphelin.
- **Flags (règle GO GATE A) → inéligibilité (règle GO P7 n° 1)** : phase 1, **les 48 configs grid × SOL sont flaggées**
  sur leurs 3 segments (144 runs) — le « mauvais pop » de la tolérance de fermeture absolue est systématique sur SOL
  quelle que soit la config (spacing 1.5-3 %, ATR 1.5-3, protection bear) ; phase 2, les 5 configs SOL du top-5 sont
  flaggées sur 60 fenêtres/segments. Les 48 configs BTC réconcilient toutes (288 + 100 segments, divergence ≤ 1e-28).
  `B4_P7_final_selection.json` : `ineligible_flagged` = 5, `flagged_runs` = 204, `selected_for_paper` = **[]**.
- **Anomalies phase 2 — expliquées avant acceptation** : (a) PF `inf` sur 27 fenêtres grid = aucune paire perdante
  dans la fenêtre (13 finissent inventaire vide, 14 finissent avec 1-2 lots liquidés **au-dessus** du coût : ex.
  `9d3bf21b` w1 train, 2 lots de 24.98 USDC liquidés à 71 279.48 = 71 308 × (1 − 0.0004), produit net 50.53, P&L
  +0.58 = +1.16 % — la fenêtre se termine en tendance haussière au milieu d'un cycle, la liquidation est valorisée au
  close moins taker + coûts, ce n'est pas une survalorisation) ; l'agrégateur P7 (`_safe_float`) compte un PF `inf`
  comme 0 dans le PF moyen — conservateur, sans effet sur le verdict (Sharpe OOS 0.04 ≪ 0.4) ; (b) 66 segments à
  0 trade = fenêtres test de 3 mois des stratégies lentes (DCA 35/40, SuperTrend 17/120, Donchian 6/40) : c'est le
  critère n° 4 (≥ 20 trades/fenêtre) qui les sanctionne, pas un bug.
- **Verdict des 7 critères (inchangés, règle n° 3)** : **0 / 35 configs agrégées** ne passent, 0 éligible → **0 sélection
  paper**. Meilleur Sharpe OOS moyen par combo : grid BTC 0.04 (PF 2.26, MaxDD 3.5 %, 6/8, 18 trades/fenêtre, ratio
  OOS/train 0.49) ; grid SOL 0.04 (inéligible) ; SuperTrend −0.12 / −0.10 / −0.16 (BTC / ETH / SOL, 3-4 trades par
  fenêtre, cohérence 2-3/8) ; DCA −0.13 (1.5 trade/fenêtre) ; Donchian −0.29. La famille SuperTrend ETH mult 2.0, seule
  à « sauver » son défaut en phase 1 (test 0.78 / 3.01 / +3.0 %, 18 trades), tombe à −0.10 en walk-forward : son
  score phase 1 tenait au seul segment test 2025-05 → 2026-04.
- **Réponse à la question P7** : aucune config ne sauve une stratégie que sa config par défaut condamne.
