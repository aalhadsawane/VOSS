"""Erlang loss-model planners (planner-v2 proposal §2-5, round-4 review): ``erlang_greedy`` (Stage A keys + Stage B
warm state) and ``erlang_dpp`` (exposure priced by a virtual queue).

Guarantees: only Stage A's per-tenant subproblem under a cardinality limit has a (1 − 1/e) bound; the joint plan has
none (see ``erlang_keys``). The virtual queue gives the sample-path bound ``(1/K)Σ_k E_t(k) ≤ E_t^max + Q_t(K)/K``
and nothing more (no O(1/V) optimality claim: holdings persist across rounds)."""

from __future__ import annotations

import numpy as np

from voss.core.registry import register
from voss.policy.plan.erlang_keys import allocate_keys
from voss.policy.plan.erlang_warm import warm_state
from voss.policy.plan.objective import finish
from voss.policy.plan.types import Plan, PlanInput


def _solve(inp: PlanInput, prices: np.ndarray, name: str) -> Plan:
    t, f, j = inp.shape
    y, c = np.zeros((t, j), bool), np.zeros((t, j))
    s, w = np.zeros((f, j), bool), np.zeros((f, j), int)
    if t and j:
        allocate_keys(inp, y, c, prices)
        warm_state(inp, y, s, w)
    return finish(inp, y, s, w, c, name)


def planned_exposure(inp: PlanInput, y: np.ndarray) -> np.ndarray:
    """``[T]`` ``E_t = Σ_j y_tj (1 − a_j)`` of a plan."""
    out: np.ndarray = (y * (1.0 - inp.assurance[None, :])).sum(axis=1)
    return out


@register("planner", "erlang_greedy")
class ErlangGreedy:
    def plan(self, inp: PlanInput) -> Plan:
        return _solve(inp, inp.params.exposure_weight * inp.sigma, "erlang_greedy")


@register("planner", "erlang_dpp")
class ErlangDpp:
    """Exposure price of tenant ``t`` is ``exposure_weight·Q_t`` with ``Q_t(0) = σ_t`` (a short run has few
    rounds) and ``Q_t ← max(Q_t + E_t − E_t^max, 0)`` once per planning round (V = 1). ``E_t`` is the measured
    exposure (``PlanInput.measured_exposure``: keys held, including those released on demand) when the scheduler
    supplies it, else the exposure of the previous plan. ``on_reused`` runs the same update on rounds where the
    scheduler reuses the previous plan, so the queue advances every round. State is per planner instance."""

    every_round = True

    def __init__(self) -> None:
        self.q: dict[str, float] = {}
        self.last_e: dict[str, float] = {}
        self.rounds = 0

    def _update(self, inp: PlanInput) -> None:
        li = inp.loss_inputs()
        meas = inp.measured_exposure
        for i, t in enumerate(inp.tenants):
            key = str(t)
            e = float(meas[i]) if meas is not None else self.last_e.get(key, 0.0)
            q = self.q.get(key, float(inp.sigma[i]))
            self.q[key] = max(q + e - float(li.budget_t[i]), 0.0) if self.rounds else q
        self.rounds += 1

    def on_reused(self, inp: PlanInput) -> None:
        """Called by the scheduler when the previous plan is reused: the queue still advances."""
        self._update(inp)

    def plan(self, inp: PlanInput) -> Plan:
        self._update(inp)
        prices = np.array([inp.params.exposure_weight * self.q[str(t)] for t in inp.tenants])
        plan = _solve(inp, prices, "erlang_dpp")
        for i, e in enumerate(planned_exposure(inp, plan.y)):
            self.last_e[str(inp.tenants[i])] = float(e)
        return plan
