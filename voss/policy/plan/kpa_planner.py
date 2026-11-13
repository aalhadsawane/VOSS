"""``kpa`` planner: the Knative Pod Autoscaler baseline (``policy.plan.kpa``) mapped onto a plan.

Per function: the desired sandbox count from ``decide``; sandboxes go to workers that hold the function's key first,
then to the allowed workers with the highest ``S_j(H)·(1 − p_j)`` (``PlanInput.contrib``), at most ``w_max`` and the
worker's memory per worker. Keys follow the sandboxes; ``finish`` truncates holders to the budget ``K``.
"""

from __future__ import annotations

import numpy as np

from voss.core.registry import register
from voss.policy.plan.kpa import KpaParams, KpaState, decide, place
from voss.policy.plan.objective import finish
from voss.policy.plan.types import Plan, PlanInput


@register("planner", "kpa")
class KpaPlanner:
    def __init__(self, params: KpaParams | None = None) -> None:
        self.p = params or KpaParams()
        self.state: dict[str, KpaState] = {}

    def plan(self, inp: PlanInput) -> Plan:
        n_t, n_f, n_j = inp.shape
        y, c = np.zeros((n_t, n_j), bool), np.zeros((n_t, n_j))
        s, w = np.zeros((n_f, n_j), bool), np.zeros((n_f, n_j), np.int64)
        conc = inp.fn_inflight if inp.fn_inflight is not None else np.zeros(n_f)
        allowed, score = inp.allowed(), inp.contrib()
        mem = np.maximum(0.0, inp.mem_mb - inp.params.m_base_mb)
        for f, fn in enumerate(inp.fns):
            st = self.state.setdefault(str(fn), KpaState())
            st.observe(inp.now, float(conc[f]), self.p.stable_s)
            want = decide(st, inp.now, self.p)
            t = int(inp.fn_tenant[f])
            ok = np.flatnonzero(allowed[t])
            order = sorted(ok, key=lambda j: (not inp.y_prev[t, j], -score[j], j))
            room = [int(min(inp.params.w_max, mem[j] // max(inp.fn_mem[f], 1.0))) for j in range(n_j)]
            for j, n in place(want, [int(j) for j in order], room).items():
                w[f, j] = n
                mem[j] -= n * inp.fn_mem[f]
                y[t, j] = True
                c[t, j] += n
        return finish(inp, y, s, w, c, "kpa")
