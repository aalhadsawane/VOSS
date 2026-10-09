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
        self.key: object | None = None  # the keyed view's cache tuple (held, so its identity cannot be reused)
        self.arrays: ViewArrays | None = None
        self.lv: dict[str, tuple[np.ndarray, np.ndarray]] = {}
        self.holders: dict[str, np.ndarray] = {}
        self.rtts: dict[tuple[float, float], np.ndarray] = {}

    def get(self, view: ClusterView, ctx: CostContext) -> ViewArrays:
        if self.key is not view.cache or self.arrays is None:
            self.key, self.arrays, self.lv = view.cache, view_arrays(view, ctx), {}
            self.holders, self.rtts = {}, {}
        return self.arrays

    def holder(self, view: ClusterView, tenant: str) -> np.ndarray:
        """Workers already holding ``tenant``'s key (trust-warm), per view."""
        if tenant not in self.holders:
            self.holders[tenant] = np.fromiter((tenant in ts for ts in view.trust), dtype=bool, count=len(view))
        return self.holders[tenant]

    def startup(self, view: ClusterView, ctx: CostContext, fn: str) -> tuple[np.ndarray, np.ndarray]:
        key = f"startup:{fn}"
        if key not in self.lv:
            code, hdd = self.level(view, fn)
            assert self.arrays is not None
            self.lv[key] = startup_arrays(self.arrays, code, hdd, ctx, fn, view.speed)
        return self.lv[key]

    def rtt(self, ctx: CostContext, lat: float, lon: float) -> np.ndarray:
        key = (lat, lon)
        if key not in self.rtts:
            assert self.arrays is not None
            self.rtts[key] = ctx.geo.rtt(self.arrays.lat, self.arrays.lon, lat, lon)
        return self.rtts[key]

    def level(self, view: ClusterView, fn: str) -> tuple[np.ndarray, np.ndarray]:
        if fn not in self.lv:
            self.lv[fn] = levels(view, fn)
        return self.lv[fn]


def startup_arrays(
    a: ViewArrays, code: np.ndarray, hdd: np.ndarray, ctx: CostContext, fn: str, speed: np.ndarray
) -> tuple[np.ndarray, np.ndarray]:
    """``(fetch_s, rest_s)`` per worker from its cache level (doc 02 §5 ladder)."""
    f = ctx.fns[fn]
    read = np.where(hdd, a.hdd_read, a.ssd_read)
    boot = f.rootfs_mb / read + a.boot + f.init_s / speed + a.dispatch
    restore = f.snapshot_mb * a.touched / read + a.restore + a.dispatch
    rest = np.where(code >= 3, a.dispatch, np.where((code == 2) & a.has_snap, restore, boot))
    mb = f.bundle_mb + f.rootfs_mb
    fetch = np.where(code == 0, a.reg_rtt + mb * 8 * 1024 * 1024 / a.down + a.verify * mb / speed, 0.0)
    return fetch, rest
