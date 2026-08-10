"""The two ways he reaches the assistant: the admin endpoint and `/a` in chat.

Both call the same `assistant.answer`, so what is tested here is the wiring and
the failure shape — a 503 that says why rather than a 500, and a chat reply
that cannot break an HTML send. The service itself is next door in
`test_assistant.py`.
"""

import pytest

from conftest import FakeTelegram

from app.bot import copy, handlers
from app.services import inbox as inbox_svc
from app.services import llm

OWNER = 673615046


def _message(text: str) -> dict:
    return {"message_id": 1, "chat": {"id": OWNER}, "from": {"id": OWNER}, "text": text}


# --- the endpoint ---------------------------------------------------------


def test_the_endpoint_answers_the_admin(client, auth, monkeypatch):
    monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-test")
    monkeypatch.setattr(llm, "chat", lambda *a, **k: "Nothing left today.")

    res = client.post("/api/assistant/chat", json={"message": "what's left?"}, headers=auth)
    assert res.status_code == 200, res.text
    assert res.json() == {"reply": "Nothing left today."}


def test_the_endpoint_is_admin_only(client):
    """It reads his private everything — there is no public view of this."""
    anon = client.__class__(client.app)
    res = anon.post("/api/assistant/chat", json={"message": "what's left?"})
    assert res.status_code == 401


def test_an_unconfigured_model_is_a_503_that_says_why(client, auth, monkeypatch):
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    res = client.post("/api/assistant/chat", json={"message": "what's left?"}, headers=auth)
    assert res.status_code == 503
    assert "DEEPSEEK_API_KEY" in res.json()["detail"]


def test_a_model_failure_is_also_a_503_not_a_500(client, auth, monkeypatch):
    monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-test")
    monkeypatch.setattr(llm, "chat", lambda *a, **k: None)
    res = client.post("/api/assistant/chat", json={"message": "what's left?"}, headers=auth)
    assert res.status_code == 503


def test_an_empty_message_is_rejected_before_the_model(client, auth, monkeypatch):
    monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-test")
    monkeypatch.setattr(llm, "chat", lambda *a, **k: "should not happen")
    res = client.post("/api/assistant/chat", json={"message": "  "}, headers=auth)
    assert res.status_code == 422


def test_history_is_accepted_and_carried(client, auth, monkeypatch):
    monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-test")
    seen = {}
    monkeypatch.setattr(llm, "chat", lambda s, u, **k: seen.update(user=u) or "ok")

    res = client.post(
        "/api/assistant/chat",
        json={
            "message": "and tomorrow?",
            "history": [{"role": "user", "content": "what's on today?"}],
        },
        headers=auth,
    )
    assert res.status_code == 200
    assert "User: what's on today?" in seen["user"]


# --- the bot command ------------------------------------------------------


def test_slash_a_answers_from_the_same_assistant(db, monkeypatch):
    monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-test")
    monkeypatch.setattr(llm, "chat", lambda *a, **k: "Two tasks are overdue.")

    tg = FakeTelegram()
    handlers.handle_message(db, tg, _message("/a what's left today?"), OWNER)

    assert tg.sent[-1]["text"] == "Two tasks are overdue."
    assert inbox_svc.list_items(db) == []  # a question is not a captured thought


def test_slash_ask_is_the_same_command(db, monkeypatch):
    monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-test")
    monkeypatch.setattr(llm, "chat", lambda *a, **k: "All clear.")

    tg = FakeTelegram()
    handlers.handle_message(db, tg, _message("/ask anything outstanding?"), OWNER)
    assert tg.sent[-1]["text"] == "All clear."


def test_a_thinking_answer_shows_the_typing_cue(db, monkeypatch):
    monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-test")
    monkeypatch.setattr(llm, "chat", lambda *a, **k: "Done.")

    tg = FakeTelegram()
    handlers.handle_message(db, tg, _message("/a how am I doing?"), OWNER)
    assert tg.actions == ["typing"]


def test_the_answer_is_escaped_before_it_goes_near_telegram(db, monkeypatch):
    """One stray "<" from a completion would break the whole HTML send."""
    monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-test")
    monkeypatch.setattr(llm, "chat", lambda *a, **k: "use <b> & co")

    tg = FakeTelegram()
    handlers.handle_message(db, tg, _message("/a what tag?"), OWNER)
    assert tg.sent[-1]["text"] == "use &lt;b&gt; &amp; co"


def test_slash_a_with_no_question_explains_itself(db):
    tg = FakeTelegram()
    handlers.handle_message(db, tg, _message("/a"), OWNER)

    text = tg.sent[-1]["text"]
    assert text == copy.ASSISTANT_USAGE
    # It says the two things that surprise people: capture still works, and
    # there is no memory between questions.
    assert "Inbox" in text and "don't remember" in text


def test_an_unconfigured_model_says_so_in_chat_rather_than_failing(db, monkeypatch):
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)

    tg = FakeTelegram()
    handlers.handle_message(db, tg, _message("/a what's left today?"), OWNER)
    assert tg.sent[-1]["text"] == copy.ASSISTANT_UNAVAILABLE


def test_plain_text_is_still_inbox_capture(db):
    """The load-bearing rule: only the command asks a question."""
    tg = FakeTelegram()
    handlers.handle_message(db, tg, _message("what's left today?"), OWNER)
    assert [i.text for i in inbox_svc.list_items(db)] == ["what's left today?"]


@pytest.mark.parametrize("command", ["/a", "/ask"])
def test_the_command_is_owner_locked_like_everything_else(command):
    """The lock is in the dispatcher, above every handler — a stranger's /a
    never reaches the assistant."""
    from app.bot import main

    tg = FakeTelegram()
    main._dispatch(tg, OWNER, {"message": {**_message(f"{command} secrets?"),
                                           "from": {"id": 999}}})
    assert tg.sent[-1]["text"] == copy.REFUSED
