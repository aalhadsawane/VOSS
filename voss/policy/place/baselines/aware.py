"""Feature-aware placer baselines (doc 03 §5.3): ``warm_first``, ``latency_aware``, ``reliability_aware``,
``nearest_edge`` and ``hash_locality``. They read the shared cost matrix but ignore trust and exposure pricing."""

from __future__ import annotations

import hashlib

import numpy as np

from voss.core.registry import register
from voss.core.types import Placement
from voss.policy.place.base import PlaceRequest, placement
from voss.policy.place.candidates import load

LEVEL = {"L3": 0, "L2": 1, "L1": 2, "L0": 3}


def _by(req: PlaceRequest, key: str) -> Placement:
    if req.cm is None:
        raise ValueError(f"{key} baseline needs a cost matrix")
    assign = {}
    for i in range(len(req.invs)):
        x = np.where(req.cm.feasible[i], req.cm.components[key][i], np.inf)
        if np.isfinite(x).any():
            assign[i] = int(req.cm.candidates[i][int(np.argmin(x))])
    return placement(req, assign)


@register("placer", "warm_first")
class WarmFirstPlacer:
    """Warmest cache level for the function, then least loaded."""

    def place(self, req: PlaceRequest) -> Placement:
        occ = load(req.view)
        assign = {}
        for i, inv in enumerate(req.invs):
            opts = req.options(i)
            if not len(opts):
                continue
            lv = [LEVEL.get(getattr(req.view.cache[j].get(inv.fn), "level", "L0"), 3) for j in opts]
            assign[i] = int(opts[np.lexsort((occ[opts], lv))[0]])
        return placement(req, assign)


@register("placer", "latency_aware")
class LatencyAwarePlacer:
    """Minimum expected completion time (no failure or exposure pricing)."""

    def place(self, req: PlaceRequest) -> Placement:
        if req.cm is None:
            raise ValueError("latency_aware needs a cost matrix")
        mean = req.cm.completion.mean()
        assign = {}
        for i in range(len(req.invs)):
            x = np.where(req.cm.feasible[i], mean[i], np.inf)
            if np.isfinite(x).any():
                assign[i] = int(req.cm.candidates[i][int(np.argmin(x))])
        return placement(req, assign)


@register("placer", "reliability_aware")
class ReliabilityAwarePlacer:
    def place(self, req: PlaceRequest) -> Placement:
        return _by(req, "pFail")


@register("placer", "nearest_edge")
class NearestEdgePlacer:
    def place(self, req: PlaceRequest) -> Placement:
        return _by(req, "net")


@register("placer", "hash_locality")
class HashLocalityPlacer:
    """Rendezvous hashing of the function name over feasible workers (cache locality without load awareness)."""

    def place(self, req: PlaceRequest) -> Placement:
        assign = {}
        for i, inv in enumerate(req.invs):
            opts = req.options(i)
            if not len(opts):
                continue
            score = [hashlib.sha256(f"{inv.fn}|{req.view.workers[j]}".encode()).digest()[:8] for j in opts]
            assign[i] = int(opts[int(np.argmax([int.from_bytes(s, "big") for s in score]))])
        return placement(req, assign)
