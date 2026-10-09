"""Orchestrator actor (doc 03 §2, doc 07 §3, doc 08): cluster arrangement, membership, and scheduler appointment
per cluster by epoch CAS in the DB. Appointments are instance-bound (cluster, epoch, session-cert id); a scheduler
whose keepalives stop is replaced (P6 adds progress-based detection, checkpoints, standbys, planned handover)."""

from __future__ import annotations

from collections.abc import Callable

import numpy as np

from voss.core.ids import ClusterId, NodeId, WorkerId
from voss.core.messages import (
    Assign,
    DbCasResult,
    DrainNotice,
    HomeDemand,
    Join,
    KeepaliveSummary,
    Leave,
    Membership,
    Message,
    Revoke,
    RevokeSession,
    RouterStats,
    SchedulerAddr,
    Summaries,
)
from voss.core.messages_acct import ReportEvents, Settled
from voss.core.messages_ft import PutCheckpoint, Stall
from voss.metrics.schema import Table
from voss.policy.orchestrate import ClusterParams, form_clusters, nearest_cluster
from voss.policy.orchestrate_triggers import NEW_CLUSTER, step
from voss.runtime.actor import Actor, ActorContext
from voss.runtime.orchlib.appoint import AppointMixin
from voss.runtime.orchlib.book import Book, Cluster, MemberRec
from voss.runtime.orchlib.standing import StandingMixin

RegionOf = Callable[[float, float], int]


class Orchestrator(StandingMixin, AppointMixin, Actor):
    role = "orch"

    def __init__(self, host: NodeId, ctx: ActorContext, region_of: RegionOf) -> None:
        super().__init__(host, ctx)
        cc = ctx.cfg.voss.clusters
        self.mode, self.region_of = cc.mode, region_of
        self.params = ClusterParams(
            cc.target_size,
            cc.min_size,
            cc.max_size,
            cc.d_min,
            cc.dwell_s,
            cc.max_moves,
            cc.slo_theta,
            cc.slo_periods,
            cc.imbalance_delta,
            cc.max_moves_per_h,
        )
        self.book = Book()
        self.pending: list[WorkerId] = []
        self.formed = False
        self.region_cluster: dict[int, int] = {}
        oc = ctx.cfg.voss.orchestrator
        self.after(oc.check_s, self._check)
        self.after(oc.summaries_s, self._push_summaries)
        self.after(cc.period_s, self._push_home)
        if self.mode == "dynamic":
            self.after(cc.period_s, self._period)
        self._init_standing()

    # --- messages -------------------------------------------------------------------------------------------
    def on_message(self, msg: Message) -> None:
        if isinstance(msg, Join):
            self._join(msg)
        elif isinstance(msg, Leave | RevokeSession):
            if self._remove(msg.worker, msg.cert_id):
                self._session_end(msg.worker, abrupt=isinstance(msg, RevokeSession))
        elif isinstance(msg, DrainNotice):
            self._drain(msg.worker)
        elif isinstance(msg, KeepaliveSummary):
            self._keepalive(msg)
        elif isinstance(msg, Stall):
            self._stall(msg)
        elif isinstance(msg, PutCheckpoint):
            self._checkpoint(msg)
        elif isinstance(msg, RouterStats):
            for cid, n, missed in msg.stats:
                c = self.book.clusters.get(cid)
                if c is not None:
                    c.done, c.missed = c.done + n, c.missed + missed
            for cid, key, n in msg.home:
                c = self.book.clusters.get(cid)
                if c is not None:
                    c.home[key] = c.home.get(key, 0) + n
        elif isinstance(msg, DbCasResult):
            self._cas_result(msg)
        elif isinstance(msg, ReportEvents):
            self._report_events(msg)
        elif isinstance(msg, Settled):
            self._settled(msg)

    def _drain(self, w: WorkerId) -> None:
        """A hint (doc 07 §4): deprioritized for appointment; a draining scheduler hands over (planned)."""
        m = self.book.members.get(w)
        if m is None:
            return
        m.draining = True
        c = self.book.clusters.get(m.cluster)
        if c is not None and c.holder is not None and c.holder[0] == w:
            self._handover(c, "drain")

    def _join(self, m: Join) -> None:
        if self._remove(m.worker, None):
            self._session_end(m.worker, abrupt=True)  # the previous session ended unannounced
        self._session_start(m.worker, m.tier)
        self.book.members[m.worker] = MemberRec(
            m.cert_id, m.expiry, m.assurance, m.speed, m.slots, m.domain, m.lat, m.lon
        )
        if not self.formed:
            self.pending.append(m.worker)
            if len(self.pending) == 1:
                self.after(self.ctx.cfg.voss.clusters.bootstrap_s, self._form)
            return
        self._assign(m.worker, self._home(m.worker))

    def _remove(self, w: WorkerId, cert_id: str | None) -> bool:
        m = self.book.members.get(w)
        if m is None or (cert_id is not None and m.cert_id != cert_id):
            return False
        if w in self.pending:
            self.pending.remove(w)
        c = self.book.remove(w)
        if c is None:
            return True
        if c.holder is not None and c.holder[0] == w:
            self._appoint(c, frozenset({w}))
        self._changed(c)
        return True

    # --- arrangement ----------------------------------------------------------------------------------------
    def _form(self) -> None:
        """Initial clustering of the workers that joined during the bootstrap window (doc 03 §2)."""
        ws = sorted(self.pending)
        self.pending, self.formed = [], True
        if not ws:
            return
        recs = [self.book.members[w] for w in ws]
        if self.mode == "none_global":
            labels = np.zeros(len(ws), dtype=np.int64)
        elif self.mode == "static_regions":
            labels = np.array([self.region_of(r.lat, r.lon) for r in recs], dtype=np.int64)
        else:
            lat, lon = np.array([r.lat for r in recs]), np.array([r.lon for r in recs])
            labels, _ = form_clusters(lat, lon, np.array([r.domain for r in recs]), self.params)
        ids = {int(lab): self.book.new_cluster().cid for lab in sorted(set(labels.tolist()))}
        if self.mode == "static_regions":
            self.region_cluster = dict(ids)
        for w, lab in zip(ws, labels, strict=True):
            self._assign(w, ids[int(lab)])

    def _home(self, w: WorkerId) -> int:
        m = self.book.members[w]
        if self.mode == "none_global":
            return 0 if 0 in self.book.clusters else self.book.new_cluster().cid
        if self.mode == "static_regions":
            reg = self.region_of(m.lat, m.lon)
            if reg not in self.region_cluster:
                self.region_cluster[reg] = self.book.new_cluster().cid
            return self.region_cluster[reg]
        cid = nearest_cluster(m.lat, m.lon, self.book.infos(), self.params.max_size)
        return cid if cid is not None else self.book.new_cluster().cid

    def _assign(self, w: WorkerId, cid: int) -> None:
        old = self.book.members[w].cluster
        self.book.place(w, cid, self.now)
        self.send(("agent", int(w)), Assign(ClusterId(cid)))
        self._changed(self.book.clusters[cid])
        if old in self.book.clusters and old != cid and not self.book.clusters[old].members:
            self._dissolve(self.book.clusters[old])

    def _period(self) -> None:
        """Dynamic arrangement: triggers with hysteresis (doc 03 §2)."""
        for c in self.book.clusters.values():
            c.slo_miss = c.missed / c.done if c.done else 0.0
            c.bad_periods = c.bad_periods + 1 if c.slo_miss > self.params.slo_theta else 0
            c.done = c.missed = 0
        delay = self.ctx.clock.charge("orchestrate", work=len(self.book.members))
        ops = step(self.book.infos(), self.book.trigger_members(self.now), self.now, self.params)
        new: int | None = None
        for op in ops:
            if op.dst == NEW_CLUSTER and new is None:
                new = self.book.new_cluster().cid
            dst = new if op.dst == NEW_CLUSTER else op.dst
            if WorkerId(op.worker) in self.book.members and dst is not None:
                self.ctx.rec.log(
                    Table.EVENTS,
                    t=self.now,
                    kind="move",
                    worker=op.worker,
                    value=float(dst),
                    src=op.src,
                    reason=op.reason,
                )
                self._assign(WorkerId(op.worker), dst)
        self.after(self.ctx.cfg.voss.clusters.period_s + delay, self._period)

    def _changed(self, c: Cluster) -> None:
        for other in self.book.clusters.values():  # a move also changes the source cluster
            if other.dirty and other is not c and other.holder is not None and other.members:
                self.after(0.2, self._push_membership, other.cid)
        if not c.members:
            self._dissolve(c)
        elif c.holder is None:
            self._appoint(c, frozenset())
        else:
            c.dirty = True
            self.after(0.2, self._push_membership, c.cid)

    def _push_membership(self, cid: int) -> None:
        c = self.book.clusters.get(cid)
        if c is None or not c.dirty or c.holder is None:
            return
        c.dirty = False
        moved, c.moved_out = tuple(sorted(c.moved_out - c.members)), set()
        self.send(("sched", c.holder[0]), Membership(ClusterId(cid), c.epoch, tuple(sorted(c.members)), moved))

    def _dissolve(self, c: Cluster) -> None:
        if c.holder is not None:
            self.send(("sched", c.holder[0]), Revoke(ClusterId(c.cid), c.epoch + 1))
            self._role_record(c, WorkerId(-1), None, c.epoch + 1)
        del self.book.clusters[c.cid]
        for r in self.ctx.directory.routers:
            self.send(r, SchedulerAddr(ClusterId(c.cid), c.epoch + 1, None))

    def _push_home(self) -> None:
        """Regional demand per cluster to its scheduler's planner (D-32)."""
        period = self.ctx.cfg.voss.clusters.period_s
        for cid in sorted(self.book.clusters):
            c = self.book.clusters[cid]
            if c.holder is not None:
                rates = tuple((k, n / period) for k, n in sorted(c.home.items()))
                self.send(("sched", c.holder[0]), HomeDemand(ClusterId(cid), c.epoch, rates))
            c.home = {}
        self.after(period, self._push_home)

    def _push_summaries(self) -> None:
        cards = tuple(
            card for cid in sorted(self.book.clusters) if (card := self.book.card(self.book.clusters[cid])) is not None
        )
        if cards:
            for r in self.ctx.directory.routers:
                self.send(r, Summaries(cards))
        self.after(self.ctx.cfg.voss.orchestrator.summaries_s, self._push_summaries)
