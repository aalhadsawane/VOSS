"""Scalarizers (doc 03 §5.2, D-12): turn a cost matrix into one number per (invocation, candidate).

``slo_miss`` (default) = ``w_i·pMiss + ε·E[T] + λ_exp·exposure``; sweeps use ``expected``, ``mean_spread``,
``quantile``, ``cvar`` and ``tardiness``. Infeasible entries are +inf.
"""

from __future__ import annotations

from collections.abc import Callable

import numpy as np

from voss.core.types import Invocation
from voss.policy.cost.components import CostMatrix, slo_weight
from voss.policy.cost.inputs import CostContext

Scalarizer = Callable[[CostMatrix, tuple[Invocation, ...], CostContext], np.ndarray]
FAIL_PENALTY_S = 30.0  # expectation-only scalarizers price a failure as this many seconds. TODO verify (E03 sweep)


def _mask(cm: CostMatrix, x: np.ndarray) -> np.ndarray:
    out: np.ndarray = np.where(cm.feasible, x, np.inf)
    return out


def slo_miss(cm: CostMatrix, invs: tuple[Invocation, ...], ctx: CostContext) -> np.ndarray:
    w = np.array([slo_weight(i, ctx) for i in invs])[:, None]
    x = w * cm.p_miss + ctx.eps * cm.completion.mean() + ctx.lambda_exposure * cm.components["exposure"]
    return _mask(cm, x)


def expected(cm: CostMatrix, invs: tuple[Invocation, ...], ctx: CostContext) -> np.ndarray:
    return _mask(cm, cm.completion.mean() + FAIL_PENALTY_S * cm.components["pFail"])


def mean_spread(cm: CostMatrix, invs: tuple[Invocation, ...], ctx: CostContext, k: float = 1.0) -> np.ndarray:
    c = cm.completion
    sd = np.sqrt((np.exp(c.s**2) - 1) * np.exp(2 * c.m + c.s**2))
    return _mask(cm, c.mean() + k * sd + FAIL_PENALTY_S * cm.components["pFail"])


def quantile(cm: CostMatrix, invs: tuple[Invocation, ...], ctx: CostContext, q: float = 0.95) -> np.ndarray:
    return _mask(cm, cm.completion.quantile(q) + FAIL_PENALTY_S * cm.components["pFail"])


def cvar(cm: CostMatrix, invs: tuple[Invocation, ...], ctx: CostContext, q: float = 0.95) -> np.ndarray:
    return _mask(cm, cm.completion.cvar(q) + FAIL_PENALTY_S * cm.components["pFail"])


def tardiness(cm: CostMatrix, invs: tuple[Invocation, ...], ctx: CostContext) -> np.ndarray:
    """``E[max(0, T − D)]`` approximated on a quantile grid, plus the failure penalty."""
    qs = (np.arange(16) + 0.5) / 16
    late = np.mean([np.maximum(0.0, cm.completion.quantile(float(q)) - cm.budget) for q in qs], axis=0)
    return _mask(cm, late + FAIL_PENALTY_S * cm.components["pFail"])


SCALARIZERS: dict[str, Scalarizer] = {
    "slo_miss": slo_miss,
    "expected": expected,
    "mean_spread": mean_spread,
    "quantile": quantile,
    "cvar": cvar,
    "tardiness": tardiness,
}
