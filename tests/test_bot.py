"""The bot: scheduling decisions, and what a message actually does.

Telegram is replaced by a recorder, so these exercise the real handlers and the
real services without a token or a network.
"""

import io
from dataclasses import dataclass
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from conftest import FakeTelegram

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

    # "✅ Right" only acknowledges — but it has to acknowledge, not raise.
    handlers.handle_callback(
        db,
        tg,
        {
            "id": "cb1",
            "data": f"rc:{events[0].id}",
            "from": {"id": OWNER},
            "message": {"message_id": 5, "chat": {"id": OWNER}},
        },
        OWNER,
    )
    assert tg.answers[-1] == "On your calendar."
    assert calendar_svc.list_events(db)[0].title == "позвонить маме"


def test_start_explains_itself(db):
    tg = FakeTelegram()
    handlers.handle_message(db, tg, _message("/start"), OWNER)
    assert "Inbox" in tg.sent[0]["text"]

    handlers.handle_message(db, tg, _message("/nonsense"), OWNER)
    assert "don't know that command" in tg.sent[1]["text"]


# --- the command menu + profile (published once at startup) ---------------


def test_startup_registers_the_command_menu_and_profile():
    from app.bot import copy, main

    tg = FakeTelegram()
    main._register_profile(tg)

    # Every user-facing command the bot handles is in the menu…
    assert [c["command"] for c in tg.commands] == ["start", "review", "digest"]
    # …each with a helpful, non-empty, punctuation-free-ending description.
    for c in tg.commands:
        assert c["description"].strip()
        assert not c["description"].endswith(".")

    assert tg.short_description == copy.BOT_SHORT_DESCRIPTION
    assert tg.short_description and len(tg.short_description) <= 120
    assert "Inbox" in tg.description
    assert len(tg.description) <= 512


def test_a_menu_registration_failure_never_crashes_startup():
    """A Telegram hiccup at startup must warn, not take down polling."""
    from app.bot import main
    from app.bot.client import TelegramError

    class Boom(FakeTelegram):
        def set_my_commands(self, commands):
            raise TelegramError("setMyCommands failed: 429 Too Many Requests")

    # Must return normally — the bot goes on to poll.
    main._register_profile(Boom())


# --- the persistent reply keyboard ----------------------------------------


def test_start_raises_the_persistent_keyboard(db):
    from app.bot import copy

    tg = FakeTelegram()
    handlers.handle_message(db, tg, _message("/start"), OWNER)
    assert tg.sent[0]["keyboard"] == copy.MENU_KEYBOARD


def test_reply_keyboard_markup_is_persistent_and_resized():
    from app.bot import client, copy

    markup = client.reply_keyboard(copy.MENU_KEYBOARD)
    assert markup["is_persistent"] is True
    assert markup["resize_keyboard"] is True
    labels = [b["text"] for row in markup["keyboard"] for b in row]
    assert labels == ["🌙 Review", "🗓 Week", "📅 Today", "📥 Inbox", "📔 Diary"]


def test_the_inbox_button_shows_untriaged_and_does_not_capture(db):
    """A tap on 📥 Inbox lists what's waiting — it must NOT become a note."""
    from app.bot import copy

    inbox_svc.create_item(db, "buy milk")
    inbox_svc.create_item(db, "email the accountant")

    tg = FakeTelegram()
    handlers.handle_message(db, tg, _message(copy.BTN_MENU_INBOX), OWNER)

    # The two real items are still the only ones — the tap added nothing.
    assert [i.text for i in inbox_svc.list_items(db)] == [
        "email the accountant",
        "buy milk",
    ]
    assert tg.sent[-1]["text"].startswith("📥 <b>Inbox</b> · 2 to triage")
    assert "buy milk" in tg.sent[-1]["text"]


def test_the_today_button_shows_the_morning_view_and_does_not_capture(db):
    from app.bot import copy

    tg = FakeTelegram()
    handlers.handle_message(db, tg, _message(copy.BTN_MENU_TODAY), OWNER)

    assert inbox_svc.list_items(db) == []          # not captured
    assert tg.sent[-1]["text"].split("\n")[0] == "<b>Today</b>"


def test_the_review_button_runs_the_review_not_capture(db):
    from app.bot import copy

    tg = FakeTelegram()
    handlers.handle_message(db, tg, _message(copy.BTN_MENU_REVIEW), OWNER)

    assert inbox_svc.list_items(db) == []          # not captured
    # Empty calendar → the review's own "nothing" line, not an inbox ack.
    assert tg.sent[-1]["text"] == copy.REVIEW_NOTHING


def test_the_week_button_runs_the_digest_not_capture(db):
    from app.bot import copy

    tg = FakeTelegram()
    handlers.handle_message(db, tg, _message(copy.BTN_MENU_WEEK), OWNER)

    assert inbox_svc.list_items(db) == []          # not captured
    assert "week" in tg.sent[-1]["text"].lower()


def test_other_text_still_captures_normally(db):
    """The keyboard intercept is exact-match only — everything else is a thought."""
    from app.bot import copy

    tg = FakeTelegram()
    # A near-miss (no emoji) is not a button, so it captures as usual.
    handlers.handle_message(db, tg, _message("Review the lease"), OWNER)

    assert [i.text for i in inbox_svc.list_items(db)] == ["Review the lease"]
    assert tg.sent[-1]["text"] == f"{copy.CAPTURED}\n{copy.TRIAGE_PROMPT}"


# --- the diary (write from chat, read it back article-style) ---------------


def _diary_reply(text="", **extra):
    """A message replying to the diary prompt for today."""
    from app.bot import copy
    from app.services import diary as diary_svc

    prompt = copy.diary_prompt(diary_svc.today())
    return _message(text, reply_to_message={"text": prompt}, **extra)


def test_the_diary_button_shows_empty_and_prompts_without_capturing(db):
    from app.bot import copy

    tg = FakeTelegram()
    handlers.handle_message(db, tg, _message(copy.BTN_MENU_DIARY), OWNER)

    assert inbox_svc.list_items(db) == []                      # not captured
    assert "empty — start writing" in tg.sent[0]["text"]
    assert tg.sent[-1]["text"].startswith("✍️ <b>Write today's diary</b>")
    assert "#diary-" in tg.sent[-1]["text"]


def test_a_reply_to_the_diary_prompt_appends_text_not_an_inbox_item(db):
    from app.bot import copy
    from app.services import diary as diary_svc

    tg = FakeTelegram()
    handlers.handle_message(db, tg, _diary_reply("Woke up early, ran the lake loop."), OWNER)

    assert inbox_svc.list_items(db) == []                      # never captured
    entry = diary_svc.get_entry(db, diary_svc.today())
    assert entry.exists
    assert entry.body_md == "Woke up early, ran the lake loop."
    assert tg.sent[-1]["text"] == copy.DIARY_SAVED


def test_a_second_diary_reply_appends_with_the_same_separator_as_triage(db):
    from app.services import diary as diary_svc
    from app.services.inbox import DIARY_SEPARATOR

    tg = FakeTelegram()
    handlers.handle_message(db, tg, _diary_reply("First thought."), OWNER)
    handlers.handle_message(db, tg, _diary_reply("Second thought."), OWNER)

    entry = diary_svc.get_entry(db, diary_svc.today())
    assert entry.body_md == f"First thought.{DIARY_SEPARATOR}Second thought."


def test_diary_direct_write_and_inbox_triage_share_one_entry(db):
    """Both flows append to today's single entry — no double store, no clash."""
    from app.services import diary as diary_svc
    from app.services.inbox import DIARY_SEPARATOR

    tg = FakeTelegram()
    handlers.handle_message(db, tg, _diary_reply("Typed straight in."), OWNER)

    # …now a captured thought filed to Diary via the inbox triage path.
    item = inbox_svc.create_item(db, "Filed from the inbox.")
    inbox_svc.triage_item(db, item, "diary")

    entry = diary_svc.get_entry(db, diary_svc.today())
    assert entry.body_md == (
        f"Typed straight in.{DIARY_SEPARATOR}Filed from the inbox."
    )


def test_a_photo_reply_attaches_to_todays_diary(db, tmp_path, monkeypatch):
    from app.services import diary as diary_svc

    monkeypatch.setattr(diary_svc, "UPLOAD_DIR", tmp_path / "diary")
    tg = FakeTelegram()
    tg.files["big"] = _png()

    handlers.handle_message(
        db, tg, _diary_reply("", photo=[{"file_id": "small"}, {"file_id": "big"}]), OWNER
    )

    assert inbox_svc.list_items(db) == []                      # not captured
    entry = diary_svc.get_entry(db, diary_svc.today())
    assert len(entry.images) == 1
    assert tg.sent[-1]["text"] == "📔 Photo added to today's diary"


def test_the_diary_button_renders_the_entry_article_style(db, tmp_path, monkeypatch):
    from app.bot import copy
    from app.services import diary as diary_svc

    monkeypatch.setattr(diary_svc, "UPLOAD_DIR", tmp_path / "diary")
    diary_svc.upsert_entry(
        db, diary_svc.today(), "# Morning\n\nRan **hard** today.", title="My day"
    )
    diary_svc.add_image(db, diary_svc.today(), _png(), "image/png")

    tg = FakeTelegram()
    handlers.handle_message(db, tg, _message(copy.BTN_MENU_DIARY), OWNER)

    article = tg.sent[0]["text"]
    assert "📔 <b>My day</b>" in article        # title as a heading
    assert "<b>Morning</b>" in article          # markdown heading → bold
    assert "Ran <b>hard</b> today." in article  # inline bold
    assert "1 photo" in article                 # the photo cue
    # The photo itself is sent as a real image, after the text.
    assert len(tg.photos) == 1


def test_render_markdown_maps_the_site_subset_to_telegram_html():
    from app.bot import copy

    assert copy.render_markdown("## Heading") == "<b>Heading</b>"
    assert copy.render_markdown("- one\n- two") == "• one\n• two"
    assert copy.render_markdown("**b** and *i* and ~~s~~") == "<b>b</b> and <i>i</i> and <s>s</s>"
    assert copy.render_markdown("`x < y`") == "<code>x &lt; y</code>"
    assert copy.render_markdown("[site](https://a.b)") == '<a href="https://a.b">site</a>'
    assert copy.render_markdown("---") == "┄┄┄┄┄┄┄┄"
    assert copy.render_markdown("![alt](u.jpg)").strip() == ""   # images dropped from text
    # A stray tag in the body can never break the send.
    assert "<script>" not in copy.render_markdown("watch <script>alert(1)</script>")


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
    # The flow ends settled: the prompt is replaced by the Note card.
    assert tg.edits[-1] == "📝 <b>написать пост</b>\nDraft note · private"


def test_a_task_button_asks_for_a_due_date_then_sets_it(db):
    tg = FakeTelegram()
    handlers.handle_message(db, tg, _message("сходить к врачу"), OWNER)
    item_id = inbox_svc.list_items(db)[0].id

    handlers.handle_callback(db, tg, _callback(f"k:task:{item_id}"), OWNER)
    labels = [b["text"] for b in tg.sent[-1]["buttons"][0]]
    assert labels == ["Today", "Tomorrow", "Next week"]
    assert tg.sent[-1]["text"] == "Due when?"
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

    assert "Already filed." in tg.answers[-1]


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


# --- rendered message formats (the site's vocabulary, in chat) -------------


def test_capture_ack_is_one_quiet_line_then_the_prompt(db):
    tg = FakeTelegram()
    handlers.handle_message(db, tg, _message("a thought"), OWNER)
    assert tg.sent[0]["text"] == "📥 Saved to Inbox\nFile it as:"


def test_the_buttons_use_the_site_s_words(db):
    tg = FakeTelegram()
    handlers.handle_message(db, tg, _message("x"), OWNER)
    labels = [b["text"] for row in tg.sent[0]["buttons"] for b in row]
    assert labels == ["Task", "Event", "Note", "Diary", "✕"]


def test_an_event_confirmation_reads_like_the_site_s_event_card(db):
    tg = FakeTelegram()
    handlers.handle_message(db, tg, _message("напомни 9.08 в 15:00 позвонить"), OWNER)

    text = tg.sent[0]["text"]
    lines = text.split("\n")
    assert lines[0] == "📅 <b>позвонить</b>"
    assert lines[1].startswith("📅 ")
    assert " · 15:00" in lines[1]
    assert lines[2] == "⏰ Reminder at the time"


def test_a_task_confirmation_shows_its_due_chip(db):
    from app.services import tasks as tasks_svc

    tg = FakeTelegram()
    handlers.handle_message(db, tg, _message("сходить к врачу"), OWNER)
    item_id = inbox_svc.list_items(db)[0].id

    handlers.handle_callback(db, tg, _callback(f"k:task:{item_id}"), OWNER)
    handlers.handle_callback(db, tg, _callback(f"d:task:{item_id}:today"), OWNER)

    assert tg.edits[-1] == "✅ <b>сходить к врачу</b>\nDue: Today"

    # And tomorrow reads as Tomorrow, not as a date.
    handlers.handle_message(db, tg, _message("another"), OWNER)
    second = inbox_svc.list_items(db)[0].id
    handlers.handle_callback(db, tg, _callback(f"d:task:{second}:tomorrow"), OWNER)
    assert tg.edits[-1].endswith("Due: Tomorrow")


def test_diary_confirmation_names_the_day(db):
    tg = FakeTelegram()
    handlers.handle_message(db, tg, _message("today's thought"), OWNER)
    item_id = inbox_svc.list_items(db)[0].id

    handlers.handle_callback(db, tg, _callback(f"g:diary:{item_id}"), OWNER)
    assert tg.edits[-1].startswith("📔 Added to your Diary\n")


def test_start_is_a_scannable_onboarding_with_both_reminder_examples(db):
    tg = FakeTelegram()
    handlers.handle_message(db, tg, _message("/start"), OWNER)
    text = tg.sent[0]["text"]

    for lead in ("<b>Capture</b>", "<b>Reminders</b>", "<b>Every morning</b>"):
        assert lead in text
    # One Russian example and one Kazakh one.
    assert "remind me tomorrow at 15:00" in text
    assert "ертең сағат 15:00" in text
    # The site's four destinations, named the same way.
    for word in ("Task", "Event", "Note", "Diary", "Inbox"):
        assert word in text


def test_the_digest_is_laid_out_like_the_dashboard():
    from app.bot import copy

    text = copy.digest(
        today_iso="2026-08-08",
        events=[("09:00", "Standup"), (None, "Holiday")],
        tasks=["Renew the domain"],
        overdue=2,
        inbox=3,
    )
    assert text.split("\n")[0] == "<b>Today</b>"
    assert "📅 <b>Events</b>" in text
    assert "09:00 · Standup" in text
    assert "— · Holiday" in text          # all-day keeps its place in the timeline
    assert "✅ <b>Tasks</b> · 1 due" in text
    assert "• Renew the domain" in text
    assert "⚠️ 2 overdue" in text
    assert "📥 <b>Inbox</b> · 3 to triage" in text


def test_an_empty_digest_says_so_without_empty_sections():
    from app.bot import copy

    text = copy.digest("2026-08-08", [], [], 0, 0)
    assert "Nothing scheduled" in text
    for absent in ("Events", "Tasks", "Inbox"):
        assert absent not in text


def test_the_digest_drops_sections_that_are_empty():
    from app.bot import copy

    text = copy.digest("2026-08-08", [("10:00", "Only event")], [], 0, 0)
    assert "📅 <b>Events</b>" in text
    assert "Tasks" not in text
    assert "Inbox" not in text


def test_a_fired_reminder_leads_with_the_title():
    from app.bot import copy

    assert copy.reminder_fire("Dentist", "2026-08-09T15:00:00+05:00") == (
        "⏰ <b>Dentist</b>\n15:00"
    )


def test_the_due_chip_matches_the_site_s_wording():
    from app.bot import copy

    assert copy.due_chip("2026-08-08", "2026-08-08") == "Due: Today"
    assert copy.due_chip("2026-08-09", "2026-08-08") == "Due: Tomorrow"
    assert copy.due_chip("2026-08-20", "2026-08-08") == "Due: 20 Aug"
    assert copy.due_chip("2026-08-20T14:30:00+05:00", "2026-08-08") == "Due: 20 Aug · 14:30"
    assert copy.due_chip(None, "2026-08-08") == "No due date"
