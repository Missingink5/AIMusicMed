from __future__ import annotations

import hashlib
import hmac
import json
import os
import re
import shutil
import sqlite3
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Literal

import soundfile
from fastapi import APIRouter, Depends, File, Form, Header, Request, UploadFile
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel, Field

from .security import new_token, token_hash, verification_code, verification_code_hash
from .storage_guard import storage_status


MIB = 1024 * 1024
DECLARATION_VERSION = "2026-07-17"
MUSIC_DECLARATION = "我声明拥有上传并处理该音乐所需的合法权利，并承担由此产生的责任。"
VOICE_DECLARATION = "我声明该录音为本人声音或已取得声音权利人的明确授权，并同意用于音色克隆。"
ALLOWED_MUSIC_SUFFIXES = {".wav", ".mp3", ".m4a", ".flac"}
MINIMAX_CLONE_SUFFIXES = {".wav", ".mp3", ".m4a"}
SAFE_ANALYTICS_EVENTS = {
    "login_succeeded", "music_uploaded", "voice_clone_requested", "generation_started",
    "generation_completed", "generation_failed", "work_downloaded",
}
SAFE_ANALYTICS_PROPERTIES = {
    "duration_bucket", "credential_mode", "voice_mode", "music_source",
    "status", "error_category",
}
ADMIN_SENSITIVE_ACTIONS = {
    "adjust_user_quota", "change_user_status", "user_storage_quota",
    "disable_voice", "enable_voice", "public_music_create", "delete_public_track",
    "cancel_job", "delete_work", "create_backup", "upload_backup", "verify_backup",
    "restore_backup", "download_backup",
}
BACKUP_PACKAGE_RE = re.compile(
    r"^aimusicmed-(?:offline|upload)-[A-Za-z0-9T-]+-[0-9a-f]{8,64}\.tar\.gz$"
)


class MusicPatch(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    primary_emotion: str | None = Field(default=None, min_length=1, max_length=40)
    tags: list[str] | None = None
    loudness: Literal["auto", "light", "standard", "strong"] | None = None
    trim_start_ms: int | None = Field(default=None, ge=0)
    trim_end_ms: int | None = Field(default=None, ge=0)
    fade_in_ms: int | None = Field(default=None, ge=0, le=60000)
    fade_out_ms: int | None = Field(default=None, ge=0, le=60000)


class StorageQuotaPatch(BaseModel):
    private_music_bytes: int | None = Field(default=None, ge=0)
    private_music_count: int | None = Field(default=None, ge=0)
    private_music_file_bytes: int | None = Field(default=None, ge=1)
    private_music_duration_seconds: int | None = Field(default=None, ge=1)
    clone_recording_bytes: int | None = Field(default=None, ge=0)
    clone_recording_file_bytes: int | None = Field(default=None, ge=1)
    clone_count: int | None = Field(default=None, ge=0)
    clone_attempts_30d: int | None = Field(default=None, ge=0)


class AdminVoiceStatusInput(BaseModel):
    status: Literal["active", "disabled"]


class DeclarationInput(BaseModel):
    resource_type: Literal["work", "music", "voice"]
    resource_id: str
    declaration_version: str = Field(default=DECLARATION_VERSION, min_length=1, max_length=40)
    declaration_text: str = Field(min_length=20, max_length=2000)
    accepted: bool


class SensitiveActionInput(BaseModel):
    action: str = Field(min_length=1, max_length=100)


class SensitiveVerifyInput(SensitiveActionInput):
    code: str = Field(pattern=r"^\d{6}$")


class AnalyticsInput(BaseModel):
    event_name: str = Field(min_length=1, max_length=80)
    properties: dict[str, str | int | float | bool] = Field(default_factory=dict)


class AnalyticsPreference(BaseModel):
    enabled: bool


class CloneCompleteInput(BaseModel):
    provider_file_id: str | None = Field(default=None, max_length=200)
    preview_relpath: str = Field(min_length=1, max_length=500)
    base_resp_status_code: int


class CloneFailInput(BaseModel):
    error_code: str = Field(min_length=1, max_length=100)
    category: Literal["user_input", "provider_rejected", "provider_network", "platform"]
    base_resp_status_code: int | None = None


class ProviderActionCompleteInput(BaseModel):
    base_resp_status_code: int
    error_message: str | None = Field(default=None, max_length=500)


def _now() -> int:
    return int(time.time())


def _id() -> str:
    return uuid.uuid4().hex


def _json(value) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True)


def _disk_status(settings) -> dict[str, int | str]:
    return storage_status(settings)


def _audio_duration(path: Path) -> float:
    try:
        return float(soundfile.info(str(path)).duration)
    except (RuntimeError, ValueError):
        try:
            import librosa
            return float(librosa.get_duration(path=str(path)))
        except Exception:
            return 0.0


def _safe_storage_path(root: Path, relative: str) -> Path | None:
    root = root.resolve()
    candidate = (root / relative).resolve()
    try:
        candidate.relative_to(root)
    except ValueError:
        return None
    return candidate


def _backup_root() -> Path:
    return Path(os.environ.get("AIMUSICMED_BACKUPS_ROOT", "/backups")).resolve()


def _safe_backup_package(root: Path, filename: str) -> Path | None:
    if not BACKUP_PACKAGE_RE.fullmatch(filename):
        return None
    for directory in ("offline", "uploads"):
        candidate = (root / directory / filename).resolve()
        try:
            candidate.relative_to((root / directory).resolve())
        except ValueError:
            continue
        if candidate.is_file():
            return candidate
    return None


def _write_json_atomic(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".partial")
    with temporary.open("x", encoding="utf-8") as target:
        json.dump(value, target, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
        target.flush()
        os.fsync(target.fileno())
    os.replace(temporary, path)


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        while chunk := source.read(MIB):
            digest.update(chunk)
    return digest.hexdigest()


def _audio_signature_matches(path: Path, suffix: str) -> bool:
    with path.open("rb") as source:
        head = source.read(16)
    if suffix == ".wav":
        return head[:4] == b"RIFF" and head[8:12] == b"WAVE"
    if suffix == ".flac":
        return head[:4] == b"fLaC"
    if suffix == ".m4a":
        return len(head) >= 12 and head[4:8] == b"ftyp"
    if suffix == ".mp3":
        return head[:3] == b"ID3" or (len(head) >= 2 and head[0] == 0xFF and head[1] & 0xE0 == 0xE0)
    return False


def consume_admin_action_token(conn, admin, token: str | None, purpose: str, error) -> None:
    if not token:
        raise error("admin_action_verification_required", "需要15分钟邮箱验证码授权", 403)
    now = _now()
    grant = conn.execute(
        "SELECT 1 FROM admin_sensitive_grants WHERE token_hash=? AND user_id=? AND purpose=? "
        "AND used_at IS NULL AND expires_at>?",
        (token_hash(token), admin["id"], purpose, now),
    ).fetchone()
    if not grant:
        raise error("invalid_admin_action_token", "管理操作授权无效、已用或已过期", 403)
    changed = conn.execute(
        "UPDATE admin_sensitive_grants SET used_at=? WHERE token_hash=? AND used_at IS NULL",
        (now, token_hash(token)),
    ).rowcount
    if changed != 1:
        raise error("invalid_admin_action_token", "管理操作授权已被使用", 403)


def record_admin_audit(conn, request: Request, admin, settings, action: str,
                       target_type: str, target_id: str | None, detail=None) -> None:
    ip = request.client.host if request.client else "unknown"
    conn.execute(
        "INSERT INTO admin_audit_events"
        "(id,actor_user_id,action,target_type,target_id,detail_json,ip_hash,created_at)"
        " VALUES(?,?,?,?,?,?,?,?)",
        (_id(), admin["id"], action, target_type, target_id, _json(detail or {}),
         hmac.new(settings.worker_token.encode(), ip.encode(), hashlib.sha256).hexdigest(), _now()),
    )


async def _stream_upload(upload: UploadFile, destination: Path, max_bytes: int, error) -> tuple[int, str]:
    declared = getattr(upload, "size", None)
    if declared is not None and declared > max_bytes:
        raise error("file_too_large", "文件超过单文件上限", 413)
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(destination.suffix + ".upload")
    total = 0
    digest = hashlib.sha256()
    try:
        with temporary.open("xb") as target:
            while chunk := await upload.read(MIB):
                total += len(chunk)
                if total > max_bytes:
                    raise error("file_too_large", "文件超过单文件上限", 413)
                digest.update(chunk)
                target.write(chunk)
        if total == 0:
            raise error("empty_file", "文件不能为空", 422)
        os.replace(temporary, destination)
        return total, digest.hexdigest()
    finally:
        await upload.close()
        if temporary.exists():
            temporary.unlink()


def create_operations_router(
    *,
    db,
    settings,
    current_user: Callable,
    admin_user: Callable,
    worker_auth: Callable,
    send_email: Callable,
    admin_alert: Callable,
    secrets,
    error,
) -> APIRouter:
    router = APIRouter()

    def ensure_limits(conn: sqlite3.Connection, user_id: str):
        conn.execute(
            "INSERT OR IGNORE INTO user_storage_limits(user_id,updated_at) VALUES(?,?)",
            (user_id, _now()),
        )
        return conn.execute("SELECT * FROM user_storage_limits WHERE user_id=?", (user_id,)).fetchone()

    def notify(conn, user_id: str, title: str, body: str, kind: str, dedupe_key: str | None = None):
        if dedupe_key and conn.execute(
            "SELECT 1 FROM notifications WHERE user_id=? AND dedupe_key=? AND created_at>?",
            (user_id, dedupe_key, _now() - 6 * 3600),
        ).fetchone():
            return
        conn.execute(
            "INSERT INTO notifications(id,user_id,title,body,kind,dedupe_key,created_at)"
            " VALUES(?,?,?,?,?,?,?)",
            (_id(), user_id, title, body, kind, dedupe_key, _now()),
        )

    def consume_action_token(conn, admin, token: str | None, purpose: str):
        consume_admin_action_token(conn, admin, token, purpose, error)

    def audit(conn, request: Request, admin, action: str, target_type: str, target_id: str | None, detail=None):
        record_admin_audit(conn, request, admin, settings, action, target_type, target_id, detail)

    def enqueue_backup_request(action: str, admin_id: str, package_id: str | None = None) -> dict:
        root = _backup_root()
        request_id, now = _id(), _now()
        payload = {
            "schema": 1,
            "id": request_id,
            "action": action,
            "requested_by": admin_id,
            "package_id": package_id,
            "created_at": now,
        }
        _write_json_atomic(root / "requests" / "pending" / f"{request_id}.json", payload)
        return {**payload, "status": "pending"}

    def backup_records() -> list[dict]:
        root = _backup_root()
        records: list[dict] = []
        offline = root / "offline"
        if offline.is_dir():
            for package in sorted(offline.glob("*.tar.gz"), key=lambda item: item.stat().st_mtime,
                                  reverse=True):
                if not BACKUP_PACKAGE_RE.fullmatch(package.name):
                    continue
                checksum = package.with_name(f"{package.name}.sha256")
                records.append({
                    "id": package.name,
                    "kind": "package",
                    "status": "ready" if checksum.is_file() else "incomplete",
                    "size_bytes": package.stat().st_size,
                    "created_at": int(package.stat().st_mtime),
                    "downloadable": checksum.is_file(),
                })
        request_root = root / "requests"
        for state in ("pending", "working", "completed", "failed"):
            directory = request_root / state
            if not directory.is_dir():
                continue
            for record in directory.glob("*.json"):
                try:
                    payload = json.loads(record.read_text(encoding="utf-8"))
                except (OSError, json.JSONDecodeError):
                    continue
                if payload.get("id") != record.stem:
                    continue
                records.append({
                    "id": payload["id"],
                    "kind": "request",
                    "action": payload.get("action"),
                    "status": state,
                    "package_id": payload.get("package_id") or payload.get("result_package"),
                    "created_at": payload.get("created_at"),
                    "finished_at": payload.get("finished_at"),
                    "error": payload.get("error") if state == "failed" else None,
                })
        return sorted(records, key=lambda item: int(item.get("created_at") or 0), reverse=True)

    def declaration(
        conn, request: Request, user, resource_type: str, resource_id: str,
        text: str, content_hash: str,
    ) -> int:
        now = _now()
        ip = request.client.host if request.client else "unknown"
        secret = settings.worker_token.encode()
        conn.execute(
            "INSERT INTO authorization_declarations"
            "(id,user_id,resource_type,resource_id,declaration_version,declaration_text,"
            "accepted_at,account_email_hash,ip_hash,content_hash) VALUES(?,?,?,?,?,?,?,?,?,?)",
            (
                _id(), user["id"], resource_type, resource_id, DECLARATION_VERSION, text, now,
                hmac.new(secret, user["email"].encode(), hashlib.sha256).hexdigest(),
                hmac.new(secret, ip.encode(), hashlib.sha256).hexdigest(), content_hash,
            ),
        )
        conn.execute(
            "UPDATE declaration_requirements SET satisfied_at=? "
            "WHERE user_id=? AND resource_type=? AND resource_id=?",
            (now, user["id"], resource_type, resource_id),
        )
        return now

    def serialize_music(conn, row) -> dict:
        edit = json.loads(row["edit_params_json"] or "{}")
        tags = [r[0] for r in conn.execute(
            "SELECT tag FROM media_asset_tags WHERE asset_id=? ORDER BY tag", (row["id"],)
        )]
        return {
            "id": row["id"], "name": row["filename"], "scope": row["visibility"],
            "primary_emotion": row["primary_emotion"], "tags": tags,
            "loudness": edit.get("loudness", "auto"),
            "trim_start_ms": edit.get("trim_start_ms", 0),
            "trim_end_ms": edit.get("trim_end_ms"),
            "fade_in_ms": edit.get("fade_in_ms", 2000),
            "fade_out_ms": edit.get("fade_out_ms", 2000),
            "duration_ms": round(row["duration_seconds"] * 1000),
            "created_at": row["created_at"],
        }

    @router.get("/assets/quota")
    def asset_quota(user=Depends(current_user)):
        cutoff = _now() - 30 * 86400
        with db.transaction(immediate=True) as conn:
            limits = ensure_limits(conn, user["id"])
            music = conn.execute(
                "SELECT COALESCE(SUM(size_bytes),0),COUNT(*) FROM media_assets "
                "WHERE owner_user_id=? AND kind='private_music' AND deleted_at IS NULL",
                (user["id"],),
            ).fetchone()
            voices = conn.execute(
                "SELECT COUNT(*) FROM voice_clones WHERE user_id=? AND disabled_at IS NULL "
                "AND status IN ('processing','ready')", (user["id"],)
            ).fetchone()[0]
            attempts = conn.execute(
                "SELECT COUNT(*) FROM voice_clone_attempts WHERE user_id=? AND created_at>=?",
                (user["id"], cutoff),
            ).fetchone()[0]
        return {
            "voice_slots_used": voices, "voice_slots_limit": limits["clone_count"],
            "clone_requests_used_30d": attempts,
            "clone_requests_limit_30d": limits["clone_attempts_30d"],
            "private_music_bytes_used": music[0],
            "private_music_bytes_limit": limits["private_music_bytes"],
            "private_music_tracks_used": music[1],
            "private_music_tracks_limit": limits["private_music_count"],
        }

    @router.get("/music-library")
    def list_music(scope: Literal["private", "public"] = "private", user=Depends(current_user)):
        with db.connection() as conn:
            if scope == "private":
                rows = conn.execute(
                    "SELECT * FROM media_assets WHERE owner_user_id=? AND kind='private_music' "
                    "AND deleted_at IS NULL ORDER BY created_at DESC", (user["id"],)
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM media_assets WHERE visibility='public' AND kind='public_music' "
                    "AND deleted_at IS NULL ORDER BY created_at DESC"
                ).fetchall()
            return {"items": [serialize_music(conn, row) for row in rows]}

    @router.post("/music-library/tracks", status_code=201)
    async def upload_music(
        request: Request, file: UploadFile = File(...), name: str = Form(...),
        primary_emotion: str = Form(...), tags: str = Form("[]"),
        loudness: str = Form("auto"), trim_start_ms: int = Form(0),
        trim_end_ms: int | None = Form(None), fade_in_ms: int = Form(2000),
        fade_out_ms: int = Form(2000), consent_confirmed: bool = Form(...),
        user=Depends(current_user),
    ):
        if not consent_confirmed:
            raise error("music_consent_required", "必须确认音乐授权声明", 422)
        if loudness not in ("auto", "light", "standard", "strong"):
            raise error("invalid_loudness", "响度参数无效", 422)
        disk = _disk_status(settings)
        if not disk["uploads_allowed"]:
            admin_alert(
                "disk_upload_stop",
                "磁盘保护已停止上传",
                "磁盘使用率达到 85% 或仍处于保护状态；低于 75% 后自动恢复。",
            )
            raise error("storage_protected", "存储空间不足，暂时停止上传", 507)
        suffix = Path(file.filename or "").suffix.lower()
        if suffix not in ALLOWED_MUSIC_SUFFIXES:
            raise error("unsupported_audio_type", "不支持的音频格式", 415)
        try:
            parsed_tags = json.loads(tags)
        except json.JSONDecodeError as exc:
            raise error("invalid_tags", "标签格式无效", 422) from exc
        if not isinstance(parsed_tags, list) or len(parsed_tags) > 20:
            raise error("invalid_tags", "标签最多20个", 422)
        clean_tags = sorted({str(item).strip()[:40] for item in parsed_tags if str(item).strip()})
        asset_id, now = _id(), _now()
        with db.transaction(immediate=True) as conn:
            limits = ensure_limits(conn, user["id"])
            usage = conn.execute(
                "SELECT COALESCE(SUM(size_bytes),0),COUNT(*) FROM media_assets "
                "WHERE owner_user_id=? AND kind='private_music' AND deleted_at IS NULL",
                (user["id"],),
            ).fetchone()
            if usage[1] >= limits["private_music_count"]:
                raise error("music_count_quota_exceeded", "私人音乐数量已达上限", 409)
            max_file = min(limits["private_music_file_bytes"], limits["private_music_bytes"] - usage[0])
            if max_file <= 0:
                raise error("music_storage_quota_exceeded", "私人音乐空间已用完", 409)
        relpath = f"library/{user['id']}/{asset_id}{suffix}"
        path = settings.storage_root / relpath
        size, digest = await _stream_upload(file, path, int(max_file), error)
        if not _audio_signature_matches(path, suffix):
            path.unlink(missing_ok=True)
            raise error("audio_type_mismatch", "文件内容与扩展名不一致或音频已损坏", 415)
        duration = _audio_duration(path)
        try:
            with db.transaction(immediate=True) as conn:
                limits = ensure_limits(conn, user["id"])
                usage = conn.execute(
                    "SELECT COALESCE(SUM(size_bytes),0),COUNT(*) FROM media_assets "
                    "WHERE owner_user_id=? AND kind='private_music' AND deleted_at IS NULL",
                    (user["id"],),
                ).fetchone()
                if usage[0] + size > limits["private_music_bytes"] or usage[1] >= limits["private_music_count"]:
                    raise error("music_storage_quota_exceeded", "并发上传导致私人音乐额度已满", 409)
                if duration <= 0 or duration > limits["private_music_duration_seconds"]:
                    raise error("music_duration_invalid", "音频无法识别或超过30分钟", 422)
                edit = {
                    "loudness": loudness, "trim_start_ms": trim_start_ms,
                    "trim_end_ms": trim_end_ms, "fade_in_ms": fade_in_ms, "fade_out_ms": fade_out_ms,
                }
                conn.execute(
                    "INSERT INTO media_assets"
                    "(id,owner_user_id,visibility,kind,filename,content_type,size_bytes,duration_seconds,"
                    "storage_relpath,primary_emotion,edit_params_json,status,created_at,updated_at)"
                    " VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    (asset_id, user["id"], "private", "private_music", name[:120],
                     file.content_type or "application/octet-stream", size, duration, relpath,
                     primary_emotion[:40], _json(edit), "ready", now, now),
                )
                conn.executemany(
                    "INSERT INTO media_asset_tags(asset_id,tag) VALUES(?,?)",
                    [(asset_id, tag) for tag in clean_tags],
                )
                declaration(conn, request, user, "music", asset_id, MUSIC_DECLARATION, digest)
                item = serialize_music(conn, conn.execute(
                    "SELECT * FROM media_assets WHERE id=?", (asset_id,)
                ).fetchone())
            return {"item": item}
        except Exception:
            path.unlink(missing_ok=True)
            raise

    @router.patch("/music-library/tracks/{track_id}")
    def update_music(track_id: str, body: MusicPatch, user=Depends(current_user)):
        with db.transaction(immediate=True) as conn:
            row = conn.execute(
                "SELECT * FROM media_assets WHERE id=? AND owner_user_id=? AND kind='private_music' "
                "AND deleted_at IS NULL", (track_id, user["id"])
            ).fetchone()
            if not row:
                raise error("track_not_found", "音乐不存在", 404)
            edit = json.loads(row["edit_params_json"] or "{}")
            values = body.model_dump(exclude_none=True)
            tags = values.pop("tags", None)
            name = values.pop("name", row["filename"])
            emotion = values.pop("primary_emotion", row["primary_emotion"])
            edit.update(values)
            if edit.get("trim_end_ms") is not None and edit["trim_end_ms"] < edit.get("trim_start_ms", 0):
                raise error("invalid_trim", "结束位置不能早于开始位置", 422)
            conn.execute(
                "UPDATE media_assets SET filename=?,primary_emotion=?,edit_params_json=?,updated_at=? WHERE id=?",
                (name, emotion, _json(edit), _now(), track_id),
            )
            if tags is not None:
                conn.execute("DELETE FROM media_asset_tags WHERE asset_id=?", (track_id,))
                conn.executemany(
                    "INSERT INTO media_asset_tags(asset_id,tag) VALUES(?,?)",
                    [(track_id, tag.strip()[:40]) for tag in sorted(set(tags)) if tag.strip()],
                )
            return {"item": serialize_music(conn, conn.execute(
                "SELECT * FROM media_assets WHERE id=?", (track_id,)
            ).fetchone())}

    @router.delete("/music-library/tracks/{track_id}", status_code=204)
    def delete_music(track_id: str, user=Depends(current_user)):
        now = _now()
        with db.transaction(immediate=True) as conn:
            row = conn.execute(
                "SELECT * FROM media_assets WHERE id=? AND owner_user_id=? AND deleted_at IS NULL",
                (track_id, user["id"]),
            ).fetchone()
            if not row:
                raise error("track_not_found", "音乐不存在", 404)
            conn.execute("UPDATE media_assets SET deleted_at=?,status='deleted',updated_at=? WHERE id=?",
                         (now, now, track_id))
            conn.execute(
                "UPDATE authorization_declarations SET original_deleted_at=? "
                "WHERE resource_type='music' AND resource_id=? AND original_deleted_at IS NULL",
                (now, track_id),
            )
            referenced = conn.execute(
                "SELECT 1 FROM jobs WHERE selected_music_asset_id=? "
                "AND status IN ('queued','running','cancel_requested') LIMIT 1",
                (track_id,),
            ).fetchone()
        if row["storage_relpath"] and not referenced:
            path = _safe_storage_path(settings.storage_root, row["storage_relpath"])
            if path:
                path.unlink(missing_ok=True)
        return Response(status_code=204)

    @router.get("/music-library/tracks/{track_id}/audio")
    def music_audio(track_id: str, user=Depends(current_user)):
        with db.connection() as conn:
            row = conn.execute("SELECT * FROM media_assets WHERE id=? AND deleted_at IS NULL", (track_id,)).fetchone()
        if not row or (row["visibility"] != "public" and row["owner_user_id"] != user["id"]):
            raise error("track_not_found", "音乐不存在", 404)
        path = _safe_storage_path(settings.storage_root, row["storage_relpath"])
        if path is None:
            raise error("unsafe_storage_path", "存储路径无效", 500)
        if not path.is_file():
            raise error("audio_missing", "音频文件不存在", 410)
        return FileResponse(path, media_type=row["content_type"], filename=row["filename"])

    @router.get("/voices")
    def list_voices(user=Depends(current_user)):
        with db.connection() as conn:
            rows = conn.execute(
                "SELECT vc.*,ma.storage_relpath,ad.accepted_at FROM voice_clones vc "
                "JOIN media_assets ma ON ma.id=vc.source_asset_id "
                "LEFT JOIN authorization_declarations ad ON ad.resource_type='voice' "
                "AND ad.resource_id=vc.id WHERE vc.user_id=? AND vc.disabled_at IS NULL "
                "ORDER BY vc.created_at DESC", (user["id"],)
            ).fetchall()
        return {"items": [{
            "id": row["id"], "name": row["name"],
            "provider_voice_id": row["provider_voice_id"], "status": row["status"],
            "created_at": row["created_at"],
            "recording_retained": bool(row["storage_relpath"]),
            "consent_recorded_at": row["accepted_at"],
            "provider_expires_at": row["provider_expires_at"],
            "preview_available": bool(row["preview_relpath"]),
        } for row in rows]}

    @router.get("/voices/{voice_id}/preview")
    def voice_preview(voice_id: str, user=Depends(current_user)):
        with db.connection() as conn:
            row = conn.execute(
                "SELECT preview_relpath FROM voice_clones WHERE id=? AND user_id=? "
                "AND status='ready' AND disabled_at IS NULL",
                (voice_id, user["id"]),
            ).fetchone()
        if not row or not row["preview_relpath"]:
            raise error("voice_preview_not_found", "音色试听尚不可用", 404)
        path = _safe_storage_path(settings.storage_root, row["preview_relpath"])
        if path is None or not path.is_file():
            raise error("voice_preview_missing", "音色试听文件不存在", 410)
        return FileResponse(path, media_type="audio/wav")

    @router.post("/voices/clone", status_code=202)
    async def clone_voice(
        request: Request, name: str = Form(...), recording: UploadFile = File(...),
        consent_confirmed: bool = Form(...),
        credential_mode: Literal["platform", "byok"] = Form("platform"),
        user=Depends(current_user),
    ):
        if not consent_confirmed:
            raise error("voice_consent_required", "必须确认声音授权声明", 422)
        disk = _disk_status(settings)
        if not disk["uploads_allowed"]:
            admin_alert(
                "disk_upload_stop",
                "磁盘保护已停止上传",
                "磁盘使用率达到 85% 或仍处于保护状态；低于 75% 后自动恢复。",
            )
            raise error("storage_protected", "存储空间不足，暂时停止克隆录音上传", 507)
        suffix = Path(recording.filename or "").suffix.lower()
        if suffix not in MINIMAX_CLONE_SUFFIXES:
            raise error("unsupported_clone_audio_type", "MiniMax仅接受mp3、m4a或wav", 415)
        now, cutoff = _now(), _now() - 30 * 86400
        clone_id, asset_id = _id(), _id()
        with db.transaction(immediate=True) as conn:
            limits = ensure_limits(conn, user["id"])
            active = conn.execute(
                "SELECT COUNT(*) FROM voice_clones WHERE user_id=? AND disabled_at IS NULL "
                "AND status IN ('processing','ready')", (user["id"],)
            ).fetchone()[0]
            attempts = conn.execute(
                "SELECT COUNT(*) FROM voice_clone_attempts WHERE user_id=? AND created_at>=?",
                (user["id"], cutoff),
            ).fetchone()[0]
            recording_used = conn.execute(
                "SELECT COALESCE(SUM(size_bytes),0) FROM media_assets WHERE owner_user_id=? "
                "AND kind='clone_recording' AND deleted_at IS NULL", (user["id"],)
            ).fetchone()[0]
            if active >= limits["clone_count"]:
                raise error("voice_slot_quota_exceeded", "克隆音色数量已达上限", 409)
            if attempts >= limits["clone_attempts_30d"]:
                raise error("clone_rate_quota_exceeded", "30天内克隆次数已达上限", 429)
            if credential_mode == "byok" and not conn.execute(
                "SELECT 1 FROM credentials WHERE user_id=?", (user["id"],)
            ).fetchone():
                raise error("byok_not_configured", "请先配置MiniMax个人API", 409)
            max_product = min(
                limits["clone_recording_file_bytes"],
                limits["clone_recording_bytes"] - recording_used,
            )
            if max_product <= 0:
                raise error("clone_storage_quota_exceeded", "克隆录音空间已用完", 409)
        # Product storage accepts 50 MiB. The worker prepares a separate <=20 MiB MiniMax copy.
        max_upload = int(max_product)
        relpath = f"voices/{user['id']}/{asset_id}{suffix}"
        path = settings.storage_root / relpath
        size, digest = await _stream_upload(recording, path, max_upload, error)
        if not _audio_signature_matches(path, suffix):
            path.unlink(missing_ok=True)
            raise error("audio_type_mismatch", "文件内容与扩展名不一致或音频已损坏", 415)
        duration = _audio_duration(path)
        try:
            if not 10 <= duration <= 300:
                raise error("clone_duration_invalid", "MiniMax克隆录音必须为10秒到5分钟", 422)
            voice_id = f"aimusicmed_{uuid.uuid4().hex}"
            with db.transaction(immediate=True) as conn:
                conn.execute(
                    "INSERT INTO media_assets"
                    "(id,owner_user_id,visibility,kind,filename,content_type,size_bytes,duration_seconds,"
                    "storage_relpath,primary_emotion,status,created_at,updated_at)"
                    " VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    (asset_id, user["id"], "private", "clone_recording", name[:120],
                     recording.content_type or "application/octet-stream", size, duration, relpath,
                     None, "ready", now, now),
                )
                conn.execute(
                    "INSERT INTO voice_clones"
                    "(id,user_id,source_asset_id,name,provider,provider_voice_id,credential_mode,status,"
                    "provider_expires_at,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                    (clone_id, user["id"], asset_id, name[:120], "minimax", voice_id, credential_mode,
                     "processing", now + 7 * 86400, now, now),
                )
                conn.execute(
                    "INSERT INTO voice_clone_attempts(id,user_id,voice_clone_id,created_at,outcome)"
                    " VALUES(?,?,?,?,?)", (_id(), user["id"], clone_id, now, "accepted"),
                )
                accepted_at = declaration(conn, request, user, "voice", clone_id, VOICE_DECLARATION, digest)
                notify(conn, user["id"], "音色克隆已提交", "关闭页面后仍会继续处理。", "info",
                       f"voice-submitted:{clone_id}")
            return {"item": {
                "id": clone_id, "name": name, "provider_voice_id": voice_id,
                "status": "processing", "created_at": now, "recording_retained": True,
                "consent_recorded_at": accepted_at, "provider_expires_at": now + 7 * 86400,
            }}
        except Exception:
            path.unlink(missing_ok=True)
            raise

    @router.delete("/voices/{voice_id}", status_code=204)
    def delete_voice(voice_id: str, user=Depends(current_user)):
        now = _now()
        with db.transaction(immediate=True) as conn:
            row = conn.execute(
                "SELECT vc.*,ma.storage_relpath FROM voice_clones vc JOIN media_assets ma "
                "ON ma.id=vc.source_asset_id WHERE vc.id=? AND vc.user_id=? AND vc.disabled_at IS NULL",
                (voice_id, user["id"]),
            ).fetchone()
            if not row:
                raise error("voice_not_found", "音色不存在", 404)
            conn.execute(
                "UPDATE voice_clones SET status='disabled',disabled_at=?,updated_at=? WHERE id=?",
                (now, now, voice_id),
            )
            conn.execute(
                "INSERT INTO provider_voice_actions"
                "(id,voice_clone_id,action,status,next_attempt_at,created_at) VALUES(?,?,?,'pending',?,?)",
                (_id(), voice_id, "delete", now, now),
            )
            conn.execute(
                "UPDATE media_assets SET deleted_at=?,status='deleted',storage_relpath=NULL,updated_at=? "
                "WHERE id=?", (now, now, row["source_asset_id"]),
            )
            conn.execute(
                "UPDATE authorization_declarations SET original_deleted_at=? "
                "WHERE resource_type='voice' AND resource_id=? AND original_deleted_at IS NULL",
                (now, voice_id),
            )
        if row["storage_relpath"]:
            path = _safe_storage_path(settings.storage_root, row["storage_relpath"])
            if path:
                path.unlink(missing_ok=True)
        if row["preview_relpath"]:
            preview = _safe_storage_path(settings.storage_root, row["preview_relpath"])
            if preview:
                preview.unlink(missing_ok=True)
        return Response(status_code=204)

    @router.post("/internal/worker/voice-clones/claim", dependencies=[Depends(worker_auth)])
    def claim_voice_clone():
        now = _now()
        with db.transaction(immediate=True) as conn:
            conn.execute(
                "UPDATE voice_clones SET started_at=NULL,updated_at=? "
                "WHERE status='processing' AND started_at IS NOT NULL AND started_at<?",
                (now, now - 2 * 3600),
            )
            row = conn.execute(
                "SELECT vc.*,ma.storage_relpath,ma.content_type,ma.size_bytes,ma.duration_seconds "
                "FROM voice_clones vc JOIN media_assets ma ON ma.id=vc.source_asset_id "
                "WHERE vc.status='processing' AND vc.started_at IS NULL AND vc.disabled_at IS NULL "
                "ORDER BY vc.created_at LIMIT 1"
            ).fetchone()
            if not row:
                return Response(status_code=204)
            changed = conn.execute(
                "UPDATE voice_clones SET started_at=?,updated_at=? "
                "WHERE id=? AND started_at IS NULL AND status='processing'",
                (now, now, row["id"]),
            ).rowcount
            if changed != 1:
                return Response(status_code=204)
            credential = None
            if row["credential_mode"] == "byok":
                credential = conn.execute(
                    "SELECT minimax_key FROM credentials WHERE user_id=?", (row["user_id"],)
                ).fetchone()
        source = _safe_storage_path(settings.storage_root, row["storage_relpath"])
        if source is None or not source.is_file():
            raise error("clone_source_missing", "clone source is missing", 410)
        result = {
            "id": row["id"], "user_id": row["user_id"], "name": row["name"],
            "source_path": str(source), "source_size_bytes": row["size_bytes"],
            "source_duration_seconds": row["duration_seconds"],
            "source_content_type": row["content_type"],
            "provider_voice_id": row["provider_voice_id"],
            "credential_mode": row["credential_mode"],
            "minimax_upload_limit_bytes": 20 * MIB,
            "minimax_duration_min_seconds": 10,
            "minimax_duration_max_seconds": 300,
            "preview_relpath": f"voices/{row['user_id']}/previews/{row['id']}.wav",
        }
        preview = _safe_storage_path(settings.storage_root, result["preview_relpath"])
        if preview is None:
            raise error("unsafe_storage_path", "preview path is invalid", 500)
        preview.parent.mkdir(parents=True, exist_ok=True)
        result["preview_path"] = str(preview)
        if credential:
            result["minimax_api_key"] = secrets.decrypt(credential["minimax_key"])
        return result

    @router.post("/internal/worker/voice-clones/{clone_id}/complete", dependencies=[Depends(worker_auth)])
    def complete_voice_clone(clone_id: str, body: CloneCompleteInput):
        if body.base_resp_status_code != 0:
            raise error("minimax_business_error", "MiniMax业务状态不是成功", 409)
        now = _now()
        with db.transaction(immediate=True) as conn:
            row = conn.execute(
                "SELECT * FROM voice_clones WHERE id=? AND status='processing' AND disabled_at IS NULL",
                (clone_id,),
            ).fetchone()
            if not row:
                raise error("voice_clone_not_active", "voice clone is not active", 409)
            preview = _safe_storage_path(settings.storage_root, body.preview_relpath)
            if preview is None or not preview.is_file():
                raise error("voice_preview_missing", "voice preview is missing", 409)
            conn.execute(
                "UPDATE voice_clones SET status='ready',provider_file_id=?,preview_relpath=?,"
                "activated_at=?,updated_at=? WHERE id=?",
                (body.provider_file_id, body.preview_relpath, now, now, clone_id),
            )
            conn.execute(
                "UPDATE voice_clone_attempts SET outcome='succeeded' WHERE voice_clone_id=?",
                (clone_id,),
            )
            if body.provider_file_id:
                conn.execute(
                    "INSERT INTO provider_voice_actions"
                    "(id,voice_clone_id,action,status,next_attempt_at,created_at)"
                    " VALUES(?,?,?,'pending',?,?)",
                    (_id(), clone_id, "delete_file", now, now),
                )
            notify(conn, row["user_id"], "音色克隆成功", "新音色已经可以选择使用。", "success",
                   f"voice-ready:{clone_id}")
        return {"status": "ready"}

    @router.post("/internal/worker/voice-clones/{clone_id}/fail", dependencies=[Depends(worker_auth)])
    def fail_voice_clone(clone_id: str, body: CloneFailInput):
        now = _now()
        with db.transaction(immediate=True) as conn:
            row = conn.execute(
                "SELECT * FROM voice_clones WHERE id=? AND status='processing'", (clone_id,)
            ).fetchone()
            if not row:
                raise error("voice_clone_not_active", "voice clone is not active", 409)
            conn.execute(
                "UPDATE voice_clones SET status='failed',error_code=?,updated_at=? WHERE id=?",
                (body.error_code, now, clone_id),
            )
            outcome = body.category
            if body.category in ("provider_network", "platform"):
                # Infrastructure failures do not consume the user's 30-day clone allowance.
                conn.execute("DELETE FROM voice_clone_attempts WHERE voice_clone_id=?", (clone_id,))
            else:
                conn.execute(
                    "UPDATE voice_clone_attempts SET outcome=? WHERE voice_clone_id=?",
                    (outcome, clone_id),
                )
            notify(conn, row["user_id"], "音色克隆失败", "录音未能完成克隆，请检查后重试。", "warning",
                   f"voice-failed:{clone_id}")
        if body.category in ("provider_network", "platform"):
            admin_alert(
                f"voice_clone_{body.category}",
                "音色克隆基础设施异常",
                f"音色克隆任务失败，错误代码：{body.error_code}",
            )
        return {"status": "failed", "allowance_consumed": body.category not in ("provider_network", "platform")}

    @router.post("/internal/worker/provider-voice-actions/claim", dependencies=[Depends(worker_auth)])
    def claim_provider_voice_action():
        now = _now()
        with db.transaction(immediate=True) as conn:
            conn.execute(
                "UPDATE provider_voice_actions SET status='pending',next_attempt_at=?,started_at=NULL "
                "WHERE status='running' AND completed_at IS NULL AND started_at<?",
                (now, now - 2 * 3600),
            )
            row = conn.execute(
                "SELECT pva.*,vc.provider_voice_id,vc.provider_file_id,vc.credential_mode,vc.user_id "
                "FROM provider_voice_actions pva JOIN voice_clones vc ON vc.id=pva.voice_clone_id "
                "WHERE pva.status='pending' AND pva.next_attempt_at<=? "
                "AND NOT EXISTS(SELECT 1 FROM jobs j WHERE j.selected_voice_id=vc.id "
                "AND j.status IN ('queued','running','cancel_requested')) "
                "ORDER BY pva.created_at LIMIT 1",
                (now,),
            ).fetchone()
            if not row:
                return Response(status_code=204)
            conn.execute(
                "UPDATE provider_voice_actions SET status='running',attempts=attempts+1,started_at=? "
                "WHERE id=?",
                (now, row["id"]),
            )
            credential = conn.execute(
                "SELECT minimax_key FROM credentials WHERE user_id=?", (row["user_id"],)
            ).fetchone() if row["credential_mode"] == "byok" else None
        result = {
            "id": row["id"], "voice_clone_id": row["voice_clone_id"],
            "action": row["action"], "provider_voice_id": row["provider_voice_id"],
            "provider_file_id": row["provider_file_id"],
            "voice_type": "voice_cloning", "credential_mode": row["credential_mode"],
        }
        if credential:
            result["minimax_api_key"] = secrets.decrypt(credential["minimax_key"])
        return result

    @router.post("/internal/worker/provider-voice-actions/{action_id}/complete",
                 dependencies=[Depends(worker_auth)])
    def complete_provider_voice_action(action_id: str, body: ProviderActionCompleteInput):
        now = _now()
        with db.transaction(immediate=True) as conn:
            row = conn.execute(
                "SELECT * FROM provider_voice_actions WHERE id=? AND status='running'", (action_id,)
            ).fetchone()
            if not row:
                raise error("provider_action_not_active", "provider action is not active", 409)
            if body.base_resp_status_code == 0:
                conn.execute(
                    "UPDATE provider_voice_actions SET status='complete',completed_at=? WHERE id=?",
                    (now, action_id),
                )
                return {"status": "complete"}
            delay = min(86400, 60 * (2 ** min(row["attempts"], 10)))
            conn.execute(
                "UPDATE provider_voice_actions SET status='pending',next_attempt_at=?,last_error=?,"
                "started_at=NULL WHERE id=?",
                (now + delay, body.error_message or str(body.base_resp_status_code), action_id),
            )
        return {"status": "pending", "retry_in_seconds": delay}

    @router.get("/account/declarations/pending")
    def pending_declarations(user=Depends(current_user)):
        with db.connection() as conn:
            rows = conn.execute(
                "SELECT resource_type,resource_id,created_at FROM declaration_requirements "
                "WHERE user_id=? AND satisfied_at IS NULL ORDER BY created_at",
                (user["id"],),
            ).fetchall()
        return {"items": [dict(row) for row in rows], "declaration_version": DECLARATION_VERSION}

    @router.post("/account/declarations", status_code=201)
    def accept_declaration(body: DeclarationInput, request: Request, user=Depends(current_user)):
        if not body.accepted:
            raise error("declaration_required", "必须接受授权声明", 422)
        with db.transaction(immediate=True) as conn:
            required = conn.execute(
                "SELECT 1 FROM declaration_requirements WHERE user_id=? AND resource_type=? AND resource_id=?",
                (user["id"], body.resource_type, body.resource_id),
            ).fetchone()
            if not required:
                raise error("declaration_target_not_found", "待补声明记录不存在", 404)
            accepted_at = declaration(
                conn, request, user, body.resource_type, body.resource_id,
                body.declaration_text, hashlib.sha256(body.declaration_text.encode()).hexdigest(),
            )
        return {"accepted_at": accepted_at, "declaration_version": body.declaration_version}

    @router.post("/admin/sensitive-actions/code/request")
    def sensitive_request(body: SensitiveActionInput, request: Request, admin=Depends(admin_user)):
        if body.action not in ADMIN_SENSITIVE_ACTIONS:
            raise error("invalid_admin_action", "不支持的敏感操作", 422)
        now, code, challenge_id = _now(), verification_code(), _id()
        purpose = f"admin:{body.action}"
        with db.transaction(immediate=True) as conn:
            # Rate-limit OTP requests: at most 1 active challenge per admin+action,
            # and at most 5 requests per admin per 15 minutes to prevent email flooding.
            active_count = conn.execute(
                "SELECT COUNT(*) FROM verification_codes WHERE user_id=? AND purpose=?"
                " AND used_at IS NULL AND expires_at>?",
                (admin["id"], purpose, now),
            ).fetchone()[0]
            if active_count >= 1:
                raise error("otp_request_rate_limited",
                            "该操作的验证码仍然有效，请勿重复请求", 429)
            recent_count = conn.execute(
                "SELECT COUNT(*) FROM verification_codes WHERE user_id=? AND purpose=?"
                " AND created_at>?",
                (admin["id"], purpose, now - 900),
            ).fetchone()[0]
            if recent_count >= 5:
                raise error("otp_request_rate_limited",
                            "验证码请求过于频繁，请稍后再试", 429)
            conn.execute(
                "UPDATE verification_codes SET used_at=? WHERE user_id=? AND purpose=? AND used_at IS NULL",
                (now, admin["id"], purpose),
            )
            conn.execute(
                "INSERT INTO verification_codes(id,user_id,purpose,code_hash,expires_at,created_at)"
                " VALUES(?,?,?,?,?,?)",
                (challenge_id, admin["id"], purpose,
                 verification_code_hash(settings.worker_token, challenge_id, code), now + 900, now),
            )
        send_email(admin["email"], "AIMusicMed 管理操作验证码",
                   action=body.action, expires="15 分钟", code=code)
        result = {"sent": True, "expires_in": 900}
        if settings.dev_auth_codes:
            result["verification_code"] = code
        return result

    @router.post("/admin/sensitive-actions/code/verify")
    def sensitive_verify(body: SensitiveVerifyInput, request: Request, admin=Depends(admin_user)):
        if body.action not in ADMIN_SENSITIVE_ACTIONS:
            raise error("invalid_admin_action", "不支持的敏感操作", 422)
        now = _now()
        purpose = f"admin:{body.action}"
        with db.transaction(immediate=True) as conn:
            # Global verify rate limit: at most 30 verification attempts
            # across all challenges per admin per 15 minutes.
            global_attempts = conn.execute(
                "SELECT COALESCE(SUM(attempts),0) FROM verification_codes "
                "WHERE user_id=? AND created_at>?",
                (admin["id"], now - 900),
            ).fetchone()[0]
            if global_attempts >= 30:
                raise error("otp_verify_rate_limited",
                            "验证尝试过多，请稍后再试", 429)
            challenge = conn.execute(
                "SELECT * FROM verification_codes WHERE user_id=? AND purpose=? AND used_at IS NULL "
                "AND expires_at>? ORDER BY created_at DESC LIMIT 1",
                (admin["id"], purpose, now),
            ).fetchone()
            if not challenge or challenge["attempts"] >= 5 or not hmac.compare_digest(
                verification_code_hash(settings.worker_token, challenge["id"], body.code),
                challenge["code_hash"],
            ):
                if challenge:
                    conn.execute("UPDATE verification_codes SET attempts=attempts+1 WHERE id=?",
                                 (challenge["id"],))
                raise error("invalid_code", "验证码错误或已过期", 401)
            conn.execute("UPDATE verification_codes SET used_at=? WHERE id=?", (now, challenge["id"]))
            token = new_token()
            conn.execute(
                "INSERT INTO admin_sensitive_grants(token_hash,user_id,purpose,expires_at,created_at)"
                " VALUES(?,?,?,?,?)", (token_hash(token), admin["id"], body.action, now + 900, now),
            )
        return {"action_token": token, "expires_in": 900}

    @router.patch("/admin/users/{user_id}/storage-quota")
    def patch_storage_quota(
        user_id: str, body: StorageQuotaPatch, request: Request,
        action_token: str | None = Header(default=None, alias="X-Admin-Action-Token"),
        admin=Depends(admin_user),
    ):
        fields = body.model_dump(exclude_none=True)
        if not fields:
            raise error("empty_patch", "没有可更新的额度", 422)
        with db.transaction(immediate=True) as conn:
            consume_action_token(conn, admin, action_token, "user_storage_quota")
            if not conn.execute("SELECT 1 FROM users WHERE id=? AND role='user'", (user_id,)).fetchone():
                raise error("user_not_found", "用户不存在", 404)
            ensure_limits(conn, user_id)
            fields["updated_at"] = _now()
            conn.execute(
                f"UPDATE user_storage_limits SET {','.join(f'{key}=?' for key in fields)} WHERE user_id=?",
                (*fields.values(), user_id),
            )
            row = conn.execute("SELECT * FROM user_storage_limits WHERE user_id=?", (user_id,)).fetchone()
            audit(conn, request, admin, "user_storage_quota", "user", user_id, fields)
        return dict(row)

    @router.post("/analytics/events", status_code=204)
    def analytics_event(body: AnalyticsInput, user=Depends(current_user)):
        if user.get("analytics_opt_out"):
            return Response(status_code=204)
        if body.event_name not in SAFE_ANALYTICS_EVENTS:
            raise error("analytics_event_not_allowed", "不允许的统计事件", 422)
        if any(key not in SAFE_ANALYTICS_PROPERTIES for key in body.properties):
            raise error("analytics_pii_rejected", "统计属性不得包含内容或个人信息", 422)
        for value in body.properties.values():
            if isinstance(value, str) and (
                len(value) > 40 or "@" in value or "://" in value or any(char in value for char in "\r\n")
            ):
                raise error("analytics_pii_rejected", "统计属性不得包含内容或个人信息", 422)
        now = _now()
        day = datetime.fromtimestamp(now, timezone.utc).strftime("%Y-%m-%d")
        anonymous_id = hmac.new(
            settings.worker_token.encode(), f"{day}:{user['id']}".encode(), hashlib.sha256
        ).hexdigest()
        with db.transaction(immediate=True) as conn:
            conn.execute(
                "INSERT INTO anonymous_events(id,event_day,anonymous_id,event_name,properties_json,created_at)"
                " VALUES(?,?,?,?,?,?)",
                (_id(), day, anonymous_id, body.event_name, _json(body.properties), now),
            )
            conn.execute(
                "INSERT INTO anonymous_daily_aggregates(event_day,event_name,event_count,updated_at)"
                " VALUES(?,?,1,?) ON CONFLICT(event_day,event_name) DO UPDATE SET "
                "event_count=event_count+1,updated_at=excluded.updated_at",
                (day, body.event_name, now),
            )
            conn.execute(
                "INSERT OR IGNORE INTO anonymous_daily_subjects(event_day,event_name,anonymous_id)"
                " VALUES(?,?,?)", (day, body.event_name, anonymous_id),
            )
            conn.execute("DELETE FROM anonymous_events WHERE created_at<?", (now - 90 * 86400,))
        return Response(status_code=204)

    @router.put("/account/analytics")
    def analytics_preference(body: AnalyticsPreference, user=Depends(current_user)):
        with db.transaction(immediate=True) as conn:
            conn.execute(
                "UPDATE users SET analytics_opt_out=? WHERE id=?",
                (0 if body.enabled else 1, user["id"]),
            )
        return {"enabled": body.enabled}

    @router.get("/notifications")
    def notifications(user=Depends(current_user)):
        with db.connection() as conn:
            rows = conn.execute(
                "SELECT id,title,body,kind,read_at,created_at FROM notifications "
                "WHERE user_id=? ORDER BY created_at DESC,id DESC LIMIT 200",
                (user["id"],),
            ).fetchall()
        return {"items": [dict(row) for row in rows]}

    @router.post("/notifications/{notification_id}/read", status_code=204)
    def read_notification(notification_id: str, user=Depends(current_user)):
        with db.transaction(immediate=True) as conn:
            changed = conn.execute(
                "UPDATE notifications SET read_at=COALESCE(read_at,?) WHERE id=? AND user_id=?",
                (_now(), notification_id, user["id"]),
            ).rowcount
        if not changed:
            raise error("notification_not_found", "通知不存在", 404)
        return Response(status_code=204)

    @router.get("/admin/stats/anonymous")
    def anonymous_stats(admin=Depends(admin_user)):
        del admin
        with db.connection() as conn:
            rows = conn.execute(
                "SELECT a.event_day,a.event_name,a.event_count,COUNT(s.anonymous_id) unique_users "
                "FROM anonymous_daily_aggregates a JOIN anonymous_daily_subjects s "
                "ON s.event_day=a.event_day AND s.event_name=a.event_name "
                "GROUP BY a.event_day,a.event_name,a.event_count HAVING COUNT(s.anonymous_id)>=3 "
                "ORDER BY a.event_day DESC,a.event_name"
            ).fetchall()
        return {"items": [dict(row) for row in rows]}

    @router.get("/admin/voices")
    def admin_voices(admin=Depends(admin_user)):
        del admin
        with db.connection() as conn:
            rows = conn.execute(
                "SELECT id,user_id,provider,provider_voice_id,credential_mode,status,activated_at,"
                "provider_expires_at,created_at,disabled_at,error_code FROM voice_clones "
                "ORDER BY created_at DESC"
            ).fetchall()
        return {"items": [dict(row) for row in rows]}

    @router.patch("/admin/voices/{voice_id}/status", status_code=204)
    def admin_change_voice_status(
        voice_id: str, body: AdminVoiceStatusInput, request: Request,
        action_token: str | None = Header(default=None, alias="X-Admin-Action-Token"),
        admin=Depends(admin_user),
    ):
        now = _now()
        with db.transaction(immediate=True) as conn:
            purpose = "disable_voice" if body.status == "disabled" else "enable_voice"
            consume_action_token(conn, admin, action_token, purpose)
            row = conn.execute("SELECT * FROM voice_clones WHERE id=?", (voice_id,)).fetchone()
            if not row:
                raise error("voice_not_found", "音色不存在", 404)
            if body.status == "disabled":
                if row["disabled_at"] is None:
                    conn.execute(
                        "UPDATE voice_clones SET status='disabled',disabled_at=?,updated_at=? WHERE id=?",
                        (now, now, voice_id),
                    )
                    conn.execute(
                        "INSERT INTO provider_voice_actions"
                        "(id,voice_clone_id,action,status,next_attempt_at,created_at)"
                        " VALUES(?,?,?,'pending',?,?)",
                        (_id(), voice_id, "delete", now, now),
                    )
                notify(conn, row["user_id"], "音色已停用", "管理员已停用该音色。", "warning",
                       f"voice-disabled:{voice_id}")
            else:
                completed_delete = conn.execute(
                    "SELECT 1 FROM provider_voice_actions WHERE voice_clone_id=? AND action='delete' "
                    "AND status='complete' LIMIT 1", (voice_id,),
                ).fetchone()
                if completed_delete:
                    raise error("voice_provider_deleted", "供应商音色已删除，无法重新启用", 409)
                conn.execute(
                    "UPDATE provider_voice_actions SET status='cancelled' "
                    "WHERE voice_clone_id=? AND action='delete' AND status='pending'",
                    (voice_id,),
                )
                conn.execute(
                    "UPDATE voice_clones SET status='ready',disabled_at=NULL,updated_at=? WHERE id=?",
                    (now, voice_id),
                )
            audit(conn, request, admin, purpose, "voice_clone", voice_id, {"status": body.status})
        return Response(status_code=204)

    @router.get("/admin/music-library")
    def admin_music(admin=Depends(admin_user)):
        del admin
        with db.connection() as conn:
            rows = conn.execute(
                "SELECT id,owner_user_id,visibility,kind,filename,size_bytes,duration_seconds,"
                "primary_emotion,status,created_at,deleted_at FROM media_assets "
                "WHERE kind IN ('private_music','public_music') ORDER BY created_at DESC"
            ).fetchall()
        return {"items": [dict(row) for row in rows]}

    @router.post("/admin/music-library/tracks", status_code=201)
    async def admin_upload_public_music(
        request: Request, file: UploadFile = File(...), name: str = Form(...),
        primary_emotion: str = Form(...), tags: str = Form("[]"),
        consent_confirmed: bool = Form(...),
        action_token: str | None = Header(default=None, alias="X-Admin-Action-Token"),
        admin=Depends(admin_user),
    ):
        if not consent_confirmed:
            raise error("music_consent_required", "必须确认音乐授权声明", 422)
        suffix = Path(file.filename or "").suffix.lower()
        if suffix not in ALLOWED_MUSIC_SUFFIXES:
            raise error("unsupported_audio_type", "不支持的音频格式", 415)
        if not _disk_status(settings)["uploads_allowed"]:
            admin_alert(
                "disk_upload_stop",
                "磁盘保护已停止上传",
                "磁盘使用率达到 85% 或仍处于保护状态；低于 75% 后自动恢复。",
            )
            raise error("storage_protected", "存储空间不足，暂时停止上传", 507)
        try:
            parsed_tags = json.loads(tags)
        except json.JSONDecodeError as exc:
            raise error("invalid_tags", "标签格式无效", 422) from exc
        if not isinstance(parsed_tags, list) or len(parsed_tags) > 20:
            raise error("invalid_tags", "标签最多20个", 422)
        asset_id, now = _id(), _now()
        relpath = f"library/public/{asset_id}{suffix}"
        path = settings.storage_root / relpath
        # Consume authorization before accepting a potentially expensive upload.
        with db.transaction(immediate=True) as conn:
            consume_action_token(conn, admin, action_token, "public_music_create")
        size, digest = await _stream_upload(file, path, 100 * MIB, error)
        try:
            if not _audio_signature_matches(path, suffix):
                raise error("audio_type_mismatch", "文件内容与扩展名不一致或音频已损坏", 415)
            duration = _audio_duration(path)
            if not 0 < duration <= 1800:
                raise error("music_duration_invalid", "音频无法识别或超过30分钟", 422)
            with db.transaction(immediate=True) as conn:
                conn.execute(
                    "INSERT INTO media_assets"
                    "(id,owner_user_id,visibility,kind,filename,content_type,size_bytes,duration_seconds,"
                    "storage_relpath,primary_emotion,edit_params_json,status,created_at,updated_at)"
                    " VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    (asset_id, admin["id"], "public", "public_music", name[:120],
                     file.content_type or "application/octet-stream", size, duration, relpath,
                     primary_emotion[:40], _json({"loudness": "auto", "fade_in_ms": 2000,
                                                  "fade_out_ms": 2000, "trim_start_ms": 0}),
                     "ready", now, now),
                )
                conn.executemany(
                    "INSERT INTO media_asset_tags(asset_id,tag) VALUES(?,?)",
                    [(asset_id, str(tag).strip()[:40]) for tag in parsed_tags if str(tag).strip()],
                )
                declaration(conn, request, admin, "music", asset_id, MUSIC_DECLARATION, digest)
                audit(conn, request, admin, "public_music_create", "media_asset", asset_id,
                      {"size_bytes": size, "duration_seconds": duration})
                item = serialize_music(conn, conn.execute(
                    "SELECT * FROM media_assets WHERE id=?", (asset_id,)
                ).fetchone())
            return {"item": item}
        except Exception:
            path.unlink(missing_ok=True)
            raise

    @router.delete("/admin/music-library/tracks/{track_id}", status_code=204)
    def admin_delete_public_music(
        track_id: str, request: Request,
        action_token: str | None = Header(default=None, alias="X-Admin-Action-Token"),
        admin=Depends(admin_user),
    ):
        now = _now()
        with db.transaction(immediate=True) as conn:
            consume_action_token(conn, admin, action_token, "delete_public_track")
            row = conn.execute(
                "SELECT * FROM media_assets WHERE id=? AND kind='public_music' AND deleted_at IS NULL",
                (track_id,),
            ).fetchone()
            if not row:
                raise error("track_not_found", "公共音乐不存在", 404)
            conn.execute(
                "UPDATE media_assets SET deleted_at=?,status='deleted',updated_at=? WHERE id=?",
                (now, now, track_id),
            )
            referenced = conn.execute(
                "SELECT 1 FROM jobs WHERE selected_music_asset_id=? "
                "AND status IN ('queued','running','cancel_requested') LIMIT 1",
                (track_id,),
            ).fetchone()
            audit(conn, request, admin, "delete_public_track", "media_asset", track_id)
        if row["storage_relpath"] and not referenced:
            path = _safe_storage_path(settings.storage_root, row["storage_relpath"])
            if path:
                path.unlink(missing_ok=True)
        return Response(status_code=204)

    @router.get("/admin/jobs")
    def admin_jobs(admin=Depends(admin_user)):
        del admin
        with db.connection() as conn:
            rows = conn.execute(
                "SELECT id,user_id,status,progress_stage,created_at,started_at,heartbeat_at,"
                "finished_at,error_code FROM jobs ORDER BY created_at DESC LIMIT 500"
            ).fetchall()
        return {"items": [dict(row) for row in rows]}

    @router.post("/admin/jobs/{job_id}/cancel", status_code=204)
    def admin_cancel_job(
        job_id: str, request: Request,
        action_token: str | None = Header(default=None, alias="X-Admin-Action-Token"),
        admin=Depends(admin_user),
    ):
        now = _now()
        with db.transaction(immediate=True) as conn:
            consume_action_token(conn, admin, action_token, "cancel_job")
            job = conn.execute("SELECT status,user_id FROM jobs WHERE id=?", (job_id,)).fetchone()
            if not job:
                raise error("job_not_found", "任务不存在", 404)
            if job["status"] == "queued":
                conn.execute(
                    "UPDATE jobs SET status='cancelled',progress_stage='cancelled',finished_at=? WHERE id=?",
                    (now, job_id),
                )
            elif job["status"] == "running":
                conn.execute(
                    "UPDATE jobs SET status='cancel_requested' WHERE id=?", (job_id,)
                )
            else:
                raise error("job_not_cancellable", "当前任务无法取消", 409)
            audit(conn, request, admin, "cancel_job", "job", job_id, {"previous_status": job["status"]})
            notify(conn, job["user_id"], "任务已由管理员取消", "该生成任务已停止。", "warning",
                   f"admin-cancel-job:{job_id}")
        return Response(status_code=204)

    @router.get("/admin/works")
    def admin_works(admin=Depends(admin_user)):
        del admin
        with db.connection() as conn:
            rows = conn.execute(
                "SELECT id,user_id,job_id,title,expires_at,is_favorite,created_at,deleted_at FROM works "
                "ORDER BY created_at DESC LIMIT 500"
            ).fetchall()
        return {"items": [dict(row) for row in rows]}

    @router.delete("/admin/works/{work_id}", status_code=204)
    def admin_delete_work(
        work_id: str, request: Request,
        action_token: str | None = Header(default=None, alias="X-Admin-Action-Token"),
        admin=Depends(admin_user),
    ):
        now = _now()
        with db.transaction(immediate=True) as conn:
            consume_action_token(conn, admin, action_token, "delete_work")
            work = conn.execute(
                "SELECT id,user_id,deleted_at FROM works WHERE id=?", (work_id,)
            ).fetchone()
            if not work or work["deleted_at"] is not None:
                raise error("work_not_found", "作品不存在", 404)
            conn.execute("UPDATE works SET deleted_at=? WHERE id=?", (now, work_id))
            audit(conn, request, admin, "delete_work", "work", work_id)
            notify(conn, work["user_id"], "作品已由管理员删除", "该作品已停止提供访问。", "warning",
                   f"admin-delete-work:{work_id}")
        return Response(status_code=204)

    @router.get("/admin/backups")
    def admin_backups(admin=Depends(admin_user)):
        del admin
        items = backup_records()
        failed = [item for item in items if item.get("status") == "failed"]
        if failed:
            admin_alert(
                "backup_failed",
                "备份或恢复任务失败",
                f"检测到 {len(failed)} 个失败的备份请求，请进入管理后台检查。",
            )
        return {"items": items}

    @router.post("/admin/backups", status_code=202)
    def admin_create_backup(
        request: Request,
        action_token: str | None = Header(default=None, alias="X-Admin-Action-Token"),
        admin=Depends(admin_user),
    ):
        with db.transaction(immediate=True) as conn:
            consume_action_token(conn, admin, action_token, "create_backup")
            queued = enqueue_backup_request("create_export", admin["id"])
            audit(conn, request, admin, "backup_create_requested", "backup_request", queued["id"])
        return {"id": queued["id"], "status": "pending"}

    @router.post("/admin/backups/upload", status_code=202)
    async def admin_upload_backup(
        request: Request, file: UploadFile = File(...),
        action_token: str | None = Header(default=None, alias="X-Admin-Action-Token"),
        admin=Depends(admin_user),
    ):
        if not (file.filename or "").lower().endswith(".tar.gz"):
            raise error("backup_type_invalid", "仅支持 AIMusicMed 离线备份 .tar.gz 文件", 415)
        root, now, upload_id = _backup_root(), _now(), _id()
        max_bytes = int(os.environ.get("AIMUSICMED_OFFLINE_UPLOAD_MAX_BYTES", str(8 * 1024 * MIB)))
        filename = (
            f"aimusicmed-upload-{datetime.fromtimestamp(now, timezone.utc).strftime('%Y%m%dT%H%M%SZ')}"
            f"-{upload_id}.tar.gz"
        )
        destination = root / "uploads" / filename
        with db.transaction(immediate=True) as conn:
            consume_action_token(conn, admin, action_token, "upload_backup")
        size, digest = await _stream_upload(file, destination, max_bytes, error)
        checksum = destination.with_name(f"{filename}.sha256")
        try:
            checksum.write_text(f"{digest}  {filename}\n", encoding="ascii")
            queued = enqueue_backup_request("verify_upload", admin["id"], filename)
            with db.transaction(immediate=True) as conn:
                audit(conn, request, admin, "backup_upload_requested", "backup_request", queued["id"],
                      {"package_id": filename, "size_bytes": size, "sha256": digest})
        except Exception:
            destination.unlink(missing_ok=True)
            checksum.unlink(missing_ok=True)
            raise
        return {"id": queued["id"], "status": "pending", "package_id": filename}

    @router.post("/admin/backups/{backup_id}/verify", status_code=202)
    def admin_verify_backup(
        backup_id: str, request: Request,
        action_token: str | None = Header(default=None, alias="X-Admin-Action-Token"),
        admin=Depends(admin_user),
    ):
        root = _backup_root()
        if not _safe_backup_package(root, backup_id):
            raise error("backup_not_found", "备份包不存在", 404)
        with db.transaction(immediate=True) as conn:
            consume_action_token(conn, admin, action_token, "verify_backup")
            queued = enqueue_backup_request("verify", admin["id"], backup_id)
            audit(conn, request, admin, "backup_verify_requested", "backup_request", queued["id"],
                  {"package_id": backup_id})
        return {"id": queued["id"], "status": "pending"}

    @router.get("/admin/backups/{backup_id}/download")
    def admin_download_backup(
        backup_id: str, request: Request,
        action_token: str | None = Header(default=None, alias="X-Admin-Action-Token"),
        admin=Depends(admin_user),
    ):
        root = _backup_root()
        package = _safe_backup_package(root, backup_id)
        if not package or package.parent.name != "offline":
            raise error("backup_not_found", "可下载的备份包不存在", 404)
        checksum_path = package.with_name(f"{package.name}.sha256")
        if not checksum_path.is_file():
            raise error("backup_checksum_missing", "备份校验文件缺失", 409)
        expected = checksum_path.read_text(encoding="ascii").split(maxsplit=1)[0].lower()
        if not re.fullmatch(r"[0-9a-f]{64}", expected) or not hmac.compare_digest(
            expected, _sha256_file(package)
        ):
            raise error("backup_checksum_failed", "备份包校验失败，已阻止下载", 409)
        marker = root / "status" / "last-offline-download"
        marker.parent.mkdir(parents=True, exist_ok=True)
        temporary = marker.with_suffix(".partial")
        temporary.write_text(f"{_now()}\t{package.name}\n", encoding="utf-8")
        os.replace(temporary, marker)
        with db.transaction(immediate=True) as conn:
            consume_action_token(conn, admin, action_token, "download_backup")
            audit(conn, request, admin, "backup_download_verified", "backup_package", package.name,
                  {"size_bytes": package.stat().st_size, "sha256": expected})
        return FileResponse(
            package, media_type="application/gzip", filename=package.name,
            headers={"X-Content-Type-Options": "nosniff", "Cache-Control": "no-store"},
        )

    @router.post("/admin/backups/{backup_id}/restore", status_code=202)
    def admin_restore_backup(
        backup_id: str, request: Request,
        action_token: str | None = Header(default=None, alias="X-Admin-Action-Token"),
        admin=Depends(admin_user),
    ):
        root = _backup_root()
        if not _safe_backup_package(root, backup_id):
            raise error("backup_not_found", "备份包不存在", 404)
        with db.transaction(immediate=True) as conn:
            consume_action_token(conn, admin, action_token, "restore_backup")
            queued = enqueue_backup_request("restore", admin["id"], backup_id)
            audit(conn, request, admin, "backup_restore_requested", "backup_request", queued["id"],
                  {"package_id": backup_id})
        return {"id": queued["id"], "status": "pending"}

    @router.get("/admin/system/status")
    def system_status(admin=Depends(admin_user)):
        del admin
        result = _disk_status(settings)
        result.update({
            "warning_percent": settings.disk_warning_percent,
            "cleanup_percent": settings.disk_cleanup_percent,
            "upload_stop_percent": settings.disk_upload_stop_percent,
            "generation_stop_percent": settings.disk_generation_stop_percent,
            "resume_percent": settings.disk_resume_percent,
        })
        return result

    @router.get("/admin/audit-log")
    def audit_log(admin=Depends(admin_user)):
        del admin
        with db.connection() as conn:
            admin_rows = conn.execute(
                "SELECT id,actor_user_id,action,target_type,target_id,detail_json,created_at "
                "FROM admin_audit_events ORDER BY created_at DESC LIMIT 500"
            ).fetchall()
            declaration_rows = conn.execute(
                "SELECT id,user_id AS actor_user_id,'authorization_declared' AS action,"
                "resource_type AS target_type,resource_id AS target_id,"
                "'{}' AS detail_json,accepted_at AS created_at "
                "FROM authorization_declarations ORDER BY accepted_at DESC LIMIT 500"
            ).fetchall()
        return {"items": sorted(
            [dict(row) for row in (*admin_rows, *declaration_rows)],
            key=lambda item: item["created_at"], reverse=True,
        )[:500]}

    return router
