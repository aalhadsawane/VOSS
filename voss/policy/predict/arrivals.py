"""Arrival forecaster (doc 03 §6.2): per key (tenant or function) EWMA of rates at two time scales, plus a Poisson
quantile of required concurrency ``q = Q_0.95(λ × service time)`` for the planner."""

from __future__ import annotations

import math
from dataclasses import dataclass, field

from voss.core.registry import register


@dataclass(frozen=True)
class Demand:
    """Forecast per key: rate (1/s) and required concurrent capacity quantile."""

    rate: dict[str, float] = field(default_factory=dict)
    q: dict[str, float] = field(default_factory=dict)


def poisson_quantile(mean: float, p: float) -> int:
    """Smallest k with P(Poisson(mean) ≤ k) ≥ p (normal approximation above mean 50)."""
    if mean <= 0:
        return 0
    if mean > 50:
        from statistics import NormalDist  # noqa: PLC0415

        return math.ceil(mean + NormalDist().inv_cdf(p) * math.sqrt(mean))
    k, term = 0, math.exp(-mean)
    cdf = term
    while cdf < p:
        k += 1
        term *= mean / k
        cdf += term
    return k


@register("forecaster", "ewma2")
class TwoScaleForecaster:
    """Counts arrivals in bins of ``bin_s``; short and long EWMAs; forecast = max of the two (conservative)."""

    def __init__(self, bin_s: float = 10.0, short_tau_s: float = 60.0, long_tau_s: float = 900.0, q: float = 0.95):
        self.bin_s, self.q = bin_s, q
        self.a_short = 1 - math.exp(-bin_s / short_tau_s)
        self.a_long = 1 - math.exp(-bin_s / long_tau_s)
        self.counts: dict[str, int] = {}
        self.short: dict[str, float] = {}
        self.long: dict[str, float] = {}
        self.service: dict[str, float] = {}
        self.home: dict[str, float] = {}
        self.bin_start = 0.0

    def observe(self, key: str, t: float, service_s: float | None = None) -> None:
        self._roll(t)
        self.counts[key] = self.counts.get(key, 0) + 1
        if service_s is not None:
            self.service[key] = 0.9 * self.service.get(key, service_s) + 0.1 * service_s

    def observe_service(self, key: str, service_s: float) -> None:
        self.service[key] = 0.9 * self.service.get(key, service_s) + 0.1 * service_s

    def set_home(self, rates: dict[str, float]) -> None:
        """Regional demand reported by the routers (D-32), smoothed; the forecast is the larger of the two."""
        keys = sorted(set(self.home) | set(rates))
        self.home = {k: 0.5 * self.home.get(k, 0.0) + 0.5 * rates.get(k, 0.0) for k in keys}

    def _roll(self, t: float) -> None:
        while t >= self.bin_start + self.bin_s:
            for key in sorted(set(self.short) | set(self.counts)):
                r = self.counts.get(key, 0) / self.bin_s
                self.short[key] = self.short.get(key, r) + self.a_short * (r - self.short.get(key, r))
                self.long[key] = self.long.get(key, r) + self.a_long * (r - self.long.get(key, r))
            self.counts = {}
            self.bin_start += self.bin_s

    def forecast(self, now: float) -> Demand:
        self._roll(now)
        keys = sorted(set(self.short) | set(self.home))
        rate = {k: max(self.short.get(k, 0.0), self.long.get(k, 0.0), self.home.get(k, 0.0)) for k in keys}
        q = {k: float(poisson_quantile(rate[k] * self.service.get(k, 1.0), self.q)) for k in keys}
        return Demand(rate, q)
