from sqlalchemy import Boolean, String
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class AdminKey(Base):
    """A credential *file* that logs Bektas in — the replacement for the passcode.

    Only the SHA-256 of the secret is stored, so the database is not a copy of
    the credential. Re-issuing (``python -m app.issue_key``) revokes every
    existing row, so an old bekonai.key stops working the moment a new one is
    generated.
    """

    __tablename__ = "admin_keys"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    secret_hash: Mapped[str] = mapped_column(String, nullable=False)
    issued_at: Mapped[str] = mapped_column(String, nullable=False)
    revoked: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    last_used_at: Mapped[str | None] = mapped_column(String, nullable=True)
