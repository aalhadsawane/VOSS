"""D-112 and D-113: placement and provisioning see every eligible worker and every active function, with no caps."""

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


def test_every_live_worker_is_planned() -> None:
    planning = Planning.__new__(Planning)
    planning.cfg = VossConfig()
    idx = planning._workers(_view(), 0.0, 60.0)
    assert list(idx) == [i for i in range(N) if i % 10]  # all but the draining ones, whatever their reliability


def test_every_function_above_the_minimum_rate_is_planned() -> None:
    rates = {f"f{i:03d}": 1.0 + i for i in range(80)} | {"cold": 0.001}
    hot = _hot(rates, 0.01)
    assert len(hot) == 80 and "cold" not in hot and hot[0] == "f079"
