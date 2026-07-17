FROM alpine:3.22

RUN apk add --no-cache restic sqlite

COPY deploy/backup.sh deploy/backup-loop.sh deploy/db-snapshot.sh \
  deploy/restore.sh deploy/verify-backup.sh \
  deploy/export-offline-backup.sh deploy/verify-offline-backup.sh \
  deploy/upload-offline-backup.sh deploy/drill-restore-offline.sh \
  deploy/import-offline-backup.sh deploy/restore-offline-item.sh \
  deploy/mark-offline-downloaded.sh deploy/backup-health.sh \
  deploy/create-offline-backup.sh deploy/offline-snapshot-id.sh /opt/backup/
RUN chmod 0555 /opt/backup/*.sh

ENTRYPOINT ["/bin/sh"]
CMD ["/opt/backup/backup-loop.sh"]
