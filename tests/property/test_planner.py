"""Planner properties (roadmap P4 exit): robust coverage survives removing any f workers (brute force on tiny
instances); plans satisfy every constraint; the MILP is never worse than greedy on the shared objective."""

from __future__ import annotations

import itertools

import numpy as np
from hypothesis import given, settings
from hypothesis import strategies as st
from voss.core.ids import FnId, TenantId, WorkerId
from voss.core.rng import stream
from voss.policy.plan.greedy import GreedyPlanner
from voss.policy.plan.milp import MilpPlanner
from voss.policy.plan.objective import feasible
from voss.policy.plan.types import PlanInput, PlanParams


def instance(seed: int, n_t: int, n_j: int, f: int, robust: bool = True) -> PlanInput:
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
        assurance=g.uniform(0.5, 0.95, n_j),
        domain=g.integers(0, max(2, n_j // 2), n_j),
        fresh_ok=g.random(n_j) < 0.9,
        tenants=tuple(TenantId(f"t{i}") for i in range(n_t)),
        q=g.uniform(0.5, 4.0, n_t),
        rate=g.uniform(1, 10, n_t),
        sigma=g.choice([0.1, 1.0, 3.0], n_t),
        a_min=g.choice([0.0, 0.0, 0.7], n_t),
        f=np.full(n_t, f),
        cold_penalty=g.uniform(5, 20, n_t),
        fns=tuple(FnId(f"f{i}") for i in range(n_f)),
        fn_tenant=np.repeat(np.arange(n_t), 2),
        fn_mem=g.choice([128.0, 256.0, 512.0], n_f),
        fn_size=g.uniform(50, 600, n_f),
        fn_benefit=g.uniform(0, 20, n_f),
        fn_units=g.integers(0, 4, n_f).astype(float),
        y_prev=g.random((n_t, n_j)) < 0.3,
        params=PlanParams(use_robust=robust),
    )


def removal_coverage(inp: PlanInput, c: np.ndarray, t: int, removed: tuple[int, ...]) -> float:
    e = inp.contrib()
    keep = np.ones(len(e), bool)
    keep[list(removed)] = False
    return float((c[t] * e)[keep].sum())


@settings(max_examples=40, deadline=None)
@given(seed=st.integers(0, 10_000), n_t=st.integers(1, 3), n_j=st.integers(2, 7), f=st.integers(0, 2))
def test_robust_coverage_brute_force(seed: int, n_t: int, n_j: int, f: int) -> None:
    inp = instance(seed, n_t, n_j, f)
    plan = MilpPlanner().plan(inp)
    u = np.array([max(0.0, inp.q[t] - 0) for t in range(n_t)])  # shortfall is in cost_terms; recompute per tenant
    from voss.policy.plan.objective import shortfall

    u = shortfall(inp, plan.c)
    for t in range(n_t):
        for removed in itertools.combinations(range(n_j), min(f, n_j)):
            assert removal_coverage(inp, plan.c, t, removed) + u[t] >= inp.q[t] - 1e-6


@settings(max_examples=40, deadline=None)
@given(seed=st.integers(0, 10_000), n_t=st.integers(1, 3), n_j=st.integers(2, 8), f=st.integers(0, 2))
def test_plans_feasible_and_milp_not_worse(seed: int, n_t: int, n_j: int, f: int) -> None:
    inp = instance(seed, n_t, n_j, f)
    g, m = GreedyPlanner().plan(inp), MilpPlanner().plan(inp)
    assert not feasible(inp, g), feasible(inp, g)
    assert not feasible(inp, m), feasible(inp, m)
    assert m.objective <= g.objective + 1e-6 * max(1.0, abs(g.objective))
