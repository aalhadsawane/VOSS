"""Learned models held by the scheduler (doc 03 §6) and the per-decision prediction bundle for the cost model."""

from __future__ import annotations

from typing import Any

import numpy as np

from voss.core.config import VossConfig
from voss.core.registry import create
from voss.core.types import ClusterView, Invocation
from voss.policy import omission as _omission  # noqa: F401  (registers models)
from voss.policy import survival as _survival  # noqa: F401
from voss.policy.cost.components import Preds, PredsFn
from voss.policy.predict import arrivals as _arrivals  # noqa: F401
from voss.policy.predict.base import ExecObs, FnPrior
from voss.policy.predict.conformal import Conformal
from voss.policy.predict.registry import make_predictor


class SchedModels:
    """Predictor, survival, omission and a service-time estimate; checkpointable soft state (doc 07 §3)."""

    def __init__(self, cfg: VossConfig, priors: dict[str, FnPrior]) -> None:
        pc = cfg.predictor
        inner = make_predictor(pc.name, priors, pc.forgetting)
        self.predictor: Any = Conformal(inner) if pc.conformal else inner
        self.survival: Any = create("survival", cfg.models.survival)
        self.omission: Any = create("omission", cfg.models.omission, h=cfg.models.cusum_h)
        self.forecaster: Any = create("forecaster", "ewma2")
        self.svc = 1.0
        self.survival_version = 0
        self._static_key: tuple[int, int] | None = None
        self._static_cache: tuple[np.ndarray, ...] = ()

    def observe(self, obs: ExecObs) -> None:
        self.predictor.update(obs)
        self.svc = 0.98 * self.svc + 0.02 * obs.exec_s

    def preds_fn(self, invs: tuple[Invocation, ...], view: ClusterView, now: float, start_utc_h: float) -> PredsFn:
        """Predictions for row ``i`` on view indices ``sub`` (evaluated lazily on pruned candidates only)."""
        workers = np.asarray(view.workers, dtype=np.int64)
        load = (view.busy + view.queued + view.inflight) / np.maximum(view.slots, 1)
        k, lam, start, tz, drain = self._static(view)
        hour = np.mod(start_utc_h + now / 3600 + tz, 24)

        def fn(i: int, sub: np.ndarray) -> Preds:
            inv = invs[i]
            d = self.predictor.predict(inv.fn, inv.in_bytes, workers[sub], view.speed[sub], load[sub])
            mean = d.mean()
            alive = self.survival.p_alive_arr(
                k[sub], lam[sub], now - start[sub], mean + 2.0, hour[sub], drain[sub], now
            )
            return Preds(mean, d.var(), alive, self.omission.p_omit(workers[sub]))

        return fn

    def _static(self, view: ClusterView) -> tuple[np.ndarray, ...]:
        key = (id(view.cache), self.survival_version)
        if self._static_key != key:
            st = view.static if view.static else (None,) * len(view)
            k, lam = self.survival.tier_params([s.tier if s else "idle" for s in st])
            start = np.array([s.session_start if s else 0.0 for s in st])
            tz = np.array([s.tz if s else 0.0 for s in st])
            drain = (
                np.array([d if d is not None else np.inf for d in view.drain_deadline])
                if view.drain_deadline
                else np.full(len(view), np.inf)
            )
            self._static_cache = (k, lam, start, tz, drain)
            self._static_key = key
        return self._static_cache

    def refit(self, live: dict[str, list[float]]) -> None:
        self.survival.refit(live)
        self.survival_version += 1
