"""Fault-tolerance protocol messages (doc 07 §2-3, doc 08 §4): progress detection, succession and leases."""

from __future__ import annotations

from dataclasses import dataclass

from voss.core.ids import Addr, InvId, WorkerId
from voss.core.messages import Message


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
