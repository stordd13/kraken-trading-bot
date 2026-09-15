# P6 — Binance Backtest Validation Report

## Executive Summary

We tested **24 combinations** (8 strategies x 3 pairs) over 3 years of Binance data (2023-04 to 2026-04) with cross-validation (70/30 train/test split). **0** combinations passed all 5 acceptance criteria on the test set. 

## Methodology

- **Period**: 2023-04-01 to 2026-04-01 (3 years)
- **Exchange**: Binance (historical data from Binance Vision)
- **Fees**: model `bybit` (maker/taker per fill site; per-pair costs: config/pair_costs_b4.json; min order: 5.0 USDC)
- **Starting capital**: $1,000 USDC per backtest
- **Cross-validation**: 70% train / 30% test temporal split
- **Walk-forward**: 12-month train / 3-month test, 3-month advance (8 windows)
- **Execution model**: Next-bar (signal on candle N, fill at open of candle N+1)

### Acceptance Criteria (all must pass on TEST set)

| Metric | Threshold |
|--------|-----------|
| Sharpe Ratio | > 1.0 |
| Sortino Ratio | > 1.5 |
| Max Drawdown | < 25% |
| Profit Factor | > 1.5 |
| Calmar Ratio | > 0.5 |
| Min Trades | >= 30 (except DCA) |
| Consistency | test_sharpe / train_sharpe > 0.5 |
| Benchmark | Must beat Buy & Hold or DCA in Sharpe |

## Data Coverage

## 2. P6 Period Coverage (2023-04-01 → 2026-04-01)

| Pair | TF | Expected | Actual | Coverage % | Gap % | Status |
|------|-----|----------|--------|------------|-------|--------|
| BTC/USDC | 5m | 315,648 | 315,648 | 100.0% | 0.0% | OK |
| BTC/USDC | 15m | 105,216 | 105,216 | 100.0% | 0.0% | OK |
| BTC/USDC | 1h | 26,304 | 26,304 | 100.0% | 0.0% | OK |
| BTC/USDC | 4h | 6,576 | 6,576 | 100.0% | 0.0% | OK |
| BTC/USDC | 1d | 1,096 | 1,096 | 100.0% | 0.0% | OK |
| BTC/USDC | 1w | 156 | 155 | 99.4% | 0.6% | OK |
| ETH/USDC | 5m | 315,648 | 315,648 | 100.0% | 0.0% | OK |
| ETH/USDC | 15m | 105,216 | 105,216 | 100.0% | 0.0% | OK |
| ETH/USDC | 1h | 26,304 | 26,304 | 100.0% | 0.0% | OK |
| ETH/USDC | 4h | 6,576 | 6,576 | 100.0% | 0.0% | OK |
| ETH/USDC | 1d | 1,096 | 1,096 | 100.0% | 0.0% | OK |
| ETH/USDC | 1w | 156 | 155 | 99.4% | 0.6% | OK |
| SOL/USDC | 5m | 315,648 | 237,504 | 75.2% | 24.8% | FAIL |
| SOL/USDC | 15m | 105,216 | 79,168 | 75.2% | 24.8% | FAIL |
| SOL/USDC | 1h | 26,304 | 19,792 | 75.2% | 24.8% | FAIL |
| SOL/USDC | 4h | 6,576 | 4,948 | 75.2% | 24.8% | FAIL |
| SOL/USDC | 1d | 1,096 | 825 | 75.3% | 24.7% | FAIL |
| SOL/USDC | 1w | 156 | 117 | 75.0% | 25.0% | FAIL |


## Benchmarks

| Pair | Strategy | Return % | Sharpe | Sortino | MaxDD % | Calmar |
|------|----------|----------|--------|---------|---------|--------|
| BTC/USDC | Buy & Hold | +137.5% | 0.84 | 1.27 | 49.6% | 0.92 |
| ETH/USDC | Buy & Hold | +12.5% | 0.38 | 0.57 | 63.8% | 0.07 |
| SOL/USDC | Buy & Hold | -20.4% | 0.30 | 0.45 | 70.2% | -0.13 |
| BTC/USDC | DCA $15/wk | +20.9% | 2.35 | 6.76 | 100.0% | 62.94 |
| ETH/USDC | DCA $15/wk | -18.2% | 2.09 | 4.74 | 100.0% | 42.45 |
| SOL/USDC | DCA $15/wk | -42.9% | 2.08 | 4.52 | 100.0% | 29.42 |

## First Pass Results (Cross-Validated)

| Strategy | Pair | Train Ret | Test Ret | Train Sharpe | Test Sharpe | MaxDD | PF | Calmar | Trades | Status |
|---|---|---|---|---|---|---|---|---|---|---|
| gemini_retour_moyenne | BTC/USDC | -0.3% | -0.2% | -0.18 | -0.20 | 0.2% | 0.19 | -1.02 | 21 | FAIL |
| gemini_retour_moyenne | ETH/USDC | -0.3% | -0.3% | -0.15 | -0.20 | 0.3% | 0.11 | -1.04 | 23 | FAIL |
| gemini_retour_moyenne | SOL/USDC | -0.3% | -0.2% | -0.15 | -0.13 | 0.2% | 0.37 | -0.99 | 21 | FAIL |
| gemini_scalping_volatilite | BTC/USDC | -4.1% | -2.0% | -0.54 | -0.70 | 2.0% | 0.15 | -1.11 | 217 | FAIL |
| gemini_scalping_volatilite | ETH/USDC | -5.5% | -2.6% | -0.59 | -0.59 | 2.7% | 0.28 | -1.09 | 298 | FAIL |
| gemini_scalping_volatilite | SOL/USDC | -5.9% | -4.1% | -0.61 | -0.71 | 4.1% | 0.23 | -1.10 | 370 | FAIL |
| gemini_suivi_tendance_momentum | BTC/USDC | -1.1% | -0.5% | -0.03 | -0.14 | 0.6% | 0.16 | -0.91 | 12 | FAIL |
| gemini_suivi_tendance_momentum | ETH/USDC | -1.5% | -0.5% | -0.03 | -0.04 | 1.0% | 0.66 | -0.52 | 15 | FAIL |
| gemini_suivi_tendance_momentum | SOL/USDC | -1.6% | -1.6% | -0.04 | -0.10 | 2.1% | 0.39 | -0.83 | 21 | FAIL |
| grok_adaptive_dca_weekly | BTC/USDC | +143.5% | -10.1% | 1.31 | -1.20 | 13.5% | 0.00 | -0.83 | 45 | FAIL |
| grok_adaptive_dca_weekly | ETH/USDC | -16.7% | -12.2% | 0.08 | -0.56 | 27.7% | 0.00 | -0.49 | 47 | FAIL |
| grok_adaptive_dca_weekly | SOL/USDC | +2.3% | -22.5% | 0.25 | -1.14 | 32.4% | 0.00 | -0.77 | 46 | FAIL |
| grok_donchian_breakout_4h | BTC/USDC | +1.0% | -0.3% | 0.17 | -0.22 | 0.7% | 0.60 | -0.43 | 8 | FAIL |
| grok_donchian_breakout_4h | ETH/USDC | -0.8% | +0.2% | -0.13 | 0.06 | 1.6% | 1.10 | 0.12 | 12 | FAIL |
| grok_donchian_breakout_4h | SOL/USDC | -2.4% | -0.7% | -0.36 | -0.23 | 1.4% | 0.69 | -0.57 | 14 | FAIL |
| grok_ema_adx_atr | BTC/USDC | +1.0% | -0.0% | 0.30 | -0.07 | 0.1% | 0.00 | -0.21 | 1 | FAIL |
| grok_ema_adx_atr | ETH/USDC | -0.3% | +0.1% | -0.18 | 0.11 | 0.3% | 4.00 | 0.25 | 2 | FAIL |
| grok_ema_adx_atr | SOL/USDC | +1.4% | -0.2% | 0.35 | -0.15 | 0.8% | 0.32 | -0.29 | 2 | FAIL |
| grok_grid_atr_adaptive_v4 | BTC/USDC | +27.1% | -11.6% | 0.07 | -0.03 | 24.0% | 0.46 | -0.54 | 293 | FAIL |
| grok_grid_atr_adaptive_v4 | ETH/USDC | +1.3% | -31.7% | 0.01 | -0.05 | 44.7% | 0.30 | -0.79 | 404 | FAIL |
| grok_grid_atr_adaptive_v4 | SOL/USDC | +48.1% | -44.4% | 0.07 | -0.06 | 58.5% | 0.31 | -0.84 | 580 | FAIL |
| grok_supertrend_4h | BTC/USDC | +1.6% | +0.3% | 0.22 | 0.16 | 0.6% | 1.57 | 0.48 | 9 | FAIL |
| grok_supertrend_4h | ETH/USDC | -0.0% | +1.2% | 0.00 | 0.29 | 1.8% | 1.53 | 0.70 | 13 | FAIL |
| grok_supertrend_4h | SOL/USDC | +0.9% | +0.8% | 0.11 | 0.21 | 1.1% | 1.59 | 0.78 | 10 | FAIL |

## Walk-Forward Results

*No walk-forward results available (no survivors or Phase F not run).*

## Recommendations

### Priority 1 — Activate in Paper Trading

*None*

### Priority 2 — Observe in Paper with Reduced Capital

*None*

### Abandon

- grok_grid_atr_adaptive_v4 on BTC/USDC
- grok_grid_atr_adaptive_v4 on ETH/USDC
- grok_grid_atr_adaptive_v4 on SOL/USDC
- grok_supertrend_4h on BTC/USDC
- grok_supertrend_4h on ETH/USDC
- grok_supertrend_4h on SOL/USDC
- grok_ema_adx_atr on BTC/USDC
- grok_ema_adx_atr on ETH/USDC
- grok_ema_adx_atr on SOL/USDC
- grok_adaptive_dca_weekly on BTC/USDC
- grok_adaptive_dca_weekly on ETH/USDC
- grok_adaptive_dca_weekly on SOL/USDC
- grok_donchian_breakout_4h on BTC/USDC
- grok_donchian_breakout_4h on ETH/USDC
- grok_donchian_breakout_4h on SOL/USDC
- gemini_scalping_volatilite on BTC/USDC
- gemini_scalping_volatilite on ETH/USDC
- gemini_scalping_volatilite on SOL/USDC
- gemini_suivi_tendance_momentum on BTC/USDC
- gemini_suivi_tendance_momentum on ETH/USDC
- gemini_suivi_tendance_momentum on SOL/USDC
- gemini_retour_moyenne on BTC/USDC
- gemini_retour_moyenne on ETH/USDC
- gemini_retour_moyenne on SOL/USDC

## Surprising Findings

- No particularly surprising patterns detected.

## Flagged runs (inventory divergence / formula vs cash)

| Run | Strategy | Pair | Segment | Params | Reasons |
|---|---|---|---|---|---|
| `grok_grid_atr_adaptive_v4_SOL_USDC` | grok_grid_atr_adaptive_v4 | SOL/USDC | train | - | inventory divergence -0.025647635176225406481895346 BTC; net_pnl 480.5454113897327 != lot basis 484.3079194700849573245609320 (formula vs cash) |
| `grok_grid_atr_adaptive_v4_SOL_USDC` | grok_grid_atr_adaptive_v4 | SOL/USDC | test | - | inventory divergence -0.005809007961228377788323002 BTC; net_pnl -444.3962523855874 != lot basis -443.6526993665501604597355850 (formula vs cash) |
| `grok_grid_atr_adaptive_v4_SOL_USDC` | grok_grid_atr_adaptive_v4 | SOL/USDC | all | - | inventory divergence -0.033472291971067908103841611 BTC; net_pnl 309.7712599076728 != lot basis 313.6339624011340646958120296 (formula vs cash) |

## Effective parameters (runtime capture, survivors)

_No survivor: the effective parameters of every combo are in the phase D JSON (`effective_params` per entry)._

## Next Steps

1. Activate Priority 1 combinations in paper trading (2-4 weeks)
2. Monitor Priority 2 with reduced capital
3. P7: Parameter optimization on survivors (grid search or Bayesian)
4. P8: ML feature engineering (XGBoost/RF on technical features)
5. Scale capital progressively on confirmed winners (1k -> 10k -> 20k USDC)

