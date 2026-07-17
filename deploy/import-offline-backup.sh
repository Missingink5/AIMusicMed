#!/bin/sh
set -eu

: "${AIMUSICMED_BACKUP_PASSPHRASE:?AIMUSICMED_BACKUP_PASSPHRASE is required}"
: "${OFFLINE_PACKAGE:?OFFLINE_PACKAGE is required}"
: "${BACKUP_SNAPSHOT:?BACKUP_SNAPSHOT must be an explicit restic snapshot ID}"
: "${IMPORT_CONFIRM:?Set IMPORT_CONFIRM=IMPORT_VERIFIED_OFFLINE_BACKUP}"
if [ "$IMPORT_CONFIRM" != "IMPORT_VERIFIED_OFFLINE_BACKUP" ]; then
  echo "Refusing import without exact confirmation" >&2
  exit 2
fi
case "$BACKUP_SNAPSHOT" in
  ''|latest|*[!0-9a-f]*) echo "Use an explicit hexadecimal snapshot ID" >&2; exit 2 ;;
esac

/opt/backup/verify-offline-backup.sh
# Capture current live state before adding an offline restore source.
/opt/backup/backup.sh

stage="$(mktemp -d)"
trap 'rm -rf "$stage"' EXIT
tar -xzf "$OFFLINE_PACKAGE" -C "$stage"
password_file="$stage/password"
printf '%s' "$AIMUSICMED_BACKUP_PASSPHRASE" > "$password_file"
chmod 600 "$password_file"
destination="${AIMUSICMED_BACKUP_REPOSITORY:-/backups/restic}"
mkdir -p "$destination"
export RESTIC_REPOSITORY="$destination"
export RESTIC_PASSWORD_FILE="$password_file"
if [ ! -f "$destination/config" ]; then
  restic init
fi
restic copy \
  --from-repo "$stage/repository" \
  --from-password-file "$password_file" \
  "$BACKUP_SNAPSHOT"
restic check --read-data
restic snapshots "$BACKUP_SNAPSHOT"
echo "Offline snapshot imported. Use restore.sh with the same explicit snapshot ID."

