"""Soft-state succession of the scheduler role (doc 07 §3): epoch-fenced checkpoints, leases with self-fencing, roll
call adoption of running attempts, warm standby views, and planned handover."""

from __future__ import annotations

import copy
from typing import TYPE_CHECKING, Any

from voss.core.ids import Addr, ClusterId, InvId, WorkerId
from voss.core.messages import Appoint
from voss.core.messages_ft import Checkpoint, Lease, PutCheckpoint, RollCallReport, Standby
from voss.metrics.schema import Table
from voss.policy.predict.base import ExecObs
from voss.runtime.actor import ActorContext
from voss.runtime.schedlib.inflight import Copy, Inflight
from voss.runtime.schedlib.models import SchedModels
from voss.runtime.schedlib.planning import Planning
from voss.runtime.schedlib.viewcache import ViewCache
from voss.runtime.workerlib.host import HostLocal


class SuccessionMixin:
    ctx: ActorContext
    hl: HostLocal
    views: ViewCache
    models: SchedModels
    planning: Planning
    inflight: dict[InvId, Inflight]
    done: set[InvId]
    members: set[WorkerId]
    active: bool
    epoch: int
    cluster: ClusterId
    lease_until: float
    standby: Addr | None
    standby_for: tuple[ClusterId, int] | None
    fenced_logged: bool

    if TYPE_CHECKING:

        @property
        def now(self) -> float: ...
        def send(self, dst: Addr, msg: Any) -> bool: ...
        def after(self, dt: float, fn: Any, *args: Any) -> Any: ...
        def _arm(self, rec: Inflight, c: Copy) -> None: ...

    # --- appointment -------------------------------------------------------------------------------------------
    def _restore(self, m: Appoint) -> None:
        """Warm start from the predecessor's checkpoint (plan + learned state); never from local memory."""
        self.lease_until = self.now + self.ctx.cfg.voss.succession.lease_s
        self.standby = m.standby
        ck = m.checkpoint
        if isinstance(ck, Checkpoint) and ck.cluster == int(m.cluster):
            if isinstance(ck.models, SchedModels):
                self.models = copy.deepcopy(ck.models)
            self.planning.prev = ck.plan  # type: ignore[assignment]
            self.ctx.rec.log(Table.EVENTS, t=self.now, kind="checkpoint_restore", worker=self.hl.worker, value=ck.t)
        self.after(self.ctx.cfg.voss.succession.T_ckpt, self._checkpoint_tick)

    def _checkpoint_tick(self) -> None:
        if not self.active:
            return
        self._put_checkpoint()
        self.after(self.ctx.cfg.voss.succession.T_ckpt, self._checkpoint_tick)

    def _put_checkpoint(self) -> None:
        ck = Checkpoint(int(self.cluster), self.epoch, self.now, self.planning.prev, copy.deepcopy(self.models))
        self.send(self.ctx.directory.orchestrator, PutCheckpoint(ck))

    def _handover(self) -> None:
        if self.active:
            self._put_checkpoint()

    # --- lease / self-fence ------------------------------------------------------------------------------------
    def _lease(self, m: Lease) -> None:
        if self.active and m.epoch == self.epoch and m.cluster == self.cluster:
            self.lease_until = max(self.lease_until, m.until)
            self.fenced_logged = False

    def fenced(self) -> bool:
        """Zombie protection (doc 07 §3): no dispatch without a fresh lease from the orchestrator."""
        if self.now <= self.lease_until:
            return False
        if not self.fenced_logged:
            self.fenced_logged = True
            self.ctx.rec.log(Table.EVENTS, t=self.now, kind="self_fence", worker=self.hl.worker, value=self.epoch)
        return True

    # --- roll call ---------------------------------------------------------------------------------------------
    def _roll_call(self, m: RollCallReport) -> None:
        """Adopt the reporting worker's running attempts and replay its retained outcomes into the models."""
        if not self.active or m.epoch != self.epoch or m.cluster != self.cluster:
            return
        self.views.heard(m.state, self.now)
        for ra in m.running:
            inv = ra.inv
            if inv.id in self.inflight or inv.id in self.done:
                continue
            rec = Inflight(inv, ra.router, ra.t_dispatch, t_in=self.now, next_attempt=inv.attempt + 1)
            c = Copy(inv.attempt, m.worker, ra.t_dispatch, accepted=True)
            rec.copies[inv.attempt] = c
            self.inflight[inv.id] = rec
            self._arm(rec, c)
        for r in m.outcomes:
            if r.outcome.status == "ok":
                obs = ExecObs(r.fn, int(m.worker), r.in_bytes, m.state.speed, 0.0, r.outcome.timings.exec, r.t)
                self.models.observe(obs)

    # --- standby -----------------------------------------------------------------------------------------------
    def _standby(self, m: Standby) -> None:
        """Keep a warm view from heartbeats so promotion needs no roll-call wait for the view (doc 07 §3)."""
        if self.active:
            return
        self.standby_for = (m.cluster, m.epoch)
        self.members = set(m.members)
        self.views.members_changed()
