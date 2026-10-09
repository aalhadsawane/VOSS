"""Baseline placers on hand-built views (doc 05 §9 recipe)."""

from __future__ import annotations

import numpy as np
from voss.core.ids import FnId, InvId, TenantId, WorkerId
from voss.core.registry import create
from voss.core.rng import stream
from voss.core.types import ClusterView, Invocation, SloClass
from voss.policy.place import baselines  # noqa: F401
from voss.policy.place.base import PlaceRequest


def view(n: int = 4, busy: list[int] | None = None) -> ClusterView:
    b = np.array(busy if busy is not None else [0] * n)
    return ClusterView(
        as_of=0.0,
        workers=tuple(WorkerId(i) for i in range(n)),
        slots=np.full(n, 2),
        busy=b,
        queued=np.zeros(n, int),
        mem_free_mb=np.full(n, 1000.0),
        speed=np.ones(n),
        assurance=np.full(n, 0.8),
        domain=np.arange(n),
        session_expiry=np.full(n, 1000.0),
        age=np.zeros(n),
        draining=np.zeros(n, bool),
        cache=({},) * n,
        trust=(frozenset(),) * n,
        inflight=np.zeros(n, int),
    )


def inv(i: int, excluded: frozenset[WorkerId] = frozenset()) -> Invocation:
    return Invocation(InvId(i), FnId("f"), TenantId("t"), 0, 0.0, 10, SloClass.SYNC, 1.0, excluded=excluded)


def test_least_loaded_balances_and_respects_exclusion() -> None:
    p = create("placer", "least_loaded")
    req = PlaceRequest((inv(0), inv(1), inv(2)), view(busy=[2, 0, 1, 0]), 0.0, stream(1, "p"))
    a = p.place(req).assign
    assert a[InvId(0)] == WorkerId(1) and a[InvId(1)] == WorkerId(3) and a[InvId(2)] in (WorkerId(1), WorkerId(3))
    req = PlaceRequest((inv(5, frozenset({WorkerId(1), WorkerId(3)})),), view(busy=[2, 0, 1, 0]), 0.0, stream(1, "p"))
    assert p.place(req).assign[InvId(5)] == WorkerId(2)


def test_expiring_and_draining_workers_are_skipped() -> None:
    v = view()
    v = ClusterView(
        **{
            **v.__dict__,
            "session_expiry": np.array([1.0, 1000, 1000, 1000]),
            "draining": np.array([False, True, False, True]),
        }
    )
    for name in ("random", "least_loaded"):
        got = {
            create("placer", name).place(PlaceRequest((inv(i),), v, 0.0, stream(i, "p"))).assign[InvId(i)]
            for i in range(20)
        }
        assert got == {WorkerId(2)}


def test_no_candidate_is_partial() -> None:
    v = view(n=1)
    pl = create("placer", "random").place(PlaceRequest((inv(0, frozenset({WorkerId(0)})),), v, 0.0, stream(1, "p")))
    assert pl.status == "partial" and not pl.assign


def test_k8s_default_spreads_and_binpack_packs() -> None:
    """kube-scheduler profiles: LeastAllocated + topology spread vs MostAllocated bin-packing."""
    reqs = (inv(0), inv(1), inv(2))
    got = create("placer", "k8s_default").place(PlaceRequest(reqs, view(busy=[1, 0, 0, 0]), 0.0, stream(1, "p")))
    assert len(set(got.assign.values())) == 3 and WorkerId(0) not in got.assign.values()
    packed = create("placer", "k8s_binpack").place(PlaceRequest(reqs, view(busy=[1, 0, 0, 0]), 0.0, stream(1, "p")))
    assert packed.assign[InvId(0)] == WorkerId(0)  # the fullest feasible node first
    assert len(set(packed.assign.values())) <= 2
