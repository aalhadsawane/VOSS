"""Stable content hashes for configs, scenarios, bundles and results (doc 01 §8)."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

import numpy as np


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


def hash_columns(tables: Mapping[str, Mapping[str, Sequence[Any] | np.ndarray]]) -> str:
    """SHA-256 over named tables of named columns, in sorted order (format- and library-independent)."""
    h = hashlib.sha256()
    for name in sorted(tables):
        h.update(f"<{name}>".encode())
        cols = tables[name]
        for col in sorted(cols):
            h.update(f"[{col}]".encode())
            h.update(column_bytes(cols[col]))
    return h.hexdigest()


def column_bytes(values: Sequence[Any] | np.ndarray) -> bytes:
    arr = np.asarray(values)
    if arr.dtype.kind in "iuf":
        return np.ascontiguousarray(arr.astype(np.float64)).tobytes()
    return "\x1e".join(repr(v) for v in arr.tolist()).encode()
