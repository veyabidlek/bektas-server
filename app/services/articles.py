import uuid
from datetime import datetime, timezone

from sqlalchemy.orm import Session, joinedload

from app.models.article import Article, Comment
from app.schemas.article import ArticleCreate, ArticleUpdate, CommentCreate


def list_articles(db: Session, include_archived: bool = False) -> list[Article]:
    q = db.query(Article)
    if not include_archived:
        q = q.filter(Article.archived == False)  # noqa: E712
    return q.order_by(Article.date.desc()).all()


def get_article(db: Session, slug: str) -> Article | None:
    return (
        db.query(Article)
        .options(joinedload(Article.comments))
        .filter(Article.slug == slug)
        .first()
    )


def create_article(db: Session, data: ArticleCreate) -> Article:
    article = Article(
        slug=data.slug,
        title=data.title,
        description=data.description,
        date=data.date,
        read_time=data.read_time,
        body=data.body,
        archived=False,
    )
    db.add(article)
    db.commit()
    db.refresh(article)
    return article


def update_article(db: Session, slug: str, data: ArticleUpdate) -> Article | None:
    article = db.query(Article).filter(Article.slug == slug).first()
    if not article:
        return None

    for field, value in data.model_dump(exclude_none=True).items():
        setattr(article, field, value)

    db.commit()
    db.refresh(article)
    return article


def archive_article(db: Session, slug: str, archived: bool) -> Article | None:
    article = db.query(Article).filter(Article.slug == slug).first()
    if not article:
        return None
    article.archived = archived
    db.commit()
    db.refresh(article)
    return article


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


def delete_comment(db: Session, comment_id: str) -> None:
    comment = db.query(Comment).filter(Comment.id == comment_id).first()
    if comment:
        db.delete(comment)
        db.commit()
