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
| gemini_retour_moyenne | BTC/USDC | -0.2% | -0.20 | -0.25 | 0.2% | 0.19 | -1.02 | 21 | FAIL | Sharpe -0.20 < 1.0 |
| gemini_retour_moyenne | ETH/USDC | -0.3% | -0.20 | -0.25 | 0.3% | 0.11 | -1.04 | 23 | FAIL | Sharpe -0.20 < 1.0 |
| gemini_retour_moyenne | SOL/USDC | -0.2% | -0.13 | -0.16 | 0.2% | 0.37 | -0.99 | 21 | FAIL | Sharpe -0.13 < 1.0 |
| gemini_scalping_volatilite | BTC/USDC | -2.0% | -0.70 | -0.81 | 2.0% | 0.15 | -1.11 | 217 | FAIL | Sharpe -0.70 < 1.0 |
| gemini_scalping_volatilite | ETH/USDC | -2.6% | -0.59 | -0.73 | 2.7% | 0.28 | -1.09 | 298 | FAIL | Sharpe -0.59 < 1.0 |
| gemini_scalping_volatilite | SOL/USDC | -4.1% | -0.71 | -0.86 | 4.1% | 0.23 | -1.10 | 370 | FAIL | Sharpe -0.71 < 1.0 |
| gemini_suivi_tendance_momentum | BTC/USDC | -0.5% | -0.14 | -0.19 | 0.6% | 0.16 | -0.91 | 12 | FAIL | Sharpe -0.14 < 1.0 |
| gemini_suivi_tendance_momentum | ETH/USDC | -0.5% | -0.04 | -0.06 | 1.0% | 0.66 | -0.52 | 15 | FAIL | Sharpe -0.04 < 1.0 |
| gemini_suivi_tendance_momentum | SOL/USDC | -1.6% | -0.10 | -0.14 | 2.1% | 0.39 | -0.83 | 21 | FAIL | Sharpe -0.10 < 1.0 |
| grok_adaptive_dca_weekly | BTC/USDC | -10.1% | -1.20 | -1.59 | 13.5% | 0.00 | -0.83 | 45 | FAIL | Sharpe -1.20 < 1.0 |
| grok_adaptive_dca_weekly | ETH/USDC | -12.2% | -0.56 | -0.78 | 27.7% | 0.00 | -0.49 | 47 | FAIL | Sharpe -0.56 < 1.0 |
| grok_adaptive_dca_weekly | SOL/USDC | -22.5% | -1.14 | -1.51 | 32.4% | 0.00 | -0.77 | 46 | FAIL | Sharpe -1.14 < 1.0 |
| grok_donchian_breakout_4h | BTC/USDC | -0.3% | -0.22 | -0.32 | 0.7% | 0.60 | -0.43 | 8 | FAIL | Sharpe -0.22 < 1.0 |
| grok_donchian_breakout_4h | ETH/USDC | +0.2% | 0.06 | 0.09 | 1.6% | 1.10 | 0.12 | 12 | FAIL | Sharpe 0.06 < 1.0 |
| grok_donchian_breakout_4h | SOL/USDC | -0.7% | -0.23 | -0.31 | 1.4% | 0.69 | -0.57 | 14 | FAIL | Sharpe -0.23 < 1.0 |
| grok_ema_adx_atr | BTC/USDC | -0.0% | -0.07 | -0.09 | 0.1% | 0.00 | -0.21 | 1 | FAIL | Sharpe -0.07 < 1.0 |
| grok_ema_adx_atr | ETH/USDC | +0.1% | 0.11 | 0.18 | 0.3% | 4.00 | 0.25 | 2 | FAIL | Sharpe 0.11 < 1.0 |
| grok_ema_adx_atr | SOL/USDC | -0.2% | -0.15 | -0.21 | 0.8% | 0.32 | -0.29 | 2 | FAIL | Sharpe -0.15 < 1.0 |
| grok_grid_atr_adaptive_v4 | BTC/USDC | -11.6% | -0.03 | -0.05 | 24.0% | 0.46 | -0.54 | 293 | FAIL | Sharpe -0.03 < 1.0 |
| grok_grid_atr_adaptive_v4 | ETH/USDC | -31.7% | -0.05 | -0.07 | 44.7% | 0.30 | -0.79 | 404 | FAIL | Sharpe -0.05 < 1.0 |
| grok_grid_atr_adaptive_v4 | SOL/USDC | -44.4% | -0.06 | -0.08 | 58.5% | 0.31 | -0.84 | 580 | FAIL | Sharpe -0.06 < 1.0 |
| grok_supertrend_4h | BTC/USDC | +0.3% | 0.16 | 0.23 | 0.6% | 1.57 | 0.48 | 9 | FAIL | Sharpe 0.16 < 1.0 |
| grok_supertrend_4h | ETH/USDC | +1.2% | 0.29 | 0.42 | 1.8% | 1.53 | 0.70 | 13 | FAIL | Sharpe 0.29 < 1.0 |
| grok_supertrend_4h | SOL/USDC | +0.8% | 0.21 | 0.31 | 1.1% | 1.59 | 0.78 | 10 | FAIL | Sharpe 0.21 < 1.0 |

## Survivors

No combinations passed all criteria.

## Flagged runs (inventory divergence / formula vs cash)

| Run | Strategy | Pair | Segment | Params | Reasons |
|---|---|---|---|---|---|
| `grok_grid_atr_adaptive_v4_SOL_USDC` | grok_grid_atr_adaptive_v4 | SOL/USDC | train | - | inventory divergence -0.025647635176225406481895346 BTC; net_pnl 480.5454113897327 != lot basis 484.3079194700849573245609320 (formula vs cash) |
| `grok_grid_atr_adaptive_v4_SOL_USDC` | grok_grid_atr_adaptive_v4 | SOL/USDC | test | - | inventory divergence -0.005809007961228377788323002 BTC; net_pnl -444.3962523855874 != lot basis -443.6526993665501604597355850 (formula vs cash) |
| `grok_grid_atr_adaptive_v4_SOL_USDC` | grok_grid_atr_adaptive_v4 | SOL/USDC | all | - | inventory divergence -0.033472291971067908103841611 BTC; net_pnl 309.7712599076728 != lot basis 313.6339624011340646958120296 (formula vs cash) |

