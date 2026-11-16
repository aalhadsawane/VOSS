"""One request-placement decision (doc 03 §5): predictions → cost matrix → scalarize → admission → place.

The scheduler role calls this and applies the result after the decision latency (doc 01 §7).
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field, replace
from typing import Any

import numpy as np

from voss.core.config import VossConfig
from voss.core.ids import InvId, WorkerId
from voss.core.registry import create
from voss.core.types import ClusterView, Invocation, Placement
from voss.policy.admission import admit
from voss.policy.cost.arrays import ArrayCache
from voss.policy.cost.components import CostMatrix, Waits, build_cost_matrix, completion_of
from voss.policy.cost.inputs import CostContext
from voss.policy.cost.scalarize import SCALARIZERS
from voss.policy.cost.wait import JobEst, worker_waits
from voss.policy.place import registry as _placers  # noqa: F401  (registers placers)
from voss.policy.place.base import PlaceRequest
from voss.runtime.schedlib.models import SchedModels


@dataclass(frozen=True)
class Timing:
    """Predicted completion of the chosen attempt, from the decision time (plan V7.1)."""

    q: float  # the detector quantile (``voss.detection.quantile``) of completion time
    mean: float  # mean completion time
    budget: float  # remaining deadline budget


@dataclass
class Decision:
    assign: dict[InvId, WorkerId] = field(default_factory=dict)
    rejected: dict[InvId, str] = field(default_factory=dict)
    deferred: list[InvId] = field(default_factory=list)
    predicted: dict[tuple[InvId, WorkerId], tuple[float, float]] = field(default_factory=dict)
    timing: dict[InvId, Timing] = field(default_factory=dict)
    work: int = 0


def make_placer(name: str, cfg: VossConfig) -> Any:
    return create("placer", name)


class Decider:
    def __init__(self, cfg: VossConfig, ctx: CostContext, models: SchedModels, start_utc_h: float) -> None:
        self.cfg, self.ctx, self.models, self.start_utc_h = cfg, ctx, models, start_utc_h
        self.sync = make_placer(cfg.placer.sync, cfg)
        self.batch = make_placer(cfg.placer.async_, cfg)
        self.scalarize = SCALARIZERS[cfg.cost.scalarizer]
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
        jobs: Mapping[WorkerId, Sequence[JobEst]] | None = None,
        rtt: Mapping[WorkerId, float] | None = None,
    ) -> Decision:
        out = Decision(work=len(invs) * max(1, len(view)))
        if not len(view):
            out.deferred = [i.id for i in invs]
            return out
        preds, svc = self.models.preds_fn(invs, view, now, self.start_utc_h), self.models.svc
        cm = build_cost_matrix(
            invs, view, self.ctx, preds, now, routers, self.cache, svc_s=svc, waits=self._waits(view, jobs, now, svc)
        )
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
        placer = self.batch if windowed else self.sync
        if getattr(placer, "uses_fn_load", False):
            req = replace(req, fn_load=self.models.fn_load(sorted({inv.fn for inv in sub}), now))
        self._record(out, req, placer.place(req), view, tuple(routers[k] for k in keep), idx, rtt or {})
        return out

    def _record(
        self,
        out: Decision,
        req: PlaceRequest,
        pl: Placement,
        view: ClusterView,
        routers: tuple[str, ...],
        idx: dict[WorkerId, int] | None,
        rtt: Mapping[WorkerId, float],
    ) -> None:
        """Assignments, predictions and watchdog timings of a placement; unplaced invocations are deferred."""
        idx = idx if idx is not None else view.index()
        for r, inv in enumerate(req.invs):
            w = pl.assign.get(inv.id)
            if w is None:
                out.deferred.append(inv.id)
                continue
            out.assign[inv.id] = w
            j = idx[w]
            out.predicted[(inv.id, w)] = _pred(req.cm, r, j)
            relay = self._relay(view, routers[r], j, rtt)
            out.timing[inv.id] = _timing(req.cm, r, j, self.cfg.detection.quantile, relay)

    def _relay(self, view: ClusterView, router: str, j: int, rtt: Mapping[WorkerId, float]) -> float:
        """Seconds the watchdog's span adds to the cost model's network time on view worker ``j`` (development log
        iteration 2). The timer runs from the dispatch at the scheduler to the outcome back there, so its round trip is
        scheduler-worker, not router-worker: the round trip the scheduler last observed to ``j`` (dispatch to
        ``ACCEPTED``, sent on receipt), else its distance estimate. Input and output transfer stay in ``net``."""
        a = self.cache.get(view, self.ctx)
        lat, lon = a.lat[j : j + 1], a.lon[j : j + 1]
        rlat, rlon = self.ctx.routers.get(router, (float(a.lat.mean()), float(a.lon.mean())))
        to_router = float(self.ctx.geo.rtt(lat, lon, rlat, rlon)[0])
        seen = rtt.get(view.workers[j])
        if seen is not None:
            return seen - to_router
        if self.ctx.scheduler is None:
            return 0.0
        return float(self.ctx.geo.rtt(lat, lon, *self.ctx.scheduler)[0]) - to_router

    def _waits(
        self, view: ClusterView, jobs: Mapping[WorkerId, Sequence[JobEst]] | None, now: float, svc: float
    ) -> Waits | None:
        """Doc 03 §5.2 / D-77: per-worker wait from predicted remaining work (``cost.wait_model: per_worker``)."""
        if self.cfg.cost.wait_model != "per_worker" or jobs is None:
            return None
        prio = self.cfg.worker.sync_priority
        asyn = worker_waits(view, jobs, now, svc, False, prio)
        return Waits(asyn, worker_waits(view, jobs, now, svc, True, True) if prio else asyn)

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


def _pred(cm: CostMatrix | None, r: int, j: int) -> tuple[float, float]:
    """Predicted (mean, variance) of execution for row ``r`` on view index ``j`` (from the cost matrix)."""
    if cm is None or j not in cm.candidates[r]:
        return 0.0, 0.0
    k = int(np.flatnonzero(cm.candidates[r] == j)[0])
    return float(cm.components["exec"][r, k]), float(cm.components["exec_var"][r, k])


def _timing(cm: CostMatrix | None, r: int, j: int, q: float, relay: float = 0.0) -> Timing:
    """The detector quantile is of the attempt as the scheduler times it (network ``net + relay``); the mean and the
    budget stay those of the invocation as its router sees it, for the deadline-fit check."""
    if cm is None or j not in cm.candidates[r]:
        return Timing(0.0, 0.0, float("inf"))
    k = int(np.flatnonzero(cm.candidates[r] == j)[0])
    c, x = cm.completion, cm.components
    tts = x["tts"][r, k : k + 1]
    watched = completion_of(tts, x["net"][r, k : k + 1] + relay, x["exec"][r, k : k + 1], x["exec_var"][r, k : k + 1])
    return Timing(float(watched.quantile(q)[0]), float(c.mean()[r, k]), float(cm.budget[r, k]))


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
