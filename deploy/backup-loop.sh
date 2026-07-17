#!/bin/sh
set -u

db_interval="${AIMUSICMED_DB_SNAPSHOT_INTERVAL_SECONDS:-21600}"
full_interval="${AIMUSICMED_BACKUP_INTERVAL_SECONDS:-86400}"
retry="${AIMUSICMED_BACKUP_RETRY_SECONDS:-3600}"
case "$db_interval:$full_interval:$retry" in
  *[!0-9:]*|:*|*:) echo "Backup interval and retry delay must be positive integers" >&2; exit 2 ;;
esac
if [ "$db_interval" -lt 3600 ] || [ "$full_interval" -lt 21600 ] || [ "$retry" -lt 300 ]; then
  echo "Backup interval must be at least 3600s and retry delay at least 300s" >&2
  exit 2
fi

next_db=0
next_full=0
while true; do
  now="$(date +%s)"
  if [ "$now" -ge "$next_db" ]; then
    if /opt/backup/db-snapshot.sh; then
      next_db="$((now + db_interval))"
    else
      echo "Database snapshot failed; retrying in ${retry}s" >&2
      next_db="$((now + retry))"
    fi
  fi
  if [ "$now" -ge "$next_full" ]; then
    if /opt/backup/backup.sh; then
      next_full="$((now + full_interval))"
    else
      echo "Full backup failed; retrying in ${retry}s" >&2
      next_full="$((now + retry))"
    fi
  fi
  /opt/backup/backup-health.sh || true
  sleep 300
done
