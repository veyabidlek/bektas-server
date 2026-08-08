"""Key-file admin login.

Replaces the passcode (2026-08-08). Logging in means handing the server the
contents of ``bekonai.key`` — either as an uploaded file or as pasted text.
Both paths end up here as one string, because the file *is* the string.

Only ``sha256(secret)`` is stored. The database is therefore not a copy of the
credential: someone who reads a backup still cannot log in.
"""

import base64
import hashlib
import hmac
import json
import secrets
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from sqlalchemy.orm import Session

from app.models.admin_key import AdminKey

ASTANA = ZoneInfo("Asia/Almaty")

SECRET_BYTES = 64
KEY_FILE_NAME = "bekonai.key"
# Refuse anything absurd before hashing — an uploaded photo should not become a
# 5 MB constant-time comparison.
MAX_PAYLOAD_BYTES = 64 * 1024


def _now() -> str:
    return datetime.now(timezone.utc).astimezone(ASTANA).isoformat()


def _hash(secret: str) -> str:
    return hashlib.sha256(secret.encode("utf-8")).hexdigest()


def extract_secret(payload: str) -> str | None:
    """Pull the secret out of whatever was handed to us.

    Accepts the whole key file (JSON with a ``key`` field) or a bare secret
    string pasted from a password manager. Anything else returns None.
    """
    text = payload.strip()
    if not text or len(text.encode("utf-8", "ignore")) > MAX_PAYLOAD_BYTES:
        return None

    if text.startswith("{"):
        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            return None
        if not isinstance(data, dict):
            return None
        key = data.get("key")
        return key.strip() if isinstance(key, str) and key.strip() else None

    # A bare paste: the base64 secret on its own, possibly wrapped across lines
    # by a notes app.
    compact = "".join(text.split())
    return compact or None


def verify_secret(db: Session, secret: str) -> AdminKey | None:
    """Constant-time match against every active key.

    Same shape as ``friends.verify_code``: hash first, then compare against all
    candidates so the timing does not reveal how much of the secret was right.
    """
    candidate = _hash(secret)
    match: AdminKey | None = None
    for key in db.query(AdminKey).filter(AdminKey.revoked == False).all():  # noqa: E712
        if hmac.compare_digest(candidate, key.secret_hash):
            match = key
    if match:
        match.last_used_at = _now()
        db.commit()
    return match


def issue_key(db: Session) -> dict:
    """Mint a new key file and revoke every previous one.

    Returns the key-file document. This is the *only* moment the secret exists
    in plaintext on the server — the caller writes it to disk and it is never
    recoverable afterwards.
    """
    db.query(AdminKey).filter(AdminKey.revoked == False).update(  # noqa: E712
        {AdminKey.revoked: True}
    )

    secret = base64.urlsafe_b64encode(secrets.token_bytes(SECRET_BYTES)).decode("ascii")
    key_id = secrets.token_hex(4)
    issued_at = _now()

    db.add(
        AdminKey(
            id=key_id,
            secret_hash=_hash(secret),
            issued_at=issued_at,
            revoked=False,
        )
    )
    db.commit()

    return {
        "v": 1,
        "site": "bektas.app",
        "id": key_id,
        "issued_at": issued_at,
        "key": secret,
    }


def has_active_key(db: Session) -> bool:
    return (
        db.query(AdminKey).filter(AdminKey.revoked == False).first() is not None  # noqa: E712
    )
