#!/bin/sh
set -eu

: "${AIMUSICMED_BACKUP_PASSPHRASE:?AIMUSICMED_BACKUP_PASSPHRASE is required}"
test -f /data/app.db

export RESTIC_PASSWORD="$AIMUSICMED_BACKUP_PASSPHRASE"
export RESTIC_REPOSITORY="${AIMUSICMED_BACKUP_REPOSITORY:-/backups/restic}"
export RESTIC_CACHE_DIR="${AIMUSICMED_BACKUP_CACHE_DIR:-/backups/.cache}"
stage=/db-snapshot-stage

mkdir -p "$RESTIC_REPOSITORY" "$RESTIC_CACHE_DIR" /backups/status
if [ ! -f "$RESTIC_REPOSITORY/config" ]; then
  restic init
fi
rm -rf "$stage"
mkdir -p "$stage"
sqlite3 /data/app.db ".backup '$stage/app.db'"
sqlite3 "$stage/app.db" 'PRAGMA integrity_check;' | grep -qx ok

restic backup --host aimusicmed --tag aimusicmed-db "$stage/app.db"
restic forget \
  --host aimusicmed \
  --tag aimusicmed-db \
  --keep-within 36h \
  --keep-daily "${AIMUSICMED_BACKUP_KEEP_DAILY:-7}" \
  --keep-weekly "${AIMUSICMED_BACKUP_KEEP_WEEKLY:-4}" \
  --keep-monthly "${AIMUSICMED_BACKUP_KEEP_MONTHLY:-3}" \
  --prune
restic check
date +%s > /backups/status/last-db-success

