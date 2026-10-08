"""Retry policy (doc 03 §5.4, doc 07 §4): re-place with the failed worker excluded, elapsed time counting.

Retries happen only for idempotent functions or failures that never reached execution, within an attempt budget.
Storm control: a per-cluster token bucket on retries; when it is empty the retry is delayed.
"""

from __future__ import annotations

from dataclasses import dataclass

from voss.core.registry import register
from voss.core.types import Invocation

PRE_EXEC_FAILURES = frozenset({"key_denied", "expired", "aborted", "lost", "preempted"})


@dataclass(frozen=True)
class RetryDecision:
    retry: bool
    delay_s: float = 0.0
    counts_attempt: bool = True


@register("retry", "basic")
class BasicRetry:
    def __init__(
        self, max_attempts: int = 3, backoff_s: float = 0.2, storm_rate_per_s: float = 50.0, storm_cap: float = 100.0
    ) -> None:
        self.max_attempts, self.backoff_s = max_attempts, backoff_s
        self.rate, self.cap = storm_rate_per_s, storm_cap
        self.tokens, self.last = storm_cap, 0.0

    def on_failure(self, inv: Invocation, status: str, now: float) -> RetryDecision:
        if status == "preempted":
            return RetryDecision(True, 0.0, counts_attempt=False)
        if inv.attempt + 1 >= self.max_attempts or not (inv.idempotent or status in PRE_EXEC_FAILURES):
            return RetryDecision(False)
        self.tokens = min(self.cap, self.tokens + (now - self.last) * self.rate)
        self.last = now
        if self.tokens >= 1.0:
            self.tokens -= 1.0
            return RetryDecision(True, self.backoff_s)
        return RetryDecision(True, self.backoff_s + (1.0 - self.tokens) / self.rate)
