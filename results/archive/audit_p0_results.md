# P0 Audit Results — Sizing & Risk Overlay

**Date**: 2026-03-29
**Branch**: `audit/p0-sizing`

---

## Audit 1: Sizing Backtest = Runtime

### Runtime Sizing Path

```
Strategy.generate_signal()
  → metadata: { order_size_usdc, position_size_multiplier }
  → MultiStrategyRouter._apply_risk_overlay()
    → GeminiGlobalRiskManager.process_signal()
      - SL = entry - 3.0 × ATR(14, 4h)
      - size_btc = (capital × 1%) / |entry - SL|
      - position_size_multiplier = min(strategy_mult, risk_mult)
  → ExecutionEngine._resolve_open_order_notional()
    - Priority 1: metadata["order_size_usdc"] (if present)
    - Priority 2: default_order_amount_eur × metadata["position_size_multiplier"]
  → amount_btc = notional / price
```

### Backtest Sizing Path (BEFORE fix)

```
Strategy.generate_signal()
  → BacktestEngine.execute_signal()
    - Priority 1: metadata["order_size_usdc"] (if present, for OTF strategies)
    - Priority 2: default_order_amount_eur (NO multiplier applied)
```

### Divergence Found

**`position_size_multiplier` was ignored in backtest fallback path.**

When `order_size_usdc` is absent, runtime uses `default × multiplier`, backtest used `default` only. The risk overlay constrains the multiplier via `min(strategy_mult, risk_mult)`, so backtest could oversize positions relative to runtime.

**Current impact**: None for active strategies (all set `order_size_usdc` explicitly). Future strategies using only the multiplier would have been affected.

### Fix Applied

`scripts/backtest.py` line 532-538: added `position_size_multiplier` application in fallback path.

### Test Added

- `test_sizing_multiplier_path_matches_runtime`: signal with `position_size_multiplier=0.5`, no `order_size_usdc` — verifies runtime and backtest produce the same notional.

---

## Audit 2: Risk Overlay Completeness

### Signal Path Matrix

All 5 strategies use custom `_handle_ohlc()`. The `MultiStrategyRouter` wraps each strategy's EventBus with `_RiskOverlayEventBusProxy`, which intercepts all `TRADE_SIGNAL` emissions and routes them through `_apply_risk_overlay()`.

| Strategy | Custom `_handle_ohlc` | Risk overlay mechanism | Covered |
|---|---|---|---|
| grok_grid_atr_adaptive_v4 | Yes | `_RiskOverlayEventBusProxy` | YES |
| grok_supertrend_4h | Yes | `_RiskOverlayEventBusProxy` | YES |
| grok_ema_adx_atr | Yes | `_RiskOverlayEventBusProxy` | YES |
| grok_adaptive_dca_weekly | Yes | `_RiskOverlayEventBusProxy` | YES |
| grok_donchian_breakout_4h | Yes | `_RiskOverlayEventBusProxy` | YES |

**No bypass path exists.** SELL signals pass through unchanged (line 344 of risk manager).

### Tests Added

- `test_risk_overlay_values_supertrend`: verifies SL = entry - 3 x ATR, and 1% rule sizing formula
- `test_risk_overlay_values_grid`: verifies SL < entry, multiplier constrained, position value < capital
- `test_risk_overlay_atr_overrides_bad_strategy_stop_loss`: strategy SL > entry is overridden by ATR-based SL
- `test_sell_signal_passes_through_unchanged`: SELL signal not modified by risk overlay

---

## Audit 3: Daily Loss vs SuperTrend Stop Coherence

### Calculation

**Parameters:**
- `supertrend_4h.order_size_usdc = 100 USDC`
- `global_daily_loss_limit_eur = 15 EUR`
- Risk manager SL: `entry - 3.0 × ATR(14, 4h)`

**Worst-case ATR scenarios:**

| Scenario | ATR(14, 4h) | Entry | SL | Loss % | Loss on 100 USDC | Loss EUR (~0.92) |
|---|---|---|---|---|---|---|
| Normal market | $1,500 | $84,000 | $79,500 | 5.4% | $5.36 | ~4.9 EUR |
| Elevated vol | $3,000 | $84,000 | $75,000 | 10.7% | $10.71 | ~9.9 EUR |
| High vol (2022) | $5,000 | $84,000 | $69,000 | 17.9% | $17.86 | ~16.4 EUR |
| Extreme | $6,000 | $84,000 | $66,000 | 21.4% | $21.43 | ~19.7 EUR |

**Note:** The 1% risk rule limits the BTC position size such that the dollar loss at SL equals 1% of capital = $10. However, `order_size_usdc` takes priority over the multiplier in `_resolve_open_order_notional()`. So if `order_size_usdc=100` is set, the 100 USDC is used directly regardless of the 1% rule.

**Actual risk:** The 1% rule adjusts `position_size_multiplier` but this is ignored when `order_size_usdc` is present. With `order_size_usdc=100` and ATR=$5,000, max loss = 100 × (15,000/84,000) = ~$17.86 = ~16.4 EUR.

### Verdict

**Worst-case single-trade loss (16.4 EUR) exceeds daily_loss_limit (15 EUR).**

### Recommendations

1. **Option A**: Reduce `supertrend_4h.order_size_usdc` to 80 USDC (worst-case loss ~13.1 EUR)
2. **Option B**: Raise `global_daily_loss_limit_eur` to 20 EUR
3. **Option C**: Remove `order_size_usdc` from SuperTrend and let the 1% rule size via `position_size_multiplier` — this guarantees max loss = 1% of capital = $10 = ~9.2 EUR

Option C is the most robust as it lets the risk overlay actually control sizing.

---

## Tests Added Summary

| Test | File | Audit |
|---|---|---|
| `test_sizing_multiplier_path_matches_runtime` | `tests/test_integration_p0_p1.py` | 1 |
| `test_risk_overlay_values_supertrend` | `tests/test_integration_p0_p1.py` | 2 |
| `test_risk_overlay_values_grid` | `tests/test_integration_p0_p1.py` | 2 |
| `test_risk_overlay_atr_overrides_bad_strategy_stop_loss` | `tests/test_integration_p0_p1.py` | 2 |
| `test_sell_signal_passes_through_unchanged` | `tests/test_integration_p0_p1.py` | 2 |
| `test_one_percent_rule_caps_loss_across_atr_scenarios[normal]` | `tests/test_integration_p0_p1.py` | 3/C |
| `test_one_percent_rule_caps_loss_across_atr_scenarios[elevated]` | `tests/test_integration_p0_p1.py` | 3/C |
| `test_one_percent_rule_caps_loss_across_atr_scenarios[high_vol]` | `tests/test_integration_p0_p1.py` | 3/C |

---

## Option C Applied

### Changes
- Removed `order_size_usdc` from BUY signal metadata: `grok_supertrend_4h`, `grok_ema_adx_atr`, `grok_donchian_breakout_4h`
- Removed `order_size_usdc` from `strategies.yaml` for same 3 strategies
- Kept `order_size_usdc` for: `grok_grid_atr_adaptive_v4` (10 USDC, fixed per grid level)
- Kept `base_amount_usdc` for: `grok_adaptive_dca_weekly` (15 USDC, dynamic DCA)
- `default_order_amount_eur` = 100.0 (settings.py default, used as base for multiplier)
- SELL metadata still includes `order_size_usdc` (tracks actual position size for ExecutionEngine)

### Sizing Verification (SuperTrend, capital=1000, default_order=100)

| Scenario | ATR | Entry | SL | 1% Size BTC | Notional USDC | Loss at SL |
|---|---|---|---|---|---|---|
| Normal | $1,500 | $84,000 | $79,500 | 0.00222 | $18.67 | $10.00 |
| Elevated | $3,000 | $84,000 | $75,000 | 0.00111 | $9.33 | $10.00 |
| High vol | $5,000 | $84,000 | $69,000 | 0.000667 | $5.60 | $10.00 |

### Daily Loss Coherence
- Max loss per trade: $10.00 = ~9.2 EUR
- Daily loss limit: 15 EUR
- Margin of safety: ~63%
- Single-trade worst case can never breach the daily limit
