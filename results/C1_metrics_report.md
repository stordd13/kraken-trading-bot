# C1 — Métriques de backtest fiables : rapport A/B et valeurs de référence

> Brief : `agent/chantier1_metriques.md` (v2 + 4 précisions). Plan approuvé le 2026-09-16 (amendements C2-C3, C11,
> C12, C13, étapes 2/4/8). Branche `feat/c1-metrics` depuis `dev` @ `8e327b0` (moteur bit-identique au tag
> `v2.8.0-b4-3-campaign` : `git diff v2.8.0-b4-3-campaign dev -- scripts src tests` vide).
> Sélection paper B4 **inchangée (vide)** : ce chantier répare l'instrument, il ne rejoue aucune campagne.
> État : tableau A/B **approuvé** (GO conditionnel Bruno, 2026-09-16 : invariant MaxDD engine § 4 bis vérifié,
> migration locale appliquée § 7, hashes recalés en C7) ; branche poussée sur `origin`, merge dans `dev` = humain.

## 1. Résumé

- **Un système de mesure unique** : `src/krakenbot/backtest_metrics.py` (`METRICS_VERSION = 2`, pur Python, aucun
  import de `scripts/`), appelé par les deux moteurs (`apply_shared_metrics`) et par `compute_benchmarks.py`.
- **Simulation inchangée au centime** : sur les trois rejeux de référence (signal A, grid quick binance + bybit,
  grid A 3 ans), trades (15 champs pré-C1), soldes finaux et `equity_curve` point à point sont **identiques** entre
  l'ancien moteur (tag) et le nouveau ; toutes les clés « comptables » de `to_dict()` sont identiques ; seuls Sharpe,
  Sortino, MaxDD %, PF et Calmar bougent, chacun avec sa cause (§ 4).
- Défauts corrigés : D1 (rééchantillonnage quotidien, unité unique), D2 (drawdown relatif au pic courant), D3 (PF net
  des deux jambes sans double comptage), D4 (agrégation P7 None-aware sur les sommes), D5 (equity exportée : sidecar
  `--equity-out`, `equity_daily` par segment), D6 (DCA fixe : dépôts = flux externes).
- Conventions figées (C2-C7 du plan) : ancre autoritaire à `t₀`, dernier point gagne entre données, `I₀ = 1`,
  écart-type échantillon partout, Sortino N total, Calmar CAGR géométrique, lots à coût inconnu exclus du PF.
- Tests : 21 cas synthétiques du module (les 8 du brief + bords), 10 tests moteur (`run()` synthétique, sites de
  vente, sidecar, sauvegarde DB par session stub), tests p7_report / runners / outils P6 ; **suite complète hors DB : 1 392 passés, 6 skipped** ; mypy `src/` = 64 erreurs (baseline
  inchangée) ; ruff check / format verts sur les fichiers suivis (hors dette 10 `p6_5_diagnose_*`).
- Les **verdicts B4 (35 configs, 0 sélectionnée) sont reproduits à l'identique** par le chemin legacy v1 de
  `p7_report` (`test_b4_campaign_verdicts_are_reproduced_bit_identically`).

## 2. Défauts → corrections

| # | Défaut (audit red-team 16/09) | Correction C1 | Où |
|---|---|---|---|
| D1 | Sharpe/Sortino `×√365` sur des pas 5 m / 4 h / 1 j | grille quotidienne UTC (`start`, minuits, `end`), rendements quotidiens, `ddof=1`, `None` si indéfini | `backtest_metrics.resample_daily`, `sharpe_ratio`, `sortino_ratio` |
| D2 | MaxDD % = perte max ÷ pic final | drawdown relatif au **pic courant** : `max_drawdown_pct_daily` (critères) + `max_drawdown_pct_engine` (diagnostic) ; `max_drawdown` USDC inchangé | `max_drawdown_pct` |
| D3 | PF sans la fee d'achat | `BacktestTrade.buy_fee_alloc` aux 4 sites de vente, `pnl_net_trade = pnl − buy_fee_alloc`, sommes exportées, `pf_excluded_trades` | `scripts/backtest.py`, `net_trade_pnls` |
| D4 | `_safe_float` → 0, moyenne de PF | `_metric` / `mean_available` (n rapporté), critère 2 sur Σ gains / Σ pertes (∞ passe, 0/0 échoue), `None` échoue avec note | `scripts/p7_report.py` |
| D5 | aucune equity persistée | `--equity-out` (JSONL résolution moteur), `equity_daily` par segment (runners, dump) | `dump_equity_jsonl`, runners |
| D6 | DCA : dépôts comptés comme rendements | compte cash + `ExternalFlow` par dépôt, rendements ajustés, indice de performance | `compute_benchmarks.dca_fixed_weekly` |

Conventions détaillées : `skills/backtest.md` § « Système de mesure unique ».

## 3. Méthodologie A/B

- Harnais : `scripts/audit/c1_equity_probe.py` — `capture` construit le moteur comme le chemin mono-run de
  `backtest.py main()` (mêmes constructeurs que le harnais B4.2) et sérialise le payload schéma 1 **+ `equity_curve`
  verbatim + soldes + extras Decimal (`max_drawdown`, `average_win/loss`)** ; `--engine-root` exécute les moteurs
  d'un autre checkout. `compare-ab` asserte l'identité (trades sur les 15 champs pré-C1, soldes, equity point à
  point, projection schéma 1 hors clés de contrat) et produit le tableau partitionné.
- Étape 0 (commit `3a65e8e`, code intact @ `8e327b0`) : captures `_old` ; chacune **IDENTICAL** à sa référence B4.3
  sur la projection schéma 1 (`b4_3_bybit_signal_A_post.json`, `b4_3_bybit_grid_quick_post.json`,
  `b4_3_ref_grid_quick_post_trades.json`, `b4_3_bybit_grid_A_post.json`). Contre-rejeux depuis un `git worktree` du
  tag (`_wt`, `--engine-root`) : identiques aux captures `dev` (16 clés identiques, `IDENTITY OK`).
- Étape N (moteur C1, commit `76bde08`) : captures `_new` + dumps `--trades-out --equity-out` (`verify-fees --fees
  bybit` : OK sur les deux dumps).
- Commandes : signal A `grok_supertrend_4h BTC/USDC 2023-04-01 → 2026-04-01 --interval 5 --capital 1000 --fees
  bybit` ; grid quick `grok_grid_atr_adaptive_v4 BTC/USDC 2025-03-01 → 03-15` (binance et bybit) ; grid A idem
  2023-04-01 → 2026-04-01 (bybit, ~25 min, 315 650 points).

| Capture | sha256 (16) |
|---|---|
| `c1_ab/signal_A_bybit_old.json` / `_wt.json` / `_new.json` | `8bc140f721346730` / `cb482c053722d945` / `c8e5832e17446caa` |
| `c1_ab/grid_quick_binance_old.json` / `_new.json` | `d4be8dde5bb4cb1d` / `bf6d492129fc5aa3` |
| `c1_ab/grid_quick_bybit_old.json` / `_wt.json` / `_new.json` | `dc92ab0ea235ea3e` / `3d16aea1d9ecb1dc` / `04d109094a388d2f` |
| `c1_ab/grid_A_bybit_old.json.gz` / `_new.json.gz` (non versionnés) | `b1fe591e7605efaa` / `0edd0e79854e6e14` |
| dumps neufs : `signal_A_bybit_new_trades.json` / `_equity.jsonl` | `1e6e2e629ba6baeb` / `8084a448cd6803c6` |
| dumps neufs : `grid_quick_bybit_new_trades.json` / `_equity.jsonl` | `98b64778e14942b3` / `2e53a6d46c959c82` |

Légende des causes : **D1** rééchantillonnage quotidien + unité ; **D2** drawdown relatif au pic courant ; **D3**
PF net de la fee d'achat ; **C2** ancre / forward-fill / bords ; **C4** écart-type échantillon ; **C5** CAGR
géométrique. Les ratios bougent dans les deux sens (D1 relève le Sharpe des séries 5 m / 4 h, D3 abaisse le PF, D2
abaisse ou laisse le MaxDD).

## 4. Tableaux A/B (ancien moteur → nouveau, simulation identique)

### BacktestEngine — grok_supertrend_4h BTC/USDC 2023-04-01 → 2026-04-01 (`--fees bybit`)

- trades: 92 / equity points: 6577 / balances: {'crypto': '0', 'usdc': '1019.314423426761564209318170'}
- old engine: `/Users/stordd/doc/GitHub/kraken-trading-bot/scripts/backtest.py` · new engine: `/Users/stordd/doc/GitHub/kraken-trading-bot/scripts/backtest.py`
- identity (trades on the 15 pre-C1 fields, balances, equity curve point by point, schema-1 projection): **IDENTICAL**

| Key | Old | New | Status | Cause |
|---|---|---|---|---|
| `total_trades` | 46 | 46 | identical | - |
| `winning_trades` | 16 | 16 | identical | - |
| `losing_trades` | 30 | 30 | identical | - |
| `win_rate` | 0.347826 | 0.347826 | identical | - |
| `total_return_pct` | 1.931442 | 1.931442 | identical | - |
| `net_pnl` | 19.314423 | 19.314423 | identical | - |
| `total_fees` | 8.112818 | 8.112818 | identical | - |
| `total_pnl` | 21.614423 | 21.614423 | identical | - |
| `unrealized_pnl` | 0.000000 | 0.000000 | identical | - |
| `starting_balance` | 1000.000000 | 1000.000000 | identical | - |
| `ending_balance` | 1019.314423 | 1019.314423 | identical | - |
| `duration_days` | 1096.000000 | 1096.000000 | identical | - |
| `average_holding_time_minutes` | 10653.913043 | 10653.913043 | identical | - |
| `max_drawdown` | 23.656423190336227659464973 | 23.656423190336227659464973 | identical | - |
| `average_win` | 4.407515120811949091422873568 | 4.407515120811949091422873568 | identical | - |
| `average_loss` | -1.630193950207654041781593474 | -1.630193950207654041781593474 | identical | - |
| `sharpe_ratio` | 0.201458 | 0.454305 | moving | D1 daily resampling + unit; C2 anchor/ffill; C4 ddof=1 |
| `sortino_ratio` | 0.286363 | 0.697758 | moving | D1 daily resampling + unit; C2 anchor/ffill; C4 ddof=1 |
| `max_drawdown_pct -> max_drawdown_pct_daily` | 2.302904 | 2.279494 | moving | D2 relative to running peak; D1/C2 daily NAV |
| `profit_factor` | 1.441960 | 1.383178 | moving | D3 net of the buy fee (pnl_net_trade); 0 losses -> None |
| `calmar_ratio` | 0.279311 | 0.280381 | moving | D2 (denominator) ; C5 geometric CAGR ; D1/C2 daily |
| `gross_loss_net` | - | 50.405819 | new | - |
| `gross_profit_net` | - | 69.720242 | new | - |
| `max_drawdown_pct_engine` | - | 2.302904 | new | - |
| `metrics_version` | - | 2 | new | - |
| `n_daily_returns` | - | 1096 | new | - |
| `pf_excluded_trades` | - | 0 | new | - |

Lecture signal A : PF 1.441960 → **1.383178 = `pf_net_all_fees` calculé indépendamment par l'audit red-team**
(`results/red_team_b4_20260916/metrics_evidence.json`) ; Sharpe 0.2015 → 0.4543 (le seul facteur √6 aurait donné
0.4935 : le passage au quotidien et `ddof=1` font le reste) ; MaxDD 2.3029 → 2.2795 (quotidien vs 4 h).

### GridBacktester — grok_grid_atr_adaptive_v4 BTC/USDC 2025-03-01 → 2025-03-15 (`--fees binance`)

- trades: 90 / equity points: 4034 / balances: {'crypto': '0', 'usdc': '1001.520224293757642926965040'}
- old engine: `/Users/stordd/doc/GitHub/kraken-trading-bot/scripts/backtest.py` · new engine: `/Users/stordd/doc/GitHub/kraken-trading-bot/scripts/backtest.py`
- identity (trades on the 15 pre-C1 fields, balances, equity curve point by point, schema-1 projection): **IDENTICAL**

| Key | Old | New | Status | Cause |
|---|---|---|---|---|
| `total_trades` | 45 | 45 | identical | - |
| `winning_trades` | 37 | 37 | identical | - |
| `losing_trades` | 8 | 8 | identical | - |
| `win_rate` | 0.822222 | 0.822222 | identical | - |
| `total_return_pct` | 0.152022 | 0.152022 | identical | - |
| `net_pnl` | 1.520224 | 1.520224 | identical | - |
| `total_fees` | 1.689274 | 1.689274 | identical | - |
| `total_pnl` | 2.363974 | 2.363974 | identical | - |
| `unrealized_pnl` | -11.122098 | -11.122098 | identical | - |
| `starting_balance` | 1000.000000 | 1000.000000 | identical | - |
| `ending_balance` | 1001.520224 | 1001.520224 | identical | - |
| `duration_days` | 14.000000 | 14.000000 | identical | - |
| `average_holding_time_minutes` | 323.783784 | 323.783784 | identical | - |
| `max_drawdown` | 30.6980632678669756360294998 | 30.6980632678669756360294998 | identical | - |
| `average_win` | 0.3644884450163908936579341703 | 0.3644884450163908936579341703 | identical | - |
| `average_loss` | -1.390262271481102517297315538 | -1.390262271481102517297315538 | identical | - |
| `sharpe_ratio` | 0.020939 | 0.351973 | moving | D1 daily resampling + unit; C2 anchor/ffill; C4 ddof=1 |
| `sortino_ratio` | 0.030557 | 0.544204 | moving | D1 daily resampling + unit; C2 anchor/ffill; C4 ddof=1 |
| `max_drawdown_pct -> max_drawdown_pct_daily` | 3.050866 | 2.182222 | moving | D2 relative to running peak; D1/C2 daily NAV |
| `profit_factor` | 1.212548 | 1.134866 | moving | D3 net of the buy fee (pnl_net_trade); 0 losses -> None |
| `calmar_ratio` | 1.299120 | 1.851280 | moving | D2 (denominator) ; C5 geometric CAGR ; D1/C2 daily |
| `gross_loss_net` | - | 11.272098 | new | - |
| `gross_profit_net` | - | 12.792322 | new | - |
| `max_drawdown_pct_engine` | - | 3.050866 | new | - |
| `metrics_version` | - | 2 | new | - |
| `n_daily_returns` | - | 14 | new | - |
| `pf_excluded_trades` | - | 0 | new | - |

### GridBacktester — grok_grid_atr_adaptive_v4 BTC/USDC 2025-03-01 → 2025-03-15 (`--fees bybit`)

- trades: 90 / equity points: 4034 / balances: {'crypto': '0', 'usdc': '1000.654537804206683177476290'}
- old engine: `/Users/stordd/doc/GitHub/kraken-trading-bot/scripts/backtest.py` · new engine: `/Users/stordd/doc/GitHub/kraken-trading-bot/scripts/backtest.py`
- identity (trades on the 15 pre-C1 fields, balances, equity curve point by point, schema-1 projection): **IDENTICAL**

| Key | Old | New | Status | Cause |
|---|---|---|---|---|
| `total_trades` | 45 | 45 | identical | - |
| `winning_trades` | 37 | 37 | identical | - |
| `losing_trades` | 8 | 8 | identical | - |
| `win_rate` | 0.822222 | 0.822222 | identical | - |
| `total_return_pct` | 0.065454 | 0.065454 | identical | - |
| `net_pnl` | 0.654538 | 0.654538 | identical | - |
| `total_fees` | 2.535270 | 2.535270 | identical | - |
| `total_pnl` | 1.779538 | 1.779538 | identical | - |
| `unrealized_pnl` | -11.468595 | -11.468595 | identical | - |
| `starting_balance` | 1000.000000 | 1000.000000 | identical | - |
| `ending_balance` | 1000.654538 | 1000.654538 | identical | - |
| `duration_days` | 14.000000 | 14.000000 | identical | - |
| `average_holding_time_minutes` | 323.783784 | 323.783784 | identical | - |
| `max_drawdown` | 30.8222400221688126771728011 | 30.8222400221688126771728011 | identical | - |
| `average_win` | 0.3580576504956181517038574119 | 0.3580576504956181517038574119 | identical | - |
| `average_loss` | -1.433574408016398554445804271 | -1.433574408016398554445804271 | identical | - |
| `sharpe_ratio` | 0.011338 | 0.188154 | moving | D1 daily resampling + unit; C2 anchor/ffill; C4 ddof=1 |
| `sortino_ratio` | 0.016532 | 0.288301 | moving | D1 daily resampling + unit; C2 anchor/ffill; C4 ddof=1 |
| `max_drawdown_pct -> max_drawdown_pct_daily` | 3.064055 | 2.199705 | moving | D2 relative to running peak; D1/C2 daily NAV |
| `profit_factor` | 1.155166 | 1.056094 | moving | D3 net of the buy fee (pnl_net_trade); 0 losses -> None |
| `calmar_ratio` | 0.556933 | 0.782173 | moving | D2 (denominator) ; C5 geometric CAGR ; D1/C2 daily |
| `gross_loss_net` | - | 11.668595 | new | - |
| `gross_profit_net` | - | 12.323133 | new | - |
| `max_drawdown_pct_engine` | - | 3.064055 | new | - |
| `metrics_version` | - | 2 | new | - |
| `n_daily_returns` | - | 14 | new | - |
| `pf_excluded_trades` | - | 0 | new | - |

Lecture grid quick : `max_drawdown_pct_engine` (nouveau) = ancien `max_drawdown_pct` sur cette fenêtre (le pic au
creux était le pic global) ; le quotidien 2.18 / 2.20 % lisse les creux 5 m.

### GridBacktester — grok_grid_atr_adaptive_v4 BTC/USDC 2023-04-01 → 2026-04-01 (`--fees bybit`)

- trades: 2128 / equity points: 315650 / balances: {'crypto': '0', 'usdc': '1114.206947482765602539070709'}
- old engine: `/Users/stordd/doc/GitHub/kraken-trading-bot/scripts/backtest.py` · new engine: `/Users/stordd/doc/GitHub/kraken-trading-bot/scripts/backtest.py`
- identity (trades on the 15 pre-C1 fields, balances, equity curve point by point, schema-1 projection): **IDENTICAL**

| Key | Old | New | Status | Cause |
|---|---|---|---|---|
| `total_trades` | 1064 | 1064 | identical | - |
| `winning_trades` | 1031 | 1031 | identical | - |
| `losing_trades` | 33 | 33 | identical | - |
| `win_rate` | 0.968985 | 0.968985 | identical | - |
| `total_return_pct` | 11.420695 | 11.420695 | identical | - |
| `net_pnl` | 114.206947 | 114.206947 | identical | - |
| `total_fees` | 54.238166 | 54.238166 | identical | - |
| `total_pnl` | 140.806947 | 140.806947 | identical | - |
| `unrealized_pnl` | -228.121604 | -228.121604 | identical | - |
| `starting_balance` | 1000.000000 | 1000.000000 | identical | - |
| `ending_balance` | 1114.206947 | 1114.206947 | identical | - |
| `duration_days` | 1096.000000 | 1096.000000 | identical | - |
| `average_holding_time_minutes` | 1434.859360 | 1434.859360 | identical | - |
| `max_drawdown` | 260.195240019090295356227684 | 260.195240019090295356227684 | identical | - |
| `average_win` | 0.3578356466499585896241559721 | 0.3578356466499585896241559721 | identical | - |
| `average_loss` | -6.912775885252778889801033418 | -6.912775885252778889801033418 | identical | - |
| `sharpe_ratio` | 0.021316 | 0.367125 | moving | D1 daily resampling + unit; C2 anchor/ffill; C4 ddof=1 |
| `sortino_ratio` | 0.030435 | 0.523637 | moving | D1 daily resampling + unit; C2 anchor/ffill; C4 ddof=1 |
| `max_drawdown_pct -> max_drawdown_pct_daily` | 19.989342 | 17.966712 | moving | D2 relative to running peak; D1/C2 daily NAV |
| `profit_factor` | 1.617245 | 1.498837 | moving | D3 net of the buy fee (pnl_net_trade); 0 losses -> None |
| `calmar_ratio` | 0.190273 | 0.204106 | moving | D2 (denominator) ; C5 geometric CAGR ; D1/C2 daily |
| `gross_loss_net` | - | 228.946604 | new | - |
| `gross_profit_net` | - | 343.153552 | new | - |
| `max_drawdown_pct_engine` | - | 19.989342 | new | - |
| `metrics_version` | - | 2 | new | - |
| `n_daily_returns` | - | 1096 | new | - |
| `pf_excluded_trades` | - | 0 | new | - |

Lecture grid A : 2 128 trades, 315 650 points d'equity identiques ; PF 1.617 → 1.499 (1 064 fees d'achat imputées),
MaxDD 19.99 → 17.97 % (quotidien), Sharpe 0.021 → 0.367.

### 4 bis. Invariant MaxDD engine (condition préalable au recalage, GO conditionnel)

Théorème : l'ancien `max_drawdown_pct` (perte monétaire max ÷ pic global **final**) est toujours ≤ au drawdown
relatif au pic **courant** à la même résolution (`max_drawdown_pct_engine`), le pic final étant ≥ au pic au moment du
creux. Vérifié sur les 4 rejeux (captures `_new`, et re-captures post-correctifs pour signal A / grid quick) :

| Run | ancien `max_drawdown_pct` (cassé) | nouveau `max_drawdown_pct_engine` | post-correctifs | engine ≥ ancien |
|---|---|---|---|---|
| signal A bybit | 2.302904 | 2.302904 | 2.302904 | ✅ (égalité : le pic au creux était le pic final) |
| grid quick binance | 3.050866 | 3.050866 | 3.050866 | ✅ (égalité) |
| grid quick bybit | 3.064055 | 3.064055 | 3.064055 | ✅ (égalité) |
| grid A bybit | 19.989342 | 19.989342 | — (hashes gold inchangés post-correctifs) | ✅ (égalité) |

Sur ces quatre runs le creux maximal survient sous le pic global final, d'où l'égalité ; la valeur **quotidienne**
(`max_drawdown_pct_daily`, celle des critères) est plus basse (2.28 / 2.18 / 2.20 / 17.97 %) car elle lisse les creux
intrajournaliers de la résolution moteur.

## 5. Benchmarks v1 → v2 (`results/B4_benchmarks.json` → `results/C1_benchmarks_v2.json`, même commande :
`--fees bybit --pair-costs-file config/pair_costs_b4.json`)

| Pair | Benchmark | Sharpe v1 → v2 | MaxDD v1 → v2 (%) | Calmar v1 → v2 | Return (inchangé) | n jours |
|---|---|---|---|---|---|---|
| BTC/USDC | Buy & Hold | 0.8387 → 0.8470 | 49.65 → 49.65 | 0.9232 → 0.6724 | +137.51 % | 1096 |
| BTC/USDC | DCA fixe | **2.3541 → 0.8430** | **100.0 → 49.65** | 62.94 → 0.6658 | +20.91 % | 1093 |
| ETH/USDC | Buy & Hold | 0.3769 → 0.3829 | 63.79 → 63.79 | 0.0655 → 0.0628 | +12.53 % | 1096 |
| ETH/USDC | DCA fixe | **2.0892 → 0.3822** | **100.0 → 63.81** | 42.45 → 0.0616 | −18.25 % | 1093 |
| SOL/USDC | Buy & Hold | 0.3048 → 0.2954 | 70.23 → 70.23 | −0.129 → −0.1371 | −20.43 % | 824 |
| SOL/USDC | DCA fixe | **2.0803 → 0.3036** | **100.0 → 70.26** | 29.42 → −0.1283 | −42.94 % | 820 |

Le Sharpe du DCA fixe rejoint celui du Buy & Hold — attendu : le rendement pondéré dans le temps d'un DCA sur un
actif unique est la série de rendements de l'actif. Le B&H bouge peu (ancre à l'open de la première bougie,
`ddof=1`) ; son Calmar baisse car le CAGR géométrique (33.4 %/an) remplace le linéaire (137.5 / 3 = 45.8 %/an).
`total_return_pct` reste pondéré en argent (final vs investi).

## 6. Gold hashes (fenêtre `grok_grid_atr_adaptive_v4` BTC/USDC 2025-03-01 → 03-15, runner P6 train/test/all)

Protocole : le runner P6 (`tests/test_strategies/test_grid_atr_v4_backward_compat.py`, split 70/30 à
2025-03-10T19:12Z, segments train / test / all) a été rejoué (a) avec l'**ancien** moteur + runner depuis le
`git worktree` du tag (`v2.8.0-b4-3-campaign`) : le hash obtenu **reproduit exactement les `EXPECTED_HASHES` en
vigueur** (H1 binance `43dcdf8d…`, H2 bybit `818d7fa8…`) — la baseline est bien celle-là ; (b) avec le moteur C1
sur `feat/c1-metrics` @ `a47a928` (run pytest, JSON du runner conservés, hash recalculé depuis le JSON = valeur
affichée par le test). Les 13 clés comptables de chaque segment sont identiques ; les 5 ratios bougent avec leur
cause. Segment test (4 jours, 6 gagnants, 0 perdant) : PF v1 `inf` → v2 `None` désambiguïsé par les sommes (gains
2.02 / pertes 0 → ∞), Sortino et Calmar `None` (aucun rendement négatif, drawdown quotidien 0), Sharpe sur 5
rendements quotidiens (n rapporté). Bords partiels : le split à 19:12Z est conservé comme instant de grille.

#### `--fees binance` — old hash `43dcdf8d…` (== EXPECTED_HASHES (baseline reproduced)), new hash `619cac94d128a877615a042a8f00e007048beee11d49aa0b04fda391d6a7f9f1`

| Segment | Clé | Ancien | Nouveau | Statut | Cause |
|---|---|---|---|---|---|
| train | 13 clés comptables (total_trades, winning_trades, losing_trades, win_rate, total_return_pct, net_pnl, …) | — | — | **identiques** | - |
| train | `sharpe_ratio` | -0.383238 | -7.110160 | moving | D1/C2/C4 |
| train | `sortino_ratio` | -0.545217 | -7.478601 | moving | D1/C2/C4 |
| train | `max_drawdown_pct → max_drawdown_pct_daily` | 2.839125 | 2.570242 | moving | D2/D1/C2 |
| train | `profit_factor` | 0.300653 | 0.282975 | moving | D3 |
| train | `calmar_ratio` | -28.842398 | -21.907711 | moving | D2/C5/D1 |
| train | `max_drawdown_pct_engine` / `gross_profit_net` / `gross_loss_net` / `pf_excluded_trades` / `n_daily_returns` | - | 2.839125 / 8.676884 / 30.663028 / 0 / 10 | new | - |
| test | 13 clés comptables (total_trades, winning_trades, losing_trades, win_rate, total_return_pct, net_pnl, …) | — | — | **identiques** | - |
| test | `sharpe_ratio` | 0.969079 | 20.596031 | moving | D1/C2/C4 |
| test | `sortino_ratio` | 1.520690 | n/a | moving | D1/C2/C4 |
| test | `max_drawdown_pct → max_drawdown_pct_daily` | 0.070461 | 0.000000 | moving | D2/D1/C2 |
| test | `profit_factor` | ∞ | n/a | moving | D3 |
| test | `calmar_ratio` | 249.347597 | n/a | moving | D2/C5/D1 |
| test | `max_drawdown_pct_engine` / `gross_profit_net` / `gross_loss_net` / `pf_excluded_trades` / `n_daily_returns` | - | 0.070553 / 2.021666 / 0.000000 / 0 / 5 | new | - |
| all | 13 clés comptables (total_trades, winning_trades, losing_trades, win_rate, total_return_pct, net_pnl, …) | — | — | **identiques** | - |
| all | `sharpe_ratio` | 0.020939 | 0.351973 | moving | D1/C2/C4 |
| all | `sortino_ratio` | 0.030557 | 0.544204 | moving | D1/C2/C4 |
| all | `max_drawdown_pct → max_drawdown_pct_daily` | 3.050866 | 2.182222 | moving | D2/D1/C2 |
| all | `profit_factor` | 1.212548 | 1.134866 | moving | D3 |
| all | `calmar_ratio` | 1.299120 | 1.851280 | moving | D2/C5/D1 |
| all | `max_drawdown_pct_engine` / `gross_profit_net` / `gross_loss_net` / `pf_excluded_trades` / `n_daily_returns` | - | 3.050866 / 12.792322 / 11.272098 / 0 / 14 | new | - |

#### `--fees bybit` — old hash `818d7fa8…` (== EXPECTED_HASHES (baseline reproduced)), new hash `ca846347817276ed3040fd341b5a2ee9e46c5aaa62b5efd7e8907c84ae8f13ec`

| Segment | Clé | Ancien | Nouveau | Statut | Cause |
|---|---|---|---|---|---|
| train | 13 clés comptables (total_trades, winning_trades, losing_trades, win_rate, total_return_pct, net_pnl, …) | — | — | **identiques** | - |
| train | `sharpe_ratio` | -0.399588 | -7.322200 | moving | D1/C2/C4 |
| train | `sortino_ratio` | -0.567501 | -7.638121 | moving | D1/C2/C4 |
| train | `max_drawdown_pct → max_drawdown_pct_daily` | 2.868107 | 2.641362 | moving | D2/D1/C2 |
| train | `profit_factor` | 0.290242 | 0.267247 | moving | D3 |
| train | `calmar_ratio` | -29.765653 | -21.896978 | moving | D2/C5/D1 |
| train | `max_drawdown_pct_engine` / `gross_profit_net` / `gross_loss_net` / `pf_excluded_trades` / `n_daily_returns` | - | 2.868107 / 8.359847 / 31.281399 / 0 / 10 | new | - |
| test | 13 clés comptables (total_trades, winning_trades, losing_trades, win_rate, total_return_pct, net_pnl, …) | — | — | **identiques** | - |
| test | `sharpe_ratio` | 0.932288 | 20.524195 | moving | D1/C2/C4 |
| test | `sortino_ratio` | 1.456864 | n/a | moving | D1/C2/C4 |
| test | `max_drawdown_pct → max_drawdown_pct_daily` | 0.071072 | 0.000000 | moving | D2/D1/C2 |
| test | `profit_factor` | ∞ | n/a | moving | D3 |
| test | `calmar_ratio` | 237.902005 | n/a | moving | D2/C5/D1 |
| test | `max_drawdown_pct_engine` / `gross_profit_net` / `gross_loss_net` / `pf_excluded_trades` / `n_daily_returns` | - | 0.071163 / 1.945607 / 0.000000 / 0 / 5 | new | - |
| all | 13 clés comptables (total_trades, winning_trades, losing_trades, win_rate, total_return_pct, net_pnl, …) | — | — | **identiques** | - |
| all | `sharpe_ratio` | 0.011338 | 0.188154 | moving | D1/C2/C4 |
| all | `sortino_ratio` | 0.016532 | 0.288301 | moving | D1/C2/C4 |
| all | `max_drawdown_pct → max_drawdown_pct_daily` | 3.064055 | 2.199705 | moving | D2/D1/C2 |
| all | `profit_factor` | 1.155166 | 1.056094 | moving | D3 |
| all | `calmar_ratio` | 0.556933 | 0.782173 | moving | D2/C5/D1 |
| all | `max_drawdown_pct_engine` / `gross_profit_net` / `gross_loss_net` / `pf_excluded_trades` / `n_daily_returns` | - | 3.064055 / 12.323133 / 11.668595 / 0 / 14 | new | - |

**Valeurs approuvées** (GO Bruno 2026-09-16, recalées dans `EXPECTED_HASHES`, commit C7 ; vérifiées avant et après
les correctifs de revue) :

| Modèle | Ancien (v1) | Nouveau (v2) |
|---|---|---|
| `binance` | `43dcdf8d283db5c837f9d98d5e38dbddf1717f71177d4a19d9ea36460cf39faf` | `619cac94d128a877615a042a8f00e007048beee11d49aa0b04fda391d6a7f9f1` |
| `bybit` | `818d7fa875d5626bda6f7862739eadda5fb7e24622703a86841f00162397f39a` | `ca846347817276ed3040fd341b5a2ee9e46c5aaa62b5efd7e8907c84ae8f13ec` |

Déterminisme (`tests/test_scripts/test_run_p6_determinism.py -m "not slow"`) : 6 tests verts sur le moteur C1
(sériel vs sériel, parallèle vs sériel, 3 combos).

## 7. Contrat consommateurs

- `metrics_version` par entrée (runners, `to_dict()`, dumps, benchmarks) ; reprise / amorçage phase 2 / phase
  `report` refusent un fichier pré-C1 ou mixte (exit 2, sans échappatoire) ; **`--force` = recalcul complet dans un
  fichier homogène** (mêmes fees, contrat, coûts) — les JSON B4 (`B4_P6_*`, `B4_P7_*`) sont inécrasables.
- `p7_report` : chemin v2 None-aware (moyennes sur les fenêtres définies, `n_*`), critère 2 sur Σ gains / Σ pertes
  (∞ passe, affiché « ∞ » ; 0/0 échoue, « n/a ») ; chemin legacy v1 sélectionné par l'absence des sommes ;
  `--benchmarks` v2 obligatoire pour un rapport v2 ; jambe benchmark `None` jamais battue.
- Outils P6 (`run_p6_walkforward`, `filter_p6_survivors`, `generate_p6_report`) None-aware, `equity_daily` par
  fenêtre, refus d'un fichier pré-C1.
- DB : migration `c1ae7a1c0001` (ratios NULL, colonnes `gross_profit_net`, `gross_loss_net`, `pf_excluded_trades`,
  `metrics_version`) **appliquée sur la base Docker locale** le 16/09 (§ 7 bis) ; **serveur en attente** d'une
  fenêtre services stoppés (règle 11, hors périmètre) ; `save_to_database` écrit NULL pour un ratio indéfini ;
  dashboard : ∞ / n/a / incomplet dérivés des colonnes.

### 7 bis. Migration locale — garde-fou et sortie

Garde-fou anti-tunnel avant `alembic upgrade head` (le `.env` pointe sur le tunnel 5433) : `DATABASE_URL` explicite
`postgresql+asyncpg://krakenbot:***@127.0.0.1:5432/krakenbot` ; `alembic current` → `f7a8b9c0d1e2` ;
`SELECT count(*) FROM market_data_ohlc` → **2 768 566** rows (port 5432, container `krakenbot-db`, données Kraken)
contre **12 466 509** rows sur le serveur via le tunnel (lecture seule, pour contraste) → cible = base locale.

```
Running upgrade f7a8b9c0d1e2 -> b4c0ffee0001, market_data_ohlc.timestamp column comment: period end, not open time
Running upgrade b4c0ffee0001 -> c1ae7a1c0001, backtest_runs: undefined ratios stored as NULL + C1 metrics columns
alembic current: c1ae7a1c0001 (head)

    column_name     | data_type | precision | scale | is_nullable | comment
--------------------+-----------+-----------+-------+-------------+--------------------------------------------------------------
 max_drawdown_pct   | numeric   |        10 |     4 | NO          | Maximum drawdown percentage (C1: daily NAV, relative to the running peak)
 sharpe_ratio       | numeric   |        10 |     4 | YES         | Sharpe ratio (daily returns); NULL when undefined
 profit_factor      | numeric   |        10 |     4 | YES         | Profit factor net of both legs; NULL when losses == 0 (see the sums)
 sortino_ratio      | numeric   |        10 |     4 | YES         | Sortino ratio (downside volatility); NULL when undefined
 gross_profit_net   | numeric   |        18 |     8 | YES         | C1: sum of the net gains (buy fee imputed) behind profit_factor
 gross_loss_net     | numeric   |        18 |     8 | YES         | C1: sum of the net losses (absolute value) behind profit_factor
 pf_excluded_trades | integer   |        32 |     0 | YES         | C1: closed lots with an unknown cost basis, excluded from profit_factor
 metrics_version    | integer   |        32 |     0 | YES         | C1: contract version of the ratios (krakenbot.backtest_metrics); NULL = pre-C1
backtest_runs rows: 22 (untouched)
```

## 8. Signalé, non traité

1. Moteur signal, accumulation (DCA) : `cost_basis = entry_price × crypto_balance` au dernier prix d'entrée —
   approximation préexistante (chantier 2) ; l'allocation de fee (Σ fees ouvertes) est, elle, exacte.
2. `_process_grok_grid_sell_fill` : vente sans position appariée → wallet débité sans trade enregistré
   (instrumenté par la divergence d'inventaire, hors chantier).
3. Benchmarks chargés `< P6_END`, moteurs `<= end` (un jour) ; « lundi » = stamp de fin de période = close du
   dimanche (préexistant) → chantier 3.
4. Checkpoints B4 (`scripts/audit/b4_p6/p7_checkpoint.py`) : détection « PF inf » aveugle sur v2 ;
   `scripts/audit/b4_3_gate_a_reconcile.py` lit les captures B4 (v1, clé `max_drawdown_pct`) et ne sait pas lire
   une capture v2 — outils de la campagne close.
6. Revue adversariale (26 agents, 2 constats confirmés, 8 réfutés, 11 mineurs) : intégrée avant soumission —
   garde de contrat sur **tout** le fichier à la reprise (un job à clé nouvelle ne peut plus s'ajouter à un JSON
   pré-C1), contrôle de contrat des survivants (`run_p6_walkforward`) et des fichiers benchmarks (`filter` /
   `generate`), flux daté exactement `start` = capital initial (ancre), série moteur du MaxDD bornée à
   `[start, end]`, Calmar défini sur perte totale (−1), `pf_excluded_trades` agrégé et signalé en P7, tableau de
   comparaison et libellés v1 du dashboard, tests ajoutés (clé disjointe, rang `None`, chargeur v2, lot ouvert,
   sauvegarde DB).
5. Incident git du 16/09 (checkout de `dev` par une autre session pendant le chantier) : `dev` remis à `0241848`
   et poussé, C6 réappliqué en `a47a928`, branche de sauvegarde `c1-stray-db377ce` conservée jusqu'au merge ;
   toute preuve produite pendant la fenêtre a été régénérée sur `feat/c1-metrics`.
