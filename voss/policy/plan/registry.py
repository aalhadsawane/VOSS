"""Imports every planner so ``@register`` runs (doc 05 §4)."""

from voss.policy.plan import baselines, hetero_planner, kpa_planner, provisioned

__all__ = ["baselines", "hetero_planner", "kpa_planner", "provisioned"]
