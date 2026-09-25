#!/usr/bin/env bash
# usage: capture.sh <tag: ref|c3b> <log>
set -o pipefail
cd /Users/stordd/doc/GitHub/kraken-trading-bot || exit 2
TAG=$1; LOG=$2
OUT=results/c3b_producteur/lot1_ab; ARC=$HOME/archive/c3b_lot1_20260925
P=(poetry run python scripts/audit/c1_equity_probe.py capture --pair BTC/USDC --exchange binance --interval 5 --capital 1000 --fees bybit)
echo "HEAD $(git rev-parse --short HEAD) branch $(git branch --show-current) src-dirty-lines $(git status --porcelain -- src | wc -l)" > "$LOG"
"${P[@]}" --strategy grok_supertrend_4h --start-date 2023-04-01 --end-date 2026-04-01 --out "$OUT/signal_A_bybit_$TAG.json" >> "$LOG" 2>&1; echo "signal_A exit $?" >> "$LOG"
"${P[@]}" --strategy grok_grid_atr_adaptive_v4 --start-date 2025-03-01 --end-date 2025-03-15 --out "$OUT/grid_quick_bybit_$TAG.json" >> "$LOG" 2>&1; echo "grid_quick exit $?" >> "$LOG"
"${P[@]}" --strategy grok_grid_atr_adaptive_v4 --start-date 2023-04-01 --end-date 2026-04-01 --out "$ARC/grid_A_bybit_$TAG.json.gz" >> "$LOG" 2>&1; echo "grid_A exit $?" >> "$LOG"
grep -E "exit|captured|HEAD" "$LOG"
