import unittest
from pathlib import Path


class BackupOperationsTests(unittest.TestCase):
    root = Path(__file__).resolve().parents[1] / "deploy"

    def read(self, name: str) -> str:
        return (self.root / name).read_text(encoding="utf-8")

    def test_scheduler_runs_six_hour_database_and_daily_full_backups(self):
        loop = self.read("backup-loop.sh")
        self.assertIn("AIMUSICMED_DB_SNAPSHOT_INTERVAL_SECONDS:-21600", loop)
        self.assertIn("AIMUSICMED_BACKUP_INTERVAL_SECONDS:-86400", loop)
        self.assertIn("/opt/backup/db-snapshot.sh", loop)
        self.assertIn("/opt/backup/backup.sh", loop)

    def test_database_snapshots_are_consistent_encrypted_and_retained(self):
        script = self.read("db-snapshot.sh")
        self.assertIn("sqlite3 /data/app.db \".backup '$stage/app.db'\"", script)
        self.assertIn("PRAGMA integrity_check", script)
        self.assertIn("restic backup", script)
        self.assertIn("--keep-within 36h", script)
        self.assertIn('--keep-daily "${AIMUSICMED_BACKUP_KEEP_DAILY:-7}"', script)
        self.assertIn('--keep-weekly "${AIMUSICMED_BACKUP_KEEP_WEEKLY:-4}"', script)
        self.assertIn('--keep-monthly "${AIMUSICMED_BACKUP_KEEP_MONTHLY:-3}"', script)

    def test_offline_export_has_explicit_snapshot_checksum_and_no_password(self):
        script = self.read("export-offline-backup.sh")
        self.assertIn("BACKUP_SNAPSHOT", script)
        self.assertIn("restic copy", script)
        self.assertIn("restic check --read-data", script)
        self.assertIn("sha256sum", script)
        self.assertIn("password_included=no", script)
        self.assertNotIn("$AIMUSICMED_BACKUP_PASSPHRASE\nEOF", script)

    def test_verification_and_drill_never_touch_live_data(self):
        verify = self.read("verify-offline-backup.sh")
        drill = self.read("drill-restore-offline.sh")
        self.assertIn("sha256sum -c", verify)
        self.assertIn("restic check --read-data", verify)
        self.assertIn("PRAGMA integrity_check", verify)
        self.assertIn("*/../*", verify)
        self.assertIn("Unsafe package entry", verify)
        self.assertIn("''|latest|*[!0-9a-f]*", drill)
        self.assertIn('restic restore "$BACKUP_SNAPSHOT"', drill)
        self.assertNotIn("restic restore latest", drill)
        self.assertIn("/backups/drills/*", drill)
        self.assertIn("Unsafe drill target name", drill)
        self.assertIn("must be absent or empty", drill)
        self.assertIn("existing data will never be overwritten", drill)
        self.assertNotIn("rm -rf /data", drill)
        self.assertNotIn("mv ", drill)

    def test_offline_import_requires_explicit_snapshot_and_pre_import_backup(self):
        script = self.read("import-offline-backup.sh")
        self.assertIn("IMPORT_VERIFIED_OFFLINE_BACKUP", script)
        self.assertIn("''|latest|*[!0-9a-f]*", script)
        self.assertIn("verify-offline-backup.sh", script)
        self.assertIn("restic copy", script)
        self.assertLess(script.index("/opt/backup/backup.sh"), script.index("restic copy"))

    def test_offline_item_restore_is_allowlisted_and_non_overwriting(self):
        script = self.read("restore-offline-item.sh")
        self.assertIn("RESTORE_ITEM_NON_OVERWRITING", script)
        self.assertIn("''|latest|*[!0-9a-f]*", script)
        self.assertIn("/data/storage/*|/backup-stage/app.db|/db-snapshot-stage/app.db", script)
        self.assertIn("Path traversal is forbidden", script)
        self.assertIn("/backups/restored-items/$ITEM_RESTORE_NAME", script)
        self.assertIn("must be absent or empty", script)
        self.assertNotIn("--target / ", script)
        self.assertNotIn("rm -rf /data", script)

    def test_destructive_local_restore_takes_snapshot_before_live_replacement(self):
        script = self.read("restore.sh")
        self.assertIn("''|latest|*[!0-9a-f]*", script)
        self.assertIn("/opt/backup/backup.sh", script)
        self.assertLess(script.index("/opt/backup/backup.sh"), script.index("rm -rf /data/storage"))

    def test_upload_is_atomic_and_download_warning_is_fourteen_days(self):
        upload = self.read("upload-offline-backup.sh")
        health = self.read("backup-health.sh")
        marker = self.read("mark-offline-downloaded.sh")
        export = self.read("export-offline-backup.sh")
        self.assertIn("verify-offline-backup.sh", upload)
        self.assertIn(".partial", upload)
        self.assertIn("AIMUSICMED_OFFLINE_WARNING_DAYS:-14", health)
        self.assertIn("last-offline-download", health)
        self.assertIn("sha256sum -c", marker)
        self.assertNotIn("mark-offline-downloaded.sh", export)

    def test_backup_image_contains_every_operation_script(self):
        dockerfile = self.read("backup.Dockerfile")
        for name in (
            "db-snapshot.sh",
            "export-offline-backup.sh",
            "verify-offline-backup.sh",
            "upload-offline-backup.sh",
            "drill-restore-offline.sh",
            "import-offline-backup.sh",
            "restore-offline-item.sh",
            "mark-offline-downloaded.sh",
            "backup-health.sh",
            "create-offline-backup.sh",
            "offline-snapshot-id.sh",
        ):
            self.assertIn(name, dockerfile)

    def test_api_never_gets_docker_socket_and_host_runner_allowlists_actions(self):
        compose = (self.root.parent / "docker-compose.yml").read_text(encoding="utf-8")
        runner = self.read("backup-request-runner.sh")
        api_section = compose.split("  api:", 1)[1].split("  worker:", 1)[0]
        self.assertNotIn("docker.sock", api_section)
        self.assertIn("./backups/requests:/backups/requests", api_section)
        self.assertIn("./backups/offline:/backups/offline:ro", api_section)
        self.assertIn("case \"$action\" in", runner)
        self.assertIn("docker compose stop api worker backup", runner)
        self.assertIn("docker compose up -d api worker backup", runner)
        self.assertNotIn("eval ", runner)


if __name__ == "__main__":
    unittest.main()
