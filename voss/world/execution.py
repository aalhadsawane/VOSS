"""Execution model (doc 02 §4): true runtime of an invocation on a worker.

``runtime = work_f(input) / (speed × interference(load)) × substrate_slowdown × noise``, drawn from the invocation's
own stream so every compared system sees the same underlying randomness (common random numbers, doc 01 §3).
"""

from __future__ import annotations

import numpy as np
from pydantic import BaseModel, ConfigDict, Field

from voss.world.workload import FunctionSpec, warm_estimate_s


class ExecParams(BaseModel):
    """tag: assumed (shape: heavy-tailed lognormal mixture; refit from P9 `sebs`)."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    noise_sigma: float = Field(default=0.1, ge=0)
    tail_p: float = Field(default=0.05, ge=0, le=1)
    tail_median: float = Field(default=2.0, ge=1)
    tail_sigma: float = Field(default=0.3, ge=0)
    interference: float = Field(default=0.1, ge=0)
    timeout_s: dict[str, float] = Field(default_factory=lambda: {"sync": 30.0, "async": 300.0, "filler": 600.0})


def noise_matrix(gen: np.random.Generator, n: int, attempts: int, p: ExecParams) -> np.ndarray:
    """Noise multipliers per ``(invocation, attempt)``: a heavy-tailed lognormal mixture. Drawn once per scenario so
    every compared system sees the same draws for the same invocation (common random numbers, doc 01 §3)."""
    tail = gen.random((n, attempts)) < p.tail_p
    body = gen.lognormal(0.0, p.noise_sigma, (n, attempts))
    slow = gen.lognormal(np.log(p.tail_median), p.tail_sigma, (n, attempts))
    out: np.ndarray = np.where(tail, slow, body)
    return out


def ref_work_units(fn: FunctionSpec, in_bytes: int) -> float:
    """Reference-core seconds (credits are paid in these, doc 09 §4)."""
    return float(warm_estimate_s(fn, np.asarray(float(in_bytes))))


def true_runtime(
    fn: FunctionSpec,
    in_bytes: int,
    speed: float,
    busy: int,
    slots: int,
    cpu_slowdown: float,
    noise: float,
    p: ExecParams,
) -> float:
    """Doc 02 §4. ``busy`` counts co-running invocations including this one; ``noise`` comes from
    ``noise_matrix``."""
    interference = 1.0 + p.interference * max(0, busy - 1) / max(1, slots)
    return ref_work_units(fn, in_bytes) / speed * interference * cpu_slowdown * noise
