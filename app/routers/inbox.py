from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import require_admin
from app.schemas.inbox import (
    InboxCount,
    InboxImageOut,
    InboxItemCreate,
    InboxItemOut,
    InboxItemUpdate,
    TriageRequest,
    TriageResult,
)
from app.services import inbox as svc
from app.services import inbox_triage as triage
from app.services.image_optimize import ALLOWED_CONTENT_TYPES

# Admin-only, images included — the inbox is a private staging area.
router = APIRouter(prefix="/api/inbox", tags=["inbox"])


@router.get("/count", response_model=InboxCount)
def count(db: Session = Depends(get_db), _: None = Depends(require_admin)):
    """Declared before /{item_id} routes so "count" is never read as an id."""
    return InboxCount(untriaged=svc.count_untriaged(db))


@router.get("", response_model=list[InboxItemOut])
def list_items(
    triaged: bool | None = None,
    db: Session = Depends(get_db),
    _: None = Depends(require_admin),
):
    return svc.list_items(db, triaged=triaged)


@router.post("", response_model=InboxItemOut, status_code=201)
def create_item(
    data: InboxItemCreate,
    db: Session = Depends(get_db),
    _: None = Depends(require_admin),
):
    """Capture. Text may be empty when the item is only a photo."""
    return svc.out(svc.create_item(db, data.text, data.source))


@router.put("/{item_id}", response_model=InboxItemOut)
def update_item(
    item_id: str,
    data: InboxItemUpdate,
    db: Session = Depends(get_db),
    _: None = Depends(require_admin),
):
    item = svc.get_item(db, item_id)
    if not item:
        raise HTTPException(status_code=404, detail="Item not found")
    return svc.out(svc.update_text(db, item, data.text))


@router.delete("/{item_id}", status_code=204)
def delete_item(
    item_id: str,
    db: Session = Depends(get_db),
    _: None = Depends(require_admin),
):
    item = svc.get_item(db, item_id)
    if not item:
        raise HTTPException(status_code=404, detail="Item not found")
    svc.delete_item(db, item)


@router.post("/{item_id}/triage", response_model=TriageResult)
def triage_item(
    item_id: str,
    data: TriageRequest,
    db: Session = Depends(get_db),
    _: None = Depends(require_admin),
):
    """Turn the item into a task / writing / event / diary line, or dismiss it."""
    item = svc.get_item(db, item_id)
    if not item:
        raise HTTPException(status_code=404, detail="Item not found")

    try:
        item, target_id = svc.triage_item(
            db,
            item,
            data.kind,
            title=data.title,
            due_at=data.due_at,
            starts_at=data.starts_at,
            reminder_minutes=data.reminder_minutes,
        )
    except triage.TriageError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    return TriageResult(item=svc.out(item), kind=data.kind, target_id=target_id)


# --- photos ---


@router.post("/{item_id}/images", response_model=list[InboxImageOut], status_code=201)
async def upload_images(
    item_id: str,
    files: list[UploadFile] = File(...),
    db: Session = Depends(get_db),
    _: None = Depends(require_admin),
):
    item = svc.get_item(db, item_id)
    if not item:
        raise HTTPException(status_code=404, detail="Item not found")

    saved: list[InboxImageOut] = []
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

        saved.append(svc.add_image(db, item, data, content_type))

    if not saved:
        raise HTTPException(status_code=422, detail="No image uploaded")
    return saved


@router.get("/images/{image_id}")
def serve_image(
    image_id: str,
    db: Session = Depends(get_db),
    _: None = Depends(require_admin),
):
    """Admin-only, like the diary's: nothing in the inbox is published yet."""
    image = svc.get_image(db, image_id)
    if not image:
        raise HTTPException(status_code=404, detail="Image not found")

    path = svc.image_path(image)
    if not path.exists():
        raise HTTPException(status_code=404, detail="Image file missing")

    return FileResponse(
        path,
        media_type=image.content_type,
        headers={"Cache-Control": "private, max-age=86400"},
    )


@router.delete("/images/{image_id}", status_code=204)
def delete_image(
    image_id: str,
    db: Session = Depends(get_db),
    _: None = Depends(require_admin),
):
    if not svc.delete_image(db, image_id):
        raise HTTPException(status_code=404, detail="Image not found")
