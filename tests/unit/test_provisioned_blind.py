"""``provisioned_keys`` (holder count from greedy, workers by reliability) and the ``survival_blind`` ablation."""

from __future__ import annotations

from dataclasses import replace

import numpy as np
from hypothesis import given, settings
from hypothesis import strategies as st
from voss.policy.plan.ablate import survival_blind
from voss.policy.plan.greedy import GreedyPlanner
from voss.policy.plan.provisioned import ProvisionedKeys, most_reliable
from voss.policy.plan.types import PlanParams

from tests.property.test_planner import instance


def test_most_reliable_picks_top_allowed_with_stable_ties() -> None:
    score = np.array([0.9, 0.5, 0.9, 0.7, 0.99])
    allowed = np.array([True, True, True, True, False])
    assert most_reliable(score, allowed, 2).tolist() == [True, False, True, False, False]
    assert most_reliable(score, allowed, 9).tolist() == [True, True, True, True, False]
    assert not most_reliable(score, allowed, 0).any()


@settings(max_examples=40, deadline=None)
@given(seed=st.integers(0, 5000), n_t=st.integers(1, 4), n_j=st.integers(3, 12))
def test_holder_count_matches_greedy_and_workers_are_the_most_reliable(seed: int, n_t: int, n_j: int) -> None:
    inp = instance(seed, n_t, n_j, 1)
    ref, plan = GreedyPlanner().plan(inp), ProvisionedKeys().plan(inp)
    assert plan.planner == "provisioned_keys"
    assert (plan.y.sum(axis=1) == ref.y.sum(axis=1)).all()
    assert not plan.s.any() and not plan.w.any()  # no warm-state planning
    assert not (plan.y & ~inp.allowed()).any()  # assurance floor and freshness respected
    e = inp.contrib()
    for t in range(n_t):
        held, ok = plan.y[t], inp.allowed()[t]
        if held.any() and (ok & ~held).any():
            assert e[held].min() >= e[ok & ~held].max() - 1e-12


def test_plan_is_deterministic() -> None:
    inp = instance(7, 3, 9, 1)
    a, b = ProvisionedKeys().plan(inp), ProvisionedKeys().plan(inp)
    assert (a.y == b.y).all() and (a.c == b.c).all()


def test_survival_blind_replaces_survival_and_residence_by_the_mean() -> None:
    base = instance(3, 2, 8, 1)
    inp = replace(base, residence=np.linspace(10.0, 100.0, 8))
    out = survival_blind(inp)
    assert np.allclose(out.survival, inp.survival.mean()) and np.allclose(out.residence, 55.0)
    assert (out.p_omit == inp.p_omit).all() and (out.assurance == inp.assurance).all()
    assert inp.survival.std() > 0  # the input itself is not mutated
    assert survival_blind(instance(3, 2, 0, 1)).survival.size == 0


def test_survival_blind_without_residence_keeps_it_unset() -> None:
    assert survival_blind(instance(5, 2, 6, 1)).residence is None


def test_survival_blind_makes_provisioned_keys_pick_by_omission_only() -> None:
    inp = survival_blind(instance(11, 2, 10, 1))
    plan = ProvisionedKeys().plan(inp)
    for t in range(2):
        held, ok = plan.y[t], inp.allowed()[t]
        if held.any() and (ok & ~held).any():
            assert inp.p_omit[held].max() <= inp.p_omit[ok & ~held].min() + 1e-12


def test_survival_blind_is_off_by_default() -> None:
    assert PlanParams().survival_blind is False
