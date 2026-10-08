"""Orchestrator actor (doc 03 §2, doc 07 §3, doc 08): membership and scheduler appointment by epoch CAS in the DB.

P2: one cluster. Appointment is instance-bound (cluster, epoch, session-cert id). A scheduler whose keepalives stop
is replaced (P6 adds progress-based detection, checkpoints, standbys and planned handover).
"""

from __future__ import annotations

from dataclasses import dataclass

from voss.core.ids import ClusterId, NodeId, WorkerId
from voss.core.messages import (
    Appoint,
    DbCasEpoch,
    DbCasResult,
    DrainNotice,
    Join,
    KeepaliveSummary,
    Leave,
    Membership,
    Message,
    Revoke,
    RevokeSession,
    SchedulerAddr,
)
from voss.metrics.schema import Table
from voss.policy.succession_rank import rank
from voss.runtime.actor import Actor, ActorContext


@dataclass
class Member:
    cert_id: str
    expiry: float
    assurance: float
    speed: float
    slots: int
    domain: int
    draining: bool = False


class Orchestrator(Actor):
    role = "orch"

    def __init__(self, host: NodeId, ctx: ActorContext) -> None:
        super().__init__(host, ctx)
        self.cluster = ClusterId(0)
        self.members: dict[WorkerId, Member] = {}
        self.epoch = 0
        self.holder: tuple[WorkerId, str] | None = None
        self.last_keepalive = 0.0
        self.cas_pending = False
        self.dirty = False
        self.after(ctx.cfg.voss.orchestrator.check_s, self._check)

    def on_message(self, msg: Message) -> None:
        if isinstance(msg, Join):
            self.members[msg.worker] = Member(msg.cert_id, msg.expiry, msg.assurance, msg.speed, msg.slots, msg.domain)
            self._changed()
        elif isinstance(msg, Leave | RevokeSession):
            self._remove(msg.worker, msg.cert_id)
        elif isinstance(msg, DrainNotice):
            m = self.members.get(msg.worker)
            if m is not None:
                m.draining = True  # hint: deprioritized for appointment only (doc 07 §4)
        elif isinstance(msg, KeepaliveSummary):
            if self.holder is not None and msg.epoch == self.epoch and msg.worker == self.holder[0]:
                self.last_keepalive = self.now
        elif isinstance(msg, DbCasResult):
            self._cas_result(msg)

    def _remove(self, w: WorkerId, cert_id: str) -> None:
        m = self.members.get(w)
        if m is None or m.cert_id != cert_id:
            return
        del self.members[w]
        if self.holder is not None and self.holder[0] == w:
            self._appoint(exclude=frozenset({w}))
        self._changed()

    def _changed(self) -> None:
        if self.holder is None:
            self._appoint(frozenset())
        elif not self.dirty:
            self.dirty = True
            self.after(0.2, self._push_membership)

    def _push_membership(self) -> None:
        self.dirty = False
        if self.holder is not None:
            self.send(("sched", self.holder[0]), Membership(self.cluster, self.epoch, tuple(sorted(self.members))))

    def _check(self) -> None:
        cfg = self.ctx.cfg.voss.orchestrator
        if self.holder is not None and self.now - self.last_keepalive > cfg.keepalive_timeout_s:
            self.ctx.rec.log(
                Table.EVENTS, t=self.now, kind="scheduler_timeout", worker=self.holder[0], value=self.epoch
            )
            self._appoint(exclude=frozenset({self.holder[0]}))
        self.after(cfg.check_s, self._check)

    def _appoint(self, exclude: frozenset[WorkerId]) -> None:
        if self.cas_pending:
            return
        cands = {w: (m.speed, m.assurance * (0.5 if m.draining else 1.0)) for w, m in self.members.items()}
        order = rank(cands, exclude)
        if not order:
            if self.holder is not None:
                self._install(None, self.epoch)
            return
        w = order[0]
        self.cas_pending = True
        delay = self.ctx.clock.charge("orchestrate", work=len(self.members))
        cas = DbCasEpoch(self.cluster, self.epoch, self.epoch + 1, w, self.members[w].cert_id, self.addr)
        self.after(delay, self.send, self.ctx.directory.opdb, cas)

    def _cas_result(self, m: DbCasResult) -> None:
        self.cas_pending = False
        if not m.ok:
            self.epoch = m.epoch
            self._appoint(frozenset())
            return
        old = self.holder
        self.epoch = m.epoch
        if m.holder not in self.members or self.members[m.holder].cert_id != m.cert_id:
            self._appoint(frozenset())  # the appointee left meanwhile
            return
        if old is not None:
            self.send(("sched", old[0]), Revoke(self.cluster, m.epoch))
        self._install((m.holder, m.cert_id), m.epoch)

    def _install(self, holder: tuple[WorkerId, str] | None, epoch: int) -> None:
        self.holder = holder
        self.last_keepalive = self.now
        addr = ("sched", holder[0]) if holder is not None else None
        if holder is not None:
            self.send(("sched", holder[0]), Appoint(self.cluster, epoch, holder[1], tuple(sorted(self.members))))
            self.ctx.rec.log(Table.EVENTS, t=self.now, kind="appoint", worker=holder[0], cert=holder[1], value=epoch)
        for r in self.ctx.directory.routers:
            self.send(r, SchedulerAddr(self.cluster, epoch, addr))
