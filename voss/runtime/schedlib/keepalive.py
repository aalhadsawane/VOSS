"""Scheduler side of the histogram keep-alive baseline (doc 03 §7, D-77): learn the idle times of sandbox instances
cluster-wide, tell the worker that just finished an invocation what to do with its sandbox, and, after the pre-warm
window, re-warm on any worker that currently holds the tenant's key (no planned key releases). Active only when the
configured planner offers ``dispatch``/``end`` (``histogram_prewarm``); inert otherwise."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from voss.core.ids import FnId, TenantId, WorkerId
from voss.core.messages_ka import KeepWarm
from voss.policy.keepalive_hist import pick_holder
from voss.runtime.schedlib.inflight import Inflight
from voss.runtime.schedlib.planning import Planning
from voss.runtime.schedlib.viewcache import ViewCache


class KeepaliveMixin:
    planning: Planning
    inflight: dict[Any, Inflight]
    views: ViewCache
    epoch: int
    active: bool

    if TYPE_CHECKING:

        @property
        def now(self) -> float: ...
        def send(self, dst: Any, msg: Any) -> bool: ...
        def after(self, dt: float, fn: Any, *args: Any) -> Any: ...
        def eligible(self) -> set[WorkerId]: ...

    def _ka_dispatch(self, fn: str, worker: WorkerId) -> None:
        p = self.planning.planner
        if hasattr(p, "dispatch"):
            p.dispatch(fn, int(worker), self.now)

    def _ka_end(self, fn: str, tenant: str, worker: WorkerId) -> None:
        """Call after the finished invocation has left ``inflight``."""
        p = self.planning.planner
        if not hasattr(p, "end"):
            return
        busy = any(r.inv.fn == fn for r in self.inflight.values())
        w = p.end(fn, int(worker), self.now, busy)
        unload = w.prewarm_s > 0
        self.send(("agent", int(worker)), KeepWarm(FnId(fn), unload, False, w.keepalive_s, self.epoch))
        if unload:
            due = self.now + w.prewarm_s
            p.tracker.pending[fn] = due
            self.after(w.prewarm_s, self._ka_rewarm, fn, tenant, worker, due, w.keepalive_s)

    def _ka_rewarm(self, fn: str, tenant: str, orig: WorkerId, due: float, keepalive_s: float) -> None:
        p = self.planning.planner
        if not self.active or p.tracker.pending.get(fn) != due:
            return  # superseded: a request arrived before the pre-warm window elapsed
        del p.tracker.pending[fn]
        view = self.views.view(self.eligible(), self.now)
        t = TenantId(tenant)
        cands = [
            (int(view.workers[j]), float(view.mem_free_mb[j]))
            for j in range(len(view))
            if t in view.trust[j] and not view.draining[j]
        ]
        w = pick_holder(cands, int(orig))
        if w is None:
            return  # nobody holds the key: a single loop plans none, so the next request is cold
        p.tracker.loaded(fn, w, self.now)
        self.send(("agent", w), KeepWarm(FnId(fn), False, True, keepalive_s, self.epoch))
