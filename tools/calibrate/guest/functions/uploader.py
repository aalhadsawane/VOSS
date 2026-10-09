"""SeBS 120.uploader without the network: persist the payload to disk (fsync) and read it back."""

from __future__ import annotations

import os


def make_input(size_kb: int) -> bytes:
    return os.urandom(size_kb * 1024)


def handler(data: bytes) -> int:
    path = "/tmp/voss-upload.bin"
    with open(path, "wb") as f:
        f.write(data)
        f.flush()
        os.fsync(f.fileno())
    with open(path, "rb") as f:
        return len(f.read())
