"""What an inbox item became.

The reference is one string — "task:abc123", "article:my-post", "event:9f2",
"diary:2026-08-08" or "dismissed" — so adding a triage target later (a phase-3
Telegram reply, say) costs a constant, not a migration.

Pure on purpose: parsing, building and the "may this be triaged?" rule are the
seams worth testing without a database behind them.
"""

from __future__ import annotations

# Targets an item can become. "dismissed" is a real outcome, not an absence:
# deciding something does not matter is a decision worth recording.
KINDS = ("task", "article", "event", "diary", "dismissed")

# The ones that point at another object and therefore carry an id.
REFERENCE_KINDS = ("task", "article", "event", "diary")

SEPARATOR = ":"


class TriageError(ValueError):
    """Raised for a triage that does not make sense."""


def is_valid_kind(kind: str) -> bool:
    return kind in KINDS


def make_ref(kind: str, target_id: str | None = None) -> str:
    """Build the stored reference for a triage outcome."""
    if not is_valid_kind(kind):
        raise TriageError(f"Unknown triage target: {kind!r}")

    if kind == "dismissed":
        return "dismissed"

    identifier = (target_id or "").strip()
    if not identifier:
        raise TriageError(f"Triaging to {kind!r} needs the id of what was created")
    if SEPARATOR in identifier:
        # Otherwise the ref could not be parsed back apart.
        raise TriageError("Target id may not contain ':'")

    return f"{kind}{SEPARATOR}{identifier}"


def parse_ref(ref: str | None) -> tuple[str | None, str | None]:
    """(kind, id) for a stored reference. (None, None) when untriaged.

    Anything unrecognised comes back as (None, None) rather than raising: a row
    written by an older or newer version must not break the list endpoint.
    """
    if not ref:
        return None, None
    if ref == "dismissed":
        return "dismissed", None

    kind, _, identifier = ref.partition(SEPARATOR)
    if kind in REFERENCE_KINDS and identifier:
        return kind, identifier
    return None, None


def is_triaged(ref: str | None) -> bool:
    kind, _ = parse_ref(ref)
    return kind is not None


def ensure_triageable(ref: str | None) -> None:
    """An item is triaged once. Doing it twice would orphan the first object."""
    if is_triaged(ref):
        kind, identifier = parse_ref(ref)
        became = kind if identifier is None else f"{kind} {identifier}"
        raise TriageError(f"Already triaged — it became {became}")


def title_from_text(text: str, fallback: str = "Атаусыз") -> str:
    """First meaningful line, for a task title or a writing's headline."""
    for line in text.splitlines():
        cleaned = line.strip().lstrip("#").strip()
        if cleaned:
            return cleaned[:120]
    return fallback


def slugify(text: str, fallback: str = "note") -> str:
    """A URL-safe slug, transliterating Cyrillic so a Kazakh note keeps a readable one."""
    table = {
        "а": "a", "ә": "a", "б": "b", "в": "v", "г": "g", "ғ": "g", "д": "d",
        "е": "e", "ё": "yo", "ж": "zh", "з": "z", "и": "i", "й": "y", "к": "k",
        "қ": "q", "л": "l", "м": "m", "н": "n", "ң": "n", "о": "o", "ө": "o",
        "п": "p", "р": "r", "с": "s", "т": "t", "у": "u", "ұ": "u", "ү": "u",
        "ф": "f", "х": "h", "һ": "h", "ц": "ts", "ч": "ch", "ш": "sh",
        "щ": "sch", "ъ": "", "ы": "y", "і": "i", "ь": "", "э": "e", "ю": "yu",
        "я": "ya",
    }

    out: list[str] = []
    for char in text.lower():
        if char in table:
            out.append(table[char])
        elif char.isalnum() and char.isascii():
            out.append(char)
        elif char in " -_\t\n":
            out.append("-")

    slug = "".join(out)
    while "--" in slug:
        slug = slug.replace("--", "-")
    slug = slug.strip("-")[:60].strip("-")
    return slug or fallback
