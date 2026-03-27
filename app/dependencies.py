from fastapi import Header, HTTPException

from app.services.admin import verify_token


def require_admin(authorization: str = Header(default="")) -> None:
    token = authorization.removeprefix("Bearer ").strip()
    if not token or not verify_token(token):
        raise HTTPException(status_code=401, detail="Unauthorized")
