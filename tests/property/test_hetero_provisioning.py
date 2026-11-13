"""Provisioning with heterogeneous, unreliable workers (plan §11.6): Proposition 1, the greedy bounds, constraints."""

from __future__ import annotations

import itertools
import math

import numpy as np
from hypothesis import given, settings
from hypothesis import strategies as st
from voss.core.rng import stream
from voss.policy.plan.hetero import HeteroInput, _State, provision, scenarios, unit_value
from voss.policy.plan.loss import Carried, erlang_b_curve


def instance(seed: int, n_f: int, n_j: int, m: int = 16, budget: int = 0, units: int = 2) -> HeteroInput:
    g = stream(seed, "test.hetero")
    et = g.lognormal(0.0, 0.6, (n_f, n_j))
    return HeteroInput(
        lam=g.uniform(0.5, 6.0, n_f),
        t_ref=np.ones(n_f),
        et=et,
        pi=g.uniform(0.2, 1.0, (n_f, n_j)),
        alive=scenarios(g.uniform(0.5, 1.0, n_j), np.arange(n_j) % 3, np.full(3, 0.1), m, g),
        units=np.full(n_j, units),
        budget=np.full(n_f, budget),
        allowed=np.ones((n_f, n_j), bool),
        prev=np.zeros((n_f, n_j), bool),
    )


def value_of(inp: HeteroInput, holders: np.ndarray, units: np.ndarray) -> float:
    st_ = _State(inp, unit_value(inp))
    for f, j in zip(*np.nonzero(holders), strict=True):
        for _ in range(int(units[f, j])):
            st_.take(int(f), int(j))
    return st_.value()


def test_carried_traffic_is_concave_and_increasing() -> None:
    b = erlang_b_curve(40, 7.5)
    assert (np.diff(b) <= 1e-15).all() and (np.diff(b, 2) >= -1e-15).all()  # Messerli 1972
    g = Carried(7.5, 40)
    x = np.linspace(0, 40, 2001)
    y = g(x)
    assert (np.diff(y) >= -1e-12).all() and (np.diff(y, 2) <= 1e-9).all()
    assert g(1.0) == 1.0 - 7.5 / 8.5  # B(1, a) = a / (1 + a)


@settings(max_examples=40, deadline=None)
@given(st.integers(0, 2**31 - 1))
def test_proposition_1_diminishing_returns(seed: int) -> None:
    inp = instance(seed, 1, 6)
    g = stream(seed, "test.hetero.sets")
    small = g.random(6) < 0.3
    big = small | (g.random(6) < 0.5)
    e = int(np.flatnonzero(~big)[0]) if (~big).any() else None
    if e is None:
        return
    ones = np.ones((1, 6), np.int64)

    def val(mask: np.ndarray) -> float:
        return value_of(inp, mask[None, :], ones)

    plus = np.zeros(6, bool)
    plus[e] = True
    gain_small = val(small | plus) - val(small)
    gain_big = val(big | plus) - val(big)
    assert gain_small >= gain_big - 1e-12 and gain_big >= -1e-12


@settings(max_examples=25, deadline=None)
@given(st.integers(0, 2**31 - 1), st.integers(1, 4))
def test_greedy_is_within_1_minus_1_over_e_of_brute_force_for_one_function(seed: int, k: int) -> None:
    inp = instance(seed, 1, 7, budget=k, units=1)
    got = provision(inp).value
    best = 0.0
    for size in range(k + 1):
        for s in itertools.combinations(range(7), size):
            mask = np.zeros((1, 7), bool)
            mask[0, list(s)] = True
            best = max(best, value_of(inp, mask, np.ones((1, 7), np.int64)))
    assert got >= (1 - 1 / math.e) * best - 1e-9


@settings(max_examples=40, deadline=None)
@given(st.integers(0, 2**31 - 1), st.integers(1, 4), st.integers(1, 3))
def test_budget_and_worker_units_are_respected(seed: int, k: int, units: int) -> None:
    inp = instance(seed, 4, 10, budget=k, units=units)
    a = provision(inp)
    assert (a.holders.sum(axis=1) <= k).all()
    assert (a.units.sum(axis=0) <= units).all() and ((a.units > 0) == a.holders).all()
    assert abs(a.value - value_of(inp, a.holders, a.units)) < 1e-9  # same model, other summation order


def test_slower_or_less_reliable_workers_are_chosen_later() -> None:
    fast_reliable = HeteroInput(
        lam=np.array([4.0]),
        t_ref=np.ones(1),
        et=np.array([[1.0, 3.0, 1.0]]),
        pi=np.array([[0.95, 0.95, 0.95]]),
        alive=np.array([[True, True, False]] * 8 + [[True, True, True]] * 2),
        units=np.ones(3),
        budget=np.ones(1),
        allowed=np.ones((1, 3), bool),
        prev=np.zeros((1, 3), bool),
    )
    a = provision(fast_reliable)
    assert a.holders[0].tolist() == [True, False, False]  # the fast worker that stays beats a slow or a leaving one
