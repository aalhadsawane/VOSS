"""Workload: functions, tenants, arrivals, SLO classes (doc 02 §8).

Arrivals are a precomputed trace: Zipf popularity over functions; per function a Poisson or two-state MMPP process;
origin city by population with local-time demand diurnality (thinning); optional flash crowds.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

import numpy as np
import pandas as pd
from pydantic import BaseModel, ConfigDict, Field

from voss.core.config import ScenarioConfig
from voss.core.paths import load_data_yaml
from voss.core.rng import RngFactory
from voss.world.config_merge import merged
from voss.world.geo import Metros, diurnal, local_hour

SLO_CLASSES: tuple[str, ...] = ("sync", "async", "filler")


class _M(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class FunctionSpec(_M):
    """One function@version (``configs/functions.yaml``)."""

    name: str
    tenant: str
    runtime: str
    version: int = 1
    rootfs_mb: float = Field(gt=0)
    bundle_mb: float = Field(gt=0)
    snapshot_mb: float = Field(gt=0)
    mem_mb: float = Field(gt=0)
    init_s: float = Field(ge=0)
    work_ref_s: float = Field(gt=0)
    in_kb: float = Field(gt=0)
    in_sigma: float = Field(ge=0)
    size_exp: float = Field(ge=0)
    out_kb: float = Field(ge=0)
    idempotent: bool
    slo_class: Literal["sync", "async", "filler"]
    slo_k: float = Field(gt=0)


class TenantSpec(_M):
    """One tenant (``configs/tenants.yaml``)."""

    id: str
    sensitivity: Literal["low", "medium", "high"]
    kbs_city: str
    assurance_floor: float = Field(ge=0, le=1)
    f: int | None = None


class FlashCrowd(_M):
    t: float
    duration_s: float = Field(gt=0)
    mult: float = Field(gt=1)
    fn: str = "top"
    city: str


class LoadRegime(_M):
    """``configs/regimes/load_*.yaml`` merged with ``scenario.load`` overrides."""

    regime: str
    rate: float = Field(gt=0)
    zipf_s: float = Field(ge=0)
    diurnal: dict[str, float] = Field(default_factory=lambda: {"peak_h": 15.0, "amplitude": 0.3})
    mmpp: dict[str, float | bool] = Field(default_factory=dict)
    async_deadline_s: float = 60.0
    sync_overhead_s: float = 0.05
    flash_crowds: list[FlashCrowd] = Field(default_factory=list)


@dataclass(frozen=True)
class Catalog:
    functions: tuple[FunctionSpec, ...]
    tenants: tuple[TenantSpec, ...]

    def fn_index(self, name: str) -> int:
        return [f.name for f in self.functions].index(name)

    def tenant_index(self, tid: str) -> int:
        return [t.id for t in self.tenants].index(tid)


@dataclass(frozen=True)
class ArrivalTrace:
    """Doc 01 §4 ``ArrivalTrace``: ``(t, fn, tenant, origin, in_bytes, slo_class, deadline_s)`` sorted by ``t``."""

    frame: pd.DataFrame

    def __len__(self) -> int:
        return len(self.frame)


def load_catalog(sc: ScenarioConfig) -> Catalog:
    fns = tuple(FunctionSpec.model_validate(f) for f in load_data_yaml(sc.functions)["functions"])
    ten = tuple(TenantSpec.model_validate(t) for t in load_data_yaml(sc.tenants)["tenants"])
    known = {t.id for t in ten}
    for f in fns:
        if f.tenant not in known:
            raise ValueError(f"function {f.name}: unknown tenant {f.tenant}")
    return Catalog(fns, ten)


def load_load_regime(sc: ScenarioConfig) -> LoadRegime:
    name = str(sc.load.get("regime", "load_default"))
    return LoadRegime.model_validate(merged(load_data_yaml(f"regimes/{name}.yaml"), sc.load))


def popularity(n: int, s: float, gen: np.random.Generator) -> np.ndarray:
    """Zipf(s) shares assigned to functions in a random rank order."""
    w = 1.0 / np.arange(1, n + 1) ** s
    out: np.ndarray = (w / w.sum())[gen.permutation(n)]
    return out


def _mmpp_multiplier(reg: LoadRegime, horizon: float, gen: np.random.Generator) -> tuple[np.ndarray, np.ndarray]:
    """Piecewise-constant rate multiplier ``(breakpoints, values)`` with mean 1 (two-state MMPP)."""
    mp = reg.mmpp
    if not mp.get("enabled", False):
        return np.array([0.0]), np.array([1.0])
    b, tn, tb = float(mp["burst_mult"]), float(mp["mean_normal_s"]), float(mp["mean_burst_s"])
    norm = (tn + b * tb) / (tn + tb)
    t, burst, bps, vals = 0.0, False, [], []
    while t < horizon:
        bps.append(t)
        vals.append((b if burst else 1.0) / norm)
        t += gen.exponential(tb if burst else tn)
        burst = not burst
    return np.array(bps), np.array(vals)


def _one_function(
    lam: float, reg: LoadRegime, metros: Metros, horizon: float, start_utc_h: float, gen: np.random.Generator
) -> tuple[np.ndarray, np.ndarray]:
    """Arrival times and origin cities for one function (thinning over MMPP × origin diurnality)."""
    bps, vals = _mmpp_multiplier(reg, horizon, gen)
    amp, peak = reg.diurnal.get("amplitude", 0.0), reg.diurnal.get("peak_h", 15.0)
    lam_max = lam * float(vals.max()) * (1 + amp)
    n = gen.poisson(lam_max * horizon)
    t = np.sort(gen.random(n) * horizon)
    origin = gen.choice(len(metros), size=n, p=metros.weights())
    m = vals[np.searchsorted(bps, t, side="right") - 1]
    d = np.asarray(diurnal(local_hour(metros.tz[origin], t, start_utc_h), peak, amp))
    keep = gen.random(n) * lam_max <= lam * m * d
    return t[keep], origin[keep]


def _flash(
    fc: FlashCrowd, lam: float, metros: Metros, horizon: float, gen: np.random.Generator
) -> tuple[np.ndarray, np.ndarray]:
    end = min(fc.t + fc.duration_s, horizon)
    n = gen.poisson(lam * (fc.mult - 1) * max(0.0, end - fc.t))
    return np.sort(fc.t + gen.random(n) * (end - fc.t)), np.full(n, metros.index(fc.city))


def generate_arrivals(
    sc: ScenarioConfig, catalog: Catalog, metros: Metros, horizon: float, rng: RngFactory
) -> ArrivalTrace:
    """Doc 02 §8; each function draws from its own stream (adding a function never perturbs the others)."""
    reg = load_load_regime(sc)
    fns = catalog.functions
    share = popularity(len(fns), reg.zipf_s, rng.stream("workload.popularity"))
    top = int(np.argmax(share))
    parts = []
    for i, f in enumerate(fns):
        g = rng.stream("workload.fn", f.name)
        t, origin = _one_function(reg.rate * share[i], reg, metros, horizon, sc.start_utc_h, g)
        for fc in reg.flash_crowds:
            if fc.fn == f.name or (fc.fn == "top" and i == top):
                ft, fo = _flash(fc, reg.rate * share[i], metros, horizon, g)
                t, origin = np.r_[t, ft], np.r_[origin, fo]
        size = g.lognormal(np.log(f.in_kb * 1024), f.in_sigma, len(t))
        parts.append(_frame(f, i, catalog.tenant_index(f.tenant), t, origin, size, reg))
    df = pd.concat(parts, ignore_index=True).sort_values(["t", "fn"], kind="stable").reset_index(drop=True)
    return ArrivalTrace(df)


def warm_estimate_s(f: FunctionSpec, in_bytes: np.ndarray) -> np.ndarray:
    """Reference warm execution time at a given input size (``work ∝ (in/in_ref)^size_exp``)."""
    return f.work_ref_s * (in_bytes / (f.in_kb * 1024)) ** f.size_exp


def _frame(
    f: FunctionSpec, fi: int, ti: int, t: np.ndarray, origin: np.ndarray, size: np.ndarray, reg: LoadRegime
) -> pd.DataFrame:
    if f.slo_class == "sync":
        deadline = f.slo_k * (warm_estimate_s(f, size) + reg.sync_overhead_s)
    elif f.slo_class == "async":
        deadline = np.full(len(t), reg.async_deadline_s)
    else:
        deadline = np.full(len(t), np.inf)
    return pd.DataFrame(
        {
            "t": t,
            "fn": fi,
            "tenant": ti,
            "origin": origin,
            "in_bytes": size.astype(np.int64),
            "slo_class": SLO_CLASSES.index(f.slo_class),
            "deadline_s": deadline,
        }
    )
