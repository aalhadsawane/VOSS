"""One fast-loop decision (doc 03 §5): predictions → cost matrix → scalarize → admission → place → hedge.

The scheduler role calls this and applies the result after the decision latency (doc 01 §7).
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Any

import numpy as np

from voss.core.config import VossConfig
from voss.core.ids import InvId, WorkerId
from voss.core.registry import REGISTRY, create
from voss.core.types import ClusterView, Invocation, SloClass
from voss.policy import hedge as _hedge  # noqa: F401  (registers hedge policies)
from voss.policy.admission import admit, filler_mask
from voss.policy.cost.arrays import ArrayCache
from voss.policy.cost.components import CostMatrix, PredsFn, build_cost_matrix
from voss.policy.cost.inputs import CostContext
from voss.policy.cost.scalarize import SCALARIZERS
from voss.policy.hedge import TokenBucket
from voss.policy.place import registry as _placers  # noqa: F401  (registers placers)
from voss.policy.place.base import PlaceRequest
from voss.runtime.schedlib.models import SchedModels


@dataclass
class Decision:
    assign: dict[InvId, WorkerId] = field(default_factory=dict)
    hedges: dict[InvId, WorkerId] = field(default_factory=dict)
    rejected: dict[InvId, str] = field(default_factory=dict)
    deferred: list[InvId] = field(default_factory=list)
    predicted: dict[tuple[InvId, WorkerId], tuple[float, float]] = field(default_factory=dict)
    work: int = 0


def make_placer(name: str, cfg: VossConfig) -> Any:
    if name in ("flow", "ilp_window"):
        return create("placer", name, slots_per_worker=cfg.placer.slots_per_worker)
    return create("placer", name)


class Decider:
    def __init__(self, cfg: VossConfig, ctx: CostContext, models: SchedModels, start_utc_h: float) -> None:
        self.cfg, self.ctx, self.models, self.start_utc_h = cfg, ctx, models, start_utc_h
        self.sync = make_placer(cfg.placer.sync, cfg)
        self.batch = make_placer(cfg.placer.async_, cfg)
        self.scalarize = SCALARIZERS[cfg.cost.scalarizer]
        self.hedge = REGISTRY.get("hedge", cfg.hedge.name) if cfg.hedge.name else None
        self.bucket = TokenBucket(cfg.hedge.budget)
        self.cache = ArrayCache()

    def decide(
        self,
        invs: tuple[Invocation, ...],
        view: ClusterView,
        now: float,
        routers: tuple[str, ...],
        gen: np.random.Generator,
        windowed: bool,
        idx: dict[WorkerId, int] | None = None,
    ) -> Decision:
        out = Decision(work=len(invs) * max(1, len(view)))
        if not len(view):
            out.deferred = [i.id for i in invs]
            return out
        preds = self.models.preds_fn(invs, view, now, self.start_utc_h)
        svc = self.models.svc
        cm = build_cost_matrix(invs, view, self.ctx, preds, now, routers, self.cache, svc_s=svc)
        cm = self._filler(invs, view, cm)
        scores = self.scalarize(cm, invs, self.ctx)
        keep = self._admission(invs, cm, out)
        if not keep:
            return out
        sub = tuple(invs[i] for i in keep)
        req = PlaceRequest(
            sub,
            view,
            now,
            gen,
            cm=_rows(cm, keep),
            scores=scores[keep],
            slot_step=self.ctx.eps * svc / np.maximum(view.slots[cm.candidates[keep]], 1),
        )
        pl = (self.batch if windowed else self.sync).place(req)
        idx = idx if idx is not None else view.index()
        for r, inv in enumerate(sub):
            w = pl.assign.get(inv.id)
            if w is None:
                out.deferred.append(inv.id)
                continue
            out.assign[inv.id] = w
            j = idx[w]
            out.predicted[(inv.id, w)] = _pred(req.cm, r, j)
            self._maybe_hedge(inv, r, j, req, view, out, preds, keep[r])
        return out

    def _filler(self, invs: tuple[Invocation, ...], view: ClusterView, cm: CostMatrix) -> CostMatrix:
        if not any(i.slo_class == SloClass.FILLER for i in invs):
            return cm
        ok = filler_mask(view, self.cfg.admission.filler_headroom)
        feas = cm.feasible.copy()
        for i, inv in enumerate(invs):
            if inv.slo_class == SloClass.FILLER:
                feas[i] &= ok[cm.candidates[i]]
        return replace(cm, feasible=feas)

    def _admission(self, invs: tuple[Invocation, ...], cm: CostMatrix, out: Decision) -> list[int]:
        keep = []
        for i, inv in enumerate(invs):
            budget = float(cm.budget[i, 0]) if cm.budget.shape[1] else 0.0
            verdict = (
                admit(inv, cm.p_miss[i], cm.feasible[i], cm.components["wait"][i], budget, self.cfg.admission.eps)
                if self.cfg.admission.enabled and not inv.excluded  # a retry was admitted already (D-43)
                else ("admit" if cm.feasible[i].any() else "defer")
            )
            if verdict == "admit":
                keep.append(i)
            elif verdict == "reject":
                out.rejected[inv.id] = "admission"
            else:
                out.deferred.append(inv.id)
        return keep

    def _maybe_hedge(
        self,
        inv: Invocation,
        r: int,
        j: int,
        req: PlaceRequest,
        view: ClusterView,
        out: Decision,
        preds: PredsFn,
        row: int,
    ) -> None:
        self.bucket.earn()
        if self.hedge is None or req.cm is None or req.scores is None:
            return
        h = self.hedge(
            inv,
            req.cm.candidates[r],
            req.cm.feasible[r],
            req.scores[r],
            req.cm.p_miss[r],
            j,
            view,
            self.cfg.hedge.theta,
        )
        if h is not None and self.bucket.take():
            w = view.workers[h]
            out.hedges[inv.id] = w
            out.predicted[(inv.id, w)] = _pred(req.cm, r, h)


def _pred(cm: CostMatrix | None, r: int, j: int) -> tuple[float, float]:
    """Predicted (mean, variance) of execution for row ``r`` on view index ``j`` (from the cost matrix)."""
    if cm is None or j not in cm.candidates[r]:
        return 0.0, 0.0
    k = int(np.flatnonzero(cm.candidates[r] == j)[0])
    return float(cm.components["exec"][r, k]), float(cm.components["exec_var"][r, k])


def _rows(cm: CostMatrix, keep: list[int]) -> CostMatrix:
    from voss.policy.cost.completion import Completion  # noqa: PLC0415

    c = cm.completion
    return CostMatrix(
        {k: v[keep] for k, v in cm.components.items()},
        cm.candidates[keep],
        cm.feasible[keep],
        Completion(c.shift[keep], c.m[keep], c.s[keep]),
        cm.p_miss[keep],
        cm.budget[keep],
    )
