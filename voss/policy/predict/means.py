"""``means`` predictor: per-function running mean of speed-normalized log runtime (doc 03 §6, baseline)."""

from __future__ import annotations

import math

import numpy as np

from voss.core.registry import register
from voss.policy.predict.base import ExecObs, FnPrior, LogDist, prior_mu


@register("predictor", "means")
class MeansPredictor:
    def __init__(self, priors: dict[str, FnPrior], prior_weight: float = 2.0) -> None:
        self.priors = priors
        self.w0 = prior_weight
        self.n: dict[str, float] = {}
        self.s: dict[str, float] = {}
        self.ss: dict[str, float] = {}

    def _resid(self, fn: str, in_bytes: int, speed: float, exec_s: float) -> float:
        return math.log(max(exec_s, 1e-9)) - float(prior_mu(self.priors[fn], in_bytes, np.array([speed]))[0])

    def update(self, obs: ExecObs) -> None:
        r = self._resid(obs.fn, obs.in_bytes, obs.speed, obs.exec_s)
        self.n[obs.fn] = self.n.get(obs.fn, 0.0) + 1
        self.s[obs.fn] = self.s.get(obs.fn, 0.0) + r
        self.ss[obs.fn] = self.ss.get(obs.fn, 0.0) + r * r

    def predict(self, fn: str, in_bytes: int, workers: np.ndarray, speed: np.ndarray, load: np.ndarray) -> LogDist:
        p = self.priors[fn]
        n = self.n.get(fn, 0.0)
        mean = self.s.get(fn, 0.0) / (n + self.w0)
        var = (self.ss.get(fn, 0.0) + self.w0 * p.sigma**2) / (n + self.w0) - mean**2 * n / (n + self.w0)
        mu = prior_mu(p, in_bytes, speed) + mean
        return LogDist(mu, np.full(len(mu), math.sqrt(max(var, 1e-4))))
