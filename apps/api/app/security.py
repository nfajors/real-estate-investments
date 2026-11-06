"""Password hashing, JWT access tokens, refresh/invite tokens and signed URLs."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
import time
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

import jwt

from .config import get_settings

_SCRYPT_N, _SCRYPT_R, _SCRYPT_P = 2**14, 8, 1


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(password.encode(), salt=salt, n=_SCRYPT_N, r=_SCRYPT_R, p=_SCRYPT_P, dklen=32)
    return f"scrypt${_SCRYPT_N}${_SCRYPT_R}${_SCRYPT_P}${salt.hex()}${digest.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        algo, n, r, p, salt_hex, digest_hex = stored.split("$")
    except ValueError:
        return False
    if algo != "scrypt":
        return False
    digest = hashlib.scrypt(
        password.encode(), salt=bytes.fromhex(salt_hex), n=int(n), r=int(r), p=int(p), dklen=len(digest_hex) // 2
    )
    return hmac.compare_digest(digest.hex(), digest_hex)


def create_access_token(user_id: uuid.UUID) -> tuple[str, int]:
    s = get_settings()
    expires = datetime.now(timezone.utc) + timedelta(minutes=s.access_token_minutes)
    token = jwt.encode(
        {"sub": str(user_id), "type": "access", "exp": expires, "iat": datetime.now(timezone.utc),
         "jti": secrets.token_hex(8)},
        s.secret_key,
        algorithm="HS256",
    )
    return token, s.access_token_minutes * 60


def decode_access_token(token: str) -> uuid.UUID | None:
    try:
        payload = jwt.decode(token, get_settings().secret_key, algorithms=["HS256"])
    except jwt.PyJWTError:
        return None
    if payload.get("type") != "access":
        return None
    try:
        return uuid.UUID(payload["sub"])
    except (KeyError, ValueError):
        return None


def new_opaque_token() -> tuple[str, str]:
    """Random token for refresh/invite flows → (plaintext, sha256 hash stored in DB)."""
    token = secrets.token_urlsafe(32)
    return token, hash_token(token)


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


# ------------------------------------------------------------- signed URLs
def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode().rstrip("=")


def _unb64(data: str) -> bytes:
    return base64.urlsafe_b64decode(data + "=" * (-len(data) % 4))


def sign_payload(payload: dict[str, Any], ttl_seconds: int | None = None) -> str:
    s = get_settings()
    body = dict(payload)
    body["exp"] = int(time.time()) + (ttl_seconds or s.signed_url_seconds)
    raw = _b64(json.dumps(body, separators=(",", ":"), sort_keys=True).encode())
    sig = _b64(hmac.new(s.secret_key.encode(), raw.encode(), hashlib.sha256).digest())
    return f"{raw}.{sig}"


def verify_signed(token: str) -> dict[str, Any] | None:
    try:
        raw, sig = token.split(".")
    except ValueError:
        return None
    expected = _b64(hmac.new(get_settings().secret_key.encode(), raw.encode(), hashlib.sha256).digest())
    if not hmac.compare_digest(expected, sig):
        return None
    try:
        body = json.loads(_unb64(raw))
    except (ValueError, json.JSONDecodeError):
        return None
    if body.get("exp", 0) < time.time():
        return None
    return body
