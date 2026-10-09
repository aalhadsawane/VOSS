"""Scheduler appointment and succession at the orchestrator (doc 07 §3): epoch CAS, keepalive timeout, progress-based
suspicion (router stalls, decision-latency SLO), planned handover, leases, checkpoints and warm standbys."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import numpy as np

from voss.core.ids import Addr, ClusterId, WorkerId
from voss.core.messages import Appoint, DbCasEpoch, DbCasResult, KeepaliveSummary, Revoke, SchedulerAddr
from voss.core.messages_ft import Handover, Lease, PutCheckpoint, Stall, Standby
from voss.metrics.schema import Table
from voss.policy.orchestrate import great_circle
from voss.policy.succession_rank import rank
from voss.runtime.actor import ActorContext
from voss.runtime.orchlib.book import Book, Cluster


class AppointMixin:
    ctx: ActorContext
    book: Book
    addr: Addr

    if TYPE_CHECKING:

        @property
        def now(self) -> float: ...
        def send(self, dst: Addr, msg: Any) -> bool: ...
        def after(self, dt: float, fn: Any, *args: Any) -> Any: ...
        def _role_record(self, c: Cluster, holder: WorkerId, standby: WorkerId | None, epoch: int) -> None: ...
        def _send_scores(self, cid: int) -> None: ...

    # --- detection --------------------------------------------------------------------------------------------
    def _suspect_scheduler(self, c: Cluster, reason: str) -> None:
        if c.holder is None or c.cas_pending:
            return
        self.ctx.rec.log(
            Table.EVENTS, t=self.now, kind="scheduler_suspect", worker=c.holder[0], value=c.epoch, cluster=c.cid,
            reason=reason,
        )  # fmt: skip
        self._appoint(c, frozenset({c.holder[0]}))

    def _check(self) -> None:
        cfg = self.ctx.cfg.voss.orchestrator
        for cid in sorted(self.book.clusters):
            c = self.book.clusters[cid]
            if c.holder is not None and self.now - c.last_keepalive > cfg.keepalive_timeout_s:
                self._suspect_scheduler(c, "keepalive_timeout")
        self.after(cfg.check_s, self._check)

    def _stall(self, m: Stall) -> None:
        """Router progress evidence. An over-full cluster also stalls, but its new dispatches are still accepted:
        that is a capacity problem for the triggers, not a reason to replace its scheduler (D-42)."""
        c = self.book.clusters.get(int(m.cluster))
        if c is None or m.epoch != c.epoch or c.holder is None:
            return
        grace = 2 * self.ctx.cfg.voss.scheduler.heartbeat_s + self.ctx.cfg.voss.detection.stall_window_s
        if self.now - c.appointed_at < grace:
            return  # a new scheduler without a view yet defers everything: not a fault
        if m.idle_s < self.ctx.cfg.voss.router.T_dispatch:
            return  # the router still sees new dispatches accepted: over-full, not stuck (router evidence)
        self._suspect_scheduler(c, "stall")

    def _keepalive(self, m: KeepaliveSummary) -> None:
        c = self.book.clusters.get(int(m.cluster))
        if c is None or c.holder is None or m.epoch != c.epoch or m.worker != c.holder[0]:
            return
        c.last_keepalive, c.summary = self.now, m
        sc = self.ctx.cfg.voss.succession
        self.send(("sched", m.worker), Lease(m.cluster, m.epoch, self.now + sc.lease_s))
        dc = self.ctx.cfg.voss.detection
        if dc.mode == "progress" and m.stuck_workers >= dc.stall_n:
            self._suspect_scheduler(c, "unaccepted")  # its own dispatches vanish: its host drops them
            return
        if m.decide_p90_s >= 0:  # periods without decisions say nothing
            c.slow_periods = c.slow_periods + 1 if m.decide_p90_s > dc.T_decide_max else 0
        if dc.mode == "progress" and c.slow_periods >= dc.decide_periods:  # consecutive slow keepalive periods
            c.slow_periods = 0
            self._handover(c, "decision_slo")

    def _handover(self, c: Cluster, reason: str) -> None:
        """Planned handover (doc 07 §3): the scheduler flushes a checkpoint, then the CAS happens."""
        if c.holder is None or c.handover_pending or c.cas_pending:
            return
        c.handover_pending = True
        self.send(("sched", c.holder[0]), Handover(ClusterId(c.cid), c.epoch))
        self.after(self.ctx.cfg.voss.succession.handover_wait_s, self._handover_now, c.cid, c.epoch, reason)

    def _handover_now(self, cid: int, epoch: int, reason: str) -> None:
        c = self.book.clusters.get(cid)
        if c is not None and c.epoch == epoch:
            c.handover_pending = False
            self._suspect_scheduler(c, reason)

    def _checkpoint(self, m: PutCheckpoint) -> None:
        ck = m.checkpoint
        c = self.book.clusters.get(ck.cluster)
        if c is not None and ck.epoch == c.epoch:  # epoch-fenced (doc 08 §3)
            c.checkpoint = ck

    # --- appointment -------------------------------------------------------------------------------------------
    def _rank(self, c: Cluster, exclude: frozenset[WorkerId]) -> list[WorkerId]:
        """Succession list (doc 07 §3): speed × assurance × centrality × remaining session; standby first."""
        mem = self.book.members
        lat0, lon0 = self.book.centroid(c)
        cands = {}
        for w in sorted(c.members):
            m = mem[w]
            km = float(great_circle(np.array([m.lat]), np.array([m.lon]), lat0, lon0)[0])
            life = min(1.0, max(0.0, m.expiry - self.now) / 3600.0)
            cands[w] = (m.speed, m.assurance * (0.5 if m.draining else 1.0), 1.0 / (1.0 + km / 1000.0), 0.1 + life)
        order = rank(cands, exclude)
        if c.standby in order:
            order.remove(c.standby)
            order.insert(0, c.standby)
        return order

    def _appoint(self, c: Cluster, exclude: frozenset[WorkerId]) -> None:
        if c.cas_pending:
            return
        order = self._rank(c, exclude)
        if not order:
            return
        w = order[0]
        c.cas_pending = True
        delay = self.ctx.clock.charge("orchestrate", work=len(c.members))
        cas = DbCasEpoch(ClusterId(c.cid), c.epoch, c.epoch + 1, w, self.book.members[w].cert_id, self.addr)
        self.after(delay, self.send, self.ctx.directory.opdb, cas)

    def _cas_result(self, m: DbCasResult) -> None:
        c = self.book.clusters.get(int(m.cluster))
        if c is None:
            return
        c.cas_pending = False
        if not m.ok:
            c.epoch = m.epoch
            self._appoint(c, frozenset())
            return
        old, c.epoch = c.holder, m.epoch
        rec = self.book.members.get(m.holder)
        if rec is None or rec.cert_id != m.cert_id or m.holder not in c.members:
            self._appoint(c, frozenset())  # the appointee left or moved meanwhile
            return
        if old is not None:
            self.send(("sched", old[0]), Revoke(ClusterId(c.cid), m.epoch))
        c.holder, c.last_keepalive, c.summary, c.appointed_at = (m.holder, m.cert_id), self.now, None, self.now
        standby = self._pick_standby(c)
        sb_addr: Addr | None = ("sched", standby) if standby is not None else None
        members = tuple(sorted(c.members))
        appoint = Appoint(ClusterId(c.cid), m.epoch, m.cert_id, members, c.checkpoint, sb_addr, old is not None)
        self.send(("sched", m.holder), appoint)
        if standby is not None:
            self.send(("sched", standby), Standby(ClusterId(c.cid), m.epoch, members))
        self._role_record(c, m.holder, standby, m.epoch)
        self._send_scores(c.cid)
        self.ctx.rec.log(
            Table.EVENTS, t=self.now, kind="appoint", worker=m.holder, cert=m.cert_id, value=m.epoch, cluster=c.cid
        )
        for r in self.ctx.directory.routers:
            self.send(r, SchedulerAddr(ClusterId(c.cid), m.epoch, ("sched", m.holder)))

    def _pick_standby(self, c: Cluster) -> WorkerId | None:
        k = self.ctx.cfg.voss.succession.standbys
        if k <= 0 or c.holder is None or len(c.members) < 2:
            c.standby = None
            return None
        order = self._rank_without_standby(c, frozenset({c.holder[0]}))
        c.standby = order[0] if order else None
        return c.standby

    def _rank_without_standby(self, c: Cluster, exclude: frozenset[WorkerId]) -> list[WorkerId]:
        saved, c.standby = c.standby, None
        try:
            return self._rank(c, exclude)
        finally:
            c.standby = saved
