"""Router pending table entries and the per-invocation latency row (doc 06 §2, doc 05 §7 components)."""

from __future__ import annotations

from dataclasses import dataclass, field

from voss.core.ids import WorkerId
from voss.core.kernel import Handle
from voss.core.types import Invocation, Outcome


@dataclass
class Pending:
    inv: Invocation
    cluster: int | None = None
    t_first_enqueue: float | None = None
    t_cluster: float = 0.0
    resends: int = 0
    spills: int = 0
    accepted: bool = False
    excluded: set[int] = field(default_factory=set)
    workers: dict[int, WorkerId] = field(default_factory=dict)
    timers: list[Handle] = field(default_factory=list)


def row(p: Pending, region: str, status: str, o: Outcome | None, now: float) -> dict[str, object]:
    """Terminal row: ``route + retry + batch_wait + decide + net_in + wait + trust + startup + exec + net_out``
    equals ``e2e`` for successful invocations (doc 05 §7)."""
    inv = p.inv
    first = p.t_first_enqueue if p.t_first_enqueue is not None else now
    out: dict[str, object] = {
        "inv": int(inv.id),
        "fn": inv.fn,
        "tenant": inv.tenant,
        "origin": inv.origin,
        "router": region,
        "cluster": -1 if p.cluster is None else p.cluster,
        "slo_class": int(inv.slo_class),
        "t_arrive": inv.t_arrive,
        "t_done": now,
        "e2e": now - inv.t_arrive,
        "deadline": inv.deadline,
        "outcome": status,
        "resends": p.resends,
        "spills": p.spills,
        "route": first - inv.t_arrive,
    }
    if o is None:
        out.update(worker=-1, attempts=len(p.workers), met=False, start_level="", tier="", trust_cold=False)
        return out
    t = o.timings
    out.update(
        worker=int(o.worker),
        attempts=o.attempt + 1,
        met=now - inv.t_arrive <= inv.deadline,
        retry=t.t_enqueue - first,
        batch_wait=t.batch_wait,
        decide=t.t_dispatch - t.t_enqueue - t.batch_wait,
        net_in=(t.t_received - t.t_dispatch) + t.input_wait,
        wait=t.wait,
        trust=t.trust,
        startup=t.startup,
        exec=t.exec,
        net_out=now - t.t_sent,
        start_level=o.start_level,
        tier=o.tier,
        trust_cold=o.trust_cold,
    )
    return out
