"""Operational DB actor (doc 08 §3), private to the orchestrator tier: the receipts table written by routers."""

from __future__ import annotations

from voss.core.ids import NodeId
from voss.core.messages import DbAppendReceipts, Message
from voss.core.messages_acct import ReceiptRow
from voss.metrics.schema import Table
from voss.runtime.actor import Actor, ActorContext


class OpDb(Actor):
    role = "opdb"

    def __init__(self, host: NodeId, ctx: ActorContext) -> None:
        super().__init__(host, ctx)
        self.receipts = 0

    def on_message(self, msg: Message) -> None:
        if isinstance(msg, DbAppendReceipts):
            for r in msg.rows:
                if isinstance(r, ReceiptRow):
                    self._receipt(r)

    def _receipt(self, r: ReceiptRow) -> None:
        self.receipts += 1
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
