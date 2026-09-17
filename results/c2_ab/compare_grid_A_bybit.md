### GridBacktester — grok_grid_atr_adaptive_v4 BTC/USDC 2023-04-01 → 2026-04-01 (`--fees bybit`)

- trades: 2128 / equity points: 315650 / balances: {'crypto': '0', 'usdc': '1114.206947482765602539070709'}
- old engine: `/Users/stordd/wt-c1-ref/scripts/backtest.py` · new engine: `/Users/stordd/doc/GitHub/kraken-trading-bot/scripts/backtest.py`
- identity (trades on the 15 pre-C1 fields, balances, equity curve point by point, …): **VIOLATIONS**
  - trades: 2128 != 114
  - trade 1.timestamp: '2023-04-03T01:45:00+00:00' != '2023-12-11T02:15:00+00:00'
  - trade 2.timestamp: '2023-04-03T08:10:00+00:00' != '2023-12-20T14:00:00+00:00'
  - trade 3.timestamp: '2023-04-03T21:00:00+00:00' != '2024-01-03T12:05:00+00:00'
  - trade 4.timestamp: '2023-04-03T23:05:00+00:00' != '2024-01-08T12:05:00+00:00'
  - trade 5.timestamp: '2023-04-05T14:15:00+00:00' != '2024-01-12T22:05:00+00:00'
  - trade 6.timestamp: '2023-04-10T15:45:00+00:00' != '2024-02-07T21:35:00+00:00'
  - trade 7.timestamp: '2023-04-14T15:30:00+00:00' != '2024-02-09T15:10:00+00:00'
  - trade 8.timestamp: '2023-04-16T01:45:00+00:00' != '2024-02-09T15:15:00+00:00'
  - trade 9.timestamp: '2023-04-16T01:50:00+00:00' != '2024-03-05T17:15:00+00:00'
  - trade 10.timestamp: '2023-04-17T00:40:00+00:00' != '2024-03-05T20:00:00+00:00'
  - trade 11.timestamp: '2023-04-17T11:35:00+00:00' != '2024-03-05T20:15:00+00:00'
  - trade 12.timestamp: '2023-04-18T11:25:00+00:00' != '2024-03-06T08:00:00+00:00'
  - trade 13.timestamp: '2023-04-18T11:40:00+00:00' != '2024-03-15T02:55:00+00:00'
  - trade 14.timestamp: '2023-04-19T08:10:00+00:00' != '2024-03-16T23:20:00+00:00'
  - trade 15.timestamp: '2023-04-19T08:15:00+00:00' != '2024-03-17T16:40:00+00:00'
  - trade 16.timestamp: '2023-04-19T21:45:00+00:00' != '2024-03-19T07:05:00+00:00'
  - trade 17.timestamp: '2023-04-20T19:30:00+00:00' != '2024-03-20T20:35:00+00:00'
  - trade 18.timestamp: '2023-04-21T19:10:00+00:00' != '2024-03-22T14:00:00+00:00'
  - trade 19.timestamp: '2023-04-24T01:05:00+00:00' != '2024-03-24T18:35:00+00:00'
  - trade 20.timestamp: '2023-04-24T08:55:00+00:00' != '2024-03-25T20:05:00+00:00'
  - ... (truncated)
  - balances: {'crypto': '0', 'usdc': '1114.206947482765602539070709'} != {'crypto': '0', 'usdc': '1045.722405322421403208156383'}
  - equity_curve[597]: ['2023-04-03T01:45:00+00:00', '999.9740101819125133759201012'] != ['2023-04-03T01:45:00+00:00', '1000.00000000']
  - grid: differs
  - metrics.total_trades: 1064 != 57 (must be identical)
  - metrics.winning_trades: 1031 != 53 (must be identical)
  - metrics.losing_trades: 33 != 4 (must be identical)
  - metrics.win_rate: 0.9689849624060151 != 0.9298245614035088 (must be identical)
  - metrics.total_return_pct: 11.42069474827656 != 4.57224053224214 (must be identical)
  - metrics.net_pnl: 114.2069474827656 != 45.7224053224214 (must be identical)
  - metrics.total_fees: 54.23816600941196 != 3.0245249239127974 (must be identical)
  - metrics.total_pnl: 140.8069474827656 != 47.147405322421406 (must be identical)
  - metrics.unrealized_pnl: -228.1216042133417 != -15.310009211802027 (must be identical)
  - metrics.ending_balance: 1114.2069474827656 != 1045.7224053224213 (must be identical)
  - metrics.average_holding_time_minutes: 1434.8593598448108 != 5776.981132075472 (must be identical)
  - metrics.max_drawdown: '260.195240019090295356227684' != '27.030722940924218247000434' (must be identical)
  - metrics.average_win: '0.3578356466499585896241559721' != '1.178441783664593022111397519' (must be identical)
  - metrics.average_loss: '-6.912775885252778889801033418' != '-3.827502302950506740936920945' (must be identical)
  - schema-1 projection (ignoring moving / new / removed metric keys): $.grid.fills.buy: 1064 != 57

| Key | Old | New | Status | Cause |
|---|---|---|---|---|
| `total_trades` | 1064 | 57 | DIFFERENT (violation) | - |
| `winning_trades` | 1031 | 53 | DIFFERENT (violation) | - |
| `losing_trades` | 33 | 4 | DIFFERENT (violation) | - |
| `win_rate` | 0.968985 | 0.929825 | DIFFERENT (violation) | - |
| `total_return_pct` | 11.420695 | 4.572241 | DIFFERENT (violation) | - |
| `net_pnl` | 114.206947 | 45.722405 | DIFFERENT (violation) | - |
| `total_fees` | 54.238166 | 3.024525 | DIFFERENT (violation) | - |
| `total_pnl` | 140.806947 | 47.147405 | DIFFERENT (violation) | - |
| `unrealized_pnl` | -228.121604 | -15.310009 | DIFFERENT (violation) | - |
| `starting_balance` | 1000.000000 | 1000.000000 | identical | - |
| `ending_balance` | 1114.206947 | 1045.722405 | DIFFERENT (violation) | - |
| `duration_days` | 1096.000000 | 1096.000000 | identical | - |
| `average_holding_time_minutes` | 1434.859360 | 5776.981132 | DIFFERENT (violation) | - |
| `max_drawdown` | 260.195240019090295356227684 | 27.030722940924218247000434 | DIFFERENT (violation) | - |
| `average_win` | 0.3578356466499585896241559721 | 1.178441783664593022111397519 | DIFFERENT (violation) | - |
| `average_loss` | -6.912775885252778889801033418 | -3.827502302950506740936920945 | DIFFERENT (violation) | - |
| `sharpe_ratio` | 0.367125 | 0.930586 | moving | D1 daily resampling + unit; C2 anchor/ffill; C4 ddof=1 |
| `sortino_ratio` | 0.523637 | 1.493563 | moving | D1 daily resampling + unit; C2 anchor/ffill; C4 ddof=1 |
| `max_drawdown_pct -> max_drawdown_pct_daily` | n/a | 2.044308 | moving | D2 relative to running peak; D1/C2 daily NAV |
| `profit_factor` | 1.498837 | 3.967059 | moving | D3 net of the buy fee (pnl_net_trade); 0 losses -> None |
| `calmar_ratio` | 0.204106 | 0.733766 | moving | D2 (denominator) ; C5 geometric CAGR ; D1/C2 daily |
| `gross_loss_net` | - | 15.410009 | new | - |
| `gross_profit_net` | - | 61.132415 | new | - |
| `max_drawdown_pct_engine` | - | 2.574449 | new | - |
| `metrics_version` | - | 2 | new | - |
| `n_daily_returns` | - | 1096 | new | - |
| `pf_excluded_trades` | - | 0 | new | - |
| `gross_loss_net` | 228.946604 | - | removed | - |
| `gross_profit_net` | 343.153552 | - | removed | - |
| `max_drawdown_pct_daily` | 17.966712 | - | removed | - |
| `max_drawdown_pct_engine` | 19.989342 | - | removed | - |
| `metrics_version` | 2 | - | removed | - |
| `n_daily_returns` | 1096 | - | removed | - |
| `pf_excluded_trades` | 0 | - | removed | - |
