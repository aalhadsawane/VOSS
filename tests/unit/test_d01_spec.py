"""The development main experiment D01 and its first stage D01a (docs/REVISION_PLAN.md V11.1): the grid the plan
states, every provisioning system of ``configs/baselines.yaml`` with its overrides as published, and grid coordinates
in the collected summary."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from experiments.collect import grid_keys, lookup
from experiments.runner import points
from experiments.sweep import plan

REPO = Path(__file__).resolve().parents[2]
PROVISIONING = yaml.safe_load((REPO / "configs/baselines.yaml").read_text())["provisioning"]
SPECS = REPO / "configs" / "experiments"
K_AXIS, UTIL_AXIS = "voss.keys.max_holders", "scenario.load.rate_mult"


def spec(name: str) -> dict[str, Any]:
    out: dict[str, Any] = yaml.safe_load((SPECS / f"{name}.yaml").read_text())
    return out


def test_systems_are_the_published_presets() -> None:
    for name in ("D01", "D01a"):
        s = spec(name)
        assert set(s["systems"]) | set(s.get("left_out", [])) == set(PROVISIONING), name
        for label, ov in s["systems"].items():
            assert ov == PROVISIONING[label]["overrides"], (name, label)


def test_d01_is_the_plan_grid() -> None:
    s = spec("D01")
    assert s["grid"][K_AXIS] == [2, 4, 8, 16, None]
    assert len(s["grid"][UTIL_AXIS]) == 3
    assert s["seeds"] == [1, 2, 3, 4, 5]
    assert len(points(s)) == len(s["systems"]) * 5 * 3 * 5


def test_d01a_is_the_central_cell_of_d01() -> None:
    full, stage = spec("D01"), spec("D01a")
    assert stage["overrides"] == full["overrides"] and stage["systems"] == full["systems"]
    assert dict(stage["grid"]) == {K_AXIS: [8], UTIL_AXIS: [full["grid"][UTIL_AXIS][1]]}
    assert stage["seeds"] == [1]


def test_d01a_runs_are_d01_runs(tmp_path: Path) -> None:
    """Stage 1 is a subset of the full grid: same config hashes, so its runs can be reused, never repeated."""
    stage, _ = plan("D01a", tmp_path)
    full, cfgs = plan("D01", tmp_path, seeds=[1])
    assert {p.config_hash for p in stage} <= {p.config_hash for p in full}
    assert {c.voss.keys.max_holders for c in cfgs} == {2, 4, 8, 16, None}  # null = unbounded K
    assert all(c.calibration and "measured" in c.calibration for c in cfgs)


def test_summary_rows_carry_grid_coordinates() -> None:
    assert grid_keys("D01") == sorted([K_AXIS, UTIL_AXIS])
    assert grid_keys("TOY") == [] and grid_keys("no-such-spec") == []
    cfg = {"voss": {"keys": {"max_holders": None}}, "scenario": {"load": {"rate_mult": 7.0}}}
    assert lookup(cfg, K_AXIS) is None and lookup(cfg, UTIL_AXIS) == 7.0 and lookup(cfg, "a.b") is None


def test_trusted_hosts_run_the_voss_provisioning() -> None:
    """The upper bound is VOSS on trusted hosts (configs/references/trusted_hosts.yaml), not the config default."""
    ov = PROVISIONING["trusted_hosts"]["overrides"]
    assert set(PROVISIONING["voss"]["overrides"]) <= set(ov)
