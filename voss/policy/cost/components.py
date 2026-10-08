"""Cost matrix construction (doc 03 §5.1-5.2, doc 08 §5).

For invocations × candidate workers it produces the named components ``wait, trust, startup, net, exec, pFail,
exposure``, the completion distribution and ``pMiss``. Trust and artifact fetch overlap the slot wait:
``time_to_start = max(wait, trust, fetch) + rest`` (doc 08 §5). Candidates are pruned to the top ``K`` by a cheap
bound (expected completion plus a failure penalty).
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from voss.core.types import ClusterView, Invocation, SloClass
from voss.policy.cost.arrays import ArrayCache, ViewArrays
from voss.policy.cost.completion import Completion, moment_match, p_miss
from voss.policy.cost.inputs import CostContext
from voss.policy.place.candidates import eligible

MB = 1024 * 1024
NAMES = ("wait", "trust", "startup", "net", "exec", "pFail", "exposure", "tts")


@dataclass(frozen=True)
class Preds:
    """Per-invocation predictions over all view workers (computed by the scheduler)."""

    exec_mean: np.ndarray  # [I, N]
    exec_var: np.ndarray  # [I, N]
    p_alive: np.ndarray  # [I, N] session survival over the expected completion horizon
    p_omit: np.ndarray  # [N]
    svc_mean: np.ndarray  # [N] typical service time on the worker (readiness)


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


def startup(
    a: ViewArrays, code: np.ndarray, hdd: np.ndarray, ctx: CostContext, fn: str, speed: np.ndarray
) -> tuple[np.ndarray, np.ndarray]:
    """``(fetch_s, rest_s)`` per worker from its cache level (doc 02 §5 ladder)."""
    f = ctx.fns[fn]
    read = np.where(hdd, a.hdd_read, a.ssd_read)
    boot = f.rootfs_mb / read + a.boot + f.init_s / speed + a.dispatch
    restore = f.snapshot_mb * a.touched / read + a.restore + a.dispatch
    rest = np.where(code >= 3, a.dispatch, np.where((code == 2) & a.has_snap, restore, boot))
    mb = f.bundle_mb + f.rootfs_mb
    fetch = np.where(code == 0, a.reg_rtt + mb * MB * 8 / a.down + a.verify * mb / speed, 0.0)
    return fetch, rest


def _row(
    inv: Invocation,
    view: ClusterView,
    ctx: CostContext,
    a: ViewArrays,
    cache: ArrayCache,
    preds: Preds,
    i: int,
    now: float,
    router: str,
    wait: np.ndarray,
    margin_s: float,
) -> dict[str, np.ndarray]:
    f, t = ctx.fns[inv.fn], ctx.tenants[inv.tenant]
    ok = eligible(view, inv, now, margin_s) & (view.assurance >= t.assurance_floor)
    holder = np.fromiter((inv.tenant in ts for ts in view.trust), dtype=bool, count=len(view))
    kbs = ctx.geo.rtt(a.lat, a.lon, t.kbs_lat, t.kbs_lon)
    trust = np.where(holder | (a.trust_fixed == 0), 0.0, kbs + a.trust_fixed)
    code, hdd = cache.level(view, inv.fn)
    fetch, rest = startup(a, code, hdd, ctx, inv.fn, view.speed)
    rlat, rlon = ctx.routers.get(router, (float(a.lat.mean()), float(a.lon.mean())))
    net = ctx.geo.rtt(a.lat, a.lon, rlat, rlon) + inv.in_bytes * 8 / a.down + f.out_bytes * 8 / a.up
    tts = np.maximum(np.maximum(wait, trust), fetch) + rest
    e_mean = preds.exec_mean[i] * a.cpu_factor
    comp = moment_match(tts + net, (0.3 * tts) ** 2, e_mean, preds.exec_var[i] * a.cpu_factor**2)
    p_fail = 1 - preds.p_alive[i] * (1 - preds.p_omit)
    budget = np.full(len(view), inv.deadline - (now - inv.t_arrive))
    return {
        "ok": ok,
        "wait": wait,
        "trust": trust,
        "startup": fetch + rest,
        "net": net,
        "exec": e_mean,
        "pFail": p_fail,
        "exposure": np.where(holder, 0.0, t.sigma * (1 - view.assurance)),
        "tts": tts,
        "shift": comp.shift,
        "m": comp.m,
        "s": comp.s,
        "pMiss": p_miss(comp, budget, p_fail),
        "budget": budget,
        "bound": np.where(ok, comp.mean() + 10.0 * p_fail, np.inf),
    }


def build_cost_matrix(
    invs: tuple[Invocation, ...],
    view: ClusterView,
    ctx: CostContext,
    preds: Preds,
    now: float,
    routers: tuple[str, ...],
    cache: ArrayCache | None = None,
    margin_s: float = 5.0,
) -> CostMatrix:
    """Doc 03 §5.2 for every invocation (rows) over its top-K eligible candidates."""
    cache = cache or ArrayCache()
    a = cache.get(view, ctx)
    k = min(ctx.K, max(1, len(view)))
    occ = view.busy + view.queued + view.inflight
    wait = np.maximum(0, occ - view.slots + 1) * preds.svc_mean / np.maximum(view.slots, 1)
    rows = [_row(inv, view, ctx, a, cache, preds, i, now, routers[i], wait, margin_s) for i, inv in enumerate(invs)]
    top = np.array([np.argsort(r["bound"], kind="stable")[:k] for r in rows])

    def grid(name: str) -> np.ndarray:
        return np.array([r[name][top[i]] for i, r in enumerate(rows)])

    comps = {name: grid(name) for name in NAMES}
    completion = Completion(grid("shift"), grid("m"), grid("s"))
    return CostMatrix(comps, top, grid("ok"), completion, grid("pMiss"), grid("budget"))


def slo_weight(inv: Invocation, ctx: CostContext) -> float:
    return ctx.sync_weight if inv.slo_class == SloClass.SYNC else 0.3 * ctx.sync_weight
