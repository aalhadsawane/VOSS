"""SeBS 311.compression: zip a directory of files."""

from __future__ import annotations

import os
import shutil


def make_input(size_kb: int) -> str:
    root = f"/tmp/voss-comp-{size_kb}"
    os.makedirs(root, exist_ok=True)
    chunk = os.urandom(512) * 2  # half-compressible
    for i in range(max(1, size_kb // 100)):
        with open(os.path.join(root, f"f{i}.bin"), "wb") as f:
            f.write(chunk * 100)
    return root


def handler(root: str) -> str:
    return shutil.make_archive("/tmp/voss-archive", "zip", root)
