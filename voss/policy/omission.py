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
        self._p0 = prior[0] / (prior[0] + prior[1])
        self._p = np.full(64, self._p0)

    def p_omit(self, workers: np.ndarray) -> np.ndarray:
        w = np.asarray(workers, dtype=np.int64)
        if len(w) and int(w.max()) >= len(self._p):
            self._p = np.concatenate([self._p, np.full(int(w.max()) + 65 - len(self._p), self._p0)])
        out: np.ndarray = self._p[w]
        return out

    def update(self, worker: int, omitted: bool, t: float) -> ChangePoint | None:
        st = self.state.setdefault(worker, _State(*self.prior))
        x = 1.0 if omitted else 0.0
        st.a += x
        st.b += 1.0 - x
        st.cusum = max(0.0, st.cusum + x - self.k)
        cp = None
        if st.cusum > self.h:
            cp = ChangePoint(worker, t, st.cusum)
            st = self.state[worker] = _State(*self.pessimistic)
        self.p_omit(np.array([worker]))  # grow the cache if needed
        self._p[worker] = st.a / (st.a + st.b)
        return cp
