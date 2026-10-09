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
from voss.runtime.schedlib.planning import Planning, PlanRound, sources_for
from voss.runtime.schedlib.viewcache import ViewCache
from voss.runtime.workerlib.host import HostLocal


class PlannerMixin:
    ctx: ActorContext
    hl: HostLocal
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

    def _plan_tick(self) -> None:
        if not self.active:
            return
        view = self.views.view(self.members, self.now)
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
        view = self.views.view(self.members, self.now)
        idx = view.index()
        for a in rnd.actions:
            if a.worker in idx:
                self._send_action(a, view, idx[a.worker])

    def _send_action(self, a: PlanAction, view: Any, j: int) -> None:
        dst, k = ("agent", int(a.worker)), self.ctx.cfg.voss.cache.max_sources
        if a.kind == "PREPARE":
            src = sources_for(view, a.fns[0], j, k, self.cost) if a.fns else ()
            self.send(dst, Prepare(TenantId(a.tenant), a.fns, self.epoch, src))
        elif a.kind == "PIN_SNAPSHOT":
            src = sources_for(view, a.fns[0], j, k, self.cost, ("L2", "L3"), str(a.tenant))
            self.send(dst, PinSnapshot(FnId(a.fns[0]), self.epoch, src))
        elif a.kind == "WARM":
            self.send(dst, Warm(FnId(a.fns[0]), a.n, self.epoch))
        else:
            self.send(dst, Release(TenantId(a.tenant), self.epoch))

    def dispatch_sources(self, fn: str, w: WorkerId) -> tuple[WorkerId, ...]:
        """P2P source hints for a dispatch whose target lacks the artifacts (doc 08 §4 ``DISPATCH``)."""
        if not self.ctx.cfg.voss.cache.p2p:
            return ()
        view = self.views.view(self.members, self.now)
        idx = view.index()
        j = idx.get(w)
        if j is None:
            return ()
        e = view.cache[j].get(FnId(fn))
        if e is not None:
            return ()
        return sources_for(view, fn, j, self.ctx.cfg.voss.cache.max_sources, self.cost)
