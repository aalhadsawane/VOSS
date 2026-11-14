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


def test_streamed_hash_and_filtered_frames_equal_the_full_frames() -> None:
    """result_hash (one column at a time) equals hash_columns over the full frames, and frame_where equals filtering
    the full frame, with columns that appear only in some chunks and mixed types (plan V9.5)."""
    from voss.core.hashing import hash_columns
    from voss.metrics.recorder import Recorder

    rec = Recorder(batch_rows=7)
    for i in range(60):
        row: dict[str, object] = {"t": i * 0.5, "kind": ("a", "b", "c")[i % 3], "worker": i % 4}
        if i % 5 == 0:
            row["cert"] = f"c{i}"
        if 20 <= i < 30:
            row["value"] = i if i % 2 else f"s{i}"  # int and str in one column
        rec.log("events", **row)
        if i % 9 == 0:
            rec.log("plans", fn="f", n=i)
    full = {n: rec.frame(n) for n in rec.tables()}
    want = hash_columns({n: {c: df[c].to_numpy() for c in df.columns} for n, df in full.items()})
    assert rec.result_hash() == want
    ev = full["events"]
    got = rec.frame_where("events", "kind", ["b"])
    exp = ev[ev.kind == "b"].reset_index(drop=True)
    assert list(got.columns) == list(ev.columns)
    pd.testing.assert_frame_equal(got.reset_index(drop=True), exp, check_dtype=False)
