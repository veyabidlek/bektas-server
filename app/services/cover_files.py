"""The directory-agnostic half of cover handling.

Two shelves keep a cover as a bare **filename** on the row it pictures rather
than in a table of their own — the Islam shelf (`/data/uploads/islam`, private)
and the reading shelf (`/data/uploads/reading`, public). Everything they share
is here; the one thing that differs is the directory, which the caller passes
in. Whether the bytes are then served behind `require_admin` or to anyone is a
routing decision, not a storage one, so it does not appear in this file.

The rules that must hold for both: the bytes are downscaled on the way in, and
a replacement gets a **fresh random name** — reusing the path leaves a cached
browser showing the previous picture.
"""

import uuid
from pathlib import Path

from app.services.image_optimize import dimensions, optimize_image

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


def path_for(directory: Path, filename: str) -> Path:
    return directory / filename


def save_cover(directory: Path, owner_id: str, data: bytes, content_type: str) -> str:
    """Write the optimized bytes and hand back the filename to store.

    The name carries a fresh random suffix rather than being `<id>.jpg`: a
    replaced cover must not land on the old path, or a browser that cached the
    first one would keep showing it.
    """
    body, _out_type, ext = optimize_image(data, content_type)
    dimensions(body)  # decodes early: a file Pillow cannot read is worth knowing about

    filename = f"{owner_id}-{uuid.uuid4().hex[:8]}.{ext}"
    directory.mkdir(parents=True, exist_ok=True)
    path_for(directory, filename).write_bytes(body)
    return filename


def delete_cover(directory: Path, filename: str | None) -> None:
    """Best effort — a missing file must never block replacing or deleting the
    row that points at it."""
    if not filename:
        return
    try:
        path_for(directory, filename).unlink(missing_ok=True)
    except OSError:
        pass
