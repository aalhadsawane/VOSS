"""Scheduler-side store of the latest heartbeat per worker (doc 01 §5, doc 08 §5)."""

from __future__ import annotations

from voss.core.ids import WorkerId
from voss.core.types import WorkerState


class StateStore:
    """Latest ``WorkerState`` per worker plus the time it was received."""

    def __init__(self) -> None:
        self.states: dict[WorkerId, WorkerState] = {}
        self.received: dict[WorkerId, float] = {}
        self.version = 0

    def update(self, state: WorkerState, now: float) -> None:
        old = self.states.get(state.worker)
        if old is None or state.as_of >= old.as_of:
            self.states[state.worker] = state
            self.received[state.worker] = now
            self.version += 1

    def remove(self, w: WorkerId) -> None:
        if self.states.pop(w, None) is not None:
            self.version += 1
        self.received.pop(w, None)

    def silent_since(self, now: float, limit: float) -> list[WorkerId]:
        """Workers whose last heartbeat is older than ``limit`` (sorted)."""
        return sorted(w for w, t in self.received.items() if now - t > limit)

    def __contains__(self, w: WorkerId) -> bool:
        return w in self.states
