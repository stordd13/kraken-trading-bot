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
