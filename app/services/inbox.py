"""Capture and triage.

Triage is the interesting half: it creates the real object (task / writing /
event / diary line) and only then marks the item, so a failure part-way leaves
the item untriaged rather than pointing at something that does not exist.
"""

import os
import uuid
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy.orm import Session

from app.models.article import Article
from app.models.calendar import CalendarEvent
from app.models.inbox import InboxImage, InboxItem
from app.schemas.calendar import CalendarEventCreate
from app.schemas.inbox import InboxImageOut, InboxItemOut
from app.schemas.task import TaskCreate
from app.services import calendar as calendar_svc
from app.services import article_images as article_images_svc
from app.services import diary as diary_svc
from app.services import inbox_triage as triage
from app.services import tasks as tasks_svc
from app.services.calendar import ASTANA
from app.services.image_optimize import dimensions, optimize_image
from app.models.article_image import ArticleImage
from app.models.diary import DiaryImage

UPLOAD_DIR = Path(os.getenv("UPLOAD_DIR", "/data/uploads")) / "inbox"
MAX_UPLOAD_BYTES = 25 * 1024 * 1024

# What separates an appended thought from what was already in today's entry.
DIARY_SEPARATOR = "\n\n---\n\n"


def _now() -> str:
    return datetime.now(timezone.utc).astimezone(ASTANA).isoformat()


def _image_out(image: InboxImage) -> InboxImageOut:
    return InboxImageOut(
        id=image.id,
        item_id=image.item_id,
        url=f"/api/inbox/images/{image.id}",
        width=image.width,
        height=image.height,
        created_at=image.created_at,
    )


def _out(item: InboxItem) -> InboxItemOut:
    kind, target_id = triage.parse_ref(item.triaged_to)
    return InboxItemOut(
        id=item.id,
        text=item.text or "",
        source=item.source,
        triaged_to=item.triaged_to,
        triaged_kind=kind,
        triaged_id=target_id,
        triaged_at=item.triaged_at,
        images=[_image_out(i) for i in item.images],
        created_at=item.created_at,
        updated_at=item.updated_at,
    )


def out(item: InboxItem) -> InboxItemOut:
    return _out(item)


# --- capture ---


def create_item(db: Session, text: str, source: str = "web") -> InboxItem:
    now = _now()
    item = InboxItem(
        id=uuid.uuid4().hex[:10],
        text=(text or "").strip(),
        source=(source or "web").strip() or "web",
        created_at=now,
        updated_at=now,
    )
    db.add(item)
    db.commit()
    db.refresh(item)
    return item


def get_item(db: Session, item_id: str) -> InboxItem | None:
    return db.query(InboxItem).filter(InboxItem.id == item_id).first()


def list_items(db: Session, triaged: bool | None = None, limit: int = 200) -> list[InboxItemOut]:
    """Newest first — the inbox is a stack, not a queue."""
    q = db.query(InboxItem)
    if triaged is True:
        q = q.filter(InboxItem.triaged_to.isnot(None))
    elif triaged is False:
        q = q.filter(InboxItem.triaged_to.is_(None))
    return [_out(i) for i in q.order_by(InboxItem.created_at.desc()).limit(limit).all()]


def count_untriaged(db: Session) -> int:
    return db.query(InboxItem).filter(InboxItem.triaged_to.is_(None)).count()


def update_text(db: Session, item: InboxItem, text: str) -> InboxItem:
    item.text = (text or "").strip()
    item.updated_at = _now()
    db.commit()
    db.refresh(item)
    return item


def delete_item(db: Session, item: InboxItem) -> None:
    for image in list(item.images):
        _unlink(image)
    db.delete(item)
    db.commit()


# --- photos ---


def _unlink(image: InboxImage) -> None:
    try:
        (UPLOAD_DIR / image.filename).unlink(missing_ok=True)
    except OSError:
        pass


def add_image(db: Session, item: InboxItem, data: bytes, content_type: str) -> InboxImageOut:
    body, out_type, ext = optimize_image(data, content_type)
    width, height = dimensions(body)

    image_id = uuid.uuid4().hex[:12]
    filename = f"{item.id}-{image_id}.{ext}"

    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    (UPLOAD_DIR / filename).write_bytes(body)

    highest = (
        db.query(InboxImage)
        .filter(InboxImage.item_id == item.id)
        .order_by(InboxImage.sort_order.desc())
        .first()
    )
    image = InboxImage(
        id=image_id,
        item_id=item.id,
        filename=filename,
        content_type=out_type,
        width=width,
        height=height,
        size_bytes=len(body),
        sort_order=(highest.sort_order + 1) if highest else 0,
        created_at=_now(),
    )
    db.add(image)
    db.commit()
    db.refresh(image)
    return _image_out(image)


def get_image(db: Session, image_id: str) -> InboxImage | None:
    return db.query(InboxImage).filter(InboxImage.id == image_id).first()


def image_path(image: InboxImage) -> Path:
    return UPLOAD_DIR / image.filename


def delete_image(db: Session, image_id: str) -> bool:
    image = get_image(db, image_id)
    if not image:
        return False
    _unlink(image)
    db.delete(image)
    db.commit()
    return True


# --- triage ---


def _copy_images_to(db: Session, item: InboxItem, kind: str, owner: str) -> list[str]:
    """Copy an item's photos into whatever it became.

    A thought captured *with* a picture should land complete — before this the
    photo stayed behind in the inbox and the new writing or diary entry quietly
    lost it. The bytes are copied, not moved, so the inbox history still renders.

    Returns the URLs of the copies, for embedding in a markdown body.
    """
    urls: list[str] = []

    for index, image in enumerate(item.images):
        source = UPLOAD_DIR / image.filename
        if not source.exists():
            continue

        data = source.read_bytes()
        ext = image.filename.rsplit(".", 1)[-1]
        new_id = uuid.uuid4().hex[:12]

        if kind == "article":
            target_dir = article_images_svc.UPLOAD_DIR
            filename = f"{owner}-{new_id}.{ext}"
            row = ArticleImage(
                id=new_id,
                article_slug=owner,
                filename=filename,
                content_type=image.content_type,
                width=image.width,
                height=image.height,
                size_bytes=image.size_bytes,
                created_at=_now(),
            )
            urls.append(f"/api/articles/images/{new_id}")
        else:
            target_dir = diary_svc.UPLOAD_DIR
            filename = f"{owner}-{new_id}.{ext}"
            row = DiaryImage(
                id=new_id,
                day=owner,
                filename=filename,
                content_type=image.content_type,
                width=image.width,
                height=image.height,
                size_bytes=image.size_bytes,
                sort_order=index,
                created_at=_now(),
            )
            urls.append(f"/api/diary/images/{new_id}")

        target_dir.mkdir(parents=True, exist_ok=True)
        (target_dir / filename).write_bytes(data)
        db.add(row)

    if urls:
        db.commit()
    return urls


def _mark(db: Session, item: InboxItem, ref: str) -> InboxItem:
    item.triaged_to = ref
    item.triaged_at = _now()
    item.updated_at = item.triaged_at
    db.commit()
    db.refresh(item)
    return item


def _unique_slug(db: Session, base: str) -> str:
    slug = base
    suffix = 2
    while db.query(Article).filter(Article.slug == slug).first():
        slug = f"{base}-{suffix}"
        suffix += 1
    return slug


def triage_item(
    db: Session,
    item: InboxItem,
    kind: str,
    title: str | None = None,
    due_at: str | None = None,
    starts_at: str | None = None,
    reminder_minutes: int | None = None,
) -> tuple[InboxItem, str | None]:
    """Turn the item into something, then mark it. Returns (item, target id).

    The object is created *first* — if that fails the item stays in the inbox,
    which is the recoverable direction.
    """
    if not triage.is_valid_kind(kind):
        raise triage.TriageError(f"Unknown triage target: {kind!r}")
    triage.ensure_triageable(item.triaged_to)

    if kind == "dismissed":
        return _mark(db, item, triage.make_ref("dismissed")), None

    headline = (title or "").strip() or triage.title_from_text(item.text)

    if kind == "task":
        task = tasks_svc.create_task(
            db,
            TaskCreate(
                title=headline,
                notes=item.text if item.text.strip() != headline else "",
                due_at=due_at,
                # Attribution: this task came from the inbox, not typed directly.
                source=f"inbox:{item.source}" if item.source != "web" else "inbox",
            ),
        )
        return _mark(db, item, triage.make_ref("task", task.id)), task.id

    if kind == "event":
        if not starts_at:
            raise triage.TriageError("An event needs a start time")
        event = calendar_svc.create_event(
            db,
            CalendarEventCreate(
                title=headline,
                starts_at=starts_at,
                notes=item.text if item.text.strip() != headline else "",
                reminder_minutes=reminder_minutes,
            ),
        )
        return _mark(db, item, triage.make_ref("event", event.id)), event.id

    if kind == "article":
        slug = _unique_slug(db, triage.slugify(headline))
        article = Article(
            slug=slug,
            title=headline,
            description="",
            date=datetime.now(timezone.utc).astimezone(ASTANA).strftime("%Y-%m-%d"),
            read_time="1 min",
            body=[],
            body_md=item.text,
            archived=False,
            # A draft starts private — an inbox thought is not a published post.
            visibility="private",
        )
        db.add(article)
        db.commit()

        # The photos come along, and are embedded so they actually show.
        urls = _copy_images_to(db, item, "article", slug)
        if urls:
            embedded = "\n\n".join(f"![]({url})" for url in urls)
            article.body_md = f"{article.body_md}\n\n{embedded}".strip()
            db.commit()

        return _mark(db, item, triage.make_ref("article", slug)), slug

    # diary: append to today's entry rather than replacing it.
    day = diary_svc.today()
    entry = diary_svc.get_entry(db, day)
    body = entry.body_md.strip()
    appended = f"{body}{DIARY_SEPARATOR}{item.text}" if body else item.text
    diary_svc.upsert_entry(db, day, appended, entry.title)
    # Attached to the day itself, where the diary renders its photo grid.
    _copy_images_to(db, item, "diary", day)
    return _mark(db, item, triage.make_ref("diary", day)), day
