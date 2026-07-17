#!/bin/sh
set -eu

: "${AIMUSICMED_BACKUP_PASSPHRASE:?AIMUSICMED_BACKUP_PASSPHRASE is required}"
: "${BACKUP_SNAPSHOT:?BACKUP_SNAPSHOT must be a restic snapshot ID (not latest)}"
: "${RESTORE_CONFIRM:?Set RESTORE_CONFIRM=YES after stopping api, worker, and backup}"

if [ "$RESTORE_CONFIRM" != "YES" ]; then
  echo "Refusing restore: RESTORE_CONFIRM must equal YES" >&2
  exit 2
fi
case "$BACKUP_SNAPSHOT" in
  ''|latest|*[!0-9a-f]*)
    echo "Refusing restore: use an explicit hexadecimal snapshot ID from restic snapshots" >&2
    exit 2
    ;;
esac

export RESTIC_PASSWORD="$AIMUSICMED_BACKUP_PASSPHRASE"
export RESTIC_REPOSITORY="${AIMUSICMED_BACKUP_REPOSITORY:-/backups/restic}"
export RESTIC_CACHE_DIR="${AIMUSICMED_BACKUP_CACHE_DIR:-/backups/.cache}"
verify_stage="$(mktemp -d)"
trap 'rm -rf "$verify_stage"' EXIT

# Services are already required to be stopped. Capture the current state before
# any destructive replacement so an operator can always roll back this restore.
/opt/backup/backup.sh

# Confirm the repository and database before changing live data. restic also
# validates every restored file chunk while streaming it from the repository.
restic check --read-data
restic restore "$BACKUP_SNAPSHOT" \
  --target "$verify_stage" \
  --include /backup-stage/app.db
restored_db="$verify_stage/backup-stage/app.db"
test -f "$restored_db"
sqlite3 "$restored_db" 'PRAGMA integrity_check;' | grep -qx ok

# Services must be stopped. Restore storage into a staging directory first,
# then atomically swap it in only after all chunks have restored successfully.
# This prevents data loss when Restic or I/O fails mid-restore.
storage_stage="$(mktemp -d)"
trap 'rm -rf "$storage_stage" "$verify_stage"' EXIT
restic restore "$BACKUP_SNAPSHOT" \
  --target "$storage_stage" \
  --include /data/storage
cp "$restored_db" "$storage_stage/app.db.restore"
mv "$storage_stage/app.db.restore" /data/app.db.restore
# Atomically replace storage: move old aside, swap new in, then delete old.
if [ -d /data/storage ]; then
  mv /data/storage /data/storage.old
fi
mv "$storage_stage"/data/storage /data/storage
mv /data/app.db.restore /data/app.db
rm -f /data/app.db-wal /data/app.db-shm
rm -rf /data/storage.old
sqlite3 /data/app.db 'PRAGMA integrity_check;' | grep -qx ok
echo "Restore completed from snapshot: $BACKUP_SNAPSHOT"
