from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.schemas.article import ArticleOut, ArticleSummary, CommentCreate, CommentOut
from app.services import articles as svc

router = APIRouter(prefix="/api/articles", tags=["articles"])


@router.get("", response_model=list[ArticleSummary])
def get_articles(db: Session = Depends(get_db)):
    rows = svc.list_articles(db)
    return [
        ArticleSummary(
            slug=a.slug,
            title=a.title,
            description=a.description,
            date=a.date,
            read_time=a.read_time,
            comment_count=len(a.comments),
        )
        for a in rows
    ]


@router.get("/{slug}", response_model=ArticleOut)
def get_article(slug: str, db: Session = Depends(get_db)):
    article = svc.get_article(db, slug)
    if not article:
        raise HTTPException(status_code=404, detail="Article not found")
    return article


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
