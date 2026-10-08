"""Actor base (doc 01 §6): an actor lives on a host, dies with it, and reacts only to messages and timers.

``ActorContext`` is the shared, read-mostly environment: kernel, network, recorder, rng, decision clock, config and
the static directory of orchestrator-tier addresses (service discovery is not modeled).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from voss.core.config import RunConfig
from voss.core.decision_clock import DecisionClock
from voss.core.ids import Addr, NodeId, TenantId
from voss.core.kernel import Handle, Kernel
from voss.core.messages import Message, size_of
from voss.core.rng import RngFactory
from voss.metrics.recorder import Recorder
from voss.world.network import Network


@dataclass
class Directory:
    """Addresses of orchestrator-tier and tenant services."""

    orchestrator: Addr = ("orch", "orchestrator")
    opdb: Addr = ("opdb", "orchestrator")
    verifier: Addr = ("verifier", "verifier")
    registry: Addr = ("registry", "registry")
    routers: tuple[Addr, ...] = ()
    kbs: dict[TenantId, Addr] = field(default_factory=dict)


@dataclass
class ActorContext:
    kernel: Kernel
    net: Network
    rec: Recorder
    rng: RngFactory
    clock: DecisionClock
    cfg: RunConfig
    directory: Directory


class Actor:
    """Base class. Subclasses decode a message, call a policy and send messages (AGENTS.md rule 3)."""

    role: str = "actor"

    def __init__(self, host: NodeId, ctx: ActorContext) -> None:
        self.node = host
        self.ctx = ctx
        self.addr: Addr = (self.role, host)
        self._gen = 0

    @property
    def now(self) -> float:
        return self.ctx.kernel.now

    def send(self, dst: Addr, msg: Message) -> bool:
        return self.ctx.net.send(self.addr, dst, msg, size_of(msg))

    def after(self, dt: float, fn: Any, *args: Any) -> Handle:
        """Timer that dies with the actor's memory (``cancel_timers``)."""
        return self.ctx.kernel.after(dt, self._fire, self._gen, fn, args)

    def _fire(self, gen: int, fn: Any, args: tuple[Any, ...]) -> None:
        if gen == self._gen:
            fn(*args)

    def cancel_timers(self) -> None:
        """Forget every pending timer (the host lost its memory)."""
        self._gen += 1

    def on_message(self, msg: Message) -> None:
        raise NotImplementedError
