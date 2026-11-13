"""Sampled audit policy (docs/REVISION_PLAN.md V7.3)."""

from __future__ import annotations

from voss.core.ids import WorkerId
from voss.core.rng import stream
from voss.policy.audit import minority, select, target

W = [WorkerId(i) for i in range(6)]


def test_only_idempotent_invocations_are_audited() -> None:
    g = stream(1, "t")
    assert not any(select(False, g, 1.0) for _ in range(20))
    assert all(select(True, g, 1.0) for _ in range(20))
    assert not select(True, g, 0.0)


def test_target_is_a_holder_outside_used_domains() -> None:
    dom = [0, 0, 1, 1, 2, 2]
    hold = [True, True, True, False, False, True]
    for s in range(20):
        t = target(W, dom, hold, {W[0]}, stream(s, "t"))
        assert t in (W[2], W[5])
    assert target(W, dom, hold, {W[0], W[2], W[5]}, stream(1, "t")) is None


def test_minority_needs_a_strict_majority() -> None:
    assert minority({W[0]: 1, W[1]: 1}) == []
    assert minority({W[0]: 1, W[1]: 2}) is None
    assert minority({W[0]: 1, W[1]: 2, W[2]: 1}) == [W[1]]
