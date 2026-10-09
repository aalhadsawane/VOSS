"""``instant`` predictor (doc 06 §4 ablation "prediction → instantaneous"): the last observed runtime of the
function, the same for every worker, with no uncertainty and no speed or load model; the profile prior until the
first observation."""

from __future__ import annotations

import math

import numpy as np

from voss.core.registry import register
from voss.policy.predict.base import ExecObs, FnPrior, LogDist, prior_mu

SIGMA = 1e-3  # a point estimate (the cost model then ignores runtime risk)


@register("predictor", "instant")
class InstantPredictor:
    def __init__(self, priors: dict[str, FnPrior]) -> None:
        self.priors = priors
        self.last: dict[str, float] = {}

    def update(self, obs: ExecObs) -> None:
        self.last[obs.fn] = max(obs.exec_s, 1e-9)

    def predict(self, fn: str, in_bytes: int, workers: np.ndarray, speed: np.ndarray, load: np.ndarray) -> LogDist:
        last = self.last.get(fn)
        mu = math.log(last) if last is not None else float(prior_mu(self.priors[fn], in_bytes, np.ones(1))[0])
        return LogDist(np.full(len(workers), mu), np.full(len(workers), SIGMA))
