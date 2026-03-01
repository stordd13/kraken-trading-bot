# Phase 1B — Backtest Results: 3 New Trend-Following 4h Strategies

**Date**: 2026-03-01
**Period**: 2017-09-04 to 2026-03-01 (3100 days / ~8.5 years)
**Capital**: 1000 USDC | **Pair**: XBT/USDC
**Fees**: maker 0.16%, taker 0.26%, spread 0.02%, slippage 0.01%
**Execution**: Next-bar model (signal on candle N, fill at candle N+1)

---

## Summary Table

| Metric | Ichimoku Cloud 4h | Donchian Breakout 4h | VWAP Trend 4h | SuperTrend 4h (ref) |
|---|---|---|---|---|
| **Total Return** | +6.14% | +11.29% | +2.09% | +20.6% |
| **Net P&L (USDC)** | +39.88 | +96.27 | -42.61 | +206.0 |
| **Total Fees** | 34.66 | 26.59 | 102.49 | ~15 |
| **Total Trades** | 164 | 125 | 487 | 57 |
| **Win Rate** | 25.00% | 38.40% | 22.18% | 47.4% |
| **Avg Win** | +5.61 | +5.34 | +3.12 | — |
| **Avg Loss** | -1.27 | -1.73 | -0.73 | — |
| **Profit Factor** | 1.48 | 1.92 | 1.22 | 2.81 |
| **Max Drawdown %** | 5.40% | 2.85% | 5.28% | 5.8% |
| **Sharpe Ratio** | 0.16 | 0.32 | 0.06 | 0.49 |
| **Sortino Ratio** | 0.23 | 0.46 | 0.09 | — |
| **Avg Holding Time** | 97h | 114h | 35h | ~120h |

**Survival criteria**: Sharpe > 0.4, MaxDD < 15%, PF > 2.0, trades > 50

---

## Detailed Analysis

### 1. Donchian Breakout 4h — BEST of the three

**Verdict: WATCH** (promising but below survival thresholds)

- **Strengths**: Highest return (+11.29%), best Sharpe (0.32), best win rate (38.4%), very low drawdown (2.85%), high PF (1.92)
- **Weaknesses**: Sharpe 0.32 < 0.4 threshold, PF 1.92 < 2.0 threshold — just below cutoffs
- **Character**: Classic turtle-trader breakout. 125 trades over 8.5 years = ~15/year. Long holding period (~5 days). Lets winners run with Donchian lower(10) as natural trailing stop.
- **Potential**: Parameter tuning could push it above survival thresholds. ADX filter (18) may be too restrictive for some bull trends. Consider testing with ADX 15 or removing ADX filter entirely.

### 2. Ichimoku Cloud 4h — MEDIOCRE

**Verdict: KILL** (too many losing trades, weak edge)

- **Return**: +6.14% over 8.5 years — barely beats a savings account
- **Win rate**: 25% — 3 out of 4 trades lose, relying on outsized winners
- **Problem**: The cloud breakout condition is legitimate, but the cloud acts as support/resistance poorly in volatile crypto markets. Many false breakouts.
- **Fees**: 34.66 USDC in fees on 39.88 net P&L — fees consume nearly half the edge
- **Sharpe**: 0.16 — no meaningful risk-adjusted return

### 3. VWAP Trend 4h — KILL

**Verdict: KILL** (negative net P&L, fee-destroyed edge)

- **Return**: +2.09% ending balance but **-42.61 USDC net P&L** after fees
- **Problem**: 487 trades over 8.5 years = ~57/year — too many trades for a 4h strategy. The VWAP crossover is too noisy; it whipsaws in/out constantly.
- **Fees**: 102.49 USDC — fees exceed gross P&L. The strategy generates "activity" not "alpha"
- **Win rate**: 22.18% with tiny avg win (+3.12) and avg loss (-0.73) — the win/loss ratio (4.3:1) is decent but win rate is too low
- **Sharpe**: 0.06 — essentially random

---

## Bugs Found & Fixed During Development

1. **Donchian entry impossible (CRITICAL)**: `close > dc_upper` was always False because `dc_upper = max(last 20 highs)` includes the current candle's high, and close <= high always. Fixed by comparing against `_prev_donchian_upper` (previous candle's Donchian upper).

2. **Analyzer not fed in BacktestEngine replay loop**: The grok_* strategies don't call `analyzer.update()` internally (they rely on MultiStrategyRouter in live mode). Added `bt_analyzer.update(ohlc_data, interval)` in the backtest replay loop before `on_ohlc`.

3. **`_is_4h` flag not initialized**: The flag was only set in `_handle_ohlc()` (EventBus handler), never in `__init__`. Added `self._is_4h: bool = False` to all strategy constructors + explicit flag setting in the backtest loop.

4. **Regime tracking shows UNKNOWN**: The backtest report reads `_last_analysis.regime` which requires calling `analyzer.analyze()` — not done in the replay loop. Strategies use `get_regime("1d")` directly (which works). This is a cosmetic reporting issue only.

---

## Recommendation

| Strategy | Action | Reason |
|---|---|---|
| Donchian Breakout 4h | **WATCH** | Best of the three, close to survival thresholds. Worth param optimization. |
| Ichimoku Cloud 4h | **KILL** | Weak edge, low Sharpe, too many losing trades. |
| VWAP Trend 4h | **KILL** | Negative net P&L, fees destroy any edge. |
| SuperTrend 4h (ref) | **KEEP** | Still the best 4h trend-follower (Sharpe 0.49, PF 2.81). |

### Next Steps for Donchian

If pursuing Donchian optimization:
1. Lower ADX threshold from 18 to 15 or remove entirely
2. Test period_upper = 25 or 30 (wider channel, fewer false breakouts)
3. Test period_lower = 15 (wider trailing stop, longer holds)
4. Consider adding ATR-based trailing stop on top of Donchian lower

### Portfolio Implication

None of the 3 new strategies add value to the existing portfolio. SuperTrend 4h remains the sole viable 4h trend-following strategy. The search for diversified 4h strategies continues — consider mean-reversion approaches or different timeframes for diversification instead of more trend-following on the same timeframe.
