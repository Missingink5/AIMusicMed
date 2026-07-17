from __future__ import annotations

import json
import hmac
import os
import re
import sqlite3
import time
import uuid
from pathlib import Path
from typing import Annotated, Literal

from fastapi import Cookie, Depends, FastAPI, Header, Request, Response, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
import requests
from tencentcloud.common import credential
from tencentcloud.common.exception.tencent_cloud_sdk_exception import TencentCloudSDKException
from tencentcloud.common.profile.client_profile import ClientProfile
from tencentcloud.common.profile.http_profile import HttpProfile
from tencentcloud.ses.v20201002 import models, ses_client

from .config import Settings
from .db import Database
from .operations import (
    _disk_status, consume_admin_action_token, create_operations_router, record_admin_audit,
)
from .security import (
    SecretBox, hash_password, new_token, token_hash, verification_code,
    verification_code_hash, verify_password,
)


SESSION_COOKIE = "aimusicmed_session"
CRISIS_PATTERNS = (
    re.compile(pattern, re.IGNORECASE)
    for pattern in (
        r"自杀|(不想|不愿)活|结束生命|结束自己|去死|轻生|自残|伤害自己",
        r"杀了(他|她|他们)|伤害(他人|别人)|同归于尽",
    )
)
CRISIS_PATTERNS = tuple(CRISIS_PATTERNS)
CRISIS_HELP = {
    "title": "请先确保你此刻的安全",
    "message": "AIMusicMed 不能处理紧急危机。若你或他人正处于立即危险中，请立即拨打 110 或 120；也可拨打全国统一心理援助热线 12356，并联系身边可信任的人陪伴你。",
    "emergency_numbers": ["110", "120", "12356"],
}


class ApiError(Exception):
    def __init__(self, code: str, message: str, status_code: int = 400):
        self.code = code
        self.message = message
        self.status_code = status_code


class EmailInput(BaseModel):
    email: str = Field(min_length=3, max_length=254)


class CodeRequestInput(EmailInput):
    purpose: Literal["login", "password_reset"] = "login"


class CodeVerifyInput(CodeRequestInput):
    code: str = Field(pattern=r"^\d{6}$")


class PasswordLoginInput(EmailInput):
    password: str = Field(min_length=10, max_length=72)


class PasswordInput(BaseModel):
    current_password: str | None = Field(default=None, min_length=10, max_length=72)
    password: str = Field(min_length=10, max_length=72)
    password_confirmation: str = Field(min_length=10, max_length=72)


class PasswordResetInput(PasswordInput):
    reset_token: str = Field(min_length=20, max_length=200)


class UserStatusInput(BaseModel):
    status: Literal["active", "disabled"]


class ConversationInput(BaseModel):
    title: str = Field(default="新对话", min_length=1, max_length=80)


class ConversationRenameInput(BaseModel):
    title: str = Field(min_length=1, max_length=80)


class MessageInput(BaseModel):
    content: str = Field(min_length=1, max_length=2000)


class PlanInput(BaseModel):
    message_id: str
    draft_id: str | None = None
    duration_minutes: int = Field(ge=3, le=15)
    music_source: Literal["library", "ai"] = "library"
    target_emotion: Literal["auto", "平静", "喜悦", "友爱", "自信"] = "auto"
    credential_mode: Literal["platform", "byok"] = "platform"
    voice_mode: Literal["tts", "pure_music"] = "tts"
    guidance_style: str = Field(default="auto", min_length=1, max_length=40)
    language_density: Literal["balanced", "less_language"] = "balanced"
    selected_voice_id: str | None = Field(default=None, max_length=256)
    selected_music_asset_id: str | None = Field(default=None, max_length=64)


class PlanDraftCreateInput(BaseModel):
    credential_mode: Literal["platform", "byok"] = "platform"


class PlanDraftPatchInput(BaseModel):
    summary: str | None = Field(default=None, min_length=1, max_length=1000)
    primary_emotion: str | None = Field(default=None, min_length=1, max_length=40)
    emotion_path: str | None = Field(default=None, min_length=1, max_length=300)
    duration_minutes: int | None = Field(default=None, ge=3, le=15)
    music_source: Literal["library", "ai"] | None = None
    target_emotion: Literal["auto", "平静", "喜悦", "友爱", "自信"] | None = None
    credential_mode: Literal["platform", "byok"] | None = None
    voice_mode: Literal["tts", "pure_music"] | None = None
    guidance_style: str | None = Field(default=None, min_length=1, max_length=40)
    language_density: Literal["balanced", "less_language"] | None = None
    selected_voice_id: str | None = Field(default=None, max_length=256)
    selected_music_asset_id: str | None = Field(default=None, max_length=64)


class CredentialInput(BaseModel):
    deepseek_api_key: str = Field(min_length=8, max_length=500)
    minimax_api_key: str = Field(min_length=8, max_length=500)
    elevenlabs_api_key: str | None = Field(default=None, min_length=8, max_length=500)


class AssistantStreamInput(BaseModel):
    message_id: str
    credential_mode: Literal["platform", "byok"] = "platform"


class WorkerEventInput(BaseModel):
    stage: str = Field(min_length=1, max_length=80)
    current: int | None = Field(default=None, ge=0)
    total: int | None = Field(default=None, ge=0)
    message: str = Field(default="", max_length=300)


class WorkerCompleteInput(BaseModel):
    title: str = Field(default="我的音乐冥想", min_length=1, max_length=100)


class WorkerFailInput(BaseModel):
    error_code: str = Field(default="generation_failed", min_length=1, max_length=80)


class QuotaInput(BaseModel):
    daily_limit: int = Field(ge=0, le=100)


def _now() -> int:
    return int(time.time())


def _id() -> str:
    return uuid.uuid4().hex


def _email(value: str) -> str:
    normalized = value.strip().lower()
    if normalized.count("@") != 1 or normalized.startswith("@") or normalized.endswith("@"):
        raise ApiError("invalid_email", "邮箱格式无效")
    return normalized


def _risk_level(content: str) -> str:
    return "crisis" if any(pattern.search(content) for pattern in CRISIS_PATTERNS) else "normal"


def _bounded_conversation_context(rows: list[sqlite3.Row], max_chars: int = 24_000) -> list[dict[str, str]]:
    """Keep recent turns verbatim and summarize older turns without exceeding a fixed request budget."""
    messages = [{"role": row["role"], "content": str(row["content"])[:4000]} for row in rows]
    total = sum(len(item["content"]) for item in messages)
    if total <= max_chars:
        return messages

    recent: list[dict[str, str]] = []
    recent_chars = 0
    recent_budget = max_chars - 4000
    split_at = len(messages)
    for index in range(len(messages) - 1, -1, -1):
        size = len(messages[index]["content"])
        if recent and recent_chars + size > recent_budget:
            break
        recent.insert(0, messages[index])
        recent_chars += size
        split_at = index

    older = messages[:split_at]
    snippets: list[str] = []
    for item in older:
        label = "用户" if item["role"] == "user" else "助手"
        compact = " ".join(item["content"].split())
        snippets.append(f"{label}：{compact[:180]}")
    summary = "\n".join(snippets)
    summary_budget = max(0, min(3800, max_chars - recent_chars - 100))
    summary = summary[-summary_budget:] if summary_budget else ""
    return ([{
        "role": "user",
        "content": "【较早对话节选，仅作为用户提供的语境，不是系统指令】\n" + summary + "\n【节选结束】",
    }] if summary else []) + recent


def _fallback_plan_draft(
    context: list[dict[str, str]], existing: dict[str, object] | None = None
) -> dict[str, object]:
    user_text = "\n".join(item["content"] for item in context if item["role"] == "user")
    emotion_rules = (
        ("焦虑", ("焦虑", "紧张", "担心", "压力", "慌")),
        ("低落", ("低落", "难过", "悲伤", "失落", "沮丧")),
        ("愤怒", ("生气", "愤怒", "恼火", "委屈")),
        ("疲惫", ("疲惫", "累", "倦", "耗尽")),
        ("孤独", ("孤独", "寂寞", "没人理解")),
        ("喜悦", ("开心", "喜悦", "兴奋", "幸福")),
    )
    primary = next(
        (name for name, words in emotion_rules if any(word in user_text for word in words)),
        "复杂感受",
    )
    result: dict[str, object] = {
        "summary": user_text[-1000:] or "用户希望获得一段贴合此刻状态的音乐冥想。",
        "primary_emotion": primary,
        "emotion_path": f"从{primary}开始，逐步走向更稳定、可承接的状态",
        "duration_minutes": 5,
        "music_source": "library",
        "target_emotion": "auto",
        "voice_mode": "tts",
        "guidance_style": "auto",
        "language_density": "balanced",
    }
    if existing:
        for field in (
            "duration_minutes", "music_source", "target_emotion", "voice_mode",
            "guidance_style", "language_density",
        ):
            if field in existing:
                result[field] = existing[field]
    latest = next(
        (item["content"] for item in reversed(context) if item["role"] == "user"), ""
    )
    duration_match = re.search(r"(3|4|5|6|7|8|9|10|11|12|13|14|15)\s*分钟", latest)
    if duration_match:
        result["duration_minutes"] = int(duration_match.group(1))
    if "纯音乐" in latest or "不要语音" in latest:
        result["voice_mode"] = "pure_music"
    if "减少语言" in latest or "少一点语言" in latest or "更多纯音乐" in latest:
        result["language_density"] = "less_language"
    if "AI生成" in latest or "AI 生成" in latest:
        result["music_source"] = "ai"
    return result


def _generate_plan_draft(
    context: list[dict[str, str]], api_key: str, existing: dict[str, object] | None = None
) -> dict[str, object]:
    fallback = _fallback_plan_draft(context, existing)
    if not api_key:
        return fallback
    try:
        response = requests.post(
            f"{os.getenv('DEEPSEEK_BASE_URL', 'https://api.deepseek.com/v1').rstrip('/')}/chat/completions",
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json={
                "model": os.getenv("DEEPSEEK_MODEL", "deepseek-chat"),
                "response_format": {"type": "json_object"},
                "stream": False,
                "messages": [{
                    "role": "system",
                    "content": (
                        "根据本会话规划音乐冥想，只输出JSON。只确定一个primary_emotion；其他感受放summary。"
                        "若给出当前草稿，只在最新用户消息明确要求修改某项设置时才改该项，否则原样保留。"
                        "字段必须为summary,primary_emotion,emotion_path,duration_minutes,music_source,"
                        "target_emotion,voice_mode,guidance_style,language_density。duration_minutes为3到15整数；"
                        "music_source为library或ai；target_emotion为auto/平静/喜悦/友爱/自信；"
                        "voice_mode为tts或pure_music；language_density为balanced或less_language。"
                    ),
                }, *([{
                    "role": "system",
                    "content": "当前草稿：" + json.dumps({
                        key: existing[key] for key in (
                            "duration_minutes", "music_source", "target_emotion", "voice_mode",
                            "guidance_style", "language_density",
                        ) if key in existing
                    }, ensure_ascii=False),
                }] if existing else []), *context],
            },
            timeout=(10, 60),
        )
        response.raise_for_status()
        content = response.json()["choices"][0]["message"]["content"]
        parsed = json.loads(content)
        if not isinstance(parsed, dict):
            return fallback
        result = {**fallback, **{key: parsed[key] for key in fallback if key in parsed}}
        result["summary"] = str(result["summary"]).strip()[:1000] or fallback["summary"]
        result["primary_emotion"] = str(result["primary_emotion"]).strip()[:40] or fallback["primary_emotion"]
        result["emotion_path"] = str(result["emotion_path"]).strip()[:300] or fallback["emotion_path"]
        duration = int(result["duration_minutes"])
        result["duration_minutes"] = min(15, max(3, duration))
        if result["music_source"] not in ("library", "ai"):
            result["music_source"] = fallback["music_source"]
        if result["target_emotion"] not in ("auto", "平静", "喜悦", "友爱", "自信"):
            result["target_emotion"] = fallback["target_emotion"]
        if result["voice_mode"] not in ("tts", "pure_music"):
            result["voice_mode"] = fallback["voice_mode"]
        result["guidance_style"] = str(result["guidance_style"]).strip()[:40] or "auto"
        if result["language_density"] not in ("balanced", "less_language"):
            result["language_density"] = fallback["language_density"]
        return result
    except (requests.RequestException, ValueError, KeyError, TypeError):
        return fallback


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings.from_env()
    settings.storage_root.mkdir(parents=True, exist_ok=True)
    db = Database(settings.database_path)
    db.initialize()
    secrets = SecretBox(settings.fernet_key)
    app = FastAPI(title="AIMusicMed API", version="0.1.0")
    app.state.settings = settings
    app.state.db = db
    app.state.secrets = secrets
    dummy_password_hash = hash_password("AIMusicMed dummy password")

    if settings.admin_email:
        with db.transaction(immediate=True) as conn:
            existing = conn.execute("SELECT id FROM users WHERE email=?", (settings.admin_email,)).fetchone()
            if existing:
                conn.execute(
                    "UPDATE users SET role='admin', status='active' WHERE id=?",
                    (existing["id"],),
                )
            else:
                conn.execute(
                    "INSERT INTO users(id,email,role,status,daily_limit,created_at) VALUES(?,?,?,?,?,?)",
                    (_id(), settings.admin_email, "admin", "active", 10, _now()),
                )

    @app.exception_handler(ApiError)
    async def api_error_handler(_request: Request, exc: ApiError):
        return JSONResponse(
            status_code=exc.status_code,
            content={"error": {"code": exc.code, "message": exc.message}},
        )

    @app.exception_handler(RequestValidationError)
    async def validation_error_handler(_request: Request, _exc: RequestValidationError):
        return JSONResponse(
            status_code=422,
            content={"error": {"code": "validation_error", "message": "请检查提交的内容"}},
        )

    @app.exception_handler(Exception)
    async def unexpected_error_handler(_request: Request, _exc: Exception):
        return JSONResponse(
            status_code=500,
            content={"error": {"code": "internal_error", "message": "服务暂时不可用"}},
        )

    def current_user(request: Request, session: Annotated[str | None, Cookie(alias=SESSION_COOKIE)] = None):
        if not session:
            raise ApiError("authentication_required", "请先登录", 401)
        with db.connection() as conn:
            row = conn.execute(
                "SELECT u.* FROM sessions s JOIN users u ON u.id=s.user_id "
                "WHERE s.token_hash=? AND s.expires_at>? AND u.status='active'",
                (token_hash(session), _now()),
            ).fetchone()
        if not row:
            raise ApiError("invalid_session", "登录已失效", 401)
        user = dict(row)
        if (
            user["role"] == "admin" and not user.get("password_hash")
            and request.url.path not in ("/me", "/account/password", "/auth/logout")
        ):
            raise ApiError("password_setup_required", "请先设置登录密码", 403)
        return user

    def admin_user(user=Depends(current_user)):
        if user["role"] != "admin":
            raise ApiError("admin_required", "需要管理员权限", 403)
        return user

    def worker_auth(authorization: Annotated[str | None, Header()] = None):
        expected = f"Bearer {settings.worker_token}"
        if not authorization or not secrets_compare(authorization, expected):
            raise ApiError("worker_auth_failed", "worker authentication failed", 401)

    def set_session(response: Response, user_id: str) -> None:
        token = new_token()
        now = _now()
        with db.transaction() as conn:
            conn.execute(
                "INSERT INTO sessions(token_hash,user_id,expires_at,created_at) VALUES(?,?,?,?)",
                (token_hash(token), user_id, now + settings.session_days * 86400, now),
            )
        response.set_cookie(
            SESSION_COOKIE,
            token,
            max_age=settings.session_days * 86400,
            httponly=True,
            secure=settings.secure_cookies,
            samesite="strict",
            path="/",
        )

    def send_email(
        recipient: str,
        subject: str,
        *,
        action: str,
        expires: str,
        code: str,
    ) -> None:
        if settings.dev_auth_codes:
            return
        if not all(
            (
                settings.tencentcloud_secret_id,
                settings.tencentcloud_secret_key,
                settings.tencentcloud_region,
                settings.ses_from,
                settings.ses_template_id,
            )
        ):
            raise ApiError("email_unavailable", "邮件服务尚未配置", 503)
        try:
            cred = credential.Credential(
                settings.tencentcloud_secret_id,
                settings.tencentcloud_secret_key,
            )
            http_profile = HttpProfile()
            http_profile.endpoint = "ses.tencentcloudapi.com"
            client_profile = ClientProfile()
            client_profile.httpProfile = http_profile
            client = ses_client.SesClient(cred, settings.tencentcloud_region, client_profile)
            request = models.SendEmailRequest()
            request.from_json_string(
                json.dumps(
                    {
                        "FromEmailAddress": settings.ses_from,
                        "Destination": [recipient],
                        "Subject": subject,
                        "Template": {
                            "TemplateID": settings.ses_template_id,
                            "TemplateData": json.dumps(
                                {"action": action, "expires": expires, "code": code},
                                ensure_ascii=False,
                            ),
                        },
                    }
                )
            )
            client.SendEmail(request)
        except (TencentCloudSDKException, OSError, ValueError) as exc:
            raise ApiError("email_delivery_failed", "邮件发送失败，请稍后重试", 503) from exc

    def send_alert_email(recipient: str, title: str, message: str) -> bool:
        if settings.dev_auth_codes or not settings.ses_alert_template_id:
            return False
        if not all((
            settings.tencentcloud_secret_id,
            settings.tencentcloud_secret_key,
            settings.tencentcloud_region,
            settings.ses_from,
        )):
            return False
        try:
            cred = credential.Credential(
                settings.tencentcloud_secret_id,
                settings.tencentcloud_secret_key,
            )
            http_profile = HttpProfile()
            http_profile.endpoint = "ses.tencentcloudapi.com"
            client_profile = ClientProfile()
            client_profile.httpProfile = http_profile
            client = ses_client.SesClient(
                cred, settings.tencentcloud_region, client_profile
            )
            request = models.SendEmailRequest()
            request.from_json_string(json.dumps({
                "FromEmailAddress": settings.ses_from,
                "Destination": [recipient],
                "Subject": f"AIMusicMed 关键告警：{title}",
                "Template": {
                    "TemplateID": settings.ses_alert_template_id,
                    "TemplateData": json.dumps({
                        "title": title,
                        "message": message,
                        "time": time.strftime("%Y-%m-%d %H:%M:%S"),
                    }, ensure_ascii=False),
                },
            }))
            client.SendEmail(request)
            return True
        except (TencentCloudSDKException, OSError, ValueError):
            return False

    def admin_alert(key: str, title: str, message: str) -> None:
        now = _now()
        with db.transaction(immediate=True) as conn:
            setting_key = f"admin_alert:{key}"
            previous = conn.execute(
                "SELECT value FROM operations_settings WHERE key=?", (setting_key,)
            ).fetchone()
            if previous and now - int(previous["value"]) < 6 * 3600:
                return
            admin = conn.execute(
                "SELECT id,email FROM users WHERE role='admin' AND status='active' "
                "ORDER BY created_at LIMIT 1"
            ).fetchone()
            if not admin:
                return
            conn.execute(
                "INSERT INTO operations_settings(key,value,updated_at,updated_by) "
                "VALUES(?,?,?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value,"
                "updated_at=excluded.updated_at,updated_by=excluded.updated_by",
                (setting_key, str(now), now, admin["id"]),
            )
            conn.execute(
                "INSERT INTO notifications(id,user_id,title,body,kind,dedupe_key,created_at) "
                "VALUES(?,?,?,?,?,?,?)",
                (_id(), admin["id"], title, message, "warning", setting_key, now),
            )
        send_alert_email(admin["email"], title, message)

    @app.get("/health")
    def health():
        return {"status": "ok"}

    def auth_keys(email: str, request: Request) -> tuple[str, str]:
        client_ip = request.client.host if request.client else "unknown"
        return (
            token_hash(f"{settings.worker_token}:email:{email}"),
            token_hash(f"{settings.worker_token}:ip:{client_ip}"),
        )

    def rate_limited(conn, kind: str, email_hash: str, ip_hash: str, now: int) -> bool:
        conn.execute("DELETE FROM auth_events WHERE created_at<?", (now - 3600,))
        email_count = conn.execute(
            "SELECT COUNT(*) FROM auth_events WHERE kind=? AND email_hash=? AND created_at>?",
            (kind, email_hash, now - 3600),
        ).fetchone()[0]
        ip_count = conn.execute(
            "SELECT COUNT(*) FROM auth_events WHERE kind=? AND ip_hash=? AND created_at>?",
            (kind, ip_hash, now - 3600),
        ).fetchone()[0]
        if kind == "send":
            recent = conn.execute(
                "SELECT 1 FROM auth_events WHERE kind='send' AND created_at>? "
                "AND (email_hash=? OR ip_hash=?) LIMIT 1",
                (now - 60, email_hash, ip_hash),
            ).fetchone()
            return bool(recent or email_count >= 5 or ip_count >= 20)
        return email_count >= 20 or ip_count >= 60

    def record_event(conn, kind: str, email_hash: str, ip_hash: str, now: int) -> None:
        conn.execute(
            "INSERT INTO auth_events(kind,email_hash,ip_hash,created_at) VALUES(?,?,?,?)",
            (kind, email_hash, ip_hash, now),
        )

    def issue_code(conn, user, email: str, purpose: str, action: str, now: int) -> str:
        code, challenge_id = verification_code(), _id()
        conn.execute(
            "UPDATE verification_codes SET used_at=? WHERE user_id=? AND purpose=? AND used_at IS NULL",
            (now, user["id"], purpose),
        )
        conn.execute(
            "INSERT INTO verification_codes(id,user_id,purpose,code_hash,expires_at,created_at) "
            "VALUES(?,?,?,?,?,?)",
            (challenge_id, user["id"], purpose,
             verification_code_hash(settings.worker_token, challenge_id, code), now + 900, now),
        )
        send_email(email, "AIMusicMed 验证码", action=action, expires="15 分钟", code=code)
        return code

    @app.post("/admin/invitations", status_code=201)
    def create_invitation(body: EmailInput, request: Request, _admin=Depends(admin_user)):
        email, now = _email(body.email), _now()
        with db.transaction(immediate=True) as conn:
            user = conn.execute("SELECT * FROM users WHERE email=?", (email,)).fetchone()
            if user and user["status"] in ("active", "disabled"):
                raise ApiError("already_invited", "该邮箱已存在", 409)
            if not user:
                user_id = _id()
                conn.execute(
                    "INSERT INTO users(id,email,role,status,daily_limit,created_at) VALUES(?,?,?,?,?,?)",
                    (user_id, email, "user", "pending", 10, now),
                )
                user = conn.execute("SELECT * FROM users WHERE id=?", (user_id,)).fetchone()
            email_hash, ip_hash = auth_keys(email, request)
            if rate_limited(conn, "send", email_hash, ip_hash, now):
                raise ApiError("code_rate_limited", "验证码发送过于频繁", 429)
            record_event(conn, "send", email_hash, ip_hash, now)
            code = issue_code(conn, user, email, "login", "激活 AIMusicMed 账号", now)
        result = {"invited": True, "status": "pending", "expires_in": 900}
        if settings.dev_auth_codes:
            result["verification_code"] = code
        return result

    @app.get("/admin/users")
    def admin_users(_admin=Depends(admin_user)):
        with db.connection() as conn:
            rows = conn.execute(
                "SELECT id,email,role,status,daily_limit,created_at,activated_at," 
                "password_hash IS NOT NULL AS password_configured FROM users ORDER BY created_at,id"
            ).fetchall()
        return {"items": [dict(row) for row in rows]}

    @app.patch("/admin/users/{user_id}/quota")
    def admin_user_quota(
        user_id: str, body: QuotaInput, request: Request,
        action_token: Annotated[str | None, Header(alias="X-Admin-Action-Token")] = None,
        admin=Depends(admin_user),
    ):
        with db.transaction(immediate=True) as conn:
            consume_admin_action_token(conn, admin, action_token, "adjust_user_quota", ApiError)
            changed = conn.execute(
                "UPDATE users SET daily_limit=? WHERE id=? AND role='user'",
                (body.daily_limit, user_id),
            ).rowcount
            if changed:
                record_admin_audit(
                    conn, request, admin, settings, "adjust_user_quota", "user", user_id,
                    {"daily_limit": body.daily_limit},
                )
        if not changed:
            raise ApiError("user_not_found", "用户不存在", 404)
        return {"daily_limit": body.daily_limit}

    @app.post("/admin/users/{user_id}/code/resend")
    def resend_invitation_code(user_id: str, request: Request, _admin=Depends(admin_user)):
        now = _now()
        with db.transaction(immediate=True) as conn:
            user = conn.execute("SELECT * FROM users WHERE id=? AND status='pending'", (user_id,)).fetchone()
            if not user:
                raise ApiError("user_not_found", "待激活用户不存在", 404)
            email_hash, ip_hash = auth_keys(user["email"], request)
            if rate_limited(conn, "send", email_hash, ip_hash, now):
                raise ApiError("code_rate_limited", "验证码发送过于频繁", 429)
            record_event(conn, "send", email_hash, ip_hash, now)
            code = issue_code(conn, user, user["email"], "login", "激活 AIMusicMed 账号", now)
        result = {"sent": True, "expires_in": 900}
        if settings.dev_auth_codes:
            result["verification_code"] = code
        return result

    @app.patch("/admin/users/{user_id}/status")
    def admin_user_status(
        user_id: str, body: UserStatusInput, request: Request,
        action_token: Annotated[str | None, Header(alias="X-Admin-Action-Token")] = None,
        admin=Depends(admin_user),
    ):
        now = _now()
        with db.transaction(immediate=True) as conn:
            consume_admin_action_token(conn, admin, action_token, "change_user_status", ApiError)
            user = conn.execute("SELECT * FROM users WHERE id=? AND role='user'", (user_id,)).fetchone()
            if not user:
                raise ApiError("user_not_found", "用户不存在", 404)
            if user["status"] == "pending":
                raise ApiError("user_not_activated", "待激活用户不能停用或直接启用，请重新发送验证码", 409)
            if body.status == "active" and not user["activated_at"]:
                raise ApiError("user_not_activated", "该用户尚未激活，不能直接启用", 409)
            conn.execute("UPDATE users SET status=? WHERE id=?", (body.status, user_id))
            if body.status == "disabled":
                conn.execute("DELETE FROM sessions WHERE user_id=?", (user_id,))
                conn.execute(
                    "UPDATE verification_codes SET used_at=? WHERE user_id=? AND used_at IS NULL",
                    (now, user_id),
                )
            record_admin_audit(
                conn, request, admin, settings, "change_user_status", "user", user_id,
                {"status": body.status},
            )
        return {"status": body.status}

    @app.post("/auth/code/request")
    def request_code(body: CodeRequestInput, request: Request):
        email, now = _email(body.email), _now()
        result = {"sent": True, "expires_in": 900}
        try:
            with db.transaction(immediate=True) as conn:
                email_hash, ip_hash = auth_keys(email, request)
                if rate_limited(conn, "send", email_hash, ip_hash, now):
                    return result
                record_event(conn, "send", email_hash, ip_hash, now)
                user = conn.execute(
                    "SELECT * FROM users WHERE email=? AND status IN ('pending','active')", (email,)
                ).fetchone()
                if user:
                    action = "登录 AIMusicMed" if user["status"] == "active" else "激活 AIMusicMed 账号"
                    code = issue_code(conn, user, email, body.purpose, action, now)
                    if settings.dev_auth_codes:
                        result["verification_code"] = code
        except ApiError as exc:
            if exc.code not in ("email_unavailable", "email_delivery_failed"):
                raise
        return result

    @app.post("/auth/code/verify")
    def verify_code(body: CodeVerifyInput, request: Request, response: Response):
        email, now = _email(body.email), _now()
        invalid, reset_token, user = False, None, None
        with db.transaction(immediate=True) as conn:
            email_hash, ip_hash = auth_keys(email, request)
            if rate_limited(conn, "verify", email_hash, ip_hash, now):
                raise ApiError("verification_rate_limited", "验证尝试过多，请稍后再试", 429)
            record_event(conn, "verify", email_hash, ip_hash, now)
            user = conn.execute(
                "SELECT * FROM users WHERE email=? AND status IN ('pending','active')", (email,)
            ).fetchone()
            challenge = None
            if user:
                challenge = conn.execute(
                    "SELECT * FROM verification_codes WHERE user_id=? AND purpose=? AND used_at IS NULL "
                    "AND expires_at>? ORDER BY created_at DESC LIMIT 1",
                    (user["id"], body.purpose, now),
                ).fetchone()
            if not challenge or challenge["attempts"] >= 5:
                invalid = True
            else:
                expected = verification_code_hash(settings.worker_token, challenge["id"], body.code)
                if not hmac.compare_digest(expected, challenge["code_hash"]):
                    conn.execute(
                        "UPDATE verification_codes SET attempts=attempts+1 WHERE id=?", (challenge["id"],)
                    )
                    invalid = True
                else:
                    conn.execute("UPDATE verification_codes SET used_at=? WHERE id=?", (now, challenge["id"]))
                    if body.purpose == "login":
                        conn.execute(
                            "UPDATE users SET status='active',activated_at=COALESCE(activated_at,?) WHERE id=?",
                            (now, user["id"]),
                        )
                    else:
                        reset_token = new_token()
                        conn.execute("DELETE FROM password_reset_tokens WHERE user_id=?", (user["id"],))
                        conn.execute(
                            "INSERT INTO password_reset_tokens(token_hash,user_id,expires_at,created_at) "
                            "VALUES(?,?,?,?)",
                            (token_hash(reset_token), user["id"], now + 900, now),
                        )
        if invalid:
            raise ApiError("invalid_code", "验证码错误或已过期", 401)
        if body.purpose == "password_reset":
            return {"verified": True, "reset_token": reset_token, "expires_in": 900}
        set_session(response, user["id"])
        setup = "required" if user["role"] == "admin" and not user["password_hash"] else (
            "optional" if not user["password_hash"] else "none"
        )
        return {"authenticated": True, "password_setup": setup}

    @app.post("/auth/password/login")
    def password_login(body: PasswordLoginInput, request: Request, response: Response):
        email, now = _email(body.email), _now()
        email_hash, ip_hash = auth_keys(email, request)
        invalid = False
        with db.transaction(immediate=True) as conn:
            if rate_limited(conn, "password_login", email_hash, ip_hash, now):
                raise ApiError("password_rate_limited", "密码登录尝试过于频繁，请稍后再试或使用邮箱验证码", 429)
            user = conn.execute("SELECT * FROM users WHERE email=? AND status='active'", (email,)).fetchone()
            stored_hash = user["password_hash"] if user and user["password_hash"] else dummy_password_hash
            password_ok = verify_password(stored_hash, body.password)
            if user and user["password_locked_until"] and user["password_locked_until"] > now:
                raise ApiError("password_locked", "密码登录已锁定，请稍后再试或使用邮箱验证码", 423)
            if not user or not user["password_hash"] or not password_ok:
                if user and user["password_hash"]:
                    attempts = user["password_failed_attempts"] + 1
                    locked_until = now + 900 if attempts >= 5 else None
                    conn.execute(
                        "UPDATE users SET password_failed_attempts=?,password_locked_until=? WHERE id=?",
                        (0 if locked_until else attempts, locked_until, user["id"]),
                    )
                invalid = True
            else:
                conn.execute(
                    "UPDATE users SET password_failed_attempts=0,password_locked_until=NULL WHERE id=?", (user["id"],)
                )
            record_event(conn, "password_login", email_hash, ip_hash, now)
        if invalid:
            raise ApiError("invalid_credentials", "邮箱或密码错误", 401)
        set_session(response, user["id"])
        return {"authenticated": True, "password_setup": "none"}

    @app.put("/account/password")
    def set_account_password(body: PasswordInput, request: Request, user=Depends(current_user)):
        if not hmac.compare_digest(body.password, body.password_confirmation):
            raise ApiError("password_confirmation_mismatch", "两次输入的密码不一致", 422)
        if user["password_hash"] and (
            not body.current_password or not verify_password(user["password_hash"], body.current_password)
        ):
            raise ApiError("invalid_current_password", "当前密码错误", 401)
        with db.transaction(immediate=True) as conn:
            conn.execute(
                "UPDATE users SET password_hash=?,password_failed_attempts=0,password_locked_until=NULL WHERE id=?",
                (hash_password(body.password), user["id"]),
            )
            # Invalidate all other sessions so a stolen session cannot survive
            # the legitimate user's password-change containment action.
            conn.execute(
                "DELETE FROM sessions WHERE user_id=? AND token_hash!=?",
                (user["id"], token_hash(request.cookies.get(SESSION_COOKIE, ""))),
            )
        return {"password_configured": True}

    @app.post("/auth/password/reset")
    def reset_password(body: PasswordResetInput, response: Response):
        if not hmac.compare_digest(body.password, body.password_confirmation):
            raise ApiError("password_confirmation_mismatch", "两次输入的密码不一致", 422)
        now = _now()
        with db.transaction(immediate=True) as conn:
            reset = conn.execute(
                "SELECT * FROM password_reset_tokens WHERE token_hash=? AND used_at IS NULL AND expires_at>?",
                (token_hash(body.reset_token), now),
            ).fetchone()
            if not reset:
                raise ApiError("invalid_reset_token", "密码重置凭证无效或已过期", 400)
            conn.execute(
                "UPDATE password_reset_tokens SET used_at=? WHERE token_hash=?",
                (now, token_hash(body.reset_token)),
            )
            conn.execute(
                "UPDATE users SET password_hash=?,password_failed_attempts=0,password_locked_until=NULL WHERE id=?",
                (hash_password(body.password), reset["user_id"]),
            )
            conn.execute("DELETE FROM sessions WHERE user_id=?", (reset["user_id"],))
        response.delete_cookie(SESSION_COOKIE, path="/")
        return {"password_reset": True}

    @app.post("/auth/logout", status_code=204)
    def logout(response: Response, session: Annotated[str | None, Cookie(alias=SESSION_COOKIE)] = None):
        if session:
            with db.transaction() as conn:
                conn.execute("DELETE FROM sessions WHERE token_hash=?", (token_hash(session),))
        response.delete_cookie(SESSION_COOKIE, path="/")

    @app.get("/me")
    def me(user=Depends(current_user)):
        result = {key: user[key] for key in ("id", "email", "role", "daily_limit")}
        result["password_configured"] = bool(user["password_hash"])
        result["password_setup"] = (
            "required" if user["role"] == "admin" and not user["password_hash"]
            else "optional" if not user["password_hash"] else "none"
        )
        return result

    @app.put("/settings/credentials")
    def put_credentials(body: CredentialInput, user=Depends(current_user)):
        now = _now()
        with db.transaction(immediate=True) as conn:
            conn.execute(
                "INSERT INTO credentials(user_id,deepseek_key,minimax_key,elevenlabs_key,updated_at) VALUES(?,?,?,?,?) "
                "ON CONFLICT(user_id) DO UPDATE SET deepseek_key=excluded.deepseek_key,minimax_key=excluded.minimax_key,"
                "elevenlabs_key=excluded.elevenlabs_key,updated_at=excluded.updated_at",
                (
                    user["id"], secrets.encrypt(body.deepseek_api_key), secrets.encrypt(body.minimax_api_key),
                    secrets.encrypt(body.elevenlabs_api_key) if body.elevenlabs_api_key else None, now,
                ),
            )
        return {"configured": {"deepseek": True, "minimax": True, "elevenlabs": bool(body.elevenlabs_api_key)}}

    @app.delete("/settings/credentials", status_code=204)
    def delete_credentials(user=Depends(current_user)):
        with db.transaction() as conn:
            conn.execute("DELETE FROM credentials WHERE user_id=?", (user["id"],))

    @app.post("/conversations", status_code=201)
    def create_conversation(body: ConversationInput, user=Depends(current_user)):
        conversation_id, now = _id(), _now()
        title = body.title.strip()
        if not title:
            raise ApiError("invalid_title", "标题不能为空")
        with db.transaction() as conn:
            conn.execute(
                "INSERT INTO conversations(id,user_id,title,created_at,updated_at) VALUES(?,?,?,?,?)",
                (conversation_id, user["id"], title, now, now),
            )
        return {"id": conversation_id, "title": title}

    def purge_due_conversations(conn: sqlite3.Connection, now: int) -> None:
        Database.purge_expired_conversations(conn, now)

    @app.get("/conversations")
    def list_conversations(
        q: str = "", trash: bool = False, include_deleted: bool = False,
        user=Depends(current_user),
    ):
        term = q.strip()[:80]
        trash = trash or include_deleted
        with db.transaction(immediate=True) as conn:
            purge_due_conversations(conn, _now())
            clauses = ["user_id=?", "purged_at IS NULL"]
            params: list[object] = [user["id"]]
            clauses.append("deleted_at IS NOT NULL" if trash else "deleted_at IS NULL")
            if term:
                escaped = term.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
                clauses.append("title LIKE ? ESCAPE '\\'")
                params.append(f"%{escaped}%")
            rows = conn.execute(
                "SELECT id,title,created_at,updated_at,deleted_at,purge_at FROM conversations "
                f"WHERE {' AND '.join(clauses)} ORDER BY updated_at DESC",
                tuple(params),
            ).fetchall()
        return {"items": [dict(row) for row in rows]}

    @app.get("/conversations/{conversation_id}/messages")
    def list_messages(conversation_id: str, user=Depends(current_user)):
        with db.connection() as conn:
            owned_conversation(conn, conversation_id, user["id"])
            rows = conn.execute(
                "SELECT id,role,content,risk_level,created_at FROM messages WHERE conversation_id=? ORDER BY rowid",
                (conversation_id,),
            ).fetchall()
        return {"items": [dict(row) for row in rows]}

    def owned_conversation(
        conn: sqlite3.Connection, conversation_id: str, user_id: str, *, include_deleted: bool = False
    ):
        row = conn.execute(
            "SELECT * FROM conversations WHERE id=? AND user_id=?", (conversation_id, user_id)
        ).fetchone()
        if not row or row["purged_at"] is not None or (row["deleted_at"] is not None and not include_deleted):
            raise ApiError("conversation_not_found", "对话不存在", 404)
        return row

    @app.patch("/conversations/{conversation_id}")
    def rename_conversation(
        conversation_id: str, body: ConversationRenameInput, user=Depends(current_user)
    ):
        title = body.title.strip()
        if not title:
            raise ApiError("invalid_title", "标题不能为空")
        with db.transaction(immediate=True) as conn:
            owned_conversation(conn, conversation_id, user["id"])
            conn.execute(
                "UPDATE conversations SET title=?,updated_at=? WHERE id=?",
                (title, _now(), conversation_id),
            )
        return {"id": conversation_id, "title": title}

    @app.delete("/conversations/{conversation_id}")
    def delete_conversation(conversation_id: str, user=Depends(current_user)):
        now = _now()
        with db.transaction(immediate=True) as conn:
            owned_conversation(conn, conversation_id, user["id"])
            active = conn.execute(
                "SELECT 1 FROM jobs j JOIN plans p ON p.id=j.plan_id WHERE p.conversation_id=? "
                "AND j.status IN ('queued','running','cancel_requested') LIMIT 1",
                (conversation_id,),
            ).fetchone()
            if active:
                raise ApiError("conversation_has_active_job", "生成进行中，暂时不能删除此会话", 409)
            conn.execute(
                "UPDATE conversations SET deleted_at=?,purge_at=?,updated_at=? WHERE id=?",
                (now, now + 30 * 86400, now, conversation_id),
            )
        return {"deleted_at": now, "purge_at": now + 30 * 86400}

    @app.post("/conversations/{conversation_id}/restore")
    def restore_conversation(conversation_id: str, user=Depends(current_user)):
        with db.transaction(immediate=True) as conn:
            conversation = owned_conversation(conn, conversation_id, user["id"], include_deleted=True)
            if conversation["deleted_at"] is None:
                raise ApiError("conversation_not_deleted", "对话不在回收站中", 409)
            now = _now()
            conn.execute(
                "UPDATE conversations SET deleted_at=NULL,purge_at=NULL,updated_at=? WHERE id=?",
                (now, conversation_id),
            )
        return {"restored": True}

    @app.get("/conversations/{conversation_id}")
    def get_conversation(conversation_id: str, user=Depends(current_user)):
        with db.connection() as conn:
            conversation = owned_conversation(conn, conversation_id, user["id"])
            messages = conn.execute(
                "SELECT id,role,content,risk_level,created_at FROM messages WHERE conversation_id=? ORDER BY rowid",
                (conversation_id,),
            ).fetchall()
            plans = conn.execute(
                "SELECT id,message_id,draft_id,duration_minutes,music_source,target_emotion,credential_mode,voice_mode,"
                "guidance_style,language_density,selected_voice_id,selected_music_asset_id,status,created_at "
                "FROM plans WHERE conversation_id=? ORDER BY created_at,id",
                (conversation_id,),
            ).fetchall()
            jobs = conn.execute(
                "SELECT j.id,j.plan_id,j.status,j.progress_stage,j.created_at,j.started_at,j.finished_at,"
                "j.error_code,j.retry_of_job_id,w.id AS work_id,w.title AS work_title,"
                "w.is_favorite,w.expires_at "
                "FROM jobs j JOIN plans p ON p.id=j.plan_id LEFT JOIN works w ON w.job_id=j.id "
                "WHERE p.conversation_id=? ORDER BY j.created_at,j.id",
                (conversation_id,),
            ).fetchall()
            draft = conn.execute(
                "SELECT * FROM plan_drafts WHERE conversation_id=?", (conversation_id,)
            ).fetchone()
        return {
            "conversation": dict(conversation),
            "messages": [dict(row) for row in messages],
            "plans": [dict(row) for row in plans],
            "jobs": [dict(row) for row in jobs],
            "draft": dict(draft) if draft else None,
        }

    @app.post("/conversations/{conversation_id}/messages", status_code=201)
    def create_message(conversation_id: str, body: MessageInput, user=Depends(current_user)):
        content = body.content.strip()
        if not content:
            raise ApiError("empty_message", "消息不能为空")
        risk = _risk_level(content)
        message_id, now = _id(), _now()
        with db.transaction(immediate=True) as conn:
            owned_conversation(conn, conversation_id, user["id"])
            conn.execute(
                "INSERT INTO messages(id,conversation_id,role,content,risk_level,created_at) VALUES(?,?,?,?,?,?)",
                (message_id, conversation_id, "user", content, risk, now),
            )
            conn.execute("UPDATE conversations SET updated_at=? WHERE id=?", (now, conversation_id))
        result = {"id": message_id, "risk_level": risk}
        if risk == "crisis":
            result["crisis_help"] = CRISIS_HELP
        return result

    @app.post("/conversations/{conversation_id}/plan-draft")
    def create_or_refresh_plan_draft(
        conversation_id: str, body: PlanDraftCreateInput, user=Depends(current_user)
    ):
        with db.connection() as conn:
            owned_conversation(conn, conversation_id, user["id"])
            rows = conn.execute(
                "SELECT role,content,risk_level FROM messages WHERE conversation_id=? ORDER BY rowid",
                (conversation_id,),
            ).fetchall()
            user_rows = [row for row in rows if row["role"] == "user"]
            if not user_rows:
                raise ApiError("conversation_empty", "请先说说你此刻的感受", 409)
            if user_rows[-1]["risk_level"] == "crisis":
                raise ApiError("crisis_generation_paused", "紧急风险信息不能直接进入生成", 409)
            if body.credential_mode == "byok":
                configured = conn.execute(
                    "SELECT deepseek_key FROM credentials WHERE user_id=?", (user["id"],)
                ).fetchone()
                if not configured:
                    raise ApiError("byok_not_configured", "请先配置 DeepSeek 和 MiniMax API Key", 409)
                planner_api_key = secrets.decrypt(configured["deepseek_key"])
            else:
                planner_api_key = os.getenv("DEEPSEEK_API_KEY", "")
            existing_row = conn.execute(
                "SELECT * FROM plan_drafts WHERE conversation_id=?", (conversation_id,)
            ).fetchone()
            if existing_row and existing_row["locked_at"] is not None:
                raise ApiError("plan_draft_locked", "该方案已经开始生成，请复制设置到新会话", 409)
            existing_snapshot = dict(existing_row) if existing_row else None

        bounded = _bounded_conversation_context(rows)
        suggestion = _generate_plan_draft(bounded, planner_api_key, existing_snapshot)
        now = _now()
        with db.transaction(immediate=True) as conn:
            owned_conversation(conn, conversation_id, user["id"])
            existing = conn.execute(
                "SELECT * FROM plan_drafts WHERE conversation_id=?", (conversation_id,)
            ).fetchone()
            if existing and existing["locked_at"] is not None:
                raise ApiError("plan_draft_locked", "该方案已经开始生成，请复制设置到新会话", 409)
            selected_music_asset_id = (
                existing["selected_music_asset_id"] if existing else None
            )
            if suggestion["music_source"] == "library" and not selected_music_asset_id:
                recommended = conn.execute(
                    "SELECT id FROM media_assets WHERE deleted_at IS NULL AND status='ready' "
                    "AND kind IN ('private_music','public_music') "
                    "AND (owner_user_id=? OR visibility='public') "
                    "ORDER BY CASE WHEN owner_user_id=? THEN 0 ELSE 1 END,"
                    "CASE WHEN primary_emotion=? THEN 0 ELSE 1 END,created_at DESC LIMIT 1",
                    (user["id"], user["id"], suggestion["primary_emotion"]),
                ).fetchone()
                selected_music_asset_id = recommended["id"] if recommended else None
            elif suggestion["music_source"] != "library":
                selected_music_asset_id = None
            if existing:
                conn.execute(
                    "UPDATE plan_drafts SET summary=?,primary_emotion=?,emotion_path=?,duration_minutes=?,"
                    "music_source=?,target_emotion=?,credential_mode=?,voice_mode=?,guidance_style=?,"
                    "language_density=?,selected_music_asset_id=?,updated_at=? WHERE conversation_id=?",
                    (
                        suggestion["summary"], suggestion["primary_emotion"], suggestion["emotion_path"],
                        suggestion["duration_minutes"], suggestion["music_source"], suggestion["target_emotion"],
                        body.credential_mode, suggestion["voice_mode"], suggestion["guidance_style"],
                        suggestion["language_density"], selected_music_asset_id, now, conversation_id,
                    ),
                )
                draft_id = existing["id"]
            else:
                draft_id = _id()
                conn.execute(
                    "INSERT INTO plan_drafts(id,conversation_id,summary,primary_emotion,emotion_path,"
                    "duration_minutes,music_source,target_emotion,credential_mode,voice_mode,guidance_style,"
                    "language_density,selected_music_asset_id,created_at,updated_at) "
                    "VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    (
                        draft_id, conversation_id, suggestion["summary"], suggestion["primary_emotion"],
                        suggestion["emotion_path"], suggestion["duration_minutes"], suggestion["music_source"],
                        suggestion["target_emotion"], body.credential_mode, suggestion["voice_mode"],
                        suggestion["guidance_style"], suggestion["language_density"],
                        selected_music_asset_id, now, now,
                    ),
                )
            draft = conn.execute("SELECT * FROM plan_drafts WHERE id=?", (draft_id,)).fetchone()
        return dict(draft)

    @app.patch("/conversations/{conversation_id}/plan-draft")
    def update_plan_draft(
        conversation_id: str, body: PlanDraftPatchInput, user=Depends(current_user)
    ):
        values = body.model_dump(exclude_none=True)
        if not values:
            raise ApiError("empty_update", "没有需要更新的设置")
        with db.transaction(immediate=True) as conn:
            owned_conversation(conn, conversation_id, user["id"])
            draft = conn.execute(
                "SELECT id,locked_at FROM plan_drafts WHERE conversation_id=?", (conversation_id,)
            ).fetchone()
            if not draft:
                raise ApiError("plan_draft_not_found", "请先生成冥想方案", 404)
            if draft["locked_at"] is not None:
                raise ApiError("plan_draft_locked", "该方案已经开始生成，请复制设置到新会话", 409)
            if values.get("credential_mode") == "byok":
                configured = conn.execute(
                    "SELECT 1 FROM credentials WHERE user_id=?", (user["id"],)
                ).fetchone()
                if not configured:
                    raise ApiError("byok_not_configured", "请先配置 DeepSeek 和 MiniMax API Key", 409)
            assignments = ",".join(f"{field}=?" for field in values)
            conn.execute(
                f"UPDATE plan_drafts SET {assignments},updated_at=? WHERE id=?",
                (*values.values(), _now(), draft["id"]),
            )
            updated = conn.execute("SELECT * FROM plan_drafts WHERE id=?", (draft["id"],)).fetchone()
        return {"draft": dict(updated)}

    @app.post("/conversations/{conversation_id}/plans", status_code=201)
    def create_plan(conversation_id: str, body: PlanInput, user=Depends(current_user)):
        plan_id, now = _id(), _now()
        with db.transaction(immediate=True) as conn:
            owned_conversation(conn, conversation_id, user["id"])
            message = conn.execute(
                "SELECT * FROM messages WHERE id=? AND conversation_id=? AND role='user'",
                (body.message_id, conversation_id),
            ).fetchone()
            if not message:
                raise ApiError("message_not_found", "消息不存在", 404)
            if message["risk_level"] == "crisis":
                raise ApiError("crisis_generation_paused", "紧急风险信息不能直接进入生成", 409)
            plan_values = {
                "duration_minutes": body.duration_minutes,
                "music_source": body.music_source,
                "target_emotion": body.target_emotion,
                "credential_mode": body.credential_mode,
                "voice_mode": body.voice_mode,
                "guidance_style": body.guidance_style,
                "language_density": body.language_density,
                "selected_voice_id": body.selected_voice_id,
                "selected_music_asset_id": body.selected_music_asset_id,
            }
            draft_primary_emotion = None
            if body.draft_id:
                existing_plan = conn.execute(
                    "SELECT id,status FROM plans WHERE draft_id=? AND conversation_id=?",
                    (body.draft_id, conversation_id),
                ).fetchone()
                if existing_plan:
                    return {
                        "id": existing_plan["id"], "status": existing_plan["status"],
                        "idempotent_replay": True,
                    }
                draft = conn.execute(
                    "SELECT * FROM plan_drafts WHERE id=? AND conversation_id=?",
                    (body.draft_id, conversation_id),
                ).fetchone()
                if not draft:
                    raise ApiError("plan_draft_not_found", "方案草稿不存在", 404)
                draft_primary_emotion = draft["primary_emotion"]
                for field in plan_values:
                    plan_values[field] = draft[field]
            if plan_values["credential_mode"] == "byok":
                credential = conn.execute("SELECT 1 FROM credentials WHERE user_id=?", (user["id"],)).fetchone()
                if not credential:
                    raise ApiError("byok_not_configured", "请先配置 DeepSeek 和 MiniMax API Key", 409)
            if plan_values["voice_mode"] == "pure_music":
                plan_values["selected_voice_id"] = None
            else:
                plan_values["selected_voice_id"] = (
                    plan_values["selected_voice_id"] or "female-chengshu-jingpin"
                )
                if plan_values["selected_voice_id"] != "female-chengshu-jingpin":
                    voice = conn.execute(
                        "SELECT 1 FROM voice_clones WHERE id=? AND user_id=? AND status='ready' "
                        "AND disabled_at IS NULL",
                        (plan_values["selected_voice_id"], user["id"]),
                    ).fetchone()
                    if not voice:
                        raise ApiError("voice_not_available", "所选音色不可用", 409)
            if (
                plan_values["music_source"] == "library"
                and not plan_values["selected_music_asset_id"]
            ):
                preferred_emotion = (
                    draft_primary_emotion
                    if plan_values["target_emotion"] == "auto"
                    else plan_values["target_emotion"]
                )
                recommended = conn.execute(
                    "SELECT id FROM media_assets WHERE deleted_at IS NULL AND status='ready' "
                    "AND kind IN ('private_music','public_music') "
                    "AND (owner_user_id=? OR visibility='public') "
                    "ORDER BY CASE WHEN owner_user_id=? THEN 0 ELSE 1 END,"
                    "CASE WHEN primary_emotion=? THEN 0 ELSE 1 END,created_at DESC LIMIT 1",
                    (user["id"], user["id"], preferred_emotion),
                ).fetchone()
                plan_values["selected_music_asset_id"] = (
                    recommended["id"] if recommended else None
                )
            if plan_values["selected_music_asset_id"]:
                asset = conn.execute(
                    "SELECT 1 FROM media_assets WHERE id=? AND deleted_at IS NULL AND status='ready' "
                    "AND kind IN ('private_music','public_music') "
                    "AND (owner_user_id=? OR visibility='public')",
                    (plan_values["selected_music_asset_id"], user["id"]),
                ).fetchone()
                if not asset:
                    raise ApiError("music_asset_not_available", "所选音乐不可用", 409)
            conn.execute(
                "INSERT INTO plans(id,conversation_id,message_id,duration_minutes,music_source,target_emotion,"
                "credential_mode,voice_mode,guidance_style,language_density,selected_voice_id,"
                "selected_music_asset_id,draft_id,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    plan_id, conversation_id, body.message_id, plan_values["duration_minutes"],
                    plan_values["music_source"], plan_values["target_emotion"],
                    plan_values["credential_mode"], plan_values["voice_mode"],
                    plan_values["guidance_style"], plan_values["language_density"],
                    plan_values["selected_voice_id"], plan_values["selected_music_asset_id"],
                    body.draft_id, now,
                ),
            )
            if body.draft_id:
                conn.execute(
                    "UPDATE plan_drafts SET locked_at=?,updated_at=? WHERE id=?",
                    (now, now, body.draft_id),
                )
        return {"id": plan_id, "status": "pending"}

    @app.post("/conversations/{conversation_id}/assistant-stream")
    def assistant_stream(conversation_id: str, body: AssistantStreamInput, user=Depends(current_user)):
        with db.connection() as conn:
            owned_conversation(conn, conversation_id, user["id"])
            message = conn.execute(
                "SELECT content,risk_level FROM messages WHERE id=? AND conversation_id=? AND role='user'",
                (body.message_id, conversation_id),
            ).fetchone()
            if not message:
                raise ApiError("message_not_found", "消息不存在", 404)
            if message["risk_level"] == "crisis":
                raise ApiError("crisis_generation_paused", "紧急风险信息不能进入助手对话", 409)
            context_rows = conn.execute(
                "SELECT role,content FROM messages WHERE conversation_id=? ORDER BY rowid",
                (conversation_id,),
            ).fetchall()
            conversation_context = _bounded_conversation_context(context_rows)
            if body.credential_mode == "byok":
                credential = conn.execute("SELECT deepseek_key FROM credentials WHERE user_id=?", (user["id"],)).fetchone()
                if not credential:
                    raise ApiError("byok_not_configured", "请先配置 DeepSeek API Key", 409)
                api_key = secrets.decrypt(credential["deepseek_key"])
            else:
                api_key = os.getenv("DEEPSEEK_API_KEY", "")
        if not api_key:
            raise ApiError("platform_api_unavailable", "平台助手服务暂不可用", 503)

        def stream():
            response = None
            chunks: list[str] = []
            try:
                response = requests.post(
                    f"{os.getenv('DEEPSEEK_BASE_URL', 'https://api.deepseek.com/v1').rstrip('/')}/chat/completions",
                    headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                    json={
                        "model": os.getenv("DEEPSEEK_MODEL", "deepseek-chat"),
                        "stream": True,
                        "messages": [{
                            "role": "system",
                            "content": "你是AIMusicMed助手。只做简短、有边界的共情，必要时只问一个澄清问题；不做诊断，不声称替代专业治疗。用户尚未明确说完前，不要催促生成冥想。",
                        }, *conversation_context],
                    },
                    stream=True,
                    timeout=(10, 180),
                )
                response.raise_for_status()
                for raw in response.iter_lines(decode_unicode=True):
                    if not raw or not raw.startswith("data:"):
                        continue
                    data = raw[5:].strip()
                    if data == "[DONE]":
                        break
                    payload = json.loads(data)
                    delta = payload.get("choices", [{}])[0].get("delta", {}).get("content", "")
                    if delta:
                        chunks.append(delta)
                        yield f"data: {json.dumps({'delta': delta}, ensure_ascii=False)}\n\n"
                content = "".join(chunks).strip()
                if content:
                    now = _now()
                    with db.transaction(immediate=True) as conn:
                        conn.execute(
                            "INSERT INTO messages(id,conversation_id,role,content,risk_level,created_at) VALUES(?,?,?,?,?,?)",
                            (_id(), conversation_id, "assistant", content, "normal", now),
                        )
                        conn.execute("UPDATE conversations SET updated_at=? WHERE id=?", (now, conversation_id))
                yield "event: done\ndata: {}\n\n"
            except (requests.RequestException, ValueError, KeyError):
                yield 'event: error\ndata: {"code":"assistant_unavailable"}\n\n'
            finally:
                if response is not None:
                    response.close()

        return StreamingResponse(stream(), media_type="text/event-stream")

    def enqueue_job(plan_id: str | None, user, retry_of_job_id: str | None = None):
        job_id, now = _id(), _now()
        if not _disk_status(settings)["generation_allowed"]:
            admin_alert(
                "disk_generation_stop",
                "磁盘保护已停止生成",
                "磁盘使用率达到 90% 或仍处于保护状态；低于 75% 后自动恢复。",
            )
            raise ApiError("storage_protected", "存储空间达到临界值，暂时停止生成", 507)
        relpath = f"users/{user['id']}/jobs/{job_id}/meditation.wav"
        day_start = ((now + 8 * 3600) // 86400) * 86400 - 8 * 3600
        with db.transaction(immediate=True) as conn:
            existing = None
            if retry_of_job_id:
                original = conn.execute(
                    "SELECT plan_id,status FROM jobs WHERE id=? AND user_id=?",
                    (retry_of_job_id, user["id"]),
                ).fetchone()
                if not original:
                    raise ApiError("job_not_found", "任务不存在", 404)
                if original["status"] not in ("failed", "cancelled"):
                    raise ApiError("job_not_retryable", "只有失败或已取消的任务可以重试", 409)
                plan_id = original["plan_id"]
            elif plan_id:
                existing = conn.execute(
                    "SELECT id,status FROM jobs WHERE plan_id=? AND user_id=? ORDER BY created_at LIMIT 1",
                    (plan_id, user["id"]),
                ).fetchone()
            if not plan_id:
                raise ApiError("plan_not_found", "方案不存在", 404)
            plan = conn.execute(
                "SELECT p.* FROM plans p JOIN conversations c ON c.id=p.conversation_id "
                "WHERE p.id=? AND c.user_id=? AND c.deleted_at IS NULL AND c.purged_at IS NULL",
                (plan_id, user["id"]),
            ).fetchone()
            if not plan:
                raise ApiError("plan_not_found", "方案不存在", 404)
            if existing:
                return {
                    "id": existing["id"], "status": existing["status"],
                    "idempotent_replay": True,
                }
            active = conn.execute(
                "SELECT 1 FROM jobs WHERE user_id=? AND status IN ('queued','running','cancel_requested') LIMIT 1",
                (user["id"],),
            ).fetchone()
            if active:
                raise ApiError("user_job_limit", "每位用户同时只能生成一个任务", 409)
            if plan["credential_mode"] == "platform":
                used = conn.execute(
                    "SELECT COUNT(*) FROM jobs WHERE user_id=? AND credential_mode='platform' "
                    "AND created_at>=? AND status IN ('queued','running','cancel_requested','succeeded')",
                    (user["id"], day_start),
                ).fetchone()[0]
                if used >= user["daily_limit"]:
                    raise ApiError("daily_limit_reached", "今日生成额度已用完", 429)
            conn.execute(
                "INSERT INTO jobs(id,user_id,plan_id,status,credential_mode,output_relpath,created_at,retry_of_job_id,"
                "selected_voice_id,selected_music_asset_id) VALUES(?,?,?,?,?,?,?,?,?,?)",
                (
                    job_id, user["id"], plan_id, "queued", plan["credential_mode"], relpath, now,
                    retry_of_job_id, plan["selected_voice_id"], plan["selected_music_asset_id"],
                ),
            )
            conn.execute(
                "INSERT INTO job_events(job_id,event_type,stage,message,created_at) VALUES(?,?,?,?,?)",
                (job_id, "status", "queued", "任务已排队", now),
            )
        result = {"id": job_id, "status": "queued"}
        if retry_of_job_id:
            result["retry_of_job_id"] = retry_of_job_id
        return result

    @app.post("/plans/{plan_id}/jobs", status_code=201)
    def create_job(plan_id: str, user=Depends(current_user)):
        return enqueue_job(plan_id, user)

    @app.get("/jobs/{job_id}")
    def get_job(job_id: str, user=Depends(current_user)):
        now = _now()
        with db.connection() as conn:
            job = conn.execute("SELECT * FROM jobs WHERE id=? AND user_id=?", (job_id, user["id"])).fetchone()
            if not job:
                raise ApiError("job_not_found", "任务不存在", 404)
            events = conn.execute(
                "SELECT id,event_type,stage,current,total,message,created_at FROM job_events WHERE job_id=? ORDER BY id",
                (job_id,),
            ).fetchall()
            latest_progress = conn.execute(
                "SELECT current,total FROM job_events WHERE job_id=? AND event_type='progress' "
                "ORDER BY id DESC LIMIT 1",
                (job_id,),
            ).fetchone()
        public_job = {key: job[key] for key in ("id", "status", "progress_stage", "created_at", "finished_at", "error_code")}
        start = job["started_at"] or job["created_at"]
        end = job["finished_at"] or now
        public_job["elapsed_seconds"] = max(0, end - start)
        public_job["current"] = latest_progress["current"] if latest_progress else None
        public_job["total"] = latest_progress["total"] if latest_progress else None
        public_job["retry_allowed"] = job["status"] in ("failed", "cancelled")
        return {"job": public_job, "events": [dict(row) for row in events]}

    @app.post("/jobs/{job_id}/editable-draft", status_code=201)
    def create_editable_draft_from_job(job_id: str, user=Depends(current_user)):
        now = _now()
        with db.transaction(immediate=True) as conn:
            source = conn.execute(
                "SELECT j.status AS job_status,j.plan_id,p.conversation_id,p.duration_minutes,"
                "p.music_source,p.target_emotion,p.credential_mode,p.voice_mode,p.guidance_style,"
                "p.language_density,c.deleted_at,c.purged_at "
                "FROM jobs j JOIN plans p ON p.id=j.plan_id "
                "JOIN conversations c ON c.id=p.conversation_id "
                "WHERE j.id=? AND j.user_id=? AND c.user_id=?",
                (job_id, user["id"], user["id"]),
            ).fetchone()
            if not source:
                raise ApiError("job_not_found", "任务不存在", 404)
            if source["job_status"] not in ("failed", "cancelled"):
                raise ApiError("job_not_editable", "只有失败或已取消的任务可以修改方案", 409)
            if source["deleted_at"] is not None or source["purged_at"] is not None:
                raise ApiError("conversation_deleted", "已删除的会话不能修改方案", 409)

            current = conn.execute(
                "SELECT * FROM plan_drafts WHERE conversation_id=?",
                (source["conversation_id"],),
            ).fetchone()
            if current and current["locked_at"] is None:
                if current["source_job_id"] == job_id:
                    return {**dict(current), "idempotent_replay": True}
                raise ApiError(
                    "editable_draft_exists", "当前会话已有可编辑方案，请先处理该方案", 409
                )

            if current:
                summary = current["summary"]
                primary_emotion = current["primary_emotion"]
                emotion_path = current["emotion_path"]
                conn.execute("DELETE FROM plan_drafts WHERE id=?", (current["id"],))
            else:
                context_rows = conn.execute(
                    "SELECT role,content FROM messages WHERE conversation_id=? ORDER BY rowid",
                    (source["conversation_id"],),
                ).fetchall()
                fallback = _fallback_plan_draft(_bounded_conversation_context(context_rows))
                summary = fallback["summary"]
                primary_emotion = fallback["primary_emotion"]
                emotion_path = fallback["emotion_path"]

            draft_id = _id()
            conn.execute(
                "INSERT INTO plan_drafts(id,conversation_id,summary,primary_emotion,emotion_path,"
                "duration_minutes,music_source,target_emotion,credential_mode,voice_mode,guidance_style,"
                "language_density,created_at,updated_at,locked_at,source_job_id) "
                "VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,NULL,?)",
                (
                    draft_id, source["conversation_id"], summary, primary_emotion, emotion_path,
                    source["duration_minutes"], source["music_source"], source["target_emotion"],
                    source["credential_mode"], source["voice_mode"], source["guidance_style"],
                    source["language_density"], now, now, job_id,
                ),
            )
            created = conn.execute(
                "SELECT * FROM plan_drafts WHERE id=?", (draft_id,)
            ).fetchone()
        return dict(created)

    @app.post("/jobs/{job_id}/retry", status_code=201)
    def retry_job(job_id: str, user=Depends(current_user)):
        return enqueue_job(None, user, retry_of_job_id=job_id)

    @app.post("/jobs/{job_id}/cancel")
    def cancel_job(job_id: str, user=Depends(current_user)):
        now = _now()
        with db.transaction(immediate=True) as conn:
            job = conn.execute("SELECT status FROM jobs WHERE id=? AND user_id=?", (job_id, user["id"])).fetchone()
            if not job:
                raise ApiError("job_not_found", "任务不存在", 404)
            if job["status"] == "queued":
                new_status = "cancelled"
                conn.execute("UPDATE jobs SET status=?,finished_at=? WHERE id=?", (new_status, now, job_id))
            elif job["status"] == "running":
                new_status = "cancel_requested"
                conn.execute("UPDATE jobs SET status=? WHERE id=?", (new_status, job_id))
            else:
                raise ApiError("job_not_cancellable", "当前任务无法取消", 409)
            conn.execute(
                "INSERT INTO job_events(job_id,event_type,stage,message,created_at) VALUES(?,?,?,?,?)",
                (job_id, "status", new_status, "已请求取消", now),
            )
        return {"status": new_status}

    @app.post("/internal/worker/claim", dependencies=[Depends(worker_auth)])
    def worker_claim():
        now = _now()
        with db.transaction(immediate=True) as conn:
            stale_before = now - 2 * 3600
            stale = conn.execute(
                "SELECT id FROM jobs WHERE status='running' AND heartbeat_at<?", (stale_before,)
            ).fetchall()
            for item in stale:
                conn.execute(
                    "UPDATE jobs SET status='failed',progress_stage='failed',finished_at=?,error_code='worker_lost' WHERE id=?",
                    (now, item["id"]),
                )
                conn.execute(
                    "INSERT INTO job_events(job_id,event_type,stage,message,created_at) VALUES(?,?,?,?,?)",
                    (item["id"], "status", "failed", "worker 超时，请手动重试", now),
                )
            running = conn.execute("SELECT COUNT(*) FROM jobs WHERE status IN ('running','cancel_requested')").fetchone()[0]
            if running >= settings.global_task_concurrency:
                return Response(status_code=204)
            job = conn.execute(
                "SELECT * FROM jobs WHERE status='queued' ORDER BY created_at,rowid LIMIT 1"
            ).fetchone()
            if not job:
                return Response(status_code=204)
            changed = conn.execute(
                "UPDATE jobs SET status='running',progress_stage='understanding',started_at=?,heartbeat_at=? "
                "WHERE id=? AND status='queued'",
                (now, now, job["id"]),
            ).rowcount
            if changed != 1:
                return Response(status_code=204)
            conn.execute(
                "INSERT INTO job_events(job_id,event_type,stage,message,created_at) VALUES(?,?,?,?,?)",
                (job["id"], "status", "understanding", "正在理解你的感受", now),
            )
            payload = conn.execute(
                "SELECT j.*,p.conversation_id,p.message_id,p.duration_minutes,p.music_source,p.target_emotion,"
                "p.voice_mode,p.guidance_style,p.language_density,p.selected_voice_id,"
                "p.selected_music_asset_id,m.content "
                "FROM jobs j JOIN plans p ON p.id=j.plan_id JOIN messages m ON m.id=p.message_id WHERE j.id=?",
                (job["id"],),
            ).fetchone()
            context_rows = conn.execute(
                "SELECT role,content FROM messages WHERE conversation_id=? AND rowid<="
                "(SELECT rowid FROM messages WHERE id=?) ORDER BY rowid",
                (payload["conversation_id"], payload["message_id"]),
            ).fetchall()
            bounded_context = _bounded_conversation_context(context_rows)
            credential = None
            if payload["credential_mode"] == "byok":
                credential = conn.execute("SELECT * FROM credentials WHERE user_id=?", (payload["user_id"],)).fetchone()
            selected_voice_provider_id = payload["selected_voice_id"]
            if selected_voice_provider_id and selected_voice_provider_id != "female-chengshu-jingpin":
                voice = conn.execute(
                    "SELECT provider_voice_id FROM voice_clones WHERE id=? AND user_id=? "
                    "AND status IN ('ready','disabled')",
                    (selected_voice_provider_id, payload["user_id"]),
                ).fetchone()
                if not voice:
                    raise ApiError("voice_not_available", "selected voice is not available", 409)
                selected_voice_provider_id = voice["provider_voice_id"]
            selected_music = None
            if payload["selected_music_asset_id"]:
                music = conn.execute(
                    "SELECT storage_relpath,filename,primary_emotion,edit_params_json "
                    "FROM media_assets WHERE id=? AND deleted_at IS NULL "
                    "AND status='ready' AND (owner_user_id=? OR visibility='public')",
                    (payload["selected_music_asset_id"], payload["user_id"]),
                ).fetchone()
                if not music:
                    raise ApiError("music_asset_not_available", "selected music is not available", 409)
                tags = conn.execute(
                    "SELECT tag FROM media_asset_tags WHERE asset_id=? ORDER BY tag",
                    (payload["selected_music_asset_id"],),
                ).fetchall()
                selected_music = {
                    "path": str(safe_storage_path(settings.storage_root, music["storage_relpath"])),
                    "name": music["filename"],
                    "primary_emotion": music["primary_emotion"],
                    "tags": [tag["tag"] for tag in tags],
                    "edit": json.loads(music["edit_params_json"] or "{}"),
                }
        output_path = safe_storage_path(settings.storage_root, payload["output_relpath"])
        output_path.parent.mkdir(parents=True, exist_ok=True)
        generation_context = "\n".join(
            f"{'语境摘要' if item['role'] == 'system' else ('用户' if item['role'] == 'user' else '助手')}：{item['content']}"
            for item in bounded_context
        )
        result = {
            "id": payload["id"], "user_id": payload["user_id"],
            "content": generation_context or payload["content"],
            "duration_minutes": payload["duration_minutes"], "music_source": payload["music_source"],
            "target_emotion": payload["target_emotion"], "credential_mode": payload["credential_mode"],
            "voice_mode": payload["voice_mode"], "guidance_style": payload["guidance_style"],
            "language_density": payload["language_density"],
            "selected_voice_id": payload["selected_voice_id"],
            "provider_voice_id": selected_voice_provider_id,
            "selected_music_asset_id": payload["selected_music_asset_id"],
            "selected_music": selected_music,
            "output_path": str(output_path),
        }
        if credential:
            result["credentials"] = {
                "deepseek_api_key": secrets.decrypt(credential["deepseek_key"]),
                "minimax_api_key": secrets.decrypt(credential["minimax_key"]),
                "elevenlabs_api_key": secrets.decrypt(credential["elevenlabs_key"]) if credential["elevenlabs_key"] else None,
            }
        return result

    @app.post("/internal/worker/jobs/{job_id}/events", dependencies=[Depends(worker_auth)])
    def worker_event(job_id: str, body: WorkerEventInput):
        now = _now()
        with db.transaction(immediate=True) as conn:
            job = conn.execute("SELECT status FROM jobs WHERE id=?", (job_id,)).fetchone()
            if not job or job["status"] not in ("running", "cancel_requested"):
                raise ApiError("worker_job_not_active", "job is not active", 409)
            conn.execute("UPDATE jobs SET progress_stage=?,heartbeat_at=? WHERE id=?", (body.stage, now, job_id))
            conn.execute(
                "INSERT INTO job_events(job_id,event_type,stage,current,total,message,created_at) VALUES(?,?,?,?,?,?,?)",
                (job_id, "progress", body.stage, body.current, body.total, body.message, now),
            )
        return {"cancel_requested": job["status"] == "cancel_requested"}

    @app.post("/internal/worker/jobs/{job_id}/heartbeat", dependencies=[Depends(worker_auth)])
    def worker_heartbeat(job_id: str):
        with db.transaction(immediate=True) as conn:
            job = conn.execute("SELECT status FROM jobs WHERE id=?", (job_id,)).fetchone()
            if not job or job["status"] not in ("running", "cancel_requested"):
                raise ApiError("worker_job_not_active", "job is not active", 409)
            conn.execute("UPDATE jobs SET heartbeat_at=? WHERE id=?", (_now(), job_id))
        return {"cancel_requested": job["status"] == "cancel_requested"}

    @app.post("/internal/worker/jobs/{job_id}/complete", dependencies=[Depends(worker_auth)])
    def worker_complete(job_id: str, body: WorkerCompleteInput):
        now = _now()
        with db.transaction(immediate=True) as conn:
            job = conn.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone()
            if not job or job["status"] != "running":
                raise ApiError("worker_job_not_active", "job is not running", 409)
            output = safe_storage_path(settings.storage_root, job["output_relpath"])
            if not output.is_file() or output.stat().st_size <= 0:
                raise ApiError("artifact_missing", "worker output is missing", 409)
            work_id = _id()
            mp3_relpath = str(Path(job["output_relpath"]).with_suffix(".mp3")).replace("\\", "/")
            txt_relpath = str(Path(job["output_relpath"]).with_suffix(".txt")).replace("\\", "/")
            if not safe_storage_path(settings.storage_root, mp3_relpath).is_file():
                raise ApiError("artifact_missing", "worker MP3 output is missing", 409)
            if not safe_storage_path(settings.storage_root, txt_relpath).is_file():
                raise ApiError("artifact_missing", "worker guidance output is missing", 409)
            conn.execute(
                "INSERT INTO works(id,job_id,user_id,title,file_relpath,mp3_relpath,txt_relpath,expires_at,created_at) "
                "VALUES(?,?,?,?,?,?,?,?,?)",
                (work_id, job_id, job["user_id"], body.title, job["output_relpath"], mp3_relpath,
                 txt_relpath, now + 30 * 86400, now),
            )
            conn.execute(
                "UPDATE jobs SET status='succeeded',progress_stage='complete',finished_at=?,heartbeat_at=? WHERE id=?",
                (now, now, job_id),
            )
            conn.execute(
                "INSERT INTO job_events(job_id,event_type,stage,message,created_at) VALUES(?,?,?,?,?)",
                (job_id, "status", "complete", "音乐冥想已完成", now),
            )
            conn.execute(
                "INSERT INTO notifications(id,user_id,title,body,kind,dedupe_key,created_at)"
                " VALUES(?,?,?,?,?,?,?)",
                (_id(), job["user_id"], "生成完成", "你的音乐冥想已经生成完成。", "success",
                 f"job-complete:{job_id}", now),
            )
        return {"work_id": work_id}

    @app.post("/internal/worker/jobs/{job_id}/fail", dependencies=[Depends(worker_auth)])
    def worker_fail(job_id: str, body: WorkerFailInput):
        now = _now()
        with db.transaction(immediate=True) as conn:
            job = conn.execute("SELECT status,user_id FROM jobs WHERE id=?", (job_id,)).fetchone()
            if not job or job["status"] not in ("running", "cancel_requested"):
                raise ApiError("worker_job_not_active", "job is not active", 409)
            final_status = "cancelled" if job["status"] == "cancel_requested" else "failed"
            conn.execute(
                "UPDATE jobs SET status=?,progress_stage=?,finished_at=?,heartbeat_at=?,error_code=? WHERE id=?",
                (final_status, final_status, now, now, body.error_code, job_id),
            )
            conn.execute(
                "INSERT INTO job_events(job_id,event_type,stage,message,created_at) VALUES(?,?,?,?,?)",
                (job_id, "status", final_status, "任务已取消" if final_status == "cancelled" else "生成失败", now),
            )
            if final_status == "failed":
                conn.execute(
                    "INSERT INTO notifications(id,user_id,title,body,kind,dedupe_key,created_at)"
                    " VALUES(?,?,?,?,?,?,?)",
                    (_id(), job["user_id"], "生成失败", "任务未能完成，请稍后重试。", "warning",
                     f"job-failed:{job_id}", now),
                )
        return {"status": final_status}

    @app.get("/works")
    def list_works(favorites_only: bool = False, user=Depends(current_user)):
        clauses = ["user_id=?", "deleted_at IS NULL"]
        params: list[object] = [user["id"]]
        if favorites_only:
            clauses.append("is_favorite=1")
        with db.connection() as conn:
            rows = conn.execute(
                "SELECT id,job_id,title,file_relpath,mp3_relpath,expires_at,is_favorite,created_at FROM works "
                f"WHERE {' AND '.join(clauses)} ORDER BY created_at DESC,id DESC",
                tuple(params),
            ).fetchall()
        now = _now()
        items = []
        for row in rows:
            item = dict(row)
            preferred_relpath = row["mp3_relpath"] or row["file_relpath"]
            item["audio_available"] = bool(
                safe_storage_path(settings.storage_root, preferred_relpath).is_file()
                and (row["is_favorite"] or row["expires_at"] is None or row["expires_at"] > now)
            )
            item.pop("file_relpath", None)
            item.pop("mp3_relpath", None)
            items.append(item)
        return {"items": items}

    @app.get("/works/{work_id}/download")
    def download_work(work_id: str, format: Literal["wav", "mp3", "txt"] = "mp3", user=Depends(current_user)):
        with db.connection() as conn:
            work = conn.execute("SELECT * FROM works WHERE id=?", (work_id,)).fetchone()
        if not work or work["user_id"] != user["id"] or work["deleted_at"] is not None:
            raise ApiError("work_not_found", "作品不存在", 404)
        if format != "txt" and not work["is_favorite"] and work["expires_at"] is not None and work["expires_at"] <= _now():
            raise ApiError("audio_expired", "音频已过期或不存在", 410)
        relpath = {"wav": work["file_relpath"], "mp3": work["mp3_relpath"], "txt": work["txt_relpath"]}[format]
        path = safe_storage_path(settings.storage_root, relpath)
        if not path.is_file():
            raise ApiError("audio_expired", "音频已过期或不存在", 410)
        media = {"wav": "audio/wav", "mp3": "audio/mpeg", "txt": "text/plain; charset=utf-8"}[format]
        return FileResponse(path, media_type=media, filename=f"{work['title']}.{format}")

    @app.post("/works/{work_id}/favorite")
    def favorite_work(work_id: str, user=Depends(current_user)):
        return set_favorite(work_id, user["id"], True)

    @app.delete("/works/{work_id}/favorite")
    def unfavorite_work(work_id: str, user=Depends(current_user)):
        return set_favorite(work_id, user["id"], False)

    def set_favorite(work_id: str, user_id: str, value: bool):
        with db.transaction(immediate=True) as conn:
            work = conn.execute(
                "SELECT * FROM works WHERE id=? AND user_id=? AND deleted_at IS NULL", (work_id, user_id)
            ).fetchone()
            if not work:
                raise ApiError("work_not_found", "作品不存在", 404)
            if value:
                preferred_relpath = work["mp3_relpath"] or work["file_relpath"]
                if (
                    (work["expires_at"] is not None and work["expires_at"] <= _now())
                    or not safe_storage_path(settings.storage_root, preferred_relpath).is_file()
                ):
                    raise ApiError("audio_expired", "音频已过期，无法收藏", 410)
            conn.execute(
                "UPDATE works SET is_favorite=? WHERE id=? AND user_id=?",
                (int(value), work_id, user_id),
            )
        return {"is_favorite": value}

    app.include_router(create_operations_router(
        db=db,
        settings=settings,
        current_user=current_user,
        admin_user=admin_user,
        worker_auth=worker_auth,
        send_email=send_email,
        admin_alert=admin_alert,
        secrets=secrets,
        error=ApiError,
    ))
    return app


def safe_storage_path(root: Path, relative: str) -> Path:
    root = root.resolve()
    candidate = (root / relative).resolve()
    try:
        candidate.relative_to(root)
    except ValueError as exc:
        raise ApiError("unsafe_storage_path", "unsafe storage path", 500) from exc
    return candidate


def secrets_compare(left: str, right: str) -> bool:
    import hmac

    return hmac.compare_digest(left.encode("utf-8"), right.encode("utf-8"))
