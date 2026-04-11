# Kraken PF_XBTUSD — Structural Analysis
Generated: 2026-04-11T16:12:41.223669+00:00
Period analyzed: 2025-04-16 17:00 -> 2026-04-11 16:00 (8631 hours, 359.6 days)

## 1. Distribution of Funding Rates

### Global

- **Count**: 8631
- **Mean**: 0.00000698 (0.000698%)
- **Median**: 0.00000655 (0.000655%)
- **Stdev**: 0.00000825
- **Min**: -0.00017729 (-0.017729%)
- **Max**: 0.00004552 (0.004552%)
- **P5**: -0.00000496 (-0.000496%)
- **P25**: 0.00000206
- **P75**: 0.00001127
- **P95**: 0.00002153 (0.002153%)
- **Positive %**: 83.8%
- **Negative %**: 16.2%

### Positive Only

- **Count**: 7230
- **Mean**: 0.00000919 (0.000919%)
- **Median**: 0.00000797 (0.000797%)
- **Stdev**: 0.00000653
- **Min**: 0.00000000 (0.000000%)
- **Max**: 0.00004552 (0.004552%)
- **P5**: 0.00000107 (0.000107%)
- **P25**: 0.00000443
- **P75**: 0.00001236
- **P95**: 0.00002282 (0.002282%)
- **Positive %**: 100.0%
- **Negative %**: 0.0%

### Negative Only

- **Count**: 1401
- **Mean**: -0.00000443 (-0.000443%)
- **Median**: -0.00000302 (-0.000302%)
- **Stdev**: 0.00000663
- **Min**: -0.00017729 (-0.017729%)
- **Max**: -0.00000001 (-0.000001%)
- **P5**: -0.00001256 (-0.001256%)
- **P25**: -0.00000572
- **P75**: -0.00000123
- **P95**: -0.00000024 (-0.000024%)
- **Positive %**: 0.0%
- **Negative %**: 100.0%

## 2. Run Analysis

### Positive Runs

- **Count**: 297
- **Mean duration**: 24.3 hours
- **Median duration**: 5.0 hours
- **Max**: 672 hours
- **Min**: 1 hours
- **Total hours**: 7230

**Histogram:**

| Bucket | Count |
|--------|-------|
| < 1h | 0 |
| 1-6h | 165 |
| 6-24h | 82 |
| 1-3d | 28 |
| 3-7d | 11 |
| 7-30d | 11 |
| 30d+ | 0 |

### Negative Runs

- **Count**: 298
- **Mean duration**: 4.7 hours
- **Median duration**: 2.0 hours
- **Max**: 89 hours
- **Min**: 1 hours
- **Total hours**: 1401

**Histogram:**

| Bucket | Count |
|--------|-------|
| < 1h | 0 |
| 1-6h | 240 |
| 6-24h | 46 |
| 1-3d | 11 |
| 3-7d | 1 |
| 7-30d | 0 |
| 30d+ | 0 |

## 3. Three Hedge Scenarios — Passive Hold Simulation

### Scenario A: Spot + Perp Hedge

- Fees round-trip: 0.36%
- Basis risk: None (perfect hedge)
- Position: 500 USDC delta-neutral

**Results:**

- Gross funding collected: 30.1079 USDC
- Total fees: 1.8000 USDC
- Net P&L: 28.3079 USDC (2.83%)
- Annualized APR: 2.87%
- Max drawdown (funding): 1.2085 USDC

### Scenario B: Perp + Quarterly Calendar Spread

- Fees round-trip: 0.08% (4.5x lower than Scenario A)
- Basis risk: ASSUMED ZERO (unrealistic - see warning)
- Position: 500 USDC notional

> **WARNING**: This scenario assumes zero basis drift between perp and quarterly. In reality, basis can add +/-2-5% PnL deviation. Real results may be significantly different.

**Results:**

- Gross funding collected: 30.1079 USDC
- Total fees: 0.4000 USDC
- Net P&L: 29.7079 USDC (2.97%)
- Annualized APR: 3.02%

### Scenario C: Leveraged Perp Long (3x)

- Fees round-trip: 0.04%
- NOT market-neutral — directional exposure
- Position: 500 USDC collateral, 1500 USDC notional

> **WARNING**: This is directional speculation, not arbitrage. A BTC drop of 10% causes -30% loss on position.

**BTC price evolution on period:**

- Start: $84,028
- End: $72,891
- Change: -13.25%

**Results breakdown:**

- Funding PnL: 90.3237 USDC
- Directional PnL: -198.7974 USDC
- Fees: 0.6000 USDC
- Total Net P&L: -109.0737 USDC (-10.91%)
- Annualized APR: -11.07%

## 4. Monthly Breakdown

| Month | Funding Collected | Positive % | Best Run | Worst Run |
|-------|-------------------|------------|----------|-----------|
| 2025-04 | 0.9918 USDC | 88.3% | 82h | 12h |
| 2025-05 | 4.0392 USDC | 97.4% | 298h | 3h |
| 2025-06 | 1.7700 USDC | 85.8% | 81h | 18h |
| 2025-07 | 5.4206 USDC | 97.7% | 614h | 14h |
| 2025-08 | 5.3918 USDC | 99.2% | 345h | 3h |
| 2025-09 | 3.1218 USDC | 96.8% | 320h | 7h |
| 2025-10 | 2.7103 USDC | 94.2% | 188h | 6h |
| 2025-11 | 2.4179 USDC | 90.9% | 291h | 9h |
| 2025-12 | 2.1520 USDC | 87.5% | 278h | 14h |
| 2026-01 | 3.2565 USDC | 94.2% | 362h | 8h |
| 2026-02 | -0.3215 USDC | 49.0% | 42h | 30h |
| 2026-03 | -0.4308 USDC | 45.3% | 85h | 89h |
| 2026-04 | -0.4119 USDC | 21.8% | 20h | 57h |

Months positive: 10 / 13
Months negative: 3 / 13
Best month: 2025-07 (5.4206 USDC)
Worst month: 2026-03 (-0.4308 USDC)

## 5. Top 10 Worst Negative Runs

| # | Start | End | Duration (h) | Cumulative Loss (USDC) |
|---|-------|-----|--------------|------------------------|
| 1 | 2026-03-09 11:00 | 2026-03-13 04:00 | 89 | -0.3688 |
| 2 | 2026-04-01 08:00 | 2026-04-03 17:00 | 57 | -0.1459 |
| 3 | 2026-03-14 05:00 | 2026-03-16 03:00 | 46 | -0.1159 |
| 4 | 2026-04-08 12:00 | 2026-04-10 10:00 | 46 | -0.1093 |
| 5 | 2026-02-28 07:00 | 2026-03-01 19:00 | 36 | -0.1012 |
| 6 | 2026-01-31 18:00 | 2026-02-02 01:00 | 31 | -0.2112 |
| 7 | 2026-02-07 23:00 | 2026-02-09 05:00 | 30 | -0.0396 |
| 8 | 2026-04-10 11:00 | 2026-04-11 16:00 | 30 | -0.1337 |
| 9 | 2026-03-27 22:00 | 2026-03-29 03:00 | 29 | -0.0843 |
| 10 | 2026-02-06 07:00 | 2026-02-07 10:00 | 27 | -0.1408 |

## 6. Key Observations

- **Is Scenario A profitable?** YES — APR: 2.87%
- **Is Scenario B profitable?** YES — APR: 3.02% (but with basis risk caveat)
- **Is Scenario C profitable?** NO — APR: -11.07% (but non-neutral)
- **What is the longest negative run?** 89 hours on 2026-03-09 11:00
- **Is the monthly trend improving, worsening, or stable?** WORSENING (first half avg: 3.4559, second half avg: 1.3389)
- **What % of negative runs are < 24h?** 286/298 (96.0%) — these could be held through without closing

## 7. Recommendations for Phase 4A Design

**Option 3 — Hold with smart exit**: Scenarios A/B are marginal. Consider holding through short negative runs (<24h) and only exiting on prolonged negative runs (>72h).
