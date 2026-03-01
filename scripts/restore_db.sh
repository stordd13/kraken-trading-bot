#!/bin/bash
# KrakenBot — Restore PostgreSQL from backup
#
# Usage: ./restore_db.sh <backup_file.dump.gz>
#
# This script restores a KrakenBot database from a pg_dump custom format backup.
# It drops and recreates existing tables (--clean --if-exists).
#
# WARNING: This is a destructive operation. The current database content
# will be replaced by the backup.

set -euo pipefail

# === CONFIGURATION ===
DB_NAME="${KRAKENBOT_DB_NAME:-krakenbot}"
DB_USER="${KRAKENBOT_DB_USER:-krakenbot}"

# === ARGUMENT VALIDATION ===

BACKUP_FILE="${1:-}"
if [[ -z "$BACKUP_FILE" ]]; then
    echo "Usage: $0 <backup_file.dump.gz>" >&2
    exit 1
fi

if [[ ! -f "$BACKUP_FILE" ]]; then
    echo "ERROR: File not found: $BACKUP_FILE" >&2
    exit 1
fi

# === DECOMPRESS IF NEEDED ===

RESTORE_FILE="$BACKUP_FILE"
TEMP_FILE=""

if [[ "$BACKUP_FILE" == *.gz ]]; then
    TEMP_FILE=$(mktemp /tmp/krakenbot_restore_XXXXXX.dump)
    trap 'rm -f "$TEMP_FILE"' EXIT
    echo "Decompressing $BACKUP_FILE..."
    gunzip -c "$BACKUP_FILE" > "$TEMP_FILE"
    RESTORE_FILE="$TEMP_FILE"
fi

# === SAFETY CONFIRMATION ===

echo ""
echo "========================================"
echo "  KrakenBot Database Restore"
echo "========================================"
echo "  Backup:   $BACKUP_FILE"
echo "  Database:  $DB_NAME"
echo "  User:      $DB_USER"
echo "========================================"
echo ""
echo "WARNING: This will REPLACE all data in '$DB_NAME'."
echo "Press Ctrl+C within 5 seconds to cancel..."
echo ""

for i in 5 4 3 2 1; do
    echo -n "$i... "
    sleep 1
done
echo ""

# === RESTORE ===

echo "Restoring database..."
if pg_restore -U "$DB_USER" -d "$DB_NAME" --clean --if-exists "$RESTORE_FILE"; then
    echo "Restore completed successfully."
else
    EXIT_CODE=$?
    # pg_restore returns non-zero for warnings too (e.g. "table does not exist")
    # Exit code 1 with --clean --if-exists is usually just warnings
    if [[ $EXIT_CODE -eq 1 ]]; then
        echo "Restore completed with warnings (this is normal for --clean --if-exists)."
    else
        echo "ERROR: pg_restore failed with exit code $EXIT_CODE" >&2
        exit $EXIT_CODE
    fi
fi
