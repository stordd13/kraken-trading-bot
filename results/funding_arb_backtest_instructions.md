# How to run the Kraken Futures funding arb backtest

## Prerequisites
1. Kraken Futures demo API keys (create at https://demo-futures.kraken.com/settings/api)
2. Store credentials in `.env.local` (not committed)

## Setup

Create `.env.local` at the project root:

```bash
# .env.local (for local testing only, gitignored)
KRAKEN_FUTURES_ENABLED=true
KRAKEN_FUTURES_API_KEY=<your-demo-api-key>
KRAKEN_FUTURES_API_SECRET=<your-demo-api-secret>
KRAKEN_FUTURES_DEMO=true
KRAKEN_FUTURES_MAX_LEVERAGE=3
```

## Run

```bash
poetry run python scripts/analyze_funding_arb_kraken.py --months 12
```

Options:
- `--months N` — Number of months of history to analyze (default: 12)
- `--pair XBT/USD` — Internal pair name (default: XBT/USD)

## Output

- `results/funding_history_raw.json` — raw funding rate history
- `results/funding_arb_backtest_results.md` — analysis report with verdict

## Interpretation

- **APR > 5%** — Phase 4A is viable, proceed with implementation
- **0 < APR < 5%** — Marginal, review conditions
- **APR < 0%** — Not viable, look for alternative strategies

## Troubleshooting

- **`kraken_futures_api_key_missing`** — Set `KRAKEN_FUTURES_API_KEY` in `.env.local`
- **`no_funding_data_fetched`** — Check API key permissions and network connectivity
- **Empty results** — Kraken Futures demo may have limited historical data; try `--months 3`
