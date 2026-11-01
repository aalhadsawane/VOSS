"""Erlang planners (planner-v2 proposal §2-5, round-4 review): Erlang-B facts, submodularity of ``U_t`` (independent
and correlated survival), marginal allocation against brute force, the robustness certificate, feasibility, the
virtual queue, and the runtime budget."""

from __future__ import annotations

import itertools
import math
import time
from collections.abc import Callable
from dataclasses import replace

import numpy as np
from hypothesis import given, settings
from hypothesis import strategies as st
from voss.core.ids import FnId, TenantId, WorkerId
from voss.core.rng import stream
from voss.policy.plan.erlang import ErlangDpp, ErlangGreedy
from voss.policy.plan.erlang_keys import Tenant
from voss.policy.plan.erlang_math import erlang_b, erlang_b_curve, utility, worst_case_utility
from voss.policy.plan.erlang_warm import warm_pass
from voss.policy.plan.objective import feasible
from voss.policy.plan.types import PlanInput, PlanParams

from tests.property.test_planner import instance


def with_loss(inp: PlanInput, seed: int) -> PlanInput:
    """Add explicit loss-model arrays to a ``test_planner`` instance."""
    g = stream(seed, "erlang.loss")
    n_f = len(inp.fns)
    boot = g.uniform(0.5, 3.0, n_f)
    return replace(
        inp,
        fn_rate=g.uniform(0.5, 6.0, n_f),
        fn_hold=g.uniform(0.05, 0.8, n_f),
        fn_boot=boot,
        fn_restore=boot * g.uniform(0.1, 0.6, n_f),
        delta_t=g.uniform(0.5, 3.0, len(inp.tenants)),
    )


@given(c=st.integers(0, 8), a=st.floats(0.01, 20.0))
def test_erlang_b_matches_closed_form(c: int, a: float) -> None:
    closed = (a**c / math.factorial(c)) / sum(a**k / math.factorial(k) for k in range(c + 1))
    assert abs(erlang_b(c, a) - closed) < 1e-9 * max(1.0, closed)
    assert abs(erlang_b_curve(c, a)[c] - closed) < 1e-9 * max(1.0, closed)


@given(a=st.floats(0.01, 40.0))
def test_erlang_b_decreasing_and_convex(a: float) -> None:
    d = np.diff(erlang_b_curve(60, a))
    assert (d <= 1e-15).all()
    assert (np.diff(d) >= -1e-12).all()


def check_submodular(u: Callable[[list[int]], float], n: int) -> None:
    for r in range(n):
        for big in itertools.combinations(range(n), r):
            for k in range(len(big) + 1):
                for small in itertools.combinations(big, k):
                    for j in set(range(n)) - set(big):
                        g_small = u([*small, j]) - u(list(small))
                        g_big = u([*big, j]) - u(list(big))
                        assert g_small >= -1e-9
                        assert g_small >= g_big - 1e-9


@settings(max_examples=40, deadline=None)
@given(seed=st.integers(0, 10_000), n=st.integers(2, 6))
def test_utility_monotone_submodular(seed: int, n: int) -> None:
    g = stream(seed, "erlang.sub")
    slots, e = g.integers(1, 5, n), g.uniform(0.2, 1.0, n)
    a, lam, delta = float(g.uniform(0.5, 12)), float(g.uniform(0.5, 5)), float(g.uniform(0.5, 3))

    def u(idx: list[int]) -> float:
        return utility(slots[idx], e[idx], a, lam, delta) if idx else 0.0

    check_submodular(u, n)


@settings(max_examples=40, deadline=None)
@given(seed=st.integers(0, 10_000), n=st.integers(2, 6))
def test_utility_submodular_with_correlated_survival(seed: int, n: int) -> None:
    """Proposition 1: any joint survival law not depending on ``S`` works. Mixture of a normal scenario and a
    shock in which a random block of workers is lost together."""
    g = stream(seed, "erlang.corr")
    slots, e = g.integers(1, 5, n), g.uniform(0.2, 1.0, n)
    shock_p = float(g.uniform(0.05, 0.5))
    dead = g.random(n) < 0.5
    a, lam, delta = float(g.uniform(0.5, 12)), float(g.uniform(0.5, 5)), float(g.uniform(0.5, 3))
    e_shock = np.where(dead, 0.0, e)

    def u(idx: list[int]) -> float:
        if not idx:
            return 0.0
        return (1 - shock_p) * utility(slots[idx], e[idx], a, lam, delta) + shock_p * utility(
            slots[idx], e_shock[idx], a, lam, delta
        )

    check_submodular(u, n)


@settings(max_examples=40, deadline=None)
@given(seed=st.integers(0, 10_000), n_f=st.integers(1, 3), budget=st.integers(0, 6))
def test_marginal_allocation_matches_brute_force(seed: int, n_f: int, budget: int) -> None:
    """The real warm pass (RAM only, equal sandbox sizes, survival 1, one holder) against enumeration."""
    g = stream(seed, "erlang.alloc")
    rate, hold = g.uniform(0.5, 5.0, n_f), g.uniform(0.2, 1.5, n_f)
    inp = PlanInput(
        now=0.0,
        horizon_s=60.0,
        workers=(WorkerId(0),),
        cap=np.array([4.0]),
        mem_mb=np.array([512.0 + budget]),
        ssd_mb=np.array([0.0]),
        survival=np.ones(1),
        p_omit=np.zeros(1),
        assurance=np.ones(1),
        domain=np.zeros(1, int),
        fresh_ok=np.ones(1, bool),
        tenants=(TenantId("t"),),
        q=np.ones(1),
        rate=np.ones(1),
        sigma=np.ones(1),
        a_min=np.zeros(1),
        f=np.zeros(1, int),
        cold_penalty=np.ones(1),
        fns=tuple(FnId(f"f{i}") for i in range(n_f)),
        fn_tenant=np.zeros(n_f, int),
        fn_mem=np.ones(n_f),
        fn_size=np.ones(n_f),
        fn_benefit=np.ones(n_f),
        fn_units=np.full(n_f, 50.0),
        y_prev=np.zeros((1, 1), bool),
        params=PlanParams(w_max=100, beta_warm=1e9, rho_mem=0.0),
        fn_rate=rate,
        fn_hold=hold,
        fn_boot=np.ones(n_f),
    )
    w = np.zeros((n_f, 1), int)
    warm_pass(inp, np.ones((1, 1), bool), w)
    a = rate * hold

    def val(c: tuple[int, ...]) -> float:
        return sum(rate[f] * (1 - erlang_b(c[f], a[f])) for f in range(n_f))

    best = max(val(c) for c in itertools.product(range(budget + 1), repeat=n_f) if sum(c) <= budget)
    assert val(tuple(int(x) for x in w[:, 0])) >= best - 1e-9


def test_buffer_improves_worst_case_utility() -> None:
    """The sacrificial buffer improves the exact certificate ``min_{|R|≤f} U_t(S∖R)`` (never worse here)."""
    better = worse = 0
    for seed in range(60):
        inp = replace(
            instance(seed, 1, 10, 2),
            fresh_ok=np.ones(10, bool),
            a_min=np.zeros(1),
            rate=np.array([4.0]),
            delta_t=np.array([3.0]),
            tenant_load=np.array([4.0]),
        )
        td = Tenant(inp, inp.loss_inputs(), 0, inp.cap.astype(float), 0.05)
        r = []
        for buffer in (True, False):
            ch = td.run(True, buffer=buffer)
            r.append(worst_case_utility(td.m[ch], td.e[ch], td.a, td.lam, td.delta, 2) if ch else 0.0)
        better += r[0] > r[1] + 1e-9
        worse += r[0] < r[1] - 1e-9
    assert worse == 0 and better >= 30, (better, worse)


@settings(max_examples=40, deadline=None)
@given(seed=st.integers(0, 10_000), n_t=st.integers(1, 3), n_j=st.integers(3, 9), f=st.integers(0, 2))
def test_erlang_plans_feasible(seed: int, n_t: int, n_j: int, f: int) -> None:
    inp = with_loss(instance(seed, n_t, n_j, f), seed)
    ablated = replace(inp.params, use_exposure=False, use_robust=False)
    for planner in (ErlangGreedy(), ErlangDpp()):
        for params in (inp.params, ablated):
            case = replace(inp, params=params)
            plan = planner.plan(case)
            assert not feasible(case, plan), feasible(case, plan)
            plan.robust_slack(case)  # reported quantity only: must compute, need not be >= 0


def test_defaults_derived_without_loss_inputs() -> None:
    inp = instance(3, 2, 6, 1)
    assert not feasible(inp, ErlangGreedy().plan(inp))


def test_dpp_virtual_queue() -> None:
    """``Q(0) = σ``; then ``Q ← max(Q + E − E_budget, 0)`` every round, including reused rounds (``on_reused``)."""
    base = with_loss(instance(5, 2, 9, 1), 5)
    inp = replace(base, params=PlanParams(e_budget=0.01), measured_exposure=np.array([0.5, 0.2]))
    pl = ErlangDpp()
    pl.plan(inp)
    assert [pl.q[str(t)] for t in inp.tenants] == list(inp.sigma)
    pl.on_reused(inp)
    pl.plan(inp)
    for i, t in enumerate(inp.tenants):
        once = max(inp.sigma[i] + inp.measured_exposure[i] - 0.01, 0.0)
        assert abs(pl.q[str(t)] - max(once + inp.measured_exposure[i] - 0.01, 0.0)) < 1e-12
    loose = replace(inp, params=PlanParams(e_budget=1e6))
    pl2 = ErlangDpp()
    for _ in range(3):
        pl2.plan(loose)
    assert all(v == 0.0 for v in pl2.q.values())


def big_instance(scale: float = 1.0) -> PlanInput:
    """40 workers, 20 tenants, 50 functions (ten tenants get a third function). ``scale`` multiplies capacity."""
    inp = with_loss(instance(11, 20, 40, 1), 11)
    pick = np.concatenate([np.arange(len(inp.fns)), np.arange(0, 20, 2) * 2])
    fns = tuple(FnId(f"f{i}") for i in range(len(pick)))
    keys = ("fn_tenant", "fn_mem", "fn_size", "fn_benefit", "fn_units", "fn_rate", "fn_hold", "fn_boot", "fn_restore")
    return replace(inp, fns=fns, cap=inp.cap * scale, **{k: getattr(inp, k)[pick] for k in keys})


def test_runtime_under_50ms_soft() -> None:
    """Soft check: best of five runs (shared CI machines are noisy), 40 workers x 20 tenants x 50 functions."""
    inp = big_instance(scale=3.0)
    assert len(inp.fns) == 50
    best = float("inf")
    for _ in range(5):
        t0 = time.perf_counter()
        plan = ErlangGreedy().plan(inp)
        best = min(best, time.perf_counter() - t0)
    assert not feasible(inp, plan)
    assert best < 0.05, best
