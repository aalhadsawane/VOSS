"""``eviction_aware`` placer baseline (docs/REVISION_PLAN.md V8): placement on harvested resources after Zhang et al.,
"Faster and Cheaper Serverless Computing on Harvested Resources" (SOSP 2021), which prefers the machines least likely
to be evicted. Here: the candidate with the lowest predicted failure probability over the attempt (``pFail``: session
survival and drop estimate), ties broken by occupancy and then worker id. Deviation: the paper's machines are harvest
VMs with an eviction-time model; ours are volunteer sessions with a survival model (the same input role)."""

from __future__ import annotations

import numpy as np

from voss.core.registry import register
from voss.core.types import Placement
from voss.policy.place.base import PlaceRequest, placement
from voss.policy.place.candidates import load


@register("placer", "eviction_aware")
class EvictionAwarePlacer:
    def place(self, req: PlaceRequest) -> Placement:
        if req.cm is None:
            return placement(req, {})
        occ = load(req.view).astype(float)
        ids = np.asarray(req.view.workers)
        assign = {}
        for i in range(len(req.invs)):
            opts = req.options(i)
            if not len(opts):
                continue
            k = {int(j): n for n, j in enumerate(req.cm.candidates[i])}
            fail = np.array([req.cm.components["pFail"][i, k[int(j)]] for j in opts])
            j = int(opts[np.lexsort((ids[opts], occ[opts], fail))[0]])
            assign[i] = j
            occ[j] += 1.0 / max(1, int(req.view.slots[j]))
        return placement(req, assign)
