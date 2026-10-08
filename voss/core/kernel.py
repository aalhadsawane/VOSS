"""Discrete-event kernel (doc 01 §2).

Callbacks, not coroutines. Ties at equal time are broken by insertion sequence, so a run is a pure function of the
order in which events were scheduled.
"""

from __future__ import annotations

import heapq
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any


@dataclass(slots=True)
class Handle:
    """A scheduled callback; the heap orders entries by ``(t, seq)``."""

    t: float
    seq: int
    fn: Callable[..., Any]
    args: tuple[Any, ...] = ()
    cancelled: bool = False


class Kernel:
    """Single-threaded event loop over virtual time in seconds (doc 01 §2)."""

    def __init__(self) -> None:
        self.now: float = 0.0
        self._queue: list[tuple[float, int, Handle]] = []
        self._seq: int = 0
        self.events_run: int = 0

    def at(self, t: float, fn: Callable[..., Any], *args: Any) -> Handle:
        """Schedule ``fn(*args)`` at absolute time ``t`` (never in the past)."""
        if t < self.now:
            raise ValueError(f"cannot schedule at {t} < now {self.now}")
        h = Handle(float(t), self._seq, fn, args)
        self._seq += 1
        heapq.heappush(self._queue, (h.t, h.seq, h))
        return h

    def after(self, dt: float, fn: Callable[..., Any], *args: Any) -> Handle:
        """Schedule ``fn(*args)`` after a non-negative delay ``dt``."""
        if dt < 0:
            raise ValueError(f"negative delay {dt}")
        return self.at(self.now + dt, fn, *args)

    def cancel(self, h: Handle) -> None:
        """Cancel a pending handle (lazy deletion)."""
        h.cancelled = True

    def pending(self) -> int:
        """Number of live (not cancelled) scheduled events."""
        return sum(1 for _, _, h in self._queue if not h.cancelled)

    def run(self, until: float) -> None:
        """Run events with ``t <= until``; afterwards ``now == until``."""
        q = self._queue
        pop = heapq.heappop
        while q and q[0][0] <= until:
            h = pop(q)[2]
            if h.cancelled:
                continue
            self.now = h.t
            self.events_run += 1
            h.fn(*h.args)
        self.now = max(self.now, until)
