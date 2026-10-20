"""Accounts for the review panel: scrypt password hashes and short-lived signed tokens.

Only analysts and admins log in. People checking messages never need an account.
"""

import base64
import hashlib
import hmac
import json
import logging
import os
import time
from dataclasses import dataclass

from fastapi import HTTPException, Request
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.config import Settings
from app.db.models import User

log = logging.getLogger(__name__)

ROLES = ("analyst", "admin")
DEFAULT_SECRET = "dev-only-auth-secret-change-me"
_N, _R, _P = 2**14, 8, 1


def hash_password(password: str) -> str:
    salt = os.urandom(16)
    digest = hashlib.scrypt(password.encode(), salt=salt, n=_N, r=_R, p=_P, dklen=32)
    return f"scrypt${_N}${_R}${_P}${base64.b64encode(salt).decode()}${base64.b64encode(digest).decode()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        _, n, r, p, salt, digest = stored.split("$")
        expected = base64.b64decode(digest)
        actual = hashlib.scrypt(password.encode(), salt=base64.b64decode(salt), n=int(n), r=int(r), p=int(p), dklen=len(expected))
    except (ValueError, TypeError):
        return False
    return hmac.compare_digest(actual, expected)


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode().rstrip("=")


def _unb64(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


def make_token(settings: Settings, email: str, role: str) -> str:
    payload = _b64(json.dumps({"sub": email, "role": role, "exp": int(time.time()) + settings.token_hours * 3600}).encode())
    sig = _b64(hmac.new(settings.auth_secret.encode(), payload.encode(), hashlib.sha256).digest())
    return f"{payload}.{sig}"


def read_token(settings: Settings, token: str) -> dict | None:
    if not token.isascii() or login_available(settings):
        return None
    try:
        payload, sig = token.split(".")
    except ValueError:
        return None
    expected = _b64(hmac.new(settings.auth_secret.encode(), payload.encode(), hashlib.sha256).digest())
    if not hmac.compare_digest(sig, expected):
        return None
    try:
        data = json.loads(_unb64(payload))
    except (ValueError, json.JSONDecodeError):
        return None
    if data.get("exp", 0) < time.time() or data.get("role") not in ROLES:
        return None
    return data


def login_available(settings: Settings) -> str | None:
    """None if logging in (and accepting tokens) is allowed, else the reason it is not.

    The default secret is public, so anyone could sign a token with it. It is accepted only
    for local development and tests: never in production, and never with a real database."""
    weak = settings.auth_secret == DEFAULT_SECRET or len(settings.auth_secret) < 16
    if weak and (settings.app_env == "production" or settings.uses_postgres):
        return "Set AUTH_SECRET to a long random string (16+ characters) to enable the review panel."
    return None


@dataclass
class Principal:
    email: str
    role: str

    @property
    def is_admin(self) -> bool:
        return self.role == "admin"


async def principal_from_request(request: Request, role: str = "analyst") -> Principal:
    settings: Settings = request.app.state.settings
    header = request.headers.get("authorization", "")
    token = header[7:] if header.lower().startswith("bearer ") else ""
    problem = login_available(settings)
    if problem:
        raise HTTPException(503, problem)
    data = read_token(settings, token) if token else None
    if not data:
        raise HTTPException(401, "Log in to use the review panel.")
    async with request.app.state.deps.sessionmaker() as session:
        user = (await session.execute(select(User).where(User.email == data["sub"]))).scalar_one_or_none()
    if not user or not user.active:
        raise HTTPException(401, "This account is no longer active.")
    if role == "admin" and user.role != "admin":
        raise HTTPException(403, "Only an admin can do this.")
    return Principal(user.email, user.role)


async def require_analyst(request: Request) -> Principal:
    return await principal_from_request(request, "analyst")


async def require_admin(request: Request) -> Principal:
    return await principal_from_request(request, "admin")


async def bootstrap_admin(sessionmaker: async_sessionmaker, settings: Settings) -> bool:
    """Create the first admin from ADMIN_EMAIL / ADMIN_PASSWORD when there are no users yet."""
    if not settings.admin_email or not settings.admin_password:
        return False
    if len(settings.admin_password) < 10:
        log.warning("ADMIN_PASSWORD must be at least 10 characters; no admin was created.")
        return False
    async with sessionmaker() as session:
        if (await session.execute(select(func.count(User.id)))).scalar_one():
            return False
        session.add(User(email=settings.admin_email.lower().strip(), password_hash=hash_password(settings.admin_password), role="admin"))
        await session.commit()
    return True
