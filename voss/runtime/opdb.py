"""Operational DB actor (doc 08 §3), private to the orchestrator tier: epoch CAS and the receipts table."""

from __future__ import annotations

from voss.core.ids import ClusterId, NodeId, WorkerId
from voss.core.messages import DbAppendReceipts, DbCasEpoch, DbCasResult, Message
from voss.metrics.schema import Table
from voss.runtime.actor import Actor, ActorContext


class OpDb(Actor):
    role = "opdb"

    def __init__(self, host: NodeId, ctx: ActorContext) -> None:
        super().__init__(host, ctx)
        self.epochs: dict[ClusterId, tuple[int, WorkerId, str]] = {}
        self.receipts = 0

    def on_message(self, msg: Message) -> None:
        if isinstance(msg, DbCasEpoch):
            cur = self.epochs.get(msg.cluster, (0, WorkerId(-1), ""))
            ok = cur[0] == msg.expect
            if ok:
                self.epochs[msg.cluster] = (msg.new, msg.holder, msg.cert_id)
            ep, holder, cert = self.epochs.get(msg.cluster, cur)
            self.send(msg.reply_to, DbCasResult(msg.cluster, ep, holder, cert, ok))
        elif isinstance(msg, DbAppendReceipts):
            for r, t_result, router in msg.rows:
                self.receipts += 1
                self.ctx.rec.log(
                    Table.RECEIPTS,
                    t=self.now,
                    inv=r.inv,
                    attempt=r.attempt,
                    worker=r.worker,
                    cert=r.cert_id,
                    epoch=r.epoch,
                    exec_s=r.exec_s,
                    ref_work_units=r.ref_work_units,
                    t_result=t_result,
                    router=router,
                )
