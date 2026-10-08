"""Decision latency is never free (doc 01 §7).

``charge(kind, work, host_speed, wall_s)`` returns the simulated seconds before a decision takes effect.

- ``modeled``: ``a + b·work`` per kind, divided by host speed.
- ``measured``: the caller's wall-clock seconds × ``cpu_scale`` / host speed.
- ``replay``: the next value logged for that kind by a previous ``measured`` run.
"""

from __future__ import annotations

import json
from collections import defaultdict, deque
from pathlib import Path

from voss.core.config import DecisionClockConfig


class DecisionClock:
    """Charges simulated time for decisions and keeps a per-kind log for replay."""

    def __init__(self, cfg: DecisionClockConfig) -> None:
        self.cfg = cfg
        self.log: list[tuple[str, float]] = []
        self._replay: dict[str, deque[float]] = defaultdict(deque)
        if cfg.mode == "replay":
            if cfg.replay_log is None:
                raise ValueError("decision_clock.replay requires replay_log")
            for kind, secs in json.loads(Path(cfg.replay_log).read_text()):
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
        return secs

    def dump(self, path: Path) -> None:
        """Write the charge log so a later run can use ``mode=replay``."""
        path.write_text(json.dumps(self.log))
