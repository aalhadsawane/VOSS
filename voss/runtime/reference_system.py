"""Reference-cloud system (doc 02 §9, doc 05 §6 ``system: reference_cloud``): the VOSS engine on an always-on
provider fleet with the reference's own control choices (keep-alive TTL, nearest-region routing, no planning)."""

from __future__ import annotations

from voss.core.config import RunConfig, apply_overrides
from voss.core.registry import register
from voss.runtime.system import RunResult
from voss.runtime.voss_system import VossSystem
from voss.world.reference_cloud import load_reference, reference_scenario
from voss.world.scenario import generate


def reference_config(cfg: RunConfig) -> RunConfig:
    """The run config with the reference profile's overrides applied (deterministic from ``cfg``)."""
    ref = load_reference(cfg.reference)
    tree = cfg.model_dump(mode="json", by_alias=True)
    return RunConfig.model_validate(apply_overrides(tree, list(ref.voss)))


@register("system", "reference_cloud")
def run_reference(cfg: RunConfig) -> RunResult:
    ref = load_reference(cfg.reference)
    run_cfg = reference_config(cfg)
    scn = reference_scenario(generate(cfg), ref, run_cfg.voss.infra.routers)
    return VossSystem(run_cfg, scn).run()
