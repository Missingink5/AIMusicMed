from __future__ import annotations

import json
import os
import sqlite3
import tempfile
import unittest
from contextlib import closing
from dataclasses import replace
from pathlib import Path
from unittest.mock import Mock, patch
from unittest.mock import AsyncMock
from types import SimpleNamespace

from cryptography.fernet import Fernet
from fastapi.testclient import TestClient
from tencentcloud.common.exception.tencent_cloud_sdk_exception import TencentCloudSDKException

from webapp import Settings, create_app


ADMIN_EMAIL = "admin@example.com"
WORKER_TOKEN = "worker-token-longer-than-24-characters"
PASSWORD = "correct horse battery staple"


class WebAppTests(unittest.TestCase):
    def setUp(self):
        self.environment = patch.dict(os.environ, {"DEEPSEEK_API_KEY": ""})
        self.environment.start()
        self.temp = tempfile.TemporaryDirectory()
        root = Path(self.temp.name)
        self.settings = Settings(
            database_path=root / "app.db",
            storage_root=root / "storage",
            fernet_key=Fernet.generate_key().decode(),
            worker_token=WORKER_TOKEN,
            admin_email=ADMIN_EMAIL,
            dev_auth_codes=True,
            secure_cookies=False,
        )
        self.app = create_app(self.settings)
        self.client = TestClient(self.app)
        self.admin_login()

    def tearDown(self):
        self.client.close()
        self.temp.cleanup()
        self.environment.stop()

    def admin_login(self):
        code = self.client.post("/auth/code/request", json={"email": ADMIN_EMAIL}).json()["verification_code"]
        verified = self.client.post("/auth/code/verify", json={"email": ADMIN_EMAIL, "code": code, "purpose": "login"})
        self.assertEqual(verified.status_code, 200)
        self.client.put("/account/password", json={"password": PASSWORD, "password_confirmation": PASSWORD})

    def create_user_client(self, email: str) -> TestClient:
        with closing(sqlite3.connect(self.settings.database_path)) as conn:
            conn.execute("DELETE FROM auth_events")
            conn.commit()
        invite = self.client.post("/admin/invitations", json={"email": email})
        code = invite.json()["verification_code"]
        user_client = TestClient(self.app)
        login = user_client.post("/auth/code/verify", json={"email": email, "code": code, "purpose": "login"})
        self.assertEqual(login.status_code, 200)
        return user_client

    @staticmethod
    def create_plan(client: TestClient, *, mode="platform", content="今天有点紧张", voice_mode="tts"):
        conversation = client.post("/conversations", json={"title": "测试"}).json()["id"]
        message = client.post(
            f"/conversations/{conversation}/messages", json={"content": content}
        ).json()["id"]
        response = client.post(
            f"/conversations/{conversation}/plans",
            json={
                "message_id": message,
                "duration_minutes": 5,
                "music_source": "library",
                "target_emotion": "auto",
                "credential_mode": mode,
                "voice_mode": voice_mode,
            },
        )
        return response

    def worker_headers(self):
        return {"Authorization": f"Bearer {WORKER_TOKEN}"}

    def test_sqlite_uses_wal_and_errors_are_uniform(self):
        with closing(sqlite3.connect(self.settings.database_path)) as conn:
            self.assertEqual(conn.execute("PRAGMA journal_mode").fetchone()[0], "wal")
        with TestClient(self.app) as anonymous:
            response = anonymous.get("/me")
        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.json()["error"]["code"], "authentication_required")

    def test_admin_email_code_is_single_use_and_cookie_is_httponly(self):
        with closing(sqlite3.connect(self.settings.database_path)) as conn:
            conn.execute("DELETE FROM auth_events")
            conn.commit()
        fresh = TestClient(self.app)
        code = fresh.post("/auth/code/request", json={"email": ADMIN_EMAIL}).json()["verification_code"]
        bad = fresh.post("/auth/code/verify", json={"email": ADMIN_EMAIL, "code": "000000", "purpose": "login"})
        self.assertEqual(bad.status_code, 401)
        good = fresh.post("/auth/code/verify", json={"email": ADMIN_EMAIL, "code": code, "purpose": "login"})
        self.assertIn("HttpOnly", good.headers["set-cookie"])
        self.assertIn("SameSite=strict", good.headers["set-cookie"])
        reused = fresh.post("/auth/code/verify", json={"email": ADMIN_EMAIL, "code": code, "purpose": "login"})
        self.assertEqual(reused.status_code, 401)

    def test_uninvited_login_is_non_enumerating(self):
        response = self.client.post("/auth/code/request", json={"email": "unknown@example.com"})
        self.assertEqual(response.json(), {"sent": True, "expires_in": 900})

    def test_email_code_is_throttled_without_email_or_ip_storage(self):
        with closing(sqlite3.connect(self.settings.database_path)) as conn:
            conn.execute("DELETE FROM auth_events")
            conn.commit()
        first = self.client.post("/auth/code/request", json={"email": ADMIN_EMAIL}).json()
        second = self.client.post("/auth/code/request", json={"email": ADMIN_EMAIL}).json()
        self.assertIn("verification_code", first)
        self.assertEqual(second, {"sent": True, "expires_in": 900})
        with closing(sqlite3.connect(self.settings.database_path)) as conn:
            row = conn.execute("SELECT email_hash,ip_hash FROM auth_events ORDER BY id DESC LIMIT 1").fetchone()
        self.assertNotIn("@", row[0])
        self.assertNotIn("testclient", row[1])

    @patch("webapp.app.ses_client.SesClient")
    def test_production_email_uses_ses_and_failure_rolls_back_tokens(self, ses_client_type):
        production = replace(
            self.settings,
            dev_auth_codes=False,
            public_base_url="https://aimusicmed.cn",
            tencentcloud_secret_id="test-secret-id",
            tencentcloud_secret_key="test-secret-key",
            tencentcloud_region="ap-hongkong",
            ses_from="AIMusicMed <no-reply@mail.aimusicmed.cn>",
            ses_template_id=12345,
        )
        client = TestClient(create_app(production))
        client.cookies.update(self.client.cookies)
        ses = ses_client_type.return_value
        with closing(sqlite3.connect(self.settings.database_path)) as conn:
            conn.execute("DELETE FROM auth_events")
            conn.commit()
        sent = client.post("/admin/invitations", json={"email": "ses@example.com"})
        self.assertEqual(sent.status_code, 201)
        request = ses.SendEmail.call_args.args[0]
        payload = json.loads(request.to_json_string())
        self.assertEqual(payload["Destination"], ["ses@example.com"])
        self.assertEqual(payload["FromEmailAddress"], "AIMusicMed <no-reply@mail.aimusicmed.cn>")
        self.assertEqual(payload["Template"]["TemplateID"], 12345)
        template_data = json.loads(payload["Template"]["TemplateData"])
        self.assertEqual(template_data["action"], "激活 AIMusicMed 账号")
        self.assertEqual(template_data["expires"], "15 分钟")
        self.assertRegex(template_data["code"], r"^\d{6}$")
        self.assertEqual(set(template_data), {"action", "expires", "code"})

        ses.SendEmail.side_effect = TencentCloudSDKException("InternalError", "offline")
        with closing(sqlite3.connect(self.settings.database_path)) as conn:
            conn.execute("DELETE FROM auth_events")
            conn.commit()
        failed = client.post("/admin/invitations", json={"email": "ses-fail@example.com"})
        self.assertEqual(failed.status_code, 503)
        self.assertEqual(failed.json()["error"]["code"], "email_delivery_failed")
        with closing(sqlite3.connect(self.settings.database_path)) as conn:
            missing = conn.execute("SELECT 1 FROM users WHERE email='ses-fail@example.com'").fetchone()
        self.assertIsNone(missing)

        with closing(sqlite3.connect(self.settings.database_path)) as conn:
            conn.execute("DELETE FROM auth_events")
            before = conn.execute("SELECT COUNT(*) FROM verification_codes").fetchone()[0]
            conn.commit()
        login_failed = client.post("/auth/code/request", json={"email": ADMIN_EMAIL})
        self.assertEqual(login_failed.status_code, 200)
        self.assertEqual(login_failed.json(), {"sent": True, "expires_in": 900})
        with closing(sqlite3.connect(self.settings.database_path)) as conn:
            after = conn.execute("SELECT COUNT(*) FROM verification_codes").fetchone()[0]
        self.assertEqual(after, before)

    def test_global_task_concurrency_is_configurable_from_one_to_two(self):
        first = self.create_user_client("concurrency-one@example.com")
        second = self.create_user_client("concurrency-two@example.com")
        first_job = first.post(f"/plans/{self.create_plan(first).json()['id']}/jobs").json()["id"]
        second_job = second.post(f"/plans/{self.create_plan(second).json()['id']}/jobs").json()["id"]

        claimed = self.client.post("/internal/worker/claim", headers=self.worker_headers())
        self.assertEqual(claimed.json()["id"], first_job)
        blocked = self.client.post("/internal/worker/claim", headers=self.worker_headers())
        self.assertEqual(blocked.status_code, 204)

        two_slot_client = TestClient(create_app(replace(self.settings, global_task_concurrency=2)))
        second_claim = two_slot_client.post("/internal/worker/claim", headers=self.worker_headers())
        self.assertEqual(second_claim.json()["id"], second_job)
        two_slot_client.close()

    def test_crisis_message_pauses_plan_before_job(self):
        user = self.create_user_client("risk@example.com")
        conversation = user.post("/conversations", json={"title": "危机"}).json()["id"]
        message = user.post(
            f"/conversations/{conversation}/messages", json={"content": "我不想活了"}
        )
        self.assertEqual(message.json()["risk_level"], "crisis")
        self.assertEqual(message.json()["crisis_help"]["emergency_numbers"], ["110", "120", "12356"])
        plan = user.post(
            f"/conversations/{conversation}/plans",
            json={"message_id": message.json()["id"], "duration_minutes": 5},
        )
        self.assertEqual(plan.status_code, 409)
        self.assertEqual(plan.json()["error"]["code"], "crisis_generation_paused")

    def test_byok_is_encrypted_and_worker_receives_decrypted_keys(self):
        user = self.create_user_client("byok@example.com")
        values = {
            "deepseek_api_key": "deepseek-private-key",
            "minimax_api_key": "minimax-private-key",
            "elevenlabs_api_key": "eleven-private-key",
        }
        self.assertEqual(user.put("/settings/credentials", json=values).status_code, 200)
        database_bytes = self.settings.database_path.read_bytes()
        for value in values.values():
            self.assertNotIn(value.encode(), database_bytes)
        plan = self.create_plan(user, mode="byok").json()["id"]
        job = user.post(f"/plans/{plan}/jobs").json()["id"]
        claim = self.client.post("/internal/worker/claim", headers=self.worker_headers())
        self.assertEqual(claim.json()["id"], job)
        self.assertEqual(claim.json()["voice_mode"], "tts")
        self.assertEqual(claim.json()["credentials"]["minimax_api_key"], values["minimax_api_key"])

    def test_one_active_job_per_user_and_failed_job_releases_slot(self):
        user = self.create_user_client("queue@example.com")
        first_plan = self.create_plan(user).json()["id"]
        first_job = user.post(f"/plans/{first_plan}/jobs").json()["id"]
        second_plan = self.create_plan(user).json()["id"]
        blocked = user.post(f"/plans/{second_plan}/jobs")
        self.assertEqual(blocked.status_code, 409)
        self.client.post("/internal/worker/claim", headers=self.worker_headers())
        self.client.post(
            f"/internal/worker/jobs/{first_job}/fail",
            headers=self.worker_headers(),
            json={"error_code": "offline_test"},
        )
        self.assertEqual(user.post(f"/plans/{second_plan}/jobs").status_code, 201)

    def test_platform_daily_limit_is_reserved_but_byok_bypasses_it(self):
        user = self.create_user_client("limit@example.com")
        user_id = user.get("/me").json()["id"]
        with closing(sqlite3.connect(self.settings.database_path)) as conn:
            conn.execute("UPDATE users SET daily_limit=0 WHERE id=?", (user_id,))
            conn.commit()
        platform_plan = self.create_plan(user).json()["id"]
        limited = user.post(f"/plans/{platform_plan}/jobs")
        self.assertEqual(limited.status_code, 429)
        user.put(
            "/settings/credentials",
            json={"deepseek_api_key": "deepseek-key", "minimax_api_key": "minimax-key"},
        )
        byok_plan = self.create_plan(user, mode="byok").json()["id"]
        self.assertEqual(user.post(f"/plans/{byok_plan}/jobs").status_code, 201)

    def test_worker_progress_cancel_and_persistent_events(self):
        user = self.create_user_client("events@example.com")
        plan = self.create_plan(user).json()["id"]
        job = user.post(f"/plans/{plan}/jobs").json()["id"]
        self.client.post("/internal/worker/claim", headers=self.worker_headers())
        event = self.client.post(
            f"/internal/worker/jobs/{job}/events",
            headers=self.worker_headers(),
            json={"stage": "music", "current": 1, "total": 3, "message": "第一段"},
        )
        self.assertFalse(event.json()["cancel_requested"])
        self.assertEqual(user.post(f"/jobs/{job}/cancel").json()["status"], "cancel_requested")
        heartbeat = self.client.post(
            f"/internal/worker/jobs/{job}/heartbeat", headers=self.worker_headers()
        )
        self.assertTrue(heartbeat.json()["cancel_requested"])
        data = user.get(f"/jobs/{job}").json()
        self.assertIn("music", [item["stage"] for item in data["events"]])

    def test_completed_work_download_is_owner_only(self):
        owner = self.create_user_client("owner@example.com")
        stranger = self.create_user_client("stranger@example.com")
        plan = self.create_plan(owner).json()["id"]
        job = owner.post(f"/plans/{plan}/jobs").json()["id"]
        claim = self.client.post("/internal/worker/claim", headers=self.worker_headers()).json()
        output = Path(claim["output_path"])
        output.write_bytes(b"RIFF-test-audio")
        output.with_suffix(".mp3").write_bytes(b"mp3-test-audio")
        output.with_suffix(".txt").write_text("引导词", encoding="utf-8")
        complete = self.client.post(
            f"/internal/worker/jobs/{job}/complete",
            headers=self.worker_headers(),
            json={"title": "成品"},
        )
        work_id = complete.json()["work_id"]
        self.assertEqual(owner.get(f"/works/{work_id}/download?format=wav").content, b"RIFF-test-audio")
        self.assertEqual(owner.get(f"/works/{work_id}/download?format=mp3").content, b"mp3-test-audio")
        ranged = owner.get(
            f"/works/{work_id}/download?format=mp3", headers={"Range": "bytes=0-2"}
        )
        self.assertEqual(ranged.status_code, 206)
        self.assertEqual(ranged.content, b"mp3")
        self.assertIn("引导词", owner.get(f"/works/{work_id}/download?format=txt").text)
        self.assertEqual(stranger.get(f"/works/{work_id}/download").status_code, 404)
        self.assertEqual(self.client.get(f"/works/{work_id}/download").status_code, 404)

    def test_admin_can_list_users_and_adjust_quota_without_content_access(self):
        user = self.create_user_client("quota-admin@example.com")
        user_id = user.get("/me").json()["id"]
        users = self.client.get("/admin/users").json()["items"]
        self.assertIn("quota-admin@example.com", [item["email"] for item in users])
        changed = self.client.patch(f"/admin/users/{user_id}/quota", json={"daily_limit": 4})
        self.assertEqual(changed.json()["daily_limit"], 4)
        self.assertEqual(user.get("/me").json()["daily_limit"], 4)
        self.assertNotIn("content", str(users))

    def test_expired_work_is_blocked_but_favorite_is_retained(self):
        owner = self.create_user_client("favorite@example.com")
        plan = self.create_plan(owner, voice_mode="pure_music").json()["id"]
        job = owner.post(f"/plans/{plan}/jobs").json()["id"]
        claim = self.client.post("/internal/worker/claim", headers=self.worker_headers()).json()
        self.assertEqual(claim["voice_mode"], "pure_music")
        output = Path(claim["output_path"])
        output.write_bytes(b"wav")
        output.with_suffix(".mp3").write_bytes(b"mp3")
        output.with_suffix(".txt").write_text("", encoding="utf-8")
        work_id = self.client.post(
            f"/internal/worker/jobs/{job}/complete", headers=self.worker_headers(), json={}
        ).json()["work_id"]
        with closing(sqlite3.connect(self.settings.database_path)) as conn:
            conn.execute("UPDATE works SET expires_at=0 WHERE id=?", (work_id,))
            conn.commit()
        self.assertEqual(owner.get(f"/works/{work_id}/download").status_code, 410)
        self.assertEqual(owner.get(f"/works/{work_id}/download?format=txt").status_code, 200)
        self.assertEqual(owner.post(f"/works/{work_id}/favorite").status_code, 410)
        with closing(sqlite3.connect(self.settings.database_path)) as conn:
            conn.execute("UPDATE works SET expires_at=? WHERE id=?", (2**31, work_id))
            conn.commit()
        self.assertTrue(owner.post(f"/works/{work_id}/favorite").json()["is_favorite"])
        with closing(sqlite3.connect(self.settings.database_path)) as conn:
            conn.execute("UPDATE works SET expires_at=0 WHERE id=?", (work_id,))
            conn.commit()
        self.assertEqual(owner.get(f"/works/{work_id}/download").status_code, 200)
        with closing(sqlite3.connect(self.settings.database_path)) as conn:
            conversation_id = conn.execute(
                "SELECT p.conversation_id FROM jobs j JOIN plans p ON p.id=j.plan_id WHERE j.id=?",
                (job,),
            ).fetchone()[0]
        self.assertEqual(owner.delete(f"/conversations/{conversation_id}").status_code, 200)
        favorites = owner.get("/works?favorites_only=true").json()["items"]
        self.assertEqual([item["id"] for item in favorites], [work_id])
        self.assertEqual(owner.get(f"/works/{work_id}/download").status_code, 200)

    def test_conversation_restore_is_owner_scoped(self):
        owner = self.create_user_client("history@example.com")
        stranger = self.create_user_client("history-stranger@example.com")
        plan_response = self.create_plan(owner)
        plan_id = plan_response.json()["id"]
        with closing(sqlite3.connect(self.settings.database_path)) as conn:
            conversation_id = conn.execute("SELECT conversation_id FROM plans WHERE id=?", (plan_id,)).fetchone()[0]
        restored = owner.get(f"/conversations/{conversation_id}")
        self.assertEqual(restored.status_code, 200)
        self.assertEqual(restored.json()["plans"][0]["id"], plan_id)
        self.assertEqual(stranger.get(f"/conversations/{conversation_id}").status_code, 404)

    def test_conversation_search_rename_trash_restore_and_purge(self):
        owner = self.create_user_client("history-v2@example.com")
        stranger = self.create_user_client("history-v2-stranger@example.com")
        conversation = owner.post("/conversations", json={"title": "工作压力"}).json()["id"]
        message = owner.post(
            f"/conversations/{conversation}/messages", json={"content": "今天工作让我很紧张"}
        ).json()["id"]
        draft = owner.post(f"/conversations/{conversation}/plan-draft", json={}).json()
        renamed = owner.patch(
            f"/conversations/{conversation}", json={"title": "周五的工作压力"}
        )
        self.assertEqual(renamed.json()["title"], "周五的工作压力")
        self.assertEqual(
            [item["id"] for item in owner.get("/conversations?q=周五").json()["items"]],
            [conversation],
        )
        self.assertEqual(
            stranger.patch(f"/conversations/{conversation}", json={"title": "越权"}).status_code,
            404,
        )
        deleted = owner.delete(f"/conversations/{conversation}")
        self.assertEqual(deleted.status_code, 200)
        self.assertEqual(owner.get(f"/conversations/{conversation}").status_code, 404)
        self.assertEqual(
            owner.get("/conversations?include_deleted=true").json()["items"][0]["id"],
            conversation,
        )
        self.assertEqual(owner.post(f"/conversations/{conversation}/restore").status_code, 200)
        owner.delete(f"/conversations/{conversation}")
        with closing(sqlite3.connect(self.settings.database_path)) as conn:
            conn.execute(
                "UPDATE conversations SET purge_at=0 WHERE id=?", (conversation,)
            )
            conn.commit()
        owner.get("/conversations?include_deleted=true")
        with closing(sqlite3.connect(self.settings.database_path)) as conn:
            self.assertIsNone(
                conn.execute(
                    "SELECT 1 FROM plan_drafts WHERE id=?", (draft["id"],)
                ).fetchone()
            )
            self.assertIsNone(
                conn.execute("SELECT content FROM messages WHERE id=?", (message,)).fetchone()
            )

    def test_plan_draft_updates_in_place_and_worker_receives_full_context(self):
        user = self.create_user_client("draft@example.com")
        conversation = user.post("/conversations", json={"title": "倾诉"}).json()["id"]
        first = user.post(
            f"/conversations/{conversation}/messages", json={"content": "最近工作压力很大"}
        ).json()["id"]
        first_draft = user.post(f"/conversations/{conversation}/plan-draft", json={}).json()
        self.assertEqual(first_draft["primary_emotion"], "焦虑")
        user.patch(
            f"/conversations/{conversation}/plan-draft",
            json={
                "language_density": "less_language", "duration_minutes": 10,
                "guidance_style": "温柔陪伴",
            },
        )
        second = user.post(
            f"/conversations/{conversation}/messages",
            json={"content": "我说完了，希望最后更有自信"},
        ).json()["id"]
        refreshed = user.post(f"/conversations/{conversation}/plan-draft", json={}).json()
        self.assertEqual(refreshed["id"], first_draft["id"])
        detail = user.get(f"/conversations/{conversation}").json()
        self.assertEqual(detail["draft"]["id"], first_draft["id"])
        plan_payload = {
            "message_id": second,
            "draft_id": refreshed["id"],
            "duration_minutes": refreshed["duration_minutes"],
            "music_source": refreshed["music_source"],
            "target_emotion": refreshed["target_emotion"],
            "credential_mode": "platform",
            "voice_mode": refreshed["voice_mode"],
            "guidance_style": "温柔陪伴",
            "language_density": "less_language",
        }
        plan_response = user.post(
            f"/conversations/{conversation}/plans", json=plan_payload
        ).json()
        plan = plan_response["id"]
        repeated = user.post(
            f"/conversations/{conversation}/plans", json=plan_payload
        ).json()
        self.assertEqual(repeated["id"], plan)
        self.assertTrue(repeated["idempotent_replay"])
        self.assertEqual(
            user.patch(
                f"/conversations/{conversation}/plan-draft",
                json={"duration_minutes": 15},
            ).status_code,
            409,
        )
        user.post(f"/plans/{plan}/jobs")
        claim = self.client.post("/internal/worker/claim", headers=self.worker_headers()).json()
        self.assertIn("最近工作压力很大", claim["content"])
        self.assertIn("我说完了", claim["content"])
        self.assertEqual(claim["guidance_style"], "温柔陪伴")
        self.assertEqual(claim["language_density"], "less_language")
        self.assertNotEqual(first, second)

    @patch("webapp.app.requests.post")
    def test_plan_draft_uses_deepseek_structured_context(self, post):
        user = self.create_user_client("planner@example.com")
        user.put(
            "/settings/credentials",
            json={"deepseek_api_key": "deepseek-key", "minimax_api_key": "minimax-key"},
        )
        conversation = user.post("/conversations", json={"title": "规划"}).json()["id"]
        user.post(
            f"/conversations/{conversation}/messages", json={"content": "我先说工作的压力"}
        )
        user.post(
            f"/conversations/{conversation}/messages", json={"content": "现在我说完了"}
        )
        response = Mock()
        response.raise_for_status.return_value = None
        response.json.return_value = {
            "choices": [{"message": {"content": json.dumps({
                "summary": "用户表达了工作压力，也确认倾诉完毕。",
                "primary_emotion": "焦虑",
                "emotion_path": "从紧绷走向安定",
                "duration_minutes": 10,
                "music_source": "library",
                "target_emotion": "平静",
                "voice_mode": "tts",
                "guidance_style": "温柔陪伴",
                "language_density": "less_language",
            }, ensure_ascii=False)}}]
        }
        post.return_value = response
        draft = user.post(
            f"/conversations/{conversation}/plan-draft",
            json={"credential_mode": "byok"},
        ).json()
        self.assertEqual(draft["duration_minutes"], 10)
        self.assertEqual(draft["language_density"], "less_language")
        sent_messages = post.call_args.kwargs["json"]["messages"]
        sent_text = json.dumps(sent_messages, ensure_ascii=False)
        self.assertIn("我先说工作的压力", sent_text)
        self.assertIn("现在我说完了", sent_text)

    def test_failed_job_retry_does_not_consume_platform_quota(self):
        user = self.create_user_client("retry@example.com")
        user_id = user.get("/me").json()["id"]
        with closing(sqlite3.connect(self.settings.database_path)) as conn:
            conn.execute("UPDATE users SET daily_limit=1 WHERE id=?", (user_id,))
            conn.commit()
        plan = self.create_plan(user).json()["id"]
        job = user.post(f"/plans/{plan}/jobs").json()["id"]
        self.client.post("/internal/worker/claim", headers=self.worker_headers())
        self.client.post(
            f"/internal/worker/jobs/{job}/fail",
            headers=self.worker_headers(),
            json={"error_code": "provider_unavailable"},
        )
        failed = user.get(f"/jobs/{job}").json()["job"]
        self.assertTrue(failed["retry_allowed"])
        self.assertGreaterEqual(failed["elapsed_seconds"], 0)
        retried = user.post(f"/jobs/{job}/retry")
        self.assertEqual(retried.status_code, 201)
        self.assertEqual(retried.json()["retry_of_job_id"], job)

    @patch("webapp.app.requests.post")
    def test_assistant_reply_streams_and_is_persisted(self, post):
        user = self.create_user_client("stream@example.com")
        user.put(
            "/settings/credentials",
            json={"deepseek_api_key": "deepseek-key", "minimax_api_key": "minimax-key"},
        )
        conversation = user.post("/conversations", json={"title": "流式"}).json()["id"]
        message = user.post(
            f"/conversations/{conversation}/messages", json={"content": "我刚汇报完，有点紧张"}
        ).json()["id"]
        response = Mock()
        response.raise_for_status.return_value = None
        response.iter_lines.return_value = [
            'data: {"choices":[{"delta":{"content":"我听见你"}}]}',
            'data: {"choices":[{"delta":{"content":"还有些紧张。"}}]}',
            "data: [DONE]",
        ]
        post.return_value = response
        streamed = user.post(
            f"/conversations/{conversation}/assistant-stream",
            json={"message_id": message, "credential_mode": "byok"},
        )
        self.assertIn("我听见你", streamed.text)
        restored = user.get(f"/conversations/{conversation}").json()
        self.assertEqual(restored["messages"][-1]["role"], "assistant")
        self.assertEqual(restored["messages"][-1]["content"], "我听见你还有些紧张。")

    def test_worker_token_is_required(self):
        self.assertEqual(self.client.post("/internal/worker/claim").status_code, 401)

    @patch("webapp.worker._export_artifacts")
    @patch("webapp.worker.MeditationApp")
    @patch("webapp.worker.load_config")
    def test_worker_adapts_claim_to_isolated_core_session(self, load_config_mock, app_type, export):
        config = SimpleNamespace(
            api=SimpleNamespace(deepseek_api_key="", minimax_api_key="", elevenlabs_api_key=""),
            paths=SimpleNamespace(base_dir="", cache_dir="", temp_dir=""),
            audio=SimpleNamespace(minimax_voice_id=""),
            create_directories=Mock(),
        )
        load_config_mock.return_value = config
        source = Path(self.temp.name) / "source.wav"
        source.write_bytes(b"wav")
        app_type.return_value.create_meditation_session = AsyncMock(
            return_value=(str(source), {"guidance_text": "引导词"})
        )
        client = Mock()
        client.cancelled.return_value = False
        client.progress.return_value = False
        claim = {
            "id": "job-1",
            "content": "紧张",
            "duration_minutes": 5,
            "music_source": "ai",
            "target_emotion": "自信",
            "credential_mode": "byok",
            "voice_mode": "pure_music",
            "output_path": str(Path(self.temp.name) / "job" / "meditation.wav"),
            "credentials": {
                "deepseek_api_key": "deepseek-key",
                "minimax_api_key": "minimax-key",
                "elevenlabs_api_key": "eleven-key",
            },
        }
        from webapp.worker import run_claim

        run_claim(client, claim)
        kwargs = app_type.return_value.create_meditation_session.await_args.kwargs
        self.assertEqual(kwargs["ai_music_provider"], "minimax")
        self.assertEqual(kwargs["target_emotion"], "自豪")
        self.assertFalse(kwargs["include_guidance"])
        worker_config = app_type.call_args.args[0]
        self.assertEqual(worker_config.audio.minimax_voice_id, "female-chengshu-jingpin")
        self.assertEqual(worker_config.api.elevenlabs_api_key, "eleven-key")
        export.assert_called_once()
        self.assertIn("/complete", client.post.call_args.args[0])


if __name__ == "__main__":
    unittest.main()
