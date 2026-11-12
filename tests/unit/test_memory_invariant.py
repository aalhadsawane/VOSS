"""Doc 02 §4: running invocations fit in a worker's donated memory, so admission needs no memory check."""

from __future__ import annotations

import pytest
from voss.core.config import ScenarioConfig
from voss.core.rng import RngFactory
from voss.world.geo import load_metros
from voss.world.hardware import load_hw_classes
from voss.world.scenario import check_memory_invariant
from voss.world.workers import generate_workers
from voss.world.workload import load_catalog

METROS = load_metros()
CLASSES = ("C0", "C1", "C2", "C3", "E0")  # every worker class used by a scenario (DC is the reference cloud only)


def _check(sc: ScenarioConfig) -> None:
    workers = generate_workers(sc, METROS, load_hw_classes(sorted(sc.hw_mix)), RngFactory(1))
    check_memory_invariant(workers, load_catalog(sc))


@pytest.mark.parametrize("hw", CLASSES)
def test_default_envelope_fits_every_class(hw: str) -> None:
    _check(ScenarioConfig(workers=50, hw_mix={hw: 1.0}))


def test_violation_is_reported() -> None:
    """E0 (3 cores, 4 GB) at cpu_frac 1.0 holds 3 x 1024 MB > 2458 MB: the guard must refuse it."""
    sc = ScenarioConfig(workers=20, hw_mix={"E0": 1.0}, envelope={"cpu_frac": 1.0})
    with pytest.raises(ValueError, match="memory invariant violated"):
        _check(sc)
