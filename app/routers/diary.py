from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import require_admin
from app.schemas.diary import (
    DiaryEntryOut,
    DiaryEntrySummary,
    DiaryEntryUpdate,
    DiaryImageOut,
)
from app.services import diary as svc
from app.services.image_optimize import ALLOWED_CONTENT_TYPES

# Private, like the calendar: every route is admin-only, images included. There
# are no public URLs for diary photos — the bytes are served through an
# auth-checked route, never from a static directory.
router = APIRouter(prefix="/api/diary", tags=["diary"])


def _valid_day(day: str) -> str:
    if not svc.is_valid_day(day):
        raise HTTPException(status_code=422, detail="Day must be YYYY-MM-DD")
    return day


@router.get("/today", response_model=DiaryEntryOut)
def get_today(db: Session = Depends(get_db), _: None = Depends(require_admin)):
    """What the dashboard card asks: is today written yet?"""
    return svc.get_entry(db, svc.today())


@router.get("/entries", response_model=list[DiaryEntrySummary])
def list_entries(
    limit: int = 60,
    before: str | None = None,
    db: Session = Depends(get_db),
    _: None = Depends(require_admin),
):
    return svc.list_entries(db, limit=min(limit, 200), before=before)


@router.get("/entries/{day}", response_model=DiaryEntryOut)
def get_entry(day: str, db: Session = Depends(get_db), _: None = Depends(require_admin)):
    return svc.get_entry(db, _valid_day(day))


@router.put("/entries/{day}", response_model=DiaryEntryOut)
def put_entry(
    day: str,
    data: DiaryEntryUpdate,
    db: Session = Depends(get_db),
    _: None = Depends(require_admin),
):
    """Upsert: writing the same day again edits it, never duplicates it."""
    return svc.upsert_entry(db, _valid_day(day), data.body_md, data.title)


@router.delete("/entries/{day}", status_code=204)
def delete_entry(day: str, db: Session = Depends(get_db), _: None = Depends(require_admin)):
    if not svc.delete_entry(db, _valid_day(day)):
        raise HTTPException(status_code=404, detail="No entry for that day")


@router.post("/entries/{day}/images", response_model=list[DiaryImageOut], status_code=201)
async def upload_images(
    day: str,
    files: list[UploadFile] = File(...),
    db: Session = Depends(get_db),
    _: None = Depends(require_admin),
):
    _valid_day(day)
    saved: list[DiaryImageOut] = []

    for upload in files:
        content_type = (upload.content_type or "").lower()
        if content_type not in ALLOWED_CONTENT_TYPES:
            raise HTTPException(
                status_code=415, detail=f"Unsupported image type: {content_type or 'unknown'}"
            )

        data = await upload.read(svc.MAX_UPLOAD_BYTES + 1)
        if len(data) > svc.MAX_UPLOAD_BYTES:
            raise HTTPException(status_code=413, detail=f"{upload.filename} is too large")
        if not data:
            continue

        saved.append(svc.add_image(db, day, data, content_type))

    if not saved:
        raise HTTPException(status_code=422, detail="No image uploaded")
    return saved


@router.get("/images/{image_id}")
def serve_image(image_id: str, db: Session = Depends(get_db), _: None = Depends(require_admin)):
    """Serve a photo — admin only.

    A browser cannot put an Authorization header on an `<img>`, which is why
    login also sets the HttpOnly `bk_admin` cookie: it rides along on the image
    request automatically, and `require_admin` accepts it. Anonymous callers get
    401 here exactly as they do on the entry routes.
    """
    image = svc.get_image(db, image_id)
    if not image:
        raise HTTPException(status_code=404, detail="Image not found")

    path = svc.image_path(image)
    if not path.exists():
        raise HTTPException(status_code=404, detail="Image file missing")

    return FileResponse(
        path,
        media_type=image.content_type,
        # Private: never let a shared cache hold onto his photos.
        headers={"Cache-Control": "private, max-age=86400"},
    )


@router.delete("/images/{image_id}", status_code=204)
def delete_image(image_id: str, db: Session = Depends(get_db), _: None = Depends(require_admin)):
    if not svc.delete_image(db, image_id):
        raise HTTPException(status_code=404, detail="Image not found")
