"""The scheduler's cached stale view plus exact own in-flight counts since each worker's last heartbeat
(doc 01 §5 soft bookkeeping, doc 08 §5)."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import replace

import numpy as np

from voss.core.ids import WorkerId
from voss.core.types import ClusterView, WorkerState
from voss.observe.statestore import StateStore
from voss.observe.views import build_view


class ViewCache:
    def __init__(self, refresh_s: float) -> None:
        self.refresh_s = refresh_s
        self.store = StateStore()
        self.members_version = 0
        self._view: ClusterView | None = None
        self._key = (-1, -1)
        self._t = -1e9
        self._idx: dict[WorkerId, int] = {}
        self.recent: dict[WorkerId, list[float]] = {}
        self._counts = np.zeros(0, dtype=np.int64)

    @property
    def idx(self) -> dict[WorkerId, int]:
        """Worker → position in the current base view."""
        return self._idx

    def members_changed(self) -> None:
        self.members_version += 1

    def heard(self, state: WorkerState, now: float) -> None:
        """A heartbeat covers our dispatches up to its ``as_of``."""
        self.store.update(state, now)
        w = state.worker
        times = self.recent.get(w)
        if times is None:
            return
        times[:] = [t for t in times if t >= state.as_of]
        if not times:
            del self.recent[w]
        i = self._idx.get(w)
        if i is not None:
            self._counts[i] = len(times)

    def dispatched(self, w: WorkerId, now: float) -> None:
        self.recent.setdefault(w, []).append(now)
        i = self._idx.get(w)
        if i is not None:
            self._counts[i] += 1

    def lost(self, w: WorkerId) -> None:
        self.store.remove(w)
        self.recent.pop(w, None)

    def view(self, members: Iterable[WorkerId], now: float) -> ClusterView:
        """Rebuilt at most every ``refresh_s`` (or when membership changes)."""
        key = (self.store.version, self.members_version)
        stale = key != self._key and now - self._t >= self.refresh_s
        if self._view is None or stale or key[1] != self._key[1]:
            self._view = build_view(self.store, members, now, {})
            self._key, self._t = key, now
            self._idx = self._view.index()
            self._counts = np.zeros(len(self._view), dtype=np.int64)
            for w, times in self.recent.items():
                if w in self._idx:
                    self._counts[self._idx[w]] = len(times)
        return replace(self._view, inflight=self._counts.copy())
