"""Planner inputs and plans (doc 03 §4.1-4.2, doc 05 §3).

Arrays are indexed by hot tenants ``T``, hot functions ``F`` and attested workers ``J`` of one cluster. All inputs
are estimates from the scheduler's view (no ground truth).
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from voss.core.ids import FnId, TenantId, WorkerId


@dataclass(frozen=True)
class PlanParams:
    """Objective weights and structural limits (doc 03 §4.2). tag: assumed; swept by E04/E23."""

    rho_mem: float = 1e-4  # per MB of warm-VM memory
    rho_ssd: float = 2e-5  # per MB of pinned snapshot
    kappa_switch: float = 0.05
    beta_warm: float = 0.05
    gamma: float = 0.5  # a pinned snapshot is worth γ of a warm VM
    kappa_dom: float = 0.5  # max share of a tenant's earmarked capacity in one failure domain
    w_max: int = 4
    m_base_mb: float = 512.0
    use_robust: bool = True
    use_exposure: bool = True
    use_domain_cap: bool = True
    use_freshness: bool = True
    exposure_weight: float = 1.0
    tie_break: float = 0.0  # reputation tie-break strength (doc 09 §1: tie-breaks only)


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
    assurance: np.ndarray  # [J]
    domain: np.ndarray  # [J]
    fresh_ok: np.ndarray  # [J] attestation valid through the horizon (or a re-quote fits)
    tenants: tuple[TenantId, ...]
    q: np.ndarray  # [T] required concurrent capacity quantile
    rate: np.ndarray  # [T] arrival rate (orders the greedy planner)
    sigma: np.ndarray  # [T] sensitivity weight
    a_min: np.ndarray  # [T] assurance floor
    f: np.ndarray  # [T] robustness level (workers that may defect)
    cold_penalty: np.ndarray  # [T] cost per unit of uncovered demand
    fns: tuple[FnId, ...]
    fn_tenant: np.ndarray  # [F] index into tenants
    fn_mem: np.ndarray  # [F] MB per warm VM
    fn_size: np.ndarray  # [F] snapshot MB
    fn_benefit: np.ndarray  # [F] start-up seconds saved × expected hits in the horizon (per warm unit)
    fn_units: np.ndarray  # [F] warm VMs worth keeping cluster-wide (demand bound)
    y_prev: np.ndarray  # [T, J] previous trust-warm sets
    params: PlanParams = field(default_factory=PlanParams)
    rep: np.ndarray | None = None  # [J] reputation tie-break scores in [0, 1] (doc 09 §2)

    def preference(self) -> np.ndarray:
        """``[J]`` tie-break multiplier ``1 + tie_break × score`` (1 without reputation)."""
        if self.rep is None or self.params.tie_break == 0:
            return np.ones(len(self.workers))
        out: np.ndarray = 1.0 + self.params.tie_break * self.rep
        return out

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
        """``[T, J]`` assurance floor and freshness (``y`` forced to 0 elsewhere)."""
        ok = self.assurance[None, :] >= self.a_min[:, None]
        if self.params.use_freshness:
            ok &= self.fresh_ok[None, :]
        out: np.ndarray = ok
        return out


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

    def robust_slack(self, inp: PlanInput) -> np.ndarray:
        """``[T]`` coverage minus the ``f_t`` largest contributions minus ``q_t`` (≥ 0 means robust)."""
        eff = self.c * inp.contrib()[None, :]
        out = np.empty(len(self.tenants))
        for t in range(len(self.tenants)):
            k = int(inp.f[t])
            top = np.sort(self.c[t])[::-1][:k].sum() if k > 0 else 0.0
            out[t] = eff[t].sum() - top - inp.q[t]
        return out
