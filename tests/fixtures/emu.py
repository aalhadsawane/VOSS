"""Fixtures for the V13 emulation tests (not used by reported runs).

The shipped scenario needs the traced inputs of `configs/base.yaml` (the fleet survey, the seti09 sessions and the
Ookla links), which are gitignored release assets. These helpers swap in the tiny fixtures under `tests/` — the same
ones `configs/smoke.yaml` uses — and can write a short session trace when a test needs session ends inside a few
seconds.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd

from tests.fixtures.fleet import FLEET

#: Overrides that make the shipped emulation scenario runnable without the gitignored trace data.
FIXTURE: list[str] = [
    "scenario.machines=" + str(FLEET).replace("'", ""),
    "scenario.churn={trace: test, trace_root: tests/fixtures/traces, split: dev}",
    "scenario.network={link: {trace: ''}}",
]


def sessions_trace(root: Path, intervals: list[tuple[float, float]], hosts: int = 12) -> Path:
    """Write ``sessions_dev.parquet`` for ``hosts`` hosts replaying ``intervals``; returns the trace root."""
    rows: list[dict[str, Any]] = [
        {"host": h, "start_s": start, "end_s": end} for h in range(hosts) for start, end in intervals
    ]
    d = root / "test"
    d.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows).to_parquet(d / "sessions_dev.parquet", index=False)
    return root
