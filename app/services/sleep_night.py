"""A night's sleep, computed from Apple Health samples — pure, no database.

The samples arrive from a hand-built Apple Shortcut (Huawei Band 7 → Huawei
Health → Apple Health → here), which is why everything in this module is
written to be *liberal about what it accepts and strict about what it stores*.
A recipe assembled by tapping boxes on a phone will spell a stage
"AsleepDeep" one morning and "Deep " the next, and it will hand over a
timestamp with no offset at all.

Three decisions worth keeping:

* **A night belongs to the morning you woke up.** Its `date` is the local
  (Almaty) date of the *latest* segment end, so a 23:00 → 07:00 night is filed
  under the 07:00 day and re-running the shortcut lands on the same row.
* **Overlaps are merged, never summed.** Apple Health routinely holds two
  sources describing the same minutes (the watch and the phone, or two writes
  of one night). Adding them up invents sleep; the union counts each minute
  once.
* **A stage with no samples is `None`, not `0`.** "The band did not report
  REM" and "he got no REM" are different facts, and only one of them is
  something to be told about. `asleep_minutes` is the exception — it is always
  a number, because the whole night is what was asked for.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timedelta

from app.services.calendar import ASTANA

#: Apple's stage names, in whatever spacing and case a Shortcut emits them.
#: The key is the name with everything that is not a letter or digit removed
#: and lowercased, so "In Bed", "in_bed" and "InBed" are one key.
STAGE_ALIASES: dict[str, str] = {
    "inbed": "in_bed",
    "asleep": "asleep",
    "asleepunspecified": "asleep",
    "unspecified": "asleep",
    "core": "core",
    "asleepcore": "core",
    "deep": "deep",
    "asleepdeep": "deep",
    "rem": "rem",
    "asleeprem": "rem",
    "awake": "awake",
}

#: The stages that count as sleeping. An unrecognized stage joins them — see
#: `normalize_stage`: under-counting a night is the worse mistake.
SLEEP_STAGES = ("asleep", "core", "deep", "rem")

#: Every bucket the stored night carries a number for.
STAGE_BUCKETS = (*SLEEP_STAGES, "awake", "in_bed")

#: Longer than this and the sample is garbage — a single "asleep" spanning
#: three days is a broken export, not a nap.
MAX_SEGMENT = timedelta(hours=24)

#: HealthKit sometimes hands over the raw enum name rather than the label.
_HK_PREFIX = "hkcategoryvaluesleepanalysis"


@dataclass(frozen=True)
class Segment:
    """One sample: when it started, when it ended, and what it was."""

    start: datetime
    end: datetime
    stage: str


def normalize_stage(raw: str) -> tuple[str, bool]:
    """`("deep", True)` — the canonical stage, and whether it was recognized.

    An unknown name is mapped to `asleep` on purpose: a stage this code has
    never heard of is far more likely to be a new *sleep* stage than a new kind
    of wakefulness, and counting it keeps the night's total honest. The `False`
    travels back to the caller so the shortcut can be fixed rather than quietly
    mis-reporting forever.
    """
    key = re.sub(r"[^a-z0-9]", "", (raw or "").lower())
    key = key.removeprefix(_HK_PREFIX)
    stage = STAGE_ALIASES.get(key)
    return (stage, True) if stage else ("asleep", False)


def parse_dt(raw: str) -> datetime:
    """A timestamp from the shortcut, as an aware datetime.

    ISO 8601 with an offset is what the recipe should send. Without one, the
    value is *his* local time — Almaty, the same call `calendar.normalize_dt`
    makes. `ValueError` names the value that could not be read, because a
    shortcut is debugged by reading the error on the phone.
    """
    text = (raw or "").strip()
    if not text:
        raise ValueError("empty timestamp")
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00").replace(" ", "T", 1))
    except ValueError as exc:
        raise ValueError(f"{text!r} is not a recognizable timestamp") from exc
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=ASTANA)


def _merged(spans: list[tuple[datetime, datetime]]) -> list[tuple[datetime, datetime]]:
    """The union of a set of intervals, so no minute is counted twice."""
    out: list[tuple[datetime, datetime]] = []
    for start, end in sorted(spans):
        if out and start <= out[-1][1]:
            out[-1] = (out[-1][0], max(out[-1][1], end))
        else:
            out.append((start, end))
    return out


def _minutes(segments: list[Segment], stages: tuple[str, ...]) -> int | None:
    """Merged minutes across `stages`, or None when none of them was reported."""
    spans = [(s.start, s.end) for s in segments if s.stage in stages]
    if not spans:
        return None
    total = sum((end - start).total_seconds() for start, end in _merged(spans))
    return round(total / 60)


@dataclass(frozen=True)
class Night:
    """The stored shape: one row, one night, all minutes already merged."""

    date: str
    in_bed_minutes: int | None
    asleep_minutes: int
    deep_minutes: int | None
    rem_minutes: int | None
    core_minutes: int | None
    awake_minutes: int | None
    bedtime: str | None
    wake_time: str | None


def usable(segments: list[Segment]) -> list[Segment]:
    """Samples worth counting: positive length, and shorter than a day."""
    return [s for s in segments if s.start < s.end and s.end - s.start <= MAX_SEGMENT]


def aggregate(segments: list[Segment], date: str | None = None) -> Night | None:
    """One night from many samples, or None when nothing usable came in."""
    kept = usable(segments)
    if not kept:
        return None

    asleep = sorted((s for s in kept if s.stage in SLEEP_STAGES), key=lambda s: s.start)
    # The morning he woke up, not the evening he lay down.
    latest_end = max(s.end for s in kept)

    return Night(
        date=date or latest_end.astimezone(ASTANA).date().isoformat(),
        in_bed_minutes=_minutes(kept, ("in_bed",)),
        asleep_minutes=_minutes(kept, SLEEP_STAGES) or 0,
        deep_minutes=_minutes(kept, ("deep",)),
        rem_minutes=_minutes(kept, ("rem",)),
        core_minutes=_minutes(kept, ("core",)),
        awake_minutes=_minutes(kept, ("awake",)),
        bedtime=asleep[0].start.astimezone(ASTANA).isoformat() if asleep else None,
        wake_time=max(s.end for s in asleep).astimezone(ASTANA).isoformat() if asleep else None,
    )
