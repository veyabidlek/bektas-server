"""Test fixtures.

The environment has to be set **before** app modules import, because
`app.database` reads DATABASE_URL and `app.services.admin` reads JWT_SECRET at
import time. Each test session gets its own throwaway SQLite file — nothing
here ever touches the production database, which lives inside a Docker volume.
"""

import os
import tempfile

_tmp_db = os.path.join(tempfile.mkdtemp(prefix="bektas-test-"), "test.db")
os.environ["DATABASE_URL"] = f"sqlite:///{_tmp_db}"
os.environ.pop("SUPABASE_DATABASE_URL", None)
os.environ["JWT_SECRET"] = "test-secret-not-the-real-one"
os.environ["SESSION_COOKIE_SECURE"] = "false"
os.environ.pop("GOOGLE_OAUTH_CLIENT_ID", None)
os.environ.pop("GOOGLE_OAUTH_CLIENT_SECRET", None)

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

import app.models  # noqa: F401,E402  — registers every table
from app.database import Base, SessionLocal, engine  # noqa: E402
from app.main import app as fastapi_app  # noqa: E402
from app.services import admin_key  # noqa: E402
from app.services.search_index import drop_search_index, ensure_search_index  # noqa: E402


class FakeTelegram:
    """Records what the bot would have sent.

    Shared by the bot suites: the handlers are exercised for real, only the
    network is replaced. `send_message` hands back an ascending message_id so a
    flow that later edits its own message has something to edit.
    """

    def __init__(self):
        self.sent: list[dict] = []
        self.edits: list[str] = []
        self.edited: list[dict] = []
        self.answers: list[str] = []
        self.files: dict[str, bytes] = {}
        self.commands: list[dict] | None = None
        self.short_description: str | None = None
        self.description: str | None = None
        self.photos: list[dict] = []
        self.actions: list[str] = []

    def set_my_commands(self, commands):
        self.commands = commands

    def set_my_short_description(self, short_description):
        self.short_description = short_description

    def set_my_description(self, description):
        self.description = description

    def send_message(self, chat_id, text, buttons=None, reply_to=None, keyboard=None):
        self.sent.append(
            {"chat_id": chat_id, "text": text, "buttons": buttons, "keyboard": keyboard}
        )
        return {"message_id": len(self.sent)}

    def edit_message(self, chat_id, message_id, text, buttons=None):
        self.edits.append(text)
        self.edited.append({"message_id": message_id, "text": text, "buttons": buttons})

    def send_photo(self, chat_id, data, filename="photo.jpg", caption=None):
        self.photos.append(
            {"chat_id": chat_id, "bytes": len(data), "filename": filename, "caption": caption}
        )

    def send_chat_action(self, chat_id, action="typing"):
        self.actions.append(action)

    def answer_callback(self, callback_id, text=""):
        self.answers.append(text)

    def download_file(self, file_id):
        return self.files.get(file_id)


@pytest.fixture(autouse=True)
def _reset_rate_limiter():
    """The per-IP limiter is module-level and in-memory.

    Every test calls from the same "address", so without this a test that
    deliberately sends bad keys would rate-limit the next test out of logging
    in — which is exactly what happened the first time this suite ran.
    """
    from app.services.admin import _rate_limits

    _rate_limits.clear()
    yield
    _rate_limits.clear()


@pytest.fixture()
def db():
    Base.metadata.create_all(bind=engine)
    # The search index is a virtual table, so `drop_all` neither creates nor
    # removes it — without building and tearing it down here, one test's rows
    # would still be findable in the next one.
    ensure_search_index(engine)
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()
        drop_search_index(engine)
        Base.metadata.drop_all(bind=engine)


@pytest.fixture()
def client(db):
    with TestClient(fastapi_app) as c:
        yield c


@pytest.fixture()
def key_document(db):
    """A freshly issued key file, as the CLI would write it."""
    return admin_key.issue_key(db)


@pytest.fixture()
def auth(client, key_document):
    """Logged-in Authorization header, obtained the way the UI does it."""
    res = client.post("/api/admin/login", data={"key": key_document["key"]})
    assert res.status_code == 200, res.text
    return {"Authorization": f"Bearer {res.json()['token']}"}
