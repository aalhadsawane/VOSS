"""Per-view arrays for the vectorized cost model (doc 01 §9: vectorize cost matrices).

Static worker attributes and per-function cache levels are extracted once per view snapshot and reused by every
invocation placed against it.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from voss.core.types import ClusterView
from voss.policy.cost.inputs import CostContext

LEVEL_CODE = {"L0": 0, "L1": 1, "L2": 2, "L3": 3}


@dataclass(frozen=True)
class ViewArrays:
    lat: np.ndarray
    lon: np.ndarray
    down: np.ndarray
    up: np.ndarray
    ssd_read: np.ndarray
    hdd_read: np.ndarray
    boot: np.ndarray
    restore: np.ndarray
    dispatch: np.ndarray
    trust_fixed: np.ndarray
    verify: np.ndarray
    touched: np.ndarray
    has_snap: np.ndarray
    cpu_factor: np.ndarray
    reg_rtt: np.ndarray


def view_arrays(view: ClusterView, ctx: CostContext) -> ViewArrays:
    st = view.static if view.static else (None,) * len(view)
    default = next(iter(ctx.startup.values()))
    sm = [ctx.startup.get(s.substrate, default) if s else default for s in st]

    def col(get: object, fallback: float) -> np.ndarray:
        return np.array([getattr(s, str(get)) if s else fallback for s in st], dtype=float)

    lat, lon = col("lat", 0.0), col("lon", 0.0)
    return ViewArrays(
        lat=lat,
        lon=lon,
        down=col("down_bps", 1e8),
        up=col("up_bps", 1e7),
        ssd_read=np.maximum(col("ssd_read_MBps", 500.0), 1.0),
        hdd_read=np.maximum(col("hdd_read_MBps", 100.0), 1.0),
        boot=np.array([m.boot_s for m in sm]),
        restore=np.array([m.restore_s for m in sm]),
        dispatch=np.array([m.dispatch_s for m in sm]),
        trust_fixed=np.array([m.trust_fixed_s for m in sm]),
        verify=np.array([m.verify_s_per_mb for m in sm]),
        touched=np.array([m.touched_frac for m in sm]),
        has_snap=np.array([m.has_snapshot_level for m in sm]),
        cpu_factor=np.array([m.cpu_factor for m in sm]),
        reg_rtt=ctx.geo.rtt(lat, lon, *ctx.registry),
    )


def levels(view: ClusterView, fn: str) -> tuple[np.ndarray, np.ndarray]:
    """``(level code, on_hdd)`` per worker for ``fn``."""
    code = np.zeros(len(view), dtype=np.int64)
    hdd = np.zeros(len(view), dtype=bool)
    for j, c in enumerate(view.cache):
        e = c.get(fn)  # type: ignore[call-overload]
        if e is not None:
            code[j] = LEVEL_CODE.get(e.level, 0)
            hdd[j] = e.tier == "hdd"
    return code, hdd


class ArrayCache:
    """Remembers arrays for the most recent base view (keyed by its cache tuple identity)."""

    def __init__(self) -> None:
        self.key: int | None = None
        self.arrays: ViewArrays | None = None
        self.lv: dict[str, tuple[np.ndarray, np.ndarray]] = {}

    def get(self, view: ClusterView, ctx: CostContext) -> ViewArrays:
        if self.key != id(view.cache) or self.arrays is None:
            self.key, self.arrays, self.lv = id(view.cache), view_arrays(view, ctx), {}
        return self.arrays

    def level(self, view: ClusterView, fn: str) -> tuple[np.ndarray, np.ndarray]:
        if fn not in self.lv:
            self.lv[fn] = levels(view, fn)
        return self.lv[fn]
