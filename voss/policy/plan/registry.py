"""Imports every planner so ``@register`` runs (doc 05 §4)."""

from voss.policy.plan import baselines, erlang, greedy, milp

__all__ = ["baselines", "erlang", "greedy", "milp"]
