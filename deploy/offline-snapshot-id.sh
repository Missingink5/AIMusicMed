#!/bin/sh
set -eu

: "${OFFLINE_PACKAGE:?OFFLINE_PACKAGE is required}"
/opt/backup/verify-offline-backup.sh >&2
snapshot="$(tar -xOf "$OFFLINE_PACKAGE" MANIFEST.txt | awk -F= '$1 == "snapshot" {print $2}')"
case "$snapshot" in
  ''|latest|*[!0-9a-f]*) echo "Offline package has no safe explicit snapshot ID" >&2; exit 2 ;;
esac
printf '%s\n' "$snapshot"
