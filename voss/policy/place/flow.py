"""``flow`` placer (doc 03 §5.3, async/filler windows) and the ``ilp_window`` baseline.

Both solve the same min-cost assignment of window invocations to ``(worker, slot)`` columns, where the r-th extra
invocation on a worker costs ``score + r·slot_step``. ``flow`` uses the polynomial assignment algorithm; ``ilp_window``
solves it as a MILP (the old per-window ILP, kept to show the split is better). On these uncoupled instances both are
optimal, so their objectives match (property test).
"""

from __future__ import annotations

import numpy as np
from scipy.optimize import Bounds, LinearConstraint, linear_sum_assignment, milp

from voss.core.registry import register
from voss.core.types import Placement
from voss.policy.place.base import PlaceRequest, placement

BIG = 1e9


def expanded(req: PlaceRequest, slots_per_worker: int) -> tuple[np.ndarray, list[int]]:
    """Cost matrix ``[I, W·m]`` over (worker, slot rank) columns and the worker of each column."""
    if req.cm is None or req.scores is None:
        raise ValueError("flow placers need a cost matrix and scores")
    cm, scores = req.cm, req.scores
    step = req.slot_step if req.slot_step is not None else np.zeros_like(scores)
    workers = sorted({int(j) for j in cm.candidates.ravel()})
    col = {w: c for c, w in enumerate(workers)}
    m = max(1, min(slots_per_worker, len(req.invs)))
    cost = np.full((len(req.invs), len(workers) * m), BIG)
    for i in range(len(req.invs)):
        for k, j in enumerate(cm.candidates[i]):
            if cm.feasible[i, k] and np.isfinite(scores[i, k]):
                base = col[int(j)] * m
                cost[i, base : base + m] = scores[i, k] + step[i, k] * np.arange(m)
    return cost, [w for w in workers for _ in range(m)]


def objective(cost: np.ndarray, rows: np.ndarray, cols: np.ndarray) -> float:
    return float(sum(cost[r, c] for r, c in zip(rows, cols, strict=True) if cost[r, c] < BIG))


@register("placer", "flow")
class FlowPlacer:
    def __init__(self, slots_per_worker: int = 4) -> None:
        self.m = slots_per_worker
        self.last_objective = 0.0

    def place(self, req: PlaceRequest) -> Placement:
        cost, owner = expanded(req, self.m)
        rows, cols = linear_sum_assignment(cost)
        self.last_objective = objective(cost, rows, cols)
        return placement(req, {int(r): owner[c] for r, c in zip(rows, cols, strict=True) if cost[r, c] < BIG})


@register("placer", "ilp_window")
class IlpWindowPlacer:
    def __init__(self, slots_per_worker: int = 4, time_limit: float = 2.0) -> None:
        self.m, self.time_limit = slots_per_worker, time_limit
        self.last_objective = 0.0

    def place(self, req: PlaceRequest) -> Placement:
        cost, owner = expanded(req, self.m)
        n_i, n_c = cost.shape
        idx = [(i, c) for i in range(n_i) for c in range(n_c) if cost[i, c] < BIG]
        nv = len(idx) + n_i  # x_ic for finite entries, then one "unassigned" slack per row
        obj = np.array([cost[i, c] for i, c in idx] + [BIG] * n_i)
        a_row = np.zeros((n_i, nv))
        a_col = np.zeros((n_c, nv))
        for v, (i, c) in enumerate(idx):
            a_row[i, v] = 1
            a_col[c, v] = 1
        a_row[np.arange(n_i), len(idx) + np.arange(n_i)] = 1
        cons = [LinearConstraint(a_row, 1, 1), LinearConstraint(a_col, 0, 1)]
        res = milp(
            obj,
            constraints=cons,
            integrality=np.ones(nv),
            bounds=Bounds(0, 1),
            options={"time_limit": self.time_limit, "presolve": True},
        )
        if res.x is None:
            return Placement({}, status="infeasible")
        x = np.round(res.x).astype(int)
        chosen = [(i, c) for v, (i, c) in enumerate(idx) if x[v] == 1]
        self.last_objective = float(sum(cost[i, c] for i, c in chosen))
        return placement(req, {i: owner[c] for i, c in chosen})
