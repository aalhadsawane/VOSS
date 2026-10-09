"""Reputation per EK identity (doc 09 §2). Inputs are disjoint from survival and omission (doc 09 §1): declared-tier
commitments honored or breached, verified on-time vs late work (envelope shortfall), and the long-run omission
summary (change points, suspicions). It feeds rewards and planner tie-breaks only, never ``pFail``.

Default ``beta_decay``: Beta(α, β) decaying to a pessimistic prior with half-life ``H``; score = lower credible bound.
Newcomers in probation get at least the exploration floor ``ε`` as tie-break score. Variants: ``no_decay``,
``success_rate``, ``ewma``, ``survival_informed`` (also counts every abrupt session end: the double-counting
variant), ``eigentrust_lite`` (one rater: normalized local trust mixed with a uniform prior), ``none``.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, replace

import numpy as np
from scipy.special import betaincinv

from voss.core.registry import register


@dataclass(frozen=True)
class RepParams:
    half_life_s: float = 168 * 3600.0
    prior: tuple[float, float] = (1.0, 2.0)
    quantile: float = 0.05
    probation_s: float = 24 * 3600.0
    explore_floor: float = 0.3


@dataclass(frozen=True)
class Standing:
    alpha: float
    beta: float
    t: float  # last update
    first: float  # first seen (probation start)
    ewma: float = math.nan


def newcomer(now: float, p: RepParams) -> Standing:
    a0, b0 = p.prior
    return Standing(a0, b0, now, now, a0 / (a0 + b0))


def decayed(s: Standing, now: float, half_life_s: float, prior: tuple[float, float]) -> Standing:
    """Evidence decays toward the pessimistic prior: ``α ← α₀ + (α − α₀)·2^(−Δt/H)``."""
    if not math.isfinite(half_life_s) or now <= s.t:
        return replace(s, t=max(s.t, now))
    f = 0.5 ** ((now - s.t) / half_life_s)
    a0, b0 = prior
    return replace(s, alpha=a0 + (s.alpha - a0) * f, beta=b0 + (s.beta - b0) * f, t=now)


class BetaDecay:
    """Default rule (doc 09 §2)."""

    survival_inputs = False
    decays = True

    def update(self, s: Standing, now: float, good: float, bad: float, p: RepParams) -> Standing:
        s = decayed(s, now, p.half_life_s if self.decays else math.inf, p.prior)
        return replace(s, alpha=s.alpha + good, beta=s.beta + bad)

    def scores(self, states: dict[int, Standing], now: float, p: RepParams) -> dict[int, float]:
        ids = sorted(states)
        hl = p.half_life_s if self.decays else math.inf
        cur = [decayed(states[i], now, hl, p.prior) for i in ids]
        a = np.array([s.alpha for s in cur])
        b = np.array([s.beta for s in cur])
        lb = betaincinv(a, b, p.quantile) if ids else np.zeros(0)
        return {i: float(v) for i, v in zip(ids, lb, strict=True)}


register("reputation", "beta_decay")(BetaDecay)


@register("reputation", "no_decay")
class NoDecay(BetaDecay):
    decays = False


@register("reputation", "survival_informed")
class SurvivalInformed(BetaDecay):
    survival_inputs = True


@register("reputation", "success_rate")
class SuccessRate(BetaDecay):
    """Plain ratio of good to all evidence, no prior bound and no decay."""

    decays = False

    def scores(self, states: dict[int, Standing], now: float, p: RepParams) -> dict[int, float]:
        a0, b0 = p.prior
        out = {}
        for i, s in sorted(states.items()):
            g, b = s.alpha - a0, s.beta - b0
            out[i] = g / (g + b) if g + b > 0 else a0 / (a0 + b0)
        return out


@register("reputation", "ewma")
class Ewma(BetaDecay):
    """Exponentially weighted share of good evidence (time constant: ``tau`` units of evidence)."""

    decays = False

    def __init__(self, tau: float = 5.0) -> None:
        self.tau = tau

    def update(self, s: Standing, now: float, good: float, bad: float, p: RepParams) -> Standing:
        s = super().update(s, now, good, bad, p)
        total = good + bad
        if total <= 0:
            return s
        step = 1.0 - math.exp(-total / self.tau)
        return replace(s, ewma=s.ewma + step * (good / total - s.ewma))

    def scores(self, states: dict[int, Standing], now: float, p: RepParams) -> dict[int, float]:
        return {i: s.ewma for i, s in sorted(states.items())}


@register("reputation", "eigentrust_lite")
class EigenTrustLite(BetaDecay):
    """EigenTrust with the orchestrator as the only rater: ``t = (1−a)·c/Σc + a/N``, scaled so that the average
    identity scores 0.5 (``c`` = decayed net positive evidence)."""

    def __init__(self, pretrust: float = 0.15) -> None:
        self.a = pretrust

    def scores(self, states: dict[int, Standing], now: float, p: RepParams) -> dict[int, float]:
        ids = sorted(states)
        if not ids:
            return {}
        a0, b0 = p.prior
        cur = [decayed(states[i], now, p.half_life_s, p.prior) for i in ids]
        c = np.array([max(0.0, (s.alpha - a0) - (s.beta - b0)) for s in cur])
        n = len(ids)
        norm = c / c.sum() if c.sum() > 0 else np.full(n, 1.0 / n)
        t = (1 - self.a) * norm + self.a / n
        return {i: float(min(1.0, v * n * 0.5)) for i, v in zip(ids, t, strict=True)}


@register("reputation", "none")
class NoReputation(BetaDecay):
    """No reputation: every identity ties (score 0, no tie-break effect)."""

    def scores(self, states: dict[int, Standing], now: float, p: RepParams) -> dict[int, float]:
        return dict.fromkeys(sorted(states), 0.0)


def tie_break_scores(rule: BetaDecay, states: dict[int, Standing], now: float, p: RepParams) -> dict[int, float]:
    """Scores used by planner tie-breaks: identities in probation get at least the exploration floor ``ε``."""
    raw = rule.scores(states, now, p)
    if isinstance(rule, NoReputation):
        return raw
    return {i: max(v, p.explore_floor) if now - states[i].first < p.probation_s else v for i, v in sorted(raw.items())}
