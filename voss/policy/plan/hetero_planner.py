"""``hetero`` provisioning (docs/REVISION_PLAN.md §11, D-96): VOSS's provisioning policy.

Maps the allocation of ``policy.plan.hetero.provision`` onto a plan: holders and reserved units per key (one key per
function), one warm sandbox per reserved unit while the worker's memory allows (larger arrival rates first), and a
snapshot on every holder whose disk has room (so a lost warm sandbox restores instead of booting).
"""

from __future__ import annotations

import numpy as np

from voss.core.registry import register
from voss.policy.plan.hetero import provision
from voss.policy.plan.objective import finish
from voss.policy.plan.types import Plan, PlanInput


def _warm(inp: PlanInput, units: np.ndarray, lam: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    n_f, n_j = units.shape
    w, s = np.zeros((n_f, n_j), np.int64), np.zeros((n_f, n_j), bool)
    mem = np.maximum(0.0, inp.mem_mb - inp.params.m_base_mb)
    ssd = inp.ssd_mb.astype(float).copy()
    for f in np.argsort(-lam, kind="stable"):
        for j in np.flatnonzero(units[f]):
            n = int(min(units[f, j], inp.params.w_max, mem[j] // max(inp.fn_mem[f], 1.0)))
            w[f, j], mem[j] = n, mem[j] - n * inp.fn_mem[f]
            if ssd[j] >= inp.fn_size[f]:
                s[f, j], ssd[j] = True, ssd[j] - inp.fn_size[f]
    return w, s


@register("planner", "hetero")
class HeteroPlanner:
    def plan(self, inp: PlanInput) -> Plan:
        n_t, n_f, n_j = inp.shape
        y, c = np.zeros((n_t, n_j), bool), np.zeros((n_t, n_j))
        s, w = np.zeros((n_f, n_j), bool), np.zeros((n_f, n_j), np.int64)
        if inp.hetero is not None and n_f and n_j:
            a = provision(inp.hetero)
            for f in range(n_f):
                t = int(inp.fn_tenant[f])
                y[t] |= a.holders[f]
                c[t] += a.units[f]
            w, s = _warm(inp, a.units, inp.hetero.lam)
        return finish(inp, y, s, w, c, "hetero")
