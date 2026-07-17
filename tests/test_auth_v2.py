from __future__ import annotations

import sqlite3
import tempfile
import time
import unittest
from contextlib import closing
from pathlib import Path

from cryptography.fernet import Fernet
from fastapi.testclient import TestClient

from webapp import Settings, create_app
from webapp.security import token_hash


class AuthV2Tests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        root = Path(self.temp.name)
        self.settings = Settings(
            database_path=root / "app.db", storage_root=root / "storage",
            fernet_key=Fernet.generate_key().decode(), worker_token="worker-token-longer-than-24-characters",
            admin_email="admin@example.com", dev_auth_codes=True, secure_cookies=False,
        )
        self.client = TestClient(create_app(self.settings))

    def tearDown(self):
        self.client.close()
        self.temp.cleanup()

    def code(self, email, purpose="login"):
        return self.client.post("/auth/code/request", json={"email": email, "purpose": purpose}).json().get("verification_code")

    def login_admin(self):
        code = self.code("admin@example.com")
        result = self.client.post("/auth/code/verify", json={"email": "admin@example.com", "code": code, "purpose": "login"})
        self.assertEqual(result.json()["password_setup"], "required")

    def action_token(self, action: str) -> str:
        issued = self.client.post(
            "/admin/sensitive-actions/code/request", json={"action": action}
        ).json()
        return self.client.post(
            "/admin/sensitive-actions/code/verify",
            json={"action": action, "code": issued["verification_code"]},
        ).json()["action_token"]

    def clear_events(self):
        with closing(sqlite3.connect(self.settings.database_path)) as conn:
            conn.execute("DELETE FROM auth_events")
            conn.commit()

    def test_unknown_email_is_non_enumerating_and_gets_no_code(self):
        known = self.client.post("/auth/code/request", json={"email": "admin@example.com", "purpose": "login"}).json()
        unknown = self.client.post("/auth/code/request", json={"email": "nobody@example.com", "purpose": "login"}).json()
        self.assertEqual({k: unknown[k] for k in ("sent", "expires_in")}, {"sent": True, "expires_in": 900})
        self.assertIn("verification_code", known)
        self.assertNotIn("verification_code", unknown)

    def test_admin_setup_is_enforced_then_password_login_works(self):
        self.login_admin()
        self.assertEqual(self.client.get("/admin/users").status_code, 403)
        password = "correct horse battery staple"
        self.assertEqual(self.client.put("/account/password", json={"password": password, "password_confirmation": password}).status_code, 200)
        fresh = TestClient(self.client.app)
        self.assertEqual(fresh.post("/auth/password/login", json={"email": "admin@example.com", "password": password}).status_code, 200)
        fresh.close()

    def test_invite_activates_with_single_use_hashed_code_and_disable_revokes(self):
        self.login_admin()
        password = "correct horse battery staple"
        self.client.put("/account/password", json={"password": password, "password_confirmation": password})
        with closing(sqlite3.connect(self.settings.database_path)) as conn:
            conn.execute("DELETE FROM auth_events")
            conn.commit()
        invite = self.client.post("/admin/invitations", json={"email": "user@example.com"}).json()
        code = invite["verification_code"]
        user = TestClient(self.client.app)
        self.assertEqual(user.post("/auth/code/verify", json={"email": "user@example.com", "code": code, "purpose": "login"}).status_code, 200)
        self.assertEqual(user.post("/auth/code/verify", json={"email": "user@example.com", "code": code, "purpose": "login"}).status_code, 401)
        with closing(sqlite3.connect(self.settings.database_path)) as conn:
            row = conn.execute("SELECT users.id,code_hash FROM verification_codes JOIN users ON users.id=verification_codes.user_id WHERE email='user@example.com'").fetchone()
            self.assertNotIn(code, row[1])
        self.client.patch(
            f"/admin/users/{row[0]}/status",
            headers={"X-Admin-Action-Token": self.action_token("change_user_status")},
            json={"status": "disabled"},
        )
        self.assertEqual(user.get("/me").status_code, 401)
        user.close()

    def test_pending_user_cannot_be_disabled_or_enabled(self):
        self.login_admin()
        password = "correct horse battery staple"
        self.client.put(
            "/account/password",
            json={"password": password, "password_confirmation": password},
        )
        self.clear_events()
        invite = self.client.post(
            "/admin/invitations", json={"email": "pending@example.com"}
        )
        self.assertEqual(invite.status_code, 201)
        with closing(sqlite3.connect(self.settings.database_path)) as conn:
            user_id = conn.execute(
                "SELECT id FROM users WHERE email='pending@example.com'"
            ).fetchone()[0]
        for target_status in ("disabled", "active"):
            response = self.client.patch(
                f"/admin/users/{user_id}/status",
                headers={"X-Admin-Action-Token": self.action_token("change_user_status")},
                json={"status": target_status},
            )
            self.assertEqual(response.status_code, 409)
            self.assertEqual(
                response.json()["error"]["code"], "user_not_activated"
            )

    def test_five_bad_passwords_lock_for_fifteen_minutes(self):
        self.login_admin()
        password = "correct horse battery staple"
        self.client.put("/account/password", json={"password": password, "password_confirmation": password})
        fresh = TestClient(self.client.app)
        for _ in range(5):
            self.assertEqual(fresh.post("/auth/password/login", json={"email": "admin@example.com", "password": "wrong password value"}).status_code, 401)
        self.assertEqual(fresh.post("/auth/password/login", json={"email": "admin@example.com", "password": "another wrong password"}).status_code, 423)
        self.assertEqual(fresh.post("/auth/password/login", json={"email": "admin@example.com", "password": password}).status_code, 423)
        fresh.close()

    def test_current_password_required_when_changing_existing_password(self):
        self.login_admin()
        old, new = "correct horse battery staple", "new correct horse battery staple"
        self.client.put("/account/password", json={"password": old, "password_confirmation": old})
        missing = self.client.put("/account/password", json={"password": new, "password_confirmation": new})
        self.assertEqual(missing.status_code, 401)
        wrong = self.client.put("/account/password", json={"current_password": "not the current password", "password": new, "password_confirmation": new})
        self.assertEqual(wrong.status_code, 401)
        changed = self.client.put("/account/password", json={"current_password": old, "password": new, "password_confirmation": new})
        self.assertEqual(changed.status_code, 200)

    def test_password_reset_revokes_all_existing_sessions(self):
        self.login_admin()
        old, new = "correct horse battery staple", "new correct horse battery staple"
        self.client.put("/account/password", json={"password": old, "password_confirmation": old})
        first, second = TestClient(self.client.app), TestClient(self.client.app)
        for client in (first, second):
            self.assertEqual(client.post("/auth/password/login", json={"email": "admin@example.com", "password": old}).status_code, 200)
        self.clear_events()
        code = self.code("admin@example.com", "password_reset")
        verified = self.client.post("/auth/code/verify", json={"email": "admin@example.com", "code": code, "purpose": "password_reset"}).json()
        reset = self.client.post("/auth/password/reset", json={"reset_token": verified["reset_token"], "password": new, "password_confirmation": new})
        self.assertEqual(reset.status_code, 200)
        self.assertEqual(first.get("/me").status_code, 401)
        self.assertEqual(second.get("/me").status_code, 401)
        first.close(); second.close()

    def test_auth_v2_migration_is_idempotent_and_preserves_content(self):
        now = int(time.time())
        with closing(sqlite3.connect(self.settings.database_path)) as conn:
            user_id = conn.execute("SELECT id FROM users WHERE email='admin@example.com'").fetchone()[0]
            conn.execute("DELETE FROM schema_migrations WHERE name='20260716_auth_v2'")
            conn.execute("INSERT INTO conversations(id,user_id,title,created_at,updated_at) VALUES('kept',?,'kept',?,?)", (user_id, now, now))
            conn.execute("INSERT INTO sessions(token_hash,user_id,expires_at,created_at) VALUES('legacy-session',?,?,?)", (user_id, now + 900, now))
            conn.execute("INSERT INTO magic_links(token_hash,user_id,expires_at) VALUES('legacy-link',?,?)", (user_id, now + 900))
            conn.commit()
        restarted = TestClient(create_app(self.settings))
        restarted.close()
        with closing(sqlite3.connect(self.settings.database_path)) as conn:
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM sessions").fetchone()[0], 0)
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM magic_links").fetchone()[0], 0)
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM conversations WHERE id='kept'").fetchone()[0], 1)
            conn.execute("INSERT INTO sessions(token_hash,user_id,expires_at,created_at) VALUES('new-session',?,?,?)", (user_id, now + 900, now))
            conn.commit()
        restarted = TestClient(create_app(self.settings)); restarted.close()
        with closing(sqlite3.connect(self.settings.database_path)) as conn:
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM sessions WHERE token_hash='new-session'").fetchone()[0], 1)

    def test_hourly_send_limit_uses_only_hashed_identifiers(self):
        self.clear_events()
        now = int(time.time())
        email_hash = token_hash(f"{self.settings.worker_token}:email:admin@example.com")
        ip_hash = token_hash(f"{self.settings.worker_token}:ip:testclient")
        with closing(sqlite3.connect(self.settings.database_path)) as conn:
            conn.executemany(
                "INSERT INTO auth_events(kind,email_hash,ip_hash,created_at) VALUES('send',?,?,?)",
                [(email_hash, f"other-ip-{index}", now - 120) for index in range(5)],
            )
            conn.commit()
        limited = self.client.post("/auth/code/request", json={"email": "admin@example.com", "purpose": "login"}).json()
        self.assertNotIn("verification_code", limited)
        self.assertNotIn("@", email_hash)
        self.assertNotIn("testclient", ip_hash)


if __name__ == "__main__":
    unittest.main()
