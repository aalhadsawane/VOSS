"""``REPORT_EVENTS`` of the scheduler role (doc 08 §3.2) and reputation intake (doc 09): every ``report_s`` the
planner-pinned warm state held by responsive members (MB·s, the donor-caching credit basis), new omission change
points and new suspicions; tie-break scores from the orchestrator go to the planner (never to ``pFail``)."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from voss.core.ids import Addr, ClusterId, WorkerId
from voss.core.messages_acct import ReportEvents, ReputationScores
from voss.policy.cost.inputs import CostContext
from voss.runtime.actor import ActorContext
from voss.runtime.schedlib.planning import Planning
from voss.runtime.schedlib.viewcache import ViewCache


class EventsMixin:
    ctx: ActorContext
    cost: CostContext
    views: ViewCache
    planning: Planning
    active: bool
    epoch: int
    cluster: ClusterId
    suspects: dict[WorkerId, float]

    if TYPE_CHECKING:

        @property
        def now(self) -> float: ...
        def send(self, dst: Addr, msg: Any) -> bool: ...
        def after(self, dt: float, fn: Any, *args: Any) -> Any: ...
        def eligible(self) -> set[WorkerId]: ...
        def fenced(self) -> bool: ...

    def _init_standing(self) -> None:
        self.change_points: list[WorkerId] = []
        self.reported: set[WorkerId] = set()
        self.t_report = 0.0

    def _start_reports(self) -> None:
        self.t_report = self.now
        self.after(self.ctx.cfg.voss.accounting.report_s, self._report_tick)

    def _report_tick(self) -> None:
        if not self.active:
            return
        if not self.fenced():
            dt = self.now - self.t_report
            pinned = tuple((w, mb * dt) for w, mb in sorted(self.pinned_mb().items()) if mb > 0)
            new = sorted(set(self.suspects) - self.reported)
            self.reported = (self.reported & set(self.suspects)) | set(new)
            cps, self.change_points = tuple(sorted(set(self.change_points))), []
            if pinned or cps or new:
                self.send(
                    self.ctx.directory.orchestrator, ReportEvents(self.cluster, self.epoch, pinned, cps, tuple(new))
                )
        self.t_report = self.now
        self.after(self.ctx.cfg.voss.accounting.report_s, self._report_tick)

    def pinned_mb(self) -> dict[WorkerId, float]:
        """MB of warm VMs and snapshots the current plan pins on each responsive member (fresh view, not
        suspected): donated state is credited only while the worker shows progress (doc 09 §4)."""
        plan = self.planning.prev
        if plan is None:
            return {}
        view = self.views.view(self.eligible(), self.now)
        stale = self.ctx.cfg.voss.scheduler.stale_after_s
        fresh = {w for w, age in zip(view.workers, view.age, strict=True) if age < stale}
        mem = [self.cost.fns[f].mem_mb if f in self.cost.fns else 0.0 for f in plan.fns]
        snap = [self.cost.fns[f].snapshot_mb if f in self.cost.fns else 0.0 for f in plan.fns]
        out: dict[WorkerId, float] = {}
        for j, w in enumerate(plan.workers):
            if w in fresh:
                out[w] = float(sum(plan.w[f, j] * mem[f] + plan.s[f, j] * snap[f] for f in range(len(plan.fns))))
        return out

    def _scores(self, m: ReputationScores) -> None:
        if self.active and m.cluster == self.cluster and m.epoch == self.epoch:
            self.planning.models.rep = {int(w): s for w, s in m.scores}
