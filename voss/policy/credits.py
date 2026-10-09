"""Credits (doc 09 §4): a batch job over ``receipts`` + ``scheduler_roles`` + accruals writes ``credits``.

- Workers: ``ref_work_units × timeliness`` for verified results only (reference units, so throttling earns nothing).
- Donor caching: planner-pinned GB·h, accrued by the scheduler only while the worker answered probes.
- Schedulers: per assignment (the receipt's ``(cluster, epoch)`` names the holder) and per hour active or standby.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field

import numpy as np

from voss.core.messages_acct import ReceiptRow, RoleRecord

PAID = ("ok", "duplicate")


@dataclass(frozen=True)
class CreditParams:
    late_factor: float = 0.5
    cache_per_gb_h: float = 0.1
    sched_per_assign: float = 0.01
    sched_per_h: float = 1.0
    standby_per_h: float = 0.25


@dataclass
class Ledger:
    """The job's memory between settlements: role history per cluster and the last settlement time."""

    roles: dict[int, list[RoleRecord]] = field(default_factory=dict)
    holders: dict[tuple[int, int], int] = field(default_factory=dict)
    t_last: float = 0.0

    def add_roles(self, roles: Iterable[RoleRecord]) -> None:
        for r in roles:
            self.roles.setdefault(int(r.cluster), []).append(r)
            self.holders[(int(r.cluster), r.epoch)] = int(r.holder)
        for rs in self.roles.values():
            rs.sort(key=lambda r: (r.t, r.epoch))


@dataclass
class Settlement:
    credits: dict[tuple[int, str], list[float]]  # (worker, kind) → [amount, count]
    on_time: dict[int, float]  # reference units delivered on time (reputation input)
    late: dict[int, float]
    latency: np.ndarray  # settlement time − result time of the receipts settled


def timeliness(r: ReceiptRow, late_factor: float) -> float:
    return 1.0 if r.t_result - r.t_arrive <= r.deadline else late_factor


def _add(out: dict[tuple[int, str], list[float]], w: int, kind: str, amount: float) -> None:
    acc = out.setdefault((w, kind), [0.0, 0.0])
    acc[0] += amount
    acc[1] += 1


def _work(rows: Sequence[ReceiptRow], led: Ledger, p: CreditParams, s: Settlement) -> None:
    for r in rows:
        if r.status not in PAID or r.receipt is None:
            continue
        w, units = int(r.worker), r.receipt.ref_work_units
        f = timeliness(r, p.late_factor)
        _add(s.credits, w, "work" if r.status == "ok" else "duplicate", units * f)
        bucket = s.on_time if f == 1.0 else s.late
        bucket[w] = bucket.get(w, 0.0) + units
        holder = led.holders.get((r.cluster, r.receipt.epoch))
        if r.status == "ok" and holder is not None and holder >= 0:
            _add(s.credits, holder, "sched_assign", p.sched_per_assign)


def _roles(led: Ledger, now: float, p: CreditParams, s: Settlement) -> None:
    """Active/standby time in ``(t_last, now]``: each record holds until the cluster's next record."""
    for cid in sorted(led.roles):
        rs = led.roles[cid]
        for i, r in enumerate(rs):
            end = rs[i + 1].t if i + 1 < len(rs) else now
            dt = max(0.0, min(end, now) - max(r.t, led.t_last))
            if dt <= 0:
                continue
            if r.holder >= 0:
                _add(s.credits, int(r.holder), "sched_active", p.sched_per_h * dt / 3600)
            if r.standby is not None and r.standby >= 0:
                _add(s.credits, int(r.standby), "sched_standby", p.standby_per_h * dt / 3600)
        led.roles[cid] = [r for i, r in enumerate(rs) if i + 1 == len(rs) or rs[i + 1].t > now]


def settle(
    receipts: Sequence[ReceiptRow],
    accruals: Sequence[tuple[str, int, float]],
    led: Ledger,
    now: float,
    p: CreditParams,
) -> Settlement:
    """One settlement over the rows appended since the last one (roles must already be in the ledger)."""
    s = Settlement({}, {}, {}, np.array([now - r.t_result for r in receipts if r.status in PAID]))
    _work(receipts, led, p, s)
    for kind, w, mb_s in accruals:
        if kind == "cache" and mb_s > 0:
            _add(s.credits, int(w), "cache", p.cache_per_gb_h * mb_s / 1024 / 3600)
    _roles(led, now, p, s)
    led.t_last = now
    return s
