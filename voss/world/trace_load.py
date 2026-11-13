"""Trace-driven workload (docs/REVISION_PLAN.md V9.1): the sampled Azure Functions 2019 functions and their per-minute
invocation counts (``tools/traces/azure.py``) replace the synthetic arrival process.

- Each trace function becomes a copy of the measured workload function whose run time at its reference input is nearest
  to the trace function's median duration on a log scale (``nearest_profile``). Run times always come from the
  calibration bundle, never from the trace. Trace functions without a duration in the trace are left out (counted).
- Tenant = owner hash, with the settings of the template tenant (the first in ``tenants.yaml``); a function is
  synchronous if its trigger is ``http``.
- Arrivals: in each minute, a Poisson number of invocations with mean ``rate_mult`` × the trace count, at uniform times
  (the trace has only per-minute counts). Minute 0 of the run is ``start_min`` of the split.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

from voss.core.paths import REPO_ROOT
from voss.core.rng import RngFactory
from voss.world.geo import Metros
from voss.world.workload import Catalog, LoadRegime, _frame


@dataclass(frozen=True)
class TraceFunctions:
    table: pd.DataFrame  # functions_<split>.parquet rows kept, with column "base" (mapped workload function)
    dropped: int  # trace functions without a duration


def trace_dir(reg: LoadRegime) -> Path:
    d = Path(reg.trace_root) / reg.trace
    d = d if d.is_absolute() else REPO_ROOT / d
    if not (d / f"functions_{reg.split}.parquet").exists():
        raise FileNotFoundError(f"{d}: run `python -m tools.traces.azure --out {d}` or fetch the release asset")
    return d


def nearest_profile(dur_s: np.ndarray, names: list[str], work_s: np.ndarray) -> list[str]:
    """For each duration, the profile name whose run time is nearest on a log scale (ties: first in order)."""
    lw = np.log(np.maximum(work_s, 1e-9))
    ld = np.log(np.maximum(dur_s, 1e-9))
    return [names[int(np.argmin(np.abs(lw - x)))] for x in ld]


def load_trace_functions(reg: LoadRegime, base: Catalog) -> TraceFunctions:
    t = pd.read_parquet(trace_dir(reg) / f"functions_{reg.split}.parquet")
    keep = t.dur_p50_ms.notna() & (t.dur_p50_ms > 0)
    t = t[keep].reset_index(drop=True)
    names = [f.name for f in base.functions]
    work = np.array([f.work_ref_s for f in base.functions])
    return TraceFunctions(
        t.assign(base=nearest_profile(t.dur_p50_ms.to_numpy() / 1000, names, work)), int((~keep).sum())
    )


def trace_catalog(reg: LoadRegime, base: Catalog) -> Catalog:
    """Catalog of the trace's functions and owners (before per-function key domains, D-85)."""
    tf = load_trace_functions(reg, base)
    by_name = {f.name: f for f in base.functions}
    tmpl = base.tenants[0]
    fns = tuple(
        by_name[r.base].model_copy(
            update={"name": f"tr{int(r.fn):04d}", "tenant": str(r.owner), "slo_class": "sync" if r.sync else "async"}
        )
        for r in tf.table.itertuples()
    )
    owners = sorted({f.tenant for f in fns})
    tenants = tuple(tmpl.model_copy(update={"id": o}) for o in owners)
    return Catalog(fns, tenants)


def trace_arrivals(reg: LoadRegime, catalog: Catalog, metros: Metros, horizon: float, rng: RngFactory) -> pd.DataFrame:
    """Arrival frame in the ``ArrivalTrace`` schema (``workload._frame``), sorted by time."""
    counts = pd.read_parquet(trace_dir(reg) / f"arrivals_{reg.split}.parquet")
    lo, hi = reg.start_min, reg.start_min + int(np.ceil(horizon / 60))
    counts = counts[(counts.minute >= lo) & (counts.minute < hi)]
    by_fn = dict(tuple(counts.groupby("fn")))
    parts = []
    for i, f in enumerate(catalog.functions):
        g = rng.stream("workload.trace", f.name)
        c = by_fn.get(int(f.name[2:]))
        if c is None:
            continue
        n = g.poisson(reg.rate_mult * c["count"].to_numpy())
        t = np.repeat((c.minute.to_numpy() - lo) * 60.0, n) + g.random(int(n.sum())) * 60.0
        t = np.sort(t[t < horizon])
        origin = g.choice(len(metros), size=len(t), p=metros.weights())
        size = g.lognormal(np.log(f.in_kb * 1024), f.in_sigma, len(t))
        parts.append(_frame(f, i, catalog.tenant_index(f.tenant), t, origin, size, reg))
    df = (
        pd.concat(parts, ignore_index=True)
        if parts
        else _frame(catalog.functions[0], 0, 0, np.zeros(0), np.zeros(0, np.int64), np.zeros(0), reg)
    )
    return df.sort_values(["t", "fn"], kind="stable").reset_index(drop=True)
