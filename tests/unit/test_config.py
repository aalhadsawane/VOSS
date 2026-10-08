"""Config loading, inheritance, overrides, registry and decision clock (doc 05 §4, §6; doc 01 §7)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import ValidationError
from voss.core.config import DecisionClockConfig, RunConfig, load_config
from voss.core.decision_clock import DecisionClock
from voss.core.registry import Registry


def test_extends_and_overrides(tmp_path: Path) -> None:
    (tmp_path / "base.yaml").write_text("seed: 1\nhorizon_s: 10\nscenario: {workers: 5, x: {a: 1}}\n")
    (tmp_path / "child.yaml").write_text("extends: base.yaml\nscenario: {x: {b: 2}}\n")
    cfg = load_config(tmp_path / "child.yaml", ["seed=9", "scenario.workers=7"])
    assert cfg.seed == 9
    assert cfg.scenario == {"workers": 7, "x": {"a": 1, "b": 2}}


def test_unknown_keys_rejected() -> None:
    with pytest.raises(ValidationError):
        RunConfig.model_validate({"bogus": 1})


def test_config_hash_stable() -> None:
    assert RunConfig(seed=1).config_hash() == RunConfig(seed=1).config_hash()
    assert RunConfig(seed=1).config_hash() != RunConfig(seed=2).config_hash()


def test_registry() -> None:
    reg = Registry()

    @reg.register("placer", "a")
    def make_a(x: int) -> int:
        return x + 1

    assert reg.create("placer", "a", 1) == 2
    assert reg.names("placer") == ["a"]
    with pytest.raises(KeyError, match="unknown placer 'b'"):
        reg.get("placer", "b")


def test_decision_clock_modes(tmp_path: Path) -> None:
    modeled = DecisionClock(DecisionClockConfig(mode="modeled", coeffs={"place": (0.1, 0.01)}))
    assert modeled.charge("place", work=10, host_speed=2.0) == pytest.approx(0.1)
    measured = DecisionClock(DecisionClockConfig(mode="measured", cpu_scale=2.0))
    assert measured.charge("plan", wall_s=0.5) == pytest.approx(1.0)
    log = tmp_path / "clock.json"
    measured.dump(log)
    assert json.loads(log.read_text()) == [["plan", 1.0]]
    replay = DecisionClock(DecisionClockConfig(mode="replay", replay_log=str(log)))
    assert replay.charge("plan") == pytest.approx(1.0)
    with pytest.raises(RuntimeError):
        replay.charge("plan")
