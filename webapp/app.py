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


class MessageInput(BaseModel):
    content: str = Field(min_length=1, max_length=2000)


class PlanInput(BaseModel):
    message_id: str
    duration_minutes: int = Field(ge=3, le=15)
    music_source: Literal["library", "ai"] = "library"
    target_emotion: Literal["auto", "平静", "喜悦", "友爱", "自信"] = "auto"
    credential_mode: Literal["platform", "byok"] = "platform"
    voice_mode: Literal["tts", "pure_music"] = "tts"


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
    def admin_user_quota(user_id: str, body: QuotaInput, _admin=Depends(admin_user)):
        with db.transaction(immediate=True) as conn:
            changed = conn.execute(
                "UPDATE users SET daily_limit=? WHERE id=? AND role='user'",
                (body.daily_limit, user_id),
            ).rowcount
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
    def admin_user_status(user_id: str, body: UserStatusInput, _admin=Depends(admin_user)):
        now = _now()
        with db.transaction(immediate=True) as conn:
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
    def password_login(body: PasswordLoginInput, response: Response):
        email, now = _email(body.email), _now()
        invalid = False
        with db.transaction(immediate=True) as conn:
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
        if invalid:
            raise ApiError("invalid_credentials", "邮箱或密码错误", 401)
        set_session(response, user["id"])
        return {"authenticated": True, "password_setup": "none"}

    @app.put("/account/password")
    def set_account_password(body: PasswordInput, user=Depends(current_user)):
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

    @app.get("/conversations")
    def list_conversations(user=Depends(current_user)):
        with db.connection() as conn:
            rows = conn.execute(
                "SELECT id,title,created_at,updated_at FROM conversations WHERE user_id=? ORDER BY updated_at DESC",
                (user["id"],),
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

    def owned_conversation(conn: sqlite3.Connection, conversation_id: str, user_id: str):
        row = conn.execute(
            "SELECT * FROM conversations WHERE id=? AND user_id=?", (conversation_id, user_id)
        ).fetchone()
        if not row:
            raise ApiError("conversation_not_found", "对话不存在", 404)
        return row

    @app.get("/conversations/{conversation_id}")
    def get_conversation(conversation_id: str, user=Depends(current_user)):
        with db.connection() as conn:
            conversation = owned_conversation(conn, conversation_id, user["id"])
            messages = conn.execute(
                "SELECT id,role,content,risk_level,created_at FROM messages WHERE conversation_id=? ORDER BY rowid",
                (conversation_id,),
            ).fetchall()
            plans = conn.execute(
                "SELECT id,message_id,duration_minutes,music_source,target_emotion,credential_mode,voice_mode,status,created_at "
                "FROM plans WHERE conversation_id=? ORDER BY created_at,id",
                (conversation_id,),
            ).fetchall()
            jobs = conn.execute(
                "SELECT j.id,j.plan_id,j.status,j.progress_stage,j.created_at,j.finished_at,w.id AS work_id "
                "FROM jobs j JOIN plans p ON p.id=j.plan_id LEFT JOIN works w ON w.job_id=j.id "
                "WHERE p.conversation_id=? ORDER BY j.created_at,j.id",
                (conversation_id,),
            ).fetchall()
        return {
            "conversation": dict(conversation),
            "messages": [dict(row) for row in messages],
            "plans": [dict(row) for row in plans],
            "jobs": [dict(row) for row in jobs],
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
            if body.credential_mode == "byok":
                credential = conn.execute("SELECT 1 FROM credentials WHERE user_id=?", (user["id"],)).fetchone()
                if not credential:
                    raise ApiError("byok_not_configured", "请先配置 DeepSeek 和 MiniMax API Key", 409)
            conn.execute(
                "INSERT INTO plans(id,conversation_id,message_id,duration_minutes,music_source,target_emotion,credential_mode,voice_mode,created_at) "
                "VALUES(?,?,?,?,?,?,?,?,?)",
                (plan_id, conversation_id, body.message_id, body.duration_minutes, body.music_source,
                 body.target_emotion, body.credential_mode, body.voice_mode, now),
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
                        "messages": [
                            {"role": "system", "content": "你是AIMusicMed助手。只做简短、有边界的共情，必要时只问一个澄清问题；不做诊断，不声称替代专业治疗。"},
                            {"role": "user", "content": message["content"]},
                        ],
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

    @app.post("/plans/{plan_id}/jobs", status_code=201)
    def create_job(plan_id: str, user=Depends(current_user)):
        job_id, now = _id(), _now()
        relpath = f"users/{user['id']}/jobs/{job_id}/meditation.wav"
        day_start = ((now + 8 * 3600) // 86400) * 86400 - 8 * 3600
        with db.transaction(immediate=True) as conn:
            plan = conn.execute(
                "SELECT p.* FROM plans p JOIN conversations c ON c.id=p.conversation_id "
                "WHERE p.id=? AND c.user_id=?",
                (plan_id, user["id"]),
            ).fetchone()
            if not plan:
                raise ApiError("plan_not_found", "方案不存在", 404)
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
                "INSERT INTO jobs(id,user_id,plan_id,status,credential_mode,output_relpath,created_at) VALUES(?,?,?,?,?,?,?)",
                (job_id, user["id"], plan_id, "queued", plan["credential_mode"], relpath, now),
            )
            conn.execute(
                "INSERT INTO job_events(job_id,event_type,stage,message,created_at) VALUES(?,?,?,?,?)",
                (job_id, "status", "queued", "任务已排队", now),
            )
        return {"id": job_id, "status": "queued"}

    @app.get("/jobs/{job_id}")
    def get_job(job_id: str, user=Depends(current_user)):
        with db.connection() as conn:
            job = conn.execute("SELECT * FROM jobs WHERE id=? AND user_id=?", (job_id, user["id"])).fetchone()
            if not job:
                raise ApiError("job_not_found", "任务不存在", 404)
            events = conn.execute(
                "SELECT id,event_type,stage,current,total,message,created_at FROM job_events WHERE job_id=? ORDER BY id",
                (job_id,),
            ).fetchall()
        public_job = {key: job[key] for key in ("id", "status", "progress_stage", "created_at", "finished_at", "error_code")}
        return {"job": public_job, "events": [dict(row) for row in events]}

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
                "SELECT j.*,p.duration_minutes,p.music_source,p.target_emotion,p.voice_mode,m.content "
                "FROM jobs j JOIN plans p ON p.id=j.plan_id JOIN messages m ON m.id=p.message_id WHERE j.id=?",
                (job["id"],),
            ).fetchone()
            credential = None
            if payload["credential_mode"] == "byok":
                credential = conn.execute("SELECT * FROM credentials WHERE user_id=?", (payload["user_id"],)).fetchone()
        output_path = safe_storage_path(settings.storage_root, payload["output_relpath"])
        output_path.parent.mkdir(parents=True, exist_ok=True)
        result = {
            "id": payload["id"], "user_id": payload["user_id"], "content": payload["content"],
            "duration_minutes": payload["duration_minutes"], "music_source": payload["music_source"],
            "target_emotion": payload["target_emotion"], "credential_mode": payload["credential_mode"],
            "voice_mode": payload["voice_mode"],
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
        return {"work_id": work_id}

    @app.post("/internal/worker/jobs/{job_id}/fail", dependencies=[Depends(worker_auth)])
    def worker_fail(job_id: str, body: WorkerFailInput):
        now = _now()
        with db.transaction(immediate=True) as conn:
            job = conn.execute("SELECT status FROM jobs WHERE id=?", (job_id,)).fetchone()
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
        return {"status": final_status}

    @app.get("/works/{work_id}/download")
    def download_work(work_id: str, format: Literal["wav", "mp3", "txt"] = "mp3", user=Depends(current_user)):
        with db.connection() as conn:
            work = conn.execute("SELECT * FROM works WHERE id=?", (work_id,)).fetchone()
        if not work or work["user_id"] != user["id"]:
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
            changed = conn.execute(
                "UPDATE works SET is_favorite=? WHERE id=? AND user_id=?",
                (int(value), work_id, user_id),
            ).rowcount
        if not changed:
            raise ApiError("work_not_found", "作品不存在", 404)
        return {"is_favorite": value}

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
