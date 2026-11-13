"""Traced host availability (docs/REVISION_PLAN.md V9.2): workers replay hosts' weeks."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
from voss.world.sessions import WEEK_S, SessionRegime, _traced_rows


def test_each_worker_replays_one_hosts_week(tmp_path: Path) -> None:
    (tmp_path / "s").mkdir()
    pd.DataFrame({"host": [1, 1, 2], "start_s": [0.0, 7200.0, 100.0], "end_s": [3600.0, 9000.0, WEEK_S]}).to_parquet(
        tmp_path / "s" / "sessions_dev.parquet"
    )
    reg = SessionRegime.model_validate(
        {
            "regime": "t",
            "tiers": {},
            "graceful_frac": 0.5,
            "drain_lead": {"dist": "const", "value": 60.0},
            "trace": "s",
            "trace_root": str(tmp_path),
        }
    )
    rows = _traced_rows(reg, 2, -WEEK_S, WEEK_S, np.random.default_rng(1))  # noqa: TID251  (test-local generator)
    by_w = {w: sorted((s, e) for ww, s, e in rows if ww == w) for w in (0, 1)}
    lens = sorted(len(v) for v in by_w.values())
    assert lens == [2, 4]  # host 2: one interval per week; host 1: two per week; two weeks cover the window
    two = next(v for v in by_w.values() if len(v) == 4)
    assert two[0] == (-WEEK_S, -WEEK_S + 3600.0) and two[2] == (0.0, 3600.0)
