"""Actor base (doc 01 §6): an actor lives on a host, dies with it, and reacts only to messages and timers."""

from __future__ import annotations

from voss.core.ids import NodeId
from voss.core.messages import Message


class Actor:
    """Base class. Subclasses decode a message, call a policy and send messages (AGENTS.md rule 3)."""

    def __init__(self, host: NodeId) -> None:
        self.host = host

    def on_message(self, msg: Message) -> None:
        raise NotImplementedError
