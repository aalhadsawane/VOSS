"""Cost matrix construction (doc 03 §5.1-5.2, doc 08 §5).

For invocations × candidate workers it produces the named components ``wait, trust, startup, net, exec, pFail``,
the completion distribution and ``pMiss``. Trust and artifact fetch overlap the slot wait:
``time_to_start = max(wait, trust, fetch) + rest`` (doc 08 §5).

Every eligible worker is a candidate (D-112); candidates are ordered by expected completion plus a failure
penalty, the best first.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field

import numpy as np

from voss.core.types import ClusterView, Invocation, SloClass
from voss.policy.cost.arrays import ArrayCache
from voss.policy.cost.completion import Completion, moment_match, p_miss
from voss.policy.cost.inputs import CostContext
from voss.policy.keys.budget import may_add_holder
from voss.policy.place.candidates import eligible

NAMES = ("wait", "trust", "startup", "net", "exec", "exec_var", "pFail", "tts")


@dataclass(frozen=True)
class Preds:
    """Predictions for one invocation over a subset of view workers (computed by the scheduler)."""

    exec_mean: np.ndarray
    exec_var: np.ndarray
    p_alive: np.ndarray  # session survival over the expected completion horizon
    p_omit: np.ndarray


PredsFn = Callable[[int, np.ndarray], Preds]  # (row, view indices) -> predictions on those workers


@dataclass(frozen=True)
class Waits:
    """Per-worker slot-wait vectors from ``voss.policy.cost.wait`` (D-77); ``sync`` is used by synchronous requests when
    they may overtake queued asynchronous ones."""

    asyn: np.ndarray
    sync: np.ndarray

    def pick(self, inv: Invocation) -> np.ndarray:
        return self.sync if inv.slo_class == SloClass.SYNC else self.asyn


@dataclass(frozen=True)
class CostMatrix:
    """Doc 05 §3: named components over ``[I, K]`` candidate grids; ``candidates`` index into the view."""

    components: dict[str, np.ndarray]
    candidates: np.ndarray
    feasible: np.ndarray
    completion: Completion
    p_miss: np.ndarray
    budget: np.ndarray
    extra: dict[str, np.ndarray] = field(default_factory=dict)


@dataclass(frozen=True)
class Static:
    """Per-invocation parts that do not need predictions, over all view workers."""

    ok: np.ndarray
    holder: np.ndarray
    trust: np.ndarray
    fetch: np.ndarray
    rest: np.ndarray
    net: np.ndarray


def static_parts(
    inv: Invocation, view: ClusterView, ctx: CostContext, cache: ArrayCache, now: float, router: str, margin_s: float
) -> Static:
    a = cache.get(view, ctx)
    f, t = ctx.fns[inv.fn], ctx.tenants[inv.tenant]
    ok = eligible(view, inv, now, margin_s)
    holder = cache.holder(view, inv.tenant)
    # a backup, or the budget is reached: only holders are candidates (D-85, plan V7.1)
    if inv.holders_only or not may_add_holder(int(holder.sum()), t.max_holders):
        ok &= holder
    trust = np.where(holder | (a.trust_fixed == 0), 0.0, cache.rtt(ctx, t.kbs_lat, t.kbs_lon) + a.trust_fixed)
    fetch, rest = cache.startup(view, ctx, inv.fn)
    rlat, rlon = ctx.routers.get(router, (float(a.lat.mean()), float(a.lon.mean())))
    net = cache.rtt(ctx, rlat, rlon) + inv.in_bytes * 8 / a.down + f.out_bytes * 8 / a.up
    return Static(ok, holder, trust, fetch, rest, net)


def completion_of(tts: np.ndarray, net: np.ndarray, exec_mean: np.ndarray, exec_var: np.ndarray) -> Completion:
    """Doc 03 §5.2: time to start plus network, with a 30% spread on the time to start, then execution."""
    return moment_match(tts + net, (0.3 * tts) ** 2, exec_mean, exec_var)


def _row(
    inv: Invocation,
    view: ClusterView,
    ctx: CostContext,
    cache: ArrayCache,
    st: Static,
    sub: np.ndarray,
    p: Preds,
    now: float,
    wait: np.ndarray,
) -> dict[str, np.ndarray]:
    a = cache.get(view, ctx)
    w = wait[sub]
    tts = np.maximum(np.maximum(w, st.trust[sub]), st.fetch[sub]) + st.rest[sub]
    cpu = a.cpu_factor[sub]
    e_mean = p.exec_mean * cpu
    comp = completion_of(tts, st.net[sub], e_mean, p.exec_var * cpu**2)
    p_fail = 1 - p.p_alive * (1 - p.p_omit)
    budget = np.full(len(sub), inv.deadline - (now - inv.t_arrive))
    return {
        "ok": st.ok[sub],
        "wait": w,
        "trust": st.trust[sub],
        "startup": st.fetch[sub] + st.rest[sub],
        "net": st.net[sub],
        "exec": e_mean,
        "exec_var": p.exec_var * cpu**2,
        "pFail": p_fail,
        "tts": tts,
        "shift": comp.shift,
        "m": comp.m,
        "s": comp.s,
        "pMiss": p_miss(comp, budget, p_fail),
        "budget": budget,
        "bound": np.where(st.ok[sub], comp.mean() + 10.0 * p_fail, np.inf),
    }


def candidates(st: Static, width: int) -> np.ndarray:
    """Every eligible worker (D-112), padded with ineligible ones to ``width`` columns (sorted view indices)."""
    ok = np.flatnonzero(st.ok)
    pad = np.flatnonzero(~st.ok)[: max(0, width - len(ok))]
    return np.sort(np.concatenate([ok, pad]))


def build_cost_matrix(
    invs: tuple[Invocation, ...],
    view: ClusterView,
    ctx: CostContext,
    preds: PredsFn | Preds,
    now: float,
    routers: tuple[str, ...],
    cache: ArrayCache | None = None,
    margin_s: float = 5.0,
    svc_s: float = 1.0,
    waits: Waits | None = None,
) -> CostMatrix:
    """Doc 03 §5.2 for every invocation (rows) over every eligible worker (D-112), best bound first; rows are padded
    with infeasible columns to the widest row."""
    cache = cache or ArrayCache()
    occ = view.busy + view.queued + view.inflight
    base = np.maximum(0, occ - view.slots + 1) * svc_s / np.maximum(view.slots, 1)
    sts = [static_parts(inv, view, ctx, cache, now, routers[i], margin_s) for i, inv in enumerate(invs)]
    width = min(len(view), max([1, *(int(st.ok.sum()) for st in sts)]))
    rows, tops = [], []
    for i, inv in enumerate(invs):
        wait = waits.pick(inv) if waits is not None else base  # D-77: per-worker estimate, by SLO class
        st = sts[i]
        sub = candidates(st, width)
        p = _slice(preds, i, sub) if isinstance(preds, Preds) else preds(i, sub)
        r = _row(inv, view, ctx, cache, st, sub, p, now, wait)
        top = np.argsort(r["bound"], kind="stable")
        rows.append({name: v[top] for name, v in r.items()})
        tops.append(sub[top])

    def grid(name: str) -> np.ndarray:
        return np.array([r[name] for r in rows])

    completion = Completion(grid("shift"), grid("m"), grid("s"))
    comps = {name: grid(name) for name in NAMES}
    return CostMatrix(comps, np.array(tops), grid("ok"), completion, grid("pMiss"), grid("budget"))


def _slice(p: Preds, i: int, sub: np.ndarray) -> Preds:
    def pick(x: np.ndarray) -> np.ndarray:
        out: np.ndarray = x[i, sub] if x.ndim == 2 else x[sub]
        return out

    return Preds(pick(p.exec_mean), pick(p.exec_var), pick(p.p_alive), pick(p.p_omit))
