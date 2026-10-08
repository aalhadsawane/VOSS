"""Cost matrix, completion distribution and scalarizers on hand-built views (doc 03 §5.2)."""

from __future__ import annotations

from dataclasses import replace

import numpy as np
import pytest
from voss.core.ids import FnId, InvId, TenantId, WorkerId
from voss.core.types import CacheEntry, ClusterView, Invocation, SloClass, WorkerStatic
from voss.policy.admission import admit
from voss.policy.cost.completion import moment_match, p_miss
from voss.policy.cost.components import Preds, build_cost_matrix
from voss.policy.cost.inputs import CostContext, FnInfo, StartupModel, TenantInfo
from voss.policy.cost.scalarize import SCALARIZERS

N = 4
CTX = CostContext(
    startup={"appliance_tpm": StartupModel(0.15, 0.02, 0.002, 0.002, 0.0007, 0.3)},
    fns={"f": FnInfo("f", "t", 128, 10, 100, 50, 0.5, 1000, True)},
    tenants={"t": TenantInfo(1.0, 50.0, 8.0, 0.0)},
    registry=(50.0, 8.0),
    routers={"r": (50.0, 8.0)},
    K=3,
)


def view() -> ClusterView:
    st = WorkerStatic(50.0, 8.0, 1.0, "idle", "appliance_tpm", 1e8, 2e7, 2000, 150, 0.0)
    cache = ({"f": CacheEntry("L3", "ram", 1)}, {"f": CacheEntry("L2", "ssd")}, {}, {"f": CacheEntry("L1", "hdd")})
    return ClusterView(
        as_of=0.0,
        workers=tuple(WorkerId(i) for i in range(N)),
        slots=np.full(N, 2),
        busy=np.array([0, 0, 0, 2]),
        queued=np.zeros(N, int),
        mem_free_mb=np.full(N, 1e3),
        speed=np.ones(N),
        assurance=np.full(N, 0.8),
        domain=np.arange(N),
        session_expiry=np.full(N, 1e4),
        age=np.zeros(N),
        draining=np.zeros(N, bool),
        cache=cache,
        trust=(frozenset({TenantId("t")}), frozenset(), frozenset(), frozenset()),
        inflight=np.zeros(N, int),
        static=(st,) * N,
        drain_deadline=(None,) * N,
    )


def preds() -> Preds:
    return Preds(np.full((1, N), 0.5), np.full((1, N), 0.01), np.ones((1, N)), np.zeros(N), np.full(N, 0.5))


def inv(deadline: float = 2.0) -> Invocation:
    return Invocation(InvId(0), FnId("f"), TenantId("t"), 0, 0.0, 1000, SloClass.SYNC, deadline)


def test_components_follow_the_ladder_and_trust() -> None:
    cm = build_cost_matrix((inv(),), view(), CTX, preds(), 0.0, ("r",))
    assert cm.candidates.shape == (1, 3)  # top-K pruning
    by = {int(j): k for k, j in enumerate(cm.candidates[0])}
    c = cm.components
    assert by and 0 in by
    assert c["trust"][0, by[0]] == 0 and c["exposure"][0, by[0]] == 0  # trust-warm worker
    if 1 in by:
        assert c["trust"][0, by[1]] > 0 and c["exposure"][0, by[1]] == pytest.approx(0.2)
        assert c["startup"][0, by[0]] < c["startup"][0, by[1]]  # L3 < L2
    assert ((cm.p_miss >= 0) & (cm.p_miss <= 1)).all()
    assert int(cm.candidates[0, 0]) == 0  # the warm, trusted, idle worker is the best bound


def test_full_worker_waits() -> None:
    cm = build_cost_matrix((inv(),), view(), replace(CTX, K=4), preds(), 0.0, ("r",))
    k = list(cm.candidates[0]).index(3)
    assert cm.components["wait"][0, k] > 0


def test_scalarizers_finite_on_feasible() -> None:
    cm = build_cost_matrix((inv(),), view(), CTX, preds(), 0.0, ("r",))
    for name, f in SCALARIZERS.items():
        s = f(cm, (inv(),), CTX)
        assert np.isfinite(s[cm.feasible]).all(), name


def test_completion_and_pmiss() -> None:
    c = moment_match(np.array([1.0]), np.array([0.01]), np.array([1.0]), np.array([0.25]))
    assert float(c.mean()[0]) == pytest.approx(2.0, rel=1e-6)
    assert float(c.sf(np.array([0.1]))[0]) == 1.0
    assert float(p_miss(c, np.array([100.0]), np.array([0.1]))[0]) == pytest.approx(0.1, abs=1e-3)
    assert float(c.quantile(0.99)[0]) > float(c.quantile(0.5)[0])


def test_admission_rejects_only_overload() -> None:
    hopeless = np.array([0.99, 0.99])
    feas = np.array([True, True])
    assert admit(inv(), hopeless, feas, np.array([0.0, 0.0]), 1.0) == "admit"  # cold start, not overload
    assert admit(inv(), hopeless, feas, np.array([5.0, 9.0]), 1.0) == "reject"
    assert admit(replace(inv(), slo_class=SloClass.ASYNC), hopeless, feas, np.array([5.0, 9.0]), 1.0) == "defer"
    assert admit(inv(), np.array([0.5, 0.99]), feas, np.zeros(2), 1.0) == "admit"
