"""Cost matrix construction (doc 03 §5.1-5.2, doc 08 §5).

For invocations × candidate workers it produces the named components ``wait, trust, startup, net, exec, pFail,
exposure``, the completion distribution and ``pMiss``. Trust and artifact fetch overlap the slot wait:
``time_to_start = max(wait, trust, fetch) + rest`` (doc 08 §5).

Candidates are pruned in two stages (doc 03 §5.1 "top-K by a cheap lower bound"): a bound from cached per-view
arrays (prior execution time, no failure model) keeps ``prune × K`` workers; predictions and the full model run on
those only, and the best ``K`` by expected completion plus a failure penalty are returned.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field

import numpy as np

from voss.core.types import ClusterView, Invocation, SloClass
from voss.policy.cost.arrays import ArrayCache
from voss.policy.cost.completion import Completion, moment_match, p_miss
from voss.policy.cost.inputs import CostContext
from voss.policy.place.candidates import eligible

NAMES = ("wait", "trust", "startup", "net", "exec", "exec_var", "pFail", "exposure", "tts")


@dataclass(frozen=True)
class Preds:
    """Predictions for one invocation over a subset of view workers (computed by the scheduler)."""

    exec_mean: np.ndarray
    exec_var: np.ndarray
    p_alive: np.ndarray  # session survival over the expected completion horizon
    p_omit: np.ndarray


PredsFn = Callable[[int, np.ndarray], Preds]  # (row, view indices) -> predictions on those workers


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
    ok = eligible(view, inv, now, margin_s) & (view.assurance >= t.assurance_floor)
    holder = cache.holder(view, inv.tenant)
    trust = np.where(holder | (a.trust_fixed == 0), 0.0, cache.rtt(ctx, t.kbs_lat, t.kbs_lon) + a.trust_fixed)
    fetch, rest = cache.startup(view, ctx, inv.fn)
    if not ctx.lifecycle_aware:  # ablation: one startup estimate for every candidate (warmth is invisible)
        fetch, rest = np.full_like(fetch, fetch.mean()), np.full_like(rest, rest.mean())
    rlat, rlon = ctx.routers.get(router, (float(a.lat.mean()), float(a.lon.mean())))
    net = cache.rtt(ctx, rlat, rlon) + inv.in_bytes * 8 / a.down + f.out_bytes * 8 / a.up
    return Static(ok, holder, trust, fetch, rest, net)


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
    t = ctx.tenants[inv.tenant]
    w = wait[sub]
    tts = np.maximum(np.maximum(w, st.trust[sub]), st.fetch[sub]) + st.rest[sub]
    cpu = a.cpu_factor[sub]
    e_mean = p.exec_mean * cpu
    comp = moment_match(tts + st.net[sub], (0.3 * tts) ** 2, e_mean, p.exec_var * cpu**2)
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
        "exposure": np.where(st.holder[sub], 0.0, t.sigma * (1 - view.assurance[sub])),
        "shift": comp.shift,
        "m": comp.m,
        "s": comp.s,
        "pMiss": p_miss(comp, budget, p_fail),
        "budget": budget,
        "bound": np.where(st.ok[sub], comp.mean() + 10.0 * p_fail, np.inf),
    }


def prune(inv: Invocation, view: ClusterView, ctx: CostContext, st: Static, wait: np.ndarray, m: int) -> np.ndarray:
    """Stage 1: the ``m`` best eligible workers by a prediction-free bound (sorted view indices)."""
    prior = ctx.fns[inv.fn].work_ref_s / np.maximum(view.speed, 1e-9)
    bound = np.where(st.ok, np.maximum(np.maximum(wait, st.trust), st.fetch) + st.rest + st.net + prior, np.inf)
    if len(bound) <= m:
        return np.arange(len(bound))
    return np.sort(np.argpartition(bound, m - 1)[:m])


def build_cost_matrix(
    invs: tuple[Invocation, ...],
    view: ClusterView,
    ctx: CostContext,
    preds: PredsFn | Preds,
    now: float,
    routers: tuple[str, ...],
    cache: ArrayCache | None = None,
    margin_s: float = 5.0,
    prune_factor: int = 3,
    svc_s: float = 1.0,
) -> CostMatrix:
    """Doc 03 §5.2 for every invocation (rows) over its top-K eligible candidates."""
    cache = cache or ArrayCache()
    k = min(ctx.K, max(1, len(view)))
    occ = view.busy + view.queued + view.inflight
    wait = np.maximum(0, occ - view.slots + 1) * svc_s / np.maximum(view.slots, 1)
    rows, tops = [], []
    for i, inv in enumerate(invs):
        st = static_parts(inv, view, ctx, cache, now, routers[i], margin_s)
        sub = prune(inv, view, ctx, st, wait, prune_factor * k)
        p = _slice(preds, i, sub) if isinstance(preds, Preds) else preds(i, sub)
        r = _row(inv, view, ctx, cache, st, sub, p, now, wait)
        top = np.argsort(r["bound"], kind="stable")[:k]
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


def slo_weight(inv: Invocation, ctx: CostContext) -> float:
    return ctx.sync_weight if inv.slo_class == SloClass.SYNC else 0.3 * ctx.sync_weight
