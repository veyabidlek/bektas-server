"""Cover images for Islam books and audio.

Books and audio store their cover as a bare **filename** on the row rather than
in a table of their own — a cover is one-to-one with the thing it pictures, and
a second table would buy nothing but a join.

The bytes go to the named volume (``/data/uploads/islam``), downscaled on the
way in, exactly like the diary's photos. They are served through an
auth-checked route: the portfolio's public-image exception does **not** apply
here, this whole section is private.

The mechanics are `cover_files.py`, shared with the reading shelf. What stays
here is the one thing that is this section's own: the directory. The wrappers
read `UPLOAD_DIR` at call time on purpose — the tests point it at a tmp_path.
"""

import os
from pathlib import Path

from app.services import cover_files
from app.services.cover_files import MAX_UPLOAD_BYTES, media_type  # noqa: F401  — re-exported

UPLOAD_DIR = Path(os.getenv("UPLOAD_DIR", "/data/uploads")) / "islam"


def path_for(filename: str) -> Path:
    return cover_files.path_for(UPLOAD_DIR, filename)


def save_cover(owner_id: str, data: bytes, content_type: str) -> str:
    return cover_files.save_cover(UPLOAD_DIR, owner_id, data, content_type)


def delete_cover(filename: str | None) -> None:
    cover_files.delete_cover(UPLOAD_DIR, filename)
