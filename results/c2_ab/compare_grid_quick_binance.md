### GridBacktester — grok_grid_atr_adaptive_v4 BTC/USDC 2025-03-01 → 2025-03-15 (`--fees binance`)

- trades: 90 / equity points: 4034 / balances: {'crypto': '0', 'usdc': '1001.520224293757642926965040'}
- old engine: `/Users/stordd/wt-c1-ref/scripts/backtest.py` · new engine: `/Users/stordd/doc/GitHub/kraken-trading-bot/scripts/backtest.py`
- identity (trades on the 15 pre-C1 fields, balances, equity curve point by point, …): **VIOLATIONS**
  - trades: 90 != 4
  - trade 1.timestamp: '2025-03-03T01:15:00+00:00' != '2025-03-03T20:05:00+00:00'
  - trade 2.timestamp: '2025-03-03T06:50:00+00:00' != '2025-03-05T10:35:00+00:00'
  - trade 3.timestamp: '2025-03-03T13:45:00+00:00' != '2025-03-07T00:50:00+00:00'
  - trade 4.timestamp: '2025-03-03T14:40:00+00:00' != '2025-03-07T09:35:00+00:00'
  - balances: {'crypto': '0', 'usdc': '1001.520224293757642926965040'} != {'crypto': '0', 'usdc': '1002.421275157085834467500172'}
  - equity_curve: 4034 != 4033 points
  - equity_curve[591]: ['2025-03-03T01:15:00+00:00', '999.9767036405174140496953537'] != ['2025-03-03T01:15:00+00:00', '1000.00000000']
  - grid: differs
  - metrics.total_trades: 45 != 2 (must be identical)
  - metrics.winning_trades: 37 != 2 (must be identical)
  - metrics.losing_trades: 8 != 0 (must be identical)
  - metrics.win_rate: 0.8222222222222222 != 1.0 (must be identical)
  - metrics.total_return_pct: 0.1520224293757643 != 0.24212751570858346 (must be identical)
  - metrics.net_pnl: 1.520224293757643 != 2.4212751570858346 (must be identical)
  - metrics.total_fees: 1.6892743114539086 != 0.07684546546691456 (must be identical)
  - metrics.total_pnl: 2.363974293757643 != 2.4587751570858343 (must be identical)
  - metrics.unrealized_pnl: -11.12209817184882 != 0.0 (must be identical)
  - metrics.ending_balance: 1001.5202242937577 != 1002.4212751570858 (must be identical)
  - metrics.average_holding_time_minutes: 323.7837837837838 != 1417.5 (must be identical)
  - metrics.max_drawdown: '30.6980632678669756360294998' != '1.4800672301087016278925598' (must be identical)
  - metrics.average_win: '0.3644884450163908936579341703' != '1.229387578542917233750085995' (must be identical)
  - metrics.average_loss: '-1.390262271481102517297315538' != '0' (must be identical)
  - schema-1 projection (ignoring moving / new / removed metric keys): $.grid.fills.buy: 45 != 2

| Key | Old | New | Status | Cause |
|---|---|---|---|---|
| `total_trades` | 45 | 2 | DIFFERENT (violation) | - |
| `winning_trades` | 37 | 2 | DIFFERENT (violation) | - |
| `losing_trades` | 8 | 0 | DIFFERENT (violation) | - |
| `win_rate` | 0.822222 | 1.000000 | DIFFERENT (violation) | - |
| `total_return_pct` | 0.152022 | 0.242128 | DIFFERENT (violation) | - |
| `net_pnl` | 1.520224 | 2.421275 | DIFFERENT (violation) | - |
| `total_fees` | 1.689274 | 0.076845 | DIFFERENT (violation) | - |
| `total_pnl` | 2.363974 | 2.458775 | DIFFERENT (violation) | - |
| `unrealized_pnl` | -11.122098 | 0.000000 | DIFFERENT (violation) | - |
| `starting_balance` | 1000.000000 | 1000.000000 | identical | - |
| `ending_balance` | 1001.520224 | 1002.421275 | DIFFERENT (violation) | - |
| `duration_days` | 14.000000 | 14.000000 | identical | - |
| `average_holding_time_minutes` | 323.783784 | 1417.500000 | DIFFERENT (violation) | - |
| `max_drawdown` | 30.6980632678669756360294998 | 1.4800672301087016278925598 | DIFFERENT (violation) | - |
| `average_win` | 0.3644884450163908936579341703 | 1.229387578542917233750085995 | DIFFERENT (violation) | - |
| `average_loss` | -1.390262271481102517297315538 | 0 | DIFFERENT (violation) | - |
| `sharpe_ratio` | 0.351973 | 9.169936 | moving | D1 daily resampling + unit; C2 anchor/ffill; C4 ddof=1 |
| `sortino_ratio` | 0.544204 | n/a | moving | D1 daily resampling + unit; C2 anchor/ffill; C4 ddof=1 |
| `max_drawdown_pct -> max_drawdown_pct_daily` | n/a | 0.000000 | moving | D2 relative to running peak; D1/C2 daily NAV |
| `profit_factor` | 1.134866 | n/a | moving | D3 net of the buy fee (pnl_net_trade); 0 losses -> None |
| `calmar_ratio` | 1.851280 | n/a | moving | D2 (denominator) ; C5 geometric CAGR ; D1/C2 daily |
| `gross_loss_net` | - | 0.000000 | new | - |
| `gross_profit_net` | - | 2.421275 | new | - |
| `max_drawdown_pct_engine` | - | 0.147946 | new | - |
| `metrics_version` | - | 2 | new | - |
| `n_daily_returns` | - | 14 | new | - |
| `pf_excluded_trades` | - | 0 | new | - |
| `gross_loss_net` | 11.272098 | - | removed | - |
| `gross_profit_net` | 12.792322 | - | removed | - |
| `max_drawdown_pct_daily` | 2.182222 | - | removed | - |
| `max_drawdown_pct_engine` | 3.050866 | - | removed | - |
| `metrics_version` | 2 | - | removed | - |
| `n_daily_returns` | 14 | - | removed | - |
| `pf_excluded_trades` | 0 | - | removed | - |
