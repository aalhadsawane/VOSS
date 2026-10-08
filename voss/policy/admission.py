"""Admission and filler gating (doc 03 §5.4).

If no candidate has ``pMiss < 1 − ε`` the invocation is rejected (sync) or deferred (async). Filler work only uses
slots idle beyond a sync headroom and is preempted by sync work.
"""

from __future__ import annotations

import numpy as np

from voss.core.types import ClusterView, Invocation, SloClass


def admit(
    inv: Invocation,
    p_miss_row: np.ndarray,
    feasible_row: np.ndarray,
    wait_row: np.ndarray,
    budget: float,
    eps: float = 0.05,
) -> str:
    """``admit`` | ``reject`` | ``defer``.

    Doc 03 §5.4 with D-27: a hopeless invocation (every candidate has ``pMiss ≥ 1 − ε``) is rejected (sync) or
    deferred (async) only when the miss is caused by overload, i.e. even the shortest slot wait exceeds the remaining
    budget. Misses caused by cold start-up are admitted: they warm the caches that later invocations need.
    """
    if not feasible_row.any():
        return "defer"
    if (feasible_row & (p_miss_row < 1 - eps)).any():
        return "admit"
    overloaded = float(np.min(np.where(feasible_row, wait_row, np.inf))) > budget
    if not overloaded:
        return "admit"
    return "reject" if inv.slo_class == SloClass.SYNC else "defer"


def filler_mask(view: ClusterView, headroom: int = 1) -> np.ndarray:
    """Workers with more than ``headroom`` idle slots (filler may only use those)."""
    free = view.slots - (view.busy + view.queued + view.inflight)
    out: np.ndarray = free > headroom
    return out
