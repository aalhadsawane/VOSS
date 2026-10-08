"""Raw event recorder (doc 05 §8: ``recorder.log(EventType, **fields)``; doc 06 §2).

Rows are buffered in memory per table and written as Parquet. ``result_hash`` is a deterministic digest of the
logged content, independent of file formats and library versions.
"""

from __future__ import annotations

from collections import defaultdict
from pathlib import Path
from typing import Any

import pandas as pd

from voss.core.hashing import hash_columns
from voss.metrics.schema import Table


class Recorder:
    """Append-only row buffers, one per table."""

    def __init__(self) -> None:
        self._rows: dict[str, list[dict[str, Any]]] = defaultdict(list)

    def log(self, table: Table | str, **fields: Any) -> None:
        self._rows[str(table)].append(fields)

    def tables(self) -> list[str]:
        return sorted(self._rows)

    def frame(self, table: Table | str) -> pd.DataFrame:
        return pd.DataFrame(self._rows.get(str(table), []))

    def count(self, table: Table | str) -> int:
        return len(self._rows.get(str(table), []))

    def write(self, out_dir: Path) -> None:
        out_dir.mkdir(parents=True, exist_ok=True)
        for name in self.tables():
            self.frame(name).to_parquet(out_dir / f"{name}.parquet", index=False)

    def result_hash(self) -> str:
        """SHA-256 over every table's columns (names, then values in row order)."""
        tables = {}
        for name in self.tables():
            df = self.frame(name)
            tables[name] = {c: df[c].to_numpy() for c in df.columns}
        return hash_columns(tables)
