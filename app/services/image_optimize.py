"""Server-side downscale + re-encode for diary photo uploads.

Ported from shakyrtu's `app/services/image_optimize.py` — same rules, same
guarantees, trimmed to what this site needs. A phone photo is 3-4 MP and gets
displayed in a column a few hundred pixels wide; storing the original would
fill the droplet's volume for no visible gain.

Design constraints kept from the original:

- **Pure function on bytes.** No I/O, no DB — trivially unit-testable.
- **Never fails an upload.** Any exception (including Pillow not being
  installed) falls back to storing the ORIGINAL bytes unchanged.
- **Lazy Pillow import**, so importing this module can never raise
  ModuleNotFoundError on a container built before the dependency existed.

Returns ``(body, content_type, ext)`` so the caller can name the stored file
consistently even when the format changes (PNG-without-alpha becomes WebP).
"""

from __future__ import annotations

import io
import logging

log = logging.getLogger("image_optimize")

MAX_EDGE = 1600  # longest-edge cap in pixels
PASSTHROUGH_MAX_BYTES = 300 * 1024  # small AND light → leave untouched
JPEG_QUALITY = 85
WEBP_QUALITY = 85

ALLOWED_CONTENT_TYPES = {
    "image/jpeg",
    "image/jpg",
    "image/png",
    "image/webp",
    "image/heic",
    "image/heif",
}

_EXT_BY_TYPE = {
    "image/jpeg": "jpg",
    "image/jpg": "jpg",
    "image/png": "png",
    "image/webp": "webp",
}


def optimize_image(data: bytes, content_type: str) -> tuple[bytes, str, str]:
    """Downscale + re-encode an uploaded still image.

    - Apply EXIF orientation, then cap the longest edge at 1600 px (LANCZOS).
    - JPEG → JPEG q85 progressive; WebP → WebP q85.
    - PNG with alpha stays PNG; PNG without alpha becomes WebP.
    - Small (≤1600 px) AND already ≤300 KB → returned unchanged.
    - Animated or undecodable input → returned unchanged.

    Never raises.
    """
    ct = (content_type or "").lower()
    passthrough_ext = _EXT_BY_TYPE.get(ct, "jpg")
    try:
        from PIL import Image, ImageOps

        resample = getattr(Image, "Resampling", Image).LANCZOS

        with Image.open(io.BytesIO(data)) as im:
            fmt = (im.format or "").upper()

            if fmt not in ("JPEG", "PNG", "WEBP"):
                return data, content_type, passthrough_ext

            if getattr(im, "is_animated", False) or getattr(im, "n_frames", 1) > 1:
                return data, content_type, passthrough_ext

            if max(im.size) <= MAX_EDGE and len(data) <= PASSTHROUGH_MAX_BYTES:
                return data, content_type, passthrough_ext

            # Bake EXIF rotation into pixels — otherwise a phone portrait shot
            # renders sideways once the metadata is dropped.
            im = ImageOps.exif_transpose(im)

            has_alpha = im.mode in ("RGBA", "LA", "PA") or (
                im.mode == "P" and "transparency" in im.info
            )

            if fmt == "JPEG":
                target_fmt, out_ct, out_ext = "JPEG", "image/jpeg", "jpg"
            elif fmt == "PNG" and has_alpha:
                target_fmt, out_ct, out_ext = "PNG", "image/png", "png"
            else:
                target_fmt, out_ct, out_ext = "WEBP", "image/webp", "webp"

            if target_fmt == "JPEG":
                im = im.convert("RGB")
            elif has_alpha:
                im = im.convert("RGBA")
            else:
                im = im.convert("RGB")

            if max(im.size) > MAX_EDGE:
                im.thumbnail((MAX_EDGE, MAX_EDGE), resample)

            out = io.BytesIO()
            if target_fmt == "JPEG":
                im.save(out, format="JPEG", quality=JPEG_QUALITY, progressive=True, optimize=True)
            elif target_fmt == "PNG":
                im.save(out, format="PNG", optimize=True)
            else:
                im.save(out, format="WEBP", quality=WEBP_QUALITY, method=6)
            candidate = out.getvalue()

        # Only keep the re-encode if it actually saved bytes.
        if candidate and len(candidate) < len(data):
            return candidate, out_ct, out_ext
        return data, content_type, passthrough_ext
    except Exception as exc:  # noqa: BLE001 — optimisation must never fail an upload
        log.warning("image optimize skipped (%s): %s", content_type, exc)
        return data, content_type, passthrough_ext


def dimensions(data: bytes) -> tuple[int | None, int | None]:
    """Best-effort (width, height). None when Pillow can't read it."""
    try:
        from PIL import Image

        with Image.open(io.BytesIO(data)) as im:
            return im.size
    except Exception:  # noqa: BLE001
        return None, None
