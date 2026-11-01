"""Stage A of the Erlang planners (planner-v2 proposal §3): which workers hold each hot tenant's key.

Per tenant, on a fixed ground set (assurance floor and freshness filter it) with a holder limit ``k``, the planner
maximises ``U_t(S) − κ(S)``. ``U_t`` is monotone submodular (proposal claim A1) and ``κ`` is modular and non-negative:
exposure ``price·(1 − a_j)``, memory ``ρ_mem m c_tj`` and the one-off prepare cost amortised over the expected stay,
``Δ_t·[y_prev = 0] / E[min(L_j, T)]`` (renewal-reward; the value of a long session is therefore in the cost, not
multiplied into the utility). Selection is distorted greedy (Harshaw et al., ICML 2019) and plain greedy, keeping the
better set. Only this per-tenant problem carries the ``(1 − 1/e)U(OPT) − κ(OPT)`` bound, and only under the
cardinality limit; the sacrificial buffer of the ``f_t`` best single holders (Orlin–Schulz–Udwani style), the domain
cap, shared slots across tenants and priority order are heuristics. The joint plan has no guarantee. The coverage
requirement ``q_t`` is not enforced; ``Plan.robust_slack`` is a reported quantity (round-4 review §0.4).

Approximation: a holder's survival is ``S_j(H)(1 − p_omit_j)``; a dropping worker keeps its slot and costs a retry
rather than capacity, so the thinning by ``p_omit`` is an approximation of that retry delay."""

from __future__ import annotations

import numpy as np

from voss.policy.plan.erlang_math import add_holder, erlang_b_curve, utility
from voss.policy.plan.types import LossInputs, PlanInput


def _gains(p: np.ndarray, hcur: np.ndarray, m: np.ndarray, e: np.ndarray) -> np.ndarray:
    """Marginal ``E[h(C + m_j X_j)] − E[h(C)]`` for every candidate: one dot product per distinct slot count."""
    base = float(p @ hcur[: len(p)])
    out = np.zeros(len(m))
    for mv in np.unique(m):
        sel = m == mv
        out[sel] = e[sel] * (float(p @ hcur[mv : mv + len(p)]) - base)
    return out


class Tenant:
    """Candidate arrays of one tenant and the greedy rounds over them."""

    def __init__(self, inp: PlanInput, li: LossInputs, t: int, free: np.ndarray, price: float) -> None:
        p = inp.params
        self.inp, self.t = inp, t
        self.cand = np.flatnonzero(inp.allowed()[t] & (free >= 1.0))
        self.lam, self.delta, self.a = float(inp.rate[t]), float(li.delta_t[t]), float(li.load_t[t])
        self.m = np.minimum(np.floor(free[self.cand]), li.slots_t[t]).astype(np.int64)
        self.e = inp.contrib()[self.cand]
        fns = inp.fn_tenant == t
        mem_cost = p.rho_mem * float(inp.fn_mem[fns].mean()) if fns.any() else 0.0
        expo = price * (1 - inp.assurance[self.cand]) if p.use_exposure else 0.0
        prep = self.delta * (~inp.y_prev[t, self.cand]) / np.maximum(li.residence[self.cand], 1.0)
        self.kappa = (expo + mem_cost * self.m + prep) / inp.preference()[self.cand]
        self.k = int(li.k_t[t])
        self.n_cap = int(self.m.sum()) + 1
        self.hcur = 1.0 - erlang_b_curve(self.n_cap + int(self.m.max(initial=0)), self.a)

    def net(self, chosen: list[int]) -> float:
        """``U_t(S) − κ(S)`` of a chosen set (indices into the candidate arrays), exactly."""
        if not chosen:
            return 0.0
        u = utility(self.m[chosen], self.e[chosen], self.a, self.lam, self.delta)
        return u - float(self.kappa[chosen].sum())

    def run(self, distorted: bool, buffer: bool = True) -> list[int]:
        pmf = np.zeros(self.n_cap)
        pmf[0] = 1.0
        chosen: list[int] = []
        alive = np.ones(len(self.cand), bool)
        scale = self.lam * self.delta
        f = int(self.inp.f[self.t]) if self.inp.params.use_robust and buffer else 0
        buf: list[int] = []
        if f > 0:  # sacrificial buffer: the f best single holders with positive net value (not conditioned on)
            net = scale * _gains(pmf, self.hcur, self.m, self.e) - self.kappa
            buf = [int(i) for i in np.argsort(-net, kind="stable")[: min(f, self.k)] if net[i] > 0]
            alive[buf] = False
        rounds = max(0, min(self.k - len(buf), int(alive.sum())))
        for r in range(rounds):
            w = (1.0 - 1.0 / rounds) ** (rounds - r - 1) if distorted else 1.0
            score = np.where(alive, w * scale * _gains(pmf, self.hcur, self.m, self.e) - self.kappa, -np.inf)
            i = int(np.argmax(score))
            if not np.isfinite(score[i]) or score[i] <= 0:
                break
            pmf = add_holder(pmf, int(self.m[i]), float(self.e[i]))
            chosen.append(i)
            alive[i] = False
        return [*buf, *chosen]


def select_holders(inp: PlanInput, t: int, free: np.ndarray, price: float) -> tuple[list[int], np.ndarray]:
    """Holders of tenant ``t`` (worker indices) and integer slots per worker (``≤ free``)."""
    slots = np.zeros(len(inp.workers), dtype=np.int64)
    td = Tenant(inp, inp.loss_inputs(), t, free, price)
    if not len(td.cand):
        return [], slots
    best = max((td.run(True), td.run(False)), key=td.net)
    slots[td.cand[best]] = td.m[best]
    if inp.params.use_domain_cap:
        _trim_domains(inp, slots)
    return [int(j) for j in np.flatnonzero(slots)], slots


def _trim_domains(inp: PlanInput, slots: np.ndarray) -> None:
    """Domain cap: while a failure domain holds more than ``κ_dom`` of the tenant's slots, take one slot from its
    largest holder (a lone holder or a single domain is dropped entirely, as in the greedy planner)."""
    kd = inp.params.kappa_dom
    for _ in range(int(slots.sum()) + 1):
        total = int(slots.sum())
        if total == 0:
            return
        over = [d for d in np.unique(inp.domain) if slots[inp.domain == d].sum() > kd * total + 1e-9]
        if not over:
            return
        idx = np.flatnonzero((inp.domain == over[0]) & (slots > 0))
        slots[idx[np.argmax(slots[idx])]] -= 1


def allocate_keys(inp: PlanInput, y: np.ndarray, c: np.ndarray, prices: np.ndarray) -> None:
    """Fill ``y``/``c`` for every hot tenant in the greedy planner's priority order on the remaining slots."""
    free = inp.cap.astype(float).copy()
    for ti in np.argsort(-(inp.rate * inp.cold_penalty), kind="stable"):
        t = int(ti)
        chosen, slots = select_holders(inp, t, free, float(prices[t]))
        y[t, chosen] = True
        c[t, chosen] = slots[chosen]
        free -= c[t]
