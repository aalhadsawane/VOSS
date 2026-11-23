"""Placement order (doc 03 §5.2, D-110): lowest probability of missing the deadline first, ties broken by the lowest
expected completion. Lexicographic, so there is no weight between the two; infeasible entries are +inf in both.
"""

from __future__ import annotations

import numpy as np

from voss.policy.cost.components import CostMatrix


def placement_keys(cm: CostMatrix) -> tuple[np.ndarray, np.ndarray]:
    """``(pMiss, E[C])`` per (invocation, candidate): the primary and the tie-break key, +inf where infeasible."""
    primary: np.ndarray = np.where(cm.feasible, cm.p_miss, np.inf)
    tiebreak: np.ndarray = np.where(cm.feasible, cm.completion.mean(), np.inf)
    return primary, tiebreak
