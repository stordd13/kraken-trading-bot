# P6 — Binance Backtest Validation Report

## Executive Summary

We tested **24 combinations** (8 strategies x 3 pairs) over 3 years of Binance data (2023-04 to 2026-04) with cross-validation (70/30 train/test split). **0** combinations passed all 5 acceptance criteria on the test set. 

## Methodology

- **Period**: 2023-04-01 to 2026-04-01 (3 years)
- **Exchange**: Binance (historical data from Binance Vision)
- **Fees**: 0.075% maker/taker (BNB discount), 0.02% spread, 0.01% slippage
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
| BTC/USDC | Buy & Hold | +139.7% | 0.85 | 1.30 | 49.6% | 0.94 |
| ETH/USDC | Buy & Hold | +15.5% | 0.40 | 0.60 | 63.8% | 0.08 |
| SOL/USDC | Buy & Hold | -19.5% | 0.31 | 0.46 | 70.2% | -0.12 |
| BTC/USDC | DCA $15/wk | +23.3% | 2.37 | 6.90 | 100.0% | 64.20 |
| ETH/USDC | DCA $15/wk | -15.2% | 2.10 | 4.82 | 100.0% | 44.06 |
| SOL/USDC | DCA $15/wk | -42.6% | 1.93 | 4.73 | 100.0% | 29.54 |

## First Pass Results (Cross-Validated)

| Strategy | Pair | Train Ret | Test Ret | Train Sharpe | Test Sharpe | MaxDD | PF | Calmar | Trades | Status |
|---|---|---|---|---|---|---|---|---|---|---|
| gemini_retour_moyenne | BTC/USDC | +0.0% | +0.0% | 0.03 | 0.03 | 0.0% | 0.00 | 0.83 | 3 | FAIL |
| gemini_retour_moyenne | ETH/USDC | +0.0% | -0.0% | 0.01 | -0.04 | 0.0% | 0.51 | -0.65 | 5 | FAIL |
| gemini_retour_moyenne | SOL/USDC | +0.1% | -0.1% | 0.07 | -0.10 | 0.1% | 0.43 | -0.99 | 12 | FAIL |
| gemini_scalping_volatilite | BTC/USDC | -2.8% | -1.3% | -0.40 | -0.50 | 1.3% | 0.30 | -1.10 | 213 | FAIL |
| gemini_scalping_volatilite | ETH/USDC | -3.6% | -1.8% | -0.41 | -0.43 | 1.9% | 0.42 | -1.08 | 292 | FAIL |
| gemini_scalping_volatilite | SOL/USDC | -3.4% | -2.6% | -0.39 | -0.49 | 2.6% | 0.37 | -1.10 | 355 | FAIL |
| gemini_suivi_tendance_momentum | BTC/USDC | -6.5% | -0.8% | -0.18 | -0.22 | 0.8% | 0.02 | -1.11 | 12 | FAIL |
| gemini_suivi_tendance_momentum | ETH/USDC | -5.6% | -1.6% | -0.15 | -0.16 | 1.7% | 0.02 | -1.09 | 16 | FAIL |
| gemini_suivi_tendance_momentum | SOL/USDC | -5.0% | -2.1% | -0.15 | -0.17 | 2.2% | 0.24 | -1.06 | 26 | FAIL |
| grok_adaptive_dca_weekly | BTC/USDC | +139.5% | -11.0% | 1.31 | -1.25 | 14.4% | 0.00 | -0.85 | 46 | FAIL |
| grok_adaptive_dca_weekly | ETH/USDC | -17.3% | -12.7% | 0.07 | -0.61 | 27.4% | 0.00 | -0.51 | 47 | FAIL |
| grok_adaptive_dca_weekly | SOL/USDC | +2.1% | -22.2% | 0.25 | -1.17 | 31.5% | 0.00 | -0.78 | 47 | FAIL |
| grok_donchian_breakout_4h | BTC/USDC | +1.5% | -0.0% | 0.24 | -0.01 | 0.5% | 1.02 | -0.04 | 7 | FAIL |
| grok_donchian_breakout_4h | ETH/USDC | +0.3% | +0.5% | 0.05 | 0.15 | 1.5% | 1.26 | 0.33 | 12 | FAIL |
| grok_donchian_breakout_4h | SOL/USDC | -2.3% | -0.1% | -0.34 | -0.02 | 1.3% | 0.99 | -0.05 | 14 | FAIL |
| grok_ema_adx_atr | BTC/USDC | +1.1% | +0.0% | 0.32 | 0.01 | 0.2% | 1.94 | 0.02 | 2 | FAIL |
| grok_ema_adx_atr | ETH/USDC | -0.3% | +0.1% | -0.16 | 0.15 | 0.2% | 6.74 | 0.34 | 2 | FAIL |
| grok_ema_adx_atr | SOL/USDC | +1.4% | -0.2% | 0.35 | -0.13 | 0.8% | 0.37 | -0.26 | 2 | FAIL |
| grok_grid_atr_adaptive_v4 | BTC/USDC | +28.0% | -13.6% | 0.08 | -0.04 | 23.5% | inf | -0.64 | 187 | FAIL |
| grok_grid_atr_adaptive_v4 | ETH/USDC | +7.5% | -25.3% | 0.02 | -0.05 | 37.6% | inf | -0.75 | 369 | FAIL |
| grok_grid_atr_adaptive_v4 | SOL/USDC | +50.3% | -44.9% | 0.07 | -0.06 | 57.8% | inf | -0.86 | 415 | FAIL |
| grok_supertrend_4h | BTC/USDC | +2.9% | +0.4% | 0.37 | 0.25 | 0.6% | 1.90 | 0.83 | 9 | FAIL |
| grok_supertrend_4h | ETH/USDC | +0.4% | +2.1% | 0.06 | 0.53 | 1.8% | 2.39 | 1.30 | 12 | FAIL |
| grok_supertrend_4h | SOL/USDC | +2.0% | +1.1% | 0.23 | 0.29 | 1.1% | 1.96 | 1.08 | 10 | FAIL |

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

## Next Steps

1. Activate Priority 1 combinations in paper trading (2-4 weeks)
2. Monitor Priority 2 with reduced capital
3. P7: Parameter optimization on survivors (grid search or Bayesian)
4. P8: ML feature engineering (XGBoost/RF on technical features)
5. Scale capital progressively on confirmed winners (1k -> 10k -> 20k USDC)

