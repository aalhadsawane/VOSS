"""Omission model (doc 03 §6.4): Beta posterior of result omission per worker plus CUSUM change-point detection.

Only *mid-session* outcomes feed it (session ends feed survival, doc 09 §1). When CUSUM fires, the worker's posterior
restarts from a pessimistic prior and the change point is reported (eligibility reset; defeats on-off attackers).
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from voss.core.registry import register


@dataclass
class ChangePoint:
    worker: int
    t: float
    statistic: float


@dataclass
class _State:
    a: float
    b: float
    cusum: float = 0.0


@register("omission", "beta_cusum")
class BetaCusum:
    def __init__(
        self,
        prior: tuple[float, float] = (0.5, 20.0),
        pessimistic: tuple[float, float] = (2.0, 4.0),
        k: float = 0.1,
        h: float = 5.0,
    ) -> None:
        self.prior, self.pessimistic, self.k, self.h = prior, pessimistic, k, h
        self.state: dict[int, _State] = {}

    def p_omit(self, workers: np.ndarray) -> np.ndarray:
        out = np.empty(len(workers))
        for i, w in enumerate(workers):
            st = self.state.get(int(w))
            a, b = (st.a, st.b) if st else self.prior
            out[i] = a / (a + b)
        return out

    def update(self, worker: int, omitted: bool, t: float) -> ChangePoint | None:
        st = self.state.setdefault(worker, _State(*self.prior))
        x = 1.0 if omitted else 0.0
        st.a += x
        st.b += 1.0 - x
        st.cusum = max(0.0, st.cusum + x - self.k)
        if st.cusum > self.h:
            cp = ChangePoint(worker, t, st.cusum)
            self.state[worker] = _State(*self.pessimistic)
            return cp
        return None
