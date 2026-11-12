"""Worker-side support for progress detection (doc 07 §2): the attested agent answers the scheduler's probes about
attempts it is running or has finished."""

from __future__ import annotations

from collections import deque
from typing import TYPE_CHECKING, Any

from voss.core.ids import Addr, ClusterId, WorkerId
from voss.core.messages_ft import Pong, Probe
from voss.core.types import Outcome, WorkerState
from voss.runtime.actor import ActorContext
from voss.runtime.workerlib.attempt import Attempt
from voss.runtime.workerlib.host import HostLocal

KEEP_FINISHED = 512


class RecoveryMixin:
    ctx: ActorContext
    host: HostLocal
    attempts: dict[tuple[int, int], Attempt]
    finished_at: dict[tuple[int, int], float]
    finished_order: deque[tuple[int, int]]
    omitted: set[tuple[int, int]]
    cluster: ClusterId | None

    if TYPE_CHECKING:

        @property
        def now(self) -> float: ...
        def send(self, dst: Addr, msg: Any) -> bool: ...
        def state(self) -> WorkerState: ...

    def _init_recovery(self) -> None:
        self.finished_at, self.finished_order, self.omitted = {}, deque(), set()

    def _finished(self, att: Attempt, out: Outcome | None) -> None:
        key = (int(att.inv.id), att.inv.attempt)
        self.finished_at[key] = self.now
        self.finished_order.append(key)
        while len(self.finished_order) > KEEP_FINISHED:
            self.finished_at.pop(self.finished_order.popleft(), None)

    def _probe(self, m: Probe) -> None:
        """The attested agent answers truthfully; an omitting owner drops the reply with the result."""
        key = (int(m.inv), m.attempt)
        if key in self.omitted or not self.host.up:
            return
        w = WorkerId(self.host.worker)
        if key in self.attempts:
            self.send(m.scheduler, Pong(m.inv, m.attempt, w, "running"))
        elif key in self.finished_at:
            self.send(m.scheduler, Pong(m.inv, m.attempt, w, "done", self.finished_at[key]))
        else:
            self.send(m.scheduler, Pong(m.inv, m.attempt, w, "unknown"))
