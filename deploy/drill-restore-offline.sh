#!/bin/sh
set -eu

: "${OFFLINE_PACKAGE:?OFFLINE_PACKAGE is required}"
: "${BACKUP_SNAPSHOT:?BACKUP_SNAPSHOT must be an explicit restic snapshot ID}"
: "${DRILL_RESTORE_TARGET:?DRILL_RESTORE_TARGET must be /backups/drills/NAME}"
case "$BACKUP_SNAPSHOT" in
  ''|latest|*[!0-9a-f]*) echo "Use an explicit hexadecimal snapshot ID" >&2; exit 2 ;;
esac
case "$DRILL_RESTORE_TARGET" in
  /backups/drills/*) ;;
  *) echo "Drill target must be below /backups/drills" >&2; exit 2 ;;
esac
drill_name="${DRILL_RESTORE_TARGET#/backups/drills/}"
case "$drill_name" in
  ''|*/*|*..*|*[!A-Za-z0-9._-]*) echo "Unsafe drill target name" >&2; exit 2 ;;
esac
if [ -e "$DRILL_RESTORE_TARGET" ] && [ -n "$(find "$DRILL_RESTORE_TARGET" -mindepth 1 -maxdepth 1 -print -quit 2>/dev/null)" ]; then
  echo "Drill target must be absent or empty; existing data will never be overwritten" >&2
  exit 2
fi
mkdir -p /backups/drills
/opt/backup/verify-offline-backup.sh
stage="$(mktemp -d)"
trap 'rm -rf "$stage"' EXIT
tar -xzf "$OFFLINE_PACKAGE" -C "$stage"
mkdir -p "$DRILL_RESTORE_TARGET"
export RESTIC_REPOSITORY="$stage/repository"
export RESTIC_PASSWORD="$AIMUSICMED_BACKUP_PASSPHRASE"
restic restore "$BACKUP_SNAPSHOT" --target "$DRILL_RESTORE_TARGET"
database="$(find "$DRILL_RESTORE_TARGET" -type f -name app.db | head -n 1)"
test -n "$database"
sqlite3 "$database" 'PRAGMA integrity_check;' | grep -qx ok
echo "Non-overwriting restore drill completed: $DRILL_RESTORE_TARGET"
