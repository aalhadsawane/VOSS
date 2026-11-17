"""``eviction_aware`` placer baseline (docs/REVISION_PLAN.md V8): the load balancer of Zhang et al., "Faster and
Cheaper Serverless Computing on Harvested Resources" (SOSP 2021), §5.2 Algorithm 1, min-worker-set (MWS).

For function ``f`` the balancer estimates its resource usage ``u_f = RPS_f · E(CPU_f) · E(lat_f)``, starts at the
function's home worker on a consistent-hashing ring and adds the next workers clockwise until their usable resources
reach ``u_f``; the invocation goes to the least loaded worker of that set. A worker under an eviction notice receives no
new invocations (§4.1); here a draining worker is not eligible (``candidates.eligible``).

Deviations (``configs/baselines.yaml``): the ring holds the shared candidates of the cost matrix (AGENTS.md rule 5)
rather than every invoker; usable resources are a worker's free concurrency slots (slots not busy, queued or
dispatched; the paper's usable resources of a harvest VM) and ``E(CPU_f)`` is one slot, because a sandbox runs one
invocation on one slot; load is occupancy per slot (busy, queued and in flight) instead of the
paper's weighted CPU and memory utilisation, which the scheduler does not observe.
"""

from __future__ import annotations

import hashlib

import numpy as np

from voss.core.registry import register
from voss.core.types import Placement
from voss.policy.place.base import PlaceRequest, placement
from voss.policy.place.candidates import load


def ring_position(key: str) -> int:
    """Position on the consistent-hashing ring ``[0, 2^64)`` (stable across runs and machines)."""
    return int.from_bytes(hashlib.sha256(key.encode()).digest()[:8], "little")


def worker_set(fn: str, workers: np.ndarray, usable: np.ndarray, usage: float) -> np.ndarray:
    """Algorithm 1: positions into ``workers`` of the min worker set of ``fn``, from its home worker clockwise until
    the summed usable resources (free slots) reach ``usage`` and are not zero (every worker when they never do)."""
    if not len(workers):
        return np.zeros(0, np.int64)
    pos = np.array([ring_position(f"worker:{int(w)}") for w in workers], dtype=np.uint64)
    order = np.argsort(pos, kind="stable")
    start = int(np.searchsorted(pos[order], np.uint64(ring_position(f"fn:{fn}"))))
    ring = np.roll(order, -start)
    cum = np.cumsum(usable[ring].astype(float))
    reached = (cum >= usage) & (cum > 0)
    n = int(np.argmax(reached)) + 1 if reached.any() else len(ring)
    out: np.ndarray = ring[:n]
    return out


@register("placer", "eviction_aware")
class EvictionAwarePlacer:
    uses_fn_load = True  # the scheduler fills ``PlaceRequest.fn_load`` (u_f) for this placer

    def place(self, req: PlaceRequest) -> Placement:
        occ = load(req.view).astype(float)
        ids = np.asarray(req.view.workers)
        assign = {}
        for i, inv in enumerate(req.invs):
            opts = req.options(i)
            if not len(opts):
                continue
            free = np.maximum(0.0, req.view.slots[opts] * (1.0 - occ[opts]))  # usable resources now (§5.2)
            s = opts[worker_set(inv.fn, ids[opts], free, req.fn_load.get(inv.fn, 0.0))]
            j = int(s[np.lexsort((ids[s], occ[s]))[0]])
            assign[i] = j
            occ[j] += 1.0 / max(1, int(req.view.slots[j]))
        return placement(req, assign)
