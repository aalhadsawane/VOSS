"""Kubernetes-style placer baselines (doc 03 §5.3 ``k8s_*``): filter feasible nodes, then score each with the
kube-scheduler's default plugins and pick the best (ties by worker id).

- ``k8s_default``: ``NodeResourcesFit`` (LeastAllocated) + ``NodeResourcesBalancedAllocation`` + ``ImageLocality``
  + 2 × ``PodTopologySpread`` over failure domains (the default plugin weights).
- ``k8s_binpack``: ``NodeResourcesFit`` with MostAllocated (bin-packing profile) + ``ImageLocality``.

Scores are on the plugins' 0-100 scale. No trust, exposure, failure or latency pricing: that is the point.
"""

from __future__ import annotations

import numpy as np

from voss.core.registry import register
from voss.core.types import Invocation, Placement
from voss.policy.place.base import PlaceRequest, placement
from voss.policy.place.candidates import load

FN_MEM_MB = 256.0  # request per pod when the function's memory is unknown to the view  # TODO verify


def _image(req: PlaceRequest, inv: Invocation, opts: np.ndarray) -> np.ndarray:
    """``ImageLocality``: 100 if the function's artifacts are already on the node (any cache level), else 0."""
    return np.array([100.0 if inv.fn in req.view.cache[j] else 0.0 for j in opts])


def _spread(dom_count: dict[int, int], domains: np.ndarray) -> np.ndarray:
    """``PodTopologySpread``: fewer pods of this batch already in the node's domain scores higher."""
    counts = np.array([dom_count.get(int(d), 0) for d in domains], dtype=float)
    return 100.0 * (1.0 - counts / max(1.0, counts.max())) if counts.max() > 0 else np.full(len(domains), 100.0)


def _place(req: PlaceRequest, binpack: bool) -> Placement:
    v = req.view
    cpu = load(v).astype(float)
    mem_total = np.maximum(v.mem_free_mb + (v.busy + v.queued) * FN_MEM_MB, 1.0)
    mem = 1.0 - v.mem_free_mb / mem_total
    dom_count: dict[int, int] = {}
    assign = {}
    for i, inv in enumerate(req.invs):
        opts = req.options(i)
        if not len(opts):
            continue
        fits = opts[cpu[opts] < 1.0 - 1e-9]  # NodeResourcesFit filter (all full: queue on the best anyway)
        opts = fits if len(fits) else opts
        c, m = np.clip(cpu[opts], 0, 1), np.clip(mem[opts], 0, 1)
        fit = 100.0 * ((c + m) / 2 if binpack else (2 - c - m) / 2)
        score = fit + _image(req, inv, opts)
        if not binpack:
            score += 100.0 * (1.0 - np.abs(c - m)) + 2 * _spread(dom_count, v.domain[opts])
        j = int(opts[np.lexsort((np.asarray(v.workers)[opts], -score))[0]])
        assign[i] = j
        cpu[j] += 1.0 / max(1, int(v.slots[j]))
        mem[j] += FN_MEM_MB / float(mem_total[j])
        dom_count[int(v.domain[j])] = dom_count.get(int(v.domain[j]), 0) + 1
    return placement(req, assign)


@register("placer", "k8s_default")
class K8sDefaultPlacer:
    def place(self, req: PlaceRequest) -> Placement:
        return _place(req, binpack=False)


@register("placer", "k8s_binpack")
class K8sBinpackPlacer:
    def place(self, req: PlaceRequest) -> Placement:
        return _place(req, binpack=True)
