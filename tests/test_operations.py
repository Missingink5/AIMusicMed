from __future__ import annotations

import io
import os
import sqlite3
import tempfile
import unittest
import wave
from contextlib import closing
from pathlib import Path
from unittest.mock import patch

from cryptography.fernet import Fernet
from fastapi.testclient import TestClient

from webapp import Settings, create_app
from webapp.security import token_hash


ADMIN = "admin@example.com"
TOKEN = "worker-token-longer-than-24-characters"
PASSWORD = "correct horse battery staple"


def wav_bytes(seconds: int = 10, rate: int = 8000) -> bytes:
    output = io.BytesIO()
    with wave.open(output, "wb") as target:
        target.setnchannels(1)
        target.setsampwidth(2)
        target.setframerate(rate)
        target.writeframes(b"\x00\x00" * rate * seconds)
    return output.getvalue()


class OperationsTests(unittest.TestCase):
    def setUp(self):
        self.environment = patch.dict(os.environ, {"DEEPSEEK_API_KEY": ""})
        self.environment.start()
        self.temp = tempfile.TemporaryDirectory()
        root = Path(self.temp.name)
        self.settings = Settings(
            database_path=root / "app.db",
            storage_root=root / "storage",
            fernet_key=Fernet.generate_key().decode(),
            worker_token=TOKEN,
            admin_email=ADMIN,
            dev_auth_codes=True,
            secure_cookies=False,
        )
        self.app = create_app(self.settings)
        self.admin = TestClient(self.app)
        self.clients: list[TestClient] = []
        code = self.admin.post("/auth/code/request", json={"email": ADMIN}).json()["verification_code"]
        self.admin.post("/auth/code/verify", json={"email": ADMIN, "code": code, "purpose": "login"})
        self.admin.put("/account/password", json={
            "password": PASSWORD, "password_confirmation": PASSWORD,
        })

    def tearDown(self):
        for client in self.clients:
            client.close()
        self.admin.close()
        self.temp.cleanup()
        self.environment.stop()

    def user(self, email: str) -> TestClient:
        with closing(sqlite3.connect(self.settings.database_path)) as conn:
            conn.execute("DELETE FROM auth_events")
            conn.commit()
        invitation = self.admin.post("/admin/invitations", json={"email": email}).json()
        client = TestClient(self.app)
        self.clients.append(client)
        login = client.post("/auth/code/verify", json={
            "email": email, "code": invitation["verification_code"], "purpose": "login",
        })
        self.assertEqual(login.status_code, 200)
        return client

    def action_token(self, purpose: str) -> str:
        issued = self.admin.post(
            "/admin/sensitive-actions/code/request", json={"action": purpose},
        ).json()
        verified = self.admin.post("/admin/sensitive-actions/code/verify", json={
            "action": purpose, "code": issued["verification_code"],
        })
        self.assertEqual(verified.status_code, 200)
        return verified.json()["action_token"]

    def test_music_upload_requires_declaration_and_preserves_text_audit_after_delete(self):
        user = self.user("music@example.com")
        fields = {
            "name": "calm", "primary_emotion": "平静", "tags": '["睡眠","放松"]',
            "loudness": "auto", "trim_start_ms": "0", "fade_in_ms": "2000",
            "fade_out_ms": "2000",
        }
        denied = user.post(
            "/music-library/tracks", data=fields,
            files={"file": ("../../escape.wav", wav_bytes(11), "audio/wav")},
        )
        self.assertEqual(denied.status_code, 422)
        fields["consent_confirmed"] = "true"
        uploaded = user.post(
            "/music-library/tracks", data=fields,
            files={"file": ("../../escape.wav", wav_bytes(11), "audio/wav")},
        )
        self.assertEqual(uploaded.status_code, 201, uploaded.text)
        item = uploaded.json()["item"]
        stored = list((self.settings.storage_root / "library").rglob("*.wav"))
        self.assertEqual(len(stored), 1)
        self.assertTrue(stored[0].resolve().is_relative_to(self.settings.storage_root.resolve()))
        deleted = user.delete(f"/music-library/tracks/{item['id']}")
        self.assertEqual(deleted.status_code, 204)
        with closing(sqlite3.connect(self.settings.database_path)) as conn:
            row = conn.execute(
                "SELECT declaration_text,ip_hash,original_deleted_at "
                "FROM authorization_declarations WHERE resource_id=?", (item["id"],)
            ).fetchone()
        self.assertIn("合法权利", row[0])
        self.assertNotIn("testclient", row[1])
        self.assertIsNotNone(row[2])

    def test_private_music_is_auto_preferred_and_worker_receives_declared_edits(self):
        user = self.user("selected-music@example.com")
        uploaded = user.post(
            "/music-library/tracks",
            data={
                "name": "晨雾钢琴",
                "primary_emotion": "平静",
                "tags": '["舒缓","钢琴"]',
                "loudness": "light",
                "trim_start_ms": "500",
                "trim_end_ms": "2500",
                "fade_in_ms": "1000",
                "fade_out_ms": "1500",
                "consent_confirmed": "true",
            },
            files={"file": ("morning.wav", wav_bytes(11), "audio/wav")},
        )
        self.assertEqual(uploaded.status_code, 201, uploaded.text)
        asset_id = uploaded.json()["item"]["id"]
        conversation = user.post("/conversations", json={"title": "test"}).json()
        message = user.post(
            f"/conversations/{conversation['id']}/messages",
            json={"content": "我想慢慢平静下来"},
        ).json()
        plan = user.post(
            f"/conversations/{conversation['id']}/plans",
            json={
                "message_id": message["id"],
                "duration_minutes": 3,
                "music_source": "library",
                "target_emotion": "平静",
                "credential_mode": "platform",
                "voice_mode": "pure_music",
            },
        )
        self.assertEqual(plan.status_code, 201, plan.text)
        job = user.post(f"/plans/{plan.json()['id']}/jobs")
        self.assertEqual(job.status_code, 201, job.text)
        claim = self.admin.post(
            "/internal/worker/claim",
            headers={"Authorization": f"Bearer {TOKEN}"},
        )
        self.assertEqual(claim.status_code, 200, claim.text)
        selected = claim.json()["selected_music"]
        self.assertEqual(claim.json()["selected_music_asset_id"], asset_id)
        self.assertEqual(selected["name"], "晨雾钢琴")
        self.assertEqual(selected["primary_emotion"], "平静")
        self.assertEqual(selected["tags"], ["舒缓", "钢琴"])
        self.assertEqual(selected["edit"]["loudness"], "light")
        self.assertTrue(Path(selected["path"]).is_file())

    def test_disguised_audio_is_rejected_and_removed(self):
        user = self.user("fake@example.com")
        response = user.post(
            "/music-library/tracks",
            data={"name": "fake", "primary_emotion": "平静", "tags": "[]",
                  "consent_confirmed": "true"},
            files={"file": ("fake.wav", b"not audio", "audio/wav")},
        )
        self.assertEqual(response.status_code, 415)
        self.assertFalse(list(self.settings.storage_root.rglob("*.upload")))

    def test_voice_clone_is_async_and_worker_business_status_is_checked(self):
        user = self.user("voice@example.com")
        created = user.post(
            "/voices/clone",
            data={"name": "我的声音", "consent_confirmed": "true", "credential_mode": "platform"},
            files={"recording": ("voice.wav", wav_bytes(10), "audio/wav")},
        )
        self.assertEqual(created.status_code, 202, created.text)
        clone_id = created.json()["item"]["id"]
        headers = {"Authorization": f"Bearer {TOKEN}"}
        claimed = self.admin.post("/internal/worker/voice-clones/claim", headers=headers)
        self.assertEqual(claimed.status_code, 200)
        self.assertEqual(claimed.json()["id"], clone_id)
        with closing(sqlite3.connect(self.settings.database_path)) as conn:
            conn.execute(
                "UPDATE voice_clones SET started_at=strftime('%s','now')-7201 WHERE id=?",
                (clone_id,),
            )
            conn.commit()
        reclaimed = self.admin.post("/internal/worker/voice-clones/claim", headers=headers)
        self.assertEqual(reclaimed.status_code, 200)
        self.assertEqual(reclaimed.json()["id"], clone_id)
        failed_business = self.admin.post(
            f"/internal/worker/voice-clones/{clone_id}/complete",
            headers=headers, json={
                "provider_file_id": "file-1", "preview_relpath": "voices/preview.wav",
                "base_resp_status_code": 1001,
            },
        )
        self.assertEqual(failed_business.status_code, 409)
        preview = self.settings.storage_root / "voices" / "preview.wav"
        preview.parent.mkdir(parents=True, exist_ok=True)
        preview.write_bytes(wav_bytes(1))
        completed = self.admin.post(
            f"/internal/worker/voice-clones/{clone_id}/complete",
            headers=headers, json={
                "provider_file_id": "file-1", "preview_relpath": "voices/preview.wav",
                "base_resp_status_code": 0,
            },
        )
        self.assertEqual(completed.status_code, 200)
        self.assertEqual(user.get("/voices").json()["items"][0]["status"], "ready")
        self.assertTrue(user.get("/notifications").json()["items"])
        cleanup = self.admin.post(
            "/internal/worker/provider-voice-actions/claim", headers=headers
        )
        self.assertEqual(cleanup.status_code, 200)
        action_id = cleanup.json()["id"]
        with closing(sqlite3.connect(self.settings.database_path)) as conn:
            conn.execute(
                "UPDATE provider_voice_actions SET started_at=strftime('%s','now')-7201 "
                "WHERE id=?", (action_id,),
            )
            conn.commit()
        reclaimed_cleanup = self.admin.post(
            "/internal/worker/provider-voice-actions/claim", headers=headers
        )
        self.assertEqual(reclaimed_cleanup.status_code, 200)
        self.assertEqual(reclaimed_cleanup.json()["id"], action_id)

    def test_sensitive_token_is_purpose_bound_and_single_use(self):
        user = self.user("quota@example.com")
        user_id = user.get("/me").json()["id"]
        wrong = self.action_token("delete_public_track")
        denied = self.admin.patch(
            f"/admin/users/{user_id}/storage-quota",
            headers={"X-Admin-Action-Token": wrong},
            json={"private_music_count": 2},
        )
        self.assertEqual(denied.status_code, 403)
        token = self.action_token("user_storage_quota")
        changed = self.admin.patch(
            f"/admin/users/{user_id}/storage-quota",
            headers={"X-Admin-Action-Token": token},
            json={"private_music_count": 2},
        )
        self.assertEqual(changed.status_code, 200)
        reused = self.admin.patch(
            f"/admin/users/{user_id}/storage-quota",
            headers={"X-Admin-Action-Token": token},
            json={"private_music_count": 3},
        )
        self.assertEqual(reused.status_code, 403)
        expired = self.action_token("adjust_user_quota")
        with closing(sqlite3.connect(self.settings.database_path)) as conn:
            conn.execute(
                "UPDATE admin_sensitive_grants SET expires_at=0 WHERE token_hash=?",
                (token_hash(expired),),
            )
            conn.commit()
        expired_result = self.admin.patch(
            f"/admin/users/{user_id}/quota",
            headers={"X-Admin-Action-Token": expired},
            json={"daily_limit": 2},
        )
        self.assertEqual(expired_result.status_code, 403)
        self.assertEqual(
            self.admin.patch(
                f"/admin/users/{user_id}/quota", json={"daily_limit": 2}
            ).status_code,
            403,
        )
        self.assertEqual(
            user.post(
                "/admin/sensitive-actions/code/request",
                json={"action": "adjust_user_quota"},
            ).status_code,
            403,
        )

    def test_admin_delete_disable_and_cancel_actions_require_matching_tokens(self):
        user = self.user("admin-actions@example.com")
        user_id = user.get("/me").json()["id"]
        now = 1_700_000_000
        with closing(sqlite3.connect(self.settings.database_path)) as conn:
            conn.execute(
                "INSERT INTO media_assets"
                "(id,owner_user_id,visibility,kind,filename,content_type,size_bytes,duration_seconds,"
                "primary_emotion,status,created_at,updated_at) VALUES"
                "('voice-asset',?,'private','clone_recording','voice.wav','audio/wav',1,10,NULL,"
                "'ready',?,?)", (user_id, now, now),
            )
            conn.execute(
                "INSERT INTO voice_clones"
                "(id,user_id,source_asset_id,name,provider,provider_voice_id,credential_mode,status,"
                "created_at,updated_at) VALUES"
                "('voice-1',?,'voice-asset','voice','minimax','provider-1','platform','ready',?,?)",
                (user_id, now, now),
            )
            conn.execute(
                "INSERT INTO media_assets"
                "(id,owner_user_id,visibility,kind,filename,content_type,size_bytes,duration_seconds,"
                "primary_emotion,status,created_at,updated_at) VALUES"
                "('public-1',?,'public','public_music','public.wav','audio/wav',1,10,'平静',"
                "'ready',?,?)", (user_id, now, now),
            )
            conn.execute(
                "INSERT INTO conversations(id,user_id,title,created_at,updated_at)"
                " VALUES('conversation-1',?,'test',?,?)", (user_id, now, now),
            )
            conn.execute(
                "INSERT INTO messages(id,conversation_id,role,content,created_at)"
                " VALUES('message-1','conversation-1','user','test',?)", (now,),
            )
            conn.execute(
                "INSERT INTO plans(id,conversation_id,message_id,duration_minutes,music_source,"
                "target_emotion,credential_mode,created_at) VALUES"
                "('plan-1','conversation-1','message-1',5,'library','auto','platform',?)", (now,),
            )
            conn.execute(
                "INSERT INTO jobs(id,user_id,plan_id,status,credential_mode,output_relpath,created_at)"
                " VALUES('job-1',?,'plan-1','queued','platform','jobs/job-1.wav',?)",
                (user_id, now),
            )
            conn.execute(
                "INSERT INTO jobs(id,user_id,plan_id,status,credential_mode,output_relpath,created_at)"
                " VALUES('job-2',?,'plan-1','succeeded','platform','jobs/job-2.wav',?)",
                (user_id, now),
            )
            conn.execute(
                "INSERT INTO works(id,job_id,user_id,title,file_relpath,created_at)"
                " VALUES('work-1','job-2',?,'work','jobs/job-2.wav',?)", (user_id, now),
            )
            conn.commit()

        self.assertEqual(self.admin.patch(
            "/admin/voices/voice-1/status", json={"status": "disabled"}
        ).status_code, 403)
        self.assertEqual(self.admin.patch(
            "/admin/voices/voice-1/status",
            headers={"X-Admin-Action-Token": self.action_token("disable_voice")},
            json={"status": "disabled"},
        ).status_code, 204)
        self.assertEqual(self.admin.patch(
            "/admin/voices/voice-1/status",
            headers={"X-Admin-Action-Token": self.action_token("enable_voice")},
            json={"status": "active"},
        ).status_code, 204)
        self.assertEqual(self.admin.delete(
            "/admin/music-library/tracks/public-1",
            headers={"X-Admin-Action-Token": self.action_token("delete_public_track")},
        ).status_code, 204)
        self.assertEqual(self.admin.post(
            "/admin/jobs/job-1/cancel",
            headers={"X-Admin-Action-Token": self.action_token("cancel_job")},
        ).status_code, 204)
        self.assertEqual(self.admin.delete(
            "/admin/works/work-1",
            headers={"X-Admin-Action-Token": self.action_token("delete_work")},
        ).status_code, 204)
        with closing(sqlite3.connect(self.settings.database_path)) as conn:
            actions = {row[0] for row in conn.execute("SELECT action FROM admin_audit_events")}
        self.assertTrue({
            "disable_voice", "enable_voice", "delete_public_track", "cancel_job", "delete_work",
        }.issubset(actions))

    def test_anonymous_stats_hide_groups_under_three_and_respect_opt_out(self):
        users = [self.user(f"stats-{index}@example.com") for index in range(4)]
        for client in users[:2]:
            self.assertEqual(client.post(
                "/analytics/events", json={"event_name": "login_succeeded", "properties": {}},
            ).status_code, 204)
        self.assertEqual(self.admin.get("/admin/stats/anonymous").json()["items"], [])
        users[2].post("/analytics/events", json={"event_name": "login_succeeded", "properties": {}})
        self.assertEqual(len(self.admin.get("/admin/stats/anonymous").json()["items"]), 1)
        users[3].put("/account/analytics", json={"enabled": False})
        users[3].post("/analytics/events", json={"event_name": "generation_started", "properties": {}})
        rows = self.admin.get("/admin/stats/anonymous").json()["items"]
        self.assertEqual([row["event_name"] for row in rows], ["login_succeeded"])
        self.assertEqual(users[0].post(
            "/analytics/events",
            json={"event_name": "generation_failed", "properties": {"content": "private"}},
        ).status_code, 422)
        self.assertEqual(users[0].post(
            "/analytics/events",
            json={"event_name": "generation_failed",
                  "properties": {"error_category": "person@example.com"}},
        ).status_code, 422)
        with closing(sqlite3.connect(self.settings.database_path)) as conn:
            conn.execute(
                "INSERT INTO anonymous_events"
                "(id,event_day,anonymous_id,event_name,properties_json,created_at)"
                " VALUES('old-event','2020-01-01','old-anon','login_succeeded','{}',1)"
            )
            conn.execute(
                "INSERT OR IGNORE INTO anonymous_daily_aggregates"
                "(event_day,event_name,event_count,updated_at)"
                " VALUES('2020-01-01','login_succeeded',5,1)"
            )
            conn.commit()
        users[0].post(
            "/analytics/events",
            json={"event_name": "generation_started", "properties": {"duration_bucket": "3-5m"}},
        )
        with closing(sqlite3.connect(self.settings.database_path)) as conn:
            self.assertEqual(
                conn.execute("SELECT COUNT(*) FROM anonymous_events WHERE id='old-event'").fetchone()[0],
                0,
            )
            self.assertEqual(
                conn.execute(
                    "SELECT event_count FROM anonymous_daily_aggregates "
                    "WHERE event_day='2020-01-01' AND event_name='login_succeeded'"
                ).fetchone()[0],
                5,
            )
        with patch("webapp.operations._now", return_value=1_700_000_000):
            users[0].post(
                "/analytics/events",
                json={"event_name": "generation_completed", "properties": {}},
            )
        with patch("webapp.operations._now", return_value=1_700_086_400):
            users[0].post(
                "/analytics/events",
                json={"event_name": "generation_completed", "properties": {}},
            )
        with closing(sqlite3.connect(self.settings.database_path)) as conn:
            daily_ids = conn.execute(
                "SELECT DISTINCT anonymous_id FROM anonymous_events "
                "WHERE event_name='generation_completed'"
            ).fetchall()
        self.assertEqual(len(daily_ids), 2)


if __name__ == "__main__":
    unittest.main()
