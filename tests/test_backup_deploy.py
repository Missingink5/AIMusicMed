from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


class BackupDeploymentTests(unittest.TestCase):
    def read(self, name: str) -> str:
        return (ROOT / "deploy" / name).read_text(encoding="utf-8")

    def test_backup_is_deduplicated_and_database_is_consistent(self):
        script = self.read("backup.sh")
        self.assertIn("sqlite3 /data/app.db \".backup '$stage/app.db'\"", script)
        self.assertIn("restic backup", script)
        self.assertIn('"$stage/app.db" /data/storage', script)
        self.assertNotIn("storage.tar", script)
        self.assertNotIn("openssl enc", script)

    def test_backup_has_bounded_retention_and_disk_guards(self):
        script = self.read("backup.sh")
        self.assertIn("--keep-daily", script)
        self.assertIn("--keep-weekly", script)
        self.assertIn("--keep-monthly", script)
        self.assertIn("--prune", script)
        self.assertIn("AIMUSICMED_BACKUP_MAX_REPO_MB", script)
        self.assertIn("AIMUSICMED_BACKUP_MIN_FREE_MB", script)
        self.assertIn('mv "$run_marker" "$success_marker"', script)

    def test_restore_requires_explicit_snapshot_and_checks_database(self):
        script = self.read("restore.sh")
        self.assertIn("BACKUP_SNAPSHOT", script)
        self.assertIn("''|latest|*[!0-9a-f]*", script)
        self.assertIn("PRAGMA integrity_check", script)
        self.assertIn("restic check --read-data", script)
        self.assertLess(script.index("restic check"), script.index("rm -rf /data/storage"))
        self.assertLess(script.index("restic restore \"$BACKUP_SNAPSHOT\""), script.index("rm -rf /data/storage"))

    def test_non_destructive_verifier_is_packaged(self):
        verifier = self.read("verify-backup.sh")
        dockerfile = self.read("backup.Dockerfile")
        self.assertIn("PRAGMA integrity_check", verifier)
        self.assertIn("restic check --read-data", verifier)
        self.assertNotIn("rm -rf /data/storage", verifier)
        self.assertIn("verify-backup.sh", dockerfile)
        self.assertIn("restic", dockerfile)


if __name__ == "__main__":
    unittest.main()
