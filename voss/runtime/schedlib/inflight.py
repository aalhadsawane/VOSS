"""Soft in-flight bookkeeping of the scheduler (doc 07 §3: rebuilt by roll call, never durable)."""

from __future__ import annotations

from dataclasses import dataclass, field

from voss.core.ids import Addr, InvId, WorkerId
from voss.core.types import Invocation, SloClass
from voss.policy.cost.wait import JobEst


@dataclass
class Copy:
    """One dispatched attempt (first, retry or backup) of an invocation."""

    attempt: int
    worker: WorkerId
    t_dispatch: float
    backup: bool = False
    accepted: bool = False
    mu: float = 0.0
    sigma: float = 0.0
    load: float = 0.0
    probes: int = 0  # result-watchdog generation (doc 07 §4)
    q_done: float = 0.0  # predicted completion quantile from dispatch (the voss timer, plan V7.1)


@dataclass
class Inflight:
    inv: Invocation
    router: Addr
    t_enqueue: float
    copies: dict[int, Copy] = field(default_factory=dict)
    next_attempt: int = 0
    deciding: bool = False
    failures: int = 0
    t_window: float | None = None
    batch_wait: float = 0.0
    t_in: float = 0.0  # when this scheduler received the ENQUEUE (its own clock)
    want_backup: bool = False  # the next decision places a backup attempt (plan V7.1)

    @property
    def t_deadline(self) -> float:
        return self.inv.t_arrive + self.inv.deadline

    def live_on(self, w: WorkerId) -> list[Copy]:
        return [c for c in self.copies.values() if c.worker == w]


def job_estimates(inflight: dict[InvId, Inflight]) -> dict[WorkerId, list[JobEst]]:
    """What the scheduler dispatched and has not heard back about, per worker, in dispatch order (D-77)."""
    out: dict[WorkerId, list[JobEst]] = {}
    for _, rec in sorted(inflight.items()):
        for _, c in sorted(rec.copies.items()):
            out.setdefault(c.worker, []).append(JobEst(c.t_dispatch, c.mu, rec.inv.slo_class == SloClass.SYNC))
    for js in out.values():
        js.sort(key=lambda j: j.t_dispatch)
    return out
