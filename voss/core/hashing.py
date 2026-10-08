"""Stable content hashes for configs, scenarios, bundles and results (doc 01 §8)."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any


def canonical_json(obj: Any) -> str:
    """JSON with sorted keys and no whitespace; floats via repr (exact round trip)."""
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), default=str)


def hash_obj(obj: Any) -> str:
    return hashlib.sha256(canonical_json(obj).encode()).hexdigest()


def hash_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def hash_dir(path: Path) -> str:
    """Hash of all files under ``path`` (relative names + contents), in sorted order."""
    h = hashlib.sha256()
    for p in sorted(path.rglob("*")):
        if p.is_file():
            h.update(p.relative_to(path).as_posix().encode())
            h.update(b"\0")
            h.update(p.read_bytes())
    return h.hexdigest()
