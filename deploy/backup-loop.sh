#!/bin/sh
set -u

interval="${AIMUSICMED_BACKUP_INTERVAL_SECONDS:-86400}"
retry="${AIMUSICMED_BACKUP_RETRY_SECONDS:-3600}"
case "$interval:$retry" in
  *[!0-9:]*|:*|*:) echo "Backup interval and retry delay must be positive integers" >&2; exit 2 ;;
esac
if [ "$interval" -lt 3600 ] || [ "$retry" -lt 300 ]; then
  echo "Backup interval must be at least 3600s and retry delay at least 300s" >&2
  exit 2
fi

while true; do
  if /opt/backup/backup.sh; then
    sleep "$interval"
  else
    echo "Backup failed; retrying in ${retry}s" >&2
    sleep "$retry"
  fi
done
