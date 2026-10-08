"""Typed messages between actors (doc 08 §4). One frozen dataclass per message kind."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Message:
    """Base class of every message sent through ``net.send``."""
