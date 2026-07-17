#!/bin/sh
set -eu

: "${AIMUSICMED_BACKUP_PASSPHRASE:?AIMUSICMED_BACKUP_PASSPHRASE is required}"

export RESTIC_PASSWORD="$AIMUSICMED_BACKUP_PASSPHRASE"
export RESTIC_REPOSITORY="${AIMUSICMED_BACKUP_REPOSITORY:-/backups/restic}"
export RESTIC_CACHE_DIR="${AIMUSICMED_BACKUP_CACHE_DIR:-/backups/.cache}"

keep_daily="${AIMUSICMED_BACKUP_KEEP_DAILY:-7}"
keep_weekly="${AIMUSICMED_BACKUP_KEEP_WEEKLY:-4}"
keep_monthly="${AIMUSICMED_BACKUP_KEEP_MONTHLY:-3}"
max_repo_mb="${AIMUSICMED_BACKUP_MAX_REPO_MB:-12288}"
min_free_mb="${AIMUSICMED_BACKUP_MIN_FREE_MB:-6144}"
stage=/backup-stage
success_marker=/backups/status/last-success

require_uint() {
  name="$1"
  value="$2"
  case "$value" in
    ''|*[!0-9]*) echo "$name must be a non-negative integer" >&2; exit 2 ;;
  esac
}

require_uint AIMUSICMED_BACKUP_KEEP_DAILY "$keep_daily"
require_uint AIMUSICMED_BACKUP_KEEP_WEEKLY "$keep_weekly"
require_uint AIMUSICMED_BACKUP_KEEP_MONTHLY "$keep_monthly"
require_uint AIMUSICMED_BACKUP_MAX_REPO_MB "$max_repo_mb"
require_uint AIMUSICMED_BACKUP_MIN_FREE_MB "$min_free_mb"
if [ "$max_repo_mb" -lt 1024 ] || [ "$min_free_mb" -lt 1024 ]; then
  echo "Backup repository cap and free-space reserve must each be at least 1024 MB" >&2
  exit 2
fi

mkdir -p "$RESTIC_REPOSITORY" "$RESTIC_CACHE_DIR" /backups/status "$stage"
if [ ! -f "$RESTIC_REPOSITORY/config" ]; then
  restic init
fi

# Protect a small single disk from a surprise full-volume backup. With the
# immutable-file storage model, files newer than the last successful snapshot
# are a conservative estimate of bytes newly entering the repository.
repo_mb="$(du -sm "$RESTIC_REPOSITORY" | awk '{print $1}')"
if [ -f "$success_marker" ]; then
  changed_kb="$(find /data/storage -type f -newer "$success_marker" -exec du -k {} + 2>/dev/null | awk '{sum += $1} END {print sum + 0}')"
else
  changed_kb="$(du -sk /data/storage 2>/dev/null | awk '{print $1 + 0}')"
fi
changed_mb="$(( (changed_kb + 1023) / 1024 ))"
free_mb="$(df -Pm /backups | awk 'NR == 2 {print $4}')"

if [ "$repo_mb" -ge "$max_repo_mb" ] || [ $((repo_mb + changed_mb)) -gt "$max_repo_mb" ]; then
  echo "Backup skipped: repository cap would be exceeded (${repo_mb} MB existing + up to ${changed_mb} MB changed > ${max_repo_mb} MB cap)." >&2
  echo "Move the restic repository off-server or increase storage/capacity before retrying." >&2
  exit 1
fi
if [ "$free_mb" -lt $((min_free_mb + changed_mb)) ]; then
  echo "Backup skipped: preserving ${min_free_mb} MB free space (${free_mb} MB free, up to ${changed_mb} MB changed)." >&2
  exit 1
fi

rm -rf "$stage"
mkdir -p "$stage"
sqlite3 /data/app.db ".backup '$stage/app.db'"
sqlite3 "$stage/app.db" 'PRAGMA integrity_check;' | grep -qx ok
run_marker=/backups/status/current-start
touch "$run_marker"

# One encrypted, content-addressed snapshot contains both the consistent
# SQLite copy and storage tree. Unchanged audio chunks are not stored again.
restic backup \
  --host aimusicmed \
  --tag aimusicmed \
  "$stage/app.db" /data/storage

# Keep useful restore points while bounding metadata/history. Prune releases
# chunks referenced only by expired snapshots; current originals remain in all
# current snapshots until the user deletes them from live storage.
restic forget \
  --host aimusicmed \
  --tag aimusicmed \
  --keep-daily "$keep_daily" \
  --keep-weekly "$keep_weekly" \
  --keep-monthly "$keep_monthly" \
  --prune
restic check

repo_mb="$(du -sm "$RESTIC_REPOSITORY" | awk '{print $1}')"
if [ "$repo_mb" -gt "$max_repo_mb" ]; then
  echo "Backup completed, but repository is above its ${max_repo_mb} MB cap (${repo_mb} MB). Capacity action is required." >&2
  exit 1
fi

mv "$run_marker" "$success_marker"
echo "Backup completed. Latest restore point:"
restic snapshots --host aimusicmed --tag aimusicmed --latest 1
