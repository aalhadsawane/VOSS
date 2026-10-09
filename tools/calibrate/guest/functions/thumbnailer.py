"""SeBS 210.thumbnailer: decode a JPEG, thumbnail it to 200x200, re-encode (Pillow)."""

from __future__ import annotations

import io
import math
import os

from PIL import Image


def make_input(size_kb: int) -> bytes:
    side = max(64, int(math.sqrt(size_kb * 1024 * 4 / 3)))
    img = Image.frombytes("RGB", (side, side), os.urandom(side * side * 3))
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=90)
    return buf.getvalue()


def handler(data: bytes) -> int:
    img = Image.open(io.BytesIO(data))
    img.thumbnail((200, 200))
    out = io.BytesIO()
    img.save(out, format="JPEG")
    return out.tell()
