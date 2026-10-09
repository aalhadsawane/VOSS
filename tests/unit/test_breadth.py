"""P8 building blocks: reference-cloud worlds (doc 02 §9), ablation switches and their expansion (doc 06 §4), the
``instant`` predictor, lifecycle-unaware costs and reputation-in-cost (ablations)."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest
import yaml
from experiments.runner import points, systems
from voss.core.config import load_config
from voss.core.ids import WorkerId
from voss.policy.predict.base import ExecObs, FnPrior
from voss.policy.predict.instant import InstantPredictor
from voss.runtime.reference_system import reference_config
from voss.runtime.schedlib.models import SchedModels
from voss.world.reference_cloud import load_reference, reference_scenario
from voss.world.scenario import generate

REPO = Path(__file__).resolve().parents[2]
SMALL = ["horizon_s=60", "scenario.workers=50", "scenario.load.rate=2"]


@pytest.mark.parametrize("name", ["ref_lambda_like", "ref_azure_like"])
def test_reference_world_is_always_on_and_benign(name: str) -> None:
    cfg = load_config(REPO / "configs/pilot.yaml", [*SMALL, "system=reference_cloud", f"reference={name}"])
    ref = load_reference(name)
    scn0 = generate(cfg)
    run_cfg = reference_config(cfg)
    scn = reference_scenario(scn0, ref, run_cfg.voss.infra.routers)
    n = ref.hosts_per_region * len(run_cfg.voss.infra.routers)
    assert len(scn.workers) == n and set(scn.workers.substrate_names) == {ref.substrate}
    s = scn.sessions.sessions
    assert len(s) == n and (s.start < 0).all() and np.isinf(s.end).all()
    assert (scn.adversary.behavior == 0).all() and scn.control_faults.empty
    assert scn.arrivals is scn0.arrivals and scn.hash != scn0.hash  # same workload, different world
    assert run_cfg.voss.planner.name == "keepalive_ttl" and run_cfg.voss.hedge.name == "off"
    assert ref.pricing.per_m_requests > 0


def test_ablations_expand_into_paired_systems() -> None:
    table = yaml.safe_load((REPO / "configs/ablations.yaml").read_text())
    spec = {"systems": {"voss_full": []}, "ablations": "all", "seeds": [1, 2]}
    assert set(systems(spec)) == {"voss_full", *table}
    pts = points(spec)
    assert len(pts) == 2 * (len(table) + 1)
    assert ["voss.cache.p2p=false", "seed=2", "label=no_p2p"] in pts
    only = points({"systems": {"a": []}, "ablations": ["no_hdd"]})
    assert [p[-1] for p in only] == ["label=a", "label=no_hdd"]


def test_every_ablation_switch_is_a_valid_config() -> None:
    table = yaml.safe_load((REPO / "configs/ablations.yaml").read_text())
    full = load_config(REPO / "configs/pilot.yaml", [])
    for name, ov in sorted(table.items()):
        cfg = load_config(REPO / "configs/pilot.yaml", ov)
        assert cfg.config_hash() != full.config_hash(), name


def test_instant_predictor_is_a_point_estimate_without_speed() -> None:
    p = InstantPredictor({"f": FnPrior(1.0, 1000.0, 0.0)})
    d0 = p.predict("f", 1000, np.array([1, 2]), np.array([1.0, 0.5]), np.zeros(2))
    assert np.allclose(d0.mean(), 1.0, rtol=1e-3)  # prior, no speed scaling
    p.update(ExecObs("f", 1, 1000, 0.5, 0.0, 3.0, 1.0))
    d = p.predict("f", 1000, np.array([1, 2]), np.array([1.0, 0.5]), np.zeros(2))
    assert np.allclose(d.mean(), 3.0, rtol=1e-3) and (d.var() < 1e-4).all()


def test_reputation_in_cost_raises_p_omit_only_when_enabled() -> None:
    cfg = load_config(REPO / "configs/pilot.yaml", ["voss.reputation.in_cost=true"])
    m = SchedModels(cfg.voss, {"f": FnPrior(1.0, 1000.0, 0.0)})
    w = np.array([1, 2])
    base = m.p_omit(w).copy()
    m.rep = {1: 1.0, 2: 0.0}
    got = m.p_omit(w)
    assert got[0] == pytest.approx(base[0]) and got[1] == pytest.approx(1 - (1 - base[1]) * 0.5)
    off = SchedModels(load_config(REPO / "configs/pilot.yaml", []).voss, {"f": FnPrior(1.0, 1000.0, 0.0)})
    off.rep = {int(WorkerId(2)): 0.0}
    assert np.allclose(off.p_omit(w), base)
