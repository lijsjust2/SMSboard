"""认证：PBKDF2 密码哈希 + 手写 HMAC JWT（无第三方依赖）"""
import base64
import hashlib
import hmac
import json
import os
import time

from fastapi import Depends, HTTPException, Request
from sqlalchemy.orm import Session

from . import config
from .app_settings import admin_exists, get_setting
from .database import get_db

_SALT_LEN = 16
_ITERATIONS = 120_000


def hash_password(password: str) -> str:
    salt = os.urandom(_SALT_LEN)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, _ITERATIONS)
    return f"pbkdf2${_ITERATIONS}${salt.hex()}${dk.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        _, iters, salt_hex, dk_hex = stored.split("$")
        dk = hashlib.pbkdf2_hmac(
            "sha256", password.encode(), bytes.fromhex(salt_hex), int(iters)
        )
        return hmac.compare_digest(dk.hex(), dk_hex)
    except Exception:
        return False


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def _b64url_decode(s: str) -> bytes:
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))


def create_jwt(payload: dict) -> str:
    header = {"alg": "HS256", "typ": "JWT"}
    body = {**payload, "exp": int(time.time()) + config.JWT_EXPIRE_HOURS * 3600}
    h = _b64url(json.dumps(header, separators=(",", ":")).encode())
    p = _b64url(json.dumps(body, separators=(",", ":")).encode())
    sig = _b64url(hmac.new(config.JWT_SECRET.encode(), f"{h}.{p}".encode(), hashlib.sha256).digest())
    return f"{h}.{p}.{sig}"


def verify_jwt(token: str) -> dict | None:
    try:
        h, p, sig = token.split(".")
        expect = _b64url(
            hmac.new(config.JWT_SECRET.encode(), f"{h}.{p}".encode(), hashlib.sha256).digest()
        )
        if not hmac.compare_digest(sig, expect):
            return None
        body = json.loads(_b64url_decode(p))
        if body.get("exp", 0) < time.time():
            return None
        return body
    except Exception:
        return None


async def get_current_user(request: Request, db: Session = Depends(get_db)) -> dict:
    auth = request.headers.get("Authorization", "")
    token = auth[7:] if auth.startswith("Bearer ") else request.query_params.get("token", "")
    payload = verify_jwt(token) if token else None
    if not payload or not admin_exists(db):
        raise HTTPException(status_code=401, detail="未登录或登录已过期")
    return payload
