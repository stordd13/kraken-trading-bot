### GridBacktester — grok_grid_atr_adaptive_v4 BTC/USDC 2025-03-01 → 2025-03-15 (`--fees bybit`)

- trades: 90 / equity points: 4034 / balances: {'crypto': '0', 'usdc': '1000.654537804206683177476290'}
- old engine: `/Users/stordd/wt-c1-ref/scripts/backtest.py` · new engine: `/Users/stordd/doc/GitHub/kraken-trading-bot/scripts/backtest.py`
- identity (trades on the 15 pre-C1 fields, balances, equity curve point by point, …): **VIOLATIONS**
  - trades: 90 != 4
  - trade 1.timestamp: '2025-03-03T01:15:00+00:00' != '2025-03-03T20:05:00+00:00'
  - trade 2.timestamp: '2025-03-03T06:50:00+00:00' != '2025-03-05T10:35:00+00:00'
  - trade 3.timestamp: '2025-03-03T13:45:00+00:00' != '2025-03-07T00:50:00+00:00'
  - trade 4.timestamp: '2025-03-03T14:40:00+00:00' != '2025-03-07T09:35:00+00:00'
  - balances: {'crypto': '0', 'usdc': '1000.654537804206683177476290'} != {'crypto': '0', 'usdc': '1002.395048128024284297185500'}
  - equity_curve: 4034 != 4033 points
  - equity_curve[591]: ['2025-03-03T01:15:00+00:00', '999.9704547779603669108287800'] != ['2025-03-03T01:15:00+00:00', '1000.00000000']
  - grid: differs
  - metrics.total_trades: 45 != 2 (must be identical)
  - metrics.winning_trades: 37 != 2 (must be identical)
  - metrics.losing_trades: 8 != 0 (must be identical)
  - metrics.win_rate: 0.8222222222222222 != 1.0 (must be identical)
  - metrics.total_return_pct: 0.06545378042066832 != 0.23950481280242844 (must be identical)
  - metrics.net_pnl: 0.6545378042066832 != 2.395048128024284 (must be identical)
  - metrics.total_fees: 2.535269927635404 != 0.10244749562364794 (must be identical)
  - metrics.total_pnl: 1.7795378042066832 != 2.4450481280242844 (must be identical)
  - metrics.unrealized_pnl: -11.468595264131189 != 0.0 (must be identical)
  - metrics.ending_balance: 1000.6545378042067 != 1002.3950481280243 (must be identical)
  - metrics.average_holding_time_minutes: 323.7837837837838 != 1417.5 (must be identical)
  - metrics.max_drawdown: '30.8222400221688126771728011' != '1.4796969355802781348658164' (must be identical)
  - metrics.average_win: '0.3580576504956181517038574119' != '1.22252406401214214859275011' (must be identical)
  - metrics.average_loss: '-1.433574408016398554445804271' != '0' (must be identical)
  - schema-1 projection (ignoring moving / new / removed metric keys): $.grid.fills.buy: 45 != 2

| Key | Old | New | Status | Cause |
|---|---|---|---|---|
| `total_trades` | 45 | 2 | DIFFERENT (violation) | - |
| `winning_trades` | 37 | 2 | DIFFERENT (violation) | - |
| `losing_trades` | 8 | 0 | DIFFERENT (violation) | - |
| `win_rate` | 0.822222 | 1.000000 | DIFFERENT (violation) | - |
| `total_return_pct` | 0.065454 | 0.239505 | DIFFERENT (violation) | - |
| `net_pnl` | 0.654538 | 2.395048 | DIFFERENT (violation) | - |
| `total_fees` | 2.535270 | 0.102447 | DIFFERENT (violation) | - |
| `total_pnl` | 1.779538 | 2.445048 | DIFFERENT (violation) | - |
| `unrealized_pnl` | -11.468595 | 0.000000 | DIFFERENT (violation) | - |
| `starting_balance` | 1000.000000 | 1000.000000 | identical | - |
| `ending_balance` | 1000.654538 | 1002.395048 | DIFFERENT (violation) | - |
| `duration_days` | 14.000000 | 14.000000 | identical | - |
| `average_holding_time_minutes` | 323.783784 | 1417.500000 | DIFFERENT (violation) | - |
| `max_drawdown` | 30.8222400221688126771728011 | 1.4796969355802781348658164 | DIFFERENT (violation) | - |
| `average_win` | 0.3580576504956181517038574119 | 1.22252406401214214859275011 | DIFFERENT (violation) | - |
| `average_loss` | -1.433574408016398554445804271 | 0 | DIFFERENT (violation) | - |
| `sharpe_ratio` | 0.188154 | 9.164218 | moving | D1 daily resampling + unit; C2 anchor/ffill; C4 ddof=1 |
| `sortino_ratio` | 0.288301 | n/a | moving | D1 daily resampling + unit; C2 anchor/ffill; C4 ddof=1 |
| `max_drawdown_pct -> max_drawdown_pct_daily` | n/a | 0.000000 | moving | D2 relative to running peak; D1/C2 daily NAV |
| `profit_factor` | 1.056094 | n/a | moving | D3 net of the buy fee (pnl_net_trade); 0 losses -> None |
| `calmar_ratio` | 0.782173 | n/a | moving | D2 (denominator) ; C5 geometric CAGR ; D1/C2 daily |
| `gross_loss_net` | - | 0.000000 | new | - |
| `gross_profit_net` | - | 2.395048 | new | - |
| `max_drawdown_pct_engine` | - | 0.147910 | new | - |
| `metrics_version` | - | 2 | new | - |
| `n_daily_returns` | - | 14 | new | - |
| `pf_excluded_trades` | - | 0 | new | - |
| `gross_loss_net` | 11.668595 | - | removed | - |
| `gross_profit_net` | 12.323133 | - | removed | - |
| `max_drawdown_pct_daily` | 2.199705 | - | removed | - |
| `max_drawdown_pct_engine` | 3.064055 | - | removed | - |
| `metrics_version` | 2 | - | removed | - |
| `n_daily_returns` | 14 | - | removed | - |
| `pf_excluded_trades` | 0 | - | removed | - |
