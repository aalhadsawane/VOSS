"""Reference clouds (doc 02 §9, doc 06 §4 ``ref_lambda_like``/``ref_azure_like``): regional always-on, reliable
provider hosts at the router metros with a fixed keep-alive TTL and published cold-start distributions; no churn, no
adversaries, no control-plane faults. The workload (catalog, arrivals, geography) is the VOSS scenario's, so
systems compare paired on the same arrivals. Profiles live in ``configs/references/<name>.yaml``.
"""

from __future__ import annotations

import hashlib
from dataclasses import replace

import numpy as np
import pandas as pd
from pydantic import BaseModel, ConfigDict

from voss.core.paths import load_data_yaml
from voss.world.adversary import AdversaryTrace
from voss.world.hardware import load_hw_class
from voss.world.scenario import Scenario, with_world
from voss.world.sessions import SessionTrace
from voss.world.workers import TIERS, WorkerTable

DC_LAST_MILE_S = 0.0005  # in-region data-centre hop  # TODO verify
DC_BPS = 10e9
RACKS = 8  # failure domains per region


class Pricing(BaseModel):
    """Published list prices (USD) and billing granularity."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    per_m_requests: float
    per_gb_s: float
    min_billed_ms: float = 1.0
    mem_step_mb: float = 1.0
    min_mem_mb: float = 128.0


class RefProfile(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    name: str
    substrate: str
    hw: str
    hosts_per_region: int
    voss: tuple[str, ...] = ()  # overrides applied to the run config (the reference's own control choices)
    pricing: Pricing


def load_reference(name: str) -> RefProfile:
    raw = load_data_yaml(f"references/{name}.yaml")
    raw.pop("provenance", None)
    prof = RefProfile.model_validate(raw)
    if prof.name != name:
        raise ValueError(f"references/{name}.yaml declares name '{prof.name}'")
    return prof


def dc_workers(scn: Scenario, ref: RefProfile, regions: tuple[str, ...]) -> WorkerTable:
    """``hosts_per_region`` provider hosts at each router metro, ``RACKS`` failure domains per region."""
    m, hw = scn.metros, load_hw_class(ref.hw)
    city = np.repeat([m.index(c) for c in regions], ref.hosts_per_region)
    n = len(city)
    rack = np.tile(np.arange(ref.hosts_per_region) % RACKS, len(regions))
    domain = np.repeat(np.arange(len(regions)), ref.hosts_per_region) * RACKS + rack
    ident = tuple(hashlib.sha256(f"{ref.name}:{i}".encode()).hexdigest()[:16] for i in range(n))
    return WorkerTable(
        city=city,
        lat=m.lat[city].astype(float),
        lon=m.lon[city].astype(float),
        tz=m.tz[city],
        hw=np.zeros(n, dtype=np.int64),
        substrate=np.zeros(n, dtype=np.int64),
        tier=np.full(n, TIERS.index("dedicated")),
        asn=domain.copy(),
        domain=domain,
        down_bps=np.full(n, DC_BPS),
        up_bps=np.full(n, DC_BPS),
        last_mile_s=np.full(n, DC_LAST_MILE_S),
        relayed=np.zeros(n, dtype=bool),
        known_good=np.ones(n, dtype=bool),
        slots=np.full(n, hw.cores),
        speed=np.full(n, hw.speed),
        mem_mb=np.full(n, hw.mem_gb * 1024.0),
        ssd_mb=np.full(n, hw.ssd_gb * 1024.0),
        hdd_mb=np.zeros(n),
        identity=ident,
        hw_names=(ref.hw,),
        substrate_names=(ref.substrate,),
    )


def reference_scenario(scn: Scenario, ref: RefProfile, regions: tuple[str, ...]) -> Scenario:
    """The VOSS scenario's workload on an always-on provider fleet (one session per host covering the run)."""
    workers = dc_workers(scn, ref, regions)
    n = len(workers)
    sessions = SessionTrace(
        pd.DataFrame({"worker": np.arange(n), "start": -1.0, "end": np.inf, "drain_t": np.nan, "reason": "always_on"}),
        pd.DataFrame({"worker": pd.Series([], dtype=np.int64), "t": [], "deadline": []}),
        np.zeros(n),
        np.full(n, np.inf),
    )
    adv = AdversaryTrace(np.zeros(n, dtype=np.int64), np.zeros(n), np.ones(n), ((),) * n, scn.adversary.params)
    return with_world(replace(scn, control_faults=scn.control_faults.iloc[0:0]), workers, sessions, adv)
