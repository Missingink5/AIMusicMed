#!/bin/sh
set -eu

: "${AIMUSICMED_BACKUP_PASSPHRASE:?AIMUSICMED_BACKUP_PASSPHRASE is required}"
: "${BACKUP_SNAPSHOT:?BACKUP_SNAPSHOT must be an explicit restic snapshot ID}"
case "$BACKUP_SNAPSHOT" in
  ''|latest|*[!0-9a-f]*) echo "Use an explicit hexadecimal snapshot ID" >&2; exit 2 ;;
esac

source_repo="${AIMUSICMED_BACKUP_REPOSITORY:-/backups/restic}"
output_dir="${AIMUSICMED_OFFLINE_EXPORT_DIR:-/backups/offline}"
work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT
password_file="$work/password"
printf '%s' "$AIMUSICMED_BACKUP_PASSPHRASE" > "$password_file"
chmod 600 "$password_file"
mkdir -p "$work/export/repository" "$output_dir" /backups/status

export RESTIC_REPOSITORY="$work/export/repository"
export RESTIC_PASSWORD_FILE="$password_file"
restic init
restic copy \
  --from-repo "$source_repo" \
  --from-password-file "$password_file" \
  "$BACKUP_SNAPSHOT"
restic check --read-data

created="$(date -u +%Y%m%dT%H%M%SZ)"
package="aimusicmed-offline-${created}-${BACKUP_SNAPSHOT}.tar.gz"
cat > "$work/export/MANIFEST.txt" <<EOF
AIMusicMed encrypted offline restic package
created_utc=$created
snapshot=$BACKUP_SNAPSHOT
password_included=no
restore_mode=non_overwriting_drill_first
EOF
tar -czf "$output_dir/$package.partial" -C "$work/export" repository MANIFEST.txt
mv "$output_dir/$package.partial" "$output_dir/$package"
(cd "$output_dir" && sha256sum "$package" > "$package.sha256")
printf '%s\t%s\n' "$(date +%s)" "$package" > /backups/status/last-offline-export
echo "Offline package created: $output_dir/$package"
echo "Keep the backup passphrase separately; it is not included in the package."
