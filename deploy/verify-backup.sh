#!/bin/sh
set -eu

: "${AIMUSICMED_BACKUP_PASSPHRASE:?AIMUSICMED_BACKUP_PASSPHRASE is required}"
: "${BACKUP_SNAPSHOT:?BACKUP_SNAPSHOT must be a restic snapshot ID (or latest)}"

export RESTIC_PASSWORD="$AIMUSICMED_BACKUP_PASSPHRASE"
export RESTIC_REPOSITORY="${AIMUSICMED_BACKUP_REPOSITORY:-/backups/restic}"
export RESTIC_CACHE_DIR="${AIMUSICMED_BACKUP_CACHE_DIR:-/backups/.cache}"
stage="$(mktemp -d)"
trap 'rm -rf "$stage"' EXIT

restic check --read-data
restic restore "$BACKUP_SNAPSHOT" \
  --target "$stage" \
  --include /backup-stage/app.db
test -f "$stage/backup-stage/app.db"
sqlite3 "$stage/backup-stage/app.db" 'PRAGMA integrity_check;' | grep -qx ok
restic ls "$BACKUP_SNAPSHOT" /data/storage >/dev/null
echo "Snapshot verified without changing live data: $BACKUP_SNAPSHOT"
