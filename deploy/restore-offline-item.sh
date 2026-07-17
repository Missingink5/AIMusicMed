#!/bin/sh
set -eu

: "${AIMUSICMED_BACKUP_PASSPHRASE:?AIMUSICMED_BACKUP_PASSPHRASE is required}"
: "${OFFLINE_PACKAGE:?OFFLINE_PACKAGE is required}"
: "${BACKUP_SNAPSHOT:?BACKUP_SNAPSHOT must be an explicit restic snapshot ID}"
: "${RESTORE_ITEM:?RESTORE_ITEM must be an absolute path stored in the snapshot}"
: "${ITEM_RESTORE_NAME:?ITEM_RESTORE_NAME is required}"
: "${ITEM_RESTORE_CONFIRM:?Set ITEM_RESTORE_CONFIRM=RESTORE_ITEM_NON_OVERWRITING}"
if [ "$ITEM_RESTORE_CONFIRM" != "RESTORE_ITEM_NON_OVERWRITING" ]; then
  echo "Refusing item restore without exact confirmation" >&2
  exit 2
fi
case "$BACKUP_SNAPSHOT" in
  ''|latest|*[!0-9a-f]*) echo "Use an explicit hexadecimal snapshot ID" >&2; exit 2 ;;
esac
case "$RESTORE_ITEM" in
  /data/storage/*|/backup-stage/app.db|/db-snapshot-stage/app.db) ;;
  *) echo "RESTORE_ITEM is outside the allowed backup paths" >&2; exit 2 ;;
esac
case "$RESTORE_ITEM" in *'/../'*|*/..|*'\'*) echo "Path traversal is forbidden" >&2; exit 2 ;; esac
case "$ITEM_RESTORE_NAME" in ''|*/*|*..*|*[!A-Za-z0-9._-]*) echo "Unsafe item restore name" >&2; exit 2 ;; esac

target="/backups/restored-items/$ITEM_RESTORE_NAME"
if [ -e "$target" ] && [ -n "$(find "$target" -mindepth 1 -maxdepth 1 -print -quit 2>/dev/null)" ]; then
  echo "Item restore target must be absent or empty" >&2
  exit 2
fi
/opt/backup/verify-offline-backup.sh
stage="$(mktemp -d)"
trap 'rm -rf "$stage"' EXIT
tar -xzf "$OFFLINE_PACKAGE" -C "$stage"
mkdir -p "$target"
export RESTIC_REPOSITORY="$stage/repository"
export RESTIC_PASSWORD="$AIMUSICMED_BACKUP_PASSPHRASE"
restic restore "$BACKUP_SNAPSHOT" --target "$target" --include "$RESTORE_ITEM"
echo "Item restored without overwriting live data: $target"

