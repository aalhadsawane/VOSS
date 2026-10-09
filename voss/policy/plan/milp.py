"""Robust MILP planner (doc 03 §4.2, D-10): trust-warm sets, warm units, snapshot pins and earmarked capacity.

The worst case over any ``f_t`` defectors is linearized exactly by LP duality: ``f_t·θ_t + Σ_j π_tj`` equals the sum
of the ``f_t`` largest ``c_tj`` with ``π_tj ≥ c_tj − θ_t, π ≥ 0``. Solved with HiGHS (``scipy.optimize.milp``);
``modeled``/``replay`` runs use a deterministic node limit, ``measured`` runs a wall time limit. On failure the
planner falls back to the greedy plan (doc 03 §4.2).
"""

from __future__ import annotations

import os
import sys
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass

import numpy as np
from scipy.optimize import Bounds, LinearConstraint, milp
from scipy.sparse import coo_matrix

from voss.core.registry import register
from voss.policy.plan.greedy import GreedyPlanner
from voss.policy.plan.objective import finish
from voss.policy.plan.types import Plan, PlanInput


@dataclass(frozen=True)
class Layout:
    """Column offsets of each variable block."""

    T: int
    F: int
    J: int

    def y(self, t: int, j: int) -> int:
        return t * self.J + j

    def s(self, f: int, j: int) -> int:
        return self.T * self.J + f * self.J + j

    def w(self, f: int, j: int) -> int:
        return (self.T + self.F) * self.J + f * self.J + j

    def c(self, t: int, j: int) -> int:
        return (self.T + 2 * self.F) * self.J + t * self.J + j

    def pi(self, t: int, j: int) -> int:
        return (2 * self.T + 2 * self.F) * self.J + t * self.J + j

    def z(self, t: int, j: int) -> int:
        return (3 * self.T + 2 * self.F) * self.J + t * self.J + j

    def u(self, t: int) -> int:
        return (4 * self.T + 2 * self.F) * self.J + t

    def theta(self, t: int) -> int:
        return (4 * self.T + 2 * self.F) * self.J + self.T + t

    @property
    def n(self) -> int:
        return (4 * self.T + 2 * self.F) * self.J + 2 * self.T


class _Rows:
    """Sparse constraint builder: ``lb ≤ A x ≤ ub``."""

    def __init__(self) -> None:
        self.r: list[int] = []
        self.c: list[int] = []
        self.v: list[float] = []
        self.lb: list[float] = []
        self.ub: list[float] = []

    def add(self, coefs: list[tuple[int, float]], lb: float, ub: float) -> None:
        row = len(self.lb)
        for col, val in coefs:
            self.r.append(row)
            self.c.append(col)
            self.v.append(val)
        self.lb.append(lb)
        self.ub.append(ub)

    def constraint(self, n: int) -> LinearConstraint:
        a = coo_matrix((self.v, (self.r, self.c)), shape=(len(self.lb), n)).tocsr()
        return LinearConstraint(a, np.array(self.lb), np.array(self.ub))


def _objective(inp: PlanInput, L: Layout) -> np.ndarray:
    p = inp.params
    obj = np.zeros(L.n)
    pref = 2.0 - inp.preference()  # reputation tie-break: reputable workers cost slightly less to trust or add
    for t in range(L.T):
        obj[L.u(t)] = inp.cold_penalty[t]
        for j in range(L.J):
            expo = p.exposure_weight * inp.sigma[t] * (1 - inp.assurance[j]) if p.use_exposure else 0.0
            obj[L.y(t, j)] = expo * pref[j]
            obj[L.z(t, j)] = p.kappa_switch * pref[j]
    for f in range(L.F):
        for j in range(L.J):
            obj[L.w(f, j)] = p.rho_mem * inp.fn_mem[f] - p.beta_warm * inp.fn_benefit[f]
            obj[L.s(f, j)] = p.rho_ssd * inp.fn_size[f] - p.beta_warm * p.gamma * inp.fn_benefit[f]
    return obj


def _coverage(inp: PlanInput, L: Layout, rows: _Rows) -> None:
    e = inp.contrib()
    for t in range(L.T):
        coefs = [(L.c(t, j), float(e[j])) for j in range(L.J)] + [(L.u(t), 1.0)]
        if inp.params.use_robust and inp.f[t] > 0:
            coefs += [(L.theta(t), -float(inp.f[t]))] + [(L.pi(t, j), -1.0) for j in range(L.J)]
            for j in range(L.J):
                rows.add([(L.pi(t, j), 1.0), (L.c(t, j), -1.0), (L.theta(t), 1.0)], 0.0, np.inf)
        rows.add(coefs, float(inp.q[t]), np.inf)


def big_m(inp: PlanInput) -> np.ndarray:
    """``[T, J]`` tight bound on ``c_tj``: never more than the slots, nor more than covering ``q_t`` alone (larger
    values cannot help robust coverage, so the bound is valid and tightens the fixed-charge relaxation)."""
    e = np.maximum(inp.contrib(), 1e-6)
    out: np.ndarray = np.minimum(inp.cap[None, :], inp.q[:, None] / e[None, :])
    return out


def _structure(inp: PlanInput, L: Layout, rows: _Rows) -> None:
    p = inp.params
    m = big_m(inp)
    for j in range(L.J):
        for t in range(L.T):
            rows.add([(L.c(t, j), 1.0), (L.y(t, j), -float(m[t, j]))], -np.inf, 0.0)
            rows.add([(L.z(t, j), 1.0), (L.y(t, j), -1.0)], -float(inp.y_prev[t, j]), np.inf)
        for f in range(L.F):
            t = int(inp.fn_tenant[f])
            rows.add([(L.w(f, j), 1.0), (L.y(t, j), -float(min(p.w_max, inp.fn_units[f])))], -np.inf, 0.0)
            rows.add([(L.s(f, j), 1.0), (L.y(t, j), -1.0)], -np.inf, 0.0)
        rows.add([(L.c(t, j), 1.0) for t in range(L.T)], -np.inf, float(inp.cap[j]))
        rows.add(
            [(L.w(f, j), float(inp.fn_mem[f])) for f in range(L.F)],
            -np.inf,
            max(0.0, float(inp.mem_mb[j]) - p.m_base_mb),
        )
        rows.add([(L.s(f, j), float(inp.fn_size[f])) for f in range(L.F)], -np.inf, float(inp.ssd_mb[j]))
    for f in range(L.F):
        rows.add([(L.w(f, j), 1.0) for j in range(L.J)], -np.inf, float(inp.fn_units[f]))
        rows.add([(L.s(f, j), 1.0) for j in range(L.J)], -np.inf, float(inp.fn_snaps[f]))
    if p.use_domain_cap:
        for d in np.unique(inp.domain):
            inside = set(np.flatnonzero(inp.domain == d).tolist())
            for t in range(L.T):
                coefs = [(L.c(t, j), (1.0 if j in inside else 0.0) - p.kappa_dom) for j in range(L.J)]
                rows.add(coefs, -np.inf, 0.0)


def candidates(inp: PlanInput, factor: float = 3.0, minimum: int = 8) -> np.ndarray:
    """``[T, J]`` workers each tenant may use: previous holders plus the best by the greedy score, enough for
    ``factor`` × the capacity robust coverage needs. Bounds the MILP size (D-30)."""
    allowed = inp.allowed()
    e = inp.contrib()
    out = np.zeros_like(allowed)
    mean_cap = max(1.0, float(inp.cap.mean()))
    for t in range(len(inp.tenants)):
        need = (float(inp.q[t]) / max(float(e.mean()), 1e-3) + float(inp.f[t]) * float(inp.cap.max())) / mean_cap
        m = int(min(len(e), max(minimum, np.ceil(factor * need))))
        score = e * inp.assurance * inp.cap / (inp.sigma[t] * (1 - inp.assurance) + 1e-3)
        order = [j for j in np.argsort(-score, kind="stable") if allowed[t, j]]
        out[t, order[:m]] = True
        out[t] |= inp.y_prev[t] & allowed[t]
    return out


def _bounds(inp: PlanInput, L: Layout) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    lo, hi, integ = np.zeros(L.n), np.full(L.n, np.inf), np.zeros(L.n)
    allowed = candidates(inp)
    for t in range(L.T):
        for j in range(L.J):
            hi[L.y(t, j)] = 1.0 if allowed[t, j] else 0.0
            integ[L.y(t, j)] = 1
            hi[L.c(t, j)] = float(inp.cap[j]) if allowed[t, j] else 0.0
    for f in range(L.F):
        for j in range(L.J):
            hi[L.s(f, j)], integ[L.s(f, j)] = 1.0, 1
            hi[L.w(f, j)], integ[L.w(f, j)] = float(min(inp.params.w_max, inp.fn_units[f])), 1
    return lo, hi, integ


@contextmanager
def _quiet() -> Iterator[None]:
    """HiGHS prints some MIP diagnostics straight to file descriptor 1; keep run logs clean."""
    try:
        fd = os.dup(1)
    except OSError:
        yield
        return
    with open(os.devnull, "w") as null:
        sys.stdout.flush()
        os.dup2(null.fileno(), 1)
        try:
            yield
        finally:
            sys.stdout.flush()
            os.dup2(fd, 1)
            os.close(fd)


@register("planner", "milp")
class MilpPlanner:
    def __init__(
        self, time_limit: float = 2.0, node_limit: int = 200, deterministic: bool = True, gap: float = 0.01
    ) -> None:
        self.time_limit, self.node_limit, self.deterministic, self.gap = time_limit, node_limit, deterministic, gap
        self.fallback = GreedyPlanner()

    def plan(self, inp: PlanInput) -> Plan:
        if not inp.tenants or not inp.workers:
            return Plan.empty(inp, "milp")
        L = Layout(*inp.shape)
        rows = _Rows()
        _coverage(inp, L, rows)
        _structure(inp, L, rows)
        lo, hi, integ = _bounds(inp, L)
        opts: dict[str, float | bool] = {"disp": False, "mip_rel_gap": self.gap}
        opts |= {"node_limit": self.node_limit} if self.deterministic else {"time_limit": self.time_limit}
        with _quiet():
            res = milp(
                _objective(inp, L),
                integrality=integ,
                bounds=Bounds(lo, hi),
                constraints=rows.constraint(L.n),
                options=opts,
            )
        greedy = self.fallback.plan(inp)
        if res.x is None:
            return finish(inp, greedy.y, greedy.s, greedy.w, greedy.c, "milp", status=f"fallback:{res.status}")
        x = res.x
        T, F, J = L.T, L.F, L.J
        y = x[: T * J].reshape(T, J) > 0.5
        s = x[T * J : (T + F) * J].reshape(F, J) > 0.5
        w = np.rint(x[(T + F) * J : (T + 2 * F) * J].reshape(F, J)).astype(int)
        c = np.clip(x[(T + 2 * F) * J : (2 * T + 2 * F) * J].reshape(T, J), 0, None) * y
        status = "optimal" if res.status == 0 else f"limit:{res.status}"
        plan = finish(inp, y, s, w, c, "milp", status=status)
        if greedy.objective < plan.objective:  # a budget-limited incumbent may lose to greedy: keep the better one
            return finish(inp, greedy.y, greedy.s, greedy.w, greedy.c, "milp", status=f"greedy_incumbent:{status}")
        return plan
