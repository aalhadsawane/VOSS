"""Baseline placers (doc 03 §5.3). Importing this package registers every baseline placer."""

from voss.policy.place.baselines import aware, least_loaded, random

__all__ = ["aware", "least_loaded", "random"]
