"""Settlement job (doc 09 §4, doc 08 §3): every ``settle_s`` it reads the rows appended to the DB since its cursor
(receipts, scheduler roles, cache accruals), computes credits after the charged CPU time, writes ``credits`` and
feeds verified on-time and late work back to the orchestrator's reputation (doc 09 §2)."""

from __future__ import annotations

import numpy as np

from voss.core.ids import NodeId, WorkerId
from voss.core.messages import Message
from voss.core.messages_acct import Settled, SettleRead, SettleRows
from voss.metrics.schema import Table
from voss.policy.credits import CreditParams, Ledger, Settlement, settle
from voss.runtime.actor import Actor, ActorContext


class Accounting(Actor):
    role = "acct"

    def __init__(self, host: NodeId, ctx: ActorContext) -> None:
        super().__init__(host, ctx)
        ac = ctx.cfg.voss.accounting
        self.params = CreditParams(
            ac.late_factor, ac.cache_per_gb_h, ac.sched_per_assign, ac.sched_per_h, ac.standby_per_h
        )
        self.ledger = Ledger()
        self.cursor = 0
        self.after(ac.settle_s, self._tick)

    def on_message(self, msg: Message) -> None:
        if isinstance(msg, SettleRows):
            self.cursor = msg.cursor
            self.ledger.add_roles(msg.roles)
            delay = self.ctx.clock.charge("settle", work=len(msg.receipts) + len(msg.accruals))
            self.after(delay, self._write, msg, delay)

    def _tick(self) -> None:
        self.settle_now()
        self.after(self.ctx.cfg.voss.accounting.settle_s, self._tick)

    def settle_now(self) -> None:
        self.send(self.ctx.directory.opdb, SettleRead(self.cursor, self.addr))

    def _write(self, m: SettleRows, cpu_s: float) -> None:
        s = settle(m.receipts, m.accruals, self.ledger, self.now, self.params)
        for (w, kind), (amount, n) in sorted(s.credits.items()):
            self.ctx.rec.log(Table.CREDITS, t=self.now, worker=w, kind=kind, amount=amount, n=int(n))
        self._log(m, s, cpu_s)
        workers = sorted(set(s.on_time) | set(s.late))
        rows = tuple((WorkerId(w), s.on_time.get(w, 0.0), s.late.get(w, 0.0)) for w in workers)
        if rows:
            self.send(self.ctx.directory.orchestrator, Settled(rows))

    def _log(self, m: SettleRows, s: Settlement, cpu_s: float) -> None:
        lat = s.latency
        q = np.quantile(lat, [0.5, 0.99]) if len(lat) else np.array([np.nan, np.nan])
        self.ctx.rec.log(
            Table.EVENTS,
            t=self.now,
            kind="settlement",
            worker=-1,
            value=float(len(m.receipts)),
            n_paid=len(lat),
            lat_p50=float(q[0]),
            lat_p99=float(q[1]),
            lat_max=float(lat.max()) if len(lat) else np.nan,
            cpu_s=cpu_s,
        )
