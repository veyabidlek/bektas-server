"""The Quran half of the Islam section: khatms, the reading log, sura notes
and the prayer grid.

Everything here is **private**. Unlike the reading list or the portfolio there
is no public view of any of it, not even a degraded one — the same rule the
diary and the calendar follow.
"""

from sqlalchemy import ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base

# A full mushaf. The default target of a khatm, and the ceiling every logged
# page range is checked against.
QURAN_PAGES = 604

# `individual` is his own khatm start to finish; `shared` is one he is taking a
# slice of with other people, and then `portion` says which slice.
KHATM_KINDS = ("individual", "shared")


class Khatm(Base):
    """One Quran khatm — several run at once on purpose.

    `pages_logged` is deliberately **not** a column. It is the sum of the log
    entries' ranges, computed on read: a stored counter can drift away from the
    entries that produced it the first time a row is deleted, and a number that
    disagrees with its own inputs is worse than no number (the same reasoning
    that kept `reading_items` from storing "Day Count").
    """

    __tablename__ = "quran_khatms"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    name: Mapped[str] = mapped_column(String, nullable=False)
    kind: Mapped[str] = mapped_column(String, nullable=False, default="individual")
    # Only meaningful for a shared khatm, and free text on purpose — "juz 5",
    # "pages 81-100", "Ya-Sin" are all things he might be handed.
    portion: Mapped[str | None] = mapped_column(String, nullable=True)
    target_pages: Mapped[int] = mapped_column(Integer, nullable=False, default=QURAN_PAGES)
    started_at: Mapped[str] = mapped_column(String, nullable=False)
    # NULL while it is still running. Set = finished, and the list sorts on it.
    completed_at: Mapped[str | None] = mapped_column(String, nullable=True)

    entries: Mapped[list["QuranLogEntry"]] = relationship(
        back_populates="khatm",
        cascade="all, delete-orphan",
    )


class QuranLogEntry(Base):
    """A sitting: "on this day I read pages 41 to 60 of that khatm".

    The range is inclusive at both ends, so a single page is `41..41` and the
    pages it accounts for are `page_to - page_from + 1`.
    """

    __tablename__ = "quran_log_entries"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    khatm_id: Mapped[str] = mapped_column(
        String,
        ForeignKey("quran_khatms.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    date: Mapped[str] = mapped_column(String, nullable=False, index=True)  # YYYY-MM-DD
    page_from: Mapped[int] = mapped_column(Integer, nullable=False)
    page_to: Mapped[int] = mapped_column(Integer, nullable=False)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)

    khatm: Mapped["Khatm"] = relationship(back_populates="entries")


class SuraNote(Base):
    """What he has understood about one surah — **one** note per surah.

    The surah number *is* the identity (1..114), exactly like the diary's day:
    writing about al-Baqara again edits that note rather than starting a second
    one, so the UI needs no create/update decision.
    """

    __tablename__ = "sura_notes"

    surah: Mapped[int] = mapped_column(Integer, primary_key=True)  # 1..114
    body_md: Mapped[str] = mapped_column(Text, nullable=False, default="")
    updated_at: Mapped[str] = mapped_column(String, nullable=False)


# The five obligatory prayers plus the two he tracks on top of them.
PRAYERS = ("fajr", "dhuhr", "asr", "maghrib", "isha", "awwabin", "tahajjud")

# How it was prayed. `qaza_restored` is a missed prayer made up later — worth
# distinguishing from both `in_time` and `skipped`, because it is the recovery.
PRAYER_STATUSES = ("in_time", "late", "skipped", "qaza_restored")

# And how it *felt*. Separate from status on purpose: a prayer can be on time
# and absent-minded, which is the thing worth seeing on a month grid.
PRAYER_QUALITIES = ("focus", "lazy")


class PrayerMark(Base):
    """One cell of the prayer grid.

    A row exists only where something was actually marked — an untouched day is
    an absence, not seven NULL rows, and clearing both fields deletes the row
    again. That keeps "he has not filled this in" and "he skipped it"
    distinguishable, which a boolean grid could never do.
    """

    __tablename__ = "prayer_marks"
    __table_args__ = (UniqueConstraint("date", "prayer", name="uq_prayer_date_name"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    date: Mapped[str] = mapped_column(String, nullable=False, index=True)  # YYYY-MM-DD
    prayer: Mapped[str] = mapped_column(String, nullable=False)
    status: Mapped[str | None] = mapped_column(String, nullable=True)
    quality: Mapped[str | None] = mapped_column(String, nullable=True)
