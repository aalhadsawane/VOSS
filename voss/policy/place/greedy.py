"""``greedy`` placer (doc 03 §5.3, default for sync): per invocation, tightest budget first, the candidate with the
lowest miss probability, ties to the lowest expected completion (D-110). Local bookkeeping adds each assignment's
service time per slot to that worker's expected completion, so later invocations in the same call see the load."""

from __future__ import annotations

import numpy as np

from voss.core.registry import register
from voss.core.types import Placement
from voss.policy.place.base import PlaceRequest, placement


@register("placer", "greedy")
class GreedyPlacer:
    def place(self, req: PlaceRequest) -> Placement:
        if req.cm is None or req.scores is None:
            raise ValueError("greedy needs a cost matrix and scores")
        cm, scores = req.cm, req.scores
        tie = req.tiebreak if req.tiebreak is not None else np.zeros_like(scores)
        step = req.slot_step if req.slot_step is not None else np.zeros_like(scores)
        extra: dict[int, int] = {}
        assign: dict[int, int] = {}
        for i in np.argsort(cm.budget[:, 0] if cm.budget.size else np.zeros(len(req.invs)), kind="stable"):
            cand = cm.candidates[i]
            primary = np.where(cm.feasible[i], scores[i], np.inf)
            if not np.isfinite(primary).any():
                continue
            second = tie[i] + step[i] * np.array([extra.get(int(j), 0) for j in cand])
            k = int(np.lexsort((second, primary))[0])
            j = int(cand[k])
            assign[int(i)] = j
            extra[j] = extra.get(j, 0) + 1
        return placement(req, assign)
