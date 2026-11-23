"""Execution model (doc 02 §4; D-133): true runtime of an invocation on a worker.

``runtime = work_f(input) / (speed × interference(load)) × substrate_slowdown × noise``, drawn from the invocation's
own stream so every compared system sees the same underlying randomness (common random numbers, doc 01 §3).

Both variation terms come from the calibration bundle (D-133): co-run interference is the bundle's measured table per
function and concurrency level, and run-to-run noise is the coefficient of variation of the function's repeat samples
at concurrency 1 in ``calibration/raw`` (the source of ``experiments/analysis/machines.py``). The v1 heavy-tail
mixture, its assumed parameters and the scalar interference are deleted.
"""

from __future__ import annotations

import json
import math
from collections import defaultdict
from functools import lru_cache

import numpy as np
from pydantic import BaseModel, ConfigDict, Field

from voss.core.paths import REPO_ROOT, config_path, load_data_yaml
from voss.world.workload import FunctionSpec, warm_estimate_s


class ExecParams(BaseModel):
    """Execution variation of one machine class, from its bundle (D-133)."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    interference: dict[str, dict[int, float]] = Field(default_factory=dict)  # function -> concurrency -> multiplier
    noise_cv: dict[str, float] = Field(default_factory=dict)  # function -> coefficient of variation at concurrency 1
    timeout_s: dict[str, float] = Field(default_factory=lambda: {"sync": 30.0, "async": 300.0})


def _nearest_level(table: dict[int, float], busy: int) -> float:
    """The measured co-run multiplier nearest to ``busy`` (the table's levels are measured, not interpolated)."""
    if not table:
        return 1.0
    level = min(table, key=lambda k: (abs(k - busy), k))
    return float(table[level])


def noise_matrix(gen: np.random.Generator, base: np.ndarray, attempts: int, p: ExecParams) -> np.ndarray:
    """Noise multipliers per ``(invocation, attempt)``: lognormal with the function's measured coefficient of variation
    (``sigma^2 = ln(1 + cv^2)``). Drawn once per scenario so every compared system sees the same draws for the same
    invocation (common random numbers, doc 01 §3)."""
    sig = np.array([math.sqrt(math.log1p(p.noise_cv.get(str(name), 0.0) ** 2)) for name in base], dtype=float)
    out: np.ndarray = gen.lognormal(0.0, sig[:, None], (len(base), attempts))
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
    ``noise_matrix``; interference is the bundle's measured table for the function (D-133)."""
    table = p.interference.get(fn.base or fn.name, {})
    interference = _nearest_level(table, max(1, busy))
    return ref_work_units(fn, in_bytes) / speed * interference * cpu_slowdown * noise


@lru_cache(maxsize=16)
def repeat_cv(bundle: str) -> dict[str, float]:
    """Coefficient of variation of each function's concurrency-1 handler times in the bundle's raw records (D-133)."""
    meta = load_data_yaml(config_path(bundle) / "meta.yaml")
    host = str(meta["raw_host"])
    runs: dict[tuple[str, int], list[float]] = defaultdict(list)
    for path in sorted((REPO_ROOT / "calibration" / "raw" / host / "sebs").glob("*/records.jsonl")):
        for line in path.read_text().splitlines():
            r = json.loads(line)
            c = r.get("config", {})
            if r.get("probe") == "sebs_exec" and c.get("concurrency") == 1:
                runs[(str(c["fn"]), int(c["size_kb"]))].append(float(r["value"]))
    by_fn: dict[str, list[float]] = defaultdict(list)
    for (fn, _size), values in sorted(runs.items()):
        if len(values) >= 5 and np.mean(values) > 0:
            by_fn[fn].append(float(np.std(values, ddof=1) / np.mean(values)))
    return {fn: float(np.mean(v)) for fn, v in sorted(by_fn.items()) if v}


def load_exec(bundle: str) -> ExecParams:
    """The execution variation of one measured bundle (D-133): its interference tables and repeat variation."""
    rows = load_data_yaml(config_path(bundle) / "functions.yaml").get("functions") or {}
    interference = {
        name: {int(k): float(v) for k, v in sorted((row.get("interference") or {}).items())}
        for name, row in sorted(rows.items())
        if row.get("interference")
    }
    return ExecParams(interference=interference, noise_cv=repeat_cv(bundle))
