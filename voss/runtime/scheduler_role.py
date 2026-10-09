"""Scheduler role (doc 03 §5, doc 07 §3, doc 08 §4): latent in every attested worker, active when appointed.

Thin actor: decodes messages, calls the fast-loop decision pipeline (``schedlib.decide``) and applies its result after
the decision latency (doc 01 §7); keeps only soft state (in-flight copies, learned models).
"""

from __future__ import annotations

import math
import time
from dataclasses import replace

from voss.core.ids import ClusterId, InvId, TenantId, WorkerId
from voss.core.messages import (
    Accepted,
    Appoint,
    Assigned,
    Cancel,
    Dispatch,
    DrainNotice,
    Enqueue,
    EpochInstall,
    Heartbeat,
    HomeDemand,
    KeepaliveSummary,
    Membership,
    Message,
    OutcomeMsg,
    Reject,
    Revoke,
    Stale,
    Withdraw,
)
from voss.core.types import ClusterView, Outcome, SloClass
from voss.metrics.schema import Table
from voss.observe.summaries import summarize
from voss.policy.cost.inputs import CostContext
from voss.policy.predict.base import ExecObs, FnPrior
from voss.policy.retry import BasicRetry
from voss.runtime.actor import Actor, ActorContext
from voss.runtime.schedlib.decide import Decider, Decision
from voss.runtime.schedlib.inflight import Copy, Inflight
from voss.runtime.schedlib.models import SchedModels
from voss.runtime.schedlib.planner_mixin import PlannerMixin
from voss.runtime.schedlib.planning import Planning
from voss.runtime.schedlib.viewcache import ViewCache
from voss.runtime.workerlib.host import HostLocal

OVERHEAD_PRIOR_S = 0.2  # card prior: decision + dispatch hop  # TODO verify


class SchedulerRole(PlannerMixin, Actor):
    role = "sched"

    def __init__(self, host: HostLocal, ctx: ActorContext, cost: CostContext, priors: dict[str, FnPrior]) -> None:
        super().__init__(host.worker, ctx)
        self.hl, self.cost, self.priors = host, cost, priors
        self.reset()

    def reset(self) -> None:
        """Host loss: all soft state is gone (doc 07 §3)."""
        self.cancel_timers()
        cfg = self.ctx.cfg.voss
        self.active, self.cluster, self.epoch = False, ClusterId(0), 0
        self.members: set[WorkerId] = set()
        self.views = ViewCache(cfg.scheduler.view_refresh_s)
        self.inflight: dict[InvId, Inflight] = {}
        self.done: set[InvId] = set()
        self.window: list[InvId] = []
        self.fillers: set[InvId] = set()
        self.busy_until = 0.0
        self.models = SchedModels(cfg, self.priors)
        self.decider = Decider(cfg, self.cost, self.models, self.ctx.cfg.scenario.start_utc_h)
        self.planning = Planning(cfg, self.cost, self.models, self.ctx.cfg.scenario.start_utc_h)
        self.retry = BasicRetry(cfg.scheduler.max_attempts, cfg.scheduler.retry_backoff_s)
        self.gen = self.ctx.rng.stream("sched.place", self.hl.worker, self.hl.session)
        self.token = 0
        self.overhead = OVERHEAD_PRIOR_S  # decision + dispatch + queue wait; trust and cold starts are priced apart

    # --- membership and epochs ----------------------------------------------------------------------------
    def on_message(self, msg: Message) -> None:
        if isinstance(msg, Heartbeat):
            if self.active:
                self.views.heard(msg.state, self.now)
        elif isinstance(msg, Enqueue):
            self._enqueue(msg)
        elif isinstance(msg, Withdraw):
            self._withdraw(msg.inv)
        elif isinstance(msg, HomeDemand):
            if self.active and msg.epoch == self.epoch and msg.cluster == self.cluster:
                self.models.forecaster.set_home(dict(msg.rates))
        elif isinstance(msg, OutcomeMsg):
            self._outcome(msg.outcome)
        elif isinstance(msg, Accepted):
            rec = self.inflight.get(msg.inv)
            if rec is not None and msg.attempt in rec.copies:
                rec.copies[msg.attempt].accepted = True
        elif isinstance(msg, Appoint):
            self._appoint(msg)
        elif isinstance(msg, Membership):
            self._membership(msg)
        elif isinstance(msg, Revoke) or (isinstance(msg, Stale) and msg.cluster == int(self.cluster)):
            self._deactivate(msg.epoch)
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
        cfg = self.ctx.cfg.voss
        self.after(cfg.scheduler.heartbeat_s, self._check_silent)
        self.after(cfg.models.refit_s, self._refit)
        self.after(cfg.planner.T_plan, self._plan_tick)

    def _membership(self, m: Membership) -> None:
        if not self.active or m.epoch != self.epoch:
            return
        new = set(m.members)
        for w in sorted(new - self.members):
            self.send(("agent", w), EpochInstall(self.cluster, self.epoch, self.addr, self.hl.cert_id))
        moved = set(m.moved)
        for w in sorted(self.members - new):
            if w in moved:
                self.views.lost(w)  # alive elsewhere: its in-flight copies still report to us
            else:
                self._lost(w)
        self.members = new
        self.views.members_changed()

    def _deactivate(self, epoch: int) -> None:
        if self.active and epoch >= self.epoch:
            self.ctx.rec.log(Table.EVENTS, t=self.now, kind="scheduler_inactive", worker=self.hl.worker, value=epoch)
            self.reset()

    def _keepalive(self) -> None:
        """``KEEPALIVE+SUMMARY`` (doc 08 §4): load, free capacity, trust-warm capacity per tenant, warm functions."""
        if not self.active:
            return
        view = self.views.view(self.members, self.now)
        summ = summarize(self.cluster, view)
        decay = math.exp(-self.ctx.cfg.voss.scheduler.keepalive_s / 60.0)  # stale measurements fade to the prior
        self.overhead = OVERHEAD_PRIOR_S + (self.overhead - OVERHEAD_PRIOR_S) * decay
        warm: dict[str, int] = {}
        for c in view.cache:
            for fn, e in c.items():
                if e.level == "L3":
                    warm[str(fn)] = warm.get(str(fn), 0) + 1
        prev = self.planning.prev
        msg = KeepaliveSummary(
            self.cluster,
            self.epoch,
            self.hl.worker,
            summ.attested,
            summ.load,
            summ.free_slots,
            self.overhead,
            tuple(sorted((str(t), v) for t, v in summ.trust_warm_capacity.items())),
            tuple(sorted(warm.items())),
            summ.diversity,
            bool(prev is not None and prev.cost_terms.get("shortfall", 0.0) > 1e-6),
            self._forecast_load(view),
        )
        self.send(self.ctx.directory.orchestrator, msg)
        self.after(self.ctx.cfg.voss.scheduler.keepalive_s, self._keepalive)

    def _forecast_load(self, view: ClusterView) -> float:
        """Forecast concurrent demand (sum of per-function capacity quantiles) over attested slots."""
        d = self.models.forecaster.forecast(self.now)
        need = sum(q for k, q in d.q.items() if k.startswith("fn:"))
        return float(need / max(1, int(view.slots.sum())))

    def _check_silent(self) -> None:
        if not self.active:
            return
        for w in self.views.store.silent_since(self.now, self.ctx.cfg.voss.scheduler.stale_after_s):
            self._lost(w)
        self.after(self.ctx.cfg.voss.scheduler.heartbeat_s, self._check_silent)

    def _refit(self) -> None:
        if not self.active:
            return
        live: dict[str, list[float]] = {}
        for s in self.views.store.states.values():
            if s.static is not None:
                live.setdefault(s.static.tier, []).append(self.now - s.static.session_start)
        self.models.refit(live)
        self.after(self.ctx.cfg.voss.models.refit_s, self._refit)

    def _lost(self, w: WorkerId) -> None:
        st = self.views.store.states.get(w)
        if st is not None and st.static is not None:
            hour = (self.ctx.cfg.scenario.start_utc_h + self.now / 3600 + st.static.tz) % 24
            self.models.survival.observe_end(st.static.tier, self.now - st.static.session_start, hour)
        self.views.lost(w)
        for _, rec in sorted(self.inflight.items()):
            for c in rec.live_on(w):
                self._copy_failed(rec, c, "lost")

    # --- decisions --------------------------------------------------------------------------------------------
    def _enqueue(self, m: Enqueue) -> None:
        if not self.active or m.inv.id in self.done:
            return
        rec = self.inflight.get(m.inv.id)
        if rec is not None:
            for c in rec.copies.values():  # duplicate ENQUEUE (router watchdog): re-announce assignments
                self.send(
                    rec.router, Assigned(rec.inv.id, c.attempt, c.worker, self.epoch, self.token, int(self.cluster))
                )
            return
        self.inflight[m.inv.id] = Inflight(m.inv, m.router, m.t_sent, t_in=self.now)
        if m.inv.slo_class == SloClass.FILLER:
            self.fillers.add(m.inv.id)
        self.models.forecaster.observe(m.inv.tenant, self.now)
        self.models.forecaster.observe(f"fn:{m.inv.fn}", self.now)
        if m.inv.slo_class == SloClass.SYNC:
            self._decide([m.inv.id], windowed=False)
            return
        self.inflight[m.inv.id].t_window = self.now
        self.window.append(m.inv.id)
        if len(self.window) == 1:
            self.after(self.ctx.cfg.voss.placer.window_s, self._flush_window)

    def _withdraw(self, inv_id: InvId) -> None:
        """Spilled to another cluster (doc 03 §3): forget it and cancel any copies already dispatched."""
        rec = self.inflight.pop(inv_id, None)
        if rec is None:
            return
        self.done.add(inv_id)
        self.fillers.discard(inv_id)
        for c in rec.copies.values():
            self.send(("agent", c.worker), Cancel(inv_id, c.attempt))

    def _flush_window(self) -> None:
        ids, self.window = self.window, []
        self._decide(ids, windowed=True)

    def _decide(self, ids: list[InvId], windowed: bool) -> None:
        recs = [self.inflight[i] for i in ids if i in self.inflight and not self.inflight[i].deciding]
        if not self.active or not recs:
            return
        for r in recs:
            r.deciding = True
            if r.t_window is not None:
                r.batch_wait, r.t_window = self.now - r.t_window, None
        view = self.views.view(self.members, self.now)
        routers = tuple(str(r.router[1]) for r in recs)
        t0 = time.perf_counter()
        d = self.decider.decide(tuple(r.inv for r in recs), view, self.now, routers, self.gen, windowed, self.views.idx)
        wall = time.perf_counter() - t0
        delay = self.ctx.clock.charge("place", work=d.work, host_speed=self.hl.speed, wall_s=wall)
        start = max(self.now, self.busy_until)
        self.busy_until = start + delay
        self.after(self.busy_until - self.now, self._apply, d, [r.inv.id for r in recs], windowed)

    def _apply(self, d: Decision, ids: list[InvId], windowed: bool) -> None:
        cfg = self.ctx.cfg.voss
        for inv_id in ids:
            rec = self.inflight.get(inv_id)
            if rec is None:
                continue
            rec.deciding = False
            if inv_id in d.rejected:
                del self.inflight[inv_id]
                self.done.add(inv_id)
                self.send(rec.router, Reject(inv_id, d.rejected[inv_id]))
            elif inv_id in d.assign:
                self._dispatch(rec, d.assign[inv_id], False, d.predicted.get((inv_id, d.assign[inv_id])))
                if inv_id in d.hedges:
                    self._dispatch(rec, d.hedges[inv_id], True, d.predicted.get((inv_id, d.hedges[inv_id])))
            else:
                wait = cfg.admission.defer_s if windowed else cfg.scheduler.no_candidate_retry_s
                self.after(wait, self._decide, [inv_id], windowed)

    def _dispatch(self, rec: Inflight, w: WorkerId, hedge: bool, pred: tuple[float, float] | None) -> None:
        self.token += 1
        a = rec.next_attempt
        rec.next_attempt += 1
        mu, var = pred or (0.0, 0.0)
        st = self.views.store.states.get(w)
        load = (st.busy + st.queued) / max(1, st.slots) if st else 0.0
        rec.copies[a] = Copy(a, w, self.now, hedge, mu=mu, sigma=var, load=load)
        self.views.dispatched(w, self.now)
        inv = replace(rec.inv, attempt=a)
        src = self.dispatch_sources(inv.fn, w)
        d = Dispatch(
            inv,
            self.epoch,
            self.token,
            rec.router,
            self.hl.cert_id,
            rec.t_enqueue,
            self.now,
            self.addr,
            rec.batch_wait,
            src,
            int(self.cluster),
        )
        self.send(("agent", w), d)
        self.send(rec.router, Assigned(inv.id, a, w, self.epoch, self.token, int(self.cluster)))
        if inv.slo_class == SloClass.SYNC:
            self._preempt_filler(w)

    def _preempt_filler(self, w: WorkerId) -> None:
        """Doc 03 §5.4: filler is preempted by sync work on a full worker."""
        st = self.views.store.states.get(w)
        if st is None or st.busy + st.queued + len(self.views.recent.get(w, ())) <= st.slots:
            return
        for inv_id in sorted(self.fillers):
            rec = self.inflight.get(inv_id)
            if rec is None:
                self.fillers.discard(inv_id)
                continue
            for c in rec.live_on(w):
                self.send(("agent", w), Cancel(rec.inv.id, c.attempt))
                self._copy_failed(rec, c, "preempted")
                return

    # --- outcomes ---------------------------------------------------------------------------------------------
    def _outcome(self, o: Outcome) -> None:
        rec = self.inflight.get(o.inv)
        if rec is None or o.attempt not in rec.copies:
            return
        c = rec.copies[o.attempt]
        if o.status != "ok":
            self._copy_failed(rec, c, o.status)
            return
        del self.inflight[o.inv]
        self.done.add(o.inv)
        t = o.timings
        self.overhead += 0.05 * ((c.t_dispatch - rec.t_in) + t.wait - self.overhead)  # in-cluster only
        for other in sorted(rec.copies.values(), key=lambda x: x.attempt):
            if other.attempt != o.attempt:
                self.send(("agent", other.worker), Cancel(o.inv, other.attempt))
        self._learn(rec, c, o)

    def _learn(self, rec: Inflight, c: Copy, o: Outcome) -> None:
        st = self.views.store.states.get(c.worker)
        speed = st.speed if st else 1.0
        obs = ExecObs(rec.inv.fn, int(c.worker), rec.inv.in_bytes, speed, c.load, o.timings.exec, self.now)
        self.models.observe(obs)
        self.models.forecaster.observe_service(rec.inv.tenant, o.timings.exec)
        self.models.forecaster.observe_service(f"fn:{rec.inv.fn}", o.timings.exec)
        cp = self.models.omission.update(int(c.worker), False, self.now)
        if cp is not None:
            self.ctx.rec.log(Table.EVENTS, t=self.now, kind="change_point", worker=c.worker, value=cp.statistic)
        self.ctx.rec.log(
            Table.PREDICTIONS,
            t=self.now,
            fn=rec.inv.fn,
            worker=int(c.worker),
            hedge=c.hedge,
            pred_mean=c.mu,
            pred_var=c.sigma,
            actual=o.timings.exec,
            tenant=TenantId(rec.inv.tenant),
        )

    def _copy_failed(self, rec: Inflight, c: Copy, status: str) -> None:
        rec.copies.pop(c.attempt, None)
        if rec.copies or rec.inv.id not in self.inflight:
            return  # another copy is still running
        dec = self.retry.on_failure(replace(rec.inv, attempt=rec.failures), status, self.now)
        if dec.counts_attempt:
            rec.failures += 1
        if not dec.retry:
            del self.inflight[rec.inv.id]
            self.done.add(rec.inv.id)
            return
        rec.inv = replace(rec.inv, excluded=rec.inv.excluded | {c.worker})
        rec.t_enqueue, rec.batch_wait = self.now, 0.0
        self.ctx.rec.log(
            Table.EVENTS,
            t=self.now,
            kind="retry",
            worker=c.worker,
            value=float(rec.failures),
            inv=int(rec.inv.id),
            status=status,
        )
        self.after(dec.delay_s, self._decide, [rec.inv.id], rec.inv.slo_class != SloClass.SYNC)
