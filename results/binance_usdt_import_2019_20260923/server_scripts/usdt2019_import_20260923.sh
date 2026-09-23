#!/bin/bash
# usdt2019_import_20260923.sh — import USDT 2019-2020 complet (brief étape 4) : 3 paires × 6 TF × 24 mois = 432 fichiers Vision
# (318 attendus 200, 114 attendus 404 = SOLUSDT × 6 TF × 2019-01 → 2020-07, constatés à l'état avant).
# Serveur Hetzner, arbre du service sur dev, base locale, tmux : tmux new -d -s usdt2019_import "bash -lc /home/bruno/usdt2019_import_20260923.sh"
# Script d'import NON modifié. Journal : /home/bruno/import_usdt2019.log ; statut : /home/bruno/import_usdt2019.status
exec > >(tee /home/bruno/import_usdt2019.log) 2>&1
cd /home/bruno/apps/kraken-trading-bot || exit 3
set -o pipefail
unset SCHEDULER_PAIRS SCHEDULER_INTERVALS
export NO_COLOR=1
echo "=== $(date -u +%FT%TZ) import start on $(git rev-parse HEAD) ($(git branch --show-current)) ; df: $(df -h / | tail -1 | awk '{print $4" free"}')"
poetry run python scripts/binance_vision_import.py --pairs BTC/USDT,ETH/USDT,SOL/USDT --intervals 5m,15m,1h,4h,1d,1w --start-date 2019-01-01 --end-date 2020-12-31
rc=$?
echo "=== $(date -u +%FT%TZ) import exit=$rc ; df: $(df -h / | tail -1 | awk '{print $4" free"}')"
echo "exit=$rc" > /home/bruno/import_usdt2019.status
