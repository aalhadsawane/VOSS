"""Wall-clock kernel for the emulation testbed (doc 10 §4, P9b).

Same API as ``voss.core.kernel.Kernel`` (``now``, ``at``, ``after``, ``cancel``, ``pending``, ``run``) so actors, the
network model and the resource models run unchanged; ``now`` is real seconds since construction. Callbacks still run
one at a time on the thread that calls ``run``. Threads that wait for real work (microVM boot, snapshot, guest
execution) hand their completion back with ``post``, which wakes the loop. A callback that runs later than its
scheduled time is not an error here (the simulator forbids scheduling in the past); the lateness is recorded.
"""

from __future__ import annotations

import heapq
import threading
import time
from collections import deque
from collections.abc import Callable
from typing import Any

from voss.core.kernel import Handle


class RealtimeKernel:
    """Single-threaded event loop over wall-clock time in seconds."""

    def __init__(self) -> None:
        self._t0 = time.monotonic()
        self._queue: list[tuple[float, int, Handle]] = []
        self._seq = 0
        self._cv = threading.Condition()
        self._posted: deque[tuple[Callable[..., Any], tuple[Any, ...]]] = deque()
        self.events_run = 0
        self.max_lag_s = 0.0
        self.lag_sum_s = 0.0

    @property
    def now(self) -> float:
        return time.monotonic() - self._t0

    def at(self, t: float, fn: Callable[..., Any], *args: Any) -> Handle:
        """Schedule ``fn(*args)`` at absolute time ``t`` (a time already past runs at the next loop turn)."""
        h = Handle(float(t), self._seq, fn, args)
        self._seq += 1
        with self._cv:
            heapq.heappush(self._queue, (h.t, h.seq, h))
            self._cv.notify()
        return h

    def after(self, dt: float, fn: Callable[..., Any], *args: Any) -> Handle:
        # time moves while a caller computes ``deadline - now``: a delay a few microseconds below zero means "now"
        return self.at(self.now + max(0.0, dt), fn, *args)

    def cancel(self, h: Handle) -> None:
        h.cancelled = True

    def pending(self) -> int:
        with self._cv:
            return sum(1 for _, _, h in self._queue if not h.cancelled)

    def post(self, fn: Callable[..., Any], *args: Any) -> None:
        """Thread-safe: run ``fn(*args)`` on the loop thread as soon as possible."""
        with self._cv:
            self._posted.append((fn, args))
            self._cv.notify()

    def run(self, until: float) -> None:
        """Process events until wall-clock time ``until``; events due by then have run when it returns."""
        while True:
            fn, args, due = self._next(until)
            if fn is None:
                return
            if due is not None:
                lag = max(0.0, self.now - due)
                self.max_lag_s = max(self.max_lag_s, lag)
                self.lag_sum_s += lag
            self.events_run += 1
            fn(*args)

    def _next(self, until: float) -> tuple[Callable[..., Any] | None, tuple[Any, ...], float | None]:
        with self._cv:
            while True:
                if self._posted:
                    fn, args = self._posted.popleft()
                    return fn, args, None
                now = self.now
                while self._queue and self._queue[0][2].cancelled:
                    heapq.heappop(self._queue)
                if self._queue and self._queue[0][0] <= now:
                    h = heapq.heappop(self._queue)[2]
                    return h.fn, h.args, h.t
                if now >= until:
                    return None, (), None
                wake = until if not self._queue else min(until, self._queue[0][0])
                self._cv.wait(timeout=max(0.0, wake - now))
