"""Planner-input ablations (round-4 plan §2b, E25). ``survival_blind`` removes the survival information any planner
sees: every worker gets the planning-pool mean of ``S_j(H)`` and of the residence ``E[min(L_j, T)]``. Reliability
differences between workers (``p_omit``, assurance) are untouched: only the *session-length* signal is lost."""

from __future__ import annotations

from dataclasses import replace

import numpy as np

from voss.policy.plan.types import PlanInput


def survival_blind(inp: PlanInput) -> PlanInput:
    """Copy of ``inp`` with survival and residence replaced by their cluster means."""
    if not len(inp.workers):
        return inp
    surv = np.full(len(inp.workers), float(inp.survival.mean()))
    res = None if inp.residence is None else np.full(len(inp.workers), float(inp.residence.mean()))
    return replace(inp, survival=surv, residence=res)
