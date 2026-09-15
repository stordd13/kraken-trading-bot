# B4 — CHECKPOINT post-P6

1. Completion: 24/24 combos succeeded, 0 crashed, 0 missing
2. Campaign signature (fees, pair_costs_file, min_order_usdc): ('bybit', 'config/pair_costs_b4.json', 5.0) x24
3. Survivors (5 strict criteria + consistency + benchmark): 0 — none
4. Best test Sharpe: grok_supertrend_4h_ETH_USDC Sharpe 0.29 PF 1.53 ret +1.2% trades 13; grok_supertrend_4h_SOL_USDC Sharpe 0.21 PF 1.59 ret +0.8% trades 10; grok_supertrend_4h_BTC_USDC Sharpe 0.16 PF 1.57 ret +0.3% trades 9
5. Flag rule (divergence / formula vs cash): 3 flagged — grok_grid_atr_adaptive_v4_SOL_USDC/train: inventory divergence -0.025647635176225406481895346 BTC; net_pnl 480.5454113897327 != lot basis 484.3079194700849573245609320 (formula vs cash); grok_grid_atr_adaptive_v4_SOL_USDC/test: inventory divergence -0.005809007961228377788323002 BTC; net_pnl -444.3962523855874 != lot basis -443.6526993665501604597355850 (formula vs cash); grok_grid_atr_adaptive_v4_SOL_USDC/all: inventory divergence -0.033472291971067908103841611 BTC; net_pnl 309.7712599076728 != lot basis 313.6339624011340646958120296 (formula vs cash)
6. Anomalies: 3 — grok_adaptive_dca_weekly_ETH_USDC/train: MaxDD 63.2%; grok_adaptive_dca_weekly_ETH_USDC/all: MaxDD 62.2%; grok_adaptive_dca_weekly_SOL_USDC/all: MaxDD 66.6%
7. Grid liquidations: 9 segments — grok_grid_atr_adaptive_v4_BTC_USDC/train: 6 lots pnl -9.58 fees 0.35 residual 0 div -2E-30; grok_grid_atr_adaptive_v4_BTC_USDC/test: 33 lots pnl -202.07 fees 1.56 residual 0 div 0E-30; grok_grid_atr_adaptive_v4_BTC_USDC/all: 33 lots pnl -228.12 fees 1.49 residual 0 div -4E-30; grok_grid_atr_adaptive_v4_ETH_USDC/train: 50 lots pnl -401.14 fees 2.12 residual 0 div -6E-28; grok_grid_atr_adaptive_v4_ETH_USDC/test: 44 lots pnl -439.50 fees 1.65 residual 0 div 3E-28; grok_grid_atr_adaptive_v4_ETH_USDC/all: 56 lots pnl -475.77 fees 2.31 residual 0 div -7E-28; grok_grid_atr_adaptive_v4_SOL_USDC/train: 29 lots pnl -178.74 fees 1.36 residual 0 div -0.025647635176225406481895346; grok_grid_atr_adaptive_v4_SOL_USDC/test: 47 lots pnl -624.80 fees 1.37 residual 0 div -0.005809007961228377788323002; grok_grid_atr_adaptive_v4_SOL_USDC/all: 45 lots pnl -577.73 fees 1.36 residual 0 div -0.033472291971067908103841611
8. Failure reasons (first token): Sharpe x24, Sortino x24, Does x24, Calmar x22, PF x20, Trades x15, Overfit x9, MaxDD x4
9. Per strategy (test Sharpe/PF per pair): gemini_retour_moyenne: BTC -0.20/0.19, ETH -0.20/0.11, SOL -0.13/0.37; gemini_scalping_volatilite: BTC -0.70/0.15, ETH -0.59/0.28, SOL -0.71/0.23; gemini_suivi_tendance_momentum: BTC -0.14/0.16, ETH -0.04/0.66, SOL -0.10/0.39; grok_adaptive_dca_weekly: BTC -1.20/0.00, ETH -0.56/0.00, SOL -1.14/0.00; grok_donchian_breakout_4h: BTC -0.22/0.60, ETH 0.06/1.10, SOL -0.23/0.69; grok_ema_adx_atr: BTC -0.07/0.00, ETH 0.11/4.00, SOL -0.15/0.32; grok_grid_atr_adaptive_v4: BTC -0.03/0.46, ETH -0.05/0.30, SOL -0.06/0.31; grok_supertrend_4h: BTC 0.16/1.57, ETH 0.29/1.53, SOL 0.21/1.59
10. Verdict for P7: 0 survivors → P7 on the 4 historical grid-search strategies (brief § 6.2); STOP if any crash / flag / anomaly above is unexplained

## Lecture (Bruno — GO/STOP avant P7 phase 1)

**Contexte d'exécution** : serveur `krakenbot`, branche `feat/b4-3-campaign` @ `874fb62` (+ `77918e3` audit), tmux `b4`,
3 workers `nice -n 10`, `--fees bybit --pair-costs-file config/pair_costs_b4.json --min-order-usdc 5 --timeout 5400`,
sortie `results/B4_P6_phase_d_results.json` (24 entrées, signature de campagne uniforme). **Durées** : calibration
`--limit 3` (les 3 grids) 08:01:26 → 08:05:18 = **3 min 52** ; les 21 autres combos 08:07:27 → 08:17:21 = **10 min** ;
total P6 ≈ 22 min (vs ≈ 2.5 h estimées : la DB locale supprime la latence du tunnel qui dominait le benchmark P6.7).
Disque 58 G libres avant/après ; log filtré `logs/b4_p6.log` 10.8 Mo ; collector `active` sans interruption
(29 candles 1 m / paire sur 07:50-08:18, 0 trou, pas de reconnexion dans le journal) ; aucun process orphelin ; tmux `spread`
intact.

**Incidents de lancement (corrigés, consignés GATE B § 4)** : (1) le shell interactif du serveur exporte
`SCHEDULER_PAIRS` sans guillemets (`~/.bashrc` fait `set -a; source .env`) → `SettingsError` dans les workers ; les scripts
de run font `unset SCHEDULER_PAIRS SCHEDULER_INTERVALS` ; (2) `LOG_LEVEL=WARNING` n'est pas honoré par les scripts
(`get_logger()` ne reconfigure pas le niveau) → ~190 Mo/min de logs INFO ; filtre `grep --line-buffered` sur le flux
persisté. Un premier lancement (07:53) a été relancé proprement après ces deux correctifs, sans job comptabilisé.

**Point 3 — 0 survivant** : comme en P6 historique (fees Binance), aucune des 24 combinaisons ne passe les 5 critères
stricts ; le meilleur Sharpe test est `grok_supertrend_4h` ETH 0.29 (PF 1.53, 13 trades). Conséquence brief § 6.2 :
**P7 tourne sur les 4 stratégies historiques du grid search** (SuperTrend, Grid ATR v4, DCA, Donchian) — la question
posée est « une config sauve-t-elle une stratégie que sa config par défaut condamne ? ».

**Point 5 — 3 flags nominatifs, tous `grok_grid_atr_adaptive_v4` × SOL/USDC (train / test / all)** : divergence
d'inventaire −0.0256 / −0.0058 / −0.0335 SOL et `net_pnl` (cash) ≠ lot-basis de −3.76 / −0.74 / −3.86 USDC. Diagnostic
(dump local `--trades-out` du même run `all`, 4 620 trades) : **40 lots vendus deux fois** (39 montants distincts) — le
« mauvais pop » annexé au GATE A : la stratégie ferme la position par proximité de prix (`|sell_level − prix| < 1` USD,
tolérance absolue) alors que le moteur débite par `position_id` ; à ~180 USD le SOL, des cibles SELL à moins de 1 USD
sont fréquentes, jamais sur BTC (divergence 1e-30) et quasi jamais sur ETH (1e-28). Effet : le lot-basis surestime le
P&L de 1.2 % sur `all` ; **le `net_pnl` cash publié est exact** (identité `usdc − capital`), PF/win-rate SOL grid
légèrement optimistes (les lots fantômes ont été liquidés au clamp). Verdict de la règle : run **flaggé, non
invalidé** — le grid SOL ne survit de toute façon pas (Sharpe test −0.06, PF 0.31, MaxDD 58 %). Fix = stratégie
protégée (post-B4, avec la dette 13).

**Point 6 — 3 anomalies MaxDD > 60 %** : `grok_adaptive_dca_weekly` ETH (train 63 %, all 62 %) et SOL (all 67 %) — le DCA
accumule sans jamais vendre : son drawdown est celui de l'actif (ETH −64 % / SOL −70 % en B&H sur la période), attendu
et identique en P6 historique. Pas un bug.

**Grid BTC = référence B4.3** : `all` 1 064 trades, PF 1.617, `net_pnl` 114.21, liquidation −228.12 sur 33 lots —
identique au run de référence bybit du GATE A (mêmes coûts globaux pour BTC) → la chaîne runner = chaîne de référence.

**Benchmarks `--fees bybit`** (`B4_benchmarks.json`) : B&H Sharpe BTC 0.84 / ETH 0.38 / SOL 0.30, DCA fixe 2.35 / 2.09 /
2.08. L'écart avec `P6_benchmarks.json` (0.85 / 0.40 / 0.31 ; 2.37 / 2.10 / 1.93) vient **entièrement du re-stamp B4.1**
(vérifié par un run `--fees none` sur les données actuelles : Sharpe identique à 4 décimales avec ou sans fees, seuls
les returns bougent de ≤ 0.7 pt). Le « MaxDD 100 % » du DCA fixe est un artefact préexistant du script (courbe partant
de 0).

**Estimation P7 révisée** (mesures serveur) : grid ≈ 3.9 min par job (3 segments) à 3 en parallèle, signal ≈ 1.4 min →
phase 1 ≈ 96 × 3.9 / 3 + 116 × 1.4 / 3 ≈ **3 h** (pas 27 h) ; phase 2 (280 fenêtres de 15 mois) ≈ **1 h** ; rapport :
minutes. Disque : négligeable avec le filtre de log.

**Demande** : GO pour P7 phase 1 sur les 4 stratégies historiques (212 jobs, ≈ 3 h), même config de campagne, ou STOP.
