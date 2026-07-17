from __future__ import annotations

import hashlib
import hmac
import secrets

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError
from cryptography.fernet import Fernet, InvalidToken


def new_token() -> str:
    return secrets.token_urlsafe(32)


def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def verification_code() -> str:
    return f"{secrets.randbelow(1_000_000):06d}"


def verification_code_hash(secret: str, challenge_id: str, code: str) -> str:
    return hmac.new(
        secret.encode("utf-8"), f"{challenge_id}:{code}".encode("utf-8"), hashlib.sha256
    ).hexdigest()


_PASSWORD_HASHER = PasswordHasher()


def hash_password(password: str) -> str:
    return _PASSWORD_HASHER.hash(password)


def verify_password(password_hash: str, password: str) -> bool:
    try:
        return _PASSWORD_HASHER.verify(password_hash, password)
    except (VerificationError, InvalidHashError):
        return False


class SecretBox:
    def __init__(self, key: str):
        try:
            self._fernet = Fernet(key.encode("ascii"))
        except (ValueError, TypeError) as exc:
            raise RuntimeError("AIMUSICMED_FERNET_KEY must be a valid Fernet key") from exc

    def encrypt(self, value: str) -> str:
        return self._fernet.encrypt(value.encode("utf-8")).decode("ascii")

    def decrypt(self, value: str) -> str:
        try:
            return self._fernet.decrypt(value.encode("ascii")).decode("utf-8")
        except InvalidToken as exc:
            raise RuntimeError("stored credential cannot be decrypted") from exc
