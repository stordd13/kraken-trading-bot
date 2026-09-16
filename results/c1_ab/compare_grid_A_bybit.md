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
