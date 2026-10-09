"""P5 exit: bounded migrations per worker per hour under arbitrary churn and load (doc 03 §2 hysteresis).

Drives the pure trigger policy through a small orchestrator model (joins, leaves, random summaries) and checks that
no worker is moved more than ``max_moves_per_h`` times in any one-hour window.
"""

from __future__ import annotations

import numpy as np
from hypothesis import given, settings
from hypothesis import strategies as st
from voss.core.rng import RngFactory
from voss.policy.orchestrate import ClusterInfo, ClusterParams, form_clusters, great_circle, nearest_cluster
from voss.policy.orchestrate_triggers import NEW_CLUSTER, Member, step

P = ClusterParams(target_size=8, min_size=3, max_size=14, d_min=2, dwell_s=120.0, max_moves=6, max_moves_per_h=2)


class Model:
    def __init__(self, seed: int, n: int) -> None:
        self.g = RngFactory(seed).stream("test.migrations")
        self.lat, self.lon = self.g.uniform(-50, 60, 3 * n), self.g.uniform(-120, 140, 3 * n)
        self.dom = self.g.integers(0, 5, 3 * n)
        labels, _ = form_clusters(self.lat[:n], self.lon[:n], self.dom[:n], P)
        self.of = {w: int(labels[w]) for w in range(n)}
        self.since = dict.fromkeys(range(n), 0.0)
        self.moves: dict[int, list[float]] = {}
        self.next = int(labels.max()) + 1
        self.idle = list(range(n, 3 * n))

    def infos(self) -> list[ClusterInfo]:
        out = []
        for c in sorted(set(self.of.values())):
            ws = {w for w, x in self.of.items() if x == c}
            med = (float(self.lat[list(ws)].mean()), float(self.lon[list(ws)].mean()))
            slo = float(self.g.uniform(0, 0.5))
            out.append(ClusterInfo(c, ws, med, float(self.g.uniform(0, 2)), slo, int(self.g.integers(0, 5))))
        return out

    def members(self, now: float) -> dict[int, Member]:
        def recent(w: int) -> int:
            return sum(1 for t in self.moves.get(w, []) if now - t < 3600.0)

        return {
            w: Member(self.lat[w], self.lon[w], int(self.dom[w]), 4, self.since[w], recent(w)) for w in sorted(self.of)
        }

    def churn(self, now: float) -> None:
        for w in sorted(self.of):
            if self.g.random() < 0.02:
                del self.of[w]
                self.idle.append(w)
        for _ in range(int(self.g.integers(0, 3))):
            if self.idle:
                w = self.idle.pop(int(self.g.integers(0, len(self.idle))))
                c = nearest_cluster(self.lat[w], self.lon[w], self.infos(), P.max_size)
                self.of[w], self.since[w] = (c if c is not None else self._new()), now

    def _new(self) -> int:
        self.next += 1
        return self.next - 1

    def period(self, now: float) -> None:
        new = None
        for op in step(self.infos(), self.members(now), now, P):
            if op.worker not in self.of:
                continue
            if op.dst == NEW_CLUSTER and new is None:
                new = self._new()
            self.of[op.worker] = new if op.dst == NEW_CLUSTER else op.dst  # type: ignore[assignment]
            self.since[op.worker] = now
            self.moves.setdefault(op.worker, []).append(now)


@settings(max_examples=15, deadline=None)
@given(seed=st.integers(0, 10_000), n=st.integers(20, 60))
def test_moves_per_worker_per_hour_are_bounded(seed: int, n: int) -> None:
    m = Model(seed, n)
    for k in range(1, 300):  # 300 periods × 30 s = 2.5 h
        now = 30.0 * k
        m.churn(now)
        m.period(now)
    for times in m.moves.values():
        t = np.array(times)
        for a in t:
            assert ((t >= a) & (t < a + 3600.0)).sum() <= P.max_moves_per_h


def test_great_circle_is_symmetric() -> None:
    a = great_circle(np.array([10.0]), np.array([20.0]), -30.0, 100.0)[0]
    b = great_circle(np.array([-30.0]), np.array([100.0]), 10.0, 20.0)[0]
    assert abs(a - b) < 1e-6
