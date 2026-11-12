"""Imports every placer module so ``@register`` runs (doc 05 §4)."""

from voss.policy.place import baselines, greedy

__all__ = ["baselines", "greedy"]
