"""Planner inputs and plans (doc 03 §4.1, doc 05 §3).

Arrays are indexed by hot tenants ``T``, hot functions ``F`` and attested workers ``J`` of one cluster. All inputs
are estimates from the scheduler's view (no ground truth). The v1 objective weights, robust cover rule and failure-
domain cap are deleted (D-131); ``hetero`` is the only VOSS provisioning planner.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from voss.core.ids import FnId, TenantId, WorkerId
from voss.policy.plan.hetero import HeteroInput


@dataclass(frozen=True)
class PlanParams:
    """Structural limits of a plan (doc 03 §4.2; D-131)."""

    w_max: int = 4  # warm sandboxes per function per worker
    use_freshness: bool = True
    survival_blind: bool = False  # R06 ablation: survival, residence = cluster mean (plan.ablate)


@dataclass(frozen=True)
class PlanInput:
    now: float
    horizon_s: float
    workers: tuple[WorkerId, ...]
    cap: np.ndarray  # [J] slots
    mem_mb: np.ndarray  # [J] memory budget for warm VMs
    ssd_mb: np.ndarray  # [J] SSD budget for pinned snapshots
    survival: np.ndarray  # [J] S_j(H)
    p_omit: np.ndarray  # [J]
    fresh_ok: np.ndarray  # [J] attestation valid through the horizon (or a re-quote fits)
    tenants: tuple[TenantId, ...]
    q: np.ndarray  # [T] required concurrent capacity quantile
    fns: tuple[FnId, ...]
    fn_tenant: np.ndarray  # [F] index into tenants
    fn_rate: np.ndarray  # [F] arrival rate (1/s)
    fn_mem: np.ndarray  # [F] MB per warm VM
    fn_size: np.ndarray  # [F] snapshot MB
    fn_units: np.ndarray  # [F] warm VMs worth keeping cluster-wide (demand bound)
    y_prev: np.ndarray  # [T, J] previous trust-warm sets
    params: PlanParams = field(default_factory=PlanParams)
    m_base_mb: float = 512.0  # image memory reserve, voss.worker.m_base_mb (D-117)
    max_holders: np.ndarray | None = None  # [T] holder budget K per key, 0 = none (D-85); None = no budgets
    fn_inflight: np.ndarray | None = None  # [F] in-flight requests of each function now (kpa baseline)
    hetero: HeteroInput | None = None  # per-worker run times, deadline probabilities, scenarios (§11; hetero planner)

    @property
    def fn_snaps(self) -> np.ndarray:
        """``[F]`` snapshot copies worth pinning cluster-wide: one per warm unit plus one spare (D-30)."""
        out: np.ndarray = self.fn_units + 1.0
        return out

    @property
    def shape(self) -> tuple[int, int, int]:
        return len(self.tenants), len(self.fns), len(self.workers)

    def contrib(self) -> np.ndarray:
        """Expected useful fraction of an earmarked slot: ``S_j(H)·(1 − p_j)``."""
        out: np.ndarray = self.survival * (1 - self.p_omit)
        return out

    def allowed(self) -> np.ndarray:
        """``[T, J]`` freshness (``y`` forced to 0 elsewhere); the v1 trust floor is deleted (D-125)."""
        ok = np.broadcast_to(self.fresh_ok[None, :], (len(self.tenants), len(self.workers))).copy()
        if not self.params.use_freshness:
            ok[:] = True
        return ok


@dataclass(frozen=True)
class Plan:
    tenants: tuple[TenantId, ...]
    fns: tuple[FnId, ...]
    workers: tuple[WorkerId, ...]
    y: np.ndarray  # [T, J] bool
    s: np.ndarray  # [F, J] bool
    w: np.ndarray  # [F, J] int
    c: np.ndarray  # [T, J] float
    valid_until: float
    cost_terms: dict[str, float] = field(default_factory=dict)
    status: str = "ok"
    objective: float = 0.0
    planner: str = ""

    @staticmethod
    def empty(inp: PlanInput, planner: str = "none") -> Plan:
        t, f, j = inp.shape
        return Plan(
            inp.tenants,
            inp.fns,
            inp.workers,
            np.zeros((t, j), bool),
            np.zeros((f, j), bool),
            np.zeros((f, j), int),
            np.zeros((t, j)),
            inp.now + inp.horizon_s,
            planner=planner,
        )
