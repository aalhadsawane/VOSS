"""Failure detectors compared in V7 (docs/REVISION_PLAN.md V7.1-V7.2): when an attempt is presumed failed, what happens
then, and when a worker is ejected. Every detector gets the same timers and the same retry mechanism (guardrail 18).

| name | timer | on expiry | ejection |
|---|---|---|---|
| ``fixed`` | the invocation's deadline | retry once elsewhere | never (heartbeat loss removes crashed workers) |
| ``consecutive`` | the invocation's deadline | retry once elsewhere | after 5 failures in a row, for 30 s |
| ``voss`` | predicted q95 completion | backup attempt on a holder in another failure domain | drop estimate + streak |
| ``hedged`` | observed q95 latency of the function | second request to the best other eligible worker | never |

``hedged`` is the hedged request of Dean and Barroso ("The Tail at Scale", CACM 2013) as published: the timer is the
function's observed 95th-percentile latency (dispatch to outcome), the second request may go to any other eligible
worker, and the slower one is cancelled. Until ``HEDGE_MIN_SAMPLES`` latencies are observed, the deadline is the timer.

The ``consecutive`` defaults are Envoy's outlier detection (``consecutive_5xx: 5``, ``base_ejection_time: 30s``).
# TODO verify against the Envoy documentation of the version cited in the paper.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

import numpy as np

from voss.core.config import DetectionConfig

HEDGE_MIN_SAMPLES = 20


@dataclass(frozen=True)
class Detector:
    name: str
    timer: str  # "q95": predicted completion quantile | "deadline": the invocation's deadline
    on_expiry: str  # "backup": start a backup, keep the first attempt | "retry": abandon it and retry
    streak: int  # failures in a row that eject a worker; 0 = never
    eject_s: float  # how long an ejection lasts
    change_point: bool  # an omission change point also ejects (drop estimate, doc 07)
    max_attempts: int  # attempts per invocation, the first included
    backup_scope: str = "holders_other_domain"  # where a backup may go: or "any" (hedged)
    probe: bool = True  # probe the silent worker on expiry (evidence for the drop estimate)

    def expiry_s(
        self, t_dispatch: float, q_completion: float, t_deadline: float, now: float, observed: Sequence[float] = ()
    ) -> float:
        """Seconds from ``now`` until the attempt is presumed failed. No floor (plan V7.1, review F5)."""
        if self.timer == "q95":
            at = t_dispatch + q_completion
        elif self.timer == "observed_q95" and len(observed) >= HEDGE_MIN_SAMPLES:
            at = t_dispatch + float(np.quantile(np.asarray(observed), 0.95))
        else:
            at = t_deadline
        return max(0.0, at - now)


def detector(name: str, dc: DetectionConfig, max_attempts: int) -> Detector:
    """The named detector with its parameters from ``voss.detection`` (doc 05 §6: chosen in config)."""
    if name == "fixed":
        return Detector("fixed", "deadline", "retry", 0, 0.0, False, 2)
    if name == "consecutive":
        return Detector("consecutive", "deadline", "retry", dc.consecutive_streak, dc.consecutive_eject_s, False, 2)
    if name == "hedged":
        return Detector("hedged", "observed_q95", "backup", 0, 0.0, False, max_attempts, "any", False)
    if name == "voss":
        return Detector("voss", "q95", "backup", dc.suspect_streak, dc.suspect_s, True, max_attempts)
    raise KeyError(f"unknown detector {name!r}")


def fits(mean_completion: float, budget: float) -> bool:
    """A retry or backup goes only to a worker whose predicted mean completion fits the remaining deadline (V7.1)."""
    return mean_completion <= budget
