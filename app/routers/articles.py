from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import can_view, require_admin, viewer_level, visible_levels
from app.schemas.article import (
    ArticleCreate,
    ArticleImageOut,
    ArticleOut,
    ArticleSummary,
    ArticleUpdate,
    CommentCreate,
    CommentOut,
)
from app.services import article_images as images_svc
from app.services import articles as svc
from app.services.image_optimize import ALLOWED_CONTENT_TYPES

router = APIRouter(prefix="/api/articles", tags=["articles"])


@router.get("", response_model=list[ArticleSummary])
def get_articles(
    include_archived: bool = False,
    db: Session = Depends(get_db),
    level: str = Depends(viewer_level),
):
    rows = svc.list_articles(
        db, include_archived=include_archived, levels=visible_levels(level)
    )
    return [
        ArticleSummary(
            slug=a.slug,
            title=a.title,
            description=a.description,
            date=a.date,
            read_time=a.read_time,
            comment_count=len(a.comments),
            archived=a.archived,
            visibility=a.visibility,
        )
        for a in rows
    ]


@router.get("/{slug}/backlinks", response_model=list[ArticleSummary])
def get_article_backlinks(
    slug: str,
    db: Session = Depends(get_db),
    level: str = Depends(viewer_level),
):
    """Articles that mention `[[slug]]` — visibility-filtered both ways: the
    target must be visible to the viewer (404 otherwise), and only sources
    the viewer may read are listed."""
    article = svc.get_article(db, slug)
    if not article or article.visibility not in visible_levels(level):
        raise HTTPException(status_code=404, detail="Article not found")
    rows = svc.list_backlinks(db, slug, levels=visible_levels(level))
    return [
        ArticleSummary(
            slug=a.slug,
            title=a.title,
            description=a.description,
            date=a.date,
            read_time=a.read_time,
            comment_count=len(a.comments),
            archived=a.archived,
            visibility=a.visibility,
        )
        for a in rows
    ]


@router.get("/{slug}", response_model=ArticleOut)
def get_article(
    slug: str,
    db: Session = Depends(get_db),
    level: str = Depends(viewer_level),
):
    article = svc.get_article(db, slug)
    if not article or article.visibility not in visible_levels(level):
        raise HTTPException(status_code=404, detail="Article not found")
    return article


@router.post("", response_model=ArticleOut, status_code=201)
def create_article(
    data: ArticleCreate,
    db: Session = Depends(get_db),
    _: None = Depends(require_admin),
):
    existing = svc.get_article(db, data.slug)
    if existing:
        raise HTTPException(status_code=409, detail="Article with this slug already exists")
    article = svc.create_article(db, data)
    return svc.get_article(db, article.slug)


@router.put("/{slug}", response_model=ArticleOut)
def update_article(
    slug: str,
    data: ArticleUpdate,
    db: Session = Depends(get_db),
    _: None = Depends(require_admin),
):
    article = svc.update_article(db, slug, data)
    if not article:
        raise HTTPException(status_code=404, detail="Article not found")
    return svc.get_article(db, slug)


@router.delete("/{slug}", status_code=204)
def delete_article(
    slug: str,
    db: Session = Depends(get_db),
    _: None = Depends(require_admin),
):
    """Permanent. Archiving is the reversible option; this removes the row,
    its comments and its photo files."""
    if not svc.delete_article(db, slug):
        raise HTTPException(status_code=404, detail="Article not found")


@router.patch("/{slug}/archive")
def toggle_archive(
    slug: str,
    db: Session = Depends(get_db),
    _: None = Depends(require_admin),
):
    article = svc.get_article(db, slug)
    if not article:
        raise HTTPException(status_code=404, detail="Article not found")
    updated = svc.archive_article(db, slug, not article.archived)
    return {"slug": slug, "archived": updated.archived if updated else False}


@router.post("/{slug}/comments", response_model=CommentOut, status_code=201)
def create_comment(
    slug: str,
    data: CommentCreate,
    db: Session = Depends(get_db),
):
    article = svc.get_article(db, slug)
    if not article:
        raise HTTPException(status_code=404, detail="Article not found")
    return svc.add_comment(db, slug, data)


@router.delete("/{slug}/comments/{comment_id}", status_code=204)
def delete_comment(
    slug: str,
    comment_id: str,
    db: Session = Depends(get_db),
    _: None = Depends(require_admin),
):
    svc.delete_comment(db, comment_id)


# --- photos ---------------------------------------------------------------
#
# Upload and delete are admin-only. *Serving* is not: a photo has to be exactly
# as reachable as the writing it belongs to, so the route resolves the parent's
# visibility and asks `can_view`. A public writing's images load for a logged-out
# reader; a private one's do not.


@router.get("/{slug}/images", response_model=list[ArticleImageOut])
def list_article_images(
    slug: str,
    db: Session = Depends(get_db),
    level: str = Depends(viewer_level),
):
    article = svc.get_article(db, slug)
    if not article or not can_view(article.visibility, level):
        raise HTTPException(status_code=404, detail="Article not found")
    return images_svc.list_images(db, slug)


@router.post("/{slug}/images", response_model=list[ArticleImageOut], status_code=201)
async def upload_article_images(
    slug: str,
    files: list[UploadFile] = File(...),
    db: Session = Depends(get_db),
    _: None = Depends(require_admin),
):
    article = svc.get_article(db, slug)
    if not article:
        raise HTTPException(status_code=404, detail="Article not found")

    saved: list[ArticleImageOut] = []
    for upload in files:
        content_type = (upload.content_type or "").lower()
        if content_type not in ALLOWED_CONTENT_TYPES:
            raise HTTPException(
                status_code=415, detail=f"Unsupported image type: {content_type or 'unknown'}"
            )

        data = await upload.read(images_svc.MAX_UPLOAD_BYTES + 1)
        if len(data) > images_svc.MAX_UPLOAD_BYTES:
            raise HTTPException(status_code=413, detail=f"{upload.filename} is too large")
        if not data:
            continue

        saved.append(images_svc.add_image(db, slug, data, content_type))

    if not saved:
        raise HTTPException(status_code=422, detail="No image uploaded")
    return saved


@router.get("/images/{image_id}")
def serve_article_image(
    image_id: str,
    db: Session = Depends(get_db),
    level: str = Depends(viewer_level),
):
    """Serve a writing's photo, mirroring that writing's visibility."""
    image = images_svc.get_image(db, image_id)
    if not image:
        raise HTTPException(status_code=404, detail="Image not found")

    visibility = images_svc.parent_visibility(db, image)
    if not can_view(visibility, level):
        # 404, not 403: a gated image should not confirm it exists.
        raise HTTPException(status_code=404, detail="Image not found")

    path = images_svc.image_path(image)
    if not path.exists():
        raise HTTPException(status_code=404, detail="Image file missing")

    # A public image may sit in a shared cache; anything gated must not.
    cache = "public, max-age=86400" if visibility == "public" else "private, max-age=86400"
    return FileResponse(path, media_type=image.content_type, headers={"Cache-Control": cache})


@router.delete("/images/{image_id}", status_code=204)
def delete_article_image(
    image_id: str,
    db: Session = Depends(get_db),
    _: None = Depends(require_admin),
):
    if not images_svc.delete_image(db, image_id):
        raise HTTPException(status_code=404, detail="Image not found")
