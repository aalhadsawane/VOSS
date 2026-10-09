"""Exogenous drivers (doc 01 §4): replay the scenario's session and arrival traces into the running system.

The session driver plays the world's owners (power on, drain, power off); the client driver plays clients sending
``INVOKE`` to their nearest router. Each driver keeps one pending kernel event and chains through its sorted trace.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import numpy as np
import pandas as pd

from voss.core.ids import Addr, FnId, InvId, TenantId
from voss.core.kernel import Kernel
from voss.core.messages import Invoke, OwnerEvent
from voss.core.types import Invocation, SloClass
from voss.world.network import Network
from voss.world.scenario import Scenario


class TraceDriver:
    """Feeds rows of a time-sorted frame to ``handle(row)`` at their times (``t < 0`` is clipped to 0)."""

    def __init__(self, kernel: Kernel, frame: pd.DataFrame, handle: Callable[[dict[str, Any]], None]) -> None:
        self.k, self.handle = kernel, handle
        self.rows = frame.to_dict("records")
        self.i = 0

    def start(self) -> None:
        self._arm()

    def _arm(self) -> None:
        if self.i < len(self.rows):
            self.k.at(max(0.0, float(self.rows[self.i]["t"]), self.k.now), self._fire)

    def _fire(self) -> None:
        t = max(0.0, float(self.rows[self.i]["t"]))
        while self.i < len(self.rows) and max(0.0, float(self.rows[self.i]["t"])) <= t:
            row = self.rows[self.i]
            self.i += 1
            self.handle(row)
        self._arm()


def session_events(scn: Scenario, until: float | None = None) -> pd.DataFrame:
    """Owner events of ``[0, until)``: sessions starting before the horizon (prebooted at 0 if already running), and
    their drains and ends up to ``until`` (default: the horizon). Owners keep powering off during the drain window."""
    end = scn.horizon if until is None else until
    s = scn.sessions.sessions
    s = s[(s.end > 0) & (s.start < scn.horizon)]
    g = s[s.drain_t.notna() & (s.drain_t < end)]
    e = s[s.end < end]
    f = scn.sessions.fake_drains
    f = f[(f.t >= 0) & (f.t < end)]
    parts = [
        pd.DataFrame({"t": s.start, "o": 1, "kind": "start", "worker": s.worker, "deadline": 0.0, "graceful": False}),
        pd.DataFrame(
            {"t": g.drain_t, "o": 2, "kind": "drain", "worker": g.worker, "deadline": g.end, "graceful": True}
        ),
        pd.DataFrame(
            {"t": e.end, "o": 0, "kind": "end", "worker": e.worker, "deadline": 0.0, "graceful": e.drain_t.notna()}
        ),
        pd.DataFrame(
            {"t": f.t, "o": 2, "kind": "drain", "worker": f.worker, "deadline": f.deadline, "graceful": False}
        ),
    ]
    ev = pd.concat([p for p in parts if len(p)], ignore_index=True)
    ev["prebooted"] = ev.t <= 0
    ev["t"] = ev.t.clip(lower=0.0)
    return ev.sort_values(["t", "o", "worker"], kind="stable").reset_index(drop=True)


def owner_event(row: dict[str, Any]) -> OwnerEvent:
    return OwnerEvent(
        str(row["kind"]),
        prebooted=bool(row["prebooted"]),
        deadline=float(row["deadline"]),
        graceful=bool(row["graceful"]),
    )


def nearest(net: Network, src: str, candidates: list[Addr]) -> Addr:
    return min(candidates, key=lambda a: (net.rtt(src, a[1]), str(a[1])))


def invocations(scn: Scenario) -> pd.DataFrame:
    """Arrival rows enriched with ids and function metadata, ready for the client driver."""
    a = scn.arrivals.frame.copy()
    a["inv"] = np.arange(len(a))
    return a


def make_invocation(scn: Scenario, row: dict[str, Any]) -> Invocation:
    fn = scn.catalog.functions[int(row["fn"])]
    return Invocation(
        id=InvId(int(row["inv"])),
        fn=FnId(fn.name),
        tenant=TenantId(fn.tenant),
        origin=int(row["origin"]),
        t_arrive=float(row["t"]),
        in_bytes=int(row["in_bytes"]),
        slo_class=SloClass(int(row["slo_class"])),
        deadline=float(row["deadline_s"]),
        idempotent=fn.idempotent,
    )


def client_handler(net: Network, scn: Scenario, routers: list[Addr]) -> Callable[[dict[str, Any]], None]:
    """Clients live at origin metros and send ``INVOKE`` to their nearest router."""
    near = {i: nearest(net, f"client:{i}", routers) for i in range(len(scn.metros))}

    def handle(row: dict[str, Any]) -> None:
        inv = make_invocation(scn, row)
        msg = Invoke(inv)
        net.send(("client", f"client:{inv.origin}"), near[inv.origin], msg, 600)

    return handle
