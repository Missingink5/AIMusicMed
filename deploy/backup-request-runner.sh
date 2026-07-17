#!/bin/sh
set -eu

project_dir="${AIMUSICMED_PROJECT_DIR:-$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)}"
backup_root="${AIMUSICMED_BACKUPS_ROOT:-$project_dir/backups}"
pending="$backup_root/requests/pending"
working="$backup_root/requests/working"
completed="$backup_root/requests/completed"
failed="$backup_root/requests/failed"
lock="$backup_root/requests/.runner-lock"
mkdir -p "$pending" "$working" "$completed" "$failed"
if ! mkdir "$lock" 2>/dev/null; then
  exit 0
fi
cd "$project_dir"
restore_started=0
cleanup() {
  if [ "$restore_started" -eq 1 ]; then
    docker compose up -d api worker backup || true
  fi
  rmdir "$lock" 2>/dev/null || true
}
trap cleanup EXIT INT TERM

read_field() {
  python3 - "$1" "$2" <<'PY'
import json
import sys
with open(sys.argv[1], encoding="utf-8") as source:
    value = json.load(source).get(sys.argv[2])
if value is not None:
    print(value)
PY
}

finish_request() {
  source="$1"
  state="$2"
  message="$3"
  destination="$completed"
  [ "$state" = "completed" ] || destination="$failed"
  python3 - "$source" "$destination/$(basename "$source")" "$state" "$message" <<'PY'
import json
import os
import sys
import time
source, destination, state, message = sys.argv[1:]
with open(source, encoding="utf-8") as handle:
    record = json.load(handle)
record["finished_at"] = int(time.time())
if state == "completed":
    if message:
        record["result_package"] = message
else:
    record["error"] = message[:1000]
temporary = destination + ".partial"
with open(temporary, "x", encoding="utf-8") as handle:
    json.dump(record, handle, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
    handle.flush()
    os.fsync(handle.fileno())
os.replace(temporary, destination)
os.unlink(source)
PY
}

safe_package_path() {
  name="$1"
  case "$name" in
    aimusicmed-offline-*.tar.gz|aimusicmed-upload-*.tar.gz) ;;
    *) return 1 ;;
  esac
  case "$name" in *[!A-Za-z0-9.T_-]*) return 1 ;; esac
  if [ -f "$backup_root/offline/$name" ]; then
    printf '%s\n' "/backups/offline/$name"
  elif [ -f "$backup_root/uploads/$name" ]; then
    printf '%s\n' "/backups/uploads/$name"
  else
    return 1
  fi
}

for queued in "$pending"/*.json; do
  [ -f "$queued" ] || continue
  job="$working/$(basename "$queued")"
  mv "$queued" "$job"
  action="$(read_field "$job" action 2>/dev/null || true)"
  package_id="$(read_field "$job" package_id 2>/dev/null || true)"
  output=""
  result=0
  case "$action" in
    create_export)
      output="$(docker compose run --rm --no-deps backup /opt/backup/create-offline-backup.sh 2>&1)" || result=$?
      if [ "$result" -eq 0 ]; then
        output="$(printf '%s\n' "$output" | tail -n 1)"
      fi
      ;;
    verify)
      package="$(safe_package_path "$package_id" 2>/dev/null)" || result=2
      if [ "$result" -eq 0 ]; then
        output="$(docker compose run --rm --no-deps \
          -e "OFFLINE_PACKAGE=$package" backup /opt/backup/verify-offline-backup.sh 2>&1)" || result=$?
      fi
      ;;
    verify_upload)
      package="$(safe_package_path "$package_id" 2>/dev/null)" || result=2
      if [ "$result" -eq 0 ]; then
        output="$(docker compose run --rm --no-deps \
          -e "OFFLINE_PACKAGE=$package" -e OFFLINE_UPLOAD_TARGET=/backups/offline \
          backup /opt/backup/upload-offline-backup.sh 2>&1)" || result=$?
      fi
      ;;
    restore)
      package="$(safe_package_path "$package_id" 2>/dev/null)" || result=2
      if [ "$result" -eq 0 ]; then
        snapshot="$(docker compose run --rm --no-deps \
          -e "OFFLINE_PACKAGE=$package" backup /opt/backup/offline-snapshot-id.sh 2>/dev/null)" || result=$?
      fi
      case "${snapshot:-}" in ''|latest|*[!0-9a-f]*) result=2 ;; esac
      if [ "$result" -eq 0 ]; then
        docker compose stop api worker backup
        restore_started=1
        output="$({
          docker compose run --rm --no-deps \
            -e "OFFLINE_PACKAGE=$package" -e "BACKUP_SNAPSHOT=$snapshot" \
            -e IMPORT_CONFIRM=IMPORT_VERIFIED_OFFLINE_BACKUP \
            backup /opt/backup/import-offline-backup.sh &&
          docker compose run --rm --no-deps \
            -e "BACKUP_SNAPSHOT=$snapshot" -e RESTORE_CONFIRM=YES \
            backup /opt/backup/restore.sh
        } 2>&1)" || result=$?
        if docker compose up -d api worker backup; then
          restore_started=0
        fi
      fi
      ;;
    *)
      result=2
      output="Unsupported backup request action"
      ;;
  esac
  if [ "$restore_started" -eq 1 ]; then
    docker compose up -d api worker backup || true
    restore_started=0
  fi
  if [ "$result" -eq 0 ]; then
    finish_request "$job" completed "$([ "$action" = create_export ] && printf '%s' "$output" || true)"
  else
    finish_request "$job" failed "${output:-Backup operation failed safely}"
  fi
done
