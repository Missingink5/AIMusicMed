#!/bin/sh
set -eu

now="$(date +%s)"
warning_days="${AIMUSICMED_OFFLINE_WARNING_DAYS:-14}"
case "$warning_days" in ''|*[!0-9]*) echo "warning days must be an integer" >&2; exit 2 ;; esac
threshold="$((warning_days * 86400))"
marker=/backups/status/last-offline-download
baseline=/backups/status/last-success

if [ -f "$marker" ]; then
  recorded="$(awk 'NR==1 {print $1}' "$marker")"
elif [ -f "$baseline" ]; then
  recorded="$(stat -c %Y "$baseline")"
else
  echo "WARNING: no successful full backup or verified offline download has been recorded" >&2
  exit 1
fi
if [ $((now - recorded)) -gt "$threshold" ]; then
  echo "WARNING: no checksum-verified offline backup download in ${warning_days} days" >&2
  exit 1
fi
echo "Backup health OK: offline download age is within ${warning_days} days"

