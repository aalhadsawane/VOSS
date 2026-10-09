"""Routing prices a scheduler measures and reports on its cluster card (doc 03 §3, D-33): in-cluster overhead, the
cost actually paid when an attempt was trust-cold or started cold, and the backlog behind a full cluster."""

from __future__ import annotations

import math
from dataclasses import dataclass

from voss.core.types import Outcome

OVERHEAD_PRIOR_S = 0.0  # optimistic: an idle cluster must not look slower than a busy one it has not been compared to
ALPHA = 0.05


@dataclass
class Prices:
    """EWMAs over successful outcomes; priors (``voss.router`` config) until the cluster has seen any."""

    cold_trust: float
    cold_fn: float
    overhead: float = OVERHEAD_PRIOR_S

    def outcome(self, o: Outcome, in_cluster_s: float | None) -> None:
        """``in_cluster_s``: ENQUEUE receipt → DISPATCH of a sync attempt (``None`` for windowed classes, whose
        batching wait would make clusters serving more async work look slower)."""
        t = o.timings
        if in_cluster_s is not None:
            self.overhead += ALPHA * (in_cluster_s + t.wait - self.overhead)
        if o.trust_cold:
            self.cold_trust += ALPHA * (t.trust + t.startup - self.cold_trust)
        elif t.startup > 1e-3:
            self.cold_fn += ALPHA * (t.startup - self.cold_fn)

    def decay(self, dt: float) -> None:
        """Stale overhead fades to the (optimistic) prior so an idle cluster is not locked out by old or prior
        values: traffic it then receives measures it again."""
        self.overhead = OVERHEAD_PRIOR_S + (self.overhead - OVERHEAD_PRIOR_S) * math.exp(-dt / 60.0)


def backlog_s(load: float, svc_s: float) -> float:
    """Queued work per slot ahead of a new arrival in an over-full cluster (0 while slots are free)."""
    return svc_s * max(0.0, load - 1.0)
