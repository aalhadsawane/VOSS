"""``blr`` predictor (docs/REVISION_PLAN.md §11.3): hierarchical Bayesian log-linear run-time model with forgetting.

``log T_fj = α_f + β_f·log(x/x_f) − log(speed_j) + γ_{f,m(j)} + δ_j + b_f·load + ε``.

- ``(α_f, β_f, b_f)``: Gaussian prior centred on the function's measured profile, updated in information form with
  forgetting factor λ. A function with no profile gets the population prior (``base.population_prior``).
- ``γ_{f,m}``: function × machine-class effect, shrunk toward its prior mean (the calibration's measured log ratio for
  that function on class ``m``, else 0) with strength ``noise / τ_γ²``; learned from runs of ``f`` on any worker of
  class ``m``.
- ``δ_j``: worker effect shared by all functions on ``j``, shrunk toward 0 (pseudo-count κ).
The predictive variance adds the noise, the coefficients' uncertainty and the remaining uncertainty of ``γ`` and ``δ``,
so a pair (function, worker) never seen together gets a wider distribution (§11.3, table of cases).
"""

from __future__ import annotations

import math

import numpy as np

from voss.core.detmath import inv3, log_safe, matvec3, quad3, rows_dot3
from voss.core.registry import register
from voss.policy.predict.base import ExecObs, FnPrior, LogDist, population_prior


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
            cov = inv3(lam)  # fixed-order arithmetic: no BLAS/LAPACK, identical on every CPU (D-68)
            self._cache = (matvec3(cov, np.diag(self.lam0) * self.beta0 + self.d / self.noise_var), cov)
        return self._cache


@register("predictor", "blr")
class BlrPredictor:
    def __init__(
        self,
        priors: dict[str, FnPrior],
        forgetting: float = 0.995,
        kappa: float = 5.0,
        prior_sd: tuple[float, float, float] = (0.7, 0.3, 0.5),
        tau_gamma: float = 0.4,
    ) -> None:
        self.priors, self.prior_sd = dict(priors), prior_sd
        self.models = {fn: _FnModel(p, prior_sd) for fn, p in sorted(priors.items())}
        self.lam, self.kappa, self.tau2 = forgetting, kappa, tau_gamma**2
        self.delta_s = np.zeros(64)
        self.delta_n = np.zeros(64)
        self.classes: dict[int, str] = {}  # worker -> machine class (set from the view)
        self.gamma: dict[tuple[str, str], tuple[float, float]] = {}  # (fn, class) -> (residual sum, count)

    def set_classes(self, classes: dict[int, str]) -> None:
        self.classes.update(classes)

    def _model(self, fn: str) -> _FnModel:
        if fn not in self.models:  # a new function: population prior (plan §11.3)
            self.models[fn] = _FnModel(population_prior(self.priors), self.prior_sd)
        return self.models[fn]

    def _gamma(self, fn: str, m: _FnModel, cls: str) -> tuple[float, float]:
        """Posterior mean and variance of ``γ_{f,cls}``."""
        mu0 = self.priors[fn].class_log_ratio.get(cls, 0.0) if fn in self.priors else 0.0
        s, n = self.gamma.get((fn, cls), (0.0, 0.0))
        k = m.noise_var / self.tau2
        return (k * mu0 + s) / (k + n), m.noise_var / (k + n)

    def _grow(self, w: int) -> None:
        if w >= len(self.delta_s):
            n = max(w + 1, 2 * len(self.delta_s))
            self.delta_s = np.concatenate([self.delta_s, np.zeros(n - len(self.delta_s))])
            self.delta_n = np.concatenate([self.delta_n, np.zeros(n - len(self.delta_n))])

    def offsets(self, workers: np.ndarray) -> np.ndarray:
        """Shrunk worker offsets ``δ_j`` (vectorized over a growable per-worker array)."""
        w = np.asarray(workers, dtype=np.int64)
        if len(w):
            self._grow(int(w.max()))
        out: np.ndarray = self.delta_s[w] / (self.delta_n[w] + self.kappa)
        return out

    def predict(self, fn: str, in_bytes: int, workers: np.ndarray, speed: np.ndarray, load: np.ndarray) -> LogDist:
        m = self._model(fn)
        X = m.x(in_bytes, np.asarray(load, dtype=float))
        beta, cov = m.posterior()
        w = np.asarray(workers, dtype=np.int64)
        g = [self._gamma(fn, m, self.classes.get(int(j), "")) for j in w]
        g_mu = np.array([a for a, _ in g]) if g else np.zeros(0)
        g_var = np.array([b for _, b in g]) if g else np.zeros(0)
        if len(w):
            self._grow(int(w.max()))
        d_var = m.noise_var / (self.delta_n[w] + self.kappa) if len(w) else np.zeros(0)
        mu = rows_dot3(X, beta) - log_safe(speed) + self.offsets(w) + g_mu
        var = m.noise_var + quad3(X, cov) + g_var + d_var
        return LogDist(mu, np.sqrt(var))

    def update(self, obs: ExecObs) -> None:
        m = self._model(obs.fn)
        X = m.x(obs.in_bytes, np.array([obs.load]))[0]
        y = math.log(max(obs.exec_s, 1e-9)) + math.log(max(obs.speed, 1e-9))
        beta, _ = m.posterior()
        w = int(obs.worker)
        self._grow(w)
        cls = obs.cls or self.classes.get(w, "")
        if obs.cls:
            self.classes[w] = obs.cls
        gam, _ = self._gamma(obs.fn, m, cls)
        delta = float(self.delta_s[w] / (self.delta_n[w] + self.kappa))
        raw = y - float(rows_dot3(X[None, :], beta)[0])
        s, n = self.gamma.get((obs.fn, cls), (0.0, 0.0))
        self.gamma[(obs.fn, cls)] = (self.lam * s + (raw - delta), self.lam * n + 1.0)
        y, resid = y - gam, raw - gam
        # noise variance: discounted mean of squared residuals after the worker offset
        m.noise_var = max(1e-4, self.lam * m.noise_var + (1 - self.lam) * (resid - delta) ** 2)
        m.D = self.lam * m.D + np.outer(X, X)
        m.d = self.lam * m.d + X * (y - delta)
        m.n += 1
        m._cache = None
        self.delta_s[w] = self.lam * self.delta_s[w] + resid
        self.delta_n[w] = self.lam * self.delta_n[w] + 1.0
