# Funding Rate Arb Backtest — XBT/USD — 12 months

Generated: 2026-04-11T15:49:29.471239+00:00

## Distribution of Hourly Funding Rates

- **Total observations**: 8631
- **Mean rate**: 0.000007 (0.0007%)
- **Median rate**: 0.000007 (0.0007%)
- **Std dev**: 0.000008
- **Min**: -0.000177 (-0.0177%)
- **Max**: 0.000046 (0.0046%)

## Positive vs Negative Frequency

- **Positive rate hours**: 7230 (83.8%)
- **Negative rate hours**: 1401
- **Zero rate hours**: 0
- **Hours above entry threshold (0.005%)**: 7057 (81.8%)

## Strategy Simulation (Asymmetric Funding Arb)

**Rules:**
- Open long spot + short perp when funding rate > 0.005% / hour
- Close when funding rate <= 0
- Position size: 500 USDC (50% of 1000 USDC capital)
- Fees: 0.16% maker spot + 0.02% maker perp on each leg (both entry and exit) = 0.36% round-trip

**Results:**

- **Initial capital**: 1000.00 USDC
- **Position size**: 500.00 USDC
- **Period analyzed**: 359.6 days (8631 hours)
- **Number of trades opened**: 25
- **Number of trades closed**: 25
- **Avg duration per trade**: 329.8 hours
- **Cumulative funding collected**: 31.4814 USDC
- **Cumulative fees paid**: 45.0000 USDC
- **Net P&L**: -13.5186 USDC (-1.35%)
- **Annualized APR**: -1.37%

## Verdict

**NOT PROFITABLE** — Annualized APR of -1.37% is negative or zero.

Recommendation: Do NOT proceed with Phase 4A. Funding arb is not viable on Kraken in current conditions.

## Raw Data

See `results/funding_history_raw.json` for the raw funding history used.