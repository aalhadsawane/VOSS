"""Raw event recorder (doc 05 §8: ``recorder.log(EventType, **fields)``; doc 06 §2).

Rows are buffered in memory per table and written as Parquet. ``result_hash`` is a deterministic digest of the
logged content, independent of file formats and library versions.

Memory (docs/REVISION_PLAN.md V9.5): a Python dict per row costs about ten times its columnar size, and a day-long run
at 700 workers exhausted a 16 GB runner. Every ``batch_rows`` rows a table's buffer is compacted into a DataFrame
chunk; ``frame`` concatenates the chunks and the open buffer, with columns in order of first appearance as before.
"""

from __future__ import annotations

from collections import defaultdict
from pathlib import Path
from typing import Any

import pandas as pd

from voss.core.hashing import hash_columns
from voss.metrics.schema import Table


class Recorder:
    """Append-only tables: an open row buffer plus compacted columnar chunks per table."""

    def __init__(self, batch_rows: int = 100_000) -> None:
        self.batch_rows = batch_rows
        self._rows: dict[str, list[dict[str, Any]]] = defaultdict(list)
        self._chunks: dict[str, list[pd.DataFrame]] = defaultdict(list)
        self._n: dict[str, int] = defaultdict(int)

    def log(self, table: Table | str, **fields: Any) -> None:
        name = str(table)
        rows = self._rows[name]
        rows.append(fields)
        self._n[name] += 1
        if len(rows) >= self.batch_rows:
            self._chunks[name].append(pd.DataFrame(rows))
            self._rows[name] = []

    def tables(self) -> list[str]:
        return sorted(self._n)

    def frame(self, table: Table | str) -> pd.DataFrame:
        name = str(table)
        parts = [*self._chunks.get(name, []), *([pd.DataFrame(self._rows[name])] if self._rows.get(name) else [])]
        if not parts:
            return pd.DataFrame()
        if len(parts) == 1:
            return parts[0]
        return pd.concat(parts, ignore_index=True, sort=False)

    def count(self, table: Table | str) -> int:
        return self._n.get(str(table), 0)

    def write(self, out_dir: Path) -> None:
        out_dir.mkdir(parents=True, exist_ok=True)
        for name in self.tables():
            self.frame(name).to_parquet(out_dir / f"{name}.parquet", index=False)

    def result_hash(self) -> str:
        """SHA-256 over every table's columns (names, then values in row order).

        Wall-clock measurements (columns ending in ``_wall_s``) are metadata, not simulation results: they are
        excluded so ``modeled`` and ``replay`` runs hash identically across machines (doc 01 §7-8).
        """
        tables = {}
        for name in self.tables():
            df = self.frame(name)
            tables[name] = {c: df[c].to_numpy() for c in df.columns if not str(c).endswith("_wall_s")}
        return hash_columns(tables)
