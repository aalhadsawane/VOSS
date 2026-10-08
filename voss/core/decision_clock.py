"""Decision latency is never free (doc 01 §7).

``charge(kind, work, host_speed, wall_s)`` returns the simulated seconds before a decision takes effect.

- ``modeled``: ``a + b·work`` per kind, divided by host speed (default for sweeps; deterministic).
- ``measured``: the caller's wall-clock seconds × ``cpu_scale`` / host speed (solver studies E02/E04).
- ``replay``: the charges logged by a previous run, per kind and in order (reproduces ``measured`` runs bit for bit).

Every charge is reported to an optional ``sink`` (the run logs them in the ``solver`` table).
"""

from __future__ import annotations

from collections import defaultdict, deque
from collections.abc import Callable, Iterable

from voss.core.config import DecisionClockConfig

Sink = Callable[[str, float, float, float], None]  # kind, work, wall_s, charged_s


class DecisionClock:
    def __init__(
        self, cfg: DecisionClockConfig, replay: Iterable[tuple[str, float]] | None = None, sink: Sink | None = None
    ) -> None:
        self.cfg = cfg
        self.sink = sink
        self.log: list[tuple[str, float]] = []
        self._replay: dict[str, deque[float]] = defaultdict(deque)
        if cfg.mode == "replay":
            if replay is None:
                raise ValueError("decision_clock.mode=replay needs a replay log")
            for kind, secs in replay:
                self._replay[kind].append(float(secs))

    def charge(self, kind: str, work: float = 0.0, host_speed: float = 1.0, wall_s: float = 0.0) -> float:
        if self.cfg.mode == "modeled":
            a, b = self.cfg.coeffs.get(kind, (0.0, 0.0))
            secs = (a + b * work) / max(host_speed, 1e-9)
        elif self.cfg.mode == "measured":
            secs = wall_s * self.cfg.cpu_scale / max(host_speed, 1e-9)
        else:
            queue = self._replay[kind]
            if not queue:
                raise RuntimeError(f"replay log exhausted for kind '{kind}'")
            secs = queue.popleft()
        self.log.append((kind, secs))
        if self.sink is not None:
            self.sink(kind, work, wall_s, secs)
        return secs
