FROM alpine:3.22

RUN apk add --no-cache restic sqlite

COPY deploy/backup.sh deploy/backup-loop.sh deploy/restore.sh deploy/verify-backup.sh /opt/backup/
RUN chmod 0555 /opt/backup/*.sh

ENTRYPOINT ["/bin/sh"]
CMD ["/opt/backup/backup-loop.sh"]
