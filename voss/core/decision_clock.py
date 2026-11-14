"""Decision latency is never free (doc 01 §7, docs/REVISION_PLAN.md V10).

``charge(kind, work, host_speed, wall_s)`` returns the simulated seconds before a decision takes effect.

- ``modeled``: ``a + b·work`` per kind, divided by host speed (deterministic). In v2 the coefficients come from timing
  the real policy code on a stated provider CPU (V10); until then they are the defaults in ``DecisionClockConfig``.
- ``measured``: the caller's wall-clock seconds × ``cpu_scale`` / host speed (used by the real-time emulation).

Every charge is reported to an optional ``sink`` (the run logs them in the ``solver`` table).
"""

from __future__ import annotations

from collections.abc import Callable

from voss.core.config import DecisionClockConfig

Sink = Callable[[str, float, float, float], None]  # kind, work, wall_s, charged_s


class DecisionClock:
    def __init__(self, cfg: DecisionClockConfig, sink: Sink | None = None) -> None:
        self.cfg = cfg
        self.sink = sink

    def charge(self, kind: str, work: float = 0.0, host_speed: float = 1.0, wall_s: float = 0.0) -> float:
        if self.cfg.mode == "modeled":
            a, b = self.cfg.coeffs.get(kind, (0.0, 0.0))
            secs = (a + b * work) / max(host_speed, 1e-9)
        else:
            secs = wall_s * self.cfg.cpu_scale / max(host_speed, 1e-9)
        if self.sink is not None:
            self.sink(kind, work, wall_s, secs)
        return secs
