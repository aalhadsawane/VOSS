"""Shared plan finish and constraint checks (doc 03 §4.2; D-131).

Every planner's plan is truncated to the holder budget and logged with the same terms: the uncovered demand and the
counts of holders, warm sandboxes and snapshots. The v1 weighted objective (donor cost, churn, warm benefit, exposure)
is deleted; the hetero planner's own on-time rate is its objective.
"""

from __future__ import annotations

import numpy as np

from voss.core.detmath import dot
from voss.policy.keys.budget import truncate
from voss.policy.plan.types import Plan, PlanInput


def shortfall(inp: PlanInput, c: np.ndarray) -> np.ndarray:
    """``u_t``: uncovered demand, ``max(0, q_t − Σ_j c_tj · S_j(H)(1 − p_j))``."""
    e = inp.contrib()
    out = np.empty(len(inp.tenants))
    for t in range(len(inp.tenants)):
        out[t] = max(0.0, float(inp.q[t]) - dot(c[t], e))
    return out


def terms(inp: PlanInput, y: np.ndarray, s: np.ndarray, w: np.ndarray, c: np.ndarray) -> dict[str, float]:
    u = shortfall(inp, c)
    return {
        "shortfall": float(u.sum()),
        "holders": float(y.sum()),
        "warm": float(w.sum()),
        "snapshots": float(s.sum()),
    }


def finish(
    inp: PlanInput, y: np.ndarray, s: np.ndarray, w: np.ndarray, c: np.ndarray, planner: str, status: str = "ok"
) -> Plan:
    if inp.max_holders is not None:  # the holder budget binds every provisioning policy (D-85, G2)
        y = truncate(y, c, inp.y_prev, inp.max_holders)
        c = c * y
        keep = y[inp.fn_tenant] if len(inp.fn_tenant) else np.zeros_like(w, dtype=bool)
        s, w = s & keep, w * keep
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
        -tm["shortfall"],
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
    if ((inp.fn_mem[:, None] * plan.w).sum(axis=0) > inp.mem_mb - inp.m_base_mb + tol).any():
        out.append("memory")
    if ((inp.fn_size[:, None] * plan.s).sum(axis=0) > inp.ssd_mb + tol).any():
        out.append("ssd")
    if (plan.s.sum(axis=1) > inp.fn_snaps + tol).any() or (plan.w.sum(axis=1) > inp.fn_units + tol).any():
        out.append("demand bounds")
    if (plan.y & ~inp.allowed()).any():
        out.append("freshness")
    return out
