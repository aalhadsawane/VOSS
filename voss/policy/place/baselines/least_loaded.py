"""Load-based placer baselines (doc 03 §5.3): ``least_loaded`` (occupancy per slot), ``jsq`` (shortest queue) and
``po2`` (power of two choices)."""

from __future__ import annotations

import numpy as np

from voss.core.registry import register
from voss.core.types import Placement
from voss.policy.place.base import PlaceRequest, placement
from voss.policy.place.candidates import load


def _pick(req: PlaceRequest, metric: np.ndarray, per_slot: np.ndarray) -> Placement:
    m = metric.astype(float).copy()
    assign = {}
    for i in range(len(req.invs)):
        opts = req.options(i)
        if not len(opts):
            continue
        j = int(opts[np.lexsort((np.asarray(req.view.workers)[opts], m[opts]))[0]])
        assign[i] = j
        m[j] += per_slot[j]
    return placement(req, assign)


@register("placer", "least_loaded")
class LeastLoadedPlacer:
    def place(self, req: PlaceRequest) -> Placement:
        return _pick(req, load(req.view), 1.0 / np.maximum(req.view.slots, 1))


@register("placer", "jsq")
class JsqPlacer:
    def place(self, req: PlaceRequest) -> Placement:
        v = req.view
        return _pick(req, v.busy + v.queued + v.inflight, np.ones(len(v)))


@register("placer", "po2")
class Po2Placer:
    def place(self, req: PlaceRequest) -> Placement:
        occ = load(req.view).astype(float)
        assign = {}
        for i in range(len(req.invs)):
            opts = req.options(i)
            if not len(opts):
                continue
            a, b = (int(x) for x in req.gen.choice(opts, size=2, replace=len(opts) < 2))
            j = a if occ[a] <= occ[b] else b
            assign[i] = j
            occ[j] += 1.0 / max(1, int(req.view.slots[j]))
        return placement(req, assign)
