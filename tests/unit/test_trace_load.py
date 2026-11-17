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


def _fn(name: str, work: float, in_kb: float) -> FunctionSpec:
    return FunctionSpec(
        name=name, tenant="o", runtime="python3", rootfs_mb=1, bundle_mb=1, snapshot_mb=1, mem_mb=128, init_s=0.1,
        work_ref_s=work, in_kb=in_kb, in_sigma=0.5, size_exp=1.0, out_kb=1, idempotent=True, slo_class="sync",
        slo_k=5,
    )  # fmt: skip


def _trace(tmp_path: Path, durations_ms: list[float | None]) -> LoadRegime:
    d = tmp_path / "tr"
    d.mkdir()
    n = len(durations_ms)
    funcs = {"fn": list(range(n)), "owner": ["o"] * n, "sync": [True] * n, "dur_p50_ms": durations_ms}
    pd.DataFrame(funcs).to_parquet(d / "functions_dev.parquet")
    return LoadRegime(regime="t", rate=1, zipf_s=0, trace="tr", trace_root=str(tmp_path))


def test_trace_functions_map_to_the_nearest_measured_input_size(tmp_path: Path) -> None:
    """Plan V9.1: across every measured (function, size); invocations use that size and its measured run time."""
    from voss.world.trace_load import load_trace_functions, trace_catalog

    reg = _trace(tmp_path, [2.0, 50.0, 900.0, 40_000.0, None])
    tenant = TenantSpec(id="o", sensitivity="low", kbs_city="x", assurance_floor=0)
    base = Catalog((_fn("a", 0.01, 10), _fn("b", 0.5, 100), _fn("js", 9.0, 1)), (tenant,))
    sizes = {"a": {1.0: 0.001, 10.0: 0.01, 100.0: 0.1}, "b": {100.0: 0.5, 1000.0: 5.0}}  # "js" has no measurement
    tf = load_trace_functions(reg, base, sizes)
    assert tf.per_size and tf.dropped == 1
    assert list(zip(tf.table.base, tf.table.size_kb, strict=True)) == [
        ("a", 1.0),
        ("a", 100.0),
        ("b", 100.0),
        ("b", 1000.0),
    ]
    assert list(tf.table.outside) == [False, False, False, True] and tf.outside == 0.25  # 40 s > the 5 s maximum
    cat = trace_catalog(reg, base, sizes)
    f = cat.functions[1]
    assert (f.name, f.in_kb, f.in_sigma, f.work_ref_s) == ("tr0001", 100.0, 0.0, 0.1)
    ref = load_trace_functions(reg, base)  # a bundle without exec_by_size: one profile per function, as before
    assert not ref.per_size and list(ref.table.base) == ["a", "a", "b", "js"]
    assert trace_catalog(reg, base).functions[1].in_kb == 10  # the reference input is kept


def test_function_sizes_read_exec_by_size(tmp_path: Path) -> None:
    import yaml
    from voss.world.calibration import function_sizes

    rows = {1: {"median_s": 0.002, "n": 30}, 10: {"median_s": 0.02, "n": 30}}
    fns = {"a": {"exec_by_size": rows, "work_ref_s": 0.01}, "b": {"work_ref_s": 1.0}}
    (tmp_path / "functions.yaml").write_text(yaml.safe_dump({"functions": fns}))
    assert function_sizes(str(tmp_path)) == {"a": {1.0: 0.002, 10.0: 0.02}}
    assert function_sizes(None) == {}  # the placeholder bundle has no per-size run times
