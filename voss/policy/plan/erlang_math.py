"""Erlang-B loss model helpers (planner-v2 proposal §2-3): the blocking curve, the exact distribution of surviving
reserved slots, and the expected-utility evaluation of a key-holder set."""

from __future__ import annotations

import itertools

import numpy as np


def erlang_b(c: int, a: float) -> float:
    """``B(c, a)`` by the stable recursion ``B(0)=1``, ``B(c)=a·B(c−1)/(c + a·B(c−1))`` (proposal §2, Fact 2)."""
    b = 1.0
    for k in range(1, c + 1):
        b = a * b / (k + a * b)
    return b


def erlang_b_curve(n: int, a: float) -> np.ndarray:
    """``[n+1]`` array ``B(0..n, a)`` (decreasing, convex in ``c``: Messerli 1972)."""
    out = np.empty(n + 1)
    b = 1.0
    out[0] = b
    for k in range(1, n + 1):
        b = a * b / (k + a * b)
        out[k] = b
    return out


def survivor_pmf(slots: np.ndarray, e: np.ndarray, size: int | None = None) -> np.ndarray:
    """Exact pmf of ``C = Σ_j X_j m_j`` with independent ``X_j ~ Bernoulli(e_j)``, by convolution over integer
    slots (proposal §3). ``size`` pads the support (default: total slots + 1)."""
    m = np.asarray(slots, dtype=np.int64)
    n = int(m.sum()) + 1 if size is None else size
    p = np.zeros(n)
    p[0] = 1.0
    for mj, ej in zip(m.tolist(), np.asarray(e, dtype=float).tolist(), strict=True):
        p = add_holder(p, mj, ej)
    return p


def add_holder(p: np.ndarray, m: int, e: float) -> np.ndarray:
    """pmf after adding one holder of ``m`` slots that survives with probability ``e``."""
    out = (1.0 - e) * p
    if m < len(p):
        out[m:] += e * p[: len(p) - m]
    return out


def expected_blocking(slots: np.ndarray, e: np.ndarray, a: float) -> float:
    """``E[B(C_t(S), a_t)]`` for a holder set with the given slots and survival probabilities."""
    p = survivor_pmf(slots, e)
    return float(p @ erlang_b_curve(len(p) - 1, a))


def utility(slots: np.ndarray, e: np.ndarray, a: float, lam: float, delta: float) -> float:
    """``U_t(S) = λ_t Δ_t E[1 − B(C_t(S), a_t)]`` (proposal §3, claim A1): monotone and submodular in ``S``."""
    return lam * delta * (1.0 - expected_blocking(slots, e, a))


def worst_case_utility(slots: np.ndarray, e: np.ndarray, a: float, lam: float, delta: float, f: int) -> float:
    """Robustness certificate ``min_{|R| ≤ f} U_t(S ∖ R)`` by enumeration (round-4 review §2.1 A4): the utility left
    after the adversary removes the ``f`` most damaging holders. Exact, ``C(|S|, f)`` evaluations."""
    n = len(slots)
    f = min(f, n)
    best = float("inf")
    for removed in itertools.combinations(range(n), f):
        keep = np.ones(n, bool)
        keep[list(removed)] = False
        best = min(best, utility(np.asarray(slots)[keep], np.asarray(e)[keep], a, lam, delta))
    return best
