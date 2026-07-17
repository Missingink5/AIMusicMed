#!/bin/sh
set -eu

project_dir="${AIMUSICMED_PROJECT_DIR:-/opt/aimusicmed}"
if [ "$(id -u)" -ne 0 ]; then
  echo "Run this installer as root" >&2
  exit 2
fi
test -f "$project_dir/docker-compose.yml"
install -d -o 10001 -g 10001 -m 2750 \
  "$project_dir/backups/requests/pending" \
  "$project_dir/backups/requests/working" \
  "$project_dir/backups/requests/completed" \
  "$project_dir/backups/requests/failed" \
  "$project_dir/backups/uploads" \
  "$project_dir/backups/status"
install -d -o root -g 10001 -m 2750 "$project_dir/backups/offline"
chmod 0555 "$project_dir/deploy/backup-request-runner.sh"
install -m 0644 "$project_dir/deploy/aimusicmed-backup-requests.service" \
  /etc/systemd/system/aimusicmed-backup-requests.service
install -m 0644 "$project_dir/deploy/aimusicmed-backup-requests.path" \
  /etc/systemd/system/aimusicmed-backup-requests.path
systemctl daemon-reload
systemctl enable --now aimusicmed-backup-requests.path
