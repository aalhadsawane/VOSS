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


@dataclass(frozen=True, slots=True)
class JobEst:
    """One dispatched, unfinished job: when the scheduler sent it and its predicted run time on that worker."""

    t_dispatch: float
    dur_s: float  # predicted execution mean (<= 0: unknown, replaced by ``default_s``)
    sync: bool = False


def _waits_pair(
    slots: int,
    jobs: Sequence[JobEst],
    now: float,
    default_s: float,
    unseen: int,
    overdue_frac: float,
    sync_priority: bool,
) -> tuple[float, float]:
    """``(async, sync)`` waits for an arrival at ``now`` on one worker, in one replay.

    The replay stops at ``now``: jobs still running occupy their servers, and the jobs still queued are served for
    each arrival in the priority order the model uses (synchronous jobs first when ``sync_priority``). The async
    arrival is behind every queued job; the synchronous arrival is behind the queued synchronous ones only. ``jobs``
    are dispatched before ``now`` (``JobEst`` is an in-flight job), so a job with a later dispatch time is not queued.
    """
    n = max(1, slots)
    held = min(unseen, n)
    free = [_IDLE] * (n - held) + [now + default_s] * held
    heapq.heapify(free)
    queued = max(0, unseen - held)
    items: list[tuple[float, int, float, bool]] = [
        (now, -(i + 1), default_s, False) for i in range(queued)
    ]
    items += [
        (j.t_dispatch, i, j.dur_s if j.dur_s > 0 else default_s, j.sync) for i, j in enumerate(jobs)
    ]
    if any(items[i][0] > items[i + 1][0] for i in range(len(items) - 1)):
        items.sort(key=lambda x: (x[0], x[1]))
    ready: list[tuple[int, float, int, float, bool]] = []  # (priority, t, seq, dur, sync)
    waiting: list[tuple[int, float, int, float, bool]] = []
    k, clock = 0, _IDLE
    while k < len(items) or ready:
        s = max(free[0], clock)
        if not ready:
            s = max(s, items[k][0])
        clock = s
        while k < len(items) and items[k][0] <= s:
            t, seq, dur, sync = items[k]
            heapq.heappush(ready, (0 if (sync_priority and sync) else 1, t, seq, dur, sync))
            k += 1
        if not ready and s > now and free[0] <= now:  # a server is free now and nothing is queued
            waiting = []
            break
        if s >= now:  # every job that arrived by ``now`` and has not started is queued
            waiting = [q for q in ready if q[1] <= now]
            waiting += [
                (0 if (sync_priority and sync) else 1, t, seq, dur, sync)
                for t, seq, dur, sync in items[k:]
                if t <= now
            ]
            break
        _, t, seq, dur, _sync = heapq.heappop(ready)
        end = s + dur
        if s <= now and end <= now:
            end = now + overdue_frac * dur
        heapq.heapreplace(free, end)

    def serve(queue: list[tuple[int, float, int, float, bool]]) -> float:
        f = list(free)
        heapq.heapify(f)
        for _pr, t, _seq, dur, _sync in queue:
            at = max(f[0], t)
            end = at + dur
            if at <= now and end <= now:
                end = now + overdue_frac * dur
            heapq.heapreplace(f, end)
        return max(0.0, f[0] - now)

    base = max(0.0, free[0] - now)
    if not waiting:
        return base, base
    if not sync_priority:
        fifo = serve(sorted(waiting, key=lambda x: (x[1], x[2])))
        return fifo, fifo
    asynchronous = serve(sorted(waiting, key=lambda x: (x[0], x[1], x[2])))
    synced = [q for q in waiting if q[4]]
    synchronous = serve(sorted(synced, key=lambda x: (x[1], x[2]))) if synced else base
    return asynchronous, synchronous


def expected_wait(
    slots: int,
    jobs: Sequence[JobEst],
    now: float,
    default_s: float,
    unseen: int = 0,
    arrival_sync: bool = False,
    sync_priority: bool = False,
    overdue_frac: float = 0.25,
) -> float:
    """Seconds until a slot is free for a request arriving at ``now`` (exact replay, O(n log slots)).

    ``jobs`` are replayed in dispatch order (ties keep list order) on ``slots`` servers; a job past its predicted end
    keeps holding its slot for ``overdue_frac`` of its prediction (D-122). ``unseen`` extra jobs (the worker reports
    more load than the scheduler dispatched) are assumed to need ``default_s`` more: the first ``slots`` of them hold a
    slot now, the rest queue at ``now``. With ``sync_priority`` a free slot serves waiting synchronous jobs first, so a
    synchronous arrival only waits behind running jobs and earlier synchronous ones.
    """
    asyn, sync = _waits_pair(slots, jobs, now, default_s, unseen, overdue_frac, sync_priority)
    return sync if (arrival_sync and sync_priority) else asyn


def worker_waits(
    view: ClusterView,
    jobs: Mapping[WorkerId, Sequence[JobEst]],
    now: float,
    default_s: float,
    arrival_sync: bool = False,
    sync_priority: bool = False,
    overdue_frac: float = 0.25,
) -> np.ndarray:
    """``expected_wait`` for every view worker; load not attributable to own dispatches is ``unseen``."""
    asyn, sync = worker_waits_pair(view, jobs, now, default_s, overdue_frac, sync_priority)
    return sync if (arrival_sync and sync_priority) else asyn


def worker_waits_pair(
    view: ClusterView,
    jobs: Mapping[WorkerId, Sequence[JobEst]],
    now: float,
    default_s: float,
    overdue_frac: float = 0.25,
    sync_priority: bool = True,
    needed: np.ndarray | None = None,
) -> tuple[np.ndarray, np.ndarray]:
    """``(async, sync)`` waits for every view worker (or only the ``needed`` mask), one replay per worker."""
    occ = view.busy + view.queued + view.inflight
    asyn, sync = np.zeros(len(view)), np.zeros(len(view))
    indices = range(len(view)) if needed is None else np.flatnonzero(needed)
    for i in indices:
        w = view.workers[i]
        js = jobs.get(w, ())
        if not js and occ[i] <= 0:
            continue  # idle worker: a new arrival starts at once
        unseen = max(0, int(occ[i]) - len(js))
        asyn[i], sync[i] = _waits_pair(
            int(view.slots[i]), js, now, default_s, unseen, overdue_frac, sync_priority
        )
    return asyn, sync
