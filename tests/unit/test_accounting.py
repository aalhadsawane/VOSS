"""P7 building blocks: credit settlement (doc 09 §4), reputation rules and variants (doc 09 §2), and the planner's
reputation tie-break (tie-breaks only, doc 09 §1)."""

from __future__ import annotations

import math
from dataclasses import replace

import numpy as np
import pytest
from voss.core.ids import ClusterId, FnId, InvId, TenantId, WorkerId
from voss.core.messages import Receipt
from voss.core.messages_acct import ReceiptRow, RoleRecord
from voss.core.registry import REGISTRY, create
from voss.policy import reputation as _rep  # noqa: F401  (registers reputation rules)
from voss.policy.credits import CreditParams, Ledger, settle
from voss.policy.plan.greedy import GreedyPlanner
from voss.policy.plan.types import PlanInput, PlanParams
from voss.policy.reputation import RepParams, decayed, newcomer, tie_break_scores

P = CreditParams(late_factor=0.5, cache_per_gb_h=0.1, sched_per_assign=0.01, sched_per_h=1.0, standby_per_h=0.25)


def _row(inv: int, worker: int, status: str = "ok", t: float = 1.0, units: float = 2.0, epoch: int = 1) -> ReceiptRow:
    rc = Receipt(InvId(inv), 0, WorkerId(worker), "c", epoch, 0.5, units, "d") if status != "no_result" else None
    return ReceiptRow(InvId(inv), 0, WorkerId(worker), status, t, "r", rc, 0, "f", "t", 0.0, 2.0)


def _ledger(*roles: tuple[int, int, int | None, float]) -> Ledger:
    led = Ledger()
    led.add_roles(
        RoleRecord(ClusterId(0), e, WorkerId(h), None if s is None else WorkerId(s), t) for e, h, s, t in roles
    )
    return led


def test_work_credit_uses_reference_units_and_timeliness() -> None:
    rows = [_row(1, 5), _row(2, 5, t=3.0), _row(3, 6, "duplicate"), _row(4, 7, "no_result")]
    s = settle(rows, [], _ledger((1, 9, None, 0.0)), 10.0, P)
    assert s.credits[(5, "work")] == pytest.approx([2.0 + 1.0, 2])  # on time + late at half
    assert s.credits[(6, "duplicate")] == pytest.approx([2.0, 1])
    assert not any(w == 7 for w, _ in s.credits)  # no result, no credit
    assert s.on_time == {5: 2.0, 6: 2.0} and s.late == {5: 2.0}
    assert s.credits[(9, "sched_assign")] == pytest.approx([0.02, 2])  # ok receipts of epoch 1 only
    assert list(s.latency) == pytest.approx([9.0, 7.0, 9.0])


def test_role_time_accrues_until_the_next_record_across_settlements() -> None:
    led = _ledger((1, 1, 2, 0.0), (2, 3, None, 1800.0))
    s1 = settle([], [], led, 3600.0, P)
    assert s1.credits[(1, "sched_active")][0] == pytest.approx(0.5)
    assert s1.credits[(2, "sched_standby")][0] == pytest.approx(0.125)
    assert s1.credits[(3, "sched_active")][0] == pytest.approx(0.5)
    s2 = settle([], [], led, 7200.0, P)
    assert set(s2.credits) == {(3, "sched_active")} and s2.credits[(3, "sched_active")][0] == pytest.approx(1.0)


def test_cache_accrual_is_per_gb_hour() -> None:
    s = settle([], [("cache", WorkerId(4), 1024.0 * 3600)], Ledger(), 1.0, P)
    assert s.credits[(4, "cache")][0] == pytest.approx(0.1)


RP = RepParams(half_life_s=3600.0, prior=(1.0, 2.0), quantile=0.05, probation_s=600.0, explore_floor=0.3)


def test_registered_variants() -> None:
    expected = {"beta_decay", "no_decay", "success_rate", "ewma", "survival_informed", "eigentrust_lite", "none"}
    assert expected <= set(REGISTRY.names("reputation"))


def test_beta_decay_returns_to_the_pessimistic_prior() -> None:
    rule = create("reputation", "beta_decay")
    s = rule.update(newcomer(0.0, RP), 0.0, 10.0, 0.0, RP)
    half = decayed(s, 3600.0, RP.half_life_s, RP.prior)
    assert half.alpha == pytest.approx(1.0 + 5.0) and half.beta == pytest.approx(2.0)
    far = rule.scores({1: s}, 1e7, RP)[1]
    assert far == pytest.approx(rule.scores({1: newcomer(0.0, RP)}, 0.0, RP)[1], abs=1e-6)
    keep = create("reputation", "no_decay").scores({1: s}, 1e7, RP)[1]
    assert keep > 0.5


def test_score_is_a_lower_bound_that_grows_with_evidence() -> None:
    rule = create("reputation", "beta_decay")
    small = rule.update(newcomer(0.0, RP), 0.0, 4.0, 1.0, RP)
    big = rule.update(newcomer(0.0, RP), 0.0, 40.0, 10.0, RP)
    sc = rule.scores({1: small, 2: big}, 0.0, RP)
    assert sc[1] < sc[2] < 41 / 53  # more evidence: a higher bound, still below the posterior mean
    bad = rule.update(big, 0.0, 0.0, 20.0, RP)
    assert rule.scores({3: bad}, 0.0, RP)[3] < sc[2]


def test_probation_floor_and_none() -> None:
    rule = create("reputation", "beta_decay")
    st = {1: newcomer(0.0, RP), 2: newcomer(-1000.0, RP)}
    tb = tie_break_scores(rule, st, 0.0, RP)
    assert tb[1] == 0.3 and tb[2] < 0.3  # only the identity still in probation gets the exploration floor
    assert tie_break_scores(create("reputation", "none"), st, 0.0, RP) == {1: 0.0, 2: 0.0}


def test_variants_order_good_above_bad() -> None:
    for name in ("beta_decay", "no_decay", "success_rate", "ewma", "survival_informed", "eigentrust_lite"):
        rule = create("reputation", name)
        good = rule.update(newcomer(0.0, RP), 1.0, 10.0, 1.0, RP)
        bad = rule.update(newcomer(0.0, RP), 1.0, 1.0, 10.0, RP)
        sc = rule.scores({1: good, 2: bad}, 1.0, RP)
        assert sc[1] > sc[2], name
        assert all(0.0 <= v <= 1.0 and math.isfinite(v) for v in sc.values()), name


def _plan_input(rep: np.ndarray | None) -> PlanInput:
    n = 4
    return PlanInput(
        now=0.0,
        horizon_s=60.0,
        workers=tuple(WorkerId(i) for i in range(n)),
        cap=np.full(n, 2.0),
        mem_mb=np.full(n, 2000.0),
        ssd_mb=np.full(n, 0.0),
        survival=np.ones(n),
        p_omit=np.zeros(n),
        assurance=np.full(n, 0.9),
        domain=np.arange(n),
        fresh_ok=np.ones(n, bool),
        tenants=(TenantId("t0"),),
        q=np.array([1.0]),
        rate=np.array([1.0]),
        sigma=np.array([1.0]),
        a_min=np.array([0.0]),
        f=np.array([0]),
        cold_penalty=np.array([10.0]),
        fns=(FnId("f0"),),
        fn_tenant=np.array([0]),
        fn_mem=np.array([256.0]),
        fn_size=np.array([100.0]),
        fn_benefit=np.array([0.0]),
        fn_units=np.array([0.0]),
        y_prev=np.zeros((1, n), bool),
        params=PlanParams(tie_break=0.02, use_domain_cap=False),
        rep=rep,
    )


def test_reputation_only_breaks_ties_in_the_planner() -> None:
    plain = GreedyPlanner().plan(_plan_input(None))
    assert plain.y[0].tolist() == [True, False, False, False]  # identical workers: first index
    rep = GreedyPlanner().plan(_plan_input(np.array([0.1, 0.2, 0.9, 0.3])))
    assert rep.y[0].tolist() == [False, False, True, False]
    worse = replace(_plan_input(np.array([0.0, 0.0, 1.0, 0.0])), assurance=np.array([0.9, 0.9, 0.85, 0.9]))
    assert not GreedyPlanner().plan(worse).y[0, 2]  # a real difference outweighs the tie-break
