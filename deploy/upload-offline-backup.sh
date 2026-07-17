#!/bin/sh
set -eu

: "${OFFLINE_PACKAGE:?OFFLINE_PACKAGE is required}"
: "${OFFLINE_UPLOAD_TARGET:?OFFLINE_UPLOAD_TARGET must be a mounted offline/remote directory}"
test -d "$OFFLINE_UPLOAD_TARGET"
/opt/backup/verify-offline-backup.sh
name="$(basename "$OFFLINE_PACKAGE")"
cp "$OFFLINE_PACKAGE" "$OFFLINE_UPLOAD_TARGET/$name.partial"
cp "$OFFLINE_PACKAGE.sha256" "$OFFLINE_UPLOAD_TARGET/$name.sha256.partial"
mv "$OFFLINE_UPLOAD_TARGET/$name.partial" "$OFFLINE_UPLOAD_TARGET/$name"
mv "$OFFLINE_UPLOAD_TARGET/$name.sha256.partial" "$OFFLINE_UPLOAD_TARGET/$name.sha256"
printf '%s\t%s\n' "$(date +%s)" "$name" > /backups/status/last-offline-upload
echo "Verified package uploaded to mounted target: $OFFLINE_UPLOAD_TARGET/$name"

