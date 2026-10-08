"""Immutable cluster views for policies (doc 01 §5): frozen struct-of-arrays snapshots with per-worker age."""

from __future__ import annotations

from collections.abc import Iterable, Mapping

import numpy as np

from voss.core.ids import WorkerId
from voss.core.types import ClusterView
from voss.observe.statestore import StateStore


def build_view(
    store: StateStore, members: Iterable[WorkerId], now: float, inflight: Mapping[WorkerId, int]
) -> ClusterView:
    """Snapshot of ``members`` that have reported at least once, in sorted worker order."""
    ws = sorted(w for w in members if w in store)
    st = [store.states[w] for w in ws]
    return ClusterView(
        as_of=now,
        workers=tuple(ws),
        slots=np.array([s.slots for s in st], dtype=np.int64),
        busy=np.array([s.busy for s in st], dtype=np.int64),
        queued=np.array([s.queued for s in st], dtype=np.int64),
        mem_free_mb=np.array([s.mem_free_mb for s in st], dtype=float),
        speed=np.array([s.speed for s in st], dtype=float),
        assurance=np.array([s.assurance for s in st], dtype=float),
        domain=np.array([s.domain for s in st], dtype=np.int64),
        session_expiry=np.array([s.session_expiry for s in st], dtype=float),
        age=np.array([now - s.as_of for s in st], dtype=float),
        draining=np.array([s.drain_deadline is not None for s in st], dtype=bool),
        cache=tuple(s.cache for s in st),
        trust=tuple(s.trust for s in st),
        inflight=np.array([inflight.get(w, 0) for w in ws], dtype=np.int64),
    )
