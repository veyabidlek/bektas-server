"""The media half of the Islam section: books he is reading and audio he is
listening to, each with its own notes and sessions.

The two halves are deliberately **separate tables** rather than one `items`
table with a `type` column. They diverge where it matters — a book note points
at a page range, an audio note at a free-text position ("episode 3", "1:12:00");
a book session counts pages, an audio session counts minutes — and a shared
table would have to carry both sets of columns half-empty forever.

Covers live on the Docker volume (``/data/uploads/islam``) with only the
filename here, the same split the diary's and the portfolio's photos use. They
are served through an **auth-checked route**: this whole section is private.
"""

from sqlalchemy import ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base

# Where a book or an audio item is in its life. `shelved` is "put down, not
# abandoned" — kept visible rather than deleted, like reading_items.abandoned.
MEDIA_STATUSES = ("reading", "finished", "shelved")

# An audiobook has an author reading a text; a playlist is a set of lectures or
# recitations. Different enough to filter on, not different enough to split.
AUDIO_KINDS = ("audiobook", "playlist")


class IslamBook(Base):
    __tablename__ = "islam_books"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    title: Mapped[str] = mapped_column(String, nullable=False)
    author: Mapped[str | None] = mapped_column(String, nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Filename on the volume, not bytes and not a URL. NULL = no cover yet.
    cover_image: Mapped[str | None] = mapped_column(String, nullable=True)
    status: Mapped[str] = mapped_column(String, nullable=False, default="reading")
    total_pages: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[str] = mapped_column(String, nullable=False)

    notes: Mapped[list["IslamBookNote"]] = relationship(
        back_populates="book", cascade="all, delete-orphan"
    )
    sessions: Mapped[list["IslamBookSession"]] = relationship(
        back_populates="book", cascade="all, delete-orphan"
    )


class IslamBookNote(Base):
    """A thought while reading, optionally about a page range."""

    __tablename__ = "islam_book_notes"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    book_id: Mapped[str] = mapped_column(
        String, ForeignKey("islam_books.id", ondelete="CASCADE"), nullable=False, index=True
    )
    date: Mapped[str] = mapped_column(String, nullable=False, index=True)
    page_from: Mapped[int | None] = mapped_column(Integer, nullable=True)
    page_to: Mapped[int | None] = mapped_column(Integer, nullable=True)
    body_md: Mapped[str] = mapped_column(Text, nullable=False, default="")

    book: Mapped["IslamBook"] = relationship(back_populates="notes")


class IslamBookSession(Base):
    """A sitting with the book: how many pages, and how long if he timed it."""

    __tablename__ = "islam_book_sessions"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    book_id: Mapped[str] = mapped_column(
        String, ForeignKey("islam_books.id", ondelete="CASCADE"), nullable=False, index=True
    )
    date: Mapped[str] = mapped_column(String, nullable=False, index=True)
    pages: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    minutes: Mapped[int | None] = mapped_column(Integer, nullable=True)

    book: Mapped["IslamBook"] = relationship(back_populates="sessions")


class IslamAudio(Base):
    __tablename__ = "islam_audio"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    title: Mapped[str] = mapped_column(String, nullable=False)
    # "author" for a book, "creator" for audio — the reciter, shaykh or channel.
    creator: Mapped[str | None] = mapped_column(String, nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    cover_image: Mapped[str | None] = mapped_column(String, nullable=True)
    kind: Mapped[str] = mapped_column(String, nullable=False, default="audiobook")
    status: Mapped[str] = mapped_column(String, nullable=False, default="reading")
    created_at: Mapped[str] = mapped_column(String, nullable=False)

    notes: Mapped[list["IslamAudioNote"]] = relationship(
        back_populates="audio", cascade="all, delete-orphan"
    )
    sessions: Mapped[list["IslamAudioSession"]] = relationship(
        back_populates="audio", cascade="all, delete-orphan"
    )


class IslamAudioNote(Base):
    __tablename__ = "islam_audio_notes"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    audio_id: Mapped[str] = mapped_column(
        String, ForeignKey("islam_audio.id", ondelete="CASCADE"), nullable=False, index=True
    )
    date: Mapped[str] = mapped_column(String, nullable=False, index=True)
    # Free text — "episode 3", "1:12:00", "second half". A number would have to
    # pick a unit, and the sources do not agree on one.
    position: Mapped[str | None] = mapped_column(String, nullable=True)
    body_md: Mapped[str] = mapped_column(Text, nullable=False, default="")

    audio: Mapped["IslamAudio"] = relationship(back_populates="notes")


class IslamAudioSession(Base):
    """Listening is measured in minutes only — there are no pages to count."""

    __tablename__ = "islam_audio_sessions"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    audio_id: Mapped[str] = mapped_column(
        String, ForeignKey("islam_audio.id", ondelete="CASCADE"), nullable=False, index=True
    )
    date: Mapped[str] = mapped_column(String, nullable=False, index=True)
    minutes: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    audio: Mapped["IslamAudio"] = relationship(back_populates="sessions")
