"""Identifier types (doc 05 §3)."""

from __future__ import annotations

from typing import NewType

WorkerId = NewType("WorkerId", int)
InfraNodeId = NewType("InfraNodeId", str)
TenantId = NewType("TenantId", str)
FnId = NewType("FnId", str)
InvId = NewType("InvId", int)
ClusterId = NewType("ClusterId", int)

NodeId = int | str

Addr = tuple[str, int | str]
"""Network address of an actor: ``(role, host id)`` (doc 01 §6)."""
