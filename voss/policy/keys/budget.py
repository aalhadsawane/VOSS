"""Holder budget ``K`` per function key (D-85, docs/REVISION_PLAN.md V4): the one place provisioning and placement
apply it. The tenant's key service enforces the same budget, so a plan that exceeded it would only be refused.
"""

from __future__ import annotations

import numpy as np

UNBOUNDED = 0  # in arrays of budgets, 0 means no budget


def may_add_holder(holders_now: int, k: int | None) -> bool:
    """Whether one more worker may receive the key."""
    return k is None or k == UNBOUNDED or holders_now < k


def truncate(y: np.ndarray, c: np.ndarray, y_prev: np.ndarray, k: np.ndarray) -> np.ndarray:
    """``[T, J]`` holder sets cut to at most ``k[t]`` per key (``0`` = no limit). Existing holders are kept first
    (a key in hand costs no release), then the workers with the most reserved concurrency ``c``; ties by index."""
    out = y.astype(bool).copy()
    for t in range(out.shape[0]):
        kt = int(k[t]) if len(k) else UNBOUNDED
        held = np.flatnonzero(out[t])
        if kt == UNBOUNDED or len(held) <= kt:
            continue
        order = sorted(held, key=lambda j: (not bool(y_prev[t, j]), -float(c[t, j]), int(j)))
        out[t] = False
        out[t, order[:kt]] = True
    return out
