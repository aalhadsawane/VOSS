"""Distribution specs (doc 02 intro, doc 10 §1)."""

from __future__ import annotations

import numpy as np
import pytest
from pydantic import TypeAdapter, ValidationError
from voss.core.dist import Const, Dist, Empirical, LogNormal, Range, Weibull
from voss.core.rng import stream

ADAPTER: TypeAdapter[Dist] = TypeAdapter(Dist)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    "d",
    [
        LogNormal(median=2.0, sigma=0.5),
        Weibull(shape=0.7, scale=3.0),
        Range(low=0.2, high=8.0, at=0.3, sigma=0.2),
        Empirical(quantiles=(1.0, 2.0, 4.0, 9.0)),
        Const(value=1.5),
    ],
)
def test_sample_mean_and_quantile(d: Dist) -> None:
    x = np.asarray(d.sample(stream(1, "dist"), 200_000))
    assert float(x.mean()) == pytest.approx(d.mean(), rel=0.03)
    assert float(np.quantile(x, 0.9)) == pytest.approx(d.quantile(0.9), rel=0.05)


def test_discriminated_parsing() -> None:
    d = ADAPTER.validate_python({"dist": "range", "low": 1, "high": 4, "at": 0.5, "tag": "literature"})
    assert isinstance(d, Range) and d.point() == pytest.approx(2.0)
    with pytest.raises(ValidationError):
        ADAPTER.validate_python({"dist": "range", "low": 4, "high": 1})
    with pytest.raises(ValidationError):
        ADAPTER.validate_python({"dist": "lognormal", "median": 1, "sigma": 1, "tag": "guess"})
