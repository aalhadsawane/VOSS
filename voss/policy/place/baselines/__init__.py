"""Baseline placers (doc 03 §5.3). Importing this package registers every baseline placer."""

from voss.policy.place.baselines import aware, k8s, least_loaded, random

__all__ = ["aware", "k8s", "least_loaded", "random"]
