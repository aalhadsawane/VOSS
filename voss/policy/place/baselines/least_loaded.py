"""``least_loaded`` placer baseline (doc 03 §5.3): lowest occupancy per slot, ties by worker id."""

from __future__ import annotations

import numpy as np

from voss.core.ids import InvId, WorkerId
from voss.core.registry import register
from voss.core.types import Placement
from voss.policy.place.base import PlaceRequest
from voss.policy.place.candidates import eligible, load


@register("placer", "least_loaded")
class LeastLoadedPlacer:
    def place(self, req: PlaceRequest) -> Placement:
        occ = load(req.view).astype(float)
        assign: dict[InvId, WorkerId] = {}
        for inv in req.invs:
            ok = eligible(req.view, inv, req.now, req.expiry_margin_s)
            if not ok.any():
                continue
            i = int(np.argmin(np.where(ok, occ, np.inf)))
            assign[inv.id] = req.view.workers[i]
            occ[i] += 1.0 / max(1, int(req.view.slots[i]))
        return Placement(assign, status="ok" if len(assign) == len(req.invs) else "partial")
