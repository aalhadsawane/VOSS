"""Planner baselines (doc 03 §7): ``none`` (reactive cold path only) and ``keepalive_ttl`` (classic per-function
keep-alive without trust planning: the worker-side TTL does all the work, the plan is empty)."""

from __future__ import annotations

from voss.core.registry import register
from voss.policy.keepalive_hist import HistParams, IdleTracker, Windows
from voss.policy.plan.types import Plan, PlanInput


@register("planner", "none")
class NoPlanner:
    def plan(self, inp: PlanInput) -> Plan:
        return Plan.empty(inp, "none")


@register("planner", "keepalive_ttl")
class KeepaliveTtl:
    def plan(self, inp: PlanInput) -> Plan:
        return Plan.empty(inp, "keepalive_ttl")


@register("planner", "histogram_prewarm")
class HistogramPrewarm:
    """Azure hybrid-histogram keep-alive (D-77). The trust plan is empty (single loop: no planned key releases); the
    scheduler feeds dispatches and completions to ``tracker`` and sends the resulting windows to the worker."""

    def __init__(self, params: HistParams | None = None) -> None:
        self.tracker = IdleTracker(params or HistParams())

    def plan(self, inp: PlanInput) -> Plan:
        return Plan.empty(inp, "histogram_prewarm")

    def dispatch(self, fn: str, worker: int, now: float) -> None:
        self.tracker.dispatch(fn, worker, now)

    def end(self, fn: str, worker: int, now: float, others_busy: bool) -> Windows:
        return self.tracker.end(fn, worker, now, others_busy)
