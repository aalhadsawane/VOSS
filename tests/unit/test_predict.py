"""Prediction models (doc 03 §6): execution time, survival, omission, arrivals."""

from __future__ import annotations

import math

import numpy as np
import pytest
from voss.core.rng import stream
from voss.policy.omission import BetaCusum
from voss.policy.predict.arrivals import TwoScaleForecaster, poisson_quantile
from voss.policy.predict.base import ExecObs, FnPrior
from voss.policy.predict.conformal import Conformal
from voss.policy.predict.registry import make_predictor
from voss.policy.survival import KaplanMeierSurvival, WeibullSurvival, weibull_mle

PRIORS = {"f": FnPrior(work_ref_s=1.0, in_ref_bytes=1e4, size_exp=0.5)}


def _truth(g: np.random.Generator, in_bytes: float, speed: float, worker: int) -> float:
    # true model: 2 s at reference size, slope 0.8, worker 7 is 1.5x slower, noise sigma 0.2
    base = math.log(2.0) + 0.8 * (math.log(in_bytes) - math.log(1e4)) - math.log(speed)
    return math.exp(base + (math.log(1.5) if worker == 7 else 0.0) + 0.2 * g.standard_normal())


@pytest.mark.parametrize("name", ["blr", "ewma", "means"])
def test_predictors_learn(name: str) -> None:
    p = make_predictor(name, PRIORS)
    g = stream(1, "pred")
    errs = []
    for t in range(1500):
        w, size, speed = int(g.integers(0, 10)), float(10 ** g.uniform(3, 5)), float(g.uniform(0.5, 1.5))
        y = _truth(g, size, speed, w)
        d = p.predict("f", int(size), np.array([w]), np.array([speed]), np.array([0.2]))
        errs.append(abs(float(d.mu[0]) - math.log(y)))
        p.update(ExecObs("f", w, int(size), speed, 0.2, y, float(t)))
    early, late = np.mean(errs[:100]), np.mean(errs[-300:])
    assert late < early
    if name == "blr":
        assert late < 0.25  # learns slope and the slow worker's offset


def test_blr_worker_offset() -> None:
    p = make_predictor("blr", PRIORS)
    g = stream(2, "pred")
    for t in range(2000):
        w = int(g.integers(0, 10))
        y = _truth(g, 1e4, 1.0, w)
        p.update(ExecObs("f", w, 10_000, 1.0, 0.2, y, float(t)))
    d = p.predict("f", 10_000, np.array([3, 7]), np.ones(2), np.full(2, 0.2))
    assert d.mu[1] - d.mu[0] == pytest.approx(math.log(1.5), abs=0.12)


def test_conformal_coverage() -> None:
    inner = make_predictor("means", PRIORS)
    c = Conformal(inner, coverage=0.9)
    g = stream(3, "conf")
    hits = []
    for t in range(3000):
        y = math.exp(math.log(3.0) + 0.6 * g.standard_normal())  # wider than the prior sigma
        d = c.predict("f", 10_000, np.array([0]), np.ones(1), np.zeros(1))
        lo, hi = float(d.quantile(0.05)[0]), float(d.quantile(0.95)[0])
        hits.append(lo <= y <= hi)
        c.update(ExecObs("f", 0, 10_000, 1.0, 0.0, y, float(t)))
    assert np.mean(hits[1000:]) == pytest.approx(0.9, abs=0.04)


def test_weibull_mle_with_censoring() -> None:
    g = stream(4, "weib")
    x = 3600 * g.weibull(0.7, 4000)
    c = g.exponential(12_000, 4000)  # independent censoring times
    cens = c < x
    obs = np.minimum(x, c)
    k, lam = weibull_mle(obs[~cens], obs[cens])
    assert k == pytest.approx(0.7, rel=0.08) and lam == pytest.approx(3600, rel=0.12)


def test_survival_monotone_and_drain() -> None:
    s = WeibullSurvival({"idle": (0.7, 3600.0)})
    p = s.p_alive(
        ["idle"] * 3,
        np.array([100.0, 100.0, 100.0]),
        np.array([10.0, 1000.0, 10.0]),
        np.zeros(3),
        np.array([np.inf, np.inf, 50.0]),
        now=45.0,
    )
    assert 1 >= p[0] > p[1] > 0 and p[2] == 0.0
    km = KaplanMeierSurvival(min_obs=5)
    for d in (100, 200, 300, 400, 500, 600):
        km.observe_end("idle", d, 3)
    q = km.p_alive(["idle"], np.array([150.0]), 200.0, np.zeros(1))
    assert q[0] == pytest.approx((3 + 1) / (5 + 1), rel=0.01)  # S(350)/S(150) = (4/7)/(6/7)


def test_omission_change_point() -> None:
    m = BetaCusum()
    for t in range(50):
        assert m.update(1, False, t) is None
    p_clean = float(m.p_omit(np.array([1]))[0])
    fired = [m.update(1, True, 50 + t) for t in range(10)]
    assert any(c is not None for c in fired)
    assert float(m.p_omit(np.array([1]))[0]) > p_clean


def test_forecaster() -> None:
    f = TwoScaleForecaster(bin_s=1.0)
    for t in np.arange(0, 300, 0.1):
        f.observe("t1", float(t), service_s=0.5)
    d = f.forecast(300.0)
    assert d.rate["t1"] == pytest.approx(10.0, rel=0.1)
    assert d.q["t1"] >= poisson_quantile(5.0, 0.95) - 1
    assert poisson_quantile(0.0, 0.95) == 0 and poisson_quantile(100.0, 0.5) == 100
