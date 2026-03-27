import os
import time
from datetime import datetime, timedelta, timezone

import jwt
from dotenv import load_dotenv

load_dotenv()

ADMIN_PASSCODE = os.getenv("ADMIN_PASSCODE", "300804")
JWT_SECRET = os.getenv("JWT_SECRET", "change-me-in-prod")
JWT_ALGORITHM = "HS256"
JWT_EXPIRY_HOURS = 24

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


def verify_passcode(passcode: str) -> bool:
    return passcode == ADMIN_PASSCODE


def create_token() -> str:
    payload = {
        "sub": "admin",
        "exp": datetime.now(timezone.utc) + timedelta(hours=JWT_EXPIRY_HOURS),
        "iat": datetime.now(timezone.utc),
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


def verify_token(token: str) -> bool:
    try:
        jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        return True
    except (jwt.ExpiredSignatureError, jwt.InvalidTokenError):
        return False
