"""The orchestrator's books (doc 08 §3 ``workers``/``clusters``): members, epochs, scheduler holders, summaries."""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from voss.core.ids import WorkerId
from voss.core.messages import KeepaliveSummary
from voss.core.types import ClusterCard
from voss.policy.orchestrate import ClusterInfo
from voss.policy.orchestrate_triggers import Member


@dataclass
class MemberRec:
    cert_id: str
    expiry: float
    assurance: float
    speed: float
    slots: int
    domain: int
    lat: float
    lon: float
    cluster: int = -1
    since: float = 0.0
    draining: bool = False


@dataclass
class Cluster:
    cid: int
    members: set[WorkerId] = field(default_factory=set)
    epoch: int = 0
    holder: tuple[WorkerId, str] | None = None
    last_keepalive: float = 0.0
    cas_pending: bool = False
    dirty: bool = False
    moved_out: set[WorkerId] = field(default_factory=set)
    summary: KeepaliveSummary | None = None
    done: int = 0
    missed: int = 0
    bad_periods: int = 0
    slo_miss: float = 0.0
    home: dict[str, int] = field(default_factory=dict)


class Book:
    """All clusters and members; one writer (the orchestrator)."""

    def __init__(self) -> None:
        self.members: dict[WorkerId, MemberRec] = {}
        self.clusters: dict[int, Cluster] = {}
        self.next_id = 0
        self.moved_at: dict[WorkerId, list[float]] = {}  # survives sessions: the migration budget is per worker

    def new_cluster(self) -> Cluster:
        c = Cluster(self.next_id)
        self.clusters[c.cid] = c
        self.next_id += 1
        return c

    def place(self, w: WorkerId, cid: int, now: float) -> None:
        m = self.members[w]
        if m.cluster in self.clusters and m.cluster != cid:
            old = self.clusters[m.cluster]
            old.members.discard(w)
            old.moved_out.add(w)
            old.dirty = True
        if m.cluster >= 0 and m.cluster != cid:
            self.moved_at.setdefault(w, []).append(now)
        m.cluster, m.since = cid, now
        self.clusters[cid].members.add(w)
        self.clusters[cid].dirty = True

    def remove(self, w: WorkerId) -> Cluster | None:
        m = self.members.pop(w, None)
        if m is None or m.cluster not in self.clusters:
            return None
        c = self.clusters[m.cluster]
        c.members.discard(w)
        c.dirty = True
        return c

    def centroid(self, c: Cluster) -> tuple[float, float]:
        if not c.members:
            return 0.0, 0.0
        lat = np.array([self.members[w].lat for w in c.members])
        lon = np.array([self.members[w].lon for w in c.members])
        return float(lat.mean()), float(
            np.degrees(np.arctan2(np.sin(np.radians(lon)).mean(), np.cos(np.radians(lon)).mean()))
        )

    def infos(self) -> list[ClusterInfo]:
        out = []
        for cid in sorted(self.clusters):
            c = self.clusters[cid]
            s = c.summary
            out.append(
                ClusterInfo(
                    cid,
                    set(c.members),
                    self.centroid(c),
                    s.load if s else 0.0,
                    c.slo_miss,
                    c.bad_periods,
                    bool(s.infeasible) if s else False,
                    s.forecast if s else 0.0,
                )
            )
        return out

    def recent_moves(self, w: WorkerId, now: float) -> int:
        times = self.moved_at.get(w)
        if not times:
            return 0
        times[:] = [t for t in times if now - t < 3600.0]
        return len(times)

    def trigger_members(self, now: float) -> dict[int, Member]:
        return {
            int(w): Member(m.lat, m.lon, m.domain, m.slots, m.since, self.recent_moves(w, now))
            for w, m in sorted(self.members.items())
        }

    def card(self, c: Cluster) -> ClusterCard | None:
        s = c.summary
        if c.holder is None or s is None:
            return None
        lat, lon = self.centroid(c)
        return ClusterCard(
            c.cid,
            lat,
            lon,
            s.load,
            s.free_slots,
            c.slo_miss,
            s.overhead_s,
            dict(s.trust_warm),
            dict(s.warm_fns),
            s.cold_trust_s,
            s.cold_fn_s,
            s.backlog_s,
        )
