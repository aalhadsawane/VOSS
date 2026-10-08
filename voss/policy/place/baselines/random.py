"""``random`` placer baseline (doc 03 §5.3)."""

from __future__ import annotations

from voss.core.ids import InvId, WorkerId
from voss.core.registry import register
from voss.core.types import Placement
from voss.policy.place.base import PlaceRequest
from voss.policy.place.candidates import eligible


@register("placer", "random")
class RandomPlacer:
    def place(self, req: PlaceRequest) -> Placement:
        assign: dict[InvId, WorkerId] = {}
        for inv in req.invs:
            idx = eligible(req.view, inv, req.now, req.expiry_margin_s).nonzero()[0]
            if len(idx):
                assign[inv.id] = req.view.workers[int(req.gen.choice(idx))]
        return Placement(assign, status="ok" if len(assign) == len(req.invs) else "partial")
