"""Receipt rows written by routers to the operational DB (doc 08 §3): the audit trail of signed results."""

from __future__ import annotations

from dataclasses import dataclass

from voss.core.ids import InvId, WorkerId
from voss.core.messages import Receipt


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
