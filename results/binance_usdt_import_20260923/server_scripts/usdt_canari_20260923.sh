#!/bin/bash
# usdt_canari_20260923.sh — canari : un seul fichier Vision (BTCUSDT 1d 2021-01), brief étape 3.
# Serveur Hetzner, arbre du service sur dev, base locale, tmux : tmux new -d -s usdt_canari "bash -lc /home/bruno/usdt_canari_20260923.sh"
# Script d'import NON modifié. Journal : /home/bruno/import_usdt_canari.log ; statut : /home/bruno/import_usdt_canari.status
exec > >(tee /home/bruno/import_usdt_canari.log) 2>&1
cd /home/bruno/apps/kraken-trading-bot || exit 3
set -o pipefail
unset SCHEDULER_PAIRS SCHEDULER_INTERVALS
export NO_COLOR=1
echo "=== $(date -u +%FT%TZ) canari start on $(git rev-parse HEAD) ($(git branch --show-current))"
poetry run python scripts/binance_vision_import.py --pairs BTC/USDT --intervals 1d --start-date 2021-01-01 --end-date 2021-01-31
rc=$?
echo "=== $(date -u +%FT%TZ) canari exit=$rc"
echo "exit=$rc" > /home/bruno/import_usdt_canari.status
