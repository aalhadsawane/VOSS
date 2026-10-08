"""Regional router (doc 03 §3, doc 07 §2, doc 09 §3): pending table, ``ENQUEUE``/``ASSIGNED``/``INPUT``, dispatch
watchdog, results with attested receipts (batched to the DB), and the per-invocation latency breakdown."""

from __future__ import annotations

from dataclasses import dataclass, field

from voss.core.ids import Addr, InvId, NodeId, WorkerId
from voss.core.kernel import Handle
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
from voss.core.types import Invocation, Outcome
from voss.metrics.schema import Table
from voss.runtime.actor import Actor, ActorContext
from voss.world.workload import SLO_CLASSES


@dataclass
class Pending:
    inv: Invocation
    t_route: float = 0.0
    t_first_enqueue: float | None = None
    resends: int = 0
    accepted: bool = False
    workers: dict[int, WorkerId] = field(default_factory=dict)
    timers: list[Handle] = field(default_factory=list)


class Router(Actor):
    role = "router"

    def __init__(self, host: NodeId, ctx: ActorContext, region: str) -> None:
        super().__init__(host, ctx)
        self.region = region
        self.sched: Addr | None = None
        self.epoch = 0
        self.pending: dict[InvId, Pending] = {}
        self.unrouted: list[InvId] = []
        self.finished: set[InvId] = set()
        self.revoked: set[str] = set()
        self.batch: list[tuple[Receipt, float, str]] = []
        self.after(ctx.cfg.voss.router.receipt_batch_s, self._flush_tick)

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
                self._finalize(p, "rejected", None)

    # --- request path ------------------------------------------------------------------------------------------
    def _invoke(self, inv: Invocation) -> None:
        p = Pending(inv)
        self.pending[inv.id] = p
        give_up = self.ctx.cfg.voss.router.give_up_s[SLO_CLASSES[int(inv.slo_class)]]
        p.timers.append(self.after(max(0.0, inv.t_arrive + give_up - self.now), self._give_up, inv.id))
        self.after(self.ctx.clock.charge("route", work=1), self._route, inv.id)

    def _route(self, inv_id: InvId) -> None:
        if inv_id not in self.pending:
            return
        if self.sched is None:
            self.unrouted.append(inv_id)
            return
        self._enqueue(inv_id)

    def _enqueue(self, inv_id: InvId) -> None:
        p = self.pending.get(inv_id)
        if p is None or self.sched is None:
            return
        if p.t_first_enqueue is None:
            p.t_first_enqueue = self.now
        self.send(self.sched, Enqueue(p.inv, self.addr, self.now))
        p.timers.append(self.after(self.ctx.cfg.voss.router.T_dispatch, self._watchdog, inv_id))

    def _watchdog(self, inv_id: InvId) -> None:
        """Doc 07 §2: no ``ACCEPTED`` within ``T_dispatch`` → re-send (bounded)."""
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
        if m.epoch < self.epoch:
            return
        self.sched, self.epoch = m.addr, m.epoch
        if self.sched is None:
            return
        waiting, self.unrouted = self.unrouted, []
        for inv_id in waiting:
            self._enqueue(inv_id)
        for inv_id, p in sorted(self.pending.items()):
            if p.t_first_enqueue is not None and not p.accepted:
                self._enqueue(inv_id)

    def _assigned(self, m: Assigned) -> None:
        p = self.pending.get(m.inv)
        if p is None or m.attempt in p.workers:
            return  # unknown, finished, or a re-announced assignment whose input is already on its way
        p.workers[m.attempt] = m.worker
        self.send(("agent", m.worker), Input(m.inv, m.attempt, m.token, int(p.inv.in_bytes)))

    # --- completion ---------------------------------------------------------------------------------------------
    def _result(self, o: Outcome, r: Receipt) -> None:
        p = self.pending.get(o.inv)
        if p is None:
            if o.inv in self.finished:
                self.ctx.rec.log(
                    Table.EVENTS, t=self.now, kind="duplicate_result", worker=o.worker, value=o.attempt, inv=int(o.inv)
                )
            return
        if r.cert_id in self.revoked or r.inv != o.inv:
            self.ctx.rec.log(
                Table.EVENTS, t=self.now, kind="receipt_rejected", worker=o.worker, value=o.attempt, inv=int(o.inv)
            )
            return
        self.batch.append((r, self.now, self.region))
        self._finalize(p, "ok", o)

    def _give_up(self, inv_id: InvId) -> None:
        p = self.pending.get(inv_id)
        if p is not None:
            self._finalize(p, "timeout", None)

    def finalize_all(self) -> None:
        """End of run: still-pending invocations get a terminal ``unfinished`` row."""
        for _, p in sorted(self.pending.items()):
            self._finalize(p, "unfinished", None)
        self._flush()

    def _finalize(self, p: Pending, status: str, o: Outcome | None) -> None:
        for h in p.timers:
            self.ctx.kernel.cancel(h)
        del self.pending[p.inv.id]
        self.finished.add(p.inv.id)
        self.ctx.rec.log(Table.INVOCATIONS, **self._row(p, status, o))

    def _row(self, p: Pending, status: str, o: Outcome | None) -> dict[str, object]:
        inv, now = p.inv, self.now
        first = p.t_first_enqueue if p.t_first_enqueue is not None else now
        row: dict[str, object] = {
            "inv": int(inv.id),
            "fn": inv.fn,
            "tenant": inv.tenant,
            "origin": inv.origin,
            "router": self.region,
            "slo_class": int(inv.slo_class),
            "t_arrive": inv.t_arrive,
            "t_done": now,
            "e2e": now - inv.t_arrive,
            "deadline": inv.deadline,
            "outcome": status,
            "resends": p.resends,
            "route": first - inv.t_arrive,
        }
        if o is None:
            row.update(worker=-1, attempts=len(p.workers), met=False, start_level="", tier="", trust_cold=False)
            return row
        t = o.timings
        row.update(
            worker=int(o.worker),
            attempts=o.attempt + 1,
            met=now - inv.t_arrive <= inv.deadline,
            retry=t.t_enqueue - first,
            batch_wait=t.batch_wait,
            decide=t.t_dispatch - t.t_enqueue - t.batch_wait,
            net_in=(t.t_received - t.t_dispatch) + t.input_wait,
            wait=t.wait,
            trust=t.trust,
            startup=t.startup,
            exec=t.exec,
            net_out=now - t.t_sent,
            start_level=o.start_level,
            tier=o.tier,
            trust_cold=o.trust_cold,
        )
        return row

    def _flush_tick(self) -> None:
        self._flush()
        self.after(self.ctx.cfg.voss.router.receipt_batch_s, self._flush_tick)

    def _flush(self) -> None:
        if self.batch:
            self.send(self.ctx.directory.opdb, DbAppendReceipts(tuple(self.batch)))
            self.batch = []
