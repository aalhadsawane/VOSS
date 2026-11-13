"""Tenant key service (doc 04 §6, D-85): one per tenant, serving the keys of all its functions.

It releases a function key, wrapped to the worker's session key, only to a holder of a valid verifier-issued session
certificate, and only while the function has fewer holders than its budget ``K`` (the tenant's own enforcement of the
budget). A place frees when the worker reports that it dropped the key, when the verifier revokes the worker's session,
or when the certificate the key was released under has expired. The scheduler and orchestrator never see keys.
"""

from __future__ import annotations

from voss.core.ids import NodeId, TenantId, WorkerId
from voss.core.messages import Key, KeyDrop, KeyRequest, KeyRotate, Message, RevokeSession
from voss.metrics.schema import Table
from voss.runtime.actor import Actor, ActorContext

Holding = tuple[str, float]  # session certificate id, its expiry


class TenantKbs(Actor):
    role = "kbs"

    def __init__(self, host: NodeId, ctx: ActorContext, budgets: dict[TenantId, int | None]) -> None:
        super().__init__(host, ctx)
        self.budgets = budgets  # key domain -> K (None = unbounded)
        self.holders: dict[TenantId, dict[WorkerId, Holding]] = {k: {} for k in budgets}
        self.version: dict[TenantId, int] = dict.fromkeys(budgets, 1)
        self.released = 0
        rotate = ctx.cfg.voss.keys.rotate_s
        if rotate is not None:
            self.after(rotate, self._rotate, rotate)

    def _rotate(self, period: float) -> None:
        """Every ``R`` seconds each key gets a new version; holders keep their place and fetch it again (D-85)."""
        for key in sorted(self.version):
            self.version[key] += 1
            self.ctx.rec.log(Table.EVENTS, t=self.now, kind="key_rotate", worker=-1, value=float(self.version[key]),
                             tenant=key)  # fmt: skip
            for w in sorted(self.holders[key]):
                self.send(("agent", int(w)), KeyRotate(key, self.version[key]))
        self.after(period, self._rotate, period)

    def on_message(self, msg: Message) -> None:
        if isinstance(msg, KeyRequest):
            self._request(msg)
        elif isinstance(msg, KeyDrop):
            h = self.holders.get(msg.tenant, {})
            if h.get(msg.worker, ("", 0.0))[0] == msg.cert_id:
                del h[msg.worker]
        elif isinstance(msg, RevokeSession):
            for h in self.holders.values():
                if h.get(msg.worker, ("", 0.0))[0] == msg.cert_id:
                    del h[msg.worker]

    def _request(self, m: KeyRequest) -> None:
        if m.tenant not in self.budgets or m.cert_expiry <= self.now:
            self.send(m.reply_to, Key(m.tenant, m.cert_id, False, "cert"))
            return
        h = self.holders[m.tenant]
        for w in [w for w, (_, exp) in sorted(h.items()) if exp <= self.now]:
            del h[w]  # released under a certificate that has expired since
        k = self.budgets[m.tenant]
        if m.worker not in h and k is not None and len(h) >= k:
            self.ctx.rec.log(
                Table.EVENTS, t=self.now, kind="key_refused", worker=m.worker, value=float(k), tenant=m.tenant
            )
            self.send(m.reply_to, Key(m.tenant, m.cert_id, False, "budget"))
            return
        h[m.worker] = (m.cert_id, m.cert_expiry)
        self.released += 1
        self.ctx.rec.log(
            Table.EVENTS,
            t=self.now,
            kind="key_release",
            worker=m.worker,
            cert=m.cert_id,
            value=float(self.version[m.tenant]),  # key version released
            tenant=m.tenant,
        )
        self.send(m.reply_to, Key(m.tenant, m.cert_id, True))
