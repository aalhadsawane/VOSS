"""Artifact registry actor (doc 08 §2): serves encrypted bundles and rootfs by digest (bulk transfer)."""

from __future__ import annotations

from voss.core.messages import Chunk, Fetch, Message
from voss.runtime.actor import Actor


class Registry(Actor):
    role = "registry"

    def on_message(self, msg: Message) -> None:
        if isinstance(msg, Fetch):
            self.send(msg.reply_to, Chunk(msg.digest, msg.nbytes))
