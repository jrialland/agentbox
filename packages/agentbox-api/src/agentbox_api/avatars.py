"""Agent avatar generation (RoboHash set1 default) and upload normalization."""

from __future__ import annotations

import io
from functools import lru_cache

from PIL import Image, UnidentifiedImageError
from robohash import Robohash

AVATAR_SIZE = 300
MAX_UPLOAD_BYTES = 2 * 1024 * 1024
ALLOWED_UPLOAD_TYPES = {"image/png", "image/jpeg", "image/webp"}


@lru_cache(maxsize=512)
def _render_default(seed: str, size: int) -> bytes:
    rh = Robohash(seed)
    rh.assemble(roboset="set1", sizex=size, sizey=size, format="png")
    buf = io.BytesIO()
    rh.img.save(buf, format="PNG")
    return buf.getvalue()


def generate_default_avatar(seed: str, size: int = AVATAR_SIZE) -> bytes:
    return _render_default(seed, size)


def normalize_upload(data: bytes) -> bytes:
    try:
        with Image.open(io.BytesIO(data)) as img:
            img = img.convert("RGB")
            w, h = img.size
            side = min(w, h)
            left = (w - side) // 2
            top = (h - side) // 2
            img = img.crop((left, top, left + side, top + side))
            img = img.resize((AVATAR_SIZE, AVATAR_SIZE), Image.Resampling.LANCZOS)
            out = io.BytesIO()
            img.save(out, format="PNG")
            return out.getvalue()
    except (UnidentifiedImageError, OSError) as exc:
        raise ValueError("invalid image") from exc
