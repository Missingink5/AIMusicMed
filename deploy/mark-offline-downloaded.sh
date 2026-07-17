#!/bin/sh
set -eu

: "${OFFLINE_PACKAGE:?OFFLINE_PACKAGE is required}"
test -f "$OFFLINE_PACKAGE"
test -f "$OFFLINE_PACKAGE.sha256"
(cd "$(dirname "$OFFLINE_PACKAGE")" && sha256sum -c "$(basename "$OFFLINE_PACKAGE").sha256")
mkdir -p /backups/status
printf '%s\t%s\n' "$(date +%s)" "$(basename "$OFFLINE_PACKAGE")" > /backups/status/last-offline-download
echo "Offline download recorded after checksum verification."

