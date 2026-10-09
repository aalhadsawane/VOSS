"""Soft in-flight bookkeeping of the scheduler (doc 07 §3: rebuilt by roll call, never durable)."""

from __future__ import annotations

from dataclasses import dataclass, field

from voss.core.ids import Addr, WorkerId
from voss.core.types import Invocation


@dataclass
class Copy:
    """One dispatched copy (primary, retry or hedge) of an invocation."""

    attempt: int
    worker: WorkerId
    t_dispatch: float
    hedge: bool = False
    accepted: bool = False
    mu: float = 0.0
    sigma: float = 0.0
    load: float = 0.0
    probes: int = 0  # result-watchdog generation (doc 07 §4)


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

    def live_on(self, w: WorkerId) -> list[Copy]:
        return [c for c in self.copies.values() if c.worker == w]
