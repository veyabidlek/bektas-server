"""One small DeepSeek call, for the parts of this site that want prose.

Three rules, all of them the same rule the Google sync follows:

1. **Config-driven.** No `DEEPSEEK_API_KEY` means no summary, not an error.
2. **It never raises.** Every failure — no key, a timeout, a 500, an empty
   completion — comes back as `None`, and the caller drops its section. A
   weekly digest that does not arrive because a model was busy would be a
   worse product than one without its paragraph.
3. **urllib, not a client library.** One endpoint, and the production image
   stays free of a dependency it would use once (see `gcal.py`).

⚠️ DeepSeek's current family are REASONING models: `max_tokens` covers the
reasoning trace *and* the visible content, so a tight budget returns HTTP 200
with an EMPTY `content`. Give it room. `deepseek-chat` is retired — the model
name to use is `deepseek-v4-flash`.
"""

from __future__ import annotations

import json
import logging
import os
import urllib.error
import urllib.request

log = logging.getLogger("llm")

API_URL = "https://api.deepseek.com/chat/completions"
DEFAULT_MODEL = "deepseek-v4-flash"
TIMEOUT_SECONDS = 30


def configured() -> bool:
    return bool(os.getenv("DEEPSEEK_API_KEY", "").strip())


def _model() -> str:
    return os.getenv("DEEPSEEK_MODEL", "").strip() or DEFAULT_MODEL


def chat(
    system: str,
    user: str,
    *,
    max_tokens: int = 2000,
    temperature: float = 0.6,
    timeout: int = TIMEOUT_SECONDS,
) -> str | None:
    """The assistant's reply, or None if anything at all went wrong."""
    key = os.getenv("DEEPSEEK_API_KEY", "").strip()
    if not key:
        log.info("DEEPSEEK_API_KEY is not set — skipping the summary")
        return None

    payload = json.dumps(
        {
            "model": _model(),
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "max_tokens": max_tokens,
            "temperature": temperature,
        }
    ).encode("utf-8")

    request = urllib.request.Request(API_URL, data=payload, method="POST")
    request.add_header("Content-Type", "application/json")
    request.add_header("Authorization", f"Bearer {key}")

    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            body = json.loads(response.read().decode("utf-8"))
        choice = body["choices"][0]
        content = (choice["message"].get("content") or "").strip()
        if content:
            return content
        # HTTP 200 with nothing in it: the failure mode worth logging with its
        # numbers, because the fix is a bigger budget, not a retry.
        usage = body.get("usage") or {}
        log.warning(
            "deepseek returned empty content (finish=%s, completion_tokens=%s, max_tokens=%s)",
            choice.get("finish_reason"),
            usage.get("completion_tokens"),
            max_tokens,
        )
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", "ignore")[:200]
        log.warning("deepseek failed: %s %s", exc.code, detail)
    except Exception:  # noqa: BLE001 — the caller degrades, so nothing escapes
        log.warning("deepseek call failed", exc_info=True)
    return None
