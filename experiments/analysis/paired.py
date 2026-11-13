"""Paired comparisons across seeds (docs/REVISION_PLAN.md V2, V12.1).

Two systems run on the same seeds face the same scenario, so they are compared per seed. The estimators:

- ``paired_diff``: mean over seeds of ``b - a``, with a 95% percentile bootstrap interval over seeds;
- ``paired_ratio``: ratio of per-seed means, ``mean(b) / mean(a)`` over the same resampled seeds, with the same
  interval; a relative change is ``ratio - 1`` and is never below -100%.

Resampling uses ``voss.core.rng.stream`` (AGENTS.md rule 9), so intervals are reproducible.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd
from voss.core.rng import stream

B = 10_000


@dataclass(frozen=True)
class Estimate:
    value: float
    lo: float
    hi: float
    n: int

    def excludes(self, x: float) -> bool:
        return not self.lo <= x <= self.hi


def _aligned(a: pd.Series, b: pd.Series) -> tuple[np.ndarray, np.ndarray]:
    """Values of ``a`` and ``b`` (indexed by seed) on their common seeds, in seed order."""
    seeds = sorted(set(a.index) & set(b.index))
    return a.loc[seeds].to_numpy(dtype=float), b.loc[seeds].to_numpy(dtype=float)


def _draws(n: int, label: str) -> np.ndarray:
    return stream(0, "analysis.bootstrap", label, n).integers(0, n, size=(B, n))


def paired_diff(a: pd.Series, b: pd.Series, label: str = "") -> Estimate:
    x, y = _aligned(a, b)
    if not len(x):
        return Estimate(float("nan"), float("nan"), float("nan"), 0)
    d = y - x
    boot = d[_draws(len(d), label)].mean(axis=1)
    lo, hi = np.quantile(boot, [0.025, 0.975])
    return Estimate(float(d.mean()), float(lo), float(hi), len(d))


def paired_ratio(a: pd.Series, b: pd.Series, label: str = "") -> Estimate:
    x, y = _aligned(a, b)
    if not len(x) or x.mean() == 0:
        return Estimate(float("nan"), float("nan"), float("nan"), len(x))
    idx = _draws(len(x), label)
    boot = y[idx].mean(axis=1) / np.maximum(x[idx].mean(axis=1), 1e-12)
    lo, hi = np.quantile(boot, [0.025, 0.975])
    return Estimate(float(y.mean() / x.mean()), float(lo), float(hi), len(x))


def holm(pvalues: dict[str, float], alpha: float = 0.05) -> dict[str, bool]:
    """Holm step-down: which hypotheses are rejected at family-wise level ``alpha``."""
    order = sorted(pvalues, key=lambda k: (pvalues[k], k))
    out, m = {}, len(order)
    still = True
    for i, k in enumerate(order):
        still = still and pvalues[k] <= alpha / (m - i)
        out[k] = still
    return out
