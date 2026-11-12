"""Planner timers of the scheduler role (doc 03 §4, D-31): every ``T_plan`` the planner runs on the view at that
time (on its own core, so it does not delay placements), and its actions are sent after the charged latency."""

from __future__ import annotations

import time
from typing import TYPE_CHECKING, Any

from voss.core.ids import Addr, ClusterId, FnId, TenantId, WorkerId
from voss.core.messages import PinSnapshot, Prepare, Release, Warm
from voss.metrics.schema import Table
from voss.policy.cost.inputs import CostContext
from voss.policy.plan.diff import PlanAction
from voss.runtime.actor import ActorContext
from voss.runtime.schedlib.planning import Planning, PlanRound
from voss.runtime.schedlib.provider_host import ProviderHost
from voss.runtime.schedlib.viewcache import ViewCache


class PlannerMixin:
    ctx: ActorContext
    hl: ProviderHost
    cost: CostContext
    views: ViewCache
    planning: Planning
    members: set[WorkerId]
    active: bool
    epoch: int
    cluster: ClusterId

    if TYPE_CHECKING:

        @property
        def now(self) -> float: ...
        def send(self, dst: Addr, msg: Any) -> bool: ...
        def after(self, dt: float, fn: Any, *args: Any) -> Any: ...
        def eligible(self) -> set[WorkerId]: ...

    def _plan_tick(self) -> None:
        if not self.active:
            return
        view = self.views.view(self.eligible(), self.now)
        t0 = time.perf_counter()
        rnd = self.planning.run(view, self.now)
        wall = time.perf_counter() - t0
        delay = self.ctx.clock.charge("plan", work=rnd.n_vars, host_speed=self.hl.speed, wall_s=wall)
        self.after(delay, self._apply_plan, rnd, wall, delay)
        self.after(self.ctx.cfg.voss.planner.T_plan, self._plan_tick)

    def _apply_plan(self, rnd: PlanRound, wall: float, charged: float) -> None:
        if not self.active:
            return
        p = rnd.plan
        slack = p.cost_terms.get("shortfall", 0.0)
        self.ctx.rec.log(
            Table.PLANS,
            t=self.now,
            cluster=int(self.cluster),
            epoch=self.epoch,
            planner=p.planner,
            status=p.status,
            solve_wall_s=wall,
            charged_s=charged,
            objective=p.objective,
            tenants=len(p.tenants),
            workers=len(p.workers),
            trust_pairs=int(p.y.sum()),
            warm_units=int(p.w.sum()),
            snapshots=int(p.s.sum()),
            actions=len(rnd.actions),
            shortfall=slack,
            **{f"term_{k}": v for k, v in sorted(p.cost_terms.items())},
        )
        view = self.views.view(self.eligible(), self.now)
        idx = view.index()
        for a in rnd.actions:
            if a.worker in idx:
                self._send_action(a, view, idx[a.worker])

    def _send_action(self, a: PlanAction, view: Any, j: int) -> None:
        dst = ("agent", int(a.worker))
        if a.kind == "PREPARE":
            self.send(dst, Prepare(TenantId(a.tenant), a.fns, self.epoch))
        elif a.kind == "PIN_SNAPSHOT":
            self.send(dst, PinSnapshot(FnId(a.fns[0]), self.epoch))
        elif a.kind == "WARM":
            self.send(dst, Warm(FnId(a.fns[0]), a.n, self.epoch))
        else:
            self.send(dst, Release(TenantId(a.tenant), self.epoch))
