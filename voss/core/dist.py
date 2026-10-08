"""Distribution specs used by data files (doc 02 intro, doc 10 §1).

Every number in a profile is a distribution spec with a provenance tag (``measured | literature | assumed``):

- ``{dist: const, value}``
- ``{dist: lognormal, median, sigma}``
- ``{dist: weibull, shape, scale}``
- ``{dist: range, low, high, at, sigma}``: literature ranges; ``at`` in [0, 1] picks a point on the log scale
  (swept by experiments), with optional lognormal spread ``sigma``.
- ``{dist: empirical, quantiles}``: equally spaced quantiles from a calibration bundle (linear interpolation).
"""

from __future__ import annotations

import math
from statistics import NormalDist
from typing import Annotated, Literal

import numpy as np
from pydantic import BaseModel, ConfigDict, Field, model_validator

Tag = Literal["measured", "literature", "assumed"]


class _DistBase(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    tag: Tag = "assumed"
    source: str = ""


class Const(_DistBase):
    dist: Literal["const"] = "const"
    value: float

    def sample(self, gen: np.random.Generator, n: int | None = None) -> np.ndarray | float:
        return self.value if n is None else np.full(n, self.value)

    def mean(self) -> float:
        return self.value

    def quantile(self, q: float) -> float:
        return self.value


class LogNormal(_DistBase):
    dist: Literal["lognormal"] = "lognormal"
    median: float = Field(gt=0)
    sigma: float = Field(ge=0)

    def sample(self, gen: np.random.Generator, n: int | None = None) -> np.ndarray | float:
        x = gen.lognormal(math.log(self.median), self.sigma, n)
        return float(x) if n is None else x

    def mean(self) -> float:
        return self.median * math.exp(self.sigma**2 / 2)

    def quantile(self, q: float) -> float:
        return self.median * math.exp(self.sigma * _norm_ppf(q))


class Weibull(_DistBase):
    dist: Literal["weibull"] = "weibull"
    shape: float = Field(gt=0)
    scale: float = Field(gt=0)

    def sample(self, gen: np.random.Generator, n: int | None = None) -> np.ndarray | float:
        x = self.scale * gen.weibull(self.shape, n)
        return float(x) if n is None else x

    def mean(self) -> float:
        return float(self.scale * math.gamma(1 + 1 / self.shape))

    def quantile(self, q: float) -> float:
        return float(self.scale * (-math.log(1 - q)) ** (1 / self.shape))


class Range(_DistBase):
    dist: Literal["range"] = "range"
    low: float = Field(gt=0)
    high: float = Field(gt=0)
    at: float = Field(default=0.5, ge=0, le=1)
    sigma: float = Field(default=0.0, ge=0)

    @model_validator(mode="after")
    def _ordered(self) -> Range:
        if self.low > self.high:
            raise ValueError(f"range low {self.low} > high {self.high}")
        return self

    def point(self) -> float:
        return math.exp(math.log(self.low) + self.at * (math.log(self.high) - math.log(self.low)))

    def sample(self, gen: np.random.Generator, n: int | None = None) -> np.ndarray | float:
        return LogNormal(median=self.point(), sigma=self.sigma).sample(gen, n)

    def mean(self) -> float:
        return self.point() * math.exp(self.sigma**2 / 2)

    def quantile(self, q: float) -> float:
        return self.point() * math.exp(self.sigma * _norm_ppf(q))


class Empirical(_DistBase):
    dist: Literal["empirical"] = "empirical"
    quantiles: tuple[float, ...] = Field(min_length=2)

    def sample(self, gen: np.random.Generator, n: int | None = None) -> np.ndarray | float:
        u = gen.random(n)
        x = np.interp(u, np.linspace(0, 1, len(self.quantiles)), self.quantiles)
        return float(x) if n is None else x

    def mean(self) -> float:
        return float(np.trapezoid(self.quantiles, dx=1 / (len(self.quantiles) - 1)))

    def quantile(self, q: float) -> float:
        return float(np.interp(q, np.linspace(0, 1, len(self.quantiles)), self.quantiles))


_STD_NORMAL = NormalDist()

Dist = Annotated[Const | LogNormal | Weibull | Range | Empirical, Field(discriminator="dist")]


def _norm_ppf(q: float) -> float:
    """Standard normal quantile."""
    return _STD_NORMAL.inv_cdf(q)
