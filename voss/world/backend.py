"""Real-execution backend hook (doc 10 §4, P9b): lets the emulation testbed replace selected simulated delays and
the execution model by real work, while the simulator itself stays unchanged.

A backend is optional (``None`` everywhere in simulations). The world and runtime layers only know this protocol;
the implementation (Firecracker microVMs on a real node) lives in ``tools/emu``.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, Protocol


class RealBackend(Protocol):
    """Called by the lifecycle engine and by attempts; both call back on the kernel thread."""

    def handle_op(self, op: Any, env: Any, cont: Callable[[], None]) -> bool:
        """Perform ``op`` for real and call ``cont`` when done; return ``False`` to leave it to the simulator."""

    def execute(self, worker: int, fn: Any, in_bytes: int, timeout_s: float, done: Callable[[bool], None]) -> None:
        """Run one invocation of ``fn`` for real on ``worker``; ``done(ok)`` fires on completion or timeout."""
