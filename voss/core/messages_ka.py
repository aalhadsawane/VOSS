"""Keep-alive baseline message (doc 03 §7, D-77)."""

from __future__ import annotations

from dataclasses import dataclass

from voss.core.ids import FnId
from voss.core.messages import Message


@dataclass(frozen=True, slots=True)
class KeepWarm(Message):
    """Per-function keep-alive directive of the histogram baseline (scheduler to worker): set the function's
    keep-alive window on this worker, optionally ``unload`` the sandbox that just finished (pre-warm window), and
    optionally ``build`` one warm sandbox in the background (the scheduler's re-warm after the pre-warm window)."""

    fn: FnId
    unload: bool
    build: bool
    keepalive_s: float
    epoch: int
