"""Operational DB actor (doc 08 §3), private to the orchestrator tier: epoch CAS, the ``receipts`` table (routers),
``scheduler_roles`` and credit accruals (orchestrator), read in order by the settlement job (doc 09 §4)."""

from __future__ import annotations

from voss.core.ids import ClusterId, NodeId, WorkerId
from voss.core.messages import DbAppendReceipts, DbCasEpoch, DbCasResult, Message
from voss.core.messages_acct import DbAccrual, ReceiptRow, RoleRecord, SettleRead, SettleRows
from voss.metrics.schema import Table
from voss.runtime.actor import Actor, ActorContext

Accrual = tuple[str, WorkerId, float]


class OpDb(Actor):
    role = "opdb"

    def __init__(self, host: NodeId, ctx: ActorContext) -> None:
        super().__init__(host, ctx)
        self.epochs: dict[ClusterId, tuple[int, WorkerId, str]] = {}
        self.receipts = 0
        self.journal: list[ReceiptRow | RoleRecord | Accrual] = []  # append order = settlement read order
        self.offset = 0  # journal entries before this were read by the settlement job and dropped

    def on_message(self, msg: Message) -> None:
        if isinstance(msg, DbCasEpoch):
            cur = self.epochs.get(msg.cluster, (0, WorkerId(-1), ""))
            ok = cur[0] == msg.expect
            if ok:
                self.epochs[msg.cluster] = (msg.new, msg.holder, msg.cert_id)
            ep, holder, cert = self.epochs.get(msg.cluster, cur)
            self.send(msg.reply_to, DbCasResult(msg.cluster, ep, holder, cert, ok))
        elif isinstance(msg, DbAppendReceipts):
            for r in msg.rows:
                if isinstance(r, ReceiptRow):
                    self._receipt(r)
        elif isinstance(msg, RoleRecord):
            self.journal.append(msg)
        elif isinstance(msg, DbAccrual):
            self.journal.extend(msg.rows)
        elif isinstance(msg, SettleRead):
            self._read(msg)

    def _receipt(self, r: ReceiptRow) -> None:
        self.receipts += 1
        self.journal.append(r)
        rc = r.receipt
        self.ctx.rec.log(
            Table.RECEIPTS,
            t=self.now,
            inv=int(r.inv),
            attempt=r.attempt,
            worker=int(r.worker),
            status=r.status,
            cert=rc.cert_id if rc is not None else "",
            epoch=rc.epoch if rc is not None else -1,
            exec_s=rc.exec_s if rc is not None else 0.0,
            ref_work_units=rc.ref_work_units if rc is not None else 0.0,
            t_result=r.t_result,
            router=r.router,
            cluster=r.cluster,
            fn=r.fn,
            tenant=r.tenant,
            t_arrive=r.t_arrive,
            deadline=r.deadline,
        )

    def _read(self, m: SettleRead) -> None:
        start = max(m.cursor, self.offset) - self.offset
        rows = self.journal[start:]
        cursor = self.offset + len(self.journal)
        self.journal, self.offset = [], cursor  # read once: settled rows are rolled up (doc 08 §3.3)
        receipts = tuple(r for r in rows if isinstance(r, ReceiptRow))
        roles = tuple(r for r in rows if isinstance(r, RoleRecord))
        accruals = tuple(r for r in rows if isinstance(r, tuple))
        self.send(m.reply_to, SettleRows(cursor, receipts, roles, accruals, self.now))
