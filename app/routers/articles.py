from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import require_admin
from app.schemas.article import (
    ArticleCreate,
    ArticleOut,
    ArticleSummary,
    ArticleUpdate,
    CommentCreate,
    CommentOut,
)
from app.services import articles as svc

router = APIRouter(prefix="/api/articles", tags=["articles"])


@router.get("", response_model=list[ArticleSummary])
def get_articles(
    include_archived: bool = False,
    db: Session = Depends(get_db),
):
    rows = svc.list_articles(db, include_archived=include_archived)
    return [
        ArticleSummary(
            slug=a.slug,
            title=a.title,
            description=a.description,
            date=a.date,
            read_time=a.read_time,
            comment_count=len(a.comments),
            archived=a.archived,
        )
        for a in rows
    ]


@router.get("/{slug}", response_model=ArticleOut)
def get_article(slug: str, db: Session = Depends(get_db)):
    article = svc.get_article(db, slug)
    if not article:
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
