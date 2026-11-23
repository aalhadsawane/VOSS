"""Trace-driven workload (docs/REVISION_PLAN.md V9.1): the sampled Azure Functions 2019 functions and their per-minute
invocation counts (``tools/traces/azure.py``) replace the synthetic arrival process.

- Each trace function is mapped to the measured (workload function, input size) profile whose median run time is
  nearest to the trace function's median duration on a log scale, across all profiles of the calibration bundle
  (``exec_by_size`` in ``functions.yaml``); its invocations use that input size, and its copy of the function runs
  for the measured median at that size. A bundle without run times per input size gives one profile per catalogue
  function at its reference input (``work_ref_s``). Run times always come from the calibration bundle, never from the
  trace. Trace functions without a duration in the trace are left out (counted); the share whose duration lies
  outside the measured range is recorded (``TraceFunctions.outside``).
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

from voss.core.paths import REPO_ROOT, load_data_yaml
from voss.core.rng import RngFactory
from voss.world.geo import Metros
from voss.world.workload import Catalog, LoadRegime, _frame


@dataclass(frozen=True)
class TraceFunctions:
    # functions_<split>.parquet rows kept, with the mapped profile: "base" (workload function), "size_kb" (its input
    # size), "profile_s" (its measured median run time) and "outside" (duration outside the measured range)
    table: pd.DataFrame
    dropped: int  # trace functions without a duration
    per_size: bool  # True: profiles per (function, input size); False: one per function at its reference input

    @property
    def outside(self) -> float:
        """Share of the kept trace functions whose median duration is outside the measured range of run times."""
        return float(self.table.outside.mean()) if len(self.table) else 0.0


@dataclass(frozen=True)
class Profile:
    base: str
    size_kb: float
    work_s: float


def trace_dir(reg: LoadRegime) -> Path:
    d = Path(reg.trace_root) / reg.trace
    d = d if d.is_absolute() else REPO_ROOT / d
    if not (d / f"functions_{reg.split}.parquet").exists():
        raise FileNotFoundError(f"{d}: run `python -m tools.traces.azure --out {d}` or fetch the release asset")
    return d


def nearest(dur_s: np.ndarray, work_s: np.ndarray) -> np.ndarray:
    """For each duration, the index of the run time nearest on a log scale (ties: first in order)."""
    lw = np.log(np.maximum(work_s, 1e-9))
    ld = np.log(np.maximum(dur_s, 1e-9))
    return np.array([int(np.argmin(np.abs(lw - x))) for x in ld], dtype=np.int64)


def nearest_profile(dur_s: np.ndarray, names: list[str], work_s: np.ndarray) -> list[str]:
    """For each duration, the profile name whose run time is nearest on a log scale (ties: first in order)."""
    return [names[i] for i in nearest(dur_s, work_s)]


def profiles(base: Catalog, sizes: dict[str, dict[float, float]]) -> tuple[list[Profile], bool]:
    """Every measured (function, input size) profile, in catalogue then size order; without per-size run times in
    the bundle, each catalogue function at its reference input."""
    per = [Profile(f.name, s, t) for f in base.functions for s, t in sorted(sizes.get(f.name, {}).items())]
    if per:
        return per, True
    return [Profile(f.name, f.in_kb, f.work_ref_s) for f in base.functions], False


def load_trace_functions(
    reg: LoadRegime, base: Catalog, sizes: dict[str, dict[float, float]] | None = None
) -> TraceFunctions:
    t = pd.read_parquet(trace_dir(reg) / f"functions_{reg.split}.parquet")
    keep = t.dur_p50_ms.notna() & (t.dur_p50_ms > 0)
    t = t[keep].reset_index(drop=True)
    prof, per_size = profiles(base, sizes or {})
    work = np.array([p.work_s for p in prof])
    dur = t.dur_p50_ms.to_numpy() / 1000
    pick = [prof[i] for i in nearest(dur, work)]
    t = t.assign(
        base=[p.base for p in pick],
        size_kb=[p.size_kb for p in pick],
        profile_s=[p.work_s for p in pick],
        outside=(dur < work.min()) | (dur > work.max()),
    )
    return TraceFunctions(t, int((~keep).sum()), per_size)


def request_kb(fn: str, size: float, rules: dict[str, object], param_kb: float) -> float:
    """kB a client sends for one invocation of ``fn`` at the measured input ``size`` (``configs/request_bytes.yaml``,
    D-106): the size itself for data functions, ``param_kb`` (the catalogue's smallest input) for functions whose
    guest builds the input from parameters, the encoded image for image functions."""
    images = dict(rules.get("images") or {})  # type: ignore[call-overload]
    if fn in (rules.get("data") or []):  # type: ignore[operator]
        return float(size)
    if fn in (rules.get("parameters") or []):  # type: ignore[operator]
        return float(param_kb)
    if fn in images:
        im = images[fn]
        return float(im["small_bytes"] if size <= im["max_small_size"] else im["large_bytes"]) / 1024
    raise ValueError(f"configs/request_bytes.yaml: no request size rule for {fn}")


def trace_catalog(reg: LoadRegime, base: Catalog, sizes: dict[str, dict[float, float]] | None = None) -> Catalog:
    """Catalog of the trace's functions and owners (before per-function key domains, D-85). With per-size profiles a
    function's copy runs for the measured median at its mapped size (``work_ref_s``) and its invocations carry the
    bytes a client sends at that size (``in_kb`` by ``request_kb``, exact: D-105, D-106)."""
    tf = load_trace_functions(reg, base, sizes)
    rules = load_data_yaml("request_bytes.yaml") if tf.per_size else {}
    param_kb = min(f.in_kb for f in base.functions)
    by_name = {f.name: f for f in base.functions}
    tmpl = base.tenants[0]
    fns, prof = [], {}
    for r in tf.table.itertuples():
        upd: dict[str, object] = {"name": f"tr{int(r.fn):04d}", "tenant": str(r.owner)}
        upd["slo_class"] = "sync" if r.sync else "async"
        if tf.per_size:
            kb = request_kb(str(r.base), float(r.size_kb), rules, param_kb)
            upd |= {"in_kb": kb, "work_ref_s": float(r.profile_s)}
        fns.append(by_name[str(r.base)].model_copy(update=upd))
        prof[str(upd["name"])] = (str(r.base), float(r.size_kb) if tf.per_size else None)
    owners = sorted({f.tenant for f in fns})
    tenants = tuple(tmpl.model_copy(update={"id": o}) for o in owners)
    return Catalog(tuple(fns), tenants, transfer_deadline=tf.per_size, profiles=prof)


def trace_arrivals(
    reg: LoadRegime,
    catalog: Catalog,
    metros: Metros,
    horizon: float,
    rng: RngFactory,
    down_bps: float | None = None,
    deadline_multiple: float = 5.0,
) -> pd.DataFrame:
    """Arrival frame in the ``ArrivalTrace`` schema (``workload._frame``), sorted by time; with ``down_bps`` the
    synchronous deadlines include the input's transfer at that rate (D-106)."""
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
        size = np.full(len(t), f.in_kb * 1024)
        parts.append(_frame(f, i, catalog.tenant_index(f.tenant), t, origin, size, reg, deadline_multiple, down_bps))
    df = (
        pd.concat(parts, ignore_index=True)
        if parts
        else _frame(catalog.functions[0], 0, 0, np.zeros(0), np.zeros(0, np.int64), np.zeros(0), reg, deadline_multiple)
    )
    return df.sort_values(["t", "fn"], kind="stable").reset_index(drop=True)
