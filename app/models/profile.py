from sqlalchemy import Integer, String, Text
from sqlalchemy.dialects.postgresql import JSON
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class Profile(Base):
    __tablename__ = "profile"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)
    tagline: Mapped[str] = mapped_column(String, nullable=False, default="")
    short_bio: Mapped[str] = mapped_column(Text, nullable=False, default="")
    long_bio: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    social_links: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
