### BacktestEngine — grok_supertrend_4h BTC/USDC 2023-04-01 → 2026-04-01 (`--fees bybit`)

- trades: 92 / equity points: 6577 / balances: {'crypto': '0', 'usdc': '1019.314423426761564209318170'}
- old engine: `/Users/stordd/wt-c1-ref/scripts/backtest.py` · new engine: `/Users/stordd/doc/GitHub/kraken-trading-bot/scripts/backtest.py`
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
| `sharpe_ratio` | 0.454305 | 0.454305 | moving | D1 daily resampling + unit; C2 anchor/ffill; C4 ddof=1 |
| `sortino_ratio` | 0.697758 | 0.697758 | moving | D1 daily resampling + unit; C2 anchor/ffill; C4 ddof=1 |
| `max_drawdown_pct -> max_drawdown_pct_daily` | n/a | 2.279494 | moving | D2 relative to running peak; D1/C2 daily NAV |
| `profit_factor` | 1.383178 | 1.383178 | moving | D3 net of the buy fee (pnl_net_trade); 0 losses -> None |
| `calmar_ratio` | 0.280381 | 0.280381 | moving | D2 (denominator) ; C5 geometric CAGR ; D1/C2 daily |
| `gross_loss_net` | - | 50.405819 | new | - |
| `gross_profit_net` | - | 69.720242 | new | - |
| `max_drawdown_pct_engine` | - | 2.302904 | new | - |
| `metrics_version` | - | 2 | new | - |
| `n_daily_returns` | - | 1096 | new | - |
| `pf_excluded_trades` | - | 0 | new | - |
| `gross_loss_net` | 50.405819 | - | removed | - |
| `gross_profit_net` | 69.720242 | - | removed | - |
| `max_drawdown_pct_daily` | 2.279494 | - | removed | - |
| `max_drawdown_pct_engine` | 2.302904 | - | removed | - |
| `metrics_version` | 2 | - | removed | - |
| `n_daily_returns` | 1096 | - | removed | - |
| `pf_excluded_trades` | 0 | - | removed | - |
