"""Result watchdog, probes and worker suspicion (doc 07 §2, §4; docs/REVISION_PLAN.md V7.1-V7.2). Progress, not
heartbeats, is the evidence. The detector (``policy.detect``) sets the timer. On expiry ``voss`` starts a backup
attempt on a key holder in another failure domain and probes the first worker: the probe only feeds the drop estimate.
``fixed`` and ``consecutive`` abandon the attempt and retry. Repeated failures (or an omission change point, for
``voss``) eject the worker: no new work, no trust."""

from __future__ import annotations

from collections import deque
from typing import TYPE_CHECKING, Any

from voss.core.ids import Addr, ClusterId, InvId, TenantId, WorkerId
from voss.core.messages import Cancel, Release
from voss.core.messages_ft import Pong, Probe
from voss.metrics.schema import Table
from voss.policy.detect import Detector
from voss.runtime.actor import ActorContext
from voss.runtime.schedlib.inflight import Copy, Inflight
from voss.runtime.schedlib.models import SchedModels
from voss.runtime.schedlib.viewcache import ViewCache


class WatchdogMixin:
    ctx: ActorContext
    addr: Addr
    views: ViewCache
    models: SchedModels
    inflight: dict[InvId, Inflight]
    members: set[WorkerId]
    active: bool
    epoch: int
    cluster: ClusterId
    suspects: dict[WorkerId, float]
    streak: dict[WorkerId, int]
    det: Detector
    lat_obs: dict[str, deque[float]]  # per function: observed dispatch-to-outcome latencies (hedged timer)

    if TYPE_CHECKING:

        @property
        def now(self) -> float: ...
        def send(self, dst: Addr, msg: Any) -> bool: ...
        def after(self, dt: float, fn: Any, *args: Any) -> Any: ...
        def _copy_failed(self, rec: Inflight, c: Copy, status: str) -> None: ...
        def fenced(self) -> bool: ...
        def _request_backup(self, rec: Inflight, c: Copy) -> None: ...

    def eligible(self) -> set[WorkerId]:
        """Members that may get new work or trust: not suspected."""
        return self.members - self.suspects.keys() if self.suspects else self.members

    def _arm(self, rec: Inflight, c: Copy) -> None:
        """Result watchdog at the detector's timer: predicted completion quantile or the deadline (plan V7.2)."""
        obs = self.lat_obs.get(str(rec.inv.fn), ())
        dt = self.det.expiry_s(c.t_dispatch, c.q_done, rec.t_deadline, self.now, obs)
        self.after(dt, self._watch_fire, rec.inv.id, c.attempt, c.probes)

    def _arm_dispatch(self, rec: Inflight, c: Copy) -> None:
        """Scheduler-side dispatch watchdog: no ``ACCEPTED`` within 2 × ``T_dispatch`` → the dispatch was lost."""
        self.after(2 * self.ctx.cfg.voss.router.T_dispatch, self._dispatch_check, rec.inv.id, c.attempt)

    def _dispatch_check(self, inv: InvId, attempt: int) -> None:
        live = self._live(inv, attempt)
        if live is None or live[1].accepted:
            return
        self._copy_failed(live[0], live[1], "unaccepted")

    def _live(self, inv: InvId, attempt: int) -> tuple[Inflight, Copy] | None:
        """The copy, if this scheduler may still act on it (a fenced zombie draws no conclusions)."""
        rec = self.inflight.get(inv)
        if not self.active or rec is None or attempt not in rec.copies or self.fenced():
            return None
        return rec, rec.copies[attempt]

    def _watch_fire(self, inv: InvId, attempt: int, probes: int) -> None:
        live = self._live(inv, attempt)
        if live is None or live[1].probes != probes:
            return
        rec, c = live
        c.probes += 1
        if self.det.on_expiry == "retry":  # fixed, consecutive: the attempt is presumed lost
            self._evidence(c.worker, "timeout", inv)
            self.send(("agent", int(c.worker)), Cancel(inv, attempt))
            self._copy_failed(rec, c, "timeout")
            return
        self._request_backup(rec, c)
        if not self.det.probe:
            return
        self.send(("agent", int(c.worker)), Probe(inv, attempt, self.addr))
        self.after(self.ctx.cfg.voss.detection.probe_timeout_s, self._probe_timeout, inv, attempt, c.probes)

    def _probe_timeout(self, inv: InvId, attempt: int, probes: int) -> None:
        """No PONG: evidence for the drop estimate only. The attempt is not ended (a backup may be running)."""
        live = self._live(inv, attempt)
        if live is not None and live[1].probes == probes:
            self._evidence(live[1].worker, "no_pong", inv)

    def _pong(self, m: Pong) -> None:
        live = self._live(m.inv, m.attempt)
        if live is None:
            return
        rec, c = live
        c.probes += 1  # this probe is answered
        if m.phase == "running":
            self._arm(rec, c)
        elif m.phase == "done" and self.now - m.done_at < self.ctx.cfg.voss.detection.probe_timeout_s:
            self._arm(rec, c)  # the outcome may still be in flight
        else:  # done long ago without an outcome (omitted on the way), or unknown to the agent
            self._evidence(c.worker, "omitted" if m.phase == "done" else "unknown", m.inv)
            self._copy_failed(rec, c, "watchdog")

    def _evidence(self, w: WorkerId, reason: str, inv: InvId) -> None:
        """A progress failure: omission model update, streak, and suspicion past the threshold."""
        self.ctx.rec.log(Table.EVENTS, t=self.now, kind="watchdog", worker=w, value=0.0, inv=int(inv), reason=reason)
        cp = self.models.omission.update(int(w), True, self.now)
        self.streak[w] = self.streak.get(w, 0) + 1
        cp = cp if self.det.change_point else None
        if cp is not None or (self.det.streak and self.streak[w] >= self.det.streak):
            self._suspect(w, "change_point" if cp is not None else reason)

    def _suspect(self, w: WorkerId, reason: str) -> None:
        if w in self.suspects:
            return
        self.suspects[w] = self.now + self.det.eject_s
        self.ctx.rec.log(Table.EVENTS, t=self.now, kind="worker_suspect", worker=w, value=0.0, reason=reason)
        st = self.views.store.states.get(w)
        for t in sorted(st.trust if st is not None else ()):
            self.send(("agent", int(w)), Release(TenantId(t), self.epoch))  # trust-warm eligibility revoked
        self.views.members_changed()

    def _expire_suspicion(self) -> None:
        gone = [w for w, until in sorted(self.suspects.items()) if until <= self.now]
        for w in gone:
            del self.suspects[w]
            self.streak.pop(w, None)
        if gone:
            self.views.members_changed()
