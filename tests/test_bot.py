"""The bot: scheduling decisions, and what a message actually does.

Telegram is replaced by a recorder, so these exercise the real handlers and the
real services without a token or a network.
"""

import io
from dataclasses import dataclass
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from app.bot import handlers, scheduler
from app.services import inbox as inbox_svc

ASTANA = ZoneInfo("Asia/Almaty")
NOW = datetime(2026, 8, 12, 10, 0, tzinfo=ASTANA)
OWNER = 673615046


@dataclass
class FakeEvent:
    id: str
    title: str
    starts_at: str
    reminder_minutes: int | None = 0
    reminder_fired_at: str | None = None


class FakeTelegram:
    """Records what the bot would have sent."""

    def __init__(self):
        self.sent: list[dict] = []
        self.edits: list[str] = []
        self.answers: list[str] = []
        self.files: dict[str, bytes] = {}

    def send_message(self, chat_id, text, buttons=None, reply_to=None):
        self.sent.append({"chat_id": chat_id, "text": text, "buttons": buttons})
        return {"message_id": len(self.sent)}

    def edit_message(self, chat_id, message_id, text):
        self.edits.append(text)

    def answer_callback(self, callback_id, text=""):
        self.answers.append(text)

    def download_file(self, file_id):
        return self.files.get(file_id)


def _png() -> bytes:
    Image = pytest.importorskip("PIL.Image", reason="Pillow not installed")
    buf = io.BytesIO()
    Image.new("RGB", (40, 30), (200, 60, 60)).save(buf, format="PNG")
    return buf.getvalue()


def _message(text: str = "", **extra) -> dict:
    return {"message_id": 1, "chat": {"id": OWNER}, "from": {"id": OWNER}, "text": text, **extra}


# --- scheduling decisions (pure) -----------------------------------------


def test_a_reminder_fires_once_its_moment_has_come():
    event = FakeEvent("a", "Dentist", "2026-08-12T10:00:00+05:00", reminder_minutes=0)
    assert [d.event_id for d in scheduler.due_reminders([event], NOW)] == ["a"]


def test_a_reminder_offset_fires_early():
    event = FakeEvent("a", "Dentist", "2026-08-12T10:30:00+05:00", reminder_minutes=30)
    assert scheduler.due_reminders([event], NOW)  # 10:00 is exactly 30 min before
    later = FakeEvent("b", "Dentist", "2026-08-12T11:00:00+05:00", reminder_minutes=30)
    assert scheduler.due_reminders([later], NOW) == []


def test_an_already_fired_reminder_never_fires_again():
    """The whole point of the flag: restarts must not double-ping."""
    event = FakeEvent(
        "a", "Dentist", "2026-08-12T10:00:00+05:00", 0, reminder_fired_at="2026-08-12T10:00:00+05:00"
    )
    assert scheduler.due_reminders([event], NOW) == []


def test_an_event_without_a_reminder_is_never_pinged():
    event = FakeEvent("a", "Quiet", "2026-08-12T10:00:00+05:00", reminder_minutes=None)
    assert scheduler.due_reminders([event], NOW) == []


def test_a_very_late_reminder_is_dropped_rather_than_delivered():
    """After an outage, do not bury him in pings for things already past."""
    stale = FakeEvent("a", "Old", "2026-08-11T10:00:00+05:00", reminder_minutes=0)
    assert scheduler.due_reminders([stale], NOW) == []


def test_the_digest_goes_out_once_a_day_from_eight():
    assert scheduler.should_send_digest(NOW, None) is True
    assert scheduler.should_send_digest(NOW, "2026-08-12") is False
    assert scheduler.should_send_digest(NOW, "2026-08-11") is True
    early = NOW.replace(hour=7)
    assert scheduler.should_send_digest(early, None) is False


# --- what a message does --------------------------------------------------


def test_plain_text_becomes_an_inbox_item_with_triage_buttons(db):
    tg = FakeTelegram()
    handlers.handle_message(db, tg, _message("купить молоко"), OWNER)

    items = inbox_svc.list_items(db)
    assert [i.text for i in items] == ["купить молоко"]
    assert items[0].source == "telegram"
    # Four triage choices plus dismiss.
    labels = [b["text"] for row in tg.sent[0]["buttons"] for b in row]
    assert labels == ["Task", "Event", "Note", "Diary", "✕"]


def test_a_forwarded_message_keeps_its_origin(db):
    tg = FakeTelegram()
    handlers.handle_message(
        db,
        tg,
        _message("посмотри это", forward_origin={"type": "user", "sender_user": {"first_name": "Мадина"}}),
        OWNER,
    )
    assert inbox_svc.list_items(db)[0].text.startswith("↪️ Мадина:")


def test_a_photo_is_captured_through_the_upload_pipeline(db, tmp_path, monkeypatch):
    monkeypatch.setattr(inbox_svc, "UPLOAD_DIR", tmp_path / "inbox")
    tg = FakeTelegram()
    tg.files["file-1"] = _png()

    handlers.handle_message(
        db,
        tg,
        _message("", caption="вот", photo=[{"file_id": "small"}, {"file_id": "file-1"}]),
        OWNER,
    )

    item = inbox_svc.list_items(db)[0]
    assert item.text == "вот"
    assert len(item.images) == 1


def test_a_reminder_message_becomes_a_calendar_event_not_an_inbox_item(db):
    from app.services import calendar as calendar_svc

    tg = FakeTelegram()
    handlers.handle_message(db, tg, _message("напомни завтра в 15:00 позвонить маме"), OWNER)

    assert inbox_svc.list_items(db) == []
    events = calendar_svc.list_events(db)
    assert [e.title for e in events] == ["позвонить маме"]
    assert events[0].starts_at.endswith("15:00:00+05:00")
    # Confirm-or-fix buttons come back with it.
    assert [b["text"] for b in tg.sent[0]["buttons"][0]] == ["✅ Right", "✏️ Change"]


def test_start_explains_itself(db):
    tg = FakeTelegram()
    handlers.handle_message(db, tg, _message("/start"), OWNER)
    assert "Inbox" in tg.sent[0]["text"]

    handlers.handle_message(db, tg, _message("/nonsense"), OWNER)
    assert "don't know that command" in tg.sent[1]["text"]


# --- triage from a button -------------------------------------------------


def _callback(data: str) -> dict:
    return {
        "id": "cb1",
        "data": data,
        "from": {"id": OWNER},
        "message": {"message_id": 5, "chat": {"id": OWNER}},
    }


def test_a_button_triages_through_the_same_service_as_the_web(db):
    tg = FakeTelegram()
    handlers.handle_message(db, tg, _message("написать пост"), OWNER)
    item_id = inbox_svc.list_items(db)[0].id

    handlers.handle_callback(db, tg, _callback(f"g:article:{item_id}"), OWNER)

    item = inbox_svc.list_items(db)[0]
    assert item.triaged_kind == "article"
    assert "Draft note created" in tg.answers[-1]


def test_a_task_button_asks_for_a_due_date_then_sets_it(db):
    tg = FakeTelegram()
    handlers.handle_message(db, tg, _message("сходить к врачу"), OWNER)
    item_id = inbox_svc.list_items(db)[0].id

    handlers.handle_callback(db, tg, _callback(f"k:task:{item_id}"), OWNER)
    labels = [b["text"] for b in tg.sent[-1]["buttons"][0]]
    assert labels == ["Today", "Tomorrow", "Next week"]
    # Still untriaged until he answers.
    assert inbox_svc.list_items(db)[0].triaged_kind is None

    handlers.handle_callback(db, tg, _callback(f"d:task:{item_id}:today"), OWNER)

    from app.models.task import Task

    task = db.query(Task).first()
    assert task.title == "сходить к врачу"
    assert task.due_at == datetime.now(ASTANA).strftime("%Y-%m-%d")
    assert task.source == "inbox:telegram"


def test_pressing_a_triage_button_twice_says_so_instead_of_duplicating(db):
    tg = FakeTelegram()
    handlers.handle_message(db, tg, _message("дважды"), OWNER)
    item_id = inbox_svc.list_items(db)[0].id

    handlers.handle_callback(db, tg, _callback(f"g:dismissed:{item_id}"), OWNER)
    handlers.handle_callback(db, tg, _callback(f"g:task:{item_id}"), OWNER)

    assert "already been triaged" in tg.answers[-1]


# --- the fold-in ----------------------------------------------------------


def test_a_captured_photo_follows_the_thought_into_a_writing(db, tmp_path, monkeypatch):
    """Phase-2 gap: the picture used to stay behind in the inbox."""
    from app.services import article_images as article_images_svc

    monkeypatch.setattr(inbox_svc, "UPLOAD_DIR", tmp_path / "inbox")
    monkeypatch.setattr(article_images_svc, "UPLOAD_DIR", tmp_path / "articles")

    item = inbox_svc.create_item(db, "Тау туралы")
    inbox_svc.add_image(db, item, _png(), "image/png")

    _, slug = inbox_svc.triage_item(db, item, "article")

    images = article_images_svc.list_images(db, slug)
    assert len(images) == 1
    assert (tmp_path / "articles" / f"{slug}-{images[0].id}.png").exists()

    # Embedded, so it actually shows in the draft.
    from app.models.article import Article

    article = db.query(Article).filter(Article.slug == slug).first()
    assert f"![]({images[0].url})" in article.body_md

    # Copied, not moved — the inbox history still renders.
    assert (tmp_path / "inbox").exists()
    assert len(list((tmp_path / "inbox").iterdir())) == 1


def test_a_captured_photo_follows_the_thought_into_the_diary(db, tmp_path, monkeypatch):
    from app.services import diary as diary_svc

    monkeypatch.setattr(inbox_svc, "UPLOAD_DIR", tmp_path / "inbox")
    monkeypatch.setattr(diary_svc, "UPLOAD_DIR", tmp_path / "diary")

    item = inbox_svc.create_item(db, "бүгінгі сурет")
    inbox_svc.add_image(db, item, _png(), "image/png")

    _, day = inbox_svc.triage_item(db, item, "diary")

    entry = diary_svc.get_entry(db, day)
    assert len(entry.images) == 1
    assert "бүгінгі сурет" in entry.body_md
