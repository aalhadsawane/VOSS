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
            "plan": (0.02, 5e-5),
            "place": (0.0002, 2e-5),
            "route": (0.0001, 1e-5),
            "orchestrate": (0.001, 1e-4),
            "verify": (0.0, 5e-5),  # receipt signature check per row (Ed25519 ~50 µs)  # TODO verify
            "settle": (0.01, 2e-6),
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
    faults: list[dict[str, Any]] = Field(default_factory=list)  # control-plane faults (doc 07 §5, E15)


class InfraConfig(Frozen):
    """Orchestrator-tier node locations (metro names, doc 08 §2)."""

    orchestrator: str = "Frankfurt"
    verifier: str = "Frankfurt"
    registry: str = "Frankfurt"
    routers: tuple[str, ...] = ("Washington", "Frankfurt", "Singapore")


class RouterConfig(Frozen):
    """Doc 03 §3, doc 07 §2 (dispatch watchdog, spillover)."""

    name: str = "score"
    cold_penalty_s: float = 3.0  # prior price of a trust-cold start until a cluster measured one  # TODO verify
    exposure_s: float = 0.5  # exposure increment of a trust-cold spill (seconds-equivalent)
    health_s: float = 5.0  # seconds per unit of router-observed SLO miss rate
    cold_fn_s: float = 0.5  # prior price of a cold function start until measured  # TODO verify
    T_dispatch: float = 1.0
    T_spill: float = 1.5
    stats_s: float = 5.0
    max_resends: int = 3
    give_up_s: dict[str, float] = Field(default_factory=lambda: {"sync": 30.0, "async": 300.0, "filler": 900.0})
    receipt_batch_s: float = 1.0


class PlacerConfig(Frozen):
    """Fast-loop placers (doc 03 §5.3): ``sync`` per invocation, ``async`` per window (async and filler)."""

    sync: str = "greedy"
    async_: str = Field(default="flow", alias="async")
    K: int = 12
    window_s: float = 0.2
    slots_per_worker: int = 4

    model_config = ConfigDict(extra="forbid", frozen=True, populate_by_name=True)


class PredictorConfig(Frozen):
    """Doc 03 §6.1."""

    name: str = "blr"
    forgetting: float = 0.995
    conformal: bool = True


class CostConfig(Frozen):
    """Doc 03 §5.2, D-12. ``sigma``: weight per tenant sensitivity class (doc 04 §8). tag: assumed."""

    scalarizer: str = "slo_miss"
    eps: float = 0.05
    lambda_exposure: float = 1.0
    sync_weight: float = 1.0
    sigma: dict[str, float] = Field(default_factory=lambda: {"low": 0.1, "medium": 1.0, "high": 3.0})


class HedgeConfig(Frozen):
    """Doc 03 §5.4, doc 07 §6."""

    name: str = "risk_proportional"
    theta: float = 0.2
    budget: float = 0.1


class AdmissionConfig(Frozen):
    enabled: bool = True
    eps: float = 0.05
    filler_headroom: int = 1
    defer_s: float = 1.0


class PlannerConfig(Frozen):
    """Slow loop (doc 03 §4, doc 05 §6). Objective weights are in ``params`` (``policy.plan.types.PlanParams``)."""

    name: str = "milp"
    T_plan: float = 30.0
    T_solve: float = 2.0
    node_limit: int = 50
    max_plan_workers: int = 40
    replan_tolerance: float = 0.2
    hot_top_k: int = 20
    hot_fn_k: int = 50
    min_rate: float = 0.01
    f_from_alpha: float = 0.1
    horizon_factor: float = 2.0
    cold_penalty: float = 10.0
    max_parallel_prepares: int = 2
    T_linger: float = 30.0
    params: dict[str, Any] = Field(default_factory=dict)


class ModelsConfig(Frozen):
    """Survival and omission models (doc 03 §6.3-6.4)."""

    survival: str = "weibull"
    omission: str = "beta_cusum"
    refit_s: float = 60.0
    cusum_h: float = 5.0


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
    """Doc 03 §2, doc 07 §3."""

    keepalive_timeout_s: float = 5.0
    check_s: float = 1.0
    summaries_s: float = 1.0


class ClustersConfig(Frozen):
    """Cluster arrangement (doc 03 §2). ``mode``: ``dynamic`` (triggers on), ``static_kmeans`` (formed once),
    ``static_regions`` (one cluster per world region), ``none_global`` (a single cluster)."""

    mode: str = "dynamic"
    target_size: int = 30
    min_size: int = 10
    max_size: int = 60
    d_min: int = 3
    dwell_s: float = 600.0
    max_moves: int = 10
    period_s: float = 30.0
    bootstrap_s: float = 3.0
    slo_theta: float = 0.2
    slo_periods: int = 3
    imbalance_delta: float = 0.4
    max_moves_per_h: int = 3


class CacheConfig(Frozen):
    """Doc 02 §6."""

    value: str = "gdsf"
    hdd_tier: bool = True
    p2p: bool = True
    max_sources: int = 3


class DetectionConfig(Frozen):
    """Progress-based detection (doc 07 §2, §6). ``mode``: ``progress`` or ``heartbeat_only`` (ablation)."""

    mode: str = "progress"
    watchdog_slack: float = 1.2  # result watchdog at predicted q90 × slack (doc 07 §6: q90 + 20%)
    watchdog_min_s: float = 3.0
    probe_timeout_s: float = 2.0
    stall_n: int = 3  # dispatch-watchdog fires per cluster ...
    stall_window_s: float = 5.0  # ... within this window → STALL
    suspect_streak: int = 2  # watchdog failures in a row → suspected
    suspect_s: float = 600.0  # suspicion lasts this long (then probation)
    T_decide_max: float = 0.2
    decide_periods: int = 3


class SuccessionConfig(Frozen):
    """Scheduler succession (doc 07 §3, §6)."""

    T_ckpt: float = 30.0
    lease_s: float = 5.0
    standbys: int = 1
    handover_wait_s: float = 1.0
    retain_outcomes: int = 64


class AccountingConfig(Frozen):
    """Receipts and credits (doc 09 §3-4). tag: assumed."""

    settle_s: float = 60.0
    late_factor: float = 0.5  # timeliness multiplier for results past their deadline
    cache_per_gb_h: float = 0.1  # credit per pinned GB-hour of warm state
    sched_per_assign: float = 0.01
    sched_per_h: float = 1.0
    standby_per_h: float = 0.25
    report_s: float = 5.0


class ReputationConfig(Frozen):
    """Doc 09 §2. Reputation feeds rewards and planner tie-breaks only, never ``pFail``. Weights tag: assumed."""

    name: str = "beta_decay"
    half_life_h: float = 168.0
    prior: tuple[float, float] = (1.0, 2.0)  # pessimistic
    quantile: float = 0.05  # score = lower credible bound
    probation_h: float = 24.0
    explore_floor: float = 0.3  # newcomers' tie-break score floor (exploration quota ε)
    share_cap: float = 0.05  # no tie-break bonus above this share of settled work (concentration guard)
    tie_break: float = 0.02
    push_s: float = 30.0
    commit_s: dict[str, float] = Field(default_factory=lambda: {"dedicated": 86400.0, "nightly": 14400.0})
    breach_w: dict[str, float] = Field(default_factory=lambda: {"dedicated": 3.0, "nightly": 1.0})
    honor_w: float = 1.0
    result_w: float = 0.1  # α per reference work unit delivered on time
    late_w: float = 0.05  # β per reference work unit delivered late (envelope shortfall)
    change_point_w: float = 2.0
    suspect_w: float = 1.0


class VossConfig(Frozen):
    """The ``voss`` section: scheduler-side choices (doc 05 §6). Grows phase by phase."""

    infra: InfraConfig = Field(default_factory=InfraConfig)
    router: RouterConfig = Field(default_factory=RouterConfig)
    placer: PlacerConfig = Field(default_factory=PlacerConfig)
    predictor: PredictorConfig = Field(default_factory=PredictorConfig)
    cost: CostConfig = Field(default_factory=CostConfig)
    hedge: HedgeConfig = Field(default_factory=HedgeConfig)
    admission: AdmissionConfig = Field(default_factory=AdmissionConfig)
    models: ModelsConfig = Field(default_factory=ModelsConfig)
    planner: PlannerConfig = Field(default_factory=PlannerConfig)
    scheduler: SchedulerConfig = Field(default_factory=SchedulerConfig)
    worker: WorkerConfig = Field(default_factory=WorkerConfig)
    orchestrator: OrchestratorConfig = Field(default_factory=OrchestratorConfig)
    clusters: ClustersConfig = Field(default_factory=ClustersConfig)
    cache: CacheConfig = Field(default_factory=CacheConfig)
    detection: DetectionConfig = Field(default_factory=DetectionConfig)
    succession: SuccessionConfig = Field(default_factory=SuccessionConfig)
    accounting: AccountingConfig = Field(default_factory=AccountingConfig)
    reputation: ReputationConfig = Field(default_factory=ReputationConfig)


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
    label: str = ""

    def config_hash(self) -> str:
        return hash_obj(self.model_dump(mode="json", exclude={"out_dir", "label"}))


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
