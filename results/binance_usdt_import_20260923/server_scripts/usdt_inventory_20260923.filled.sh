#!/bin/bash
# usdt_inventory_20260923.sh — inventaire post-import (brief étape 4), lecture seule, décision Bruno STOP 1 (option 2) :
# l'outil de `dev` tel qu'il est sur le serveur (scripts/audit/data_inventory.py @ 8fdaa2a), sans --pairs, toutes les
# séries binance (USDC re-mesurées = preuve qu'aucune row USDC n'a été touchée). Sortie HORS de l'arbre du service.
# tmux : tmux new -d -s usdt_inventory "bash -lc /home/bruno/usdt_inventory_20260923.sh"
# 2026-09-23T07:43:00Z est substitué (sed) par l'heure de fin de l'import arrondie à la minute supérieure avant l'envoi.
exec > >(tee /home/bruno/usdt_inventory_20260923.log) 2>&1
cd /home/bruno/apps/kraken-trading-bot || exit 3
set -o pipefail
unset SCHEDULER_PAIRS SCHEDULER_INTERVALS
export NO_COLOR=1
OUT=/home/bruno/usdt_inventory_out
mkdir -p "$OUT"
echo "=== $(date -u +%FT%TZ) inventory start ; HEAD $(git rev-parse HEAD) ($(git branch --show-current)) ; data_inventory.py sha256 $(sha256sum scripts/audit/data_inventory.py | cut -c1-64)"
poetry run python scripts/audit/data_inventory.py --now 2026-09-23T07:43:00Z --output $OUT/inventory.json --markdown $OUT/inventory.md
rc=$?
echo "=== $(date -u +%FT%TZ) inventory exit=$rc"
echo "exit=$rc" > /home/bruno/usdt_inventory_20260923.status
