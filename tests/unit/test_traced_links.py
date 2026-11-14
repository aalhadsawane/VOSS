"""Measured home links (docs/REVISION_PLAN.md V9.3): workers draw their metro's measured triples."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
from voss.world.workers import LinkParams, _links


def test_workers_draw_their_metros_triples(tmp_path: Path) -> None:
    (tmp_path / "net").mkdir()
    pd.DataFrame(
        {
            "city": ["A", "A", "B"],
            "down_kbps": [1000, 2000, 50_000],
            "up_kbps": [100, 200, 5_000],
            "lat_ms": [20, 40, 8],
        }
    ).to_parquet(tmp_path / "net" / "links.parquet")
    lp = LinkParams(trace="net", trace_root=str(tmp_path))
    out = _links(np.random.default_rng(0), lp, 3, ["A", "B", "A"])  # noqa: TID251  (test-local generator)
    assert out["down_bps"][1] == 50e6 and out["last_mile_s"][1] == 0.004
    assert set(out["down_bps"][[0, 2]]) <= {1e6, 2e6}
    assert np.all(out["up_bps"] == out["down_bps"] / 10)  # the triple stays together


def test_the_trace_key_passes_the_network_config() -> None:
    """``scenario.network.link.trace`` reaches LinkParams (it used to fail as a non-number)."""
    from voss.world.network import NetworkParams

    net = NetworkParams.model_validate({"link": {"trace": "ookla-fixed-2024q1", "down_mbps_median": 50}})
    lp = LinkParams.model_validate(net.link)
    assert lp.trace == "ookla-fixed-2024q1" and lp.down_mbps_median == 50.0
