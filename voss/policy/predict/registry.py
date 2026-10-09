"""Predictor factory by name (doc 05 §4)."""

from __future__ import annotations

from typing import Any

from voss.core.registry import create
from voss.policy.predict import blr as _blr  # noqa: F401  (registers predictors)
from voss.policy.predict import ewma as _ewma  # noqa: F401
from voss.policy.predict import instant as _instant  # noqa: F401
from voss.policy.predict import means as _means  # noqa: F401
from voss.policy.predict.base import FnPrior


def make_predictor(name: str, priors: dict[str, FnPrior], forgetting: float = 0.995) -> Any:
    if name == "blr":
        return create("predictor", name, priors, forgetting=forgetting)
    return create("predictor", name, priors)
