"""Sampled audit in the scheduler (docs/REVISION_PLAN.md V7.3; policy in ``policy.audit``).

After the first correct-status outcome of an audited invocation, the scheduler dispatches an audit attempt to another
holder outside every used failure domain and compares the result digests it reports (a digest is metadata: no tenant
data or key reaches the scheduler). On a mismatch it asks a third holder; the worker in the minority is banned through
the verifier. Audit attempts never reach the client: the router drops their results as duplicates.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import TYPE_CHECKING, Any

import numpy as np

from voss.core.ids import Addr, InvId, TenantId, WorkerId
from voss.core.messages import Assigned, Ban, Dispatch
from voss.core.types import Invocation, Outcome
from voss.metrics.schema import Table
from voss.policy.audit import minority, select, target
from voss.runtime.actor import ActorContext
from voss.runtime.schedlib.provider_host import ProviderHost
from voss.runtime.schedlib.viewcache import ViewCache


@dataclass
class AuditRec:
    inv: Invocation
    router: Addr
    digests: dict[WorkerId, int] = field(default_factory=dict)
    pending: dict[int, WorkerId] = field(default_factory=dict)  # attempt → worker
    next_attempt: int = 0


class AuditMixin:
    ctx: ActorContext
    views: ViewCache
    audits: dict[InvId, AuditRec]
    gen: np.random.Generator
    epoch: int
    token: int
    addr: Addr
    hl: ProviderHost

    if TYPE_CHECKING:

        @property
        def now(self) -> float: ...
        def send(self, dst: Addr, msg: Any) -> bool: ...
        def eligible(self) -> set[WorkerId]: ...

    def _maybe_audit(self, inv: Invocation, router: Addr, o: Outcome, next_attempt: int) -> None:
        if not select(inv.idempotent, self.gen, self.ctx.cfg.voss.audit.p):
            return
        rec = AuditRec(inv, router, {o.worker: o.digest}, next_attempt=next_attempt)
        self.audits[inv.id] = rec
        self._audit_dispatch(rec)

    def _audit_dispatch(self, rec: AuditRec) -> None:
        st = self.views.store.states
        ws = sorted(w for w in self.eligible() if w in st)
        holder = [TenantId(rec.inv.tenant) in st[w].trust for w in ws]
        used = set(rec.digests) | set(rec.pending.values())
        w = target(ws, [st[x].domain for x in ws], holder, used, self.gen)
        if w is None:
            self.ctx.rec.log(Table.EVENTS, t=self.now, kind="audit_no_target", worker=-1, inv=int(rec.inv.id))
            self.audits.pop(rec.inv.id, None)
            return
        a = rec.next_attempt
        rec.next_attempt += 1
        rec.pending[a] = w
        self.token += 1
        inv = replace(rec.inv, attempt=a)
        d = Dispatch(inv, self.epoch, self.token, rec.router, self.hl.cert_id, self.now, self.now, self.addr, 0.0, 0)
        self.send(("agent", w), d)
        self.send(rec.router, Assigned(inv.id, a, w, self.epoch, self.token, 0, int(inv.in_bytes)))
        self.ctx.rec.log(Table.EVENTS, t=self.now, kind="audit", worker=w, inv=int(rec.inv.id), value=float(a))

    def _audit_outcome(self, o: Outcome) -> bool:
        """Handle an audit attempt's outcome; ``False`` when ``o`` is not an audit attempt."""
        rec = self.audits.get(o.inv)
        if rec is None or o.attempt not in rec.pending:
            return False
        del rec.pending[o.attempt]
        if o.status != "ok":
            self._audit_dispatch(rec)  # the audit attempt failed: ask another holder
            return True
        rec.digests[o.worker] = o.digest
        bad = minority(rec.digests)
        if bad is None:
            self._audit_dispatch(rec)  # a tie: a third holder decides
            return True
        del self.audits[o.inv]
        for w in bad:
            s = self.views.store.states.get(w)
            self.ctx.rec.log(Table.EVENTS, t=self.now, kind="audit_mismatch", worker=w, inv=int(o.inv))
            self.send(self.ctx.directory.verifier, Ban(w, s.cert_id if s is not None else ""))
        return True
