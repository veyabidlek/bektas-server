import os
import time
from datetime import datetime, timedelta, timezone

import jwt
from dotenv import load_dotenv
from fastapi import Response

load_dotenv()

JWT_SECRET = os.getenv("JWT_SECRET")

if not JWT_SECRET:
    raise RuntimeError(
        "JWT_SECRET must be set in the environment. Refusing to start with a "
        "default — that would let anyone mint an admin token."
    )

JWT_ALGORITHM = "HS256"

# Bektas asked for a month-long session (2026-08-08): he logs in from a phone
# with a key file, and re-uploading it every day would be miserable. The token
# is signed with JWT_SECRET (which lives in .env, not in memory), so a container
# restart does not sign anyone out.
JWT_EXPIRY_DAYS = 30
SESSION_MAX_AGE_SECONDS = JWT_EXPIRY_DAYS * 24 * 60 * 60

# Mirrored into an HttpOnly cookie so the session survives a cleared
# localStorage and is not readable by injected JavaScript.
SESSION_COOKIE = "bk_admin"
# Off only for local http development; prod is https end to end.
COOKIE_SECURE = os.getenv("SESSION_COOKIE_SECURE", "true").lower() != "false"

MAX_ATTEMPTS = 5
BLOCK_DURATION_SECONDS = 15 * 60

# In-memory rate limiter: {ip: {"count": int, "blocked_until": float}}
_rate_limits: dict[str, dict[str, float]] = {}


def check_rate_limit(ip: str) -> str | None:
    """Returns error message if rate limited, None if ok."""
    entry = _rate_limits.get(ip)
    if not entry:
        return None

    if entry.get("blocked_until", 0) > time.time():
        remaining = int(entry["blocked_until"] - time.time())
        return f"Too many attempts. Try again in {remaining // 60 + 1} minutes."

    if entry.get("blocked_until", 0) <= time.time() and entry.get("count", 0) >= MAX_ATTEMPTS:
        _rate_limits.pop(ip, None)

    return None


def record_failed_attempt(ip: str) -> None:
    entry = _rate_limits.get(ip, {"count": 0, "blocked_until": 0})
    entry["count"] = entry.get("count", 0) + 1

    if entry["count"] >= MAX_ATTEMPTS:
        entry["blocked_until"] = time.time() + BLOCK_DURATION_SECONDS

    _rate_limits[ip] = entry


def clear_attempts(ip: str) -> None:
    _rate_limits.pop(ip, None)


def create_token() -> str:
    payload = {
        "sub": "admin",
        "exp": datetime.now(timezone.utc) + timedelta(days=JWT_EXPIRY_DAYS),
        "iat": datetime.now(timezone.utc),
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


def set_session_cookie(response: Response, token: str) -> None:
    """Persist the session for 30 days.

    HttpOnly so injected script cannot read it, SameSite=Lax so it still rides
    along on a normal navigation back to the site. Secure is on by default and
    only switched off for local http development.
    """
    response.set_cookie(
        SESSION_COOKIE,
        token,
        max_age=SESSION_MAX_AGE_SECONDS,
        httponly=True,
        secure=COOKIE_SECURE,
        samesite="lax",
        path="/",
    )


def clear_session_cookie(response: Response) -> None:
    response.delete_cookie(SESSION_COOKIE, path="/")


def verify_token(token: str) -> bool:
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
    except (jwt.ExpiredSignatureError, jwt.InvalidTokenError):
        return False
    # Friend tokens are signed with the same secret, so a valid signature alone
    # is not proof of admin — the subject has to say so.
    return payload.get("sub") == "admin"
