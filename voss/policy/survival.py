"""Session survival (doc 03 §6.3, doc 09 §1): residual life of a donation session.

``weibull`` fits one Weibull by censored maximum likelihood (completed sessions + live ages) with a 24-bin local-hour
hazard multiplier; ``km`` is the Kaplan–Meier comparison. The v1 per-tier split is deleted with the assumed tiers
(checklist 2.8/2.9). Drain notices are hints that only *shorten* predicted life (they may be fake, doc 07 §4).
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from voss.core.registry import register


@dataclass
class _Data:
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
    """One Weibull; prior shape/scale until ``min_obs`` sessions completed."""

    def __init__(self, prior: tuple[float, float] | None = None, min_obs: int = 20) -> None:
        self.params: tuple[float, float] = prior or (0.7, 7200.0)
        self.min_obs = min_obs
        self.data = _Data()
        self.hour_mult = np.ones(24)

    def observe_end(self, duration_s: float, local_hour: float) -> None:
        self.data.done.append(duration_s)
        self.data.end_hours.append(int(local_hour) % 24)

    def refit(self, live_ages: list[float]) -> None:
        if len(self.data.done) >= self.min_obs:
            self.params = weibull_mle(np.array(self.data.done), np.array(live_ages))
        hours = np.array(self.data.end_hours, dtype=int)
        if len(hours) >= 48:
            counts = np.bincount(hours, minlength=24) + 1.0
            self.hour_mult = counts / counts.mean()

    def params_arr(self, n: int) -> tuple[np.ndarray, np.ndarray]:
        k, lam = self.params
        return np.full(n, k), np.full(n, lam)

    def p_alive(
        self,
        age_s: np.ndarray,
        horizon_s: np.ndarray | float,
        local_hour: np.ndarray,
        drain_deadline: np.ndarray | None = None,
        now: float = 0.0,
    ) -> np.ndarray:
        """``S(age + h) / S(age)`` per worker, scaled by the local-hour hazard; 0 past a drain deadline."""
        k, lam = self.params_arr(len(age_s))
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
    """Kaplan–Meier product-limit estimate (comparison model); falls back to the Weibull prior."""

    def p_alive(
        self,
        age_s: np.ndarray,
        horizon_s: np.ndarray | float,
        local_hour: np.ndarray,
        drain_deadline: np.ndarray | None = None,
        now: float = 0.0,
    ) -> np.ndarray:
        base = super().p_alive(age_s, horizon_s, local_hour, drain_deadline, now)
        h = np.broadcast_to(np.asarray(horizon_s, dtype=float), age_s.shape)
        out = base.copy()
        done = np.sort(np.array(self.data.done))
        if len(done) < self.min_obs:
            return out
        n = len(done)
        for i in range(len(age_s)):
            s_now = (np.sum(done > age_s[i]) + 1) / (n + 1)
            s_end = (np.sum(done > age_s[i] + h[i]) + 1) / (n + 1)
            out[i] = 0.0 if base[i] == 0 else float(s_end / s_now)
        return out
