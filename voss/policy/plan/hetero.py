"""Heterogeneity- and reliability-aware provisioning (docs/REVISION_PLAN.md §11, D-96): the core of VOSS.

For function ``f`` and worker ``j``, one reserved concurrency unit is worth ``v_fj = (t_f / E[T_fj]) · π_fj`` reference
servers: ``t_f`` is the function's reference run time, ``E[T_fj]`` its predicted run time on ``j`` and ``π_fj`` the
probability that an invocation placed on ``j`` meets its deadline. In failure scenario ``ω`` (which workers stay for the
horizon and do not drop work, with domain-wide shocks), function ``f`` with holders ``S`` and units ``u`` has capacity
``X_f(ω) = Σ_{j ∈ S alive in ω} u_fj · v_fj`` and serves ``R_f(ω) = λ_f · (1 − B(X_f(ω), a_f))`` invocations per
second within their deadline, ``a_f = λ_f · t_f``. Provisioning maximises ``Σ_f E_ω[R_f]`` over ``M`` sampled scenarios.

- Stage A chooses holders: elements are (function, worker) pairs with one unit; at most ``K_f`` holders per function and
  at most ``c_j`` units per worker (two partition matroids). The objective is monotone submodular (concave of a modular
  sum in each scenario, averaged), so greedy is within 1/3 of the optimum, and within ``1 − 1/e`` per function when
  workers are not shared (Propositions 1-2).
- Stage B adds further units on chosen holders while workers have free units (one partition matroid).
Both stages use lazy greedy (Minoux 1978): a stale gain is an upper bound by submodularity.
- Swap rule (development log, iteration 1): the same two stages are run a second time starting from the current
  holders, and that allocation is kept unless the plain greedy's value net of preparation is larger. A new holder of
  ``f`` on ``j`` serves nothing for ``prep_fj`` seconds (key release and start-up) of the horizon ``H``, so its takes
  are charged ``gain × prep_fj / H``. Because the greedy's gains sum to its value, the kept allocation has
  ``F ≥ (1 − max prep / H) · F(greedy)``: the bounds above hold with that factor.
"""

from __future__ import annotations

import heapq
from collections.abc import Callable
from dataclasses import dataclass

import numpy as np

from voss.policy.plan.loss import Carried


@dataclass(frozen=True)
class HeteroInput:
    lam: np.ndarray  # [F] arrival rate (1/s)
    t_ref: np.ndarray  # [F] reference mean run time (s)
    et: np.ndarray  # [F, J] predicted mean run time on each worker (s)
    pi: np.ndarray  # [F, J] probability of meeting the deadline on each worker
    alive: np.ndarray  # [M, J] bool: worker stays and does not drop work in scenario m
    units: np.ndarray  # [J] free concurrency units
    budget: np.ndarray  # [F] holder budget K (0 = none)
    allowed: np.ndarray  # [F, J] bool: may hold the key (owner class, certificate valid through the horizon)
    prev: np.ndarray  # [F, J] bool: holds the key now (ties go to them: no new release)
    prep: np.ndarray | None = None  # [F, J] seconds before a new holder serves: key release and start-up (None: 0)
    horizon_s: float = 0.0  # provisioning horizon H over which the on-time rate is averaged


@dataclass(frozen=True)
class Allocation:
    holders: np.ndarray  # [F, J] bool
    units: np.ndarray  # [F, J] int reserved units
    value: float  # Σ_f E_ω[R_f]: invocations per second served within their deadline (model)


def unit_value(inp: HeteroInput) -> np.ndarray:
    """``[F, J]`` reference servers one unit on each worker is worth for each function."""
    ratio = np.divide(inp.t_ref[:, None], inp.et, out=np.zeros_like(inp.et), where=inp.et > 0)
    out: np.ndarray = ratio * inp.pi * inp.allowed
    return out


class _State:
    """Per-scenario capacity ``X[F, M]`` and the carried-traffic curves ``g_f``."""

    def __init__(self, inp: HeteroInput, v: np.ndarray) -> None:
        self.inp, self.v = inp, v
        self.alive = inp.alive.astype(float)  # [M, J]
        cap = (v * inp.units[None, :]).sum(axis=1)
        self.g = [Carried(lam * t, c) for lam, t, c in zip(inp.lam, inp.t_ref, cap, strict=True)]
        self.x = np.zeros((len(inp.lam), inp.alive.shape[0]))

    def gain(self, f: int, j: int) -> float:
        add = self.v[f, j] * self.alive[:, j]
        g = self.g[f]
        return float(self.inp.lam[f] * np.mean(g(self.x[f] + add) - g(self.x[f])))

    def take(self, f: int, j: int) -> None:
        self.x[f] += self.v[f, j] * self.alive[:, j]

    def value(self) -> float:
        return float(sum(lam * np.mean(g(x)) for lam, g, x in zip(self.inp.lam, self.g, self.x, strict=True)))


Pred = Callable[[int, int], bool]
Take = Callable[[int, int, float], bool]


def _lazy(st: _State, pairs: list[tuple[int, int]], ok: Pred, on_take: Take, eps: float) -> None:
    """Lazy greedy over ``pairs``: pop the best stale gain, refresh it, take it if it is still the best."""
    heap = [(-st.gain(f, j), -int(st.inp.prev[f, j]), f, j) for f, j in pairs]
    heapq.heapify(heap)
    while heap:
        _, tie, f, j = heapq.heappop(heap)
        if not ok(f, j):
            continue
        fresh = st.gain(f, j)
        if heap and fresh < -heap[0][0] - 1e-15:
            heapq.heappush(heap, (-fresh, tie, f, j))
            continue
        if fresh <= eps:
            return
        st.take(f, j)
        if on_take(f, j, fresh):
            heapq.heappush(heap, (-st.gain(f, j), tie, f, j))  # stage B: the same pair may take another unit


@dataclass
class _Run:
    st: _State
    hold: np.ndarray
    units: np.ndarray
    lost: float = 0.0  # on-time rate lost while new holders prepare, averaged over the horizon


def _delay(inp: HeteroInput) -> np.ndarray:
    """``[F, J]`` share of the horizon a new holder spends preparing (0 for current holders)."""
    if inp.prep is None or inp.horizon_s <= 0:
        return np.zeros(inp.et.shape)
    out: np.ndarray = np.where(inp.prev, 0.0, np.minimum(inp.prep / inp.horizon_s, 1.0))
    return out


def _greedy(inp: HeteroInput, v: np.ndarray, first: list[tuple[int, int]], eps: float) -> _Run:
    """Stages A and B (module docstring); stage A takes from ``first`` before it considers every pair."""
    n_f, n_j = inp.et.shape
    run = _Run(_State(inp, v), np.zeros((n_f, n_j), bool), np.zeros((n_f, n_j), np.int64))
    left, delay = inp.units.astype(np.int64).copy(), _delay(inp)
    pairs = [(f, j) for f in range(n_f) for j in range(n_j) if v[f, j] > 0 and inp.lam[f] > 0]

    def can_add(f: int, j: int) -> bool:
        k = int(inp.budget[f])
        return not run.hold[f, j] and left[j] > 0 and (k == 0 or int(run.hold[f].sum()) < k)

    def added(f: int, j: int, g: float) -> bool:
        run.hold[f, j], run.units[f, j], left[j] = True, 1, left[j] - 1
        run.lost += g * delay[f, j]
        return False

    for group in (first, pairs) if first else (pairs,):
        _lazy(run.st, group, can_add, added, eps)

    def can_grow(f: int, j: int) -> bool:
        return bool(run.hold[f, j]) and left[j] > 0

    def grew(f: int, j: int, g: float) -> bool:
        run.units[f, j] += 1
        left[j] -= 1
        run.lost += g * delay[f, j]
        return True

    chosen = [(f, j) for f in range(n_f) for j in range(n_j) if run.hold[f, j]]
    _lazy(run.st, chosen, can_grow, grew, eps)
    return run


def provision(inp: HeteroInput, eps: float = 1e-9) -> Allocation:
    """Two-stage lazy greedy (module docstring), then the swap rule: the same greedy started from the current holders
    is kept unless the plain greedy's on-time rate, net of what its new holders lose while they prepare
    (``Σ gain × prep / H`` over new pairs), is larger. Deterministic: ties go to current holders, then lower
    indices. Since the greedy's gains sum to its value, the result keeps ``F ≥ (1 − max prep / H) · F(greedy)``."""
    v = unit_value(inp)
    run = _greedy(inp, v, [], eps)
    kept = [(int(f), int(j)) for f, j in zip(*np.nonzero(inp.prev & (v > 0)), strict=True) if inp.lam[f] > 0]
    if kept:
        inc = _greedy(inp, v, kept, eps)
        if inc.st.value() - inc.lost >= run.st.value() - run.lost:
            run = inc
    return Allocation(run.hold, run.units, run.st.value())


def scenarios(
    reliability: np.ndarray, domain: np.ndarray, shock: np.ndarray, m: int, gen: np.random.Generator
) -> np.ndarray:
    """``[m, J]`` failure scenarios: worker ``j`` survives with probability ``reliability[j]`` independently, and every
    worker of a domain is lost together with that domain's shock probability ``shock[domain]`` (§11.5)."""
    n_j = len(reliability)
    own = gen.random((m, n_j)) < reliability[None, :]
    doms = np.unique(domain) if n_j else np.zeros(0, np.int64)
    hit = gen.random((m, len(doms))) < np.asarray([shock[d] if d < len(shock) else 0.0 for d in doms])[None, :]
    lost = hit[:, np.searchsorted(doms, domain)] if n_j else np.zeros((m, 0), bool)
    out: np.ndarray = own & ~lost
    return out
