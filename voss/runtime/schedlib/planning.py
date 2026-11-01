"""Slow loop on the scheduler (doc 03 §4): build the planner's input from the stale view and forecasts, run the
registered planner, and turn the plan diff into rate-limited, value-ordered actions (doc 03 §4.4)."""

from __future__ import annotations

import math
from dataclasses import dataclass, field, replace
from typing import Any

import numpy as np

from voss.core.config import VossConfig
from voss.core.ids import FnId, TenantId, WorkerId
from voss.core.registry import create
from voss.core.types import ClusterView
from voss.policy.cache_value import source_score
from voss.policy.cost.inputs import CostContext
from voss.policy.keepalive_hist import HistParams
from voss.policy.plan import registry as _planners  # noqa: F401  (registers planners)
from voss.policy.plan.diff import PlanAction, diff, rate_limit
from voss.policy.plan.types import Plan, PlanInput, PlanParams
from voss.policy.predict.arrivals import poisson_quantile
from voss.runtime.schedlib.models import SchedModels
from voss.runtime.schedlib.prices import Prices


@dataclass
class PlanRound:
    plan: Plan
    actions: list[PlanAction] = field(default_factory=list)
    n_vars: int = 0


def _hot(rates: dict[str, float], k: int, min_rate: float) -> list[str]:
    return [key for key, r in sorted(rates.items(), key=lambda x: (-x[1], x[0])) if r >= min_rate][:k]


class Planning:
    def __init__(self, cfg: VossConfig, ctx: CostContext, models: SchedModels, start_utc_h: float) -> None:
        self.cfg, self.ctx, self.models, self.start_utc_h = cfg, ctx, models, start_utc_h
        pc = cfg.planner
        kw: dict[str, Any] = {}
        if pc.name == "milp":
            kw = {"time_limit": pc.T_solve, "node_limit": pc.node_limit}
        if pc.name == "histogram_prewarm":
            kw = {"params": HistParams(**cfg.keepalive_hist.model_dump())}
        self.planner: Any = create("planner", pc.name, **kw)
        self.params = PlanParams(**{"tie_break": cfg.reputation.tie_break, **pc.params})
        self.prev: Plan | None = None
        self.prices: Prices | None = None  # set by the scheduler: measured card prices (D-33)
        self._last_sig: tuple[object, ...] = ()

    def _workers(self, view: ClusterView, now: float, horizon: float) -> np.ndarray:
        """Planning pool (D-30): live workers, at most ``max_plan_workers`` (previous holders first, then by
        capacity × assurance), until P5 clustering bounds cluster size."""
        ok = (~view.draining) & (view.age < self.cfg.scheduler.stale_after_s) & (view.session_expiry > now)
        idx = np.flatnonzero(ok)
        k = self.cfg.planner.max_plan_workers
        if len(idx) <= k:
            return idx
        held = {int(w) for w in (self.prev.workers if self.prev is not None else ())}
        score = view.slots[idx] * view.assurance[idx] + np.array(
            [1e6 if int(view.workers[i]) in held else 0.0 for i in idx]
        )
        out: np.ndarray = np.sort(idx[np.argsort(-score, kind="stable")[:k]])
        return out

    def build(self, view: ClusterView, now: float) -> PlanInput:
        pc = self.cfg.planner
        horizon = pc.horizon_factor * pc.T_plan
        idx = self._workers(view, now, horizon)
        st = [view.static[i] if view.static else None for i in idx]
        demand = self.models.forecaster.forecast(now)
        tenants = _hot({k: v for k, v in demand.rate.items() if not k.startswith("fn:")}, pc.hot_top_k, pc.min_rate)
        tenants = [t for t in tenants if t in self.ctx.tenants]
        fn_rates = {k[3:]: v for k, v in demand.rate.items() if k.startswith("fn:")}
        fns = [
            f
            for f in _hot(fn_rates, pc.hot_fn_k, pc.min_rate)
            if f in self.ctx.fns and self.ctx.fns[f].tenant in tenants
        ]
        workers = np.asarray(view.workers, dtype=np.int64)[idx]
        k, lam, start, tz, drain = self.models._static(view)
        hour = np.mod(self.start_utc_h + now / 3600 + tz[idx], 24)
        survival = self.models.survival.p_alive_arr(k[idx], lam[idx], now - start[idx], horizon, hour, drain[idx], now)
        f_default = math.ceil(pc.f_from_alpha * len(idx))
        return PlanInput(
            now=now,
            horizon_s=horizon,
            workers=tuple(WorkerId(int(w)) for w in workers),
            cap=view.slots[idx].astype(float),
            mem_mb=np.array([s.mem_mb if s else 0.0 for s in st]),
            ssd_mb=np.array([s.ssd_mb if s else 0.0 for s in st]),
            survival=survival,
            p_omit=self.models.p_omit(workers),
            assurance=view.assurance[idx],
            domain=view.domain[idx],
            fresh_ok=view.session_expiry[idx] > now + min(horizon, 300.0),
            tenants=tuple(TenantId(t) for t in tenants),
            q=np.array([demand.q.get(t, 0.0) for t in tenants]),
            rate=np.array([demand.rate[t] for t in tenants]),
            sigma=np.array([self.ctx.tenants[t].sigma for t in tenants]),
            a_min=np.array([self.ctx.tenants[t].assurance_floor for t in tenants]),
            f=np.array([self.ctx.tenants[t].f if self.ctx.tenants[t].f is not None else f_default for t in tenants]),
            cold_penalty=np.full(len(tenants), pc.cold_penalty),
            fns=tuple(FnId(f) for f in fns),
            fn_tenant=np.array([tenants.index(self.ctx.fns[f].tenant) for f in fns], dtype=np.int64),
            fn_mem=np.array([self.ctx.fns[f].mem_mb for f in fns]),
            fn_size=np.array([self.ctx.fns[f].snapshot_mb for f in fns]),
            fn_benefit=np.array([self._benefit(f, fn_rates[f], horizon, demand.q) for f in fns]),
            fn_units=np.array([float(poisson_quantile(fn_rates[f] * self._svc(f), 0.95)) for f in fns]),
            y_prev=self._prev_y(tenants, workers),
            params=self.params,
            rep=np.array([self.models.rep.get(int(w), 0.0) for w in workers]) if self.models.rep else None,
            **self._loss_inputs(view, idx, now, horizon, tenants, fns, fn_rates, demand.rate),
        )

    def _loss_inputs(
        self,
        view: ClusterView,
        idx: np.ndarray,
        now: float,
        horizon: float,
        tenants: list[str],
        fns: list[str],
        fn_rates: dict[str, float],
        t_rates: dict[str, float],
    ) -> dict[str, np.ndarray]:
        """Estimates for the Erlang planners (planner-v2 §6), all from the scheduler's own view: slot hold time =
        warm dispatch + execution; boot and restore from the cost card the placer uses; Δ_t = measured price of a
        trust-cold start (``Prices.cold_trust``, D-33); residence ``E[min(L_j, T)]`` by quadrature of the survival
        model; measured exposure from the keys workers actually hold (``view.trust``)."""
        sm = next(iter(self.ctx.startup.values()))
        info = [self.ctx.fns[f] for f in fns]
        # TODO verify: 500 MB/s rootfs pull rate (same constant as ``_benefit``)
        boot = np.array([i.rootfs_mb / 500.0 + sm.boot_s + i.init_s for i in info])
        hold = np.array([self._svc(f) + sm.dispatch_s for f in fns])
        by_t = [[i for i, f in enumerate(fns) if self.ctx.fns[f].tenant == t] for t in tenants]
        t_svc = [
            self.models.forecaster.service.get(t, float(np.mean(hold[ix])) if ix else 0.1)
            for t, ix in zip(tenants, by_t, strict=True)
        ]
        delta = self.prices.cold_trust if self.prices is not None else self.cfg.router.cold_penalty_s
        trust = [view.trust[i] for i in idx]
        return {
            "fn_rate": np.array([fn_rates[f] for f in fns]),
            "fn_hold": hold,
            "fn_boot": boot,
            "fn_restore": np.full(len(fns), sm.restore_s),
            "delta_t": np.full(len(tenants), float(delta)),
            "tenant_load": np.array([t_rates[t] * float(v) for t, v in zip(tenants, t_svc, strict=True)]),
            "residence": self._residence(view, idx, now, horizon),
            "measured_exposure": np.array(
                [
                    sum(1 - view.assurance[i] for i, tr in zip(idx, trust, strict=True) if TenantId(t) in tr)
                    for t in tenants
                ]
            ),
        }

    def _residence(self, view: ClusterView, idx: np.ndarray, now: float, horizon: float) -> np.ndarray:
        """``E[min(L_j, T)] = ∫₀ᵀ S_j(τ) dτ`` with ``T = session_horizons·H``, by trapezoid over 9 points."""
        k, lam, start, tz, drain = self.models._static(view)
        t_max = self.params.session_horizons * horizon
        hour = np.mod(self.start_utc_h + now / 3600 + tz[idx], 24)
        grid = np.linspace(0.0, t_max, 9)
        s = np.array(
            [
                self.models.survival.p_alive_arr(k[idx], lam[idx], now - start[idx], g, hour, drain[idx], now)
                for g in grid
            ]
        )
        out: np.ndarray = np.trapezoid(s, grid, axis=0)
        return out

    def _svc(self, fn: str) -> float:
        return float(self.models.forecaster.service.get(f"fn:{fn}", self.ctx.fns[fn].work_ref_s))

    def _benefit(self, fn: str, rate: float, horizon: float, q: dict[str, float]) -> float:
        """Start-up seconds a warm unit saves over the horizon (cold boot from artifacts vs warm dispatch)."""
        f = self.ctx.fns[fn]
        sm = next(iter(self.ctx.startup.values()))
        saved = f.rootfs_mb / 500.0 + sm.boot_s + f.init_s
        units = max(1.0, float(poisson_quantile(rate * self._svc(fn), 0.95)))
        return rate * horizon * saved / units

    def _prev_y(self, tenants: list[str], workers: np.ndarray) -> np.ndarray:
        out = np.zeros((len(tenants), len(workers)), dtype=bool)
        if self.prev is None:
            return out
        ti = {str(t): i for i, t in enumerate(self.prev.tenants)}
        wi = {int(w): j for j, w in enumerate(self.prev.workers)}
        for a, t in enumerate(tenants):
            for b, w in enumerate(workers):
                if t in ti and int(w) in wi:
                    out[a, b] = self.prev.y[ti[t], wi[int(w)]]
        return out

    def confirmed(self, view: ClusterView, inp: PlanInput) -> Plan:
        """What workers have confirmed (doc 03 §4.4): trust-warm pins from heartbeats, snapshots the previous plan
        asked for that the cache inventory shows, warm units as previously requested. Actions are the diff from
        this state, so unconfirmed ones are re-sent (they are idempotent)."""
        idx = view.index()
        cols = [idx[w] for w in inp.workers]
        y = np.array(
            [[str(t) in view.pinned[c] if view.pinned else False for c in cols] for t in inp.tenants], dtype=bool
        ).reshape(len(inp.tenants), len(cols))
        s = np.zeros((len(inp.fns), len(cols)), dtype=bool)
        w = np.zeros((len(inp.fns), len(cols)), dtype=int)
        if self.prev is not None:
            pf = {str(f): i for i, f in enumerate(self.prev.fns)}
            pw = {int(x): j for j, x in enumerate(self.prev.workers)}
            for a, f in enumerate(inp.fns):
                for b, wid in enumerate(inp.workers):
                    i, j = pf.get(str(f)), pw.get(int(wid))
                    if i is None or j is None:
                        continue
                    e = view.cache[cols[b]].get(f)
                    s[a, b] = self.prev.s[i, j] and e is not None and e.level in ("L2", "L3")
                    w[a, b] = self.prev.w[i, j]
        return Plan(inp.tenants, inp.fns, inp.workers, y, s, w, np.zeros(y.shape), inp.now)

    def _signature(self, inp: PlanInput) -> tuple[object, ...]:
        tol = self.cfg.planner.replan_tolerance
        q = tuple(np.round(np.log1p(inp.q) / max(tol, 1e-6)).astype(int).tolist())
        units = tuple(np.round(np.log1p(inp.fn_units) / max(tol, 1e-6)).astype(int).tolist())
        return (inp.tenants, inp.fns, inp.workers, q, units)

    def run(self, view: ClusterView, now: float) -> PlanRound:
        """Re-solve only when the inputs changed materially (doc 03 §4: periodic + events); otherwise keep the
        previous plan and re-send whatever workers have not confirmed yet."""
        inp = self.build(view, now)
        sig = self._signature(inp)
        if self.prev is not None and sig == self._last_sig:
            plan = replace(self.prev, valid_until=now + inp.horizon_s, status="reused")
            if hasattr(self.planner, "on_reused"):  # stateful planners (erlang_dpp) advance every round
                self.planner.on_reused(inp)
        else:
            plan = self.planner.plan(inp)
            self._last_sig = sig
        fn_tenant = {f: self.ctx.fns[f].tenant for f in self.ctx.fns}
        benefit = {str(f): float(b) for f, b in zip(inp.fns, inp.fn_benefit, strict=True)}
        acts = diff(self.confirmed(view, inp), plan, fn_tenant, benefit)
        acts = rate_limit(acts + stale_releases(view, inp), self.cfg.planner.max_parallel_prepares)
        self.prev = plan
        t, f, j = inp.shape
        return PlanRound(plan, acts, 0 if plan.status == "reused" else (4 * t + 2 * f) * j)


def stale_releases(view: ClusterView, inp: PlanInput) -> list[PlanAction]:
    """RELEASE tenants still pinned on workers although they left the hot set (doc 03 §4.4)."""
    hot = {str(t) for t in inp.tenants}
    out = []
    for j, w in enumerate(view.workers):
        for t in sorted(view.pinned[j] if view.pinned else ()):
            if t not in hot:
                out.append(PlanAction("RELEASE", WorkerId(int(w)), TenantId(t)))
    return out


def sources_for(
    view: ClusterView,
    fn: str,
    target: int,
    k: int,
    ctx: CostContext,
    level: tuple[str, ...] = ("L1", "L2", "L3"),
    tenant: str | None = None,
) -> tuple[WorkerId, ...]:
    """Peers holding ``fn`` at ``level`` (same snapshot class and trust-warm for snapshots), fastest expected pull
    first (doc 02 §6 source choice). Artifacts the registry also serves only use peers that beat the registry: a
    residential uplink is often slower than the registry, so the nearest peer is not the fastest source."""
    if not view.static or k <= 0:
        return ()
    me = view.static[target]
    info = ctx.fns.get(fn)
    if me is None or info is None:
        return ()
    nbytes = (info.snapshot_mb if tenant is not None else info.bundle_mb + info.rootfs_mb) * 2**20
    down = max(me.down_bps, 1.0)
    reg = float(ctx.geo.rtt(np.array([ctx.registry[0]]), np.array([ctx.registry[1]]), me.lat, me.lon)[0])
    limit = float("inf") if tenant is not None else reg + nbytes * 8 / down
    found = []
    for j, c in enumerate(view.cache):
        e = c.get(FnId(fn))
        st = view.static[j]
        if j == target or e is None or e.level not in level or st is None:
            continue
        if tenant is not None and (st.snapshot_class != me.snapshot_class or tenant not in view.trust[j]):
            continue
        rtt = float(ctx.geo.rtt(np.array([st.lat]), np.array([st.lon]), me.lat, me.lon)[0])
        t = source_score(rtt, nbytes, min(st.up_bps, down), int(view.busy[j]), e.tier or "ssd")
        if t < limit:
            found.append((t, int(view.workers[j])))
    return tuple(WorkerId(w) for _, w in sorted(found)[:k])
