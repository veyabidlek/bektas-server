"""Hosted screenshots for the projects page.

Same storage shape as the diary's and a writing's photos — downscaled on write,
bytes on the Docker volume, metadata in SQLite — with two differences:

- **Unbound.** An image belongs to no project. The add-project form needs a URL
  before the project row exists, so the upload cannot take a project id.
- **Public serve.** A project card is public content; the picture has to load
  for a logged-out reader, so the GET route carries no auth dependency and the
  response may sit in a shared cache. Upload and delete stay admin-only.
"""

import os
import uuid
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy.orm import Session

from app.models.portfolio import PortfolioImage
from app.schemas.portfolio import PortfolioImageOut
from app.services.calendar import ASTANA
from app.services.image_optimize import dimensions, optimize_image

UPLOAD_DIR = Path(os.getenv("UPLOAD_DIR", "/data/uploads")) / "portfolio"

MAX_UPLOAD_BYTES = 25 * 1024 * 1024


def _now() -> str:
    return datetime.now(timezone.utc).astimezone(ASTANA).isoformat()


def out(image: PortfolioImage) -> PortfolioImageOut:
    return PortfolioImageOut(
        id=image.id,
        url=f"/api/portfolio/images/{image.id}",
        width=image.width,
        height=image.height,
        created_at=image.created_at,
    )


def add_image(db: Session, data: bytes, content_type: str) -> PortfolioImageOut:
    body, out_type, ext = optimize_image(data, content_type)
    width, height = dimensions(body)

    image_id = uuid.uuid4().hex[:12]
    filename = f"{image_id}.{ext}"

    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    (UPLOAD_DIR / filename).write_bytes(body)

    image = PortfolioImage(
        id=image_id,
        filename=filename,
        content_type=out_type,
        width=width,
        height=height,
        size_bytes=len(body),
        created_at=_now(),
    )
    db.add(image)
    db.commit()
    db.refresh(image)
    return out(image)


def get_image(db: Session, image_id: str) -> PortfolioImage | None:
    return db.query(PortfolioImage).filter(PortfolioImage.id == image_id).first()


def image_path(image: PortfolioImage) -> Path:
    return UPLOAD_DIR / image.filename


def delete_image(db: Session, image_id: str) -> bool:
    image = get_image(db, image_id)
    if not image:
        return False
    try:
        image_path(image).unlink(missing_ok=True)
    except OSError:
        pass  # a missing file must not block deleting the row
    db.delete(image)
    db.commit()
    return True
