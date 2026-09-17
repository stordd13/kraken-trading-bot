### BacktestEngine — grok_adaptive_dca_weekly BTC/USDC 2022-01-01 → 2022-09-28 (`--fees bybit`)

- trades: 36 / equity points: 271 / balances: {'crypto': '0.01731820757311601048921256875', 'usdc': '505.0'}
- old engine: `/Users/stordd/wt-c1-ref/scripts/backtest.py` · new engine: `/Users/stordd/doc/GitHub/kraken-trading-bot/scripts/backtest.py`
- identity (trades on the 15 pre-C1 fields, balances, equity curve point by point, …): **VIOLATIONS**
  - trade 4.amount_usdc: '7.5' != '18.75'
  - trade 24.amount_usdc: '15.0' != '37.5'
  - trade 26.amount_usdc: '15.0' != '37.5'
  - balances: {'crypto': '0.01731820757311601048921256875', 'usdc': '505.0'} != {'crypto': '0.01988980246807650071759785811', 'usdc': '448.75'}
  - equity_curve[24]: ['2022-01-25T00:00:00+00:00', '996.3546678100995678225588161'] != ['2022-01-25T00:00:00+00:00', '996.4815403946509555524245852']
  - metrics.total_return_pct: -16.46255764078621 != -17.181800635922034 (must be identical)
  - metrics.net_pnl: -0.495 != -0.55125 (must be identical)
  - metrics.total_fees: 0.495 != 0.55125 (must be identical)
  - metrics.ending_balance: 835.3744235921379 != 828.1819936407796 (must be identical)
  - metrics.max_drawdown: '201.0535464814338707630603072' != '213.2998957604425695337210535' (must be identical)
  - schema-1 projection (ignoring moving / new / removed metric keys): $.metrics.ending_balance: 835.3744235921379 != 828.1819936407796

| Key | Old | New | Status | Cause |
|---|---|---|---|---|
| `total_trades` | 36 | 36 | identical | - |
| `winning_trades` | 0 | 0 | identical | - |
| `losing_trades` | 0 | 0 | identical | - |
| `win_rate` | 0.000000 | 0.000000 | identical | - |
| `total_return_pct` | -16.462558 | -17.181801 | DIFFERENT (violation) | - |
| `net_pnl` | -0.495000 | -0.551250 | DIFFERENT (violation) | - |
| `total_fees` | 0.495000 | 0.551250 | DIFFERENT (violation) | - |
| `total_pnl` | 0.000000 | 0.000000 | identical | - |
| `unrealized_pnl` | 0.000000 | 0.000000 | identical | - |
| `starting_balance` | 1000.000000 | 1000.000000 | identical | - |
| `ending_balance` | 835.374424 | 828.181994 | DIFFERENT (violation) | - |
| `duration_days` | 270.000000 | 270.000000 | identical | - |
| `average_holding_time_minutes` | 0.000000 | 0.000000 | identical | - |
| `max_drawdown` | 201.0535464814338707630603072 | 213.2998957604425695337210535 | DIFFERENT (violation) | - |
| `average_win` | 0 | 0 | identical | - |
| `average_loss` | 0 | 0 | identical | - |
| `sharpe_ratio` | -1.535326 | -1.396860 | moving | D1 daily resampling + unit; C2 anchor/ffill; C4 ddof=1 |
| `sortino_ratio` | -1.956746 | -1.806962 | moving | D1 daily resampling + unit; C2 anchor/ffill; C4 ddof=1 |
| `max_drawdown_pct -> max_drawdown_pct_daily` | n/a | 20.718048 | moving | D2 relative to running peak; D1/C2 daily NAV |
| `profit_factor` | n/a | n/a | moving | D3 net of the buy fee (pnl_net_trade); 0 losses -> None |
| `calmar_ratio` | -1.101615 | -1.085868 | moving | D2 (denominator) ; C5 geometric CAGR ; D1/C2 daily |
| `gross_loss_net` | - | 0.000000 | new | - |
| `gross_profit_net` | - | 0.000000 | new | - |
| `max_drawdown_pct_engine` | - | 20.718048 | new | - |
| `metrics_version` | - | 2 | new | - |
| `n_daily_returns` | - | 270 | new | - |
| `pf_excluded_trades` | - | 0 | new | - |
| `gross_loss_net` | 0.000000 | - | removed | - |
| `gross_profit_net` | 0.000000 | - | removed | - |
| `max_drawdown_pct_daily` | 19.594661 | - | removed | - |
| `max_drawdown_pct_engine` | 19.594661 | - | removed | - |
| `metrics_version` | 2 | - | removed | - |
| `n_daily_returns` | 270 | - | removed | - |
| `pf_excluded_trades` | 0 | - | removed | - |
