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
    e_budget: float = 1.5  # erlang_dpp: default exposure budget Σ_j y_tj (1 − a_j) per tenant and round; assumed
    session_horizons: float = 3.0  # erlang: residence window E[min(L_j, T)] with T this many horizons; assumed


@dataclass(frozen=True)
class LossInputs:
    """Resolved loss-model arrays. ``[F]``: ``rate_f``, ``hold_f``, ``boot_f``, ``restore_f``. ``[T]``: ``load_t``,
    ``delta_t``, ``slots_t`` (integer slots per holder), ``k_t`` (holder limit), ``budget_t``.
    ``[J]``: ``residence``."""

    rate_f: np.ndarray
    hold_f: np.ndarray
    boot_f: np.ndarray
    restore_f: np.ndarray
    load_t: np.ndarray
    delta_t: np.ndarray
    residence: np.ndarray
    slots_t: np.ndarray
    k_t: np.ndarray
    budget_t: np.ndarray


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
    # Loss-model inputs of the Erlang planners (proposal planner-v2 §6); optional, derived when absent.
    fn_rate: np.ndarray | None = None  # [F] arrival rate λ_f (1/s)
    fn_hold: np.ndarray | None = None  # [F] mean slot hold time (s): start-up + execution
    fn_boot: np.ndarray | None = None  # [F] cold start (boot + rootfs + init) seconds
    fn_restore: np.ndarray | None = None  # [F] restore-from-snapshot seconds
    delta_t: np.ndarray | None = None  # [T] slow-path delay Δ_t in seconds (measured trust-cold price)
    tenant_load: np.ndarray | None = None  # [T] offered load a_t = λ_t s_t (slots)
    residence: np.ndarray | None = None  # [J] E[min(L_j, T)] seconds a holder is expected to stay
    holder_slots: np.ndarray | None = None  # [T] integer slots reserved per holder
    holders_k: np.ndarray | None = None  # [T] holder limit k per tenant
    exposure_budget: np.ndarray | None = None  # [T] per-round exposure budget (erlang_dpp)
    measured_exposure: np.ndarray | None = None  # [T] Σ_j (1 − a_j) over workers that really hold the key

    def preference(self) -> np.ndarray:
        """``[J]`` tie-break multiplier ``1 + tie_break × score`` (1 without reputation)."""
        if self.rep is None or self.params.tie_break == 0:
            return np.ones(len(self.workers))
        out: np.ndarray = 1.0 + self.params.tie_break * self.rep
        return out

    def loss_inputs(self) -> LossInputs:
        """Loss-model arrays; where the scheduler gave none they are derived from the older fields."""
        n_f, n_t = len(self.fns), len(self.tenants)
        ft = self.fn_tenant
        per_t = np.bincount(ft, minlength=n_t).clip(min=1) if n_f else np.ones(n_t)
        rate_f = self.fn_rate if self.fn_rate is not None else self.rate[ft] / per_t[ft]
        hold = self.fn_hold if self.fn_hold is not None else np.full(n_f, 0.1)
        boot = self.fn_boot
        if boot is None:  # invert fn_benefit = λ_f H τ_f / units
            units = np.maximum(self.fn_units, 1.0)
            boot = np.where(rate_f > 0, self.fn_benefit * units / np.maximum(rate_f * self.horizon_s, 1e-9), 0.0)
        restore = self.fn_restore if self.fn_restore is not None else (1.0 - self.params.gamma) * boot
        load = self.tenant_load
        if load is None:
            load = np.bincount(ft, weights=rate_f * hold, minlength=n_t) if n_f else np.zeros(n_t)
        delta = self.delta_t
        if delta is None:
            delta = np.bincount(ft, weights=boot, minlength=n_t) / per_t if n_f else np.zeros(n_t)
        return LossInputs(rate_f, hold, boot, restore, load, delta, *self._holder_inputs(load))

    def _holder_inputs(self, load: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
        slots = self.holder_slots if self.holder_slots is not None else np.ceil(load) + 1
        k = self.holders_k if self.holders_k is not None else np.minimum(np.ceil(2 * (self.q + self.f)), 16)
        budget = self.exposure_budget if self.exposure_budget is not None else np.full(len(load), self.params.e_budget)
        return self._residence(), slots.astype(int), np.maximum(k, 1).astype(int), budget

    def _residence(self) -> np.ndarray:
        """``E[min(L_j, T)]``, ``T = session_horizons·H``. Proxy when not supplied: exponential lifetime with the
        hazard implied by ``S_j(H)``, ``(1 − e^{−hT})/h`` (loses the age effect of a Weibull shape below 1)."""
        if self.residence is not None:
            return self.residence
        t_max = self.params.session_horizons * self.horizon_s
        h = -np.log(np.clip(self.survival, 1e-6, 1.0)) / self.horizon_s
        safe = np.where(h < 1e-12, 1.0, h)
        out: np.ndarray = np.where(h < 1e-12, t_max, (1.0 - np.exp(-safe * t_max)) / safe)
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
