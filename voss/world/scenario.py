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
from voss.world.geo import Metros, load_metros
from voss.world.hardware import load_hw_classes
from voss.world.sessions import SessionTrace, generate_sessions
from voss.world.workers import GeoParams, WorkerTable, generate_workers
from voss.world.workload import ArrivalTrace, Catalog, generate_arrivals, load_catalog

CONTROL_FAULT_COLUMNS = ("t", "kind", "target", "duration_s", "factor")
FAULT_KINDS = ("sched_crash", "sched_blackhole", "sched_slow", "sched_partition")


def control_faults(rows: list[dict[str, object]]) -> pd.DataFrame:
    """Doc 07 §5 control-plane faults (E15): ``{t, kind, target: "cluster:<k>", duration_s, factor}``. Targets name a
    cluster (k-th by id when the fault fires); the runtime resolves its scheduler then."""
    out = []
    for r in rows:
        kind = str(r["kind"])
        if kind not in FAULT_KINDS:
            raise ValueError(f"unknown control fault {kind!r} (one of {FAULT_KINDS})")
        out.append(
            {
                "t": float(r["t"]),  # type: ignore[arg-type]
                "kind": kind,
                "target": str(r.get("target", "cluster:0")),
                "duration_s": float(r.get("duration_s", 60.0)),  # type: ignore[arg-type]
                "factor": float(r.get("factor", 10.0)),  # type: ignore[arg-type]
            }
        )
    return pd.DataFrame(out, columns=list(CONTROL_FAULT_COLUMNS)).sort_values("t", kind="stable")


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
    control_faults: pd.DataFrame

    def tables(self) -> dict[str, pd.DataFrame]:
        return _tables(self.workers, self.sessions, self.adversary, self.arrivals, self.control_faults)


def _tables(
    workers: WorkerTable, sessions: SessionTrace, adv: AdversaryTrace, arr: ArrivalTrace, faults: pd.DataFrame
) -> dict[str, pd.DataFrame]:
    platform = pd.DataFrame({"worker": np.arange(len(workers)), "join_t": sessions.join_t, "leave_t": sessions.leave_t})
    return {
        "workers": workers.to_frame(),
        "sessions": sessions.sessions,
        "fake_drains": sessions.fake_drains,
        "platform": platform,
        "adversary": adv.to_frame(),
        "arrivals": arr.frame,
        "control_faults": faults,
    }


def _hash(tables: dict[str, pd.DataFrame], catalog: Catalog, horizon: float) -> str:
    cols = {name: {c: df[c].to_numpy() for c in df.columns} for name, df in tables.items()}
    cols["catalog"] = {
        "functions": [f.model_dump_json() for f in catalog.functions],
        "tenants": [t.model_dump_json() for t in catalog.tenants],
    }
    cols["meta"] = {"horizon": [horizon]}
    return hash_columns(cols)


def generate(cfg: RunConfig) -> Scenario:
    """Doc 01 §4. Order: workers → adversaries → sessions (fake drains) → arrivals; each uses its own streams."""
    sc, rng, horizon = cfg.scenario, RngFactory(cfg.seed), cfg.horizon_s
    gp = GeoParams.model_validate(sc.geo)
    metros = load_metros(gp.metros).restrict(gp.regions)
    catalog = load_catalog(sc)
    workers = generate_workers(sc, metros, load_hw_classes(sorted(sc.hw_mix)), rng)
    adv = generate_adversaries(sc, workers, horizon, rng)
    params = load_adversary_regime(sc).params
    fake = np.flatnonzero(adv.behavior == BEHAVIORS.index("fake_signals"))
    sessions = generate_sessions(
        sc, workers, metros, horizon, rng, (fake, params.fake_drain_rate_per_h, params.fake_drain_lead_s)
    )
    arrivals = generate_arrivals(sc, catalog, metros, horizon, rng)
    faults = control_faults(sc.faults)
    h = _hash(_tables(workers, sessions, adv, arrivals, faults), catalog, horizon)
    return Scenario(h, horizon, metros, catalog, workers, sessions, adv, arrivals, faults)


def with_world(scn: Scenario, workers: WorkerTable, sessions: SessionTrace, adversary: AdversaryTrace) -> Scenario:
    """The same workload on another worker population (reference clouds, doc 02 §9), rehashed."""
    h = _hash(_tables(workers, sessions, adversary, scn.arrivals, scn.control_faults), scn.catalog, scn.horizon)
    return replace(scn, hash=h, workers=workers, sessions=sessions, adversary=adversary)


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
    (out / "meta.json").write_text(json.dumps(meta, indent=2, sort_keys=True))
    return out
