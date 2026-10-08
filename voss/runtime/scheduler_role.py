"""Scheduler role (doc 03 §5, doc 07 §3, doc 08 §4): latent in every attested worker, active when appointed.

P2: placement via a registered placer over the stale view plus own in-flight bookkeeping; basic retry when a worker
is lost (silent or removed) or an attempt fails before execution. No durable state: everything is soft.
"""

from __future__ import annotations

from dataclasses import dataclass, replace

import numpy as np

from voss.core.ids import Addr, ClusterId, InvId, WorkerId
from voss.core.messages import (
    Accepted,
    Appoint,
    Assigned,
    Dispatch,
    DrainNotice,
    Enqueue,
    EpochInstall,
    Heartbeat,
    KeepaliveSummary,
    Membership,
    Message,
    OutcomeMsg,
    Revoke,
    Stale,
)
from voss.core.registry import create
from voss.core.types import ClusterView, Invocation
from voss.metrics.schema import Table
from voss.observe.statestore import StateStore
from voss.observe.views import build_view
from voss.policy.place import baselines as _placers  # noqa: F401  (registers placers)
from voss.policy.place.base import PlaceRequest
from voss.runtime.actor import Actor, ActorContext
from voss.runtime.workerlib.host import HostLocal

PRE_EXEC_FAILURES = frozenset({"key_denied", "expired", "aborted", "lost"})


@dataclass
class Inflight:
    inv: Invocation
    router: Addr
    t_enqueue: float
    worker: WorkerId | None = None
    t_dispatch: float = 0.0
    accepted: bool = False


class SchedulerRole(Actor):
    role = "sched"

    def __init__(self, host: HostLocal, ctx: ActorContext) -> None:
        super().__init__(host.worker, ctx)
        self.hl = host
        self.placer = create("placer", ctx.cfg.voss.placer.sync)
        self.reset()

    def reset(self) -> None:
        """Host loss: all soft state is gone (doc 07 §3)."""
        self.cancel_timers()
        self.active = False
        self.cluster = ClusterId(0)
        self.epoch = 0
        self.members: set[WorkerId] = set()
        self.store = StateStore()
        self.inflight: dict[InvId, Inflight] = {}
        self.done: set[InvId] = set()
        self.waiting: list[InvId] = []
        self.gen = self.ctx.rng.stream("sched.place", self.hl.worker, self.hl.session)
        self.token = 0
        self.members_version = 0
        self._view: ClusterView | None = None
        self._view_key = (-1, -1)
        self._view_t = -1e9
        self._view_idx: dict[WorkerId, int] = {}
        self.recent: dict[WorkerId, list[float]] = {}
        self._counts = np.zeros(0, dtype=np.int64)

    # --- membership and epochs ----------------------------------------------------------------------------
    def on_message(self, msg: Message) -> None:
        if isinstance(msg, Heartbeat):
            if self.active:
                self.store.update(msg.state, self.now)
                self._heard(msg.state.worker, msg.state.as_of)
        elif isinstance(msg, Enqueue):
            self._enqueue(msg)
        elif isinstance(msg, OutcomeMsg):
            self._outcome(msg)
        elif isinstance(msg, Accepted):
            rec = self.inflight.get(msg.inv)
            if rec is not None and rec.inv.attempt == msg.attempt:
                rec.accepted = True
        elif isinstance(msg, Appoint):
            self._appoint(msg)
        elif isinstance(msg, Membership):
            self._membership(msg)
        elif isinstance(msg, Revoke | Stale):
            self._deactivate(getattr(msg, "epoch", self.epoch))
        elif isinstance(msg, DrainNotice):
            pass  # hint only: the view's drain flag arrives with the next heartbeat (doc 07 §4)

    def _appoint(self, m: Appoint) -> None:
        if m.cert_id != self.hl.cert_id or m.epoch <= self.epoch or not self.hl.attested:
            return
        self.reset()
        self.active, self.cluster, self.epoch = True, m.cluster, m.epoch
        self.ctx.rec.log(Table.EVENTS, t=self.now, kind="scheduler_active", worker=self.hl.worker, value=m.epoch)
        self._membership(Membership(m.cluster, m.epoch, m.members))
        self._keepalive()
        self.after(self.ctx.cfg.voss.scheduler.heartbeat_s, self._check_silent)

    def _membership(self, m: Membership) -> None:
        if not self.active or m.epoch != self.epoch:
            return
        new = set(m.members)
        for w in sorted(new - self.members):
            self.send(("agent", w), EpochInstall(self.cluster, self.epoch, self.addr, self.hl.cert_id))
        for w in sorted(self.members - new):
            self._lost(w)
        self.members = new
        self.members_version += 1

    def _deactivate(self, epoch: int) -> None:
        if self.active and epoch >= self.epoch:
            self.ctx.rec.log(Table.EVENTS, t=self.now, kind="scheduler_inactive", worker=self.hl.worker, value=epoch)
            self.reset()

    def _keepalive(self) -> None:
        if not self.active:
            return
        load = sum(s.busy + s.queued for s in self.store.states.values())
        msg = KeepaliveSummary(self.cluster, self.epoch, self.hl.worker, len(self.store.states), float(load))
        self.send(self.ctx.directory.orchestrator, msg)
        self.after(self.ctx.cfg.voss.scheduler.keepalive_s, self._keepalive)

    def _check_silent(self) -> None:
        if not self.active:
            return
        for w in self.store.silent_since(self.now, self.ctx.cfg.voss.scheduler.stale_after_s):
            self._lost(w)
        self.after(self.ctx.cfg.voss.scheduler.heartbeat_s, self._check_silent)

    def _lost(self, w: WorkerId) -> None:
        self.store.remove(w)
        self.recent.pop(w, None)
        for rec in [r for _, r in sorted(self.inflight.items()) if r.worker == w]:
            self._retry(rec, "lost")

    # --- placement -------------------------------------------------------------------------------------------
    def _enqueue(self, m: Enqueue) -> None:
        if not self.active or m.inv.id in self.done:
            return
        rec = self.inflight.get(m.inv.id)
        if rec is not None:
            if rec.worker is not None:  # duplicate ENQUEUE (router watchdog): re-announce the assignment
                self.send(rec.router, Assigned(rec.inv.id, rec.inv.attempt, rec.worker, self.epoch, self.token))
            return
        self.inflight[m.inv.id] = Inflight(m.inv, m.router, m.t_sent)
        self._schedule(m.inv.id)

    def _schedule(self, inv: InvId) -> None:
        delay = self.ctx.clock.charge("place", work=len(self.members), host_speed=self.hl.speed)
        self.after(delay, self._place, inv)

    def _place(self, inv_id: InvId) -> None:
        rec = self.inflight.get(inv_id)
        if not self.active or rec is None or rec.worker is not None:
            return
        pl = self.placer.place(PlaceRequest((rec.inv,), self.current_view(), self.now, self.gen))
        w = pl.assign.get(inv_id)
        if w is None:
            self.after(self.ctx.cfg.voss.scheduler.no_candidate_retry_s, self._schedule, inv_id)
            return
        self._dispatch(rec, w)

    def current_view(self) -> ClusterView:
        """Cached stale view (rebuilt at most every ``view_refresh_s``) plus exact own in-flight counts."""
        key = (self.store.version, self.members_version)
        stale = key != self._view_key and self.now - self._view_t >= self.ctx.cfg.voss.scheduler.view_refresh_s
        if self._view is None or stale or key[1] != self._view_key[1]:
            self._view = build_view(self.store, self.members, self.now, {})
            self._view_key, self._view_t = key, self.now
            self._view_idx = self._view.index()
            self._counts = np.zeros(len(self._view), dtype=np.int64)
            for w, times in self.recent.items():
                if w in self._view_idx:
                    self._counts[self._view_idx[w]] = len(times)
        return replace(self._view, inflight=self._counts.copy())

    def _heard(self, w: WorkerId, as_of: float) -> None:
        """A heartbeat covers our dispatches up to ``as_of``: keep only later ones as in-flight bookkeeping."""
        times = self.recent.get(w)
        if times is None:
            return
        times[:] = [t for t in times if t >= as_of]
        if not times:
            del self.recent[w]
        i = self._view_idx.get(w)
        if i is not None:
            self._counts[i] = len(times)

    def _dispatch(self, rec: Inflight, w: WorkerId) -> None:
        self.token += 1
        rec.worker, rec.t_dispatch, rec.accepted = w, self.now, False
        self.recent.setdefault(w, []).append(self.now)
        i = self._view_idx.get(w)
        if i is not None:
            self._counts[i] += 1
        d = Dispatch(rec.inv, self.epoch, self.token, rec.router, self.hl.cert_id, rec.t_enqueue, self.now, self.addr)
        self.send(("agent", w), d)
        self.send(rec.router, Assigned(rec.inv.id, rec.inv.attempt, w, self.epoch, self.token))

    def _outcome(self, m: OutcomeMsg) -> None:
        o = m.outcome
        rec = self.inflight.get(o.inv)
        if rec is None or rec.inv.attempt != o.attempt:
            return
        if o.status == "ok":
            del self.inflight[o.inv]
            self.done.add(o.inv)
            return
        self._retry(rec, o.status)

    def _retry(self, rec: Inflight, status: str) -> None:
        cfg = self.ctx.cfg.voss.scheduler
        failed = rec.worker
        if rec.inv.attempt + 1 >= cfg.max_attempts or not (rec.inv.idempotent or status in PRE_EXEC_FAILURES):
            self.inflight.pop(rec.inv.id, None)
            self.done.add(rec.inv.id)
            return
        excluded = rec.inv.excluded | ({failed} if failed is not None else set())
        rec.inv = replace(rec.inv, attempt=rec.inv.attempt + 1, excluded=frozenset(excluded))
        rec.worker, rec.t_enqueue = None, self.now
        self.ctx.rec.log(
            Table.EVENTS,
            t=self.now,
            kind="retry",
            worker=failed if failed is not None else -1,
            value=float(rec.inv.attempt),
            inv=int(rec.inv.id),
            status=status,
        )
        self.after(cfg.retry_backoff_s, self._schedule, rec.inv.id)

    def inflight_array(self) -> np.ndarray:  # pragma: no cover - debugging aid
        return np.array(sorted(int(i) for i in self.inflight))
