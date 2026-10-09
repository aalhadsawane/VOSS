"""Control-plane fault injection (doc 07 §5, E15): at the times of the scenario's ``control_faults`` trace, the current
scheduler of the target cluster crashes, black-holes (drops everything but keepalives), slows down, or is partitioned
from everyone. Ground truth for detection metrics is logged as ``fault_start`` / ``fault_end`` events."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from voss.core.ids import Addr, WorkerId
from voss.core.kernel import Kernel
from voss.core.messages import KeepaliveSummary, Message
from voss.metrics.recorder import Recorder
from voss.metrics.schema import Table
from voss.runtime.orchestrator import Orchestrator
from voss.runtime.scheduler_role import SchedulerRole
from voss.world.network import Network

ISOLATED = 99


def blackhole(src: Addr, dst: Addr, msg: Message) -> bool:
    """A scheduler host that keeps its keepalives flowing and drops all other scheduler traffic."""
    return src[0] == "sched" and not isinstance(msg, KeepaliveSummary)


class FaultDriver:
    def __init__(
        self,
        kernel: Kernel,
        net: Network,
        rec: Recorder,
        orch: Orchestrator,
        scheds: dict[WorkerId, SchedulerRole],
        owner: Callable[[dict[str, Any]], None],
    ) -> None:
        self.k, self.net, self.rec, self.orch, self.scheds, self.owner = kernel, net, rec, orch, scheds, owner

    def start(self, faults: list[dict[str, Any]]) -> None:
        for row in faults:
            self.k.at(float(row["t"]), self._fire, row)

    def _target(self, target: str) -> tuple[int, WorkerId] | None:
        kind, _, idx = target.partition(":")
        ids = sorted(self.orch.book.clusters)
        if kind != "cluster" or not ids:
            return None
        c = self.orch.book.clusters[ids[int(idx) % len(ids)]]
        return (c.cid, c.holder[0]) if c.holder is not None else None

    def _fire(self, row: dict[str, Any]) -> None:
        hit = self._target(str(row["target"]))
        if hit is None:
            return
        cid, w = hit
        kind, dur = str(row["kind"]), float(row["duration_s"])
        self.rec.log(Table.EVENTS, t=self.k.now, kind="fault_start", worker=w, value=dur, cluster=cid, reason=kind)
        if kind == "sched_crash":
            if not self.net.hosts[w].up:
                return
            self.owner({"worker": w, "kind": "end", "prebooted": False, "deadline": 0.0, "graceful": False})
        elif kind == "sched_blackhole":
            self.net.set_filter(w, blackhole)
        elif kind == "sched_slow":
            self.scheds[w].hl.extra.update(slow_factor=float(row["factor"]), slow_until=self.k.now + dur)
        elif kind == "sched_partition":
            self.net.set_partition(w, ISOLATED)
        self.k.after(dur, self._end, kind, w, cid)

    def _end(self, kind: str, w: WorkerId, cid: int) -> None:
        self.rec.log(Table.EVENTS, t=self.k.now, kind="fault_end", worker=w, value=0.0, cluster=cid, reason=kind)
        if kind == "sched_crash" and not self.net.hosts[w].up:
            self.owner({"worker": w, "kind": "start", "prebooted": False, "deadline": 0.0, "graceful": False})
        elif kind == "sched_blackhole":
            self.net.set_filter(w, None)
        elif kind == "sched_slow":
            self.scheds[w].hl.extra.pop("slow_until", None)
        elif kind == "sched_partition":
            self.net.set_partition(w, 0)
