from fastapi import (
    APIRouter,
    Cookie,
    Depends,
    File,
    Form,
    Header,
    HTTPException,
    Request,
    Response,
    UploadFile,
)
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import get_db
from app.services import admin as svc
from app.services import admin_key as key_svc

router = APIRouter(prefix="/api/admin", tags=["admin"])


class LoginResponse(BaseModel):
    token: str


class VerifyResponse(BaseModel):
    valid: bool


def _client_ip(request: Request) -> str:
    """Real caller, not the proxy.

    Every request arrives through Vercel's rewrite and then Caddy, so
    ``request.client.host`` is the same address for everybody — one scanner
    would rate-limit Bektas out of his own site. The leftmost X-Forwarded-For
    entry is client-supplied and therefore only trustworthy enough for
    bucketing, which is all it is used for.
    """
    forwarded = request.headers.get("x-forwarded-for", "")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


@router.post("/login", response_model=LoginResponse)
async def login(
    request: Request,
    response: Response,
    file: UploadFile | None = File(default=None),
    key: str | None = Form(default=None),
    db: Session = Depends(get_db),
):
    """Log in with the key file.

    Two ways in, one credential: upload ``bekonai.key`` or paste its contents.
    Phones make file pickers awkward, so the paste path is a first-class door,
    not a fallback — both are validated identically here.
    """
    ip = _client_ip(request)

    rate_error = svc.check_rate_limit(ip)
    if rate_error:
        raise HTTPException(status_code=429, detail=rate_error)

    payload = key or ""
    if file is not None:
        raw = await file.read(key_svc.MAX_PAYLOAD_BYTES + 1)
        if len(raw) > key_svc.MAX_PAYLOAD_BYTES:
            raise HTTPException(status_code=413, detail="That file is not a key file")
        payload = raw.decode("utf-8", errors="ignore")

    secret = key_svc.extract_secret(payload) if payload else None
    if not secret or not key_svc.verify_secret(db, secret):
        svc.record_failed_attempt(ip)
        raise HTTPException(status_code=401, detail="Invalid key file")

    svc.clear_attempts(ip)
    token = svc.create_token()
    svc.set_session_cookie(response, token)
    return LoginResponse(token=token)


@router.get("/verify", response_model=VerifyResponse)
def verify(
    authorization: str = Header(default=""),
    bk_admin: str = Cookie(default=""),
):
    # Header first, cookie second — a browser with a cleared localStorage still
    # has the HttpOnly cookie, and that is what keeps the 30-day session alive.
    token = authorization.removeprefix("Bearer ").strip() or bk_admin
    if not token:
        return VerifyResponse(valid=False)
    return VerifyResponse(valid=svc.verify_token(token))


@router.post("/logout")
def logout(response: Response):
    svc.clear_session_cookie(response)
    return {"ok": True}
