"""Hedging (doc 03 §5.4, doc 07 §4): a tied duplicate on another failure domain when ``pMiss`` is high.

Policies: ``off``, ``always`` and ``risk_proportional`` (default θ = 0.2). Only idempotent invocations are hedged;
the scheduler enforces the budget (fraction of placements) with a token bucket.
"""

from __future__ import annotations

from collections.abc import Callable

import numpy as np

from voss.core.registry import register
from voss.core.types import ClusterView, Invocation

HedgeFn = Callable[[Invocation, np.ndarray, np.ndarray, np.ndarray, np.ndarray, int, ClusterView], int | None]


def _other_domain(chosen: int, cand: np.ndarray, feas: np.ndarray, scores: np.ndarray, view: ClusterView) -> int | None:
    dom = view.domain[chosen]
    best, best_cost = None, np.inf
    for k, j in enumerate(cand):
        if feas[k] and int(j) != chosen and view.domain[int(j)] != dom and scores[k] < best_cost:
            best, best_cost = int(j), float(scores[k])
    return best


@register("hedge", "off")
def hedge_off(
    inv: Invocation,
    cand: np.ndarray,
    feas: np.ndarray,
    scores: np.ndarray,
    p_miss: np.ndarray,
    chosen: int,
    view: ClusterView,
    theta: float = 0.2,
) -> int | None:
    return None


@register("hedge", "always")
def hedge_always(
    inv: Invocation,
    cand: np.ndarray,
    feas: np.ndarray,
    scores: np.ndarray,
    p_miss: np.ndarray,
    chosen: int,
    view: ClusterView,
    theta: float = 0.2,
) -> int | None:
    return _other_domain(chosen, cand, feas, scores, view) if inv.idempotent else None


@register("hedge", "risk_proportional")
def hedge_risk(
    inv: Invocation,
    cand: np.ndarray,
    feas: np.ndarray,
    scores: np.ndarray,
    p_miss: np.ndarray,
    chosen: int,
    view: ClusterView,
    theta: float = 0.2,
) -> int | None:
    k = int(np.flatnonzero(cand == chosen)[0]) if (cand == chosen).any() else -1
    if not inv.idempotent or k < 0 or p_miss[k] <= theta:
        return None
    return _other_domain(chosen, cand, feas, scores, view)


class TokenBucket:
    """Budget as a fraction of placements (``rate`` tokens per placement, capped)."""

    def __init__(self, rate: float, cap: float = 20.0) -> None:
        self.rate, self.cap, self.tokens = rate, cap, min(cap, 1.0)

    def earn(self) -> None:
        self.tokens = min(self.cap, self.tokens + self.rate)

    def take(self) -> bool:
        if self.tokens >= 1.0:
            self.tokens -= 1.0
            return True
        return False
