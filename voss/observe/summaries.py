"""Cluster summaries for routers and the orchestrator (doc 03 §3, doc 08 §4 ``KEEPALIVE+SUMMARY``)."""

from __future__ import annotations

from voss.core.ids import ClusterId, TenantId
from voss.core.types import ClusterSummary, ClusterView


def summarize(cluster: ClusterId, view: ClusterView, slo_health: float = 1.0) -> ClusterSummary:
    slots = int(view.slots.sum())
    used = int((view.busy + view.queued + view.inflight).sum())
    trust: dict[TenantId, float] = {}
    for i, ts in enumerate(view.trust):
        for t in sorted(ts):
            trust[t] = trust.get(t, 0.0) + float(view.slots[i])
    return ClusterSummary(
        cluster=cluster,
        as_of=view.as_of,
        load=used / slots if slots else 1.0,
        slo_health=slo_health,
        attested=len(view),
        free_slots=max(0, slots - used),
        trust_warm_capacity=trust,
        diversity=len(set(view.domain.tolist())),
    )
