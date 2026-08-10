"""Cover images for the reading shelf.

The mechanics are `cover_files.py`, shared with the Islam shelf; what is this
module's own is the directory — ``/data/uploads/reading`` on the named volume,
never in the image layer and never in SQLite. `scripts/backup.sh` tars all of
`/data/uploads`, so these are captured already.

The **serving** rule is the other difference, and it is the portfolio's, not
the diary's: `/reading` is a page anyone can look at, so a cover has to load
for a logged-out visitor. `GET /api/reading/covers/{id}` therefore carries no
auth dependency and is `Cache-Control: public`. Upload and delete stay
admin-only.

The wrappers read `UPLOAD_DIR` at call time on purpose — the tests point it at
a tmp_path.
"""

import os
from pathlib import Path

from app.services import cover_files
from app.services.cover_files import MAX_UPLOAD_BYTES, media_type  # noqa: F401  — re-exported

UPLOAD_DIR = Path(os.getenv("UPLOAD_DIR", "/data/uploads")) / "reading"


def path_for(filename: str) -> Path:
    return cover_files.path_for(UPLOAD_DIR, filename)


def save_cover(owner_id: str, data: bytes, content_type: str) -> str:
    return cover_files.save_cover(UPLOAD_DIR, owner_id, data, content_type)


def delete_cover(filename: str | None) -> None:
    cover_files.delete_cover(UPLOAD_DIR, filename)
