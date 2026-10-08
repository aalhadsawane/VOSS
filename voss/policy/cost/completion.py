"""Completion-time distribution (doc 03 §5.2): moment-matched shifted log-normal over
``wait + trust + startup + net + exec``, and the SLO-miss probability including failure."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy.special import ndtr


@dataclass(frozen=True)
class Completion:
    """``T = shift + LogNormal(m, s)`` elementwise over an ``[I, K]`` grid."""

    shift: np.ndarray
    m: np.ndarray
    s: np.ndarray

    def mean(self) -> np.ndarray:
        out: np.ndarray = self.shift + np.exp(self.m + self.s**2 / 2)
        return out

    def sf(self, t: np.ndarray) -> np.ndarray:
        """``P(T > t)``."""
        x = np.maximum(t - self.shift, 1e-12)
        out: np.ndarray = 1.0 - ndtr((np.log(x) - self.m) / np.maximum(self.s, 1e-9))
        return np.where(t <= self.shift, 1.0, out)

    def quantile(self, q: float) -> np.ndarray:
        from statistics import NormalDist  # noqa: PLC0415

        out: np.ndarray = self.shift + np.exp(self.m + self.s * NormalDist().inv_cdf(q))
        return out

    def cvar(self, q: float, n: int = 16) -> np.ndarray:
        """Mean of the upper ``1 − q`` tail (midpoint rule over quantiles)."""
        qs = q + (1 - q) * (np.arange(n) + 0.5) / n
        out: np.ndarray = np.asarray(np.mean([self.quantile(float(x)) for x in qs], axis=0))
        return out


def moment_match(
    const_mean: np.ndarray, const_var: np.ndarray, exec_mean: np.ndarray, exec_var: np.ndarray, shift_frac: float = 0.5
) -> Completion:
    """Shift = ``shift_frac`` × deterministic part; the rest is a log-normal with the summed mean and variance."""
    shift = shift_frac * const_mean
    mean = np.maximum(const_mean - shift + exec_mean, 1e-9)
    var = np.maximum(const_var + exec_var, 1e-12)
    s2 = np.log1p(var / mean**2)
    return Completion(shift, np.log(mean) - s2 / 2, np.sqrt(s2))


def p_miss(c: Completion, budget: np.ndarray, p_fail: np.ndarray) -> np.ndarray:
    """Probability of missing the remaining deadline budget, counting failures as misses."""
    out: np.ndarray = np.clip(p_fail + (1 - p_fail) * c.sf(budget), 0.0, 1.0)
    return out
