"""``provisioned_keys`` (holder count from the demand quantile, workers by reliability) and the ``survival_blind``
ablation."""

from __future__ import annotations

import numpy as np
from hypothesis import given, settings
from hypothesis import strategies as st
from voss.policy.plan.ablate import survival_blind
from voss.policy.plan.provisioned import ProvisionedKeys, holder_count, most_reliable

from tests.fixtures.plan import plan_input


def test_most_reliable_picks_top_allowed_with_stable_ties() -> None:
    score = np.array([0.9, 0.5, 0.9, 0.7, 0.99])
    allowed = np.array([True, True, True, True, False])
    assert most_reliable(score, allowed, 2).tolist() == [True, False, True, False, False]
    assert most_reliable(score, allowed, 9).tolist() == [True, True, True, True, False]
    assert not most_reliable(score, allowed, 0).any()


@settings(max_examples=40, deadline=None)
@given(seed=st.integers(0, 5000), n_t=st.integers(1, 4), n_j=st.integers(3, 12))
def test_holder_count_is_the_demand_bound_and_workers_are_most_reliable(seed: int, n_t: int, n_j: int) -> None:
    inp = plan_input(seed, n_t, n_j)
    plan = ProvisionedKeys().plan(inp)
    assert plan.planner == "provisioned_keys"
    assert not plan.s.any() and not plan.w.any()  # no warm-state planning
    assert not (plan.y & ~inp.allowed()).any()  # freshness respected (v1 trust floor deleted, D-125)
    e = inp.contrib()
    for t in range(n_t):
        assert int(plan.y[t].sum()) == holder_count(inp, t, inp.allowed()[t])
        held, ok = plan.y[t], inp.allowed()[t]
        if held.any() and (ok & ~held).any():
            assert e[held].min() >= e[ok & ~held].max() - 1e-12


def test_plan_is_deterministic() -> None:
    inp = plan_input(7, 3, 9)
    a, b = ProvisionedKeys().plan(inp), ProvisionedKeys().plan(inp)
    assert (a.y == b.y).all() and (a.c == b.c).all()


def test_survival_blind_replaces_survival_by_the_mean() -> None:
    inp = plan_input(3, 2, 8)
    out = survival_blind(inp)
    assert np.allclose(out.survival, inp.survival.mean())
    assert (out.p_omit == inp.p_omit).all()
    assert inp.survival.std() > 0  # the input itself is not mutated
    assert survival_blind(plan_input(3, 2, 0)).survival.size == 0


def test_survival_blind_makes_provisioned_keys_pick_by_omission_only() -> None:
    inp = survival_blind(plan_input(11, 2, 10))
    plan = ProvisionedKeys().plan(inp)
    for t in range(2):
        held, ok = plan.y[t], inp.allowed()[t]
        if held.any() and (ok & ~held).any():
            assert inp.p_omit[held].min() <= inp.p_omit[ok & ~held].max() + 1e-12
