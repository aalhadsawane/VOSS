"""Soft in-flight bookkeeping of the scheduler (doc 07 §3: rebuilt by roll call, never durable)."""

from __future__ import annotations

from collections.abc import Iterator, Mapping
from dataclasses import dataclass, field

from voss.core.ids import Addr, InvId, WorkerId
from voss.core.types import Invocation
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


@dataclass
class _Job:
    """One active copy in the per-worker job index."""

    est: JobEst
    inv: InvId
    attempt: int
    active: bool = True


class JobIndex(Mapping[WorkerId, list[JobEst]]):
    """Per-worker ``JobEst`` lists maintained on dispatch and removal (D-77, D-114).

    Dispatch times are nondecreasing, so a new job appends in time order; copies dispatched at the same instant are
    ordered by ``(invocation, attempt)``, matching ``job_estimates``' sorted scan. Removals mark the job inactive and
    the list is compacted when a worker is read, so a decision never scans every in-flight invocation.
    """

    def __init__(self) -> None:
        self._by_worker: dict[WorkerId, list[_Job]] = {}
        self._by_key: dict[tuple[WorkerId, int, int], _Job] = {}

    def add(self, worker: WorkerId, inv: InvId, attempt: int, est: JobEst) -> None:
        job = _Job(est, inv, attempt)
        self._by_key[(worker, int(inv), attempt)] = job
        jobs = self._by_worker.setdefault(worker, [])
        jobs.append(job)
        i = len(jobs) - 1
        while i > 0:
            prev = jobs[i - 1]
            if prev.est.t_dispatch < est.t_dispatch:
                break
            if prev.est.t_dispatch == est.t_dispatch and (int(prev.inv), prev.attempt) <= (int(inv), attempt):
                break
            jobs[i] = prev
            i -= 1
        jobs[i] = job

    def drop(self, worker: WorkerId, inv: InvId, attempt: int) -> None:
        job = self._by_key.pop((worker, int(inv), attempt), None)
        if job is not None:
            job.active = False

    def drop_all(self, inv: InvId, copies: dict[int, Copy]) -> None:
        for c in copies.values():
            self.drop(c.worker, inv, c.attempt)

    def _live(self, worker: WorkerId) -> list[JobEst]:
        jobs = self._by_worker.get(worker)
        if jobs is None:
            return []
        if any(not j.active for j in jobs):
            jobs[:] = [j for j in jobs if j.active]
            if not jobs:
                self._by_worker.pop(worker, None)
        return [j.est for j in jobs]

    def __getitem__(self, worker: WorkerId) -> list[JobEst]:
        live = self._live(worker)
        if not live:
            raise KeyError(worker)
        return live

    def get(self, worker: WorkerId, default: list[JobEst] | None = None) -> list[JobEst] | None:  # type: ignore[override]
        if worker not in self._by_worker:
            return default
        live = self._live(worker)
        return live if live else default

    def __iter__(self) -> Iterator[WorkerId]:
        return iter(self._by_worker)

    def __len__(self) -> int:
        return len(self._by_worker)

    def clear(self) -> None:
        self._by_worker.clear()
        self._by_key.clear()
