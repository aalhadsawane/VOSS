"""The run-time model's four cases (docs/REVISION_PLAN.md §11.3): seen pair, unseen worker of a seen class, unseen class
with a calibration prior, and a new function."""

from __future__ import annotations

import math

import numpy as np
import pytest
from voss.policy.predict.base import ExecObs, FnPrior
from voss.policy.predict.blr import BlrPredictor

PRIOR = {
    "f": FnPrior(0.1, 1024.0, 0.5, class_log_ratio={"slow": math.log(3.0)}),
    "g": FnPrior(1.0, 1024.0, 0.5),
}


def _train(p: BlrPredictor, fn: str, worker: int, cls: str, secs: float, n: int = 40) -> None:
    for i in range(n):
        p.update(ExecObs(fn, worker, 1024, 1.0, 0.0, secs, float(i), cls))


def _pred(p: BlrPredictor, fn: str, worker: int) -> tuple[float, float]:
    d = p.predict(fn, 1024, np.array([worker]), np.ones(1), np.zeros(1))
    return float(np.exp(d.mu[0])), float(d.sigma[0])


def test_unseen_class_uses_the_calibration_ratio() -> None:
    p = BlrPredictor(PRIOR, forgetting=1.0)
    p.set_classes({1: "fast", 2: "slow"})
    assert _pred(p, "f", 2)[0] == pytest.approx(3 * _pred(p, "f", 1)[0], rel=1e-6)


def test_class_effect_is_learned_and_shared_by_workers_of_that_class() -> None:
    """With one worker of a class, a class effect and that worker's own effect cannot be told apart, so the model
    splits the difference; evidence from more workers of the class moves an unseen worker toward the class value."""
    p = BlrPredictor(PRIOR, forgetting=1.0)
    p.set_classes({1: "fast", 2: "mid", 3: "mid", 4: "mid", 5: "mid"})
    _train(p, "g", 1, "fast", 1.0)
    _train(p, "g", 2, "mid", 2.0)
    one, _ = _pred(p, "g", 3)
    _train(p, "g", 4, "mid", 2.0)
    _train(p, "g", 5, "mid", 2.0)
    three, s3 = _pred(p, "g", 3)  # worker 3 never ran g
    assert 1.0 < one < three < 2.0 and three == pytest.approx(2.0, rel=0.15)
    _, s2 = _pred(p, "g", 2)
    assert s3 > s2  # the unseen worker is less certain


def test_a_seen_pair_is_tighter_than_a_new_function() -> None:
    p = BlrPredictor(PRIOR, forgetting=1.0)
    p.set_classes({1: "fast"})
    _train(p, "f", 1, "fast", 0.1)
    _, s_seen = _pred(p, "f", 1)
    t_new, s_new = _pred(p, "brand-new", 1)  # population prior: no profile, no runs
    assert s_new > 2 * s_seen and 0.1 < t_new < 1.0
