"""From plan to actions (doc 03 §4.4): idempotent, value-ordered, rate-limited per worker."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from voss.core.ids import FnId, TenantId, WorkerId
from voss.policy.plan.types import Plan


@dataclass(frozen=True)
class PlanAction:
    """Doc 05 §3: ``kind ∈ {PREPARE, PIN_SNAPSHOT, WARM, RELEASE}``."""

    kind: str
    worker: WorkerId
    tenant: TenantId
    fns: tuple[FnId, ...] = ()
    n: int = 0
    value: float = 0.0


def _index(
    plan: Plan | None,
) -> tuple[dict[tuple[str, int], bool], dict[tuple[str, int], int], dict[tuple[str, int], bool]]:
    if plan is None:
        return {}, {}, {}
    y = {(str(t), int(w)): bool(plan.y[i, j]) for i, t in enumerate(plan.tenants) for j, w in enumerate(plan.workers)}
    wv = {(str(f), int(w)): int(plan.w[i, j]) for i, f in enumerate(plan.fns) for j, w in enumerate(plan.workers)}
    s = {(str(f), int(w)): bool(plan.s[i, j]) for i, f in enumerate(plan.fns) for j, w in enumerate(plan.workers)}
    return y, wv, s


def diff(prev: Plan | None, plan: Plan, fn_tenant: dict[str, str], benefit: dict[str, float]) -> list[PlanAction]:
    """Actions that move workers from ``prev`` to ``plan`` (sorted: releases first, then by value)."""
    py, pw, ps = _index(prev)
    ny, nw, ns = _index(plan)
    out: list[PlanAction] = []
    for (t, w), on in sorted(py.items()):
        if on and not ny.get((t, w), False):
            out.append(PlanAction("RELEASE", WorkerId(w), TenantId(t)))
    fns_of: dict[str, list[str]] = {}
    for f, t in sorted(fn_tenant.items()):
        fns_of.setdefault(t, []).append(f)
    for (t, w), on in sorted(ny.items()):
        if on and not py.get((t, w), False):
            fns = tuple(FnId(f) for f in fns_of.get(t, []) if f in plan.fns)
            out.append(PlanAction("PREPARE", WorkerId(w), TenantId(t), fns, value=sum(benefit.get(f, 0) for f in fns)))
    for (f, w), on in sorted(ns.items()):
        if on and not ps.get((f, w), False):
            out.append(
                PlanAction("PIN_SNAPSHOT", WorkerId(w), TenantId(fn_tenant[f]), (FnId(f),), value=benefit.get(f, 0.0))
            )
    for (f, w), n in sorted(nw.items()):
        if n != pw.get((f, w), 0):
            out.append(
                PlanAction("WARM", WorkerId(w), TenantId(fn_tenant[f]), (FnId(f),), n, value=benefit.get(f, 0.0) * n)
            )
    rank = {"RELEASE": 0, "PREPARE": 1, "PIN_SNAPSHOT": 2, "WARM": 3}
    return sorted(out, key=lambda a: (rank[a.kind], -a.value, int(a.worker), a.tenant, a.fns))


def rate_limit(actions: list[PlanAction], per_worker: int) -> list[PlanAction]:
    """Keep at most ``per_worker`` PREPAREs per worker per round (releases always pass)."""
    seen: dict[int, int] = {}
    out = []
    for a in actions:
        if a.kind == "PREPARE":
            seen[int(a.worker)] = seen.get(int(a.worker), 0) + 1
            if seen[int(a.worker)] > per_worker:
                continue
        out.append(a)
    return out


def confirmed(plan: Plan, trust: dict[int, frozenset[str]]) -> np.ndarray:
    """``[T, J]``: planned trust-warm pairs the worker has confirmed (key present) — the fast loop's view."""
    out = np.zeros_like(plan.y)
    for j, w in enumerate(plan.workers):
        ts = trust.get(int(w), frozenset())
        for i, t in enumerate(plan.tenants):
            out[i, j] = plan.y[i, j] and t in ts
    return out
