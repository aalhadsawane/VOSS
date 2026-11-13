"""Predictor interface and the log-normal predictive distribution (doc 03 §6.1, doc 05 §4)."""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Protocol

import numpy as np


@dataclass(frozen=True)
class LogDist:
    """Per-candidate log-normal predictive distribution of execution time: ``log T ~ N(mu, sigma²)``."""

    mu: np.ndarray
    sigma: np.ndarray

    def mean(self) -> np.ndarray:
        out: np.ndarray = np.exp(self.mu + self.sigma**2 / 2)
        return out

    def var(self) -> np.ndarray:
        out: np.ndarray = (np.exp(self.sigma**2) - 1) * np.exp(2 * self.mu + self.sigma**2)
        return out

    def quantile(self, q: float) -> np.ndarray:
        from statistics import NormalDist  # noqa: PLC0415

        out: np.ndarray = np.exp(self.mu + self.sigma * NormalDist().inv_cdf(q))
        return out


@dataclass(frozen=True)
class ExecObs:
    """One observed execution (from an ``OUTCOME``)."""

    fn: str
    worker: int
    in_bytes: int
    speed: float
    load: float
    exec_s: float
    t: float
    cls: str = ""  # the worker's machine class


@dataclass(frozen=True)
class FnPrior:
    """Profile prior for a function (doc 03 §6.1: priors from SeBS profiling on node C0)."""

    work_ref_s: float
    in_ref_bytes: float
    size_exp: float
    sigma: float = 0.35
    class_log_ratio: dict[str, float] = field(default_factory=dict)  # prior of γ_{f,m} per machine class (§11.3)


class Predictor(Protocol):
    def predict(self, fn: str, in_bytes: int, workers: np.ndarray, speed: np.ndarray, load: np.ndarray) -> LogDist: ...
    def update(self, obs: ExecObs) -> None: ...


def prior_mu(p: FnPrior, in_bytes: int, speed: np.ndarray) -> np.ndarray:
    base = math.log(p.work_ref_s) + p.size_exp * (math.log(max(in_bytes, 1)) - math.log(p.in_ref_bytes))
    out: np.ndarray = base - np.log(np.maximum(speed, 1e-9))
    return out


def population_prior(priors: dict[str, FnPrior]) -> FnPrior:
    """Prior for a function with no profile and no runs (plan §11.3): the geometric mean run time and mean size exponent
    of the known functions, with a wide spread so that early runs dominate quickly."""
    if not priors:
        return FnPrior(1.0, 1024.0, 0.5, sigma=1.0)
    ps = list(priors.values())
    work = math.exp(sum(math.log(p.work_ref_s) for p in ps) / len(ps))
    size = math.exp(sum(math.log(p.in_ref_bytes) for p in ps) / len(ps))
    return FnPrior(work, size, sum(p.size_exp for p in ps) / len(ps), sigma=1.0)
