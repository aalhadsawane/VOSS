"""Accounting and reputation messages (doc 09, doc 08 §3-4): receipt rows to the DB, scheduler event reports,
scheduler-role records, the settlement job's reads, settlement feedback and reputation scores."""

from __future__ import annotations

from dataclasses import dataclass

from voss.core.ids import Addr, ClusterId, InvId, WorkerId
from voss.core.messages import Message, Receipt


@dataclass(frozen=True, slots=True)
class ReceiptRow:
    """One ``receipts`` row (doc 08 §3): a verified receipt (``ok``, or ``duplicate`` for a result of an already
    finished invocation) or an attempt that never returned (``no_result``, written at the router's give-up)."""

    inv: InvId
    attempt: int
    worker: WorkerId
    status: str  # ok | duplicate | no_result
    t_result: float
    router: str
    receipt: Receipt | None = None
    cluster: int = -1
    fn: str = ""
    tenant: str = ""
    t_arrive: float = 0.0
    deadline: float = 0.0


@dataclass(frozen=True, slots=True)
class ReportEvents(Message):
    """Scheduler → orchestrator every few seconds (doc 08 §3.2 ``REPORT_EVENTS``): planner-pinned warm state held by
    responsive workers (MB·s since the last report), omission change points and new suspicions."""

    cluster: ClusterId
    epoch: int
    pinned_mb_s: tuple[tuple[WorkerId, float], ...] = ()
    change_points: tuple[WorkerId, ...] = ()
    suspects: tuple[WorkerId, ...] = ()


@dataclass(frozen=True, slots=True)
class RoleRecord(Message):
    """Orchestrator → DB (``scheduler_roles``): who holds (``-1``: nobody) and who stands by for a cluster
    from ``t`` on."""

    cluster: ClusterId
    epoch: int
    holder: WorkerId
    standby: WorkerId | None
    t: float


@dataclass(frozen=True, slots=True)
class DbAccrual(Message):
    """Orchestrator → DB: non-receipt credit accruals, e.g. ``("cache", worker, MB·s)``."""

    rows: tuple[tuple[str, WorkerId, float], ...]


@dataclass(frozen=True, slots=True)
class SettleRead(Message):
    """Settlement job → DB: rows appended after ``cursor``."""

    cursor: int
    reply_to: Addr


@dataclass(frozen=True, slots=True)
class SettleRows(Message):
    """DB → settlement job: receipts, role records and accruals appended after the cursor (and the new cursor)."""

    cursor: int
    receipts: tuple[ReceiptRow, ...]
    roles: tuple[RoleRecord, ...]
    accruals: tuple[tuple[str, WorkerId, float], ...]
    t_read: float


@dataclass(frozen=True, slots=True)
class Settled(Message):
    """Settlement job → orchestrator: reference work of verified results per identity, on time and late (reputation
    input, doc 09 §2)."""

    rows: tuple[tuple[WorkerId, float, float], ...]


@dataclass(frozen=True, slots=True)
class ReputationScores(Message):
    """Orchestrator → scheduler: tie-break scores of its members (planner tie-breaks only, doc 09 §1)."""

    cluster: ClusterId
    epoch: int
    scores: tuple[tuple[WorkerId, float], ...]
