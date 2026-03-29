# Fast-Cash v1 Runbook

Operational profile for the next 30 days.

## Scope

- No ML work
- No new strategies
- Single-pair runtime only: `XBT/USDC`
- Active inner strategies:
  - `grok_grid_atr_adaptive_v4`
  - `grok_supertrend_4h`
- Parked until J30 review:
  - `grok_ema_adx_atr`
  - `grok_adaptive_dca_weekly`

## Active Runtime Config

The live `strategies.yaml` config is aligned to this profile:

- `capital_usdc = 1000`
- `global_max_open_positions = 8`
- `global_daily_loss_limit_eur = 15`
- `global_max_portfolio_exposure_pct = 25`
- `grid_atr_v4.order_size_usdc = 10`
- `grid_atr_v4.max_allocation_pct = 10`
- `supertrend_4h.max_allocation_pct = 10`
- SuperTrend sizing controlled by GeminiGlobalRiskManager 1% rule
  (max loss per trade = 1% of capital = ~$10 = ~9.2 EUR)

Pair selection remains environment-driven. The repo defaults already target `TRADING_PAIR=XBT/USDC`.

## Commands

Paper:

```bash
poetry run python -m krakenbot
```

Dashboard:

```bash
poetry run python scripts/dashboard.py
```

Status snapshot:

```bash
poetry run python scripts/status.py
```

Micro-live:

```bash
TRADING_MODE=live TRADING_CONFIRM_LIVE=yes poetry run python -m krakenbot
```

## Timeline

### J0-J1

- Keep `TRADING_MODE=paper`
- Verify:
  - `pytest -q`
  - `pytest -q tests/test_integration_p0_p1.py`
  - dashboard shows open positions, pending orders, runtime/paper P&L

### J1-J7

- Paper only
- Review twice per day
- Log daily:
  - signal count
  - orders placed
  - orders expired
  - orders filled
  - realized P&L
  - open positions
  - pending orders at end of day
  - runtime / execution / order manager errors

### J8-J21

- Keep the same config
- Switch to micro-live only if J1-J7 is clean
- Stop and return to paper if any of the following happens:
  - order / position mismatch
  - paper/live balance drift
  - pending order still stuck after expiry
  - 2 execution-related runtime errors in 24h
  - realized daily loss `>= 15 EUR`

### J22-J30

- If execution is clean, scale by +50%:
  - `grid_atr_v4.order_size_usdc = 15`
  - Increase `capital_usdc` to 1500 (SuperTrend auto-scales via 1% rule)
- Otherwise:
  - keep current sizes if the system is healthy but flat
  - return to paper if live behavior diverges from the execution model

## Go / No-Go Gates

Paper -> live:

- `0` runtime integration bug
- `0` paper balance drift
- `0` orphan pending order after expiry
- `0` `position_id` mismatch
- if `0 fill` over 7 days, extend paper by 7 more days

Live -> scale:

- `0` blocking execution incident
- `0` balance / position divergence
- fill behavior and fees not worse than `25%` vs paper/backtest model
- total live P&L `>= -1%` of deployed capital
