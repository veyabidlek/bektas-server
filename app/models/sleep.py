from sqlalchemy import JSON, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class SleepNight(Base):
    """One row per night, keyed by the morning he woke up.

    The date **is** the identity, the same call `diary_entries` makes: the
    Apple Shortcut runs every morning and may run twice, and a second POST for
    the same night has to replace that night rather than grow a second row.

    Both halves are stored on purpose. The aggregates are what every read
    wants, and `segments` is the raw sample list exactly as it arrived —
    already parsed and normalized, but not yet collapsed. Sleep staging is the
    part of this pipeline most likely to be re-thought (merge windows, what
    counts as awake, a stage Apple adds next year), and a re-analysis is only
    possible if the minutes it should be computed from were kept. They are a
    few kilobytes a night.

    A `None` on a stage column means **the band did not report that stage**,
    not that it measured zero — see `services/sleep_night.py`. Only
    `asleep_minutes` is always a number.
    """

    __tablename__ = "sleep_nights"

    # YYYY-MM-DD, Almaty — the local date of the last sample's end.
    date: Mapped[str] = mapped_column(String, primary_key=True)
    in_bed_minutes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    asleep_minutes: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    deep_minutes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    rem_minutes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    core_minutes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    awake_minutes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # ISO 8601 with the Almaty offset, like every other timestamp here.
    bedtime: Mapped[str | None] = mapped_column(String, nullable=True)
    wake_time: Mapped[str | None] = mapped_column(String, nullable=True)
    # [{"start": iso, "end": iso, "stage": "deep"}, ...] — kept for re-analysis.
    segments: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    created_at: Mapped[str] = mapped_column(String, nullable=False)
    updated_at: Mapped[str] = mapped_column(String, nullable=False)
