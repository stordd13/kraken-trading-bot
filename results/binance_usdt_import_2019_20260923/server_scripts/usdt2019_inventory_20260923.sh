#!/bin/bash
# usdt2019_inventory_20260923.sh — inventaire post-import (brief étape 5), lecture seule : l'outil de `dev` tel qu'il est sur le
# serveur (scripts/audit/data_inventory.py @ 373da3f, --pairs présent), restreint aux trois paires USDT, sans HEAD Vision
# (--skip-vision : les sondes ont été faites à l'état avant, vision_head_before.txt). Sortie HORS de l'arbre du service.
# tmux : tmux new -d -s usdt2019_inventory "bash -lc /home/bruno/usdt2019_inventory_20260923.sh"
# __NOW__ est substitué (sed) par l'heure de fin de l'import arrondie à la minute supérieure avant l'envoi.
exec > >(tee /home/bruno/usdt2019_inventory_20260923.log) 2>&1
cd /home/bruno/apps/kraken-trading-bot || exit 3
set -o pipefail
unset SCHEDULER_PAIRS SCHEDULER_INTERVALS
export NO_COLOR=1
OUT=/home/bruno/usdt2019_inventory_out
mkdir -p "$OUT"
echo "=== $(date -u +%FT%TZ) inventory start ; HEAD $(git rev-parse HEAD) ($(git branch --show-current)) ; data_inventory.py sha256 $(sha256sum scripts/audit/data_inventory.py | cut -c1-64)"
poetry run python scripts/audit/data_inventory.py --pairs BTC/USDT,ETH/USDT,SOL/USDT --skip-vision --now __NOW__ --output $OUT/inventory.json --markdown $OUT/inventory.md
rc=$?
echo "=== $(date -u +%FT%TZ) inventory exit=$rc"
echo "exit=$rc" > /home/bruno/usdt2019_inventory_20260923.status
