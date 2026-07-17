from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path


SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
  id TEXT PRIMARY KEY, email TEXT NOT NULL UNIQUE, role TEXT NOT NULL DEFAULT 'user',
  status TEXT NOT NULL DEFAULT 'pending', daily_limit INTEGER NOT NULL DEFAULT 10,
  totp_secret TEXT, created_at INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS invitations (
  token_hash TEXT PRIMARY KEY, user_id TEXT NOT NULL REFERENCES users(id),
  expires_at INTEGER NOT NULL, used_at INTEGER
);
CREATE TABLE IF NOT EXISTS magic_links (
  token_hash TEXT PRIMARY KEY, user_id TEXT NOT NULL REFERENCES users(id),
  expires_at INTEGER NOT NULL, used_at INTEGER
);
CREATE TABLE IF NOT EXISTS totp_challenges (
  token_hash TEXT PRIMARY KEY, user_id TEXT NOT NULL REFERENCES users(id),
  expires_at INTEGER NOT NULL, used_at INTEGER, attempts INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS sessions (
  token_hash TEXT PRIMARY KEY, user_id TEXT NOT NULL REFERENCES users(id),
  expires_at INTEGER NOT NULL, created_at INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS auth_throttle (
  id INTEGER PRIMARY KEY AUTOINCREMENT, email_hash TEXT NOT NULL,
  ip_hash TEXT NOT NULL, created_at INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_auth_throttle_time ON auth_throttle(created_at);
CREATE TABLE IF NOT EXISTS verification_codes (
  id TEXT PRIMARY KEY, user_id TEXT NOT NULL REFERENCES users(id), purpose TEXT NOT NULL,
  code_hash TEXT NOT NULL, expires_at INTEGER NOT NULL, used_at INTEGER,
  attempts INTEGER NOT NULL DEFAULT 0, created_at INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_verification_codes_user ON verification_codes(user_id,purpose,created_at);
CREATE TABLE IF NOT EXISTS password_reset_tokens (
  token_hash TEXT PRIMARY KEY, user_id TEXT NOT NULL REFERENCES users(id),
  expires_at INTEGER NOT NULL, used_at INTEGER, created_at INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS auth_events (
  id INTEGER PRIMARY KEY AUTOINCREMENT, kind TEXT NOT NULL, email_hash TEXT NOT NULL,
  ip_hash TEXT NOT NULL, created_at INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_auth_events_time ON auth_events(kind,created_at);
CREATE TABLE IF NOT EXISTS schema_migrations (
  name TEXT PRIMARY KEY, applied_at INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS conversations (
  id TEXT PRIMARY KEY, user_id TEXT NOT NULL REFERENCES users(id), title TEXT NOT NULL,
  created_at INTEGER NOT NULL, updated_at INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS messages (
  id TEXT PRIMARY KEY, conversation_id TEXT NOT NULL REFERENCES conversations(id),
  role TEXT NOT NULL, content TEXT NOT NULL, risk_level TEXT NOT NULL DEFAULT 'normal',
  created_at INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS plan_drafts (
  id TEXT PRIMARY KEY, conversation_id TEXT NOT NULL UNIQUE REFERENCES conversations(id),
  summary TEXT NOT NULL, primary_emotion TEXT NOT NULL, emotion_path TEXT NOT NULL,
  duration_minutes INTEGER NOT NULL, music_source TEXT NOT NULL, target_emotion TEXT NOT NULL,
  credential_mode TEXT NOT NULL, voice_mode TEXT NOT NULL, guidance_style TEXT NOT NULL,
  language_density TEXT NOT NULL, created_at INTEGER NOT NULL, updated_at INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS plans (
  id TEXT PRIMARY KEY, conversation_id TEXT NOT NULL REFERENCES conversations(id),
  message_id TEXT NOT NULL REFERENCES messages(id), duration_minutes INTEGER NOT NULL,
  music_source TEXT NOT NULL, target_emotion TEXT NOT NULL, credential_mode TEXT NOT NULL,
  voice_mode TEXT NOT NULL DEFAULT 'tts',
  status TEXT NOT NULL DEFAULT 'pending', created_at INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS credentials (
  user_id TEXT PRIMARY KEY REFERENCES users(id), deepseek_key TEXT NOT NULL,
  minimax_key TEXT NOT NULL, elevenlabs_key TEXT, updated_at INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS jobs (
  id TEXT PRIMARY KEY, user_id TEXT NOT NULL REFERENCES users(id), plan_id TEXT NOT NULL REFERENCES plans(id),
  status TEXT NOT NULL, credential_mode TEXT NOT NULL, progress_stage TEXT NOT NULL DEFAULT 'queued',
  output_relpath TEXT NOT NULL, created_at INTEGER NOT NULL, started_at INTEGER,
  heartbeat_at INTEGER, finished_at INTEGER, error_code TEXT
);
CREATE INDEX IF NOT EXISTS idx_jobs_status_created ON jobs(status, created_at);
CREATE INDEX IF NOT EXISTS idx_jobs_user_created ON jobs(user_id, created_at);
CREATE TABLE IF NOT EXISTS job_events (
  id INTEGER PRIMARY KEY AUTOINCREMENT, job_id TEXT NOT NULL REFERENCES jobs(id),
  event_type TEXT NOT NULL, stage TEXT NOT NULL, current INTEGER, total INTEGER,
  message TEXT NOT NULL DEFAULT '', created_at INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS works (
  id TEXT PRIMARY KEY, job_id TEXT NOT NULL UNIQUE REFERENCES jobs(id),
  user_id TEXT NOT NULL REFERENCES users(id), title TEXT NOT NULL,
  file_relpath TEXT NOT NULL, mp3_relpath TEXT, txt_relpath TEXT,
  expires_at INTEGER, is_favorite INTEGER NOT NULL DEFAULT 0, created_at INTEGER NOT NULL,
  deleted_at INTEGER
);
CREATE TABLE IF NOT EXISTS user_storage_limits (
  user_id TEXT PRIMARY KEY REFERENCES users(id),
  private_music_bytes INTEGER NOT NULL DEFAULT 1073741824,
  private_music_count INTEGER NOT NULL DEFAULT 100,
  private_music_file_bytes INTEGER NOT NULL DEFAULT 104857600,
  private_music_duration_seconds INTEGER NOT NULL DEFAULT 1800,
  clone_recording_bytes INTEGER NOT NULL DEFAULT 314572800,
  clone_recording_file_bytes INTEGER NOT NULL DEFAULT 52428800,
  clone_count INTEGER NOT NULL DEFAULT 3,
  clone_attempts_30d INTEGER NOT NULL DEFAULT 3,
  updated_at INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS media_assets (
  id TEXT PRIMARY KEY, owner_user_id TEXT REFERENCES users(id),
  visibility TEXT NOT NULL CHECK(visibility IN ('private','public')),
  kind TEXT NOT NULL CHECK(kind IN ('private_music','clone_recording','public_music')),
  filename TEXT NOT NULL, content_type TEXT NOT NULL, size_bytes INTEGER NOT NULL,
  duration_seconds REAL NOT NULL, storage_relpath TEXT,
  primary_emotion TEXT, edit_params_json TEXT NOT NULL DEFAULT '{}',
  status TEXT NOT NULL DEFAULT 'pending',
  created_at INTEGER NOT NULL, updated_at INTEGER NOT NULL, deleted_at INTEGER
);
CREATE INDEX IF NOT EXISTS idx_media_assets_owner_kind
  ON media_assets(owner_user_id,kind,status,created_at);
CREATE TABLE IF NOT EXISTS media_asset_tags (
  asset_id TEXT NOT NULL REFERENCES media_assets(id) ON DELETE CASCADE,
  tag TEXT NOT NULL, PRIMARY KEY(asset_id,tag)
);
CREATE TABLE IF NOT EXISTS authorization_declarations (
  id TEXT PRIMARY KEY, user_id TEXT NOT NULL REFERENCES users(id),
  resource_type TEXT NOT NULL, resource_id TEXT NOT NULL,
  declaration_version TEXT NOT NULL, declaration_text TEXT NOT NULL,
  accepted_at INTEGER NOT NULL, account_email_hash TEXT NOT NULL,
  ip_hash TEXT NOT NULL, content_hash TEXT NOT NULL,
  original_deleted_at INTEGER
);
CREATE INDEX IF NOT EXISTS idx_authorization_resource
  ON authorization_declarations(resource_type,resource_id,accepted_at);
CREATE TABLE IF NOT EXISTS declaration_requirements (
  user_id TEXT NOT NULL REFERENCES users(id), resource_type TEXT NOT NULL,
  resource_id TEXT NOT NULL, created_at INTEGER NOT NULL, satisfied_at INTEGER,
  PRIMARY KEY(user_id,resource_type,resource_id)
);
CREATE TABLE IF NOT EXISTS voice_clones (
  id TEXT PRIMARY KEY, user_id TEXT NOT NULL REFERENCES users(id),
  source_asset_id TEXT NOT NULL REFERENCES media_assets(id),
  name TEXT NOT NULL,
  provider TEXT NOT NULL DEFAULT 'minimax',
  provider_voice_id TEXT, credential_mode TEXT NOT NULL,
  status TEXT NOT NULL, activated_at INTEGER, provider_expires_at INTEGER,
  created_at INTEGER NOT NULL, updated_at INTEGER NOT NULL,
  started_at INTEGER, provider_file_id TEXT, preview_relpath TEXT,
  disabled_at INTEGER, error_code TEXT
);
CREATE INDEX IF NOT EXISTS idx_voice_clones_user_status
  ON voice_clones(user_id,status,created_at);
CREATE TABLE IF NOT EXISTS voice_clone_attempts (
  id TEXT PRIMARY KEY, user_id TEXT NOT NULL REFERENCES users(id),
  voice_clone_id TEXT REFERENCES voice_clones(id),
  created_at INTEGER NOT NULL, outcome TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS provider_voice_actions (
  id TEXT PRIMARY KEY, voice_clone_id TEXT NOT NULL REFERENCES voice_clones(id),
  action TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'pending',
  attempts INTEGER NOT NULL DEFAULT 0, next_attempt_at INTEGER NOT NULL,
  last_error TEXT, created_at INTEGER NOT NULL, started_at INTEGER, completed_at INTEGER
);
CREATE TABLE IF NOT EXISTS admin_permissions (
  user_id TEXT NOT NULL REFERENCES users(id), permission TEXT NOT NULL,
  granted_at INTEGER NOT NULL, granted_by TEXT REFERENCES users(id),
  PRIMARY KEY(user_id,permission)
);
CREATE TABLE IF NOT EXISTS admin_sensitive_grants (
  token_hash TEXT PRIMARY KEY, user_id TEXT NOT NULL REFERENCES users(id),
  purpose TEXT NOT NULL, expires_at INTEGER NOT NULL, used_at INTEGER,
  created_at INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS admin_audit_events (
  id TEXT PRIMARY KEY, actor_user_id TEXT NOT NULL REFERENCES users(id),
  action TEXT NOT NULL, target_type TEXT NOT NULL, target_id TEXT,
  detail_json TEXT NOT NULL DEFAULT '{}', ip_hash TEXT NOT NULL,
  created_at INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS anonymous_events (
  id TEXT PRIMARY KEY, event_day TEXT NOT NULL, anonymous_id TEXT NOT NULL,
  event_name TEXT NOT NULL, properties_json TEXT NOT NULL DEFAULT '{}',
  created_at INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_anonymous_events_day_name
  ON anonymous_events(event_day,event_name,created_at);
CREATE TABLE IF NOT EXISTS anonymous_daily_aggregates (
  event_day TEXT NOT NULL, event_name TEXT NOT NULL,
  event_count INTEGER NOT NULL DEFAULT 0, updated_at INTEGER NOT NULL,
  PRIMARY KEY(event_day,event_name)
);
CREATE TABLE IF NOT EXISTS anonymous_daily_subjects (
  event_day TEXT NOT NULL, event_name TEXT NOT NULL, anonymous_id TEXT NOT NULL,
  PRIMARY KEY(event_day,event_name,anonymous_id)
);
CREATE TABLE IF NOT EXISTS operations_settings (
  key TEXT PRIMARY KEY, value TEXT NOT NULL, updated_at INTEGER NOT NULL,
  updated_by TEXT REFERENCES users(id)
);
CREATE TABLE IF NOT EXISTS notifications (
  id TEXT PRIMARY KEY, user_id TEXT NOT NULL REFERENCES users(id),
  title TEXT NOT NULL, body TEXT NOT NULL,
  kind TEXT NOT NULL CHECK(kind IN ('info','success','warning')),
  dedupe_key TEXT, read_at INTEGER, created_at INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_notifications_user_created
  ON notifications(user_id,created_at DESC);
"""


class Database:
    def __init__(self, path: Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path, timeout=10, isolation_level=None)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys=ON")
        conn.execute("PRAGMA busy_timeout=10000")
        return conn

    def initialize(self) -> None:
        with self.connection() as conn:
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA synchronous=NORMAL")
            conn.executescript(SCHEMA)
            self._add_column(conn, "plans", "voice_mode", "TEXT NOT NULL DEFAULT 'tts'")
            self._add_column(conn, "works", "mp3_relpath", "TEXT")
            self._add_column(conn, "works", "txt_relpath", "TEXT")
            self._add_column(conn, "works", "expires_at", "INTEGER")
            self._add_column(conn, "works", "is_favorite", "INTEGER NOT NULL DEFAULT 0")
            self._add_column(conn, "works", "deleted_at", "INTEGER")
            self._add_column(conn, "users", "password_hash", "TEXT")
            self._add_column(conn, "users", "password_failed_attempts", "INTEGER NOT NULL DEFAULT 0")
            self._add_column(conn, "users", "password_locked_until", "INTEGER")
            self._add_column(conn, "users", "activated_at", "INTEGER")
            self._add_column(conn, "users", "analytics_opt_out", "INTEGER NOT NULL DEFAULT 0")
            self._add_column(conn, "conversations", "deleted_at", "INTEGER")
            self._add_column(conn, "conversations", "purge_at", "INTEGER")
            self._add_column(conn, "conversations", "purged_at", "INTEGER")
            self._add_column(conn, "jobs", "retry_of_job_id", "TEXT")
            self._add_column(conn, "plans", "guidance_style", "TEXT NOT NULL DEFAULT 'gentle'")
            self._add_column(conn, "plans", "language_density", "TEXT NOT NULL DEFAULT 'balanced'")
            self._add_column(conn, "plans", "draft_id", "TEXT")
            self._add_column(conn, "plan_drafts", "locked_at", "INTEGER")
            self._add_column(conn, "plan_drafts", "source_job_id", "TEXT")
            self._add_column(conn, "plan_drafts", "selected_voice_id", "TEXT")
            self._add_column(conn, "plan_drafts", "selected_music_asset_id", "TEXT")
            self._add_column(conn, "plans", "selected_voice_id", "TEXT")
            self._add_column(conn, "plans", "selected_music_asset_id", "TEXT")
            self._add_column(conn, "jobs", "selected_voice_id", "TEXT")
            self._add_column(conn, "jobs", "selected_music_asset_id", "TEXT")
            self._add_column(conn, "provider_voice_actions", "started_at", "INTEGER")
            self._add_column(conn, "voice_clones", "started_at", "INTEGER")
            self._add_column(conn, "voice_clones", "provider_file_id", "TEXT")
            self._add_column(conn, "voice_clones", "preview_relpath", "TEXT")
            self._add_column(conn, "voice_clones", "name", "TEXT NOT NULL DEFAULT '我的音色'")
            conn.execute(
                "CREATE UNIQUE INDEX IF NOT EXISTS idx_plans_draft_id "
                "ON plans(draft_id) WHERE draft_id IS NOT NULL"
            )
            self._apply_auth_v2_cutover(conn)
            self._apply_operations_v1(conn)

    @staticmethod
    def _apply_auth_v2_cutover(conn: sqlite3.Connection) -> None:
        migration = "20260716_auth_v2"
        if conn.execute("SELECT 1 FROM schema_migrations WHERE name=?", (migration,)).fetchone():
            return
        # The V2 release deliberately invalidates all legacy authentication artifacts.
        for table in ("sessions", "magic_links", "invitations", "totp_challenges"):
            conn.execute(f"DELETE FROM {table}")
        conn.execute("INSERT INTO schema_migrations(name,applied_at) VALUES(?,strftime('%s','now'))", (migration,))

    @staticmethod
    def _apply_operations_v1(conn: sqlite3.Connection) -> None:
        migration = "20260717_operations_v1"
        if conn.execute("SELECT 1 FROM schema_migrations WHERE name=?", (migration,)).fetchone():
            return
        now = int(conn.execute("SELECT strftime('%s','now')").fetchone()[0])
        conn.execute(
            "INSERT OR IGNORE INTO user_storage_limits(user_id,updated_at) "
            "SELECT id,? FROM users",
            (now,),
        )
        conn.execute(
            "INSERT INTO schema_migrations(name,applied_at) VALUES(?,?)",
            (migration, now),
        )

    @staticmethod
    def _add_column(conn: sqlite3.Connection, table: str, column: str, definition: str) -> None:
        existing = {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}
        if column not in existing:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")

    @staticmethod
    def purge_expired_conversations(conn: sqlite3.Connection, now: int) -> int:
        due = conn.execute(
            "SELECT id FROM conversations WHERE purged_at IS NULL AND purge_at IS NOT NULL AND purge_at<=?",
            (now,),
        ).fetchall()
        for item in due:
            conversation_id = item["id"]
            conn.execute("DELETE FROM plan_drafts WHERE conversation_id=?", (conversation_id,))
            conn.execute(
                "DELETE FROM messages WHERE conversation_id=? AND id NOT IN "
                "(SELECT message_id FROM plans WHERE conversation_id=?)",
                (conversation_id, conversation_id),
            )
            # A plan's anchor message is retained only to satisfy immutable FK history; its text is destroyed.
            conn.execute(
                "UPDATE messages SET content='[聊天记录已永久删除]' WHERE conversation_id=?",
                (conversation_id,),
            )
            conn.execute(
                "UPDATE conversations SET title='[已删除的会话]',purged_at=? WHERE id=?",
                (now, conversation_id),
            )
        return len(due)

    @contextmanager
    def connection(self):
        conn = self.connect()
        try:
            yield conn
        finally:
            conn.close()

    @contextmanager
    def transaction(self, immediate: bool = False):
        conn = self.connect()
        try:
            conn.execute("BEGIN IMMEDIATE" if immediate else "BEGIN")
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()
