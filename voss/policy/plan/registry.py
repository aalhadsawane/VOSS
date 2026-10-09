"""Imports every planner so ``@register`` runs (doc 05 §4)."""

from voss.policy.plan import baselines, greedy, milp

__all__ = ["baselines", "greedy", "milp"]
