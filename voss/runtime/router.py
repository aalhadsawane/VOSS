"""Regional router (doc 07 §2, doc 09 §3, D-83): forwards each invocation to the provider-hosted scheduler, keeps the
pending table, re-sends an invocation the scheduler has not assigned within ``T_dispatch``, streams the input to the
assigned worker, and verifies signed receipts (batched to the DB)."""

from __future__ import annotations

import numpy as np

from voss.core.ids import Addr, InvId, NodeId
from voss.core.messages import (
    Accepted,
    Assigned,
    DbAppendReceipts,
    Enqueue,
    Input,
    Invoke,
    Message,
    Receipt,
    Reject,
    Result,
    RevokeSession,
    SchedulerAddr,
)
from voss.core.messages_acct import ReceiptRow
from voss.core.types import Invocation, Outcome
from voss.metrics.schema import Table
from voss.runtime.actor import Actor, ActorContext
from voss.runtime.routerlib.pending import InvCtx, Pending, inv_ctx, row
from voss.world.workload import SLO_CLASSES


class Router(Actor):
    role = "router"

    def __init__(self, host: NodeId, ctx: ActorContext, region: str, origins: np.ndarray) -> None:
        super().__init__(host, ctx)
        self.region, self.origins = region, origins  # origins[i] = (lat, lon) of metro i
        self.scheds: dict[int, tuple[int, Addr]] = {}
        self.epochs: dict[int, int] = {}
        self.pending: dict[InvId, Pending] = {}
        self.unrouted: list[InvId] = []
        self.finished: dict[InvId, InvCtx] = {}
        self.revoked: set[str] = set()
        self.batch: list[ReceiptRow] = []
        rc = ctx.cfg.voss.router
        self.after(rc.receipt_batch_s, self._flush_tick)

    def on_message(self, msg: Message) -> None:
        if isinstance(msg, Invoke):
            self._invoke(msg.inv)
        elif isinstance(msg, Assigned):
            self._assigned(msg)
        elif isinstance(msg, Accepted):
            p = self.pending.get(msg.inv)
            if p is not None:
                p.accepted = True
        elif isinstance(msg, Result):
            self._result(msg.outcome, msg.receipt)
        elif isinstance(msg, SchedulerAddr):
            self._scheduler(msg)
        elif isinstance(msg, RevokeSession):
            self.revoked.add(msg.cert_id)
        elif isinstance(msg, Reject):
            p = self.pending.get(msg.inv)
            if p is not None:
                # the scheduler gave up (attempts used up, or no worker fits a retry, plan V7.1): lost, reported at once
                self._finalize(p, "abandoned" if msg.reason in ("no_fit", "gave_up") else "rejected", None)

    # --- request path ------------------------------------------------------------------------------------------
    def _invoke(self, inv: Invocation) -> None:
        p = Pending(inv)
        self.pending[inv.id] = p
        give_up = self.ctx.cfg.voss.router.give_up_s[SLO_CLASSES[int(inv.slo_class)]]
        p.timers.append(self.after(max(0.0, inv.t_arrive + give_up - self.now), self._give_up, inv.id))
        self.after(self.ctx.clock.charge("route", work=max(1, len(self.scheds))), self._route, inv.id)

    def _choose(self, p: Pending) -> int | None:
        """The one scheduler (cluster 0), once the orchestrator has announced it."""
        return min(self.scheds) if self.scheds else None

    def _route(self, inv_id: InvId) -> None:
        p = self.pending.get(inv_id)
        if p is None:
            return
        cluster = self._choose(p)
        if cluster is None:
            self.unrouted.append(inv_id)
            return
        p.cluster, p.t_cluster, p.accepted = cluster, self.now, False
        self._enqueue(inv_id)

    def _enqueue(self, inv_id: InvId) -> None:
        p = self.pending.get(inv_id)
        if p is None or p.cluster not in self.scheds:
            return
        if p.t_first_enqueue is None:
            p.t_first_enqueue = self.now
        self.send(self.scheds[p.cluster][1], Enqueue(p.inv, self.addr, self.now))
        p.timers.append(self.after(self.ctx.cfg.voss.router.T_dispatch, self._watchdog, inv_id))

    def _watchdog(self, inv_id: InvId) -> None:
        """Doc 07 §2: no ``ACCEPTED`` within ``T_dispatch`` → re-send to the scheduler, up to ``max_resends`` times."""
        p = self.pending.get(inv_id)
        if p is None or p.accepted:
            return
        if p.resends < self.ctx.cfg.voss.router.max_resends:
            p.resends += 1
            self.ctx.rec.log(
                Table.EVENTS, t=self.now, kind="dispatch_watchdog", worker=-1, value=p.resends, inv=int(inv_id)
            )
            self._enqueue(inv_id)

    def _scheduler(self, m: SchedulerAddr) -> None:
        cid = int(m.cluster)
        if m.epoch < self.epochs.get(cid, -1):
            return
        self.epochs[cid] = m.epoch
        if m.addr is None:
            self.scheds.pop(cid, None)
        else:
            self.scheds[cid] = (m.epoch, m.addr)
        waiting, self.unrouted = self.unrouted, []
        for inv_id in waiting:
            self._route(inv_id)
        for inv_id, p in sorted(self.pending.items()):
            if p.cluster == cid and p.t_first_enqueue is not None and not p.accepted:
                if m.addr is None:
                    self._route(inv_id)
                else:
                    self._enqueue(inv_id)

    def _assigned(self, m: Assigned) -> None:
        if m.audit_bytes >= 0:  # the router keeps an audited invocation's input until the audit ends (plan V7.3)
            self.send(("agent", m.worker), Input(m.inv, m.attempt, m.token, m.audit_bytes))
            return
        p = self.pending.get(m.inv)
        if p is None or m.attempt in p.workers:
            return  # unknown, finished, or a re-announced assignment whose input is already on its way
        p.workers[m.attempt] = m.worker
        self.send(("agent", m.worker), Input(m.inv, m.attempt, m.token, int(p.inv.in_bytes)))

    # --- completion ---------------------------------------------------------------------------------------------
    def _result(self, o: Outcome, r: Receipt) -> None:
        """Doc 09 §3: verify the receipt against the session certificate (revocation list) and log it. A result of
        an invocation that already finished (the slower of two attempts) is logged as ``duplicate``."""
        p = self.pending.get(o.inv)
        ic = inv_ctx(p) if p is not None else self.finished.get(o.inv)
        if ic is None:
            return
        if r.cert_id in self.revoked or r.inv != o.inv:
            self.ctx.rec.log(
                Table.EVENTS, t=self.now, kind="receipt_rejected", worker=o.worker, value=o.attempt, inv=int(o.inv)
            )
            return
        status = "ok" if p is not None else "duplicate"
        self.batch.append(ReceiptRow(r.inv, r.attempt, r.worker, status, self.now, self.region, r, *ic))
        if p is None:
            self.ctx.rec.log(
                Table.EVENTS, t=self.now, kind="duplicate_result", worker=o.worker, value=o.attempt, inv=int(o.inv)
            )
            return
        self._finalize(p, "ok", o)

    def _give_up(self, inv_id: InvId) -> None:
        p = self.pending.get(inv_id)
        if p is not None:
            self._finalize(p, "timeout", None)

    def finalize_all(self) -> None:
        """End of run: still-pending invocations get a terminal ``unfinished`` row."""
        for _, p in sorted(self.pending.items()):
            self._finalize(p, "unfinished", None)
        self.flush()

    def _finalize(self, p: Pending, status: str, o: Outcome | None) -> None:
        for h in p.timers:
            self.ctx.kernel.cancel(h)
        del self.pending[p.inv.id]
        ic = self.finished[p.inv.id] = inv_ctx(p)
        won = o.attempt if o is not None else -1
        for a, w in sorted(p.workers.items()):
            if a != won:  # doc 09 §3: attempts without the accepted result
                self.batch.append(ReceiptRow(p.inv.id, a, w, "no_result", self.now, self.region, None, *ic))
        r = row(p, self.region, status, o, self.now)
        self.ctx.rec.log(Table.INVOCATIONS, **r)

    def _flush_tick(self) -> None:
        self.flush()
        self.after(self.ctx.cfg.voss.router.receipt_batch_s, self._flush_tick)

    def flush(self) -> None:
        """Batched, asynchronous append to the DB after the signature checks' CPU time (doc 08 §3.2, E13)."""
        if self.batch:
            verified = sum(1 for b in self.batch if b.receipt is not None)
            delay = self.ctx.clock.charge("verify", work=verified)
            self.after(delay, self.send, self.ctx.directory.opdb, DbAppendReceipts(tuple(self.batch)))
            self.batch = []
