"""Inputs of heterogeneity- and reliability-aware provisioning (docs/REVISION_PLAN.md §11.3-11.5), built from the
scheduler's view and estimators only (information boundary, D-05).

- ``et[f, j]``: mean of the run-time predictor's log-normal for ``f`` at its reference input on worker ``j``.
- ``pi[f, j]``: probability that the run time plus warm dispatch fits the function's deadline on ``j``.
- ``alive[m, j]``: sampled failure scenarios: ``j`` stays for the horizon (session survival) and does not drop work
  (drop estimate), and its failure domain is not hit by a shock.
"""

from __future__ import annotations

import math

import numpy as np

from voss.core.rng import stream
from voss.core.types import ClusterView
from voss.policy.cost.inputs import CostContext
from voss.policy.plan.hetero import HeteroInput, scenarios
from voss.policy.plan.types import PlanInput
from voss.runtime.schedlib.models import SchedModels

SQRT2 = math.sqrt(2.0)


def _phi(z: np.ndarray) -> np.ndarray:
    out: np.ndarray = 0.5 * (1.0 + np.vectorize(math.erf)(z / SQRT2))
    return out


def hetero_inputs(
    inp: PlanInput,
    view: ClusterView,
    ctx: CostContext,
    models: SchedModels,
    m: int,
    shock_p: float,
    ablate: tuple[str, ...] = (),
) -> HeteroInput:
    """Everything ``policy.plan.hetero.provision`` needs, for the functions and workers of ``inp``. ``ablate`` removes
    one first-class element for the ablations of plan §11.7: ``homogeneous`` (pool-mean run time and deadline
    probability for every worker), ``binary`` (deadline probability rounded to 0 or 1, as a feasibility filter),
    ``reliability_blind`` (every worker stays and never drops work)."""
    idx = view.index()
    cols = np.array([idx[w] for w in inp.workers], dtype=np.int64)
    speed = view.speed[cols] if len(cols) else np.zeros(0)
    n_f, n_j = len(inp.fns), len(inp.workers)
    et, pi = np.zeros((n_f, n_j)), np.zeros((n_f, n_j))
    dispatch = next(iter(ctx.startup.values())).dispatch_s
    models.sync_classes(view)
    for a, f in enumerate(inp.fns):
        info = ctx.fns[f]
        d = models.predictor.predict(f, int(info.in_ref_bytes), np.asarray(inp.workers), speed, np.zeros(n_j))
        et[a] = np.exp(d.mu + 0.5 * d.sigma**2)
        room = max(info.deadline_s - dispatch, 1e-9)
        pi[a] = _phi((math.log(room) - d.mu) / np.maximum(d.sigma, 1e-9))
    if "homogeneous" in ablate and n_j:
        et, pi = np.repeat(et.mean(axis=1, keepdims=True), n_j, 1), np.repeat(pi.mean(axis=1, keepdims=True), n_j, 1)
    if "binary" in ablate:
        pi = (pi >= 0.5).astype(float)
    reliability = inp.survival * (1.0 - inp.p_omit)
    if "reliability_blind" in ablate:
        reliability, shock_p = np.ones(n_j), 0.0
    gen = stream(0, "plan.scenarios", round(inp.now * 1000))
    dom = np.asarray(inp.domain, dtype=np.int64)
    alive = scenarios(reliability, dom, np.full(int(dom.max()) + 1 if n_j else 0, shock_p), m, gen)
    t_ref = np.array([ctx.fns[f].work_ref_s for f in inp.fns])
    allowed = inp.allowed()[inp.fn_tenant] if n_f else np.zeros((0, n_j), bool)
    prev = inp.y_prev[inp.fn_tenant] if n_f else np.zeros((0, n_j), bool)
    lam = inp.rate[inp.fn_tenant] if n_f else np.zeros(0)
    budget = inp.max_holders if inp.max_holders is not None else np.zeros(len(inp.tenants), np.int64)
    return HeteroInput(lam, t_ref, et, pi, alive, inp.cap.astype(np.int64), budget[inp.fn_tenant], allowed, prev)
