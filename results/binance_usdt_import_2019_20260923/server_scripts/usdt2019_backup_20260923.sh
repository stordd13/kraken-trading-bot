#!/bin/bash
# usdt2019_backup_20260923.sh — backup pré-import USDT 2019-2020 (brief « import complémentaire USDT 2019-2020 », étape 3).
# Serveur Hetzner, base locale via docker exec, lancé en tmux : tmux new -d -s usdt2019_backup "bash -lc /home/bruno/usdt2019_backup_20260923.sh"
# Lecture seule côté base. Journal : /home/bruno/usdt2019_backup_20260923.log ; statut : <dump>.status
exec > >(tee /home/bruno/usdt2019_backup_20260923.log) 2>&1
set -o pipefail
OUT=/home/bruno/backups/krakenbot/krakenbot_20260923_pre_usdt2019.dump
echo "=== $(date -u +%FT%TZ) backup start -> $OUT ; df: $(df -h / | tail -1 | awk '{print $4" free"}')"
sudo -n docker exec krakenbot-db pg_dump -U krakenbot -Fc --no-owner --no-acl krakenbot > "$OUT" 2> "${OUT%.dump}.err"
rc=$?
echo "=== $(date -u +%FT%TZ) pg_dump rc=$rc"
ls -l "$OUT"
sha256sum "$OUT"
echo "pg_restore --list entries: $(sudo -n docker exec -i krakenbot-db pg_restore -l < "$OUT" | wc -l)"
echo "done $rc $(date -u +%FT%TZ)" > "${OUT%.dump}.status"
echo "=== $(date -u +%FT%TZ) backup end rc=$rc ; df: $(df -h / | tail -1 | awk '{print $4" free"}')"
