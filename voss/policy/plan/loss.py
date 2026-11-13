"""Erlang loss on real-valued capacity (docs/REVISION_PLAN.md §11.6).

``B(c, a)`` is the Erlang-B blocking probability of ``c`` servers offered ``a`` Erlang. For integer ``c`` it is computed
by the stable recursion ``B(0) = 1``, ``B(k) = a·B(k−1) / (k + a·B(k−1))``; it is decreasing and convex in ``c``
(Messerli 1972). For real ``c ≥ 0`` this module uses the linear interpolation between the neighbouring integers. A
linear interpolation of a convex decreasing sequence is convex and decreasing, so the carried fraction ``1 − B`` is
concave and increasing in ``c``: the property Proposition 1 needs. Only fixed-order arithmetic is used (identical on every CPU).
"""

from __future__ import annotations

import math

import numpy as np


def erlang_b_curve(n: int, a: float) -> np.ndarray:
    """``[n + 1]`` array ``B(0..n, a)``."""
    out = np.empty(n + 1)
    b = 1.0
    out[0] = b
    for k in range(1, n + 1):
        b = a * b / (k + a * b) if a > 0 else 0.0
        out[k] = b
    return out


class Carried:
    """``g(c) = 1 − B(c, a)`` for real ``c ≥ 0`` (piecewise linear between integers), with the curve cached."""

    def __init__(self, a: float, c_max: float) -> None:
        self.a = max(float(a), 0.0)
        self.n = int(math.ceil(max(c_max, 0.0))) + 1
        self.b = erlang_b_curve(self.n, self.a)

    def __call__(self, c: np.ndarray | float) -> np.ndarray:
        x = np.clip(np.asarray(c, dtype=float), 0.0, float(self.n))
        lo = np.floor(x).astype(np.int64)
        hi = np.minimum(lo + 1, self.n)
        frac = x - lo
        out: np.ndarray = 1.0 - ((1.0 - frac) * self.b[lo] + frac * self.b[hi])
        return out
