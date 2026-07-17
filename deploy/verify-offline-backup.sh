#!/bin/sh
set -eu

: "${AIMUSICMED_BACKUP_PASSPHRASE:?AIMUSICMED_BACKUP_PASSPHRASE is required}"
: "${OFFLINE_PACKAGE:?OFFLINE_PACKAGE is required}"
test -f "$OFFLINE_PACKAGE"
test -f "$OFFLINE_PACKAGE.sha256"
(cd "$(dirname "$OFFLINE_PACKAGE")" && sha256sum -c "$(basename "$OFFLINE_PACKAGE").sha256")

stage="$(mktemp -d)"
trap 'rm -rf "$stage"' EXIT

# Defensive limits before extraction: at most 512 members and
# expanded size under 24 GiB (3× the 8 GiB compressed budget).
member_count="$(tar -tzf "$OFFLINE_PACKAGE" 2>/dev/null | wc -l)"
max_members=512
if [ "$member_count" -gt "$max_members" ]; then
  echo "Unsafe package: $member_count members exceeds $max_members limit" >&2
  exit 2
fi
available_kb="$(df --output=avail "$stage" 2>/dev/null | tail -n 1 || echo 0)"
max_expanded_kb=25165824
if [ "$available_kb" -lt "$max_expanded_kb" ]; then
  echo "Insufficient disk space for verification" >&2
  exit 2
fi

tar -tzf "$OFFLINE_PACKAGE" | while IFS= read -r item; do
  case "$item" in
    /*|../*|*/../*|*/..|*'\'*|*:*)
      echo "Unsafe package entry: $item" >&2
      exit 2
      ;;
    repository/*|repository|MANIFEST.txt) ;;
    *) echo "Unsafe package entry: $item" >&2; exit 2 ;;
  esac
done
tar -xzf "$OFFLINE_PACKAGE" -C "$stage"
export RESTIC_REPOSITORY="$stage/repository"
export RESTIC_PASSWORD="$AIMUSICMED_BACKUP_PASSPHRASE"
restic check --read-data
restic snapshots
restic restore latest --target "$stage/restore"
database="$(find "$stage/restore" -type f -name app.db | head -n 1)"
test -n "$database"
sqlite3 "$database" 'PRAGMA integrity_check;' | grep -qx ok
echo "Offline package verified without changing live data: $OFFLINE_PACKAGE"
