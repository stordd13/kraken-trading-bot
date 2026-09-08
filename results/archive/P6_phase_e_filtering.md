# P6 Phase E — Survivor Filtering Report

**Total combinations**: 24
**Survivors**: 0
**Rejected**: 24

## Acceptance Criteria (applied on TEST set)

- Sharpe > 1.0
- Sortino > 1.5
- Max Drawdown < 25.0%
- Profit Factor > 1.5
- Calmar > 0.5
- Min 30 trades (except DCA)
- Train/test consistency > 0.5
- Must beat Buy & Hold or DCA benchmark in Sharpe

## Full Results

| Strategy | Pair | Return (test) | Sharpe | Sortino | MaxDD | PF | Calmar | Trades | Status | Primary Reason |
|---|---|---|---|---|---|---|---|---|---|---|
| gemini_retour_moyenne | BTC/USDC | +0.0% | 0.03 | 0.04 | 0.0% | 0.00 | 0.83 | 3 | FAIL | Sharpe 0.03 < 1.0 |
| gemini_retour_moyenne | ETH/USDC | +0.0% | 0.00 | 0.00 | 0.0% | 0.00 | 0.00 | 0 | FAIL | Sharpe 0.00 < 1.0 |
| gemini_retour_moyenne | SOL/USDC | +0.0% | 0.00 | 0.00 | 0.0% | 0.00 | 0.00 | 0 | FAIL | Sharpe 0.00 < 1.0 |
| gemini_scalping_volatilite | BTC/USDC | -1.3% | -0.50 | -0.62 | 1.3% | 0.30 | -1.10 | 213 | FAIL | Sharpe -0.50 < 1.0 |
| gemini_scalping_volatilite | ETH/USDC | +0.0% | 0.00 | 0.00 | 0.0% | 0.00 | 0.00 | 0 | FAIL | Sharpe 0.00 < 1.0 |
| gemini_scalping_volatilite | SOL/USDC | +0.0% | 0.00 | 0.00 | 0.0% | 0.00 | 0.00 | 0 | FAIL | Sharpe 0.00 < 1.0 |
| gemini_suivi_tendance_momentum | BTC/USDC | -0.8% | -0.22 | -0.28 | 0.8% | 0.02 | -1.11 | 12 | FAIL | Sharpe -0.22 < 1.0 |
| gemini_suivi_tendance_momentum | ETH/USDC | +0.0% | 0.00 | 0.00 | 0.0% | 0.00 | 0.00 | 0 | FAIL | Sharpe 0.00 < 1.0 |
| gemini_suivi_tendance_momentum | SOL/USDC | +0.0% | 0.00 | 0.00 | 0.0% | 0.00 | 0.00 | 0 | FAIL | Sharpe 0.00 < 1.0 |
| grok_adaptive_dca_weekly | BTC/USDC | -11.0% | -1.25 | -1.65 | 14.4% | 0.00 | -0.85 | 46 | FAIL | Sharpe -1.25 < 1.0 |
| grok_adaptive_dca_weekly | ETH/USDC | -12.7% | -0.61 | -0.85 | 27.4% | 0.00 | -0.51 | 47 | FAIL | Sharpe -0.61 < 1.0 |
| grok_adaptive_dca_weekly | SOL/USDC | -22.2% | -1.17 | -1.55 | 31.5% | 0.00 | -0.78 | 47 | FAIL | Sharpe -1.17 < 1.0 |
| grok_donchian_breakout_4h | BTC/USDC | -0.0% | -0.01 | -0.02 | 0.5% | 1.02 | -0.04 | 7 | FAIL | Sharpe -0.01 < 1.0 |
| grok_donchian_breakout_4h | ETH/USDC | +0.5% | 0.15 | 0.23 | 1.5% | 1.26 | 0.33 | 12 | FAIL | Sharpe 0.15 < 1.0 |
| grok_donchian_breakout_4h | SOL/USDC | -0.1% | -0.02 | -0.02 | 1.3% | 0.99 | -0.05 | 14 | FAIL | Sharpe -0.02 < 1.0 |
| grok_ema_adx_atr | BTC/USDC | +0.0% | 0.01 | 0.02 | 0.2% | 1.94 | 0.02 | 2 | FAIL | Sharpe 0.01 < 1.0 |
| grok_ema_adx_atr | ETH/USDC | +0.1% | 0.15 | 0.23 | 0.2% | 6.74 | 0.34 | 2 | FAIL | Sharpe 0.15 < 1.0 |
| grok_ema_adx_atr | SOL/USDC | -0.2% | -0.13 | -0.18 | 0.8% | 0.37 | -0.26 | 2 | FAIL | Sharpe -0.13 < 1.0 |
| grok_grid_atr_adaptive_v4 | BTC/USDC | -13.6% | -0.04 | -0.06 | 23.5% | 0.00 | -0.64 | 187 | FAIL | Sharpe -0.04 < 1.0 |
| grok_grid_atr_adaptive_v4 | ETH/USDC | -25.3% | -0.05 | -0.07 | 37.6% | 0.00 | -0.75 | 369 | FAIL | Sharpe -0.05 < 1.0 |
| grok_grid_atr_adaptive_v4 | SOL/USDC | -44.9% | -0.06 | -0.09 | 57.8% | 0.00 | -0.86 | 415 | FAIL | Sharpe -0.06 < 1.0 |
| grok_supertrend_4h | BTC/USDC | +0.4% | 0.25 | 0.37 | 0.6% | 1.90 | 0.83 | 9 | FAIL | Sharpe 0.25 < 1.0 |
| grok_supertrend_4h | ETH/USDC | +2.1% | 0.53 | 0.79 | 1.8% | 2.39 | 1.30 | 12 | FAIL | Sharpe 0.53 < 1.0 |
| grok_supertrend_4h | SOL/USDC | +1.1% | 0.29 | 0.43 | 1.1% | 1.96 | 1.08 | 10 | FAIL | Sharpe 0.29 < 1.0 |

## Survivors

No combinations passed all criteria.

