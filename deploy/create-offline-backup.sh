#!/bin/sh
set -eu

/opt/backup/backup.sh
export RESTIC_PASSWORD="${AIMUSICMED_BACKUP_PASSPHRASE:?AIMUSICMED_BACKUP_PASSPHRASE is required}"
export RESTIC_REPOSITORY="${AIMUSICMED_BACKUP_REPOSITORY:-/backups/restic}"
snapshot="$(
  restic snapshots --host aimusicmed --tag aimusicmed --latest 1 --compact |
    awk '$1 ~ /^[0-9a-f]+$/ {value=$1} END {print value}'
)"
case "$snapshot" in
  ''|*[!0-9a-f]*) echo "Could not determine the explicit snapshot ID" >&2; exit 2 ;;
esac
BACKUP_SNAPSHOT="$snapshot" /opt/backup/export-offline-backup.sh
package="$(awk -F '\t' 'NF >= 2 {print $2}' /backups/status/last-offline-export)"
case "$package" in
  aimusicmed-offline-*.tar.gz) printf '%s\n' "$package" ;;
  *) echo "Offline export did not produce a safe package name" >&2; exit 2 ;;
esac
