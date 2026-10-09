"""Core value types shared by world, observe, policy and runtime (doc 05 §3).

Views live here so that ``policy`` never needs ``observe`` or ``world`` (doc 05 §2).
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import IntEnum

import numpy as np

from voss.core.ids import ClusterId, FnId, InvId, TenantId, WorkerId


class SloClass(IntEnum):
    SYNC = 0
    ASYNC = 1
    FILLER = 2


@dataclass(frozen=True, slots=True)
class Invocation:
    """One invocation attempt's metadata (doc 05 §3). Payloads never travel with it."""

    id: InvId
    fn: FnId
    tenant: TenantId
    origin: int
    t_arrive: float
    in_bytes: int
    slo_class: SloClass
    deadline: float
    attempt: int = 0
    idempotent: bool = True
    excluded: frozenset[WorkerId] = frozenset()


@dataclass(frozen=True, slots=True)
class CacheEntry:
    """Cache inventory entry for one function on one worker (doc 08 §5)."""

    level: str
    tier: str
    warm_vms: int = 0


@dataclass(frozen=True, slots=True)
class WorkerStatic:
    """Declared at ``JOIN`` (doc 08 §5): location, tier, substrate, envelope speeds, session start."""

    lat: float
    lon: float
    tz: float
    tier: str
    substrate: str
    down_bps: float
    up_bps: float
    ssd_read_MBps: float
    hdd_read_MBps: float
    session_start: float
    mem_mb: float = 0.0
    ssd_mb: float = 0.0
    snapshot_class: str = ""


@dataclass(frozen=True, slots=True)
class WorkerState:
    """Heartbeat content (doc 08 §5); static fields come from ``JOIN``."""

    worker: WorkerId
    slots: int
    busy: int
    queued: int
    mem_free_mb: float
    ssd_free_mb: float
    hdd_free_mb: float
    cache: Mapping[FnId, CacheEntry]
    trust: frozenset[TenantId]
    session_expiry: float
    drain_deadline: float | None
    assurance: float
    speed: float
    domain: int
    as_of: float
    cert_id: str = ""
    static: WorkerStatic | None = None
    pinned: frozenset[str] = frozenset()  # tenants whose PREPARE completed (confirmed plan state)


@dataclass(frozen=True)
class ClusterView:
    """Immutable, stale snapshot of a cluster for policies (doc 01 §5). Struct-of-arrays over ``workers``."""

    as_of: float
    workers: tuple[WorkerId, ...]
    slots: np.ndarray
    busy: np.ndarray
    queued: np.ndarray
    mem_free_mb: np.ndarray
    speed: np.ndarray
    assurance: np.ndarray
    domain: np.ndarray
    session_expiry: np.ndarray
    age: np.ndarray
    draining: np.ndarray
    cache: tuple[Mapping[FnId, CacheEntry], ...]
    trust: tuple[frozenset[TenantId], ...]
    inflight: np.ndarray = field(default_factory=lambda: np.zeros(0))
    static: tuple[WorkerStatic | None, ...] = ()
    drain_deadline: tuple[float | None, ...] = ()
    pinned: tuple[frozenset[str], ...] = ()

    def __len__(self) -> int:
        return len(self.workers)

    def index(self) -> dict[WorkerId, int]:
        return {w: i for i, w in enumerate(self.workers)}


@dataclass(frozen=True, slots=True)
class ClusterSummary:
    """What a scheduler tells the orchestrator tier (doc 05 §3, doc 08 §4 ``KEEPALIVE+SUMMARY``)."""

    cluster: ClusterId
    as_of: float
    load: float
    slo_health: float
    attested: int
    free_slots: int
    trust_warm_capacity: Mapping[TenantId, float] = field(default_factory=dict)
    robust_slack: float = 0.0
    diversity: int = 0


@dataclass(frozen=True, slots=True)
class ClusterCard:
    """What routers know about one cluster (doc 03 §3): pushed by the orchestrator from scheduler summaries."""

    cluster: int
    lat: float
    lon: float
    load: float
    free_slots: int
    slo_miss: float
    overhead_s: float  # measured completion − execution (routing, decision, network, wait, trust, startup)
    trust_warm: Mapping[str, float] = field(default_factory=dict)
    warm_fns: Mapping[str, int] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class Placement:
    """Placer output (doc 05 §3)."""

    assign: Mapping[InvId, WorkerId]
    hedges: Mapping[InvId, WorkerId] = field(default_factory=dict)
    status: str = "ok"
    solve_s: float = 0.0


@dataclass(frozen=True, slots=True)
class Timings:
    """Per-attempt timestamps and worker-side latency components (doc 06 §2).

    ``t_enqueue``: when the router (or a scheduler retry) enqueued this attempt; ``t_dispatch``: scheduler sent
    ``DISPATCH``; ``t_received``: worker got it; ``t_sent``: worker sent ``RESULT``.
    """

    t_enqueue: float = 0.0
    batch_wait: float = 0.0
    t_dispatch: float = 0.0
    t_received: float = 0.0
    t_sent: float = 0.0
    wait: float = 0.0
    trust: float = 0.0
    startup: float = 0.0
    input_wait: float = 0.0
    exec: float = 0.0


@dataclass(frozen=True, slots=True)
class Outcome:
    """Result of one attempt as reported by a worker (doc 05 §3)."""

    inv: InvId
    attempt: int
    worker: WorkerId
    status: str
    timings: Timings
    start_level: str
    trust_cold: bool
    tier: str = ""
    ref_work_units: float = 0.0
