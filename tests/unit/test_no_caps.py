"""D-112 and D-113 fallback: placement sees every eligible worker; provisioning pre-filters the plan."""

from __future__ import annotations

import numpy as np
from voss.core.config import VossConfig
from voss.core.ids import WorkerId
from voss.core.types import ClusterView
from voss.runtime.schedlib.planning import Planning, _hot

N = 120  # more than the old cap of 40 planned workers


def _view() -> ClusterView:
    return ClusterView(
        as_of=0.0,
        workers=tuple(WorkerId(i) for i in range(N)),
        slots=np.full(N, 2),
        busy=np.zeros(N, int),
        queued=np.zeros(N, int),
        mem_free_mb=np.full(N, 1e3),
        speed=np.ones(N),
        domain=np.arange(N),
        session_expiry=np.full(N, 1e4),
        age=np.zeros(N),
        draining=np.arange(N) % 10 == 0,
        cache=({},) * N,
        trust=(frozenset(),) * N,
        inflight=np.zeros(N, int),
        static=None,
        drain_deadline=(None,) * N,
    )


def test_the_planning_pool_is_capped_and_keeps_previous_holders() -> None:
    planning = Planning.__new__(Planning)
    planning.cfg = VossConfig()
    planning.prev = None
    idx = planning._workers(_view(), 0.0, 60.0)
    eligible = [i for i in range(N) if i % 10]
    assert len(idx) == planning.cfg.planner.max_plan_workers
    assert set(idx) <= set(eligible)


def test_the_function_pre_filter_is_capped_at_the_busiest() -> None:
    rates = {f"f{i:03d}": 1.0 + i for i in range(80)} | {"cold": 0.001}
    hot = _hot(rates, 50, 0.01)
    assert len(hot) == 50 and "cold" not in hot and hot[0] == "f079"
