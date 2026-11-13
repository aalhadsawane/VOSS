"""``provisioned_keys`` baseline ("pre-released keys", docs/REVISION_PLAN.md V8): keys held ahead of demand, without
planning. It isolates *how many* holders from *which* holders.

For every hot key ``t`` the holder count ``N_t`` is the budget ``K`` when the tenant sets one; otherwise the planner
asks ``greedy`` what it would do on the same input and takes ``N_t = Σ_j y_tj``. It then holds ``t``'s key on the
``N_t`` eligible workers with the highest ``S_j(H)·(1 − p_j)`` (``PlanInput.contrib``), eligible = assurance floor and
freshness (``PlanInput.allowed``). Equal ``N_t`` means the key-holder count, and so roughly the exposure, matches
greedy; what differs is *which* workers: reliability only, with no robust coverage, no failure-domain cap, no exposure
or memory trade-off. Warm sandboxes and snapshots are not planned (``s = w = 0``); the worker keep-alive TTL alone keeps
sandboxes warm. Capacity ``c_tj`` is greedy's total for ``t`` split evenly over its holders (capped at the worker's
slots); it only feeds the logged objective, never the placement. Slots are not shared out between tenants, so a very
reliable worker may hold several tenants' keys.
"""

from __future__ import annotations

import numpy as np

from voss.core.registry import register
from voss.policy.plan.greedy import GreedyPlanner
from voss.policy.plan.objective import finish
from voss.policy.plan.types import Plan, PlanInput


def most_reliable(score: np.ndarray, allowed: np.ndarray, n: int) -> np.ndarray:
    """``[J]`` bool: the ``n`` allowed workers with the highest ``score`` (stable: lower index wins ties)."""
    out = np.zeros(len(score), bool)
    ok = np.flatnonzero(allowed)
    order = ok[np.argsort(-score[ok], kind="stable")]
    out[order[:n]] = True
    return out


@register("planner", "provisioned_keys")
class ProvisionedKeys:
    """Keys on the most reliable workers, holder count borrowed from greedy (module docstring)."""

    def __init__(self) -> None:
        self._greedy = GreedyPlanner()

    def plan(self, inp: PlanInput) -> Plan:
        t, f, j = inp.shape
        y, c = np.zeros((t, j), bool), np.zeros((t, j))
        s, w = np.zeros((f, j), bool), np.zeros((f, j), int)
        if t and j:
            ref = self._greedy.plan(inp)
            score, allowed = inp.contrib(), inp.allowed()
            for i in range(t):
                k = None if inp.max_holders is None else int(inp.max_holders[i])
                n = k if k else int(ref.y[i].sum())  # plan V8: the full budget K when the tenant sets one
                y[i] = most_reliable(score, allowed[i], n)
                if y[i].any():
                    c[i] = y[i] * np.minimum(inp.cap, ref.c[i].sum() / y[i].sum())
        return finish(inp, y, s, w, c, "provisioned_keys")
