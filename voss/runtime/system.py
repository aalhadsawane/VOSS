"""Builds and runs a registered system for a config (doc 01 §8 entrypoints)."""

from __future__ import annotations

from dataclasses import dataclass

from voss.core.config import RunConfig
from voss.core.registry import create
from voss.metrics.recorder import Recorder


@dataclass
class RunResult:
    recorder: Recorder
    scenario_hash: str | None
    events_run: int


def run_system(cfg: RunConfig) -> RunResult:
    """Run ``cfg.system`` (a registered ``system`` factory taking the config) to the horizon."""
    _import_systems()
    result: RunResult = create("system", cfg.system, cfg)
    return result


def _import_systems() -> None:
    """Import modules whose ``@register("system", ...)`` decorators must run."""
    import voss.runtime.toy  # noqa: PLC0415
    import voss.runtime.voss_system  # noqa: F401, PLC0415
