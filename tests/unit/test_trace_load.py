"""Trace-driven workload (docs/REVISION_PLAN.md V9.1): profile mapping and per-minute arrivals."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
from voss.core.rng import RngFactory
from voss.world.trace_load import nearest_profile, trace_arrivals
from voss.world.workload import Catalog, FunctionSpec, LoadRegime, TenantSpec


def test_nearest_profile_is_log_scale() -> None:
    names = ["fast", "mid", "slow"]
    work = np.array([0.01, 0.3, 10.0])
    assert nearest_profile(np.array([0.004, 0.05, 2.0, 100.0]), names, work) == ["fast", "fast", "slow", "slow"]
    assert nearest_profile(np.array([0.06]), names, work) == ["mid"]  # log distance, not linear


class _Metros:
    def __len__(self) -> int:
        return 2

    def weights(self) -> np.ndarray:
        return np.array([0.5, 0.5])


def test_arrivals_follow_minute_counts(tmp_path: Path) -> None:
    d = tmp_path / "tr"
    d.mkdir()
    pd.DataFrame({"fn": [0, 0, 0], "minute": [10, 11, 13], "count": [600, 0, 1200]}).to_parquet(
        d / "arrivals_dev.parquet"
    )
    pd.DataFrame({"fn": [0]}).to_parquet(d / "functions_dev.parquet")
    f = FunctionSpec(
        name="tr0000",
        tenant="o",
        runtime="python3",
        rootfs_mb=1,
        bundle_mb=1,
        snapshot_mb=1,
        mem_mb=128,
        init_s=0.1,
        work_ref_s=0.1,
        in_kb=1,
        in_sigma=0,
        size_exp=0,
        out_kb=1,
        idempotent=True,
        slo_class="sync",
        slo_k=5,
    )
    cat = Catalog((f,), (TenantSpec(id="o", sensitivity="low", kbs_city="x", assurance_floor=0),))
    reg = LoadRegime(regime="t", rate=1, zipf_s=0, trace="tr", trace_root=str(tmp_path), start_min=10, rate_mult=2)
    a = trace_arrivals(reg, cat, _Metros(), 240.0, RngFactory(3))  # type: ignore[arg-type]
    first, third = a[a.t < 60], a[(a.t >= 180) & (a.t < 240)]
    assert abs(len(first) - 1200) < 150 and abs(len(third) - 2400) < 200  # Poisson(2 x count) in that minute
    assert a[(a.t >= 60) & (a.t < 120)].empty and a.t.is_monotonic_increasing
