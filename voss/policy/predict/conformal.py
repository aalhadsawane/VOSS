"""Online conformal calibration of predictive spread (doc 03 §6.1).

Keeps the last ``window`` standardized residuals ``z = (log T − mu) / sigma`` and scales sigma so that the central
``coverage`` interval matches the empirical quantile of ``|z|``. Wraps any predictor.
"""

from __future__ import annotations

from collections import deque
from statistics import NormalDist

import numpy as np

from voss.policy.predict.base import ExecObs, LogDist, Predictor


class Conformal:
    def __init__(self, inner: Predictor, coverage: float = 0.9, window: int = 500, min_obs: int = 30) -> None:
        self.inner, self.coverage, self.min_obs = inner, coverage, min_obs
        self.z: deque[float] = deque(maxlen=window)
        self.zq = NormalDist().inv_cdf(0.5 + coverage / 2)
        self.scale = 1.0
        self.n_obs = 0

    def predict(self, fn: str, in_bytes: int, workers: np.ndarray, speed: np.ndarray, load: np.ndarray) -> LogDist:
        d = self.inner.predict(fn, in_bytes, workers, speed, load)
        return LogDist(d.mu, d.sigma * self.scale)

    def update(self, obs: ExecObs) -> None:
        d = self.inner.predict(
            obs.fn, obs.in_bytes, np.array([obs.worker]), np.array([obs.speed]), np.array([obs.load])
        )
        z = (np.log(max(obs.exec_s, 1e-9)) - float(d.mu[0])) / max(float(d.sigma[0]), 1e-6)
        self.z.append(abs(z))
        self.n_obs += 1
        if len(self.z) >= self.min_obs and self.n_obs % 20 == 0:
            self.scale = max(0.25, float(np.quantile(np.array(self.z), self.coverage)) / self.zq)
        self.inner.update(obs)
