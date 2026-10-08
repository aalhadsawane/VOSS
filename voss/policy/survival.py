"""Session survival (doc 03 §6.3, doc 09 §1): residual life of a donation session.

``weibull`` fits a Weibull per tier by censored maximum likelihood (completed sessions + live ages) with a 24-bin
local-hour hazard multiplier; ``km`` is the Kaplan–Meier comparison. Drain notices are hints that only *shorten*
predicted life (they may be fake, doc 07 §4).
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from voss.core.registry import register


@dataclass
class _TierData:
    done: list[float] = field(default_factory=list)
    end_hours: list[int] = field(default_factory=list)


def weibull_mle(done: np.ndarray, censored: np.ndarray, k0: float = 0.7) -> tuple[float, float]:
    """Censored Weibull MLE ``(shape, scale)`` by Newton iterations on the profile likelihood of the shape."""
    x = np.concatenate([done, censored])
    x = np.maximum(x, 1.0)
    r = len(done)
    if r == 0:
        return k0, float(np.mean(x) * 3 if len(x) else 3600.0)
    lx, ld = np.log(x), np.log(np.maximum(done, 1.0))
    k = k0
    for _ in range(30):
        xk = x**k
        s0, s1, s2 = xk.sum(), (xk * lx).sum(), (xk * lx * lx).sum()
        g = r / k + ld.sum() - r * s1 / s0
        h = -r / k**2 - r * (s2 / s0 - (s1 / s0) ** 2)
        k_new = min(5.0, max(0.1, k - g / h))
        if abs(k_new - k) < 1e-6:
            k = k_new
            break
        k = k_new
    scale = float((np.sum(x**k) / r) ** (1 / k))
    return float(k), scale


@register("survival", "weibull")
class WeibullSurvival:
    """Per-tier Weibull; prior shape/scale until ``min_obs`` sessions completed."""

    def __init__(self, prior: dict[str, tuple[float, float]] | None = None, min_obs: int = 20) -> None:
        self.prior = prior or {}
        self.min_obs = min_obs
        self.data: dict[str, _TierData] = {}
        self.params: dict[str, tuple[float, float]] = dict(self.prior)
        self.hour_mult = np.ones(24)

    def observe_end(self, tier: str, duration_s: float, local_hour: float) -> None:
        d = self.data.setdefault(tier, _TierData())
        d.done.append(duration_s)
        d.end_hours.append(int(local_hour) % 24)

    def refit(self, live_ages: dict[str, list[float]]) -> None:
        for tier in sorted(set(self.data) | set(live_ages)):
            d = self.data.get(tier, _TierData())
            if len(d.done) >= self.min_obs:
                self.params[tier] = weibull_mle(np.array(d.done), np.array(live_ages.get(tier, [])))
        hours = np.array([h for d in self.data.values() for h in d.end_hours], dtype=int)
        if len(hours) >= 48:
            counts = np.bincount(hours, minlength=24) + 1.0
            self.hour_mult = counts / counts.mean()

    def tier_params(self, tiers: list[str]) -> tuple[np.ndarray, np.ndarray]:
        kl = [self.params.get(t, (0.7, 7200.0)) for t in tiers]
        return np.array([x[0] for x in kl]), np.array([x[1] for x in kl])

    def p_alive(
        self,
        tiers: list[str],
        age_s: np.ndarray,
        horizon_s: np.ndarray | float,
        local_hour: np.ndarray,
        drain_deadline: np.ndarray | None = None,
        now: float = 0.0,
    ) -> np.ndarray:
        """``S(age + h) / S(age)`` per worker, scaled by the local-hour hazard; 0 past a drain deadline."""
        k, lam = self.tier_params(tiers)
        return self.p_alive_arr(k, lam, age_s, horizon_s, local_hour, drain_deadline, now)

    def p_alive_arr(
        self,
        k: np.ndarray,
        lam: np.ndarray,
        age_s: np.ndarray,
        horizon_s: np.ndarray | float,
        local_hour: np.ndarray,
        drain_deadline: np.ndarray | None = None,
        now: float = 0.0,
    ) -> np.ndarray:
        a = np.maximum(age_s, 0.0)
        h = np.broadcast_to(np.asarray(horizon_s, dtype=float), a.shape)
        dh = ((a + h) / lam) ** k - (a / lam) ** k
        out: np.ndarray = np.exp(-dh * self.hour_mult[local_hour.astype(int) % 24])
        if drain_deadline is not None:
            out = np.where(np.isfinite(drain_deadline) & (now + h > drain_deadline), 0.0, out)
        return out


@register("survival", "km")
class KaplanMeierSurvival(WeibullSurvival):
    """Kaplan–Meier product-limit estimate per tier (comparison model); falls back to the Weibull prior."""

    def p_alive(
        self,
        tiers: list[str],
        age_s: np.ndarray,
        horizon_s: np.ndarray | float,
        local_hour: np.ndarray,
        drain_deadline: np.ndarray | None = None,
        now: float = 0.0,
    ) -> np.ndarray:
        base = super().p_alive(tiers, age_s, horizon_s, local_hour, drain_deadline, now)
        h = np.broadcast_to(np.asarray(horizon_s, dtype=float), age_s.shape)
        out = base.copy()
        for i, tier in enumerate(tiers):
            done = np.sort(np.array(self.data.get(tier, _TierData()).done))
            if len(done) < self.min_obs:
                continue
            n = len(done)
            s_now = (np.sum(done > age_s[i]) + 1) / (n + 1)
            s_end = (np.sum(done > age_s[i] + h[i]) + 1) / (n + 1)
            out[i] = 0.0 if base[i] == 0 else float(s_end / s_now)
        return out
