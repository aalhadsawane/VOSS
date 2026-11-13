"""Recorder compaction (docs/REVISION_PLAN.md V9.5): chunked tables equal the unchunked ones, hash included."""

from __future__ import annotations

import pandas as pd
from voss.metrics.recorder import Recorder


def _fill(rec: Recorder) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for i in range(1000):
        r: dict[str, object] = {"t": i * 0.5, "kind": "a" if i % 3 else "b", "worker": i % 7}
        if i % 5 == 0:
            r["extra"] = i  # a field only some rows carry
        rec.log("events", **r)
        rows.append(r)
    return rows


def test_chunked_frames_and_hashes_equal_the_unchunked_ones() -> None:
    big = Recorder(batch_rows=10**9)
    _fill(big)
    for small in (Recorder(batch_rows=64, spill=False), Recorder(batch_rows=64)):  # in memory, spilled to disk
        rows = _fill(small)
        pd.testing.assert_frame_equal(small.frame("events"), pd.DataFrame(rows))
        assert small.count("events") == 1000 and small.tables() == ["events"]
        assert small.result_hash() == big.result_hash()
