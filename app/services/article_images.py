"""Photos attached to writings.

Storage mirrors the diary's — downscaled on write, bytes on the Docker volume,
metadata in SQLite — but the *serving* rule is different: a writing has a
visibility level, and its photos must be exactly as reachable as the writing
itself. That check lives in `dependencies.can_view`; this module only resolves
which article an image belongs to.
"""

import os
import uuid
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy.orm import Session

from app.models.article import Article
from app.models.article_image import ArticleImage
from app.schemas.article import ArticleImageOut
from app.services.calendar import ASTANA
from app.services.image_optimize import dimensions, optimize_image

UPLOAD_DIR = Path(os.getenv("UPLOAD_DIR", "/data/uploads")) / "articles"

MAX_UPLOAD_BYTES = 25 * 1024 * 1024


def _now() -> str:
    return datetime.now(timezone.utc).astimezone(ASTANA).isoformat()


def _out(image: ArticleImage) -> ArticleImageOut:
    return ArticleImageOut(
        id=image.id,
        article_slug=image.article_slug,
        url=f"/api/articles/images/{image.id}",
        width=image.width,
        height=image.height,
        created_at=image.created_at,
    )


def out(image: ArticleImage) -> ArticleImageOut:
    return _out(image)


def list_images(db: Session, slug: str) -> list[ArticleImageOut]:
    images = (
        db.query(ArticleImage)
        .filter(ArticleImage.article_slug == slug)
        .order_by(ArticleImage.created_at.asc())
        .all()
    )
    return [_out(i) for i in images]


def add_image(db: Session, slug: str, data: bytes, content_type: str) -> ArticleImageOut:
    body, out_type, ext = optimize_image(data, content_type)
    width, height = dimensions(body)

    image_id = uuid.uuid4().hex[:12]
    filename = f"{slug}-{image_id}.{ext}"

    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    (UPLOAD_DIR / filename).write_bytes(body)

    image = ArticleImage(
        id=image_id,
        article_slug=slug,
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
    return _out(image)


def get_image(db: Session, image_id: str) -> ArticleImage | None:
    return db.query(ArticleImage).filter(ArticleImage.id == image_id).first()


def parent_visibility(db: Session, image: ArticleImage) -> str:
    """The visibility this image inherits.

    An orphaned image (parent deleted) reports "private" so it cannot outlive
    its writing as a publicly readable URL.
    """
    article = db.query(Article).filter(Article.slug == image.article_slug).first()
    return article.visibility if article else "private"


def image_path(image: ArticleImage) -> Path:
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
