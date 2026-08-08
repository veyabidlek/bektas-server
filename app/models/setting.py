from sqlalchemy import String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class Setting(Base):
    """Tiny key/value store for server-side state that is not a domain object.

    Currently: the Google OAuth refresh token + the connected account's email.
    It lives in the database (on the named volume) rather than in a file so it
    survives ``docker compose up --build``, which replaces the image layer.
    """

    __tablename__ = "settings"

    key: Mapped[str] = mapped_column(String, primary_key=True)
    value: Mapped[str] = mapped_column(Text, nullable=False, default="")
