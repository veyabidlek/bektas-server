import hmac
import secrets
import uuid
from datetime import datetime, timedelta, timezone

import jwt
from sqlalchemy.orm import Session

from app.models.friend import Friend
from app.services.admin import JWT_ALGORITHM, JWT_SECRET

# Friends stay signed in far longer than admin: they type the code once from a
# link and should not be re-prompted every day.
FRIEND_TOKEN_DAYS = 90
CODE_LENGTH = 6


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def generate_code(db: Session) -> str:
    """A short numeric code that is unique across friends."""
    for _ in range(50):
        code = "".join(secrets.choice("0123456789") for _ in range(CODE_LENGTH))
        if not db.query(Friend).filter(Friend.code == code).first():
            return code
    raise RuntimeError("Could not allocate a free friend code")


def list_friends(db: Session) -> list[Friend]:
    return db.query(Friend).order_by(Friend.created_at.desc()).all()


def create_friend(db: Session, name: str) -> Friend:
    friend = Friend(
        id=str(uuid.uuid4())[:8],
        name=name,
        code=generate_code(db),
        created_at=_now(),
        revoked=False,
    )
    db.add(friend)
    db.commit()
    db.refresh(friend)
    return friend


def set_revoked(db: Session, friend_id: str, revoked: bool) -> Friend | None:
    friend = db.query(Friend).filter(Friend.id == friend_id).first()
    if not friend:
        return None
    friend.revoked = revoked
    db.commit()
    db.refresh(friend)
    return friend


def delete_friend(db: Session, friend_id: str) -> bool:
    friend = db.query(Friend).filter(Friend.id == friend_id).first()
    if not friend:
        return False
    db.delete(friend)
    db.commit()
    return True


def verify_code(db: Session, code: str) -> Friend | None:
    """Constant-time match against every active code.

    Looking the code up with a WHERE would be faster, but this keeps the
    comparison time independent of how much of the code was right.
    """
    match: Friend | None = None
    for friend in db.query(Friend).filter(Friend.revoked == False).all():  # noqa: E712
        if hmac.compare_digest(code, friend.code):
            match = friend
    if match:
        match.last_seen_at = _now()
        db.commit()
    return match


def create_token(friend: Friend) -> str:
    payload = {
        "sub": "friend",
        "fid": friend.id,
        "exp": datetime.now(timezone.utc) + timedelta(days=FRIEND_TOKEN_DAYS),
        "iat": datetime.now(timezone.utc),
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


def friend_id_from_token(db: Session, token: str) -> str | None:
    """Returns the friend id if the token is valid and the friend is still active."""
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
    except (jwt.ExpiredSignatureError, jwt.InvalidTokenError):
        return None
    if payload.get("sub") != "friend":
        return None

    fid = payload.get("fid")
    if not fid:
        return None
    # Revoking a friend must kill tokens already issued to them.
    friend = db.query(Friend).filter(Friend.id == fid, Friend.revoked == False).first()  # noqa: E712
    return friend.id if friend else None
