"""``KEEPALIVE+SUMMARY`` of the scheduler role (doc 08 §4): load, capacity, trust-warm capacity, warm functions,
measured routing prices (D-33) and placement latency for the orchestrator's decision-latency SLO (doc 07 §2)."""

from __future__ import annotations

from collections import deque
from typing import TYPE_CHECKING, Any

import numpy as np

from voss.core.ids import Addr, ClusterId, WorkerId
from voss.core.messages import KeepaliveSummary
from voss.core.types import ClusterView
from voss.observe.summaries import summarize
from voss.runtime.actor import ActorContext
from voss.runtime.schedlib.models import SchedModels
from voss.runtime.schedlib.planning import Planning
from voss.runtime.schedlib.prices import Prices, backlog_s
from voss.runtime.schedlib.viewcache import ViewCache
from voss.runtime.workerlib.host import HostLocal


class ReportMixin:
    ctx: ActorContext
    hl: HostLocal
    views: ViewCache
    planning: Planning
    models: SchedModels
    prices: Prices
    active: bool
    epoch: int
    cluster: ClusterId
    decide_lat: deque[float]

    if TYPE_CHECKING:

        @property
        def now(self) -> float: ...
        def send(self, dst: Addr, msg: Any) -> bool: ...
        def after(self, dt: float, fn: Any, *args: Any) -> Any: ...
        def eligible(self) -> set[WorkerId]: ...
        def stuck_workers(self) -> int: ...

    def _keepalive(self) -> None:
        if not self.active:
            return
        view = self.views.view(self.eligible(), self.now)
        summ = summarize(self.cluster, view)
        self.prices.decay(self.ctx.cfg.voss.scheduler.keepalive_s)
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
            self.prices.overhead,
            tuple(sorted((str(t), v) for t, v in summ.trust_warm_capacity.items())),
            tuple(sorted(warm.items())),
            summ.diversity,
            bool(prev is not None and prev.cost_terms.get("shortfall", 0.0) > 1e-6),
            self._forecast_load(view),
            self.prices.cold_trust,
            self.prices.cold_fn,
            backlog_s(summ.load, float(self.models.svc)),
            float(np.quantile(self.decide_lat, 0.9)) if self.decide_lat else -1.0,  # -1: no decisions
            self.stuck_workers(),
        )
        self.decide_lat.clear()
        self.send(self.ctx.directory.orchestrator, msg)
        self.after(self.ctx.cfg.voss.scheduler.keepalive_s, self._keepalive)

    def _forecast_load(self, view: ClusterView) -> float:
        """Forecast concurrent demand (sum of per-function capacity quantiles) over attested slots."""
        d = self.models.forecaster.forecast(self.now)
        need = sum(q for k, q in d.q.items() if k.startswith("fn:"))
        return float(need / max(1, int(view.slots.sum())))
