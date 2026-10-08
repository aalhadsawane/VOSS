"""Baseline placers (doc 03 §5.3); all share the candidates of ``policy/place/candidates.py``.

Importing this package registers every baseline placer.
"""

from voss.policy.place.baselines import least_loaded, random

__all__ = ["least_loaded", "random"]
