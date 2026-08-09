"""A very small Telegram client.

urllib rather than a bot framework: this bot has one user, a handful of message
shapes and no plugins, and the production image already avoids dependencies it
does not need (the Google Calendar sync is built the same way).
"""

from __future__ import annotations

import json
import logging
import urllib.error
import urllib.parse
import urllib.request

log = logging.getLogger("bot.client")

API_ROOT = "https://api.telegram.org"
# Long-poll window. Telegram holds the connection open until something arrives.
POLL_TIMEOUT = 30
HTTP_TIMEOUT = POLL_TIMEOUT + 15


class TelegramError(RuntimeError):
    pass


class TelegramClient:
    def __init__(self, token: str):
        self._token = token

    def _call(self, method: str, payload: dict | None = None, timeout: int | None = None) -> dict:
        url = f"{API_ROOT}/bot{self._token}/{method}"
        data = json.dumps(payload or {}).encode("utf-8")
        req = urllib.request.Request(url, data=data, method="POST")
        req.add_header("Content-Type", "application/json")

        try:
            with urllib.request.urlopen(req, timeout=timeout or HTTP_TIMEOUT) as resp:
                body = json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", "ignore")[:300]
            raise TelegramError(f"{method} failed: {exc.code} {detail}") from exc
        except OSError as exc:
            raise TelegramError(f"{method} failed: {exc}") from exc

        if not body.get("ok"):
            raise TelegramError(f"{method} failed: {body.get('description')}")
        return body.get("result")

    # --- receiving ---

    def get_updates(self, offset: int | None = None) -> list[dict]:
        return self._call(
            "getUpdates",
            {
                "timeout": POLL_TIMEOUT,
                "offset": offset,
                # Only what this bot acts on.
                "allowed_updates": ["message", "callback_query"],
            },
        )

    def get_me(self) -> dict:
        return self._call("getMe", timeout=15)

    # --- profile (menu + about text) ---

    def set_my_commands(self, commands: list[dict]) -> None:
        """Publish the blue "Menu"/"/" command list. Default scope, no language —
        a one-user bot needs no per-scope complexity. Raises on failure; the
        caller decides whether that is fatal (it is not — see main._register_profile)."""
        self._call("setMyCommands", {"commands": commands}, timeout=15)

    def set_my_description(self, description: str) -> None:
        """The longer about text shown on the bot's profile / empty-chat screen."""
        self._call("setMyDescription", {"description": description}, timeout=15)

    def set_my_short_description(self, short_description: str) -> None:
        """The one-line tagline under the bot's name."""
        self._call("setMyShortDescription", {"short_description": short_description}, timeout=15)

    def download_file(self, file_id: str) -> bytes | None:
        """Photo bytes, or None if Telegram will not give them up."""
        try:
            info = self._call("getFile", {"file_id": file_id}, timeout=30)
            path = info.get("file_path")
            if not path:
                return None
            url = f"{API_ROOT}/file/bot{self._token}/{path}"
            with urllib.request.urlopen(url, timeout=60) as resp:
                return resp.read()
        except (TelegramError, OSError) as exc:
            log.warning("could not download %s: %s", file_id, exc)
            return None

    # --- sending ---

    def send_message(
        self,
        chat_id: int,
        text: str,
        buttons: list[list[dict]] | None = None,
        reply_to: int | None = None,
        keyboard: list[list[str]] | None = None,
    ) -> dict | None:
        payload: dict = {
            "chat_id": chat_id,
            "text": text,
            "parse_mode": "HTML",
            "disable_web_page_preview": True,
        }
        # A message carries one reply_markup. Inline buttons (a flow) win; the
        # persistent keyboard is a chat-level thing Telegram keeps showing from
        # the last message that set it, so it survives inline-button messages.
        if buttons:
            payload["reply_markup"] = {"inline_keyboard": buttons}
        elif keyboard:
            payload["reply_markup"] = reply_keyboard(keyboard)
        if reply_to:
            payload["reply_to_message_id"] = reply_to
            payload["allow_sending_without_reply"] = True

        try:
            return self._call("sendMessage", payload, timeout=30)
        except TelegramError as exc:
            # A send failure must never kill the poll loop.
            log.warning("send failed: %s", exc)
            return None

    def edit_message(
        self,
        chat_id: int,
        message_id: int,
        text: str,
        buttons: list[list[dict]] | None = None,
    ) -> None:
        """Rewrite a message in place. Without `buttons` its keyboard is dropped,
        which is what a settled confirmation wants."""
        payload: dict = {
            "chat_id": chat_id,
            "message_id": message_id,
            "text": text,
            "parse_mode": "HTML",
        }
        if buttons:
            payload["reply_markup"] = {"inline_keyboard": buttons}
        try:
            self._call("editMessageText", payload, timeout=30)
        except TelegramError as exc:
            log.warning("edit failed: %s", exc)

    def answer_callback(self, callback_id: str, text: str = "") -> None:
        try:
            self._call(
                "answerCallbackQuery",
                {"callback_query_id": callback_id, "text": text},
                timeout=15,
            )
        except TelegramError as exc:
            log.warning("callback ack failed: %s", exc)


def button(text: str, data: str) -> dict:
    return {"text": text, "callback_data": data}


def reply_keyboard(rows: list[list[str]]) -> dict:
    """A persistent ReplyKeyboardMarkup — tappable buttons above the text box.

    `is_persistent` keeps it up after a tap; `resize_keyboard` shrinks it to fit.
    """
    return {
        "keyboard": [[{"text": label} for label in row] for row in rows],
        "resize_keyboard": True,
        "is_persistent": True,
    }
