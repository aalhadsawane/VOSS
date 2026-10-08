"""Property (roadmap P3 exit): ``flow == ilp_window`` on uncoupled instances (equal optimal objective)."""

from __future__ import annotations

import numpy as np
from hypothesis import given, settings
from hypothesis import strategies as st
from voss.core.ids import FnId, InvId, TenantId, WorkerId
from voss.core.rng import stream
from voss.core.types import ClusterView, Invocation, SloClass
from voss.policy.cost.completion import Completion
from voss.policy.cost.components import CostMatrix
from voss.policy.place.base import PlaceRequest
from voss.policy.place.flow import FlowPlacer, IlpWindowPlacer


def _req(n_inv: int, n_w: int, k: int, seed: int) -> PlaceRequest:
    g = stream(seed, "flow")
    k = min(k, n_w)
    cand = np.array([g.permutation(n_w)[:k] for _ in range(n_inv)])
    feas = g.random((n_inv, k)) < 0.85
    scores = g.uniform(0, 10, (n_inv, k))
    step = g.uniform(0, 3, (n_inv, k))
    z = np.zeros((n_inv, k))
    cm = CostMatrix({}, cand, feas, Completion(z, z, z + 1), z, z)
    view = ClusterView(
        0.0,
        tuple(WorkerId(i) for i in range(n_w)),
        *(np.zeros(n_w),) * 10,
        cache=({},) * n_w,
        trust=(frozenset(),) * n_w,
    )
    invs = tuple(Invocation(InvId(i), FnId("f"), TenantId("t"), 0, 0.0, 1, SloClass.ASYNC, 1.0) for i in range(n_inv))
    return PlaceRequest(invs, view, 0.0, g, cm=cm, scores=scores, slot_step=step)


@settings(max_examples=60, deadline=None)
@given(n_inv=st.integers(1, 8), n_w=st.integers(1, 6), k=st.integers(1, 5), seed=st.integers(0, 10_000))
def test_flow_matches_ilp(n_inv: int, n_w: int, k: int, seed: int) -> None:
    req = _req(n_inv, n_w, k, seed)
    flow, ilp = FlowPlacer(slots_per_worker=3), IlpWindowPlacer(slots_per_worker=3)
    a, b = flow.place(req), ilp.place(req)
    assert len(a.assign) == len(b.assign)
    assert abs(flow.last_objective - ilp.last_objective) < 1e-6
