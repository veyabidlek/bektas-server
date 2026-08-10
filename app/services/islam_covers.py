"""Cover images for Islam books and audio.

Books and audio store their cover as a bare **filename** on the row rather than
in a table of their own — a cover is one-to-one with the thing it pictures, and
a second table would buy nothing but a join.

The bytes go to the named volume (``/data/uploads/islam``), downscaled on the
way in, exactly like the diary's photos. They are served through an
auth-checked route: the portfolio's public-image exception does **not** apply
here, this whole section is private.
"""

import os
import uuid
from pathlib import Path

from app.services.image_optimize import dimensions, optimize_image

UPLOAD_DIR = Path(os.getenv("UPLOAD_DIR", "/data/uploads")) / "islam"

MAX_UPLOAD_BYTES = 25 * 1024 * 1024

# Only what optimize_image can emit. The content type is not stored — the
# extension is the single source of truth for it, so the two cannot disagree.
_TYPE_BY_EXT = {
    "jpg": "image/jpeg",
    "jpeg": "image/jpeg",
    "png": "image/png",
    "webp": "image/webp",
}


def media_type(filename: str) -> str:
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    return _TYPE_BY_EXT.get(ext, "application/octet-stream")


def path_for(filename: str) -> Path:
    return UPLOAD_DIR / filename


def save_cover(owner_id: str, data: bytes, content_type: str) -> str:
    """Write the optimized bytes and hand back the filename to store.

    The name carries a fresh random suffix rather than being `<id>.jpg`: a
    replaced cover must not land on the old path, or a browser that cached the
    first one would keep showing it.
    """
    body, _out_type, ext = optimize_image(data, content_type)
    dimensions(body)  # decodes early: a file Pillow cannot read is worth knowing about

    filename = f"{owner_id}-{uuid.uuid4().hex[:8]}.{ext}"
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    path_for(filename).write_bytes(body)
    return filename


def delete_cover(filename: str | None) -> None:
    """Best effort — a missing file must never block replacing or deleting the
    row that points at it."""
    if not filename:
        return
    try:
        path_for(filename).unlink(missing_ok=True)
    except OSError:
        pass
