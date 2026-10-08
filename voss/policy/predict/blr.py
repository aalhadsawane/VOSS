"""``blr`` predictor (doc 03 §6.1): Bayesian log-linear regression with hierarchical shrinkage and forgetting.

``log T = f_fn + g·log(in_bytes) − log(speed_j) + δ_j + β·load + ε``. Per function, the coefficients
``(f_fn, g, β)`` have a Gaussian prior centred on the profile (SeBS on node C0) and are updated in information form
with forgetting factor λ on the data. Worker offsets ``δ_j`` are shrunk toward 0 (prior pseudo-count κ) and also
forgotten. The predictive sd combines noise and coefficient uncertainty.
"""

from __future__ import annotations

import math

import numpy as np

from voss.core.registry import register
from voss.policy.predict.base import ExecObs, FnPrior, LogDist


class _FnModel:
    def __init__(self, p: FnPrior, prior_sd: tuple[float, float, float]) -> None:
        self.beta0 = np.array([math.log(p.work_ref_s), p.size_exp, 0.0])
        self.lam0 = np.diag(1.0 / np.square(prior_sd))
        self.D = np.zeros((3, 3))
        self.d = np.zeros(3)
        self.ref = math.log(p.in_ref_bytes)
        self.noise_var = p.sigma**2
        self.n = 0.0
        self._cache: tuple[np.ndarray, np.ndarray] | None = None

    def x(self, in_bytes: int, load: np.ndarray) -> np.ndarray:
        lb = math.log(max(in_bytes, 1)) - self.ref
        return np.stack([np.ones_like(load), np.full_like(load, lb), load], axis=1)

    def posterior(self) -> tuple[np.ndarray, np.ndarray]:
        if self._cache is None:
            lam = self.lam0 + self.D / self.noise_var
            cov = np.linalg.inv(lam)
            self._cache = (cov @ (self.lam0 @ self.beta0 + self.d / self.noise_var), cov)
        return self._cache


@register("predictor", "blr")
class BlrPredictor:
    def __init__(
        self,
        priors: dict[str, FnPrior],
        forgetting: float = 0.995,
        kappa: float = 5.0,
        prior_sd: tuple[float, float, float] = (0.7, 0.3, 0.5),
    ) -> None:
        self.models = {fn: _FnModel(p, prior_sd) for fn, p in sorted(priors.items())}
        self.lam, self.kappa = forgetting, kappa
        self.delta_s: dict[int, float] = {}
        self.delta_n: dict[int, float] = {}

    def offsets(self, workers: np.ndarray) -> np.ndarray:
        return np.array([self.delta_s.get(int(w), 0.0) / (self.delta_n.get(int(w), 0.0) + self.kappa) for w in workers])

    def predict(self, fn: str, in_bytes: int, workers: np.ndarray, speed: np.ndarray, load: np.ndarray) -> LogDist:
        m = self.models[fn]
        X = m.x(in_bytes, np.asarray(load, dtype=float))
        beta, cov = m.posterior()
        mu = X @ beta - np.log(np.maximum(speed, 1e-9)) + self.offsets(workers)
        var = m.noise_var + np.einsum("ij,jk,ik->i", X, cov, X)
        return LogDist(mu, np.sqrt(var))

    def update(self, obs: ExecObs) -> None:
        m = self.models[obs.fn]
        X = m.x(obs.in_bytes, np.array([obs.load]))[0]
        y = math.log(max(obs.exec_s, 1e-9)) + math.log(max(obs.speed, 1e-9))
        beta, _ = m.posterior()
        w = int(obs.worker)
        delta = self.delta_s.get(w, 0.0) / (self.delta_n.get(w, 0.0) + self.kappa)
        resid = y - float(X @ beta)
        # noise variance: discounted mean of squared residuals after the worker offset
        m.noise_var = max(1e-4, self.lam * m.noise_var + (1 - self.lam) * (resid - delta) ** 2)
        m.D = self.lam * m.D + np.outer(X, X)
        m.d = self.lam * m.d + X * (y - delta)
        m.n += 1
        m._cache = None
        self.delta_s[w] = self.lam * self.delta_s.get(w, 0.0) + resid
        self.delta_n[w] = self.lam * self.delta_n.get(w, 0.0) + 1.0
