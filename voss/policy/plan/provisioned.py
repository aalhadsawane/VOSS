"""``provisioned_keys`` baseline ("pre-released keys", docs/REVISION_PLAN.md V8): keys held ahead of demand, without
planning. It isolates *how many* holders from *which* holders.

For every hot key ``t`` the holder count ``N_t`` is the budget ``K`` when the tenant sets one; otherwise it is the
fewest holders whose expected contribution covers the demand quantile, ``ceil(q_t / mean_j contrib_j)``. It then holds
``t``'s key on the ``N_t`` eligible workers with the highest ``S_j(H)·(1 − p_j)`` (``PlanInput.contrib``), eligible =
freshness (``PlanInput.allowed``). What differs from VOSS is *which* workers: reliability only, with no per-worker run
times, deadline probabilities or preparation cost. Warm sandboxes and snapshots are not planned (``s = w = 0``); the
worker keep-alive TTL alone keeps sandboxes warm. Capacity ``c_tj`` is the tenant's demand spread evenly over its
holders (capped at the worker's slots); it only feeds the logged terms, never the placement. Slots are not shared out
between tenants, so a very reliable worker may hold several tenants' keys.
"""

from __future__ import annotations

import math

import numpy as np

from voss.core.registry import register
from voss.policy.plan.objective import finish
from voss.policy.plan.types import Plan, PlanInput


def most_reliable(score: np.ndarray, allowed: np.ndarray, n: int) -> np.ndarray:
    """``[J]`` bool: the ``n`` allowed workers with the highest ``score`` (stable: lower index wins ties)."""
    out = np.zeros(len(score), bool)
    ok = np.flatnonzero(allowed)
    order = ok[np.argsort(-score[ok], kind="stable")]
    out[order[:n]] = True
    return out


def holder_count(inp: PlanInput, t: int, allowed: np.ndarray) -> int:
    """``N_t``: the budget ``K`` if set, else the fewest allowed holders whose mean contribution covers ``q_t``."""
    if inp.max_holders is not None and int(inp.max_holders[t]) > 0:
        return int(inp.max_holders[t])
    e = inp.contrib()[allowed]
    n = max(1, math.ceil(float(inp.q[t]) / max(float(e.mean()) if len(e) else 0.0, 1e-6)))
    return min(n, len(e)) if len(e) else 0


@register("planner", "provisioned_keys")
class ProvisionedKeys:
    """Keys on the most reliable workers, holder count from the demand quantile (module docstring)."""

    def plan(self, inp: PlanInput) -> Plan:
        t, f, j = inp.shape
        y, c = np.zeros((t, j), bool), np.zeros((t, j))
        s, w = np.zeros((f, j), bool), np.zeros((f, j), int)
        if t and j:
            score, allowed = inp.contrib(), inp.allowed()
            for i in range(t):
                n = holder_count(inp, i, allowed[i])
                y[i] = most_reliable(score, allowed[i], n)
                if y[i].any():
                    c[i] = y[i] * np.minimum(inp.cap, float(inp.q[i]) / max(int(y[i].sum()), 1))
        return finish(inp, y, s, w, c, "provisioned_keys")
