"""Greedy trust & warm-state planner (doc 03 §4.3): baseline and MILP fallback.

For each hot tenant in decreasing ``λ_t × ColdPenalty_t``: add the worker with the best
``S_j(1−p_j)·a_j / (memory cost + σ_t(1−a_j))`` (assurance floor, freshness, domain cap) until coverage with the
``f_t`` largest contributions removed reaches ``q_t``; then add warm VMs and snapshots by value density until the
budgets bind.
"""

from __future__ import annotations

import numpy as np

from voss.core.registry import register
from voss.policy.plan.objective import finish, shortfall
from voss.policy.plan.types import Plan, PlanInput


def _fill(inp: PlanInput, t: int, y: np.ndarray, c: np.ndarray, free: np.ndarray, base: np.ndarray) -> None:
    """Add workers (best score, preferring under-represented domains) until robust coverage holds."""
    e = inp.contrib()
    allowed = inp.allowed()[t]
    cap_c = np.minimum(inp.cap, inp.q[t] / np.maximum(e, 1e-6))
    chunk = _chunk(inp, t, allowed & (free > 1e-9))
    while (short := shortfall(inp, c)[t]) > 1e-9:
        total = max(c[t].sum(), 1e-9)
        share = np.array([c[t][inp.domain == d].sum() for d in inp.domain]) / total
        score = np.where(allowed & (free > 1e-9) & ~y[t], base / (1.0 + 4.0 * share), -np.inf)
        j = int(np.argmax(score))
        if not np.isfinite(score[j]):
            return
        add = min(free[j], cap_c[j], max(chunk, short / max(e[j], 1e-6) / (int(inp.f[t]) + 1)))
        y[t, j], c[t, j] = True, add
        free[j] -= add


def _chunk(inp: PlanInput, t: int, avail: np.ndarray) -> float:
    """Even spread: capacity per worker such that removing the ``f_t`` largest still leaves ``q_t`` (doc 03 §4.3)."""
    e = inp.contrib()[avail]
    if not len(e):
        return 1.0
    f, q = int(inp.f[t]), float(inp.q[t])
    n = int(min(len(e), max(f + 2, np.ceil(2 * q / max(float(e.mean() * inp.cap[avail].mean()), 1e-6)) + f)))
    return max(0.5, q / (float(e.mean()) * max(1, n - f)))


def _trust_sets(inp: PlanInput, y: np.ndarray, c: np.ndarray) -> None:
    e = inp.contrib()
    free = inp.cap.astype(float).copy()
    for t in np.argsort(-(inp.rate * inp.cold_penalty), kind="stable"):
        fns = inp.fn_tenant == t
        mem_cost = inp.params.rho_mem * float(inp.fn_mem[fns].mean()) if fns.any() else 0.0
        exposure = inp.params.exposure_weight * inp.sigma[t] * (1 - inp.assurance) if inp.params.use_exposure else 0.0
        base = e * inp.assurance / (mem_cost + exposure + 1e-6)
        for _ in range(4):  # fill, cap domains, refill what the cap removed
            _fill(inp, t, y, c, free, base)
            before = c[t].copy()
            _enforce_domain_cap(inp, c[t])
            free += before - c[t]
            if shortfall(inp, c)[t] <= 1e-9:
                break
        y[t] &= c[t] > 1e-9
        c[t] *= y[t]


def _enforce_domain_cap(inp: PlanInput, c_t: np.ndarray) -> None:
    """Scale down over-represented domains until every domain holds at most ``κ_dom`` of the tenant's capacity."""
    if not inp.params.use_domain_cap:
        return
    for _ in range(50):
        total = c_t.sum()
        over = [d for d in np.unique(inp.domain) if c_t[inp.domain == d].sum() > inp.params.kappa_dom * total + 1e-9]
        if not over or total <= 0:
            return
        for d in over:
            m = inp.domain == d
            rest = total - c_t[m].sum()
            target = inp.params.kappa_dom / (1 - inp.params.kappa_dom) * rest if inp.params.kappa_dom < 1 else total
            c_t[m] *= target / c_t[m].sum()


def _warm_state(inp: PlanInput, y: np.ndarray, s: np.ndarray, w: np.ndarray) -> None:
    p = inp.params
    mem = np.maximum(0.0, inp.mem_mb - p.m_base_mb)
    ssd = inp.ssd_mb.astype(float).copy()
    units = inp.fn_units.astype(float).copy()
    for f in np.argsort(-(inp.fn_benefit / np.maximum(inp.fn_mem, 1.0)), kind="stable"):
        if p.beta_warm * inp.fn_benefit[f] <= p.rho_mem * inp.fn_mem[f]:
            continue
        for j in np.flatnonzero(y[inp.fn_tenant[f]]):
            while units[f] >= 1 and w[f, j] < p.w_max and mem[j] >= inp.fn_mem[f]:
                w[f, j] += 1
                mem[j] -= inp.fn_mem[f]
                units[f] -= 1
    snaps = inp.fn_snaps.astype(float).copy()
    for f in np.argsort(-(inp.fn_benefit / np.maximum(inp.fn_size, 1.0)), kind="stable"):
        if p.beta_warm * p.gamma * inp.fn_benefit[f] <= p.rho_ssd * inp.fn_size[f]:
            continue
        for j in np.flatnonzero(y[inp.fn_tenant[f]]):
            if ssd[j] >= inp.fn_size[f] and snaps[f] >= 1:
                snaps[f] -= 1
                s[f, j] = True
                ssd[j] -= inp.fn_size[f]


@register("planner", "greedy")
class GreedyPlanner:
    def plan(self, inp: PlanInput) -> Plan:
        t, f, j = inp.shape
        y, c = np.zeros((t, j), bool), np.zeros((t, j))
        s, w = np.zeros((f, j), bool), np.zeros((f, j), int)
        if t and j:
            _trust_sets(inp, y, c)
            _warm_state(inp, y, s, w)
        return finish(inp, y, s, w, c, "greedy")
