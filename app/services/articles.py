import uuid
from datetime import datetime, timezone

from sqlalchemy.orm import Session, joinedload

from app.models.article import Article, Comment
from app.schemas.article import CommentCreate


def list_articles(db: Session) -> list[Article]:
    return db.query(Article).order_by(Article.date.desc()).all()


def get_article(db: Session, slug: str) -> Article | None:
    return (
        db.query(Article)
        .options(joinedload(Article.comments))
        .filter(Article.slug == slug)
        .first()
    )


def add_comment(db: Session, slug: str, data: CommentCreate) -> Comment:
    words = data.author.strip().split()
    avatar = "".join(w[0] for w in words[:2]).upper() if words else "?"

    comment = Comment(
        id=str(uuid.uuid4())[:8],
        article_slug=slug,
        author=data.author.strip(),
        avatar=avatar,
        date=datetime.now(timezone.utc).strftime("%B %d, %Y"),
        body=data.body.strip(),
    )
    db.add(comment)
    db.commit()
    db.refresh(comment)
    return comment
