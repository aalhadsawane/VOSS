"""Backup attempts and deadline-fit retries (docs/REVISION_PLAN.md V7.1).

- A backup attempt goes only to a key holder in a different failure domain from every live attempt, and only when its
  predicted mean completion fits the remaining deadline. The first result wins; the others are cancelled.
- A retry follows the same fit rule. If no worker fits, the invocation is reported as missed at once (``Reject`` with
  reason ``no_fit``) instead of being started cold.
- At its deadline an invocation leaves the in-flight table, so it no longer counts as queued work. If attempts are still
  silent, the router reports it lost; if none is running (a retry is pending), it is reported missed at once.
"""

from __future__ import annotations

from dataclasses import replace
from typing import TYPE_CHECKING, Any

from voss.core.ids import Addr, InvId
from voss.core.messages import Reject
from voss.core.types import Invocation
from voss.metrics.schema import Table
from voss.policy.detect import fits
from voss.runtime.actor import ActorContext
from voss.runtime.schedlib.decide import Timing
from voss.runtime.schedlib.inflight import Copy, Inflight
from voss.runtime.schedlib.viewcache import ViewCache


class BackupMixin:
    ctx: ActorContext
    views: ViewCache
    inflight: dict[InvId, Inflight]
    done: set[InvId]

    if TYPE_CHECKING:

        @property
        def now(self) -> float: ...
        def send(self, dst: Addr, msg: Any) -> bool: ...
        def after(self, dt: float, fn: Any, *args: Any) -> Any: ...
        def _decide(self, ids: list[InvId], windowed: bool) -> None: ...
        def _log_attempt(self, rec: Inflight, c: Copy, result: str) -> None: ...

    def _request_backup(self, rec: Inflight, c: Copy) -> None:
        """Ask for one backup attempt of an idempotent invocation (none for non-idempotent ones)."""
        if not rec.inv.idempotent or rec.deciding or any(x.backup for x in rec.copies.values()):
            return
        rec.want_backup = True
        self._decide([rec.inv.id], False)

    def _variant(self, rec: Inflight) -> Invocation:
        """The invocation as placement sees it: a backup excludes every worker in a live attempt's failure domain."""
        if not rec.want_backup:
            return rec.inv
        st = self.views.store.states
        doms = {st[c.worker].domain for c in rec.copies.values() if c.worker in st}
        same = {w for w, s in st.items() if s.domain in doms}
        live = {c.worker for c in rec.copies.values()}
        return replace(rec.inv, excluded=rec.inv.excluded | live | same, holders_only=True)

    def _fits_or_drop(self, rec: Inflight, backup: bool, t: Timing | None) -> bool:
        """Whether a retry or backup fits the deadline; a misfit retry ends the invocation as missed."""
        if rec.next_attempt == 0 or (t is not None and fits(t.mean, t.budget)):
            return True
        self.ctx.rec.log(Table.EVENTS, t=self.now, kind="no_fit", worker=-1, value=0.0, inv=int(rec.inv.id))
        if not backup and not rec.copies:
            del self.inflight[rec.inv.id]
            self.done.add(rec.inv.id)
            self.send(rec.router, Reject(rec.inv.id, "no_fit"))
        return False

    def _arm_expiry(self, rec: Inflight) -> None:
        self.after(max(0.0, rec.t_deadline - self.now) + 1e-6, self._expire, rec.inv.id)

    def _expire(self, inv: InvId) -> None:
        rec = self.inflight.get(inv)
        if rec is None:
            return
        if rec.deciding:  # a decision is being made: let it finish
            self.after(0.1, self._expire, inv)
            return
        probed = max((c.t_dispatch + c.q_done for c in rec.copies.values()), default=0.0)
        probed += self.ctx.cfg.voss.detection.probe_timeout_s
        if self.now < probed:  # let the watchdog and its probe resolve, so the drop estimate sees silent attempts
            self.after(probed - self.now + 1e-6, self._expire, inv)
            return
        del self.inflight[inv]
        self.done.add(inv)
        for c in sorted(rec.copies.values(), key=lambda x: x.attempt):
            self._log_attempt(rec, c, "expired")
        if not rec.copies:
            self.ctx.rec.log(Table.EVENTS, t=self.now, kind="no_fit", worker=-1, value=0.0, inv=int(inv))
            self.send(rec.router, Reject(inv, "no_fit"))
