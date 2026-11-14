"""Raw event recorder (doc 05 §8: ``recorder.log(EventType, **fields)``; doc 06 §2).

Rows are buffered in memory per table and written as Parquet. ``result_hash`` is a deterministic digest of the
logged content, independent of file formats and library versions.

Memory (docs/REVISION_PLAN.md V9.5): a Python dict per row costs about ten times its columnar size, and a day-long run
at 700 workers exhausted a 16 GB runner. Every ``batch_rows`` rows a table's buffer becomes a DataFrame chunk written
to a Parquet file in a temporary directory (``spill=True``, the default), so recorder memory no longer grows with the
run's length; ``frame`` reads the chunks back and concatenates them with the open buffer, columns in order of first
appearance as before. Frames and result hashes equal the unchunked ones (``tests/unit/test_recorder_chunks.py``).
End-of-run readers never need a whole long table at once: ``frame_where`` filters each chunk, and ``result_hash`` is
built one column at a time in slices (a 500-worker day peaked at 15.3 GB when both read whole tables).
"""

from __future__ import annotations

import hashlib
import tempfile
from collections import defaultdict
from collections.abc import Iterable, Iterator
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from voss.core.hashing import update_column
from voss.metrics.schema import Table


class Recorder:
    """Append-only tables: an open row buffer plus compacted columnar chunks per table."""

    def __init__(self, batch_rows: int = 100_000, spill: bool = True) -> None:
        self.batch_rows = batch_rows
        self._rows: dict[str, list[dict[str, Any]]] = defaultdict(list)
        self._chunks: dict[str, list[pd.DataFrame | Path]] = defaultdict(list)
        self._n: dict[str, int] = defaultdict(int)
        self._dir = tempfile.TemporaryDirectory(prefix="voss-rec-") if spill else None

    def log(self, table: Table | str, **fields: Any) -> None:
        name = str(table)
        rows = self._rows[name]
        rows.append(fields)
        self._n[name] += 1
        if len(rows) >= self.batch_rows:
            chunk = pd.DataFrame(rows)
            self._rows[name] = []
            if self._dir is None:
                self._chunks[name].append(chunk)
                return
            path = Path(self._dir.name) / f"{name}.{len(self._chunks[name]):06d}.pkl"
            chunk.to_pickle(path)  # exact round trip of dtypes and object columns (Parquet coerces mixed objects)
            self._chunks[name].append(path)

    def tables(self) -> list[str]:
        return sorted(self._n)

    def _parts(self, name: str) -> list[pd.DataFrame]:
        chunks = [pd.read_pickle(c) if isinstance(c, Path) else c for c in self._chunks.get(name, [])]
        return [*chunks, *([pd.DataFrame(self._rows[name])] if self._rows.get(name) else [])]

    def _part_iter(self, name: str) -> Iterator[pd.DataFrame]:
        """Chunks one at a time (read from disk on demand), then the open buffer."""
        for c in self._chunks.get(name, []):
            yield pd.read_pickle(c) if isinstance(c, Path) else c
        if self._rows.get(name):
            yield pd.DataFrame(self._rows[name])

    def frame(self, table: Table | str) -> pd.DataFrame:
        parts = self._parts(str(table))
        if not parts:
            return pd.DataFrame()
        if len(parts) == 1:
            return parts[0]
        return pd.concat(parts, ignore_index=True, sort=False)

    def frame_where(self, table: Table | str, col: str, values: Iterable[Any]) -> pd.DataFrame:
        """The rows of ``frame(table)`` whose ``col`` is in ``values``, with all of the table's columns, filtering each
        chunk before concatenating (end-of-run checks read a few kinds of a long events table; plan V9.5)."""
        keep, cols, vals = [], {}, list(values)
        for p in self._part_iter(str(table)):
            cols.update(dict.fromkeys(p.columns))
            keep.append(p[p[col].isin(vals)] if col in p.columns else p.iloc[:0])
        if not keep:
            return pd.DataFrame()
        out = keep[0] if len(keep) == 1 else pd.concat(keep, ignore_index=True, sort=False)
        return out.reindex(columns=list(cols))

    def _column(self, name: str, col: str) -> np.ndarray:
        """``frame(name)[col].to_numpy()``, concatenating only that column (missing in a chunk: filled as ``frame``
        fills it)."""
        parts = [p[[col]] if col in p.columns else p[[]] for p in self._part_iter(name)]
        s = parts[0][col] if len(parts) == 1 else pd.concat(parts, ignore_index=True, sort=False)[col]
        out: np.ndarray = s.to_numpy()
        return out

    def _columns(self, name: str) -> list[str]:
        cols: dict[str, None] = {}
        for c in self._chunks.get(name, []):
            cols.update(dict.fromkeys(pd.read_pickle(c).columns if isinstance(c, Path) else c.columns))
        for r in self._rows.get(name, []):
            cols.update(dict.fromkeys(r))
        return list(cols)

    def count(self, table: Table | str) -> int:
        return self._n.get(str(table), 0)

    def write(self, out_dir: Path) -> None:
        out_dir.mkdir(parents=True, exist_ok=True)
        for name in self.tables():
            self.frame(name).to_parquet(out_dir / f"{name}.parquet", index=False)

    def result_hash(self) -> str:
        """SHA-256 over every table's columns (names, then values in row order); equal to ``hash_columns`` over the
        full frames, built one column at a time so a long run's tables are never all in memory (plan V9.5).

        Wall-clock measurements (columns ending in ``_wall_s``) are metadata, not simulation results: they are
        excluded so ``modeled`` and ``replay`` runs hash identically across machines (doc 01 §7-8).
        """
        h = hashlib.sha256()
        for name in self.tables():
            h.update(f"<{name}>".encode())
            for col in sorted(c for c in self._columns(name) if not str(c).endswith("_wall_s")):
                h.update(f"[{col}]".encode())
                update_column(h, self._column(name, col))
        return h.hexdigest()
