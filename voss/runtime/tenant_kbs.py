"""Tenant key broker (doc 04 §6): releases the tenant key, wrapped to the session key, only to holders of a valid
verifier-issued session certificate. The scheduler and orchestrator never see keys."""

from __future__ import annotations

from voss.core.ids import NodeId, TenantId
from voss.core.messages import Key, KeyRequest, Message
from voss.metrics.schema import Table
from voss.runtime.actor import Actor, ActorContext


class TenantKbs(Actor):
    role = "kbs"

    def __init__(self, host: NodeId, ctx: ActorContext, tenant: TenantId) -> None:
        super().__init__(host, ctx)
        self.tenant = tenant
        self.released = 0

    def on_message(self, msg: Message) -> None:
        if not isinstance(msg, KeyRequest):
            return
        ok = msg.tenant == self.tenant and msg.cert_expiry > self.now
        if ok:
            self.released += 1
            self.ctx.rec.log(
                Table.EVENTS,
                t=self.now,
                kind="key_release",
                worker=msg.worker,
                cert=msg.cert_id,
                value=0.0,
                tenant=msg.tenant,
            )
        self.send(msg.reply_to, Key(msg.tenant, msg.cert_id, ok))
