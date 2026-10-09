"""Nominal wire sizes of messages (doc 08 §4) used by ``net.send``; payload messages report their own size."""

from __future__ import annotations

from voss.core.messages import (
    Accepted,
    Appoint,
    Assign,
    Assigned,
    Attest,
    Cancel,
    Chunk,
    DbAppendReceipts,
    DbCasEpoch,
    DbCasResult,
    Dispatch,
    DrainNotice,
    Enqueue,
    EpochInstall,
    Fetch,
    Heartbeat,
    HomeDemand,
    Input,
    Invoke,
    Join,
    KeepaliveSummary,
    Key,
    KeyRequest,
    Leave,
    Membership,
    Message,
    OutcomeMsg,
    PinSnapshot,
    Prepare,
    Reject,
    Release,
    Requote,
    Result,
    Revoke,
    RevokeSession,
    RouterStats,
    SchedulerAddr,
    SessionCert,
    Stale,
    Summaries,
    Warm,
    Withdraw,
)
from voss.core.messages_acct import (
    DbAccrual,
    ReportEvents,
    ReputationScores,
    RoleRecord,
    Settled,
    SettleRead,
    SettleRows,
)
from voss.core.messages_ft import Handover, Lease, Pong, Probe, PutCheckpoint, RollCallReport, Stall, Standby

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
    Withdraw: 64,
    Stall: 64,
    Probe: 64,
    Pong: 64,
    Lease: 64,
    Handover: 64,
    Attest: 6144,
    SessionCert: 2048,
    Requote: 4096,
    RevokeSession: 128,
    Join: 512,
    Assign: 64,
    RouterStats: 256,
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
    RoleRecord: 128,
    SettleRead: 64,
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
    if isinstance(msg, PutCheckpoint):
        return msg.checkpoint.size
    if isinstance(msg, RollCallReport):
        return 400 + 40 * len(msg.state.cache) + 200 * len(msg.running) + 120 * len(msg.outcomes)
    if isinstance(msg, Standby):
        return 64 + 8 * len(msg.members)
    if isinstance(msg, HomeDemand):
        return 64 + 40 * len(msg.rates)
    if isinstance(msg, Summaries):
        return 64 + 200 * len(msg.cards)
    return _acct_size(msg)


def _acct_size(msg: Message) -> int:
    if isinstance(msg, ReportEvents):
        return 64 + 16 * len(msg.pinned_mb_s) + 8 * (len(msg.change_points) + len(msg.suspects))
    if isinstance(msg, DbAccrual | Settled):
        return 64 + 24 * len(msg.rows)
    if isinstance(msg, ReputationScores):
        return 64 + 12 * len(msg.scores)
    if isinstance(msg, SettleRows):
        return 64 + 256 * len(msg.receipts) + 64 * len(msg.roles) + 24 * len(msg.accruals)
    return 256
