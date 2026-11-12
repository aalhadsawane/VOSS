"""Baseline placers (doc 03 §5.3). Importing this package registers every baseline placer."""

from voss.policy.place.baselines import least_loaded

__all__ = ["least_loaded"]
