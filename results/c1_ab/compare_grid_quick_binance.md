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
