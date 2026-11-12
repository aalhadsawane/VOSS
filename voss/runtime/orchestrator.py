"""Orchestrator actor (D-83, docs/REVISION_PLAN.md §2 and V3.1): the membership service of the provider.

There is one scheduler and it runs on provider hardware. The orchestrator appoints it once (epoch 1) when the first
worker joins, tells the routers where it is, and keeps its member list current as sessions start and end. Workers are
all in cluster 0; the scheduler is never replaced, because provider services are trusted for availability (D-03).
"""

from __future__ import annotations

from voss.core.ids import Addr, ClusterId, NodeId, WorkerId
from voss.core.messages import (
    Appoint,
    Assign,
    Join,
    Leave,
    Membership,
    Message,
    RevokeSession,
    SchedulerAddr,
)
from voss.metrics.schema import Table
from voss.runtime.actor import Actor, ActorContext

CLUSTER = ClusterId(0)
EPOCH = 1


class Orchestrator(Actor):
    role = "orch"

    def __init__(self, host: NodeId, ctx: ActorContext, scheduler: Addr, scheduler_cert: str) -> None:
        super().__init__(host, ctx)
        self.scheduler, self.scheduler_cert = scheduler, scheduler_cert
        self.members: dict[WorkerId, str] = {}  # worker -> session certificate id
        self.appointed = False
        self.push_due = False

    def on_message(self, msg: Message) -> None:
        if isinstance(msg, Join):
            self._join(msg)
        elif isinstance(msg, Leave | RevokeSession) and self.members.get(msg.worker) == msg.cert_id:
            del self.members[msg.worker]
            self._changed()

    def _join(self, m: Join) -> None:
        self.members[m.worker] = m.cert_id  # replaces a previous session that ended unannounced
        self.send(("agent", int(m.worker)), Assign(CLUSTER))
        if not self.appointed:
            self._appoint()
        else:
            self._changed()

    def _appoint(self) -> None:
        self.appointed = True
        members = tuple(sorted(self.members))
        self.send(self.scheduler, Appoint(CLUSTER, EPOCH, self.scheduler_cert, members))
        for r in self.ctx.directory.routers:
            self.send(r, SchedulerAddr(CLUSTER, EPOCH, self.scheduler))
        self.ctx.rec.log(Table.EVENTS, t=self.now, kind="appoint", worker=-1, value=EPOCH, cert=self.scheduler_cert)

    def _changed(self) -> None:
        """Membership changes are pushed after 0.2 s, so a burst of joins becomes one message."""
        if not self.push_due:
            self.push_due = True
            self.after(0.2, self._push)

    def _push(self) -> None:
        self.push_due = False
        self.send(self.scheduler, Membership(CLUSTER, EPOCH, tuple(sorted(self.members))))
