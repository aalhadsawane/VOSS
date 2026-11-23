"""The held-out experiments R01-R09 (docs/REVISION_PLAN.md V12.2): the plan's grids, the calibrated fleet, the
held-out split, the header of guardrail 21, systems as published, and shared cells that run once."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import pytest
import yaml
from experiments.runner import points
from experiments.sweep import plan
from voss.core.config import RunConfig
from voss.world.adversary import load_adversary_regime
from voss.world.machines import MachinesParams
from voss.world.sessions import load_session_regime
from voss.world.workload import load_load_regime

REPO = Path(__file__).resolve().parents[2]
SPECS = REPO / "configs" / "experiments"
BASELINES = yaml.safe_load((REPO / "configs/baselines.yaml").read_text())
R = [f"R0{i}" for i in range(1, 10)]
HEADER = ("workers", "load", "utilisation", "duration", "warm-up", "calibration", "trace split", "seeds")
K_AXIS, UTIL_AXIS = "voss.keys.max_holders", "scenario.load.rate_mult"
# Swept (S) constants without an R07 variant, and why (D-129).
R07_EXEMPT = {
    "voss.router.give_up_s": "above every deadline: changes only when a lost invocation is recorded, not whether",
    "voss.router.receipt_batch_s": "receipt batching to the database, off the invocation path",
    "voss.predictor.name": "the estimator is a design choice (plan V5.4); the alternatives are v1 estimators",
    "voss.models.omission": "one registered model; its constants become keys (D-111)",
    "voss.planner.params": "a container; its rows are varied one by one",
    "drain_s": "simulated time after the horizon, outside the measured window",
    "decision_clock.cpu_scale": "emulation only",
    "voss.predictor.prior_sd": "D-122: the run-time priors wash out after a few observations",
    "voss.detection.hedge_min_samples": "D-122: the baseline's warm-up, not a VOSS design constant",
}


def spec(name: str) -> dict[str, Any]:
    out: dict[str, Any] = yaml.safe_load((SPECS / f"{name}.yaml").read_text())
    return out


def hashes(name: str, tmp: Path, label: str | None = None) -> set[str]:
    pts, _ = plan(name, tmp)
    return {p.config_hash for p in pts if label is None or p.label == label}


def s_keys() -> set[str]:
    rows = (REPO / "docs/PARAMETERS.md").read_text().splitlines()
    return {m.group(1) for line in rows if (m := re.match(r"^\| `([^`]+)` \| [^|]+ \| S \|", line))}


@pytest.mark.parametrize("name", R)
def test_header_states_every_field_of_guardrail_21(name: str) -> None:
    head = (SPECS / f"{name}.yaml").read_text().split("\nexperiment:")[0]
    for field in HEADER:
        assert re.search(rf"^#\s+{field}\s", head, re.M), (name, field)
    assert "HELD-OUT SPLIT" in head and "v2-freeze" in head


@pytest.mark.parametrize("name", R)
def test_held_out_fleet_seeds_and_warm_up(name: str, tmp_path: Path) -> None:
    s = spec(name)
    assert s["experiment"] == name and s["base"] == "../base.yaml"
    assert not any(o.startswith("calibration=") for o in s["overrides"]), "the fleet's reference is the calibration"
    assert s["seeds"] == list(range(1, 11)) and "seeds_by_system" not in s
    _, cfgs = plan(name, tmp_path)
    for c in cfgs:
        _check_config(c)


def _check_config(c: RunConfig) -> None:
    sc = c.scenario
    assert c.calibration and "measured" in c.calibration
    fleet = MachinesParams.model_validate(sc.machines)
    assert Path(c.calibration).name in fleet.bundles
    assert load_session_regime(sc).split == "heldout" and load_session_regime(sc).trace == "seti09"
    load = load_load_regime(sc)
    assert load.split == "heldout" and load.trace == "azure2019"
    assert sc.network["link"]["trace"] == "ookla-fixed-2024q1" and sc.geo["pop_trace"] == "wup2025"
    load_adversary_regime(sc)  # every adversary axis is a valid regime
    assert sc.warmup_s >= c.voss.keepalive_hist.range_s  # guardrail 23
    assert c.horizon_s - sc.warmup_s >= 86400.0  # 24 h measured (D-97)


def test_r01_is_the_plan_grid_with_the_published_systems() -> None:
    s = spec("R01")
    prov = BASELINES["provisioning"]
    assert set(s["systems"]) | set(s["left_out"]) == set(prov)
    assert set(s["left_out"]) == {"trusted_hosts"}
    for label, ov in s["systems"].items():
        assert ov == prov[label]["overrides"], label
    assert s["grid"] == {K_AXIS: [2, 4, 8, 16, None], UTIL_AXIS: [2.2, 4.4, 6.3]}
    assert len(points(s)) == 8 * 5 * 3 * 10


@pytest.mark.parametrize(("name", "label"), [("R02", None), ("R06", "voss"), ("R07", "voss"), ("R09", "voss")])
def test_central_cell_runs_are_r01_runs(name: str, label: str | None, tmp_path: Path) -> None:
    """Cells shared with R01 have R01's config hashes, so the held-out sweep runs each of them once."""
    assert hashes(name, tmp_path, label) <= hashes("R01", tmp_path)


def test_r08_smallest_pool_is_r01_central_cell(tmp_path: Path) -> None:
    assert hashes("R08", tmp_path, "w500") <= hashes("R01", tmp_path)
    assert list(spec("R08")["systems"]) == ["w500"]  # larger pools: the decision-timing bench (D-127)


def test_r02_and_r09_are_the_central_cell() -> None:
    r01 = spec("R01")
    assert spec("R02")["systems"] == r01["systems"]
    r09 = spec("R09")["systems"]
    assert r09 == {k: BASELINES["provisioning"][k]["overrides"] for k in ("voss", "trusted_hosts")}
    for name in ("R02", "R04", "R05", "R06", "R07", "R09"):
        assert {f"{K_AXIS}=8", f"{UTIL_AXIS}=4.4"} <= set(spec(name)["overrides"]), name


def test_r03_operating_region() -> None:
    s = spec("R03")
    assert s["grid"] == {
        "scenario.workers": [100, 300, 500],
        UTIL_AXIS: [2.2, 4.4, 6.3],
        "scenario.churn.graceful_frac": [0.0, 0.5],
    }
    assert set(s["systems"]) | set(s["left_out"]) == set(BASELINES["provisioning"])


def test_r04_failure_handling_as_published() -> None:
    s = spec("R04")
    fh = BASELINES["failure_handling"]
    assert s["systems"] == {k: v["overrides"] for k, v in fh.items()}
    assert s["grid"]["scenario.adversary.alpha"] == [0.0, 0.1, 0.2]
    mixes = s["grid"]["scenario.adversary.mix"]
    assert [list(m) for m in mixes] == [["black_hole"], ["omit_random"], ["on_off"], ["throttle"]]


def test_r05_audit_grid_class_p_only() -> None:
    s = spec("R05")
    assert s["grid"] == {
        "scenario.physical_frac": [0.05, 0.2],
        "scenario.adversary.params.forge_p": [0.5, 1.0],
        "voss.audit.p": [0.0, 0.01, 0.05],
    }
    assert list(s["systems"]) == ["voss"]


def test_r06_ablations_change_one_thing() -> None:
    systems = spec("R06")["systems"]
    for label, ov in systems.items():
        assert ov[0] == "voss.planner.name=hetero" and len(ov) == (1 if label == "voss" else 2), label


def test_r07_varies_every_swept_constant() -> None:
    """Every S row of the ledger has an R07 variant (both directions for numbers) or a stated exemption."""
    systems = spec("R07")["systems"]
    varied: dict[str, set[str]] = {}
    for label, ov in systems.items():
        assert ov[0] == "voss.planner.name=hetero" and (len(ov) == 1) == (label == "voss"), label
        for o in ov[1:]:
            key, _, value = o.partition("=")
            varied.setdefault(key, set()).add(value)
    assert sorted(s_keys() - set(varied) - set(R07_EXEMPT)) == []
    assert not set(R07_EXEMPT) & set(varied)
    for label in (lab for lab in systems if lab.endswith("_lo")):  # numbers: a low and a high value of one key
        lo, hi = systems[label][1].partition("=")[0], systems[label[:-3] + "_hi"][1].partition("=")[0]
        assert lo == hi, label
    assert {"voss.keys.rotate_s", "scenario.machines.survey", "scenario.machines.bundles"} <= set(varied)


def test_hypotheses_name_their_experiments() -> None:
    doc = (REPO / "docs/architecture/06-experiments.md").read_text()
    section = doc.split("## 3. v2 hypotheses")[1].split("\n## 4.")[0]
    for h, exp in (("H1", "R01"), ("H2", "R01"), ("H3", "R04"), ("H4", "R05"), ("H5", "R03")):
        row = next(line for line in section.splitlines() if line.startswith(f"| **{h}**"))
        assert exp in row, h
    assert "class P" in section  # guardrail 24
