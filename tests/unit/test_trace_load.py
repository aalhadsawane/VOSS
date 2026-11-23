"""Trace-driven workload (docs/REVISION_PLAN.md V9.1): profile mapping and per-minute arrivals."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import pytest
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
        size_exp=0,
        out_kb=1,
        slo_class="sync",
    )
    cat = Catalog((f,), (TenantSpec(id="o", kbs_city="x"),))
    reg = LoadRegime(regime="t", rate=1, zipf_s=0, trace="tr", trace_root=str(tmp_path), start_min=10, rate_mult=2)
    a = trace_arrivals(reg, cat, _Metros(), 240.0, RngFactory(3))  # type: ignore[arg-type]
    first, third = a[a.t < 60], a[(a.t >= 180) & (a.t < 240)]
    assert abs(len(first) - 1200) < 150 and abs(len(third) - 2400) < 200  # Poisson(2 x count) in that minute
    assert a[(a.t >= 60) & (a.t < 120)].empty and a.t.is_monotonic_increasing


def _fn(name: str, work: float, in_kb: float) -> FunctionSpec:
    return FunctionSpec(
        name=name, tenant="o", runtime="python3", rootfs_mb=1, bundle_mb=1, snapshot_mb=1, mem_mb=128, init_s=0.1,
        work_ref_s=work, in_kb=in_kb, size_exp=1.0, out_kb=1, slo_class="sync",
    )  # fmt: skip


def _trace(tmp_path: Path, durations_ms: list[float | None]) -> LoadRegime:
    d = tmp_path / "tr"
    d.mkdir()
    n = len(durations_ms)
    funcs = {"fn": list(range(n)), "owner": ["o"] * n, "sync": [True] * n, "dur_p50_ms": durations_ms}
    pd.DataFrame(funcs).to_parquet(d / "functions_dev.parquet")
    return LoadRegime(regime="t", rate=1, zipf_s=0, trace="tr", trace_root=str(tmp_path))


def test_trace_functions_map_to_the_nearest_measured_input_size(tmp_path: Path) -> None:
    """Plan V9.1: across every measured (function, size); invocations carry the bytes a client sends at that size
    and run for its measured time (D-105, D-106)."""
    from voss.world.trace_load import load_trace_functions, trace_catalog

    reg = _trace(tmp_path, [2.0, 50.0, 900.0, 40_000.0, None])
    tenant = TenantSpec(id="o", kbs_city="x")
    base = Catalog((_fn("uploader", 0.01, 10), _fn("graph-bfs", 0.5, 100), _fn("js", 9.0, 1)), (tenant,))
    sizes = {"uploader": {1.0: 0.001, 10.0: 0.01, 100.0: 0.1}, "graph-bfs": {100.0: 0.5, 1000.0: 5.0}}  # js: none
    tf = load_trace_functions(reg, base, sizes)
    assert tf.per_size and tf.dropped == 1
    assert list(zip(tf.table.base, tf.table.size_kb, strict=True)) == [
        ("uploader", 1.0),
        ("uploader", 100.0),
        ("graph-bfs", 100.0),
        ("graph-bfs", 1000.0),
    ]
    assert list(tf.table.outside) == [False, False, False, True] and tf.outside == 0.25  # 40 s > the 5 s maximum
    cat = trace_catalog(reg, base, sizes)
    assert cat.transfer_deadline
    up, graph = cat.functions[1], cat.functions[2]
    assert (up.name, up.in_kb, up.work_ref_s) == ("tr0001", 100.0, 0.1)  # data: size kB
    assert (graph.in_kb, graph.work_ref_s) == (1.0, 0.5)  # parameters only: the catalogue's smallest input
    ref = load_trace_functions(reg, base)  # a bundle without exec_by_size: one profile per function, as before
    assert not ref.per_size and list(ref.table.base) == ["uploader", "uploader", "graph-bfs", "js"]
    old = trace_catalog(reg, base)
    assert old.functions[1].in_kb == 10 and not old.transfer_deadline  # the reference input and deadline are kept


def test_request_bytes_follow_what_the_client_sends() -> None:
    """D-106: kB of data, a parameter-only request, or the encoded image the guest's input stands for."""
    from voss.core.paths import load_data_yaml
    from voss.world.trace_load import request_kb

    rules = load_data_yaml("request_bytes.yaml")
    for fn in ("compression", "dna-visualisation", "thumbnailer", "uploader", "video-processing"):
        assert request_kb(fn, 16000.0, rules, 1.0) == 16000.0
    for fn in ("dynamic-html", "graph-bfs", "graph-mst", "graph-pagerank"):
        assert request_kb(fn, 100000.0, rules, 1.0) == 1.0
    assert request_kb("image-recognition", 100.0, rules, 1.0) * 1024 == 45606  # 224x224 JPEG
    assert request_kb("image-recognition", 400.0, rules, 1.0) * 1024 == 180505  # 448x448 JPEG
    with pytest.raises(ValueError, match="no request size rule"):
        request_kb("js", 1.0, rules, 1.0)
    root = Path(__file__).parents[2] / "tools" / "calibrate" / "guest" / "functions"
    guests = {f.stem.replace("_", "-") for f in root.glob("[a-z]*.py")}
    covered = set(rules["data"]) | set(rules["parameters"]) | set(rules["images"])
    assert covered == guests  # every guest function has exactly one rule


def test_sync_deadline_adds_the_input_transfer_only_when_asked() -> None:
    """D-106: deadline_multiple x (run time + input bytes at the median downlink + overhead)."""
    from voss.world.workload import _frame

    f = _fn("uploader", 0.1, 16000)
    reg = LoadRegime(regime="t", rate=1, zipf_s=0, sync_overhead_s=0.05)
    size, one = np.array([16000 * 1024.0]), np.zeros(1)
    old = _frame(f, 0, 0, one, one.astype(np.int64), size, reg).deadline_s.iloc[0]
    new = _frame(f, 0, 0, one, one.astype(np.int64), size, reg, 5.0, 190e6).deadline_s.iloc[0]
    assert old == pytest.approx(5 * (0.1 + 0.05))
    assert new == pytest.approx(5 * (0.1 + 16000 * 1024 * 8 / 190e6 + 0.05))


def test_median_downlink_comes_from_the_links_trace(tmp_path: Path) -> None:
    from voss.world.workers import LinkParams, median_down_bps

    d = tmp_path / "ln"
    d.mkdir()
    pd.DataFrame({"city": ["a", "a", "b"], "down_kbps": [100.0, 300.0, 200_000.0]}).to_parquet(d / "links.parquet")
    assert median_down_bps(LinkParams(trace="ln", trace_root=str(tmp_path))) == 300.0e3
    assert median_down_bps(LinkParams()) == LinkParams().down_mbps_median * 1e6  # no trace: the seed's median


def test_function_sizes_read_exec_by_size(tmp_path: Path) -> None:
    import yaml
    from voss.world.calibration import function_sizes

    rows = {1: {"median_s": 0.002, "n": 30}, 10: {"median_s": 0.02, "n": 30}}
    fns = {"a": {"exec_by_size": rows, "work_ref_s": 0.01}, "b": {"work_ref_s": 1.0}}
    (tmp_path / "functions.yaml").write_text(yaml.safe_dump({"functions": fns}))
    assert function_sizes(str(tmp_path)) == {"a": {1.0: 0.002, 10.0: 0.02}}
    assert function_sizes(None) == {}  # the placeholder bundle has no per-size run times
