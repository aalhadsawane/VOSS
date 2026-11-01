"""Per-worker slot-wait estimate from predicted remaining work (doc 03 §5.2 ``wait``; C-46, D-77).

The default estimate ``(occupancy - slots + 1)^+ * svc / slots`` uses one scheduler-wide mean service time, so a
queue of long jobs looks as short as a queue of short ones. ``expected_wait`` instead replays the worker FIFO over
``slots`` servers with the *predicted* duration of every job dispatched there that has not reported back, and
returns the time until a slot frees for a new arrival. Pure function; the scheduler supplies the job records.
"""

from __future__ import annotations

import heapq
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

import numpy as np

from voss.core.ids import WorkerId
from voss.core.types import ClusterView

_IDLE = -1e12  # a server that has been idle "forever"
OVERDUE_FRAC = 0.25  # a job past its predicted end is assumed to need this fraction of its prediction more. TODO verify


@dataclass(frozen=True, slots=True)
class JobEst:
    """One dispatched, unfinished job: when the scheduler sent it and its predicted run time on that worker."""

    t_dispatch: float
    dur_s: float  # predicted execution mean (<= 0: unknown, replaced by ``default_s``)
    sync: bool = False


def expected_wait(
    slots: int,
    jobs: Sequence[JobEst],
    now: float,
    default_s: float,
    unseen: int = 0,
    arrival_sync: bool = False,
    sync_priority: bool = False,
) -> float:
    """Seconds until a slot is free for a request arriving at ``now`` (exact replay, O(n log n)).

    ``jobs`` are replayed in dispatch order (ties keep list order) on ``slots`` servers; a job past its predicted end
    keeps holding its slot for ``OVERDUE_FRAC`` of its prediction. ``unseen`` extra jobs (the worker reports more load
    than the scheduler dispatched) are assumed to need ``default_s`` more: the first ``slots`` of them hold a slot now,
    the rest queue at ``now``. With ``sync_priority`` a free slot serves waiting synchronous jobs first, so a
    synchronous arrival only waits behind running jobs and earlier synchronous ones.
    """
    n = max(1, slots)
    held = min(unseen, n)
    free = [_IDLE] * (n - held) + [now + default_s] * held
    heapq.heapify(free)
    pending = [(now, -(i + 1), JobEst(now, default_s)) for i in range(unseen - held)]
    pending += [(j.t_dispatch, i, j) for i, j in enumerate(jobs)]
    target = len(jobs)
    pending.append((now, target, JobEst(now, default_s, arrival_sync)))
    pending.sort(key=lambda p: (p[0], p[1]))
    ready: list[tuple[int, float, int, JobEst]] = []  # (priority class, arrival, seq, job)
    k, clock = 0, _IDLE
    while True:
        s = max(free[0], clock)
        if not ready:
            s = max(s, pending[k][0])
        clock = s
        while k < len(pending) and pending[k][0] <= s:
            t, seq, j = pending[k]
            heapq.heappush(ready, (0 if (sync_priority and j.sync) else 1, t, seq, j))
            k += 1
        _, _, seq, j = heapq.heappop(ready)
        heapq.heappop(free)
        if seq == target:
            return max(0.0, s - now)
        dur = j.dur_s if j.dur_s > 0 else default_s
        end = s + dur
        if s <= now and end <= now:
            end = now + OVERDUE_FRAC * dur
        heapq.heappush(free, end)


def worker_waits(
    view: ClusterView,
    jobs: Mapping[WorkerId, Sequence[JobEst]],
    now: float,
    default_s: float,
    arrival_sync: bool = False,
    sync_priority: bool = False,
) -> np.ndarray:
    """``expected_wait`` for every view worker; load not attributable to own dispatches is ``unseen``."""
    occ = view.busy + view.queued + view.inflight
    out = np.zeros(len(view))
    for i, w in enumerate(view.workers):
        js = jobs.get(w, ())
        unseen = max(0, int(occ[i]) - len(js))
        out[i] = expected_wait(int(view.slots[i]), js, now, default_s, unseen, arrival_sync, sync_priority)
    return out
