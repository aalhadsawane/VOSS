"""Single pydantic config tree (doc 05 §6).

A YAML file may say ``extends: <path>`` to deep-merge onto a parent (usually ``configs/base.yaml``). Overrides
``a.b.c=value`` are applied last; values are parsed as YAML scalars.
"""

from __future__ import annotations

import copy
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field

from voss.core.hashing import hash_obj


class Frozen(BaseModel):
    """Base for config sections: immutable, unknown keys rejected."""

    model_config = ConfigDict(extra="forbid", frozen=True)


class DecisionClockConfig(Frozen):
    """Doc 01 §7."""

    mode: Literal["measured", "modeled", "replay"] = "modeled"
    cpu_scale: float = 1.0
    replay_log: str | None = None
    # modeled cost: seconds = a + b * work, per kind. TODO verify: seeds, refit from E02 measured runs.
    coeffs: dict[str, tuple[float, float]] = Field(
        default_factory=lambda: {
            "plan": (0.005, 2e-5),
            "place": (0.0002, 2e-5),
            "route": (0.0001, 1e-5),
            "orchestrate": (0.001, 1e-4),
        }
    )


class ScenarioConfig(Frozen):
    """Exogenous scenario inputs (doc 01 §4, doc 02). World sections stay dicts here and are validated by the
    world models that own them (regime files merged with inline overrides)."""

    workers: int = Field(default=1000, ge=1)
    start_utc_h: float = 0.0
    warmup_s: float = Field(default=172800.0, ge=0)
    substrate_mix: dict[str, float] = Field(default_factory=lambda: {"appliance_tpm": 1.0})
    tiers: dict[str, float] = Field(default_factory=lambda: {"nightly": 0.6, "idle": 0.3, "dedicated": 0.1})
    hw_mix: dict[str, float] = Field(default_factory=lambda: {"C0": 0.1, "C1": 0.35, "C2": 0.35, "C3": 0.2})
    tofu_frac: float = Field(default=0.3, ge=0, le=1)
    regime: str = "churn_med"
    churn: dict[str, Any] = Field(default_factory=dict)
    adversary: dict[str, Any] = Field(default_factory=dict)
    load: dict[str, Any] = Field(default_factory=dict)
    geo: dict[str, Any] = Field(default_factory=dict)
    network: dict[str, Any] = Field(default_factory=dict)
    envelope: dict[str, Any] = Field(default_factory=dict)
    execution: dict[str, Any] = Field(default_factory=dict)
    functions: str = "functions.yaml"
    tenants: str = "tenants.yaml"


class InfraConfig(Frozen):
    """Orchestrator-tier node locations (metro names, doc 08 §2)."""

    orchestrator: str = "Frankfurt"
    verifier: str = "Frankfurt"
    registry: str = "Frankfurt"
    routers: tuple[str, ...] = ("Washington", "Frankfurt", "Singapore")


class RouterConfig(Frozen):
    """Doc 03 §3, doc 07 §2 (dispatch watchdog)."""

    name: str = "single"
    T_dispatch: float = 1.0
    max_resends: int = 3
    give_up_s: dict[str, float] = Field(default_factory=lambda: {"sync": 30.0, "async": 300.0, "filler": 900.0})
    receipt_batch_s: float = 1.0


class PlacerConfig(Frozen):
    """Fast-loop placer names (doc 03 §5.3)."""

    sync: str = "least_loaded"


class SchedulerConfig(Frozen):
    """Scheduler role timers (doc 08 §3.2, §5)."""

    heartbeat_s: float = 2.0
    keepalive_s: float = 1.0
    stale_after_s: float = 7.0
    max_attempts: int = 3
    retry_backoff_s: float = 0.2
    no_candidate_retry_s: float = 0.5
    view_refresh_s: float = 0.25


class WorkerConfig(Frozen):
    """Worker agent knobs (doc 02 §5-6)."""

    warm_ttl_s: float = 600.0
    m_base_mb: float = 512.0
    prebooted_at_start: bool = True
    assurance_tofu_factor: float = 0.9  # f_policy for TOFU firmware (doc 04 §8). tag: assumed


class OrchestratorConfig(Frozen):
    """Doc 03 §2, doc 07 §3 (P2: one cluster; keepalive-based re-appointment)."""

    keepalive_timeout_s: float = 5.0
    check_s: float = 1.0


class CacheConfig(Frozen):
    """Doc 02 §6."""

    value: str = "lru"
    hdd_tier: bool = True
    p2p: bool = False


class VossConfig(Frozen):
    """The ``voss`` section: scheduler-side choices (doc 05 §6). Grows phase by phase."""

    infra: InfraConfig = Field(default_factory=InfraConfig)
    router: RouterConfig = Field(default_factory=RouterConfig)
    placer: PlacerConfig = Field(default_factory=PlacerConfig)
    scheduler: SchedulerConfig = Field(default_factory=SchedulerConfig)
    worker: WorkerConfig = Field(default_factory=WorkerConfig)
    orchestrator: OrchestratorConfig = Field(default_factory=OrchestratorConfig)
    cache: CacheConfig = Field(default_factory=CacheConfig)


class RunConfig(Frozen):
    """Root of the config tree."""

    seed: int = 1
    horizon_s: float = 3600.0
    system: str = "voss"
    scenario: ScenarioConfig = Field(default_factory=ScenarioConfig)
    voss: VossConfig = Field(default_factory=VossConfig)
    drain_s: float = 30.0
    decision_clock: DecisionClockConfig = Field(default_factory=DecisionClockConfig)
    calibration: str | None = None
    out_dir: str = "runs"

    def config_hash(self) -> str:
        return hash_obj(self.model_dump(mode="json", exclude={"out_dir"}))


def deep_merge(base: dict[str, Any], over: dict[str, Any]) -> dict[str, Any]:
    """Recursive dict merge; ``over`` wins; lists and scalars are replaced."""
    out = copy.deepcopy(base)
    for k, v in over.items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = deep_merge(out[k], v)
        else:
            out[k] = copy.deepcopy(v)
    return out


def load_yaml_tree(path: Path) -> dict[str, Any]:
    """Load a YAML file, resolving ``extends`` chains relative to the file."""
    data = yaml.safe_load(path.read_text()) or {}
    if not isinstance(data, dict):
        raise ValueError(f"{path}: top level must be a mapping")
    parent = data.pop("extends", None)
    if parent is None:
        return data
    return deep_merge(load_yaml_tree((path.parent / parent).resolve()), data)


def apply_overrides(tree: dict[str, Any], overrides: list[str]) -> dict[str, Any]:
    """Apply ``a.b=value`` overrides (YAML-parsed values)."""
    out = copy.deepcopy(tree)
    for item in overrides:
        key, _, raw = item.partition("=")
        if not _:
            raise ValueError(f"override '{item}' must be key=value")
        node = out
        parts = key.strip().split(".")
        for p in parts[:-1]:
            node = node.setdefault(p, {})
        node[parts[-1]] = yaml.safe_load(raw)
    return out


def load_config(path: str | Path, overrides: list[str] | None = None) -> RunConfig:
    tree = apply_overrides(load_yaml_tree(Path(path)), overrides or [])
    return RunConfig.model_validate(tree)
