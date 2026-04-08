# Paper Trading Debug Report (Phase 0)

## Date: 2026-04-08

---

## Problem 1: Grid ATR V4 — Levels at 50% Below Price (CRITIQUE)

### Root Cause

`_calculate_spacing()` had no maximum cap. With ATR(14,4h) ~$2000-3000
and `atr_multiplier=4.0`, spacing computed to 9.6%-14.5%. With bear bias
giving 7 BUY levels, the lowest level reached:

```
83000 * (1 - 0.096 * 7) = $27,240
```

This explains the 36 expired LIMIT BUY orders between 37K-65K.

### Fix Applied

Added `max_spacing_pct` parameter (default 0.05 = 5%) to clamp spacing:

```python
# Before (no cap):
return max(self.min_spacing_pct, atr_spacing)

# After (capped):
return max(self.min_spacing_pct, min(self.max_spacing_pct, atr_spacing))
```

### Before/After

| Metric | Before | After |
|--------|--------|-------|
| Spacing (ATR=$2000, BTC=$83K) | 9.64% | 5.00% |
| Lowest BUY (7 levels, bear bias) | $27,240 | $53,950 |
| Lowest BUY (6 levels, neutral) | $33,000 | $58,100 |
| Highest SELL (5 levels, bear bias) | $123,000 | $103,750 |

### Tests Added (test_grid_atr_debug.py)

- `test_spacing_capped_at_max` — ATR=$5000 -> spacing = 5% (not 24%)
- `test_spacing_uses_atr_when_within_bounds` — ATR in range -> uses ATR formula
- `test_spacing_floor_enforced` — ATR very low -> spacing = 1.5%
- `test_spacing_with_zero_price` — edge case -> returns min_spacing
- `test_buy_levels_below_sell_levels_above` — side coherence
- `test_max_distance_with_capped_spacing` — levels within 30% of price
- `test_recalc_recenters_grid` — recalc moves center to new price
- `test_recalc_timer_triggers` — 6h timer works via _handle_ohlc
- `test_get_config_has_max_spacing_pct` — config includes new param

---

## Problem 2: SuperTrend 4h — No Trades

### Diagnosis: Correct Behavior (No Bug)

BTC at ~$83K, down from ATH ~$112K. Daily EMA(20) < EMA(50), so
`get_regime("1d")` returns `"bear"` or `"neutral"`. Entry requires
`regime_1d in ("bull", "strong_bull")`, so all entries are correctly
filtered out.

**The strategy is working as designed — waiting for a bull regime.**

### Fix Applied

Added diagnostic logging at 3 points so the behavior is visible:

1. `strategy_tick` in `_handle_ohlc` — fires on every 4h candle with final signal result
2. `supertrend_entry_filtered` in `_check_entry` — logs when ST direction rejects
3. `supertrend_entry_filtered` in `_check_entry` — logs when regime filter rejects

### Tests Added (test_supertrend_debug.py)

- `test_no_buy_in_bear_regime` — bear regime -> no signal
- `test_no_buy_in_neutral_regime` — neutral regime -> no signal
- `test_no_buy_in_strong_bear_regime` — strong bear -> no signal
- `test_buy_in_bull_regime` — bull + ST UP -> BUY signal
- `test_buy_in_strong_bull_regime` — strong bull -> BUY signal
- `test_no_buy_when_st_direction_down` — ST DOWN + bull -> no signal
- `test_4h_candle_produces_strategy_tick_log` — every 4h candle -> strategy_tick log
- `test_filtered_entry_produces_log` — regime rejection -> supertrend_entry_filtered log
- `test_non_4h_candle_skips_signal` — non-4h candles -> no strategy_tick log

---

## Problem 3: Global Diagnostic Logging

### Format Standardized

All active strategies now emit a `strategy_tick` log on every relevant candle:

```python
log.info("strategy_tick",
    strategy=name,          # e.g. "grok_grid_atr_adaptive_v4"
    bot_id=bot_id,          # e.g. "grid_atr_v4"
    pair=pair,              # e.g. "XBT/USDC"
    timeframe=tf,           # "4h"
    close=str(close),       # Decimal as string
    signal=signal,          # "BUY" | "SELL" | "HOLD" | "FILTERED" | "PAUSED"
    reason=reason,          # Human-readable reason
    metadata={...})         # Strategy-specific indicators
```

### Strategies Updated

| Strategy | Log Points |
|----------|-----------|
| `grok_grid_atr_adaptive_v4` | grid_evaluation (every 4h), weekly_strong_bear (PAUSED), atr_unavailable (HOLD) |
| `grok_supertrend_4h` | strategy_tick (every 4h), st_direction_down (FILTERED), regime_not_bullish (FILTERED) |

### Future Use

These logs can be consumed by:
- Telegram alerts (filter `event == "strategy_tick"`)
- Dashboard monitoring
- Post-hoc analysis of paper trading periods
