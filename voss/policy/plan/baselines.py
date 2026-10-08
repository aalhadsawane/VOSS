"""Planner baselines (doc 03 §7): ``none`` (reactive cold path only) and ``keepalive_ttl`` (classic per-function
keep-alive without trust planning: the worker-side TTL does all the work, the plan is empty)."""

from __future__ import annotations

from voss.core.registry import register
from voss.policy.plan.types import Plan, PlanInput


@register("planner", "none")
class NoPlanner:
    def plan(self, inp: PlanInput) -> Plan:
        return Plan.empty(inp, "none")


@register("planner", "keepalive_ttl")
class KeepaliveTtl:
    def plan(self, inp: PlanInput) -> Plan:
        return Plan.empty(inp, "keepalive_ttl")
