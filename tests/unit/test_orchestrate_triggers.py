"""P5: orchestrator triggers (doc 03 §2): merge, split, SLO borrow, imbalance, diversity, hysteresis."""

from __future__ import annotations

from voss.policy.orchestrate import ClusterInfo, ClusterParams
from voss.policy.orchestrate_triggers import (
    NEW_CLUSTER,
    Member,
    borrow,
    fix_diversity,
    merge_small,
    split_large,
    step,
)

P = ClusterParams(target_size=10, min_size=4, max_size=12, d_min=2, dwell_s=100.0, max_moves=3, max_moves_per_h=2)


def _members(ws: range, lat: float, lon: float, domain: int = 0, since: float = 0.0) -> dict[int, Member]:
    return {w: Member(lat + 0.01 * (w % 7), lon, domain + w % 3, 4, since) for w in ws}


def test_merge_small_into_nearest_with_room() -> None:
    m = _members(range(0, 3), 51.5, 0.0) | _members(range(10, 18), 48.9, 2.3) | _members(range(20, 28), 40.7, -74)
    cl = [ClusterInfo(0, set(range(0, 3)), (51.5, 0.0)), ClusterInfo(1, set(range(10, 18)), (48.9, 2.3))]
    cl.append(ClusterInfo(2, set(range(20, 28)), (40.7, -74.0)))
    ops = merge_small(cl, m, P)
    assert {o.worker for o in ops} == {0, 1, 2} and {o.dst for o in ops} == {1}


def test_merge_respects_migration_budget() -> None:
    m = _members(range(0, 3), 51.5, 0.0) | _members(range(10, 18), 48.9, 2.3)
    m[1] = Member(51.5, 0.0, 1, 4, 0.0, recent_moves=2)
    cl = [ClusterInfo(0, set(range(0, 3)), (51.5, 0.0)), ClusterInfo(1, set(range(10, 18)), (48.9, 2.3))]
    assert merge_small(cl, m, P) == []


def test_split_large_moves_one_side_to_new_cluster() -> None:
    m = _members(range(0, 7), 51.5, 0.0) | _members(range(7, 14), 40.7, -74.0)
    ops = split_large([ClusterInfo(0, set(range(14)), (45.0, -30.0))], m, P)
    moved = {o.worker for o in ops}
    assert all(o.dst == NEW_CLUSTER for o in ops)
    assert moved in (set(range(0, 7)), set(range(7, 14)))


def test_borrow_needs_dwell_and_unhealthy_or_imbalanced() -> None:
    m = _members(range(0, 6), 51.5, 0.0) | _members(range(10, 18), 48.9, 2.3)
    sick = ClusterInfo(0, set(range(0, 6)), (51.5, 0.0), load=0.5, slo_miss=0.5, bad_periods=3)
    donor = ClusterInfo(1, set(range(10, 18)), (48.9, 2.3), load=0.5)
    ops = borrow([sick, donor], m, now=200.0, p=P)
    assert len(ops) == 1 and ops[0].src == 1 and ops[0].dst == 0 and ops[0].reason == "slo"
    assert borrow([sick, donor], m, now=50.0, p=P) == []  # dwell not over
    calm = ClusterInfo(0, set(range(0, 6)), (51.5, 0.0), load=0.5)
    assert borrow([calm, donor], m, now=200.0, p=P) == []
    hot = ClusterInfo(0, set(range(0, 6)), (51.5, 0.0), load=1.5)
    assert borrow([hot, donor], m, now=200.0, p=P)[0].reason == "imbalance"


def test_fix_diversity_pulls_new_domain() -> None:
    m = {w: Member(51.5, 0.0, 9, 4, 0.0) for w in range(0, 5)} | _members(range(10, 18), 48.9, 2.3)
    lone = ClusterInfo(0, set(range(0, 5)), (51.5, 0.0))
    donor = ClusterInfo(1, set(range(10, 18)), (48.9, 2.3))
    ops = fix_diversity([lone, donor], m, now=200.0, p=P)
    assert len(ops) == 1 and m[ops[0].worker].domain != 9 and ops[0].dst == 0


def test_step_caps_moves_and_one_per_worker() -> None:
    m = _members(range(0, 6), 51.5, 0.0) | _members(range(10, 22), 48.9, 2.3) | _members(range(30, 42), 52.5, 13.4)
    cl = [
        ClusterInfo(0, set(range(0, 6)), (51.5, 0.0), load=2.0, slo_miss=0.9, bad_periods=5),
        ClusterInfo(1, set(range(10, 22)), (48.9, 2.3), load=0.1),
        ClusterInfo(2, set(range(30, 42)), (52.5, 13.4), load=0.1),
    ]
    ops = step(cl, m, now=1000.0, p=P)
    assert 0 < len(ops) <= P.max_moves
    assert len({o.worker for o in ops}) == len(ops)


def test_forecast_overload_pre_moves_from_neighbour_with_headroom() -> None:
    m = _members(range(0, 6), 51.5, 0.0) | _members(range(10, 18), 48.9, 2.3)
    busy_soon = ClusterInfo(0, set(range(0, 6)), (51.5, 0.0), load=0.5, forecast=1.4)
    donor = ClusterInfo(1, set(range(10, 18)), (48.9, 2.3), load=0.5, forecast=0.3)
    ops = borrow([busy_soon, donor], m, now=200.0, p=P)
    assert len(ops) == 1 and ops[0].reason == "forecast" and ops[0].dst == 0
    donor_busy = ClusterInfo(1, set(range(10, 18)), (48.9, 2.3), load=0.5, forecast=1.2)
    assert borrow([busy_soon, donor_busy], m, now=200.0, p=P) == []
