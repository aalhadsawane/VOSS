"""Keys remembered for a bounded time after an invocation ends (docs/REVISION_PLAN.md V9.5, run sizing).

The router keeps each finished invocation's context and the scheduler each finished invocation's id, so that the
result of a slower attempt is recognised as a duplicate. Kept forever, both grow with every invocation of the run
(about 10 M in a 28-hour run at 1,000 workers). An entry is forgotten ``keep_s`` after it was added; a result that
arrives later still is ignored as unknown, like any result of an invocation this node never saw.
"""

from __future__ import annotations

from collections import deque
from collections.abc import Callable
from typing import Generic, TypeVar

K = TypeVar("K")
V = TypeVar("V")


class ExpiringDict(Generic[K, V]):
    """``dict`` whose entries are dropped ``keep_s`` after insertion (``now`` gives the simulated time)."""

    def __init__(self, keep_s: float, now: Callable[[], float]) -> None:
        self.keep_s, self._now = keep_s, now
        self._d: dict[K, V] = {}
        self._order: deque[tuple[float, K]] = deque()

    def _prune(self) -> None:
        cut = self._now() - self.keep_s
        while self._order and self._order[0][0] < cut:
            _, k = self._order.popleft()
            self._d.pop(k, None)

    def __setitem__(self, k: K, v: V) -> None:
        self._prune()
        if k not in self._d:
            self._order.append((self._now(), k))
        self._d[k] = v

    def get(self, k: K) -> V | None:
        return self._d.get(k)

    def __getitem__(self, k: K) -> V:
        return self._d[k]

    def __contains__(self, k: object) -> bool:
        return k in self._d

    def __len__(self) -> int:
        return len(self._d)


class ExpiringSet(Generic[K]):
    """``set`` of keys dropped ``keep_s`` after they were added."""

    def __init__(self, keep_s: float, now: Callable[[], float]) -> None:
        self._d: ExpiringDict[K, None] = ExpiringDict(keep_s, now)

    def add(self, k: K) -> None:
        self._d[k] = None

    def __contains__(self, k: object) -> bool:
        return k in self._d

    def __len__(self) -> int:
        return len(self._d)
