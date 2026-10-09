"""Shared plan objective (doc 03 §4.2): every planner's plan is scored by the same function, term by term, so the
MILP can be compared with greedy and baselines (and terms logged for Pareto analysis, doc 06 §2)."""

from __future__ import annotations

import numpy as np

from voss.policy.plan.types import Plan, PlanInput


def top_f(c: np.ndarray, f: int) -> float:
    """Sum of the ``f`` largest entries (the capacity a worst-case set of ``f`` defectors removes)."""
    return float(np.sort(c)[::-1][:f].sum()) if f > 0 else 0.0


def shortfall(inp: PlanInput, c: np.ndarray) -> np.ndarray:
    """``u_t``: uncovered demand under the robust coverage rule."""
    e = inp.contrib()
    out = np.empty(len(inp.tenants))
    for t in range(len(inp.tenants)):
        cov = float(c[t] @ e) - (top_f(c[t], int(inp.f[t])) if inp.params.use_robust else 0.0)
        out[t] = max(0.0, float(inp.q[t]) - cov)
    return out


def terms(inp: PlanInput, y: np.ndarray, s: np.ndarray, w: np.ndarray, c: np.ndarray) -> dict[str, float]:
    p = inp.params
    u = shortfall(inp, c)
    exposure = float(((inp.sigma[:, None] * (1 - inp.assurance[None, :])) * y).sum()) if p.use_exposure else 0.0
    exposure *= p.exposure_weight
    return {
        "coverage": float(inp.cold_penalty @ u),
        "donor": float(p.rho_mem * (inp.fn_mem[:, None] * w).sum() + p.rho_ssd * (inp.fn_size[:, None] * s).sum()),
        "exposure": exposure,
        "churn": float(p.kappa_switch * np.maximum(0, y.astype(int) - inp.y_prev.astype(int)).sum()),
        "warm": float(-p.beta_warm * (inp.fn_benefit[:, None] * (w + p.gamma * s)).sum()),
        "shortfall": float(u.sum()),
    }


def objective(t: dict[str, float]) -> float:
    return t["coverage"] + t["donor"] + t["exposure"] + t["churn"] + t["warm"]


def finish(
    inp: PlanInput, y: np.ndarray, s: np.ndarray, w: np.ndarray, c: np.ndarray, planner: str, status: str = "ok"
) -> Plan:
    tm = terms(inp, y, s, w, c)
    return Plan(
        inp.tenants,
        inp.fns,
        inp.workers,
        y.astype(bool),
        s.astype(bool),
        w.astype(int),
        c,
        inp.now + inp.horizon_s,
        tm,
        status,
        objective(tm),
        planner,
    )


def feasible(inp: PlanInput, plan: Plan, tol: float = 1e-6) -> list[str]:
    """Constraint violations of doc 03 §4.2 (empty when the plan is feasible)."""
    p, out = inp.params, []
    tf = inp.fn_tenant
    if (plan.c > inp.cap[None, :] * plan.y + tol).any():
        out.append("c > cap·y")
    if (plan.c.sum(axis=0) > inp.cap + tol).any():
        out.append("slots")
    if (plan.w > p.w_max * plan.y[tf]).any() or (plan.s & ~plan.y[tf]).any():
        out.append("coupling")
    if ((inp.fn_mem[:, None] * plan.w).sum(axis=0) > inp.mem_mb - p.m_base_mb + tol).any():
        out.append("memory")
    if ((inp.fn_size[:, None] * plan.s).sum(axis=0) > inp.ssd_mb + tol).any():
        out.append("ssd")
    if (plan.s.sum(axis=1) > inp.fn_snaps + tol).any() or (plan.w.sum(axis=1) > inp.fn_units + tol).any():
        out.append("demand bounds")
    if (plan.y & ~inp.allowed()).any():
        out.append("assurance/freshness")
    if p.use_domain_cap:
        for d in np.unique(inp.domain):
            m = inp.domain == d
            if (plan.c[:, m].sum(axis=1) > p.kappa_dom * plan.c.sum(axis=1) + tol).any():
                out.append(f"domain {d}")
    return out
