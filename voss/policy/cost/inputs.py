"""Static inputs of the cost model (doc 03 §5.2). Built by the runtime from public profiles and configs, so the
policy layer never reads the world (doc 05 §2)."""

from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np


@dataclass(frozen=True)
class StartupModel:
    """Mean fixed costs of one substrate's ladder (from its profile + calibration bundle)."""

    boot_s: float
    restore_s: float
    dispatch_s: float
    trust_fixed_s: float
    verify_s_per_mb: float
    touched_frac: float
    cpu_factor: float = 1.0
    has_snapshot_level: bool = True


@dataclass(frozen=True)
class FnInfo:
    name: str
    tenant: str
    mem_mb: float
    bundle_mb: float
    rootfs_mb: float
    snapshot_mb: float
    init_s: float
    out_bytes: float
    idempotent: bool
    work_ref_s: float = 0.1


@dataclass(frozen=True)
class TenantInfo:
    sigma: float
    kbs_lat: float
    kbs_lon: float
    assurance_floor: float
    f: int | None = None


@dataclass(frozen=True)
class GeoRtt:
    """The scheduler's own RTT estimate from declared locations (not ground truth): km / c_eff × route + last mile."""

    c_eff_km_per_ms: float = 100.0
    route_factor: float = 1.3
    last_mile_s: float = 0.02

    def rtt(self, lat1: np.ndarray, lon1: np.ndarray, lat2: float, lon2: float) -> np.ndarray:
        p1, p2 = np.radians(lat1), math.radians(lat2)
        dl = np.radians(lon2 - lon1)
        a = np.sin((p2 - p1) / 2) ** 2 + np.cos(p1) * math.cos(p2) * np.sin(dl / 2) ** 2
        km = 2 * 6371.0 * np.arcsin(np.sqrt(np.clip(a, 0, 1)))
        out: np.ndarray = km / self.c_eff_km_per_ms * self.route_factor / 1e3 + self.last_mile_s
        return out


@dataclass(frozen=True)
class CostContext:
    """Everything static the cost model needs besides the view and the predictions."""

    startup: dict[str, StartupModel]
    fns: dict[str, FnInfo]
    tenants: dict[str, TenantInfo]
    registry: tuple[float, float]
    routers: dict[str, tuple[float, float]] = field(default_factory=dict)
    geo: GeoRtt = field(default_factory=GeoRtt)
    sync_weight: float = 1.0
    eps: float = 0.05
    lambda_exposure: float = 1.0
    K: int = 12
