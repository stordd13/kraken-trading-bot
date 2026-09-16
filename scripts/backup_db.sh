#!/bin/bash
# KrakenBot — Automated PostgreSQL Backup
#
# Usage: ./backup_db.sh {daily|weekly}
#
# Cron setup (add to server crontab with: crontab -e):
#   # Daily at 03:00 UTC:
#   0 3 * * * /home/bruno/apps/kraken-trading-bot/scripts/backup_db.sh daily
#   # Weekly on Sunday at 04:00 UTC:
#   0 4 * * 0 /home/bruno/apps/kraken-trading-bot/scripts/backup_db.sh weekly

set -euo pipefail

# === CONFIGURATION (override via environment variables) ===
DB_NAME="${KRAKENBOT_DB_NAME:-krakenbot}"
DB_USER="${KRAKENBOT_DB_USER:-krakenbot}"
BACKUP_DIR="${KRAKENBOT_BACKUP_DIR:-/home/bruno/backups/krakenbot}"
RETENTION_DAILY="${KRAKENBOT_RETENTION_DAILY:-7}"
RETENTION_WEEKLY="${KRAKENBOT_RETENTION_WEEKLY:-28}"
LOG_FILE="${KRAKENBOT_LOG_FILE:-${BACKUP_DIR}/backup.log}"
DB_CONTAINER="${KRAKENBOT_DB_CONTAINER:-krakenbot-db}"
# Optional: remote sync destination (uncomment to enable)
# REMOTE_DEST="${KRAKENBOT_REMOTE_DEST:-}"

# === FUNCTIONS ===

log() {
    local msg="[$(date -u '+%Y-%m-%d %H:%M:%S UTC')] $*"
    echo "$msg" | tee -a "$LOG_FILE"
}

cleanup_old_backups() {
    local pattern="$1"
    local retention_days="$2"
    local count
    count=$(find "$BACKUP_DIR" -name "$pattern" -mtime +"$retention_days" 2>/dev/null | wc -l)
    if [ "$count" -gt 0 ]; then
        find "$BACKUP_DIR" -name "$pattern" -mtime +"$retention_days" -delete 2>/dev/null
        log "CLEANUP: removed $count old backups matching '$pattern' (older than ${retention_days}d)"
    fi
}

# === ARGUMENT VALIDATION ===

BACKUP_TYPE="${1:-}"
if [[ "$BACKUP_TYPE" != "daily" && "$BACKUP_TYPE" != "weekly" ]]; then
    echo "Usage: $0 {daily|weekly}" >&2
    exit 1
fi

# === MAIN ===

# Create backup directory if needed
mkdir -p "$BACKUP_DIR"

TIMESTAMP=$(date -u '+%Y-%m-%d_%H-%M')
FILENAME="krakenbot_${TIMESTAMP}_${BACKUP_TYPE}.dump"
FILEPATH="${BACKUP_DIR}/${FILENAME}"

log "START type=${BACKUP_TYPE} db=${DB_NAME} user=${DB_USER}"

# pg_dump with custom format (most compact, supports selective/parallel restore)
if docker exec "$DB_CONTAINER" pg_dump -Fc -U "$DB_USER" -d "$DB_NAME" > "$FILEPATH"; then
    # Compress with gzip
    gzip "$FILEPATH"
    FINAL="${FILEPATH}.gz"
    SIZE=$(du -h "$FINAL" | cut -f1)
    log "OK backup=${FINAL} size=${SIZE}"
else
    EXIT_CODE=$?
    log "FAIL pg_dump failed with exit code ${EXIT_CODE}"
    # Clean up partial file if it exists
    rm -f "$FILEPATH"
    exit 1
fi

# Apply retention policy
if [[ "$BACKUP_TYPE" == "daily" ]]; then
    cleanup_old_backups "*_daily.dump.gz" "$RETENTION_DAILY"
elif [[ "$BACKUP_TYPE" == "weekly" ]]; then
    cleanup_old_backups "*_weekly.dump.gz" "$RETENTION_WEEKLY"
fi

# Optional: sync to remote storage
# if [[ -n "${REMOTE_DEST:-}" ]]; then
#     if rsync -avz "$FINAL" "$REMOTE_DEST"; then
#         log "RSYNC OK dest=${REMOTE_DEST}"
#     else
#         log "RSYNC FAIL dest=${REMOTE_DEST} (backup is still local)"
#     fi
# fi

log "END type=${BACKUP_TYPE}"
exit 0
