"""Imports every placer module so ``@register`` runs (doc 05 §4)."""

from voss.policy.place import baselines, flow, greedy

__all__ = ["baselines", "flow", "greedy"]
