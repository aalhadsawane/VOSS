"""Emulation scenario: the one file the emulator and the simulator both run (plan V13, handoff Part E).

``configs/emu/<name>.yaml`` names a simulator config tree, the overrides that turn it into the validation scenario,
the compared systems (each with its own overrides, as ``configs/baselines.yaml`` gives them), the repetitions and the
emulated host layout. ``tools.emu.run --system S --rep i`` resolves it to a :class:`~voss.core.config.RunConfig`;
``sim_spec`` turns the same file into an ``experiments.runner`` spec, so the builder's simulator runs use the same
scenario, the same systems, the same seeds and therefore the same scenario hash. Comparing the two is then a
comparison of the two execution paths, not of two scenarios.

Nothing here is imported by ``voss/``: the emulator is a backend swap around the simulator's own actors.
"""

from __future__ import annotations

from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator
from voss.core.config import RunConfig, apply_overrides, load_yaml_tree
from voss.core.paths import REPO_ROOT

from tools.emu.topology import KINDS

EMU_DIR = REPO_ROOT / "configs" / "emu"
CLOCK_MEASURED = ["decision_clock.mode=measured", "decision_clock.cpu_scale=0.0"]
CLOCK_MODELED = ["decision_clock.mode=modeled"]


class EmuHost(BaseModel):
    """The emulated host: how many workers, on which cores, with how much memory and which assets."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    workers: int = Field(default=6, ge=1, le=10)  # handoff Part E: 6-10 emulated workers on one machine
    kind: str = "P"  # one kind only on a hybrid CPU (handoff Part E)
    cores_per_worker: int = Field(default=1, ge=1)
    infra_cores: int = Field(default=2, ge=1)  # provider roles and the coordinator, never on a worker's core
    mem_mb_per_worker: int = Field(default=4096, ge=512)  # cgroup memory.max of one worker's process tree
    assets: str = "~/voss-calib/assets"  # firecracker, vmlinux, voss-guest.ext4 (handoff Part B setup)
    rootfs: str = "voss-guest.ext4"
    workdir: str = "/var/tmp/voss-emu"  # snapshots and scratch: the storage tier under test
    tpm: bool = True  # a real tpm2_quote at every session start (handoff Part E)

    @model_validator(mode="after")
    def _kind(self) -> EmuHost:
        if self.kind not in KINDS:
            raise ValueError(f"emu.kind must be one of {sorted(KINDS)}, got {self.kind!r}")
        return self


class EmuScenario(BaseModel):
    """``configs/emu/<name>.yaml``."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    name: str
    description: str = ""
    source: str = ""  # the file this was loaded from (set by load, not in the YAML)
    config: str = "../machines.yaml"  # a RunConfig tree, relative to this file
    overrides: list[str] = Field(default_factory=list)  # applied to the simulator config, in order
    systems: dict[str, list[str]]  # system label -> its own overrides (paired runs, doc 06 §4)
    seeds: list[int] = Field(default_factory=lambda: [1, 2, 3])  # rep i runs seeds[i - 1]
    emu: EmuHost = Field(default_factory=EmuHost)
    provenance: dict[str, str] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _checks(self) -> EmuScenario:
        if not self.systems:
            raise ValueError("systems: at least one compared system")
        if not self.seeds:
            raise ValueError("seeds: at least one repetition")
        for label, ov in self.systems.items():
            bad = [o for o in ov if o.split("=", 1)[0] == "system"]
            if bad:  # every system here is the VOSS engine; the label carries the difference
                raise ValueError(f"system {label!r}: {bad[0]!r} is not an override the emulator applies")
        return self

    # --- resolution --------------------------------------------------------------------------------------------
    def config_tree(self) -> dict[str, object]:
        return load_yaml_tree(Path(self.config))

    def run_config(self, system: str, rep: int, extra: list[str] | None = None) -> RunConfig:
        """The config of repetition ``rep`` of ``system``: scenario overrides, the system's own, then the seed.

        The emulator charges decision time from the wall clock (``measured``, scale 0): the policy code runs for real,
        so its cost is already in the timeline (doc 10 §4).
        """
        ov = self.overrides_for(system, rep, extra, measured=True)
        return RunConfig.model_validate(apply_overrides(self.config_tree(), ov))

    def overrides_for(
        self, system: str, rep: int, extra: list[str] | None = None, *, measured: bool = True
    ) -> list[str]:
        if system not in self.systems:
            raise KeyError(f"system {system!r} is not in {self.name} ({sorted(self.systems)})")
        if not 1 <= rep <= len(self.seeds):
            raise ValueError(f"rep must be 1..{len(self.seeds)}, got {rep}")
        clock = CLOCK_MEASURED if measured else CLOCK_MODELED
        return [
            *self.overrides,
            *self.systems[system],
            *clock,
            f"seed={self.seeds[rep - 1]}",
            f"label={system}",
            *(extra or []),
        ]

    def sim_overrides(self, system: str, rep: int, extra: list[str] | None = None) -> list[str]:
        """The same run in the simulator: the modeled decision clock (V10 coefficients) is the only difference."""
        return self.overrides_for(system, rep, extra, measured=False)

    def check_workers(self, cfg: RunConfig) -> None:
        """The emulator must emulate exactly the workers the scenario has (one namespace and core set each)."""
        if cfg.scenario.workers != self.emu.workers:
            raise ValueError(
                f"{self.name}: scenario.workers={cfg.scenario.workers} but emu.workers={self.emu.workers}; "
                f"the emulator runs one process tree per scenario worker, so the two must be equal"
            )

    def sim_spec(self) -> dict[str, object]:
        """An ``experiments.runner`` spec that reproduces the simulator side of every repetition."""
        return {
            "experiment": f"emu-{self.name}",
            "base": str(Path(self.config).resolve()),
            "overrides": [*self.overrides, *CLOCK_MODELED],
            "systems": self.systems,
            "seeds": self.seeds,
            "note": f"simulator side of the emulation scenario {self.name} (plan V13); do not edit",
        }

    def run_dir(self, system: str, rep: int) -> str:
        """Relative run directory under the emulator's output root (data contract §7)."""
        return f"{system}/rep{rep}"


def resolve(name_or_path: str) -> Path:
    """``configs/emu/<name>.yaml`` from a scenario name or a path."""
    p = Path(name_or_path)
    if p.suffix == ".yaml":
        for cand in (p, REPO_ROOT / p):
            if cand.exists():
                return cand.resolve()
        raise FileNotFoundError(f"no scenario file {name_or_path}")
    return EMU_DIR / f"{name_or_path}.yaml"


def load(name_or_path: str) -> EmuScenario:
    """Load a scenario file; ``config`` becomes absolute so the tree resolves the same from any directory."""
    path = resolve(name_or_path)
    data = yaml.safe_load(path.read_text()) or {}
    if not isinstance(data, dict):
        raise ValueError(f"{path}: top level must be a mapping")
    data.setdefault("name", path.stem)
    data["source"] = str(path)
    data["config"] = str((path.parent / str(data.get("config", "../machines.yaml"))).resolve())
    return EmuScenario.model_validate(data)
