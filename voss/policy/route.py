"""Routing over cluster summaries (doc 03 §3).

``score(c) = rtt(origin, c) + E[completion_c] + penalty(health_c) + trust_cold_penalty(c, t)``: a cluster without
trust-warm capacity for the tenant pays the expected key release and cold start plus an exposure increment, so
spillover is a priced decision. ``E[completion_c]`` minus the (cluster-independent) execution time is the
cluster's measured overhead plus its backlog when over-full, plus a cold-function term when ``f`` has no warm
instance. Cold prices are what this cluster measured such starts to cost (D-33), not constants.
Baselines: ``nearest``, ``least_loaded``, ``po2_nearby``, ``warm_aware`` (warm state but no trust pricing).
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

import numpy as np

from voss.core.registry import register
from voss.core.types import ClusterCard
from voss.policy.orchestrate import great_circle

RTT_KM_PER_S = 100_000 / 1.3  # 100 km per ms of RTT, route factor 1.3 (doc 02 §3)


@dataclass(frozen=True)
class RouteRequest:
    origin: tuple[float, float]
    tenant: str
    fn: str
    cards: tuple[ClusterCard, ...]
    excluded: frozenset[int] = frozenset()
    exposure_s: float = 0.5  # exposure increment of a trust-cold spill, in seconds  # TODO verify
    health_s: float = 5.0  # seconds per unit of miss rate above the threshold
    slo_theta: float = 0.2  # miss rate above which a cluster is unhealthy (doc 03 §2)


Router = Callable[[RouteRequest, np.random.Generator], int | None]


def _rtt(req: RouteRequest) -> np.ndarray:
    lat = np.array([c.lat for c in req.cards])
    lon = np.array([c.lon for c in req.cards])
    out: np.ndarray = great_circle(lat, lon, *req.origin) / RTT_KM_PER_S
    return out


def _pick(req: RouteRequest, cost: np.ndarray) -> int | None:
    ok = np.array([c.cluster not in req.excluded and c.free_slots > 0 for c in req.cards])
    if not ok.any():
        ok = np.array([c.cluster not in req.excluded for c in req.cards])
    if not ok.any():
        return None
    cost = np.where(ok, cost, np.inf)
    i = int(np.lexsort((np.array([c.cluster for c in req.cards]), cost))[0])
    return req.cards[i].cluster


def home_cluster(origin: tuple[float, float], cards: tuple[ClusterCard, ...]) -> int | None:
    """Nearest cluster to the origin: where this demand would run if every cluster were trust-warm (D-32)."""
    if not cards:
        return None
    rtt = great_circle(np.array([c.lat for c in cards]), np.array([c.lon for c in cards]), *origin)
    return cards[int(np.lexsort((np.array([c.cluster for c in cards]), rtt))[0])].cluster


@register("route", "score")
def route_score(req: RouteRequest, gen: np.random.Generator) -> int | None:
    trust = np.array(
        [0.0 if c.trust_warm.get(req.tenant, 0.0) > 0 else c.cold_trust_s + req.exposure_s for c in req.cards]
    )
    health = np.array([req.health_s * max(0.0, c.slo_miss - req.slo_theta) for c in req.cards])
    return _pick(req, _rtt(req) + _queue(req) + health + trust + _cold_fn(req))


def _queue(req: RouteRequest) -> np.ndarray:
    return np.array([c.overhead_s + c.backlog_s for c in req.cards])


def _cold_fn(req: RouteRequest) -> np.ndarray:
    return np.array([0.0 if c.warm_fns.get(req.fn, 0) > 0 else c.cold_fn_s for c in req.cards])


@register("route", "nearest")
def route_nearest(req: RouteRequest, gen: np.random.Generator) -> int | None:
    return _pick(req, _rtt(req))


@register("route", "least_loaded")
def route_least_loaded(req: RouteRequest, gen: np.random.Generator) -> int | None:
    return _pick(req, np.array([c.load for c in req.cards]))


@register("route", "po2_nearby")
def route_po2(req: RouteRequest, gen: np.random.Generator, nearby: int = 4) -> int | None:
    rtt = _rtt(req)
    order = [i for i in np.argsort(rtt, kind="stable") if req.cards[i].cluster not in req.excluded][:nearby]
    if not order:
        return None
    pair = gen.choice(order, size=min(2, len(order)), replace=False)
    best = min(pair, key=lambda i: (req.cards[i].load, req.cards[i].cluster))
    return req.cards[int(best)].cluster


@register("route", "warm_aware")
def route_warm(req: RouteRequest, gen: np.random.Generator) -> int | None:
    return _pick(req, _rtt(req) + _cold_fn(req) + _queue(req))
