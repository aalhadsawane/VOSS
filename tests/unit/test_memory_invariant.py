"""Doc 02 §4: running invocations fit in a worker's donated memory, so admission needs no memory check."""

from __future__ import annotations

import pytest
from voss.core.config import ScenarioConfig
from voss.core.rng import RngFactory
from voss.world.geo import load_metros
from voss.world.hardware import HwClass
from voss.world.machines import load_hw
from voss.world.scenario import check_memory_invariant
from voss.world.workers import cap_slots_by_memory, generate_workers
from voss.world.workload import load_catalog

from tests.fixtures.fleet import BUNDLES, FLEET

METROS = load_metros()


def _workers(sc: ScenarioConfig, hw: dict[str, HwClass], mix: dict[str, float]):  # type: ignore[no-untyped-def]
    return generate_workers(sc, METROS, hw, RngFactory(1), mix)


@pytest.mark.parametrize("bundle", BUNDLES)
def test_default_envelope_fits_every_fleet_class(bundle: str) -> None:
    """D-108: the fleet's slot cap keeps every class within its donated memory at the default envelope."""
    sc = ScenarioConfig(workers=50, machines=FLEET)
    catalog = load_catalog(sc)
    big = max(f.mem_mb for f in catalog.functions)
    workers = cap_slots_by_memory(_workers(sc, {bundle: load_hw(bundle)}, {bundle: 1.0}), big)
    check_memory_invariant(workers, catalog)


def test_violation_is_reported() -> None:
    """A 3-core, 4 GB class at cpu_frac 1.0 would hold 3 x 1,024 MB > 2,458 MB: the guard must refuse it."""
    small = HwClass(
        name="small",
        speed=1.0,
        cores=3,
        mem_gb=4.0,
        ssd_gb=100.0,
        hdd_gb=0.0,
        ssd_read_MBps=500.0,
        ssd_write_MBps=500.0,
        hdd_read_MBps=100.0,
        hdd_write_MBps=100.0,
        cpu_model="test",
        tpm="none",
    )
    sc = ScenarioConfig(workers=20, machines=FLEET, envelope={"cpu_frac": 1.0})
    with pytest.raises(ValueError, match="memory invariant violated"):
        check_memory_invariant(_workers(sc, {"small": small}, {"small": 1.0}), load_catalog(sc))
