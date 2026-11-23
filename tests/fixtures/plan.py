"""A small planner input shared by the plan tests (not a reported scenario)."""

from __future__ import annotations

import numpy as np
from voss.core.ids import FnId, TenantId, WorkerId
from voss.core.rng import stream
from voss.policy.plan.types import PlanInput, PlanParams


def plan_input(seed: int, n_t: int, n_j: int, *, w_max: int = 4) -> PlanInput:
    g = stream(seed, "plan.instance")
    n_f = 2 * n_t
    return PlanInput(
        now=0.0,
        horizon_s=60.0,
        workers=tuple(WorkerId(i) for i in range(n_j)),
        cap=g.integers(1, 5, n_j).astype(float),
        mem_mb=g.uniform(600, 4000, n_j),
        ssd_mb=g.uniform(0, 2000, n_j),
        survival=g.uniform(0.6, 1.0, n_j),
        p_omit=g.uniform(0.0, 0.2, n_j),
        fresh_ok=g.random(n_j) < 0.9,
        tenants=tuple(TenantId(f"t{i}") for i in range(n_t)),
        q=g.uniform(0.5, 4.0, n_t),
        fns=tuple(FnId(f"f{i}") for i in range(n_f)),
        fn_tenant=np.repeat(np.arange(n_t), 2),
        fn_rate=g.uniform(1.0, 10.0, n_f),
        fn_mem=g.choice([128.0, 256.0, 512.0], n_f),
        fn_size=g.uniform(50, 600, n_f),
        fn_units=g.integers(0, 4, n_f).astype(float),
        y_prev=g.random((n_t, n_j)) < 0.3,
        params=PlanParams(w_max=w_max),
    )
