"""Orchestrator triggers (doc 03 §2): size floor/ceiling, SLO health, demand imbalance, diversity deficit, with
per-worker dwell time and a cap on moves per period (hysteresis). Pure: membership and summaries in, moves out."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from voss.policy.orchestrate import ClusterInfo, ClusterParams, MoveOp, great_circle, kmedoids

NEW_CLUSTER = -1


@dataclass(frozen=True)
class Member:
    lat: float
    lon: float
    domain: int
    slots: int
    since: float  # time the worker joined its current cluster
    recent_moves: int = 0  # orchestrator moves of this worker in the last hour


def _eligible(m: Member, p: ClusterParams) -> bool:
    """Hard per-worker migration budget (roadmap P5 exit: bounded migrations per worker per hour)."""
    return m.recent_moves < p.max_moves_per_h


def _movable(c: ClusterInfo, members: dict[int, Member], now: float, p: ClusterParams) -> list[int]:
    return sorted(w for w in c.members if now - members[w].since >= p.dwell_s and _eligible(members[w], p))


def _dist(c: ClusterInfo, m: Member) -> float:
    return float(great_circle(np.array([m.lat]), np.array([m.lon]), *c.medoid)[0])


def _neighbors(c: ClusterInfo, clusters: list[ClusterInfo]) -> list[ClusterInfo]:
    others = [o for o in clusters if o.cluster != c.cluster]
    lat, lon = c.medoid
    return sorted(
        others, key=lambda o: (float(great_circle(np.array([lat]), np.array([lon]), *o.medoid)[0]), o.cluster)
    )


def merge_small(clusters: list[ClusterInfo], members: dict[int, Member], p: ClusterParams) -> list[MoveOp]:
    out: list[MoveOp] = []
    if len(clusters) <= 1:
        return out
    for c in sorted(clusters, key=lambda x: x.cluster):
        if 0 < len(c.members) < p.min_size and all(_eligible(members[w], p) for w in c.members):
            room = [o for o in _neighbors(c, clusters) if len(o.members) + len(c.members) <= p.max_size]
            if room:
                out += [MoveOp(w, c.cluster, room[0].cluster, "merge") for w in sorted(c.members)]
                break  # one merge per period
    return out


def split_large(clusters: list[ClusterInfo], members: dict[int, Member], p: ClusterParams) -> list[MoveOp]:
    for c in sorted(clusters, key=lambda x: x.cluster):
        if len(c.members) > p.max_size:
            ws = sorted(c.members)
            lat = np.array([members[w].lat for w in ws])
            lon = np.array([members[w].lon for w in ws])
            labels, _ = kmedoids(lat, lon, 2)
            far = 1 if (labels == 1).sum() <= (labels == 0).sum() else 0
            go = [w for w, lab in zip(ws, labels, strict=True) if lab == far and _eligible(members[w], p)]
            if len(go) >= p.min_size:
                return [MoveOp(w, c.cluster, NEW_CLUSTER, "split") for w in go]
    return []


def borrow(clusters: list[ClusterInfo], members: dict[int, Member], now: float, p: ClusterParams) -> list[MoveOp]:
    """SLO health, demand imbalance and forecast overload: a struggling cluster borrows from a neighbour with
    headroom (one of its three nearest)."""
    out: list[MoveOp] = []
    for c in sorted(clusters, key=lambda x: (-x.slo_miss, x.cluster)):
        unhealthy, ahead = c.bad_periods >= p.slo_periods, c.forecast > 1.0
        for o in _neighbors(c, clusters)[:3]:
            imbalance = c.load - o.load > p.imbalance_delta
            reason = "slo" if unhealthy else "imbalance" if imbalance else "forecast" if ahead else ""
            if not reason or o.forecast >= 1.0 or len(o.members) <= p.min_size or len(c.members) >= p.max_size:
                continue
            cand = sorted(_movable(o, members, now, p), key=lambda w: (_dist(c, members[w]), w))
            if cand:
                out.append(MoveOp(cand[0], o.cluster, c.cluster, reason))
                break
    return out


def fix_diversity(
    clusters: list[ClusterInfo], members: dict[int, Member], now: float, p: ClusterParams
) -> list[MoveOp]:
    out: list[MoveOp] = []
    for c in sorted(clusters, key=lambda x: x.cluster):
        doms = {members[w].domain for w in c.members}
        if len(doms) >= p.d_min and not c.infeasible:
            continue
        for o in _neighbors(c, clusters)[:3]:
            if len(o.members) <= p.min_size:
                continue
            cand = [w for w in _movable(o, members, now, p) if members[w].domain not in doms]
            if cand:
                out.append(
                    MoveOp(sorted(cand, key=lambda w: (_dist(c, members[w]), w))[0], o.cluster, c.cluster, "diversity")
                )
                break
    return out


def step(clusters: list[ClusterInfo], members: dict[int, Member], now: float, p: ClusterParams) -> list[MoveOp]:
    """One orchestrator period: structural changes first (split, merge), then rebalancing; at most
    ``max_moves`` rebalancing moves and at most one move per worker."""
    structural = split_large(clusters, members, p) or merge_small(clusters, members, p)
    if structural:
        return structural
    ops = fix_diversity(clusters, members, now, p) + borrow(clusters, members, now, p)
    seen: set[int] = set()
    out: list[MoveOp] = []
    for op in ops:
        if op.worker not in seen and len(out) < p.max_moves:
            seen.add(op.worker)
            out.append(op)
    return out
