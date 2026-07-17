from __future__ import annotations

import hashlib
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from cryptography.fernet import Fernet
from fastapi.testclient import TestClient

from webapp import Settings, create_app


class BackupAdminApiTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.backups = self.root / "backups"
        self.environment = patch.dict(os.environ, {
            "DEEPSEEK_API_KEY": "",
            "AIMUSICMED_BACKUPS_ROOT": str(self.backups),
        })
        self.environment.start()
        settings = Settings(
            database_path=self.root / "app.db",
            storage_root=self.root / "storage",
            fernet_key=Fernet.generate_key().decode(),
            worker_token="backup-test-worker-token-long-enough",
            admin_email="admin@example.com",
            dev_auth_codes=True,
            secure_cookies=False,
        )
        self.database_path = settings.database_path
        self.client = TestClient(create_app(settings))
        code = self.client.post(
            "/auth/code/request", json={"email": "admin@example.com"},
        ).json()["verification_code"]
        logged_in = self.client.post("/auth/code/verify", json={
            "email": "admin@example.com", "code": code, "purpose": "login",
        })
        self.assertEqual(logged_in.status_code, 200)
        password = "correct horse battery staple"
        configured = self.client.put("/account/password", json={
            "password": password, "password_confirmation": password,
        })
        self.assertEqual(configured.status_code, 200)

    def tearDown(self):
        self.client.close()
        self.environment.stop()
        self.temp.cleanup()

    def action_token(self, action: str) -> str:
        issued = self.client.post(
            "/admin/sensitive-actions/code/request", json={"action": action},
        ).json()
        return self.client.post("/admin/sensitive-actions/code/verify", json={
            "action": action, "code": issued["verification_code"],
        }).json()["action_token"]

    def package(self) -> tuple[str, bytes]:
        name = "aimusicmed-offline-20260717T120000Z-deadbeef.tar.gz"
        content = b"encrypted-restic-package"
        directory = self.backups / "offline"
        directory.mkdir(parents=True)
        (directory / name).write_bytes(content)
        digest = hashlib.sha256(content).hexdigest()
        (directory / f"{name}.sha256").write_text(f"{digest}  {name}\n", encoding="ascii")
        return name, content

    def test_create_is_purpose_bound_queued_and_audited_without_docker(self):
        denied = self.client.post("/admin/backups")
        self.assertEqual(denied.status_code, 403)
        response = self.client.post(
            "/admin/backups",
            headers={"X-Admin-Action-Token": self.action_token("create_backup")},
        )
        self.assertEqual(response.status_code, 202, response.text)
        queued = list((self.backups / "requests" / "pending").glob("*.json"))
        self.assertEqual(len(queued), 1)
        payload = json.loads(queued[0].read_text(encoding="utf-8"))
        self.assertEqual(payload["action"], "create_export")
        self.assertNotIn("command", payload)
        source = Path(__file__).parents[1] / "webapp" / "operations.py"
        self.assertNotIn("docker.sock", source.read_text(encoding="utf-8"))
        self.assertNotIn("subprocess", source.read_text(encoding="utf-8"))

    def test_verified_package_download_is_real_and_records_marker(self):
        name, content = self.package()
        token = self.action_token("download_backup")
        response = self.client.get(
            f"/admin/backups/{name}/download",
            headers={"X-Admin-Action-Token": token},
        )
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.content, content)
        marker = (self.backups / "status" / "last-offline-download").read_text(encoding="utf-8")
        self.assertIn(name, marker)

    def test_download_rejects_checksum_mismatch(self):
        name, _ = self.package()
        token = self.action_token("download_backup")
        (self.backups / name).write_bytes(b"unused")
        (self.backups / "offline" / name).write_bytes(b"tampered")
        response = self.client.get(
            f"/admin/backups/{name}/download",
            headers={"X-Admin-Action-Token": token},
        )
        self.assertEqual(response.status_code, 409)

    def test_upload_uses_generated_name_and_queues_verification(self):
        token = self.action_token("upload_backup")
        response = self.client.post(
            "/admin/backups/upload",
            headers={"X-Admin-Action-Token": token},
            files={"file": ("../../host.tar.gz", b"archive", "application/gzip")},
        )
        self.assertEqual(response.status_code, 202, response.text)
        package_id = response.json()["package_id"]
        self.assertNotIn("..", package_id)
        self.assertTrue((self.backups / "uploads" / package_id).is_file())
        request = next((self.backups / "requests" / "pending").glob("*.json"))
        self.assertEqual(json.loads(request.read_text(encoding="utf-8"))["action"], "verify_upload")

    def test_restore_accepts_only_existing_safe_package_and_queues_request(self):
        name, _ = self.package()
        token = self.action_token("restore_backup")
        response = self.client.post(
            f"/admin/backups/{name}/restore",
            headers={"X-Admin-Action-Token": token},
        )
        self.assertEqual(response.status_code, 202, response.text)
        request = next((self.backups / "requests" / "pending").glob("*.json"))
        payload = json.loads(request.read_text(encoding="utf-8"))
        self.assertEqual(payload["action"], "restore")
        self.assertEqual(payload["package_id"], name)


if __name__ == "__main__":
    unittest.main()
