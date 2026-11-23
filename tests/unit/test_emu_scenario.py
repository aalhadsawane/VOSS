"""Emulation scenario file (plan V13): system overrides, repetition seeds, and the matching simulator spec."""

from __future__ import annotations

from pathlib import Path

import pytest
from tools.emu import scenario as spec_mod
from tools.emu.topology import KIND_PERFORMANCE, Cpu, Topology, plan
from voss.world.scenario import generate

from tests.fixtures.emu import FIXTURE

SCENARIO = "configs/emu/s1_central.yaml"


def test_the_shipped_scenario_resolves_to_the_two_handoff_systems() -> None:
    spec = spec_mod.load(SCENARIO)
    assert spec.name == "s1_central"
    assert sorted(spec.systems) == ["fixed_keepalive", "voss"]
    assert spec.seeds == [1, 2, 3]
    assert 6 <= spec.emu.workers <= 10  # handoff Part E: 6-10 emulated workers
    voss = spec.run_config("voss", 1)
    spec.check_workers(voss)
    assert voss.decision_clock.mode == "measured" and voss.decision_clock.cpu_scale == 0.0
    assert voss.label == "voss" and voss.seed == 1
    assert voss.voss.planner.name == "hetero"
    assert voss.scenario.workers == spec.emu.workers
    assert voss.horizon_s == 7200.0  # 2 h (handoff Part E)
    assert voss.scenario.functions.endswith("emu/functions.yaml")
    assert voss.calibration and "measured/" in voss.calibration


def test_each_system_runs_its_own_overrides_on_the_same_scenario() -> None:
    spec = spec_mod.load(SCENARIO)
    fk = spec.run_config("fixed_keepalive", 2)
    assert fk.voss.planner.name == "keepalive_ttl"
    assert fk.seed == 2 and fk.label == "fixed_keepalive"
    voss = spec.run_config("voss", 2)
    assert voss.voss.planner.name == "hetero"
    # the compared systems must see the same exogenous traces: the scenario hash ignores the planner
    short = [*FIXTURE, "horizon_s=60"]
    assert (
        generate(spec.run_config("voss", 1, short)).hash == generate(spec.run_config("fixed_keepalive", 1, short)).hash
    )


def test_bad_repetition_or_system_is_rejected() -> None:
    spec = spec_mod.load(SCENARIO)
    with pytest.raises(ValueError, match="rep must be"):
        spec.run_config("voss", 0)
    with pytest.raises(ValueError, match="rep must be"):
        spec.run_config("voss", len(spec.seeds) + 1)
    with pytest.raises(KeyError, match="not in s1_central"):
        spec.run_config("kpa", 1)


def test_simulator_side_uses_the_modeled_clock_and_the_same_seeds() -> None:
    spec = spec_mod.load(SCENARIO)
    ov = spec.sim_overrides("voss", 3)
    assert "decision_clock.mode=modeled" in ov
    assert "seed=3" in ov and "label=voss" in ov
    assert not any(o.startswith("decision_clock.cpu_scale") for o in ov)
    sim = spec.sim_spec()
    assert sim["experiment"] == "emu-s1_central"
    assert sim["seeds"] == spec.seeds
    assert sim["systems"] == spec.systems
    assert Path(str(sim["base"])).is_absolute()


def test_workers_must_match_the_emulated_host() -> None:
    spec = spec_mod.load(SCENARIO)
    cfg = spec.run_config("voss", 1)
    other = spec.model_copy(update={"emu": spec.emu.model_copy(update={"workers": spec.emu.workers + 1})})
    with pytest.raises(ValueError, match="one process tree per scenario worker"):
        other.check_workers(cfg)


def test_a_system_override_may_not_swap_the_engine() -> None:
    spec = spec_mod.load(SCENARIO)
    with pytest.raises(ValueError, match="not an override the emulator applies"):
        spec_mod.EmuScenario.model_validate(spec.model_dump() | {"systems": {"voss": ["system=reference_cloud"]}})


def test_the_layout_the_scenario_asks_for_fits_node02() -> None:
    """Six workers on six P-cores and two provider cores; 8 P-cores (16 threads) is the node02 shape."""
    spec = spec_mod.load(SCENARIO)
    cpus = [Cpu(2 * i, i, 0, KIND_PERFORMANCE) for i in range(8)] + [
        Cpu(2 * i + 1, i, 0, KIND_PERFORMANCE) for i in range(8)
    ]
    topo = Topology(tuple(cpus))
    lay = plan(
        topo,
        spec.emu.workers,
        kind="P",
        cores_per_worker=spec.emu.cores_per_worker,
        mem_mb=spec.emu.mem_mb_per_worker,
        infra_cores=spec.emu.infra_cores,
    )
    assert len(lay.slots) == 6 and len(lay.infra) == 2
    assert not set(lay.infra_cpus) & {c for s in lay.slots for c in s.cpus}
