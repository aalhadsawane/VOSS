"""Fault-tolerance protocol messages (doc 07 §2-3, doc 08 §4): progress detection, succession and leases."""

from __future__ import annotations

from dataclasses import dataclass, field

from voss.core.ids import Addr, ClusterId, InvId, WorkerId
from voss.core.messages import Message
from voss.core.types import Invocation, Outcome, WorkerState


@dataclass(frozen=True, slots=True)
class Stall(Message):
    """Router → orchestrator: repeated dispatch-watchdog fires for one cluster (doc 07 §2 cluster stall)."""

    cluster: ClusterId
    epoch: int
    count: int
    idle_s: float = float("inf")  # since this router last saw an ACCEPTED from the cluster (new dispatches)


@dataclass(frozen=True, slots=True)
class Probe(Message):
    """Scheduler → worker: the result watchdog fired for this attempt (doc 07 §4)."""

    inv: InvId
    attempt: int
    scheduler: Addr


@dataclass(frozen=True, slots=True)
class Pong(Message):
    """Worker → scheduler: ``phase`` is ``running``, ``done`` (result sent at ``done_at``) or ``unknown``. The agent
    is attested, so ``done`` while no outcome arrived is evidence of omission by the host."""

    inv: InvId
    attempt: int
    worker: WorkerId
    phase: str
    done_at: float = -1.0


@dataclass(frozen=True, slots=True)
class RunningAttempt:
    """An attempt a worker is still executing, reported at roll call so a successor can adopt it."""

    inv: Invocation
    router: Addr
    t_dispatch: float
    epoch: int


@dataclass(frozen=True, slots=True)
class Retained:
    """An outcome the worker keeps in memory so a successor can relearn what a lost scheduler saw."""

    outcome: Outcome
    fn: str
    in_bytes: int
    t: float


@dataclass(frozen=True, slots=True)
class RollCallReport(Message):
    """Worker → new scheduler (doc 07 §3 roll call): state, running attempts and retained outcomes."""

    cluster: ClusterId
    epoch: int
    worker: WorkerId
    state: WorkerState
    running: tuple[RunningAttempt, ...] = ()
    outcomes: tuple[Retained, ...] = ()


@dataclass(frozen=True)
class Checkpoint:
    """Learned state and the last plan of a cluster's scheduler (doc 08 §3 ``checkpoints``). In simulation the
    payload is a frozen copy of the objects; ``size`` is its nominal wire size."""

    cluster: int
    epoch: int
    t: float
    plan: object = None
    models: object = None
    size: int = 65536


@dataclass(frozen=True, slots=True)
class PutCheckpoint(Message):
    checkpoint: Checkpoint


@dataclass(frozen=True, slots=True)
class Lease(Message):
    """Orchestrator → scheduler: may dispatch until ``until``; a scheduler without a fresh lease self-fences."""

    cluster: ClusterId
    epoch: int
    until: float


@dataclass(frozen=True, slots=True)
class Handover(Message):
    """Orchestrator → scheduler: flush a checkpoint now; a successor is about to be appointed (doc 07 §3)."""

    cluster: ClusterId
    epoch: int


@dataclass(frozen=True, slots=True)
class Standby(Message):
    """Orchestrator → standby scheduler: keep a warm view of this cluster from its workers' heartbeats."""

    cluster: ClusterId
    epoch: int
    members: tuple[WorkerId, ...] = field(default_factory=tuple)
