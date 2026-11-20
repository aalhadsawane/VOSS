"""Scenario = precomputed exogenous traces (doc 01 §4): generated once from ``(config, seed)``, hashed, stored under
``runs/scenarios/<hash>/`` and replayed by every compared system.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, replace
from pathlib import Path

import numpy as np
import pandas as pd

from voss.core.config import RunConfig
from voss.core.hashing import hash_columns
from voss.core.rng import RngFactory
from voss.world.adversary import BEHAVIORS, AdversaryTrace, generate_adversaries, load_adversary_regime
from voss.world.geo import Metros, load_metros, with_traced_pop
from voss.world.hardware import load_hw_classes
from voss.world.machines import Fleet, fleet_columns, load_fleet
from voss.world.sessions import SessionTrace, generate_sessions
from voss.world.workers import GeoParams, WorkerTable, generate_workers
from voss.world.workload import ArrivalTrace, Catalog, generate_arrivals, load_catalog


@dataclass(frozen=True)
class Scenario:
    """All exogenous traces of one ``(config, seed)``."""

    hash: str
    horizon: float
    metros: Metros
    catalog: Catalog
    workers: WorkerTable
    sessions: SessionTrace
    adversary: AdversaryTrace
    arrivals: ArrivalTrace
    fleet: Fleet | None = None  # calibrated machine classes (plan V9.4); None: the configured hardware classes

    def tables(self) -> dict[str, pd.DataFrame]:
        return _tables(self.workers, self.sessions, self.adversary, self.arrivals)


def _tables(
    workers: WorkerTable, sessions: SessionTrace, adv: AdversaryTrace, arr: ArrivalTrace
) -> dict[str, pd.DataFrame]:
    platform = pd.DataFrame({"worker": np.arange(len(workers)), "join_t": sessions.join_t, "leave_t": sessions.leave_t})
    return {
        "workers": workers.to_frame(),
        "sessions": sessions.sessions,
        "fake_drains": sessions.fake_drains,
        "platform": platform,
        "adversary": adv.to_frame(),
        "arrivals": arr.frame,
    }


def _hash(tables: dict[str, pd.DataFrame], catalog: Catalog, horizon: float, fleet: Fleet | None = None) -> str:
    cols = {name: {c: df[c].to_numpy() for c in df.columns} for name, df in tables.items()}
    if fleet is not None:  # only a fleet scenario hashes it, so other scenarios keep their hash
        cols["machines"] = fleet_columns(fleet)
    cols["catalog"] = {
        "functions": [f.model_dump_json() for f in catalog.functions],
        "tenants": [t.model_dump_json() for t in catalog.tenants],
    }
    cols["meta"] = {"horizon": [horizon]}
    return hash_columns(cols)


def check_memory_invariant(workers: WorkerTable, catalog: Catalog) -> None:
    """Doc 02 §4: running invocations never exceed a worker's memory budget, so admission needs no memory check.

    Every attempt holds one concurrency slot, and ``Slots`` admits up to ``slots`` of them. The worst case is that all
    run the largest function: ``slots × max mem_mb`` must fit in ``mem_mb`` (the donated memory share). Warm sandboxes
    are evicted for running memory (``cache.park_warm``), so the invariant keeps running memory from ever going negative
    in the free-memory computation.
    """
    big = max(f.mem_mb for f in catalog.functions)
    need = workers.slots * big
    bad = np.flatnonzero(need > workers.mem_mb)
    if len(bad):
        j = int(bad[0])
        raise ValueError(
            f"memory invariant violated on {len(bad)} workers (first: worker {j}, hardware "
            f"{workers.hw_names[int(workers.hw[j])]}): {int(workers.slots[j])} slots x {big:g} MB = {need[j]:g} MB "
            f"> {workers.mem_mb[j]:g} MB donated memory; lower envelope.cpu_frac or raise envelope.mem_frac (doc 02 §4)"
        )


def generate(cfg: RunConfig) -> Scenario:
    """Doc 01 §4. Order: workers → adversaries → sessions (fake drains) → arrivals; each uses its own streams."""
    sc, rng, horizon = cfg.scenario, RngFactory(cfg.seed), cfg.horizon_s
    gp = GeoParams.model_validate(sc.geo)
    metros = load_metros(gp.metros)
    if gp.pop_trace:
        metros = with_traced_pop(metros, Path(gp.trace_root) / gp.pop_trace / "metro_pop.parquet")
    metros = metros.restrict(gp.regions)
    catalog = load_catalog(sc, cfg.calibration)
    fleet = load_fleet(sc.machines, cfg.calibration, catalog) if sc.machines else None
    if fleet is not None:
        workers = generate_workers(sc, metros, fleet.hw, rng, fleet.mix.weights)
    else:
        workers = generate_workers(sc, metros, load_hw_classes(sorted(sc.hw_mix), cfg.calibration), rng)
    check_memory_invariant(workers, catalog)
    adv = generate_adversaries(sc, workers, horizon, rng)
    params = load_adversary_regime(sc).params
    fake = np.flatnonzero(adv.behavior == BEHAVIORS.index("fake_signals"))
    sessions = generate_sessions(
        sc, workers, metros, horizon, rng, (fake, params.fake_drain_rate_per_h, params.fake_drain_lead_s)
    )
    arrivals = generate_arrivals(sc, catalog, metros, horizon, rng)
    h = _hash(_tables(workers, sessions, adv, arrivals), catalog, horizon, fleet)
    return Scenario(h, horizon, metros, catalog, workers, sessions, adv, arrivals, fleet)


def with_world(scn: Scenario, workers: WorkerTable, sessions: SessionTrace, adversary: AdversaryTrace) -> Scenario:
    """The same workload on another worker population (reference clouds, doc 02 §9), rehashed."""
    h = _hash(_tables(workers, sessions, adversary, scn.arrivals), scn.catalog, scn.horizon)
    return replace(scn, hash=h, workers=workers, sessions=sessions, adversary=adversary, fleet=None)


def store(scn: Scenario, root: Path) -> Path:
    """Write every trace as Parquet plus ``meta.json`` under ``root/<hash>/`` (idempotent)."""
    out = root / scn.hash
    if (out / "meta.json").exists():
        return out
    out.mkdir(parents=True, exist_ok=True)
    for name, df in scn.tables().items():
        df.to_parquet(out / f"{name}.parquet", index=False)
    meta = {
        "hash": scn.hash,
        "horizon": scn.horizon,
        "workers": len(scn.workers),
        "arrivals": len(scn.arrivals),
        "sessions": len(scn.sessions.sessions),
        "functions": [f.model_dump() for f in scn.catalog.functions],
        "tenants": [t.model_dump() for t in scn.catalog.tenants],
    }
    if scn.fleet is not None:  # weights and what each class shares with the reference (D-107)
        meta["machines"] = {
            "reference": scn.fleet.reference,
            "weights": scn.fleet.mix.weights,
            "unrepresented": scn.fleet.mix.unrepresented,
            "non_x86": scn.fleet.mix.non_x86,
            "provenance": {n: c.provenance for n, c in sorted(scn.fleet.classes.items())},
        }
    (out / "meta.json").write_text(json.dumps(meta, indent=2, sort_keys=True))
    return out
