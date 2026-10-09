"""Typed messages between actors (doc 08 §4). One frozen dataclass per message kind.

Sizes (``SIZE``) are nominal wire sizes in bytes used by ``net.send``; payload messages carry their own size.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from voss.core.ids import Addr, ClusterId, FnId, InvId, TenantId, WorkerId
from voss.core.types import Invocation, Outcome, WorkerState


@dataclass(frozen=True, slots=True)
class Message:
    """Base class of every message sent through ``net.send``."""


# --- clients and routers -------------------------------------------------------------------------------------
@dataclass(frozen=True, slots=True)
class Invoke(Message):
    inv: Invocation


@dataclass(frozen=True, slots=True)
class Enqueue(Message):
    inv: Invocation
    router: Addr
    t_sent: float


@dataclass(frozen=True, slots=True)
class Assigned(Message):
    inv: InvId
    attempt: int
    worker: WorkerId
    epoch: int
    token: int


@dataclass(frozen=True, slots=True)
class Input(Message):
    inv: InvId
    attempt: int
    token: int
    nbytes: int


@dataclass(frozen=True, slots=True)
class Accepted(Message):
    inv: InvId
    attempt: int
    worker: WorkerId
    token: int


@dataclass(frozen=True, slots=True)
class Receipt:
    """Attested receipt (doc 04 §9), signed by the worker's session key."""

    inv: InvId
    attempt: int
    worker: WorkerId
    cert_id: str
    epoch: int
    exec_s: float
    ref_work_units: float
    output_digest: str


@dataclass(frozen=True, slots=True)
class Result(Message):
    outcome: Outcome
    receipt: Receipt
    nbytes: int


@dataclass(frozen=True, slots=True)
class Reject(Message):
    """Admission control refused the invocation (doc 03 §5.4)."""

    inv: InvId
    reason: str


@dataclass(frozen=True, slots=True)
class SchedulerAddr(Message):
    cluster: ClusterId
    epoch: int
    addr: Addr | None


# --- scheduler ⇄ workers -------------------------------------------------------------------------------------
@dataclass(frozen=True, slots=True)
class Dispatch(Message):
    inv: Invocation
    epoch: int
    token: int
    router: Addr
    cert_id: str
    t_enqueue: float
    t_dispatch: float
    scheduler: Addr
    batch_wait: float = 0.0
    sources: tuple[WorkerId, ...] = ()


@dataclass(frozen=True, slots=True)
class OutcomeMsg(Message):
    outcome: Outcome


@dataclass(frozen=True, slots=True)
class Heartbeat(Message):
    state: WorkerState


@dataclass(frozen=True, slots=True)
class EpochInstall(Message):
    cluster: ClusterId
    epoch: int
    scheduler: Addr
    cert_id: str


@dataclass(frozen=True, slots=True)
class Stale(Message):
    worker: WorkerId
    epoch: int


@dataclass(frozen=True, slots=True)
class Cancel(Message):
    inv: InvId
    attempt: int


@dataclass(frozen=True, slots=True)
class OwnerEvent(Message):
    """Exogenous owner/world action on a worker host (doc 02 §2); delivered locally, never over the network."""

    kind: str  # "start" | "drain" | "end"
    prebooted: bool = False
    deadline: float = 0.0
    graceful: bool = False
    is_fake: bool = False


# --- attestation (worker ⇄ verifier) -------------------------------------------------------------------------
@dataclass(frozen=True, slots=True)
class Attest(Message):
    worker: WorkerId
    identity: str
    session: int
    substrate: str
    known_good: bool
    reply_to: Addr


@dataclass(frozen=True, slots=True)
class SessionCert(Message):
    worker: WorkerId
    session: int
    cert_id: str
    assurance: float
    expiry: float
    ok: bool = True


@dataclass(frozen=True, slots=True)
class Requote(Message):
    worker: WorkerId
    session: int
    cert_id: str
    reply_to: Addr


@dataclass(frozen=True, slots=True)
class RevokeSession(Message):
    worker: WorkerId
    cert_id: str


# --- membership (worker/scheduler ⇄ orchestrator) ------------------------------------------------------------
@dataclass(frozen=True, slots=True)
class Join(Message):
    worker: WorkerId
    cert_id: str
    expiry: float
    assurance: float
    speed: float
    slots: int
    domain: int
    reply_to: Addr


@dataclass(frozen=True, slots=True)
class Leave(Message):
    worker: WorkerId
    cert_id: str


@dataclass(frozen=True, slots=True)
class DrainNotice(Message):
    worker: WorkerId
    deadline: float


@dataclass(frozen=True, slots=True)
class Appoint(Message):
    cluster: ClusterId
    epoch: int
    cert_id: str
    members: tuple[WorkerId, ...]


@dataclass(frozen=True, slots=True)
class Membership(Message):
    cluster: ClusterId
    epoch: int
    members: tuple[WorkerId, ...]


@dataclass(frozen=True, slots=True)
class Revoke(Message):
    cluster: ClusterId
    epoch: int


@dataclass(frozen=True, slots=True)
class KeepaliveSummary(Message):
    cluster: ClusterId
    epoch: int
    worker: WorkerId
    attested: int
    load: float


# --- tenant keys (worker ⇄ KBS) --------------------------------------------------------------------------------
@dataclass(frozen=True, slots=True)
class KeyRequest(Message):
    worker: WorkerId
    tenant: TenantId
    cert_id: str
    cert_expiry: float
    reply_to: Addr


@dataclass(frozen=True, slots=True)
class Key(Message):
    tenant: TenantId
    cert_id: str
    ok: bool


# --- artifacts (worker ⇄ registry / peers) ---------------------------------------------------------------------
@dataclass(frozen=True, slots=True)
class Fetch(Message):
    digest: str
    nbytes: int
    reply_to: Addr


@dataclass(frozen=True, slots=True)
class Chunk(Message):
    """Artifact bytes; ``nbytes < 0`` means the peer does not hold the digest (fall back to the registry)."""

    digest: str
    nbytes: int


# --- plan actions (scheduler → worker, doc 03 §4.4) --------------------------------------------------------------
@dataclass(frozen=True, slots=True)
class Prepare(Message):
    """Become trust-warm for a tenant: request its key, fetch and pin its functions' artifacts."""

    tenant: TenantId
    fns: tuple[FnId, ...]
    epoch: int
    sources: tuple[WorkerId, ...] = ()


@dataclass(frozen=True, slots=True)
class PinSnapshot(Message):
    """Create (if trust-warm) or fetch from a same-class trust-warm peer, then pin a function snapshot."""

    fn: FnId
    epoch: int
    sources: tuple[WorkerId, ...] = ()


@dataclass(frozen=True, slots=True)
class Warm(Message):
    """Keep ``n`` warm VMs of ``fn`` (boot or restore as needed); ``n = 0`` unpins."""

    fn: FnId
    n: int
    epoch: int


@dataclass(frozen=True, slots=True)
class Release(Message):
    """Unpin a tenant's state; drop its key after ``T_linger`` if nothing is in flight."""

    tenant: TenantId
    epoch: int


# --- operational DB (orchestrator tier only) -------------------------------------------------------------------
@dataclass(frozen=True, slots=True)
class DbCasEpoch(Message):
    cluster: ClusterId
    expect: int
    new: int
    holder: WorkerId
    cert_id: str
    reply_to: Addr


@dataclass(frozen=True, slots=True)
class DbCasResult(Message):
    cluster: ClusterId
    epoch: int
    holder: WorkerId
    cert_id: str
    ok: bool


@dataclass(frozen=True, slots=True)
class DbAppendReceipts(Message):
    rows: tuple[tuple[Receipt, float, str], ...] = field(default_factory=tuple)


SIZE: dict[type[Message], int] = {
    Invoke: 600,
    Enqueue: 400,
    Assigned: 120,
    Reject: 100,
    Accepted: 120,
    SchedulerAddr: 100,
    Dispatch: 500,
    OutcomeMsg: 300,
    EpochInstall: 200,
    Stale: 64,
    Cancel: 64,
    Attest: 6144,
    SessionCert: 2048,
    Requote: 4096,
    RevokeSession: 128,
    Join: 512,
    Leave: 128,
    DrainNotice: 128,
    Appoint: 2048,
    Membership: 1024,
    Revoke: 64,
    KeepaliveSummary: 512,
    KeyRequest: 2048,
    Key: 1024,
    Fetch: 200,
    Prepare: 400,
    PinSnapshot: 200,
    Warm: 120,
    Release: 100,
    DbCasEpoch: 200,
    DbCasResult: 200,
}


def size_of(msg: Message) -> int:
    """Nominal wire size: payload-carrying messages report their own size."""
    size = SIZE.get(type(msg))
    if size is not None:
        return size
    if isinstance(msg, Input | Chunk):
        return msg.nbytes
    if isinstance(msg, Result):
        return msg.nbytes + 512
    if isinstance(msg, Heartbeat):
        return 400 + 40 * len(msg.state.cache)
    if isinstance(msg, DbAppendReceipts):
        return 64 + 256 * len(msg.rows)
    return 256
