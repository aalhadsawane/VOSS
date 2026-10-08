"""``random`` and ``round_robin`` placer baselines (doc 03 §5.3)."""

from __future__ import annotations

from voss.core.registry import register
from voss.core.types import Placement
from voss.policy.place.base import PlaceRequest, placement


@register("placer", "random")
class RandomPlacer:
    def place(self, req: PlaceRequest) -> Placement:
        assign = {}
        for i in range(len(req.invs)):
            opts = req.options(i)
            if len(opts):
                assign[i] = int(req.gen.choice(opts))
        return placement(req, assign)


@register("placer", "round_robin")
class RoundRobinPlacer:
    """Cycles through workers in id order, skipping infeasible ones."""

    def __init__(self) -> None:
        self.next_id = -1

    def place(self, req: PlaceRequest) -> Placement:
        assign = {}
        for i in range(len(req.invs)):
            opts = sorted(req.options(i), key=lambda j: req.view.workers[j])
            if not opts:
                continue
            later = [j for j in opts if req.view.workers[j] > self.next_id]
            j = later[0] if later else opts[0]
            assign[i] = int(j)
            self.next_id = req.view.workers[j]
        return placement(req, assign)
