"""Stage B of the Erlang planners (planner-v2 proposal §4, round-4 review §2.1 B1-B4).

Pass 1, warm sandboxes under each worker's RAM budget: marginal allocation (Gross 1956; Fox 1966) on one heap keyed
by gain per MB of RAM. The gain of the next sandbox of ``f``, placed on the key holder ``j`` with the best survival
probability, is ``λ_f τ_f e_j Σ_c P(W=c)[B(c, a_f) − B(c+1, a_f)]`` where ``W`` is the number of surviving sandboxes
(an exact distribution, not its mean, which would be optimistic by convexity) and ``τ_f`` is the cold-start time.
Pass 2, snapshot pins under each worker's SSD budget, given the warm counts: a request that misses the warm pool
(probability ``E[B(W, a_f)]``) restores a snapshot, saving ``boot − restore``. RAM and SSD are separate budgets, so
they are separate passes. Optimality holds only for the pooled problem with equal sandbox sizes; placement onto
workers is first-fit by survival and may lose value. The plan's ``w`` is a floor: worker TTL pools can exceed it."""

from __future__ import annotations

import heapq

import numpy as np

from voss.policy.plan.erlang_math import add_holder, erlang_b_curve
from voss.policy.plan.types import PlanInput


class WarmState:
    """Budgets, per-function pmf of surviving sandboxes and the heap of pass 1."""

    def __init__(self, inp: PlanInput, y: np.ndarray, w: np.ndarray) -> None:
        self.inp, self.y, self.w = inp, y, w
        self.li = inp.loss_inputs()
        self.e = inp.contrib()
        self.mem = np.maximum(0.0, inp.mem_mb - inp.params.m_base_mb)
        self.units = inp.fn_units.astype(float).copy()
        a = self.li.rate_f * self.li.hold_f
        size = [int(u) + 2 for u in inp.fn_units]
        self.curve = [erlang_b_curve(n, float(a[f])) for f, n in enumerate(size)]
        self.pmf = [np.eye(1, n + 1)[0] for n in size]

    def next_gain(self, f: int) -> tuple[float, int]:
        """(value density per MB, worker) of the next sandbox of ``f``; density 0 when nothing is worth placing."""
        inp, p = self.inp, self.inp.params
        ok = self.y[inp.fn_tenant[f]] & (self.w[f] < p.w_max) & (self.mem >= inp.fn_mem[f])
        cols = np.flatnonzero(ok)
        if self.units[f] < 1 or not len(cols):
            return 0.0, -1
        j = int(cols[np.argmax(self.e[cols])])
        cv = self.curve[f]
        g = self.li.rate_f[f] * self.li.boot_f[f] * self.e[j] * float(self.pmf[f][:-1] @ (cv[:-1] - cv[1:]))
        if g * p.beta_warm * inp.horizon_s <= p.rho_mem * inp.fn_mem[f]:
            return 0.0, -1
        return g / max(float(inp.fn_mem[f]), 1.0), j

    def run(self) -> None:
        heap = [(-d, f) for f in range(len(self.inp.fns)) if (d := self.next_gain(f)[0]) > 0]
        heapq.heapify(heap)
        while heap:
            neg, f = heapq.heappop(heap)
            d, j = self.next_gain(f)
            if d <= 0:
                continue
            if d < -neg - 1e-12:  # stale: memory on the best worker was used up
                heapq.heappush(heap, (-d, f))
                continue
            self.w[f, j] += 1
            self.mem[j] -= self.inp.fn_mem[f]
            self.units[f] -= 1
            self.pmf[f] = add_holder(self.pmf[f], 1, float(self.e[j]))
            if (nd := self.next_gain(f)[0]) > 0:
                heapq.heappush(heap, (-nd, f))

    def miss(self, f: int) -> float:
        """``E[B(W, a_f)]`` for the final warm pool of ``f``."""
        return float(self.pmf[f] @ self.curve[f])


def warm_pass(inp: PlanInput, y: np.ndarray, w: np.ndarray) -> WarmState:
    """Pass 1: fill ``w`` and return the state (for the snapshot pass)."""
    st = WarmState(inp, y, w)
    st.run()
    return st


def snapshot_pass(inp: PlanInput, y: np.ndarray, s: np.ndarray, st: WarmState) -> None:
    """Pass 2: pin snapshots by value per MB of SSD, given the warm pools."""
    p, li = inp.params, st.li
    ssd = inp.ssd_mb.astype(float).copy()
    saved = np.maximum(li.boot_f - li.restore_f, 0.0)
    val = np.array([li.rate_f[f] * st.miss(f) * saved[f] for f in range(len(inp.fns))])
    for f in np.argsort(-(val / np.maximum(inp.fn_size, 1.0)), kind="stable"):
        if val[f] * p.beta_warm * p.gamma * inp.horizon_s <= p.rho_ssd * inp.fn_size[f]:
            continue
        copies = int(inp.fn_snaps[f])
        for j in np.argsort(-st.e, kind="stable"):
            if copies >= 1 and y[inp.fn_tenant[f], j] and ssd[j] >= inp.fn_size[f]:
                s[f, j] = True
                ssd[j] -= inp.fn_size[f]
                copies -= 1


def warm_state(inp: PlanInput, y: np.ndarray, s: np.ndarray, w: np.ndarray) -> None:
    """Fill ``w`` (warm sandboxes) and ``s`` (snapshot pins) on workers that hold the function's tenant key."""
    snapshot_pass(inp, y, s, warm_pass(inp, y, w))
