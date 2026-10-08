"""``ewma`` predictor: exponentially weighted log-residual and squared residual per function (doc 03 §6)."""

from __future__ import annotations

import math

import numpy as np

from voss.core.registry import register
from voss.policy.predict.base import ExecObs, FnPrior, LogDist, prior_mu


@register("predictor", "ewma")
class EwmaPredictor:
    def __init__(self, priors: dict[str, FnPrior], alpha: float = 0.1) -> None:
        self.priors, self.alpha = priors, alpha
        self.m: dict[str, float] = {}
        self.v: dict[str, float] = {}

    def update(self, obs: ExecObs) -> None:
        p = self.priors[obs.fn]
        r = math.log(max(obs.exec_s, 1e-9)) - float(prior_mu(p, obs.in_bytes, np.array([obs.speed]))[0])
        m, v = self.m.get(obs.fn, 0.0), self.v.get(obs.fn, p.sigma**2)
        a = self.alpha
        self.m[obs.fn] = (1 - a) * m + a * r
        self.v[obs.fn] = (1 - a) * v + a * (r - m) ** 2

    def predict(self, fn: str, in_bytes: int, workers: np.ndarray, speed: np.ndarray, load: np.ndarray) -> LogDist:
        p = self.priors[fn]
        mu = prior_mu(p, in_bytes, speed) + self.m.get(fn, 0.0)
        return LogDist(mu, np.full(len(mu), math.sqrt(max(self.v.get(fn, p.sigma**2), 1e-4))))
